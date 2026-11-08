"""Deterministic policies; mutation guards execute inside database transactions."""
from datetime import datetime, timedelta, timezone
from backend.app.db import repository as repo
from .cancellation_policy import CancellationPolicy


class SupportError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


class SupportService:
    def __init__(self, settings, clock=None):
        self.path = settings.database_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.cancellation_policy = CancellationPolicy.load(settings.cancellation_policy_path)

    def cancel_order(self, customer_id, order_id):
        def guard(db):
            order = self.order(customer_id, order_id, db)
            # Retrying a successful cancellation has no additional side effects.
            if order['status'] == 'cancelled':
                return False
            rejection = self.cancellation_policy.rejection(order, self.clock())
            if rejection:
                raise SupportError(409, rejection)
            return True
        return repo.cancel_order(self.path, order_id, customer_id, guard=guard)

    def customer(self, customer_id):
        result = repo.get_customer(self.path, customer_id)
        if result is None:
            raise SupportError(404, 'Customer not found')
        return result

    def orders(self, customer_id):
        self.customer(customer_id)
        return repo.list_customer_orders(self.path, customer_id)

    def order(self, customer_id, order_id, db=None):
        result = repo.get_order_details(self.path, order_id, customer_id, db=db)
        if result is None:
            raise SupportError(404, 'Order not found for customer')
        return result

    def update_address(self, customer_id, order_id, request):
        def guard(db):
            order = self.order(customer_id, order_id, db)
            if order['status'] not in ('pending','confirmed','processing') or any(s['status'] != 'pending' or s['shipped_at'] or s['delivered_at'] for s in order['shipments']):
                raise SupportError(409, 'Delivery address cannot change after dispatch or cancellation')
        repo.update_delivery_address(self.path, order_id, customer_id, request.delivery_address, guard=guard)
        return self.order(customer_id, order_id)

    def request_return(self, customer_id, order_id, request):
        ids = [item.order_item_id for item in request.items]
        if len(ids) != len(set(ids)):
            raise SupportError(422, 'Duplicate return items are not allowed')
        def guard(db):
            order = self.order(customer_id, order_id, db)
            shipments = order['shipments']
            policy = self.cancellation_policy.return_policy
            if order['status'] != policy.required_order_status or not shipments or any(s['status'] != policy.required_shipment_status or not s['delivered_at'] for s in shipments):
                raise SupportError(409, 'Only fully delivered orders can be returned')
            try:
                dates = [datetime.fromisoformat(s['delivered_at'].replace('Z', '+00:00')) for s in shipments]
                dates = [d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d for d in dates]
            except ValueError:
                raise SupportError(409, 'Delivery date is unavailable') from None
            now = self.clock()
            if any(d > now or now > d + timedelta(days=policy.window_days) for d in dates):
                raise SupportError(409, 'Order is outside the return window')
        try:
            result_id = repo.create_return(self.path, order_id, customer_id, request.reason, [(i.order_item_id, i.quantity) for i in request.items], guard=guard)
        except ValueError as exc:
            raise SupportError(409, str(exc)) from None
        return repo.get_return(self.path, result_id)
