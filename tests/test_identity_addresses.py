"""The identity representation: addresses derived from names, and reversible.

Two properties carry the whole design. The rule must be **total** over the
committed name vocabulary, so every person who can exist has an address; and it
must be **single-valued in reverse**, so an address names exactly one person.
Initials would satisfy the first and fail the second — `Budi` and `Bambang`
both reduce to `b.santoso` — and a collision there would silently merge two
people in every downstream aggregate.
"""

from __future__ import annotations

import re

from scripts.generate_sdlc_tickets import (
    FIRST_NAMES,
    HERO,
    HERO_ADDRESS,
    LAST_NAMES,
    MAIL_DOMAIN,
    address_for,
)

# The shape `langchain`'s built-in email detector matches. The addresses have to
# satisfy it, or the redaction net silently covers nothing.
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

ALL_NAMES = [f"{first} {last}" for first in FIRST_NAMES for last in LAST_NAMES]


def test_rule_is_total_over_the_name_vocabulary():
    assert len(ALL_NAMES) == len(FIRST_NAMES) * len(LAST_NAMES)
    for name in ALL_NAMES:
        assert EMAIL.fullmatch(address_for(name)), name


def test_rule_is_single_valued_in_reverse():
    """No two people share an address — the property initials would break."""
    addresses = [address_for(name) for name in ALL_NAMES]
    assert len(set(addresses)) == len(ALL_NAMES)


def test_local_part_reverses_to_exactly_one_identity():
    for name in ALL_NAMES:
        local, _, domain = address_for(name).partition("@")
        assert domain == MAIL_DOMAIN
        # Exactly one dot, so the split is unambiguous.
        assert local.count(".") == 1
        first, last = local.split(".")
        assert f"{first} {last}" == name.lower()


def test_addresses_are_lower_cased():
    for name in ALL_NAMES:
        assert address_for(name) == address_for(name).lower()


def test_hero_address_derives_from_the_hero_name():
    assert HERO_ADDRESS == address_for(HERO) == "budi.santoso@pertamina.com"


def test_no_address_is_a_bare_person_name():
    """The dataset must hold no identity in the form a person would write it."""
    bare = re.compile(r"^[A-Z][a-z]+ [A-Z][a-z]+$")
    for name in ALL_NAMES:
        assert not bare.match(address_for(name))


# ── the reload path ──────────────────────────────────────────────────────────


def test_create_table_sql_defaults_to_non_destructive():
    from scripts.generate_sdlc_tickets import create_table_sql

    ddl = create_table_sql("cat.sch.tbl")
    assert ddl.startswith("CREATE TABLE cat.sch.tbl")
    assert "OR REPLACE" not in ddl


def test_create_table_sql_can_replace_in_place():
    """One atomic statement, not a drop followed by a create."""
    from scripts.generate_sdlc_tickets import create_table_sql

    ddl = create_table_sql("cat.sch.tbl", replace=True)
    assert ddl.startswith("CREATE OR REPLACE TABLE cat.sch.tbl")
    assert "DROP" not in ddl


def test_both_ddl_forms_keep_column_mapping_and_all_columns():
    from scripts.generate_sdlc_tickets import COLUMNS, create_table_sql

    for ddl in (create_table_sql("t"), create_table_sql("t", replace=True)):
        assert "'delta.columnMapping.mode' = 'name'" in ddl
        for column, _ in COLUMNS:
            assert f"`{column}`" in ddl
