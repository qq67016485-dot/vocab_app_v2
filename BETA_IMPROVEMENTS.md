# Beta Readiness Improvements

Status: Updated 2026-08-27

## Critical

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Rotate exposed API keys | Done | False alarm — `.env` was already gitignored and untracked. Added `.env.example` template. |
| 2 | Production settings (DEBUG, SECRET_KEY, ALLOWED_HOSTS, CORS) | Pending | Need environment-specific config for deployment. |

## High

| # | Item | Status | Notes |
|---|------|--------|-------|
| 3 | Rate limiting on login endpoint | Done | `LoginRateThrottle` (5/min per IP) on `/api/login/`. 429 message surfaces in UI. Hardened 2026-07-19: `NUM_PROXIES=1` — throttle keys on the nginx-provided IP (full client XFF chain was spoofable). |
| 4 | Teacher self-service password reset | Pending | Teachers can already reset student passwords via Edit Student modal. Missing: self-service reset for teachers/admins (e.g., forgot password on login page). |
| 5 | Pagination on list endpoints | Pending | `/api/words/`, `/api/word-sets/`, `/api/groups/` return all rows. |
| 6 | Database indexes on frequently queried FKs | Done | 2026-05-31 (migration 0030): `UserAnswer` `(user, answered_at)` + `(user, is_correct)` + `(question, answered_at)`. 2026-07-03 (migration 0040): `Question` `(word, lexile_score)` (covers the `Question.word` gap) and `UserWordProgress` `(user, instructional_status, next_review_at)` replacing `(user, instructional_status)`; `(user, next_review_at)` kept. |
| 7 | React error boundary | Done | `ErrorBoundary` wraps entire app in `App.jsx`. Shows fallback UI + reload button. |
| 18 | Practice-submit scoring integrity | Done | 2026-07-03 review: `daily_question_limit` + READY gate now enforced inside `process_answer` (was serve-only → replayed `question_id` farmed XP/mastery, incl. locked-pack words); row-locked against concurrent double-submits; `duration_seconds`/`answer_switches` clamped; hidden level name masked; sentence-write judge calls bounded per-day; `apply-bonuses` idempotent per session; `session-summary` start_time floored. Frontend double-tap guard + non-trapping error banner. |
| 19 | Session cookie SameSite/Secure hardening | Done | 2026-07-03: explicit `SESSION_COOKIE_SAMESITE`/`CSRF_COOKIE_SAMESITE='Lax'` + `SESSION_COOKIE_HTTPONLY`. **Updated 2026-07-19:** `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` are driven by a dedicated `COOKIE_SECURE` env bool (default `False`), *not* `DEBUG` — a Secure cookie over plain HTTP is dropped and every authed request 403s, so it stays `False` on the HTTP prod box. **Note:** DRF still has no per-endpoint throttling beyond login (`/practice/submit/` relies on the daily limit); a global throttle remains a defense-in-depth gap. |

## Medium

