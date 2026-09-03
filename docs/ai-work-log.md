# AI work log

## Tools and models

| Tool | Used for |
|---|---|
| Claude Opus 5, via Claude Code (CLI) | The whole build: packet reading, design, transcription, code, tests, documentation |
| Codex (GPT-5.x), via the Codex plugin | Delegated: rebuilding the graph view for legibility, and a first pass at the chat backend |
| `gpt-5.5` in a Docker container | The ingestion agent that turns uploaded documents into claims (`examples/`) |
| `gpt-5.5`, one call per question | The assistant that answers from a selected revision |
| `pypdf`, stdlib `zipfile` | Extracting text from the packet PDFs and the workbook so claims could be transcribed verbatim and later re-checked |

**This changed, and the change is the most important thing in this log.** The
original build had no model in the runtime path at all — deliberately, because
the product's claim is "derived deterministically from cited evidence, and you
can check every line". Two models are now in that path: one reads uploaded
documents into claims, one answers questions about a revision.

The claim survives because neither is allowed near the derivation:

* The **derivation is still model-free.** `graph.py` decides what is met,
  unmet, unknown and contested. Nothing a model produces changes how a
  conclusion is reached — only what evidence exists to reach it from.
* Extracted claims are **evidence, checkable like any other**: verbatim support,
  a locator, `/verify` against the stored upload, and they land in a *new*
  revision so the previous one stays intact for comparison.
* The assistant **cannot invent a citation**: claim ids it writes are resolved
  against the ledger and unknown ones are reported as unsupported.

What is genuinely weaker than before: a model now decides what a document
says. That is stated as a limitation in the README rather than argued away.

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

## Delegating to Codex, and what came back

Two pieces were handed to Codex with a written brief: the 3D graph was hard to
read and hard to zoom, and the chat needed a backend. Both came back working.
Two things are worth recording.

Its ingestion fix — giving the extractor the canonical queue vocabulary — was
the right diagnosis of a bug I had not solved, and I verified it against the
real runs rather than taking it on trust: v1→v2 and v1→v3 moved nothing but "a
new subject appeared" 49 and 46 times; v1→v4 moved for real. I specifically
checked it had not over-resolved, because handing a model the vocabulary could
make it force evidence into predicates. It had not.

Its chat backend worked on the first try — correct answers with real citations
— but was shaped as a page you navigate to, which was wrong for the job. I
rewrote the interface and later the whole retrieval approach. Working code in
the wrong shape is still the expensive kind of wrong.

## Where I was confidently wrong

**The chat latency, twice.** I diagnosed the tool loop as the bottleneck and
said so with more confidence than the evidence supported. Rewriting to one shot
did not fix it — 92s became 92s. I then built prompt-cache warming on the same
kind of reasoning, wired it through the API and the widget, and measured: still
59s, because the warm call is as slow as the question. A cache-busted cold call
then returned in under seven seconds, which showed the original numbers were
provider variance and neither theory was right.

I deleted the warming. The one-shot rewrite stayed, but on a different
argument than the one I started with: one request instead of up to twelve is
simpler and less exposed to a slow round trip.

The lesson recorded rather than smoothed over: I measured *after* forming the
theory both times. The five-run benchmark that finally settled it (median 1.6s,
one run at 81s) would have taken two minutes at the start.

## One AI output I rejected, more recently

The ingestion agent produced `p_maya` — a person called "Maya" with the
capability `authorize_or_withhold_ca118` — alongside the packet's `maya`, "Maya
Chen", who holds `authorise_added_cost` because the primer says so. Accepting
it would have let a model grant contractual authority by naming someone. People
are now matched by name at merge time and **the existing person always wins**;
the model's capability strings are discarded. This is the same principle as
rejecting the merged duct offset, in a place I had not thought to defend.

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
4. **A model now writes evidence.** The ingestion agent produces claims that
   enter the ledger. Every one carries verbatim support checkable by `/verify`
   against the uploaded file, and lands in a new revision to be compared rather
   than editing an existing one — but nothing checks that it read the document
   *correctly*, or that it did not miss a claim. This is the transcription
   completeness gap from the original build, now automated and therefore easier
   to trust than it has earned.
5. **A model now answers questions about the evidence.** Its citations are
   resolved against the ledger, so it cannot invent one, and the conclusions it
   reads are deterministic. Nothing checks that the prose it wrote around them
   is a fair summary. Every answer is one click from the claims it cited, which
   is the mitigation rather than a fix.
