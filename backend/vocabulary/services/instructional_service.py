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
from datetime import date
import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models import Prefetch

from vocabulary.models import (
    WordPack, WordPackItem, PrimerCardContent, MicroStory, ClozeItem,
    StudentPackCompletion, StudentWordSetAssignment, UserWordProgress,
    Translation, WordDefinition, GeneratedImage,
)

logger = logging.getLogger(__name__)


class InstructionalService:
    @staticmethod
    def _get_translations_for_primer(word, language):
        """Look up definition and example translations for a word's primer content."""
        defn = word.definitions.first()
        definition_translation = ''
        example_translation = ''

        if defn:
            ct = ContentType.objects.get_for_model(WordDefinition)
            translations = Translation.objects.filter(
                content_type=ct,
                object_id=defn.id,
                language=language,
            )
            for t in translations:
                if t.field_name == 'definition_text':
                    definition_translation = t.translated_text
                elif t.field_name == 'example_sentence':
                    example_translation = t.translated_text

        return definition_translation, example_translation

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
            ).get(id=pack_id)
        except WordPack.DoesNotExist:
            raise ValueError("Pack not found.")

        # Validate access: student must be assigned this word set
        if not StudentWordSetAssignment.objects.filter(
            user=user, word_set=pack.word_set,
        ).exists():
            raise PermissionError("You are not assigned to this word set.")

        # Pre-fetch approved images for all words in this pack
        word_ids = [item.word_id for item in pack.items.all()]
        approved_images = {}
        for img in GeneratedImage.objects.filter(
            word_id__in=word_ids,
            status=GeneratedImage.Status.APPROVED,
        ).order_by('-created_at'):
            # Keep only the most recent approved image per word
            if img.word_id not in approved_images and img.image:
                approved_images[img.word_id] = img.image.url

        # Build primer cards
        primer_cards = []
        for item in pack.items.all():
            word = item.word
            primer = getattr(word, 'primer_content', None)
            definition_translation, example_translation = (
                InstructionalService._get_translations_for_primer(word, user.native_language)
            )
            primer_cards.append({
                'word_id': word.id,
                'term_text': word.text,
                'syllable_text': primer.syllable_text if primer else word.text,
                'image_url': approved_images.get(word.id, ''),
                'audio_url': primer.audio_url if primer else '',
                'kid_friendly_definition': primer.kid_friendly_definition if primer else '',
                'example_sentence': primer.example_sentence if primer else '',
                'definition_translation': definition_translation,
                'example_translation': example_translation,
            })

        # Select Lexile-matched story
        stories = list(pack.stories.all())
        story = None
        if stories:
            user_mid = (user.lexile_min + user.lexile_max) / 2
            story = min(stories, key=lambda s: abs(s.reading_level - user_mid))

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
            'story': {
                'story_text': story.story_text,
                'reading_level': story.reading_level,
            } if story else None,
            'cloze_items': cloze_items,
        }

    @staticmethod
    def complete_pack(user, pack_id):
        """Mark pack done, flip words to READY, set next_review_date = today."""
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
            next_review_date=date.today(),
        )

        return True
