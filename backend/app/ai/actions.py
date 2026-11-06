"""Durable approval and at-most-once dispatch; uncertain actions are never replayed."""
import hashlib
import json
import sqlite3
from uuid import uuid4
from backend.app.db.database import connection
from backend.app.models.support import AddressUpdate, ReturnRequest, OrderDetails, ReturnResponse
from backend.app.services.support import SupportError
from .contracts import INPUTS, PendingAction, ToolResult


def propose(path, customer_id, request_id, tool, args):
    payload = json.dumps(args, sort_keys=True)
    fingerprint = hashlib.sha256((tool + payload).encode()).hexdigest()
    with connection(path) as db, db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO agent_actions(id,customer_id,request_id,fingerprint,tool,arguments,state) VALUES (?,?,?,?,?,?,?) ON CONFLICT(customer_id,request_id,fingerprint) DO NOTHING', (str(uuid4()), customer_id, request_id, fingerprint, tool, payload, 'pending'))
        row = db.execute('SELECT * FROM agent_actions WHERE customer_id=? AND request_id=? AND fingerprint=?', (customer_id, request_id, fingerprint)).fetchone()
        return PendingAction(action_id=row['id'], tool=row['tool'], arguments=json.loads(row['arguments']), state=row['state'])


def confirm(service, customer_id, action_id, approve):
    path = service.path
    with connection(path) as db, db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM agent_actions WHERE id=? AND customer_id=?', (action_id, customer_id)).fetchone()
        if row is None:
            raise SupportError(404, 'Action not found')
        if row['state'] in ('completed','failed','rejected'):
            return ToolResult.model_validate_json(row['result'])
        if row['state'] == 'executing':
            raise SupportError(409, 'Action is executing or requires manual review; it will not be replayed')
        if not approve:
            result = ToolResult(tool=row['tool'], status='error', detail='Action rejected by user')
            db.execute("UPDATE agent_actions SET state='rejected',result=? WHERE id=?", (result.model_dump_json(), action_id))
            return result
        db.execute("UPDATE agent_actions SET state='executing' WHERE id=?", (action_id,))
    # The durable claim commits before dispatch. A crash between claim and result
    # deliberately requires review instead of risking a duplicate return.
    try:
        args = INPUTS[row['tool']].model_validate_json(row['arguments'])
        if row['tool'] == 'update_address':
            data = OrderDetails.model_validate(service.update_address(customer_id, args.order_id, AddressUpdate(delivery_address=args.delivery_address))).model_dump(mode='json')
        elif row['tool'] == 'request_return':
            data = ReturnResponse.model_validate(service.request_return(customer_id, args.order_id, ReturnRequest(reason=args.reason, items=args.items))).model_dump(mode='json')
        elif row['tool'] == 'cancel_order':
            data = OrderDetails.model_validate(service.cancel_order(customer_id, args.order_id)).model_dump(mode='json')
        else:
            raise ValueError('Unknown action')
        result = ToolResult(tool=row['tool'], status='ok', data=data)
        state = 'completed'
    except SupportError as exc:
        result = ToolResult(tool=row['tool'], status='error', detail=exc.message)
        state = 'failed'
    except Exception:
        result = ToolResult(tool=row['tool'], status='error', detail='Action could not be verified; manual review required')
        state = 'failed'
    with connection(path) as db, db:
        db.execute('UPDATE agent_actions SET state=?,result=? WHERE id=?', (state, result.model_dump_json(), action_id))
    return result
