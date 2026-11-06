import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backend.app.db.__main__ import seed_demo
from backend.app.db.database import connection, initialize
from backend.app.db.repository import create_return, get_customer, get_order_details, list_customer_orders, update_delivery_address


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.sqlite3'
        initialize(self.path)
        seed_demo(self.path)

    def count(self, table):
        # Table identifiers are test constants, never user input.
        with connection(self.path, readonly=True) as db:
            return db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def test_initialization_and_seed_are_idempotent(self):
        initialize(self.path)
        seed_demo(self.path)
        self.assertEqual(self.count('orders'), 1)
        with connection(self.path, readonly=True) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_reads_and_customer_scoping(self):
        self.assertIsNotNone(get_customer(self.path, 1))
        self.assertIsNone(get_customer(self.path, '1 OR 1=1'))
        self.assertEqual(len(list_customer_orders(self.path, 1)), 1)
        self.assertEqual(get_order_details(self.path, 1, 1)['shipments'][0]['status'], 'delivered')
        self.assertIsNone(get_order_details(self.path, 1, 999))

    def test_address_parameterization_and_scoping(self):
        address = "Example Lane'; DROP TABLE orders; --"
        update_delivery_address(self.path, 1, 1, address)
        self.assertEqual(get_order_details(self.path, 1, 1)['delivery_address'], address)
        with self.assertRaises(ValueError):
            update_delivery_address(self.path, 1, 999, 'Other address')
        with self.assertRaises(ValueError):
            update_delivery_address(self.path, 1, 1, ' ')

    def test_return_quantity_and_rollback(self):
        create_return(self.path, 1, 1, 'Damaged', [(1, 1)])
        with self.assertRaises(ValueError):
            create_return(self.path, 1, 1, 'Damaged', [(1, 2)])
        self.assertEqual(self.count('returns'), 1)
        with self.assertRaises(ValueError):
            create_return(self.path, 1, 1, 'Damaged', [(1, 1), (999, 1)])
        self.assertEqual(self.count('return_items'), 1)
        self.assertEqual(self.count('returns'), 1)
        with self.assertRaises(ValueError):
            create_return(self.path, 1, 999, 'Damaged', [(1, 1)])

    def test_constraints(self):
        statements = [
            ("INSERT INTO customers(name,email) VALUES (?,?)", ('Duplicate', 'CUSTOMER@example.invalid')),
            ("UPDATE orders SET customer_id=? WHERE id=1", (999,)),
            ("UPDATE orders SET status=? WHERE id=1", ('invalid',)),
            ("UPDATE order_items SET quantity=? WHERE id=1", (0,)),
            ("UPDATE order_items SET unit_price_minor=? WHERE id=1", (-1,)),
        ]
        for sql, parameters in statements:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                with connection(self.path) as db, db:
                    db.execute(sql, parameters)

    def test_return_item_cannot_reference_another_order(self):
        with connection(self.path) as db, db:
            db.execute("INSERT INTO orders(id,order_number,customer_id,status,currency,delivery_address) VALUES (2,'DEMO-2',1,'pending','INR','Example')")
            db.execute("INSERT INTO returns(id,order_id,status,reason) VALUES (1,2,'requested','Example')")
        with self.assertRaises(sqlite3.IntegrityError):
            with connection(self.path) as db, db:
                db.execute('INSERT INTO return_items VALUES (1,2,1,1)')

    def test_unrelated_database_is_untouched(self):
        other = Path(self.temp.name) / 'unrelated.sqlite3'
        with closing(sqlite3.connect(other)) as db, db:
            db.execute('CREATE TABLE important(value TEXT)')
            db.execute("INSERT INTO important VALUES ('keep')")
        before = other.read_bytes()
        with self.assertRaises(ValueError):
            initialize(other)
        self.assertEqual(other.read_bytes(), before)

    def test_readonly_connection(self):
        with connection(self.path, readonly=True) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM customers')


if __name__ == '__main__':
    unittest.main()
