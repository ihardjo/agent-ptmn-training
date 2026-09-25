"""OKF v0.2 conformance, and the tolerance the spec requires of a consumer.

The asymmetry is the whole point of the format and is tested in both
directions: the three hard rules of §11 are enforced, and a document that
violates only soft guidance is *not* rejected.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone

import pytest
import yaml

from agent_server.okf import (
    DEFAULT_NOTE_TYPE,
    conformance_errors,
    ensure_conformant,
    is_reserved,
    parse,
)

SEED = pathlib.Path(__file__).resolve().parent.parent / "wiki_seed" / "notes"
ACTOR = "agent-ptmn-training/test-model"
FIXED = datetime(2026, 9, 18, 7, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def seed_docs() -> dict[str, str]:
    return {p.relative_to(SEED).as_posix(): p.read_text() for p in SEED.rglob("*.md")}


# ── 5.1 the three hard rules ─────────────────────────────────────────────────


def test_the_seed_bundle_is_conformant(seed_docs):
    assert conformance_errors(seed_docs) == []


def test_the_seed_bundle_is_not_trivially_conformant(seed_docs):
    """Guard against the check passing because it found nothing to check."""
    concepts = [p for p in seed_docs if not is_reserved(p)]
    assert len(concepts) >= 4
    assert any(p == "index.md" for p in seed_docs)
    assert any(p == "log.md" for p in seed_docs)


def test_frontmatter_removed_is_caught(seed_docs):
    seed_docs["policies/resolution-targets.md"] = "# Targets\n\n| P2 | 80 |\n"
    errors = conformance_errors(seed_docs)
    assert any("no parseable YAML frontmatter" in e for e in errors)


def test_unparseable_frontmatter_is_caught(seed_docs):
    seed_docs["policies/resolution-targets.md"] = "---\ntype: [unclosed\n---\n\nbody\n"
    assert any("no parseable YAML frontmatter" in e for e in conformance_errors(seed_docs))


@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_type_is_caught(seed_docs, value):
    rendered = "type:\n" if value is None else f'type: "{value}"\n'
    seed_docs["policies/resolution-targets.md"] = f"---\n{rendered}---\n\nbody\n"
    assert any("no non-empty `type`" in e for e in conformance_errors(seed_docs))


def test_a_log_out_of_order_is_caught(seed_docs):
    seed_docs["log.md"] = "# Log\n\n## 2026-01-01\n* **Creation**: a\n\n## 2026-08-11\n* **Update**: b\n"
    assert any("newest first" in e for e in conformance_errors(seed_docs))


def test_a_log_with_frontmatter_is_caught(seed_docs):
    seed_docs["log.md"] = "---\ntype: Log\n---\n\n# Log\n\n## 2026-08-11\n* **Update**: a\n"
    assert any("must not carry frontmatter" in e for e in conformance_errors(seed_docs))


def test_an_index_that_lists_nothing_is_caught(seed_docs):
    seed_docs["policies/index.md"] = "# Policies\n\nSome prose and no entries.\n"
    assert any("must list its contents" in e for e in conformance_errors(seed_docs))


def test_frontmatter_in_a_non_root_index_is_caught(seed_docs):
    seed_docs["policies/index.md"] = "---\nokf_version: \"0.2\"\n---\n\n# P\n\n* [A](/a.md) - a\n"
    assert any("only a bundle-root index.md" in e for e in conformance_errors(seed_docs))


def test_root_index_may_declare_okf_version(seed_docs):
    assert parse(seed_docs["index.md"])[0] == {"okf_version": "0.2"}
    assert conformance_errors(seed_docs) == []


def test_root_index_may_not_declare_anything_else(seed_docs):
    seed_docs["index.md"] = "---\nokf_version: \"0.2\"\ntype: Index\n---\n\n* [A](/a.md) - a\n"
    assert any("only `okf_version`" in e for e in conformance_errors(seed_docs))


# ── 5.2 provenance and trust on the target concepts ──────────────────────────


def test_the_target_concept_records_who_confirmed_it_and_when(seed_docs):
    fm, _ = parse(seed_docs["policies/resolution-targets.md"])
    verified = fm["verified"]
    assert isinstance(verified, list) and verified
    assert any(str(v["by"]).startswith("human:") for v in verified), "no human sign-off"
    assert all(v.get("at") for v in verified)


def test_the_target_concept_records_where_it_came_from(seed_docs):
    fm, _ = parse(seed_docs["policies/resolution-targets.md"])
    assert fm["sources"], "no sources"
    assert all(src.get("resource") for src in fm["sources"]), "§5.1 requires `resource`"
    assert fm["generated"]["by"].startswith("human:")


def test_a_confirmed_target_is_distinguishable_from_an_unconfirmed_one(seed_docs):
    """§5.3 trust tiers: the absence of `verified` has to be readable."""
    confirmed, _ = parse(seed_docs["policies/resolution-targets.md"])
    unconfirmed, _ = parse(seed_docs["policies/breach-counting.md"])
    assert "verified" in confirmed
    assert "verified" not in unconfirmed


def test_a_stale_concept_is_distinguishable_from_a_fresh_one(seed_docs):
    """§5.5 staleness is a plain comparison, so the horizon must be present."""
    stale, _ = parse(seed_docs["policies/escalation-matrix.md"])
    fresh, _ = parse(seed_docs["policies/resolution-targets.md"])
    today = datetime(2026, 9, 18, tzinfo=timezone.utc)
    assert stale["stale_after"].replace(tzinfo=timezone.utc) < today
    assert fresh["stale_after"].replace(tzinfo=timezone.utc) > today


def test_the_p2_bug_target_is_the_one_the_eval_measures_against(seed_docs):
    body = seed_docs["policies/resolution-targets.md"]
    assert "| P2 | 80 |" in body
    assert "working time" in body, "the measurement basis must be stated"


# ── 5.3 conformant writes ────────────────────────────────────────────────────


def test_a_bare_note_is_given_type_and_generated():
    out = ensure_conformant("Rank 1 holds 23.3% of closures.\n", actor=ACTOR, now=FIXED)
    fm, body = parse(out)
    assert fm["type"] == DEFAULT_NOTE_TYPE
    assert fm["generated"] == {"by": ACTOR, "at": "2026-09-18T07:30:00Z"}
    assert "23.3%" in body


def test_the_resulting_document_is_conformant():
    out = ensure_conformant("a finding\n", actor=ACTOR, now=FIXED)
    assert conformance_errors({"notes/n.md": out}) == []


def test_an_agent_supplied_type_is_kept():
    out = ensure_conformant("---\ntype: Analysis\n---\n\nbody\n", actor=ACTOR, now=FIXED)
    assert parse(out)[0]["type"] == "Analysis"


def test_an_empty_type_is_replaced():
    out = ensure_conformant("---\ntype: ''\ntags: [a]\n---\n\nbody\n", actor=ACTOR, now=FIXED)
    fm, _ = parse(out)
    assert fm["type"] == DEFAULT_NOTE_TYPE
    assert fm["tags"] == ["a"], "unrelated keys must survive"


def test_keys_the_module_does_not_know_are_preserved():
    out = ensure_conformant(
        "---\ntype: Analysis\nmystery_key: 7\n---\n\nbody\n", actor=ACTOR, now=FIXED
    )
    assert parse(out)[0]["mystery_key"] == 7


def test_an_existing_generated_by_is_not_overwritten():
    out = ensure_conformant(
        "---\ntype: Analysis\ngenerated: {by: 'human:someone', at: '2026-01-01T00:00:00Z'}\n---\n\nb\n",
        actor=ACTOR,
        now=FIXED,
    )
    assert parse(out)[0]["generated"]["by"] == "human:someone"


def test_a_generated_missing_its_timestamp_is_completed():
    out = ensure_conformant(
        "---\ntype: Analysis\ngenerated: {by: 'human:someone'}\n---\n\nb\n",
        actor=ACTOR,
        now=FIXED,
    )
    assert parse(out)[0]["generated"] == {"by": "human:someone", "at": "2026-09-18T07:30:00Z"}


def test_a_malformed_block_is_kept_verbatim_in_the_body():
    """A block that did not parse is not silently repaired into another meaning."""
    out = ensure_conformant("---\ntype: [unclosed\n---\n\nbody\n", actor=ACTOR, now=FIXED)
    fm, body = parse(out)
    assert fm["type"] == DEFAULT_NOTE_TYPE
    assert "unclosed" in body


def test_the_actor_follows_the_okf_convention():
    from agent_server.config import OKF_ACTOR

    producer, _, version = OKF_ACTOR.partition("/")
    assert producer and version, "§7 wants `<producer>/<version>` for an agent"
    assert not OKF_ACTOR.startswith("human:"), "an agent must not claim a human actor"


# ── 5.4 what a consumer must tolerate (§11) ──────────────────────────────────


def test_an_unknown_type_is_tolerated(seed_docs):
    seed_docs["policies/odd.md"] = "---\ntype: Entirely Novel Kind\n---\n\nusable body\n"
    assert conformance_errors(seed_docs) == []
    assert "usable body" in parse(seed_docs["policies/odd.md"])[1]


def test_unrecognised_frontmatter_keys_are_tolerated(seed_docs):
    seed_docs["policies/odd.md"] = "---\ntype: Reference\nnot_in_the_spec: {a: 1}\n---\n\nbody\n"
    assert conformance_errors(seed_docs) == []
    assert parse(seed_docs["policies/odd.md"])[0]["not_in_the_spec"] == {"a": 1}


def test_missing_optional_families_are_tolerated(seed_docs):
    """A concept carrying only `type` is fully conformant (§4.1)."""
    seed_docs["policies/odd.md"] = "---\ntype: Reference\n---\n\nbody\n"
    assert conformance_errors(seed_docs) == []


def test_a_broken_cross_link_is_tolerated(seed_docs):
    seed_docs["policies/odd.md"] = (
        "---\ntype: Reference\n---\n\nSee [not written yet](/policies/absent.md).\n"
    )
    assert conformance_errors(seed_docs) == []


def test_a_missing_index_is_tolerated(seed_docs):
    del seed_docs["policies/index.md"]
    assert conformance_errors(seed_docs) == []


def test_a_bare_verified_mapping_is_read_as_one_element(seed_docs):
    """§5.2 / §11 — consumers MUST treat a bare mapping as a one-element list."""
    fm, _ = parse(seed_docs["policies/escalation-matrix.md"])
    verified = fm["verified"]
    assert isinstance(verified, dict), "the seed exercises the bare-mapping form"
    as_list = verified if isinstance(verified, list) else [verified]
    assert len(as_list) == 1 and as_list[0]["by"].startswith("human:")


# ── frontmatter survives repeated rewrites ───────────────────────────────────


def test_an_unquoted_timestamp_keeps_its_canonical_form():
    """YAML parses `2026-07-01T04:00:00Z` to a datetime and dumps it back
    space-separated. §5 asks for the `T...Z` form, so every rewrite would walk
    a document one step further from the spec."""
    out = ensure_conformant(
        "---\ntype: Analysis\nstale_after: 2027-03-31T00:00:00Z\n---\n\nbody\n",
        actor=ACTOR, now=FIXED,
    )
    assert "'2027-03-31T00:00:00Z'" in out
    assert "2027-03-31 00:00:00" not in out


def test_rewriting_a_note_is_idempotent():
    once = ensure_conformant("a finding\n", actor=ACTOR, now=FIXED)
    twice = ensure_conformant(once, actor=ACTOR, now=FIXED)
    assert once == twice


def test_a_nested_timestamp_is_also_canonical():
    out = ensure_conformant(
        "---\ntype: Analysis\nverified: {by: 'human:x', at: 2026-07-01T04:00:00Z}\n---\n\nb\n",
        actor=ACTOR, now=FIXED,
    )
    assert "'2026-07-01T04:00:00Z'" in out
