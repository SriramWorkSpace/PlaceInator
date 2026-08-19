# Architecture

How PlaceInator is put together and why. The feature requirements live in
[specification.md](./specification.md); the decisions behind this design live in
[decisions/](./decisions/).

## System shape

```
┌─────────────────────────── Tauri v2 shell (Rust) ───────────────────────────┐
│  window management · sidecar lifecycle · OAuth token storage (OS keychain)   │
│  ┌──────────────────── WebView2: React 18 + TypeScript ────────────────────┐ │
│  │  Dashboard │ Jobs │ Resumes │ Tailor │ Career │ Outreach │ Placement    │ │
│  │  Vite · Tailwind 4 · TanStack Query · Monaco (lazy, Tailor route only)  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────┬──────────────────────────────────────────┘
                    HTTP on 127.0.0.1:<ephemeral> + bearer token
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                    Python sidecar — FastAPI + uvicorn                       │
│  matching (fastembed/ONNX) · documents · latex · placement · job sources    │
│  SQLAlchemy ──► SQLite (sole writer, per-user data dir, Alembic-managed)    │
└─────────────────────────────────────────────────────────────────────────────┘
```

Python owns SQLite outright — the Rust side never opens it. One writer, one schema,
one migration path. See [ADR 0001](./decisions/0001-tauri-python-sidecar.md).

## Startup handshake

The sidecar binds its own ephemeral loopback socket, then prints **exactly one line**
to stdout before serving:

```
PLACEINATOR_READY {"port": 51234, "token": "..."}
```

The shell reads that line, stops reading stdout, and injects both values into the
WebView as `window.__PLACEINATOR__`.

Two properties make this work, and both are load-bearing:

1. **Python binds the socket, not uvicorn.** That is what makes the port knowable
   *before* the server starts accepting connections.
2. **Everything the process logs goes to stderr.** uvicorn ships its access-log handler
   pointed at stdout, so `_stderr_only_log_config()` in `placeinator/main.py` repoints
   every handler. stdout carries one line for the process lifetime and nothing else.

A loopback port is reachable by any local process, so **every route except `/health`
requires the bearer token**. `/health` is deliberately open — the shell polls it to
learn when the sidecar is up, before it has anything to authenticate with.

Without the Tauri shell, the frontend falls back to `VITE_SIDECAR_PORT` /
`VITE_SIDECAR_TOKEN`, which is how the UI is developed while Rust is unavailable.

## Latency budget

The whole point of this stack. Targets, and what makes each achievable:

| Path | Target | Approach |
|---|---|---|
| Cold start to interactive | < 1.5 s | Sidecar starts async; UI renders from cache first |
| Embed one resume (~40 chunks) | < 200 ms | ONNX Runtime CPU, int8, batched |
| Rank 500 cached jobs | < 50 ms | Precomputed vectors, one NumPy matmul |
| Tailor a resume | < 2 s | Parse + score + splice, no network |
| Idle memory | ~120 MB | Native WebView, no bundled browser engine |

## Module map

Flat feature packages, each mapping to a numbered specification section.

| Package | Spec | Responsibility |
|---|---|---|
| `placeinator/api/` | — | FastAPI routers, one module per feature, each exporting `router` |
| `placeinator/db/` | — | ORM models, session, enums, column types, migration runner |
| `placeinator/profile/` | §1 | Onboarding, career preferences, employment constraints |
| `placeinator/jobs/` | §2 | Normalization, hard filters, soft-preference scoring |
| `placeinator/jobs/sources/` | §2 | Pluggable discovery adapters ([ADR 0003](./decisions/0003-job-source-boundary.md)) |
| `placeinator/resumes/` | §3 | Resume library, parsing, section extraction, selection |
| `placeinator/matching/` | — | The scoring engine and embedding encode/decode |
| `placeinator/skills/` | — | Skill taxonomy and alias normalization |
| `placeinator/career/` | §4 | Skill-gap analysis, prioritization, recommendations |
| `placeinator/latex/` | §5 | LaTeX parse, score, reorder, splice-emit, compile |
| `placeinator/outreach/` | §6 | Cold-mail target selection and draft generation |
| `placeinator/placement/` | §7 | Gmail, attachments, candidate ID, events, calendar |

