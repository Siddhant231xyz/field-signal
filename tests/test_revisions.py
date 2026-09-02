"""Revisions are directories: data/v1, data/v2, … each a complete ledger.

A new revision is always built from the *selected* revision plus what was
added, and always takes the next free number. So adding evidence while looking
at v1 produces v3 when v2 already exists — v3's content is v1 + new, not
v2 + new. This is the behaviour the whole feature turns on.
"""

import json
import shutil

import pytest

from field_signal.model import (
    ValidationError,
    create_revision,
    latest_revision,
    load_fixture,
    load_ledger,
    load_revision,
    revision_numbers,
)


@pytest.fixture
def root(tmp_path):
    shutil.copytree("data", tmp_path / "data")
    return tmp_path / "data"


def test_packet_ships_as_revision_one(root):
    assert revision_numbers(root) == [1]
    assert latest_revision(root) == 1
    assert len(load_revision(root, 1).claims) == 75


def test_load_ledger_defaults_to_the_latest_revision():
    assert load_ledger().claims  # no argument still works, for the CLI and tests


def test_new_revision_takes_the_next_free_number(root):
    n = create_revision(root, base=1, added=load_fixture("demo/rfi-04.json"))
    assert n == 2
    assert revision_numbers(root) == [1, 2]


def test_a_new_revision_contains_the_base_plus_what_was_added(root):
    create_revision(root, base=1, added=load_fixture("demo/rfi-04.json"))
    v1, v2 = load_revision(root, 1), load_revision(root, 2)
    assert "CL-S05-01" not in v1.claims
    assert "CL-S05-01" in v2.claims
    assert set(v1.claims) < set(v2.claims)  # nothing from the base is lost
    assert "S-05" in v2.sources


def test_branching_from_an_older_revision_keeps_that_revision_as_the_base(root):
    """The heart of it: base is what you selected, number is what is free."""
    create_revision(root, base=1, added=load_fixture("demo/rfi-04.json"))  # v2
    extra = load_fixture("demo/rfi-04.json")

    # Looking at v1, not v2, when the next evidence arrives.
    n = create_revision(root, base=1, added=_rename(extra, "S-06", "CL-S06"))
    assert n == 3

    v3 = load_revision(root, 3)
    assert "S-06" in v3.sources
    assert "S-05" not in v3.sources  # v2's content is not inherited
    assert set(load_revision(root, 1).claims) < set(v3.claims)


def test_branching_from_the_newer_revision_inherits_it(root):
    create_revision(root, base=1, added=load_fixture("demo/rfi-04.json"))  # v2
    extra = _rename(load_fixture("demo/rfi-04.json"), "S-06", "CL-S06")

    n = create_revision(root, base=2, added=extra)
    assert n == 3
    v3 = load_revision(root, 3)
    assert "S-05" in v3.sources and "S-06" in v3.sources


def test_added_claims_carry_the_new_revision_number(root):
    create_revision(root, base=1, added=load_fixture("demo/rfi-04.json"))
    v2 = load_revision(root, 2)
    assert v2.claims["CL-S05-01"].revision == 2
    assert v2.claims["CL-S01-05"].revision == 1  # unchanged from the base
    assert v2.max_revision() == 2


def test_re_adding_the_same_evidence_adds_nothing(root):
    """Dedup by id, so an agent re-run over the same packet is idempotent."""
    create_revision(root, base=1, added=load_fixture("demo/rfi-04.json"))
    n = create_revision(root, base=2, added=load_fixture("demo/rfi-04.json"))
    assert len(load_revision(root, n).claims) == len(load_revision(root, 2).claims)


def test_a_re_extracted_claim_with_a_new_id_is_still_a_duplicate(root):
    """The agent re-reads the packet and renames ids. Content decides."""
    added = load_fixture("demo/rfi-04.json")
    same_text = _rename(added, "S-05", "CL-RENAMED")  # same source/locator/value
    n = create_revision(root, base=1, added=same_text)
    v = load_revision(root, n)
    fresh = [c for c in v.claims.values() if c.id.startswith("CL-RENAMED")]
    assert len(fresh) == 5
    n2 = create_revision(root, base=n, added=load_fixture("demo/rfi-04.json"))
    assert len(load_revision(root, n2).claims) == len(v.claims)


def test_a_revision_that_fails_validation_is_not_written(root):
    bad = load_fixture("demo/rfi-04.json")
    bad.claims["CL-S05-01"] = type(bad.claims["CL-S05-01"])(
        **{**bad.claims["CL-S05-01"].__dict__, "stated_by": "nobody"}
    )
    with pytest.raises(ValidationError):
        create_revision(root, base=1, added=bad)
    assert revision_numbers(root) == [1]
    assert not (root / "v2").exists()


def test_an_unknown_base_revision_is_refused(root):
    with pytest.raises(ValueError, match="revision"):
        create_revision(root, base=9, added=load_fixture("demo/rfi-04.json"))


def _rename(ledger, source_id, claim_prefix):
    """A copy of a fixture under fresh ids, standing in for a second upload."""
    from dataclasses import replace

    old_source = next(iter(ledger.sources))
    sources = {source_id: replace(ledger.sources[old_source], id=source_id)}
    claims = {}
    for i, c in enumerate(ledger.claims.values(), start=1):
        new_id = f"{claim_prefix}-{i:02d}"
        claims[new_id] = replace(c, id=new_id, source=source_id, supersedes=None)
    return type(ledger)(people={}, sources=sources, claims=claims)
