# Architecture — what exists

Design intent lives in `docs/superpowers/specs/2026-09-01-field-signal-design.md`.
This file records only what is built and passing.

## Layers

```
data/*.json        evidence — the only source of project facts
   │
model.py           typed nodes, schema validation, revision slicing
```

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

## Data

- `data/people.json` — 7 people, capability sets, each cited to S-00.
- `data/sources.json` — 9 packet sources + 2 absent-but-cited sources.
- `data/claims.json` — the ledger. Every claim carries verbatim `support` and
  a locator in its source's own locator model (transcript → timestamp,
  schedule → activity ID, quote → line item, photo → image ID + region).
- `demo/rfi-04.json` — demo fixture, clearly labelled as **not packet
  evidence**.

## Tests

`tests/test_model.py` — the packet ledger loads and validates; absent cited
sources are modelled, not dropped; an unknown person is a validation error;
re-loading an existing source id is refused (corrections must arrive as a new
source); a revision slice excludes later sources.

Run: `.venv/bin/python -m pytest tests -q`
