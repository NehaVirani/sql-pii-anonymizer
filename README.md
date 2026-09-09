# SQL PII Anonymizer

A command-line program that takes a SQL export containing real personal
information and produces a new SQL file where every name, address, email
address, and phone number has been replaced with a realistic, consistent,
one-way synthetic value — while leaving the rest of the SQL (schema,
non-sensitive columns, formatting, comments) untouched.

```
python3 sql_anonymizer.py samples/original.sql samples/anonymized.sql --stats
```

## 1. Research: which technique actually fits this problem?

Before writing any code, it's worth being precise about the vocabulary,
because these terms get used loosely and they imply very different
guarantees:

| Technique | What it does | Reversible? | Realistic? | Consistent? |
|---|---|---|---|---|
| **Data masking** | Obscures part of a value in place, e.g. `john.smith@gmail.com` → `j***@g****.com`, or `612-555-1234` → `XXX-XXX-1234` | No | No — output doesn't look like a real value | Depends on implementation |
| **Hashing** | Deterministic one-way digest, e.g. `SHA256("John Smith")` → `a94a8fe5...` | No | No — output is not a name at all | Yes, trivially (same input → same hash) |
| **Tokenization** | Replaces a value with an opaque token that maps back to the original via a securely stored lookup vault | Yes, by design (that's the point of tokenization — a system like payment processing needs to get the real value back) | No — tokens aren't realistic data | Yes |
| **Pseudonymization** | Replaces identifying values with substitute values ("pseudonyms"), *optionally* keeping a mapping so it can be reversed by whoever holds the mapping | Optional | Can be, if the pseudonyms are realistic | Yes, if the same mapping is reused |
| **Synthetic data generation** | Generates entirely fabricated data that follows the statistical/structural shape of real data, with no required link back to any specific real record | No (by construction, if no mapping is kept) | Yes — that's the whole point | Yes, if generation is seeded/cached consistently |
| **Anonymization** (the general term, GDPR/NIST sense) | Any transformation, of any of the above kinds, that is irreversible and removes the ability to re-identify a person | No | Depends on method chosen | Depends on method chosen |

Reading the assignment's requirements against this table settles the design
choice:

* **"Realistic synthetic data"** rules out masking (`XXXX`) and hashing
  (`a94a8fe5...`) outright — neither produces a value that *looks like* a
  name, address, email, or phone number.
* **"One-way … you do not need to support converting it back … not required
  to generate a mapping file"** rules out tokenization, which exists
  specifically to be reversible via a vault, and rules out keeping a
  persistent reversible pseudonym table.
* **"The same value should always map to the same replacement, including
  across tables"** is a consistency requirement that hashing would satisfy
  but pure random synthetic generation, run naively, would not.

So the approach implemented here is: **synthetic data generation
(via the Python [`Faker`](https://faker.readthedocs.io/) library),
combined with pseudonymization's core mechanic of a stable, in-memory
value → replacement mapping, but with no mapping file ever written to
disk and no way to recover the original from the output.** This is best
described as *consistent, one-way pseudonymization using synthetic
replacement values* — it borrows pseudonymization's "same input, same
output" property without inheriting its "reversible by design" property.

A secondary technique from the hashing family is used, but only as an
implementation detail, not as the anonymization itself: each original
value is hashed (SHA-256) to derive a **deterministic seed** for Faker's
random generator. This is *not* the anonymization step — the hash is never
shown or stored as the output — it only makes generation reproducible
(the same input file anonymized twice produces byte-identical output),
which made development and testing much easier and is a nice property for
a grader re-running the program. It does **not** make the mapping
reversible: knowing the seed used to generate "Sandra Phillips" doesn't
help you recover "John Smith" — SHA-256 is a one-way function, and Faker's
name tables aren't invertible either.

## 2. Design

### 2.1 Identifying which values need to be anonymized

The program never inspects data values to decide if something "looks like"
a name or address — real names and addresses are far too irregular for
that to be reliable, and it would be easy to both miss real PII and
"anonymize" things that aren't PII. Instead, it works the way a human
reviewer would: **it classifies columns by name**, using the SQL schema
itself.

1. Every `CREATE TABLE` statement is parsed to record each table's column
   names, in order.
2. Every `INSERT` statement is parsed to find the target table, the values
   being inserted, and (if present) an explicit column list.
3. Each column name is classified (`anonymizer/schema.py`,
   `classify_column()`) into one of: `name`, `first_name`, `last_name`,
   `email`, `phone`, `address` (a single composite column holding a full
   address), or the split forms `street` / `city` / `state` / `zip`. This
   is keyword-based (e.g. any column containing `email` → email category),
   with a small exclusion list so that columns like `product_name`,
   `company_name`, or `username` are **not** treated as a person's name.
4. If an `INSERT` doesn't repeat the column list, the column order from the
   matching `CREATE TABLE` is used instead. If neither is available (no
   column list *and* no `CREATE TABLE` seen yet for that table), the
   statement is left untouched and a warning is printed — the program
   never guesses at column meaning from position alone.

Only columns that are both (a) classified as one of the four target
categories and (b) an actual **string literal** value are ever replaced.
Numeric IDs, foreign keys, dates, prices, and free-text notes are never
touched, regardless of what they contain.

### 2.2 Generating realistic synthetic values

[`Faker`](https://pypi.org/project/Faker/) (`en_US` locale) generates the
replacement values, because it produces syntactically and statistically
realistic names, street addresses, cities, and so on — exactly what
"realistic synthetic data" calls for — without needing to hand-roll name
lists or address templates.

* **Names** → `Faker.first_name()` + `Faker.last_name()`.
* **Addresses** → if a column holds a full `"Street, City, ST ZIP"` string,
  the replacement is generated in that same shape using
  `Faker.street_address()`, `Faker.city()`, `Faker.state_abbr()`, and
  `Faker.zipcode()`. If instead a table splits address parts into separate
  `street` / `city` / `state` / `zip` columns, each is generated and cached
  independently, consistent per original value.
* **Emails** → rather than an independent random email, an email is built
  from the *synthetic* name for that same row (`first.last@example.com`),
  so a record's name and email stay believably related to each other, the
  same way the assignment's own example does
  (`John Smith` → `Michael Anderson` and
  `john.smith@gmail.com` → `michael.anderson@example.com`). The domain is
  always `example.com` — the domain IANA/RFC 2606 reserves specifically for
  documentation and testing — rather than a real provider like `gmail.com`,
  so the tool can never accidentally generate an email address that
  happens to belong to a real person. If a row has an email but no
  associated name column, a standalone synthetic name is generated just to
  build the local part.
* **Phone numbers** → rather than a fully independent number, the original
  number's *punctuation pattern* is detected (`612-555-1234`,
  `(512) 555-9832`, `206.555.7743`, plain digits, etc.) and new random
  digits are substituted into the same positions, so the output keeps the
  original's format. The first digit is kept in the 2–9 range so area
  codes stay superficially plausible.

### 2.3 Maintaining consistency (within *and* across tables)

A single `ConsistentAnonymizer` object (`anonymizer/generator.py`) is
created once per run and threaded through the entire file. It holds one
dictionary per category (names, emails, phones, addresses, …), keyed by
the *normalized original value* (trimmed, whitespace-collapsed,
lower-cased). The very first time a given original value is encountered,
a synthetic replacement is generated and cached; every later occurrence of
that exact original value — whether it's the 2nd row of the same table or
a completely different table processed later in the file — looks up the
cache and reuses the same synthetic value instead of generating a new one.

Because the whole file is parsed as one pass with one shared mapping
object (rather than, say, processing each table or each statement in
isolation), this consistency automatically extends across tables: if
`'John Smith'` shows up in `customers`, `orders`, `contacts`, and
`shipping`, all four occurrences resolve to the same cached name the
moment the value repeats.

As a bonus (not required by the assignment, but low-cost and useful for
testing/grading), consistency also holds **across separate runs** of the
program on the same input: each value's synthetic replacement is derived
from a SHA-256 hash of that value as a deterministic Faker seed, so
re-running `sql_anonymizer.py` on the same file twice produces
byte-identical output, without ever persisting a mapping file to disk.

### 2.4 Should names and emails be related?

Yes — see §2.2. When a row contains both a name-like column and an
email-like column, the synthetic email's local part is derived from the
synthetic name generated for that same row, so the two stay recognizably
linked (as in the assignment's own worked example), rather than looking
like two unrelated pieces of synthetic data glued together.

### 2.5 Handling apostrophes and other special characters

Values are never manipulated as raw text with string replace/regex
substitution on the whole file. Instead:

1. The file is scanned character-by-character
   (`anonymizer/sqltext.py`) to find the exact start/end position of each
   literal, correctly tracking single-quoted strings (including the SQL
   `''` escaped-quote convention and backslash escapes), double-quoted
   identifiers, backtick identifiers, line (`--`) and block (`/* */`)
   comments, and nested parentheses — so a comma or quote inside a string
   value (`'Robert O''Brien'`, `'doesn''t answer calls'`) is never
   mistaken for a value/column separator.
2. Each literal is decoded from SQL-string form to a plain Python string
   before being handed to the generator.
3. The synthetic replacement string is *re-encoded* back into a
   correctly-escaped SQL string literal (doubling any `'` characters)
   before being spliced back into the file.
4. Only the exact character span of the original literal is replaced —
   everything else in the file (whitespace, line breaks, comments, column
   order, unrelated values) is copied through byte-for-byte.

This also means a synthetic name that happens to contain an apostrophe
(Faker's `en_US` last-name list includes names like `O'Keefe`) is escaped
correctly and never produces broken SQL — covered explicitly by
`test_apostrophe_in_generated_name_is_escaped_safely` in the test suite.

### 2.6 MySQL-specific handling

This assignment specifies the input is a MySQL export, so the scanner and
statement parser are written to tolerate real `mysqldump` output, not just
generic textbook SQL:

* Backtick-quoted identifiers (`` `customers` ``, `` `customer_id` ``) are
  parsed the same as unquoted or double-quoted ones.
* Column definitions like `` `customer_id` int(11) NOT NULL AUTO_INCREMENT ``
  and a trailing `` `PRIMARY KEY` (...)` `` clause inside `CREATE TABLE` are
  parsed correctly (the nested `(11)` doesn't confuse the top-level comma
  split, and `PRIMARY KEY`/`FOREIGN KEY`/`CONSTRAINT`/etc. entries are
  recognized as non-column table-level clauses and skipped).
* Trailing `ENGINE=InnoDB ... DEFAULT CHARSET=utf8mb4;` after a `CREATE
  TABLE`'s closing paren is left completely untouched.
* `#` single-line comments (MySQL-specific, in addition to standard `--`
  and `/* */`) are recognized everywhere a comment can appear.
* Versioned executable comments (`` /*!40000 ALTER TABLE ... */; ``),
  `LOCK TABLES` / `UNLOCK TABLES`, and similar mysqldump boilerplate
  statements are simply left byte-for-byte untouched, since they're not
  `CREATE TABLE`/`INSERT` statements the anonymizer needs to act on.
* `INSERT IGNORE INTO ...` is recognized in addition to plain `INSERT
  INTO ...`.
* A trailing `ON DUPLICATE KEY UPDATE col = VALUES(col), ...` upsert clause
  is detected and excluded from the row-tuple scan, so its
  `VALUES(col)` column references are never mistaken for an extra data
  row.

`tests/test_anonymizer.py::test_realistic_mysqldump_style_file` exercises
all of the above together in one statement sequence.

### 2.7 Ensuring the generated SQL stays valid

Because replacement is done by splicing corrected, re-escaped literals
into the *original* text at the exact offsets of the values being
replaced — rather than reconstructing statements from scratch — the
output is guaranteed to have the same statement structure, the same
number of values per row, and the same overall formatting as the input.
`tests/test_anonymizer.py::test_sql_structure_preserved_and_loads_in_sqlite`
goes further and actually loads both `samples/original.sql` and
`samples/anonymized.sql` into an in-memory SQLite database and confirms
every table has the same row count in both — i.e. the anonymized file is
not just superficially SQL-shaped, it actually executes.

### 2.8 Why this approach, overall

* **Faker** is the standard, well-maintained library for exactly this kind
  of realistic fake-data generation in Python, with broad locale support,
  which is why it was chosen over hand-written name/address lists.
* A **hand-written character-level scanner**, rather than a full third-party
  SQL-grammar parser, was chosen for locating statements/values because
  production SQL dumps come from many engines with subtly different
  dialects, and a full grammar parser for "any SQL" is a much larger
  undertaking than this assignment calls for. The scanner only needs to
  answer two narrow questions reliably — "where does this statement end?"
  and "where exactly is this literal value?" — which a quote/paren/comment
  aware character scan answers correctly for the wide range of
  `CREATE TABLE` / `INSERT` statements the assignment describes, while
  guaranteeing every other byte of the file is preserved exactly.
* **Column-name-based classification**, rather than value-based pattern
  detection (e.g. "does this string look like an email"), was chosen
  because it's what the schema itself tells you the data *means*, is far
  more reliable than heuristically sniffing values, and mirrors how a real
  PII-discovery tool or a human data steward would first triage a
  database.

## 3. Installation

Requires Python 3.9+.

```bash
pip install -r requirements.txt
```

This installs:

* **[Faker](https://pypi.org/project/Faker/)** — synthetic name / address /
  locale-aware data generation.
* **[pytest](https://pypi.org/project/pytest/)** — for running the test
  suite (not required just to run the anonymizer itself).

No SQL-parsing library is used; `anonymizer/sqltext.py` is a small,
dependency-free scanner written for this project (see §2.7 for why).

## 4. Usage

```bash
python3 sql_anonymizer.py <input.sql> <output.sql> [--stats]
```

* `input.sql` — the original SQL export (expected input: standard
  `CREATE TABLE` / `INSERT INTO ... VALUES (...), (...), ...;` statements,
  as produced by common `mysqldump`/`pg_dump`/manual-export style tools).
* `output.sql` — where the anonymized SQL is written (generated output: a
  full copy of the input file with only the identified name / address /
  email / phone literals replaced).
* `--stats` — optional; prints a summary of which tables/columns were
  anonymized and how many values were replaced.

Example:

```bash
python3 sql_anonymizer.py samples/original.sql samples/anonymized.sql --stats
```

## 5. Project layout

```
sql-anonymizer/
├── sql_anonymizer.py        # CLI entry point
├── anonymizer/
│   ├── sqltext.py           # quote/paren/comment-aware SQL text scanner
│   ├── schema.py            # CREATE TABLE / INSERT parsing + column classification
│   ├── generator.py         # Faker-based, consistent synthetic value generation
│   └── engine.py            # ties parsing + generation together, applies edits
├── samples/
│   ├── original.sql         # sample input (4 related tables, repeated PII)
│   └── anonymized.sql       # output of running the program on original.sql
├── tests/
│   └── test_anonymizer.py   # pytest suite (see §6)
├── testing_evidence.txt     # captured output of a full test + validation run
├── requirements.txt
└── README.md
```

## 6. Testing

Run the suite with:

```bash
pytest -q
```

`tests/test_anonymizer.py` (15 tests, all passing — see `testing_evidence.txt`
for a captured run) verifies every requirement called out in the
assignment:

* Names, addresses, emails, and phone numbers are each changed from their
  original values.
* **No original PII string survives anywhere in the output** (checked
  against every name, address, email, and phone number in the sample
  file).
* **Repeated values are anonymized consistently**: the same original name
  always yields the same synthetic name, both within one run
  (`'Jane Doe'` inserted twice → identical synthetic name both times) and
  deterministically across separate runs of the program.
* **Consistency holds across tables**: `'John Smith'`'s name and address
  appear 6 and 3 times respectively across `customers` / `orders` /
  `contacts` / `shipping` in the sample file, and the test confirms the
  *same* synthetic name/address appears exactly that many times in the
  output.
* Synthetic values have reasonable formats: emails match a standard email
  regex and use the `example.com` domain; phone numbers preserve the
  original's dash/parenthesis/dot punctuation pattern; addresses come out
  in `"Street, City, ST ZIP"` shape.
* The generated SQL is still valid: it's loaded into an in-memory SQLite
  database and shown to produce identical row counts, per table, to the
  original.
* Non-sensitive values (`customer_id`, `product_name`, `order_total`,
  dates, free-text `notes`, `NULL`) are left byte-for-byte unmodified.
* An original value containing an escaped apostrophe (`Robert O''Brien`)
  is anonymized correctly, and a synthetic replacement that itself
  contains an apostrophe is re-escaped correctly, without producing broken
  SQL.
* Non-person `_name` columns (`product_name`) are correctly *not*
  anonymized, demonstrating the classifier isn't just matching on the
  literal substring "name".
* A realistic `mysqldump`-style snippet (backtick identifiers,
  `AUTO_INCREMENT`/`ENGINE=` clauses, `#` comments, `LOCK TABLES`,
  versioned `/*!...*/` comments, `INSERT IGNORE INTO`, and a trailing
  `ON DUPLICATE KEY UPDATE` clause) is anonymized correctly, with all of
  that MySQL-specific structure preserved untouched (see §2.6).

## 7. Known limitations

* **Column-name-based classification** means a column with an unusual,
  non-descriptive name (e.g. `col5` holding an address) will not be
  detected — the tool trusts the schema's naming, not the data itself.
  This is a deliberate tradeoff (see §2.7); a production tool might add an
  optional secondary pass that also pattern-matches *values* (e.g. an
  `xxx@xxx.xxx` shape, or a `\d{3}-\d{3}-\d{4}` shape) as a safety net for
  oddly-named columns, but that risks false positives on legitimate
  non-PII data and was judged out of scope here.
* **`INSERT` statements with neither an explicit column list nor a
  preceding `CREATE TABLE` for that table** cannot be classified and are
  left unmodified, with a warning printed to stdout. In practice, database
  dumps always define a table before inserting into it, so this only
  matters for hand-written test snippets that skip the `CREATE TABLE`.
* **Addresses are not geographically anchored to the original.** A
  Minneapolis, MN address might become a Boston, MA address. This is
  intentional: keeping the original state/city while only changing the
  street could still narrow down a real individual when combined with
  other fields, so full geographic replacement was chosen to maximize
  privacy over geographic realism.
* **No cross-value identity resolution beyond exact string match.**
  `'John Smith'` and `'John  Smith'` (extra space) or `'J. Smith'` are
  treated as different original values (after trimming/case-folding, but
  not fuzzy-matched), and so would map to different synthetic names. Real
  dumps are typically consistent about a given person's stored name
  string, so this wasn't a problem in testing, but it's a real limitation
  for messier data.
* **US-only formats.** Faker is configured for the `en_US` locale, so
  addresses, area-code-shaped phone numbers, etc. are US-style. Faker
  supports other locales; swapping `Faker("en_US")` in
  `anonymizer/generator.py` for another locale code would adapt the output
  format for a different country's data.
* **Multi-row `INSERT ... VALUES (...), (...), ...;` and multi-statement
  files are supported**, but exotic SQL (stored procedures, `INSERT ...
  SELECT`, computed expressions inside a `VALUES` tuple, dialect-specific
  syntax like PostgreSQL dollar-quoted strings) is out of scope — such
  statements are simply left untouched since they don't match the
  `INSERT INTO table [...] VALUES (...)` pattern the parser looks for.

## 8. GitHub repository

This project is published at:
https://github.com/NehaVirani/sql-pii-anonymizer
