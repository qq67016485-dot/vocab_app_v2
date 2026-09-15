"""Tests for the generation queue runner and the enqueue command."""
import json
from datetime import datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from vocabulary.management.commands import run_generation_queue as rq
from vocabulary.management.commands.run_generation_queue import (
    QueueRunner, backoff_minutes, classify_error,
)
from vocabulary.models import GenerationJob, WordSet
from tests.factories import GenerationJobFactory, WordSetFactory

PENDING = GenerationJob.Status.PENDING
RUNNING = GenerationJob.Status.RUNNING
COMPLETED = GenerationJob.Status.COMPLETED
FAILED = GenerationJob.Status.FAILED


class SyncThread:
    """Thread stand-in for tests: runs the target synchronously in start()
    and always reports itself dead, so ticks are fully deterministic."""

    def __init__(self, target=None, args=(), daemon=None, name=None):
        self._target = target
        self._args = args

    def start(self):
        self._target(*self._args)

    def is_alive(self):
        return False

    def join(self, timeout=None):
        return None


def make_runner(tmp_path, **kwargs):
    kwargs.setdefault('state_file', tmp_path / 'state.json')
    runner = QueueRunner(**kwargs)
    runner._thread_factory = SyncThread
    return runner


def fail_with(message):
    """Entrypoint fake that leaves the job FAILED with the given message."""
    def fake(job_id):
        GenerationJob.objects.filter(id=job_id).update(
            status=FAILED, error_message=message,
        )
    return fake


# =============================================================================
# enqueue_generation command
# =============================================================================

@pytest.mark.django_db
class TestEnqueueGeneration:

    def _ids_file(self, tmp_path, lines):
        path = tmp_path / 'ids.txt'
        path.write_text('\n'.join(str(line) for line in lines) + '\n')
        return str(path)

    def test_creates_pending_jobs_from_word_sets(self, tmp_path):
        ws = WordSetFactory(input_words=['apple', 'banana'], target_lexile=500)
        out = StringIO()
        call_command('enqueue_generation', '--ids-file', self._ids_file(tmp_path, [ws.id]), stdout=out)

        job = GenerationJob.objects.get(word_set=ws)
        assert job.status == PENDING
        assert job.input_words == ['apple', 'banana']
        assert job.content_types == ['graphic_novel', 'infographic']
        assert job.created_by == ws.creator
        assert job.target_lexile == 500
        assert job.target_language == 'zh-CN'
        # The word set flips to GENERATING only when the runner claims the job.
        ws.refresh_from_db()
        assert ws.generation_status != WordSet.GenerationStatus.GENERATING

    def test_content_types_override(self, tmp_path):
        ws = WordSetFactory(input_words=['apple'])
        call_command(
            'enqueue_generation', '--ids-file', self._ids_file(tmp_path, [ws.id]),
            '--content-types', 'graphic_novel',
        )
        assert GenerationJob.objects.get(word_set=ws).content_types == ['graphic_novel']

    def test_skips_generated_active_and_empty_word_sets(self, tmp_path):
        generated = WordSetFactory(
            input_words=['x'], generation_status=WordSet.GenerationStatus.GENERATED,
        )
        active = WordSetFactory(input_words=['y'])
        GenerationJobFactory(word_set=active, status=PENDING)
        empty = WordSetFactory(input_words=None)

        out = StringIO()
        call_command(
            'enqueue_generation',
            '--ids-file', self._ids_file(tmp_path, [generated.id, active.id, empty.id, 999999]),
            stdout=out,
        )

        # Only the pre-seeded active job exists; nothing new was created.
        assert GenerationJob.objects.count() == 1
        text = out.getvalue()
        assert 'already GENERATED' in text
        assert 'already has a PENDING/RUNNING job' in text
        assert 'no input_words' in text
        assert 'not found' in text

    def test_idempotent_rerun_and_comments(self, tmp_path):
        ws = WordSetFactory(input_words=['apple'])
        path = self._ids_file(tmp_path, ['# first batch', ws.id, '', ws.id])
        call_command('enqueue_generation', '--ids-file', path)
        out = StringIO()
        call_command('enqueue_generation', '--ids-file', path, stdout=out)

        assert GenerationJob.objects.filter(word_set=ws).count() == 1
        assert '0 enqueued, 1 skipped' in out.getvalue()

    def test_invalid_line_rejected(self, tmp_path):
        with pytest.raises(CommandError):
            call_command('enqueue_generation', '--ids-file', self._ids_file(tmp_path, ['12', 'abc']))


# =============================================================================
# error classification + backoff
# =============================================================================

