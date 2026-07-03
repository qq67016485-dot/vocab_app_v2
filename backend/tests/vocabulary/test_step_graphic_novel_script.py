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
    page_count_for_word_count,
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
    MULTIWORD_TERMS,
    MULTIWORD_LOOKUP_RESPONSE,
    build_multiword_cloze_response,
    build_multiword_six_page_beat_response,
    build_multiword_six_page_script_response,
)


# The 6-call substep sequence mocked throughout this file generates ONE candidate.
# Force single-candidate mode for the per-candidate workflow tests; multi-candidate
# behaviour is covered explicitly in TestGraphicNovelCandidates.
@pytest.fixture(autouse=True)
def _single_candidate(monkeypatch):
    monkeypatch.setattr(
        'vocabulary.services.generation.graphic_novel_script.GRAPHIC_NOVEL_CANDIDATE_COUNT',
        1,
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
        # One reference per candidate (single-candidate mode here).
        assert len(final_log.output_data['artifact_references']) == 1
        assert final_log.output_data['artifact_references'][0]['candidate_index'] == 0
        # Per-substep artifacts are tracked on the substep COMPLETED logs.
        completed_substep_logs = substep_logs.filter(status=GenerationJob.Status.COMPLETED)
        for log in completed_substep_logs:
            assert os.path.exists(log.output_data['artifact_path'])

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_logs_failed_substep(self, mock_load, mock_anthropic):
        mock_load.return_value = "Graphic novel template {input_json}"
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            ValueError('judge failed'),
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
        mock_anthropic.side_effect = [GRAPHIC_NOVEL_TEAM_RESPONSE, bad_router, bad_router, bad_router]
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


class TestPageCountForWordCount:
    """page_count_for_word_count maps pack word count to page count:
    <=4 words -> 5 pages; >4 words -> 6 pages."""

    @pytest.mark.parametrize("word_count,expected", [
        (1, 5),
        (2, 5),
        (3, 5),
        (4, 5),   # boundary: still 5
        (5, 6),   # boundary: first to flip to 6
        (6, 6),
        (12, 6),
    ])
    def test_maps_word_count_to_page_count(self, word_count, expected):
        assert page_count_for_word_count(word_count) == expected


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
    def test_uses_5page_templates_when_pack_at_or_below_threshold_words(
        self, mock_load, mock_anthropic,
    ):
        # A 2-word pack (≤4) forces 5 pages.
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
    def test_uses_6page_templates_when_pack_has_more_than_threshold_words(
        self, mock_load, mock_anthropic,
    ):
        # A pack with >4 words forces 6 pages regardless of the winning
        # premise's declared page_count.
        mock_load.side_effect = lambda name: f"Template {name} {{input_json}}"
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            self._scoring_response_for_winner(0),  # premise_1 declares page_count=5
            build_multiword_cloze_response(),
            build_multiword_six_page_beat_response(),
            build_multiword_six_page_script_response(),
        ]
        job = GenerationJobFactory(input_words=list(MULTIWORD_TERMS))
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        for idx, term in enumerate(MULTIWORD_TERMS):
            WordPackItem.objects.create(pack=pack, word=WordFactory(text=term), order=idx)

        _step_graphic_novel_script(job, [pack], MULTIWORD_LOOKUP_RESPONSE['words'])

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
        # Forced to 6 even though the winning premise declared 5.
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


