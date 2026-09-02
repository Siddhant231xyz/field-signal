"""The brief's requirement: evidence changed → here is what moved.

The diff is computed from two revisions of the ledger. It is never authored,
so it cannot flatter the demo.
"""

import shutil

import pytest

from field_signal.diff import diff
from field_signal.graph import Basis, Mode, Status, conclusions
from field_signal.model import create_revision, load_fixture, load_revision


@pytest.fixture(scope="module")
def revisions(tmp_path_factory):
    root = tmp_path_factory.mktemp("repo") / "data"
    shutil.copytree("data", root)
    n = create_revision(root, base=1, added=load_fixture("demo/rfi-04.json"))
    return conclusions(load_revision(root, 1)), conclusions(load_revision(root, n))


def test_identical_revisions_produce_no_movement(revisions):
    c = revisions[0]
    assert diff(c, c) == ()


def test_diff_reports_only_changed_conditions(revisions):
    before, after = revisions
    moved = {m.id for m in diff(before, after) if m.kind == "condition_status"}
    assert moved == {"design_confirmed", "access_panel_located", "clearance_24in_maintained"}
    # the fire-protection question did not move, and must not be reported as if it did
    assert before.conditions["sprinkler_clearance_confirmed"].status is Status.UNKNOWN
    assert after.conditions["sprinkler_clearance_confirmed"].status is Status.UNKNOWN
    assert "cost_authorised" not in moved


def test_new_evidence_opens_a_question_that_did_not_exist(revisions):
    before, after = revisions
    assert "clearance_24in_maintained" not in before.conditions
    new = after.conditions["clearance_24in_maintained"]
    assert new.status is Status.UNKNOWN
    assert new.basis is Basis.CONTESTED  # it hangs off the disputed offset
    opened = {m.id for m in diff(before, after) if m.kind == "unknown_opened"}
    closed = {m.id for m in diff(before, after) if m.kind == "unknown_closed"}
    assert opened == {"clearance_24in_maintained"}
    assert closed == {"design_confirmed", "access_panel_located"}


def test_supersession_is_reported_with_both_claims(revisions):
    before, after = revisions
    superseded = {m.id: m for m in diff(before, after) if m.kind == "superseded"}
    assert set(superseded) == {"CL-S02-03", "CL-S02-04"}
    assert superseded["CL-S02-03"].after == "CL-S05-01"
    q = after.queues[("diffuser_relocation", "design_acceptance")]
    assert q.mode is Mode.RESOLVED
    assert any(c.id == "CL-S02-03" for c in q.claims)  # the loser stays readable


def test_recommendation_holds_for_a_different_reason(revisions):
    """A fixture that resolved everything cleanly would prove nothing."""
    before, after = revisions
    assert before.decision.recommendation == "HOLD"
    assert after.decision.recommendation == "HOLD"
    assert before.decision.blocking != after.decision.blocking
    assert "cost_authorised" in after.decision.blocking
    changed = {m.kind for m in diff(before, after)}
    assert "blocking_changed" in changed
    assert "recommendation" not in changed


def test_new_claim_on_an_unchanged_conclusion_is_still_reported(revisions):
    """Priya restates that pricing is not hers. The answer does not move."""
    before, after = revisions
    added = {m.id: m for m in diff(before, after) if m.kind == "support_added"}
    assert "cost_authorised" in added
    assert "CL-S05-05" in added["cost_authorised"].after
