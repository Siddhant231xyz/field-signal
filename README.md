# Field Signal

A decision brief for one person, on one day, about one decision — derived from
the packet rather than written about it.

**User:** Maya Chen, project manager, Northline Builders.
**Decision:** whether to direct Cascade Air to complete the north soffit duct
relocation (CA-118, $2,850) before Thursday's above-ceiling inspection.
**What it is for:** telling apart what the packet *supports*, what someone
merely *claimed*, and what is genuinely *unknown* — and showing what moves when
one consequential source changes.

Every conclusion is derived at runtime from the ledger in `data/`. Nothing is
written as prose in a template, so a new or corrected source can be dropped in
and the affected conclusions visibly change.

## Run it

Two front ends, one engine. The terminal and the browser both read the same
`conclusions()`; neither reaches a conclusion of its own.

### Terminal

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m field_signal                 # interactive, opens on /brief
.venv/bin/python -m field_signal "/brief"        # one-shot, for scripting
```

Python 3.11+ (uses `graphlib` and `X | None` annotations).

### Browser

```bash
npm --prefix web install
npm --prefix web run build
.venv/bin/python -m field_signal.web             # http://127.0.0.1:8000
```

Node 20+. For frontend development, `npm --prefix web run dev` proxies `/api`
to the Python server, so run both.

The web app covers every CLI command — the sheet rail is labelled with them —
and adds a 3D view of the evidence: the decision on top, the conditions
holding it up, the claims beneath those, and the people who spoke at the base.
Drag to orbit, click a node to fly to it, and filter by node type. Views are
hash-addressable (`#/graph`), so a sheet can be linked and survives a reload.

## The demonstration — evidence changed, here is what moved

```
field-signal> /brief                       # HOLD · basis: contested
field-signal> /conflicts                   # three duct offsets, none measured
field-signal> /load demo/rfi-04.json       # the architect answers
```

`/load` creates revision 2 from revision 1, computes the difference and prints
it. The fixture is deliberately messy: it **closes** two unknowns (the
architect confirms the shift; the access panel is fixed), **opens** one that
did not previously exist (24 in clear north of the panel, which hangs off the
still-disputed duct offset and is therefore marked *premise contested*), and
leaves the recommendation at **HOLD for a different set of reasons**. A fixture
that resolved everything cleanly would rehearse well and prove nothing.

`/rev 1` returns to the earlier revision — nothing is deleted, so every
revision stays computable. `/watch` reloads on change and prints the delta
without a command being typed.

## Adding your own evidence

```
field-signal> /agent path/to/documents/          # CLI
```

or the **Add evidence** sheet in the browser: drop in any number of files, of
any type. They are read inside a disposable Docker container that identifies
each format from its contents rather than its extension (`examples/`), and the
claims it extracts become a new revision.

Requires Docker and `OPENAI_API_KEY` in `.env`. Without them it reports a
failure and writes nothing.

### How revisions work

Each revision is a directory — `data/v1`, `data/v2`, … — holding a complete
ledger. Selecting one swaps the whole ledger, so every view shows that
revision rather than the newest set filtered down.

A new revision is built from **the revision you have selected** plus what was
added, and takes the next free number:

| selected | you add evidence | you get |
|---|---|---|
| v1 (only revision) | → | v2 = v1 + new |
| v1, with v2 present | → | v3 = **v1** + new |
| v2 | → | v3 = v2 + new |

So going back to an earlier revision and adding evidence branches from there,
without destroying what came after. Claims are deduplicated by id *and* by
source, locator, subject, predicate and value — the agent re-reads a packet on
every run and does not reproduce ids, so re-adding the same evidence adds
nothing.

Agent output is a model's proposal. It always lands in a new revision to be
compared against the one before it, never as an edit to a revision you have
already read.

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
| `/agent <path>…` | read files of any type into a new revision |
| `/load <file>` · `/diff [a] [b]` · `/rev <n>` · `/revisions` | revisions |
| `/verify` | every claim's support text against its real document |
| `/watch` · `/help` · `/quit` | |

## Verification

```bash
.venv/bin/python -m pytest tests -q          # 80 tests
.venv/bin/python -m pytest examples/tests -q # 7 tests, ingestion experiment
npm --prefix web test                        # 7 tests, tooltip escaping
.venv/bin/python -m field_signal "/verify"   # 75 claims vs the real documents
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

- **The web layer adds no rules.** A test asserts no image observation can
  appear as a gating link in the graph payload, so the CLI's central
  constraint survives the trip to the browser. Condition status strings are
  generated by `render.py` and sent to the browser, so the two front ends
  cannot drift apart on what a status looks like.
- **Evidence cannot forge its own presentation.** The graph tooltip is the one
  place the app builds HTML from ledger text, and ledger text is untrusted:
  the ingestion experiment derives claims from arbitrary packet documents. It
  is escaped in one place, tested directly, and verified end to end by loading
  a hostile claim and reading the rendered DOM. This matters more here than in
  an ordinary app — a source that could inject markup could forge what the
  tool displays about it, which is exactly the failure the tool exists to
  prevent.

**What remains unverified.** The Vue components have no unit tests. They were
checked by driving headless Chrome against the running server and reading the
screenshots, which found two layout bugs and a caption that described the
graph layout backwards. That is a weaker guarantee than the Python side has.

Whether the transcription is *complete*. No test
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
7. **The web server is single-process and has no auth.** It binds
   `127.0.0.1`, and `/api/load`, `/api/select` and `/api/agent` change what
   everyone connected sees. `/api/agent` runs a container and writes to disk on
   an unauthenticated request. Fine for a local review, wrong for anything
   shared.
9. **The agent's output is only as good as the model.** Its claims are
   validated for shape and checked by `/verify` against the uploaded file, but
   nothing checks that it read the document *correctly*, or that it did not
   miss a claim. This is the same completeness gap as the hand transcription,
   now automated and therefore easier to trust than it deserves.
10. **Uploads accumulate.** `uploads/vN` is never pruned, and the whole
    multipart body is held in memory (200 MB cap).
8. **The 3D graph needs WebGL.** Without it the canvas is blank and the rest
   of the app still works. Labels can overlap where several nodes share a DAG
   level; drag or switch to free float to separate them.

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
| `field_signal/` | the engine, the CLI and the JSON API — see `ARCHITECTURE.md` |
| `web/` | the Vue front end |
| `data/v1`, `data/v2`, … | one complete evidence ledger per revision |
| `uploads/vN` | files added via the agent, kept so their claims stay checkable |
| `demo/rfi-04.json` | demo fixture, **not packet evidence** |
| `examples/` | a separate containerized ingestion experiment, not wired into the product |
| `tests/` | 80 tests, named after the risk each prevents |
| `docs/superpowers/specs/` | the design, written before the code |
| `docs/decision-journal.md` | the path actually taken |
| `docs/ai-work-log.md` | what was delegated, what was rejected |
| `PACKET_EXPLAINED.md` | the packet in plain English, written while reading it |

No secrets, no personal data, no external services, no network calls at
runtime.
