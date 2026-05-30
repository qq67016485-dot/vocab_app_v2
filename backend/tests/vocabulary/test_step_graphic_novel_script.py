"""Tests for the graphic novel script generation step.

Covers:
- TestStepGraphicNovelScript: end-to-end script generation with mocked LLM substeps
- TestRouterValidatorPageCount: page_count validator on router output
- TestStepGraphicNovelScriptTemplateDispatch: template selection by winning page_count
"""
import os
import pytest
from unittest.mock import patch

from vocabulary.models import (
    WordPack, WordPackItem,
    GraphicNovel, GraphicNovelPage, ClozeItem,
    GenerationJob, GenerationJobLog,
)
from vocabulary.services.generation_pipeline_service import (
    _step_graphic_novel_script,
    _validate_graphic_novel_router_result,
)
from vocabulary.services.generation.constants import (
    GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES,
    GRAPHIC_NOVEL_SCRIPT_TEMPLATES,
)
from tests.factories import (
    WordFactory, GenerationJobFactory,
)
from tests.vocabulary.generation_fixtures import (
    WORD_LOOKUP_RESPONSE,
    GRAPHIC_NOVEL_RESPONSE,
    GRAPHIC_NOVEL_CLOZE_RESPONSE,
    GRAPHIC_NOVEL_TEAM_RESPONSE,
    GRAPHIC_NOVEL_ROUTER_RESPONSE,
    GRAPHIC_NOVEL_SCORING_RESPONSE,
    GRAPHIC_NOVEL_BEAT_RESPONSE,
    build_six_page_beat_response,
    build_six_page_script_response,
)


