# Assessment application

FastAPI customer-support backend with SQLite persistence. Supports customer and
order lookup, shipping status, delivery address updates, and return requests.
Gemini tool calling and a React customer workspace are implemented.

## Local setup (PowerShell)

Use Python 3.14 and select `.venv\Scripts\python.exe` in VS Code.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

The development API documentation is available at http://127.0.0.1:8000/docs.

Configuration uses process environment variables `APP_NAME` and `APP_ENV`.
`.env.example` documents defaults; `.env` is not automatically loaded or modified.
Never commit real credentials. Do not print environment values during diagnostics.

Dependency ranges are in `requirements.txt`; `requirements.lock.txt`, when present,
records the verified installed versions and can be used with `pip install -r`.

YAML configuration and cloud deployment are deferred.

## SQLite persistence

Default database: `data/customer_support.sqlite3` (excluded from Git).
SQLite uses Python's standard library; AI dependencies are separate.

```powershell
.\.venv\Scripts\python.exe -m backend.app.db
# Explicit synthetic demo seed, only for an empty customer table:
.\.venv\Scripts\python.exe -m backend.app.db --seed-demo
# Use a workspace-local temp directory if the system temp folder is restricted:
$env:TEMP = Join-Path (Get-Location) '.setup-tmp'
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m unittest discover -v
```

`--path PATH` selects an alternative database. Initialization uses application ID
1129533520 and `PRAGMA user_version=2`. It refuses unrelated populated databases
and newer schema versions. Migrations are applied in one transaction; future schema
changes must add ordered migrations rather than replace existing tables.

Schema:

- `customers`: name, case-insensitive unique email, optional phone, creation time.
- `orders`: unique order number, customer foreign key, status, three-letter currency,
  delivery address snapshot, creation/update times.
- `order_items`: order foreign key, unique SKU per order, product name, positive
  integer quantity, nonnegative integer unit price in currency minor units.
- `shipments`: order foreign key, carrier/tracking pair unique, shipping status,
  shipped/estimated delivery/delivered timestamps. Orders may have multiple shipments.
- `returns`: order foreign key, return status, reason, creation/update times.
- `return_items`: return/item composite key, positive quantity, composite foreign
  keys ensuring the item and return belong to the same order.

Foreign keys are enabled for every connection. Customer/order/item lookup indexes
support retrieval. Repository writes use bound parameters and transactions; return
requests reserve quantities under an immediate transaction to prevent over-returning.
Rejected/cancelled returns do not reserve quantities. No refunds are executed.
Connection contexts always close; writing callers use transactions explicitly.

Read functions return dictionaries; no separate ORM is used. Repository functions
scope order access by customer ID. Customer IDs alone do not establish identity.
The agent uses the selected customer ID from the local workspace; production
identity and multi-user authorization remain outside this assessment.
No external shipping integration exists.

## Backend routes and policies

Start from the workspace root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

| Method | Path | Result |
| --- | --- | --- |
| GET | `/health` | Database connectivity check |
| GET | `/customers/{customer_id}` | Customer details |
| GET | `/customers/{customer_id}/orders` | Customer orders |
| GET | `/customers/{customer_id}/orders/{order_id}` | Order, status, items, shipments, returns |
| GET | `/customers/{customer_id}/orders/{order_id}/shipments` | Shipping details |
| PATCH | `/customers/{customer_id}/orders/{order_id}/delivery-address` | Update address |
| POST | `/customers/{customer_id}/orders/{order_id}/returns` | Create return request (201) |
| POST | `/customers/{customer_id}/orders/{order_id}/cancel` | Cancel eligible order (200; no body) |

Interactive contracts and request/response schemas: http://127.0.0.1:8000/docs.
PATCH body: `{"delivery_address":"10 Example Lane, Sample City"}`.
Return body: `{"reason":"Arrived damaged","items":[{"order_item_id":1,"quantity":1}]}`.
Errors: 404 for missing/customer-mismatched records, 409 for policy conflicts,
422 for malformed requests, 503 for database errors. Error bodies do not echo
request values or internal database details.

Provisional deterministic policies, pending business confirmation:

- Address changes require pending/confirmed/processing orders and no dispatched
  shipment, shipping timestamp, or delivery timestamp.
- Returns require a delivered order and every shipment delivered with a known
  delivery date. Each shipment must be within the configured window (inclusive
  at exactly 30 days by default); future delivery timestamps are rejected.
