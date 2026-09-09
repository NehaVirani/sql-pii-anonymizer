"""
sqltext.py

Small, dependency-free SQL text scanner used to locate statement boundaries,
parenthesis groups, and top-level (comma-separated) items *without* fully
parsing SQL grammar.

Why not a full SQL parser?  Production SQL dumps come from many different
database engines with subtly different dialects (MySQL backtick identifiers,
Postgres dollar-quoting, T-SQL brackets, etc.).  A full grammar-level parser
for "any SQL" is a large undertaking and is overkill for this assignment,
which only needs to reliably answer two questions:

    1. Where does one statement end and the next begin?
    2. Within a statement, where are the individual literal values
       (so we can splice in replacements without disturbing anything else)?

A character-level scanner that understands single-quoted strings, double
quoted identifiers, line/block comments, and parenthesis nesting is enough
to answer both questions correctly for the wide range of CREATE TABLE / INSERT
statements this assignment targets, while leaving every byte of the original
file untouched except the specific spans we intentionally replace.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple


def _is_escaped_quote(text: str, i: int, quote: str) -> bool:
    """Return True if text[i] is a quote char that is doubled (SQL '' escape)."""
    return text[i] == quote and i + 1 < len(text) and text[i + 1] == quote


def scan_top_level_spans(
    text: str, start: int, end: int, separators: str
) -> List[Tuple[int, int]]:
    """
    Scan text[start:end] and split it on any character in `separators` that
    appears at "top level" -- i.e. not inside a quoted string/identifier and
    not inside nested parentheses.

    Returns a list of (span_start, span_end) tuples (whitespace-trimmed)
    covering the whole range, in order.
    """
    spans: List[Tuple[int, int]] = []
    i = start
    seg_start = start
    depth = 0
    in_squote = False
    in_dquote = False
    in_backtick = False
    n = end

    while i < n:
        c = text[i]

        if in_squote:
            if c == "'" and _is_escaped_quote(text, i, "'"):
                i += 2
                continue
            if c == "\\" and i + 1 < n:
                # backslash-escape (MySQL-style); skip escaped char
                i += 2
                continue
            if c == "'":
                in_squote = False
            i += 1
            continue

        if in_dquote:
            if c == '"' and _is_escaped_quote(text, i, '"'):
                i += 2
                continue
            if c == '"':
                in_dquote = False
            i += 1
            continue

        if in_backtick:
            if c == "`":
                in_backtick = False
            i += 1
            continue

        # Not inside any quote here.
        if c == "'":
            in_squote = True
            i += 1
            continue
        if c == '"':
            in_dquote = True
            i += 1
            continue
        if c == "`":
            in_backtick = True
            i += 1
            continue
        if c == "-" and i + 1 < n and text[i + 1] == "-":
            # line comment -- consume to end of line
            j = text.find("\n", i)
            i = n if j == -1 or j >= n else j + 1
            continue
        if c == "#":
            # MySQL '#' line comment -- consume to end of line
            j = text.find("\n", i)
            i = n if j == -1 or j >= n else j + 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c == "(":
            depth += 1
            i += 1
            continue
        if c == ")":
            depth -= 1
            i += 1
            continue

        if depth == 0 and c in separators:
            spans.append((seg_start, i))
            i += 1
            seg_start = i
            continue

        i += 1

    spans.append((seg_start, n))

    # Trim whitespace from each span.
    trimmed: List[Tuple[int, int]] = []
    for s, e in spans:
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        trimmed.append((s, e))
    return trimmed


def split_statements(text: str) -> List[Tuple[int, int]]:
    """
    Split a whole SQL file into top-level statements on ';', respecting
    quotes/comments. Returns (start, end) spans (end exclusive of the
    semicolon), skipping empty/whitespace-only statements.
    """
    spans = scan_top_level_spans(text, 0, len(text), ";")
    return [(s, e) for s, e in spans if text[s:e].strip()]


def find_matching_paren(text: str, open_idx: int) -> int:
    """Given the index of an opening '(', return the index of its matching ')'."""
    assert text[open_idx] == "("
    depth = 0
    i = open_idx
    n = len(text)
    in_squote = False
    in_dquote = False
    in_backtick = False
    while i < n:
        c = text[i]
        if in_squote:
            if c == "'" and _is_escaped_quote(text, i, "'"):
                i += 2
                continue
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == "'":
                in_squote = False
            i += 1
            continue
        if in_dquote:
            if c == '"' and _is_escaped_quote(text, i, '"'):
                i += 2
                continue
            if c == '"':
                in_dquote = False
            i += 1
            continue
        if in_backtick:
            if c == "`":
                in_backtick = False
            i += 1
            continue
        if c == "-" and i + 1 < n and text[i + 1] == "-":
            j = text.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if c == "#":
            j = text.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c == "'":
            in_squote = True
        elif c == '"':
            in_dquote = True
        elif c == "`":
            in_backtick = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("Unbalanced parentheses in SQL text")


def find_first_unquoted(text: str, sub: str, start: int, end: int) -> int:
    """Find the first top-level (unquoted, uncommented) case-insensitive
    occurrence of `sub` as a whole word within text[start:end]. Returns -1
    if not found."""
    i = start
    n = end
    in_squote = False
    in_dquote = False
    in_backtick = False
    sub_lower = sub.lower()
    slen = len(sub)
    while i < n:
        c = text[i]
        if in_squote:
            if c == "'" and _is_escaped_quote(text, i, "'"):
                i += 2
                continue
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == "'":
                in_squote = False
            i += 1
            continue
        if in_dquote:
            if c == '"' and _is_escaped_quote(text, i, '"'):
                i += 2
                continue
            if c == '"':
                in_dquote = False
            i += 1
            continue
        if in_backtick:
            if c == "`":
                in_backtick = False
            i += 1
            continue
        if c == "'":
            in_squote = True
            i += 1
            continue
        if c == '"':
            in_dquote = True
            i += 1
            continue
        if c == "`":
            in_backtick = True
            i += 1
            continue
        if c == "-" and i + 1 < n and text[i + 1] == "-":
            j = text.find("\n", i)
            i = n if j == -1 or j >= n else j + 1
            continue
        if c == "#":
            j = text.find("\n", i)
            i = n if j == -1 or j >= n else j + 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if text[i : i + slen].lower() == sub_lower:
            before_ok = i == start or not (text[i - 1].isalnum() or text[i - 1] == "_")
            after_idx = i + slen
            after_ok = after_idx >= n or not (
                text[after_idx].isalnum() or text[after_idx] == "_"
            )
            if before_ok and after_ok:
                return i
        i += 1
    return -1


@dataclass
class Literal:
    """A single top-level literal value within an INSERT VALUES tuple."""

    start: int
    end: int
    raw: str  # exact original text of the value, including quotes if any
    is_string: bool
    is_null: bool
    decoded: Optional[str]  # for strings: the unescaped Python string value


def decode_sql_string(raw: str) -> str:
    """Decode a single-quoted SQL string literal (including its quotes) into
    its Python string value, un-escaping '' and backslash escapes."""
    assert raw.startswith("'") and raw.endswith("'") and len(raw) >= 2
    inner = raw[1:-1]
    out = []
    i = 0
    n = len(inner)
    while i < n:
        c = inner[i]
        if c == "'" and i + 1 < n and inner[i + 1] == "'":
            out.append("'")
            i += 2
            continue
        if c == "\\" and i + 1 < n:
            nxt = inner[i + 1]
            mapping = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"'}
            out.append(mapping.get(nxt, nxt))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def encode_sql_string(value: str) -> str:
    """Encode a Python string as a single-quoted SQL string literal, escaping
    single quotes by doubling them (the ANSI-SQL-standard, universally-safe
    way, understood by MySQL, Postgres, SQLite, SQL Server, etc.)."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def parse_literal(text: str, start: int, end: int) -> Literal:
    raw = text[start:end]
    stripped = raw.strip()
    if stripped.upper() == "NULL":
        return Literal(start, end, raw, is_string=False, is_null=True, decoded=None)
    if stripped.startswith("'") and stripped.endswith("'") and len(stripped) >= 2:
        return Literal(
            start, end, raw, is_string=True, is_null=False, decoded=decode_sql_string(stripped)
        )
    return Literal(start, end, raw, is_string=False, is_null=False, decoded=None)


def iter_top_level_tuples(text: str, start: int, end: int) -> Iterator[Tuple[int, int]]:
    """Given the span right after VALUES (up to the terminating ';' or end of
    statement), yield (open_paren_idx, close_paren_idx) for each top-level
    '(...)' row tuple, e.g. for  "(1,2),(3,4)"  -> two spans."""
    i = start
    while i < end:
        if text[i] == "(":
            close = find_matching_paren(text, i)
            yield (i, close)
            i = close + 1
        elif text[i].isspace() or text[i] == ",":
            i += 1
        else:
            i += 1
