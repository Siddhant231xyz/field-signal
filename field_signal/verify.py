"""A runnable check, not a test: does each claim's support text actually
appear in the document it cites?

This is how the ledger's accuracy is demonstrated rather than asserted. It
cannot prove the transcription is *complete* — no check can prove a claim
absent from the ledger should have been in it.
"""

from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path

from .model import Ledger

_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Whitespace is a PDF layout artefact; quotes and dashes are not."""
    return _WS.sub(" ", text).strip()


def extract(path: Path) -> str:
    if path.suffix == ".pdf":
        from pypdf import PdfReader  # imported here so the REPL runs without it

        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if path.suffix == ".xlsx":
        return _xlsx_text(path)
    return path.read_text(encoding="utf-8")


def _xlsx_text(path: Path) -> str:
    """Rows joined with ' | ', matching how schedule claims are transcribed."""
    sheet = zipfile.ZipFile(path).read("xl/worksheets/sheet1.xml").decode("utf-8")
    rows = []
    for row in re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S):
        cells = re.findall(r"<c\b.*?(?:<t[^>]*>(.*?)</t>|<v>(.*?)</v>|/>|</c>)", row, re.S)
        values = [html.unescape(a or b or "") for a, b in cells]
        if any(values):
            rows.append(" | ".join(values))
    return "\n".join(rows)


def verify(ledger: Ledger, root: str | Path = ".") -> list[tuple[str, str, str, str]]:
    """-> [(claim_id, source_id, result, detail)], sorted by claim id."""
    root = Path(root)
    cache: dict[str, str] = {}
    rows = []
    for claim in sorted(ledger.claims.values(), key=lambda c: c.id):
        source = ledger.sources[claim.source]
        if not source.present or source.file is None:
            rows.append((claim.id, source.id, "skipped", "source not supplied"))
            continue
        if "photograph" in source.type:
            rows.append(
                (claim.id, source.id, "skipped — image", "an image has no text to check")
            )
            continue
        if source.id not in cache:
            try:
                cache[source.id] = normalise(extract(root / source.file))
            except Exception as exc:  # missing file, missing pypdf, corrupt zip
                cache[source.id] = ""
                rows.append((claim.id, source.id, "unreadable", f"{type(exc).__name__}: {exc}"))
                continue
        found = normalise(claim.support) in cache[source.id]
        rows.append(
            (
                claim.id,
                source.id,
                "found" if found else "NOT FOUND",
                claim.locator if found else f"“{normalise(claim.support)[:70]}…”",
            )
        )
    return rows
