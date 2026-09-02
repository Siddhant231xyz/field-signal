"""JSON API over the derivation engine, plus a stdlib static server.

No conclusion is reached here. Everything in the payload was derived by
`graph.py`; this module only makes it serialisable and adds the node/link view
the 3D graph draws. The rendered `display` string comes from `render.py`, so
the browser and the terminal cannot drift apart on what a status looks like.
"""

from __future__ import annotations

import json
import mimetypes
import re
import tempfile
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import render
from .agent import AgentError, ingest
from .diff import diff
from .graph import Conclusions, conclusions
from .model import (
    DATA_ROOT,
    Ledger,
    ValidationError,
    create_revision,
    load_fixture,
    load_revision,
    revision_numbers,
)
from .verify import verify

REPO = Path(__file__).resolve().parent.parent
MAX_UPLOAD = 200_000_000  # ponytail: whole body in memory; stream if this grows


def parse_multipart(body: bytes, content_type: str) -> list[tuple[str, bytes]]:
    """Files out of a multipart/form-data body. Returns [(filename, bytes)].

    `email` and `cgi.FieldStorage` both mangle binary parts, so the boundary is
    split directly. Parts without a filename are ignored.
    """
    match = re.search(r'boundary="?([^";]+)"?', content_type)
    if not match:
        raise ValueError("multipart upload has no boundary")
    sep = b"--" + match.group(1).encode()
    files: list[tuple[str, bytes]] = []
    for part in body.split(sep)[1:-1]:
        head, _, data = part.partition(b"\r\n\r\n")
        name = re.search(rb'filename="([^"]*)"', head)
        if not name or not name.group(1):
            continue
        files.append((name.group(1).decode("utf-8", "replace"), data[:-2]))
    return files


# --- serialisation --------------------------------------------------------


def _claim(ledger: Ledger, claim) -> dict:
    return {
        "id": claim.id,
        "source": claim.source,
        "locator": claim.locator,
        "citation": f"{claim.source} {claim.locator}",
        "author": ledger.author_of(claim),
        "author_id": claim.stated_by,
        "stated_at": claim.stated_at.isoformat(),
        "kind": claim.kind,
        "subject": claim.subject,
        "predicate": claim.predicate,
        "value": claim.value,
        "support": claim.support,
        "cites_basis": claim.cites_basis,
        "supersedes": claim.supersedes,
        "refutes": claim.refutes,
        "revision": claim.revision,
        "gating_allowed": claim.gating_allowed(),
    }


def _ledger(ledger: Ledger) -> dict:
    return {
        "people": [
            {
                "id": p.id,
                "name": p.name,
                "org": p.org,
                "role": p.role,
                "capabilities": list(p.capabilities),
                "capability_basis": p.capability_basis,
            }
            for _, p in sorted(ledger.people.items())
        ],
        "sources": [
            {
                "id": s.id,
                "file": s.file,
                "type": s.type,
                "author": s.author,
                "logical_time": s.logical_time,
                "locator_model": s.locator_model,
                "limitations": list(s.limitations),
                "present": s.present,
                "revision": s.revision,
            }
            for _, s in sorted(ledger.sources.items())
        ],
        "claims": [_claim(ledger, c) for c in sorted(ledger.claims.values(), key=lambda c: c.id)],
    }


