"""The risks that matter: authority, absence, conflict, taint, determinism.

Each test names the failure it exists to prevent. If one of these passes when
it should not, the product tells Maya Chen something the packet does not say.
"""

import json
import random
from dataclasses import replace
from datetime import timedelta

import pytest

from field_signal import rules
from field_signal.graph import Basis, Mode, Status, conclusions
from field_signal.model import Ledger, ValidationError, load_ledger


BASE_LEDGER = "data/v1"


@pytest.fixture(scope="module")
def base():
    return conclusions(load_ledger(BASE_LEDGER))


# --- authority ------------------------------------------------------------


def test_authorisation_unmet_above_threshold(base):
    """The core money rule: $2,850 > $2,000, and no one authorised it."""
    c = base.conditions["cost_authorised"]
    assert c.status is Status.UNMET
    assert "2,850" in c.reason and "2,000" in c.reason


def test_below_threshold_needs_no_written_authorisation():
    """The rule is driven by the threshold, not hard-coded to this quote."""
    ledger = load_ledger(BASE_LEDGER)
    cheap = ledger.claims["CL-S04-01"]
    ledger.claims["CL-S04-01"] = type(cheap)(**{**cheap.__dict__, "value": "1200.00"})
    ledger.claims["CL-S02-10"] = type(cheap)(
        **{**ledger.claims["CL-S02-10"].__dict__, "value": "1200.00"}
    )
    c = conclusions(ledger).conditions["cost_authorised"]
    assert c.status is Status.MET
    assert "below the" in c.reason


def test_owner_support_is_not_authorisation(base):
    """Tasha Reed's blessing is sentiment; the packet says she cannot authorise."""
    c = base.conditions["cost_authorised"]
    assert c.status is Status.UNMET
    # her claims are shown, and named as not counting
    assert "CL-S02-13" in c.support
    assert "Tasha Reed" in c.reason and "not authorisation" in c.reason


def test_capability_is_read_from_the_packet_not_assumed():
    ledger = load_ledger(BASE_LEDGER)
    assert ledger.people["tasha"].can("owner_preference")
    assert not ledger.people["tasha"].can("authorise_added_cost")
    assert ledger.people["maya"].can("authorise_added_cost")
    assert "$2,000" in ledger.people["maya"].capability_basis


# --- absence is not negation ---------------------------------------------


def test_field_review_outcome_is_unknown_not_false(base):
    """The record stops at 12:22. That is unknown, never 'it did not happen'."""
    c = base.conditions["field_review_outcome_recorded"]
    assert c.status is Status.UNKNOWN
    assert "no record" in c.reason.lower()
    assert "did not" not in c.reason.lower()


def test_conditional_future_sprinkler_layout_does_not_confirm_clearance():
    ledger = load_ledger(BASE_LEDGER)
    prior = ledger.claims["CL-S01-05"]
    ledger.claims["CL-NEW"] = replace(
        prior,
        id="CL-NEW",
        stated_at=prior.stated_at + timedelta(days=1),
        kind="intent",
        value="will_not_be_laid_out_before_access_panel_is_marked",
        support="I will not lay it out before the access panel is marked.",
        refutes=None,
    )

    condition = conclusions(ledger).conditions["sprinkler_clearance_confirmed"]

    assert condition.status is Status.UNKNOWN


def test_schedule_row_does_not_assert_occurrence(base):
    """A120 says 'Booked'. A plan is not a receipt."""
    ledger = load_ledger(BASE_LEDGER)
    booked = ledger.claims["CL-S03-02"]
    assert booked.kind == "plan"
    # nothing derives MET from a plan claim alone
    for cond in base.conditions.values():
        if cond.status is Status.MET:
            kinds = {ledger.claims[i].kind for i in cond.support if i in ledger.claims}
            assert kinds != {"plan"}


# --- photographs ----------------------------------------------------------


def test_caption_yields_only_a_statement_claim():
    ledger = load_ledger(BASE_LEDGER)
    cap = ledger.claims["CL-PREG-01"]
    assert cap.kind == "caption"
    assert cap.predicate == "submitter_caption"  # a claim about what was said
    assert cap.gating_allowed()  # a caption may be cited...
    obs = ledger.claims["CL-P02-01"]
    assert not obs.gating_allowed()  # ...an image observation may not gate


def test_observation_cannot_gate_compliance():
    """Enforced at edge-creation time, not by convention."""
    ledger = load_ledger(BASE_LEDGER)
    rogue = rules.ConditionSpec(
        id="rogue",
        label="compliance from a photograph",
        question="does the photo prove clearance?",
        rule=lambda ev: rules.RuleResult(Status.MET, "the photo shows it", ("CL-P02-01",)),
    )
    with pytest.raises(ValidationError) as e:
        conclusions(ledger, specs=rules.CONDITIONS + (rogue,))
    assert "observation" in str(e.value)


