"""conclusions(a) vs conclusions(b) — what moved, and nothing that did not.

Computed, never authored. This is the brief's "evidence changed → here is what
moved" requirement, satisfied structurally rather than narrated.
"""

from __future__ import annotations

from dataclasses import dataclass

from .graph import Conclusions
from .rules import Status


@dataclass(frozen=True)
class Movement:
    kind: str
    id: str
    before: str
    after: str
    note: str = ""


def diff(a: Conclusions, b: Conclusions) -> tuple[Movement, ...]:
    moves: list[Movement] = []

    for cid in sorted(set(a.conditions) | set(b.conditions)):
        old, new = a.conditions.get(cid), b.conditions.get(cid)
        if old is None:
            moves.append(
                Movement("condition_added", cid, "—", new.status.value, new.label)
            )
            moves.append(Movement("condition_status", cid, "absent", new.status.value, new.label))
        elif new is None:
            moves.append(Movement("condition_removed", cid, old.status.value, "—", old.label))
            continue
        else:
            if old.status is not new.status:
                moves.append(
                    Movement("condition_status", cid, old.status.value, new.status.value, new.label)
                )
            if old.basis is not new.basis:
                moves.append(
                    Movement("condition_basis", cid, old.basis.value, new.basis.value, new.label)
                )
            gained = sorted(set(new.support) - set(old.support))
            if gained:
                moves.append(
                    Movement("support_added", cid, "", ", ".join(gained), new.label)
                )

        was_unknown = old is not None and old.status is Status.UNKNOWN
        is_unknown = new.status is Status.UNKNOWN
        if is_unknown and not was_unknown:
            moves.append(Movement("unknown_opened", cid, "", new.question, new.label))
        if was_unknown and not is_unknown:
            moves.append(Movement("unknown_closed", cid, old.question, new.status.value, new.label))

    for key in sorted(set(a.queues) | set(b.queues)):
        old_q, new_q = a.queues.get(key), b.queues.get(key)
        label = f"{key[0]}/{key[1]}"
        if old_q is None:
            moves.append(Movement("queue_added", label, "—", new_q.mode.value, new_q.head.id))
            continue
        if new_q is None:
            continue
        if old_q.mode is not new_q.mode:
            moves.append(Movement("queue_mode", label, old_q.mode.value, new_q.mode.value, ""))
        if old_q.head.id != new_q.head.id:
            moves.append(Movement("queue_head", label, old_q.head.id, new_q.head.id, ""))
        for lost in sorted(new_q.superseded - old_q.superseded):
            winner = next(
                (c.id for c in new_q.claims if c.supersedes == lost), new_q.head.id
            )
            moves.append(Movement("superseded", lost, "live", winner, label))

    if a.decision.recommendation != b.decision.recommendation:
        moves.append(
            Movement(
                "recommendation",
                b.decision.id,
                a.decision.recommendation,
                b.decision.recommendation,
                b.decision.label,
            )
        )
    elif a.decision.blocking != b.decision.blocking:
        moves.append(
            Movement(
                "blocking_changed",
                b.decision.id,
                ", ".join(a.decision.blocking),
                ", ".join(b.decision.blocking),
                f"still {b.decision.recommendation}, for different reasons",
            )
        )
    if a.decision.basis is not b.decision.basis:
        moves.append(
            Movement(
                "decision_basis", b.decision.id, a.decision.basis.value, b.decision.basis.value, ""
            )
        )

    return tuple(moves)
