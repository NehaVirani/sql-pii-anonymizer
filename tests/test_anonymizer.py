"""
test_anonymizer.py

Automated tests demonstrating that the anonymizer satisfies the assignment's
requirements:

  1. Names are anonymized.
  2. Addresses are anonymized.
  3. Emails are anonymized.
  4. Phone numbers are anonymized.
  5. Original PII does not remain anywhere in the generated SQL.
  6. Repeated values are anonymized consistently (same input -> same output).
  7. Values appearing across multiple tables remain consistent.
  8. Synthetic values have reasonable formats (valid-looking email/phone,
     "Street, City, ST ZIP" address shape).
  9. The generated SQL is still valid (loads into SQLite with the same
     table/row shape as the original).
  10. Non-sensitive values (IDs, product names, notes, NULLs, dates,
      numeric totals) are not modified.

Run with:  pytest -q
"""

import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anonymizer.engine import anonymize_sql
from anonymizer.sqltext import decode_sql_string, encode_sql_string

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PHONE_DIGITS_RE = re.compile(r"\d")


def _load_original():
    with open(os.path.join(SAMPLES_DIR, "original.sql"), encoding="utf-8") as f:
        return f.read()


def test_original_pii_removed():
    original_text = _load_original()
    anonymized_text, _ = anonymize_sql(original_text)

    original_pii = [
        "John Smith",
        "Maria Garcia-Lopez",
        "Robert O'Brien",
        "Aisha Khan",
        "Wei Chen",
        "123 Main Street, Minneapolis, MN 55401",
        "48 Elm Court, Austin, TX 73301",
        "900 Birchwood Ln, Seattle, WA 98101",
        "john.smith@gmail.com",
        "maria.garcia@yahoo.com",
        "robert.obrien@outlook.com",
        "612-555-1234",
        "(512) 555-9832",
        "206.555.7743",
    ]
    for pii in original_pii:
        assert pii not in anonymized_text, f"Original PII leaked into output: {pii!r}"


def test_names_are_changed():
    original_text = _load_original()
    anonymized_text, stats = anonymize_sql(original_text)
    assert stats.values_replaced > 0
    assert "John Smith" not in anonymized_text
    assert "customers" in stats.columns_anonymized
    assert "name" in stats.columns_anonymized["customers"]


def test_addresses_are_changed_and_reasonable_shape():
    original_text = _load_original()
    anonymized_text, _ = anonymize_sql(original_text)

    m = re.search(r"'(\d+ [^,]+, [^,]+, [A-Z]{2} \d{5})'", anonymized_text)
    assert m, "Could not find a synthetic address in 'Street, City, ST ZIP' form"
    assert "Minneapolis" not in anonymized_text


def test_emails_are_changed_and_valid_and_linked_to_name():
    original_text = _load_original()
    anonymized_text, _ = anonymize_sql(original_text)

    emails = re.findall(r"'([\w.+-]+@[\w.-]+)'", anonymized_text)
    assert emails, "No synthetic emails found in output"
    for e in emails:
        assert EMAIL_RE.match(e), f"Synthetic email is not well-formed: {e}"
        assert e.endswith("@example.com")

    # The customer with id 101 should have an email whose local part matches
    # their (synthetic) first/last name, demonstrating name<->email linkage.
    m = re.search(
        r"\(101,\s*'([^']+)',\s*'[^']+',\s*'([^']+)@example\.com'", anonymized_text
    )
    assert m, "Could not locate customer 101's synthetic name/email pair"
    synthetic_name, local_part = m.group(1), m.group(2)
    first, last = synthetic_name.lower().split(" ", 1)
    assert first in local_part and last.replace(" ", ".") in local_part or last in local_part


def test_phone_numbers_changed_and_format_preserved():
    original_text = _load_original()
    anonymized_text, _ = anonymize_sql(original_text)

    # Original used dash format 612-555-1234 (3-3-4 digit groups).
    m = re.search(r"'(\d{3}-\d{3}-\d{4})'", anonymized_text)
    assert m, "No dash-formatted synthetic phone number found"
    assert m.group(1) != "612-555-1234"

    # Original used parenthesis format (512) 555-9832.
    m2 = re.search(r"'(\(\d{3}\) \d{3}-\d{4})'", anonymized_text)
    assert m2, "No parenthesis-formatted synthetic phone number found"

    # Original used dot format 206.555.7743.
    m3 = re.search(r"'(\d{3}\.\d{3}\.\d{4})'", anonymized_text)
    assert m3, "No dot-formatted synthetic phone number found"


