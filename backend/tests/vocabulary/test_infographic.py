"""Tests for infographic candidate selection, cloze promotion, and serving.

Covers the infographic counterpart of the graphic novel selection flow, the
shared active-cloze read filter (both FKs NULL), per-assignment content-type
serving in InstructionalService, and the design+cloze generation engine.
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework.test import APIClient

from vocabulary.models import (
    ClozeItem, GenerationJob, GenerationJobLog, Infographic,
    StudentWordSetAssignment,
)
from vocabulary.services.infographic_selection_service import (
    select_infographic_candidate,
)
from vocabulary.services.graphic_novel_selection_service import (
    select_graphic_novel_candidate,
)
from vocabulary.services.instructional_service import InstructionalService
from vocabulary.services.generation.constants import INFOGRAPHIC_SUBSTEPS
from vocabulary.services.generation.graphic_novel_validators import (
    _validate_graphic_novel_cloze_result,
)
from vocabulary.services.generation.orchestrator import (
    _clear_testing_outputs_for_step,
)
from vocabulary.services.generation.step_infographic import (
    restart_infographic_from_substep, build_infographic_image_prompt,
    _clean_infographic_title, _persist_candidate_infographic,
    _run_infographic_substep, _step_infographic_design,
    _term_in_text, _validate_infographic_design_result,
)
from tests.factories import (
    AdminUserFactory, GraphicNovelFactory, GraphicNovelPageFactory,
    InfographicFactory, WordPackFactory, WordFactory, WordPackItemFactory,
    StudentUserFactory, GenerationJobFactory,
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
    """Build a COMPLETE infographic candidate (selectable): poster image +
    staged cloze."""
    ig = InfographicFactory(
        pack=pack, candidate_index=idx, is_selected=selected,
        title=f'Infographic {idx}',
        image=f'infographics/poster_{idx}.png',
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
class TestSelectInfographicCandidateView:
    def _admin_client(self):
        client = APIClient()
        client.force_authenticate(user=AdminUserFactory())
        return client

    def test_select_candidate_without_poster_image_returns_400(self):
        """No rendered poster = not publishable: the image is the one piece of
        content a student actually sees."""
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)
        ig = InfographicFactory(pack=pack, candidate_index=0)
        ClozeItem.objects.create(
            pack=pack, infographic=ig, word=word,
            sentence_text='Staged _______ row.', correct_answer='bright',
            distractors=['a', 'b'], order=0,
        )

        response = self._admin_client().post(f'/api/infographics/{ig.id}/select/')

        assert response.status_code == 400
        ig.refresh_from_db()
        assert ig.is_selected is False

    def test_select_candidate_without_staged_cloze_returns_400(self):
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)
        ig = InfographicFactory(
            pack=pack, candidate_index=0, image='infographics/poster.png',
        )

        response = self._admin_client().post(f'/api/infographics/{ig.id}/select/')

        assert response.status_code == 400
        ig.refresh_from_db()
        assert ig.is_selected is False

    def test_select_complete_candidate_returns_200(self):
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)
        ig = _make_ig_candidate(pack, 0, word)

        response = self._admin_client().post(f'/api/infographics/{ig.id}/select/')

        assert response.status_code == 200
        ig.refresh_from_db()
        assert ig.is_selected is True


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

        novel = GraphicNovelFactory(
            pack=pack, candidate_index=0, is_selected=False,
            metadata={'page_count': 1},
        )
        GraphicNovelPageFactory(novel=novel, page_number=1)
        GraphicNovelPageFactory(novel=novel, page_number=2, is_review_page=True)
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
        # Design retries internally (max_retries=2) plus one fallback-site
        # attempt, so all 4 attempts return the bad caption — the substep must
        # ultimately fail rather than persist it.
        mock_gemini.side_effect = [bad_design, bad_design, bad_design, bad_design]

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
        mock_gemini.side_effect = [bad_design, bad_design, bad_design, bad_design]

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

    def test_rejects_invalid_layout_mode(self):
        """layout_mode selects the image-prompt guidance block — an unknown
        value must fail validation, not silently render as panorama."""
        bad = {**IG_DESIGN_RESPONSE, 'layout_mode': 'grid'}
        with pytest.raises(ValueError, match='layout_mode'):
            _validate_infographic_design_result(bad)

    def test_rejects_missing_layout_mode(self):
        bad = {k: v for k, v in IG_DESIGN_RESPONSE.items() if k != 'layout_mode'}
        with pytest.raises(ValueError, match='layout_mode'):
            _validate_infographic_design_result(bad)


@pytest.mark.django_db
class TestInfographicRestartGuardsAndPersistIntegrity:
    """2026-07-03 review HIGHs #5/#6 mirrors: the infographic restart must not
    trust unvalidated design artifacts, persistence must be all-or-nothing, and
    the resume skip-check must not treat a cloze-less candidate as complete."""

    def _make_job_and_pack(self):
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
        return job, pack, words_data

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_restart_from_cloze_requires_completed_design_log(
        self, mock_load, mock_gemini,
    ):
        """The design artifact is written BEFORE validation, so presence alone
        must not qualify it; and the check must fire before the existing
        candidate is deleted."""
        mock_load.return_value = 'Infographic template'
        mock_gemini.side_effect = [IG_DESIGN_RESPONSE, IG_CLOZE_RESPONSE]
        job, pack, words_data = self._make_job_and_pack()
        ig = restart_infographic_from_substep(job, pack.id, 'design', words_data)

        # Simulate the design substep having failed validation on a later
        # attempt: artifact on disk, COMPLETED log gone.
        GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.INFOGRAPHIC_DESIGN,
            status=GenerationJob.Status.COMPLETED,
            output_data__substep='design',
        ).delete()
        mock_gemini.reset_mock()
        mock_gemini.side_effect = ValueError('no LLM call expected')

        with pytest.raises(ValueError, match='no COMPLETED log'):
            restart_infographic_from_substep(job, pack.id, 'cloze', words_data)

        assert mock_gemini.call_count == 0
        assert Infographic.objects.filter(id=ig.id).exists()
        assert ClozeItem.objects.filter(infographic=ig).count() == 2

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_restart_refuses_selected_candidate(self, mock_load, mock_gemini):
        """The manual restart path must never delete the published candidate —
        the engine raises before touching anything."""
        mock_load.return_value = 'Infographic template'
        mock_gemini.side_effect = ValueError('no LLM call expected')
        job, pack, words_data = self._make_job_and_pack()
        ig = InfographicFactory(pack=pack, candidate_index=0, is_selected=True)

        with pytest.raises(ValueError, match='is_selected'):
            restart_infographic_from_substep(job, pack.id, 'design', words_data)

        assert mock_gemini.call_count == 0
        assert Infographic.objects.filter(id=ig.id, is_selected=True).exists()

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_restart_from_cloze_purges_only_cloze_logs(self, mock_load, mock_gemini):
        """Substep logs are append-only: restarting from 'cloze' deletes the
        stale cloze logs but keeps the design COMPLETED log that authorizes
        the restart."""
        mock_load.return_value = 'Infographic template'
        mock_gemini.side_effect = [IG_DESIGN_RESPONSE, IG_CLOZE_RESPONSE]
        job, pack, words_data = self._make_job_and_pack()
        restart_infographic_from_substep(job, pack.id, 'design', words_data)

        mock_gemini.reset_mock()
        mock_gemini.side_effect = [IG_CLOZE_RESPONSE]
        restart_infographic_from_substep(job, pack.id, 'cloze', words_data)

        assert mock_gemini.call_count == 1
        completed = GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.INFOGRAPHIC_DESIGN,
            status=GenerationJob.Status.COMPLETED,
        )
        # The design log from the first run survived; the cloze log is exactly
        # the new one (the stale first-run row was purged at engine start).
        assert completed.filter(output_data__substep='design').count() == 1
        assert completed.filter(output_data__substep='cloze').count() == 1

    @patch('vocabulary.services.generation.step_infographic.INFOGRAPHIC_CANDIDATE_COUNT', 1)
    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_half_persisted_candidate_regenerated_on_rerun(
        self, mock_load, mock_gemini,
    ):
        """An Infographic row without staged cloze (pre-atomic half persist)
        must be regenerated, not skipped as complete."""
        mock_load.return_value = 'Infographic template'
        mock_gemini.side_effect = [IG_DESIGN_RESPONSE, IG_CLOZE_RESPONSE]
        job, pack, words_data = self._make_job_and_pack()
        half = InfographicFactory(pack=pack, candidate_index=0, title='Half-written')

        _step_infographic_design(job, [pack], words_data)

        assert mock_gemini.call_count == 2
        new_ig = Infographic.objects.get(pack=pack)
        assert new_ig.id != half.id
        assert new_ig.title == 'Light Words'
        assert ClozeItem.objects.filter(infographic=new_ig).count() == 2

    @patch('vocabulary.services.generation.step_infographic.INFOGRAPHIC_CANDIDATE_COUNT', 1)
    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_selected_candidate_never_deleted_by_rerun(self, mock_load, mock_gemini):
        """A published (selected) candidate is skipped even without staged
        cloze — a resume must never unpublish student content."""
        mock_load.return_value = 'Infographic template'
        mock_gemini.side_effect = ValueError('no LLM call expected')
        job, pack, words_data = self._make_job_and_pack()
        published = InfographicFactory(pack=pack, candidate_index=0, is_selected=True)

        _step_infographic_design(job, [pack], words_data)

        assert mock_gemini.call_count == 0
        assert Infographic.objects.filter(id=published.id).exists()

    def test_persist_rolls_back_when_cloze_misses_a_pack_word(self):
        """Persistence is atomic and every pack word needs a staged cloze item:
        a dropped word raises and leaves no cloze-less Infographic row behind."""
        job, pack, _ = self._make_job_and_pack()
        cloze_missing_discover = {
            'cloze_items': [IG_CLOZE_RESPONSE['cloze_items'][0]],
        }

        with pytest.raises(ValueError, match='discover'):
            _persist_candidate_infographic(
                pack, 0, IG_DESIGN_RESPONSE, 600, cloze_missing_discover,
            )

        assert not Infographic.objects.filter(pack=pack).exists()
        assert not ClozeItem.objects.filter(pack=pack).exists()

    def test_persist_matches_cloze_item_by_correct_answer(self):
        """The cloze validator accepts an item via term OR correct_answer, so
        the persist join must too."""
        job, pack, _ = self._make_job_and_pack()
        cloze = {
            'cloze_items': [
                {'term': 'shining brightly', 'sentence_text': 'The sun is _______.',
                 'correct_answer': 'bright', 'distractors': ['dark', 'cold']},
                IG_CLOZE_RESPONSE['cloze_items'][1],
            ],
        }

        ig = _persist_candidate_infographic(pack, 0, IG_DESIGN_RESPONSE, 600, cloze)

        staged = ClozeItem.objects.filter(infographic=ig)
        assert staged.count() == 2
        assert set(staged.values_list('word__text', flat=True)) == {'bright', 'discover'}


class TestTermInText:
    """Caption/intro term matching uses symmetric stemming: the term's stem is
    compared against each text token's stem, both directions."""

    def test_plural_term_matches_singular_token(self):
        assert _term_in_text('batteries', 'Each battery powers a lamp.')

    def test_singular_term_matches_plural_token(self):
        assert _term_in_text('battery', 'Two batteries sit in the drawer.')

    def test_inflections_still_match(self):
        assert _term_in_text('discover', 'She discovered a hidden cave.')

    def test_absent_term_does_not_match(self):
        assert not _term_in_text('bright', 'The cave was dark and quiet.')


