# Build Guide

A step-by-step account of how PlaceInator was actually built — what was built in
what order, why each major technical choice was made, and what real problems came
up along the way. This is a narrative companion to the other docs, not a
replacement for them:

- [specification.md](./specification.md) — what the app is supposed to do
- [architecture.md](./architecture.md) — how it's built, as a reference
- [decisions.md](./decisions.md) — the ADRs, as standalone durable records
- [roadmap.md](./roadmap.md) — milestone status
- [CHANGELOG.md](./CHANGELOG.md) — chronological, entry-per-change

This file exists because none of those answer "how did this get built, in what
order, and why" as a single readable story. Every claim below is grounded in the
ADRs, the CHANGELOG, or work verified live during development — nothing here is
aspirational or invented.

## Development approach

Two rules shaped every milestone, stated once here rather than repeated at each
step below:

1. **Verify before coding.** Every non-trivial technical assumption — whether
   `fastembed` actually installs without pulling in PyTorch, how a real job
   board's `robots.txt` actually behaves, what `pylatexenc` actually returns for
   a real `.tex` file — was checked against the real thing before code was
   written against it, not assumed from documentation or memory. ADR 0005's
   "Verification" section and `placeinator/latex/parsing.py`'s module docstring
   are the two most visible examples, but the discipline runs throughout.
2. **A feature isn't done until it's proven, not just compiled.** "Done when"
   criteria appear throughout `roadmap.md` for exactly this reason — M1's bar is
   "add 3 resumes → paste a JD → get a ranked recommendation, verified live
   through the actual UI, not just the test suite." M0's Tauri shell was verified
   the same way: a real window, a real close event, a real check for orphaned
   processes, not just `cargo check` passing.

## Step 0 — What PlaceInator is

A local-first placement assistant: a Tauri v2 desktop shell (Rust) hosting a
React/TypeScript UI, talking to a Python FastAPI sidecar over authenticated
loopback HTTP. The sidecar owns SQLite, all ML (embeddings), all document
parsing, and all external integration work. See ADR 0001 for why this shape was
chosen over a single-process alternative (PySide6, Electron+Python, Flutter
desktop+Python).

The load-bearing constraint across the whole project is **ADR 0002:
deterministic engine, no LLM generation.** Nothing in this app calls an LLM, ever
— not for matching, not for tailoring, not for outreach drafting, not for
placement-document extraction. Every one of those spec features that *reads* as
generative is instead implemented deterministically:

| Spec feature | How it's actually done | Milestone |
|---|---|---|
| Resume-job matching | Local sentence embeddings + curated skill taxonomy | M1 |
| Resume tailoring | Reorders/splices the user's own source; never rewrites | M3 |
| Cold outreach (planned) | Jinja2 templates filled from match evidence | M5 |
| Placement extraction (planned) | Keyword rules + fuzzy header matching | M4 |

This isn't a limitation worked around after the fact — it's the starting
constraint every milestone below was designed against.

## Step 1 — M0: Foundation

**Built:** the Python sidecar (handshake protocol, bearer-token auth), the full
ORM schema (9 tables, Alembic-managed from the first migration), the React
frontend shell (seven routes, typed API client), CI, and — later, after the
initial pass — the Tauri desktop shell itself.

**The handshake protocol** is the one piece of cross-language contract the whole
app depends on, so it's worth stating precisely: the sidecar binds its own
ephemeral loopback socket (binding in Python, not letting `uvicorn` do it, is
what makes the port knowable *before* the server starts accepting), then prints
exactly one line to stdout:

```
PLACEINATOR_READY {"port": 51234, "token": "..."}
```

Every other route requires that bearer token; `/health` is the one deliberate
exception, since the shell needs something to poll before it has a token to
authenticate with. `src/lib/api.ts`'s `connection()` falls back to
`VITE_SIDECAR_PORT`/`VITE_SIDECAR_TOKEN` env vars when there's no Tauri shell at
all — which is what made the frontend fully developable *before* a Rust
toolchain was even installed, months before the desktop shell itself was built.

**The Tauri shell came much later than the rest of M0**, blocked for most of the
project on installing Rust + MSVC Build Tools. Two real environment problems
surfaced getting the toolchain working, both worth knowing about since neither
produces an obvious error message:

- Git for Windows ships its own `link.exe` (a coreutils hard-link utility) that
  shadowed the real MSVC linker on `PATH`. The failure mode — `"extra operand ...
  Try 'link --help'"` — is coreutils' error format, easy to mistake for an MSVC
  problem.
- A very new Visual Studio release wasn't recognized by the installed Rust
  toolchain's bundled detection (neither `rustup`'s C++-prerequisite check nor
  `rustc`'s own MSVC auto-detection), confirmed independently via `vswhere`,
  which found a complete, correct installation the other two tools missed.

