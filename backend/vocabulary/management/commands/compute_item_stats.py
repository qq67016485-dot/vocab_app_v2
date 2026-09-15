"""Compute classical test theory (CTT) item statistics for choice questions.

Offline analysis over UserAnswer history (first attempts only — retries never
create rows). Populates the previously-dead ``difficulty_index`` /
``discrimination_index`` columns and maintains ``qa_flags`` as a
flag-for-review signal. It NEVER sets ``is_serve_excluded`` — hiding a
question is an admin decision via POST /api/questions/{id}/flag/.

Scope: closed-answer (auto-graded) question types only. Sentence-write
questions are LLM-judged with no closed answer key and are excluded.

- difficulty_index: Beta-shrunk proportion correct,
  ``p = (correct + 8*m) / (n + 8)``, where ``m`` is the mean accuracy over all
  answers to questions of the same question_type. n < 5 (override with
  --min-n) leaves difficulty NULL (insufficient data).
- discrimination_index: point-biserial correlation between per-answer
  is_correct and the answerer's leave-one-out ability (their accuracy over all
  their other answers — excluding answers to the question itself avoids
  part-whole inflation). Needs n >= 10; for 10 <= n < 20 the value is shrunk
  toward 0 (``d * (n - 10) / 10``); zero variance on either side -> NULL.
- qa_flags: stat-flags (too_easy p > 0.9, too_hard p < 0.2,
  low_discrimination d < 0.2) are recomputed and replace previously computed
  stat-flags; foreign strings (e.g. verification_mismatch) are preserved.

--gradient runs a separate analysis-only check (no DB writes): delayed-accuracy
difficulty gradient — mean accuracy per mastery level over answers given >= 24h
after the same user's previous answer for the same word.

Usage:
    python manage.py compute_item_stats [--dry-run] [--word-set ID]
        [--min-n N] [--output PATH] [--gradient]
"""
import json
import math
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from vocabulary.constants import QUESTION_TYPE_LEVEL
from vocabulary.models import Question, UserAnswer, WordSet

SENTENCE_WRITE_TYPES = (
    Question.QuestionType.SENTENCE_WRITE_GUIDED,
    Question.QuestionType.SENTENCE_WRITE_OPEN,
)

FLAG_TOO_EASY = 'too_easy'
FLAG_TOO_HARD = 'too_hard'
FLAG_LOW_DISCRIMINATION = 'low_discrimination'
# Flags this command computes; any other string in qa_flags is foreign and
# preserved across recomputes.
STAT_FLAGS = frozenset({FLAG_TOO_EASY, FLAG_TOO_HARD, FLAG_LOW_DISCRIMINATION})

DEFAULT_MIN_N = 5               # below this, difficulty stays NULL
DISCRIMINATION_MIN_N = 10       # below this, discrimination stays NULL
DISCRIMINATION_FULL_N = 20      # below this (but >= MIN), shrink toward 0
SHRINK_STRENGTH = 8             # Beta prior weight for difficulty shrinkage

TOO_EASY_THRESHOLD = 0.9
TOO_HARD_THRESHOLD = 0.2
LOW_DISCRIMINATION_THRESHOLD = 0.2

DELAYED_GAP_MIN = timedelta(hours=24)


