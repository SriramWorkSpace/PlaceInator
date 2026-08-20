# Changelog

All notable changes to this project are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **ATS board sync is reachable from the UI at last.** `POST /api/jobs/ats-feed`
  had been complete and tested on the backend since M2's first slice but had no
  client function, no wire type, and no control — meaning Greenhouse/Lever/Ashby,
  the only adapter that reliably returns full job descriptions, was dead weight
  in the shipped app. Added `syncAtsFeed` (`src/lib/api.ts`), the `AtsFeedIn`/
  `AtsFeedOut`/`AtsPlatform` types, and an `AtsFeedSync` control on the Jobs page.
- **Discovered jobs link back to the original posting.** `JobOut` never carried
  `url`, so a posting an adapter found was a dead end in the UI even though the
  URL had been persisted all along. Job rows now also show which source they came
  from, so a discovered posting is distinguishable from a pasted one.

### Fixed

- **A component score could exceed its documented `[0, 1]` bound.**
  `_score_overall` and `_score_role` clamped only the *lower* end with
  `max(0.0, ...)`, but cosine similarity of two near-identical float32 vectors
  lands a few ULPs above 1.0 — an exact role-title match produced
  `1.0000001192092896`. Whether it crossed the bound depended on the CPU's
  vector instructions, so it stayed under on the dev machine and broke on CI.
  `MatchResult.explanation` is user-facing and the weighted sum assumes the
  bound, so all three scorers now go through one `_clamp_unit` helper.
  **This bug was pre-existing and invisible**: the only CI step that ran these
  tests was marked `continue-on-error`, so it had been failing silently.
  Making the model suite a required gate surfaced it on the first run.
