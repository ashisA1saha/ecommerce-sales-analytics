-- =====================================================================
-- SQL optimization demo: indexes + EXPLAIN ANALYZE
-- =====================================================================
-- WHY A SEPARATE SCHEMA?
--   The real project data has only ~40 orders. At that size PostgreSQL
--   correctly chooses a sequential scan whatever indexes exist, so
--   EXPLAIN ANALYZE would show nothing useful. This script builds a
--   scratch copy of the tables in a schema called perf_demo, fills it
--   with synthetic data (200,000 orders, about 600,000 order items) and
--   compares the dashboard's real queries BEFORE and AFTER new indexes.
--   Your real tables in the public schema are never touched.
--
-- HOW TO RUN (pgAdmin Query Tool, connected to ecommerce_analytics):
--   Use ONE Query Tool tab for the whole demo (search_path is per session).
--   Run each numbered section on its own: select the section, press F5.
--   Section 2 contains VACUUM, which cannot run together with other
--   statements, so run those three lines one at a time.
--
-- HOW TO READ EXPLAIN (ANALYZE, BUFFERS):
--   * Node type: Seq Scan (reads the whole table), Bitmap Heap Scan,
--     Index Scan, Index Only Scan (answers from the index alone).
--   * "Execution Time" at the bottom: real runtime in milliseconds.
--   * "Buffers: shared hit/read": 8 kB pages touched (less is better).
--   * "Heap Fetches" on an Index Only Scan: table visits still needed.
--   * "Rows Removed by Filter": rows read and thrown away (wasted work).
--   Run each EXPLAIN twice and read the second run, so the cache is warm
--   and the numbers are comparable.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. SETUP: scratch schema, tables and synthetic data
-- ---------------------------------------------------------------------
DROP SCHEMA IF EXISTS perf_demo CASCADE;
CREATE SCHEMA perf_demo;
SET search_path TO perf_demo;          -- every table below lands in perf_demo
SET max_parallel_workers_per_gather = 0;   -- simpler, easier-to-read plans
SET jit = off;                         -- avoid JIT timing noise on small queries

CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    city          VARCHAR(100)
);

CREATE TABLE categories (
    category_id   SERIAL PRIMARY KEY,
    category_name VARCHAR(100) UNIQUE
);

CREATE TABLE products (
    product_id   SERIAL PRIMARY KEY,
    product_name VARCHAR(150) NOT NULL,
    category_id  INT REFERENCES categories(category_id),
    price        NUMERIC(10,2)
);

CREATE TABLE orders (
    order_id     SERIAL PRIMARY KEY,
    customer_id  INT REFERENCES customers(customer_id),
    order_date   DATE NOT NULL,
    order_status VARCHAR(30) NOT NULL
);

CREATE TABLE order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id      INT REFERENCES orders(order_id),
    product_id    INT REFERENCES products(product_id),
    quantity      INT,
    unit_price    NUMERIC(10,2)
);

SELECT setseed(0.42);                  -- same random data on every run

INSERT INTO categories (category_name) VALUES
    ('Books'), ('Electronics'), ('Fashion'), ('Home and Kitchen'), ('Stationery');

INSERT INTO products (product_name, category_id, price)
SELECT 'Product ' || g, 1 + (g % 5), 100 + g * 10
FROM generate_series(1, 200) AS g;

INSERT INTO customers (customer_name, city)
SELECT 'Customer ' || g,
       (ARRAY['Ahmedabad','Bengaluru','Chennai','Delhi','Hyderabad','Jaipur',
              'Kolkata','Lucknow','Mumbai','Pune','Surat','Nagpur','Indore'])[1 + (g % 13)]
FROM generate_series(1, 5000) AS g;

-- 200,000 orders over two years: about 70% Delivered, 15% Pending, 15% Cancelled
INSERT INTO orders (customer_id, order_date, order_status)
SELECT 1 + floor(r1 * 5000)::int,
       DATE '2024-01-01' + floor(r2 * 730)::int,
       CASE WHEN r3 < 0.70 THEN 'Delivered'
            WHEN r3 < 0.85 THEN 'Pending'
            ELSE 'Cancelled' END
