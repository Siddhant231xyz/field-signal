# Field Signal

A decision brief for one person, on one day, about one decision — derived from
the packet rather than written about it.

**User:** Maya Chen, project manager, Northline Builders.
**Decision:** whether to direct Cascade Air to complete the north soffit duct
relocation (CA-118, $2,850) before Thursday's above-ceiling inspection.
**What it is for:** telling apart what the packet *supports*, what someone
merely *claimed*, and what is genuinely *unknown* — and showing what moves when
one consequential source changes.

Every conclusion is derived at runtime from `data/*.json`. Nothing is written
as prose in a template, so a new or corrected source can be dropped in and the
affected conclusions visibly change.

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m field_signal                 # interactive, opens on /brief
.venv/bin/python -m field_signal "/brief"        # one-shot, for scripting
```

Python 3.11+ (uses `graphlib` and `X | None` annotations).

## The demonstration — evidence changed, here is what moved

```
field-signal> /brief                       # HOLD · basis: contested
field-signal> /conflicts                   # three duct offsets, none measured
field-signal> /load demo/rfi-04.json       # the architect answers
```

`/load` computes the difference between revision 0 and revision 1 and prints
it. The fixture is deliberately messy: it **closes** two unknowns (the
architect confirms the shift; the access panel is fixed), **opens** one that
did not previously exist (24 in clear north of the panel, which hangs off the
still-disputed duct offset and is therefore marked *premise contested*), and
leaves the recommendation at **HOLD for a different set of reasons**. A fixture
that resolved everything cleanly would rehearse well and prove nothing.

`/rev 0` returns to the earlier revision — nothing is deleted, so every
revision stays computable. `/watch` reloads `data/*.json` on change and prints
the delta without a command being typed.

`demo/rfi-04.json` is labelled in its own header as **not packet evidence**.

## Commands

| | |
|---|---|
| `/brief` | exposure, conditions, recommendation |
| `/why <id>` | one condition's derivation — every claim the rule read, and the ones it may not use |
| `/evidence [subject]` | claim queues, latest on top, with resolution mode |
| `/conflicts` | queues resolved on recency alone, plus every rebuttal |
| `/unknowns` | what the packet does not say, and why it matters |
| `/exposure` | what is already true and no longer preventable |
| `/people` | the authority matrix, each capability cited to the primer |
| `/sources` | provenance, including documents cited but not supplied |
| `/graph` | the dependency tree under the decision |
| `/load <file>` · `/diff [a] [b]` · `/rev <n>` | revisions |
| `/verify` | every claim's support text against its real document |
| `/watch` · `/help` · `/quit` | |

## Verification

```bash
.venv/bin/python -m pytest tests -q        # 45 tests
.venv/bin/python -m field_signal "/verify" # 75 claims vs the real documents
```

**What is verified, and why those risks.** The tests are named after the
mistake each one prevents; `ARCHITECTURE.md` lists them individually.

- **Authority.** $2,850 exceeds the $2,000 threshold and no one with the
  capability has authorised it. Tasha Reed's support is shown and explicitly
  does not count. The rule reads the threshold from the packet, so a $1,200
  quote gives a different answer for the right reason.
- **Absence.** The record stops at 12:22. The field review is `unknown`, never
  "did not happen". A schedule row saying "Booked" is a `plan` and cannot make
  anything `met`.
- **Photographs.** An image `observation` may never gate a condition; a rule
  that tries raises. The unintelligible 08:11:02 fragment is kept verbatim and
  gates nothing.
- **Conflict.** Three stated duct offsets ("about 6 in", "six or eight
  inches", "approximately 6–12 inches"), none of them a measurement. The
  product prints all three and never a fourth.
- **Taint — the central guarantee.** Anything derived from a queue resolved by
  recency alone renders as `premise contested`, all the way to the
  recommendation. A conclusion can never look cleaner than the evidence
  beneath it.
- **Determinism.** Shuffle the ledger; the conclusions are byte-identical.
- **`/verify`** greps each claim's verbatim `support` against the real PDF or
  workbook. The suite includes a deliberately drifted claim to prove the check
  can fail.

**What remains unverified.** Whether the transcription is *complete*. No test
can prove that a claim absent from the ledger should have been in it. That is
the failure that would concern us most: a claim omitted during reading is
invisible to every check in the system, and the tool would present a confident
brief with a hole in it. The mitigations are that `/verify` proves every claim
that *is* present is real, and that `/sources` states each source's known
limitations.

The determinism guarantee runs from the **accepted ledger** to the conclusion.
Reading a document into claims is a human judgment step and sits outside it.
So does `value` normalisation (e.g. "Thursday morning" → `2026-09-17`), which
exists so that queues compare cleanly; the verbatim text is always kept in
`support` and is always checkable.

## Coverage honesty

The ledger covers the CA-118 / north soffit decision exhaustively: all 30
transcript lines, all 11 messages, the quote, the primer's working rules, the
photo register and the schedule rows that bear on it. Millwork, schedule and
photograph claims are transcribed where they touch that decision and partially
otherwise — the millwork delivery thread is present because it demonstrates
supersession and a cited-but-absent document, not because it was analysed in
full. Thin coverage is a scoping decision only when it is declared.

## Known limitations and failure modes

1. **Transcription completeness is unverifiable** (above). Most consequential.
2. **`ASSUMED` resolution follows recency**, which is a heuristic, not a
   finding. It is honoured because the latest claim is the most defensible
   default, and made safe by propagating the taint — never by claiming the
   heuristic is right.
3. **Conditions are hand-modelled.** A genuinely new kind of question needs a
   new rule in `rules.py`. A small edit, but code, not configuration.
4. **`/verify` cannot check images.** Image claims are skipped, not passed.
5. **No performance work exists.** The graph is small. At packet scale the
   queue building would need rethinking.
6. **`/watch` polls mtimes twice a second** on a daemon thread. Output can
   interleave with a half-typed command.

## Evidence handling rules this obeys

- `packet/` is the only source of project facts.
- A statement in a source is a claim by a named author at a time, not a
  verified fact.
- Absence of evidence is `unknown`, not `false`.
- Photographs prove nothing about intent, authority, completion, dimensions or
  code compliance. Captions are the submitter's claims.
- Schedule dates are plan, not proof that work occurred.
- Conflicts are surfaced with both sides cited, never silently reconciled.
- Nothing is deleted. A correction arrives as a new source that supersedes a
  claim; the superseded claim stays readable with both citations.

## Repository

| | |
|---|---|
| `field_signal/` | the product — see `ARCHITECTURE.md` |
| `data/` | the evidence ledger: people, sources, claims |
| `demo/rfi-04.json` | demo fixture, **not packet evidence** |
| `tests/` | 45 tests, named after the risk each prevents |
| `docs/superpowers/specs/` | the design, written before the code |
| `docs/decision-journal.md` | the path actually taken |
| `docs/ai-work-log.md` | what was delegated, what was rejected |
| `PACKET_EXPLAINED.md` | the packet in plain English, written while reading it |

No secrets, no personal data, no external services, no network calls at
runtime.
