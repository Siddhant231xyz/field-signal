"""JSON API over the derivation engine, plus a stdlib static server.

No conclusion is reached here. Everything in the payload was derived by
`graph.py`; this module only makes it serialisable and adds the node/link view
the 3D graph draws. The rendered `display` string comes from `render.py`, so
the browser and the terminal cannot drift apart on what a status looks like.
"""

from __future__ import annotations

import errno
import json
import mimetypes
import queue
import re
import sys
import tempfile
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import render
from .agent import AgentError, ingest
from .chat import ChatError, answer_question
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
MAX_CHAT_BODY = 100_000


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
    """The whole revision as nodes and links.

    Everything in the ledger appears: every claim, every person, every source
    including the ones cited but never supplied. An earlier version carried
    only the claims a rule happened to read — 49 of 115 — so the picture
    answered "what feeds the decision" rather than "what is in this revision".

    Queues with more than one claim become nodes too, because that is where
    agreement, supersession and conflict actually live. A queue of one adds a
    node and says nothing, so it is left out.
    """
    nodes: list[dict] = []
    links: list[dict] = []

    def node(**kw):
        nodes.append(kw)

    def link(source, target, kind):
        links.append({"source": source, "target": target, "kind": kind})

    decision_id = f"decision:{c.decision.id}"
    node(
        id=decision_id,
        type="decision",
        label=c.decision.label,
        status=c.decision.recommendation.lower(),
        basis=c.decision.basis.value,
        detail=c.decision.question,
        blocking=list(c.decision.blocking),
    )

    # Which claims any rule actually read — the spine, still identifiable.
    feeding = {cid for cond in c.conditions.values() for cid in cond.support}
    feeding |= {cid for e in c.exposures for cid in e.support}

    for cid, cond in sorted(c.conditions.items()):
        node(
            id=f"condition:{cid}",
            type="condition",
            label=cond.label,
            status=cond.status.value,
            basis=cond.basis.value,
            detail=cond.reason,
            question=cond.question,
        )
        if cond.gates:
            link(f"condition:{cid}", decision_id, "gates")
        for dep in cond.depends_on:
            if dep in c.conditions:
                link(f"condition:{cid}", f"condition:{dep}", "depends_on")
        for claim_id in cond.support:
            link(f"claim:{claim_id}", f"condition:{cid}", "supports")
        for claim_id in cond.notes:
            link(f"claim:{claim_id}", f"condition:{cid}", "noted")

    for e in c.exposures:
        node(
            id=f"exposure:{e.id}",
            type="exposure",
            label=e.label,
            status="exposed",
            basis="settled",
            detail=e.detail,
        )
        link(f"exposure:{e.id}", decision_id, "exposes")
        for claim_id in e.support:
            link(f"claim:{claim_id}", f"exposure:{e.id}", "supports_exposure")

    # Queues carrying more than one claim: agreement, supersession, conflict.
    for (subject, predicate), q in sorted(c.queues.items()):
        if len(q.claims) < 2:
            continue
        qid = f"queue:{subject}/{predicate}"
        node(
            id=qid,
            type="queue",
            label=f"{subject} · {predicate}",
            status=q.mode.value,
            basis="contested" if q.mode.value == "assumed" else "settled",
            detail=(
                "Resolved on recency alone — nothing in the packet settles it."
                if q.mode.value == "assumed"
                else f"{len(q.claims)} claims about the same thing ({q.mode.value})."
            ),
            head=q.head.id,
        )
        for claim in q.claims:
            link(f"claim:{claim.id}", qid, "in_queue")

    superseded = {cid for q in c.queues.values() for cid in q.superseded}
    for claim in ledger.claim_list():
        node(
            id=f"claim:{claim.id}",
            type="claim",
            label=claim.id,
            kind=claim.kind,
            status="superseded" if claim.id in superseded else claim.kind,
            basis="settled",
            detail=claim.support,
            citation=f"{claim.source} {claim.locator}",
            author=ledger.author_of(claim),
            subject=claim.subject,
            predicate=claim.predicate,
            value=claim.value,
            stated_at=claim.stated_at.isoformat(),
            gating_allowed=claim.gating_allowed(),
            feeds_a_conclusion=claim.id in feeding,
        )
        link(f"source:{claim.source}", f"claim:{claim.id}", "from_source")
        if claim.stated_by:
            link(f"person:{claim.stated_by}", f"claim:{claim.id}", "stated_by")
        if claim.cites_basis:
            link(f"claim:{claim.id}", f"source:{claim.cites_basis}", "cites_basis")
        if claim.supersedes:
            link(f"claim:{claim.id}", f"claim:{claim.supersedes}", "supersedes")
        if claim.refutes:
            link(f"claim:{claim.id}", f"claim:{claim.refutes}", "refutes")

    for sid, source in sorted(ledger.sources.items()):
        node(
            id=f"source:{sid}",
            type="source",
            label=sid,
            status="present" if source.present else "absent",
            basis="settled",
            detail=source.type
            + ("" if source.present else " — cited but never supplied"),
            present=source.present,
            author=source.author,
            limitations=list(source.limitations),
        )

    for pid, person in sorted(ledger.people.items()):
        node(
            id=f"person:{pid}",
            type="person",
            label=person.name,
            status="authorised" if "authorise_added_cost" in person.capabilities else "advisory",
            basis="settled",
            detail=f"{person.role} · {person.org}",
            capabilities=list(person.capabilities),
            # not `basis`: that means settled/contested on every other node
            capability_basis=person.capability_basis,
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
    chat_runner: object = answer_question

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.selected = 0
        # A run takes minutes and the page that started it may be gone by the
        # time it ends, so progress lives here rather than in the component.
        self._progress = {"phase": "idle", "running": False, "shell_calls": 0,
                          "files": 0, "base": None, "revision": None,
                          "error": None, "merged_people": {}}
        self.reload()

    def progress(self) -> dict:
        return dict(self._progress)

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

    def ingest(self, paths: list[Path], runner=None) -> dict:
        """Uploads become a new revision off the selected one."""
        def record(p):
            self._progress = {**p, "running": p["phase"] not in ("done", "failed")}

        kwargs = {"runner": runner} if runner else {}
        return self._new_revision(
            lambda: ingest(
                paths,
                root=self.data_dir,
                base=self.selected,
                on_progress=record,
                **kwargs,
            )[0]
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

    def chat(self, revision: int, question: str, history: list[dict]) -> dict:
        """Ask against an explicit revision, independent of mutable selection."""
        if revision not in self.ledgers:
            raise ValueError(f"revisions available: {sorted(self.ledgers)}")
        return self.chat_runner(self.ledgers, revision, question, history)

    def chat_stream(self, revision, question, history, answerer=None):
        """Yield ("delta", text) as the answer arrives, then ("done", payload).

        The whole answer still takes seconds; streaming is about the first
        token, which is what "slow" actually feels like.
        """
        if revision not in self.ledgers:
            yield "error", {"error": f"revisions available: {sorted(self.ledgers)}"}
            return

        # The answerer is synchronous and pushes deltas through a callback, so
        # it runs on its own thread and the queue carries them out as they
        # arrive. Collecting first and yielding after would buffer, not stream.
        answerer = answerer or self.chat_runner
        pipe: queue.Queue = queue.Queue()

        def work():
            try:
                pipe.put(("done", answerer(
                    self.ledgers, revision, question, history,
                    on_delta=lambda piece: pipe.put(("delta", piece)),
                )))
            except Exception as exc:  # surfaced to the client, never a dead stream
                pipe.put(("error", {"error": str(exc)}))

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        while True:
            kind, payload = pipe.get()
            yield kind, payload
            if kind in ("done", "error"):
                worker.join(timeout=1)
                return


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
                if url.path == "/api/agent/status":
                    return self._json(api.progress())
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
                if url.path == "/api/chat" and length > MAX_CHAT_BODY:
                    raise ValueError(
                        f"chat request exceeds {MAX_CHAT_BODY // 1_000} KB"
                    )
                body = json.loads(self.rfile.read(length) or b"{}")
                if url.path == "/api/load":
                    return self._json(api.load(body["path"]))
                if url.path == "/api/select":
                    return self._json(api.select(int(body["revision"])))
                if url.path == "/api/chat/stream":
                    return self._sse(body)
                if url.path == "/api/chat":
                    return self._json(
                        api.chat(
                            int(body["revision"]),
                            body["question"],
                            body.get("history", []),
                        )
                    )
            except (
                AgentError,
                ChatError,
                ValidationError,
                ValueError,
                KeyError,
                OSError,
                json.JSONDecodeError,
            ) as exc:
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

        def _sse(self, body: dict) -> None:
            """Server-sent events, so the answer appears as it is written."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                for kind, payload in api.chat_stream(
                    int(body["revision"]), body["question"], body.get("history", [])
                ):
                    data = json.dumps(
                        {"text": payload} if kind == "delta" else payload
                    )
                    self.wfile.write(f"event: {kind}\ndata: {data}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass  # the reader navigated away; nothing to clean up
            self.close_connection = True

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


def parse_port(argv: list[str], default: int = 8000) -> int:
    """--port 9100 or --port=9100."""
    for i, arg in enumerate(argv):
        if arg.startswith("--port="):
            return int(arg.split("=", 1)[1])
        if arg == "--port":
            if i + 1 >= len(argv):
                raise ValueError("--port needs a number")
            return int(argv[i + 1])
    return default


def serve(host: str = "127.0.0.1", port: int = 8000, data_dir: Path | None = None) -> None:
    api = Api(data_dir=data_dir) if data_dir else Api()
    static_dir = REPO / "web" / "dist"
    try:
        server = ThreadingHTTPServer((host, port), make_handler(api, static_dir))
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        # Leaving a server running and starting another is an ordinary
        # mistake. A stack trace for it tells you nothing you can act on.
        print(
            f"port {port} is already in use — Field Signal may still be running "
            f"in another terminal.\n"
            f"  stop it:      pkill -f 'field_signal.web'\n"
            f"  or pick one:  python -m field_signal.web --port 8001",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    built = "serving web/dist" if static_dir.exists() else "API only — no built frontend"
    print(f"Field Signal · http://{host}:{port} · {built}")
    print(f"revision {api.ledger.max_revision()} · {len(api.ledger.claims)} claims")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    serve(port=parse_port(sys.argv[1:]))
