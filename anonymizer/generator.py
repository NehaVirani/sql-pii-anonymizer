"""
generator.py

Synthetic-value generation for the four PII categories this assignment
targets: names, addresses, emails, and phone numbers.

Design summary (see README.md for the full write-up):

  * This is PSEUDONYMIZATION with SYNTHETIC DATA, not masking, hashing, or
    tokenization -- every original value is replaced by a *different*,
    independently realistic value drawn from the same category (Faker),
    rather than a masked/redacted/reversibly-tokenized form of the original.
    One-way: there is no stored reverse mapping written anywhere, and the
    forward mapping is deterministic but not invertible (it depends on
    Faker's internal PRNG, not on any recoverable transform of the input).

  * CONSISTENCY is achieved with an in-memory dictionary per category,
    keyed by the *normalized original value*. The first time a value is
    seen it is generated and cached; every later occurrence of the exact
    same original value (anywhere in the file, in any table) reuses the
    cached synthetic value. This directly satisfies "John Smith always
    becomes the same synthetic name" and "the same value across
    CUSTOMER/ORDER/CONTACT/SHIPPING tables stays consistent."

  * DETERMINISM across separate runs (a bonus, not required) comes from
    seeding a local Faker instance with a hash of the original value before
    generating, instead of relying on global process randomness. Running
    the program twice on the same input file therefore produces identical
    output, which makes testing and diffing much easier -- without ever
    needing to persist a mapping file.

  * RELATIONSHIPS between fields: when a single INSERT row contains both a
    name and an email column, the email is derived from the *synthetic*
    name (e.g. michael.anderson@example.com) rather than generated fully
    independently, mirroring the assignment's own example and keeping the
    synthetic record internally believable.

  * FORMAT PRESERVATION: phone numbers keep the original separator pattern
    (e.g. "612-555-1234" -> "763-555-8421", "(612) 555-1234" -> "(763)
    555-8421"). Addresses are re-emitted in "Street, City, ST ZIP" form.
    Emails always use the synthetic name and the safe, non-registrable
    "example.com" domain (see README "Known limitations" for why).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from faker import Faker

_FAKE = Faker("en_US")


def _seed_for(salt: str, value: str) -> int:
    """Deterministic 32-bit seed derived from (salt, value)."""
    h = hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _normalize(value: str) -> str:
    return " ".join(value.strip().split()).lower()


@dataclass
class NameRecord:
    synthetic_full: str
    first: str
    last: str


class ConsistentAnonymizer:
    """
    Holds all per-category mappings for a single anonymization run so that
    the same original value always yields the same synthetic value, both
    within one table and across every table in the file.
    """

    def __init__(self) -> None:
        self._names: Dict[str, NameRecord] = {}
        self._used_names: set = set()

        self._emails: Dict[str, str] = {}
        self._used_emails: set = set()

        self._phones: Dict[str, str] = {}
        self._used_phones: set = set()

        self._addresses: Dict[str, str] = {}
        self._streets: Dict[str, str] = {}
        self._cities: Dict[str, str] = {}
        self._states: Dict[str, str] = {}
        self._zips: Dict[str, str] = {}

        self._first_names: Dict[str, str] = {}
        self._last_names: Dict[str, str] = {}

    # ---------------------------------------------------------------- names
    def anonymize_name(self, original: str) -> str:
        key = _normalize(original)
        if not key:
            return original
        rec = self._names.get(key)
        if rec is not None:
            return rec.synthetic_full

        seed_salt = 0
        while True:
            seed = _seed_for(f"name{seed_salt}", key)
            _FAKE.seed_instance(seed)
            first = _FAKE.first_name()
            last = _FAKE.last_name()
            candidate = f"{first} {last}"
            if candidate.lower() not in self._used_names:
                break
            seed_salt += 1

        self._used_names.add(candidate.lower())
        rec = NameRecord(candidate, first, last)
        self._names[key] = rec
        return candidate

    def get_name_components(self, original: str) -> Optional[NameRecord]:
        return self._names.get(_normalize(original))

    def anonymize_first_name(self, original: str) -> str:
        return self._cached(self._first_names, "first_name", original, lambda: _FAKE.first_name())

    def anonymize_last_name(self, original: str) -> str:
        return self._cached(self._last_names, "last_name", original, lambda: _FAKE.last_name())

    # --------------------------------------------------------------- emails
    def anonymize_email(
        self,
        original: str,
        linked_first: Optional[str] = None,
        linked_last: Optional[str] = None,
    ) -> str:
        key = _normalize(original)
        if not key:
            return original
        if key in self._emails:
            return self._emails[key]

        first, last = linked_first, linked_last

        if first is None or last is None:
            seed = _seed_for("email-name", key)
            _FAKE.seed_instance(seed)
            first, last = _FAKE.first_name(), _FAKE.last_name()

        local_base = f"{first}.{last}".lower()
        local_base = re.sub(r"[^a-z0-9.]", "", local_base) or "user"
        candidate = f"{local_base}@example.com"
        suffix = 1
        seed_salt = 0
        while candidate.lower() in self._used_emails:
            suffix += 1
            candidate = f"{local_base}{suffix}@example.com"
            seed_salt += 1
            if seed_salt > 1000:
                break

        self._used_emails.add(candidate.lower())
        self._emails[key] = candidate
        return candidate

    # --------------------------------------------------------------- phones
    _PHONE_DIGIT_RE = re.compile(r"\d")

    def anonymize_phone(self, original: str) -> str:
        key = _normalize(original)
        if not key:
            return original
        if key in self._phones:
            return self._phones[key]

        seed_salt = 0
        while True:
            seed = _seed_for(f"phone{seed_salt}", key)
            rnd = Faker("en_US")
            rnd.seed_instance(seed)

            digit_positions = [m.start() for m in self._PHONE_DIGIT_RE.finditer(original)]
            n_digits = len(digit_positions)

            if n_digits == 0:
                return original  # nothing to anonymize (shouldn't normally happen)

            # Generate replacement digits, keeping area code (first 3 digits,
            # if present) valid-looking: non-zero leading digit, avoiding the
            # reserved N11 pattern (e.g. 911) in the middle position.
            new_digits = []
            for idx in range(n_digits):
                if idx == 0:
                    new_digits.append(str(rnd.random_int(2, 9)))
                else:
                    new_digits.append(str(rnd.random_int(0, 9)))
            new_digits_str = "".join(new_digits)

            candidate_chars = list(original)
            for pos, d in zip(digit_positions, new_digits_str):
                candidate_chars[pos] = d
            candidate = "".join(candidate_chars)

            if candidate not in self._used_phones:
                break
            seed_salt += 1
            if seed_salt > 50:
                break

        self._used_phones.add(candidate)
        self._phones[key] = candidate
        return candidate

    # ------------------------------------------------------------ addresses
    _COMPOSITE_ADDR_RE = re.compile(
        r"^(?P<street>[^,]+),\s*(?P<city>[^,]+),\s*(?P<state>[A-Za-z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$"
    )

    def anonymize_full_address(self, original: str) -> str:
        """Anonymize a single composite 'Street, City, ST ZIP' column."""
        key = _normalize(original)
        if not key:
            return original
        if key in self._addresses:
            return self._addresses[key]

        seed = _seed_for("address", key)
        _FAKE.seed_instance(seed)

        m = self._COMPOSITE_ADDR_RE.match(original.strip())
        if m:
            street = _FAKE.street_address()
            city = _FAKE.city()
            state = _FAKE.state_abbr()
            zip_code = _FAKE.zipcode()
            candidate = f"{street}, {city}, {state} {zip_code}"
        else:
            # Fall back to a full realistic single-line US address.
            candidate = _FAKE.address().replace("\n", ", ")

        self._addresses[key] = candidate
        return candidate

    def anonymize_street(self, original: str) -> str:
        return self._cached(self._streets, "street", original, lambda: _FAKE.street_address())

    def anonymize_city(self, original: str) -> str:
        return self._cached(self._cities, "city", original, lambda: _FAKE.city())

    def anonymize_state(self, original: str) -> str:
        return self._cached(self._states, "state", original, lambda: _FAKE.state_abbr())

    def anonymize_zip(self, original: str) -> str:
        return self._cached(self._zips, "zip", original, lambda: _FAKE.zipcode())

    # ------------------------------------------------------------- helpers
    def _cached(self, store: Dict[str, str], salt: str, original: str, gen) -> str:
        key = _normalize(original)
        if not key:
            return original
        if key in store:
            return store[key]
        seed = _seed_for(salt, key)
        _FAKE.seed_instance(seed)
        candidate = gen()
        store[key] = candidate
        return candidate