@pytest.mark.django_db
class TestStepGraphicNovelScript:
    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_creates_graphic_novel_pages_and_cloze(self, mock_load, mock_anthropic):
        mock_load.return_value = "Graphic novel template {input_json}"
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            GRAPHIC_NOVEL_SCORING_RESPONSE,
            GRAPHIC_NOVEL_CLOZE_RESPONSE,
            GRAPHIC_NOVEL_BEAT_RESPONSE,
            GRAPHIC_NOVEL_RESPONSE,
        ]
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word1, order=0)
        WordPackItem.objects.create(pack=pack, word=word2, order=1)

        _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])

        novel = GraphicNovel.objects.get(pack=pack)
        assert novel.title == 'The Bright Discovery'
        assert novel.metadata['away_team'] == ['Leo', 'Amara']
        assert novel.metadata['age_band'] == '9yo'
        assert novel.metadata['vault_framing'] is True
        assert novel.metadata['review_artifact_type'] == 'Vault clue board'
        assert GraphicNovelPage.objects.filter(novel=novel).count() == 6
        story_page = GraphicNovelPage.objects.get(novel=novel, page_number=1)
        assert story_page.page_number == 1
        assert story_page.characters_featured == ['Leo']
        assert story_page.setting_key == 'the_vault'
        assert story_page.vault_zone == 'map_platform'
        assert story_page.is_vault_page is True
        review_page = GraphicNovelPage.objects.get(novel=novel, is_review_page=True)
        assert review_page.page_number == 6
        assert set(review_page.vocab_words_used) == {'bright', 'discover'}
        assert ClozeItem.objects.filter(pack=pack).count() == 2
        assert mock_anthropic.call_count == 6

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_updates_counters_and_log(self, mock_load, mock_anthropic):
        mock_load.return_value = "Graphic novel template {input_json}"
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            GRAPHIC_NOVEL_SCORING_RESPONSE,
            GRAPHIC_NOVEL_CLOZE_RESPONSE,
            GRAPHIC_NOVEL_BEAT_RESPONSE,
            GRAPHIC_NOVEL_RESPONSE,
        ]
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        word = WordFactory(text='bright')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word, order=0)

        _step_graphic_novel_script(job, [pack], [WORD_LOOKUP_RESPONSE['words'][0]])

        job.refresh_from_db()
        assert job.graphic_novels_created == 1
        assert GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.COMPLETED,
        ).exists()
        substep_logs = GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            output_data__substep__isnull=False,
        )
        assert substep_logs.filter(status=GenerationJob.Status.RUNNING).count() == 6
        assert substep_logs.filter(status=GenerationJob.Status.COMPLETED).count() == 6
        final_log = GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.COMPLETED,
            output_data__artifact_references__isnull=False,
        ).latest('created_at')
        assert len(final_log.output_data['artifact_references']) == 6
        for reference in final_log.output_data['artifact_references']:
            assert os.path.exists(reference['artifact_path'])

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_logs_failed_substep(self, mock_load, mock_anthropic):
        mock_load.return_value = "Graphic novel template {input_json}"
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            ValueError('judge failed'),
            ValueError('judge failed'),
        ]
        job = GenerationJobFactory(input_words=['bright'])
        word = WordFactory(text='bright')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word, order=0)

        with pytest.raises(ValueError, match='judge failed'):
            _step_graphic_novel_script(job, [pack], [WORD_LOOKUP_RESPONSE['words'][0]])

        failed_logs = GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.FAILED,
            output_data__substep='premise_scoring',
        )
        assert failed_logs.exists()
        assert failed_logs.first().output_data['pack_label'] == 'Pack 1'

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_rejects_router_without_three_premises(self, mock_load, mock_anthropic):
        mock_load.return_value = "Graphic novel template {input_json}"
        bad_router = {
            **GRAPHIC_NOVEL_ROUTER_RESPONSE,
            'premises': GRAPHIC_NOVEL_ROUTER_RESPONSE['premises'][:1],
        }
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            bad_router,
            bad_router,
        ]
        job = GenerationJobFactory(input_words=['bright'])
        word = WordFactory(text='bright')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word, order=0)

        with pytest.raises(ValueError, match='exactly 3 premises'):
            _step_graphic_novel_script(job, [pack], [WORD_LOOKUP_RESPONSE['words'][0]])

        assert GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.FAILED,
            output_data__substep='router_premises',
        ).exists()

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_rejects_router_with_too_many_direct_ink_uses(self, mock_load, mock_anthropic):
        mock_load.return_value = "Graphic novel template {input_json}"
        bad_premise = {
            **GRAPHIC_NOVEL_ROUTER_RESPONSE['premises'][0],
            'total_ink_activations_planned': 2,
            'mini_justification': 'Two Minis demonstrate two different actions.',
            'vocab_integration_plan': [
                {
                    'term': 'bright',
                    'story_role': 'first Mini summon',
                    'integration_mode': 'lexi_mini_summon',
                    'uses_direct_ink': True,
                    'pedagogical_anchor': {
                        'anchor_type': 'demonstrated_action',
                        'anchor_sketch': 'Mini lights up to show BRIGHT.',
                    },
                },
                {
                    'term': 'discover',
                    'story_role': 'second Mini summon',
                    'integration_mode': 'lexi_mini_summon',
                    'uses_direct_ink': True,
                    'pedagogical_anchor': {
                        'anchor_type': 'demonstrated_action',
                        'anchor_sketch': 'Mini uncovers a switch to show DISCOVER.',
                    },
                },
            ],
        }
        bad_router = {
            **GRAPHIC_NOVEL_ROUTER_RESPONSE,
            'premises': [bad_premise] + GRAPHIC_NOVEL_ROUTER_RESPONSE['premises'][1:],
        }
        mock_anthropic.side_effect = [GRAPHIC_NOVEL_TEAM_RESPONSE, bad_router, bad_router]
        job = GenerationJobFactory(input_words=['bright'])
        word = WordFactory(text='bright')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word, order=0)

        with pytest.raises(ValueError, match='direct Ink'):
            _step_graphic_novel_script(job, [pack], [WORD_LOOKUP_RESPONSE['words'][0]])

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_rejects_scorer_missing_required_dimension(self, mock_load, mock_anthropic):
        mock_load.return_value = "Graphic novel template {input_json}"
        bad_scores = []
        for score in GRAPHIC_NOVEL_SCORING_RESPONSE['scores']:
            bad_score = dict(score)
            bad_score.pop('pedagogical_clarity')
            bad_scores.append(bad_score)
        bad_scoring_response = {
            **GRAPHIC_NOVEL_SCORING_RESPONSE,
            'scores': bad_scores,
        }
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            bad_scoring_response,
            bad_scoring_response,
        ]
        job = GenerationJobFactory(input_words=['bright'])
        word = WordFactory(text='bright')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word, order=0)

        with pytest.raises(ValueError, match='missing dimensions'):
            _step_graphic_novel_script(job, [pack], [WORD_LOOKUP_RESPONSE['words'][0]])

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_rejects_beat_sheet_missing_vocab_roles(self, mock_load, mock_anthropic):
        mock_load.return_value = "Graphic novel template {input_json}"
        bad_beat_response = {
            **GRAPHIC_NOVEL_BEAT_RESPONSE,
            'vocab_roles': {'bright': 'clue'},
        }
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            GRAPHIC_NOVEL_SCORING_RESPONSE,
            GRAPHIC_NOVEL_CLOZE_RESPONSE,
            bad_beat_response,
            bad_beat_response,
        ]
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word1, order=0)
        WordPackItem.objects.create(pack=pack, word=word2, order=1)

        with pytest.raises(ValueError, match='vocab_roles'):
            _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])

        assert GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.FAILED,
            output_data__substep='beat_sheet_vocab_roles',
        ).exists()

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_defaults_blank_review_artifact_type(self, mock_load, mock_anthropic):
        mock_load.return_value = "Graphic novel template {input_json}"
        beat_response = {
            **GRAPHIC_NOVEL_BEAT_RESPONSE,
            'review_artifact_type': '',
        }
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            GRAPHIC_NOVEL_SCORING_RESPONSE,
            GRAPHIC_NOVEL_CLOZE_RESPONSE,
            beat_response,
            GRAPHIC_NOVEL_RESPONSE,
        ]
        job = GenerationJobFactory(input_words=['bright'])
        word = WordFactory(text='bright')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word, order=0)

        _step_graphic_novel_script(job, [pack], [WORD_LOOKUP_RESPONSE['words'][0]])

        novel = GraphicNovel.objects.get(pack=pack)
        assert novel.metadata['review_artifact_type'] == 'Vault clue board'

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_rejects_beat_sheet_with_too_many_direct_ink_uses(self, mock_load, mock_anthropic):
        mock_load.return_value = "Graphic novel template {input_json}"
        bad_beat_response = {
            **GRAPHIC_NOVEL_BEAT_RESPONSE,
            'total_ink_activations_planned': 2,
            'ink_usage': [
                {'term': 'bright', 'page': 1, 'uses_direct_ink': True, 'purpose': 'Ink 1'},
                {'term': 'discover', 'page': 2, 'uses_direct_ink': True, 'purpose': 'Ink 2'},
            ],
        }
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            GRAPHIC_NOVEL_SCORING_RESPONSE,
            GRAPHIC_NOVEL_CLOZE_RESPONSE,
            bad_beat_response,
            bad_beat_response,
        ]
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word1, order=0)
        WordPackItem.objects.create(pack=pack, word=word2, order=1)

        with pytest.raises(ValueError, match='direct Ink'):
            _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])


