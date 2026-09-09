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
(101, 'Sandra Phillips', '2271 Allen Fort, West Larrybury, TN 67349',
 'sandra.phillips@example.com', '955-761-6611', '2021-03-14'),
(102, 'Stacey Rivera', '3018 Stevenson Green Apt. 614, Peterview, NV 32539',
 'stacey.rivera@example.com', '(720) 780-4616', '2022-07-01'),
(103, 'Kimberly Howard', '1640 Paul Islands, Barbaraton, MN 60744',
 'kimberly.howard@example.com', '202.289.6291', '2020-11-22'),
(104, 'Monique Strickland', '6215 Miller Pass Apt. 452, Robertshire, DC 99159',
 'monique.strickland@example.com', '929-130-1351', '2023-01-09'),
(105, 'Michael Ortiz', '76172 James Motorway, West Shane, RI 60352',
 'michael.ortiz@example.com', '544-883-0278', '2019-05-30');

INSERT INTO orders (order_id, customer_id, customer_name, product_name, order_total, order_date)
VALUES
(9001, 101, 'Sandra Phillips', 'Wireless Mouse', 24.99, '2023-06-01'),
(9002, 101, 'Sandra Phillips', 'Mechanical Keyboard', 89.50, '2023-06-01'),
(9003, 102, 'Stacey Rivera', 'USB-C Hub', 39.99, '2023-06-03'),
(9004, 103, 'Kimberly Howard', 'Laptop Stand', 45.00, '2023-06-05'),
(9005, 104, 'Monique Strickland', '27" Monitor', 219.99, '2023-06-07'),
(9006, 105, 'Michael Ortiz', 'Noise-Cancelling Headphones', 149.00, '2023-06-10');

INSERT INTO contacts
VALUES
(501, 101, 'Sandra Phillips', 'sandra.phillips@example.com', '955-761-6611', 'Prefers email contact, doesn''t answer calls after 5pm.'),
(502, 102, 'Stacey Rivera', 'stacey.rivera@example.com', '(720) 780-4616', 'VIP customer since 2022.'),
(503, 103, 'Kimberly Howard', 'kimberly.howard@example.com', '202.289.6291', 'Requested callback on weekends.'),
(504, 104, 'Monique Strickland', 'monique.strickland@example.com', '929-130-1351', NULL),
(505, 105, 'Michael Ortiz', 'michael.ortiz@example.com', '544-883-0278', 'Corporate account, invoice quarterly.');

INSERT INTO shipping
VALUES
(7001, 9001, 'Sandra Phillips', '2271 Allen Fort, West Larrybury, TN 67349', '955-761-6611'),
(7002, 9002, 'Sandra Phillips', '2271 Allen Fort, West Larrybury, TN 67349', '955-761-6611'),
(7003, 9003, 'Stacey Rivera', '3018 Stevenson Green Apt. 614, Peterview, NV 32539', '(720) 780-4616'),
(7004, 9004, 'Kimberly Howard', '1640 Paul Islands, Barbaraton, MN 60744', '202.289.6291'),
(7005, 9005, 'Monique Strickland', '6215 Miller Pass Apt. 452, Robertshire, DC 99159', '929-130-1351'),
(7006, 9006, 'Michael Ortiz', '76172 James Motorway, West Shane, RI 60352', '544-883-0278');
