"""Grok-powered chat and a separate explicit human confirmation endpoint."""
from uuid import UUID
from fastapi import APIRouter, Request
from backend.app.ai.contracts import AgentResponse, ChatRequest, ApprovalRequest, ToolResult
from backend.app.ai.actions import confirm
from backend.app.ai.workflow import run, event
from backend.app.services.support import SupportError

router = APIRouter(prefix='/agent', tags=['agent'])


@router.post('/chat', response_model=AgentResponse)
def chat(body: ChatRequest, request: Request):
    settings = request.app.state.settings
    model = request.app.state.model_factory(settings)
    try:
        return run(model, request.app.state.support, body.customer_id, body, settings.agent_max_steps)
    except SupportError:
        event(body.request_id, 0, 'workflow', 'error')
        raise
    finally:
        model.close()


@router.post('/actions/{action_id}/confirm', response_model=ToolResult)
def confirmation(action_id: UUID, body: ApprovalRequest, request: Request):
    result = confirm(request.app.state.support, body.customer_id, str(action_id), body.approve)
    event(action_id, 0, result.tool, result.status)
    return result
