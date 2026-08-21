"""JD-based LaTeX resume tailoring (specification section 5).

Restructures an existing LaTeX resume for a specific job by **reordering,
selecting, and emphasizing** existing content. It never rewrites prose.

``parsing.py`` splices the original source spans into a new order, which
makes the specification's "must not invent qualifications" requirement a
structural property rather than a promise -- and keeps custom macros intact.
Preamble and unrecognized constructs are immutable. ``tailoring.py`` scores
each movable unit against a job (reusing the same persisted embeddings
``placeinator.matching`` caches) and decides that order; removals are always
suggestions, never automatic -- see its module docstring.

Acceptance gate: parse then emit with no reordering reproduces the input
byte-for-byte (``tests/unit/test_latex_parsing.py``).

Entry points: ``parse_latex``, ``emit_latex`` (``parsing.py``), ``tailor_resume``
(``tailoring.py``). PDF compile is out of scope for this slice -- it's an
independent concern (TeX-distribution detection, subprocess), not a gap.
"""
