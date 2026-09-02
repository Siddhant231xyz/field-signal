# Field Signal — design

Status: awaiting review · 1 September 2026

## 1 · User and problem

**User:** Maya Chen, project manager, Northline Builders.

**Problem:** On 14 September 2026 she must direct the north soffit HVAC
relocation before a Thursday inspection and Friday close-in. Work has already
been performed without authorisation, $2,850 is unauthorised and above her
$2,000 written-authorisation threshold, and the meeting that was to resolve
the design and fire-protection questions has no recorded outcome. She needs to
know what is settled, what is merely claimed, what is genuinely unknown, and
what her exposure already is.

**Why this user:** she is the only person in the packet who can authorise the
cost. Every other actor's support is advisory. The decisive mistake to prevent
is her relying on a claim that no one with authority has actually made.

**Rejected alternative:** Luis Ortega (superintendent), a schedule-risk tool.
Rejected because he cannot approve added subcontract cost; a tool serving him
risks becoming a well-presented nudge toward the wrong authority path.

## 2 · Scope

**In scope.** The CA-118 / north soffit decision, derived from every source in
`packet/`. The full authority model. Conflict, unknown and supersession
handling. Revision history and diffing. A terminal interface.

**Out of scope, deliberately.** Automated PDF or image ingestion. Any model in
the runtime path. Cost estimating beyond the quoted figure and its stated
exclusions. Multi-project support. Persistence beyond the JSON files. A rule
DSL. Authentication.

**Deferred (§12).** Agent-assisted extraction, as a staged proposal flow.

**Coverage honesty.** The ledger covers the CA-118 decision exhaustively.
Millwork, schedule and photograph claims are transcribed where they bear on
that decision and partially otherwise. The README states this; thin coverage
is a scoping decision only when it is declared.

## 3 · Architecture

Five layers, each depending only on the one above it:

```
data/*.json          evidence — the only source of project facts
   │
model.py             typed nodes and edges, schema validation
   │
graph.py             queues, topological derivation, taint propagation
rules.py             condition rules — pure functions, no I/O
   │
diff.py              conclusions(a) vs conclusions(b)
   │
render.py            Rich rendering — no logic
__main__.py          REPL, command dispatch, live reload
```

`rules.py` and `graph.py` import nothing from `render.py` and perform no I/O.
This is what makes the derivation testable and what makes "why did this
change?" answerable without inspecting the renderer.

Python 3.11+. One runtime dependency: `rich`. One dev dependency: `pytest`.
Ordering uses stdlib `graphlib.TopologicalSorter`; no graph library.

## 4 · Data model

### Node types

| Node | Fields |
|---|---|
| `Person` | `id`, `name`, `org`, `capabilities[]` |
| `Source` | `id`, `file`, `type`, `author`, `logical_time`, `locator_model`, `limitations[]`, `present`, `revision` |
| `Claim` | `id`, `source`, `locator`, `support`, `stated_by`, `stated_at`, `subject`, `predicate`, `value`, `kind`, `revision` |
| `Subject` | `id` — implicit, created from claims |
| `Condition` | `id`, `label`, `rule` |
| `Decision` | `id`, `label` |

`support` holds the verbatim text the claim was read from. `/verify` checks it
against the real document (§10).

`present: false` on a `Source` records a document that is cited by a claim but
not supplied — Nina's "approved recovery schedule". This makes *"cited basis
absent"* a first-class state rather than something the reader must notice.

### Claim kinds

| Kind | Meaning | Constraint |
|---|---|---|
| `assertion` | a direct statement of fact by its author | — |
| `estimate` | an approximation, explicitly uncertain | never rendered as a single value |
| `intent` | what someone said they would do | never implies it was done |
| `plan` | a scheduled date or planned activity | **never** evidence work occurred |
| `caption` | a submitter's description of their own photo | claims only what was *said* |
| `observation` | what is visible in an image | **never** gates authority, completion, dimension or compliance |
| `unintelligible` | recorded but not recoverable | holds the fragment verbatim; gates nothing |

The `observation` and `unintelligible` constraints are enforced in `graph.py`
at edge-creation time, not by convention. A claim of either kind that attempts
to support a gating condition is a validation error.

### Edge types

| Edge | From → To | Meaning |
|---|---|---|
| `stated_by` | Claim → Person | attribution |
| `from_source` | Claim → Source | provenance |
| `about` | Claim → Subject | what it concerns |
| `cites_basis` | Claim → Source | a document the claim leans on |
| `supersedes` | Claim → Claim | an explicit replacement decision |
| `refutes` | Claim → Claim | a direct contradiction of another party |
| `supports` | Claim → Condition | feeds a condition's rule |
| `depends_on` | Condition → Condition | blocking dependency |
| `gates` | Condition → Decision | must be met before deciding |
| `exposes` | Claim → Decision | already true; not decidable |

