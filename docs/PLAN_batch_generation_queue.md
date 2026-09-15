# Batch Generation Queue (as built, 2026-07-20)

> This file was originally a pre-implementation plan. It is now the **as-built
> record** of what actually shipped. Items from the draft that were deliberately
> NOT built are listed at the bottom so future readers know they were decisions,
> not omissions.

**Goal:** run content generation for ~200 word sets continuously on the
production server (http://106.52.164.47) with minimal supervision.

**Constraints:** 30–45 min per word set (GN + infographic); 2 vCPU / 3.6 GB RAM;
no new infrastructure (no Redis/Celery); must survive service restarts and box
reboots; the LLM proxy has occasional short outages, so retry design is a
first-class requirement.

---

## Architecture

`GenerationJob.status = PENDING` **is the queue**. Two management commands +
one systemd unit, all new code (no changes to existing pipeline code):

1. **`enqueue_generation`** (`backend/vocabulary/management/commands/enqueue_generation.py`)
   Bulk-creates PENDING jobs from a text file of word-set IDs (one per line,
   `#` comments). Per ID: skips word sets that are missing / already GENERATED /
   already have a PENDING/RUNNING job / have no `input_words` (same locked
   duplicate-guard as `TriggerGenerationView`). Copies `input_words`, source
   fields, and `target_lexile` from the word set; `created_by` = the word set's
   creator (`--user` override); `content_types` defaults to
   `['graphic_novel', 'infographic']`. Idempotent — safe to re-run. Does not
   start anything and does not touch `word_set.generation_status`.

2. **`run_generation_queue`** (`backend/vocabulary/management/commands/run_generation_queue.py`)
   The long-running runner (`QueueRunner`). Every `--poll-interval` (30 s) it:
   - reaps finished job threads;
   - fires due retry timers (`next_retry_at` reached) via `resume_pipeline`;
   - claims the oldest PENDING jobs (`select_for_update`, sets `RUNNING` + the
     word set `GENERATING`) up to `--concurrency` (default **2**) and runs
     `run_full_pipeline` in a daemon thread per job.
   Concurrency counts **all** RUNNING jobs in the DB (including web-triggered
   ones), so don't start generation from the web UI during a batch — a
   web-triggered job works but eats a slot.

3. **`vocab-generation.service`** (systemd, `Restart=always`) runs the runner
   with `--concurrency 2 --resume-stale`. Because jobs execute in **this**
   process — not as daemon threads inside gunicorn workers — web redeploys and
   worker OOM-kills no longer kill in-flight pipelines. Unit definition:

   ```ini
   [Unit]
   Description=Vocab batch generation queue runner
   After=network.target mysql.service

   [Service]
   User=ubuntu
   WorkingDirectory=/home/ubuntu/vocab_app_v2/backend
   ExecStart=/home/ubuntu/vocab_app_v2/backend/venv/bin/python manage.py run_generation_queue --concurrency 2 --resume-stale
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

## Retry policy (three layers)

1. **In-step attempts (pre-existing, unchanged):** text steps try
   `[primary ×3, fallback ×1]`, image steps ×2, GN substeps ×3 — fired
   back-to-back with no sleeps. Absorbs blips of seconds, NOT outages.
2. **Per-job resume with classification + capped backoff:** when a job ends
   FAILED, `classify_error(error_message)` decides:
   - **transient** (429/5xx, timeout, connection, overloaded/unavailable, SDK
     error class names) → auto-resume via `resume_pipeline` with backoff
     5/10/20/30… min (30 cap), up to `--max-transient-retries` (default **8** ≈
     tolerates a ~3 h outage hitting one job);
   - **deterministic** (validation/completeness/schema errors, anything
     unmatched) → **no auto-retry**, job stays FAILED for manual review.
     Classification is conservative on purpose: a misclassified transient error
     costs one manual resume; the reverse costs at most 8 doomed resumes.
3. **Global outage breaker:** after `--outage-threshold` (default 3)
   consecutive transient failures across the whole queue, the runner freezes
   claims + resume timers for `--outage-cooldown` (default 15 min), then probes
   again. A successful completion resets the counter. A long proxy outage can
   no longer burn every queued job's layer-2 budget.

**Persistence:** per-job `{transient_attempts, next_retry_at}` lives in
`backend/data/generation_queue_state.json` (gitignored), written on every
transition — restarts never reset budgets and never cause resume loops. On
startup the runner re-arms FAILED jobs with remaining budget (honoring
`next_retry_at`) and — with `--resume-stale` — resumes jobs stuck in RUNNING
because their process died.

## Operations

```bash
# enqueue a batch (on the server, from ~/vocab_app_v2/backend)
venv/bin/python manage.py enqueue_generation --ids-file ~/generation_batch.txt

# monitor
journalctl -u vocab-generation -f          # claims, completions, retry events, breaker
# job/step detail: existing admin UI (GenerationJobStatus) works unchanged

# stop / start / restart (in-flight jobs self-heal via --resume-stale)
sudo systemctl stop vocab-generation
sudo systemctl restart vocab-generation

# change concurrency: edit ExecStart (--concurrency 3), daemon-reload, restart
```

**Pilot first:** enqueue 2–3 IDs, confirm both pipelines reach COMPLETED, then
do the retry drill — `systemctl restart vocab-generation` mid-job and confirm
the RUNNING job resumes and finishes. Then enqueue the rest.

**When a job stays FAILED:** read the runner log line — deterministic failures
need a human (bad word list, prompt/validator issue); a job that burned its
whole transient budget means the proxy was down for hours. After fixing the
cause, resume from the existing admin endpoint — the runner counts
manually-resumed jobs toward concurrency.

**Rollback:** `sudo systemctl disable --now vocab-generation`. No migrations,
no web-code changes, so nothing else to roll back.

## Tests

`backend/tests/vocabulary/test_generation_queue.py` — 35 tests: enqueue
guards/idempotency, claim order + concurrency cap, error classification,
backoff schedule, budget exhaustion, outage breaker open/reset, state-file
persistence across simulated restarts, `--resume-stale`. Job entrypoints are
monkeypatched (no LLM calls); threads run synchronously via the runner's
`_thread_factory` seam.

## Deliberately NOT built (from the draft plan)

- **CSV wordset import** (`import_wordsets_csv`) — the batch is driven by an ID
  list file; the ~200 word sets already exist in the DB.
- **`generation_queue_status` command** — the existing admin status UI +
  `journalctl -u vocab-generation` cover monitoring.
- **Per-service memory limits / log files** — journald handles logs; concurrency
  2 keeps memory comfortably inside the box's headroom.
- **Retry counter inside `GenerationJob`** — kept out of the schema on purpose;
  budgets live in the runner's JSON state file (no migration needed).