- Quantities must be positive integers, items unique in a request, and cumulative
  active returns cannot exceed purchased quantities. Return requests remain
  `requested`; this API does not issue refunds or contact carriers.
- Policy checks and writes share an immediate transaction to avoid race conditions.

Environment configuration (no `.env` files are automatically read):
`APP_DATABASE_PATH`, `APP_RETURN_WINDOW_DAYS` (default 30), and
`APP_CORS_ORIGINS` (JSON array, default `["http://localhost:5173"]`).
Existing `APP_NAME` and `APP_ENV` remain supported. CORS is restricted to configured
origins; it does not provide authentication.

Install testing dependencies with `python -m pip install -r requirements-dev.txt`.
Run `python -m unittest discover -v` and `python -m pip check` using the virtual
environment. Tests use temporary SQLite databases and a fixed clock. Coverage
includes service boundary checks, API responses, persisted writes, transaction
rollback, CORS, validation, and database-error handling. Current Starlette emits a
non-failing HTTPX deprecation notice; HTTPX 0.28.1 tests pass.

## JSON cancellation policy

`config/cancellation_policy.json` defines the versioned cancellation rules. Override
the location with `APP_CANCELLATION_POLICY_PATH`; restart the backend after edits.
The policy is validated on application creation. Missing/invalid policies stop
startup rather than silently allowing cancellation. No credentials belong in it.

Default: cancel within **24 hours of purchase**, inclusive at the boundary, while
the order is pending, confirmed, or processing. `orders.created_at` is the purchase
timestamp; SQLite timestamps without offsets are interpreted as UTC. Missing,
invalid, or future purchase timestamps require manual review and return 409.
The order must contain items, every shipment must still be pending with no shipping
or delivery timestamp, and return records must be rejected/cancelled or absent.
Orders without shipments can qualify. Shipped/delivered orders cannot be enabled
through the policy schema. This is a provisional business policy, not a carrier rule.

The request checks the customer/order association and evaluates current database
state under the same immediate transaction as the status change. Successful
cancellation changes order status to `cancelled` and updates `updated_at`, preserving
items and shipment history. Repeated cancellation returns the existing cancelled
order without another update. Policy denials return 409; missing records return
404. The operation does not contact a carrier or process a payment refund; those
integrations and payment/product-specific restrictions require additional data.

Example: `POST /customers/1/orders/1/cancel` with no request body. The delivered
demo order is deliberately ineligible. Cancellation tests create isolated eligible
orders and verify persistence, retries, time boundaries, policy changes, shipping
and return conflicts, customer scoping, and rejected requests leaving data intact.

## Gemini agent

Uses the official `google-genai` SDK and actual Gemini function calling, with
automatic SDK dispatch disabled. A bounded single-agent loop handles model/tool
routing and preserves full provider content, call IDs and thought signatures.
LangGraph and multiple agents are unnecessary for this workflow: chat requests
are independent, and approvals survive restarts in SQLite. Chat history is not
persisted; include needed context in each message. No RAG is needed for SQL lookups.

Configure these **process environment variables** using your normal secret manager
or local shell; `.env` is never automatically read:

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Google API credential, never printed |
| `APP_GEMINI_MODEL` | Model ID; default `gemini-3.8-flash` |
| `APP_AGENT_MAX_STEPS` | Model-call limit, default 6, maximum 12 |

This is deliberately a local assessment workflow without bearer authentication.
The customer ID is sent by the local workspace and is used to scope customer and
agent operations. Do not expose this mode publicly.

### Chat and approval

- `POST /agent/chat`, body:
  `{"request_id":"d06557f4-62ac-4e40-8853-24c171c47a10","customer_id":1,"message":"Check order 1 status"}`.
- Read tools: `get_customer`, `list_orders`, `get_order`, `get_shipping`.
- Write proposals: `update_address`, `request_return`, `cancel_order`. They create
  a durable pending action and return its exact typed arguments for user review;
  the model cannot approve actions or supply customer identity.
- `POST /agent/actions/{action_id}/confirm`, body:
  `{"customer_id":1,"approve":true}` (or false to reject). The human reviews the proposed action
  before calling this separate endpoint. Business rules are rechecked at execution.
- Confirmation returns a typed tool result; check `status`, not HTTP 200 alone,
  for a recorded business denial. Missing actions return 404; an executing/uncertain
  action returns 409. Repeated completed confirmations return the stored result.