class TestFormatAnchorDesignLock:
    """The anchor LLM call returns parsed JSON (a dict) because the shared
    wrappers force JSON mode. The formatter must render that dict into a text
    block — the original code assumed a plain string and crashed on .strip()."""

    def test_renders_dict_in_section_order(self):
        from vocabulary.services.generation.step_graphic_novel import (
            _format_anchor_design_lock,
        )
        # Keys deliberately out of canonical order to prove ordering.
        data = {
            'NEGATIVE_LOCK': 'do not recolor',
            'AGE_AND_BODY': 'six years old',
            'OUTFIT_LOCK': 'yellow shirt, red boots',
            'FACE_AND_HAIR': 'beige skin',
            'COLOR_PRIORITY': 'yellow and red',
        }
        out = _format_anchor_design_lock(data)
        lines = out.splitlines()
        assert lines[0].startswith('AGE_AND_BODY:')
        assert lines[1].startswith('FACE_AND_HAIR:')
        assert lines[2].startswith('OUTFIT_LOCK:')
        assert 'yellow shirt, red boots' in out

    def test_passes_through_plain_string(self):
        from vocabulary.services.generation.step_graphic_novel import (
            _format_anchor_design_lock,
        )
        assert _format_anchor_design_lock('  raw lock text  ') == 'raw lock text'

    def test_returns_empty_for_unexpected_type(self):
        from vocabulary.services.generation.step_graphic_novel import (
            _format_anchor_design_lock,
        )
        assert _format_anchor_design_lock(123) == ''
        assert _format_anchor_design_lock(None) == ''

    def test_skips_blank_section_values(self):
        from vocabulary.services.generation.step_graphic_novel import (
            _format_anchor_design_lock,
        )
        out = _format_anchor_design_lock({'AGE_AND_BODY': 'kid', 'OUTFIT_LOCK': ''})
        assert 'AGE_AND_BODY: kid' in out
        assert 'OUTFIT_LOCK' not in out


class TestGenerateSecondaryCharacterAnchors:
    """Regression: a dict LLM response must produce a stored anchor, not be
    silently dropped (the bug that let Toby's shirt drift blue->red)."""

    @patch('vocabulary.services.generation.graphic_novel_helpers._call_llm_with_config')
    def test_dict_response_produces_anchor(self, mock_llm):
        from vocabulary.services.generation.step_graphic_novel import (
            _generate_secondary_character_anchors,
        )
        mock_llm.return_value = {
            'AGE_AND_BODY': 'About 6 years old, shorter than the heroes.',
            'OUTFIT_LOCK': 'Bright yellow (#FFD700) shirt and red (#FF0000) boots.',
            'COLOR_PRIORITY': 'Yellow shirt and red boots.',
            'NEGATIVE_LOCK': 'Do not recolor the shirt.',
        }
        result = {
            'title': 'The Muddy Rescue',
            'style_prompt': 'Bright 2D graphic novel style.',
            'characters': [
                {'name': 'Toby', 'visual_description': 'A worried neighborhood boy.'},
            ],
            'pages': [
                {'page_number': 1, 'characters_featured': ['Hugo', 'Toby'], 'panels': [
                    {'dialogue': [{'speaker': 'Toby', 'text': 'Help!'}]}
                ]},
                {'page_number': 4, 'characters_featured': ['Hugo', 'Toby'], 'panels': [
                    {'dialogue': [{'speaker': 'Toby', 'text': 'Thanks!'}]}
                ]},
            ],
        }
        anchors = _generate_secondary_character_anchors(
            result, {'age_band': '9yo'}, {'model': 'm', 'provider_type': 'gemini_native'},
        )
        assert 'toby' in anchors
        assert 'OUTFIT_LOCK' in anchors['toby']
        assert '#FF0000' in anchors['toby']

    @patch('vocabulary.services.generation.graphic_novel_helpers._call_llm_with_config')
    def test_llm_failure_skips_character_without_raising(self, mock_llm):
        from vocabulary.services.generation.step_graphic_novel import (
            _generate_secondary_character_anchors,
        )
        mock_llm.side_effect = RuntimeError('boom')
        result = {
            'characters': [{'name': 'Toby', 'visual_description': 'A boy.'}],
            'pages': [
                {'page_number': 1, 'characters_featured': ['Hugo', 'Toby'], 'panels': [
                    {'dialogue': [{'speaker': 'Toby', 'text': 'Help!'}]}
                ]},
                {'page_number': 4, 'characters_featured': ['Hugo', 'Toby'], 'panels': [
                    {'dialogue': [{'speaker': 'Toby', 'text': 'Thanks!'}]}
                ]},
            ],
        }
        # Must not raise; just yields no anchor for the failed character.
        assert _generate_secondary_character_anchors(
            result, {'age_band': '9yo'}, {'model': 'm', 'provider_type': 'gemini_native'},
        ) == {}


