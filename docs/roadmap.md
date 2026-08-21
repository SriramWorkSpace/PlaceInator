# Roadmap

Milestones for building out [specification.md](./specification.md). Design rationale
lives in [architecture.md](./architecture.md) and [decisions/](./decisions/).

## M0 — Foundation

*Desktop shell up in dev mode; packaged build remains.*

Done:

- Python sidecar with ephemeral-port handshake and bearer-token auth
- Full ORM schema (9 tables), Alembic-managed, initial revision generated
- React + TypeScript + Vite + Tailwind frontend with a typed API client
- App shell with seven routes and empty states
- CI, documentation set, repository structure
- Rust + MSVC Build Tools installed and verified (a real crate built, linked, and ran)
- `src-tauri/` scaffolded; dev-mode sidecar supervision implemented and verified live:
  `npm run tauri dev` builds the Rust shell, spawns
  `.venv/Scripts/python.exe -m placeinator.main`, blocks on a background thread reading
  its stdout for the `PLACEINATOR_READY` handshake line (bounded by a 30s timeout so a
  sidecar that never starts fails loudly rather than hanging the window forever),
  injects `window.__PLACEINATOR__` via `initialization_script` before the frontend's
  first API call, and shows the real authenticated UI. Closing the window sends
  `RunEvent::ExitRequested`, which kills the sidecar -- verified with a real window
  close (not a force-kill): zero orphaned `python.exe`/`node.exe` processes survived it.

Remaining:

