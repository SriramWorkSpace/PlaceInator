"""Placement communication intelligence (specification section 7).

The placement-specific automation layer:

``Gmail -> attachments -> candidate detection -> status -> events -> Calendar``

Processes placement documents (XLSX, PDF, DOCX, scans), normalizes arbitrary
column names to canonical fields, determines whether the user appears in a
document, classifies status into SHORTLISTED / REJECTED / PENDING, extracts
event details, and creates calendar events after a duplicate check.

Confidence gates every step. Anything below the auto-accept threshold lands in a
**review queue** rather than acting on a guess -- a false positive here tells
someone they were shortlisted when they were not.

Entry points: ``scan_inbox``, ``identify_candidate``, ``extract_events``.
"""