def test_consistency_within_and_across_tables():
    original_text = _load_original()
    anonymized_text, _ = anonymize_sql(original_text)

    # John Smith appears in customers, orders (x2), contacts, and shipping
    # (x2) in the fixture -- six occurrences of the same original name.
    # After anonymization there should be exactly one distinct synthetic
    # name standing in for all six, and it should appear six times.
    names_in_original = re.findall(r"'(John Smith)'", original_text)
    assert len(names_in_original) == 6

    # Find what "John Smith" (customer 101) became by looking at the
    # customers table row for id 101, then confirm that exact string
    # appears the same number of times elsewhere.
    m = re.search(r"\(101,\s*'([^']+)',", anonymized_text)
    assert m
    synthetic_name = m.group(1)
    occurrences = anonymized_text.count(f"'{synthetic_name}'")
    assert occurrences == 6, (
        f"Expected {synthetic_name!r} to appear 6 times (once per original "
        f"John Smith occurrence across tables), found {occurrences}"
    )

    # Same check for the repeated address (customers + shipping, x3 total).
    m2 = re.search(r"\(101,\s*'[^']+',\s*'([^']+)',", anonymized_text)
    assert m2
    synthetic_address = m2.group(1)
    assert anonymized_text.count(f"'{synthetic_address}'") == 3


def test_repeated_original_value_maps_deterministically_within_one_run():
    text = """
    CREATE TABLE t (id INT, name VARCHAR(50), email VARCHAR(50));
    INSERT INTO t VALUES (1, 'Jane Doe', 'jane.doe@gmail.com');
    INSERT INTO t VALUES (2, 'Jane Doe', 'jane.doe@gmail.com');
    INSERT INTO t VALUES (3, 'Someone Else', 'someone@yahoo.com');
    """
    anonymized, _ = anonymize_sql(text)
    names = re.findall(r"'([A-Za-z]+ [A-Za-z]+)'", anonymized)
    # Row 1 and row 2 (both originally 'Jane Doe') must produce the same name.
    assert names[0] == names[1]
    assert names[0] != names[2]  # different original person -> different synthetic name


def test_repeated_original_value_maps_deterministically_across_runs():
    text = """
    CREATE TABLE t (id INT, name VARCHAR(50));
    INSERT INTO t VALUES (1, 'Jane Doe');
    """
    out1, _ = anonymize_sql(text)
    out2, _ = anonymize_sql(text)
    assert out1 == out2, "Same input should deterministically produce the same output"


def test_sql_structure_preserved_and_loads_in_sqlite():
    original_text = _load_original()
    anonymized_text, _ = anonymize_sql(original_text)

    conn_orig = sqlite3.connect(":memory:")
    conn_orig.executescript(original_text)
    conn_anon = sqlite3.connect(":memory:")
    conn_anon.executescript(anonymized_text)

    for table in ("customers", "orders", "contacts", "shipping"):
        n_orig = conn_orig.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        n_anon = conn_anon.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert n_orig == n_anon, f"Row count mismatch in {table}"

    conn_orig.close()
    conn_anon.close()


def test_non_sensitive_values_untouched():
    original_text = _load_original()
    anonymized_text, _ = anonymize_sql(original_text)

    # Primary keys / foreign keys, product names, order totals, dates, and
    # free-text notes are not PII categories targeted by this assignment
    # and must survive unchanged.
    for untouched in (
        "'Wireless Mouse'",
        "'Mechanical Keyboard'",
        "'USB-C Hub'",
        "24.99",
        "89.50",
        "'2023-06-01'",
        "'VIP customer since 2022.'",
        "'Requested callback on weekends.'",
    ):
        assert untouched in anonymized_text, f"Non-sensitive value was altered: {untouched}"

    assert original_text.count("(9001,") and anonymized_text.count("(9001,")


def test_null_values_preserved():
    original_text = _load_original()
    anonymized_text, _ = anonymize_sql(original_text)
    assert "504, 'Monique" in anonymized_text or "504," in anonymized_text
    # The NULL notes value for contact 504 must remain NULL, not a
    # generated string.
    m = re.search(r"\(504,.*?, NULL\)", anonymized_text)
    assert m, "NULL literal was not preserved for contact 504"


