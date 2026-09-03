# Architecture — what exists

Design intent lives in `docs/superpowers/specs/2026-09-01-field-signal-design.md`.
This file records only what is built and passing.

## Layers

```
data/v1, v2, …     evidence — one complete ledger per revision
   │
model.py           typed nodes, schema validation, revision directories
   │
agent.py           uploads → the containerized extractor → a new revision
   │
rules.py           condition rules — pure functions, no I/O
graph.py           queues, topological derivation, taint propagation
   │
diff.py            conclusions(a) vs conclusions(b)
chat.py            one question, one model call, citations resolved
   │
render.py          Rich rendering — no logic
__main__.py        REPL, command dispatch, live reload
   │               web.py  ── JSON API + stdlib static server
   │                  │
   │               web/    ── Vue 3 front end
verify.py          claim support text vs the real documents (a check, not a layer)
```

Two front ends, one engine. The terminal and the browser both read
`conclusions()`; neither reaches a conclusion of its own.

`rules.py` and `graph.py` import nothing from a renderer and perform no I/O.
`conclusions(ledger)` is a pure function; every iteration is over sorted ids.

## Modules

### `field_signal/model.py`

Typed evidence nodes and validation. Knows what a claim *is*; derives nothing.

- `Person` — `id`, `name`, `org`, `role`, `capabilities`, `capability_basis`
  (the packet quote the capability set was read from). `can(capability)`.
- `Source` — `id`, `file`, `type`, `author`, `logical_time`, `locator_model`,
  `limitations`, `present`, `revision`. `present=False` records a document a
  claim leans on that is **not in the packet** (`S-ABS-RECOVERY`, `S-ABS-RCP`),
  so "cited basis absent" is a modelled state rather than a silent gap.
- `Claim` — `id`, `source`, `locator`, `stated_by` (nullable: some sources are
  documents, not people — inventing an author would be fabrication),
  `stated_at`, `kind`, `subject`, `predicate`, `value`, `support` (verbatim
  text), optional `cites_basis` / `supersedes` / `refutes`, `revision`.
  `queue_key` is `(subject, predicate)`; `gating_allowed()` is false for
  `observation` and `unintelligible`.
- `CLAIM_KINDS` — assertion, estimate, intent, plan, caption, observation,
  unintelligible. `NON_GATING_KINDS` — observation, unintelligible.
- `Ledger` — the three dicts plus `claim_list()` (sorted by `stated_at`, `id`,
  so nothing downstream depends on dict order), `by_subject()`, `author_of()`,
  `max_revision()`, `validate()`.
- `load_ledger(dir)` / `load_fixture(path)` — JSON in, `Ledger` out.
  `load_ledger()` with no argument is the latest revision.
- `ValidationError` carries every problem found, not the first.

**Revisions are directories.** `data/v1`, `data/v2`, … each hold a complete
`people.json` / `sources.json` / `claims.json`. Selecting a revision swaps the
whole ledger; nothing is filtered.

- `revision_numbers(root)`, `latest_revision(root)`, `revision_dir(root, n)`,
  `load_revision(root, n)`.
- `create_revision(root, base, added) -> int` — writes **base + added** as the
  next free number. Base is the revision you selected; the number is whatever
  is free. So adding evidence while looking at v1 when v2 exists produces v3
  containing v1 + new, *not* v2 + new. Added claims and sources are stamped
  with the new revision number. Nothing is written unless the merged ledger
  validates, so a bad extraction leaves existing revisions untouched.
- `_content_key(claim)` is `(source, locator, subject, predicate, value)`.
  Dedup uses it as well as the claim id, because the agent re-reads the packet
  on every run and does not reproduce ids — without it a second run would
  duplicate the whole ledger.
- Incoming people are matched only when name, organization, and role are all
  compatible. Name matching alone is deliberately insufficient: two people
  with the same name but different employers or designations remain separate.

### `field_signal/agent.py`

Uploads in, a new revision out. It reads no documents itself.

- `stage(paths, dir)` — copies files (recursing into directories) flat into one
  staging directory, suffixing basename collisions.