- Wire PyInstaller onedir to `bundle.externalBin` (deliberately deferred rather than
  bundled into the same pass as the first Rust code this repo has ever had — see
  `docs/decisions.md`'s ADR 0001 addendum)
- A Windows Job Object (or similar) so the sidecar is reliably killed even if the shell
  crashes rather than exits cleanly -- today's `child.kill()` on `ExitRequested` handles
  the normal case but not a hard crash
- CI has no Rust/Tauri job yet

**Prove the packaged build now, not at M6.** onnxruntime's native libraries are the
likeliest packaging problem, so add `fastembed` to the bundle test as soon as M1
introduces it.

## M1 — Profile, Resume, and Matching

*Complete.* Everything else depends on it, and does now.

- Onboarding wizard (spec §1): profile, career preferences, employment constraints
- Resume library, upload, and parsing (PDF / DOCX / `.tex`)
- `placeinator/skills/taxonomy.json` — aliases and category tags
- `fastembed` integration and `placeinator/matching/vectors.py`
- Chunking, component scores, ranking, and `MatchResult.explanation`
- Resume recommendation with user override
- The `manual` job source, so the loop is exercisable end to end
- Full frontend: onboarding form, resume upload, job intake with an
  `Application deadline` field (a shadcn-style Ark UI date picker, retokenized
  onto this project's design system), ranked-match results
- The warm "studio" visual language (ADR 0006), icon set, light/dark toggle,
  profile indicator, and card hover depth

**Done when:** add 3 resumes → paste a JD → get a ranked recommendation with a readable
explanation, in under 2 seconds. **Verified live** through the actual UI, not just the
test suite — see the M1 frontend and DatePicker integration commits.

> `taxonomy.json` is the critical path, and it has not caught up to its own target yet:
> **89 entries seeded, not the ~600 originally scoped.** With no LLM, it *is* the
> semantic backbone of skill matching, gap analysis, and filtering — matching quality
> is capped by it today. Expanding it is worth doing before or alongside M2's job
> intelligence work, since M2 will surface skill-matching gaps in a much wider variety
> of real job descriptions than M1's own tests exercised.

## M2 — Job intelligence

*Complete.* All four source adapters ship (`ats_feed`, `indeed`, `linkedin`,
`naukri`), each verified live against the real site before any parsing code
was written, not assumed from the spec's own expectations:

- **`indeed`** — real, working coverage. The search-results page is plain
  server-rendered HTML with job data embedded as JSON in a `<script>` tag;
  `robots.txt` permits fetching it (only the per-job `/viewjob` detail page
  is disallowed for a generic crawler, so the adapter never requests it and
  works from the shorter search-result snippet instead). No Playwright
  needed — an earlier note in this file assumed browser automation would be
  required and was wrong; corrected after live verification.
- **`linkedin`** — `robots.txt`'s catch-all block is a blanket `Disallow: /`
  for any unrecognized crawler. Every request is blocked before the adapter
  ever gets to parse anything; this is stricter than ADR 0003's "thin —
  public job-view pages only" estimate, not a bug.
- **`naukri`** — active edge-level (Akamai) bot detection blocks every path
  tried, including `robots.txt` itself, with a 403 for this project's
  honestly-identifying user agent. Confirmed live that a generic browser UA
  gets through — deliberately not adopted, since disguising the UA to evade
  detection is exactly what ADR 0003 rules out.

Found and fixed **two** real bugs in shared infrastructure while verifying
indeed — the second one caused by the fix for the first, so both are recorded
here rather than only the tidy version:

1. `RobotFileParser.can_fetch` resolves rules by first-match-in-file-order, not
   RFC 9309's longest-match-wins, so a host whose `User-agent: *` block opens
   with a blanket `Allow: /` before later specific `Disallow:` lines (Indeed's
   shape, exactly) was read as more permissive than the file's own author
   intended.
2. The first fix kept `RobotFileParser` for parsing and only replaced its
   decision logic, reading the parsed result off `entries`, `default_entry`,
   `RuleLine.path`, and `.allowance` — **undocumented private attributes with
   no stability guarantee.** They behave differently across Python patch
   releases, so every disallow rule silently evaluated to "allowed" on CI
   (3.13.15) while passing locally (3.13.7).

The shipped implementation parses `robots.txt` from raw text itself
(`placeinator/jobs/sources/base.py::_parse_robots_groups` / `_can_fetch`), with
no dependency on `urllib.robotparser` at all, and is regression-tested against
the real captured Indeed `robots.txt`. Every adapter goes through it. CI now
pins an exact Python patch version so this class of skew can't hide again.

Also shipped: shared adapter infrastructure; hard-constraint filtering and
soft-preference scoring (`placeinator/jobs/filtering.py`, `rank_jobs` in
`placeinator/jobs/service.py`); the Jobs UI's ranked list and job-board
search form, with filter explanations; personalized notifications
(`list_notifications`, `NOTIFICATION_THRESHOLD`, `Job.notification_seen_at`),
surfaced on the Dashboard. `Job.filtered_out_reason` is recomputed on every
job create and on every preference save (`refilter_jobs`), so it never goes
stale.

A consolidation pass then closed the gap between "the backend works" and "a user
can reach it": the ATS-feed sync had been complete and tested since M2's first
slice but had no UI at all, and `JobOut` omitted `url`, so every discovered
posting was a dead end. Both are fixed, transport failures now degrade to
`SourceBlocked` instead of a 500, and the search route — the only discovery path
wired to a control — finally has tests. The `model`-marked suite, including M1's
end-to-end acceptance path, is a required CI gate rather than a deselected
afterthought.

- Source adapters in expected-success order: `indeed`, `ats_feed`, `linkedin`, `naukri`
  (see [ADR 0003](./decisions.md#adr-0003--job-source-adapters-and-their-hard-boundary)) —
  `ats_feed` shipped first in practice, reversing the documented order
- Shared adapter infrastructure: `robots.txt`, rate limiting, backoff, caching
- Job normalization, hard-constraint filtering, soft-preference scoring
- Jobs UI with ranked list and filter explanations
- Personalized notifications that state *why* an opportunity is relevant

## M3 — LaTeX resume tailoring

*Complete, except PDF compile (see below).* Verified against real `pylatexenc`
behavior before any code was written, not assumed from its docs — see
`placeinator/latex/parsing.py`'s module docstring for the two findings that
shaped the design: pylatexenc's node tree doesn't nest a section's body under
its heading (siblings, not children), and a `\newcommand`-defined macro like
`\resumeItem{...}` — the shape most real resume templates actually use —
doesn't get its argument captured as a child node at all.

- **`pylatexenc` parser retaining source spans**, but not as a tree walk:
  `parse_latex` partitions the source into a flat, ordered, contiguous span
  list (Fixed / Section / Bullet), so identity-order emission reproducing the
  input byte-for-byte is true *by construction*, not something separately
  proven correct.
- **Round-trip gate**: `tests/unit/test_latex_parsing.py`, against real
  captured resume `.tex` files in `tests/fixtures/resumes/`, including one
  using only custom bullet macros (proving the honest whole-section fallback
  when no `\item` is recognized) and one with multiple independent bullet
  groups under one section heading.
- **Unit scoring, reordering policy, splice emitter**
  (`placeinator/latex/tailoring.py`): reuses M1/M2 infrastructure end to
  end rather than a parallel pipeline — pools the *same* persisted
  `ResumeChunk`/`JobRequirement` embedding vectors
  `placeinator.matching.service` already caches, via the same
  `mean_pool`/`clamp_unit` primitives `placeinator.matching.scoring` uses for
  its `overall` component. Sections reorder into a fixed canonical whitelist
  (the spec's own section tree); bullets *within* a section reorder by
  relevance score. Removal is never automatic — a low-scoring bullet is
  flagged as a suggestion only, and the emitted `.tex` still contains it
  unless the caller explicitly excludes it.
- **Change log**: `TailoredResume.change_log` records each section's/bullet's
  original vs. new position and score, plus requirements matched/missing —
  the latter a set difference over `Job.required_skill_ids` and the resume's
  own `ResumeChunk.skill_ids`, both already computed and stored, not
  re-extracted.
- **Three-pane-equivalent Tailor workspace** (`src/routes/Tailor.tsx`):
  resume/job pickers, a Monaco-rendered `.tex` output pane, and a change-log
  pane with per-bullet exclusion checkboxes. Monaco is lazy-loaded on this
  route only, exactly like `Jobs.tsx`'s DatePicker.
- **Found and fixed a real offline-correctness bug while wiring Monaco up**:
  `@monaco-editor/react`'s loader defaults to fetching the actual editor from
  `cdn.jsdelivr.net` at runtime rather than using the locally bundled
  `monaco-editor` package — confirmed by reading `@monaco-editor/loader`'s
  own config, not assumed. Unacceptable for an app whose core commitment is
  "fully offline, zero API cost" (ADR 0002/ADR 0005): the Tailor page would
  have silently broken with no network. Fixed in
  `src/lib/monaco-editor.ts` via `loader.config({ monaco })` pointed at the
  bundled package, plus a Vite `?worker` import for the editor's worker.
  Verified against the actual production build (Monaco appears as its own
  ~4 MB chunk, isolated to the Tailor route) and Vite's dev-server resolution
  path, not just a passing `tsc`.
- **PDF compile is out of scope for this slice.** Independent concern
  (TeX-distribution detection, subprocess), not a gap in what shipped.

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