- **A transport failure in any job source is now `SourceBlocked`, not a 500.**
  No adapter caught `httpx.HTTPError`, so a connect timeout or DNS failure
  propagated out of `fetch()` and reached the UI as an error — precisely the
  outcome [ADR 0003](./decisions.md#adr-0003--job-source-adapters-and-their-hard-boundary)
  exists to prevent. Caught at `JobSource.get`, the single choke point all four
  adapters share.
- **`ats_feed` no longer crashes on an unreadable response.** `response.json()`
  and `job["id"]` were unguarded, so a 200 carrying an error page, or a posting
  without an id, raised instead of degrading to `SourceBlocked`.
- **`search_jobs` raised a bare `KeyError`** (an opaque 500) for `manual` and
  `ats_feed`, neither of which is keyword-searchable. Now a `ValueError` naming
  the sources that are.
- **The notification list went stale after adding or discovering a job.** The
  Jobs page invalidated only `["jobs", "ranked"]`, so a new job that cleared the
  threshold wouldn't reach the Dashboard until an unrelated refetch.
- **20+ tests never ran in CI.** The `model`-marked suite — `test_m1_flow.py`
  (the M1 end-to-end acceptance path), `test_ats_feed_api.py`, and the new
  search-API tests — was deselected by the default run, and the one `model` step
  CI did have was scoped to `test_scoring.py` *and* marked `continue-on-error`.
  It is now a required gate. The embedding model downloads once per run, not once
  per test (`fastembed`'s loader is `lru_cache`d).
- **CI's Python version is pinned to an exact patch** (`3.13.7`) instead of a
  floating `3.13`. The floating version is how the robots.txt bug below passed
  locally and failed in CI.
- **`actions/checkout`, `setup-node`, and `setup-python` bumped v4/v4/v5 → v7**,
  clearing the Node 20 deprecation warnings on every run.
- **`POST /api/jobs/search` and `service.search_jobs` had no test at all** —
  the only discovery path wired to a UI control was the one path with zero
  coverage. Added `tests/unit/test_jobs_search.py` (dispatch, blocked
  passthrough, adapter lifetime, unsearchable-source guard) and
  `tests/integration/test_jobs_search_api.py` (route → service → upsert →
  serialization, against the real captured Indeed fixture).

### Documentation

Four claims in the codebase were checked against the code and found false:

- `placeinator/jobs/__init__.py` advertised an entry point `normalize_posting`
  that has never existed (it is `upsert_job_from_posting`).
- `placeinator/jobs/sources/__init__.py` claimed token-bucket rate limiting,
  exponential backoff, and response caching. None exist; `base.py` is a plain
  minimum-interval limiter and says so. It also claimed every adapter ships
  fixtures — only `ats_feed` and `indeed` do, because they are the only two with
  a parser.
- `placeinator/api/jobs.py` said "only manual paste exists here" while
  containing `/ats-feed` and `/search`.
- `docs/roadmap.md` still credited the intermediate `RobotFileParser`-internals
  fix — the one that *caused* the CI break — and `docs/decisions.md` still listed
  `urllib.robotparser` as shipped infrastructure, contradicting its own addendum.
  Both now record what was actually built, including what was planned and
  dropped.

Also corrected: `read_notifications` attributed the threshold to the module-level
`NOTIFICATION_THRESHOLD`, which is only the fallback when no preferences row
exists — the user's own `Preferences.notification_threshold` is what applies.

- **CI was broken on `windows-latest` (Python 3.13.15) while passing locally
  (Python 3.13.7)** — `placeinator/jobs/sources/base.py::_can_fetch`'s
  longest-match robots.txt fix (below) read its result off
  `RobotFileParser.entries`/`.default_entry`/`RuleLine.path`/`.allowance`,
  undocumented private attributes with no stability guarantee across
  patch releases. Their behavior changed between those two Python
  versions, and every one of that fix's own tests failed in CI while
  passing locally — confirmed by pulling the actual CI log, not guessed
  at. Rewritten to parse robots.txt directly from raw text
  (`_parse_robots_groups`), with zero dependency on `RobotFileParser`
  internals; every adapter, `ats_feed` included, now goes through it.
  Added a regression test against the real captured Indeed `robots.txt`
  fixture, not just synthetic strings, so this can't silently regress
  again. See the "Verified in practice" addendum to
  [ADR 0003](./decisions.md#adr-0003--job-source-adapters-and-their-hard-boundary)
  for the full story.

### Added

- **Real logo**, replacing the placeholder rotated square in the sidebar
  and as the browser-tab favicon (`src/assets/logo.png`,
  `public/favicon.png`).
- **Fixed a real cross-component desync bug** in `useTheme`/`usePalette`:
  both are now called from two places at once (the sidebar's floating
  toggle and the new Settings > Appearance section), and the previous
  per-component `useState` meant toggling in one would silently leave the
  other showing a stale switch position while the DOM itself had already
  changed correctly. Rewritten as a shared module-level store via
  `useSyncExternalStore`, so every subscriber agrees immediately regardless
  of which one triggered the change.
- **Split Profile out of Settings, and gave Settings real content.** The
  sidebar's "Profile" link previously just routed to `/settings` — personal
  info and career preferences (spec §1) now live at their own `/profile`
  route (`src/routes/Profile.tsx`), and `/settings` is a genuine account
  page: Appearance (dark mode plus four accent-color palettes —
  `src/lib/palette.ts`, `--accent`/`--accent-fg`/`--accent-subtle` swapped
  via `[data-palette]`, applied before first paint the same way theme is),
  Notifications (a real, working match-threshold slider wired to the new
  `Preferences.notification_threshold` column — the same field
  `list_notifications` reads, not a cosmetic control), Connected accounts,
  and Account. The last two are deliberately honest rather than
  decorative: Google OAuth is real M4 scope and says so instead of a dead
  "Connect" button; there is no login system in a local single-user app, so
  the Account section explains that plainly instead of shipping a "Log out"
  button with nothing behind it.
- **`indeed`, `linkedin`, `naukri` job source adapters, completing M2.**
  Each verified live before any parsing code was written:
  - `indeed`: real coverage. The search-results page embeds job data as JSON
    in a `<script>` tag (server-rendered, no Playwright needed); the adapter
    reads it directly rather than the disallowed-by-robots.txt `/viewjob`
    detail page, so descriptions are Indeed's own short snippet, not the
    full JD — a real, documented ceiling, not a bug.
  - `linkedin`: `robots.txt`'s catch-all block is `Disallow: /` for any
    unrecognized crawler — every request is blocked before parsing, which
    is why there's no HTML-parsing logic in this adapter at all.
  - `naukri`: Akamai edge bot detection 403s every path tried, including
    `robots.txt` itself, for this project's honestly-identifying user
    agent. Confirmed live that a generic UA would get through and
    deliberately did not adopt it — that would be exactly the evasion
    ADR 0003 rules out.
  - New `POST /api/jobs/search` (keyword + location, dispatches to whichever
    of the three), and a "Search a job board" form on the Jobs page above
    the existing paste/upload flow.
  - **Fixed a real bug in shared robots.txt handling**, found while
    verifying indeed: `RobotFileParser.can_fetch` returns the *first*
    matching rule in file order, not RFC 9309's longest-match-wins, so a
    host whose `User-agent: *` opens with a blanket `Allow: /` before later,
    more specific `Disallow:` lines (indeed.com's actual shape) was read as
    more permissive than intended. Replaced with a longest-match
    implementation (`placeinator/jobs/sources/base.py::_can_fetch`) every
    adapter now goes through — ADR 0003's entire compliance boundary rests
    on this check being correct.
  - `html_to_text`/`parse_date`/`parse_epoch_ms`, previously private to
    `ats_feed.py`, moved to `base.py` as shared adapter utilities now that a
    second adapter needs them too.
- **Personalized job notifications (spec §2, completing M2's remaining
  scope).** `GET /api/jobs/notifications` surfaces jobs that pass hard
  filters, have a semantic score against the primary resume, and clear
  `NOTIFICATION_THRESHOLD` (0.6) — a deliberately separate, higher bar than
  the ranked list, which shows every non-filtered job regardless of score.
  `Job.notification_seen_at` (new column, migration `1ca39ea10a65`) tracks
  which notifications the user has already dismissed
  (`POST /api/jobs/{id}/notifications/seen`), so nothing reappears once
  acted on. Surfaced on the Dashboard, previously just a static empty state,
  with the same soft-preference reasons the Jobs page's ranked list already
  shows — one explanation source, two surfaces.

- **Hard-constraint filtering, soft-preference scoring, and a ranked Jobs UI
  (M2).** `placeinator/jobs/filtering.py` evaluates spec §2's hard
  constraints (minimum salary, bond/contract duration, experience range,
  relocation) against every job — a violation sets `Job.filtered_out_reason`
  but the job is kept, never deleted, so the UI can explain the exclusion.
  Soft preferences (work mode, city, target role, salary) score 0–1 and
  never eliminate a job. `GET /api/jobs/ranked` combines that with the
  semantic match against the profile's primary resume into one ranked list;
  filtered jobs sort last with their reason shown, not hidden. Re-runs
  automatically whenever preferences are saved (`refilter_jobs`, wired into
  `profile.service.upsert_profile`) so the ranking never goes stale. Scoped
  to filtering/scoring/UI only for this pass — `indeed`/`linkedin`/`naukri`
  adapters remain deferred (Playwright + real site reconnaissance, out of
  scope here).
- **JD file upload on the manual job-add form.** `POST /api/jobs/extract`
  parses an uploaded PDF/DOCX job description (`placeinator/jobs/parsing.py`,
  `placeinator/jobs/extraction.py` — regex/heuristic, no LLM) and prefills
  designation, company, and the full description text; a JD's layout is far
  less standardized than a resume's, so designation/company are frequently
  null and the full parsed text (always present) is what actually matters
  for matching. Autofill never overwrites a field the user already typed.
  Paste-a-JD remains fully supported alongside this — upload is additive,
  not a replacement.
- **Fixed a real bug in the page-navigation transition**, not just restyled:
  the first attempt was built on the View Transitions API via react-router's
  `viewTransition` prop, which never visibly fired. Replaced with Motion's
  `AnimatePresence` (`AppShell.tsx`'s `PageTransition`, via `useOutlet()` +
  `useLocation()`) — the same tool already proven working in this app for
  the theme toggle's icon swap — for a fade-out/fade-in between routes.
- **Resume-driven profile autofill during onboarding.** Uploading a resume on
  the onboarding form now parses it for name/email/phone/college/department
  (`placeinator/resumes/extraction.py` — regex/heuristic, no LLM, per
  [ADR 0002](./decisions.md#adr-0002--deterministic-engine-no-llm-generation))
  and prefills the form; only fields the user hasn't already typed into are
  filled, never overwritten. The same resume is saved as the profile's
  **primary resume** once onboarding completes. `Resume.is_primary` is a new
  column with a partial unique index (`uq_resume_primary_per_profile`, SQLite
  `WHERE is_primary`) enforcing exactly one primary per profile at the DB
  level, not just in application code — see migration
  `14cac5fce49b_add_resume_is_primary_flag`. A profile's first resume is
  always primary regardless of how it's uploaded; later resumes can be
  promoted from the Resume Library (`PATCH /api/resumes/{id}/primary`).
- **M1 complete.** Full onboarding → resume upload → job intake → ranked
  match loop, verified live through the running UI. Manual job intake gained
  an `Application deadline` field (`Job.deadline` existed as a column since
  M0 but was never exposed anywhere) using a shadcn-style Ark UI date picker
  integrated at `src/components/ui/date-picker.tsx`, retokenized onto this
  project's design system rather than left with its source's hardcoded
  colors — see that commit for why a literal copy-paste would have silently
  desynced from the app's theme toggle.
- Material Symbols icon set placed across the nav, a light/dark theme toggle
  (persisted, no flash-of-wrong-theme on load), and a profile indicator —
  the "Profile" slot the original spec wireframe called for but was never
  built.
- Subtle hover depth on card surfaces (SectionCard, Jobs list rows), gated
  to genuinely interactive ones to avoid implying clickability that isn't
  there on purely informational panels.

### Changed

- **Frontend visual language rebuilt around a warm "studio" reference**,
  superseding the earlier GitHub-adjacent direction — self-hosted Fraunces
  display serif, cream palette, pill controls, per-section accent colors.
  See [ADR 0006](./decisions.md#adr-0006--studio-visual-language-superseding-the-github-adjacent-direction). Fixed a real
  gap while touching the type system: Inter was previously only referenced
  by CSS name, never actually loaded, so it silently fell back to whatever
  the OS had installed.

### Added

- **Project foundation (M0).** Python sidecar (FastAPI + uvicorn) with an
  ephemeral-port startup handshake and bearer-token auth on every route except
  `/health`; React 18 + TypeScript + Vite 6 + Tailwind 4 frontend; typed API client;
  CI running the full Python and frontend check suites.
- **Database schema** — 9 tables covering profile, preferences, resume library and
  chunks, jobs and requirements, match results, and placement records and events.
  Alembic-managed from the first revision.
- **Documentation set** (`docs/`) — architecture, roadmap, foundation audit, and five
  ADRs recording the durable decisions. Previously these existed only in conversation
  and in an external plan file, so they were not versioned with the code.
- **Repository structure** — flat feature modules under `placeinator/`, one per
  specification section; `tests/` split into `unit/` and `integration/` with shared
  fixtures in `conftest.py`; frontend app shell with seven routes.

### Changed

- **Renamed the Python package `core/` → `placeinator/`.** It is installed via
  `pip install -e .`, so `import core` occupied a real global top-level name that was
  both collision-prone and uninformative. Done before the first commit, when it was
  free.
- **Alembic is now the sole owner of schema.** `create_all` was removed from the
  startup path; migrations run on every boot. See
  [ADR 0004](./decisions.md#adr-0004--alembic-is-the-sole-owner-of-database-schema).
- **Moved `feature_architecture.md` → `docs/specification.md`** (content unchanged).
- `react-router-dom` upgraded to 7.x.

### Fixed

Nine defects found in the [foundation audit](./audit-2026-08-19.md). Each typechecked
clean and would have surfaced later, far from its cause:

- **Enum columns returned `str` instead of the enum type.** Declared as `String`, they
  compared equal via `StrEnum` semantics — so `==` and `match` worked and the bug hid —
  but `.name` and `isinstance` would fail at runtime with `mypy` reporting success.
- **`create_all` and Alembic both owned schema**, which would have left
  `alembic_version` empty on fresh installs and broken the first real migration only on
  machines that had run the app before.
- **Anonymous constraints** would have broken or silently corrupted every future SQLite
  migration, since Alembic batch mode can only recreate constraints it can name.
- **uvicorn's access log wrote to stdout**, the same channel as the startup handshake.
- **Embeddings were stored without provenance**, so a model change would have silently
  turned every stored vector into meaningless numbers.
- **Four npm vulnerabilities**, reachable because Monaco renders untrusted job
  descriptions and `.tex` files. Now zero, gated in CI.
- **`tsconfig` declared a `@/*` path alias Vite did not resolve** — would typecheck and
  then fail at bundle time.
- **`npm run lint` invoked an uninstalled eslint.**
- **Two competing locations for ONNX models** (repo root vs. per-user data directory).

Four defects found while building out the M1 UI, each caught by testing the actual
running app rather than trusting the code:

- **Sidebar labels popped in at full size while the rail was still mid-width-transition**
  (conditionally mounted on the same boolean driving the width), causing a visible
  reflow on every expand. Labels now stay mounted and animate via max-width + opacity
  instead.
- **Every collapsed nav badge was off-center**, not just the one row a screenshot
  happened to catch — an unconditional flex `gap` after an invisible zero-width label
  still reserved space, which `justify-center` then centered as part of the block.
- **Every page but Dashboard repeated its nav label as its own headline** ("CAREER"
  eyebrow directly above a "Career" title). Headlines now come from the specification's
  own section names instead.
- **`apiFetch` forced `Content-Type: application/json` unconditionally**, which would
  have silently broken every multipart resume upload by overriding the browser's own
  boundary header.

### Known blockers

- **Rust and MSVC build tools are not installed**, so `src-tauri/` cannot be scaffolded
  or built. Deliberately non-fatal: the frontend falls back to `VITE_SIDECAR_PORT` /
  `VITE_SIDECAR_TOKEN`, so both halves run separately today.