- `ingest(paths, root, base, runner)` — stages, calls `runner`, loads the
  produced delta ledger, keeps the uploads under `uploads/vN`, repoints each
  generated source at the stored copy so `/verify` can still read the file a
  claim came from, then calls `create_revision`. `runner` defaults to
  `examples/run_containerized.py` (Docker + `OPENAI_API_KEY`) and is injected
  in tests, so the seam is covered without either.
- Before invoking a context-aware runner, `_prepare_context` copies the exact
  selected revision into a temporary bundle and adds `ontology.json`, generated
  from `rules.INGESTION_CONTRACT`. The bundle is mounted read-only. The model
  can therefore reuse base ids and relationships while the permanent revision
  remains untouched.
- Agent output is a model's proposal: it lands in a **new** revision to be
  compared, never as an edit to one already read.

### `field_signal/rules.py`

`Status` (MET / UNMET / UNKNOWN), `Basis` (SETTLED / CONTESTED) and `Mode`
(SINGLE / RESOLVED / ASSUMED) live here so rules stay free of graph imports.

- `RuleResult(status, reason, support, notes)` — `support` holds the claim ids
  the rule actually read; those ids *are* the `supports` edges, materialised at
  derivation time. `notes` holds claim ids that are displayed but may never
  gate (image observations, the unintelligible fragment).
- `ConditionSpec(id, label, question, rule, depends_on, gates, introduced_by,
  introduced_by_claim)`.
  `introduced_by` names a source and `introduced_by_claim` can name a canonical
  claim queue that brings the condition into existence. Claim-based activation
  keeps source ids from becoming hidden business logic.
- `INGESTION_CONTRACT` describes every canonical queue consumed by the rules,
  plus only the kind-specific value constraints that deterministic comparisons
  require. It is application schema, not evidence or an expected answer, and
  contains no packet-specific people, dates, amounts, or outcomes.
- `CONDITIONS` — seven: `cost_authorised`, `access_panel_located`,
  `design_confirmed`, `sprinkler_clearance_confirmed`,
  `duct_position_established`, `field_review_outcome_recorded`, and
  `clearance_24in_maintained` (introduced by `S-05`, absent at v1).
  `cost_authorised` compares the quoted amount against the threshold claim, so
  it is driven by the packet rather than hard-coded to $2,850.
  `sprinkler_clearance_confirmed` fails closed: it is MET only with an explicit
  completed-layout assertion and explicit clearance-confirmed assertion;
  estimates, intentions, conditional statements, and missing evidence remain
  UNKNOWN.
- `EXPOSURES` — four sunk facts: work already performed, cost pending and
  larger than the quote, a crew held, the direction in force. Exposures are
  not conditions: rendering them as conditions would imply they are still
  preventable.

### `field_signal/graph.py`

- `build_queues(ledger)` — groups claims by `(subject, predicate)`, newest
  first. `superseded` collects the targets of `supersedes` edges within the
  queue; the head is the newest live claim. Mode is `ASSUMED` whenever any
  remaining live value disagrees with the head. It is `RESOLVED` when the head
  supersedes a claim in its own queue and no other live disagreement remains,
  otherwise `SINGLE`. Superseding one claim cannot hide other conflicts.
  Superseded claims stay in the queue — nothing is deleted or mutated.
- `Evidence` — the read-only facade rules see (`queue`, `head`, `claims`,
  `person`, `source`, `name`, `can`, `cite`).
- `_check_gating` — a rule returning an `observation` or `unintelligible`
  claim in `support` for a gating condition raises `ValidationError`. This is
  the image constraint, enforced rather than trusted.
- `conclusions(ledger, specs, exposures)` — evaluates conditions in
  `graphlib.TopologicalSorter` order, then:
  - **taint**: a condition is `CONTESTED` if any support claim is the head of
    an `ASSUMED` queue, or if any condition it depends on is contested;
  - **blocking**: a `MET` status whose dependency is not `MET` is downgraded to
    `UNKNOWN` with the blocker named, so a conclusion can never render cleaner
    than its premise;
  - the decision recommends `HOLD` unless every gating condition is `MET`, and
    carries the contested basis upward.
