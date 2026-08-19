"""Resume library and parsing (specification section 3).

Maintains multiple role-specific resumes, extracts structured content from PDF,
DOCX, and LaTeX sources, and recommends the best-matching resume per job.

``Resume.source_text`` is the authoritative copy of the source. LaTeX tailoring
splices byte ranges out of it, so it must never be re-derived from the file on
disk. Parsed units become ``ResumeChunk`` rows carrying their source spans.

Selection scores the job against every resume via :mod:`placeinator.matching`;
the user can always override the recommendation.

Entry points: ``parse_resume``, ``recommend_resume``.
"""
