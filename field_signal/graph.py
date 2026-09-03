"""Queues, topological derivation and taint propagation.

`conclusions(ledger)` is a pure function: same ledger in, byte-identical
conclusions out. Every iteration is over sorted ids, so nothing depends on
dict or set ordering. No I/O, and nothing imported from `render.py`.

The guarantee runs from the accepted ledger to the conclusion. Reading a
document into claims is a human judgment step and sits outside it.
"""

from __future__ import annotations

import graphlib
from collections import defaultdict
from dataclasses import dataclass, field

from .model import Claim, Ledger, ValidationError
from .rules import (
    CONDITIONS,
    DECISION_ID,
    DECISION_LABEL,
    DECISION_QUESTION,
    EXPOSURES,
    Basis,
    ConditionSpec,
    ExposureSpec,
    Mode,
    RuleResult,
    Status,
)

__all__ = ["Basis", "Mode", "Status", "conclusions", "Conclusions", "Queue"]


@dataclass(frozen=True)
class Queue:
    """Claims sharing a subject and predicate, latest on top. Append-only."""

    subject: str
    predicate: str
    claims: tuple[Claim, ...]  # newest first; superseded claims stay in place
    mode: Mode
    superseded: frozenset[str]

    @property
    def head(self) -> Claim:
        for c in self.claims:
            if c.id not in self.superseded:
                return c
        return self.claims[0]

    @property
    def outranked(self) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if c.id != self.head.id)


@dataclass(frozen=True)
class ConditionResult:
    id: str
    label: str
    question: str
    status: Status
    basis: Basis
    reason: str
    support: tuple[str, ...]
    notes: tuple[str, ...]
    depends_on: tuple[str, ...]
    contested_by: tuple[str, ...]  # queue keys or condition ids carrying the taint
    gates: bool


@dataclass(frozen=True)
class DecisionResult:
    id: str
    label: str
    question: str
    recommendation: str
    basis: Basis
    blocking: tuple[str, ...]
    contested_by: tuple[str, ...]


@dataclass(frozen=True)
class Exposure:
    id: str
    label: str
    detail: str
    support: tuple[str, ...]


@dataclass(frozen=True)
class Conclusions:
    revision: int
    queues: dict[tuple[str, str], Queue]
    conditions: dict[str, ConditionResult]
    decision: DecisionResult
    exposures: tuple[Exposure, ...]
    rebuttals: dict[str, tuple[str, ...]]  # refuted claim id -> refuting claim ids
    absent_bases: dict[str, tuple[str, ...]]  # absent source id -> claims leaning on it

    def unknowns(self) -> tuple[ConditionResult, ...]:
        return tuple(c for c in self.conditions.values() if c.status is Status.UNKNOWN)

    def conflicts(self) -> tuple[Queue, ...]:
        return tuple(q for _, q in sorted(self.queues.items()) if q.mode is Mode.ASSUMED)

    def as_dict(self) -> dict:
        """A sorted, primitive-only view. The determinism check hashes this."""
        return {
            "revision": self.revision,
            "queues": {
                f"{s}/{p}": {
                    "mode": q.mode.value,
                    "head": q.head.id,
                    "claims": [c.id for c in q.claims],
                    "superseded": sorted(q.superseded),
                }
                for (s, p), q in sorted(self.queues.items())
            },
            "conditions": {
                cid: {
                    "status": c.status.value,
                    "basis": c.basis.value,
                    "reason": c.reason,
                    "support": list(c.support),
                    "notes": list(c.notes),
                    "contested_by": list(c.contested_by),
                }
                for cid, c in sorted(self.conditions.items())
            },
            "decision": {
                "recommendation": self.decision.recommendation,
                "basis": self.decision.basis.value,
                "blocking": list(self.decision.blocking),
                "contested_by": list(self.decision.contested_by),
            },
            "exposures": [
                {"id": e.id, "detail": e.detail, "support": list(e.support)}
                for e in self.exposures
            ],
            "rebuttals": {k: list(v) for k, v in sorted(self.rebuttals.items())},
            "absent_bases": {k: list(v) for k, v in sorted(self.absent_bases.items())},
        }


class Evidence:
    """The read-only facade a rule sees. Sorted access only."""

    def __init__(self, ledger: Ledger, queues: dict[tuple[str, str], Queue]):
        self.ledger = ledger
        self.queues = queues

    def queue(self, subject: str, predicate: str) -> Queue | None:
        return self.queues.get((subject, predicate))

    def head(self, subject: str, predicate: str) -> Claim | None:
        q = self.queue(subject, predicate)
        return q.head if q else None

    def claims(self, subject: str, predicate: str | None = None) -> list[Claim]:
        return self.ledger.by_subject(subject, predicate)

    def source(self, source_id: str):
        return self.ledger.sources[source_id]

    def person(self, person_id: str):
        return self.ledger.people[person_id]

    def name(self, claim: Claim) -> str:
        return self.ledger.author_of(claim)

    def can(self, claim: Claim, capability: str) -> bool:
        p = self.ledger.people.get(claim.stated_by or "")
        return bool(p and p.can(capability))

    def cite(self, claim: Claim | None) -> str:
        return f"{claim.source} {claim.locator}" if claim else "—"


