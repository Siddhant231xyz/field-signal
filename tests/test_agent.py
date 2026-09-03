"""The agent bridge, with the extractor stubbed.

Docker and a model are not exercised here — `examples/tests` covers the agent
itself. What matters at this seam is that whatever it returns lands in a new
revision, keeps its uploads readable, and never edits an existing revision.
"""

import json
import shutil

import pytest

from field_signal import agent
from field_signal.model import load_revision, revision_numbers


@pytest.fixture
def root(tmp_path, monkeypatch):
    # Only v1: a test must not depend on how many revisions data/ happens to
    # hold, or a real agent run on the developer's machine breaks the suite.
    shutil.copytree("data/v1", tmp_path / "data" / "v1")
    monkeypatch.setattr(agent, "UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(agent, "REPO", tmp_path)
    return tmp_path / "data"


@pytest.fixture
def uploads(tmp_path):
    d = tmp_path / "incoming"
    (d / "nested").mkdir(parents=True)
    (d / "site-note.txt").write_text("Omar confirmed 24 inches clear on 15 Sep.")
    (d / "nested" / "photo.png").write_bytes(b"\x89PNG\r\n")
    return d


def fake_extractor(ledger_json):
    """Stands in for the container: writes the three files it would produce."""

    def run(inputs, output):
        assert sorted(p.name for p in inputs.iterdir())  # uploads were staged
        for name, payload in ledger_json.items():
            (output / name).write_text(json.dumps(payload))

    return run


LEDGER = {
    "people.json": {
        "people": [
            {"id": "omar", "name": "Omar Ellis", "org": "Sentinel Fire",
             "role": "Fire-protection foreman", "capabilities": ["clearance_confirmation"],
             "capability_basis": "S-00"}
        ]
    },
    "sources.json": {
        "sources": [
            {"id": "S-90", "file": "packet/site-note.txt", "type": "field note",
             "author": "Omar Ellis", "logical_time": "2026-09-15", "locator_model": "line",
             "limitations": [], "present": True, "revision": 0}
        ]
    },
    "claims.json": {
        "claims": [
            {"id": "CL-S90-01", "source": "S-90", "locator": "line 1", "stated_by": "omar",
             "stated_at": "2026-09-15T09:00:00", "kind": "assertion",
             "subject": "clearance_north_of_panel", "predicate": "as_built_verified",
             "value": "verified", "support": "Omar confirmed 24 inches clear on 15 Sep."}
        ]
    },
}


def test_upload_becomes_a_new_revision(root, uploads):
    n, stored = agent.ingest(
        [uploads], root=root, base=1, runner=fake_extractor(LEDGER)
    )
    assert n == 2
    assert revision_numbers(root) == [1, 2]
    assert "CL-S90-01" in load_revision(root, 2).claims
    assert "CL-S90-01" not in load_revision(root, 1).claims  # v1 is untouched


def test_uploads_are_kept_and_the_source_points_at_them(root, uploads):
    """Otherwise /verify could never check a claim the agent extracted."""
    n, stored = agent.ingest([uploads], root=root, base=1, runner=fake_extractor(LEDGER))
    names = {p.name for p in stored}
    assert names == {"site-note.txt", "photo.png"}

    source = load_revision(root, n).sources["S-90"]
    assert source.file == "uploads/v2/site-note.txt"
    assert (agent.REPO / source.file).read_text().startswith("Omar confirmed")


def test_files_of_any_type_are_staged_flat(tmp_path, uploads):
    staged = agent.stage([uploads], tmp_path / "staged")
    assert {p.name for p in staged} == {"site-note.txt", "photo.png"}


def test_colliding_basenames_are_both_kept(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    (a / "notes.txt").write_text("one")
    (b / "notes.txt").write_text("two")
    staged = agent.stage([a, b], tmp_path / "staged")
    assert len(staged) == 2
    assert {p.read_text() for p in staged} == {"one", "two"}


def test_branching_from_an_older_revision(root, uploads):
    agent.ingest([uploads], root=root, base=1, runner=fake_extractor(LEDGER))  # v2
    second = json.loads(json.dumps(LEDGER))
    second["sources.json"]["sources"][0]["id"] = "S-91"
    second["claims.json"]["claims"][0].update(
        {"id": "CL-S91-01", "source": "S-91", "locator": "line 2"}
    )
    n, _ = agent.ingest([uploads], root=root, base=1, runner=fake_extractor(second))
    assert n == 3
    v3 = load_revision(root, 3)
    assert "CL-S91-01" in v3.claims
    assert "CL-S90-01" not in v3.claims  # branched off v1, not v2


def test_selected_base_is_given_to_a_context_aware_runner(root, uploads):
    seen = {}

    def context_runner(inputs, output, *, context):
        seen["people"] = json.loads((context / "people.json").read_text())
        seen["ontology"] = json.loads((context / "ontology.json").read_text())
        fake_extractor(LEDGER)(inputs, output)

    agent.ingest([uploads], root=root, base=1, runner=context_runner)

    assert seen["people"] == json.loads((root / "v1" / "people.json").read_text())
    assert seen["ontology"]["version"] == 1
    assert "field_review/outcome" in seen["ontology"]["queues"]


def test_delta_can_reference_a_person_from_the_selected_base(root, uploads):
    delta = json.loads(json.dumps(LEDGER))
    delta["people.json"]["people"] = []

    n, _ = agent.ingest(
        [uploads], root=root, base=1, runner=fake_extractor(delta)
    )

    assert load_revision(root, n).claims["CL-S90-01"].stated_by == "omar"


def test_an_empty_upload_is_refused(root, tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(agent.AgentError, match="no files"):
        agent.ingest([tmp_path / "empty"], root=root, base=1, runner=fake_extractor(LEDGER))


def test_a_failing_extractor_leaves_the_revisions_alone(root, uploads):
    def boom(inputs, output):
        raise agent.AgentError("docker is not running")

    with pytest.raises(agent.AgentError, match="docker"):
        agent.ingest([uploads], root=root, base=1, runner=boom)
    assert revision_numbers(root) == [1]


def test_an_invalid_extraction_leaves_the_revisions_alone(root, uploads):
    broken = json.loads(json.dumps(LEDGER))
    broken["claims.json"]["claims"][0]["stated_by"] = "nobody"
    with pytest.raises(Exception):
        agent.ingest([uploads], root=root, base=1, runner=fake_extractor(broken))
    assert revision_numbers(root) == [1]
    assert not (agent.UPLOADS / "v2").exists()


# --- progress reporting ---------------------------------------------------
#
# The bug this covers: a run is started, the user navigates away, and there is
# no way to tell whether anything is still happening. Progress has to live
# outside the page that started it.


def progress_runner(ledger_json, lines):
    """A runner that emits the lines the real container run prints."""

    def run(inputs, output, on_line=None):
        for line in lines:
            if on_line:
                on_line(line)
        for name, payload in ledger_json.items():
            (output / name).write_text(json.dumps(payload))

    return run


REAL_LINES = [
    "Building field-signal-ingestor-example:latest ...",
    "Starting containerized agent ...",
    "shell call 1",
    "shell call 2",
    "shell call 17",
    "Validated output promoted to /out",
]


def test_progress_reports_each_phase_in_order(root, uploads):
    seen = []
    agent.ingest(
        [uploads],
        root=root,
        base=1,
        runner=progress_runner(LEDGER, REAL_LINES),
        on_progress=lambda p: seen.append(dict(p)),
    )
    phases = [p["phase"] for p in seen]
    assert phases[0] == "staging"
    assert "building" in phases
    assert "extracting" in phases
    assert "writing" in phases
    assert phases[-1] == "done"


def test_progress_counts_shell_calls(root, uploads):
    last = {}
    agent.ingest(
        [uploads],
        root=root,
        base=1,
        runner=progress_runner(LEDGER, REAL_LINES),
        on_progress=lambda p: last.update(p),
    )
    assert last["shell_calls"] == 17  # the highest seen, not the count of lines
    assert last["revision"] == 2
    assert last["files"] == 2


def test_progress_records_a_failure_rather_than_going_quiet(root, uploads):
    last = {}

    def boom(inputs, output, on_line=None):
        if on_line:
            on_line("Building the image ...")
        raise agent.AgentError("docker is not running")

    with pytest.raises(agent.AgentError):
        agent.ingest(
            [uploads], root=root, base=1, runner=boom, on_progress=lambda p: last.update(p)
        )
    assert last["phase"] == "failed"
    assert "docker" in last["error"]


def test_a_runner_that_ignores_on_line_still_works(root, uploads):
    """The default runner signature must stay optional for existing callers."""
    n, _ = agent.ingest([uploads], root=root, base=1, runner=fake_extractor(LEDGER))
    assert n == 2
