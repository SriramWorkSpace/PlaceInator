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

*Complete, except OCR for scanned images (see below).* New
`placeinator/placement/` package implements the full spec §7 pipeline: Gmail
fetch → attachment parsing → header normalization → candidate identification
→ status/event extraction → duplicate-safe persistence → Calendar.

- **Gmail OAuth (loopback flow), OS-keychain token storage.** The refresh
  token is stored via `keyring` (confirmed against the real Windows
  Credential Manager backend before any code depended on it) — never in
  SQLite, never in a plain file. `architecture.md`'s system diagram places
  "OAuth token storage (OS keychain)" in the Tauri shell's box, but Python
  has its own direct keychain bindings, so none of this needed a round trip
  through Rust. `POST /api/placement/connect` runs the blocking
  `run_local_server` loopback flow inside `asyncio.to_thread`, so the one
  request stays open while the user approves in their browser without
  blocking the rest of the sidecar.
- **Incremental fetch via `historyId`** (`placeinator/placement/gmail.py`),
  falling back to a bounded initial scan when there's no cursor yet, or when
  Gmail no longer retains history back to a stale one (a real `404`, not a
  hypothetical). `Preferences.gmail_last_history_id` persists the cursor —
  `Preferences` was already the single-row "app-wide settings" table
  (`notification_threshold` lives there the same way).
- **Header normalization** (`placeinator/placement/headers.py`): a
  synonym dictionary matching spec's own worked example verbatim
  ("Student Name"/"Applicant" → `candidate`, "Result"/"Selection Status" →
  `status`, ...), falling back to `rapidfuzz` fuzzy matching for anything not
  named explicitly — ADR 0002's exact commitment for this milestone.
- **Candidate identification with a genuine confidence score**
  (`placeinator/placement/candidates.py`), not a single all-or-nothing check
  — email, student ID, and fuzzy name matches (including
  `Profile.name_aliases`) each contribute a weighted share. Weights are
  calibrated against spec's own worked example, which has *only* a name
  column: a single strong name match clears the review-queue floor on its
  own, and auto-accept requires a second corroborating signal — a lone
  match, however exact, stays in the **review queue** rather than being
  silently accepted.
- **Status/event extraction** (`placeinator/placement/classification.py`,
  `events.py`) via keyword rules and `dateparser` — no LLM anywhere (ADR
  0002). A real bug surfaced and was fixed here: checking the SHORTLISTED
  phrase list before REJECTED's classified "Not shortlisted" as
  SHORTLISTED, since "shortlisted" is a substring of the negation. REJECTED
  is now checked first.
- **Duplicate detection is the existing `PlacementEvent.dedupe_key` unique
  constraint doing its actual job** — `sha256(company, event_type, date,
  start_time)`, normalized so formatting/casing differences on the same
  real event still produce the same key. The service layer upserts against
  it rather than blind-inserting; verified with a real two-sync test that
  the second sync creates no duplicate.
- **Calendar integration** (`placeinator/placement/calendar.py`), same OAuth
  credential, `calendar.events` scope only (event creation, not full
  calendar control). Explicit local timezone (`tzlocal`, already a
  transitive dependency of `dateparser`) rather than assuming UTC, which
  would have misplaced every event.
- **A free-text date-scanning approach was tried and deliberately dropped**
  for plain email bodies (no structured attachment): `dateparser.search
  .search_dates` produces false positives on ordinary prose — the word "we"
  alone parsed as a date in a real test against realistic email text.
  Silently creating a calendar event from a wrong guessed date is worse than
  not creating one, so a plain-body message that mentions an event lands in
  the review queue for a human to read and act on, rather than an
  auto-extracted (and possibly wrong) date ever reaching a real calendar.
- `POST/GET /api/placement/{connect,disconnect,status,sync,review-queue,
  review/{id}/{confirm,reject},timeline}` and a rebuilt
  `src/routes/Placement.tsx` (sync control, review queue with confirm/reject,
  company timeline) plus a real Connect/Disconnect control on the Settings
  page's Connected Accounts section, replacing its former "Coming in M4"
  placeholder.
