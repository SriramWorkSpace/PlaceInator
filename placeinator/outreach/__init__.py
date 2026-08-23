"""Personalized cold outreach (specification section 6).

Selects high-value targets and drafts personalized emails from the user's
profile, the company, and the opportunity. Personalization draws on the top
contributing chunks recorded in ``MatchResult.explanation``, so the claims in a
draft trace back to real resume content.

Jinja2 templates only -- no generated prose. The system prepares drafts for
review; it never sends without the user in control -- there is deliberately
no "sent" status anywhere in this package, since the app has no way to know
whether a draft was actually sent outside itself.

Entry points: ``service.list_targets`` (reuses ``placeinator.jobs.service
.rank_jobs`` directly for target selection rather than a second scorer),
``service.draft_email``.
"""
