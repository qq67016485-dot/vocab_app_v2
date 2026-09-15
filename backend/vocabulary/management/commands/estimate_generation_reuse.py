"""Estimate cross-wordset content reuse for a batch of word sets.

Read-only preflight for a planned generation batch: for each word set it
reports how many of its words already exist (attached by a prior job's dedup)
and how much word-level content (questions, sentence-write tasks, primers,
translations) falls inside the Lexile reuse window and would be reused instead
of regenerated. No LLM or embedding calls are made.

Caveat: actual reuse is gated on the dedup step matching the existing
definition (embedding cosine >= EMBEDDING_SIMILARITY_THRESHOLD). A word that
exists but is looked up in a different sense will regenerate — treat these
numbers as an upper bound.

Usage:
    python manage.py estimate_generation_reuse --ids-file ~/generation_batch.txt
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models.functions import Lower

from vocabulary.models import Question, Word, WordSet
from vocabulary.services.generation.constants import (
    SENTENCE_WRITE_GUIDED_ONLY_MAX_LEXILE,
)
from vocabulary.services.generation.content_reuse import (
    content_lexile_for_target,
    definition_has_translations,
    find_reusable_primer_words,
    find_reusable_question_words,
    find_reusable_sentence_write_words,
)


class Command(BaseCommand):
    help = "Estimate reusable word-level content for word sets listed in an ID file."

    def add_arguments(self, parser):
        parser.add_argument(
            '--ids-file', required=True,
            help='Text file with one word-set ID per line ("#" comments allowed).',
        )
        parser.add_argument(
            '--language', default='zh-CN',
            help='Target language for the translation check (default: zh-CN).',
        )

    def handle(self, *args, **options):
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

        language = options['language']
        totals = dict(words=0, known=0, questions=0, sentence_write=0,
                      primers=0, translations=0)
        sets_seen = 0

        for word_set in WordSet.objects.filter(id__in=ids).order_by('id'):
            input_words = list(dict.fromkeys(
                w.strip() for w in (word_set.input_words or [])
                if isinstance(w, str) and w.strip()
            ))
            if not input_words:
                self.stdout.write(self.style.WARNING(
                    f'  word set {word_set.id}: skipped (no input_words)'
                ))
                continue

            sets_seen += 1
            content_lexile = content_lexile_for_target(word_set.target_lexile)
            words_by_text = {}
            for word in Word.objects.annotate(text_lower=Lower('text')).filter(
                text_lower__in=[w.lower() for w in input_words]
            ):
                words_by_text.setdefault(word.text_lower, word)
            matched = [
                words_by_text[w.lower()] for w in input_words if w.lower() in words_by_text
            ]

            reusable_questions = find_reusable_question_words(matched, content_lexile)
            guided_only = content_lexile <= SENTENCE_WRITE_GUIDED_ONLY_MAX_LEXILE
            sw = find_reusable_sentence_write_words(matched, content_lexile, guided_only)
            if guided_only:
                reusable_sw = sw[Question.QuestionType.SENTENCE_WRITE_GUIDED]
            else:
                reusable_sw = (
                    sw[Question.QuestionType.SENTENCE_WRITE_GUIDED]
                    & sw[Question.QuestionType.SENTENCE_WRITE_OPEN]
                )
            reusable_primers = find_reusable_primer_words(matched, content_lexile)
            reusable_translations = {
                word.id for word in matched
                if word.definitions.first()
                and definition_has_translations(word.definitions.first(), language)
            }

            totals['words'] += len(input_words)
            totals['known'] += len(matched)
            totals['questions'] += len(reusable_questions)
            totals['sentence_write'] += len(reusable_sw)
            totals['primers'] += len(reusable_primers)
            totals['translations'] += len(reusable_translations)

            self.stdout.write(
                f'  set {word_set.id} "{word_set.title}" '
                f'({len(input_words)} words, {word_set.target_lexile}L -> '
                f'content {content_lexile}L): known {len(matched)}/{len(input_words)}; '
                f'reusable questions {len(reusable_questions)}, '
                f'sentence-write {len(reusable_sw)}, '
                f'primers {len(reusable_primers)}, '
                f'translations {len(reusable_translations)}'
            )

        missing = set(ids) - set(
            WordSet.objects.filter(id__in=ids).values_list('id', flat=True)
        )
        for word_set_id in sorted(missing):
            self.stdout.write(self.style.WARNING(f'  word set {word_set_id}: not found'))

        self.stdout.write(self.style.SUCCESS(
            f'\n{sets_seen} sets, {totals["words"]} words: '
            f'{totals["known"]} already exist. Reusable (upper bound): '
            f'questions {totals["questions"]}, sentence-write {totals["sentence_write"]}, '
            f'primers {totals["primers"]}, translations {totals["translations"]}.\n'
            f'Pack-level steps (packs, graphic novels, infographics) always generate.'
        ))