`refutes` is what keeps Omar's 08:05:52 statement intact. It is three claims
(he requested room / he did not lay out the head / he requires the panel
location first) plus a `refutes` edge to Ben's 08:05:34 claim and a
`depends_on` to the access-hatch condition. A flat grouping would lose the
rebuttal.

### Files

```
data/people.json      7 people, capability sets
data/sources.json     7 packet sources + any absent cited sources
data/claims.json      the ledger
demo/rfi-04.json      the messy demo fixture (§8)
```

## 5 · Derivation

### Queues

Claims sharing a `subject` and `predicate` form a queue, ordered by
`stated_at` descending — **latest on top**. Every claim stays readable. The
head is what rules read.

| Mode | When | Rendered as |
|---|---|---|
| `SINGLE` | one claim | plain |
| `RESOLVED` | head declares `supersedes` | losers listed, marked superseded |
| `ASSUMED` | head disagrees with a lower claim, declares nothing | **⚠ preferred on recency alone**, outranked claims listed |

Nothing is ever deleted or mutated. Appending only ever adds.

### Condition status and basis

Two orthogonal fields, not one:

- **status** — `MET` · `UNMET` · `UNKNOWN`
- **basis** — `SETTLED` · `CONTESTED`

A condition's basis is `CONTESTED` if any claim in its support set is the head
of an `ASSUMED` queue, **or** if any condition it `depends_on` is contested.
This propagates in topological order, so taint reaches the recommendation.

This is the fix for the central risk: a conclusion can never render cleaner
than the evidence beneath it. `✓ met` and `✓* met — premise contested` are
visually distinct everywhere they appear, including in `/diff`.

`UNKNOWN` means the packet does not say. It is never rendered as `false`, and
absence of a record never becomes evidence of absence.

### Decision

The decision node has two kinds of inbound edge:

- `gates` — conditions ahead of Maya. `HOLD` if any is `UNMET` or `UNKNOWN`;
  `PROCEED` only when all are `MET`. Basis is `CONTESTED` if any contributing
  condition is.
- `exposes` — sunk facts behind her. The duct is already moved. The crew is
  held. $2,850 is pending with five stated exclusions and unknown true
  exposure. These are not decidable and must not be rendered as conditions —
  doing so implies she can still prevent them.

### Determinism

`conclusions = f(graph)` — a pure function. All iteration is over sorted node
ids; no dependence on dict or set ordering. Verified by shuffling input order
and asserting byte-identical output (§10).

**Scope of the guarantee, stated precisely:** determinism runs from the
*accepted ledger* to the conclusion. Reading a document into claims is a human
judgment step and is outside the guarantee. The README says this in these
words.

## 6 · Revisions and diff

Every `Source` carries a `revision`. `graph_at(n)` includes claims and sources
with `revision <= n`. Loading a new source increments the revision; earlier
revisions remain computable.

Loading a source whose id already exists is a validation error, not an
overwrite — corrections arrive as a new source that `supersedes` claims, never
as an edit to an existing one.

`/diff a b` compares `conclusions(a)` against `conclusions(b)` and reports:
condition status changes, basis changes, queue mode changes, superseded
claims, opened and closed unknowns, and the recommendation change. It is
computed, never authored — this is the brief's "evidence changed → here's what
moved" requirement, satisfied structurally.

## 7 · Interface

A slash-command REPL. Launch renders `/brief`.

| Command | Does |
|---|---|
| `/brief` | the decision brief — exposure, conditions, recommendation |
| `/why <id>` | one condition's full derivation path, claim by claim |
| `/evidence [subject]` | queues, latest on top, with resolution modes |
| `/conflicts` | every queue in `ASSUMED` or disputed state |
| `/unknowns` | everything the packet does not say, and why it matters |
| `/exposure` | sunk facts — what is already true |
| `/people` | the authority matrix |
| `/sources` | provenance, including absent cited sources |
| `/graph [id]` | dependency tree rooted at the decision |
| `/load <file>` | append a source, create a new revision, print the diff |
| `/diff [a] [b]` | movement between revisions (defaults to last two) |
| `/rev <n>` | render as of revision n |
| `/verify` | check every claim's `support` against its source document |
| `/watch` | toggle live reload |
| `/help`, `/quit` | |

Not a full-screen TUI: scrollback must survive, so before and after can both
be on screen when new evidence lands during the review.

### Live reload

`/watch` polls the mtime of `data/*.json` twice a second on a daemon thread.
On change: reload, revalidate, recompute, re-render the current view, and
print a compact delta. Editing the claims file in another window changes the
graph in place, with no command typed.

Validation failure prints the error and keeps the last good graph. A malformed
edit never leaves the tool in a broken state.

## 8 · The demo fixture

