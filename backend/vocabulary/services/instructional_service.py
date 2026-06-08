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
    GraphicNovel, GraphicNovelPageAudio,
)
from vocabulary.utils import get_definition_translations

logger = logging.getLogger(__name__)


class InstructionalService:
    @staticmethod
    def get_pack_data(user, pack_id):
        """Fetch pack with items, primer content, Lexile-matched story, cloze items.
        Validates student access via assignment."""
        try:
            pack = WordPack.objects.select_related('word_set').prefetch_related(
                Prefetch('items', queryset=WordPackItem.objects.select_related(
                    'word', 'word__primer_content',
                ).order_by('order')),
                'cloze_items__word',
                'stories',
                'graphic_novels__pages',
                'graphic_novels__pages__audio',
            ).get(id=pack_id)
        except WordPack.DoesNotExist:
            raise ValueError("Pack not found.")

        # Validate access: student must be assigned this word set
        if not StudentWordSetAssignment.objects.filter(
            user=user, word_set=pack.word_set,
        ).exists():
            raise PermissionError("You are not assigned to this word set.")

        # Build primer cards
        primer_cards = []
        for item in pack.items.all():
            word = item.word
            primer = getattr(word, 'primer_content', None)
            _translations = get_definition_translations(
                word, user.native_language,
                fields=('definition_text', 'example_sentence'),
            )
            definition_translation = _translations['definition_text']
            example_translation = _translations['example_sentence']
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

        # Select the new graphic novel format first; fall back to legacy stories.
        graphic_novel = pack.graphic_novels.filter(
            channel=GraphicNovel.Channel.FIVE_PAGE,
        ).first()
        stories = list(pack.stories.all())
        story = None
        if graphic_novel:
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
            story_data = {
                'type': 'graphic_novel',
                'title': graphic_novel.title,
                'reading_level': graphic_novel.reading_level,
                'pages': pages_data,
            }
        elif stories:
            user_mid = (user.lexile_min + user.lexile_max) / 2
            story = min(stories, key=lambda s: abs(s.reading_level - user_mid))
            story_data = {
                'type': 'micro_story',
                'story_text': story.story_text,
                'reading_level': story.reading_level,
            }
        else:
            story_data = None

        # Cloze items
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