class TestErrorClassification:

    @pytest.mark.parametrize('message', [
        'Error code: 429 - {"error": {"message": "Rate limit reached"}}',
        'HTTPSConnectionPool(host=proxy): Read timed out. (read timeout=600)',
        '503 Service Unavailable',
        '502 Bad Gateway',
        '504 Gateway Timeout',
        '500 Internal Server Error',
        'The server is overloaded or not ready yet.',
        'openai.APIConnectionError: Connection error.',
        'Connection reset by peer',
        'The service is currently unavailable.',
    ])
    def test_transient(self, message):
        assert classify_error(message) == 'transient'

    @pytest.mark.parametrize('message', [
        'Cloze coverage failed for pack word "bright"',
        'Validation error: beat sheet page_count mismatch',
        'Job 12 cannot be resumed (current: COMPLETED)',
        'lexile 1500 out of range',  # numeric word-boundary check
        '',
    ])
    def test_deterministic(self, message):
        assert classify_error(message) == 'deterministic'


def test_backoff_schedule():
    assert [backoff_minutes(i) for i in range(1, 7)] == [5, 10, 20, 30, 30, 30]


# =============================================================================
# claiming
# =============================================================================

@pytest.mark.django_db
class TestRunnerClaim:

    def test_claims_oldest_first_up_to_concurrency(self, tmp_path, monkeypatch):
        completed = []

        def fake_run(job_id):
            completed.append(job_id)
            GenerationJob.objects.filter(id=job_id).update(status=COMPLETED)

        monkeypatch.setattr(rq, 'run_full_pipeline', fake_run)
        jobs = [GenerationJobFactory(status=PENDING) for _ in range(3)]

        runner = make_runner(tmp_path, concurrency=2)
        runner.tick()
        assert completed == [jobs[0].id, jobs[1].id]
        runner.tick()  # dead sync threads reaped; third job fits now
        assert completed == [jobs[0].id, jobs[1].id, jobs[2].id]

    def test_claim_marks_running_and_word_set_generating(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rq, 'run_full_pipeline', lambda job_id: None)
        job = GenerationJobFactory(status=PENDING)

        make_runner(tmp_path, concurrency=1).tick()

        job.refresh_from_db()
        job.word_set.refresh_from_db()
        assert job.status == RUNNING
        assert job.word_set.generation_status == WordSet.GenerationStatus.GENERATING

    def test_running_jobs_elsewhere_count_toward_concurrency(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rq, 'run_full_pipeline', lambda job_id: None)
        GenerationJobFactory(status=RUNNING)  # e.g. triggered from the web UI
        pending = GenerationJobFactory(status=PENDING)

        make_runner(tmp_path, concurrency=1).tick()

        pending.refresh_from_db()
        assert pending.status == PENDING


# =============================================================================
# transient retry (layer 2)
# =============================================================================

@pytest.mark.django_db
class TestTransientRetry:

    def test_transient_failure_schedules_resume_with_backoff(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rq, 'run_full_pipeline', fail_with('Error code: 429 - rate limit'))
        job = GenerationJobFactory(status=PENDING)

        runner = make_runner(tmp_path)
        runner.tick()

        job.refresh_from_db()
        assert job.status == FAILED
        entry = runner._state[job.id]
        assert entry['transient_attempts'] == 1
        eta = datetime.fromisoformat(entry['next_retry_at'])
        assert timedelta(minutes=4) < eta - timezone.now() < timedelta(minutes=6)
        # persisted to disk on every transition
        disk = json.loads((tmp_path / 'state.json').read_text())
        assert disk['jobs'][str(job.id)]['transient_attempts'] == 1

    def test_due_resume_fires_and_refailure_reschedules(self, tmp_path, monkeypatch):
        resumes = []

        def fake_resume(job_id):
            resumes.append(job_id)
            GenerationJob.objects.filter(id=job_id).update(
                status=FAILED, error_message='503 Service Unavailable',
            )

        monkeypatch.setattr(rq, 'run_full_pipeline', fail_with('503 Service Unavailable'))
        monkeypatch.setattr(rq, 'resume_pipeline', fake_resume)
        job = GenerationJobFactory(status=PENDING)

        runner = make_runner(tmp_path)
        runner.tick()
        assert resumes == []  # backoff not elapsed yet

        future = timezone.now() + timedelta(minutes=6)
        runner._now = lambda: future
        runner.tick()

        assert resumes == [job.id]
        entry = runner._state[job.id]
        assert entry['transient_attempts'] == 2
        eta = datetime.fromisoformat(entry['next_retry_at'])
        assert timedelta(minutes=9) < eta - future < timedelta(minutes=11)

    def test_budget_exhaustion_leaves_failed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rq, 'run_full_pipeline', fail_with('timeout'))
        monkeypatch.setattr(rq, 'resume_pipeline', fail_with('timeout'))
        job = GenerationJobFactory(status=PENDING)

        runner = make_runner(tmp_path, max_transient_retries=1)
        runner.tick()
        assert job.id in runner._state  # one resume scheduled

        runner._now = lambda: timezone.now() + timedelta(minutes=6)
        runner.tick()  # resume fails too -> budget (1) exceeded
        assert job.id not in runner._state
        job.refresh_from_db()
        assert job.status == FAILED

    def test_deterministic_failure_is_never_retried(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            rq, 'run_full_pipeline',
            fail_with('Cloze coverage failed: pack word "bright" got no cloze row'),
        )
        job = GenerationJobFactory(status=PENDING)

        runner = make_runner(tmp_path)
        runner.tick()

        assert job.id not in runner._state  # no retry scheduled
        job.refresh_from_db()
        assert job.status == FAILED