def _graph(c: Conclusions, ledger: Ledger) -> dict:
    """Nodes and links for the 3D view — the same edges the CLI reasons over."""
    nodes: list[dict] = [
        {
            "id": f"decision:{c.decision.id}",
            "type": "decision",
            "label": c.decision.label,
            "status": c.decision.recommendation.lower(),
            "basis": c.decision.basis.value,
            "detail": c.decision.question,
        }
    ]
    links: list[dict] = []
    cited: set[str] = set()

    for cid, cond in sorted(c.conditions.items()):
        nodes.append(
            {
                "id": f"condition:{cid}",
                "type": "condition",
                "label": cond.label,
                "status": cond.status.value,
                "basis": cond.basis.value,
                "detail": cond.question,
            }
        )
        if cond.gates:
            links.append(
                {
                    "source": f"condition:{cid}",
                    "target": f"decision:{c.decision.id}",
                    "kind": "gates",
                }
            )
        for dep in cond.depends_on:
            if dep in c.conditions:
                links.append(
                    {"source": f"condition:{cid}", "target": f"condition:{dep}", "kind": "depends_on"}
                )
        for claim_id in cond.support:
            cited.add(claim_id)
            links.append(
                {"source": f"claim:{claim_id}", "target": f"condition:{cid}", "kind": "supports"}
            )
        for claim_id in cond.notes:
            cited.add(claim_id)
            links.append(
                {"source": f"claim:{claim_id}", "target": f"condition:{cid}", "kind": "noted"}
            )

    for e in c.exposures:
        nodes.append(
            {
                "id": f"exposure:{e.id}",
                "type": "exposure",
                "label": e.label,
                "status": "exposed",
                "basis": "settled",
                "detail": e.detail,
            }
        )
        links.append(
            {"source": f"exposure:{e.id}", "target": f"decision:{c.decision.id}", "kind": "exposes"}
        )
        for claim_id in e.support:
            cited.add(claim_id)
            links.append(
                {"source": f"claim:{claim_id}", "target": f"exposure:{e.id}", "kind": "supports_exposure"}
            )

    superseded = {cid for q in c.queues.values() for cid in q.superseded}
    for claim_id in sorted(cited):
        claim = ledger.claims[claim_id]
        nodes.append(
            {
                "id": f"claim:{claim_id}",
                "type": "claim",
                "label": claim_id,
                "kind": claim.kind,
                "status": "superseded" if claim_id in superseded else claim.kind,
                "basis": "settled",
                "detail": claim.support,
                "citation": f"{claim.source} {claim.locator}",
                "gating_allowed": claim.gating_allowed(),
            }
        )
        links.append({"source": f"source:{claim.source}", "target": f"claim:{claim_id}", "kind": "from_source"})
        if claim.stated_by:
            links.append(
                {"source": f"person:{claim.stated_by}", "target": f"claim:{claim_id}", "kind": "stated_by"}
            )
        if claim.cites_basis:
            links.append(
                {"source": f"claim:{claim_id}", "target": f"source:{claim.cites_basis}", "kind": "cites_basis"}
            )
        if claim.supersedes in cited:
            links.append(
                {"source": f"claim:{claim_id}", "target": f"claim:{claim.supersedes}", "kind": "supersedes"}
            )
        if claim.refutes in cited:
            links.append(
                {"source": f"claim:{claim_id}", "target": f"claim:{claim.refutes}", "kind": "refutes"}
            )

    used_sources = {l["source"].removeprefix("source:") for l in links if l["kind"] == "from_source"}
    used_sources |= {l["target"].removeprefix("source:") for l in links if l["kind"] == "cites_basis"}
    for sid in sorted(used_sources):
        s = ledger.sources[sid]
        nodes.append(
            {
                "id": f"source:{sid}",
                "type": "source",
                "label": sid,
                "status": "present" if s.present else "absent",
                "basis": "settled",
                "detail": s.type,
                "present": s.present,
            }
        )

    used_people = {l["source"].removeprefix("person:") for l in links if l["kind"] == "stated_by"}
    for pid in sorted(used_people):
        p = ledger.people[pid]
        nodes.append(
            {
                "id": f"person:{pid}",
                "type": "person",
                "label": p.name,
                "status": "authorised" if "authorise_added_cost" in p.capabilities else "advisory",
                "basis": "settled",
                "detail": f"{p.role} · {p.org}",
            }
        )

    known = {n["id"] for n in nodes}
    links = [l for l in links if l["source"] in known and l["target"] in known]
    return {"nodes": nodes, "links": links}


def _conclusions(c: Conclusions, ledger: Ledger) -> dict:
    return {
        "revision": c.revision,
        "decision": {
            "id": c.decision.id,
            "label": c.decision.label,
            "question": c.decision.question,
            "recommendation": c.decision.recommendation,
            "basis": c.decision.basis.value,
            "blocking": list(c.decision.blocking),
            "contested_by": list(c.decision.contested_by),
        },
        "conditions": [
            {
                "id": cid,
                "label": cond.label,
                "question": cond.question,
                "status": cond.status.value,
                "basis": cond.basis.value,
                "display": render.status_text(cond.status, cond.basis).plain,
                "reason": cond.reason,
                "support": list(cond.support),
                "notes": list(cond.notes),
                "depends_on": list(cond.depends_on),
                "contested_by": list(cond.contested_by),
                "gates": cond.gates,
            }
            for cid, cond in sorted(c.conditions.items())
        ],
        "queues": [
            {
                "subject": q.subject,
                "predicate": q.predicate,
                "key": f"{q.subject}/{q.predicate}",
                "mode": q.mode.value,
                "mode_label": render.mode_text(q).plain,
                "head": q.head.id,
                "claims": [cl.id for cl in q.claims],
                "superseded": sorted(q.superseded),
            }
            for _, q in sorted(c.queues.items())
        ],
        "exposures": [
            {"id": e.id, "label": e.label, "detail": e.detail, "support": list(e.support)}
            for e in c.exposures
        ],
        "rebuttals": {k: list(v) for k, v in c.rebuttals.items()},
        "absent_bases": {k: list(v) for k, v in c.absent_bases.items()},
        "graph": _graph(c, ledger),
    }


def payload(ledgers: dict[int, Ledger], selected: int) -> dict:
    """Every revision, plus the ledger of the selected one.

    The ledger is per-revision on purpose: selecting v1 has to show v1's claims
    everywhere, not the newest set filtered down.
    """
    return {
        "current": selected,
        "revisions": {
            str(n): _conclusions(conclusions(l), l) for n, l in sorted(ledgers.items())
        },
        "ledger": _ledger(ledgers[selected]),
        "ledgers": {str(n): _ledger(l) for n, l in sorted(ledgers.items())},
    }


# --- application state ----------------------------------------------------


