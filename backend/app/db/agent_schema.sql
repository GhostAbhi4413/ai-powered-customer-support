CREATE TABLE agent_actions (
 id TEXT PRIMARY KEY,
 customer_id INTEGER NOT NULL REFERENCES customers(id),
 request_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL,
 tool TEXT NOT NULL,
 arguments TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','executing','completed','failed','rejected')),
 result TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(customer_id, request_id, fingerprint)
);
CREATE INDEX idx_agent_actions_customer ON agent_actions(customer_id);