# =============================================================================
# outage breaker (layer 3)
# =============================================================================

@pytest.mark.django_db
class TestOutageBreaker:

    def test_opens_after_threshold_and_blocks_claims(self, tmp_path):
        runner = make_runner(tmp_path, outage_threshold=3, outage_cooldown_minutes=15)
        failed = GenerationJobFactory(status=FAILED, error_message='503 unavailable')

        runner._handle_failure(failed)
        runner._handle_failure(failed)
        assert not runner._breaker_open()
        runner._handle_failure(failed)
        assert runner._breaker_open()

        pending = GenerationJobFactory(status=PENDING)
        runner.tick()  # breaker open -> nothing is claimed
        pending.refresh_from_db()
        assert pending.status == PENDING

        runner._now = lambda: timezone.now() + timedelta(minutes=16)
        assert not runner._breaker_open()

    def test_success_resets_the_counter(self, tmp_path):
        runner = make_runner(tmp_path, outage_threshold=3)
        failed = GenerationJobFactory(status=FAILED, error_message='timeout')
        for _ in range(3):
            runner._handle_failure(failed)
        assert runner._breaker_open()

        done = GenerationJobFactory(status=COMPLETED)
        runner._postprocess(done.id)
        assert runner._consecutive_transient == 0
        assert not runner._breaker_open()


# =============================================================================
# state persistence + stale recovery
# =============================================================================

@pytest.mark.django_db
class TestRecovery:

    def test_retry_budget_survives_restart(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rq, 'run_full_pipeline', fail_with('429 rate limit'))
        job = GenerationJobFactory(status=PENDING)
        make_runner(tmp_path).tick()

        # Simulate a service restart: fresh runner over the same state file.
        resumes = []
        monkeypatch.setattr(rq, 'resume_pipeline', lambda job_id: resumes.append(job_id))
        runner2 = make_runner(tmp_path)
        runner2.startup()
        assert runner2._state[job.id]['transient_attempts'] == 1

        runner2._now = lambda: timezone.now() + timedelta(minutes=6)
        runner2.tick()
        assert resumes == [job.id]

    def test_exhausted_jobs_are_not_rearmed(self, tmp_path):
        job = GenerationJobFactory(status=FAILED, error_message='503')
        (tmp_path / 'state.json').write_text(json.dumps(
            {'jobs': {str(job.id): {'transient_attempts': 8, 'next_retry_at': None}}}
        ))
        runner = make_runner(tmp_path, max_transient_retries=8)
        runner.startup()
        assert job.id not in runner._state

    def test_entries_for_finished_jobs_are_dropped(self, tmp_path):
        job = GenerationJobFactory(status=COMPLETED)
        (tmp_path / 'state.json').write_text(json.dumps(
            {'jobs': {str(job.id): {'transient_attempts': 1, 'next_retry_at': None}}}
        ))
        runner = make_runner(tmp_path)
        runner.startup()
        assert job.id not in runner._state

    def test_resume_stale_resumes_running_jobs(self, tmp_path, monkeypatch):
        resumes = []
        monkeypatch.setattr(rq, 'resume_pipeline', lambda job_id: resumes.append(job_id))
        job = GenerationJobFactory(status=RUNNING)

        runner = make_runner(tmp_path, resume_stale=True, concurrency=1)
        runner.startup()
        runner.tick()
        assert resumes == [job.id]

    def test_without_resume_stale_running_jobs_are_left_alone(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            rq, 'resume_pipeline',
            lambda job_id: pytest.fail('resume_pipeline must not be called'),
        )
        job = GenerationJobFactory(status=RUNNING)

        runner = make_runner(tmp_path, resume_stale=False, concurrency=1)
        runner.startup()
        runner.tick()
        job.refresh_from_db()
        assert job.status == RUNNING
