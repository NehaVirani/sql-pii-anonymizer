#!/usr/bin/env python3
"""
sql_anonymizer.py

CLI entry point. Reads a SQL dump, replaces names, addresses, emails, and
phone numbers with consistent, realistic synthetic values, and writes the
result to a new SQL file. See README.md for the full design write-up.

Usage:
    python3 sql_anonymizer.py input.sql output.sql
    python3 sql_anonymizer.py input.sql output.sql --stats
"""

from __future__ import annotations

import argparse
import sys

from anonymizer.engine import anonymize_sql


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Anonymize PII in a SQL dump file.")
    parser.add_argument("input", help="Path to the original SQL file")
    parser.add_argument("output", help="Path to write the anonymized SQL file")
    parser.add_argument(
        "--stats", action="store_true", help="Print a summary of what was anonymized"
    )
    args = parser.parse_args(argv)

    with open(args.input, "r", encoding="utf-8") as f:
        original_text = f.read()

    anonymized_text, stats = anonymize_sql(original_text)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(anonymized_text)

    print(f"Wrote anonymized SQL to {args.output}")

    if args.stats:
        print("\n--- Anonymization summary ---")
        print(f"Tables seen (CREATE TABLE): {', '.join(stats.tables_seen) or '(none)'}")
        print(f"Rows processed (INSERT tuples): {stats.rows_processed}")
        print(f"Values replaced: {stats.values_replaced}")
        print("Columns anonymized per table:")
        for table, cols in stats.columns_anonymized.items():
            print(f"  {table}: {', '.join(cols)}")
        if stats.statements_skipped_no_schema:
            print(
                "WARNING: INSERT statements skipped (no column list and no "
                "matching CREATE TABLE seen yet) for tables: "
                + ", ".join(sorted(set(stats.statements_skipped_no_schema)))
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
