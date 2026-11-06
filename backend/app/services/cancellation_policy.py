"""Validated, declarative cancellation policy; no executable rules in JSON."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_POLICY = Path(__file__).resolve().parents[3] / 'config' / 'cancellation_policy.json'


class CancellationPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)

    version: Literal[1]
    max_hours_after_purchase: int = Field(gt=0, le=8760)
    allowed_order_statuses: list[Literal['pending', 'confirmed', 'processing']] = Field(min_length=1)
    allowed_shipment_statuses: list[Literal['pending']] = Field(min_length=1)
    allowed_return_statuses: list[Literal['rejected', 'cancelled']]

    @classmethod
    def load(cls, path):
        try:
            return cls.model_validate_json(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise ValueError('Cancellation policy is missing or invalid; check its JSON schema') from None

    def rejection(self, order, now):
        """Return an explanation, or None if the order can be cancelled."""
        if order['status'] not in self.allowed_order_statuses:
            return 'Current order status does not allow cancellation'
        if not order['items']:
            return 'Order has no items; cancellation requires review'
        try:
            # SQLite CURRENT_TIMESTAMP is UTC without an explicit offset.
            purchased_at = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00'))
            if purchased_at.tzinfo is None:
                purchased_at = purchased_at.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            return 'Purchase date is unavailable; cancellation requires review'
        if purchased_at > now:
            return 'Purchase date is in the future; cancellation requires review'
        if now > purchased_at + timedelta(hours=self.max_hours_after_purchase):
            return 'Order is outside the cancellation window'
        if any(s['status'] not in self.allowed_shipment_statuses or s['shipped_at'] or s['delivered_at'] for s in order['shipments']):
            return 'Order has shipping activity and cannot be cancelled'
        if any(r['status'] not in self.allowed_return_statuses for r in order['returns']):
            return 'Order has an active or completed return and cannot be cancelled'
        return None
