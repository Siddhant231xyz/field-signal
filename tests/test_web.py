"""The web layer must not become a second place where conclusions are made.

It serialises what `graph.py` already derived. These tests exist to catch the
frontend being handed something the CLI would never print — a status without
its basis, a claim without its citation, a gating edge from an image.
"""

import json

import pytest

from field_signal.model import load_ledger
from field_signal.web import Api, payload


@pytest.fixture(scope="module")
def api():
    return Api()


@pytest.fixture(scope="module")
def state(api):
    return api.state()


def test_payload_is_json_serialisable(state):
    json.dumps(state)  # raises on a stray dataclass, Enum or datetime


def test_every_condition_carries_status_and_basis_together(state):
    for cond in state["revisions"]["0"]["conditions"]:
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
    graph = state["revisions"]["0"]["graph"]
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
    graph = state["revisions"]["0"]["graph"]
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
    assert state["revisions"]["0"]["absent_bases"]["S-ABS-RECOVERY"] == [
        "CL-S01-21",
        "CL-S02-15",
    ]


def test_loading_a_fixture_adds_a_revision_and_a_diff(api):
    api.load("demo/rfi-04.json")
    state = api.state()
    assert set(state["revisions"]) == {"0", "1"}
    assert state["current"] == 1
    moves = api.diff(0, 1)
    kinds = {m["kind"] for m in moves}
    assert "unknown_opened" in kinds
    assert "superseded" in kinds
    assert state["revisions"]["1"]["decision"]["recommendation"] == "HOLD"


def test_loading_the_same_fixture_twice_is_refused(api):
    with pytest.raises(ValueError, match="already"):
        api.load("demo/rfi-04.json")


def test_load_rejects_a_path_outside_the_repository(api):
    with pytest.raises(ValueError, match="outside"):
        api.load("/etc/passwd")


def test_verify_reports_every_claim(api):
    rows = api.verify()
    assert len(rows) == len(load_ledger().claims) + 5  # the fixture's own claims
    assert all(r["result"] != "NOT FOUND" for r in rows)


def test_payload_helper_matches_the_api(state):
    assert payload(load_ledger())["revisions"]["0"]["decision"]["recommendation"] == "HOLD"


def test_static_handler_serves_the_built_frontend(tmp_path):
    """A built frontend is served; an unknown path falls back to the SPA."""
    from field_signal.web import make_handler

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<div id=app></div>")
    (dist / "app.js").write_text("console.log(1)")

    sent = {}

    class Fake(make_handler(Api(), dist)):
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