def _pearson(xs, ys):
    """Pearson correlation; None when undefined (< 2 pairs or zero variance)."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


class Command(BaseCommand):
    help = "Compute CTT item stats (difficulty/discrimination) and QA flags for choice questions."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Compute and report only; do not write to the database.',
        )
        parser.add_argument(
            '--word-set', type=int, metavar='ID',
            help='Restrict to questions of words in this word set.',
        )
        parser.add_argument(
            '--min-n', type=int, default=DEFAULT_MIN_N, metavar='N',
            help=f'Minimum answers before difficulty is computed (default: {DEFAULT_MIN_N}).',
        )
        parser.add_argument(
            '--output', metavar='PATH',
            help='Also write the per-question-type aggregate report as JSON.',
        )
        parser.add_argument(
            '--gradient', action='store_true',
            help='Analysis-only delayed-accuracy difficulty gradient (no DB writes).',
        )

    def handle(self, *args, **options):
        word_set = None
        if options['word_set'] is not None:
            try:
                word_set = WordSet.objects.get(id=options['word_set'])
            except WordSet.DoesNotExist:
                raise CommandError(f"Word set {options['word_set']} not found.")

        if options['gradient']:
            self._run_gradient(word_set)
            return

        questions_qs = Question.objects.exclude(
            question_type__in=SENTENCE_WRITE_TYPES,
        ).order_by('id')
        if word_set is not None:
            questions_qs = questions_qs.filter(word__in=word_set.words.all())
        questions = list(questions_qs)
        if not questions:
            self.stdout.write(self.style.WARNING('No in-scope questions found.'))
            return

        min_n = options['min_n']
        stats_by_id = self._compute_stats(questions, min_n)
        now = timezone.now()

        to_save = []
        for question in questions:
            computed = stats_by_id[question.id]
            new_stat_flags = set()
            difficulty = computed['difficulty']
            discrimination = computed['discrimination']
            if difficulty is not None:
                if difficulty > TOO_EASY_THRESHOLD:
                    new_stat_flags.add(FLAG_TOO_EASY)
                if difficulty < TOO_HARD_THRESHOLD:
                    new_stat_flags.add(FLAG_TOO_HARD)
            if discrimination is not None and discrimination < LOW_DISCRIMINATION_THRESHOLD:
                new_stat_flags.add(FLAG_LOW_DISCRIMINATION)

            preserved = [f for f in (question.qa_flags or []) if f not in STAT_FLAGS]
            question.qa_flags = preserved + sorted(new_stat_flags)
            question.qa_checked_at = now
            question.difficulty_index = difficulty
            question.discrimination_index = discrimination
            # is_serve_excluded deliberately untouched — flag-for-review only.
            to_save.append(question)

            if options['dry_run']:
                self.stdout.write(
                    f'  [dry-run] Q{question.id} ({question.question_type}): '
                    f'n={computed["n"]}, '
                    f'p={_fmt(difficulty)}, d={_fmt(discrimination)}, '
                    f'flags={question.qa_flags or "[]"}'
                )

        if not options['dry_run']:
            Question.objects.bulk_update(
                to_save,
                ['difficulty_index', 'discrimination_index', 'qa_flags', 'qa_checked_at'],
            )

        report = self._build_report(questions, stats_by_id)
        self._print_report(report)
        if options['output']:
            payload = {
                'generated_at': now.isoformat(),
                'dry_run': bool(options['dry_run']),
                'word_set_id': word_set.id if word_set else None,
                'question_types': report,
            }
            with open(options['output'], 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, indent=2)
            self.stdout.write(f'Report written to {options["output"]}')

        action = 'Would update' if options['dry_run'] else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{action} {len(to_save)} questions.'))

    # ------------------------------------------------------------------
    # Stats computation
    # ------------------------------------------------------------------

    def _compute_stats(self, questions, min_n):
        """Per-question {n, difficulty, discrimination} over the answer pool.

        The pool is all UserAnswer rows for the in-scope questions; the
        leave-one-out ability proxy is computed within this same pool.
        """
        question_type_by_id = {q.id: q.question_type for q in questions}
        answers_by_question = defaultdict(list)
        user_total = defaultdict(int)
        user_correct = defaultdict(int)
        q_user_total = defaultdict(lambda: defaultdict(int))
        q_user_correct = defaultdict(lambda: defaultdict(int))
        type_total = defaultdict(int)
        type_correct = defaultdict(int)

        answer_rows = (
            UserAnswer.objects.filter(question__in=questions)
            .values('question_id', 'user_id', 'is_correct')
            .iterator()
        )
        for row in answer_rows:
            qid = row['question_id']
            uid = row['user_id']
            correct = 1 if row['is_correct'] else 0
            answers_by_question[qid].append(row)
            user_total[uid] += 1
            user_correct[uid] += correct
            q_user_total[qid][uid] += 1
            q_user_correct[qid][uid] += correct
            qtype = question_type_by_id[qid]
            type_total[qtype] += 1
            type_correct[qtype] += correct

        type_mean = {
            qtype: type_correct[qtype] / type_total[qtype]
            for qtype in type_total
        }

        stats_by_id = {}
        for question in questions:
            qid = question.id
            rows = answers_by_question.get(qid, [])
            n = len(rows)
            correct = sum(1 for r in rows if r['is_correct'])

            difficulty = None
            if n >= min_n:
                m = type_mean.get(question.question_type, 0.0)
                difficulty = (correct + SHRINK_STRENGTH * m) / (n + SHRINK_STRENGTH)

            discrimination = None
            if n >= DISCRIMINATION_MIN_N:
                abilities = []
                outcomes = []
                for row in rows:
                    uid = row['user_id']
                    other_n = user_total[uid] - q_user_total[qid][uid]
                    if other_n <= 0:
                        # No other answers -> leave-one-out ability undefined.
                        continue
                    other_correct = user_correct[uid] - q_user_correct[qid][uid]
                    abilities.append(other_correct / other_n)
                    outcomes.append(1 if row['is_correct'] else 0)
                d = _pearson(abilities, outcomes)
                if d is not None and n < DISCRIMINATION_FULL_N:
                    d = d * (n - DISCRIMINATION_MIN_N) / (DISCRIMINATION_FULL_N - DISCRIMINATION_MIN_N)
                discrimination = d

            stats_by_id[qid] = {
                'n': n,
                'difficulty': difficulty,
                'discrimination': discrimination,
            }
        return stats_by_id

    # ------------------------------------------------------------------
    # Aggregate report
    # ------------------------------------------------------------------

    def _build_report(self, questions, stats_by_id):
        by_type = defaultdict(list)
        for question in questions:
            by_type[question.question_type].append(question)

        report = []
        for qtype in sorted(by_type):
            type_questions = by_type[qtype]
            difficulties = [
                stats_by_id[q.id]['difficulty'] for q in type_questions
                if stats_by_id[q.id]['difficulty'] is not None
            ]
            discriminations = [
                stats_by_id[q.id]['discrimination'] for q in type_questions
                if stats_by_id[q.id]['discrimination'] is not None
            ]
            flagged = sum(1 for q in type_questions if q.qa_flags)
            report.append({
                'question_type': qtype,
                'questions': len(type_questions),
                'mean_difficulty': _mean(difficulties),
                'mean_discrimination': _mean(discriminations),
                'pct_flagged': round(100 * flagged / len(type_questions), 1),
            })
        return report

    def _print_report(self, report):
        self.stdout.write('')
        self.stdout.write(f'{"question_type":<38}{"n":>6}{"mean_p":>9}{"mean_d":>9}{"%flagged":>10}')
        for row in report:
            self.stdout.write(
                f'{row["question_type"]:<38}'
                f'{row["questions"]:>6}'
                f'{_fmt(row["mean_difficulty"]):>9}'
                f'{_fmt(row["mean_discrimination"]):>9}'
                f'{row["pct_flagged"]:>9.1f}%'
            )

    # ------------------------------------------------------------------
    # --gradient: delayed-accuracy difficulty gradient (analysis only)
    # ------------------------------------------------------------------

    def _run_gradient(self, word_set):
        answers_qs = UserAnswer.objects.select_related('question')
        if word_set is not None:
            answers_qs = answers_qs.filter(question__word__in=word_set.words.all())
        rows = list(answers_qs.values(
            'user_id', 'question__word_id', 'question__question_type',
            'is_correct', 'answered_at',
        ))

        # Gap to the same user's previous answer for the same word (any
        # question type counts as exposure to the word).
        by_user_word = defaultdict(list)
        for row in rows:
            by_user_word[(row['user_id'], row['question__word_id'])].append(row)

        level_total = defaultdict(int)
        level_correct = defaultdict(int)
        delayed_count = 0
        for pair_rows in by_user_word.values():
            pair_rows.sort(key=lambda r: r['answered_at'])
            previous_at = None
            for row in pair_rows:
                gap = None if previous_at is None else row['answered_at'] - previous_at
                previous_at = row['answered_at']
                qtype = row['question__question_type']
                if qtype not in QUESTION_TYPE_LEVEL:
                    continue
                if gap is None or gap < DELAYED_GAP_MIN:
                    continue
                level = QUESTION_TYPE_LEVEL[qtype]
                delayed_count += 1
                level_total[level] += 1
                if row['is_correct']:
                    level_correct[level] += 1

        self.stdout.write(
            f'Delayed-accuracy difficulty gradient (gap >= {DELAYED_GAP_MIN} since the '
            f"user's previous answer for the same word):"
        )
        self.stdout.write(f'{"level":<8}{"n":>8}{"accuracy":>10}')
        for level in sorted(level_total):
            n = level_total[level]
            self.stdout.write(f'L{level:<7}{n:>8}{level_correct[level] / n:>10.3f}')
        if not level_total:
            self.stdout.write('  (no delayed answers found)')
        self.stdout.write(
            f'\n{delayed_count} delayed answers. Expectation: accuracy should '
            'decrease from L1 to L5; a flat or rising gradient suggests the '
            'higher-level questions are not actually harder.'
        )


def _mean(values):
    return round(sum(values) / len(values), 4) if values else None


def _fmt(value):
    return f'{value:.3f}' if value is not None else '—'
