"""Parameterized persistence functions. Callers enforce authorization and policy."""

from .database import connection
from contextlib import nullcontext


def get_customer(path, customer_id):
    with connection(path, readonly=True) as db:
        row = db.execute('SELECT * FROM customers WHERE id = ?', (customer_id,)).fetchone()
        return dict(row) if row else None


def list_customer_orders(path, customer_id):
    with connection(path, readonly=True) as db:
        return [dict(row) for row in db.execute('SELECT * FROM orders WHERE customer_id = ? ORDER BY id', (customer_id,))]


def get_order_details(path, order_id, customer_id, *, db=None):
    with (nullcontext(db) if db is not None else connection(path, readonly=True)) as db:
        order = db.execute('SELECT * FROM orders WHERE id = ? AND customer_id = ?', (order_id, customer_id)).fetchone()
        if order is None:
            return None
        result = dict(order)
        result['items'] = [dict(r) for r in db.execute('SELECT * FROM order_items WHERE order_id = ? ORDER BY id', (order_id,))]
        result['shipments'] = [dict(r) for r in db.execute('SELECT * FROM shipments WHERE order_id = ? ORDER BY id', (order_id,))]
        result['returns'] = [dict(r) for r in db.execute('SELECT * FROM returns WHERE order_id = ? ORDER BY id', (order_id,))]
        return result


def update_delivery_address(path, order_id, customer_id, address, *, guard=None):
    if not address.strip():
        raise ValueError('Address must not be empty')
    with connection(path) as db, db:
        db.execute('BEGIN IMMEDIATE')
        if guard:
            guard(db)
        cursor = db.execute('UPDATE orders SET delivery_address = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND customer_id = ?', (address, order_id, customer_id))
        if cursor.rowcount != 1:
            raise ValueError('Order not found for customer')


def create_return(path, order_id, customer_id, reason, items, *, guard=None):
    """Record a request atomically; eligibility and refunds are separate policies."""
    items = list(items)
    if not items or not reason.strip():
        raise ValueError('Return requires a reason and items')
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            if guard:
                guard(db)
            if db.execute('SELECT id FROM orders WHERE id = ? AND customer_id = ?', (order_id, customer_id)).fetchone() is None:
                raise ValueError('Order not found for customer')
            return_id = db.execute("INSERT INTO returns(order_id, status, reason) VALUES (?, 'requested', ?)", (order_id, reason)).lastrowid
            for item_id, quantity in items:
                if type(quantity) is not int or quantity <= 0:
                    raise ValueError('Return quantity must be a positive integer')
                purchased = db.execute('SELECT quantity FROM order_items WHERE id = ? AND order_id = ?', (item_id, order_id)).fetchone()
                reserved = db.execute("SELECT COALESCE(SUM(ri.quantity), 0) FROM return_items ri JOIN returns r ON r.id = ri.return_id WHERE ri.order_item_id = ? AND r.status NOT IN ('rejected','cancelled')", (item_id,)).fetchone()[0]
                if purchased is None or quantity + reserved > purchased['quantity']:
                    raise ValueError('Return quantity exceeds available purchased quantity')
                db.execute('INSERT INTO return_items(return_id, order_id, order_item_id, quantity) VALUES (?, ?, ?, ?)', (return_id, order_id, item_id, quantity))
            db.commit()
            return return_id
        except Exception:
            db.rollback()
            raise


def get_return(path, return_id):
    with connection(path, readonly=True) as db:
        row = db.execute('SELECT * FROM returns WHERE id = ?', (return_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result['items'] = [dict(r) for r in db.execute('SELECT order_item_id, quantity FROM return_items WHERE return_id = ? ORDER BY order_item_id', (return_id,))]
        return result


def cancel_order(path, order_id, customer_id, *, guard):
    """Serialize policy checks and cancellation; return the committed snapshot."""
    with connection(path) as db, db:
        db.execute('BEGIN IMMEDIATE')
        if guard(db):
            cursor = db.execute("UPDATE orders SET status='cancelled', updated_at=CURRENT_TIMESTAMP WHERE id=? AND customer_id=?", (order_id, customer_id))
            if cursor.rowcount != 1:
                raise ValueError('Order not found for customer')
        return get_order_details(path, order_id, customer_id, db=db)