@pytest.mark.django_db
class TestRouterValidatorPageCount:
    """Tests for _validate_graphic_novel_router_result page_count enforcement."""

    def _router_with_first_premise(self, first_premise):
        """Build a router response that fully replaces the first premise."""
        return {
            **GRAPHIC_NOVEL_ROUTER_RESPONSE,
            'premises': [first_premise] + GRAPHIC_NOVEL_ROUTER_RESPONSE['premises'][1:],
        }

    def _router_with_premise_override(self, premise_overrides):
        """Build a router response by overriding fields on the first premise."""
        first = {**GRAPHIC_NOVEL_ROUTER_RESPONSE['premises'][0], **premise_overrides}
        return self._router_with_first_premise(first)

    def test_accepts_baseline_response(self):
        """Sanity check: the existing fixture passes the validator."""
        _validate_graphic_novel_router_result(GRAPHIC_NOVEL_ROUTER_RESPONSE)

    def test_rejects_premise_missing_page_count(self):
        bad_premise = {**GRAPHIC_NOVEL_ROUTER_RESPONSE['premises'][0]}
        bad_premise.pop('page_count')
        bad_router = self._router_with_first_premise(bad_premise)
        with pytest.raises(ValueError, match='page_count'):
            _validate_graphic_novel_router_result(bad_router)

    def test_rejects_premise_with_invalid_page_count(self):
        bad_router = self._router_with_premise_override({'page_count': 7})
        with pytest.raises(ValueError, match='page_count'):
            _validate_graphic_novel_router_result(bad_router)

    def test_rejects_premise_with_string_page_count(self):
        bad_router = self._router_with_premise_override({'page_count': '5'})
        with pytest.raises(ValueError, match='page_count'):
            _validate_graphic_novel_router_result(bad_router)

    def test_rejects_premise_missing_page_count_rationale(self):
        bad_premise = {**GRAPHIC_NOVEL_ROUTER_RESPONSE['premises'][0]}
        bad_premise.pop('page_count_rationale')
        bad_router = self._router_with_first_premise(bad_premise)
        with pytest.raises(ValueError, match='page_count_rationale'):
            _validate_graphic_novel_router_result(bad_router)

    def test_rejects_premise_with_blank_page_count_rationale(self):
        bad_router = self._router_with_premise_override({'page_count_rationale': '   '})
        with pytest.raises(ValueError, match='page_count_rationale'):
            _validate_graphic_novel_router_result(bad_router)


