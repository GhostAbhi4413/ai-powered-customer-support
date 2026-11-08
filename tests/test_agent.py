import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from google.genai import types
import httpx
from backend.app.config import Settings
from backend.app.db.database import initialize, connection
from backend.app.db.__main__ import seed_demo
from backend.app.main import create_app
from backend.app.ai.grok import GroqModel
from backend.app.services.support import SupportError


def response(name, args, call_id='call-1'):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role='model', parts=[types.Part(function_call=types.FunctionCall(name=name, args=args, id=call_id), thought_signature=b'test-signature')]))])


class AgentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'agent.sqlite3'
        initialize(self.path)
        seed_demo(self.path)
        self.model = Mock()
        self.settings = Settings(database_path=self.path)
        self.app = create_app(self.settings, clock=lambda: datetime(2026,11,6,12,tzinfo=timezone.utc), model_factory=lambda _:self.model)
        self.client = self.enterContext(TestClient(self.app))
        self.request_id = str(uuid4())

    def chat(self, message='Check my order 1'):
        return self.client.post('/agent/chat', json={'request_id':self.request_id,'customer_id':1,'message':message})

    def approve(self, action_id, approve=True, customer_id=1):
        return self.client.post(f'/agent/actions/{action_id}/confirm',json={'customer_id':customer_id,'approve':approve})

    def test_read_tool_and_structured_final_preserve_signature(self):
        first = response('get_order',{'order_id':1})
        self.model.generate.side_effect = [first,response('final_response',{'message':'Your order is delivered.'})]
        with self.assertLogs('support.agent',level='INFO') as logs:
            result = self.chat()
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['tools'][0]['tool'],'get_order')
        self.assertEqual(result.json()['tools'][0]['data']['status'],'delivered')
        history = self.model.generate.call_args_list[1].args[0]
        self.assertEqual(history[1].parts[0].thought_signature,b'test-signature')
        self.assertEqual(history[2].parts[0].function_response.id,'call-1')
        self.assertNotIn('test-only-token',''.join(logs.output))
        self.assertNotIn('customer@example',''.join(logs.output))
        self.model.close.assert_called_once()

    def test_customer_id_scopes_agent_operations_without_authentication(self):
        self.assertEqual(self.client.get('/customers/1').status_code,200)
        self.assertEqual(self.client.get('/customers/999').status_code,404)
        self.assertEqual(self.client.post('/agent/chat',json={'request_id':self.request_id,'message':'Hi'}).status_code,422)
        self.model.generate.return_value = response('get_order',{'order_id':1,'customer_id':999})
        self.assertEqual(self.chat().status_code,502)

    def test_pending_return_approval_and_duplicate_confirmation(self):
        args={'order_id':1,'reason':'Damaged','items':[{'order_item_id':1,'quantity':1}]}
        self.model.generate.return_value=response('request_return',args)
        first=self.chat('Return one mug')
        self.assertEqual(first.status_code,200,first.text)
        action=first.json()['action']['action_id']
        self.assertEqual(first.json()['status'],'pending_approval')
        with connection(self.path,readonly=True) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM returns').fetchone()[0],0)
        self.assertEqual(self.chat('Return one mug').json()['action']['action_id'],action)
        result=self.approve(action)
        self.assertEqual(result.json()['status'],'ok',result.text)
        self.assertEqual(self.approve(action).json(),result.json())
        with connection(self.path,readonly=True) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM returns').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT state FROM agent_actions').fetchone()[0],'completed')

    def test_rejected_action_never_executes(self):
        self.model.generate.return_value=response('cancel_order',{'order_id':1})
        action=self.chat().json()['action']['action_id']
        self.assertEqual(self.approve(action,False).json()['status'],'error')
        self.assertEqual(self.approve(action).json()['detail'],'Action rejected by user')

    def test_policy_rechecked_on_approval(self):
        with connection(self.path) as db,db:
            db.execute("UPDATE orders SET status='confirmed',created_at='2026-11-06 11:00:00'")
            db.execute("UPDATE shipments SET status='pending',shipped_at=NULL,delivered_at=NULL")
        self.model.generate.return_value=response('cancel_order',{'order_id':1})
        action=self.chat('Cancel order 1').json()['action']['action_id']
        with connection(self.path) as db,db:
            db.execute("UPDATE orders SET status='shipped'")
        self.assertEqual(self.approve(action).json()['status'],'error')
        with connection(self.path,readonly=True) as db:
            self.assertEqual(db.execute('SELECT status FROM orders').fetchone()[0],'shipped')

    def test_address_and_cancel_tools_execute_services(self):
        with connection(self.path) as db,db:
            db.execute("UPDATE orders SET status='confirmed',created_at='2026-11-06 11:00:00'")
            db.execute("UPDATE shipments SET status='pending',shipped_at=NULL,delivered_at=NULL")
        self.model.generate.return_value=response('update_address',{'order_id':1,'delivery_address':'New Example Lane'})
        action=self.chat('Update address').json()['action']['action_id']
        self.assertEqual(self.approve(action).json()['data']['delivery_address'],'New Example Lane')
        self.request_id=str(uuid4())
        self.model.generate.return_value=response('cancel_order',{'order_id':1})
        action=self.chat('Cancel').json()['action']['action_id']
        self.assertEqual(self.approve(action).json()['data']['status'],'cancelled')

    def test_bad_tool_unknown_tool_empty_response_and_loop_cap(self):
        for model_response in (response('run_sql',{}),response('request_return',{'order_id':1}),types.GenerateContentResponse()):
            self.model.generate.return_value=model_response
            self.assertEqual(self.chat().status_code,502)
        self.model.generate.return_value=response('get_order',{'order_id':1})
        self.model.generate.reset_mock()
        self.assertEqual(self.chat().status_code,502)
        self.assertEqual(self.model.generate.call_count,self.settings.agent_max_steps)

    def test_tool_failure_returns_safe_result(self):
        self.model.generate.side_effect=[response('get_order',{'order_id':999}),response('final_response',{'message':'Order not found.'})]
        result=self.chat()
        self.assertEqual(result.json()['tools'][0]['status'],'error')

    def test_unknown_owner_and_uncertain_action_not_replayed(self):
        self.assertEqual(self.approve(str(uuid4())).status_code,404)
        self.model.generate.return_value=response('cancel_order',{'order_id':1})
        action=self.chat().json()['action']['action_id']
        with connection(self.path) as db,db:
            db.execute("UPDATE agent_actions SET state='executing' WHERE id=?",(action,))
        self.assertEqual(self.approve(action).status_code,409)

    def test_missing_credentials_fail_closed(self):
        with self.assertRaises(SupportError) as caught:
            GroqModel(Settings(groq_api_key=None))
        self.assertEqual(caught.exception.status,503)

    def test_approval_cannot_cross_customer(self):
        self.model.generate.return_value=response('cancel_order',{'order_id':1})
        action=self.chat().json()['action']['action_id']
        self.assertEqual(self.approve(action, customer_id=999).status_code,404)

    def test_concurrent_confirmation_dispatches_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from backend.app.ai.actions import confirm
        args={'order_id':1,'reason':'Damaged','items':[{'order_item_id':1,'quantity':1}]}
        self.model.generate.return_value=response('request_return',args)
        action=self.chat().json()['action']['action_id']
        def approve():
            try:
                return confirm(self.app.state.support,1,action,True).status
            except SupportError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(lambda _:approve(),range(2)))
        self.assertIn('ok',outcomes)
        self.assertTrue(all(o in ('ok',409) for o in outcomes))
        with connection(self.path,readonly=True) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM returns').fetchone()[0],1)

    def test_existing_version_one_database_migrates_without_data_loss(self):
        from backend.app.db.database import APPLICATION_ID
        import sqlite3
        from contextlib import closing
        old=Path(self.path.parent)/'old.sqlite3'
        with closing(sqlite3.connect(old)) as db, db:
            db.executescript(Path('backend/app/db/schema.sql').read_text(encoding='utf-8'))
            db.execute(f'PRAGMA application_id={APPLICATION_ID}')
            db.execute('PRAGMA user_version=1')
        seed_demo(old)
        initialize(old)
        with connection(old,readonly=True) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM agent_actions').fetchone()[0],0)

    def test_sdk_retries_and_timeout_are_bounded(self):
        settings=Settings(groq_api_key='test-only-key')
        completion = {'choices': [{'message': {'tool_calls': [{'id': 'call-1', 'type': 'function', 'function': {'name': 'final_response', 'arguments': '{"message":"Hello"}'}}]}}]}
        with patch('backend.app.ai.grok.httpx.Client') as constructor, patch('backend.app.ai.grok.time.sleep'):
            model=GroqModel(settings)
            mock=constructor.return_value.post
            rate_limited = httpx.Response(429, request=httpx.Request('POST', 'https://api.groq.com/openai/v1/chat/completions'))
            success = httpx.Response(200, json=completion, request=httpx.Request('POST', 'https://api.groq.com/openai/v1/chat/completions'))
            mock.side_effect=[rate_limited, success]
            model.generate([])
            self.assertEqual(mock.call_count,2)
            mock.reset_mock()
            mock.side_effect=httpx.ReadTimeout('private provider text')
            with self.assertRaises(SupportError) as caught:
                model.generate([])
            self.assertEqual(mock.call_count,2)
            self.assertNotIn('private',caught.exception.message)
            self.assertEqual(constructor.call_args.kwargs['timeout'],15.0)
