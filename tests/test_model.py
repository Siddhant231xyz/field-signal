"""Schema-level risks: a broken ledger must fail loudly, not derive quietly."""

import json

import pytest

from field_signal.model import Ledger, ValidationError, load_fixture, load_ledger


def test_packet_ledger_loads_and_validates():
    ledger = load_ledger()
    assert len(ledger.people) == 7
    assert ledger.claims  # the ledger is not empty
    # Every claim carries the verbatim text it was read from.
    assert all(c.support.strip() for c in ledger.claims.values())


def test_absent_cited_source_is_modelled_not_dropped():
    ledger = load_ledger()
    absent = [s for s in ledger.sources.values() if not s.present]
    assert {s.id for s in absent} == {"S-ABS-RECOVERY", "S-ABS-RCP"}
    # and something actually leans on one of them
    assert any(c.cites_basis == "S-ABS-RECOVERY" for c in ledger.claims.values())


def test_unknown_person_is_a_validation_error(tmp_path):
    bad = {
        "sources": [
            {"id": "S-X", "file": None, "type": "t", "author": "a",
             "logical_time": "t", "locator_model": "l"}
        ],
        "claims": [
            {"id": "CL-X", "source": "S-X", "locator": "1", "stated_by": "ghost",
             "stated_at": "2026-09-14T00:00:00", "kind": "assertion",
             "subject": "s", "predicate": "p", "value": "v", "support": "text"}
        ],
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(ValidationError) as e:
        load_fixture(path).validate()
    assert "unknown person" in str(e.value)


def test_reloading_an_existing_source_id_is_refused(tmp_path):
    """Corrections arrive as a new source, never as an edit to an old one."""
    ledger = load_ledger()
    dup = {
        "sources": [
            {"id": "S-04", "file": None, "type": "t", "author": "a",
             "logical_time": "t", "locator_model": "l"}
        ],
        "claims": [],
    }
    path = tmp_path / "dup.json"
    path.write_text(json.dumps(dup))
    with pytest.raises(ValidationError) as e:
        ledger.merge(load_fixture(path), revision=1)
    assert "already exists" in str(e.value)


def test_revision_slice_excludes_later_sources():
    ledger = load_ledger()
    assert ledger.max_revision() == 0
    fixture = load_fixture("demo/rfi-04.json")
    ledger.merge(fixture, revision=1)
    assert "S-05" in ledger.sources
    assert "S-05" not in ledger.at(0).sources
    assert "S-05" in ledger.at(1).sources
