"""Tests for infographic candidate selection, cloze promotion, and serving.

Covers the infographic counterpart of the graphic novel selection flow, the
shared active-cloze read filter (both FKs NULL), per-assignment content-type
serving in InstructionalService, and the design+cloze generation engine.
"""
from unittest.mock import patch

import pytest

from vocabulary.models import ClozeItem, Infographic, StudentWordSetAssignment
from vocabulary.services.infographic_selection_service import (
    select_infographic_candidate,
)
from vocabulary.services.graphic_novel_selection_service import (
    select_graphic_novel_candidate,
)
from vocabulary.services.instructional_service import InstructionalService
from vocabulary.services.generation.step_infographic import (
    restart_infographic_from_substep, build_infographic_image_prompt,
    _clean_infographic_title,
)
from tests.factories import (
    GraphicNovelFactory, GraphicNovelPageFactory, InfographicFactory,
    WordPackFactory, WordFactory, WordPackItemFactory, StudentUserFactory,
    GenerationJobFactory,
)


IG_DESIGN_RESPONSE = {
    'title': 'Light Words',
    'intro_text': 'The bright summer sun lit the woods as the children set out to discover a hidden cave.',
    'big_idea': 'How light travels from the sun to what we discover.',
    'layout_mode': 'panorama',
    'visual_structure': 'journey_path',
    'scene_description': 'A winding path from a bright sun to explorers discovering a cave.',
    'color_palette': 'Blues and yellows.',
    'reading_level': 600,
    'scene_elements': [
        {
            'label': 'The Sun',
            'caption': 'High in the sky, the summer sun grows so bright that the explorers shade their eyes.',
            'vocab_terms': ['bright'],
            'illustration': 'A glowing sun over hills.',
        },
        {
            'label': 'The Cave',
            'caption': 'Deep in the woods the children discover a hidden cave no one had ever entered.',
            'vocab_terms': ['discover'],
            'illustration': 'Kids with lanterns at a cave mouth.',
        },
    ],
    'entries': [
        {
            'term': 'bright', 'part_of_speech': 'adjective',
            'kid_friendly_definition': 'giving off a lot of light',
            'example_sentence': 'The lamp was bright.', 'visual_idea': 'A lightbulb.',
        },
        {
            'term': 'discover', 'part_of_speech': 'verb',
            'kid_friendly_definition': 'to find something new',
            'example_sentence': 'We discover stars.', 'visual_idea': 'A telescope.',
        },
    ],
}
IG_CLOZE_RESPONSE = {
    'cloze_items': [
        {'term': 'bright', 'sentence_text': 'The sun is _______.',
         'correct_answer': 'bright', 'distractors': ['dark', 'cold']},
        {'term': 'discover', 'sentence_text': 'They _______ a cave.',
         'correct_answer': 'discover', 'distractors': ['lose', 'hide']},
    ],
}


def _make_ig_candidate(pack, idx, word, *, selected=False):
    ig = InfographicFactory(
        pack=pack, candidate_index=idx, is_selected=selected,
        title=f'Infographic {idx}',
    )
    ClozeItem.objects.create(
        pack=pack, infographic=ig, word=word,
        sentence_text=f'The _______ thing happened in poster {idx}.',
        correct_answer=word.text, distractors=['a', 'b'], order=0,
    )
    return ig


@pytest.mark.django_db
class TestSelectInfographicCandidate:
    def test_selects_candidate_and_clears_siblings(self):
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)
        c0 = _make_ig_candidate(pack, 0, word)
        c1 = _make_ig_candidate(pack, 1, word)
        c2 = _make_ig_candidate(pack, 2, word)

        select_infographic_candidate(c1.id)

        c0.refresh_from_db(); c1.refresh_from_db(); c2.refresh_from_db()
        assert c1.is_selected is True
        assert c0.is_selected is False
        assert c2.is_selected is False

    def test_promotes_selected_candidate_cloze(self):
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)
        _make_ig_candidate(pack, 0, word)
        c1 = _make_ig_candidate(pack, 1, word)

        select_infographic_candidate(c1.id)

        promoted = ClozeItem.objects.filter(
            pack=pack, novel__isnull=True, infographic__isnull=True,
        )
        assert promoted.count() == 1
        assert promoted.first().sentence_text == 'The _______ thing happened in poster 1.'
        # Staged candidate cloze is left intact.
        assert ClozeItem.objects.filter(pack=pack, infographic=c1).count() == 1

    def test_idempotent_reselect(self):
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)
        c0 = _make_ig_candidate(pack, 0, word)

        select_infographic_candidate(c0.id)
        select_infographic_candidate(c0.id)

        assert ClozeItem.objects.filter(
            pack=pack, novel__isnull=True, infographic__isnull=True,
        ).count() == 1


