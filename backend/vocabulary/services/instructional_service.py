"""
Instructional service — serves pack data for the student learning flow.

V2 changes from v1:
- meaning → word FK path
- meaning.term.term_text → word.text
- meaning.primer_content → word.primer_content
- definition_translation/example_translation → Translation model lookup by student language
- UserMeaningMastery → UserWordProgress
- meaning_id → word_id
"""
import logging

from django.db.models import Prefetch
from django.utils import timezone

from vocabulary.models import (
    WordPack, WordPackItem, PrimerCardContent, MicroStory, ClozeItem,
    StudentPackCompletion, StudentWordSetAssignment, UserWordProgress,
    GraphicNovel, GraphicNovelPage, GraphicNovelPageAudio, Infographic,
)
from vocabulary.utils import get_definition_translations_for_words

logger = logging.getLogger(__name__)


class InstructionalService:
    @staticmethod
    def get_pack_data(user, pack_id):
        """Fetch pack with items, primer content, Lexile-matched story, cloze items.
        Validates student access via assignment."""
        try:
            # Every prefetch below is shaped to be consumed as-is: calling
            # .filter()/.select_related() on a prefetched manager later would
            # bypass the cache and re-query, so the filtering happens here.
            selected_novels = GraphicNovel.objects.filter(
                is_selected=True,
            ).prefetch_related(
                Prefetch('pages', queryset=GraphicNovelPage.objects.select_related('audio')),
            )
            promoted_cloze = ClozeItem.objects.filter(
                novel__isnull=True, infographic__isnull=True,
            )
            pack = WordPack.objects.select_related('word_set').prefetch_related(
                Prefetch('items', queryset=WordPackItem.objects.select_related(
                    'word', 'word__primer_content',
                ).order_by('order')),
                Prefetch('cloze_items', queryset=promoted_cloze),
                'stories',
                Prefetch('graphic_novels', queryset=selected_novels),
                Prefetch('infographics', queryset=Infographic.objects.filter(is_selected=True)),
            ).get(id=pack_id)
        except WordPack.DoesNotExist:
            raise ValueError("Pack not found.")

        # Validate access: student must be assigned this word set. The assignment
        # also carries which content type (graphic novel vs infographic) the
        # teacher chose for this student.
        assignment = StudentWordSetAssignment.objects.filter(
            user=user, word_set=pack.word_set,
        ).first()
        if assignment is None:
            raise PermissionError("You are not assigned to this word set.")
        content_type = assignment.content_type

        # Build primer cards (translations batched: 2 queries for the pack).
        items = list(pack.items.all())
        translations_by_word = get_definition_translations_for_words(
            [item.word for item in items], user.native_language,
            fields=('definition_text', 'example_sentence'),
        )
        primer_cards = []
        for item in items:
            word = item.word
            primer = getattr(word, 'primer_content', None)
            _translations = translations_by_word.get(word.id, {})
            definition_translation = _translations.get('definition_text', '')
            example_translation = _translations.get('example_sentence', '')
            primer_cards.append({
                'word_id': word.id,
                'term_text': word.text,
                'part_of_speech': word.part_of_speech,
                'syllable_text': primer.syllable_text if primer else word.text,
                'audio_url': primer.audio_url if primer else '',
                'kid_friendly_definition': primer.kid_friendly_definition if primer else '',
                'example_sentence': primer.example_sentence if primer else '',
                'definition_translation': definition_translation,
                'example_translation': example_translation,
            })

        # Pick the published content for the student's chosen content type. Until
        # an admin selects a candidate, none is_selected and story_data stays None
        # (pack reads as not-yet-published). If the chosen type wasn't generated /
        # selected, fall back to whatever else is published, then legacy stories.
        # (The prefetched managers already contain only is_selected candidates.)
        graphic_novel = next(iter(pack.graphic_novels.all()), None)
        infographic = next(iter(pack.infographics.all()), None)
        stories = list(pack.stories.all())

        wants_infographic = (
            content_type == StudentWordSetAssignment.ContentType.INFOGRAPHIC
        )
        if wants_infographic:
            preference = [infographic, graphic_novel]
        else:
            preference = [graphic_novel, infographic]

        story_data = None
        for choice in preference:
            if choice is None:
                continue
            if choice is infographic:
                story_data = InstructionalService._infographic_story_data(infographic)
            else:
                story_data = InstructionalService._graphic_novel_story_data(graphic_novel)
            break

        if story_data is None and stories:
            user_mid = (user.lexile_min + user.lexile_max) / 2
            story = min(stories, key=lambda s: abs(s.reading_level - user_mid))
            story_data = {
                'type': 'micro_story',
                'story_text': story.story_text,
                'reading_level': story.reading_level,
            }

        # Cloze items — only the promoted set (both novel and infographic NULL) is
        # student-facing; staged candidate cloze (novel=<id> or infographic=<id>) is
        # excluded until promoted. The prefetch above already applied that filter.
        cloze_items = [{
            'id': ci.id,
            'sentence_text': ci.sentence_text,
            'correct_answer': ci.correct_answer,
            'distractors': ci.distractors,
            'order': ci.order,
        } for ci in pack.cloze_items.all()]

        return {
            'pack_id': pack.id,
            'label': pack.label,
            'primer_cards': primer_cards,
            'story': story_data,
            'cloze_items': cloze_items,
        }

    @staticmethod
    def _graphic_novel_story_data(graphic_novel):
        pages_data = []
        for page in graphic_novel.pages.all():
            audio = getattr(page, 'audio', None)
            audio_url = ''
            if (audio and audio.student_audio
                    and audio.status == GraphicNovelPageAudio.Status.COMPLETED):
                audio_url = audio.student_audio.url
            pages_data.append({
                'page_number': page.page_number,
                'image_url': page.student_image.url if page.student_image else '',
                'audio_url': audio_url,
                'panel_count': page.panel_count,
                'layout_description': page.layout_description,
                'panel_descriptions': page.panel_descriptions,
                'vocab_words': page.vocab_words_used,
            })
        return {
            'type': 'graphic_novel',
            'title': graphic_novel.title,
            'reading_level': graphic_novel.reading_level,
            'pages': pages_data,
        }

    @staticmethod
    def _infographic_story_data(infographic):
        content = infographic.content or {}
        return {
            'type': 'infographic',
            'title': infographic.title,
            'reading_level': infographic.reading_level,
            'intro_text': infographic.intro_text,
            'image_url': infographic.student_image.url if infographic.student_image else '',
            'big_idea': content.get('big_idea', ''),
            'layout_mode': content.get('layout_mode', ''),
            'scene_description': content.get('scene_description', '') or content.get('theme', ''),
            'scene_elements': content.get('scene_elements', []),
            'entries': content.get('entries', []),
        }

    @staticmethod
    def complete_pack(user, pack_id):
        """Mark pack done, flip words to READY, set next_review_at = now."""
        try:
            pack = WordPack.objects.prefetch_related('items__word').get(id=pack_id)
        except WordPack.DoesNotExist:
            raise ValueError("Pack not found.")

        if not StudentWordSetAssignment.objects.filter(
            user=user, word_set=pack.word_set,
        ).exists():
            raise PermissionError("You are not assigned to this word set.")

        # Create completion record (idempotent)
        StudentPackCompletion.objects.get_or_create(user=user, pack=pack)

        # Flip instructional_status to READY for all words in this pack
        word_ids = pack.items.values_list('word_id', flat=True)
        UserWordProgress.objects.filter(
            user=user,
            word_id__in=word_ids,
            instructional_status='PENDING',
        ).update(
            instructional_status='READY',
            next_review_at=timezone.now(),
        )

        return True