- `Conclusions.as_dict()` — sorted, primitive-only; the determinism test hashes
  it. Also carries `rebuttals` (refuted claim → refuting claims) and
  `absent_bases` (absent source → claims leaning on it).

### `field_signal/chat.py`

One model call per question, no retrieval layer. The whole evidence base for a
revision is ~8k tokens, so everything is handed to the model at once; the
previous design searched with tools and cost up to twelve sequential requests.

- `revision_context(ledgers, revision)` — the entire revision as one string:
  derived conclusions (authoritative), every claim with its verbatim support
  and locator, the authority matrix, and what moved from the previous revision.
  Depends only on the revision, so it is a stable prompt-cache prefix and goes
  first in the request. Revisions are immutable, so it is always valid.
- `resolve_citations(text, ledger)` — claim ids the model wrote, **resolved
  against the ledger**. An id that is not in the revision comes back as
  unknown and is reported as a caveat rather than rendered as evidence. The
  model cannot fabricate a citation past this point.
- `answer_question(..., on_delta=None)` — one call. Pass `on_delta` to stream.
  Model and effort are pinned (`gpt-5.5`, `low`): the deductions are already
  computed by `graph.py`, so this only reads and cites them.

**Measured** (5 identical questions, real API): median 1.6s to first token,
2.7s complete. One run in five cold-started and took 81s — provider variance,
not architecture, which is why the client gives up after two minutes rather
than spinning. Prompt-cache warming was built, measured, and **removed**: the
warm call is as slow as the question it was meant to speed up.

### `field_signal/diff.py`

`diff(a, b) -> tuple[Movement, ...]`, where `Movement(kind, id, before, after,
note)`. Kinds: `condition_status`, `condition_basis`, `condition_added`,
`condition_removed`, `support_added`, `unknown_opened`, `unknown_closed`,
`queue_mode`, `queue_head`, `queue_added`, `superseded`, `recommendation`,
`blocking_changed`, `decision_basis`.

`support_added` reports new evidence that bears on a conclusion **without**
changing it — the case that is easy to miss and easy to fake. Nothing that did
not move is reported.

### `field_signal/render.py`

Rich rendering only — every value is computed upstream. Status is never
carried by colour alone: each state has a glyph *and* a word (`✓ met`,
`✓* met — premise contested`, `? unknown`, `✗ unmet`, `⚠ assumed`), so the
brief survives a monochrome terminal. `$2,850` never appears without its
exclusions because the exposure text is one string, built once, in `rules.py`.

Views: `brief`, `why`, `evidence`, `conflicts`, `unknowns`, `exposure`,
`people`, `sources`, `graph_view`, `diff_view`, `verify_view`.

### `field_signal/__main__.py`

`App` holds the ledger, the list of loaded fixture paths, and one
`Conclusions` per revision, so earlier revisions stay computable. `reload()`
rebuilds from disk and **keeps the last good graph** if validation fails, so a
malformed edit never leaves the tool broken. `/watch` polls `data/*.json`
mtimes on a daemon thread and, on change, reloads, prints the diff, and
re-renders the current view.

Non-interactive form for scripting and screenshots:
`python -m field_signal "/brief" "/conflicts"`.

### `field_signal/verify.py`

`verify(ledger)` greps each claim's verbatim `support` against the real
document — PDFs via `pypdf`, the workbook via stdlib `zipfile` (rows joined
with `" | "`, matching how schedule claims are transcribed), JSON fixtures as
raw text. Whitespace is normalised because it is a PDF layout artefact;
wording is not. Image claims are reported as `skipped — image` rather than
silently passed. All 75 claims currently resolve to `found`.

### `field_signal/web.py`

The JSON API and a stdlib `ThreadingHTTPServer`. No web framework.

- `payload(ledger)` — serialises every revision's conclusions plus the ledger.
  Each condition carries a `display` string produced by `render.status_text`,
  so the browser shows exactly what the terminal shows.
