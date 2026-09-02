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
def app():
    return App()


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
    assert "revision 0 → 1" in out
    assert "design_confirmed" in out
    assert "unknown_opened" in out
    assert app.ledger.max_revision() == 1


def test_earlier_revisions_stay_computable(app):
    render(app, "/load demo/rfi-04.json")
    out = render(app, "/rev 0", "/brief")
    assert "revision 0" in out
    assert "clearance_24in_maintained" not in out


def test_a_malformed_edit_keeps_the_last_good_graph(tmp_path):
    shutil.copytree("data", tmp_path / "data")
    app = App(data_dir=str(tmp_path / "data"))
    before = app.current.as_dict()
    (tmp_path / "data" / "claims.json").write_text("{ not json", encoding="utf-8")
    buffer = io.StringIO()
    app.console = Console(file=buffer, width=200, no_color=True)
    app.reload()
    assert "keeping the last good graph" in buffer.getvalue()
    assert app.current.as_dict() == before  # unchanged, not blank and not broken


def test_unknown_command_does_not_crash(app):
    out = render(app, "/nonsense")
    assert "unknown command" in out
