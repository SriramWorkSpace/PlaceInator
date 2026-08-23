# Architecture Decision Records

Durable decisions for PlaceInator, in one file so the reasoning behind the
codebase is easy to scan in one pass rather than spread across many small
files. Each entry keeps its original number for stable cross-references
elsewhere in the repo (`ADR 0004`, etc.).

- [ADR 0001 — Tauri v2 shell with a Python sidecar](#adr-0001--tauri-v2-shell-with-a-python-sidecar)
- [ADR 0002 — Deterministic engine, no LLM generation](#adr-0002--deterministic-engine-no-llm-generation)
- [ADR 0003 — Job source adapters and their hard boundary](#adr-0003--job-source-adapters-and-their-hard-boundary)
- [ADR 0004 — Alembic is the sole owner of database schema](#adr-0004--alembic-is-the-sole-owner-of-database-schema)
- [ADR 0005 — fastembed + ONNX Runtime, never PyTorch](#adr-0005--fastembed--onnx-runtime-never-pytorch)
- [ADR 0006 — Studio visual language, superseding the GitHub-adjacent direction](#adr-0006--studio-visual-language-superseding-the-github-adjacent-direction)

---

## ADR 0001 — Tauri v2 shell with a Python sidecar

- **Status:** Accepted
- **Date:** 2026-08-19

### Context

PlaceInator is a desktop application with a hard requirement for low memory footprint
and low UI latency. It also needs three heavy capabilities that all happen to be
Python's strongest ground: ONNX-based sentence embeddings, document parsing
(PDF/XLSX/DOCX/LaTeX), and Google API integration.

Two further constraints pull in opposite directions:

- The spec (the original requirements document, since retired — line 828 asked for
  this) wants the Resume Tailoring page to feel like a developer workspace, with the
  JD and LaTeX source in real editor panels. That points at a web view and Monaco.
- The ML and document stack is mature in Python and thin or absent in Rust. Rewriting
  it would be a project in itself.

Options considered: Tauri + Python sidecar; PySide6 (single-language Python/Qt);
Electron + Python sidecar; Flutter desktop + Python sidecar.

### Decision

A **Tauri v2 shell** (Rust + the OS WebView) hosting a **React + TypeScript** UI,
communicating over authenticated loopback HTTP with a **Python sidecar** (FastAPI +
uvicorn) that owns all ML, document, and integration work.

The sidecar binds its own ephemeral port and prints exactly one line to stdout:

```
PLACEINATOR_READY {"port": 51234, "token": "..."}
```

The shell reads that line and injects both values into the WebView. Binding the socket
in Python rather than letting uvicorn do it is what makes the port knowable *before*
the server starts accepting.

**Python owns SQLite outright.** The Rust side never opens the database. One writer,
one schema, one migration path.

### Consequences

**Positive**

- ~10 MB binary and roughly 120 MB idle RSS, versus ~400 MB+ for Electron.
- Monaco gives the Tailor page real editor panels for free.
- The entire Python ecosystem is available for the parts that actually need it.
- The two halves are independently testable and independently restartable.

**Negative**

- Three languages in one repo (Rust, TypeScript, Python).
- Requires a Rust toolchain plus MSVC build tools on Windows — currently the project's
  only outstanding blocker.
- An IPC boundary exists that a single-process design would not have, including a
  serialization cost on every call and a token to manage.
- PyInstaller must bundle onnxruntime's native libraries; this is the likeliest
  packaging problem and is scheduled to be proven early rather than at the end.

**Mitigations**

- A loopback port is reachable by any local process, so **every** route except
  `/health` requires the handshake bearer token (`placeinator/security.py`).
- The frontend falls back to `VITE_SIDECAR_PORT` / `VITE_SIDECAR_TOKEN` environment
  variables, so the UI is fully developable without a Rust toolchain installed.

### Verified in practice (2026-08-21)

`src-tauri/` is scaffolded and dev-mode sidecar supervision (`src-tauri/src/lib.rs`)
is implemented and verified against a real running window: `npm run tauri dev` builds
the shell, spawns the sidecar, reads the handshake, injects `window.__PLACEINATOR__`,
and shows the real authenticated UI end to end. Closing the window kills the sidecar
with zero orphaned processes.

Two real environment problems surfaced getting the Rust toolchain working on this
machine, neither specific to this project's code, both worth recording since they cost
real time and neither has an obvious error message:

1. **Git for Windows' `link.exe` shadowed the real MSVC linker.** Git ships a coreutils
   hard-link utility at `usr/bin/link.exe`; if it resolves ahead of MSVC's linker on
   `PATH` (it did here, since MSVC's linker is never added to `PATH` directly), rustc
   invokes the wrong one and fails with `"extra operand ... Try 'link --help'"` --
   coreutils' error format, easy to mistake for an MSVC problem when it's really a name
   collision.
2. **A brand-new Visual Studio release wasn't recognized by this toolchain's bundled
   detection.** Neither `rustup-init`'s C++-prerequisite check nor `rustc`'s own
   `cc`-crate-based MSVC auto-detection (which normally locates the linker and sets
   `LIB`/`INCLUDE` by querying the VS installation) recognized "Visual Studio 18" /
   Build Tools 2026 -- confirmed independently via `vswhere`, which found a complete,
   correct installation the other two tools missed. `rustup`'s legacy
   `HKLM\...\VisualStudio\SxS\VS7`/`VC7` registry-key check was also empty, since
   modern VS no longer populates those keys at all.

Both are fixed with an explicit, per-user `C:\Users\<user>\.cargo\config.toml` --
**not committed to the repo** (it's machine-specific, and CI's `windows-latest` runner
ships a VS version its bundled detection already recognizes, so it needs none of this):
a pinned `linker` path, `LIB`/`INCLUDE` set to what `vcvarsall.bat` would set, and
`CC`/`CXX`/`AR` pinned to the real `cl.exe`/`lib.exe` -- the latter needed because a
`tauri-build` build-dependency (`vswhom-sys`) compiles its own small C++ helper at
build time via the `cc` crate, a separate bootstrapping need from rustc's own final
link step, and hit the exact same "tool not found" problem for the same underlying
reason.

---

## ADR 0002 — Deterministic engine, no LLM generation

- **Status:** Accepted
- **Date:** 2026-08-19

### Context

Several spec features read as generative: tailoring a LaTeX resume to a JD (§5),
drafting cold outreach (§6), and extracting fields from messy placement documents (§7).
The options were an LLM API for generation, a local LLM, or a fully deterministic
implementation.

The user chose **deterministic only**.

### Decision

No language model generates text anywhere in the application.

- **Matching** uses local sentence embeddings (`fastembed`, see
  [ADR 0005](#adr-0005--fastembed--onnx-runtime-never-pytorch)) plus a curated skill
  taxonomy.
- **Resume tailoring** reorders, selects, and emphasizes existing content. It re-emits
  the *original* source spans byte-for-byte and never rewrites a bullet.
- **Cold outreach** uses Jinja2 templates filled from the match explanation's top
  contributing chunks.
- **Placement extraction** uses keyword rules, a header-synonym dictionary, `rapidfuzz`
  fuzzy matching, and `dateparser`.

### Consequences

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
  [architecture.md](./architecture.md)).
- Every score is explainable by construction: `MatchResult.explanation` records each
  component's value, weight, and top contributing chunk pairs.
- **`placeinator/skills/taxonomy.json` becomes the critical path.** Without a model to
  paper over vocabulary gaps, this hand-curated alias map *is* the semantic backbone of
  skill matching, gap analysis, and filtering. Matching quality is capped by it, so it
  is a first-class deliverable with its own tests, not a lookup table to be filled in
  hastily.

---

## ADR 0003 — Job source adapters and their hard boundary

- **Status:** Accepted
- **Date:** 2026-08-19

### Context

The spec (the original requirements document, since retired) asked for job discovery
from "supported sources" (§2). The user chose to target **Indeed, Naukri, and
LinkedIn** by scraping.

That choice runs into a limit the spec itself sets. Lines 836-842 place the following
explicitly out of scope:

> It will not attempt to bypass: CAPTCHA, Login requirements, MFA, Bot detection,
> Application-site restrictions

Those two requirements are in tension, because LinkedIn and Naukri gate most job search
behind login and active bot detection. The tension is resolved in favour of the spec's
own stated boundary — it is the user's written constraint, not an external one.

### Decision

Build a pluggable adapter layer targeting all three sites, which **operates only on
what is reachable without defeating an access control**.

`JobSource.fetch(query) -> FetchResult`, where `FetchResult` is either postings or
`SourceBlocked(reason)`.

Shared infrastructure in `placeinator/jobs/sources/base.py` — as originally
planned, then as actually built:

| Planned | Shipped |
|---|---|
| `robots.txt` checking via `urllib.robotparser` | A self-contained RFC 9309 parser. `urllib.robotparser` was tried and abandoned — see "Verified in practice" below |
| per-source token-bucket rate limiting and exponential backoff | A per-host minimum-interval limiter. No token bucket, no backoff — neither has been needed at one user's request volume |
| response caching keyed by URL | Not built. Only `robots.txt` responses are cached, per origin |

One choke point, `JobSource.get`, turns a robots.txt disallow *and* a transport
failure (timeout, DNS, dropped connection) into `SourceBlocked`, so no adapter
can accidentally surface an unreachable source as an error.

**When an adapter meets a login wall, CAPTCHA, or bot-detection challenge, it returns
`SourceBlocked` and stops.** It does not solve, evade, or authenticate through it.

Adapters, in expected-success order:

| Adapter | Expected coverage |
|---|---|
| `indeed` | Good — usable logged-out search pages |
| `ats_feed` | Reliable but narrow — Greenhouse/Lever/Ashby public JSON, fully permitted |
| `linkedin` | Thin — public job-view pages only |
| `naukri` | Thin — expect frequent `SourceBlocked` |
| `manual` | Always works — paste a URL or raw JD |

### Consequences

- **Coverage on LinkedIn and Naukri will be materially thinner than on Indeed.** This
  is a direct consequence of the spec's own boundary and should not be read as an
  implementation gap to be fixed later.
- `manual` is **not optional**. Spec §5 requires JD paste regardless, and it is the
  fallback whenever a source blocks.
- `SourceBlocked` is a first-class UI state, not an error. The UI shows the
  manual-paste path rather than a failure.
- Selector fragility is expected, not exceptional. Each adapter ships golden-HTML
  fixtures plus a `live`-marked test (deselected by default via `-m 'not live'`), so a
  break reads as "selectors moved" rather than "the app is broken".
- The project never automatically submits applications; the user remains in control of
  final submission and of sending outreach email (spec lines 834, 844).

### Verified in practice (2026-08-20)

The table above was a prediction, made before any adapter existed. All four were built
and each claim was checked live, not assumed:

| Adapter | Predicted | Verified |
|---|---|---|
| `indeed` | Good — usable logged-out search pages | **Confirmed.** Search results are plain server-rendered HTML with job data embedded as JSON; `robots.txt` permits fetching that page (only `/viewjob`, the per-job detail page, is disallowed). No Playwright needed. |
| `linkedin` | Thin — public job-view pages only | **Thinner than predicted: zero.** `robots.txt`'s catch-all `User-agent: *` block is `Disallow: /` — every path, not just search, is closed to any crawler not individually named earlier in the file. |
| `naukri` | Thin — expect frequent `SourceBlocked` | **Confirmed, and stronger:** every path tried (homepage, `robots.txt` itself, multiple search URL shapes) 403'd behind Akamai edge bot detection for this project's honestly-identifying user agent. A generic browser UA was confirmed, separately, to pass — deliberately not adopted, since that would be the evasion this ADR rules out. |

Two shared-infrastructure defects surfaced during indeed's verification, in sequence:

1. `RobotFileParser.can_fetch` (Python stdlib) resolves the first matching rule in file
   order, not RFC 9309's longest-match-wins. Indeed's `User-agent: *` block opens with a
   blanket `Allow: /` before dozens of later, more specific `Disallow:` lines — under
   first-match semantics, that opening `Allow: /` silently shadowed every `Disallow`
   after it, so `can_fetch` reported paths as allowed that the file's own author
   disallowed. The first fix kept `RobotFileParser` for parsing but replaced its
   decision logic with a longest-match implementation reading the parsed result off
   `RobotFileParser.entries` / `.default_entry` / `RuleLine.path` / `.allowance`.
2. Those are undocumented, private attributes with no stability guarantee, and it
   showed: CI (`windows-latest`, Python 3.13.15) failed every one of that fix's own
   tests, while the exact same tests passed locally (Python 3.13.7) — the attributes'
   behavior had changed between patch releases. Confirmed by pulling the real CI log
   (not guessed at): every `_can_fetch` call was returning "allowed" unconditionally,
   the same silent-permissiveness failure mode as defect 1, just relocated.

Final fix: `placeinator/jobs/sources/base.py::_parse_robots_groups` parses robots.txt
directly from raw text (RFC 9309 group semantics: consecutive `User-agent:` lines,
longest-matching product token wins outright, falls back to `*`), with no dependency on
`RobotFileParser` at all. Every adapter — `ats_feed` included, retroactively — goes
through this. The lesson generalizes past this one bug: undocumented stdlib internals
are not a foundation to build a compliance boundary on, however convenient the shortcut
looks in the moment.

---

## ADR 0004 — Alembic is the sole owner of database schema

- **Status:** Accepted
- **Date:** 2026-08-19
- **Supersedes:** the initial `create_all` bootstrap

### Context

The first implementation called `Base.metadata.create_all()` on startup while Alembic
was also configured, with the intention that Alembic would "take over from M1 onward".

This is a common and dangerous arrangement. A fresh install builds tables via
`create_all` and leaves `alembic_version` **empty**. The first real migration then
tries to create tables that already exist — failing on any machine that has run the
app before, while passing on a clean one. The bug is environment-dependent and
invisible during development.

A second problem compounds it: SQLite cannot `ALTER` most constraints, so Alembic runs
in **batch mode**, rebuilding each table and recreating its constraints. Batch mode can
only recreate constraints it can *name*, and SQLAlchemy's default is anonymous.

### Decision

**Alembic is the only thing that ever creates or alters schema.** `create_all` is not
called anywhere, including in the startup path.

- `placeinator/db/migrate.py::upgrade_to_head` runs on every sidecar boot.
- It resolves `alembic.ini` and `script_location` relative to the package file, not the
  CWD, so it also works inside a PyInstaller bundle.
- `alembic.ini` deliberately leaves `sqlalchemy.url` **unset**; `migrations/env.py`
  takes the URL from `placeinator.settings`, so the CLI and the running app can never
  target different databases.
- `migrations/env.py` sets `render_as_batch=True`, plus `compare_type` and
  `compare_server_default` for meaningful autogenerate diffs.
- `Base.metadata` carries a `NAMING_CONVENTION` for `ix`/`uq`/`ck`/`fk`/`pk`, so every
  constraint is nameable by batch mode.

### Consequences

- Fresh installs and upgraded installs converge on identical schema, always.
- Schema changes require a migration; there is no path that silently creates tables.
  After editing a model:

  ```bash
  .venv/Scripts/python.exe -m alembic revision --autogenerate -m "what changed"
  ```

- `alembic check` becomes a meaningful CI-able assertion that models and migrations
  have not drifted.
- Generated migrations under `migrations/versions/` are excluded from `ruff` — they are
  machine output, and reformatting them only creates churn against regenerated files.
- A test (`test_every_constraint_is_named`) fails if an anonymous constraint is ever
  introduced, because the cost of finding that out during a future migration is far
  higher than the cost of the test.

---

## ADR 0005 — fastembed + ONNX Runtime, never PyTorch

- **Status:** Accepted
- **Date:** 2026-08-19

### Context

The matching engine ([ADR 0002](#adr-0002--deterministic-engine-no-llm-generation)) needs
sentence embeddings computed locally, on CPU, inside a desktop app with a strict
footprint budget.

The obvious choice, `sentence-transformers`, depends on PyTorch. PyTorch adds roughly
2 GB to the installed size and seconds to process import time — costs that dominate
this application's entire budget, for a model of only ~130 MB.

### Decision

Use **`fastembed`** (ONNX Runtime) with **`BAAI/bge-small-en-v1.5`** (384-dim).

- Optional cross-encoder reranking runs over the top ~25 candidates only, never the
  full set.
- Vector search is a single NumPy matmul over precomputed vectors. At this scale
  (hundreds to low thousands of jobs) a vector database would be overhead, not
  optimization.
- `placeinator/matching/vectors.py` is the **only** place that encodes or decodes
  embeddings: float32 little-endian, C-contiguous, L2-normalized.

**PyTorch must never be added to the dependency tree.**

### Verification

This was the project's largest technical assumption, so it was resolved against the
real package index before any code was written against it. On Python 3.13:

```
fastembed 0.8.0
  onnxruntime 1.29.0, numpy 2.5.2, tokenizers 0.23.1,
  huggingface_hub 1.28.0, py_rust_stemmers 0.1.8, mmh3 5.2.1
```

All wheels. No source builds. **No PyTorch anywhere in the tree.**

### Consequences

- Meets the latency budget: embedding a ~40-chunk resume in under 200 ms, ranking 500
  cached jobs in under 50 ms.
- Bundle stays in the low hundreds of MB rather than multiple GB.
- Models are downloaded on first run into `Settings.models_dir` (the per-user data
  directory), never into the repository — so a dev checkout and a packaged install
  resolve them identically. M6 owns the download-with-progress UX.
- **Embeddings must carry provenance.** Changing the model would leave stored vectors
  deserialising successfully into meaningless numbers, silently degrading match quality
  with no error. `ResumeChunk` and `JobRequirement` therefore store `embedding_model`
  and `embedding_dim` alongside the bytes, making stale rows detectable and
  re-embeddable.
- onnxruntime ships native libraries, which makes it the likeliest PyInstaller
  packaging problem. Proving the packaged build is scheduled for M0/M1, not M6.

---

## ADR 0006 — Studio visual language, superseding the GitHub-adjacent direction

- **Status:** Accepted
- **Date:** 2026-08-19

### Context

The original requirements document (`docs/specification.md`, since retired —
its content is summarized in `docs/architecture.md`'s Milestone status and
module map) called for a flat, restrained visual language: "minimal, clean,
GitHub-inspired," a single accent color, subtle 1px borders, and explicitly
warned against "overly rounded 'AI SaaS' cards" and "excessive gradients."
Earlier in the project the user confirmed this direction directly, choosing
"GitHub-adjacent" over two warmer/rounder alternatives when asked.
`src/styles/index.css` and every shared component were built to that brief.

The user then supplied three reference screenshots of a Dribbble shot
("Synchronic — Studio Creative Practice System") and asked to match its
typography, fonts, and UI directly. That reference is close to the opposite of
the original brief on every axis it warned against: a serif display face for
headings, fully pill-shaped buttons, large card radii, a warm cream palette,
and a distinct accent color per section rather than one restrained accent.

Given three detailed, unambiguous reference images and an explicit "use the
same," this is read as a deliberate pivot rather than a subtle nudge, and
implemented as one. The original spec document was never edited to match at
the time — it stayed the user's original written brief while the
implementation departed from that section of it — and has since been
retired entirely now that the milestones it drove are built. This ADR exists
so that departure is a recorded decision, not silent drift.

### Decision

Rebuild the design tokens and shared components around the reference's
language:

**Typography.** `Fraunces` (soft-axis variant) for display headings —
`.display-heading`, used by `Page`'s `<h1>` and `SectionCard`'s `<h2>`. `Inter`
remains the UI/body face, now genuinely self-hosted via `@fontsource-variable`
rather than referenced by name and hoping the OS had it installed (a real gap
in the prior setup, fixed as part of this work). Both ship as local variable
font files — no runtime dependency on a font CDN, consistent with the rest of
the app running offline-first.

**Color.** A warm cream palette (`--canvas` `#f2f0e8`, `--canvas-subtle`
`#faf9f4`) replaces the cold white/grey GitHub palette. A brand
indigo-purple (`--accent`) remains the single global accent for primary
actions and focus rings, but each of the seven sections now also carries its
own muted accent (`--section-dashboard`, `--section-jobs`, ... —
`src/lib/nav.ts`), driving the sidebar's icon badges and every page's eyebrow
label via `Page`'s automatic `navItemForPath` lookup.

**Shape.** `--radius-panel` (20px) for cards, `--radius-input` (14px) for
controls and tables, `--radius-pill` (999px) for buttons. `.btn` establishes a
48px comfort target with a visible 3px focus ring and press feedback, matching
the reference's own stated principle ("Controls share a 48px comfort target,
visible keyboard focus, and contrast-safe states").

**Structure.** The reference keeps all chrome — logo, navigation, and utility
controls — in one sidebar column rather than splitting it across a header and
a rail. The app's separate top bar was removed; the theme toggle, collapse
toggle, and profile button moved into the sidebar's footer.

**Recurring pattern.** "SECTION / Display Heading / description" repeats at
two scales: `Page` for the page itself, `SectionCard` for panels within it
(the reference's "Weekly Thread" / "Current Care" cards). A card's eyebrow
color defaults to its own page's section color, but can be overridden to
borrow another section's color when a card is deliberately cross-referencing
it — the reference's own "Current Care" panel on its Observe-equivalent page
borrows Tend's teal for exactly this reason.

### Consequences

- **Positive:** a distinctive, considered visual identity in place of a
  generic "developer tool" look; genuinely offline font loading (a real fix,
  not just a side effect); a reusable eyebrow/heading pattern that
  automatically threads section color through every page without each route
  file wiring it by hand.
- **Cost:** every shared component (`Page`, `Form`, `Table`, `AppShell`) and
  every route needed a pass; this was a full re-theme, not a token tweak.
- **The original spec's UI section was aspirational text the implementation
  moved past**, not a description of the app — one of the reasons that
  document was retired rather than kept as a source of truth. Anyone wanting
  to know how the app currently looks should read this ADR and
  `docs/architecture.md`'s Frontend section instead.
- Nine icon paths from the earlier icon-placement pass (ADR-adjacent work
  from two sessions prior) carry forward unchanged into the new visual
  language — they were already the correct semantic choices; only their
  color and container treatment changed (a solid mono icon becomes a
  section-tinted icon in a soft rounded badge).
