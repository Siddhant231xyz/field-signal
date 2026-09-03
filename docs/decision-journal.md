# Decision journal

## The hypothesis I started with, and how it changed

I opened the packet expecting a **schedule-risk** problem. The urgency is
loud: inspection Thursday, close-in Friday, opening 12 October, and a foreman
saying he loses his crew. The obvious product is a critical-path tool for Luis
Ortega, the superintendent.

Reading the primer's working rules changed it. Luis "does not approve added
subcontract cost". Tasha Reed "does not directly authorise subcontractor
changes". Priya Shah "does not approve contractor pricing". Three of the four
people pushing the decision forward are structurally unable to make it. The
one person who can — Maya Chen — is the one being pushed.

So the problem is not schedule. It is that **work has been done, money is
owed, and nobody with authority has approved anything** — while the record
reads as though momentum equals agreement. Tasha's "I am comfortable with a
small field fix" is the most dangerous sentence in the packet: it is warm,
senior, and contractually worth nothing.

I rejected the Luis tool deliberately. A tool serving him would optimise
sequence, and the cost of being wrong is that it becomes a well-presented
nudge toward the wrong authority path — exactly the failure the packet is
built to catch.

## The evidence insight that shaped the build

The physical deadlock is small and completely unowned:

- Priya will not confirm the duct until she is told where the access panel goes
- Omar will not finalise the sprinkler head until he sees where the panel ends up
- Ben cannot make his final connection until both land

A piece of ceiling trim **nobody has drawn** is holding two foremen and a
$2,850 decision. The packet never resolves it. That is an unknown, not an
inference, and the product had to be able to say so without implying "no".

That forced the central design choice: **status and basis are two fields, not
one.** A condition is `met` / `unmet` / `unknown`, and separately `settled` or
`contested`. Without that split I would have had to choose between hiding
disagreement and rendering everything as doubt.

## Questions and research that changed the work

- *Can Tasha authorise this?* The primer answers it in one line, and that line
  restructured the whole product around a capability model rather than a
  sentiment model.