- **Scanned-image attachments (OCR) are explicitly out of scope for this
  slice.** Tesseract isn't installed on the dev machine — installing it is
  its own separate system-level dependency, the same risk class as the
  Rust/MSVC and Google Cloud OAuth setups this project has already worked
  through individually. A scanned attachment degrades honestly
  (`OcrUnavailableError`, caught upstream, sync continues) rather than
  crashing or silently dropping the promise `resumes/parsing.py`'s own
  `EmptyDocumentError` docstring made about M4 adding Tesseract support —
  real OCR is a fast, isolated follow-up once Tesseract is installed.

## M5 — Career intelligence and outreach

*Complete.* Neither spec §4 nor §6 defines a rigid schema, so this milestone
had more real design latitude than M4's (whose DB schema was already built
in advance) — the guiding move throughout was reuse over invention:

- **Skill-gap analysis needs no new database table at all.** It's a pure
  aggregation over data that already exists and is already kept fresh
  (`Job.required_skill_ids`, `ResumeChunk.skill_ids`, `rank_jobs`'s scores)
  — the same "computed fresh, no dedicated table" shape `rank_jobs`/
  `list_notifications` themselves already use.
- **Prioritization by frequency × role relevance, without a second
  relevance metric.** `placeinator/career/gaps.py::aggregate_skill_gaps`
  accumulates each missing skill's priority by summing
  `JobRanking.overall_score` across the jobs requiring it — a skill
  appearing in several *highly-ranked* jobs naturally outscores one
  appearing only in a marginal match, because `overall_score` already
  encodes role/location/salary/preference relevance
  (`placeinator/jobs/filtering.py`). Preferred-but-not-required skills
  count at half weight; hard-filtered jobs are excluded entirely (not a
  real target, so its requirements shouldn't drive what to learn next).
- **`placeinator/skills/resources.json`**: 26 curated entries, keyed by
  taxonomy skill id. Every URL was checked live (via `WebFetch`) before
  being added, not recalled from training data — this caught one stale
  link (`cloud.google.com/docs` now redirects permanently to
  `docs.cloud.google.com/docs`; fixed to the canonical target rather than
  left to rely on the redirect). A skill with no curated entry simply has
  none in the API response — never a fabricated one. Partial coverage
  mirrors `taxonomy.json`'s own honest 89/~600 gap: the loader degrades
  correctly for a miss from day one, so growing coverage later needs no
  code change.
- **Cold-mail drafting is Jinja2-templated from real match evidence, never
  generated prose** (ADR 0002). `placeinator/outreach/templates.py` fills
  a plain-text template from already-extracted data only —
  `placeinator/outreach/service.py` is what pulls a job's top 3
  `projects`/`experience` evidence bullets and matched skill ids out of
  `MatchResult.explanation` (the same "top contributing chunks" record
  that already powers notification reasons, resume recommendation, and
  the tailoring change log) before the template ever sees them. "Cold-Mail
  Target Selection" (spec §6) reuses `rank_jobs` directly rather than a
  second scorer, the identical reasoning as skill-gap prioritization.
- **`OutreachDraft`** (new table, one migration on top of
  `e5234ad4fa59`): upserts on `(resume_id, job_id)`, same shape as
  `MatchResult`/`TailoredResume`. Deliberately no "sent" status column —
  the app has no way to know whether a draft was actually sent outside
  itself, so it doesn't pretend to track that.
- **`GET /api/career/skill-gaps`**; `GET /api/outreach/targets`,
  `GET/POST /api/outreach/drafts`, `DELETE /api/outreach/drafts/{id}`; a
  rebuilt `src/routes/Career.tsx` (ranked gap list, real job evidence,
  resource link only when one exists) and `src/routes/Outreach.tsx`
  (resume picker, target list, per-target draft view with copy-to-
  clipboard) — **no send action exists anywhere in the UI**, matching spec
  line 423 ("The system assists with preparation rather than automatically
  sending messages... without user control") as a structural property of
  what was built, not just a stated intention.
- **Done when:** verified against a real onboarded profile with a real
  resume and a real job requiring a skill the resume doesn't have —
  `tests/integration/test_m5_flow.py` asserts the gap surfaces with real
  job evidence, and a generated draft cites the resume's actual bullet
  text verbatim (`"10k requests/sec"`/`"payments platform"`), not a
  paraphrase.

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