@pytest.mark.django_db
class TestStepGraphicNovelScriptTemplateDispatch:
    """Tests that beat-sheet and final-script substeps dispatch to the
    page_count-matched template based on winning_premise.page_count."""

    def _scoring_response_for_winner(self, winner_idx):
        winning_premise = GRAPHIC_NOVEL_ROUTER_RESPONSE['premises'][winner_idx]
        return {
            **GRAPHIC_NOVEL_SCORING_RESPONSE,
            'winning_premise_id': winning_premise['id'],
            'winning_premise': winning_premise,
        }

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_uses_5page_templates_when_winning_premise_is_5_pages(
        self, mock_load, mock_anthropic,
    ):
        # premise_1 has page_count=5 in the test fixture
        mock_load.side_effect = lambda name: f"Template {name} {{input_json}}"
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            self._scoring_response_for_winner(0),
            GRAPHIC_NOVEL_CLOZE_RESPONSE,
            GRAPHIC_NOVEL_BEAT_RESPONSE,
            GRAPHIC_NOVEL_RESPONSE,
        ]
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word1, order=0)
        WordPackItem.objects.create(pack=pack, word=word2, order=1)

        _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])

        loaded_templates = {call.args[0] for call in mock_load.call_args_list}
        assert GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES[5] in loaded_templates
        assert GRAPHIC_NOVEL_SCRIPT_TEMPLATES[5] in loaded_templates

        beat_log = GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.COMPLETED,
            output_data__substep='beat_sheet_vocab_roles',
        ).latest('created_at')
        script_log = GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.COMPLETED,
            output_data__substep='final_script_self_check',
        ).latest('created_at')
        assert beat_log.output_data['prompt_template'] == GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES[5]
        assert script_log.output_data['prompt_template'] == GRAPHIC_NOVEL_SCRIPT_TEMPLATES[5]

        novel = GraphicNovel.objects.get(pack=pack)
        assert novel.metadata['page_count'] == 5
        # 5 story pages + 1 review page
        assert GraphicNovelPage.objects.filter(novel=novel).count() == 6

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_uses_6page_templates_when_winning_premise_is_6_pages(
        self, mock_load, mock_anthropic,
    ):
        # premise_3 has page_count=6 in the test fixture
        mock_load.side_effect = lambda name: f"Template {name} {{input_json}}"
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            self._scoring_response_for_winner(2),
            GRAPHIC_NOVEL_CLOZE_RESPONSE,
            build_six_page_beat_response(),
            build_six_page_script_response(),
        ]
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word1, order=0)
        WordPackItem.objects.create(pack=pack, word=word2, order=1)

        _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])

        loaded_templates = {call.args[0] for call in mock_load.call_args_list}
        assert GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES[6] in loaded_templates
        assert GRAPHIC_NOVEL_SCRIPT_TEMPLATES[6] in loaded_templates

        beat_log = GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.COMPLETED,
            output_data__substep='beat_sheet_vocab_roles',
        ).latest('created_at')
        script_log = GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.COMPLETED,
            output_data__substep='final_script_self_check',
        ).latest('created_at')
        assert beat_log.output_data['prompt_template'] == GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES[6]
        assert script_log.output_data['prompt_template'] == GRAPHIC_NOVEL_SCRIPT_TEMPLATES[6]

        novel = GraphicNovel.objects.get(pack=pack)
        assert novel.metadata['page_count'] == 6
        # 6 story pages + 1 review page
        assert GraphicNovelPage.objects.filter(novel=novel).count() == 7