- `_graph(conclusions, ledger)` — the node/link projection the 3D view draws.
  Node types: decision, condition, exposure, claim, source, person. Link kinds:
  gates, depends_on, supports, supports_exposure, noted, exposes, from_source,
  stated_by, cites_basis, supersedes, refutes. 63 nodes / 127 links at
  revision 0. Claims carry `gating_allowed`, so the CLI's image constraint is
  visible in the browser too.
- `Api` — every revision on disk plus which one is selected. `load()` and
  `ingest()` both create a new revision branched off the selected one.
  `load()` resolves a path inside the repository and refuses anything outside.
- `parse_multipart(body, content_type)` — files out of a multipart upload by
  splitting on the boundary directly; `email` and `cgi.FieldStorage` both
  mangle binary parts. An uploaded filename is reduced to its basename, so it
  can never choose a path.
- Routes: `GET /api/state`, `/api/verify`, `/api/fixtures`, `/api/diff?a&b`;
  `POST /api/load`, `/api/select`, `/api/agent` (multipart), `/api/chat`,
  `/api/chat/stream`. Everything else serves `web/dist` with an SPA fallback.
- `Api.chat_stream` runs the answerer on a thread and carries deltas out
  through a `queue.Queue`. Collecting them and yielding afterwards would
  buffer rather than stream, and would pass a naive test — so a test asserts
  the first delta arrives while the answerer is still blocked.
- `_sse` writes `event:`/`data:` frames and flushes each one; a reader that
  navigates away closes the pipe, which is caught and ignored.
- `payload(ledgers, selected)` sends every revision's conclusions, plus the
  selected revision's ledger — per-revision on purpose, so selecting v1 shows
  v1's claims everywhere.
- `serve()` runs it: `python -m field_signal.web`.

### `web/` — Vue 3 front end

Vite + Vue 3, pinned in `package.json` with a lockfile. `3d-force-graph` and
`three` for the graph; no UI framework, no CSS framework.

- `src/store.js` — fetches and indexes the payload. Holds no rules.
- `src/escape.js` — `escapeHtml` and `tooltip`. The graph tooltip is the only
  place this app builds HTML from ledger text, because `3d-force-graph`
  inserts `nodeLabel` as markup rather than as text. Ledger text is untrusted
  — the ingestion experiment derives claims from arbitrary packet documents —
  so it is escaped in this one place. Everything else goes through Vue's `{{ }}`
  interpolation, which escapes by default; there is no `v-html` in the app.
- `src/App.vue` — title-block header, sheet rail, hash routing (`#/graph`), so
  a view can be linked and survives a reload.
- `src/components/ChatWidget.vue` — the floating assistant: a circular button
  on every sheet, opening a panel that answers from the selected revision.
  Consumes `/api/chat/stream` as SSE, appending an empty reply and filling it
  as deltas arrive. On an unreachable server or a two-minute stall it drops the
  empty reply, keeps the question in the box, and says which happened.
- `src/views/` — `BriefView` (verdict, exposures, conditions with `/why`
  drill-in), `GraphView` (3D), `EvidenceView` (queues; also serves
  `/conflicts` via a prop), `UnknownsView`, `ProvenanceView` (people +
  sources), `AgentView` (drag-drop upload → a new revision), `RevisionsView`
  (load, diff, revision select), `VerifyView`.
- `src/components/` — `StatusChip` (glyph + word + contested wording, never
  colour alone), `ClaimRow` (verbatim text, author, citation, superseded and
  non-gating markers), `VerdictStamp`.
- Design: reversed blueprint — cyan and white linework on Prussian blue.
  Barlow Condensed for title-block labels, IBM Plex Sans for body, IBM Plex
  Mono for citations. The `.hatched` diagonal rule marks contested basis.
- `GraphView` lays the graph out as a DAG (`dagMode('bu')`) so the decision
  sits on top of what holds it up; `onDagError` is swallowed because
  `cites_basis` makes the graph cyclic. Labels are canvas sprites drawn in
  `labelFor`, which avoids a text-rendering dependency.

Build: `npm --prefix web install && npm --prefix web run build` → `web/dist`,
served by `field_signal/web.py`.

## Data

