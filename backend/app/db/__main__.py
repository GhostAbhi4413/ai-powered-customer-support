"""Run initialization or explicit, idempotent synthetic demo seeding."""

import argparse

from .database import DEFAULT_DATABASE, connection, initialize


def seed_demo(path):
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute("SELECT 1 FROM orders WHERE order_number = 'DEMO-1001'").fetchone():
                db.rollback()
                return
            # Do not append sample data to databases containing user records.
            if db.execute('SELECT 1 FROM customers LIMIT 1').fetchone():
                raise ValueError('Demo seeding requires an empty customer table')
            customer = db.execute('INSERT INTO customers(name,email) VALUES (?,?)', ('Demo Customer', 'customer@example.invalid')).lastrowid
            order = db.execute('INSERT INTO orders(order_number,customer_id,status,currency,delivery_address) VALUES (?,?,?,?,?)', ('DEMO-1001', customer, 'delivered', 'INR', '10 Example Lane, Sample City, 000000, IN')).lastrowid
            db.execute('INSERT INTO order_items(order_id,sku,product_name,quantity,unit_price_minor) VALUES (?,?,?,?,?)', (order, 'DEMO-MUG', 'Sample ceramic mug', 2, 49900))
            db.execute('INSERT INTO shipments(order_id,carrier,tracking_reference,status,shipped_at,delivered_at) VALUES (?,?,?,?,?,?)', (order, 'Demo Carrier', 'DEMO-TRACK-1001', 'delivered', '2026-11-01T09:00:00Z', '2026-11-04T12:00:00Z'))
            db.commit()
        except Exception:
            db.rollback()
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', default=str(DEFAULT_DATABASE))
    parser.add_argument('--seed-demo', action='store_true')
    args = parser.parse_args()
    initialize(args.path)
    if args.seed_demo:
        seed_demo(args.path)
    print('Database initialization complete (schema version 2).')