class TestFindSecondaryCharactersNeedingAnchors:
    """Tests for _find_secondary_characters_needing_anchors detection logic."""

    def test_returns_empty_for_no_pages(self):
        from vocabulary.services.generation.step_graphic_novel import (
            _find_secondary_characters_needing_anchors,
        )
        assert _find_secondary_characters_needing_anchors({'pages': []}) == []

    def test_ignores_hero_characters(self):
        from vocabulary.services.generation.step_graphic_novel import (
            _find_secondary_characters_needing_anchors,
        )
        result = {
            'pages': [
                {'page_number': 1, 'characters_featured': ['Leo'], 'panels': [
                    {'dialogue': [{'speaker': 'Leo', 'text': 'Hi'}]}
                ]},
                {'page_number': 3, 'characters_featured': ['Leo'], 'panels': [
                    {'dialogue': [{'speaker': 'Leo', 'text': 'Bye'}]}
                ]},
            ]
        }
        assert _find_secondary_characters_needing_anchors(result) == []

    def test_detects_speaking_secondary_with_gap(self):
        from vocabulary.services.generation.step_graphic_novel import (
            _find_secondary_characters_needing_anchors,
        )
        result = {
            'pages': [
                {'page_number': 1, 'characters_featured': ['Leo', 'Dr. Vance'], 'panels': [
                    {'dialogue': [
                        {'speaker': 'Leo', 'text': 'Hello'},
                        {'speaker': 'Dr. Vance', 'text': 'Welcome'},
                    ]}
                ]},
                {'page_number': 2, 'characters_featured': ['Leo'], 'panels': [
                    {'dialogue': [{'speaker': 'Leo', 'text': 'Hmm'}]}
                ]},
                {'page_number': 3, 'characters_featured': ['Leo', 'Dr. Vance'], 'panels': [
                    {'dialogue': [{'speaker': 'Dr. Vance', 'text': 'Good job'}]}
                ]},
            ]
        }
        names = _find_secondary_characters_needing_anchors(result)
        assert 'dr. vance' in names

    def test_skips_secondary_without_dialogue(self):
        from vocabulary.services.generation.step_graphic_novel import (
            _find_secondary_characters_needing_anchors,
        )
        result = {
            'pages': [
                {'page_number': 1, 'characters_featured': ['Leo', 'Shopkeeper'], 'panels': [
                    {'dialogue': [{'speaker': 'Leo', 'text': 'Hi'}]}
                ]},
                {'page_number': 3, 'characters_featured': ['Leo', 'Shopkeeper'], 'panels': [
                    {'dialogue': [{'speaker': 'Leo', 'text': 'Bye'}]}
                ]},
            ]
        }
        assert _find_secondary_characters_needing_anchors(result) == []

    def test_skips_secondary_on_consecutive_pages(self):
        from vocabulary.services.generation.step_graphic_novel import (
            _find_secondary_characters_needing_anchors,
        )
        result = {
            'pages': [
                {'page_number': 1, 'characters_featured': ['Leo', 'Coach'], 'panels': [
                    {'dialogue': [{'speaker': 'Coach', 'text': 'Run!'}]}
                ]},
                {'page_number': 2, 'characters_featured': ['Leo', 'Coach'], 'panels': [
                    {'dialogue': [{'speaker': 'Coach', 'text': 'Faster!'}]}
                ]},
            ]
        }
        assert _find_secondary_characters_needing_anchors(result) == []
