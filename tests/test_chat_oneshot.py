"""One shot, not a tool loop.

The whole evidence base for a revision is ~8k tokens, so retrieval is not a
problem worth solving — the model can be handed everything and answer in a
single round trip. The old loop cost up to twelve sequential requests, which
is where 88 seconds came from.

Two properties matter more than speed:
  * the immutable revision blob goes first, so it is a stable cache prefix;
  * citations are resolved against the ledger, so a claim id the model invents
    is caught here rather than shown to the reader as evidence.
"""

import shutil

import pytest

from field_signal import chat
from field_signal.model import create_revision, load_fixture, load_revision


@pytest.fixture(scope="module")
def revisions(tmp_path_factory):
    root = tmp_path_factory.mktemp("repo") / "data"
    shutil.copytree("data/v1", root / "v1")
    n = create_revision(root, base=1, added=load_fixture("demo/rfi-04.json"))
    return {1: load_revision(root, 1), n: load_revision(root, n)}


# --- the prompt ----------------------------------------------------------


def test_the_context_carries_the_whole_revision(revisions):
    blob = chat.revision_context(revisions, 1)
    ledger = revisions[1]
    assert len(blob) > 10_000
    for claim in ledger.claims.values():
        assert claim.id in blob
        assert claim.support[:40] in blob  # verbatim text, not a summary


def test_the_context_carries_the_derived_conclusions(revisions):
    blob = chat.revision_context(revisions, 1)
    assert "cost_authorised" in blob
    assert "unmet" in blob
    assert "premise contested" in blob or "contested" in blob


def test_the_context_is_stable_for_a_given_revision(revisions):
    """It is the cache prefix; if it varies per call, caching never hits."""
    assert chat.revision_context(revisions, 1) == chat.revision_context(revisions, 1)


def test_different_revisions_give_different_context(revisions):
    other = max(revisions)
    assert chat.revision_context(revisions, 1) != chat.revision_context(revisions, other)


def test_the_question_is_not_baked_into_the_cached_prefix(revisions):
    """The prefix must not depend on what was asked, or nothing is reusable."""
    blob = chat.revision_context(revisions, 1)
    assert "?" not in blob.splitlines()[0]


# --- citations are verified, not trusted ---------------------------------


def test_cited_ids_are_resolved_against_the_ledger(revisions):
    text = "No one authorised it [CL-S00-01] and the quote is unsigned [CL-S04-07]."
    cites, unknown = chat.resolve_citations(text, revisions[1])
    assert [c["claim"] for c in cites] == ["CL-S00-01", "CL-S04-07"]
    assert cites[0]["support"].startswith("Maya issues contractual direction")
    assert cites[0]["citation"] == "S-00 § Working rules"
    assert unknown == []


def test_an_invented_claim_id_is_caught_not_shown(revisions):
    """The one failure mode that would put fabricated evidence on screen."""
    text = "The inspector signed it off [CL-FAKE-99]."
    cites, unknown = chat.resolve_citations(text, revisions[1])
    assert cites == []
    assert unknown == ["CL-FAKE-99"]


def test_each_claim_is_cited_once_even_if_mentioned_twice(revisions):
    text = "[CL-S00-01] says so, and again [CL-S00-01]."
    cites, unknown = chat.resolve_citations(text, revisions[1])
    assert len(cites) == 1


def test_bare_ids_without_brackets_still_resolve(revisions):
    cites, _ = chat.resolve_citations("See CL-S00-01 for the rule.", revisions[1])
    assert [c["claim"] for c in cites] == ["CL-S00-01"]


# --- one round trip ------------------------------------------------------


class FakeClient:
    """Records requests and replays a scripted answer."""

    def __init__(self, text):
        self.text = text
        self.requests = []
        self.responses = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if kwargs.get("stream"):
            return _FakeStream(self.text)
        return _FakeResponse(self.text)


class _FakeResponse:
    def __init__(self, text):
        self.output_text = text
        self.output = []