- `data/v1/people.json` — 7 people, capability sets, each cited to S-00.
- `data/v1/sources.json` — 9 packet sources + 2 absent-but-cited sources.
- `data/v1/claims.json` — the ledger, 75 claims. Every claim carries verbatim `support` and
  a locator in its source's own locator model (transcript → timestamp,
  schedule → activity ID, quote → line item, photo → image ID + region).
  `value` is *normalised* so agreement and disagreement compare cleanly
  (e.g. "Thursday morning" and "2026-09-17" both become `2026-09-17`);
  `support` stays verbatim, so every normalisation is auditable against the
  source. Normalisation is a transcription judgment and sits outside the
  determinism guarantee.
- `demo/rfi-04.json` — a *ledger* fixture (claims already extracted), clearly
  labelled as **not packet evidence**. `/load` turns it into a new revision.
- `demo/07_Project_Message_Thread_Followup.pdf` — a *source document*, in the
  packet's own visual style, for exercising `/agent` end to end. The agent
  extracts claims from it; `/load` cannot read it.
- `uploads/vN/` — files added through the agent, kept so `/verify` can still
  read the document a claim came from. Git-ignored.

## Standalone ingestion experiment

`examples/` is a standalone implementation for generating ledger JSON from an
arbitrary input directory. It can run independently with output in
`examples/data/`; the application also invokes its host launcher lazily through
`field_signal.agent`. It never imports packet facts into application code.

### Execution topology

```
host: examples/run_containerized.py
   │  builds and starts an unprivileged Docker container
   │  mounts packet/ read-only at /packet
   │  optionally mounts selected ledger + ontology read-only at /context
   ▼
container (UID 0): examples/container_agent.py
   │  OpenAI Responses API agent loop
   │  one custom function tool: shell
   ├── /packet  read-only evidence
   ├── /context read-only selected revision and consumer vocabulary
   ├── /work    temporary extraction files
   └── /output  staged JSON artifacts
   │
   ▼
host validator → atomic promotion to examples/data → reference comparison
```

The agent process and model-requested shell commands both run as root inside
the same disposable container. GPT-5.5 runs on OpenAI's servers; only the SDK,
agent loop, and tool executor run in Docker. The container is deliberately not
`--privileged`, has no Docker socket or host-home mount, uses
`no-new-privileges`, and has CPU, memory, and process limits. Its default
`bridge` network lets the agent call OpenAI and install packages.

The root `.env` selects `gpt-5.5` with `high` reasoning effort. The loop permits
up to 200 shell calls plus 8 independent-validation repair rounds. The model
receives one `shell` function with a command, timeout, and optional image
attachments; there are no format-specific model tools.

### Discovery and extraction

The host gives the agent only the task and mounted directories, with no extension
routing or reference-output hints. The generic prompt requires it to inventory
every file recursively, treat extensions as labels, inspect magic bytes and
container structure with tools such as `file --mime-type`, `xxd`, and
`unzip -l`, and then install suitable parsers. Images can be returned through
the same shell result only after their binary MIME type has been confirmed.

The prompt defines the `people.json`, `sources.json`, and `claims.json` keys,
types, evidence semantics, and completion checks. It contains no packet-specific
names, expected facts, expected counts, or decision answer. Packet content is
treated as evidence rather than instructions, and uploaded scripts, macros, and
executables must not be run.

For revision ingestion, `/context` contains the complete selected base plus
`ontology.json`. The agent emits only new packet-supported rows: it reuses base
person and source ids, points citations/supersessions/refutations at existing
ids, and maps updates to existing or consumer-defined queues. Ontology entries
do not cause claims to be emitted. This separates stable application vocabulary
from changing evidence without teaching the prompt a particular document.

`examples/ingest_agent.py` owns the prompt, Responses API tool loop, structural
validator, and atomic promotion helper. `examples/container_agent.py` owns the
root shell implementation and image attachment handling.
`examples/run_containerized.py` is the host launcher. `examples/evaluate.py`
compares generated output with the existing ledger only after the container has
stopped and the candidate files have passed validation.

### Validation and observed result

