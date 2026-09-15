"""
Assignment service — assigns word sets to students, initializes mastery.

V2 changes from v1:
- meaning → word FK path
- UserMeaningMastery → UserWordProgress
- Removed all BKT state creation (KnowledgeComponent, UserKnowledgeComponentState)
- meaning_id → word_id in WordPackItem lookups
"""
import logging

from django.db import transaction
from django.utils import timezone

from users.models import StudentGroup, CustomUser
from vocabulary.models import (
    MasteryLevel, UserWordProgress,
    StudentWordSetAssignment, StudentPackCompletion, WordPackItem,
)

logger = logging.getLogger(__name__)


class AssignmentService:
    @staticmethod
    @transaction.atomic
    def assign_word_set(teacher, word_set, student_ids, group_ids, content_type=None):
        # Validate the requested content type; default to graphic novel.
        valid_types = set(StudentWordSetAssignment.ContentType.values)
        if content_type not in valid_types:
            content_type = StudentWordSetAssignment.ContentType.GRAPHIC_NOVEL

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

        words_in_set = list(word_set.words.all())

        if not words_in_set:
            return 0, students

        # Determine which words are in packs (should get PENDING status)
        words_in_packs = set(
            WordPackItem.objects.filter(
                pack__word_set=word_set,
            ).values_list('word_id', flat=True)
        )

        for student in students:
            # Create or update the assignment record, persisting the chosen
            # content type (graphic novel vs infographic) on every (re)assign.
            assignment, created = StudentWordSetAssignment.objects.get_or_create(
                user=student,
                word_set=word_set,
                defaults={'assigned_by': teacher, 'content_type': content_type},
            )
            if not created and assignment.content_type != content_type:
                assignment.content_type = content_type
                assignment.save(update_fields=['content_type'])

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

            # Fetch this student's existing progress rows in one query instead
            # of a per-word get_or_create (~students × words queries before).
            existing_progress = {
                progress.word_id: progress
                for progress in UserWordProgress.objects.filter(
                    user=student,
                    word_id__in=[word.id for word in words_in_set],
                )
            }

            new_progress_rows = []
            reset_progress_ids = []
            for word in words_in_set:
                # Words in packs get PENDING; words not in packs get READY
                # But words in already-completed packs stay READY
                if word.id in words_in_completed_packs:
                    inst_status = 'READY'
                elif word.id in words_in_packs:
                    inst_status = 'PENDING'
                else:
                    inst_status = 'READY'

                mastery = existing_progress.get(word.id)
                if mastery is None:
                    new_progress_rows.append(UserWordProgress(
                        user=student,
                        word=word,
                        level=starting_level,
                        next_review_at=timezone.now(),
                        instructional_status=inst_status,
                    ))
                # If record exists and word is in an uncompleted pack, reset to PENDING
                elif word.id in words_in_packs \
                        and word.id not in words_in_completed_packs \
                        and mastery.instructional_status == 'READY':
                    reset_progress_ids.append(mastery.id)

            # ignore_conflicts: unique_together (user, word) means a concurrent
            # assign of the same set is a silent no-op rather than an error.
            UserWordProgress.objects.bulk_create(
                new_progress_rows, ignore_conflicts=True,
            )
            if reset_progress_ids:
                UserWordProgress.objects.filter(id__in=reset_progress_ids).update(
                    instructional_status='PENDING',
                )

        return students.count(), students
