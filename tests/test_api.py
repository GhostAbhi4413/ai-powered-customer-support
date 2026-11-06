import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.db.database import connection, initialize
from backend.app.db.__main__ import seed_demo
from backend.app.main import create_app
from backend.app.models.support import ReturnRequest
from backend.app.services.support import SupportError, SupportService

NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'api.sqlite3'
        initialize(self.path)
        seed_demo(self.path)
        self.settings = Settings(database_path=self.path)
        self.client = self.enterContext(TestClient(create_app(self.settings, clock=lambda: NOW)))
        self.base = '/customers/1/orders/1'

    def payload(self, quantity=1):
        return {'reason': 'Arrived damaged', 'items': [{'order_item_id': 1, 'quantity': quantity}]}

    def test_health_reads_and_missing_records(self):
        for url in ('/health', '/customers/1', '/customers/1/orders', self.base, self.base+'/shipments'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(self.base).json()['status'], 'delivered')
        for url in ('/customers/999', '/customers/999/orders', '/customers/999/orders/1'):
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_return_success_and_over_return_rollback(self):
        response = self.client.post(self.base+'/returns', json=self.payload())
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['status'], 'requested')
        self.assertEqual(self.client.post(self.base+'/returns', json=self.payload(2)).status_code, 409)
        with connection(self.path, readonly=True) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM returns').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT SUM(quantity) FROM return_items').fetchone()[0], 1)

    def test_address_update_persists_and_dispatch_blocks(self):
        self.assertEqual(self.client.patch(self.base+'/delivery-address', json={'delivery_address':'Example new address'}).status_code, 409)
        with connection(self.path) as db, db:
            db.execute("UPDATE orders SET status='processing'")
            db.execute("UPDATE shipments SET status='pending', shipped_at=NULL, delivered_at=NULL")
        response = self.client.patch(self.base+'/delivery-address', json={'delivery_address':'  Example new address  '})
        self.assertEqual(response.status_code, 200, response.text)
        with connection(self.path, readonly=True) as db:
            self.assertEqual(db.execute('SELECT delivery_address FROM orders WHERE id=1').fetchone()[0], 'Example new address')
        with connection(self.path) as db, db:
            db.execute("UPDATE shipments SET status='in_transit'")
        self.assertEqual(self.client.patch(self.base+'/delivery-address', json={'delivery_address':'Blocked address'}).status_code, 409)

    def test_validation_and_customer_scope(self):
        for payload in (self.payload(0), self.payload(True), {'reason':' ', 'items':[]}, {**self.payload(), 'extra':'value'}):
            self.assertEqual(self.client.post(self.base+'/returns', json=payload).status_code, 422)
        duplicate = self.payload()
        duplicate['items'] *= 2
        self.assertEqual(self.client.post(self.base+'/returns', json=duplicate).status_code, 422)
        self.assertEqual(self.client.patch(self.base+'/delivery-address', json={'delivery_address':' '}).status_code, 422)
        self.assertEqual(self.client.get('/customers/0').status_code, 422)
        self.assertEqual(self.client.post('/customers/999/orders/1/returns', json=self.payload()).status_code, 404)
        self.assertEqual(self.client.patch('/customers/999/orders/1/delivery-address', json={'delivery_address':'Example'}).status_code, 404)

    def test_return_window_service_boundaries(self):
        service = SupportService(self.settings, clock=lambda: NOW)
        request = ReturnRequest(**self.payload())
        for age, allowed in ((30, True), (30.001, False), (-1, False)):
            with self.subTest(age=age):
                delivered = (NOW-timedelta(days=age)).isoformat()
                with connection(self.path) as db, db:
                    db.execute('UPDATE shipments SET delivered_at=?', (delivered,))
                    db.execute('DELETE FROM return_items')
                    db.execute('DELETE FROM returns')
                if allowed:
                    self.assertEqual(service.request_return(1, 1, request)['status'], 'requested')
                else:
                    with self.assertRaises(SupportError) as error:
                        service.request_return(1, 1, request)
                    self.assertEqual(error.exception.status, 409)

    def test_undelivered_and_missing_timestamp(self):
        with connection(self.path) as db, db:
            db.execute("UPDATE orders SET status='shipped'")
        self.assertEqual(self.client.post(self.base+'/returns', json=self.payload()).status_code, 409)
        with connection(self.path) as db, db:
            db.execute("UPDATE orders SET status='delivered'")
            db.execute('UPDATE shipments SET delivered_at=NULL')
        self.assertEqual(self.client.post(self.base+'/returns', json=self.payload()).status_code, 409)

    def test_cors_and_database_failure(self):
        headers = {'Origin':'http://localhost:5173', 'Access-Control-Request-Method':'PATCH', 'Access-Control-Request-Headers':'authorization,content-type'}
        response = self.client.options(self.base+'/delivery-address', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['access-control-allow-origin'], headers['Origin'])
        self.assertIn('Content-Type',response.headers['access-control-allow-headers'])
        response = self.client.options('/health', headers={**headers, 'Origin':'https://unrelated.invalid'})
        self.assertEqual(response.status_code, 400)
        from unittest.mock import patch
        import sqlite3
        with patch('backend.app.main.connection', side_effect=sqlite3.OperationalError('private internal detail')):
            response = self.client.get('/health')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private', response.text)


if __name__ == '__main__':
    unittest.main()
