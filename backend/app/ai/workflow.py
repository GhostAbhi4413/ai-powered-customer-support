"""Single bounded agent: model -> validated tools -> model, or approval pause."""
import json
import logging
import sqlite3
from pydantic import ValidationError
from google.genai import types
from backend.app.models.support import Customer, Order, OrderDetails, Shipment
from backend.app.services.support import SupportError
from .contracts import INPUTS, WRITES, AgentResponse, ToolResult
from .actions import propose

logger = logging.getLogger('support.agent')
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.propagate = False


def event(request_id, step, tool, status):
    # Deliberate allowlist: never log prompts, arguments, results, keys, tokens or PII.
    logger.info(json.dumps({'event':'agent_tool','request_id':str(request_id), 'step':step, 'tool':tool, 'status':status}))


def run(model, service, customer_id, request, max_steps):
    service.customer(customer_id)
    contents = [types.Content(role='user', parts=[types.Part(text=request.message)])]
    results = []
    cache = {}
    for step in range(max_steps):
        response = model.generate(contents)
        if not response.candidates or not response.candidates[0].content:
            raise SupportError(502, 'AI returned no usable response')
        content = response.candidates[0].content
        calls = [p.function_call for p in content.parts or [] if p.function_call]
        if not calls or len(calls) > 8:
            raise SupportError(502, 'AI returned an invalid tool response')
        # Validate the entire batch before executing any call; approval is terminal.
        try:
            parsed = [(call, INPUTS[call.name].model_validate(call.args or {})) for call in calls]
        except (KeyError, ValidationError, TypeError):
            raise SupportError(502, 'AI returned invalid tool arguments') from None
        if any(c.name in WRITES or c.name == 'final_response' for c, _ in parsed) and len(parsed) != 1:
            raise SupportError(502, 'AI must propose or finish one operation at a time')
        contents.append(content)  # Preserve full provider content and thought signatures.
        parts = []
        for call, args in parsed:
            if call.name == 'final_response':
                return AgentResponse(status='completed', message=args.message, tools=results)
            if call.name in WRITES:
                action = propose(service.path, customer_id, str(request.request_id), call.name, args.model_dump(mode='json'))
                if action.state != 'pending':
                    return AgentResponse(status='completed', message=f'This action is already recorded as {action.state}. Reuse its confirmation endpoint to retrieve the recorded result; executing actions require review.', tools=results, action=action)
                event(request.request_id, step, call.name, 'pending_approval')
                results.append(ToolResult(tool=call.name, status='pending_approval'))
                return AgentResponse(status='pending_approval', message='Review the proposed action and explicitly approve it before execution.', tools=results, action=action)
            key = call.name + args.model_dump_json()
            if key in cache:
                result = cache[key]
            else:
                try:
                    if call.name == 'get_customer':
                        data = Customer.model_validate(service.customer(customer_id)).model_dump(mode='json')
                    elif call.name == 'list_orders':
                        data = [Order.model_validate(o).model_dump(mode='json') for o in service.orders(customer_id)]
                    else:
                        order = OrderDetails.model_validate(service.order(customer_id, args.order_id))
                        data = order.model_dump(mode='json') if call.name == 'get_order' else [s.model_dump(mode='json') for s in order.shipments]
                    result = ToolResult(tool=call.name, status='ok', data=data)
                except SupportError as exc:
                    result = ToolResult(tool=call.name, status='error', detail=exc.message)
                except (sqlite3.Error, ValidationError):
                    result = ToolResult(tool=call.name, status='error', detail='Tool data is unavailable')
                cache[key] = result
            results.append(result)
            event(request.request_id, step, call.name, result.status)
            parts.append(types.Part(function_response=types.FunctionResponse(name=call.name, id=call.id, response=result.model_dump(mode='json'))))
        contents.append(types.Content(role='tool', parts=parts))
    raise SupportError(502, 'AI tool limit reached; please narrow your request')
