"""Turn uploaded files into a new revision, using the containerized agent.

The extraction itself is `examples/run_containerized.py` unchanged: a
disposable Docker container with the uploads mounted read-only. Nothing here
reads a document — this module stages files, calls that, and merges the result
into a new revision.

Agent output is evidence proposed by a model, so it lands in a *new* revision
that the reader can compare against the one before it. It never edits one.
"""

from __future__ import annotations

import inspect
import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from .model import (
    DATA_ROOT,
    Ledger,
    create_revision,
    latest_revision,
    load_ledger,
    revision_dir,
)
from .rules import INGESTION_CONTRACT

REPO = Path(__file__).resolve().parent.parent
UPLOADS = REPO / "uploads"


class AgentError(RuntimeError):
    pass


def _docker_runner(
    inputs: Path, output: Path, *, context: Path, on_line=None
) -> None:
    """The real extractor. Imported lazily so the CLI runs without it."""
    from examples import run_containerized

    run_containerized.ON_LINE = on_line
    try:
        code = run_containerized.main(
            [
                "--input",
                str(inputs),
                "--context",
                str(context),
                "--output",
                str(output),
                "--no-compare",
            ]
        )
    finally:
        run_containerized.ON_LINE = None
    if code != 0:
        raise AgentError(
            f"the ingestion agent exited with {code}. It needs Docker running and "
            f"OPENAI_API_KEY set in .env — see examples/README.md."
        )


# What a caller can show while a run is in flight. The container prints these
# lines; nothing else tells an embedder that anything is happening.
PHASES = {
    "staging": "copying your files into a clean directory",
    "building": "building the container image",
    "extracting": "the agent is reading your documents",
    "writing": "merging into a new revision",
    "done": "finished",
    "failed": "stopped — nothing was written",
}


def _phase_from(line: str) -> tuple[str, int | None]:
    """Map one line of container output to a phase and a shell-call count."""
    if line.startswith("shell call"):
        try:
            return "extracting", int(line.split()[-1])
        except ValueError:
            return "extracting", None
    if line.startswith("Building"):
        return "building", None
    if line.startswith("Starting containerized agent"):
        return "extracting", None
    if line.startswith("Validated output promoted"):
        return "writing", None
    return "", None


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
            added.sources[sid] = replace(source, file=_repo_relative(target))
    return added


def _repo_relative(path: Path) -> str:
    """Repo-relative where possible; absolute rather than raising if not.

    /verify resolves a source file against the repo root, so a relative path is
    what we want — but an uploads directory outside the repo must degrade, not
    crash the whole ingestion after the model work is already paid for.
    """
    try:
        return str(path.relative_to(REPO)).replace("\\", "/")
    except ValueError:
        return str(path)


def _prepare_context(root: Path, base: int, destination: Path) -> Path:
    """Bundle the selected ledger with the vocabulary its consumers require."""
    source = revision_dir(root, base)
    if not source.is_dir():
        raise AgentError(f"unknown base revision v{base}")
    shutil.copytree(source, destination)
    (destination / "ontology.json").write_text(
        json.dumps(INGESTION_CONTRACT, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def ingest(
    paths: list[Path],
    *,
    root: Path = DATA_ROOT,
    base: int,
    runner=_docker_runner,
    on_progress=None,
) -> tuple[int, list[Path]]:
    """Extract `paths` and write base + extraction as a new revision.

    `on_progress` receives a dict as the run moves through its phases, so a
    caller can say what is happening. A run takes minutes; without this the
    only signal is that nothing has come back yet.
    """
    state = {"phase": "staging", "shell_calls": 0, "files": 0, "base": base,
             "revision": None, "error": None, "merged_people": {}}

    def report(**changes):
        state.update(changes)
        if on_progress:
            on_progress(dict(state))

    def on_line(line: str):
        phase, calls = _phase_from(line)
        if not phase:
            return
        # Highest seen, not a running total: the container numbers its own.
        report(phase=phase, shell_calls=max(state["shell_calls"], calls or 0))

    try:
        return _ingest(paths, root, base, runner, report, on_line, state)
    except Exception as exc:
        report(phase="failed", error=str(exc))
        raise


def _ingest(paths, root, base, runner, report, on_line, state) -> tuple[int, list[Path]]:
    with tempfile.TemporaryDirectory(prefix="fs-ingest-") as tmp:
        inputs, output = Path(tmp) / "in", Path(tmp) / "out"
        context = _prepare_context(root, base, Path(tmp) / "context")
        staged = stage(paths, inputs)
        report(phase="staging", files=len(staged))
        output.mkdir()
        parameters = inspect.signature(runner).parameters
        options = {}
        if "context" in parameters:
            options["context"] = context
        if "on_line" in parameters:
            options["on_line"] = on_line
        runner(inputs, output, **options)
        try:
            # A delta may refer to people, sources, and claims in the selected
            # base. Referential validation belongs after the two are combined.
            added = load_ledger(output, validate=False)
        except (OSError, KeyError, ValueError) as exc:
            raise AgentError(f"the agent produced no usable ledger: {exc}") from exc

        # Keep the uploads so their claims stay checkable against the files.
        # ponytail: single-process app, so the next free number is stable
        # between here and create_revision. Needs a lock if that stops holding.
        keep = UPLOADS / f"v{latest_revision(root) + 1}"
        if keep.exists():
            shutil.rmtree(keep)
        added = _repoint(added, {p.name: p for p in stage(staged, keep)})

        report(phase="writing")
        merged: dict[str, str] = {}
        try:
            n = create_revision(root, base=base, added=added, merged_people=merged)
        except Exception:
            shutil.rmtree(keep, ignore_errors=True)
            raise
        report(phase="done", revision=n, merged_people=merged)
        return n, sorted(keep.iterdir())
