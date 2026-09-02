# AI work log

## Tools and models

| Tool | Used for |
|---|---|
| Claude Opus 5, via Claude Code (CLI) | The whole build: packet reading, design, transcription, code, tests, documentation |
| `pypdf`, stdlib `zipfile` | Extracting text from the packet PDFs and the workbook so claims could be transcribed verbatim and later re-checked |

No hosted API beyond the Claude Code session. No network calls at runtime. No
model in the product's runtime path — that was a deliberate product decision,
not a limitation (see below).

## What was delegated, and what was not

**Delegated:** reading and summarising the packet into plain English; drafting
the design spec; writing the module code and the Rich rendering; drafting test
names and bodies; writing this documentation.

**Not delegated — decided by hand, then implemented:**

- Which user and which problem. The AI's first framing was the schedule-risk
  reading; the authority reading came from reading the primer's working rules
  directly.
- The claim taxonomy (`assertion` / `estimate` / `intent` / `plan` /
  `caption` / `observation` / `unintelligible`) and which kinds may gate.
- The status/basis split and the taint rule. This is the product's core
  guarantee and it was specified before any code existed.
- Every one of the 75 claims' `subject`, `predicate`, `value` and `kind`. The
  extraction of source *text* was mechanical; deciding what each sentence
  claims, and how strong that claim is, was not.

## Where AI materially changed my thinking

1. **Modelling the absent documents as sources.** Nina's "approved recovery
   schedule" and Priya's reflected ceiling plan are both cited and both
   missing. The prompt that produced `present: false` on a `Source` turned
   "cited basis absent" from something a careful reader might notice into a
   state the system reports on its own. That idea improved the product.
2. **`support_added` in the diff.** New evidence that lands on a conclusion
   *without changing it* is the case that is easiest to fake in a demo and
   most reassuring to a user. It was not in my first list of movement kinds.
3. **Introducing a condition with new evidence** (`introduced_by`). Being able
   to say "this question did not exist an hour ago" is a stronger
   demonstration than any status flip.

## One AI output I rejected

**Rejected: reconciling the duct offset.** An early draft of the derivation
proposed treating "about 6 in", "six or eight inches" and "approximately 6–12
inches" as one estimate with a range of 6–12 inches, and reporting "≈6–12 in
west". It is superficially reasonable — the values do overlap. It is also
exactly the failure the packet is built to catch: it invents a project fact by
merging three separate claims by one person made at three different times for
three different purposes (a text to a colleague, a remark in a meeting, a
priced scope of work), none of which is a measurement. I replaced it with a
rule that prints all three with their citations, refuses to derive a figure,
and marks everything downstream `premise contested`. The test
`three_offsets_surface_as_conflict` locks that in.

**Corrected, smaller:** the first version of the exposure text cited Ben's
Monday 08:06:28 restatement as the source for a move that happened on Sunday.
Both claims say the same thing, so nothing was factually wrong, but the
citation pointed at the wrong event. Now it cites the earliest report.

## An AI proposal I rejected on product grounds

A sandboxed agent with shell access, driven live during the review, extracting
claims from the PDFs on demand. It demos well. It also bets the review on
infrastructure that can stall, and — more importantly — it would put a model
between the evidence and the conclusion, forfeiting the one claim this product
makes: *this brief is derived deterministically from cited evidence, and you
can check every line of it.* Agent-assisted extraction belongs behind a
`/propose` staging step where a human accepts or rejects each claim before it
becomes evidence. That is written up in the spec as deferred, not built.

## How generated code and conclusions were evaluated

- **Tests before code**, per the project rules — genuinely for the model,
  graph, rules and diff layers. **Not** for `render.py` and `verify.py`: I
  wrote those modules first and their tests afterwards. Doing it in the wrong
  order let a real defect survive (`/conflicts` never said the head won on
  recency alone), which the tests then caught. Recorded here rather than
  tidied away.
- **`/verify` as an independent check on the AI's own transcription.** Every
  claim stores the verbatim text it was read from, and `/verify` greps that
  text against the real PDF or workbook. All 75 resolve to `found`. This is
  the one control that would catch the AI having paraphrased, softened or
  invented a quotation — the highest-probability AI failure in this exercise.
  `test_a_drifted_support_string_is_reported` proves the check can fail.
- **The determinism test** shuffles the ledger and asserts byte-identical
  conclusions, which catches any accidental dependence on dict ordering
  introduced while editing.
- **The images were read by me directly**, not summarised at second hand,
  before writing the two `observation` claims about P-02.

## What I do not fully understand or could not verify

- **Whether the transcription is complete.** The AI and I read every source,
  but no check proves a claim absent from the ledger should have been in it.
  This is the failure that would concern me most and it is stated in the
  README rather than hidden.
- **PDF text extraction fidelity.** `pypdf` reproduces these documents
  cleanly, and `/verify` passing on all 75 claims is evidence that what I
  transcribed matches what `pypdf` sees. It is *not* independent evidence that
  `pypdf` sees what a human reader sees. For the huddle transcript and the
  quote I checked the extracted text against the rendered PDF by eye; I did
  not do that line-by-line for the schedule workbook.
- **The 08:11:02 fragment.** "… access … twenty-four … north …" may be a 24
  inch clearance requirement, which would matter enormously. It is not
  recoverable. The demo fixture deliberately introduces a 24 in figure from a
  different source, and the product still refuses to treat the fragment as
  corroboration.

## Where AI introduced risk

1. **Fluency.** Generated reason strings read authoritatively. The mitigation
   is that every reason is assembled from claim values and citations that are
   themselves checkable, and that no reason may cite a claim the rule did not
   read.
2. **Plausible over-reach in transcription.** The pressure to make a sentence
   into a tidy claim is the pressure to sharpen it. `value` normalisation is
   where this risk lives — "Thursday morning" becoming `2026-09-17` is safe,
   but the mechanism could be used to flatten a real disagreement. `support`
   stays verbatim precisely so that every normalisation can be second-guessed.
3. **Speed.** The claim ledger was produced fast enough that it was not
   painful to get it wrong three times. Cheap rework encourages skipping the
   design step, which is what happened.
