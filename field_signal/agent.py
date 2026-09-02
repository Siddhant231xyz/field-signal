"""Turn uploaded files into a new revision, using the containerized agent.

The extraction itself is `examples/run_containerized.py` unchanged: a
disposable Docker container with the uploads mounted read-only. Nothing here
reads a document — this module stages files, calls that, and merges the result
into a new revision.

Agent output is evidence proposed by a model, so it lands in a *new* revision
that the reader can compare against the one before it. It never edits one.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from .model import DATA_ROOT, Ledger, create_revision, latest_revision, load_ledger

REPO = Path(__file__).resolve().parent.parent
UPLOADS = REPO / "uploads"


class AgentError(RuntimeError):
    pass


def _docker_runner(inputs: Path, output: Path) -> None:
    """The real extractor. Imported lazily so the CLI runs without it."""
    from examples.run_containerized import main

    code = main(["--input", str(inputs), "--output", str(output), "--no-compare"])
    if code != 0:
        raise AgentError(
            f"the ingestion agent exited with {code}. It needs Docker running and "
            f"OPENAI_API_KEY set in .env — see examples/README.md."
        )


def stage(paths: list[Path], destination: Path) -> list[Path]:
    """Copy uploads flat into one directory. Returns what was staged."""
    destination.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for path in paths:
        if not path.exists():
            raise AgentError(f"no such file: {path}")
        for src in sorted(path.rglob("*")) if path.is_dir() else [path]:
            if not src.is_file():
                continue
            target = destination / src.name
            # ponytail: basename collisions get a numeric suffix; a full path
            # mirror only matters if someone uploads two trees with same names.
            i = 1
            while target.exists():
                target = destination / f"{src.stem}-{i}{src.suffix}"
                i += 1
            shutil.copy2(src, target)
            staged.append(target)
    if not staged:
        raise AgentError("no files to ingest")
    return staged


def _repoint(added: Ledger, stored: dict[str, Path]) -> Ledger:
    """Point each source at the stored upload, so /verify can still read it."""
    for sid, source in list(added.sources.items()):
        if not source.file:
            continue
        target = stored.get(Path(source.file).name)
        if target:
            added.sources[sid] = replace(
                source, file=str(target.relative_to(REPO)).replace("\\", "/")
            )
    return added


def ingest(
    paths: list[Path],
    *,
    root: Path = DATA_ROOT,
    base: int,
    runner=_docker_runner,
) -> tuple[int, list[Path]]:
    """Extract `paths` and write base + extraction as a new revision."""
    with tempfile.TemporaryDirectory(prefix="fs-ingest-") as tmp:
        inputs, output = Path(tmp) / "in", Path(tmp) / "out"
        staged = stage(paths, inputs)
        output.mkdir()
        runner(inputs, output)
        try:
            added = load_ledger(output)
        except (OSError, KeyError, ValueError) as exc:
            raise AgentError(f"the agent produced no usable ledger: {exc}") from exc

        # Keep the uploads so their claims stay checkable against the files.
        # ponytail: single-process app, so the next free number is stable
        # between here and create_revision. Needs a lock if that stops holding.
        keep = UPLOADS / f"v{latest_revision(root) + 1}"
        if keep.exists():
            shutil.rmtree(keep)
        added = _repoint(added, {p.name: p for p in stage(staged, keep)})

        try:
            n = create_revision(root, base=base, added=added)
        except Exception:
            shutil.rmtree(keep, ignore_errors=True)
            raise
        return n, sorted(keep.iterdir())