FROM (SELECT random() AS r1, random() AS r2, random() AS r3
      FROM generate_series(1, 200000)) AS s;

-- 1 to 5 items per order (about 600,000 rows); unit_price equals the product price
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
SELECT o.order_id,
       1 + ((o.order_id * k * 31) % 200),
       1 + ((o.order_id + k) % 5),
       100 + (1 + ((o.order_id * k * 31) % 200)) * 10
FROM orders o
CROSS JOIN generate_series(1, 5) AS k
WHERE k <= 1 + (o.order_id % 5);

-- BASELINE INDEXES: exactly the ones database/schema.sql already creates
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_orders_customer   ON orders(customer_id);
CREATE INDEX idx_orders_status     ON orders(order_status);
CREATE INDEX idx_orders_date       ON orders(order_date);
CREATE INDEX idx_items_order       ON order_items(order_id);
CREATE INDEX idx_items_product     ON order_items(product_id);

-- Sanity check: expect customers 5000, orders 200000, order_items about 600000
SELECT 'customers' AS tbl, COUNT(*) FROM customers
UNION ALL SELECT 'orders',      COUNT(*) FROM orders
UNION ALL SELECT 'order_items', COUNT(*) FROM order_items;


-- ---------------------------------------------------------------------
-- 2. REFRESH STATISTICS (run each line on its own)
--    VACUUM also sets the visibility map, which Index Only Scans need.
-- ---------------------------------------------------------------------
VACUUM (ANALYZE) perf_demo.orders;
VACUUM (ANALYZE) perf_demo.order_items;
VACUUM (ANALYZE) perf_demo.customers;


-- ---------------------------------------------------------------------
-- 3. BEFORE: baseline indexes only. Run each query twice, keep the 2nd.
--    The queries are copied from src/analytics.py with literal filters.
-- ---------------------------------------------------------------------

-- Q1: Monthly revenue, Delivered orders, Jan to Mar 2025
EXPLAIN (ANALYZE, BUFFERS)
SELECT DATE_TRUNC('month', o.order_date)::date AS month,
       SUM(oi.quantity * oi.unit_price) AS revenue
FROM orders o
LEFT JOIN customers c    ON o.customer_id = c.customer_id
LEFT JOIN order_items oi ON o.order_id = oi.order_id
LEFT JOIN products p     ON oi.product_id = p.product_id
LEFT JOIN categories cat ON p.category_id = cat.category_id
WHERE oi.order_item_id IS NOT NULL
  AND o.order_date >= DATE '2025-01-01'
  AND o.order_date <= DATE '2025-03-31'
  AND o.order_status IN ('Delivered')
GROUP BY 1
ORDER BY 1;

-- Q2: Top 5 products for customers in one city, Delivered orders in 2025
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.product_name, SUM(oi.quantity) AS total_sold
FROM orders o
LEFT JOIN customers c    ON o.customer_id = c.customer_id
LEFT JOIN order_items oi ON o.order_id = oi.order_id
LEFT JOIN products p     ON oi.product_id = p.product_id
LEFT JOIN categories cat ON p.category_id = cat.category_id
WHERE p.product_id IS NOT NULL
  AND o.order_date >= DATE '2025-01-01'
  AND o.order_date <= DATE '2025-12-31'
  AND o.order_status IN ('Delivered')
  AND c.city IN ('Kolkata')
GROUP BY p.product_name
ORDER BY total_sold DESC
LIMIT 5;

-- Q3: Top 5 customers by spend, Delivered orders in 2025
--     (a heavy aggregate over a large slice: a useful control case)
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_name, SUM(oi.quantity * oi.unit_price) AS total_spent
FROM orders o
LEFT JOIN customers c    ON o.customer_id = c.customer_id
LEFT JOIN order_items oi ON o.order_id = oi.order_id
LEFT JOIN products p     ON oi.product_id = p.product_id
LEFT JOIN categories cat ON p.category_id = cat.category_id
WHERE c.customer_id IS NOT NULL
  AND o.order_date >= DATE '2025-01-01'
  AND o.order_date <= DATE '2025-12-31'
  AND o.order_status IN ('Delivered')
GROUP BY c.customer_id, c.customer_name
ORDER BY total_spent DESC
LIMIT 5;


