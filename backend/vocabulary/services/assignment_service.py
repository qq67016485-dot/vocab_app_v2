"""
Assignment service — assigns word sets to students, initializes mastery.

V2 changes from v1:
- meaning → word FK path
- UserMeaningMastery → UserWordProgress
- Removed all BKT state creation (KnowledgeComponent, UserKnowledgeComponentState)
- meaning_id → word_id in WordPackItem lookups
"""
from datetime import date
import logging

from users.models import StudentGroup, CustomUser
from vocabulary.models import (
    MasteryLevel, UserWordProgress,
    StudentWordSetAssignment, StudentPackCompletion, WordPackItem,
)

logger = logging.getLogger(__name__)


class AssignmentService:
    @staticmethod
    def assign_word_set(teacher, word_set, student_ids, group_ids):
        final_student_ids = set(student_ids)

        if group_ids:
            groups_to_assign = StudentGroup.objects.filter(
                id__in=group_ids,
                teacher=teacher,
            )
            for group in groups_to_assign:
                for student_id in group.students.values_list('id', flat=True):
                    final_student_ids.add(student_id)

        if not final_student_ids:
            raise ValueError('No valid students or groups were selected.')

        students = CustomUser.objects.filter(
            id__in=list(final_student_ids),
            teachers=teacher,
        )
        starting_level = MasteryLevel.objects.get(level_id=1)

        words_in_set = word_set.words.all()

        if not words_in_set.exists():
            return 0, students

        # Determine which words are in packs (should get PENDING status)
        words_in_packs = set(
            WordPackItem.objects.filter(
                pack__word_set=word_set,
            ).values_list('word_id', flat=True)
        )

        for student in students:
            # Create assignment record
            StudentWordSetAssignment.objects.get_or_create(
                user=student,
                word_set=word_set,
                defaults={'assigned_by': teacher},
            )

            # Find packs this student has already completed — don't reset those words
            completed_pack_ids = set(
                StudentPackCompletion.objects.filter(
                    user=student,
                    pack__word_set=word_set,
                ).values_list('pack_id', flat=True)
            )
            words_in_completed_packs = set(
                WordPackItem.objects.filter(
                    pack_id__in=completed_pack_ids,
                ).values_list('word_id', flat=True)
            ) if completed_pack_ids else set()

            for word in words_in_set:
                # Words in packs get PENDING; words not in packs get READY
                # But words in already-completed packs stay READY
                if word.id in words_in_completed_packs:
                    inst_status = 'READY'
                elif word.id in words_in_packs:
                    inst_status = 'PENDING'
                else:
                    inst_status = 'READY'

                mastery, created = UserWordProgress.objects.get_or_create(
                    user=student,
                    word=word,
                    defaults={
                        'level': starting_level,
                        'next_review_date': date.today(),
                        'instructional_status': inst_status,
                    },
                )
                # If record exists and word is in an uncompleted pack, reset to PENDING
                if not created and word.id in words_in_packs \
                        and word.id not in words_in_completed_packs \
                        and mastery.instructional_status == 'READY':
                    mastery.instructional_status = 'PENDING'
                    mastery.save(update_fields=['instructional_status'])

        return students.count(), students
