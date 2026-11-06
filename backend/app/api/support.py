"""HTTP routing; policies live in services."""
from typing import Annotated
from fastapi import APIRouter, Depends, Path, Request
from backend.app.models.support import AddressUpdate, Customer, Order, OrderDetails, ReturnRequest, ReturnResponse, Shipment

router = APIRouter(prefix='/customers', tags=['support'])
PositiveId = Annotated[int, Path(gt=0)]


def service(request: Request):
    return request.app.state.support


@router.get('/{customer_id}', response_model=Customer)
def customer(customer_id: PositiveId, support=Depends(service)):
    return support.customer(customer_id)


@router.get('/{customer_id}/orders', response_model=list[Order])
def orders(customer_id: PositiveId, support=Depends(service)):
    return support.orders(customer_id)


@router.get('/{customer_id}/orders/{order_id}', response_model=OrderDetails)
def order(customer_id: PositiveId, order_id: PositiveId, support=Depends(service)):
    return support.order(customer_id, order_id)


@router.get('/{customer_id}/orders/{order_id}/shipments', response_model=list[Shipment])
def shipments(customer_id: PositiveId, order_id: PositiveId, support=Depends(service)):
    return support.order(customer_id, order_id)['shipments']


@router.patch('/{customer_id}/orders/{order_id}/delivery-address', response_model=OrderDetails)
def address(customer_id: PositiveId, order_id: PositiveId, body: AddressUpdate, support=Depends(service)):
    return support.update_address(customer_id, order_id, body)


@router.post('/{customer_id}/orders/{order_id}/returns', response_model=ReturnResponse, status_code=201)
def returns(customer_id: PositiveId, order_id: PositiveId, body: ReturnRequest, support=Depends(service)):
    return support.request_return(customer_id, order_id, body)


@router.post('/{customer_id}/orders/{order_id}/cancel', response_model=OrderDetails)
def cancel(customer_id: PositiveId, order_id: PositiveId, support=Depends(service)):
    return support.cancel_order(customer_id, order_id)