Schema version 2 adds `agent_actions`: customer FK, action ID, request ID,
argument fingerprint, tool/arguments, state, result, creation timestamp. Version 1
data is preserved. Requests with the same request ID and exact write arguments
reuse one action. A new request ID represents a new user intent, not a retry.
Confirmation claims an action durably before dispatch. Concurrent confirmations
cannot dispatch it twice. A process crash around execution leaves an uncertain
`executing` action for manual reconciliation; it is never automatically replayed.
No exactly-once guarantee across crash boundaries is claimed. Direct legacy REST
return requests do not receive this agent confirmation idempotency behavior.

Tool inputs and outputs are Pydantic-validated. Tool names are allowlisted; no
arbitrary SQL/code, network, credential, or approval tools are exposed. Prompt
instructions treat user/database content as untrusted. Deterministic service rules
remain authoritative; model-generated language is not proof of an executed action.
Authoritative results are in `tools`/confirmation responses. Relevant customer and
order information is sent to Google when a user requests those details.

Each provider call has a 15-second timeout and at most two attempts, with retries
only for transient transport failures, 429 and selected 5xx responses. SDK retries
and automatic tool execution are disabled. The default upper bound is 12 provider
attempts per chat (6 steps x 2), not an unbounded agent loop. Unknown/malformed tools,
invalid structured results, blocked/empty responses and exhausted budgets produce
safe errors. Writes are never retried through the model loop.

Structured logs allow only event name, request/action ID, step, tool name and status.
Prompts, credentials, addresses, customer records and provider exception text are
not logged. SQLite stores proposal arguments/results for approvals; keep the data
directory private and out of version control. No refunds or carrier calls occur.

### Verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m pip check
# Explicit live Google request, only when permitted and a process key is configured:
.\.venv\Scripts\python.exe -m backend.app.ai.live_check
```

The live smoke test uses only a temporary synthetic database. It verifies a real
Gemini `get_order` call and validated final response, printing no model/customer
content or credential values. It skips when the process key is absent. Running
it with a key may consume API quota or incur provider charges.

Mocked tests verify tool routing/signature preservation, authorization, cross-customer
denials, approval/rejection, database effects, duplicate/concurrent confirmation,
policy rechecking, migration, invalid tools, loop bounds, retries and safe logs.
These tests do not establish live model availability or natural-language accuracy.

## React frontend

The `frontend` directory contains React + Vite + Tailwind CSS. One responsive
workspace shows real customer/order data, shipping, return history, address and
cancellation forms, and Gemini chat with explicit AI-action approval controls.
Forms show pending states, validate input and display backend policy denials.
No sample UI responses or AI answers are hardcoded.

From the workspace root, start FastAPI in one PowerShell terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In a second terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
# Production build:
npm.cmd run build
```

Open http://127.0.0.1:5173/. Demo customer 1 loads by default. Connection controls
allow a different customer ID. Never paste a Gemini or Grok provider key into the
frontend. Provider credentials belong only to the backend process environment.

The default public frontend setting is `VITE_API_BASE_URL=/api`. Vite proxies
`/api` to FastAPI at `http://127.0.0.1:8000`. For another backend, set
`DEV_API_PROXY_TARGET` for the Vite development server, or set
`VITE_API_BASE_URL` to the full backend URL. Only public connection URLs belong in
frontend environment configuration. The example is in `frontend/.env.example`;
no existing `.env` was read or replaced. Restart Vite after changing configuration.

Production hosting needs an `/api` reverse proxy or a full API URL set at build
time, and the frontend origin in `APP_CORS_ORIGINS`. Backend CORS permits configured
origins and the Content-Type header; it is not authentication.
No hosting or cloud resources were created.

AI chat requires only the backend's Gemini credential.
Missing configuration is displayed as a normal error. Grok is not integrated.
AI proposals show exact arguments and require separate approve/reject actions;
direct order forms show a review dialog before submitting a write.

UI verification used synthetic DEMO-1001: submitted a one-item return, observed
its requested status after reloading from the API, and verified the stored SQLite
records. Cancelling the delivered order was rejected and displayed in the dialog.
Missing agent configuration also displayed correctly. Backend tests run separately
with temporary databases; the frontend build verifies bundling rather than UI behavior.