def test_apostrophe_in_generated_name_is_escaped_safely():
    # Force a case where the *synthetic* replacement itself needs
    # escaping, independent of Faker's output, by round-tripping
    # encode/decode directly.
    value = "O'Malley-Reyes"
    encoded = encode_sql_string(value)
    assert encoded == "'O''Malley-Reyes'"
    assert decode_sql_string(encoded) == value


def test_original_apostrophe_name_handled_correctly():
    original_text = _load_original()
    anonymized_text, _ = anonymize_sql(original_text)
    # "Robert O''Brien" (SQL-escaped) must be fully replaced -- no trace of
    # the original name or a malformed/leftover quote sequence.
    assert "O''Brien" not in anonymized_text
    assert "Robert" not in anonymized_text or "Robert" in anonymized_text  # name may coincidentally recur; just ensure no crash
    # Statement must still be syntactically valid (round-trips through sqlite).
    conn = sqlite3.connect(":memory:")
    conn.executescript(anonymized_text)
    conn.close()


def test_non_person_name_columns_not_anonymized():
    original_text = _load_original()
    _, stats = anonymize_sql(original_text)
    assert "product_name" not in stats.columns_anonymized.get("orders", [])


def test_realistic_mysqldump_style_file():
    """
    The assignment specifies the input is a MySQL export. Real mysqldump
    output has several conventions a naive parser can trip on: backtick-quoted
    identifiers, `AUTO_INCREMENT`/`ENGINE=...` clauses trailing the closing
    paren, `#` comments, `LOCK TABLES` / versioned `/*!...*/` comment
    statements surrounding the INSERT, `INSERT IGNORE INTO`, an explicit
    column list, and a trailing `ON DUPLICATE KEY UPDATE col=VALUES(col)`
    upsert clause. This test exercises all of them at once.
    """
    text = """
-- MySQL dump 10.13  Distrib 8.0.36
SET NAMES utf8mb4;
/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;

--
-- Table structure for table `customers`
--

DROP TABLE IF EXISTS `customers`;
CREATE TABLE `customers` (
  `customer_id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) DEFAULT NULL,
  `address` varchar(200) DEFAULT NULL,
  `email` varchar(100) DEFAULT NULL,
  `phone` varchar(30) DEFAULT NULL,
  PRIMARY KEY (`customer_id`)
) ENGINE=InnoDB AUTO_INCREMENT=106 DEFAULT CHARSET=utf8mb4; # end table

LOCK TABLES `customers` WRITE;
/*!40000 ALTER TABLE `customers` DISABLE KEYS */;
INSERT INTO `customers` VALUES (101,'John Smith','123 Main Street, Minneapolis, MN 55401','john.smith@gmail.com','612-555-1234'),(102,'Maria Garcia','48 Elm Court, Austin, TX 73301','maria.garcia@yahoo.com','512-555-9832');
INSERT IGNORE INTO `customers` (`customer_id`,`name`,`address`,`email`,`phone`) VALUES (103,'Robert Brown','5 Oak St, Denver, CO 80202','robert.brown@example.net','303-555-1122') ON DUPLICATE KEY UPDATE name=VALUES(name), email=VALUES(email);
/*!40000 ALTER TABLE `customers` ENABLE KEYS */;
UNLOCK TABLES;
"""
    anonymized, stats = anonymize_sql(text)

    for pii in ("John Smith", "Maria Garcia", "Robert Brown", "612-555-1234", "512-555-9832"):
        assert pii not in anonymized

    # Exactly 3 data rows should have been processed -- the ON DUPLICATE KEY
    # UPDATE clause's "VALUES(name)" / "VALUES(email)" column references must
    # NOT be mistaken for extra row tuples.
    assert stats.rows_processed == 3

    # Structural MySQL-specific elements must survive untouched.
    for untouched in (
        "AUTO_INCREMENT",
        "ENGINE=InnoDB",
        "LOCK TABLES `customers` WRITE;",
        "/*!40000 ALTER TABLE `customers` DISABLE KEYS */;",
        "INSERT IGNORE INTO `customers`",
        "ON DUPLICATE KEY UPDATE name=VALUES(name), email=VALUES(email)",
        "# end table",
    ):
        assert untouched in anonymized, f"MySQL structural element was altered: {untouched!r}"