Root modules: `app.py` (application factory), `main.py` (entry point and handshake),
`settings.py` (configuration and paths), `security.py` (token auth).

## The matching engine

Everything else depends on this. Deterministic and explainable by construction — with
no LLM there is no black box to hide behind ([ADR 0002](./decisions/0002-deterministic-no-llm.md)).

**Chunking.** Resumes become typed chunks (`ChunkKind`), each retaining its source span.
Job descriptions become typed requirement lines (`RequirementKind`).

**Component scores**, each in [0,1] and each stored with its evidence:

| Component | Method |
|---|---|
| `overall` | Cosine of mean-pooled resume vs mean-pooled JD |
| `skills` | Jaccard over normalized taxonomy IDs, blended with embedding similarity for unmatched terms |
| `projects` | Per JD responsibility, max cosine over project bullets; mean of top-k |
| `experience` | Same shape over experience bullets, gated by years-of-experience fit |
| `role` | Cosine of JD title vs resume target role and the user's target roles |

The final score is a weighted sum, with weights in `config/scoring.toml` so tuning is
not a code change.

**One record powers three features.** Every score writes a `MatchResult.explanation`
capturing each component's value, weight, and top contributing chunk pairs. That single
record drives notification reasons (spec line 143), resume recommendation (line 210),
and the tailoring change log (lines 349-377).

**Embedding contract.** float32 little-endian, C-contiguous, L2-normalized, written
only through `placeinator/matching/vectors.py`, and always stamped with
`embedding_model` and `embedding_dim` so a model change leaves stale rows detectable
rather than silently wrong.

## LaTeX tailoring — the splice design

The mechanism that makes "never invent anything" a structural property rather than a
promise:

1. `pylatexenc.latexwalker` produces a node tree; each node retains its `(start, end)`
   offsets into the original source.
2. **Movable units** are identified: `\section` blocks, `itemize` items, project
   environments, skill entries. Preamble, macros, and anything unrecognized are
   **immutable**.
3. Each unit is scored against the JD by the matching engine.
4. Sections reorder by a permitted whitelist order, projects and bullets by score,
   skills by JD coverage. Units below `drop_threshold` become removal *candidates*.
5. **Output is produced by splicing the original source spans in the new order.**
   Nothing is regenerated, so invention is impossible and custom macros survive intact.
6. Removals require explicit confirmation in the UI diff. Never silent.

**Acceptance gate:** parse → emit with no reordering must reproduce the input
byte-for-byte across a corpus of real `.tex` files.

## Data layer

SQLite in the per-user data directory (`Settings.data_dir`), WAL mode, foreign keys on.

- **Alembic is the only thing that creates or alters schema** — see
  [ADR 0004](./decisions/0004-alembic-sole-schema-owner.md).
- Enum columns go through `placeinator/db/types.py::enum_column`, never bare `String`,
  so they round-trip as real enum types and reject corrupt values loudly.
- `Base.metadata` carries a constraint naming convention, because SQLite migrations run
  in Alembic batch mode and batch mode can only recreate constraints it can name.

## Frontend

A warm "studio" visual language — self-hosted Fraunces for display headings,
Inter for UI text, cream canvas, fully-rounded pill controls, and a distinct
muted accent color per section — superseding the original flat GitHub-adjacent
brief. See [ADR 0006](./decisions/0006-studio-visual-language.md) for why, and
for the note that `specification.md`'s UI section (lines 767-807) is not kept
in sync with this. Design tokens live in `src/styles/index.css` and handle
light, dark, and system themes.

`Page` and `SectionCard` (`src/components/Page.tsx`) share one recurring
pattern — a colored eyebrow naming the section, a serif display heading, then
content — derived automatically from the current route via
`navItemForPath` (`src/lib/nav.ts`), so a route file only ever passes a title
and description.

`src/components/AppShell.tsx` keeps all chrome in a single sidebar column:
logo, the seven-item navigation from spec lines 812-826 plus Settings, and a
footer row for the collapse toggle, theme toggle, and profile indicator.
There is deliberately no separate top bar. `src/routes/` holds one module per
nav item.

**Monaco is lazy-loaded on the Tailor route only** — it is several MB against a current
total bundle of ~180 KB, and no other route needs an editor.
