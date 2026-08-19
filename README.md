# PlaceInator

An intelligent placement assistant: resume↔job semantic matching, JD-driven LaTeX
resume tailoring, and Gmail→Calendar placement automation. Everything runs locally.

## Documentation

| Document | What it covers |
|---|---|
| [Specification](docs/specification.md) | Feature requirements — the source of truth |
| [Architecture](docs/architecture.md) | System design, handshake protocol, module map |
| [Roadmap](docs/roadmap.md) | Milestones M0–M6 |
| [Changelog](docs/CHANGELOG.md) | What changed and when |
| [Foundation audit](docs/audit-2026-08-19.md) | Nine defects found before development, in detail |
| [Decisions](docs/decisions/) | ADRs recording the durable "why" |

## Architecture in one picture

```
Tauri shell (Rust)  ──127.0.0.1:<ephemeral> + bearer token──►  Python sidecar
  React + TS UI                                                  FastAPI
  Monaco editors                                                 fastembed / ONNX
                                                                 SQLite (sole writer)
```

The sidecar prints exactly one line to stdout on startup, and the shell reads it:

```
PLACEINATOR_READY {"port": 51234, "token": "..."}
```

Everything it logs goes to **stderr**, so stdout carries that one line and nothing else
for the process lifetime.

## Prerequisites

| Tool | Version | Required for |
|---|---|---|
| Python | 3.11+ (developed on 3.13) | sidecar |
| Node.js | 20+ | frontend |
| Rust + MSVC build tools | stable | Tauri shell — **not yet installed** |
| MiKTeX or TeX Live | any | optional PDF compile only |
| Tesseract OCR | any | optional scanned-document support only |

The last three are optional in the strict sense that the app must detect their absence
and degrade with an explanation rather than erroring.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
npm install
```

## Running

Without a Rust toolchain, run the two halves separately:

```bash
# Terminal 1 — sidecar. Note the port and token it prints.
.venv/Scripts/python.exe -m placeinator.main

# Terminal 2 — UI, pointed at that sidecar.
VITE_SIDECAR_PORT=<port> VITE_SIDECAR_TOKEN=<token> npm run dev
```

Once Rust is installed, `npm run tauri dev` launches both together.

## Checks

```bash
.venv/Scripts/python.exe -m pytest tests/            # "-m live" opts into network tests
.venv/Scripts/python.exe -m ruff check placeinator tests migrations
.venv/Scripts/python.exe -m mypy placeinator
npm run typecheck && npm run lint && npm run build && npm audit
```

## Layout

```
placeinator/      Python sidecar — flat feature packages, one per spec section
  api/ db/        HTTP layer and data layer
  matching/       the scoring engine everything depends on
  skills/         taxonomy — the semantic backbone, since there is no LLM
migrations/       Alembic; the only thing that creates or alters schema
src/              React frontend (routes/, components/, lib/, styles/)
src-tauri/        Rust shell — blocked on the Rust toolchain
tests/            unit/ (in-process) · integration/ (real I/O) · fixtures/ (golden files)
docs/             specification, architecture, roadmap, changelog, ADRs
```

## Database

SQLite in the per-user data directory, owned exclusively by the Python side.
**Alembic is the only thing that creates or alters schema** — never call `create_all`
in application code. After changing a model:

```bash
.venv/Scripts/python.exe -m alembic revision --autogenerate -m "what changed"
.venv/Scripts/python.exe -m alembic check      # asserts models and migrations agree
```

Migrations run automatically on sidecar startup. `Base.metadata` carries a constraint
naming convention because SQLite requires Alembic's batch mode for most alterations,
and batch mode can only recreate constraints it can name — see
[ADR 0004](docs/decisions.md#adr-0004--alembic-is-the-sole-owner-of-database-schema).
