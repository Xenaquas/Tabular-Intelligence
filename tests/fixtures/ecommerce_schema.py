"""Disposable 2nd Multi-Table Relational Schema Fixture for Schema-Agnosticism Verification.

Includes:
- Multiple relational tables (CUSTOMERS, PRODUCTS, ORDERS, ORDER_ITEMS)
- Composite primary keys (ORDER_ITEMS: order_id, product_id)
- Nullable foreign keys (ORDERS.customer_id can be NULL for guest checkout)
- Relational Views (V_ORDER_SUMMARY)
- Various datatypes (INTEGER, VARCHAR, DECIMAL, TIMESTAMP, BOOLEAN)
"""

import duckdb
import pandas as pd
import numpy as np


def create_ecommerce_fixture(db_conn: duckdb.DuckDBPyConnection):
    """Initializes and seeds a complete multi-table e-commerce relational schema in DuckDB."""

    # 1. CUSTOMERS
    db_conn.execute("""
    CREATE TABLE customers (
        customer_id INTEGER PRIMARY KEY,
        customer_name VARCHAR(100) NOT NULL,
        email VARCHAR(150) UNIQUE,
        loyalty_tier VARCHAR(20) DEFAULT 'BRONZE',
        country VARCHAR(50) NOT NULL
    );
    """)

    db_conn.execute("""
    INSERT INTO customers VALUES
        (101, 'Alice Walker', 'alice@corp.test', 'PLATINUM', 'USA'),
        (102, 'Bob Chen', 'bob@corp.test', 'GOLD', 'Canada'),
        (103, 'Carlos Santana', 'carlos@corp.test', 'SILVER', 'Mexico'),
        (104, 'Deepa Patel', 'deepa@corp.test', 'BRONZE', 'India'),
        (105, 'Elena Rostova', 'elena@corp.test', 'GOLD', 'Germany');
    """)

    # 2. PRODUCTS
    db_conn.execute("""
    CREATE TABLE products (
        product_id INTEGER PRIMARY KEY,
        sku VARCHAR(30) UNIQUE NOT NULL,
        product_title VARCHAR(120) NOT NULL,
        unit_price DECIMAL(10,2) NOT NULL,
        category VARCHAR(50) NOT NULL
    );
    """)

    db_conn.execute("""
    INSERT INTO products VALUES
        (201, 'SKU-LAPTOP-X1', 'ThinkStation Ultra Laptop', 1299.99, 'ELECTRONICS'),
        (202, 'SKU-MONITOR-4K', 'Curved 32-inch 4K Monitor', 449.50, 'ELECTRONICS'),
        (203, 'SKU-CHAIR-ERGO', 'Ergonomic Mesh Chair', 299.00, 'FURNITURE'),
        (204, 'SKU-KEYBD-MECH', 'Mechanical RGB Keyboard', 89.99, 'ACCESSORIES'),
        (205, 'SKU-DESK-STAND', 'Motorized Standing Desk', 599.00, 'FURNITURE');
    """)

    # 3. ORDERS (with nullable customer_id for guest checkout)
    db_conn.execute("""
    CREATE TABLE orders (
        order_id INTEGER PRIMARY KEY,
        customer_id INTEGER,
        order_date TIMESTAMP NOT NULL,
        order_status VARCHAR(20) NOT NULL,
        total_amount DECIMAL(12,2) NOT NULL
    );
    """)

    db_conn.execute("""
    INSERT INTO orders VALUES
        (1001, 101, '2026-03-01 10:15:00', 'COMPLETED', 1749.49),
        (1002, 102, '2026-03-02 14:30:00', 'COMPLETED', 299.00),
        (1003, 101, '2026-03-05 09:00:00', 'PROCESSING', 89.99),
        (1004, 104, '2026-03-08 16:45:00', 'COMPLETED', 1048.50),
        (1005, NULL, '2026-03-10 11:20:00', 'COMPLETED', 449.50); -- Guest checkout
    """)

    # 4. ORDER_ITEMS (Composite Primary Key: order_id + product_id)
    db_conn.execute("""
    CREATE TABLE order_items (
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price DECIMAL(10,2) NOT NULL,
        PRIMARY KEY (order_id, product_id)
    );
    """)

    db_conn.execute("""
    INSERT INTO order_items VALUES
        (1001, 201, 1, 1299.99),
        (1001, 202, 1, 449.50),
        (1002, 203, 1, 299.00),
        (1003, 204, 1, 89.99),
        (1004, 202, 1, 449.50),
        (1004, 205, 1, 599.00),
        (1005, 202, 1, 449.50);
    """)

    # 5. VIEW (V_ORDER_SUMMARY)
    db_conn.execute("""
    CREATE VIEW v_order_summary AS
    SELECT 
        o.order_id,
        COALESCE(c.customer_name, 'GUEST') AS customer_name,
        o.order_date,
        o.order_status,
        COUNT(oi.product_id) AS total_items,
        o.total_amount
    FROM orders o
    LEFT JOIN customers c ON o.customer_id = c.customer_id
    JOIN order_items oi ON o.order_id = oi.order_id
    GROUP BY o.order_id, c.customer_name, o.order_date, o.order_status, o.total_amount;
    """)
