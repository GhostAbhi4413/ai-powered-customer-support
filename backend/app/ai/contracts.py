"""Strict tool and workflow contracts; identity is never a model argument."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from backend.app.models.support import Text, ReturnRequest


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Empty(Strict):
    pass


class OrderInput(Strict):
    order_id: int = Field(gt=0, strict=True)


class AddressInput(OrderInput):
    delivery_address: Text


class ReturnInput(ReturnRequest):
    order_id: int = Field(gt=0, strict=True)


class FinalInput(Strict):
    message: Text


class ChatRequest(Strict):
    request_id: UUID
    customer_id: int = Field(gt=0, strict=True)
    message: str = Field(min_length=1, max_length=4000)


class ApprovalRequest(Strict):
    customer_id: int = Field(gt=0, strict=True)
    approve: bool = Field(strict=True)


class ToolResult(Strict):
    tool: str
    status: Literal['ok', 'error', 'pending_approval']
    data: dict | list | None = None
    detail: str | None = None


class PendingAction(Strict):
    action_id: str
    tool: str
    arguments: dict
    state: str


class AgentResponse(Strict):
    status: Literal['completed', 'pending_approval']
    message: str
    tools: list[ToolResult] = Field(default_factory=list)
    action: PendingAction | None = None


INPUTS = {'get_customer': Empty, 'list_orders': Empty, 'get_order': OrderInput,
          'get_shipping': OrderInput, 'update_address': AddressInput,
          'request_return': ReturnInput, 'cancel_order': OrderInput,
          'final_response': FinalInput}
WRITES = {'update_address', 'request_return', 'cancel_order'}
