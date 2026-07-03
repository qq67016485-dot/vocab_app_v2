"""Seed a student with ready-to-practice sentence-writing questions.

The sentence-writing question types (SENTENCE_WRITE_GUIDED at L4,
SENTENCE_WRITE_OPEN at L5) are normally produced by the LLM pipeline. This
command hand-builds a small, realistic set so the student-side flow can be
exercised end-to-end WITHOUT running generation:

  - creates/reuses a student account (known password),
  - creates a handful of Words + WordDefinitions + PrimerContent,
  - attaches guided + open sentence-write Questions with proper rubric
    ``options`` and a ``model_sentence`` (example_sentence),
  - creates READY UserWordProgress rows due *now*, at the mastery level that
    makes each variant the one the picker serves (L4 → guided, L5 → open).

The only piece that still needs a live LLM is the *judge* itself: when the
student submits a sentence, ``sentence_judge`` (LLM config matrix) is called.
Make sure your local Gemini config works, or the submit returns
``sentence_write_unavailable`` (graceful skip, no penalty).

Idempotent: re-running reuses the same words/questions and resets the progress
rows to due-now so you can practice again immediately.

Usage:
    python manage.py seed_sentence_write_test
    python manage.py seed_sentence_write_test --student swtest --password pass1234
    python manage.py seed_sentence_write_test --reset   # also wipe today's answers/limit
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from vocabulary.models import (
    Word, WordDefinition, PrimerCardContent, Question, MasteryLevel,
    UserWordProgress, UserAnswer,
)
from vocabulary.constants import QUESTION_TYPE_LEVEL

CustomUser = None  # resolved in handle() to keep import light


# (word, part_of_speech, definition, kid-friendly def, guided scenario,
#  sentence starter, open scenario, model sentence, intended sense)
SEED_WORDS = [
    {
        'text': 'reluctant',
        'pos': 'adjective',
        'definition': 'unwilling and hesitant to do something',
        'kid_def': 'not wanting to do something',
        'guided_scenario': (
            "Your friend asks you to try a food you have never eaten before. "
            "Write a sentence describing how you feel using the word."
        ),
        'starter': 'At first I was',
        'open_scenario': (
            "Describe a time someone did not want to do something. Use the word."
        ),
        'model_sentence': 'At first I was reluctant to try the spicy noodles.',
        'intended_sense': 'unwilling / hesitant to act',
        'acceptable_use_notes': [
            'Must show hesitation or unwillingness, not just dislike.',
        ],
    },
    {
        'text': 'abundant',
        'pos': 'adjective',
        'definition': 'existing in large amounts; plentiful',
        'kid_def': 'more than enough',
        'guided_scenario': (
            "You walk into an orchard full of apples. Write a sentence about "
            "how much fruit there is using the word."
        ),
        'starter': 'The trees held an',
        'open_scenario': (
            "Describe a place that has a lot of something. Use the word."
        ),
        'model_sentence': 'The trees held an abundant supply of ripe apples.',
        'intended_sense': 'present in large / plentiful amounts',
        'acceptable_use_notes': [
            'Should convey a large quantity, not scarcity.',
        ],
    },
    {
        'text': 'fragile',
        'pos': 'adjective',
        'definition': 'easily broken or damaged',
        'kid_def': 'breaks easily',
        'guided_scenario': (
            "You are carrying a box of glass ornaments. Write a sentence "
            "warning someone to be careful using the word."
        ),
        'starter': 'Be careful — the',
        'open_scenario': (
            "Describe something that could break easily. Use the word."
        ),
        'model_sentence': 'Be careful — the glass ornaments are very fragile.',
        'intended_sense': 'easily broken / delicate',
        'acceptable_use_notes': [
            'Must describe something breakable or delicate.',
        ],
    },
]


class Command(BaseCommand):
    help = "Seed a student with ready-to-practice sentence-writing questions (no LLM needed for setup)."

    def add_arguments(self, parser):
        parser.add_argument('--student', default='swtest',
                            help='Student username (created if absent). Default: swtest')
        parser.add_argument('--password', default='testpass123',
                            help='Password to set on the student. Default: testpass123')
        parser.add_argument('--reset', action='store_true',
                            help="Also clear today's answers and raise the daily limit so you can practice freely.")

    @transaction.atomic
    def handle(self, *args, **opts):
        global CustomUser
        from django.contrib.auth import get_user_model
        CustomUser = get_user_model()

        username = opts['student']
        password = opts['password']

        # Mastery levels 4 (guided) and 5 (open) must exist (seeded by migration 0017).
        guided_level_id = QUESTION_TYPE_LEVEL[Question.QuestionType.SENTENCE_WRITE_GUIDED]  # 4
        open_level_id = QUESTION_TYPE_LEVEL[Question.QuestionType.SENTENCE_WRITE_OPEN]      # 5
        try:
            guided_level = MasteryLevel.objects.get(level_id=guided_level_id)
            open_level = MasteryLevel.objects.get(level_id=open_level_id)
        except MasteryLevel.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                "Mastery levels not seeded. Run `python manage.py migrate` first."))
            return

        student, created = CustomUser.objects.get_or_create(
            username=username,
            defaults={'role': CustomUser.Role.STUDENT},
        )
        student.role = CustomUser.Role.STUDENT
        student.set_password(password)
        # Widen lexile range so any question lexile passes (we also set null below).
        student.lexile_min = 0
        student.lexile_max = 2000
        if opts['reset'] or student.daily_question_limit < 50:
            student.daily_question_limit = 50
        student.save()

        if opts['reset']:
            deleted, _ = UserAnswer.objects.filter(user=student).delete()
            self.stdout.write(f"Cleared {deleted} prior answer rows for {username}.")

        now = timezone.now()
        # Alternate variants across seed words so both types are servable:
        # index 0,2 -> guided (L4); index 1 -> open (L5). Every word still gets
        # BOTH question rows attached, but its progress level decides what shows.
        for i, spec in enumerate(SEED_WORDS):
            word, _ = Word.objects.get_or_create(
                text=spec['text'], part_of_speech=spec['pos'],
                defaults={'source_context': 'sentence-write test seed'},
            )
            WordDefinition.objects.get_or_create(
                word=word, definition_text=spec['definition'],
                defaults={
                    'example_sentence': spec['model_sentence'],
                    'lexile_score': None,
                },
            )
            PrimerCardContent.objects.update_or_create(
                word=word,
                defaults={
                    'kid_friendly_definition': spec['kid_def'],
                    'syllable_text': spec['text'],
                    'example_sentence': spec['model_sentence'],
                },
            )

            self._make_guided(word, spec, guided_level)
            self._make_open(word, spec, open_level)

            # Serve guided for even indices, open for odd — so you see both.
            serve_level = open_level if (i % 2 == 1) else guided_level
            UserWordProgress.objects.update_or_create(
                user=student, word=word,
                defaults={
                    'level': serve_level,
                    'mastery_points': 0,
                    'next_review_at': now,          # due now
                    'last_reviewed_at': None,       # counts as NEW_WORD
                    'instructional_status': 'READY',
                    'learning_speed': 1.0,
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"\nSeeded {len(SEED_WORDS)} words for student '{username}' (password: '{password}')."))
        self.stdout.write(
            "  Login as this student, open Practice, and you'll get sentence-writing prompts.\n"
            "  Words served as GUIDED (starter + scenario): "
            + ", ".join(s['text'] for i, s in enumerate(SEED_WORDS) if i % 2 == 0) + "\n"
            "  Words served as OPEN (scenario only): "
            + ", ".join(s['text'] for i, s in enumerate(SEED_WORDS) if i % 2 == 1) + "\n"
            "  NOTE: submitting a sentence calls the LLM judge (sentence_judge step). "
            "Ensure your Gemini config works, or you'll see a graceful 'come back later' skip."
        )

    def _make_guided(self, word, spec, level):
        q, _ = Question.objects.update_or_create(
            word=word,
            question_type=Question.QuestionType.SENTENCE_WRITE_GUIDED,
            defaults={
                'question_text': spec['guided_scenario'],
                'options': {
                    'intended_sense': spec['intended_sense'],
                    'acceptable_use_notes': spec['acceptable_use_notes'],
                    'sentence_starter': spec['starter'],
                },
                'correct_answers': [],
                'explanation': '',
                'example_sentence': spec['model_sentence'],
                'lexile_score': None,
            },
        )
        q.suitable_levels.set([level])

    def _make_open(self, word, spec, level):
        q, _ = Question.objects.update_or_create(
            word=word,
            question_type=Question.QuestionType.SENTENCE_WRITE_OPEN,
            defaults={
                'question_text': spec['open_scenario'],
                'options': {
                    'intended_sense': spec['intended_sense'],
                    'acceptable_use_notes': spec['acceptable_use_notes'],
                },
                'correct_answers': [],
                'explanation': '',
                'example_sentence': spec['model_sentence'],
                'lexile_score': None,
            },
        )
        q.suitable_levels.set([level])