def test_unintelligible_fragment_gates_nothing(base):
    """08:11:02 is neither used as evidence nor hidden from the reader."""
    ledger = load_ledger(BASE_LEDGER)
    frag = ledger.claims["CL-S01-26"]
    assert frag.kind == "unintelligible"
    assert "twenty-four" in frag.value  # kept verbatim
    assert not any("CL-S01-26" in c.support for c in base.conditions.values())
    assert base.queues[("unrecovered_fragment_0811", "fragment")].mode is Mode.SINGLE


# --- conflict -------------------------------------------------------------


def test_three_offsets_surface_as_conflict(base):
    """Never emit an invented number. Three estimates, none measured."""
    q = base.queues[("duct_offset_west", "distance")]
    assert q.mode is Mode.ASSUMED
    assert len(q.claims) == 3
    values = {c.value for c in q.claims}
    assert values == {"about 6 in", "six or eight inches", "approximately 6–12 inches"}
    c = base.conditions["duct_position_established"]
    assert c.status is Status.UNKNOWN
    for v in values:
        assert v in c.reason  # all three shown, no single figure derived


def test_rebuttal_edge_survives_queueing(base):
    """Omar's 08:05:52 statement stays a rebuttal, not a row in a list."""
    ledger = load_ledger(BASE_LEDGER)
    assert ledger.claims["CL-S01-05"].refutes == "CL-S01-03"
    assert ledger.claims["CL-S01-17"].refutes == "CL-S01-16"
    assert "CL-S01-05" in base.rebuttals["CL-S01-03"]
    assert "CL-S01-17" in base.rebuttals["CL-S01-16"]


def test_explicit_supersession_retains_losers(base):
    """Append-only: the superseded claim stays visible with both citations."""
    q = base.queues[("curved_booth_delivery", "date")]
    assert q.mode is Mode.RESOLVED
    assert "CL-S01-19" in q.superseded
    assert any(c.id == "CL-S01-19" for c in q.claims)  # still there
    assert q.head.id == "CL-S02-15"


def test_cited_basis_absent_is_surfaced(base):
    """Nina cites a recovery schedule that is not in the packet."""
    assert "S-ABS-RECOVERY" in base.absent_bases
    assert "CL-S02-15" in base.absent_bases["S-ABS-RECOVERY"]
    assert "S-ABS-RCP" in base.absent_bases


# --- taint ----------------------------------------------------------------


def test_taint_propagates_to_recommendation(base):
    """A conclusion can never render cleaner than the evidence beneath it."""
    assert base.queues[("duct_offset_west", "distance")].mode is Mode.ASSUMED
    assert base.conditions["duct_position_established"].basis is Basis.CONTESTED
    assert base.conditions["sprinkler_clearance_confirmed"].basis is Basis.CONTESTED
    assert base.decision.basis is Basis.CONTESTED


def test_dependency_taint_reaches_a_dependent_condition(base):
    """design_confirmed depends on the access panel; the block is named."""
    c = base.conditions["design_confirmed"]
    assert "access_panel_located" in c.depends_on
    assert base.conditions["access_panel_located"].status is Status.UNKNOWN


def test_recommendation_is_hold_with_reasons(base):
    assert base.decision.recommendation == "HOLD"
    assert base.decision.blocking  # named, not just a verdict
    assert "cost_authorised" in base.decision.blocking


# --- cost -----------------------------------------------------------------


def test_excluded_scope_keeps_cost_unknown(base):
    """$2,850 is the quote, not the exposure."""
    e = {x.id: x for x in base.exposures}["cost_pending"]
    assert "2,850" in e.detail
    assert "excluded" in e.detail.lower()
    assert "unknown" in e.detail.lower()


def test_owner_cost_belief_conflicts_with_the_quote(base):
    e = {x.id: x for x in base.exposures}["cost_pending"]
    assert "two-thousand-dollar issue" in e.detail


# --- determinism ----------------------------------------------------------


def test_determinism_under_input_permutation():
    """Shuffle the ledger; the conclusions must be byte-identical."""
    ledger = load_ledger(BASE_LEDGER)
    first = json.dumps(conclusions(ledger).as_dict(), sort_keys=True)
    for seed in range(5):
        items = list(ledger.claims.items())
        random.Random(seed).shuffle(items)
        shuffled = Ledger(
            people=dict(ledger.people),
            sources=dict(ledger.sources),
            claims=dict(items),
        )
        assert json.dumps(conclusions(shuffled).as_dict(), sort_keys=True) == first