def build_queues(ledger: Ledger) -> dict[tuple[str, str], Queue]:
    grouped: dict[tuple[str, str], list[Claim]] = defaultdict(list)
    for c in ledger.claim_list():
        grouped[c.queue_key].append(c)

    queues: dict[tuple[str, str], Queue] = {}
    for key in sorted(grouped):
        claims = sorted(grouped[key], key=lambda c: (c.stated_at, c.id), reverse=True)
        present = {c.id for c in claims}
        superseded = frozenset(
            c.supersedes for c in claims if c.supersedes and c.supersedes in present
        )
        live = [c for c in claims if c.id not in superseded] or list(claims)
        head = live[0]
        if any(c.value != head.value for c in live[1:]):
            mode = Mode.ASSUMED
        elif head.supersedes in present:
            mode = Mode.RESOLVED
        else:
            mode = Mode.SINGLE
        queues[key] = Queue(key[0], key[1], tuple(claims), mode, superseded)
    return queues


def _assumed_heads(queues: dict[tuple[str, str], Queue]) -> dict[str, str]:
    """claim id -> "subject/predicate" for every head of an ASSUMED queue."""
    return {
        q.head.id: f"{s}/{p}"
        for (s, p), q in sorted(queues.items())
        if q.mode is Mode.ASSUMED
    }


def _check_gating(spec: ConditionSpec, result: RuleResult, ledger: Ledger) -> None:
    """A photograph or a noise fragment may never gate a decision."""
    if not spec.gates:
        return
    for cid in result.support:
        claim = ledger.claims.get(cid)
        if claim is None:
            raise ValidationError([f"{spec.id}: rule returned unknown claim {cid!r}"])
        if not claim.gating_allowed():
            raise ValidationError(
                [
                    f"{spec.id}: claim {cid} is kind {claim.kind!r} and may never gate a "
                    f"decision — an observation proves nothing about authority, "
                    f"completion, dimension or code compliance"
                ]
            )


def conclusions(
    ledger: Ledger,
    specs: tuple[ConditionSpec, ...] = CONDITIONS,
    exposures: tuple[ExposureSpec, ...] = EXPOSURES,
) -> Conclusions:
    queues = build_queues(ledger)
    ev = Evidence(ledger, queues)
    tainted = _assumed_heads(queues)

    active = {
        s.id: s
        for s in specs
        if s.introduced_by in ledger.sources
        or (s.introduced_by_claim is not None and s.introduced_by_claim in queues)
    }
    order = graphlib.TopologicalSorter(
        {sid: set(s.depends_on) & set(active) for sid, s in sorted(active.items())}
    )

    results: dict[str, ConditionResult] = {}
    for sid in order.static_order():
        spec = active[sid]
        result = spec.rule(ev)
        _check_gating(spec, result, ledger)

        contested = sorted({tainted[c] for c in result.support if c in tainted})
        deps = tuple(d for d in spec.depends_on if d in results)
        contested += [d for d in deps if results[d].basis is Basis.CONTESTED]

        status, reason = result.status, result.reason
        blocked = [d for d in deps if results[d].status is not Status.MET]
        if status is Status.MET and blocked:
            # A premise that is not settled cannot leave a conclusion settled.
            status = Status.UNKNOWN
            reason += f" Blocked: {', '.join(blocked)} is not met."

        results[sid] = ConditionResult(
            id=sid,
            label=spec.label,
            question=spec.question,
            status=status,
            basis=Basis.CONTESTED if contested else Basis.SETTLED,
            reason=reason,
            support=tuple(result.support),
            notes=tuple(result.notes),
            depends_on=tuple(spec.depends_on),
            contested_by=tuple(sorted(set(contested))),
            gates=spec.gates,
        )

    gates = [results[k] for k in sorted(results) if results[k].gates]
    blocking = tuple(c.id for c in gates if c.status is not Status.MET)
    decision_taint = tuple(
        sorted({t for c in gates for t in c.contested_by if c.basis is Basis.CONTESTED})
    )
    decision = DecisionResult(
        id=DECISION_ID,
        label=DECISION_LABEL,
        question=DECISION_QUESTION,
        recommendation="HOLD" if blocking else "PROCEED",
        basis=Basis.CONTESTED if decision_taint else Basis.SETTLED,
        blocking=blocking,
        contested_by=decision_taint,
    )

    rebuttals: dict[str, list[str]] = defaultdict(list)
    for c in ledger.claim_list():
        if c.refutes:
            rebuttals[c.refutes].append(c.id)

    absent: dict[str, list[str]] = defaultdict(list)
    for c in ledger.claim_list():
        if c.cites_basis and not ledger.sources[c.cites_basis].present:
            absent[c.cites_basis].append(c.id)

    return Conclusions(
        revision=ledger.max_revision(),
        queues=queues,
        conditions=results,
        decision=decision,
        exposures=tuple(
            Exposure(spec.id, spec.label, *spec.rule(ev)) for spec in exposures
        ),
        rebuttals={k: tuple(sorted(v)) for k, v in sorted(rebuttals.items())},
        absent_bases={k: tuple(sorted(v)) for k, v in sorted(absent.items())},
    )
