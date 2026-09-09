"""
schema.py

Heuristics for (a) extracting column lists from CREATE TABLE statements and
table/column info from INSERT statements, and (b) classifying which columns
hold one of the four PII categories this assignment targets: names,
addresses (composite or split into street/city/state/zip), emails, and
phone numbers.

Column *names*, not column *values*, drive classification -- this mirrors
how a human reviewer (or a real data-catalog/PII-scanning tool) would first
triage a schema before looking at any rows. It is intentionally simple and
declarative so it's easy to extend with more keywords if a real-world dump
uses different naming conventions.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .sqltext import find_first_unquoted, find_matching_paren, scan_top_level_spans

# Column-name substrings that should NOT be treated as a person's name even
# though they end in "name" (e.g. "product_name", "company_name").
_NON_PERSON_NAME_HINTS = (
    "company",
    "product",
    "category",
    "table",
    "item",
    "brand",
    "file",
    "event",
    "department",
    "username",
    "user_name",
    "login_name",
    "column_name",
    "field_name",
    "database_name",
    "school",
    "class_name",
    "domain_name",
    "host_name",
    "server_name",
)


def classify_column(col_name: str) -> Optional[str]:
    """
    Return one of: "email", "phone", "name", "first_name", "last_name",
    "street", "city", "state", "zip", "address" (a composite single-column
    address), or None if the column does not look like PII in one of the
    four target categories.
    """
    c = col_name.strip().strip("`\"[]").lower()

    if "email" in c:
        return "email"

    if any(k in c for k in ("phone", "mobile", "fax", "cell", "telephone")):
        return "phone"

    if "zip" in c or "postal" in c:
        return "zip"

    if ("state" in c or "province" in c) and "statement" not in c:
        return "state"

    if "city" in c or "town" in c:
        return "city"

    if "street" in c and "address" not in c:
        return "street"

    if "address" in c:
        return "address"

    if "first" in c and "name" in c:
        return "first_name"
    if ("last" in c or "sur" in c or "family" in c) and "name" in c:
        return "last_name"

    if c == "name" or c.endswith("_name") or c.endswith("name"):
        if any(hint in c for hint in _NON_PERSON_NAME_HINTS):
            return None
        return "name"

    return None


# Leading whitespace and/or SQL comments (-- line, /* block */) that may
# precede a statement's keyword -- e.g. a comment block documenting the
# table right above "CREATE TABLE ...". Statements are split on top-level
# ';' (see sqltext.split_statements), so a comment with no semicolon of its
# own ends up prepended to the following statement's text.
_LEADING = r"(?:\s+|--[^\n]*(?:\n|$)|/\*.*?\*/)*"


def extract_create_table(stmt: str) -> Optional[Tuple[str, List[str]]]:
    """Parse a CREATE TABLE statement's table name and column names (in
    declared order). Returns None if this isn't a CREATE TABLE statement."""
    m = re.match(
        _LEADING + r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\"\[]?)([A-Za-z0-9_.]+)\1",
        stmt,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    table = m.group(2).split(".")[-1].strip("`\"[]")

    paren_open = stmt.find("(", m.end())
    if paren_open == -1:
        return table, []
    paren_close = find_matching_paren(stmt, paren_open)

    columns: List[str] = []
    for s, e in scan_top_level_spans(stmt, paren_open + 1, paren_close, ","):
        chunk = stmt[s:e].strip()
        if not chunk:
            continue
        word_match = re.match(r"[`\"\[]?([A-Za-z0-9_]+)", chunk)
        if not word_match:
            continue
        first_word = word_match.group(1)
        if first_word.upper() in (
            "PRIMARY",
            "FOREIGN",
            "CONSTRAINT",
            "UNIQUE",
            "CHECK",
            "KEY",
            "INDEX",
        ):
            continue
        columns.append(first_word)
    return table, columns


class InsertInfo:
    def __init__(
        self,
        table: str,
        explicit_columns: Optional[List[str]],
        values_start: int,
        values_end: int,
    ):
        self.table = table
        self.explicit_columns = explicit_columns
        self.values_start = values_start
        self.values_end = values_end


def extract_insert(stmt: str) -> Optional[InsertInfo]:
    """Parse an INSERT statement's table name, optional explicit column
    list, and the character span in which the VALUES tuples live. Returns
    None if this isn't an INSERT statement."""
    m = re.match(
        # MySQL allows "INSERT IGNORE INTO ..." in addition to plain
        # "INSERT INTO ...".
        _LEADING + r"INSERT\s+(?:IGNORE\s+)?INTO\s+([`\"\[]?)([A-Za-z0-9_.]+)\1",
        stmt,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    table = m.group(2).split(".")[-1].strip("`\"[]")

    pos = m.end()
    while pos < len(stmt) and stmt[pos].isspace():
        pos += 1

    explicit_columns: Optional[List[str]] = None
    if pos < len(stmt) and stmt[pos] == "(":
        close = find_matching_paren(stmt, pos)
        explicit_columns = []
        for s, e in scan_top_level_spans(stmt, pos + 1, close, ","):
            chunk = stmt[s:e].strip().strip("`\"[]")
            explicit_columns.append(chunk)
        pos = close + 1

    values_idx = find_first_unquoted(stmt, "VALUES", pos, len(stmt))
    if values_idx == -1:
        return None
    values_start = values_idx + len("VALUES")

    # MySQL upsert dumps sometimes append "ON DUPLICATE KEY UPDATE col =
    # VALUES(col), ..." after the row tuples. That trailing clause is not
    # part of the row data (it's column references, not literals), so stop
    # scanning for row tuples there rather than mistaking "VALUES(col)" for
    # another data row.
    values_end = len(stmt)
    odku_idx = find_first_unquoted(
        stmt, "ON", values_start, len(stmt)
    )
    while odku_idx != -1:
        # Confirm this "ON" starts "ON DUPLICATE KEY UPDATE" and not some
        # unrelated identifier; if not, keep looking further along.
        tail = stmt[odku_idx : odku_idx + 40]
        if re.match(r"ON\s+DUPLICATE\s+KEY\s+UPDATE", tail, re.IGNORECASE):
            values_end = odku_idx
            break
        odku_idx = find_first_unquoted(stmt, "ON", odku_idx + 2, len(stmt))

    return InsertInfo(table, explicit_columns, values_start, values_end)