@pytest.mark.django_db
class TestSharedActiveClozeFilter:
    def test_staged_infographic_cloze_is_not_active(self):
        """A staged infographic cloze (novel=None, infographic=<id>) must NOT count
        as active — it would otherwise leak to students through the novel__isnull
        filter."""
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)
        ig = InfographicFactory(pack=pack, candidate_index=0)
        ClozeItem.objects.create(
            pack=pack, infographic=ig, word=word,
            sentence_text='Staged _______ row.', correct_answer='bright',
            distractors=['a', 'b'], order=0,
        )

        active = ClozeItem.objects.filter(
            pack=pack, novel__isnull=True, infographic__isnull=True,
        )
        assert active.count() == 0
        # The legacy filter (novel only) would have wrongly counted it.
        assert ClozeItem.objects.filter(pack=pack, novel__isnull=True).count() == 1

    def test_selecting_infographic_replaces_graphic_novel_active_cloze(self):
        """The active set is shared: publishing an infographic after a graphic
        novel replaces the active cloze (last published wins)."""
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)

        novel = GraphicNovelFactory(pack=pack, candidate_index=0, is_selected=False)
        ClozeItem.objects.create(
            pack=pack, novel=novel, word=word,
            sentence_text='Novel _______ row.', correct_answer='bright',
            distractors=['a', 'b'], order=0,
        )
        ig = _make_ig_candidate(pack, 0, word)

        select_graphic_novel_candidate(novel.id)
        assert ClozeItem.objects.filter(
            pack=pack, novel__isnull=True, infographic__isnull=True,
        ).first().sentence_text == 'Novel _______ row.'

        select_infographic_candidate(ig.id)
        active = ClozeItem.objects.filter(
            pack=pack, novel__isnull=True, infographic__isnull=True,
        )
        assert active.count() == 1
        assert active.first().sentence_text == 'The _______ thing happened in poster 0.'


@pytest.mark.django_db
class TestServingByContentType:
    def _setup(self, content_type):
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)

        novel = GraphicNovelFactory(pack=pack, candidate_index=0, is_selected=True)
        GraphicNovelPageFactory(novel=novel, page_number=1)
        ig = InfographicFactory(pack=pack, candidate_index=0, is_selected=True)

        student = StudentUserFactory()
        StudentWordSetAssignment.objects.create(
            user=student, word_set=pack.word_set, assigned_by=student,
            content_type=content_type,
        )
        return student, pack

    def test_serves_graphic_novel(self):
        student, pack = self._setup(
            StudentWordSetAssignment.ContentType.GRAPHIC_NOVEL,
        )
        data = InstructionalService.get_pack_data(student, pack.id)
        assert data['story']['type'] == 'graphic_novel'

    def test_serves_infographic(self):
        student, pack = self._setup(
            StudentWordSetAssignment.ContentType.INFOGRAPHIC,
        )
        data = InstructionalService.get_pack_data(student, pack.id)
        assert data['story']['type'] == 'infographic'
        assert 'intro_text' in data['story']
        assert 'entries' in data['story']

    def test_infographic_request_falls_back_to_graphic_novel(self):
        """If infographic wasn't published, an infographic assignment still sees
        the published graphic novel rather than nothing."""
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)
        novel = GraphicNovelFactory(pack=pack, candidate_index=0, is_selected=True)
        GraphicNovelPageFactory(novel=novel, page_number=1)

        student = StudentUserFactory()
        StudentWordSetAssignment.objects.create(
            user=student, word_set=pack.word_set, assigned_by=student,
            content_type=StudentWordSetAssignment.ContentType.INFOGRAPHIC,
        )
        data = InstructionalService.get_pack_data(student, pack.id)
        assert data['story']['type'] == 'graphic_novel'


