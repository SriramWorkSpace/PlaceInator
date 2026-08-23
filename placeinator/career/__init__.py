"""Career skill intelligence (specification section 4).

Aggregates required skills across the user's ranked target jobs, subtracts the
skills they already have, and prioritizes the gaps by frequency, role relevance,
and importance to selected opportunities.

Learning recommendations come from a curated ``resources.json`` keyed by
taxonomy id -- deterministic, so no link is ever invented. A skill with no
curated entry simply has none in the API response.

No dedicated table: this is a pure aggregation over data ``placeinator.jobs``
and ``placeinator.matching`` already keep fresh (``Job.required_skill_ids``,
``ResumeChunk.skill_ids``, ``rank_jobs``'s scores), the same "computed fresh,
no persistence" shape ``rank_jobs``/``list_notifications`` themselves use.

Entry points: ``gaps.analyze_skill_gaps`` (the real, session-backed entry
point) and ``gaps.aggregate_skill_gaps`` (the pure prioritization logic it
wraps, split out so it's unit-testable without a session), ``resources
.get_resource_library``.
"""
