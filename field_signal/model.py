"""Typed evidence nodes and schema validation.

This layer knows what a claim *is*. It does no derivation and reaches no
conclusion — that is `graph.py`. The only I/O is reading the JSON ledger.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path

# A claim's kind constrains what it is allowed to do downstream.
CLAIM_KINDS = {
    "assertion",  # a direct statement of fact by its author
    "estimate",  # explicitly approximate; never rendered as a single value
    "intent",  # what someone said they would do; never that they did it
    "plan",  # a scheduled date; never evidence work occurred
    "caption",  # a submitter's description of their own photo
    "observation",  # what is visible in an image
    "unintelligible",  # recorded but not recoverable
}

# Kinds that may never support a gating condition. Enforced in graph.py at
# edge-creation time, not by convention.
NON_GATING_KINDS = {"observation", "unintelligible"}


class ValidationError(Exception):
    """Raised with every problem found, not just the first."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    org: str
    role: str
    capabilities: tuple[str, ...]
    capability_basis: str = ""

    def can(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True)
class Source:
    id: str
    file: str | None
    type: str
    author: str
    logical_time: str
    locator_model: str
    limitations: tuple[str, ...] = ()
    present: bool = True
    revision: int = 0


@dataclass(frozen=True)
class Claim:
    id: str
    source: str
    locator: str
    stated_by: str | None  # None where the source is a document, not a person
    stated_at: datetime
    kind: str
    subject: str
    predicate: str
    value: str
    support: str  # verbatim text the claim was read from
    cites_basis: str | None = None
    supersedes: str | None = None
    refutes: str | None = None
    revision: int = 0

    @property
    def queue_key(self) -> tuple[str, str]:
        return (self.subject, self.predicate)

    def gating_allowed(self) -> bool:
        return self.kind not in NON_GATING_KINDS


@dataclass
class Ledger:
    people: dict[str, Person] = field(default_factory=dict)
    sources: dict[str, Source] = field(default_factory=dict)
    claims: dict[str, Claim] = field(default_factory=dict)

    # --- access -----------------------------------------------------------

    def claim_list(self) -> list[Claim]:
        """All claims, in a deterministic order independent of insertion."""
        return sorted(self.claims.values(), key=lambda c: (c.stated_at, c.id))

    def by_subject(self, subject: str, predicate: str | None = None) -> list[Claim]:
        return [
            c
            for c in self.claim_list()
            if c.subject == subject and (predicate is None or c.predicate == predicate)
        ]

    def author_of(self, claim: Claim) -> str:
        if claim.stated_by and claim.stated_by in self.people:
            return self.people[claim.stated_by].name
        return self.sources[claim.source].author

    def max_revision(self) -> int:
        revs = [s.revision for s in self.sources.values()]
        revs += [c.revision for c in self.claims.values()]
        return max(revs, default=0)

    # --- validation -------------------------------------------------------

    def validate(self) -> None:
        """Report every problem found, not just the first."""
        problems: list[str] = []
        for c in sorted(self.claims.values(), key=lambda c: c.id):
            if c.kind not in CLAIM_KINDS:
                problems.append(f"{c.id}: unknown kind {c.kind!r}")
            if c.source not in self.sources:
                problems.append(f"{c.id}: unknown source {c.source!r}")
            if c.stated_by is not None and c.stated_by not in self.people:
                problems.append(f"{c.id}: unknown person {c.stated_by!r}")
            if c.cites_basis and c.cites_basis not in self.sources:
                problems.append(f"{c.id}: cites unknown source {c.cites_basis!r}")
            for rel in ("supersedes", "refutes"):
                target = getattr(c, rel)
                if target == c.id:
                    problems.append(f"{c.id}: {rel} itself")
                elif target and target not in self.claims:
                    problems.append(f"{c.id}: {rel} unknown claim {target!r}")
            if not c.support.strip():
                problems.append(f"{c.id}: empty support text")
        if problems:
            raise ValidationError(problems)


def _person(d: dict) -> Person:
    return Person(
        id=d["id"],
        name=d["name"],
        org=d["org"],
        role=d.get("role", ""),
        capabilities=tuple(d.get("capabilities", ())),
        capability_basis=d.get("capability_basis", ""),
    )


def _source(d: dict) -> Source:
    return Source(
        id=d["id"],
        file=d.get("file"),
        type=d["type"],
        author=d.get("author", "unknown"),
        logical_time=d.get("logical_time", "unknown"),
        locator_model=d.get("locator_model", "unknown"),
        limitations=tuple(d.get("limitations", ())),
        present=d.get("present", True),
        revision=d.get("revision", 0),
    )


