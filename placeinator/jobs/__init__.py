"""Job intelligence (specification section 2).

Normalizes postings from every source into ``Job`` rows, then applies the user's
preferences in two distinct passes:

* **Hard constraints** eliminate a job (minimum salary, bond duration, experience
  range, unacceptable location). Eliminated jobs are *kept* with
  ``Job.filtered_out_reason`` set, so the UI can explain the exclusion rather
  than silently hiding it.
* **Soft preferences** influence ranking only (preferred city, work mode,
  industry).

Discovery adapters live in :mod:`placeinator.jobs.sources`. Ranking combines the
semantic score from :mod:`placeinator.matching` with these preference signals.

Entry points: ``upsert_job_from_posting``, ``apply_hard_filters``, ``rank_jobs``.
"""