@pytest.mark.django_db
class TestStepGraphicNovelScriptResume:
    """Resuming the GRAPHIC_NOVEL_SCRIPT step after a mid-pack substep failure
    must pick up from the failed substep, not restart from team selection."""

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_resumes_from_failed_substep_without_rerunning_earlier_ones(
        self, mock_load, mock_anthropic,
    ):
        mock_load.return_value = "Graphic novel template {input_json}"
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word1, order=0)
        WordPackItem.objects.create(pack=pack, word=word2, order=1)

        # First run: team + router succeed, premise scoring fails (after its retries).
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            ValueError('scorer down'),
            ValueError('scorer down'),
            ValueError('scorer down'),
        ]
        with pytest.raises(ValueError, match='scorer down'):
            _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])

        # Resume run: must NOT call team_selection or router again. Only the
        # remaining substeps (scoring → cloze → beat → final) should hit the LLM.
        mock_anthropic.reset_mock()
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_SCORING_RESPONSE,
            GRAPHIC_NOVEL_CLOZE_RESPONSE,
            GRAPHIC_NOVEL_BEAT_RESPONSE,
            GRAPHIC_NOVEL_RESPONSE,
        ]
        _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])

        # 4 calls = scoring + cloze + beat + final (team/router reused from disk).
        assert mock_anthropic.call_count == 4
        novel = GraphicNovel.objects.get(pack=pack)
        assert novel.title == 'The Bright Discovery'
        # away_team comes from the team_selection artifact saved on the first run.
        assert novel.metadata['away_team'] == ['Leo', 'Amara']
        assert ClozeItem.objects.filter(pack=pack).count() == 2

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_fresh_pack_runs_all_substeps_from_team_selection(
        self, mock_load, mock_anthropic,
    ):
        """A pack with no prior substep logs must run the full 6-call workflow."""
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

        assert mock_anthropic.call_count == 6
        assert GraphicNovel.objects.filter(pack=pack).exists()


