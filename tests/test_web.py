"""The web layer must not become a second place where conclusions are made.

It serialises what `graph.py` already derived. These tests exist to catch the
frontend being handed something the CLI would never print — a status without
its basis, a claim without its citation, a gating edge from an image.
"""

import json
import shutil

import pytest

from field_signal.model import load_ledger
from field_signal.web import Api, payload


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    """A copy, always. A test must never write a revision into the repo."""
    root = tmp_path_factory.mktemp("repo") / "data"
    shutil.copytree("data", root)
    return root


@pytest.fixture(scope="module")
def api(data):
    return Api(data_dir=data)


@pytest.fixture(scope="module")
def state(api):
    return api.state()


def test_payload_is_json_serialisable(state):
    json.dumps(state)  # raises on a stray dataclass, Enum or datetime


def test_every_condition_carries_status_and_basis_together(state):
    for cond in state["revisions"]["1"]["conditions"]:
        assert cond["status"] in ("met", "unmet", "unknown")
        assert cond["basis"] in ("settled", "contested")
        assert cond["reason"]
        # the rendered label the CLI shows, so the two cannot drift apart
        assert cond["display"].startswith(("✓", "✗", "?"))
        if cond["basis"] == "contested":
            assert "premise contested" in cond["display"]


def test_claims_arrive_with_author_and_citation_resolved(state):
    claims = {c["id"]: c for c in state["ledger"]["claims"]}
    omar = claims["CL-S01-05"]
    assert omar["author"] == "Omar Ellis"
    assert omar["citation"] == "S-01 08:05:52"
    assert omar["support"] == "I did not lay out the final head."
    assert omar["refutes"] == "CL-S01-03"


def test_non_gating_claims_are_flagged_for_the_frontend(state):
    claims = {c["id"]: c for c in state["ledger"]["claims"]}
    assert claims["CL-P02-01"]["gating_allowed"] is False
    assert claims["CL-S01-26"]["gating_allowed"] is False
    assert claims["CL-S01-05"]["gating_allowed"] is True


def test_graph_links_a_claim_to_the_condition_it_gates(state):
    graph = state["revisions"]["1"]["graph"]
    ids = {n["id"] for n in graph["nodes"]}
    assert "decision:ca_118_direction" in ids
    assert "condition:cost_authorised" in ids
    assert "person:maya" in ids

    supports = {
        (l["source"], l["target"]) for l in graph["links"] if l["kind"] == "supports"
    }
    # CL-S02-10 is the head of the quoted_amount queue — the claim the rule read
    assert ("claim:CL-S02-10", "condition:cost_authorised") in supports
    gates = {(l["source"], l["target"]) for l in graph["links"] if l["kind"] == "gates"}
    assert ("condition:cost_authorised", "decision:ca_118_direction") in gates


def test_no_image_observation_ever_appears_as_a_gating_link(state):
    """The CLI's central constraint must survive the trip to the browser."""
    graph = state["revisions"]["1"]["graph"]
    claims = {c["id"]: c for c in state["ledger"]["claims"]}
    for link in graph["links"]:
        if link["kind"] != "supports":
            continue
        claim_id = link["source"].removeprefix("claim:")
        assert claims[claim_id]["gating_allowed"], f"{claim_id} must not gate"


def test_absent_sources_are_marked_for_the_frontend(state):
    sources = {s["id"]: s for s in state["ledger"]["sources"]}
    assert sources["S-ABS-RECOVERY"]["present"] is False
    assert sources["S-04"]["present"] is True
    assert state["revisions"]["1"]["absent_bases"]["S-ABS-RECOVERY"] == [
        "CL-S01-21",
        "CL-S02-15",
    ]


def test_loading_a_fixture_adds_a_revision_and_a_diff(api):
    state = api.load("demo/rfi-04.json")
    assert set(state["revisions"]) == {"1", "2"}
    assert state["current"] == 2  # the new revision becomes the selected one
    assert state["created"] == {"revision": 2, "base": 1}
    kinds = {m["kind"] for m in api.diff(1, 2)}
    assert "unknown_opened" in kinds
    assert "superseded" in kinds
    assert state["revisions"]["2"]["decision"]["recommendation"] == "HOLD"


def test_selecting_a_revision_swaps_the_whole_ledger(api):
    """Choosing v1 must show v1's claims everywhere, not a filtered v2."""
    assert api.state()["current"] == 2
    v1 = api.select(1)
    assert v1["current"] == 1
    assert "CL-S05-01" not in {c["id"] for c in v1["ledger"]["claims"]}
    v2 = api.select(2)
    assert "CL-S05-01" in {c["id"] for c in v2["ledger"]["claims"]}


def test_loading_the_same_fixture_twice_adds_nothing(api):
    """Dedup, so a repeated load is a no-op rather than a duplicated ledger."""
    before = len(api.state()["ledger"]["claims"])
    after = api.load("demo/rfi-04.json")
    assert len(after["ledger"]["claims"]) == before


def test_load_rejects_a_path_outside_the_repository(api):
    with pytest.raises(ValueError, match="outside"):
        api.load("/etc/passwd")


def test_verify_reports_every_claim(api):
    rows = api.verify()
    assert len(rows) == len(api.ledger.claims)
    assert all(r["result"] != "NOT FOUND" for r in rows)


def test_payload_helper_matches_the_api(api):
    built = payload(api.ledgers, 1)
    assert built["revisions"]["1"]["decision"]["recommendation"] == "HOLD"
    assert built["current"] == 1


def test_static_handler_serves_the_built_frontend(tmp_path, data):
    """A built frontend is served; an unknown path falls back to the SPA."""
    from field_signal.web import make_handler

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<div id=app></div>")
    (dist / "app.js").write_text("console.log(1)")

    sent = {}

    class Fake(make_handler(Api(data_dir=data), dist)):
        def __init__(self):  # bypass BaseHTTPRequestHandler's socket setup
            pass

        def send_response(self, status):
            sent["status"] = status

        def send_header(self, k, v):
            sent.setdefault("headers", {})[k] = v

        def end_headers(self):
            pass

        @property
        def wfile(self):
            return type("W", (), {"write": lambda _s, b: sent.update(body=b)})()

    h = Fake()
    h._static("/app.js")
    assert sent["headers"]["Content-Type"] == "text/javascript"

    h._static("/brief")  # a client route, not a file
    assert b"id=app" in sent["body"]

    h._static("/../../etc/passwd")  # traversal falls back, never escapes
    assert b"id=app" in sent["body"]
