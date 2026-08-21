# Build Guide

How PlaceInator was actually built: what came first, why each major choice was
made, and what real problems came up along the way. This is a story, not a
reference — for those, see:

- [specification.md](./specification.md) — what the app should do
- [architecture.md](./architecture.md) — how it's built
- [decisions.md](./decisions.md) — the ADRs (formal decision records)
- [roadmap.md](./roadmap.md) — milestone status
- [CHANGELOG.md](./CHANGELOG.md) — every change, in order

Everything below is grounded in those docs or in work verified live during
development. Nothing here is guessed or aspirational.

## Two rules that shaped every milestone

1. **Verify before coding.** Before writing code against an assumption —
   "`fastembed` won't pull in PyTorch," "this site's `robots.txt` allows this
   page," "`pylatexenc` structures its output this way" — that assumption was
   checked against the real thing first.
2. **Compiling isn't done. Proving it works is done.** Every milestone has a
   "done when" test against the real, running app — not just a green test
   suite.

## What PlaceInator is

A desktop app with three parts:

- A **Tauri (Rust) shell** — the actual window
- A **React + TypeScript UI** running inside it
- A **Python sidecar** (FastAPI), talking to the UI over a local, authenticated
  HTTP connection

The sidecar does all the heavy lifting: it owns the database, runs the ML
model, parses documents, and talks to any external services. See ADR 0001 for
why this split (rather than one single-language app) was chosen.

**The one rule that shapes everything else: no LLM, anywhere.** Not for
matching resumes to jobs, not for tailoring a resume, not for drafting outreach
emails. Every feature that *sounds* like it needs a language model is instead
built as a deterministic, rule-based system:

| Feature | How it actually works | Milestone |
|---|---|---|
| Resume-job matching | Sentence embeddings (math, not text generation) + a hand-built skill list | M1 |
| Resume tailoring | Reorders the user's own text; never writes new sentences | M3 |
| Outreach emails (planned) | Fill-in-the-blank templates, not generated | M5 |
| Reading placement emails (planned) | Keyword and pattern matching | M4 |

This was decided up front (ADR 0002), not discovered as a limitation later.

## M0 — Foundation

**Built:** the Python sidecar, the database schema, the React app shell, CI,
and — much later — the Tauri desktop window itself.

**The handshake.** The sidecar picks its own open port, then prints one line:

```
PLACEINATOR_READY {"port": 51234, "token": "..."}
```

The Rust shell reads that line and hands the port + token to the UI. Every API
route except `/health` requires that token — `/health` stays open because the
shell needs *something* to check before it has a token to prove who it is.

Before the desktop shell existed, the frontend could still run on its own
(pointed at a manually-started sidecar via two environment variables) — which
is what let frontend work continue for months before Rust was even installed.

**Getting Rust working was the hard part**, and it wasn't Rust's fault — two
environment issues, both easy to misdiagnose:

- Git for Windows installs its own `link.exe` (unrelated to compilers — it's a
  file-linking utility), and it was shadowing the *real* linker Rust needed.
  The error it produced looked nothing like a compiler problem.
- The installed Visual Studio was too new for Rust's own tooling to recognize
  automatically. Confirmed by checking a different, more reliable detection
  tool (`vswhere`), which found it fine.

Both were fixed with one config file (kept local to this machine, not
committed to the repo) that points Rust directly at the real tools instead of
letting it search and guess.

**Once Rust worked**, the shell itself was built: spawn the sidecar, wait for
its handshake line (with a timeout — so a broken sidecar fails with an error
instead of freezing the window forever), hand the port/token to the UI, and
kill the sidecar when the window closes. This was tested for real — a real
window opened, showing real data, and a real close checked that no leftover
processes were left running afterward.

**Left for later, on purpose:** packaging the sidecar into a single `.exe`
(PyInstaller), and a stronger guarantee that the sidecar dies even if the app
crashes rather than closes normally. Both are separate, riskier pieces of work
that didn't need to ride along with the first Rust code this project ever had.