class TestDesignValidatorGlossaryBoundary:
    """The glossary-format check is word-boundary based: hyphenated compounds
    must not false-fail, while real 'word: definition' captions are rejected."""

    def _design(self, caption):
        return {
            **IG_DESIGN_RESPONSE,
            'scene_elements': [
                {
                    'label': 'The Sun',
                    'caption': caption,
                    'vocab_terms': ['bright'],
                    'illustration': 'A glowing sun.',
                },
                IG_DESIGN_RESPONSE['scene_elements'][1],
            ],
        }

    def test_hyphenated_compound_is_not_glossary_format(self):
        # 'bright-lit' previously false-failed the "term-" separator check.
        _validate_infographic_design_result(
            self._design('The bright-lit art-room glowed at dawn.')
        )

    def test_glossary_formats_still_rejected(self):
        for caption in (
            'bright: giving off a lot of light.',
            'Bright — giving off a lot of light.',
            'bright - giving off a lot of light.',
        ):
            with pytest.raises(ValueError, match='definition format'):
                _validate_infographic_design_result(self._design(caption))


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



@pytest.mark.django_db
class TestInfographicSubstepFallback:
    """Substep attempts mirror the word-level steps' [primary ×3, fallback ×1]
    plan: a down primary must not hard-fail the step when a fallback site is
    configured (previously the fallback was never used)."""

    @patch('vocabulary.services.generation.step_infographic._call_llm_with_config')
    def test_fallback_site_gets_one_final_attempt(self, mock_call):
        primary = {'model': 'm-primary', 'provider_type': 'gemini_native'}
        fallback = {'model': 'm-fallback', 'provider_type': 'gemini_native'}
        mock_call.side_effect = [
            RuntimeError('primary down'), RuntimeError('primary down'),
            RuntimeError('primary down'), IG_CLOZE_RESPONSE,
        ]
        job = GenerationJobFactory(content_types=['infographic'])
        pack = WordPackFactory(word_set=job.word_set, label='Pack 1', order=0)

        result, _ = _run_infographic_substep(
            job, pack, INFOGRAPHIC_SUBSTEPS[1], primary, 'template', '{}',
            {'pack_label': 'Pack 1'},
            validator=_validate_graphic_novel_cloze_result,
            fallback_site_config=fallback,
        )

        assert result == IG_CLOZE_RESPONSE
        assert mock_call.call_count == 4
        assert [c.args[0] for c in mock_call.call_args_list] == [primary] * 3 + [fallback]

    @patch('vocabulary.services.generation.step_infographic._call_llm_with_config')
    def test_without_fallback_raises_after_primary_retries(self, mock_call):
        primary = {'model': 'm-primary', 'provider_type': 'gemini_native'}
        mock_call.side_effect = RuntimeError('primary down')
        job = GenerationJobFactory(content_types=['infographic'])
        pack = WordPackFactory(word_set=job.word_set, label='Pack 1', order=0)

        with pytest.raises(RuntimeError, match='primary down'):
            _run_infographic_substep(
                job, pack, INFOGRAPHIC_SUBSTEPS[1], primary, 'template', '{}',
                {'pack_label': 'Pack 1'},
            )
        assert mock_call.call_count == 3


