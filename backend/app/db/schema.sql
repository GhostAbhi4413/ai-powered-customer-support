CREATE TABLE customers (
 id INTEGER PRIMARY KEY,
 name TEXT NOT NULL CHECK(length(trim(name)) > 0),
 email TEXT NOT NULL COLLATE NOCASE UNIQUE,
 phone TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE orders (
 id INTEGER PRIMARY KEY,
 order_number TEXT NOT NULL UNIQUE,
 customer_id INTEGER NOT NULL REFERENCES customers(id),
 status TEXT NOT NULL CHECK(status IN ('pending','confirmed','processing','shipped','delivered','cancelled')),
 currency TEXT NOT NULL CHECK(length(currency) = 3),
 delivery_address TEXT NOT NULL CHECK(length(trim(delivery_address)) > 0),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE TABLE order_items (
 id INTEGER PRIMARY KEY,
 order_id INTEGER NOT NULL REFERENCES orders(id),
 sku TEXT NOT NULL,
 product_name TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity > 0),
 unit_price_minor INTEGER NOT NULL CHECK(typeof(unit_price_minor)='integer' AND unit_price_minor >= 0),
 UNIQUE(order_id, sku),
 UNIQUE(id, order_id)
);
CREATE TABLE shipments (
 id INTEGER PRIMARY KEY,
 order_id INTEGER NOT NULL REFERENCES orders(id),
 carrier TEXT NOT NULL,
 tracking_reference TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','dispatched','in_transit','delivered','exception','returned')),
 shipped_at TEXT,
 estimated_delivery_at TEXT,
 delivered_at TEXT,
 UNIQUE(carrier, tracking_reference)
);
CREATE INDEX idx_shipments_order ON shipments(order_id);
CREATE TABLE returns (
 id INTEGER PRIMARY KEY,
 order_id INTEGER NOT NULL REFERENCES orders(id),
 status TEXT NOT NULL CHECK(status IN ('requested','approved','rejected','received','refunded','cancelled')),
 reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(id, order_id)
);
CREATE INDEX idx_returns_order ON returns(order_id);
CREATE TABLE return_items (
 return_id INTEGER NOT NULL,
 order_id INTEGER NOT NULL,
 order_item_id INTEGER NOT NULL,
 quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity > 0),
 PRIMARY KEY(return_id, order_item_id),
 FOREIGN KEY(return_id, order_id) REFERENCES returns(id, order_id),
 FOREIGN KEY(order_item_id, order_id) REFERENCES order_items(id, order_id)
);
CREATE INDEX idx_return_items_order_item ON return_items(order_item_id);