@pytest.mark.django_db
class TestInfographicGeneration:
    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_design_and_cloze_create_infographic(self, mock_load, mock_gemini):
        mock_load.return_value = 'Infographic template'
        mock_gemini.side_effect = [IG_DESIGN_RESPONSE, IG_CLOZE_RESPONSE]

        job = GenerationJobFactory(
            input_words=['bright', 'discover'], content_types=['infographic'],
        )
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPackFactory(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItemFactory(pack=pack, word=word1, order=0)
        WordPackItemFactory(pack=pack, word=word2, order=1)
        words_data = [
            {'term': 'bright', 'part_of_speech': 'adjective', 'definition': 'full of light'},
            {'term': 'discover', 'part_of_speech': 'verb', 'definition': 'to find'},
        ]

        ig = restart_infographic_from_substep(job, pack.id, 'design', words_data, candidate_index=0)

        assert ig.title == 'Light Words'
        assert ig.intro_text == (
            'The bright summer sun lit the woods as the children set out to discover a hidden cave.'
        )
        assert ig.content['big_idea'] == 'How light travels from the sun to what we discover.'
        assert ig.content['layout_mode'] == 'panorama'
        assert ig.content['visual_structure'] == 'journey_path'
        assert len(ig.content['scene_elements']) == 2
        assert len(ig.content['entries']) == 2
        # Cloze is staged against the infographic (not yet active).
        assert ClozeItem.objects.filter(pack=pack, infographic=ig).count() == 2
        assert ClozeItem.objects.filter(
            pack=pack, novel__isnull=True, infographic__isnull=True,
        ).count() == 0
        assert mock_gemini.call_count == 2

    def test_design_persists_cleaned_title(self):
        """A title carrying a generic ': A Vocabulary Guide' subtitle is stripped
        to the bare topic on persist."""
        with patch('vocabulary.services.llm_service.call_gemini') as mock_gemini, \
             patch('vocabulary.services.llm_service.load_prompt_template') as mock_load:
            mock_load.return_value = 'Infographic template'
            mock_gemini.side_effect = [
                {**IG_DESIGN_RESPONSE, 'title': 'The Global Journey of Coffee: A Vocabulary Guide'},
                IG_CLOZE_RESPONSE,
            ]
            job = GenerationJobFactory(
                input_words=['bright', 'discover'], content_types=['infographic'],
            )
            word1 = WordFactory(text='bright')
            word2 = WordFactory(text='discover')
            pack = WordPackFactory(word_set=job.word_set, label='Pack 1', order=0)
            WordPackItemFactory(pack=pack, word=word1, order=0)
            WordPackItemFactory(pack=pack, word=word2, order=1)
            words_data = [
                {'term': 'bright', 'part_of_speech': 'adjective', 'definition': 'full of light'},
                {'term': 'discover', 'part_of_speech': 'verb', 'definition': 'to find'},
            ]
            ig = restart_infographic_from_substep(job, pack.id, 'design', words_data, candidate_index=0)
            assert ig.title == 'The Global Journey of Coffee'

    def test_image_prompt_includes_entries(self):
        pack = WordPackFactory()
        ig = InfographicFactory(pack=pack)
        prompt = build_infographic_image_prompt(ig)
        assert ig.title in prompt
        assert 'bright' in prompt

    def test_image_prompt_branches_on_layout_mode(self):
        """Panorama gets spine language; gallery gets framing-device language."""
        pack = WordPackFactory()
        pano = InfographicFactory(pack=pack, candidate_index=0)
        pano.content = {**pano.content, 'layout_mode': 'panorama'}
        gallery = InfographicFactory(pack=pack, candidate_index=1)
        gallery.content = {**gallery.content, 'layout_mode': 'gallery'}

        pano_prompt = build_infographic_image_prompt(pano)
        gallery_prompt = build_infographic_image_prompt(gallery)

        assert 'VISUAL SPINE' in pano_prompt
        assert 'FRAMING DEVICE' not in pano_prompt
        assert 'FRAMING DEVICE' in gallery_prompt
        assert 'VISUAL SPINE' not in gallery_prompt

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_rejects_glossary_format_caption(self, mock_load, mock_gemini):
        """A 'word: definition' caption is the flashcard format we must reject."""
        mock_load.return_value = 'Infographic template'
        bad_design = {
            **IG_DESIGN_RESPONSE,
            'scene_elements': [
                {
                    'label': 'The Sun',
                    'caption': 'bright: giving off a lot of light.',
                    'vocab_terms': ['bright'],
                    'illustration': 'A glowing sun.',
                },
                {
                    'label': 'The Cave',
                    'caption': 'The kids discover a cave.',
                    'vocab_terms': ['discover'],
                    'illustration': 'A cave.',
                },
            ],
        }
        # Design retries internally (max_retries=2) so all 3 attempts return the
        # bad caption — the substep must ultimately fail rather than persist it.
        mock_gemini.side_effect = [bad_design, bad_design, bad_design]

        job = GenerationJobFactory(input_words=['bright', 'discover'], content_types=['infographic'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPackFactory(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItemFactory(pack=pack, word=word1, order=0)
        WordPackItemFactory(pack=pack, word=word2, order=1)
        words_data = [
            {'term': 'bright', 'part_of_speech': 'adjective', 'definition': 'full of light'},
            {'term': 'discover', 'part_of_speech': 'verb', 'definition': 'to find'},
        ]

        with pytest.raises(ValueError, match='definition format'):
            restart_infographic_from_substep(job, pack.id, 'design', words_data, candidate_index=0)
        assert not Infographic.objects.filter(pack=pack).exists()

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_rejects_intro_text_missing_a_target_word(self, mock_load, mock_gemini):
        """intro_text must use every target word so students meet them by reading."""
        mock_load.return_value = 'Infographic template'
        # intro_text mentions 'bright' but not 'discover'.
        bad_design = {
            **IG_DESIGN_RESPONSE,
            'intro_text': 'The bright summer sun lit up the whole forest.',
        }
        mock_gemini.side_effect = [bad_design, bad_design, bad_design]

        job = GenerationJobFactory(input_words=['bright', 'discover'], content_types=['infographic'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPackFactory(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItemFactory(pack=pack, word=word1, order=0)
        WordPackItemFactory(pack=pack, word=word2, order=1)
        words_data = [
            {'term': 'bright', 'part_of_speech': 'adjective', 'definition': 'full of light'},
            {'term': 'discover', 'part_of_speech': 'verb', 'definition': 'to find'},
        ]

        with pytest.raises(ValueError, match='intro_text must use every target word'):
            restart_infographic_from_substep(job, pack.id, 'design', words_data, candidate_index=0)
        assert not Infographic.objects.filter(pack=pack).exists()


class TestCleanInfographicTitle:
    def test_strips_generic_vocabulary_guide_subtitle(self):
        assert _clean_infographic_title(
            'The Global Journey of Coffee: A Vocabulary Guide'
        ) == 'The Global Journey of Coffee'

    def test_strips_dash_separated_subtitle(self):
        assert _clean_infographic_title(
            'How Plants Grow — Vocabulary Words'
        ) == 'How Plants Grow'

    def test_strips_bare_vocabulary_subtitle(self):
        assert _clean_infographic_title('Ocean Life: Vocabulary') == 'Ocean Life'

    def test_keeps_meaningful_subtitle(self):
        assert _clean_infographic_title(
            'The Solar System: A Tour of the Planets'
        ) == 'The Solar System: A Tour of the Planets'

    def test_keeps_plain_title(self):
        assert _clean_infographic_title('The Water Cycle') == 'The Water Cycle'

    def test_leaves_title_that_is_only_a_subtitle(self):
        # Nothing meaningful before the tag — keep the original rather than empty.
        assert _clean_infographic_title('A Vocabulary Guide') == 'A Vocabulary Guide'

    def test_handles_none_and_blank(self):
        assert _clean_infographic_title(None) == ''
        assert _clean_infographic_title('   ') == ''
