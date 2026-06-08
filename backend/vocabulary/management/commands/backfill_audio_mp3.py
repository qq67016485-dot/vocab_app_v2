"""Backfill MP3 companions for existing graphic novel page audio.

For every COMPLETED GraphicNovelPageAudio that has a stitched WAV but no MP3
companion, encode the compressed MP3 students load. Idempotent and safe to
re-run: rows that already have their MP3 are skipped.

Usage:
    python manage.py backfill_audio_mp3
    python manage.py backfill_audio_mp3 --dry-run
"""
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db.models import Q

from vocabulary.models import GraphicNovelPageAudio
from vocabulary.services.audiobook.encode import wav_bytes_to_mp3_bytes


def _mp3_name(wav_name):
    base = (wav_name or 'graphic_novel_audio').rsplit('/', 1)[-1]
    return base.rsplit('.', 1)[0] + '.mp3'


class Command(BaseCommand):
    help = "Generate missing MP3 companions for graphic novel page audio."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be converted without writing any files.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        # Candidates: COMPLETED rows that have a WAV but no MP3 companion yet.
        rows = (
            GraphicNovelPageAudio.objects
            .filter(
                status=GraphicNovelPageAudio.Status.COMPLETED,
                audio_mp3='',
            )
            .filter(Q(audio__gt=''))
            .select_related('page', 'page__novel')
            .order_by('page__novel_id', 'page__page_number')
        )

        total = rows.count()
        if not total:
            self.stdout.write(self.style.SUCCESS("All completed audio rows already have MP3 companions."))
            return

        self.stdout.write(f"Found {total} audio row(s) needing MP3 companions.")
        converted = 0
        for row in rows:
            page = row.page
            label = f"{page.novel.title} page {page.page_number}"
            if dry_run:
                self.stdout.write(f"  [dry-run] {label}: would encode MP3")
                continue
            try:
                with row.audio.open('rb') as fh:
                    wav_bytes = fh.read()
                mp3_bytes = wav_bytes_to_mp3_bytes(wav_bytes)
            except Exception as exc:  # noqa: BLE001 - report and continue
                self.stdout.write(self.style.WARNING(f"  {label}: skipped ({exc})"))
                continue
            row.audio_mp3.save(_mp3_name(row.audio.name), ContentFile(mp3_bytes), save=False)
            row.save(update_fields=['audio_mp3'])
            converted += 1
            self.stdout.write(f"  {label}: wrote MP3")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Dry run complete: {total} row(s) would be processed."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done: {converted} row(s) updated."))
