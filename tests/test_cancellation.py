import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.db.database import connection, initialize
from backend.app.db.__main__ import seed_demo
from backend.app.main import create_app
from backend.app.services.cancellation_policy import CancellationPolicy, DEFAULT_POLICY

NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)


class CancellationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'cancel.sqlite3'
        initialize(self.path)
        seed_demo(self.path)
        self.settings = Settings(database_path=self.path)
        self.client = self.enterContext(TestClient(create_app(self.settings, clock=lambda: NOW)))
        self.url = '/customers/1/orders/1/cancel'
        self.prepare()

    def prepare(self, status='confirmed', age=1):
        with connection(self.path) as db, db:
            db.execute('UPDATE orders SET status=?, created_at=?', (status, (NOW-timedelta(hours=age)).isoformat()))
            db.execute("UPDATE shipments SET status='pending', shipped_at=NULL, delivered_at=NULL")

    def test_success_persistence_and_retry(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'cancelled')
        with connection(self.path, readonly=True) as db:
            self.assertEqual(db.execute('SELECT status FROM orders WHERE id=1').fetchone()[0], 'cancelled')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM order_items').fetchone()[0], 1)
        self.assertEqual(self.client.post(self.url).json(), response.json())
        self.assertEqual(self.client.patch('/customers/1/orders/1/delivery-address', json={'delivery_address':'Other'}).status_code, 409)
        self.assertEqual(self.client.post('/customers/1/orders/1/returns', json={'reason':'Example','items':[{'order_item_id':1,'quantity':1}]}).status_code, 409)

    def test_window_and_status_rules(self):
        for status, age, expected in [('pending',0,200),('confirmed',24,200),('processing',1,200),('confirmed',24.001,409),('confirmed',-1,409),('shipped',1,409),('delivered',1,409)]:
            with self.subTest(status=status, age=age):
                self.prepare(status, age)
                self.assertEqual(self.client.post(self.url).status_code, expected)

    def test_missing_invalid_purchase_dates(self):
        for date in ('invalid', ''):
            with connection(self.path) as db, db:
                db.execute('UPDATE orders SET created_at=?', (date,))
            self.assertEqual(self.client.post(self.url).status_code, 409)

    def test_shipping_activity_rolls_back(self):
        for status, shipped, delivered in [('in_transit',None,None),('pending','2026-11-06',None),('pending',None,'2026-11-06')]:
            with connection(self.path) as db, db:
                db.execute('UPDATE shipments SET status=?, shipped_at=?, delivered_at=?', (status, shipped, delivered))
            self.assertEqual(self.client.post(self.url).status_code, 409)
            with connection(self.path, readonly=True) as db:
                self.assertEqual(db.execute('SELECT status FROM orders').fetchone()[0], 'confirmed')

    def test_return_records_and_customer_scope(self):
        with connection(self.path) as db, db:
            db.execute("INSERT INTO returns(order_id,status,reason) VALUES (1,'requested','Example')")
        self.assertEqual(self.client.post(self.url).status_code, 409)
        with connection(self.path) as db, db:
            db.execute("UPDATE returns SET status='cancelled'")
        self.assertEqual(self.client.post('/customers/999/orders/1/cancel').status_code, 404)
        self.assertEqual(self.client.post('/customers/1/orders/999/cancel').status_code, 404)
        self.assertEqual(self.client.post('/customers/0/orders/1/cancel').status_code, 422)
        self.assertEqual(self.client.post(self.url).status_code, 200)

    def test_policy_file_changes_behavior_and_invalid_policy_fails(self):
        policy = json.loads(DEFAULT_POLICY.read_text(encoding='utf-8'))
        path = Path(self.temp.name) / 'policy.json'
        policy['max_hours_after_purchase'] = 2
        policy['allowed_order_statuses'] = ['pending']
        path.write_text(json.dumps(policy), encoding='utf-8')
        settings = Settings(database_path=self.path, cancellation_policy_path=path)
        with TestClient(create_app(settings, clock=lambda: NOW)) as client:
            self.assertEqual(client.post(self.url).status_code, 409)
            self.prepare('pending', 3)
            self.assertEqual(client.post(self.url).status_code, 409)
            self.prepare('pending', 1)
            self.assertEqual(client.post(self.url).status_code, 200)
        for field, value in [('max_hours_after_purchase',0),('allowed_order_statuses',['shipped']),('unknown',True)]:
            path.write_text(json.dumps({**policy,field:value}), encoding='utf-8')
            with self.assertRaises(ValueError):
                CancellationPolicy.load(path)
        path.write_text('not JSON', encoding='utf-8')
        with self.assertRaises(ValueError):
            CancellationPolicy.load(path)
