# Architecture — what exists

Design intent lives in `docs/superpowers/specs/2026-09-01-field-signal-design.md`.
This file records only what is built and passing.

## Layers

```
data/*.json        evidence — the only source of project facts
   │
model.py           typed nodes, schema validation, revision slicing
   │
rules.py           condition rules — pure functions, no I/O
graph.py           queues, topological derivation, taint propagation
   │
diff.py            conclusions(a) vs conclusions(b)
   │
render.py          Rich rendering — no logic
__main__.py        REPL, command dispatch, live reload
verify.py          claim support text vs the real documents (a check, not a layer)
```

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
  `at(revision)` (revision slice), `merge(other, revision)` (append-only; a
  repeated source or claim id raises rather than overwriting), `validate()`.
- `load_ledger(dir)` / `load_fixture(path)` — JSON in, `Ledger` out.
- `ValidationError` carries every problem found, not the first.

### `field_signal/rules.py`

`Status` (MET / UNMET / UNKNOWN), `Basis` (SETTLED / CONTESTED) and `Mode`
(SINGLE / RESOLVED / ASSUMED) live here so rules stay free of graph imports.

- `RuleResult(status, reason, support, notes)` — `support` holds the claim ids
  the rule actually read; those ids *are* the `supports` edges, materialised at
  derivation time. `notes` holds claim ids that are displayed but may never
  gate (image observations, the unintelligible fragment).
- `ConditionSpec(id, label, question, rule, depends_on, gates, introduced_by)`.
  `introduced_by` names the source that brings the condition into existence, so
  new evidence can add a question that did not previously exist.
- `CONDITIONS` — seven: `cost_authorised`, `access_panel_located`,
  `design_confirmed`, `sprinkler_clearance_confirmed`,
  `duct_position_established`, `field_review_outcome_recorded`, and
  `clearance_24in_maintained` (introduced by `S-05`, absent at revision 0).
  `cost_authorised` compares the quoted amount against the threshold claim, so
  it is driven by the packet rather than hard-coded to $2,850.
- `EXPOSURES` — four sunk facts: work already performed, cost pending and
  larger than the quote, a crew held, the direction in force. Exposures are
  not conditions: rendering them as conditions would imply they are still
  preventable.

### `field_signal/graph.py`

- `build_queues(ledger)` — groups claims by `(subject, predicate)`, newest
  first. `superseded` collects the targets of `supersedes` edges within the
  queue; the head is the newest live claim. Mode is `RESOLVED` when the head
  supersedes a claim in its own queue, `ASSUMED` when a live claim disagrees
  with the head and nothing declares a resolution, otherwise `SINGLE`.
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

## Data

- `data/people.json` — 7 people, capability sets, each cited to S-00.
- `data/sources.json` — 9 packet sources + 2 absent-but-cited sources.
- `data/claims.json` — the ledger. Every claim carries verbatim `support` and
  a locator in its source's own locator model (transcript → timestamp,
  schedule → activity ID, quote → line item, photo → image ID + region).
  `value` is *normalised* so agreement and disagreement compare cleanly
  (e.g. "Thursday morning" and "2026-09-17" both become `2026-09-17`);
  `support` stays verbatim, so every normalisation is auditable against the
  source. Normalisation is a transcription judgment and sits outside the
  determinism guarantee.
- `demo/rfi-04.json` — demo fixture, clearly labelled as **not packet
  evidence**.

## Tests

`tests/test_model.py` — the packet ledger loads and validates; absent cited
sources are modelled, not dropped; an unknown person is a validation error;
re-loading an existing source id is refused (corrections must arrive as a new
source); a revision slice excludes later sources.

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
but not supplied; `/load` creates a revision and prints what moved; earlier
revisions stay computable; a malformed edit keeps the last good graph.

Run: `.venv/bin/python -m pytest tests -q`