@pytest.mark.django_db
class TestGraphicNovelCandidates:
    """Multi-candidate generation: each pack produces GRAPHIC_NOVEL_CANDIDATE_COUNT
    independent novels, none auto-selected, each with its own staged cloze."""

    def _three_candidate_side_effect(self):
        """LLM responses for 3 full candidate workflows (6 calls each)."""
        single = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            GRAPHIC_NOVEL_SCORING_RESPONSE,
            GRAPHIC_NOVEL_CLOZE_RESPONSE,
            GRAPHIC_NOVEL_BEAT_RESPONSE,
            GRAPHIC_NOVEL_RESPONSE,
        ]
        return single * 3

    @pytest.fixture(autouse=True)
    def _three_candidates(self, monkeypatch):
        monkeypatch.setattr(
            'vocabulary.services.generation.graphic_novel_script.GRAPHIC_NOVEL_CANDIDATE_COUNT',
            3,
        )

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_generates_three_unselected_candidates(self, mock_load, mock_anthropic):
        mock_load.return_value = "Graphic novel template {input_json}"
        mock_anthropic.side_effect = self._three_candidate_side_effect()
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word1, order=0)
        WordPackItem.objects.create(pack=pack, word=word2, order=1)

        _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])

        novels = GraphicNovel.objects.filter(pack=pack).order_by('candidate_index')
        assert novels.count() == 3
        assert [n.candidate_index for n in novels] == [0, 1, 2]
        # No candidate is auto-selected — an admin must pick one.
        assert not novels.filter(is_selected=True).exists()
        # 6 LLM calls per candidate.
        assert mock_anthropic.call_count == 18
        # Cloze is staged per-candidate (novel=<id>), none promoted yet (novel=None).
        assert ClozeItem.objects.filter(pack=pack, novel__isnull=False).count() == 6
        assert ClozeItem.objects.filter(pack=pack, novel__isnull=True).count() == 0

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_candidate_artifacts_are_isolated(self, mock_load, mock_anthropic):
        """Each candidate writes its own artifacts under cand_{i}/ — no clobber."""
        mock_load.return_value = "Graphic novel template {input_json}"
        mock_anthropic.side_effect = self._three_candidate_side_effect()
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word1, order=0)
        WordPackItem.objects.create(pack=pack, word=word2, order=1)

        _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])

        from vocabulary.services.generation.graphic_novel_helpers import (
            _graphic_novel_artifact_dir,
        )
        dirs = {
            i: _graphic_novel_artifact_dir(job, pack, i) for i in range(3)
        }
        assert len(set(dirs.values())) == 3
        for cand_dir in dirs.values():
            assert os.path.isdir(cand_dir)
            assert os.path.exists(os.path.join(cand_dir, '01_team_selection.json'))

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_complete_candidate_skipped_on_rerun(self, mock_load, mock_anthropic):
        """A second run regenerates only candidates lacking a novel-with-pages."""
        mock_load.return_value = "Graphic novel template {input_json}"
        mock_anthropic.side_effect = self._three_candidate_side_effect()
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word1, order=0)
        WordPackItem.objects.create(pack=pack, word=word2, order=1)

        _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])
        assert GraphicNovel.objects.filter(pack=pack).count() == 3

        # Re-run with no further LLM responses queued; all 3 are complete and skipped.
        mock_anthropic.reset_mock()
        mock_anthropic.side_effect = ValueError('should not be called')
        _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])
        assert mock_anthropic.call_count == 0
        assert GraphicNovel.objects.filter(pack=pack).count() == 3