Output is written to a temporary staging directory first. Validation requires
exact top-level filenames and object keys, expected field types, unique ids,
valid person/source/claim references, valid relationship targets, ISO-8601
timestamps, known claim kinds, and non-empty verbatim support. Invalid output is
returned to the agent for repair. With context, validation also accepts
references to base ids, rejects attempts to redefine them, and enforces the
ontology's kind-specific normalized-value constraints. Only valid files are
promoted with `os.replace`.

The live `packet/` run completed and passed both container-side and host-side
validation. It generated 7 people, 13 sources, and 260 claims. Against the
hand-curated ledger it matched all 7 people by name, all 9 present sources by
file, and 73 of 75 normalized textual supports by exact match or containment.
The two uncovered reference supports are synthetic image-observation
placeholders rather than source text.

The generated files are not exact replicas of `data/`: the reference contains
7 people, 11 sources, and 75 claims. The generic agent extracted more sources
and split passages into more atomic claims, while the reference applies human
decisions about decision scope, claim granularity, ids, and normalized
vocabulary. The experiment therefore demonstrates strong packet discovery and
evidence coverage, but not deterministic reproduction of the curated ledger
from schema keys alone. Exact equivalence would require a general extraction
policy covering those normalization and scope decisions, followed by explicit
evaluation; it cannot be inferred reliably from file contents.

### Security boundary

The launcher passes `.env` into the container because the in-container OpenAI
client needs the API key. Shell child environments remove `OPENAI_API_KEY`, but
the client and shell share one root container, so this does not protect the key
from a hostile command that inspects another process. This layout is suitable
for the local experiment, not untrusted multi-tenant ingestion. A production
version should separate the API client and root shell into different containers
or expose a short-lived internal API proxy, install dependencies before mounting
sensitive inputs, and disable processing-network access afterward.

## Tests

`tests/test_model.py` — the packet ledger loads and validates; absent cited
sources are modelled, not dropped; an unknown person is a validation error; a
fixture is a partial ledger and only becomes evidence via a revision.

`tests/test_revisions.py` — the packet ships as v1; a new revision takes the
next free number and contains base + added; **branching from an older revision
keeps that revision as the base** (v1 selected with v2 present gives v3 = v1 +
new); added claims carry the new revision number; re-adding the same evidence
adds nothing, including when the agent renames every id; a revision that fails
validation is not written.

`tests/test_agent.py` — the extractor is stubbed. An upload becomes a new
revision and leaves the base untouched; uploads are kept and each source points
at the stored copy so `/verify` can still read it; files of any type stage flat
and colliding basenames both survive; branching uses the selected revision; a
context-aware runner receives an ephemeral copy of that revision plus the rule
ontology; an empty upload, a failing extractor and an invalid extraction each
leave the revisions alone.

`tests/test_derivation.py` — the risks that matter:

| Test | Risk it prevents |
|---|---|
| `authorisation_unmet_above_threshold` | the core money rule |
| `below_threshold_needs_no_written_authorisation` | the rule reads the threshold, it is not hard-coded |
| `owner_support_is_not_authorisation` | capability, not sentiment |
| `capability_is_read_from_the_packet_not_assumed` | authority is cited, not assumed |
| `field_review_outcome_is_unknown_not_false` | absence is not negation |
| `schedule_row_does_not_assert_occurrence` | a plan is not a receipt |
| `caption_yields_only_a_statement_claim` | a caption claims only what was said |
| `observation_cannot_gate_compliance` | the image constraint, enforced |
| `unintelligible_fragment_gates_nothing` | 08:11:02 neither used nor hidden |
| `three_offsets_surface_as_conflict` | never emit an invented number |
| `rebuttal_edge_survives_queueing` | Omar's rebuttal stays intact |
| `explicit_supersession_retains_losers` | append-only holds |
| `cited_basis_absent_is_surfaced` | the missing recovery schedule |
| `taint_propagates_to_recommendation` | **the central guarantee** |
| `dependency_taint_reaches_a_dependent_condition` | the deadlock is modelled |
| `excluded_scope_keeps_cost_unknown` | $2,850 is not the exposure |
| `determinism_under_input_permutation` | **shuffle input, identical output** |

