"""/verify is the claim that the ledger is honest, made checkable.

It greps each claim's verbatim `support` against the real packet document. If
the transcription drifted, this fails — which is the point.
"""

import shutil

import pytest

from field_signal.model import load_ledger
from field_signal.verify import normalise, verify


@pytest.fixture(scope="module")
def rows():
    return verify(load_ledger())


def test_every_transcribed_claim_is_found_in_its_source(rows):
    missing = [r for r in rows if r[2] in ("NOT FOUND", "unreadable")]
    assert missing == [], f"{len(missing)} claims do not match their source: {missing[:3]}"


def test_image_claims_are_skipped_not_silently_passed(rows):
    skipped = {r[0]: r[2] for r in rows if r[2].startswith("skipped")}
    assert skipped["CL-P02-01"] == "skipped — image"
    assert skipped["CL-P02-02"] == "skipped — image"
    # and they are still counted, not dropped from the report
    assert len(rows) == len(load_ledger().claims)


def test_a_drifted_support_string_is_reported(tmp_path):
    """The check has to be able to fail, or it proves nothing."""
    shutil.copytree("data/v1", tmp_path / "data")
    claims = (tmp_path / "data" / "claims.json").read_text(encoding="utf-8")
    (tmp_path / "data" / "claims.json").write_text(
        claims.replace("I did not lay out the final head.", "I laid out the final head."),
        encoding="utf-8",
    )
    ledger = load_ledger(tmp_path / "data")
    bad = [r for r in verify(ledger) if r[2] == "NOT FOUND"]
    assert [r[0] for r in bad] == ["CL-S01-05"]


def test_whitespace_is_normalised_but_wording_is_not():
    assert normalise("a\n  b ") == "a b"
    assert normalise("six or eight") != normalise("six or ten")
