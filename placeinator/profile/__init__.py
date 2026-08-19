"""Candidate profile and preferences (specification section 1).

Owns onboarding, personal and education details, career preferences, and
employment constraints (contract and bond limits). The profile is the anchor for
all personalization, and is also the identity used to recognise the user in
placement documents -- see :mod:`placeinator.placement.candidate_id`.

Single-user application: exactly one ``Profile`` row exists.

Entry point: ``ProfileService``.
"""
