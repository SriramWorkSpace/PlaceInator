# ADR 0002 — Deterministic engine, no LLM generation

- **Status:** Accepted
- **Date:** 2026-08-19

## Context

Several spec features read as generative: tailoring a LaTeX resume to a JD (§5),
drafting cold outreach (§6), and extracting fields from messy placement documents (§7).
The options were an LLM API for generation, a local LLM, or a fully deterministic
implementation.

The user chose **deterministic only**.

## Decision

No language model generates text anywhere in the application.

- **Matching** uses local sentence embeddings (`fastembed`, see
  [ADR 0005](./0005-fastembed-no-pytorch.md)) plus a curated skill taxonomy.
- **Resume tailoring** reorders, selects, and emphasizes existing content. It re-emits
  the *original* source spans byte-for-byte and never rewrites a bullet.
- **Cold outreach** uses Jinja2 templates filled from the match explanation's top
  contributing chunks.
- **Placement extraction** uses keyword rules, a header-synonym dictionary, `rapidfuzz`
  fuzzy matching, and `dateparser`.

## Consequences

**This narrows spec §5, and that limit must stay visible.** Spec lines 327-329 ask the
system to "restructure bullet points" and "improve information density". Neither is
achievable deterministically. The Tailor UI must state plainly that it reorders and
selects but never rewrites, so the constraint is communicated rather than quietly
under-delivered.

**In exchange, the guarantee gets stronger.** Spec line 333 requires that the system
never invent qualifications, experience, projects, skills, or achievements. Because the
LaTeX emitter works by splicing byte ranges out of the user's own source, invention is
**structurally impossible** rather than merely instructed against. That is a materially
better property than prompting a model not to hallucinate, and it makes the round-trip
test (parse → emit unchanged, byte-for-byte) a meaningful correctness gate.

**Other consequences**

- Fully offline, zero API cost, no user data leaves the machine.
- Latency is bounded and predictable (see the budget in
  [architecture.md](../architecture.md)).
- Every score is explainable by construction: `MatchResult.explanation` records each
  component's value, weight, and top contributing chunk pairs.
- **`placeinator/skills/taxonomy.json` becomes the critical path.** Without a model to
  paper over vocabulary gaps, this hand-curated alias map *is* the semantic backbone of
  skill matching, gap analysis, and filtering. Matching quality is capped by it, so it
  is a first-class deliverable with its own tests, not a lookup table to be filled in
  hastily.
