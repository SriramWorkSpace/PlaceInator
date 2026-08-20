# Changelog

All notable changes to this project are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