`tests/test_diff.py` — identical revisions produce no movement; only changed
conditions are reported (the fire-protection question does not move and is not
reported as if it did); the fixture opens a question that did not previously
exist; supersession names both claims and keeps the loser readable; the
recommendation stays `HOLD` for a different set of reasons; new evidence on an
unchanged conclusion is still surfaced.

`tests/test_verify.py` — every transcribed claim is found in its source
document; image claims are skipped rather than silently passed; a drifted
support string *is* reported (the check has to be able to fail); whitespace is
normalised but wording is not.

`tests/test_cli.py` — reads rendered output, because that is what the user
sees. Borders are stripped and whitespace collapsed so the assertions test
content rather than column widths. Covers: the brief leads with the
recommendation and its blockers; status is never carried by colour alone; the
quote never appears without its exclusions; all three offsets appear and no
fourth number is invented; unknowns never render as "no"; `/why` separates
claims that gate from claims that may not; `/sources` flags documents cited
but not supplied; `/load` creates a revision and prints what moved; selecting a
revision changes every view; a new revision branches off the *selected* one
(v1 selected with v2 present gives v3); `/revisions` lists what is on disk;
`/agent` with no paths explains itself; a malformed edit keeps the last good
graph. Every CLI test runs against a copy of `data/`, never the repo's own.

`tests/test_web.py` — the payload is JSON-serialisable; every condition carries
status *and* basis together with the rendered display string; claims arrive
with author and citation resolved; non-gating claims are flagged; the graph
links a claim to the condition it gates and a condition to the decision; **no
image observation ever appears as a gating link**; absent sources are marked;
loading a fixture adds a revision and a diff; **selecting a revision swaps the
whole ledger**, so v1 does not show v2's claims; loading the same fixture twice
adds nothing, because dedup makes it a no-op; a path outside the repository is
refused; chat streams deltas and then a final payload, **with the first delta
arriving while the answerer is still working**; a mid-stream failure arrives as
an error event rather than a dead stream; a busy port explains itself instead
of tracebacking and `--port` picks another; the static handler serves
built assets, falls back to the SPA for client routes, and does not escape the
dist directory on traversal.

`tests/test_chat_oneshot.py` — the context carries every claim's verbatim
support and the derived conclusions; the prefix is stable per revision and does
not contain the question (or nothing is cacheable); **an invented claim id is
caught, not shown**; a claim mentioned twice is cited once; exactly one request
is made and no tools are offered; the revision blob leads and the question
comes last; model and effort are pinned; streaming emits deltas and still
resolves citations; empty questions and unknown revisions are refused before
any request is made.

`tests/` share one rule: a test copies `data/` before touching it. `/load` and
`/agent` write revision directories to disk, and a test that mutated the packet
would corrupt the evidence the whole product rests on.

`web/src/escape.test.mjs` (`npm --prefix web test`, Node's built-in runner, no
framework) — every tag- and attribute-opening character is escaped; `&` is
escaped first so entities are not double-decoded; ordinary claim text passes
through unchanged; a hostile claim produces exactly as many `<` and `"` as a
benign one, so no tag or attribute can be opened, while the hostile text stays
visible to the reader.

The Vue components have no unit tests. They were verified by driving headless
Chrome against the running server and reading the screenshots — a pass that
found two layout bugs and a caption describing the layout backwards. The XSS
fix was additionally verified end to end by loading a hostile claim into the
running server and confirming the rendered DOM contained escaped text and no
live element. That is still weaker than the Python coverage, and it is recorded
here rather than implied.

`examples/tests/test_ingest_agent.py` — the standalone prompt contains no known
packet answers; initial input contains no extension-based routing; generated
ledgers accept the generic schema and reject dangling or incorrectly typed
relationships; context validation accepts references to base records, rejects
redefinitions, and enforces consumer value constraints; the Docker command runs
as UID 0 without privileged mode and mounts `/packet` and optional `/context`
read-only; the Responses API loop uses GPT-5.5 at high effort and returns shell
tool output to the model.

Run: `.venv/bin/python -m pytest tests -q`

Run all production and experiment tests:
`.venv/bin/python -m pytest -q`