## M1 — Profile, Resume, and Matching

**Built:** onboarding, the resume library (PDF/DOCX/LaTeX upload), a skill
list, and the matching engine that scores a resume against a job and explains
why.

### Why fastembed?

This was the biggest technical bet in the project, so it was checked directly
before anything was built on top of it. There are really two separate
questions here, usually mixed together — worth answering separately.

**Question 1: what *kind* of model?** Not a custom-trained model (something
like a BiLSTM + Attention network built from scratch). Two reasons:

- **It would be worse, not just harder.** Pretrained sentence-embedding models
  (the modern BERT/transformer family) have outperformed BiLSTM-style models
  at this exact task — comparing the meaning of two pieces of text — for
  years. This isn't a case of "the fancy option is overkill"; the simpler
  RNN-based option genuinely does worse here.
- **There's no data to train one anyway.** Training a model from scratch needs
  a large labeled dataset of "this resume line matches this job requirement"
  examples. That dataset doesn't exist for this project, and building one is
  its own project. A pretrained model needs none of that — it's used as-is.

**Question 2: which library runs that pretrained model?** This is what
`fastembed` vs. `sentence-transformers` actually comes down to — both can run
the same kind of model, so it's a size argument, not an accuracy one.
`sentence-transformers` depends on PyTorch, which adds about **2 GB** to the
install and real startup delay — a lot to pay for a ~130 MB model in an app
that's supposed to be light and fast. `fastembed` runs the same class of model
through ONNX Runtime instead, with no PyTorch anywhere. Checked directly
before committing to it:

```
fastembed 0.8.0
  onnxruntime 1.29.0, numpy 2.5.2, tokenizers 0.23.1,
  huggingface_hub 1.28.0, py_rust_stemmers 0.1.8, mmh3 5.2.1
```

