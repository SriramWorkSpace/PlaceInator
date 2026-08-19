"""PlaceInator -- an intelligent placement assistant.

Resume-to-job semantic matching, JD-driven LaTeX resume tailoring, and
Gmail-to-Calendar placement automation, running entirely on the local machine.

This package is the sidecar: it owns all ML, document parsing, external
integrations, and the SQLite database. The Tauri shell never touches the
database. See docs/architecture.md.
"""

__version__ = "0.1.0"
