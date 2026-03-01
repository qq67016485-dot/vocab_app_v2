"""
Dashboard service — provides student progress, roster, and learning patterns.

V2 changes from v1:
- meaning → word FK path
- WordMeaning → Word
- UserMeaningMastery → UserWordProgress
- meaning.term.term_text → word.text
- meaning.definitions.first() → word.definitions.first()
- definition_chinese → Translation model lookup
"""
from datetime import date, timedelta
from collections import defaultdict, Counter
from itertools import groupby
import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q, FloatField, Avg, Case, When
from django.utils import timezone

from users.models import CustomUser, StudentGroup
from vocabulary.models import (
    UserWordProgress, MasteryLevel, UserAnswer, Question,
    Word, WordDefinition, Translation,
)
from vocabulary.constants import QUESTION_TYPE_TO_SKILL_TAG, QUESTION_TYPE_TO_PATTERN

logger = logging.getLogger(__name__)


class DashboardService:
    @staticmethod
    def _get_translation(word, language):
        """Look up the definition translation for a word."""
        defn = word.definitions.first()
        if not defn:
            return ''
        ct = ContentType.objects.get_for_model(WordDefinition)
        try:
            return Translation.objects.get(
                content_type=ct,
                object_id=defn.id,
                field_name='definition_text',
                language=language,
            ).translated_text
        except Translation.DoesNotExist:
            return ''

    @staticmethod
    def get_student_progress(student):
        # Section 1: Mastery Level Breakdown
        mastery_counts_data = list(
            MasteryLevel.objects.annotate(
                word_count=Count(
                    'userwordprogress',
                    filter=Q(userwordprogress__user=student),
                )
            ).values('level_name', 'word_count').order_by('level_id')
        )

        # Section 2: Recent Activity (Last 50 Answers)
        recent_answers_qs = UserAnswer.objects.filter(
            user=student,
        ).select_related(
            'question', 'question__word',
        ).order_by('-answered_at')[:50]

        recent_answers_data = [{
            "id": ua.id,
            "term": ua.question.word.text,
            "is_correct": ua.is_correct,
            "answered_at": ua.answered_at.strftime('%Y-%m-%d %H:%M'),
            "skill_tag": QUESTION_TYPE_TO_SKILL_TAG.get(ua.question.question_type, 'other'),
            "question_text": ua.question.question_text,
            "user_answer": ua.user_answer,
            "correct_answers": ua.question.correct_answers,
        } for ua in recent_answers_qs]

        # Section 3: Practice Statistics by Time Period
        today = date.today()

        def get_stats_for_period(start_date):
            stats = UserAnswer.objects.filter(
                user=student, answered_at__date__gte=start_date,
            ).aggregate(
                total_answered=Count('id'),
                total_correct=Count('id', filter=Q(is_correct=True)),
            )
            stats['total_incorrect'] = stats['total_answered'] - stats['total_correct']
            return stats

        practice_stats_data = {
            "today": get_stats_for_period(today),
            "past_3_days": get_stats_for_period(today - timedelta(days=2)),
            "past_7_days": get_stats_for_period(today - timedelta(days=6)),
        }

        # Section 4: Words with 2+ Consecutive Mistakes
        all_student_answers = UserAnswer.objects.filter(
            user=student,
        ).select_related('question').order_by('question__word_id', '-answered_at')

        consecutive_mistakes_map = {}
        for word_id, answers_group in groupby(
            all_student_answers, key=lambda x: x.question.word_id,
        ):
            answers_list = list(answers_group)
            if len(answers_list) >= 2:
                if not answers_list[0].is_correct and not answers_list[1].is_correct:
                    mistake_types = {
                        QUESTION_TYPE_TO_SKILL_TAG.get(answers_list[0].question.question_type, 'other'),
                        QUESTION_TYPE_TO_SKILL_TAG.get(answers_list[1].question.question_type, 'other'),
                    }
                    consecutive_mistakes_map[word_id] = list(mistake_types)

        consecutive_mistakes_data = []
        if consecutive_mistakes_map:
            word_ids = consecutive_mistakes_map.keys()
            struggle_words = Word.objects.filter(
                id__in=word_ids,
            ).prefetch_related('definitions')

            for word in struggle_words:
                defn = word.definitions.first()
                consecutive_mistakes_data.append({
                    'id': word.id,
                    'term': word.text,
                    'definition': defn.definition_text if defn else '',
                    'skill_tags': consecutive_mistakes_map.get(word.id, []),
                })

        # Section 5: Most Frequent Mistakes
        frequent_mistakes_qs = UserAnswer.objects.filter(
            user=student, is_correct=False,
        ).values(
            'question__word_id',
            'question__word__text',
        ).annotate(
            mistake_count=Count('id'),
        ).order_by('-mistake_count')[:10]

        frequent_mistakes_data = []
        for item in frequent_mistakes_qs:
            word = Word.objects.prefetch_related('definitions').get(
                id=item['question__word_id'],
            )
            defn = word.definitions.first()
            frequent_mistakes_data.append({
                'id': item['question__word_id'],
                'term': item['question__word__text'],
                'definition': defn.definition_text if defn else '',
                'mistake_count': item['mistake_count'],
            })

        return {
            "student_username": student.username,
            "mastery_counts": mastery_counts_data,
            "frequent_mistakes": frequent_mistakes_data,
            "consecutive_mistakes": consecutive_mistakes_data,
            "recent_answers": recent_answers_data,
            "practice_stats": practice_stats_data,
        }

    @staticmethod
    def get_roster_dashboard(teacher, group_id):
        students_queryset = teacher.students.all().order_by('username')
        if group_id and group_id != 'all':
            try:
                group = StudentGroup.objects.get(id=group_id, teacher=teacher)
                students_queryset = group.students.all().order_by('username')
            except (StudentGroup.DoesNotExist, ValueError):
                students_queryset = CustomUser.objects.none()

        student_ids = list(students_queryset.values_list('id', flat=True))

        three_days_ago = timezone.now() - timedelta(days=3)
        activity_stats = UserAnswer.objects.filter(
            user_id__in=student_ids,
            answered_at__gte=three_days_ago,
        ).values('user_id').annotate(
            questions_answered=Count('id'),
            accuracy_percent=(
                Avg(Case(
                    When(is_correct=True, then=1.0),
                    default=0.0,
                    output_field=FloatField(),
                )) * 100
            ),
        )
        activity_map = {
            item['user_id']: {
                'questions_answered': item['questions_answered'],
                'accuracy_percent': round(item['accuracy_percent'] or 0),
            } for item in activity_stats
        }

        challenging_words_qs = UserAnswer.objects.filter(
            user_id__in=student_ids, is_correct=False,
        ).values(
            'user_id', 'question__word__text',
        ).annotate(
            mistake_count=Count('id'),
        ).order_by('user_id', '-mistake_count')

        challenging_words_map = defaultdict(list)
        for item in challenging_words_qs:
            if len(challenging_words_map[item['user_id']]) < 5:
                challenging_words_map[item['user_id']].append(
                    item['question__word__text'],
                )

        skills_qs = UserAnswer.objects.filter(
            user_id__in=student_ids, is_correct=False,
        ).select_related('question')

        skills_map = defaultdict(Counter)
        temp_answer_map = defaultdict(list)
        for answer in skills_qs.order_by('user_id', '-answered_at'):
            if len(temp_answer_map[answer.user_id]) < 30:
                temp_answer_map[answer.user_id].append(answer)

        for user_id, answers in temp_answer_map.items():
            for answer in answers:
                pattern = QUESTION_TYPE_TO_PATTERN.get(
                    answer.question.question_type, 'Other',
                )
                skills_map[user_id][pattern] += 1

        today_date = timezone.now().date()
        due_counts_qs = UserWordProgress.objects.filter(
            user_id__in=student_ids,
            next_review_date__lte=today_date,
            instructional_status='READY',
        ).values('user_id').annotate(due_count=Count('id'))

        due_counts_map = {item['user_id']: item['due_count'] for item in due_counts_qs}

        annotated_students = []
        for student in students_queryset:
            student_skills = skills_map.get(student.id, Counter())
            skills_to_develop = [item[0] for item in student_skills.most_common(5)]

            student.activity_3d = activity_map.get(
                student.id, {'questions_answered': 0, 'accuracy_percent': 0},
            )
            student.snapshot = {
                'challenging_words': challenging_words_map.get(student.id, []),
                'skills_to_develop': skills_to_develop,
                'words_due_for_review': due_counts_map.get(student.id, 0),
            }
            annotated_students.append(student)

        groups_for_dropdown = teacher.student_groups.all()

        return {'groups': groups_for_dropdown, 'roster': annotated_students}

    @staticmethod
    def get_learning_patterns(student):
        recent_incorrect_answers = UserAnswer.objects.filter(
            user=student, is_correct=False,
        ).select_related(
            'question', 'question__word',
        ).order_by('-answered_at')[:30]

        total_analyzed = len(recent_incorrect_answers)
        if total_analyzed == 0:
            return {
                'student_username': student.username,
                'total_analyzed': 0,
                'patterns': [],
                'challenging_words': [],
            }

        pattern_counts = defaultdict(int)
        word_mistake_counts = Counter()
        for answer in recent_incorrect_answers:
            q_type = answer.question.question_type
            pattern_category = QUESTION_TYPE_TO_PATTERN.get(q_type, 'Other')
            pattern_counts[pattern_category] += 1
            word_mistake_counts[answer.question.word_id] += 1

        PATTERN_DESCRIPTIONS = {
            'Definition Recall': "This pattern suggests difficulty recalling the precise meaning of a word.",
            'Context & Nuance': "This pattern suggests you might struggle with how a word is used in a specific sentence.",
            'Synonym & Antonym': "This pattern suggests you might be confusing words with similar or opposite meanings.",
            'Word Forms': "This pattern suggests you might be mixing up different forms of a word (e.g., noun, verb, adjective).",
            'Spelling': "This pattern suggests that small typos or spelling errors are a common issue.",
            'Syntax & Grammar': "This pattern suggests that arranging words in the correct grammatical order is a point to work on.",
            'Collocation & Usage': "This pattern suggests difficulty with words that naturally go together (e.g., 'heavy rain').",
            'Conceptual Association': "This pattern suggests you may have difficulty understanding how a word relates to other concepts.",
            'Other': "These are mistakes that don't fit into a common pattern.",
        }

        patterns_breakdown = [
            {
                'name': name,
                'count': count,
                'percentage': round((count / total_analyzed) * 100),
                'description': PATTERN_DESCRIPTIONS.get(name, ''),
            }
            for name, count in pattern_counts.items()
        ]
        sorted_patterns = sorted(patterns_breakdown, key=lambda x: x['count'], reverse=True)

        most_common_word_ids = [item[0] for item in word_mistake_counts.most_common(3)]
        challenging_words = {
            w.id: w
            for w in Word.objects.filter(
                id__in=most_common_word_ids,
            ).prefetch_related('definitions')
        }

        challenging_words_data = []
        for word_id in most_common_word_ids:
            if word_id in challenging_words:
                word_obj = challenging_words[word_id]

                answers_for_this_word = [
                    ans for ans in recent_incorrect_answers
                    if ans.question.word_id == word_id
                ]
                skill_tags_for_word = list(set(
                    QUESTION_TYPE_TO_SKILL_TAG.get(ans.question.question_type, 'other')
                    for ans in answers_for_this_word
                ))

                defn = word_obj.definitions.first()
                translation = DashboardService._get_translation(
                    word_obj, student.native_language,
                )

                challenging_words_data.append({
                    'term': word_obj.text,
                    'definition': defn.definition_text if defn else '',
                    'mistake_count': word_mistake_counts[word_id],
                    'skill_tags': skill_tags_for_word,
                    'translation': translation,
                })

        return {
            'student_username': student.username,
            'total_analyzed': total_analyzed,
            'patterns': sorted_patterns,
            'challenging_words': challenging_words_data,
        }
