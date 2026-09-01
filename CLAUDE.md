# Field Signal — project rules

## Product requirement (from the brief, non-negotiable)

The product must make it possible to distinguish what is **supported** by the
supplied material from what is **inferred** or **unknown**. It must never
silently present an unsupported or contradicted claim as fact. It must
demonstrate what happens when one consequential source changes, is corrected,
or is contradicted.

Concretely: the artefact needs a visible **"the evidence changed → here's what
moved"** behaviour. Everything else — feature, interface, architecture,
workflow, interpretation — is our choice.

Implication: evidence lives as **data**, not as prose in templates. Conclusions
are derived at runtime so a new or corrected source can be dropped in and the
affected conclusions visibly change (including flipping to superseded or
contradicted). Old claims stay visible with both citations; never delete
history.

## Evidence handling

- `packet/` is the only source of project facts. Nothing outside it is a fact
  about HC-17.
- Never fabricate people, dates, approvals, measurements or costs.
- The packet is contradictory by design. Never silently reconcile a conflict —
  surface both sides with citations.
- A statement in a source is a claim by a named author at a time, not a
  verified fact. Model it that way.
- Absence of evidence is `unknown`, not `false`.
- Photos prove nothing about intent, authority, completion, dimensions or code
  compliance. Captions are the submitter's claims.
- Schedule dates are plan, not proof that work occurred.
- Cite by each source's locator: transcript → timestamp, schedule → activity
  ID, photo → image ID + region, quote → line item, messages → message
  timestamp.

## Working rules

- Use git. Commit locally as work progresses — meaningful history is a
  deliverable, don't backfill it at the end.
- Write code test-driven: failing test first, then the code that passes it.
- No secrets, personal data, or real external actions in the repo.
