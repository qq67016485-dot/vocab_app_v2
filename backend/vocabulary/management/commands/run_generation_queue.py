"""Long-running generation queue runner.

Claims PENDING GenerationJobs N at a time and executes the full pipeline
in-process (via ``run_full_pipeline``), instead of the web view's daemon
threads inside gunicorn workers — so web redeploys/OOM kills no longer kill
batch jobs. Run it as the ``vocab-generation`` systemd service on production.

Retry policy (three layers — the first lives in the pipeline itself):
  1. In-step attempts (existing): [primary x3, fallback x1] / images x2,
     fired back-to-back. Absorbs blips of seconds, not outages.
  2. Per-job resume with error classification + capped exponential backoff:
     a FAILED job whose error looks transient (LLM site/network/rate-limit)
     is resumed via ``resume_pipeline`` after 5/10/20/30... minutes, up to
     --max-transient-retries. Deterministic errors (validation, completeness
     gates, schema) are never auto-retried — retrying them only burns quota.
  3. Global outage breaker: after --outage-threshold consecutive transient
     failures across the queue, claiming and resume timers freeze for
     --outage-cooldown minutes, so a long LLM outage doesn't burn every
     queued job's layer-2 budget.

Retry budgets persist in a JSON state file (written on every transition), so
service restarts / box reboots neither reset budgets nor cause resume loops.
With --resume-stale, jobs stuck in RUNNING (process died mid-flight) are
resumed on startup.

Usage:
    python manage.py run_generation_queue --concurrency 2 --resume-stale
"""
import json
import logging
import os
import re
import signal
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection, transaction
from django.utils import timezone

from vocabulary.models import GenerationJob, WordSet
from vocabulary.services.generation.orchestrator import (
    resume_pipeline,
    run_full_pipeline,
)

logger = logging.getLogger(__name__)

DEFAULT_STATE_FILE = Path(settings.BASE_DIR) / 'data' / 'generation_queue_state.json'

# Backoff schedule for transient failures, in minutes. Attempts beyond the
# list use the last value (30 min cap).
BACKOFF_MINUTES = (5, 10, 20, 30)

_TRANSIENT_SUBSTRINGS = (
    'timeout', 'timed out',
    'connection', 'connect error',
    'rate limit', 'rate_limit', 'ratelimit',
    'overloaded', 'unavailable',
    'reset by peer', 'connection reset',
    'end of file',
    'bad gateway', 'gateway timeout', 'internal server error',
    'temporarily',
    # SDK exception class names that can surface in str(exc)
    'apiconnectionerror', 'apitimeouterror', 'ratelimiterror',
    'internalservererror', 'servererror', 'serviceunavailable',
)
_TRANSIENT_CODE_RE = re.compile(r'\b(429|500|502|503|504)\b')


def classify_error(message):
    """Classify a job error_message as 'transient' or 'deterministic'.

    Deliberately conservative: anything that doesn't clearly look like an
    LLM-site/network problem is 'deterministic' (no auto-retry). A transient
    error misclassified as deterministic costs one manual resume; the reverse
    costs at most --max-transient-retries doomed resumes, then stops.
    """
    text = (message or '').lower()
    if _TRANSIENT_CODE_RE.search(text):
        return 'transient'
    if any(marker in text for marker in _TRANSIENT_SUBSTRINGS):
        return 'transient'
    return 'deterministic'


def backoff_minutes(attempts):
    """Delay before transient resume #``attempts`` (1-based): 5/10/20/30/30..."""
    return BACKOFF_MINUTES[min(attempts, len(BACKOFF_MINUTES)) - 1]


def _close_connections_if_safe():
    """close_old_connections() kills the connection a pytest-django test
    transaction lives on — mirror the orchestrator's guard (helpers.py)."""
    if not connection.in_atomic_block:
        close_old_connections()


