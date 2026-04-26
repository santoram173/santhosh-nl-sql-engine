-- ─────────────────────────────────────────────────────────────────────────────
-- Santhosh NL→SQL Engine — Sample Database Schema + Seed Data
-- ─────────────────────────────────────────────────────────────────────────────

-- Create read-only role (recommended for production)
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'santhosh_readonly') THEN
    CREATE ROLE santhosh_readonly WITH LOGIN PASSWORD 'readonly_password';
  END IF;
END
$$;

-- ── Tables ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS customers (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(150) UNIQUE NOT NULL,
    country     VARCHAR(60),
    segment     VARCHAR(50) DEFAULT 'standard',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(80),
    price       NUMERIC(10, 2) NOT NULL,
    stock       INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    status      VARCHAR(30) DEFAULT 'pending',
    amount      NUMERIC(12, 2),
    currency    VARCHAR(3) DEFAULT 'USD',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS order_items (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER REFERENCES orders(id),
    product_id  INTEGER REFERENCES products(id),
    quantity    INTEGER NOT NULL,
    unit_price  NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    event_type  VARCHAR(80) NOT NULL,
    properties  JSONB DEFAULT '{}',
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_orders_customer    ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_created_at  ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_status      ON orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order  ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_events_customer    ON events(customer_id);
CREATE INDEX IF NOT EXISTS idx_events_occurred    ON events(occurred_at);

-- ── Seed Data ─────────────────────────────────────────────────────────────────

INSERT INTO customers (name, email, country, segment) VALUES
  ('Alice Chen',       'alice@example.com',    'US',  'premium'),
  ('Bob Müller',       'bob@example.de',       'DE',  'standard'),
  ('Priya Nair',       'priya@example.in',     'IN',  'premium'),
  ('James Wu',         'james@example.hk',     'HK',  'standard'),
  ('Sofia Rossi',      'sofia@example.it',     'IT',  'premium'),
  ('Carlos Mendez',    'carlos@example.mx',    'MX',  'standard'),
  ('Fatima Al-Said',   'fatima@example.ae',    'AE',  'enterprise'),
  ('Lena Kovač',       'lena@example.hr',      'HR',  'standard'),
  ('Raj Patel',        'raj@example.uk',       'UK',  'premium'),
  ('Emily Zhang',      'emily@example.ca',     'CA',  'standard')
ON CONFLICT DO NOTHING;

INSERT INTO products (title, category, price, stock) VALUES
  ('Pro Analytics Suite',   'Software',    299.00, 999),
  ('Data Connector Pack',   'Software',    149.00, 999),
  ('Enterprise Dashboard',  'Software',    499.00, 999),
  ('API Access Token (yr)', 'Software',     99.00, 999),
  ('Laptop Stand Pro',      'Hardware',     59.99, 124),
  ('USB-C Hub 7-port',      'Hardware',     39.99, 287),
  ('Mechanical Keyboard',   'Hardware',    129.00,  56),
  ('4K Monitor 27"',        'Hardware',    449.00,  23),
  ('Consulting Hour',       'Services',    200.00, 999),
  ('Onboarding Package',    'Services',    799.00, 999)
ON CONFLICT DO NOTHING;

-- Generate realistic orders over the last 90 days
DO $$
DECLARE
  cust_id INTEGER;
  prod_id INTEGER;
  ord_id  INTEGER;
  days_ago INTEGER;
  ord_status VARCHAR;
  statuses VARCHAR[] := ARRAY['completed','completed','completed','pending','refunded'];
BEGIN
  FOR i IN 1..80 LOOP
    cust_id  := (i % 10) + 1;
    days_ago := (RANDOM() * 90)::INTEGER;
    ord_status := statuses[(RANDOM() * 4 + 1)::INTEGER];

    INSERT INTO orders (customer_id, status, amount, created_at, completed_at)
    VALUES (
      cust_id,
      ord_status,
      ROUND((RANDOM() * 900 + 50)::NUMERIC, 2),
      NOW() - (days_ago || ' days')::INTERVAL,
      CASE WHEN ord_status = 'completed'
           THEN NOW() - (days_ago || ' days')::INTERVAL + INTERVAL '2 hours'
           ELSE NULL END
    )
    RETURNING id INTO ord_id;

    -- Add 1-3 order items per order
    FOR j IN 1..(RANDOM() * 2 + 1)::INTEGER LOOP
      prod_id := (RANDOM() * 9 + 1)::INTEGER;
      INSERT INTO order_items (order_id, product_id, quantity, unit_price)
      SELECT ord_id, prod_id, (RANDOM() * 3 + 1)::INTEGER, price
      FROM products WHERE id = prod_id;
    END LOOP;

    -- Add events
    INSERT INTO events (customer_id, event_type, occurred_at)
    VALUES (cust_id, 'page_view', NOW() - (days_ago || ' days')::INTERVAL);

    IF RANDOM() > 0.5 THEN
      INSERT INTO events (customer_id, event_type, occurred_at)
      VALUES (cust_id, 'feature_used', NOW() - (days_ago || ' days')::INTERVAL + INTERVAL '5 minutes');
    END IF;
  END LOOP;
END $$;

-- ── Grant read-only access ────────────────────────────────────────────────────
GRANT CONNECT ON DATABASE santhosh_db TO santhosh_readonly;
GRANT USAGE ON SCHEMA public TO santhosh_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO santhosh_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO santhosh_readonly;