-- ---------------------------------------------------------------------
-- 4. ADD THE NEW INDEXES
-- ---------------------------------------------------------------------
-- (Statements that change anything are schema-qualified with perf_demo, so
--  they can never touch your real tables even from a different tab.)

-- Composite: the dashboard always filters by status AND a date range, so
-- one index can narrow both at once (equality column first, range second).
CREATE INDEX idx_orders_status_date ON perf_demo.orders (order_status, order_date);

-- Covering: the join from orders to order_items needs order_id to find rows
-- and product_id, quantity and unit_price to compute revenue. INCLUDE stores
-- those columns in the index so PostgreSQL can skip the table entirely.
CREATE INDEX idx_items_order_covering
    ON perf_demo.order_items (order_id) INCLUDE (product_id, quantity, unit_price);

-- City filter: lets the planner find one city's customers without scanning all.
CREATE INDEX idx_customers_city ON perf_demo.customers (city);

-- Compare the cost of each index (extra disk space and slower writes):
SELECT indexrelid::regclass AS index_name,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_index
WHERE indrelid IN ('perf_demo.orders'::regclass,
                   'perf_demo.order_items'::regclass,
                   'perf_demo.customers'::regclass)
ORDER BY pg_relation_size(indexrelid) DESC;


-- ---------------------------------------------------------------------
-- 5. REFRESH STATISTICS AGAIN (these three lines can run together)
-- ---------------------------------------------------------------------
ANALYZE perf_demo.orders;
ANALYZE perf_demo.order_items;
ANALYZE perf_demo.customers;


-- ---------------------------------------------------------------------
-- 6. AFTER: identical queries. Run each twice, keep the 2nd.
--    Compare node types, Execution Time and Buffers with section 3.
-- ---------------------------------------------------------------------

-- Q1 (same as above)
EXPLAIN (ANALYZE, BUFFERS)
SELECT DATE_TRUNC('month', o.order_date)::date AS month,
       SUM(oi.quantity * oi.unit_price) AS revenue
FROM orders o
LEFT JOIN customers c    ON o.customer_id = c.customer_id
LEFT JOIN order_items oi ON o.order_id = oi.order_id
LEFT JOIN products p     ON oi.product_id = p.product_id
LEFT JOIN categories cat ON p.category_id = cat.category_id
WHERE oi.order_item_id IS NOT NULL
  AND o.order_date >= DATE '2025-01-01'
  AND o.order_date <= DATE '2025-03-31'
  AND o.order_status IN ('Delivered')
GROUP BY 1
ORDER BY 1;

-- Q2 (same as above)
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.product_name, SUM(oi.quantity) AS total_sold
FROM orders o
LEFT JOIN customers c    ON o.customer_id = c.customer_id
LEFT JOIN order_items oi ON o.order_id = oi.order_id
LEFT JOIN products p     ON oi.product_id = p.product_id
LEFT JOIN categories cat ON p.category_id = cat.category_id
WHERE p.product_id IS NOT NULL
  AND o.order_date >= DATE '2025-01-01'
  AND o.order_date <= DATE '2025-12-31'
  AND o.order_status IN ('Delivered')
  AND c.city IN ('Kolkata')
GROUP BY p.product_name
ORDER BY total_sold DESC
LIMIT 5;

-- Q3 (same as above)
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_name, SUM(oi.quantity * oi.unit_price) AS total_spent
FROM orders o
LEFT JOIN customers c    ON o.customer_id = c.customer_id
LEFT JOIN order_items oi ON o.order_id = oi.order_id
LEFT JOIN products p     ON oi.product_id = p.product_id
LEFT JOIN categories cat ON p.category_id = cat.category_id
WHERE c.customer_id IS NOT NULL
  AND o.order_date >= DATE '2025-01-01'
  AND o.order_date <= DATE '2025-12-31'
  AND o.order_status IN ('Delivered')
GROUP BY c.customer_id, c.customer_name
ORDER BY total_spent DESC
LIMIT 5;


-- ---------------------------------------------------------------------
-- 7. CLEAN UP when you are done (removes only the perf_demo schema)
-- ---------------------------------------------------------------------
RESET search_path;
DROP SCHEMA perf_demo CASCADE;