| # | Item | Status | Notes |
|---|------|--------|-------|
| 8 | LLM pipeline retry logic | Partial | Single retry on transient API errors (bad_response_body, unexpected end of JSON). 2026-07-20: job-level exponential backoff added in the batch queue runner (`run_generation_queue` — transient-classified failures auto-resume with 5/10/20/30-min capped backoff + a global outage breaker). In-step attempts still fire without backoff — full per-call exponential backoff not implemented. |
| 9 | Health check endpoint | Pending | Needed for load balancer / uptime monitoring. |
| 10 | Django logging config | Done | 2026-07-19: settings.py has a `LOGGING` dict (console handler, `vocabulary` logger at INFO). |
| 11 | DRF exception handler | Pending | Error response format inconsistent across views. |
| 12 | Docker setup | Pending | No Dockerfile or docker-compose for reproducible deploys. |
| 13 | Frontend tests | Pending | Backend has ~3k lines of tests; frontend has zero. |
| 17 | LLM log/artifact retention | Pending | 2026-07-03 security review: `temp/llm_logs/` (full prompt+response per LLM call) and `temp/generation_artifacts/` grow without bound — disk-exhaustion risk on the 3.6 GB production box. Needs an age-based cleanup cron or on-write pruning. 2026-07-31: also a legal-hygiene requirement now — `docs/feature_plan/design-book-neutral-wordset-discovery.md` §8 (LLM logs contain source book titles/passages; retention limit is part of the book-neutral catalog design). 2026-08-27: also a **privacy** requirement — child-written sentences from the sentence-write judge sit in plaintext logs (1,581 files as of 2026-07-29) with no retention limit, inconsistent with the capstone proposal's §8 encryption-at-rest claim. Held for a dedicated privacy pass; options: redact the sentence field from log payloads, retention cron, or encrypted storage. |
| 20 | Infographic poster edit/redraw endpoints | Pending | 2026-08-26 infographic-skills analysis (`docs/infographic-pipeline-vs-skills-analysis.md` §4 #3): `Infographic` carries `edited_image`/`use_edited_image`/`edited_image_jpeg` mirroring GN pages, but no edit/redraw/select-image endpoints exist — admins can't fix a bad poster short of full candidate regeneration. GN pages are the implementation template. |

## Low

| # | Item | Status | Notes |
|---|------|--------|-------|
| 14 | 404 page | Pending | Currently redirects to home by role. |
| 15 | Empty states | Pending | Several views show nothing when there's no data. |
| 16 | Form validation UX | Pending | No real-time field-level feedback on forms. |

## Research-review backlog (from `docs/validated-improvement-opportunities-2026-08-27.md`)

Parked items from the 2026-08-27 research analysis + design review. Statuses and
rationale are in that report's decision log; IDs (T/N) reference it.

| # | Item | Status | Notes |
|---|------|--------|-------|
| R1 | Batch answer-verification for generated questions (N3) | Approved, deferred | Independent LLM re-solve of generated choice questions (question_text + options, no key), mismatch → `verification_mismatch` QA flag. Runs as an off-peak batch management command, not inline in generation. Needs a `question_verify` LLM step key seeded into all 3 config sets (precedent: migrations 0033/0037/0039) so verification can use a different model than generation. Design: validated report, Step 1.3. |
| R2 | Achievements-style word-bank widget (T17) | Approved, on hold | Very visible counters + milestone badges + per-set mastery map; personal/non-competitive only (Zhang & Hasim: competition downsides). Blocked on a student-UI redesign pass. |
| R3 | Distinct-context constraints in generation prompts (T7) | Open | Prompt-level "each item situates the word in a different setting" + serve-time preference for unseen scenarios. Currently only guided→open sentence-write divergence is enforced. |
| R4 | Word-family/morphology content in primers (T16) | Open | Root + 1–3 transparent derivatives + one affix note in `primer_generation.txt` (Silverman: morphology g=1.14, K–5, ELs benefit most). No scheduling interaction — safe to build any time. |
| R5 | Delayed-retention KPI on dashboards (N5) | Open | Accuracy on reviews ≥24h after last correct, per word set / student. Data exists (`UserAnswer`); one aggregation query. Pairs with the capstone Track D "secure/fragile/forgotten" word states. |
| R6 | Cognitive-load: sound/quiet toggle (T5) | Open | Student-facing audio toggle; one dominant audio channel at a time. Keep GN auto-read user-controllable (default ON is evidence-backed for young grades). |
| R7 | Time-on-task persistence + extra-practice path (N6) | Post-Track-D | `PracticeSession` is a dead table (never written); daily cap is a hard 429 with no sanctioned override. Dose-response evidence (Loewen, Kessler). Daily-cap changes interact with the backlog dynamics the scheduler relies on — do after the predictive-scheduler work. |
| R8 | Post-mastery novelty injection (T8) | Post-Track-D | Queue-composition-aware next-set previews / new-scenario challenges when mastery-dominated (Yu: HR=1.8 stagnation). FSRS spacing will change how level labels read — design after it lands. |
| R9 | Mobile-first student shell polish (N7) | Open | Fixed 96px shell gutters on phones (`base.css:4-7`), no mobile nav pattern, no swipe paging in the GN reader. Bandwidth already handled (JPEG/MP3 companions). |
| R10 | Teacher guided-reading / mediation mode (N8) | Roadmap | Child-media research (Furenes, Savva): adult mediation beats independent digital reading. Not a quick fix. |
| R11 | Flip-card self-test mode (T10) | Watchlist | Primer deck is the natural host (one word per card, reveal data present). Medium evidence. |
| R12 | L1-translation recall question type (T13) | Watchlist | Terai: L2→L1 is the proficiency-safe direction. Needs per-student L1 + distractor care; extrapolation-tier evidence. |
| R13 | Cross-context exposure tracking (T14) | Watchlist | No per-word counters for story reads/primer views. If built, weight designed learning moments over raw views (Jing: naturalistic exposure r≈.07). The `SchedulingDecision` log (2026-08-27, migration 0042) covers the practice side only. |
| R14 | Word-frequency-band metadata (T15) | Watchlist | Tag words at WORD_LOOKUP with a frequency band; warn teachers on ultra-rare/ultra-common sets. `Tag` M2M exists but is never populated. |
| R15 | Content-side cultural-diversity guidance (T18) | Watchlist | Prompt guidance + admin-review rubric line for GN/infographic scenarios. Feedback-side cultural bias is covered by the capstone LLM feedback audit. |
| R16 | Embedding-based distractor similarity reject (T4) | On hold | Design review: distractor quality is context-dependent; embedding similarity to the key judged inadequate as a defect signal. Post-hoc distractor analysis rides with the item-stats flags instead. |
| R17 | Reader MC glosses (N1) | Dropped | Design review: reading phase stays stress-free; the cloze quiz after the story already provides per-word evaluative retrieval; interruptive interactivity has a documented comprehension cost for young readers (Furenes 2021). Recorded so it isn't re-proposed. |
| R18 | On-demand "tell me more" judge tier (T11) | Dropped | The revision loop already graduates hints across attempts (Jeon); long text is a barrier at ages 7–14. Recorded so it isn't re-proposed. |