@pytest.mark.django_db
class TestRestartGuardsAndPersistIntegrity:
    """2026-07-03 review HIGHs #5/#6: a manual substep restart must not trust
    unvalidated artifacts, persistence must be all-or-nothing, and the resume
    skip-check must not treat a half-persisted candidate as complete."""

    def _make_pack(self, job):
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word1, order=0)
        WordPackItem.objects.create(pack=pack, word=word2, order=1)
        return pack, word1, word2

    def _full_run(self, mock_anthropic, job, pack):
        mock_anthropic.side_effect = [
            GRAPHIC_NOVEL_TEAM_RESPONSE,
            GRAPHIC_NOVEL_ROUTER_RESPONSE,
            GRAPHIC_NOVEL_SCORING_RESPONSE,
            GRAPHIC_NOVEL_CLOZE_RESPONSE,
            GRAPHIC_NOVEL_BEAT_RESPONSE,
            GRAPHIC_NOVEL_RESPONSE,
        ]
        _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])
        return GraphicNovel.objects.get(pack=pack)

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_restart_rejects_prior_substep_without_completed_log(
        self, mock_load, mock_anthropic,
    ):
        """Artifacts are written BEFORE validation, so artifact presence alone
        must not qualify a prior substep — the COMPLETED log is required. The
        check must also fire before the existing candidate is deleted."""
        from vocabulary.services.generation.graphic_novel_script import (
            restart_graphic_novel_from_substep,
        )
        mock_load.return_value = "Graphic novel template {input_json}"
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        pack, _, _ = self._make_pack(job)
        novel = self._full_run(mock_anthropic, job, pack)

        # Simulate premise_scoring having failed validation on a later attempt:
        # its artifact stays on disk but the COMPLETED log is gone.
        GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.COMPLETED,
            output_data__substep='premise_scoring',
        ).delete()
        mock_anthropic.reset_mock()
        mock_anthropic.side_effect = ValueError('no LLM call expected')

        with pytest.raises(ValueError, match='no COMPLETED log'):
            restart_graphic_novel_from_substep(
                job, pack.id, 'cloze_generation', WORD_LOOKUP_RESPONSE['words'],
            )

        assert mock_anthropic.call_count == 0
        # Validation ran before the delete: the candidate is untouched.
        assert GraphicNovel.objects.filter(id=novel.id).exists()
        assert ClozeItem.objects.filter(novel=novel).count() == 2

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_half_persisted_candidate_regenerated_on_rerun(
        self, mock_load, mock_anthropic,
    ):
        """A candidate with pages but no staged cloze (pre-atomic half persist)
        must be regenerated, not skipped as complete."""
        mock_load.return_value = "Graphic novel template {input_json}"
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        pack, _, _ = self._make_pack(job)
        novel = self._full_run(mock_anthropic, job, pack)
        novel.cloze_items.all().delete()

        # All substeps have COMPLETED logs, so the rerun resumes at the final
        # script substep (1 LLM call) and re-persists the candidate.
        mock_anthropic.reset_mock()
        mock_anthropic.side_effect = [GRAPHIC_NOVEL_RESPONSE]
        _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])

        assert mock_anthropic.call_count == 1
        new_novel = GraphicNovel.objects.get(pack=pack)
        assert new_novel.id != novel.id
        assert new_novel.cloze_items.count() == 2

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_selected_candidate_never_deleted_by_rerun(self, mock_load, mock_anthropic):
        """A published (selected) candidate is skipped even when it looks
        incomplete — a resume must never unpublish student content."""
        mock_load.return_value = "Graphic novel template {input_json}"
        mock_anthropic.side_effect = ValueError('no LLM call expected')
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        pack, _, _ = self._make_pack(job)
        novel = GraphicNovel.objects.create(
            pack=pack, candidate_index=0, is_selected=True,
            title='Published', synopsis='s', style_prompt='x', reading_level=600,
        )

        _step_graphic_novel_script(job, [pack], WORD_LOOKUP_RESPONSE['words'])

        assert mock_anthropic.call_count == 0
        assert GraphicNovel.objects.filter(id=novel.id).exists()

    def test_persist_rolls_back_when_cloze_misses_a_pack_word(self):
        """Persistence is atomic and every pack word needs a staged cloze item:
        a dropped word raises and leaves no half-persisted candidate behind."""
        from vocabulary.services.generation.graphic_novel_script import (
            _persist_candidate_novel,
        )
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        pack, _, _ = self._make_pack(job)
        cloze_missing_discover = {
            'cloze_items': [GRAPHIC_NOVEL_CLOZE_RESPONSE['cloze_items'][0]],
        }

        with pytest.raises(ValueError, match='discover'):
            _persist_candidate_novel(
                pack, 0, GRAPHIC_NOVEL_RESPONSE,
                {'vault_framing': False, 'page_count': 5}, 600,
                [{'term': 'bright'}, {'term': 'discover'}],
                cloze_missing_discover,
            )

        assert not GraphicNovel.objects.filter(pack=pack).exists()
        assert not GraphicNovelPage.objects.filter(novel__pack=pack).exists()
        assert not ClozeItem.objects.filter(pack=pack).exists()

    def test_persist_matches_cloze_item_by_correct_answer(self):
        """The validator accepts an item via term OR correct_answer, so the
        persist join must too (LLM term labels vary)."""
        from vocabulary.services.generation.graphic_novel_script import (
            _persist_candidate_novel,
        )
        job = GenerationJobFactory(input_words=['bright'])
        word = WordFactory(text='bright')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word, order=0)
        cloze = {
            'cloze_items': [{
                'term': 'shining brightly',
                'sentence_text': 'The sun is _______.',
                'correct_answer': 'bright',
                'distractors': ['dark', 'quiet'],
            }],
        }

        novel = _persist_candidate_novel(
            pack, 0, GRAPHIC_NOVEL_RESPONSE,
            {'vault_framing': False, 'page_count': 5}, 600,
            [{'term': 'bright'}], cloze,
        )

        staged = ClozeItem.objects.get(novel=novel)
        assert staged.word == word

