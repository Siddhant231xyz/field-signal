"""Slash-command REPL. Dispatch and state only — no derivation, no formatting.

Not a full-screen TUI on purpose: scrollback has to survive, so the before and
the after can both be on screen when new evidence lands mid-review.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from rich.console import Console

from . import render
from .diff import diff
from .graph import Conclusions, conclusions
from .model import Ledger, ValidationError, load_fixture, load_ledger
from .verify import verify

HELP = """
  /brief              the decision brief — exposure, conditions, recommendation
  /why <id>           one condition's full derivation, claim by claim
  /evidence [subject] claim queues, latest on top, with resolution modes
  /conflicts          every queue resolved on recency alone, and every rebuttal
  /unknowns           what the packet does not say, and why it matters
  /exposure           sunk facts — what is already true
  /people             the authority matrix
  /sources            provenance, including documents cited but not supplied
  /graph              the dependency tree under the decision
  /load <file>        append a source as a new revision, then print the diff
  /diff [a] [b]       what moved between revisions (defaults to the last two)
  /rev <n>            render as of revision n
  /verify             check every claim's support text against its document
  /watch              toggle live reload of data/*.json
  /help  /quit
"""


class App:
    def __init__(self, data_dir: str = "data") -> None:
        self.console = Console()
        self.data_dir = data_dir
        self.loaded: list[Path] = []
        self.ledger: Ledger | None = None
        self.views: dict[int, Conclusions] = {}
        self.rev = 0
        self.last_view = "/brief"
        self.watching = False
        self._lock = threading.Lock()
        self.reload()

    # --- state ------------------------------------------------------------

    def reload(self) -> None:
        """Rebuild from disk. On a bad edit, keep the last good graph."""
        try:
            ledger = load_ledger(self.data_dir)
            for i, path in enumerate(self.loaded, start=1):
                ledger.merge(load_fixture(path), revision=i)
            views = {r: conclusions(ledger.at(r)) for r in range(ledger.max_revision() + 1)}
        except (ValidationError, OSError, ValueError) as exc:
            self.console.print(f"[red]validation failed — keeping the last good graph[/red]\n{exc}")
            return
        self.ledger, self.views = ledger, views
        self.rev = ledger.max_revision()

    @property
    def current(self) -> Conclusions:
        return self.views[min(self.rev, max(self.views))]

    # --- commands ---------------------------------------------------------

    def run(self, line: str) -> bool:
        parts = line.strip().split()
        if not parts:
            return True
        cmd, args = parts[0].lower(), parts[1:]
        if not cmd.startswith("/"):
            cmd = "/" + cmd

        if cmd in ("/quit", "/exit", "/q"):
            return False
        if cmd == "/help":
            self.console.print(HELP)
        elif cmd == "/brief":
            self.last_view = "/brief"
            render.brief(self.console, self.ledger, self.current)
        elif cmd == "/why":
            if not args:
                self.console.print("usage: /why <condition-id>")
            else:
                render.why(self.console, self.ledger, self.current, args[0])
        elif cmd == "/evidence":
            render.evidence(self.console, self.ledger, self.current, args[0] if args else None)
        elif cmd == "/conflicts":
            self.last_view = "/conflicts"
            render.conflicts(self.console, self.ledger, self.current)
        elif cmd == "/unknowns":
            self.last_view = "/unknowns"
            render.unknowns(self.console, self.ledger, self.current)
        elif cmd == "/exposure":
            render.exposure(self.console, self.ledger, self.current)
        elif cmd == "/people":
            render.people(self.console, self.ledger, self.current)
        elif cmd == "/sources":
            render.sources(self.console, self.ledger, self.current)
        elif cmd == "/graph":
            render.graph_view(self.console, self.ledger, self.current)
        elif cmd == "/verify":
            render.verify_view(self.console, verify(self.ledger))
        elif cmd == "/load":
            self.load(args)
        elif cmd == "/diff":
            self.show_diff(args)
        elif cmd == "/rev":
            self.set_rev(args)
        elif cmd == "/watch":
            self.toggle_watch()
        else:
            self.console.print(f"[yellow]unknown command[/yellow] {cmd} — try /help")
        return True

    def load(self, args: list[str]) -> None:
        if not args:
            self.console.print("usage: /load <file.json>")
            return
        path = Path(args[0])
        if not path.exists():
            self.console.print(f"[red]no such file:[/red] {path}")
            return
        before = self.ledger.max_revision()
        self.loaded.append(path)
        self.reload()
        if self.ledger.max_revision() == before:  # merge refused; undo
            self.loaded.pop()
            self.reload()
            return
        self.show_diff([str(before), str(self.ledger.max_revision())])

    def show_diff(self, args: list[str]) -> None:
        revs = sorted(self.views)
        if len(revs) < 2 and len(args) < 2:
            self.console.print("only one revision so far — nothing to compare.")
            return
        a, b = (int(args[0]), int(args[1])) if len(args) >= 2 else (revs[-2], revs[-1])
        if a not in self.views or b not in self.views:
            self.console.print(f"revisions available: {revs}")
            return
        render.diff_view(self.console, diff(self.views[a], self.views[b]), a, b)

    def set_rev(self, args: list[str]) -> None:
        if not args:
            self.console.print(f"revision {self.rev} of {sorted(self.views)}")
            return
        n = int(args[0])
        if n not in self.views:
            self.console.print(f"revisions available: {sorted(self.views)}")
            return
        self.rev = n
        self.run(self.last_view)

    # --- live reload ------------------------------------------------------

    def toggle_watch(self) -> None:
        self.watching = not self.watching
        self.console.print(f"[cyan]live reload {'on' if self.watching else 'off'}[/cyan]")
        if self.watching:
            threading.Thread(target=self._watch_loop, daemon=True).start()

    def _watch_loop(self) -> None:
        # ponytail: mtime polling, twice a second. A file watcher is a
        # dependency for a behaviour that only has to survive a demo.
        stamps = self._stamps()
        while self.watching:
            time.sleep(0.5)
            now = self._stamps()
            if now == stamps:
                continue
            stamps = now
            with self._lock:
                before = self.current
                self.reload()
                self.console.print("\n[cyan]evidence changed on disk[/cyan]")
                moves = diff(before, self.current)
                render.diff_view(self.console, moves, before.revision, self.current.revision)
                self.run(self.last_view)

    def _stamps(self) -> dict[str, float]:
        paths = list(Path(self.data_dir).glob("*.json")) + self.loaded
        return {str(p): p.stat().st_mtime for p in paths if p.exists()}


def main(argv: list[str]) -> int:
    app = App()
    if argv:  # non-interactive: `python -m field_signal "/brief" "/conflicts"`
        for line in argv:
            app.run(line)
        return 0

    app.console.print(HELP)
    app.run("/brief")
    while True:
        try:
            line = input("\nfield-signal> ")
        except (EOFError, KeyboardInterrupt):
            return 0
        with app._lock:
            if not app.run(line):
                return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