def _claim(d: dict) -> Claim:
    return Claim(
        id=d["id"],
        source=d["source"],
        locator=d["locator"],
        stated_by=d.get("stated_by"),
        stated_at=datetime.fromisoformat(d["stated_at"]),
        kind=d["kind"],
        subject=d["subject"],
        predicate=d["predicate"],
        value=str(d["value"]),
        support=d["support"],
        cites_basis=d.get("cites_basis"),
        supersedes=d.get("supersedes"),
        refutes=d.get("refutes"),
        revision=d.get("revision", 0),
    )


# --- revisions on disk ----------------------------------------------------
#
# Each revision is a directory holding a complete ledger: data/v1, data/v2, …
# A new revision is built from the *selected* revision plus what was added, and
# takes the next free number — so adding evidence while looking at v1 produces
# v3 when v2 exists, containing v1 + new rather than v2 + new.

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"


def revision_numbers(root: str | Path = DATA_ROOT) -> list[int]:
    return sorted(
        int(p.name[1:])
        for p in Path(root).glob("v*")
        if p.is_dir() and p.name[1:].isdigit()
    )


def latest_revision(root: str | Path = DATA_ROOT) -> int:
    revisions = revision_numbers(root)
    if not revisions:
        raise ValueError(f"no revision directories under {root}")
    return revisions[-1]


def revision_dir(root: str | Path, n: int) -> Path:
    return Path(root) / f"v{n}"


def load_revision(root: str | Path, n: int) -> Ledger:
    if n not in revision_numbers(root):
        raise ValueError(f"unknown revision {n}; have {revision_numbers(root)}")
    return load_ledger(revision_dir(root, n))


def _content_key(claim: Claim) -> tuple[str, ...]:
    """What makes two claims the same evidence even under different ids.

    The agent re-reads the packet on every run and does not reproduce ids, so
    identity alone would let a second run duplicate the whole ledger.
    """
    return (claim.source, claim.locator, claim.subject, claim.predicate, claim.value)


def create_revision(root: str | Path, base: int, added: Ledger) -> int:
    """Write base + added as the next free revision. Returns its number.

    Nothing is written unless the merged ledger validates, so a bad extraction
    leaves the existing revisions untouched.
    """
    root = Path(root)
    ledger = load_revision(root, base)
    n = latest_revision(root) + 1

    ledger.people.update({k: v for k, v in added.people.items() if k not in ledger.people})
    for sid, source in added.sources.items():
        if sid not in ledger.sources:
            ledger.sources[sid] = replace(source, revision=n)

    seen = {_content_key(c) for c in ledger.claims.values()}
    for cid, claim in sorted(added.claims.items()):
        if cid in ledger.claims or _content_key(claim) in seen:
            continue
        ledger.claims[cid] = replace(claim, revision=n)
        seen.add(_content_key(claim))

    ledger.validate()
    _write(ledger, revision_dir(root, n))
    return n


def _write(ledger: Ledger, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "people.json": {"people": [asdict(p) for _, p in sorted(ledger.people.items())]},
        "sources.json": {"sources": [asdict(s) for _, s in sorted(ledger.sources.items())]},
        "claims.json": {
            "claims": [
                {
                    **asdict(c),
                    "stated_at": c.stated_at.isoformat(),
                }
                for _, c in sorted(ledger.claims.items())
            ]
        },
    }
    for name, data in payload.items():
        (directory / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def load_ledger(data_dir: str | Path | None = None) -> Ledger:
    """A ledger directory. With no argument, the latest revision."""
    d = Path(data_dir) if data_dir is not None else revision_dir(
        DATA_ROOT, latest_revision(DATA_ROOT)
    )
    ledger = Ledger()
    for p in _person_list(d / "people.json"):
        ledger.people[p.id] = p
    for s in [_source(x) for x in _read(d / "sources.json", "sources")]:
        ledger.sources[s.id] = s
    for c in [_claim(x) for x in _read(d / "claims.json", "claims")]:
        ledger.claims[c.id] = c
    ledger.validate()
    return ledger


def load_fixture(path: str | Path) -> Ledger:
    """A single JSON file holding a new source and its claims."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    ledger = Ledger()
    for s in [_source(x) for x in raw.get("sources", [])]:
        ledger.sources[s.id] = s
    for c in [_claim(x) for x in raw.get("claims", [])]:
        ledger.claims[c.id] = c
    return ledger


def _person_list(path: Path) -> list[Person]:
    return [_person(x) for x in _read(path, "people")]


def _read(path: Path, key: str) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))[key]
