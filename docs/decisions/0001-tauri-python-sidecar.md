# ADR 0001 — Tauri v2 shell with a Python sidecar

- **Status:** Accepted
- **Date:** 2026-08-19

## Context

PlaceInator is a desktop application with a hard requirement for low memory footprint
and low UI latency. It also needs three heavy capabilities that all happen to be
Python's strongest ground: ONNX-based sentence embeddings, document parsing
(PDF/XLSX/DOCX/LaTeX), and Google API integration.

Two further constraints pull in opposite directions:

- The spec ([specification.md](../specification.md) line 828) wants the Resume Tailoring
  page to feel like a developer workspace, with the JD and LaTeX source in real editor
  panels. That points at a web view and Monaco.
- The ML and document stack is mature in Python and thin or absent in Rust. Rewriting
  it would be a project in itself.

Options considered: Tauri + Python sidecar; PySide6 (single-language Python/Qt);
Electron + Python sidecar; Flutter desktop + Python sidecar.

## Decision

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

## Consequences

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
