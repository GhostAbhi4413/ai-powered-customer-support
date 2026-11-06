"""Validated HTTP contracts."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
OrderStatus = Literal['pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled']


class RequestModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class AddressUpdate(RequestModel):
    delivery_address: Text


class ReturnItem(RequestModel):
    order_item_id: int = Field(gt=0, strict=True)
    quantity: int = Field(gt=0, strict=True)


class ReturnRequest(RequestModel):
    reason: Text
    items: list[ReturnItem] = Field(min_length=1, max_length=100)


class Customer(BaseModel):
    id: int
    name: str
    email: str
    phone: str | None
    created_at: str


class Order(BaseModel):
    id: int
    order_number: str
    customer_id: int
    status: OrderStatus
    currency: str
    delivery_address: str
    created_at: str
    updated_at: str


class OrderItem(BaseModel):
    id: int
    order_id: int
    sku: str
    product_name: str
    quantity: int
    unit_price_minor: int


class Shipment(BaseModel):
    id: int
    order_id: int
    carrier: str
    tracking_reference: str
    status: Literal['pending','dispatched','in_transit','delivered','exception','returned']
    shipped_at: str | None
    estimated_delivery_at: str | None
    delivered_at: str | None


class ReturnSummary(BaseModel):
    id: int
    order_id: int
    status: Literal['requested','approved','rejected','received','refunded','cancelled']
    reason: str
    created_at: str
    updated_at: str


class ReturnResponse(ReturnSummary):
    items: list[ReturnItem]


class OrderDetails(Order):
    items: list[OrderItem]
    shipments: list[Shipment]
    returns: list[ReturnSummary]


class Health(BaseModel):
    status: str


class Error(BaseModel):
    detail: str
