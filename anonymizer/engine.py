"""
engine.py

Ties the pieces together: walks a SQL file statement-by-statement, tracks
table schemas seen so far, finds every PII literal inside INSERT statements,
generates consistent synthetic replacements, and splices them back into the
*original* text (touching nothing else -- whitespace, comments, non-PII
values, formatting are all preserved byte-for-byte outside the replaced
spans).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .generator import ConsistentAnonymizer
from .schema import classify_column, extract_create_table, extract_insert
from .sqltext import (
    encode_sql_string,
    iter_top_level_tuples,
    parse_literal,
    scan_top_level_spans,
    split_statements,
)

_NAME_LIKE = {"name", "first_name", "last_name"}
_ADDRESS_LIKE = {"address", "street", "city", "state", "zip"}


@dataclass
class AnonymizationStats:
    tables_seen: List[str] = field(default_factory=list)
    columns_anonymized: Dict[str, List[str]] = field(default_factory=dict)
    values_replaced: int = 0
    rows_processed: int = 0
    statements_skipped_no_schema: List[str] = field(default_factory=list)


def _apply_category(anonymizer: ConsistentAnonymizer, category: str, original: str,
                     row_name_hint: Tuple[Optional[str], Optional[str]]) -> str:
    if category == "name":
        return anonymizer.anonymize_name(original)
    if category == "first_name":
        return anonymizer.anonymize_first_name(original)
    if category == "last_name":
        return anonymizer.anonymize_last_name(original)
    if category == "email":
        first, last = row_name_hint
        return anonymizer.anonymize_email(original, linked_first=first, linked_last=last)
    if category == "phone":
        return anonymizer.anonymize_phone(original)
    if category == "address":
        return anonymizer.anonymize_full_address(original)
    if category == "street":
        return anonymizer.anonymize_street(original)
    if category == "city":
        return anonymizer.anonymize_city(original)
    if category == "state":
        return anonymizer.anonymize_state(original)
    if category == "zip":
        return anonymizer.anonymize_zip(original)
    raise ValueError(f"Unknown category {category!r}")


def anonymize_sql(text: str, anonymizer: Optional[ConsistentAnonymizer] = None
                   ) -> Tuple[str, AnonymizationStats]:
    if anonymizer is None:
        anonymizer = ConsistentAnonymizer()
    stats = AnonymizationStats()

    schemas: Dict[str, List[str]] = {}  # table_name.lower() -> column names in order
    edits: List[Tuple[int, int, str]] = []  # (global_start, global_end, replacement_text)

    for s, e in split_statements(text):
        stmt = text[s:e]

        created = extract_create_table(stmt)
        if created is not None:
            table, columns = created
            schemas[table.lower()] = columns
            stats.tables_seen.append(table)
            continue

        inserted = extract_insert(stmt)
        if inserted is None:
            continue

        table_key = inserted.table.lower()
        if inserted.explicit_columns is not None:
            columns = inserted.explicit_columns
        else:
            columns = schemas.get(table_key)
            if columns is None:
                stats.statements_skipped_no_schema.append(inserted.table)
                continue

        categories = [classify_column(c) for c in columns]
        if not any(categories):
            continue  # nothing PII-looking in this table; leave rows untouched

        anonymized_cols = stats.columns_anonymized.setdefault(inserted.table, [])
        for col, cat in zip(columns, categories):
            if cat and col not in anonymized_cols:
                anonymized_cols.append(col)

        for open_idx, close_idx in iter_top_level_tuples(
            stmt, inserted.values_start, inserted.values_end
        ):
            value_spans = scan_top_level_spans(stmt, open_idx + 1, close_idx, ",")
            stats.rows_processed += 1

            row_first: Optional[str] = None
            row_last: Optional[str] = None

            # Pass 1: names first, so email generation can borrow the
            # synthetic first/last name for this row.
            literals = []
            for idx, (vs, ve) in enumerate(value_spans):
                if idx >= len(categories):
                    break
                cat = categories[idx]
                lit = parse_literal(stmt, vs, ve)
                literals.append((cat, lit))
                if cat in _NAME_LIKE and lit.is_string and lit.decoded:
                    if cat == "name":
                        synth = anonymizer.anonymize_name(lit.decoded)
                        rec = anonymizer.get_name_components(lit.decoded)
                        if rec:
                            row_first, row_last = rec.first, rec.last
                    elif cat == "first_name":
                        row_first = anonymizer.anonymize_first_name(lit.decoded)
                    elif cat == "last_name":
                        row_last = anonymizer.anonymize_last_name(lit.decoded)

            # Pass 2: everything else (address parts, phone, email).
            for cat, lit in literals:
                if cat is None or not lit.is_string or lit.decoded is None:
                    continue
                if cat in _NAME_LIKE:
                    # Already handled above; just recompute the same cached
                    # value so it lands in the edit list.
                    if cat == "name":
                        new_value = anonymizer.anonymize_name(lit.decoded)
                    elif cat == "first_name":
                        new_value = anonymizer.anonymize_first_name(lit.decoded)
                    else:
                        new_value = anonymizer.anonymize_last_name(lit.decoded)
                else:
                    new_value = _apply_category(
                        anonymizer, cat, lit.decoded, (row_first, row_last)
                    )
                if new_value == lit.decoded:
                    continue
                replacement = encode_sql_string(new_value)
                edits.append((s + lit.start, s + lit.end, replacement))
                stats.values_replaced += 1

    edits.sort(key=lambda t: t[0])
    out = []
    cursor = 0
    for start, end, replacement in edits:
        if start < cursor:
            continue  # overlapping edit safety guard; skip rather than corrupt output
        out.append(text[cursor:start])
        out.append(replacement)
        cursor = end
    out.append(text[cursor:])
    return "".join(out), stats
