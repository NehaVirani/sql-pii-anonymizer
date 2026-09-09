-- ===================================================================
-- Sample production-style export used to test the SQL anonymizer.
-- Contains fictional but realistic-looking personal information,
-- spread across four related tables on purpose: each of the five
-- customer records below appears again in orders, contacts, and
-- shipping, to exercise cross-table consistency of anonymization.
-- ===================================================================

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name VARCHAR(100),
    address VARCHAR(200),
    email VARCHAR(100),
    phone VARCHAR(30),
    signup_date DATE
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    customer_name VARCHAR(100),
    product_name VARCHAR(100),
    order_total DECIMAL(10,2),
    order_date DATE
);

CREATE TABLE contacts (
    contact_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    contact_name VARCHAR(100),
    contact_email VARCHAR(100),
    contact_phone VARCHAR(30),
    notes VARCHAR(255)
);

CREATE TABLE shipping (
    shipping_id INTEGER PRIMARY KEY,
    order_id INTEGER,
    recipient_name VARCHAR(100),
    shipping_address VARCHAR(200),
    shipping_phone VARCHAR(30)
);

INSERT INTO customers
VALUES
(101, 'John Smith', '123 Main Street, Minneapolis, MN 55401',
 'john.smith@gmail.com', '612-555-1234', '2021-03-14'),
(102, 'Maria Garcia-Lopez', '48 Elm Court, Austin, TX 73301',
 'maria.garcia@yahoo.com', '(512) 555-9832', '2022-07-01'),
(103, 'Robert O''Brien', '900 Birchwood Ln, Seattle, WA 98101',
 'robert.obrien@outlook.com', '206.555.7743', '2020-11-22'),
(104, 'Aisha Khan', '77 Sunset Blvd, Denver, CO 80202',
 'aisha.khan@company.com', '303-555-4410', '2023-01-09'),
(105, 'Wei Chen', '15 River Road, Boston, MA 02110',
 'wei.chen@example.net', '617-555-6620', '2019-05-30');

INSERT INTO orders (order_id, customer_id, customer_name, product_name, order_total, order_date)
VALUES
(9001, 101, 'John Smith', 'Wireless Mouse', 24.99, '2023-06-01'),
(9002, 101, 'John Smith', 'Mechanical Keyboard', 89.50, '2023-06-01'),
(9003, 102, 'Maria Garcia-Lopez', 'USB-C Hub', 39.99, '2023-06-03'),
(9004, 103, 'Robert O''Brien', 'Laptop Stand', 45.00, '2023-06-05'),
(9005, 104, 'Aisha Khan', '27" Monitor', 219.99, '2023-06-07'),
(9006, 105, 'Wei Chen', 'Noise-Cancelling Headphones', 149.00, '2023-06-10');

INSERT INTO contacts
VALUES
(501, 101, 'John Smith', 'john.smith@gmail.com', '612-555-1234', 'Prefers email contact, doesn''t answer calls after 5pm.'),
(502, 102, 'Maria Garcia-Lopez', 'maria.garcia@yahoo.com', '(512) 555-9832', 'VIP customer since 2022.'),
(503, 103, 'Robert O''Brien', 'robert.obrien@outlook.com', '206.555.7743', 'Requested callback on weekends.'),
(504, 104, 'Aisha Khan', 'aisha.khan@company.com', '303-555-4410', NULL),
(505, 105, 'Wei Chen', 'wei.chen@example.net', '617-555-6620', 'Corporate account, invoice quarterly.');

INSERT INTO shipping
VALUES
(7001, 9001, 'John Smith', '123 Main Street, Minneapolis, MN 55401', '612-555-1234'),
(7002, 9002, 'John Smith', '123 Main Street, Minneapolis, MN 55401', '612-555-1234'),
(7003, 9003, 'Maria Garcia-Lopez', '48 Elm Court, Austin, TX 73301', '(512) 555-9832'),
(7004, 9004, 'Robert O''Brien', '900 Birchwood Ln, Seattle, WA 98101', '206.555.7743'),
(7005, 9005, 'Aisha Khan', '77 Sunset Blvd, Denver, CO 80202', '303-555-4410'),
(7006, 9006, 'Wei Chen', '15 River Road, Boston, MA 02110', '617-555-6620');
