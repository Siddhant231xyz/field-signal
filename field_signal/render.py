"""Rich rendering. No logic lives here — every value is computed upstream.

Status is never carried by colour alone: each state has a glyph and a word, so
the brief survives a monochrome terminal and a colour-blind reader.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .diff import Movement
from .graph import Conclusions, Queue
from .model import Ledger
from .rules import Basis, Mode, Status

STATUS_GLYPH = {
    Status.MET: ("✓", "met", "green"),
    Status.UNMET: ("✗", "unmet", "red"),
    Status.UNKNOWN: ("?", "unknown", "yellow"),
}

MODE_LABEL = {
    Mode.SINGLE: ("", "", ""),
    Mode.RESOLVED: ("⤴", "resolved — explicitly superseded", "cyan"),
    Mode.ASSUMED: ("⚠", "assumed — preferred on recency alone", "magenta"),
}


def status_text(status: Status, basis: Basis) -> Text:
    glyph, word, colour = STATUS_GLYPH[status]
    if basis is Basis.CONTESTED:
        return Text(f"{glyph}* {word} — premise contested", style=colour)
    return Text(f"{glyph} {word}", style=colour)


def mode_text(q: Queue) -> Text:
    glyph, word, colour = MODE_LABEL[q.mode]
    return Text(f"{glyph} {word}".strip(), style=colour)


def cite(ledger: Ledger, claim_id: str) -> str:
    c = ledger.claims[claim_id]
    return f"{c.source} {c.locator}"


def header(console: Console, ledger: Ledger, c: Conclusions) -> None:
    console.print(
        Text.assemble(
            ("Field Signal", "bold"),
            ("  ·  Hawthorne Commons Café / HC-17  ·  north soffit, CA-118  ·  ", "dim"),
            (f"revision {c.revision}", "bold cyan"),
        )
    )


def brief(console: Console, ledger: Ledger, c: Conclusions) -> None:
    header(console, ledger, c)
    console.print()

    console.print(Text("Already true — behind you, not decidable", style="bold"))
    for e in c.exposures:
        console.print(Panel(e.detail, title=e.label, title_align="left", border_style="red"))

    console.print()
    console.print(Text("Ahead of you — what has to be true before you can direct", style="bold"))
    table = Table(show_lines=True, expand=True)
    table.add_column("state", width=30)
    table.add_column("condition", width=34)
    table.add_column("what the packet actually says")
    for cid in sorted(c.conditions):
        cond = c.conditions[cid]
        table.add_row(
            status_text(cond.status, cond.basis),
            Text.assemble((cond.label, "bold"), ("\n", ""), (f"/why {cid}", "dim")),
            cond.reason,
        )
    console.print(table)

    d = c.decision
    verdict = "PROCEED" if d.recommendation == "PROCEED" else "HOLD"
    colour = "green" if verdict == "PROCEED" else "red"
    basis = " · basis: contested" if d.basis is Basis.CONTESTED else " · basis: settled"
    body = Text.assemble(
        (f"{verdict}{basis}\n\n", f"bold {colour}"),
        (f"{len(d.blocking)} of {len(c.conditions)} conditions not met: ", ""),
        (", ".join(d.blocking) or "none", "bold"),
    )
    if d.basis is Basis.CONTESTED:
        body.append(
            "\n\nContested because the evidence beneath it disagrees with itself: "
            + ", ".join(d.contested_by)
        )
    console.print(Panel(body, title=d.label, title_align="left", border_style=colour))


def why(console: Console, ledger: Ledger, c: Conclusions, cid: str) -> None:
    cond = c.conditions.get(cid)
    if cond is None:
        console.print(f"[red]no such condition:[/red] {cid}")
        console.print("known: " + ", ".join(sorted(c.conditions)))
        return
    console.print(Panel(cond.question, title=cond.label, title_align="left"))
    console.print(status_text(cond.status, cond.basis))
    console.print(cond.reason)
    if cond.depends_on:
        console.print()
        console.print(Text("depends on", style="bold"))
        for dep in cond.depends_on:
            d = c.conditions.get(dep)
            if d:
                console.print(Text.assemble("  ", status_text(d.status, d.basis), f"  {d.label}"))
    _claim_table(console, ledger, "read by this rule — these gate", cond.support)
    if cond.notes:
        _claim_table(console, ledger, "shown but never allowed to gate", cond.notes)
    if cond.contested_by:
        console.print(
            Text(f"contested by: {', '.join(cond.contested_by)}", style="magenta")
        )


def _claim_table(console: Console, ledger: Ledger, title: str, ids: tuple[str, ...]) -> None:
    if not ids:
        return
    console.print()
    console.print(Text(title, style="bold"))
    table = Table(show_header=True, header_style="dim", expand=True)
    table.add_column("claim", width=12)
    table.add_column("kind", width=14)
    table.add_column("who", width=16)
    table.add_column("citation", width=22)
    table.add_column("verbatim")
    for cid in ids:
        cl = ledger.claims[cid]
        table.add_row(
            cid, cl.kind, ledger.author_of(cl), cite(ledger, cid), Text(f"“{cl.support}”", style="italic")
        )
    console.print(table)


def evidence(console: Console, ledger: Ledger, c: Conclusions, subject: str | None = None) -> None:
    keys = [k for k in sorted(c.queues) if subject is None or subject in k[0]]
    if not keys:
        console.print(f"[yellow]no subject matching[/yellow] {subject}")
        console.print("subjects: " + ", ".join(sorted({k[0] for k in c.queues})))
        return
    for key in keys:
        q = c.queues[key]
        title = Text.assemble((f"{key[0]} / {key[1]}  ", "bold"), mode_text(q))
        table = Table(show_header=True, header_style="dim", expand=True, box=None)
        table.add_column("", width=3)
        table.add_column("claim", width=12)
        table.add_column("kind", width=14)
        table.add_column("who", width=16)
        table.add_column("citation", width=22)
        table.add_column("value / verbatim")
        for cl in q.claims:
            marker = "▶" if cl.id == q.head.id else " "
            style = "dim strike" if cl.id in q.superseded else ""
            note = " [superseded]" if cl.id in q.superseded else ""
            rebut = c.rebuttals.get(cl.id, ())
            if rebut:
                note += f" [refuted by {', '.join(rebut)}]"
            table.add_row(
                marker,
                cl.id,
                cl.kind,
                ledger.author_of(cl),
                cite(ledger, cl.id),
                Text(f"{cl.value}{note}\n“{cl.support}”", style=style),
            )
        console.print(Panel(table, title=title, title_align="left"))


def conflicts(console: Console, ledger: Ledger, c: Conclusions) -> None:
    assumed = c.conflicts()
    if not assumed:
        console.print("no queue is resolved on recency alone.")
    for q in assumed:
        console.print(
            Panel(
                Text.assemble(
                    (f"{mode_text(q).plain}. ", "magenta bold"),
                    ("The head is preferred by recency and nothing else — no one in the "
                     "packet resolved this, and no measurement exists. Every claim below "
                     "stays readable, and anything derived from the head is marked "
                     "'premise contested'.\n\n", "magenta"),
                    *[
                        Text.assemble(
                            ("▶ " if cl.id is q.head.id else "  "),
                            (f"“{cl.value}” ", "bold"),
                            (f"— {ledger.author_of(cl)}, {cite(ledger, cl.id)}\n", "dim"),
                        )
                        for cl in q.claims
                    ],
                ),
                title=f"⚠ {q.subject} / {q.predicate}",
                title_align="left",
                border_style="magenta",
            )
        )
    console.print(Text("rebuttals — a direct contradiction of another party", style="bold"))
    for target, refuters in c.rebuttals.items():
        t = ledger.claims[target]
        for r in refuters:
            rc = ledger.claims[r]
            console.print(
                f"  {ledger.author_of(rc)} ({cite(ledger, r)}) refutes "
                f"{ledger.author_of(t)} ({cite(ledger, target)})"
            )
            console.print(f"    [dim]“{t.support}”[/dim]")
            console.print(f"    [bold]“{rc.support}”[/bold]")


def unknowns(console: Console, ledger: Ledger, c: Conclusions) -> None:
    console.print(
        Text("Unknown means the packet does not say. It never means no.", style="bold")
    )
    table = Table(show_lines=True, expand=True)
    table.add_column("state", width=30)
    table.add_column("the question", width=40)
    table.add_column("why it is unknown, and why it matters")
    for cond in c.unknowns():
        table.add_row(status_text(cond.status, cond.basis), cond.question, cond.reason)
    console.print(table)
    if c.absent_bases:
        console.print()
        console.print(Text("documents cited but not supplied", style="bold"))
        for sid, claim_ids in c.absent_bases.items():
            s = ledger.sources[sid]
            console.print(f"  [yellow]{sid}[/yellow] — {s.limitations[0]}")
            for cid in claim_ids:
                console.print(f"    leaned on by {cid} ({cite(ledger, cid)})")


def exposure(console: Console, ledger: Ledger, c: Conclusions) -> None:
    console.print(
        Text("Already true. These are not conditions — you cannot prevent them.", style="bold")
    )
    for e in c.exposures:
        console.print(Panel(e.detail, title=e.label, title_align="left", border_style="red"))
        console.print(Text("  " + ", ".join(cite(ledger, i) for i in e.support), style="dim"))


def people(console: Console, ledger: Ledger, c: Conclusions) -> None:
    table = Table(title="Authority — who can actually decide what", expand=True, show_lines=True)
    table.add_column("person", width=16)
    table.add_column("role", width=20)
    table.add_column("organisation", width=20)
    table.add_column("capabilities", width=30)
    table.add_column("basis in the packet")
    for pid in sorted(ledger.people):
        p = ledger.people[pid]
        table.add_row(p.name, p.role, p.org, "\n".join(p.capabilities), p.capability_basis)
    console.print(table)


def sources(console: Console, ledger: Ledger, c: Conclusions) -> None:
    table = Table(title="Sources", expand=True, show_lines=True)
    table.add_column("id", width=16)
    table.add_column("type", width=22)
    table.add_column("author", width=20)
    table.add_column("locator model", width=20)
    table.add_column("known limitations")
    for sid in sorted(ledger.sources):
        s = ledger.sources[sid]
        name = Text(sid, style="bold" if s.present else "yellow")
        if not s.present:
            name.append("\nNOT SUPPLIED", style="yellow")
        table.add_row(name, s.type, s.author, s.locator_model, "\n".join(s.limitations))
    console.print(table)


def graph_view(console: Console, ledger: Ledger, c: Conclusions) -> None:
    d = c.decision
    root = Tree(
        Text.assemble((d.label, "bold"), (f"  {d.recommendation}", "bold red"))
    )
    for cid in sorted(c.conditions):
        cond = c.conditions[cid]
        node = root.add(Text.assemble(status_text(cond.status, cond.basis), f"  {cond.label}"))
        for dep in cond.depends_on:
            dc = c.conditions.get(dep)
            if dc:
                node.add(
                    Text.assemble(
                        ("depends on ", "dim"), status_text(dc.status, dc.basis), f"  {dc.label}"
                    )
                )
        for claim_id in cond.support:
            cl = ledger.claims[claim_id]
            node.add(
                Text(f"{claim_id} · {cl.kind} · {cite(ledger, claim_id)}", style="dim")
            )
    console.print(root)


def diff_view(console: Console, moves: tuple[Movement, ...], a: int, b: int) -> None:
    console.print(Text(f"evidence changed — revision {a} → {b}", style="bold cyan"))
    if not moves:
        console.print("nothing moved.")
        return
    table = Table(expand=True, show_lines=False)
    table.add_column("what", width=20)
    table.add_column("id", width=30)
    table.add_column("before", width=26)
    table.add_column("after")
    for m in moves:
        style = {
            "condition_status": "bold",
            "condition_basis": "magenta",
            "unknown_opened": "yellow",
            "unknown_closed": "green",
            "recommendation": "bold red",
            "blocking_changed": "bold",
            "superseded": "cyan",
        }.get(m.kind, "dim")
        table.add_row(Text(m.kind, style=style), m.id, m.before, m.after)
    console.print(table)


def verify_view(console: Console, rows: list[tuple[str, str, str, str]]) -> None:
    table = Table(title="/verify — claim support text against the real documents", expand=True)
    table.add_column("claim", width=12)
    table.add_column("source", width=10)
    table.add_column("result", width=22)
    table.add_column("detail")
    failed = 0
    for claim_id, source, result, detail in rows:
        colour = {"found": "green", "NOT FOUND": "red"}.get(result, "yellow")
        if result == "NOT FOUND":
            failed += 1
        table.add_row(claim_id, source, Text(result, style=colour), detail)
    console.print(table)
    console.print(
        Text(
            f"{len(rows)} claims checked · {failed} not found in their source document",
            style="bold red" if failed else "bold green",
        )
    )