Both were fixed with an explicit, per-user `.cargo/config.toml` (machine-specific,
never committed) pinning the real linker/compiler paths and the `LIB`/`INCLUDE`
search paths `vcvarsall.bat` would normally set. Full account in ADR 0001's
"Verified in practice" addendum.

Once the toolchain worked, `src-tauri/` was scaffolded and dev-mode sidecar
supervision (`src-tauri/src/lib.rs`) was built to implement the handshake
protocol above from the Rust side: spawn the sidecar, read its stdout for the
handshake line on a background thread with a bounded timeout (so a sidecar that
never starts fails loudly instead of hanging the window forever — `std::io`'s
blocking reads have no deadline of their own), inject
`window.__PLACEINATOR__` via `initialization_script` before the frontend's first
script runs, and kill the sidecar when the window closes. Verified against a
real running window — not a mocked test — including an actual `WM_CLOSE` event
(not a force-kill) to prove the exit handler itself runs, confirming zero
orphaned processes survive a close.

**Deliberately deferred, not forgotten:** PyInstaller bundling
(`bundle.externalBin`), a Windows Job-Object-based guarantee that the sidecar
dies even on a shell crash (today's handler only covers a clean exit), and a
Rust/Tauri CI job. Bundling the Python sidecar into a standalone executable is
an independently risky effort — `onnxruntime`'s native libraries are the
likeliest packaging problem — and bolting it onto the first Rust code the repo
had ever seen was judged not worth the compounded risk. Same reasoning shows up
again at M3's PDF-compile deferral below.

## Step 2 — M1: Profile, Resume, and Matching

**Built:** the onboarding wizard, the resume library (PDF/DOCX/`.tex` upload and
parsing), the skill taxonomy (`placeinator/skills/taxonomy.json`), the chunking
pipeline that splits resumes and job descriptions into typed, scorable units,
and the matching engine that scores a resume against a job with a readable,
evidence-bearing explanation.

### Why `fastembed`, not something else

This was the project's single largest technical bet, and it was resolved before
any matching code was written, not assumed. The reasoning has two separate
layers — which *kind* of model, and which *library* to run it through — and
they're worth separating because they get conflated easily.

**Layer 1 — embedding model vs. a from-scratch architecture (e.g. BiLSTM +
Attention).** A hand-trained recurrent model (BiLSTM, or BiLSTM+Attention) was
never a serious option here, for two independent reasons:

- **The task itself favors pretrained transformer embeddings.** Modern sentence-
  embedding models (the BERT/MiniLM family, fine-tuned via contrastive learning
  on massive paired-text corpora — question/answer pairs, similar-sentence
  pairs, retrieval pairs) have been the state of the art for semantic-similarity
  tasks since roughly 2019, when they displaced exactly this kind of
  BiLSTM+Attention approach (InferSent-style models) in the sentence-embedding
  literature. Self-attention captures bidirectional, long-range context in one
  parallel pass; a BiLSTM processes the sequence step by step even when run in
  both directions, and lacks the benefit of that scale of pretraining.
- **A from-scratch model needs training data and infrastructure this project
  doesn't have.** There's no labeled corpus of (resume snippet, job requirement,
  relevance score) triples to train against, and building one is a project in
  itself. An off-the-shelf pretrained embedding model needs neither — it's used
  directly, with zero training pipeline, consistent with ADR 0002's
  deterministic-engine constraint (a trained-from-scratch model would also
  introduce a whole new axis of non-determinism and maintenance burden a fixed,
  versioned pretrained model doesn't have).

**Layer 2 — which library serves that pretrained model (`fastembed` vs.
`sentence-transformers`).** This is ADR 0005's actual subject, and it's a
footprint argument, not an accuracy argument — both libraries can serve the same
underlying model family. `sentence-transformers`, the obvious first choice,
depends on PyTorch, which adds roughly **2 GB** to the installed size and
measurable seconds to import time — costs that would dominate this desktop app's
entire latency and footprint budget, for a model that's itself only ~130 MB.
`fastembed` runs the same class of model through **ONNX Runtime** instead — no
PyTorch anywhere in the dependency tree. This was verified directly against the
real package index before any matching code depended on it:

```
fastembed 0.8.0
  onnxruntime 1.29.0, numpy 2.5.2, tokenizers 0.23.1,
  huggingface_hub 1.28.0, py_rust_stemmers 0.1.8, mmh3 5.2.1
```

All wheels, no source builds, no PyTorch. The specific model chosen is
`BAAI/bge-small-en-v1.5` (384 dimensions) — small enough to meet the latency
budget (embed a ~40-chunk resume in under 200 ms; rank 500 cached jobs in under
50 ms, since ranking at that scale is one NumPy matmul, not a vector database)
while still being a genuinely competitive general-purpose embedding model.

**The consequence that shaped everything downstream:** with no LLM to paper over
vocabulary gaps, `placeinator/skills/taxonomy.json` — the hand-curated
alias-to-skill map — became the real semantic backbone of matching, gap
analysis, and filtering. It's a first-class deliverable with its own test suite,
not a lookup table filled in as an afterthought, and its coverage (89 entries
seeded, not the ~600 originally scoped) is the project's most honestly-tracked
known limitation — deliberately left at 89 while M2/M3 proved out the rest of
the pipeline, rather than expanding it before there was a working product to
validate it against.

**Also load-bearing for later milestones:** `placeinator/matching/vectors.py`
is the *only* place that encodes or decodes an embedding (float32 little-endian,
C-contiguous, L2-normalized), and every stored vector carries its
`embedding_model`/`embedding_dim` alongside the bytes — so a future model change
leaves stale rows detectable and re-embeddable rather than silently
deserializing into meaningless numbers. This provenance discipline is what let
M2 and M3 later reuse the same stored vectors as a cache instead of re-embedding
on every request (see below).

**Done when:** add 3 resumes → paste a JD → get a ranked recommendation with a
readable explanation, in under 2 seconds — verified live through the actual UI.

## Step 3 — M2: Job intelligence

**Built:** four job-source adapters (`ats_feed`, `indeed`, `linkedin`,
`naukri`), hard-constraint filtering and soft-preference ranking, personalized
notifications, and the Jobs UI.

**The adapters were verified live against the real sites before any parsing code
was written**, which changed the plan mid-flight in a couple of places: an
earlier assumption that `indeed` would need real browser automation (Playwright)
turned out wrong once the actual search-results page was inspected — it's
server-rendered HTML with job data embedded as JSON in a `<script>` tag, so a
plain HTTP client suffices. `linkedin` and `naukri` were confirmed, live, to
block essentially everything (a blanket `robots.txt` disallow for `linkedin`;
active Akamai bot detection for `naukri`) — and per ADR 0003, blocked means
blocked. The app never disguises its user agent or otherwise evades a real
access-control boundary; a blocked source returns a `SourceBlocked` value the UI
offers manual paste against, never an error.

**A genuinely serious bug was found and fixed *twice*** while verifying `indeed`
— worth walking through in full because the second bug was introduced by fixing
the first one, and the failure mode was specifically the kind of thing "verify,
don't assume" is meant to catch:

1. Python's `urllib.robotparser.RobotFileParser.can_fetch` resolves rules by
   first-match-in-file-order, not RFC 9309's longest-match-wins. Indeed's own
   `robots.txt` opens its `User-agent: *` block with a blanket `Allow: /` before
   later, more specific `Disallow:` lines — exactly the shape that exposes this
   bug, reading the file as more permissive than its own author intended.
2. The first fix kept `RobotFileParser` for parsing and only replaced its
   decision logic, reading the result off `entries`/`default_entry`/
   `RuleLine.path`/`.allowance` — undocumented private attributes with no
   stability guarantee. They behaved differently between Python 3.13.7 (the dev
   machine) and 3.13.15 (CI's runner), so every disallow rule silently evaluated
   to "allowed" on CI while the exact same code passed locally.

The shipped fix parses `robots.txt` from raw text directly
(`placeinator/jobs/sources/base.py`), with zero dependency on
`urllib.robotparser`, regression-tested against a real captured Indeed
`robots.txt`. CI now also pins an exact Python patch version rather than a
floating minor version, specifically so this class of environment-dependent
skew can't hide again.

**A consolidation pass** later closed a gap between "the backend works" and "a
user can actually reach it": the ATS-feed sync (Greenhouse/Lever/Ashby — the
only adapter that reliably returns full job descriptions, since the other three
are scraped rather than official APIs) had been complete and tested since M2's
first slice but had no frontend at all. Fixed alongside a handful of other
reachability and robustness gaps — transport failures degrading to
`SourceBlocked` instead of a raw exception, `JobOut` gaining the `url` field it
had been missing (every discovered job was previously a dead end in the UI) —
and the `model`-marked test suite (which needs the real embedding model) was
promoted from a deselected-by-default, `continue-on-error` CI step to a required
one. That promotion immediately caught a real, previously-invisible bug: two
component scores could exceed their documented `[0, 1]` bound, because float32
cosine similarity of two near-identical vectors can land a few ULPs above 1.0 —
CPU-dependent, so it passed locally and failed on CI. Fixed with one shared
clamping helper instead of the ad hoc `max(0.0, ...)` two of the three scorers
had been doing.

**Also built in this milestone's tail:** the ranking cache. `rank_jobs` runs
over the whole job corpus on every Dashboard mount; before this, that meant
re-embedding every resume chunk and job requirement on every mount. The fix
reuses the exact provenance mechanism M1 built for a different reason (the
`embedding_model`/`embedding_dim` stamp on every stored vector) to make
`MatchResult` double as a cache: a row is reused untouched when it's still
fresh (same scoring version, and neither side has been written since the score
was taken), and even a genuine rescore reuses the persisted vectors rather than
re-embedding from text.

## Step 4 — M3: LaTeX resume tailoring

**Built:** a LaTeX structure parser with byte-exact source spans, a relevance
scorer and reordering policy, a splice-based emitter, and a three-pane Tailor
workspace.

The spec's hardest constraint here is ADR 0002's inheritance into this specific
feature: the system must never invent a qualification, experience, project, or
skill that isn't already in the user's resume. Rather than instructing a model
not to hallucinate, the design makes invention **structurally impossible**: the
emitter only ever splices byte ranges out of the user's own original source. It
never regenerates text.

**The design was shaped by two things confirmed against the real
`pylatexenc` library, not assumed from its docs**, documented in
`placeinator/latex/parsing.py`'s module docstring:

- `pylatexenc`'s node tree doesn't nest a section's body under its heading —
  `\section{Skills}` is one flat macro node, and everything that follows it is
  a *sibling* in the parent's node list, not a child.
- A `\newcommand`-defined macro — the shape most real-world resume templates
  actually use (e.g. `\resumeItem{...}`) — doesn't get its argument captured as
  a child node at all, since `pylatexenc` only associates arguments for macros
  it has a signature for.

Both findings ruled out a tree-walking design. Instead, `parse_latex`
partitions the source into a flat, ordered, contiguous list of spans (Fixed /
Section / Bullet); identity-order emission reproducing the input byte-for-byte
is therefore true *by construction*, not something separately proven correct —
this is the round-trip acceptance gate
(`tests/unit/test_latex_parsing.py`), run against real captured `.tex` files,
including one using only custom bullet macros specifically to prove the honest
whole-section fallback when no `\item` is recognized.

**The relevance scoring reuses M1/M2 infrastructure end to end rather than
building a parallel pipeline** — this is the same design principle the M2
ranking cache established, applied again: each movable unit (a section or
bullet) is scored by pooling the *same* persisted `ResumeChunk` embedding
vectors M1 already computed and M2's cache already trusts, via the same
`mean_pool`/`clamp_unit` primitives the M1 matching engine uses for its
`overall` score. No new embedding calls anywhere in the tailoring path.

**Removal is never automatic**, mirroring the spec's own requirement that
removals need explicit confirmation: a low-scoring bullet is flagged as a
*suggestion* only, and the emitted `.tex` still contains it unless the caller
explicitly excludes it by id.

**One more real bug, found integrating Monaco into the Tailor page**:
`@monaco-editor/react`'s loader defaults to fetching the editor itself from
`cdn.jsdelivr.net` at runtime, rather than using the copy already bundled with
the app — confirmed by reading the loader's own config, not assumed. For an app
whose core commitment is fully offline operation (ADR 0002/ADR 0005), this would
have silently broken the Tailor page the moment there was no network. Fixed by
pointing the loader at the bundled package explicitly and verified against the
actual production build output, not just a passing type-check.

**PDF compile is explicitly out of scope for this milestone** — a genuinely
independent concern (TeX-distribution detection, subprocess execution,
graceful degradation when no TeX distribution exists), deliberately deferred
rather than bolted onto the same pass as the highest-risk new subsystem in the
app, for the same reasoning as M0's PyInstaller deferral above.

## Current status

| Milestone | Status |
|---|---|
| M0 — Foundation | Sidecar + frontend shell complete; Tauri desktop shell verified in dev mode; PyInstaller bundling not yet wired |
| M1 — Profile, Resume, Matching | Complete |
| M2 — Job intelligence | Complete |
| M3 — LaTeX resume tailoring | Complete, except PDF compile |
| M4 — Placement automation | Not started |
| M5 — Career intelligence and outreach | Not started |
| M6 — Hardening and release | Not started |

For exact numbers: 50 Python modules under `placeinator/`, 30 TypeScript/TSX
files under `src/`, 175 tests (139 run by default; 36 require either the real
embedding model or live network access, both opt-in). See
[roadmap.md](./roadmap.md) for the authoritative, continuously-updated status
and [CHANGELOG.md](./CHANGELOG.md) for the chronological record of every change.
