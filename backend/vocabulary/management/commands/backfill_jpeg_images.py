"""Backfill JPEG companion images for existing graphic novel pages.

For every GraphicNovelPage that has a PNG (original and/or edited) but no
matching JPEG, generate the lightweight JPEG students load. Idempotent and
safe to re-run: pages that already have their JPEG companions are skipped.

Usage:
    python manage.py backfill_jpeg_images
    python manage.py backfill_jpeg_images --dry-run
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from vocabulary.models import GraphicNovelPage
from vocabulary.services.generation.graphic_novel_images import backfill_page_jpegs


class Command(BaseCommand):
    help = "Generate missing JPEG companion images for graphic novel pages."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be converted without writing any files.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        # Candidates: has a PNG variant whose JPEG companion is still empty.
        pages = (
            GraphicNovelPage.objects
            .filter(
                (Q(image__gt='') & Q(image_jpeg=''))
                | (Q(edited_image__gt='') & Q(edited_image_jpeg=''))
            )
            .select_related('novel')
            .order_by('novel_id', 'page_number')
        )

        total = pages.count()
        if not total:
            self.stdout.write(self.style.SUCCESS("All pages already have JPEG companions."))
            return

        self.stdout.write(f"Found {total} page(s) needing JPEG companions.")
        converted = 0
        for page in pages:
            label = f"{page.novel.title} page {page.page_number}"
            if dry_run:
                needed = []
                if page.image and not page.image_jpeg:
                    needed.append('image_jpeg')
                if page.edited_image and not page.edited_image_jpeg:
                    needed.append('edited_image_jpeg')
                self.stdout.write(f"  [dry-run] {label}: would write {', '.join(needed)}")
                continue
            written = backfill_page_jpegs(page)
            if written:
                converted += 1
                self.stdout.write(f"  {label}: wrote {', '.join(written)}")
            else:
                self.stdout.write(self.style.WARNING(f"  {label}: nothing written (unreadable or conversion failed)"))

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Dry run complete: {total} page(s) would be processed."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done: {converted} page(s) updated."))
