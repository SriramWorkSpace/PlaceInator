"""Placement communication intelligence (specification section 7).

The placement-specific automation layer:

``Gmail -> attachments -> candidate detection -> status -> events -> Calendar``

Processes placement documents (XLSX, PDF, DOCX; a scanned PDF falls back to
OCR, see ``ocr.extract_text_via_ocr`` -- text-only, always routed to the
review queue, never auto-accepted, since OCR'd text is meaningfully less
reliable evidence than a real structured field match), normalizes
arbitrary column names to canonical fields, determines whether the user
appears in a document, classifies status into SHORTLISTED / REJECTED /
PENDING, extracts event details, and creates calendar events after a
duplicate check.

Confidence gates every step. Anything below the auto-accept threshold lands in a
**review queue** rather than acting on a guess -- a false positive here tells
someone they were shortlisted when they were not.

Modules: ``auth`` (OAuth + OS-keychain token storage), ``gmail``
(incremental fetch), ``parsing`` (attachment -> rows), ``ocr`` (scanned-PDF
text fallback), ``headers`` (column-name normalization), ``candidates``
(confidence-scored identification), ``classification`` (status), ``events``
(extraction + dedupe key), ``calendar`` (event creation). ``service.sync``
orchestrates all of them end to end; ``service.confirm_record``/
``reject_record`` resolve a review-queue item.
"""