No PyTorch, no surprises. The model itself is `BAAI/bge-small-en-v1.5` — small
enough to stay fast (well under the app's own speed targets) while still being
a solid, general-purpose choice.

**One consequence worth calling out:** with no language model to fill in
vocabulary gaps, the hand-built skill list
(`placeinator/skills/taxonomy.json`) matters a lot more than it might in an
LLM-based app — it's the thing doing the "understanding" that a model would
otherwise do. It currently covers 89 skills, well short of the ~600 originally
planned, and that's tracked openly as the project's clearest known gap rather
than something to quietly work around.

**Also worth knowing:** every embedding the app stores is tagged with exactly
which model produced it. That sounds minor, but it's what let later milestones
safely *reuse* stored embeddings instead of recomputing them every time —
without that tag, there'd be no safe way to tell a fresh embedding from a
stale one.

**Done when:** add 3 resumes, paste a job description, get a ranked match with
a readable explanation — in under 2 seconds, tested against the real app.

## M2 — Job Intelligence

**Built:** four job-board integrations (Greenhouse/Lever/Ashby, Indeed,
LinkedIn, Naukri), filtering, ranking, and notifications.

**Every integration was checked against the real site first**, and that
changed the plan more than once. Indeed, for example, was expected to need a
real browser to scrape — turned out its search page already includes the job
data as plain JSON, so a simple HTTP request is enough. LinkedIn and Naukri, on
the other hand, really do block almost everything (LinkedIn via its own
published rules, Naukri via active bot detection) — and per this project's own
rule, "blocked" is respected, not worked around. The app never fakes being a
browser to sneak past that.

**A real bug was found and fixed — twice.** First: Python's built-in
robots.txt reader has a known flaw — it applies the *first* matching rule in a
file rather than the *most specific* one, which is backwards from how the
standard actually works. Indeed's robots.txt happens to be shaped exactly the
way that exposes this. The first fix patched around Python's own reader rather
than replacing it — and that patch relied on internal details of that reader
that turned out to behave differently between two Python versions, so the fix
silently failed in one environment while appearing to work in another. The
real fix replaced the whole approach: read the rules directly, with no
dependency on Python's flawed reader at all.

**A cleanup pass later closed a gap between "built" and "usable."** The
Greenhouse/Lever/Ashby integration — the most reliable one, since it uses
official APIs rather than scraping — had been fully working for a while but
had no button in the UI to actually use it. Fixed, along with a few related
gaps (a broken link that discovered jobs couldn't be opened from, network
failures showing as raw errors instead of a clean message). This pass also
promoted a previously-optional test suite to a required one — and that
promotion immediately caught a real bug: a matching score could, in rare
cases, land very slightly above its supposed maximum, due to how floating-point
math behaves differently on different processors. Fixed with a proper bound.

**Also added:** a cache for match scores, since re-scoring every job against
every resume on every screen refresh was wasteful. A stored score is now
reused as-is if nothing relevant has changed since it was computed.

## M3 — LaTeX Resume Tailoring

**Built:** a tool that takes an existing LaTeX resume and a job description,
and reorders (never rewrites) the resume's content to better match the job.

The hard rule here, inherited from the no-LLM constraint: the tool must never
invent a skill, project, or line of experience the user didn't already write.
Rather than just instructing a model to behave, the design makes this
*physically impossible* — the tool only ever cuts and pastes exact chunks of
the user's original text. It has no way to write anything new.

**Building this required understanding a LaTeX-parsing library's real
behavior**, which turned out to differ from what its documentation implied in
two important ways — checked directly, not assumed:

- A resume "section" doesn't come back as one clean block containing its
  content. The heading and the content after it are separate, unconnected
  pieces.
- Custom formatting commands — which is how most real resume templates
  actually write their bullet points — aren't understood by the library at
  all; it just sees them as plain, disconnected text.

Both findings ruled out the "obvious" design (walk a tree of the document's
structure). Instead, the tool treats the whole file as a flat sequence of
labeled chunks and only ever reorders *whole chunks*. This makes one important
guarantee easy to test and trust: reordering nothing at all must reproduce the
original file byte-for-byte — and it does, provably, because of how the chunks
are built, not because of a rule someone has to remember to follow.

**Scoring reuses the same infrastructure M1 and M2 already built** — the same
stored embeddings, the same scoring math — rather than building a second,
separate scoring system from scratch.

**Nothing is ever deleted automatically.** A low-scoring bullet point is
flagged as a *suggestion* to remove, but stays in the resume unless the user
explicitly says to drop it.

**One more real bug, found late:** the code editor used to display the LaTeX
output (Monaco) defaults to loading itself from the internet at runtime,
rather than using the copy already bundled with the app — which would have
silently broken this whole feature the moment someone used it offline. Fixed
by pointing it at the bundled copy instead, and confirmed against a real
production build, not just a passing type-check.

**Left out on purpose:** actually compiling the LaTeX into a PDF. That's a
separate, genuinely independent piece of work (checking for a LaTeX
installation, running it as a subprocess, handling failure gracefully), and
bundling it into the riskiest new feature in the app wasn't worth it.

## Where things stand

| Milestone | Status |
|---|---|
| M0 — Foundation | Sidecar + web app done; desktop shell working in development mode; packaging not done yet |
| M1 — Profile, Resume, Matching | Done |
| M2 — Job Intelligence | Done |
| M3 — LaTeX Tailoring | Done, except PDF export |
| M4 — Placement Automation | Not started |
| M5 — Career Intelligence & Outreach | Not started |
| M6 — Hardening & Release | Not started |

Rough numbers: 50 Python files, 30 TypeScript files, 175 tests (139 run
automatically; 36 more need either the real ML model or a live internet
connection, so they're opt-in). For the always-current status, see
[roadmap.md](./roadmap.md); for the full history, see
[CHANGELOG.md](./CHANGELOG.md).
