# Changelog

All notable changes to this project are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Frontend visual language rebuilt around a warm "studio" reference**,
  superseding the earlier GitHub-adjacent direction — self-hosted Fraunces
  display serif, cream palette, pill controls, per-section accent colors.
  See [ADR 0006](./decisions/0006-studio-visual-language.md). Fixed a real
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
  [ADR 0004](./decisions/0004-alembic-sole-schema-owner.md).
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

### Known blockers

- **Rust and MSVC build tools are not installed**, so `src-tauri/` cannot be scaffolded
  or built. Deliberately non-fatal: the frontend falls back to `VITE_SIDECAR_PORT` /
  `VITE_SIDECAR_TOKEN`, so both halves run separately today.