class _FakeStream:
    def __init__(self, text):
        self.text = text

    def __iter__(self):
        for chunk in (self.text[i : i + 7] for i in range(0, len(self.text), 7)):
            yield type("E", (), {"type": "response.output_text.delta", "delta": chunk})()
        yield type("E", (), {"type": "response.completed"})()


ANSWER = "No. It requires written authorisation [CL-S00-01] and none exists [CL-S04-06]."


def test_one_request_is_made_not_twelve(revisions):
    client = FakeClient(ANSWER)
    chat.answer_question(revisions, 1, "Was it authorised?", [], client=client)
    assert len(client.requests) == 1


def test_no_tools_are_offered(revisions):
    """A tool call is another round trip; everything is already in the prompt."""
    client = FakeClient(ANSWER)
    chat.answer_question(revisions, 1, "Was it authorised?", [], client=client)
    assert not client.requests[0].get("tools")


def test_the_answer_comes_back_with_resolved_citations(revisions):
    client = FakeClient(ANSWER)
    result = chat.answer_question(revisions, 1, "Was it authorised?", [], client=client)
    assert result["revision"] == 1
    assert result["answer"] == ANSWER
    assert [c["claim"] for c in result["citations"]] == ["CL-S00-01", "CL-S04-06"]
    assert result["unknown_citations"] == []


def test_an_invented_citation_is_reported_on_the_result(revisions):
    client = FakeClient("It passed [CL-NOPE-1].")
    result = chat.answer_question(revisions, 1, "Did it pass?", [], client=client)
    assert result["unknown_citations"] == ["CL-NOPE-1"]
    assert result["citations"] == []


def test_the_revision_blob_leads_the_request(revisions):
    """First message = cache prefix. History and question come after it."""
    client = FakeClient(ANSWER)
    chat.answer_question(revisions, 1, "Was it authorised?", [], client=client)
    first = client.requests[0]["input"][0]
    assert first["role"] == "user"
    assert "CL-S00-01" in first["content"]
    assert "Was it authorised?" not in first["content"]


def test_the_question_is_the_last_message(revisions):
    client = FakeClient(ANSWER)
    chat.answer_question(revisions, 1, "Was it authorised?", [], client=client)
    assert "Was it authorised?" in client.requests[0]["input"][-1]["content"]


def test_the_model_and_effort_are_pinned(revisions):
    client = FakeClient(ANSWER)
    chat.answer_question(revisions, 1, "q", [], client=client)
    request = client.requests[0]
    assert request["model"] == "gpt-5.5"
    assert request["reasoning"]["effort"] == "low"


# --- streaming -----------------------------------------------------------


def test_streaming_emits_deltas_and_still_resolves_citations(revisions):
    client = FakeClient(ANSWER)
    seen = []
    result = chat.answer_question(
        revisions, 1, "Was it authorised?", [], client=client, on_delta=seen.append
    )
    assert len(seen) > 1  # arrived in pieces, not one lump
    assert "".join(seen) == ANSWER
    assert result["answer"] == ANSWER
    assert [c["claim"] for c in result["citations"]] == ["CL-S00-01", "CL-S04-06"]
    assert client.requests[0]["stream"] is True


def test_not_streaming_when_no_callback_is_given(revisions):
    client = FakeClient(ANSWER)
    chat.answer_question(revisions, 1, "q", [], client=client)
    assert not client.requests[0].get("stream")


# --- input guards kept ---------------------------------------------------


def test_an_empty_question_is_refused_before_any_request(revisions):
    client = FakeClient(ANSWER)
    with pytest.raises(chat.ChatError):
        chat.answer_question(revisions, 1, "   ", [], client=client)
    assert client.requests == []


def test_an_unknown_revision_is_refused(revisions):
    client = FakeClient(ANSWER)
    with pytest.raises(chat.ChatError):
        chat.answer_question(revisions, 99, "q", [], client=client)
    assert client.requests == []

