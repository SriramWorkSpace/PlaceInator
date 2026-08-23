"""Cold-outreach email template (spec §6, ADR 0002): a single Jinja2
template filled from real, already-extracted data -- never generated prose.
This module is deliberately a pure function of its arguments (no session, no
DB) so it can be unit-tested directly with synthetic-but-realistic inputs;
placeinator.outreach.service is what pulls the real personalization data
(profile fields, MatchResult.explanation's top contributing chunks) out of
the database before calling here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jinja2 import Environment

# trim_blocks/lstrip_blocks keep {% %} control lines from leaving behind
# blank lines in the rendered output -- without them, every `{% if %}`
# below would show up as an empty line whenever its condition is false.
_ENV = Environment(trim_blocks=True, lstrip_blocks=True, autoescape=False)

_SUBJECT_TEMPLATE = _ENV.from_string("Application for {{ designation }} at {{ company }}")

_BODY_TEMPLATE = _ENV.from_string(
    """Dear {{ company }} Hiring Team,

I'm {{ full_name }}{% if target_role %}, currently focused on {{ target_role }} roles{% endif %}, \
and I'm writing to express interest in the {{ designation }} position\
{% if location %} in {{ location }}{% endif %}.
{% if highlights %}

A few things from my background that seem directly relevant:
{% for highlight in highlights %}
- {{ highlight }}
{% endfor %}
{% endif %}
{% if matched_skills %}

This role's emphasis on {{ matched_skills | join(", ") }} lines up closely with my experience.
{% endif %}

I'd welcome the chance to discuss how I could contribute to {{ company }}. Thank you for your \
time and consideration.

Best regards,
{{ full_name }}
{% if email %}{{ email }}
{% endif %}
{% if phone %}{{ phone }}
{% endif %}"""
)

# A cosmetic pass, not a correctness one: whichever optional sections above
# are skipped can still leave more than one consecutive blank line.
_EXTRA_BLANK_LINES_RE = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class DraftContent:
    subject: str
    body: str


def render_cold_email(
    *,
    full_name: str,
    email: str | None,
    phone: str | None,
    target_role: str | None,
    company: str,
    designation: str,
    location: str | None,
    highlights: list[str],
    matched_skills: list[str],
) -> DraftContent:
    """Every argument here must already be real data -- there is no field
    this function can fill in on its own. `highlights` should be real resume
    bullet text (see placeinator.outreach.service), never invented."""
    context = {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "target_role": target_role,
        "company": company,
        "designation": designation,
        "location": location,
        "highlights": highlights,
        "matched_skills": matched_skills,
    }
    subject = _SUBJECT_TEMPLATE.render(**context).strip()
    body = _EXTRA_BLANK_LINES_RE.sub("\n\n", _BODY_TEMPLATE.render(**context)).strip()
    return DraftContent(subject=subject, body=body)
