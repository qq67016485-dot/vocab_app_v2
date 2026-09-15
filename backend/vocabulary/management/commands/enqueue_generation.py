"""Enqueue PENDING generation jobs for a batch of word sets.

Reads word-set IDs from a text file (one per line, '#' comments allowed) and
creates a PENDING GenerationJob for each — without starting anything. The
``run_generation_queue`` service picks the jobs up from there. Idempotent:
re-running skips word sets that already have a PENDING/RUNNING job or are
already GENERATED.

Usage:
    python manage.py enqueue_generation --ids-file ~/generation_batch.txt
    python manage.py enqueue_generation --ids-file ids.txt --content-types graphic_novel
"""
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from vocabulary.models import GenerationJob, WordSet
from vocabulary.services.generation.constants import (
    ALLOWED_CONTENT_TYPES, CONTENT_TYPE_GRAPHIC_NOVEL, CONTENT_TYPE_INFOGRAPHIC,
)


class Command(BaseCommand):
    help = "Create PENDING generation jobs for word sets listed in an ID file."

    def add_arguments(self, parser):
        parser.add_argument(
            '--ids-file', required=True,
            help='Text file with one word-set ID per line ("#" comments allowed).',
        )
        parser.add_argument(
            '--content-types', nargs='+',
            default=[CONTENT_TYPE_GRAPHIC_NOVEL, CONTENT_TYPE_INFOGRAPHIC],
            help=f'Content types to generate. Allowed: {", ".join(ALLOWED_CONTENT_TYPES)}.',
        )
        parser.add_argument(
            '--user', default=None,
            help='Username recorded as created_by (default: the word set creator).',
        )

    def handle(self, *args, **options):
        content_types = [t for t in options['content_types'] if t in ALLOWED_CONTENT_TYPES]
        if not content_types:
            raise CommandError(
                f'No valid content types in {options["content_types"]}. '
                f'Allowed: {", ".join(ALLOWED_CONTENT_TYPES)}'
            )

        try:
            raw = Path(options['ids_file']).read_text()
        except OSError as exc:
            raise CommandError(f'Cannot read ids file: {exc}')

        ids = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                ids.append(int(line))
            except ValueError:
                raise CommandError(f'Invalid line in ids file: {line!r} (expected an integer ID)')
        ids = list(dict.fromkeys(ids))
        if not ids:
            raise CommandError('No word-set IDs found in the file.')

        user = None
        if options['user']:
            user = get_user_model().objects.filter(username=options['user']).first()
            if user is None:
                raise CommandError(f'User not found: {options["user"]}')

        active_statuses = [GenerationJob.Status.PENDING, GenerationJob.Status.RUNNING]
        enqueued, skipped, missing = [], [], []
        for word_set_id in ids:
            # Lock the word-set row per enqueue — mirrors the duplicate-job
            # guard in TriggerGenerationView so a concurrent web trigger can't
            # race us into a duplicate job for the same word set.
            with transaction.atomic():
                word_set = WordSet.objects.select_for_update().filter(id=word_set_id).first()
                if word_set is None:
                    missing.append(word_set_id)
                    continue
                if word_set.generation_status == WordSet.GenerationStatus.GENERATED:
                    skipped.append((word_set_id, 'already GENERATED'))
                    continue
                if word_set.generation_jobs.filter(status__in=active_statuses).exists():
                    skipped.append((word_set_id, 'already has a PENDING/RUNNING job'))
                    continue
                words = list(dict.fromkeys(
                    w.strip() for w in (word_set.input_words or [])
                    if isinstance(w, str) and w.strip()
                ))
                if not words:
                    skipped.append((word_set_id, 'word set has no input_words'))
                    continue
                job = GenerationJob.objects.create(
                    word_set=word_set,
                    created_by=user or word_set.creator,
                    input_words=words,
                    input_source_title=word_set.input_source_title,
                    input_source_chapter=word_set.input_source_chapter,
                    input_source_text=word_set.source_text,
                    target_lexile=word_set.target_lexile,
                    target_language='zh-CN',
                    content_types=content_types,
                )
                enqueued.append((word_set_id, job.id))

        for word_set_id, job_id in enqueued:
            self.stdout.write(f'  word set {word_set_id}: created job {job_id}')
        for word_set_id, reason in skipped:
            self.stdout.write(self.style.WARNING(f'  word set {word_set_id}: skipped ({reason})'))
        for word_set_id in missing:
            self.stdout.write(self.style.WARNING(f'  word set {word_set_id}: not found'))
        self.stdout.write(self.style.SUCCESS(
            f'Done: {len(enqueued)} enqueued, {len(skipped)} skipped, {len(missing)} missing.'
        ))