class QueueRunner:
    """Claims and executes PENDING generation jobs until stopped."""

    def __init__(self, *, concurrency=2, poll_interval=30, resume_stale=False,
                 max_transient_retries=8, outage_threshold=3,
                 outage_cooldown_minutes=15, state_file=DEFAULT_STATE_FILE,
                 out=None):
        self.concurrency = max(1, concurrency)
        self.poll_interval = poll_interval
        self.resume_stale = resume_stale
        self.max_transient_retries = max_transient_retries
        self.outage_threshold = outage_threshold
        self.outage_cooldown_minutes = outage_cooldown_minutes
        self.state_file = Path(state_file)
        self.out = out  # callable like self.stdout.write, for journald visibility

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._inflight = {}       # job_id -> Thread
        self._startup_resumes = []  # stale RUNNING job ids, drained by tick()
        self._consecutive_transient = 0
        self._breaker_until = None
        self._state = {}          # job_id -> {'transient_attempts': int, 'next_retry_at': iso|None}
        self._thread_factory = threading.Thread  # seam for tests (synchronous threads)

    # ------------------------------------------------------------------ utils

    def _log(self, message):
        logger.info('%s', message)
        if self.out:
            self.out(message)

    def _now(self):
        return timezone.now()

    def request_stop(self):
        self._stop.set()

    # ------------------------------------------------------------- state file

    def load_state(self):
        try:
            raw = json.loads(self.state_file.read_text())
            self._state = {int(k): v for k, v in raw.get('jobs', {}).items()}
        except FileNotFoundError:
            self._state = {}
        except (ValueError, OSError, AttributeError) as exc:
            self._log(f'Warning: ignoring unreadable state file {self.state_file} ({exc}).')
            self._state = {}

    def save_state(self):
        with self._lock:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_name(self.state_file.name + '.tmp')
            payload = {'jobs': {str(k): v for k, v in sorted(self._state.items())}}
            tmp.write_text(json.dumps(payload, indent=2))
            os.replace(tmp, self.state_file)

    # ---------------------------------------------------------------- startup

    def startup(self):
        self.load_state()

        stale = list(GenerationJob.objects.filter(
            status=GenerationJob.Status.RUNNING,
        ).values_list('id', flat=True))
        if stale and self.resume_stale:
            self._log(f'Resuming {len(stale)} stale RUNNING job(s): {stale}')
            self._startup_resumes.extend(stale)
        elif stale:
            self._log(
                f'Found {len(stale)} RUNNING job(s) from a previous run; leaving '
                f'them untouched (restart with --resume-stale to resume them).'
            )

        if self._state:
            failed_ids = set(GenerationJob.objects.filter(
                status=GenerationJob.Status.FAILED,
            ).values_list('id', flat=True))
            with self._lock:
                for job_id in list(self._state):
                    entry = self._state[job_id]
                    if job_id not in failed_ids:
                        # Completed or manually handled while we were down.
                        del self._state[job_id]
                    elif entry.get('transient_attempts', 0) >= self.max_transient_retries:
                        self._log(f'Job {job_id}: transient retry budget exhausted; leaving FAILED.')
                        del self._state[job_id]
                    else:
                        if not entry.get('next_retry_at'):
                            # Died between classification and scheduling — due now.
                            entry['next_retry_at'] = self._now().isoformat()
                        self._log(
                            f'Re-arming job {job_id} (transient attempt '
                            f'{entry["transient_attempts"]}/{self.max_transient_retries}).'
                        )
            self.save_state()

    # ------------------------------------------------------------ concurrency

    def _reap(self):
        with self._lock:
            done = [job_id for job_id, t in self._inflight.items() if not t.is_alive()]
            for job_id in done:
                del self._inflight[job_id]

    def _active_count(self):
        """Jobs occupying a slot: DB RUNNING (covers web-triggered jobs and
        our in-flight ones) or locally-tracked threads not yet marked RUNNING
        (claim/retry-fire window). Stale RUNNING jobs queued for --resume-stale
        are excluded — their threads are dead, so they hold no real slot."""
        running_db = (
            GenerationJob.objects.filter(status=GenerationJob.Status.RUNNING)
            .exclude(id__in=self._startup_resumes)
            .count()
        )
        with self._lock:
            inflight = len(self._inflight)
        return max(running_db, inflight)

    def _breaker_open(self):
        return self._breaker_until is not None and self._now() < self._breaker_until

    # --------------------------------------------------------------- main loop

    def tick(self):
        """One iteration: reap finished threads, fire due resumes, claim new jobs."""
        _close_connections_if_safe()
        self._reap()
        if self._breaker_open():
            return

        now = self._now()
        with self._lock:
            due = [
                job_id for job_id, entry in self._state.items()
                if entry.get('next_retry_at')
                and datetime.fromisoformat(entry['next_retry_at']) <= now
                and job_id not in self._inflight
            ]
        for job_id in due:
            if self._breaker_open() or self._active_count() >= self.concurrency:
                break
            job = GenerationJob.objects.filter(id=job_id).first()
            if job is None or job.status != GenerationJob.Status.FAILED:
                with self._lock:
                    self._state.pop(job_id, None)
                self.save_state()
                continue
            with self._lock:
                entry = self._state.get(job_id)
                if entry is None:
                    continue
                entry['next_retry_at'] = None  # consumed; wrapper re-schedules on failure
            self._start(job_id, resume_pipeline)

        while self._startup_resumes and self._active_count() < self.concurrency:
            self._start(self._startup_resumes.pop(0), resume_pipeline)

        while not self._breaker_open() and self._active_count() < self.concurrency:
            job = self._claim_next_pending()
            if job is None:
                break
            self._start(job.id, run_full_pipeline)

    def run_forever(self):
        self.startup()
        self._log(
            f'Queue runner started: concurrency={self.concurrency}, '
            f'poll={self.poll_interval}s, max_transient_retries={self.max_transient_retries}, '
            f'outage_threshold={self.outage_threshold}, state_file={self.state_file}'
        )
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception('Queue runner tick failed')
            self._stop.wait(self.poll_interval)

        self._log('Shutdown requested; waiting up to 60s for in-flight jobs...')
        deadline = time.monotonic() + 60
        with self._lock:
            threads = list(self._inflight.values())
        for thread in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(remaining)
        self._log('Runner stopped.')

    # ------------------------------------------------------------ job lifecycle

    def _claim_next_pending(self):
        with transaction.atomic():
            job = (
                GenerationJob.objects.select_for_update()
                .filter(status=GenerationJob.Status.PENDING)
                .order_by('created_at', 'id')
                .first()
            )
            if job is None:
                return None
            job.status = GenerationJob.Status.RUNNING
            job.save(update_fields=['status'])
            # run_full_pipeline doesn't flip the word set to GENERATING (the
            # web trigger does that) — do it here at claim time.
            WordSet.objects.filter(id=job.word_set_id).update(
                generation_status=WordSet.GenerationStatus.GENERATING,
            )
        return job

    def _start(self, job_id, entrypoint):
        action = 'resume' if entrypoint is resume_pipeline else 'run'
        self._log(f'Starting {action} for job {job_id}.')
        thread = self._thread_factory(
            target=self._wrapper, args=(job_id, entrypoint), daemon=True,
            name=f'generation-job-{job_id}',
        )
        with self._lock:
            self._inflight[job_id] = thread
        thread.start()

    def _wrapper(self, job_id, entrypoint):
        try:
            entrypoint(job_id)
        except Exception as exc:
            # The orchestrator converts its own failures into status=FAILED;
            # this catches errors before/after that (e.g. DB gone).
            logger.exception('Job %s entrypoint raised unexpectedly', job_id)
            try:
                GenerationJob.objects.filter(
                    id=job_id, status=GenerationJob.Status.RUNNING,
                ).update(
                    status=GenerationJob.Status.FAILED,
                    error_message=f'Runner entrypoint error: {exc}',
                )
            except Exception:
                logger.exception('Could not mark job %s as FAILED', job_id)
        finally:
            _close_connections_if_safe()
        try:
            self._postprocess(job_id)
        except Exception:
            logger.exception('Post-processing failed for job %s', job_id)

    def _postprocess(self, job_id):
        job = GenerationJob.objects.filter(id=job_id).first()
        if job is None:
            with self._lock:
                self._state.pop(job_id, None)
            self.save_state()
            return

        if job.status in (
            GenerationJob.Status.COMPLETED,
            GenerationJob.Status.PARTIALLY_COMPLETED,
        ):
            self._log(f'Job {job_id} completed ({job.status}).')
            with self._lock:
                self._state.pop(job_id, None)
                self._consecutive_transient = 0
                self._breaker_until = None
            self.save_state()
        elif job.status == GenerationJob.Status.FAILED:
            self._handle_failure(job)
        # else: still RUNNING — someone else resumed it; leave it alone.

    # ------------------------------------------------------------ retry policy

    def _handle_failure(self, job):
        kind = classify_error(job.error_message)
        if kind != 'transient':
            self._log(
                f'Job {job.id} FAILED with a non-transient error — no auto-retry. '
                f'Error: {job.error_message[:300]}'
            )
            with self._lock:
                self._consecutive_transient = 0
            return

        with self._lock:
            self._consecutive_transient += 1
            if self._consecutive_transient >= self.outage_threshold:
                self._breaker_until = self._now() + timedelta(
                    minutes=self.outage_cooldown_minutes,
                )
                breaker_opened = True
            else:
                breaker_opened = False

            entry = self._state.get(job.id, {'transient_attempts': 0, 'next_retry_at': None})
            entry['transient_attempts'] = entry.get('transient_attempts', 0) + 1
            attempts = entry['transient_attempts']
            if attempts > self.max_transient_retries:
                self._state.pop(job.id, None)
                exhausted = True
                delay = None
            else:
                delay = backoff_minutes(attempts)
                entry['next_retry_at'] = (
                    self._now() + timedelta(minutes=delay)
                ).isoformat()
                self._state[job.id] = entry
                exhausted = False
        self.save_state()

        if breaker_opened:
            self._log(
                f'OUTAGE BREAKER OPEN: {self._consecutive_transient} consecutive '
                f'transient failures — pausing claims and resumes for '
                f'{self.outage_cooldown_minutes} min.'
            )
        if exhausted:
            self._log(
                f'Job {job.id} exhausted its transient retry budget '
                f'({self.max_transient_retries}) — leaving FAILED. '
                f'Error: {job.error_message[:300]}'
            )
        else:
            self._log(
                f'Job {job.id} failed with a transient error; resume '
                f'{attempts}/{self.max_transient_retries} scheduled in {delay} min.'
            )


