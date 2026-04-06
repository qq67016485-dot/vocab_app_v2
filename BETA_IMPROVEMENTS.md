# Beta Readiness Improvements

Status: Updated 2026-04-03

## Critical

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Rotate exposed API keys | Done | False alarm — `.env` was already gitignored and untracked. Added `.env.example` template. |
| 2 | Production settings (DEBUG, SECRET_KEY, ALLOWED_HOSTS, CORS) | Pending | Need environment-specific config for deployment. |

## High

| # | Item | Status | Notes |
|---|------|--------|-------|
| 3 | Rate limiting on login endpoint | Done | `LoginRateThrottle` (5/min per IP) on `/api/login/`. 429 message surfaces in UI. |
| 4 | Teacher self-service password reset | Pending | Teachers can already reset student passwords via Edit Student modal. Missing: self-service reset for teachers/admins (e.g., forgot password on login page). |
| 5 | Pagination on list endpoints | Pending | `/api/words/`, `/api/word-sets/`, `/api/groups/` return all rows. |
| 6 | Database indexes on frequently queried FKs | Pending | `UserWordProgress.user/word`, `UserAnswer.user/answered_at`, `Question.word`. |
| 7 | React error boundary | Done | `ErrorBoundary` wraps entire app in `App.jsx`. Shows fallback UI + reload button. |

## Medium

| # | Item | Status | Notes |
|---|------|--------|-------|
| 8 | LLM pipeline retry logic | Pending | Transient Gemini/Anthropic failures fail the whole job. |
| 9 | Health check endpoint | Pending | Needed for load balancer / uptime monitoring. |
| 10 | Django logging config | Pending | No `LOGGING` dict in settings.py — errors go to stdout only. |
| 11 | DRF exception handler | Pending | Error response format inconsistent across views. |
| 12 | Docker setup | Pending | No Dockerfile or docker-compose for reproducible deploys. |
| 13 | Frontend tests | Pending | Backend has ~3k lines of tests; frontend has zero. |

## Low

| # | Item | Status | Notes |
|---|------|--------|-------|
| 14 | 404 page | Pending | Currently redirects to home by role. |
| 15 | Empty states | Pending | Several views show nothing when there's no data. |
| 16 | Form validation UX | Pending | No real-time field-level feedback on forms. |
