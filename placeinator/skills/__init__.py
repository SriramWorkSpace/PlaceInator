"""Skill taxonomy and alias normalization.

``taxonomy.json`` maps surface forms to canonical skill ids
(``js | javascript | ecmascript -> javascript``) with category tags.

With no LLM to paper over vocabulary gaps, this file *is* the semantic backbone
of skill matching, gap analysis, and job filtering -- overall matching quality is
capped by its coverage. It is a first-class deliverable with its own tests, not
a lookup table to be filled in hastily.

Entry points: ``normalize_skill``, ``extract_skills``.
"""
