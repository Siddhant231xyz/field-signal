"""Condition rules — pure functions over the evidence. No I/O, no rendering.

A rule reads claims and returns a status, a reason a project manager can act
on, and the claim ids it actually read. Those ids *are* the `supports` edges:
they are materialised at derivation time, so "why did this change?" is
answerable without reading the renderer.

A rule may never invent a value the packet does not contain. Where the packet
disagrees with itself, the rule reports the disagreement instead of choosing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


# The extractor sees this alongside the selected ledger. These are application
# inputs, not expected facts: a queue appearing here never implies that a packet
# contains a claim for it. Keeping the contract beside its consumers prevents a
# model from having to reverse-engineer otherwise invisible predicate names.
INGESTION_CONTRACT = {
    "version": 1,
    "purpose": (
        "Canonical claim queues consumed by deterministic application rules. "
        "Use a queue only when packet evidence has the described meaning."
    ),
    "queues": {
        "above_ceiling_inspection/date": {
            "meaning": "Planned or stated date of the above-ceiling inspection."
        },
        "access_panel_location/drawing_shows": {
            "meaning": "What a cited drawing states about the access-panel location."
        },
        "access_panel_location/fixed_location": {
            "meaning": "The current fixed location, or that no location is yet proposed."
        },
        "authority_rules/cost_threshold": {
            "meaning": "Monetary threshold above which written authorisation is required."
        },
        "authority_rules/verbal_direction": {
            "meaning": "Rule limiting when verbal field direction may authorise work."
        },
        "ca_118/authorisation": {
            "meaning": "Whether the added cost has been authorised in writing.",
            "value_constraints": {
                "assertion": {"allowed": ["authorised", "not_authorised"]}
            },
        },
        "ca_118/excludes_fire_protection": {
            "meaning": "Whether the quoted scope excludes fire-protection work."
        },
        "ca_118/excludes_redesign": {
            "meaning": "Whether the quoted scope excludes design or permit revision."
        },
        "ca_118/exclusions": {
            "meaning": "Other work or assumptions excluded from the quoted scope."
        },
        "ca_118/owner_cost_belief": {
            "meaning": "An owner's stated belief about the amount of the cost."
        },
        "ca_118/owner_preference": {
            "meaning": "Owner preference or support, distinct from authorisation."
        },
        "ca_118/quoted_amount": {
            "meaning": "The contractor's quoted monetary amount."
        },
        "ca_118/signature": {
            "meaning": "Whether the change quotation or authorisation is signed."
        },
        "clearance_north_of_panel/as_built_verified": {
            "meaning": "Whether the required clearance was verified against as-built work.",
            "value_constraints": {
                "assertion": {"allowed": ["verified", "not_verified"]}
            },
        },
        "clearance_north_of_panel/required_clear": {
            "meaning": "Required clear dimension north of the access panel."
        },
        "crew_availability/answer_deadline": {
            "meaning": "Deadline for direction before a crew becomes unavailable."
        },
        "diffuser_relocation/architect_confirmation_requested": {
            "meaning": "A request for architectural confirmation of the relocation."
        },
        "diffuser_relocation/design_acceptance": {
            "meaning": "Architectural acceptance or rejection of the proposed relocation.",
            "value_constraints": {
                "assertion": {
                    "prefixes": ["permitted", "not_permitted"]
                }
            },
        },
        "duct_branch_position/moved": {
            "meaning": "Whether the duct branch was moved from its prior position."
        },
        "duct_branch_position/reversibility": {
            "meaning": "Whether performed duct work can still be reversed."
        },
        "duct_branch_position/submitter_caption": {
            "meaning": "Submitter's own caption describing the duct position."
        },
        "duct_offset_west/distance": {
            "meaning": "Stated or measured westward duct offset distance."
        },
        "duct_offset_west/measurability": {
            "meaning": "Whether supplied evidence permits the offset to be measured."
        },
        "field_direction/standing_direction": {
            "meaning": "The latest field direction that remains in force."
        },
        "field_review/outcome": {
            "meaning": "Recorded result of a field review that actually occurred."
        },
        "field_review/scheduled": {
            "meaning": "A scheduled field review; this does not prove occurrence."
        },
        "luis_marked_photo/currency": {
            "meaning": "Whether the marked photograph depicts the current condition."
        },
        "soffit_close_in/date": {
            "meaning": "Planned or stated soffit close-in date."
        },
        "sprinkler_clearance/assessment": {
            "meaning": "Fire-protection assessment of clearance at the current layout.",
            "value_constraints": {
                "assertion": {"allowed": ["confirmed", "not_confirmed"]}
            },
        },
        "sprinkler_head_location/blocked_by": {
            "meaning": "Unresolved input preventing final sprinkler-head layout."
        },
        "sprinkler_head_location/final_layout": {
            "meaning": "Whether the final sprinkler-head layout has been completed.",
            "value_constraints": {
                "assertion": {"allowed": ["laid_out", "not_laid_out"]}
            },
        },
        "unrecovered_fragment_0811/fragment": {
            "meaning": "Unintelligible recorded fragment retained without interpretation."
        },
    },
}


class Status(str, Enum):
    MET = "met"
    UNMET = "unmet"
    UNKNOWN = "unknown"


class Basis(str, Enum):
    SETTLED = "settled"
    CONTESTED = "contested"


class Mode(str, Enum):
    SINGLE = "single"  # one claim, or several that agree
    RESOLVED = "resolved"  # the head explicitly supersedes a lower claim
    ASSUMED = "assumed"  # the head disagrees and declares nothing


@dataclass(frozen=True)
class RuleResult:
    status: Status
    reason: str
    support: tuple[str, ...] = ()  # claim ids the rule read — these gate
    notes: tuple[str, ...] = ()  # claim ids shown but never allowed to gate


@dataclass(frozen=True)
class ConditionSpec:
    id: str
    label: str
    question: str
    rule: Callable[..., RuleResult]
    depends_on: tuple[str, ...] = ()
    gates: bool = True
    introduced_by: str = "S-00"  # condition exists only once this source does
    introduced_by_claim: tuple[str, str] | None = None


@dataclass(frozen=True)
class ExposureSpec:
    """Already true, and behind her. Not decidable, so never a condition."""

    id: str
    label: str
    rule: Callable[..., tuple[str, tuple[str, ...]]]


def _ids(*claims) -> tuple[str, ...]:
    return tuple(c.id for c in claims if c is not None)


# --- conditions -----------------------------------------------------------


def cost_authorised(ev) -> RuleResult:
    threshold = ev.head("authority_rules", "cost_threshold")
    amount = ev.head("ca_118", "quoted_amount")
    decisions = ev.claims("ca_118", "authorisation")
    owner = ev.claims("ca_118", "owner_preference")
    support = _ids(threshold, amount) + tuple(c.id for c in decisions + owner)

    if amount is None or threshold is None:
        return RuleResult(Status.UNKNOWN, "No quoted amount or threshold is in evidence.", support)

    quoted, limit = float(amount.value), float(threshold.value)
    if quoted <= limit:
        return RuleResult(
            Status.MET,
            f"${quoted:,.2f} is below the ${limit:,.0f} threshold, so no written "
            f"authorisation is required before Northline treats it as approved "
            f"({ev.cite(threshold)}).",
            support,
        )

    approved = [c for c in decisions if c.value == "authorised" and ev.can(c, "authorise_added_cost")]
    if approved:
        head = approved[-1]
        return RuleResult(
            Status.MET,
            f"Authorised in writing by {ev.name(head)} ({ev.cite(head)}).",
            support,
        )

    refusals = "; ".join(f"{ev.cite(c)} {ev.name(c)}" for c in decisions if c.value == "not_authorised")
    backers = ", ".join(sorted({ev.name(c) for c in owner}))
    return RuleResult(
        Status.UNMET,
        f"${quoted:,.2f} exceeds the ${limit:,.0f} threshold, so it requires "
        f"{ev.person('maya').name}'s written authorisation ({ev.cite(threshold)}). "
        f"No authorisation appears anywhere in the packet — the quote is still marked "
        f"“PRICING SUBMITTED — NOT AUTHORISED” and unsigned, and the record shows only "
        f"refusals to date [{refusals}]. Support from {backers} is not authorisation: "
        f"the working rules say she does not directly authorise subcontractor changes.",
        support,
    )


def design_confirmed(ev) -> RuleResult:
    q = ev.queue("diffuser_relocation", "design_acceptance")
    asked = ev.claims("diffuser_relocation", "architect_confirmation_requested")
    support = tuple(c.id for c in asked) + (tuple(c.id for c in q.claims) if q else ())

    if q is None:
        return RuleResult(Status.UNKNOWN, "The architect has not been asked.", support)

    head = q.head
    if head.kind == "intent":
        return RuleResult(
            Status.UNKNOWN,
            f"{ev.name(head)} stated an intent to review — “{head.support}” "
            f"({ev.cite(head)}) — three days after being asked ({ev.cite(asked[0])}). "
            f"The packet holds no outcome of that review. That is unknown, not a refusal.",
            support,
        )
    if ev.can(head, "design_acceptance") and head.value.startswith("permitted"):
        return RuleResult(
            Status.MET,
            f"{ev.name(head)} confirmed the shift is acceptable ({ev.cite(head)}): "
            f"“{head.support}” Design acceptability only — the working rules say she "
            f"does not approve contractor pricing.",
            support,
        )
    return RuleResult(
        Status.UNKNOWN,
        f"The latest statement on design acceptance is “{head.value}” by "
        f"{ev.name(head)} ({ev.cite(head)}), which is not a confirmation.",
        support,
    )


def access_panel_located(ev) -> RuleResult:
    q = ev.queue("access_panel_location", "fixed_location")
    drawing = ev.claims("access_panel_location", "drawing_shows")
    waiting = ev.claims("sprinkler_head_location", "blocked_by")
    support = (tuple(c.id for c in q.claims) if q else ()) + tuple(
        c.id for c in drawing + waiting
    )

    if q is None or q.head.value == "not_yet_proposed":
        cited = ", ".join(
            f"{c.cites_basis} (not supplied)"
            for c in drawing
            if c.cites_basis and not ev.source(c.cites_basis).present
        )
        return RuleResult(
            Status.UNKNOWN,
            f"No one has proposed or fixed a location. {ev.name(drawing[0])} asked for a "
            f"proposal ({ev.cite(drawing[0])}) and cites a reflected ceiling plan showing it "
            f"“centred between lights” — that drawing is not in the packet [{cited}], so the "
            f"position cannot be checked. Two people are waiting on this answer: "
            f"{ev.name(waiting[0])} will not finalise the sprinkler head without it "
            f"({ev.cite(waiting[0])}), and the architect will not confirm the duct without it.",
            support,
        )
    return RuleResult(
        Status.MET,
        f"Fixed by {ev.name(q.head)} ({ev.cite(q.head)}): {q.head.value}.",
        support,
    )


def sprinkler_clearance_confirmed(ev) -> RuleResult:
    layout = ev.head("sprinkler_head_location", "final_layout")
    assessment = ev.head("sprinkler_clearance", "assessment")
    stale = ev.head("luis_marked_photo", "currency")
    offset = ev.head("duct_offset_west", "distance")
    support = _ids(layout, assessment, stale, offset)

    layout_confirmed = (
        layout is not None
        and layout.kind == "assertion"
        and layout.value == "laid_out"
    )
    clearance_confirmed = (
        assessment is not None
        and assessment.kind == "assertion"
        and assessment.value == "confirmed"
    )
    if not layout_confirmed or not clearance_confirmed:
        layout_detail = layout.value if layout is not None else "no final layout"
        assessment_detail = (
            assessment.value if assessment is not None else "no clearance assessment"
        )
        return RuleResult(
            Status.UNKNOWN,
            f"The latest final-layout evidence is “{layout_detail}” ({ev.cite(layout)}), "
            f"and the latest clearance assessment is “{assessment_detail}” "
            f"({ev.cite(assessment)}). Both an explicitly completed layout and an explicit "
            f"clearance confirmation are required; conditional, estimated, or missing "
            f"evidence remains unknown.",
            support,
        )
    return RuleResult(
        Status.MET,
        f"Confirmed by {ev.name(layout)} ({ev.cite(layout)}).",
        support,
    )


def duct_position_established(ev) -> RuleResult:
    q = ev.queue("duct_offset_west", "distance")
    unmeasurable = ev.claims("duct_offset_west", "measurability")
    support = tuple(c.id for c in q.claims) if q else ()
    notes = tuple(c.id for c in unmeasurable)

    if q is None:
        return RuleResult(Status.UNKNOWN, "No one has stated how far the branch moved.", support)
    if q.mode is Mode.ASSUMED:
        stated = "; ".join(f"“{c.value}” — {ev.name(c)}, {ev.cite(c)}" for c in q.claims)
        return RuleResult(
            Status.UNKNOWN,
            f"Three stated offsets, none of them a measurement: {stated}. No dimension "
            f"appears anywhere in the packet, and the one photograph of the condition "
            f"contains no scale reference, so no single figure is derived here.",
            support,
            notes,
        )
    return RuleResult(
        Status.MET,
        f"Established as {q.head.value} ({ev.cite(q.head)}).",
        support,
        notes,
    )


def field_review_outcome_recorded(ev) -> RuleResult:
    scheduled = ev.claims("field_review", "scheduled")
    outcome = ev.claims("field_review", "outcome")
    required = ev.head("field_direction", "standing_direction")
    support = tuple(c.id for c in scheduled + outcome) + _ids(required)

    if outcome:
        head = outcome[-1]
        return RuleResult(
            Status.MET, f"Outcome recorded by {ev.name(head)} ({ev.cite(head)}).", support
        )
    when = scheduled[-1] if scheduled else None
    return RuleResult(
        Status.UNKNOWN,
        f"A 13:00 field review with the architect, the fire-protection foreman and the "
        f"HVAC foreman was scheduled ({ev.cite(when)}) — a plan, not an event — and the "
        f"project manager made it the precondition for further direction. The packet holds "
        f"no record of whether it took place or what it concluded; the record simply stops "
        f"at 12:22. Absence of a record is not evidence of absence.",
        support,
    )


def clearance_24in_maintained(ev) -> RuleResult:
    required = ev.head("clearance_north_of_panel", "required_clear")
    verified = ev.head("clearance_north_of_panel", "as_built_verified")
    offset = ev.head("duct_offset_west", "distance")
    fragment = ev.head("unrecovered_fragment_0811", "fragment")
    support = _ids(required, verified, offset)
    notes = _ids(fragment)

    if required is None:
        return RuleResult(Status.UNKNOWN, "No clearance dimension is in evidence.", support)
    if verified is not None and verified.value == "not_verified":
        return RuleResult(
            Status.UNKNOWN,
            f"{required.value} clear is now required north of the access panel "
            f"({ev.cite(required)}), but the as-built branch position has never been "
            f"dimensioned ({ev.cite(verified)}) and the three stated offsets disagree. "
            f"Whether {required.value} is achievable where the duct now sits is unknown. "
            f"The 08:11:02 fragment (“… access … twenty-four … north …”) is unintelligible "
            f"and is not treated as corroboration of this figure.",
            support,
            notes,
        )
    return RuleResult(
        Status.MET, f"{required.value} clear verified ({ev.cite(verified)}).", support, notes
    )


CONDITIONS: tuple[ConditionSpec, ...] = (
    ConditionSpec(
        id="cost_authorised",
        label="Added cost is authorised in writing",
        question="Has anyone with the authority to spend this money actually approved it?",
        rule=cost_authorised,
    ),
    ConditionSpec(
        id="access_panel_located",
        label="Access-panel location is fixed",
        question="Where does the access panel go? Everything else waits on this.",
        rule=access_panel_located,
    ),
    ConditionSpec(
        id="design_confirmed",
        label="Architect has confirmed the diffuser may shift",
        question="Is the new duct position acceptable as design?",
        rule=design_confirmed,
        depends_on=("access_panel_located",),
    ),
    ConditionSpec(
        id="sprinkler_clearance_confirmed",
        label="Fire-protection clearance is confirmed",
        question="Will the sprinkler head fit alongside the duct where it now is?",
        rule=sprinkler_clearance_confirmed,
        depends_on=("access_panel_located",),
    ),
    ConditionSpec(
        id="duct_position_established",
        label="The as-built duct offset is established",
        question="How far west did the branch actually move?",
        rule=duct_position_established,
    ),
    ConditionSpec(
        id="field_review_outcome_recorded",
        label="The field review produced a recorded outcome",
        question="Did the 1:00 review happen, and what did it decide?",
        rule=field_review_outcome_recorded,
    ),
    ConditionSpec(
        id="clearance_24in_maintained",
        label="24 in clear north of the panel is achievable",
        question="Does the architect's clearance survive the duct's actual position?",
        rule=clearance_24in_maintained,
        depends_on=("access_panel_located", "duct_position_established"),
        introduced_by="S-05",
        introduced_by_claim=("clearance_north_of_panel", "required_clear"),
    ),
)


# --- exposure: already true, and behind her -------------------------------


def unauthorised_work(ev) -> tuple[str, tuple[str, ...]]:
    moved_q = ev.queue("duct_branch_position", "moved")
    moved = moved_q.claims[-1]  # cite the first report of the move, not the restatement
    reversible = ev.head("duct_branch_position", "reversibility")
    verbal = ev.head("authority_rules", "verbal_direction")
    caption = ev.head("duct_branch_position", "submitter_caption")
    return (
        f"The branch was moved west on 13 September ({ev.cite(moved)}), a day before any "
        f"review and with no authorisation in evidence. The working rules allow verbal "
        f"direction only to protect safety or prevent immediate damage ({ev.cite(verbal)}); "
        f"the stated reason was to keep the framers moving. {ev.name(reversible)} says it is "
        f"reversible — no final tap, no diffuser, no ceiling cut ({ev.cite(reversible)}) — "
        f"and that is the only thing keeping the cost bounded. Reversibility is his claim "
        f"about his own work, corroborated by his own photograph caption "
        f"({ev.cite(caption)}), not by an independent inspection.",
        _ids(moved, reversible, verbal, caption),
    )


def cost_pending(ev) -> tuple[str, tuple[str, ...]]:
    amount = ev.head("ca_118", "quoted_amount")
    exclusions = ev.head("ca_118", "exclusions")
    fire = ev.head("ca_118", "excludes_fire_protection")
    redesign = ev.head("ca_118", "excludes_redesign")
    signature = ev.head("ca_118", "signature")
    belief = ev.head("ca_118", "owner_cost_belief")
    return (
        f"${float(amount.value):,.2f} is quoted and unauthorised, on an unsigned copy "
        f"({ev.cite(signature)}). Five things are excluded from that figure: drywall "
        f"patching, painting and ceiling-grid changes; fire-protection relocation or rework "
        f"({ev.cite(fire)}); architectural redesign and permit revision ({ev.cite(redesign)}); "
        f"an assumption of normal-hours access; and any schedule impact beyond Cascade Air's "
        f"own working day. Two of those excluded items — sprinkler rework and redesign — are "
        f"exactly what the unresolved questions could trigger, so the real exposure is "
        f"unknown and cannot be lower than the quote. Separately, the owner's representative "
        f"has referred to it as “a two-thousand-dollar issue” ({ev.cite(belief)}); the quote "
        f"says ${float(amount.value):,.2f}.",
        _ids(amount, exclusions, fire, redesign, signature, belief),
    )


def crew_held(ev) -> tuple[str, tuple[str, ...]]:
    deadline_q = ev.queue("crew_availability", "answer_deadline")
    deadline = deadline_q.head
    inspection = ev.queue("above_ceiling_inspection", "date")
    close_in = ev.head("soffit_close_in", "date")
    cites = ", ".join(ev.cite(c) for c in reversed(inspection.claims))
    return (
        f"{ev.name(deadline)} requires an answer today or loses the Tuesday crew "
        f"({', '.join(ev.cite(c) for c in reversed(deadline_q.claims))}). Behind that sit "
        f"two planned dates — the above-ceiling inspection on {inspection.head.value} "
        f"({cites}) and gypsum close-in on {close_in.value} ({ev.cite(close_in)}) — which "
        f"are working-plan dates, not proof that anything will happen or has happened. The "
        f"packet does not price the cost of holding.",
        tuple(c.id for c in deadline_q.claims + inspection.claims) + _ids(close_in),
    )


def standing_direction(ev) -> tuple[str, tuple[str, ...]]:
    q = ev.queue("field_direction", "standing_direction")
    cites = ", ".join(ev.cite(c) for c in reversed(q.claims))
    return (
        f"Unchanged and restated three times: no final duct connection, and no board in the "
        f"affected bay ({cites}). This is the one thing currently protecting the option to "
        f"put the duct back.",
        tuple(c.id for c in q.claims),
    )


EXPOSURES: tuple[ExposureSpec, ...] = (
    ExposureSpec("unauthorised_work", "Work already performed without authorisation", unauthorised_work),
    ExposureSpec("cost_pending", "Cost pending, and larger than the quote", cost_pending),
    ExposureSpec("crew_held", "A crew held against a fixed sequence", crew_held),
    ExposureSpec("standing_direction", "The direction currently in force", standing_direction),
)


DECISION_ID = "ca_118_direction"
DECISION_LABEL = "Direction on CA-118 — north soffit duct relocation"
DECISION_QUESTION = "Should Northline direct Cascade Air to complete the relocation?"