`demo/rfi-04.json` is deliberately **messy**, not clean. It approves one thing
while complicating another: Priya confirms the duct may shift, but fixes the
access panel at a location that tightens Omar's clearance, and states a
dimension that partially corroborates the 08:11:02 fragment without resolving
it.

Expected behaviour: one condition moves to `MET`, one becomes `CONTESTED`, one
unknown closes while a new one opens, and the recommendation stays `HOLD` for
a different reason than before. A fixture that resolved everything cleanly
would rehearse well and prove nothing.

## 9 · Rendering

Rich throughout. Status is never carried by colour alone — every state has a
glyph and a word (`✓ met`, `✓* met — premise contested`, `? unknown`,
`✗ unmet`, `⚠ assumed`). Citations are monospaced and always adjacent to the
claim they support. The `$2,850` figure never appears without its exclusions.

`ARCHITECTURE.md` is kept current as modules land and their tests pass, per
`CLAUDE.md`. It records what exists; this spec records what was designed.

Degradation path: if Rich rendering runs over budget it falls back to plain
tables. Nothing else is affected — the renderer holds no logic.

## 10 · Verification

`pytest`. Written before the code they cover.

| Test | Risk |
|---|---|
| `authorisation_unmet_above_threshold` | the core money rule |
| `owner_support_is_not_authorisation` | capability, not sentiment |
| `field_review_outcome_is_unknown_not_false` | absence is not negation |
| `schedule_row_does_not_assert_occurrence` | plan is not receipt |
| `caption_yields_only_a_statement_claim` | photographs prove nothing |
| `observation_cannot_gate_compliance` | the image constraint, enforced |
| `three_offsets_surface_as_conflict` | never emit an invented number |
| `explicit_supersession_retains_losers` | append-only holds |
| `taint_propagates_to_recommendation` | **the central guarantee** |
| `determinism_under_input_permutation` | **shuffle input, identical output** |
| `unintelligible_fragment_gates_nothing` | 08:11:02 neither used nor hidden |
| `cited_basis_absent_is_surfaced` | Nina's missing document |
| `rebuttal_edge_survives_queueing` | Omar's statement stays intact |
| `diff_reports_only_changed_conditions` | no phantom movement |
| `excluded_scope_keeps_cost_unknown` | $2,850 is not the exposure |

`/verify` is a runnable check, not a test: it greps each claim's `support`
text against the real source document and reports any that cannot be found.
It is how the ledger's accuracy is demonstrated rather than asserted.

**Left unverified:** whether the transcription is *complete* — no test can
prove a claim absent from the ledger should have been in it. This is stated in
the README as the failure that would concern us most.

## 11 · Budget

7.0 hours remain of 8.

| | |
|---|---|
| Skeleton, schema, validation | 0.5 |
| Claim transcription | 1.5 |
| Tests, failing first | 1.0 |
| Graph, queues, rules, taint | 1.5 |
| Rich rendering | 1.25 |
| Live reload | 0.25 |
| Demo fixture and rehearsal | 0.5 |
| README, decision journal, AI log | 1.0 |
| | **7.5** |

Over by 0.5h. **Cut order, in sequence:** `/graph` tree view → live reload →
Rich rendering degrades to plain tables → transcription narrows to
CA-118-bearing claims only, declared in the README.

**Never cut:** the rules, taint propagation, the tests, the demo rehearsal,
the decision journal.

## 12 · Deferred: agent-assisted extraction

Not built now. If time allows, `/propose <text-file>` stages 3–5
`ClaimProposal` rows — each with source locator, verbatim support, and
proposed nodes and edges — for human accept or reject before any `Claim` is
created. Agent output is a proposal, never evidence.

Rejected as a runtime feature: a sandboxed agent with shell access and package
installation, driven live during the review. It bets the review on
infrastructure that can stall, and buys into a 15% criterion at the cost of
the 20% + 20% that testing and evidence handling carry.

If built, image-derived claims are structurally restricted to `caption` and
`observation` kinds, carrying image ID and crop, enforced at insertion.

## 13 · Known limitations and failure modes

1. Transcription completeness is unverifiable. A claim omitted from the ledger
   is invisible to every check in the system. This is the most consequential
   weakness.
2. Determinism does not extend to reading documents (§5).
3. `ASSUMED` resolution follows recency, which is a heuristic. It is honoured
   because it was specified, made safe by propagating the taint, never by
   claiming the heuristic is correct.
4. The graph is small enough that no performance work exists. It would need
   rethinking at packet scale.
5. Conditions are hand-modelled. A genuinely new kind of question requires a
   new rule in code — a small edit, but code, not configuration.

## 14 · Open questions for the client

1. Will the new evidence at the review arrive as text, a file, or an image?
2. Is hand-transcription of packet facts into structured claims acceptable,
   given every claim cites its source locator?
3. For the bounded change, is a deterministic before/after conclusion diff
   sufficient, or is live editing of rule code expected?
