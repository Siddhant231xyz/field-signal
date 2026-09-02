"""The interface has one job: never let a conclusion look cleaner than it is.

These tests read rendered output, because that is what Maya Chen actually
sees. Colour is deliberately ignored — every state must be legible as text.
"""

import io
import re
import shutil

import pytest
from rich.console import Console

from field_signal.__main__ import App


BOX = re.compile(r"[─-╿]")


def render(app: App, *commands: str) -> str:
    """Rendered output with borders removed and whitespace collapsed.

    Rich wraps inside panels and table cells and draws a border at every line
    end, so asserting on raw output would test the column widths rather than
    the content. Truncation still fails these assertions, because Rich's
    ellipsis breaks the substring.
    """
    buffer = io.StringIO()
    app.console = Console(file=buffer, width=200, no_color=True, highlight=False)
    for command in commands:
        app.run(command)
    return " ".join(BOX.sub(" ", buffer.getvalue()).split())


@pytest.fixture
def data(tmp_path):
    """A copy, always. /load and /agent write revisions to disk."""
    shutil.copytree("data", tmp_path / "data")
    return tmp_path / "data"


@pytest.fixture
def app(data):
    return App(data_dir=data)


def test_brief_leads_with_the_recommendation_and_its_blockers(app):
    out = render(app, "/brief")
    assert "HOLD" in out
    assert "basis: contested" in out
    assert "cost_authorised" in out
    assert "$2,850.00" in out


def test_status_is_never_carried_by_colour_alone(app):
    out = render(app, "/brief")
    assert "? unknown" in out
    assert "✗ unmet" in out
    assert "premise contested" in out  # the taint is a word, not a shade


def test_the_quote_never_appears_without_its_exclusions(app):
    out = render(app, "/exposure")
    assert "$2,850.00" in out
    assert "excluded" in out
    assert "unknown and cannot be lower than the quote" in out


def test_conflicts_shows_all_three_offsets_and_no_fourth_number(app):
    out = render(app, "/conflicts")
    for value in ("about 6 in", "six or eight inches", "approximately 6–12 inches"):
        assert value in out
    assert "recency" in out


def test_unknowns_never_render_as_no(app):
    out = render(app, "/unknowns")
    assert "does not say" in out
    assert "Absence of a record is not evidence of absence." in out


def test_why_shows_the_claims_a_rule_read_and_the_ones_it_may_not(app):
    out = render(app, "/why duct_position_established")
    assert "these gate" in out
    assert "shown but never allowed to gate" in out
    assert "CL-P02-02" in out  # the image observation, visible but non-gating


def test_sources_flags_documents_cited_but_not_supplied(app):
    out = render(app, "/sources")
    assert "NOT SUPPLIED" in out
    assert "S-ABS-RECOVERY" in out


def test_load_creates_a_revision_and_prints_what_moved(app):
    out = render(app, "/load demo/rfi-04.json")
    assert "revision 2 created from v1" in out
    assert "revision 1 → 2" in out
    assert "design_confirmed" in out
    assert "unknown_opened" in out
    assert app.rev == 2


def test_selecting_a_revision_changes_every_view(app):
    render(app, "/load demo/rfi-04.json")
    out = render(app, "/rev 1", "/brief")
    assert "revision 1" in out
    assert "clearance_24in_maintained" not in out  # that question is v2's
    out = render(app, "/rev 2", "/brief")
    assert "clearance_24in_maintained" in out


def test_a_new_revision_branches_off_the_selected_one(app):
    """v1 selected with v2 present: the next revision is v3, built from v1."""
    render(app, "/load demo/rfi-04.json")  # v2
    out = render(app, "/rev 1", "/load demo/rfi-04.json")
    assert "revision 3 created from v1" in out
    assert app.rev == 3
    assert "S-05" in app.ledgers[3].sources
    assert set(app.ledgers[1].claims) < set(app.ledgers[3].claims)


def test_revisions_lists_what_is_on_disk(app):
    render(app, "/load demo/rfi-04.json")
    out = render(app, "/revisions")
    assert "v1" in out and "v2" in out
    assert "75 claims" in out


def test_agent_without_paths_explains_itself(app):
    out = render(app, "/agent")
    assert "usage: /agent" in out
    assert "any type" in out


def test_a_malformed_edit_keeps_the_last_good_graph(app, data):
    before = app.current.as_dict()
    (data / "v1" / "claims.json").write_text("{ not json", encoding="utf-8")
    buffer = io.StringIO()
    app.console = Console(file=buffer, width=200, no_color=True)
    app.reload()
    assert "keeping the last good graph" in buffer.getvalue()
    assert app.current.as_dict() == before  # unchanged, not blank and not broken


def test_unknown_command_does_not_crash(app):
    out = render(app, "/nonsense")
    assert "unknown command" in out
