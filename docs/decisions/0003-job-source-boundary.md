# ADR 0003 — Job source adapters and their hard boundary

- **Status:** Accepted
- **Date:** 2026-08-19

## Context

The spec asks for job discovery from "supported sources" ([specification.md](../specification.md)
§2). The user chose to target **Indeed, Naukri, and LinkedIn** by scraping.

That choice runs into a limit the spec itself sets. Lines 836-842 place the following
explicitly out of scope:

> It will not attempt to bypass: CAPTCHA, Login requirements, MFA, Bot detection,
> Application-site restrictions

Those two requirements are in tension, because LinkedIn and Naukri gate most job search
behind login and active bot detection. The tension is resolved in favour of the spec's
own stated boundary — it is the user's written constraint, not an external one.

## Decision

Build a pluggable adapter layer targeting all three sites, which **operates only on
what is reachable without defeating an access control**.

`JobSource.fetch(query) -> FetchResult`, where `FetchResult` is either postings or
`SourceBlocked(reason)`.

Shared infrastructure in `placeinator/jobs/sources/base.py`:

- `robots.txt` checking via `urllib.robotparser`
- per-source token-bucket rate limiting and exponential backoff
- response caching keyed by URL

**When an adapter meets a login wall, CAPTCHA, or bot-detection challenge, it returns
`SourceBlocked` and stops.** It does not solve, evade, or authenticate through it.

Adapters, in expected-success order:

| Adapter | Expected coverage |
|---|---|
| `indeed` | Good — usable logged-out search pages |
| `ats_feed` | Reliable but narrow — Greenhouse/Lever/Ashby public JSON, fully permitted |
| `linkedin` | Thin — public job-view pages only |
| `naukri` | Thin — expect frequent `SourceBlocked` |
| `manual` | Always works — paste a URL or raw JD |

## Consequences

- **Coverage on LinkedIn and Naukri will be materially thinner than on Indeed.** This
  is a direct consequence of the spec's own boundary and should not be read as an
  implementation gap to be fixed later.
- `manual` is **not optional**. Spec §5 requires JD paste regardless, and it is the
  fallback whenever a source blocks.
- `SourceBlocked` is a first-class UI state, not an error. The UI shows the
  manual-paste path rather than a failure.
- Selector fragility is expected, not exceptional. Each adapter ships golden-HTML
  fixtures plus a `live`-marked test (deselected by default via `-m 'not live'`), so a
  break reads as "selectors moved" rather than "the app is broken".
- The project never automatically submits applications; the user remains in control of
  final submission and of sending outreach email (spec lines 834, 844).