@pytest.mark.django_db
class TestInfographicStepClears:
    def test_design_clear_preserves_selected_candidate(self):
        """A full-step INFOGRAPHIC_DESIGN restart clears only unpublished
        candidates — the selected (live) candidate, its staged cloze, and the
        pack's promoted cloze all survive. Mirrors the GN clear."""
        job = GenerationJobFactory(content_types=['infographic'])
        word = WordFactory(text='bright')
        pack = WordPackFactory(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItemFactory(pack=pack, word=word, order=0)
        selected = _make_ig_candidate(pack, 0, word, selected=True)
        _make_ig_candidate(pack, 1, word, selected=False)
        promoted = ClozeItem.objects.create(
            pack=pack, word=word, sentence_text='The _______ sun.',
            correct_answer='bright', distractors=['a', 'b'], order=1,
        )

        _clear_testing_outputs_for_step(
            job, GenerationJobLog.Step.INFOGRAPHIC_DESIGN, [],
        )

        assert Infographic.objects.filter(id=selected.id, is_selected=True).exists()
        assert not Infographic.objects.filter(pack=pack, is_selected=False).exists()
        assert ClozeItem.objects.filter(infographic=selected).count() == 1
        assert ClozeItem.objects.filter(
            id=promoted.id, novel__isnull=True, infographic__isnull=True,
        ).exists()
        job.refresh_from_db()
        assert job.infographics_created == 1
        assert job.cloze_items_created == 2

    def test_image_clear_resets_jpeg_companion(self):
        """student_image prefers image_jpeg — a clear that resets only `image`
        would keep serving the stale JPEG in the re-render window."""
        job = GenerationJobFactory(content_types=['infographic'])
        pack = WordPackFactory(word_set=job.word_set, label='Pack 1', order=0)
        ig = InfographicFactory(pack=pack, candidate_index=0)
        ig.image.save('poster.png', ContentFile(b'png'), save=False)
        ig.image_jpeg.save('poster.jpg', ContentFile(b'jpg'), save=False)
        ig.generation_status = Infographic.GenerationStatus.COMPLETED
        ig.save()

        _clear_testing_outputs_for_step(
            job, GenerationJobLog.Step.INFOGRAPHIC_IMAGE, [],
        )

        ig.refresh_from_db()
        assert not ig.image
        assert not ig.image_jpeg
        assert ig.generation_status == Infographic.GenerationStatus.PENDING


@pytest.mark.django_db
class TestInfographicStaleSweep:
    def test_stale_running_infographic_marked_failed_on_job_status(self):
        """A worker restart mid-render orphans a RUNNING row; the job-status
        poll sweeps it to FAILED (mirroring the GN page sweep) instead of
        displaying it as running forever."""
        admin = AdminUserFactory()
        job = GenerationJobFactory(
            created_by=admin, status=GenerationJob.Status.RUNNING,
            content_types=['infographic'],
        )
        pack = WordPackFactory(word_set=job.word_set, label='Pack 1', order=0)
        ig = InfographicFactory(
            pack=pack, candidate_index=0,
            generation_status=Infographic.GenerationStatus.RUNNING,
            generation_started_at=timezone.now() - timedelta(minutes=31),
        )
        old_log = GenerationJobLog.objects.create(
            job=job,
            step=GenerationJobLog.Step.INFOGRAPHIC_IMAGE,
            status=GenerationJob.Status.RUNNING,
        )
        GenerationJobLog.objects.filter(id=old_log.id).update(
            created_at=timezone.now() - timedelta(minutes=31),
        )

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(f'/api/generation-jobs/{job.id}/')

        assert response.status_code == 200
        ig.refresh_from_db()
        assert ig.generation_status == Infographic.GenerationStatus.FAILED
        assert 'stalled' in ig.generation_error
