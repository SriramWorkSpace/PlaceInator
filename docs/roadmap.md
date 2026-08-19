# Roadmap

Milestones for building out [specification.md](./specification.md). Design rationale
lives in [architecture.md](./architecture.md) and [decisions/](./decisions/).

## M0 — Foundation

*Substantially complete.*

Done:

- Python sidecar with ephemeral-port handshake and bearer-token auth
- Full ORM schema (9 tables), Alembic-managed, initial revision generated
- React + TypeScript + Vite + Tailwind frontend with a typed API client
- App shell with seven routes and empty states
- CI, documentation set, repository structure

Remaining:

- Install Rust + MSVC build tools **(the only outstanding blocker)**
- Scaffold `src-tauri/`; implement sidecar supervision: spawn, read the handshake line,
  inject into the WebView, terminate on exit
- Wire PyInstaller onedir to `bundle.externalBin`

**Prove the packaged build now, not at M6.** onnxruntime's native libraries are the
likeliest packaging problem, so add `fastembed` to the bundle test as soon as M1
introduces it.

## M1 — Profile, Resume, and Matching

The chosen first milestone; everything else depends on it.

- Onboarding wizard (spec §1): profile, career preferences, employment constraints
- Resume library, upload, and parsing (PDF / DOCX / `.tex`)
- `placeinator/skills/taxonomy.json` — seed ~600 entries with aliases and category tags
- `fastembed` integration and `placeinator/matching/vectors.py`
- Chunking, component scores, ranking, and `MatchResult.explanation`
- Resume recommendation with user override
- The `manual` job source, so the loop is exercisable end to end

**Done when:** add 3 resumes → paste a JD → get a ranked recommendation with a readable
explanation, in under 2 seconds.

> `taxonomy.json` is the critical path. With no LLM, it *is* the semantic backbone of
> skill matching, gap analysis, and filtering — matching quality is capped by it. Treat
> it as a first-class deliverable with its own tests.

## M2 — Job intelligence

- Source adapters in expected-success order: `indeed`, `ats_feed`, `linkedin`, `naukri`
  (see [ADR 0003](./decisions/0003-job-source-boundary.md))
- Shared adapter infrastructure: `robots.txt`, rate limiting, backoff, caching
- Job normalization, hard-constraint filtering, soft-preference scoring
- Jobs UI with ranked list and filter explanations
- Personalized notifications that state *why* an opportunity is relevant

## M3 — LaTeX resume tailoring

- `pylatexenc` parser retaining source spans
- **Round-trip gate:** identity reorder reproduces input byte-for-byte. This blocks the
  milestone.
- Unit scoring, reordering policy, splice emitter
- Change log: moved, de-emphasized, requirements matched, requirements missing, and
  what was deliberately not added
- Three-pane Tailor workspace (JD │ LaTeX diff │ changes), Monaco lazy-loaded
- Optional PDF compile, degrading gracefully when no TeX distribution is installed

## M4 — Placement automation

- Gmail read-only OAuth (loopback flow), incremental fetch via `historyId`
- Email classification over the spec's categories
- Attachment processing: XLSX, PDF, DOCX, and scanned images where Tesseract exists
- Header normalization via synonym dictionary + `rapidfuzz` fuzzy matching
- Tiered candidate identification with a **review queue** below the auto-accept
  threshold — never a silent guess
- Status classification, event extraction, duplicate detection, Calendar integration
- Placement timeline per company

## M5 — Career intelligence and outreach

- Skill-gap aggregation across ranked target jobs
- Prioritization by frequency × role relevance
- Curated `resources.json` keyed by taxonomy ID (deterministic — no invented links)
- Cold-mail drafting from match evidence; always a draft, never auto-sent

## M6 — Hardening and release

- NSIS installer for Windows
- First-run model download with progress
- Profiling against the [latency budget](./architecture.md#latency-budget)
- An explicit error surface for every external dependency: no network, no Tesseract,
  no TeX, blocked job source, expired OAuth

## Cross-cutting risks

| Risk | Mitigation |
|---|---|
| Rust/MSVC not installed | Only remaining M0 blocker; dev workflow already runs without it |
| PyInstaller + onnxruntime native libs | Prove the packaged build in M0/M1, not M6 |
| LinkedIn/Naukri largely gated behind login | Ordered adapter rollout; `manual` + ATS feeds carry the feature |
| Scraper selectors break | Golden-HTML fixtures + `live` tests isolate cause |
| Skill taxonomy quality caps all matching | First-class M1 deliverable with its own tests |
| No-LLM tailoring vs the spec's wording | Tailor UI states plainly that it reorders and selects, never rewrites |
| Monaco bundle size | Lazy-load on the Tailor route only |
| Monaco renders untrusted JD/`.tex` | DOMPurify pinned via `overrides`; `npm audit` gates CI |
