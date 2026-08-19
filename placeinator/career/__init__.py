"""Career skill intelligence (specification section 4).

Aggregates required skills across the user's ranked target jobs, subtracts the
skills they already have, and prioritizes the gaps by frequency, role relevance,
and importance to selected opportunities.

Learning recommendations come from a curated ``resources.json`` keyed by
taxonomy id -- deterministic, so no link is ever invented.

Entry points: ``analyze_skill_gaps``, ``prioritize_gaps``.
"""
