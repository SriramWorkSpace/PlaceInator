"""JD-based LaTeX resume tailoring (specification section 5).

Restructures an existing LaTeX resume for a specific job by **reordering,
selecting, and emphasizing** existing content. It never rewrites prose.

The emitter works by splicing the original source spans into a new order, which
makes the specification's "must not invent qualifications" requirement a
structural property rather than a promise -- and keeps custom macros intact.
Preamble and unrecognized constructs are immutable; removals always require
explicit user confirmation.

Acceptance gate: parse then emit with no reordering must reproduce the input
byte-for-byte.

Entry points: ``parse_latex``, ``tailor_resume``, ``compile_pdf``.
"""