- *Is "six inches" a fact?* Three sources, three numbers ("about 6 in", "six
  or eight inches", "approximately 6–12 inches"), all from Ben, none measured.
  I looked at P-02 to see whether the photograph resolved it: there is no
  scale reference, tape or datum in frame. It resolves nothing. That became a
  claim in its own right and a test named `three_offsets_surface_as_conflict`.
- *What is the real cost?* $2,850 excludes drywall patching, painting,
  fire-protection rework, redesign and permit revision. Two of those
  exclusions are exactly what the open questions could trigger. The quote is
  a floor, not an estimate — so the tool never prints it without them.
- Domain reading (soffit, rough-in, close-in, reflected ceiling plan, access
  panel) went into `PACKET_EXPLAINED.md` first. None of it is asserted as a
  project fact; it only made the packet legible.

## Alternatives considered and rejected

| Rejected | Why |
|---|---|
| Schedule tool for Luis | He cannot approve cost; it would nudge toward the wrong authority |
| An LLM in the runtime path | The claim I want to make is "this is derived, deterministically, from cited evidence". A model in that path forfeits it |
| Confidence scores per claim | A number invites arithmetic on things that are not commensurable, and hides the argument. A named conflict with both citations is more useful and more honest |
| Silently reconciling the three offsets | This is the exact failure being tested for |
| Auto-ingesting the PDFs | Extraction errors would be indistinguishable from evidence. Hand-transcription with verbatim `support` plus a `/verify` grep is slower and checkable |

## What surprised me

**The photograph is the trap, not the evidence.** I expected P-02 to help. It
shows an unterminated flex duct with no diffuser fitted — consistent with
Ben's "reversible" — but it proves nothing about authority, dimension or
compliance, and its caption is Ben describing his own work. It ended up as two
`observation` claims that the graph *refuses* to let gate anything.

**Nobody in the packet behaves badly.** Ben unblocked the framers, Luis
protected the schedule, Tasha protected the opening, Omar refused to commit to
what he could not see, Priya asked a fair question. The exposure is entirely
emergent. That is why a tool that summarises tone would miss it and a tool
that models authority catches it.

**Writing the CLI tests found a real gap.** `/conflicts` displayed the
competing claims but never said the head won on recency alone — the one thing
the reader most needs to know. Rendering had quietly become a place where the
product was less honest than the graph.

## Where I got it wrong, mid-build

I transcribed all 75 claims **before** writing the queue code, then had to
edit `data/claims.json` in three further passes: normalising `value` so
agreeing statements stopped registering as conflicts, shortening locators once
I saw real citations, and removing layout artefacts. Writing
`three_offsets_surface_as_conflict` first would have forced the
`value`/`support` split up front and made two of those passes unnecessary.
Same for the render layer: I wrote `render.py` before its tests and had to go
back — which is how the `/conflicts` gap survived as long as it did.

## What the work became after the timebox

The eight hours produced the CLI. Everything after it was requested and is
recorded here so the journal reflects the real path, not a tidy version of it.

**A web front end.** Same engine, second reader. All derivation stays in
Python; the browser is handed `conclusions()` and the condition status strings
are generated by `render.py`, so the two front ends cannot drift apart on what
a status looks like. The graph became a 3D view of the same edges the rules
reason over.

**Revisions became directories.** `data/v1`, `data/v2`, … each a complete
ledger. Selecting one swaps everything. A new revision is built from the
*selected* revision plus what was added and takes the next free number, so
going back to v1 and adding evidence branches from there without destroying
v2. This replaced `Ledger.merge`/`Ledger.at`, which were deleted.

**An ingestion agent.** Uploads of any type are read inside a disposable
container and become a new revision. Two real bugs came out of running it:

* It invented parallel identities — `p_maya` "Maya" beside `maya` "Maya Chen",
  with fabricated capabilities like `authorize_or_withhold_ca118`. Maya's new
  messages were attributed to someone without `authorise_added_cost`, silently
  splitting the authority model in two. `create_revision` now matches people by
  name and the *existing* person always wins: capabilities come from the
  packet's working rules, never from a model.
* Its first runs produced diffs that were 100% "a new subject appeared" — 49
  and 46 of them — because it invented its own subject/predicate names and none
  of them met a rule. Giving the extractor the canonical queue vocabulary fixed
  it; the run after that closed three unknowns, opened one, and left
  `cost_authorised` unmet and the duct offset contested. It did not over-resolve.

**An assistant.** One model call per question, handed the whole revision. The
interesting part is not the chat — it is that claim ids it writes are resolved
against the ledger, so a fabricated citation is caught rather than displayed.

## Unresolved assumptions

1. **Recency as the default head.** Where claims disagree and nothing declares
   a resolution, the latest wins. This is a heuristic. I did not try to make
   it correct; I made it *visible* by propagating contested basis to the
   recommendation.
2. **`value` normalisation is a reading judgment.** "Thursday morning" becomes
   `2026-09-17`. Verbatim text is always kept and always checkable, but the
   normalisation itself is outside the determinism guarantee.
3. **Seven conditions are hand-modelled.** They are the questions I judged
   consequential. A different reader might add one — and would have to write
   code to do it.

## Two more things I got wrong

**I diagnosed the chat latency wrong, twice.** I was confident the tool loop
was the bottleneck and said so. After rewriting to one shot, the same question
still took 92s. Then I built prompt-cache warming, wired it into the widget,
and measured: still 59s, because the warm call is as slow as the question it
was meant to speed up. Cache-busted cold calls came back in under seven
seconds, which showed the original numbers were provider variance all along. I
deleted the warming rather than ship a feature that only looked like a fix.

The one-shot rewrite stayed anyway — one request instead of up to twelve is
simpler and less exposed to a slow round trip — but it was kept for a reason I
could defend afterwards, not the reason I started with.

**My first streaming implementation did not stream.** It collected every delta
and yielded them once the answer was complete. It passed the test I had
written. The test now asserts the first delta arrives *while the answerer is
still blocked*, which failed until it was done properly with a thread and a
queue.

## What I would build next

1. `/propose <file>` — staged claim proposals from an agent, each with source
   locator and verbatim support, for human accept or reject. Agent output as a
   proposal, never as evidence.
2. A completeness check: sweep the source text for sentences no claim cites,
   and show what the ledger never looked at. It attacks the failure I most
   fear and cannot currently test.
3. Owner-facing framing of exposure — the packet's cost story is unfinished,
   and Tasha is being asked to feel comfortable about a number that is not the
   number.

## Time allocation (approximate, 8 hours)

| Activity | Hours |
|---|---|
| Reading the packet, domain research, plain-English write-up | 1.0 |
| Evidence map: deadlock, authority matrix, conflicts, timeline | 0.5 |
| Design spec | 1.0 |
| Claim transcription (75 claims) and rework | 1.75 |
| Model, graph, rules and their tests | 1.5 |
| Diff and the demo fixture | 0.5 |
| Rendering, REPL, `/verify` and their tests | 1.25 |
| README, journal, AI log, architecture upkeep | 0.5 |

Work after the eight-hour exercise — web front end, revision directories,
ingestion agent, assistant — was separately requested and is not counted here.