@dataclass
class Api:
    """Every revision on disk, and the operations the CLI exposes."""

    data_dir: Path = DATA_ROOT

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.selected = 0
        self.reload()

    def reload(self) -> None:
        self.ledgers = {
            n: load_revision(self.data_dir, n) for n in revision_numbers(self.data_dir)
        }
        self.views = {n: conclusions(l) for n, l in self.ledgers.items()}
        if self.selected not in self.views:
            self.selected = max(self.views)

    @property
    def ledger(self) -> Ledger:
        return self.ledgers[self.selected]

    def state(self) -> dict:
        return payload(self.ledgers, self.selected)

    def select(self, n: int) -> dict:
        if n not in self.views:
            raise ValueError(f"revisions available: {sorted(self.views)}")
        self.selected = n
        return self.state()

    def load(self, raw_path: str) -> dict:
        """A ledger fixture becomes a new revision off the selected one."""
        path = (REPO / raw_path).resolve()
        if not path.is_relative_to(REPO):
            raise ValueError(f"refusing to read a path outside the repository: {raw_path}")
        if not path.exists():
            raise ValueError(f"no such file: {raw_path}")
        return self._new_revision(
            lambda: create_revision(self.data_dir, self.selected, load_fixture(path))
        )

    def ingest(self, paths: list[Path]) -> dict:
        """Uploads become a new revision off the selected one."""
        return self._new_revision(
            lambda: ingest(paths, root=self.data_dir, base=self.selected)[0]
        )

    def _new_revision(self, make) -> dict:
        base = self.selected
        n = make()
        self.reload()
        self.selected = n
        state = self.state()
        state["created"] = {"revision": n, "base": base}
        return state

    def diff(self, a: int, b: int) -> list[dict]:
        if a not in self.views or b not in self.views:
            raise ValueError(f"revisions available: {sorted(self.views)}")
        return [
            {"kind": m.kind, "id": m.id, "before": m.before, "after": m.after, "note": m.note}
            for m in diff(self.views[a], self.views[b])
        ]

    def verify(self) -> list[dict]:
        return [
            {"claim": c, "source": s, "result": r, "detail": d}
            for c, s, r, d in verify(self.ledger, REPO)
        ]

    def fixtures(self) -> list[str]:
        return sorted(str(p.relative_to(REPO)) for p in (REPO / "demo").glob("*.json"))


# --- server ---------------------------------------------------------------


def make_handler(api: Api, static_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:  # quiet by default
            pass

        def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status: int = 200) -> None:
            self._send(json.dumps(data).encode(), "application/json", status)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            try:
                if url.path == "/api/state":
                    return self._json(api.state())
                if url.path == "/api/verify":
                    return self._json(api.verify())
                if url.path == "/api/fixtures":
                    return self._json(api.fixtures())
                if url.path == "/api/diff":
                    a = int(query.get("a", ["0"])[0])
                    b = int(query.get("b", [str(api.ledger.max_revision())])[0])
                    return self._json(api.diff(a, b))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            return self._static(url.path)

        def do_POST(self) -> None:
            url = urlparse(self.path)
            length = int(self.headers.get("Content-Length", 0))
            try:
                if url.path == "/api/agent":
                    return self._json(self._ingest(length))
                body = json.loads(self.rfile.read(length) or b"{}")
                if url.path == "/api/load":
                    return self._json(api.load(body["path"]))
                if url.path == "/api/select":
                    return self._json(api.select(int(body["revision"])))
            except (AgentError, ValidationError, ValueError, KeyError, OSError) as exc:
                return self._json({"error": str(exc)}, 400)
            return self._json({"error": "not found"}, 404)

        def _ingest(self, length: int) -> dict:
            """Multipart upload → a new revision. Any number of files, any type."""
            if length > MAX_UPLOAD:
                raise ValueError(f"upload exceeds {MAX_UPLOAD // 1_000_000} MB")
            ctype = self.headers.get("Content-Type", "")
            if not ctype.startswith("multipart/form-data"):
                raise ValueError("expected a multipart/form-data upload")
            files = parse_multipart(self.rfile.read(length), ctype)
            if not files:
                raise ValueError("no files in the upload")
            with tempfile.TemporaryDirectory(prefix="fs-upload-") as tmp:
                staged = []
                for name, data in files:
                    # Basename only: an uploaded name never chooses a path.
                    target = Path(tmp) / Path(name).name
                    target.write_bytes(data)
                    staged.append(target)
                return api.ingest(staged)

        def _static(self, path: str) -> None:
            if not static_dir.exists():
                return self._json(
                    {"error": "no built frontend — run: npm --prefix web run build"}, 404
                )
            target = (static_dir / path.lstrip("/")).resolve()
            if not target.is_relative_to(static_dir) or not target.is_file():
                target = static_dir / "index.html"  # SPA fallback
            if not target.is_file():
                return self._json({"error": "not found"}, 404)
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(target.read_bytes(), ctype)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    api = Api()
    static_dir = REPO / "web" / "dist"
    server = ThreadingHTTPServer((host, port), make_handler(api, static_dir))
    built = "serving web/dist" if static_dir.exists() else "API only — no built frontend"
    print(f"Field Signal · http://{host}:{port} · {built}")
    print(f"revision {api.ledger.max_revision()} · {len(api.ledger.claims)} claims")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    serve()