class Command(BaseCommand):
    help = "Run the generation job queue: claim PENDING jobs N at a time until stopped."

    def add_arguments(self, parser):
        parser.add_argument('--concurrency', type=int, default=2,
                            help='Max pipelines running at once (default: 2).')
        parser.add_argument('--poll-interval', type=float, default=30,
                            help='Seconds between queue checks (default: 30).')
        parser.add_argument('--resume-stale', action='store_true',
                            help='Resume jobs stuck in RUNNING from a previous process.')
        parser.add_argument('--max-transient-retries', type=int, default=8,
                            help='Auto-resume budget per job for transient LLM errors (default: 8).')
        parser.add_argument('--outage-threshold', type=int, default=3,
                            help='Consecutive transient failures that open the outage breaker (default: 3).')
        parser.add_argument('--outage-cooldown', type=float, default=15,
                            help='Minutes the outage breaker pauses the queue (default: 15).')
        parser.add_argument('--state-file', default=str(DEFAULT_STATE_FILE),
                            help=f'Retry-state JSON file (default: {DEFAULT_STATE_FILE}).')

    def handle(self, *args, **options):
        runner = QueueRunner(
            concurrency=options['concurrency'],
            poll_interval=options['poll_interval'],
            resume_stale=options['resume_stale'],
            max_transient_retries=options['max_transient_retries'],
            outage_threshold=options['outage_threshold'],
            outage_cooldown_minutes=options['outage_cooldown'],
            state_file=options['state_file'],
            out=self.stdout.write,
        )

        def _handle_signal(signum, frame):
            runner.request_stop()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        runner.run_forever()
