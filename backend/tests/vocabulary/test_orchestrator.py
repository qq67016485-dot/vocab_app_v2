"""Tests for the pipeline orchestrator (run_full_pipeline + restart)."""
import pytest
from unittest.mock import patch, MagicMock

from vocabulary.models import (
    Question, WordPackItem,
    GraphicNovel,
    GenerationJob, GenerationJobLog,
)
from vocabulary.services.generation_pipeline_service import (
    BACKUP_MODEL,
    DEFAULT_MODEL,
    restart_pipeline_from_step,
    run_full_pipeline,
    _run_step,
)
from tests.factories import (
    AdminUserFactory, WordFactory, WordDefinitionFactory,
    WordSetFactory, GenerationJobFactory,
    QuestionFactory, WordPackFactory,
)
from tests.vocabulary.generation_fixtures import WORD_LOOKUP_RESPONSE


@pytest.mark.django_db
class TestRunFullPipeline:
    """Tests for run_full_pipeline — the main orchestrator."""

    @patch('vocabulary.services.generation.orchestrator._log_step')
    @patch('vocabulary.services.generation.orchestrator._execute_step')
    def test_retries_default_model_then_uses_backup_model(self, mock_execute, mock_log_step):
        job = GenerationJobFactory(input_words=['bright'])
        expected_result = ([MagicMock()], [{'term': 'bright'}], [MagicMock()])
        mock_execute.side_effect = [
            Exception('temporary failure'),
            Exception('still failing'),
            expected_result,
        ]

        result = _run_step(
            job, GenerationJobLog.Step.WORD_LOOKUP, [], [], [],
        )

        assert result == expected_result
        attempted_models = [call.kwargs['site_config']['model'] for call in mock_execute.call_args_list]
        assert attempted_models == [DEFAULT_MODEL, DEFAULT_MODEL, BACKUP_MODEL]
        assert mock_log_step.call_count == 2

    @patch('vocabulary.services.generation.orchestrator._step_graphic_novel_images')
    @patch('vocabulary.services.generation.orchestrator._step_graphic_novel_script')
    @patch('vocabulary.services.generation.orchestrator._step_generate_primers')
    @patch('vocabulary.services.generation.orchestrator._step_auto_create_packs')
    @patch('vocabulary.services.generation.orchestrator._step_generate_questions')
    @patch('vocabulary.services.generation.orchestrator._step_generate_translations')
    @patch('vocabulary.services.generation.orchestrator._step_dedup_and_persist')
    @patch('vocabulary.services.generation.orchestrator._step_word_lookup')
    def test_runs_all_steps_in_order(
        self, mock_lookup, mock_dedup, mock_translate, mock_questions,
        mock_packs, mock_primers, mock_script, mock_novel_images,
    ):
        word = WordFactory(text='bright')
        mock_lookup.return_value = WORD_LOOKUP_RESPONSE['words']
        mock_dedup.return_value = [word]
        mock_packs.return_value = [MagicMock()]
        job = GenerationJobFactory(input_words=['bright'])

        run_full_pipeline(job.id)

        mock_lookup.assert_called_once()
        mock_dedup.assert_called_once()
        mock_translate.assert_called_once()
        mock_questions.assert_called_once()
        mock_packs.assert_called_once()
        mock_primers.assert_called_once()
        mock_script.assert_called_once()
        mock_novel_images.assert_called_once()

    @patch('vocabulary.services.generation.orchestrator._step_graphic_novel_images')
    @patch('vocabulary.services.generation.orchestrator._step_graphic_novel_script')
    @patch('vocabulary.services.generation.orchestrator._step_generate_primers')
    @patch('vocabulary.services.generation.orchestrator._step_auto_create_packs')
    @patch('vocabulary.services.generation.orchestrator._step_generate_questions')
    @patch('vocabulary.services.generation.orchestrator._step_generate_translations')
    @patch('vocabulary.services.generation.orchestrator._step_dedup_and_persist')
    @patch('vocabulary.services.generation.orchestrator._step_word_lookup')
    def test_sets_job_status_to_running_then_completed(
        self, mock_lookup, mock_dedup, mock_translate, mock_questions,
        mock_packs, mock_primers, mock_script, mock_novel_images,
    ):
        mock_lookup.return_value = []
        mock_dedup.return_value = []
        mock_packs.return_value = []
        job = GenerationJobFactory(input_words=['bright'])

        run_full_pipeline(job.id)

        job.refresh_from_db()
        assert job.status == GenerationJob.Status.COMPLETED
        assert job.completed_at is not None

    @patch('vocabulary.services.generation.orchestrator._step_word_lookup')
    def test_sets_job_status_to_failed_on_error(self, mock_lookup):
        mock_lookup.side_effect = Exception("LLM is down")
        job = GenerationJobFactory(input_words=['bright'])

        run_full_pipeline(job.id)

        job.refresh_from_db()
        assert job.status == GenerationJob.Status.FAILED
        assert 'LLM is down' in job.error_message

    @patch('vocabulary.services.generation.orchestrator._step_graphic_novel_images')
    @patch('vocabulary.services.generation.orchestrator._step_graphic_novel_script')
    @patch('vocabulary.services.generation.orchestrator._step_generate_primers')
    @patch('vocabulary.services.generation.orchestrator._step_auto_create_packs')
    @patch('vocabulary.services.generation.orchestrator._step_generate_questions')
    @patch('vocabulary.services.generation.orchestrator._step_generate_translations')
    @patch('vocabulary.services.generation.orchestrator._step_dedup_and_persist')
    @patch('vocabulary.services.generation.orchestrator._step_word_lookup')
    def test_passes_words_data_between_steps(
        self, mock_lookup, mock_dedup, mock_translate, mock_questions,
        mock_packs, mock_primers, mock_script, mock_novel_images,
    ):
        words_data = WORD_LOOKUP_RESPONSE['words']
        word_objs = [WordFactory(text='bright'), WordFactory(text='discover')]
        packs = [MagicMock()]

        mock_lookup.return_value = words_data
        mock_dedup.return_value = word_objs
        mock_packs.return_value = packs

        job = GenerationJobFactory(input_words=['bright', 'discover'])
        run_full_pipeline(job.id)

        # Verify data flows correctly between steps
        mock_dedup.assert_called_once_with(job, words_data)
        # Step functions now receive site_config dicts instead of model strings
        translate_call = mock_translate.call_args
        assert translate_call.args[:3] == (job, word_objs, words_data)
        assert translate_call.args[3]['model'] == DEFAULT_MODEL
        questions_call = mock_questions.call_args
        assert questions_call.args[:3] == (job, word_objs, words_data)
        assert questions_call.args[3]['model'] == DEFAULT_MODEL
        packs_call = mock_packs.call_args
        assert packs_call.args[:3] == (job, word_objs, words_data)
        assert packs_call.args[3]['model'] == DEFAULT_MODEL
        primers_call = mock_primers.call_args
        assert primers_call.args[:3] == (job, word_objs, words_data)
        assert primers_call.args[3]['model'] == DEFAULT_MODEL
        mock_script.assert_called_once_with(job, packs, words_data)
        mock_novel_images.assert_called_once_with(job, packs)


@pytest.mark.django_db
class TestRestartPipelineFromStep:
    @patch('vocabulary.services.generation.orchestrator._run_step')
    def test_reruns_only_selected_step_when_subsequent_disabled(self, mock_run_step):
        admin = AdminUserFactory()
        word_set = WordSetFactory(creator=admin)
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        word_set.words.add(word)
        job = GenerationJobFactory(
            word_set=word_set,
            created_by=admin,
            input_words=['bright'],
            status=GenerationJob.Status.COMPLETED,
        )
        QuestionFactory(
            word=word,
            generation_job=job,
            question_type=Question.QuestionType.DEFINITION_MC_SINGLE,
        )
        mock_run_step.return_value = ([word], [{'term': 'bright'}], [])

        with patch('vocabulary.services.generation.helpers.close_old_connections'):
            restart_pipeline_from_step(
                job.id,
                GenerationJobLog.Step.QUESTION_GEN,
                include_subsequent=False,
            )

        mock_run_step.assert_called_once()
        assert mock_run_step.call_args.args[1] == GenerationJobLog.Step.QUESTION_GEN
        assert not Question.objects.filter(
            generation_job=job,
            question_type=Question.QuestionType.DEFINITION_MC_SINGLE,
        ).exists()
        job.refresh_from_db()
        assert job.status == GenerationJob.Status.COMPLETED
        assert job.last_completed_step == GenerationJobLog.Step.QUESTION_GEN

    @patch('vocabulary.services.generation.orchestrator._run_step')
    def test_reruns_selected_and_subsequent_steps(self, mock_run_step):
        admin = AdminUserFactory()
        word_set = WordSetFactory(creator=admin)
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        word_set.words.add(word)
        pack = WordPackFactory(word_set=word_set)
        WordPackItem.objects.create(pack=pack, word=word, order=0)
        GraphicNovel.objects.create(
            pack=pack,
            title='Old Novel',
            synopsis='Old synopsis.',
            style_prompt='Old style.',
            reading_level=650,
        )
        job = GenerationJobFactory(
            word_set=word_set,
            created_by=admin,
            input_words=['bright'],
            status=GenerationJob.Status.COMPLETED,
        )
        mock_run_step.return_value = ([word], [{'term': 'bright'}], [pack])

        with patch('vocabulary.services.generation.helpers.close_old_connections'):
            restart_pipeline_from_step(
                job.id,
                GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
                include_subsequent=True,
            )

        attempted_steps = [call.args[1] for call in mock_run_step.call_args_list]
        assert attempted_steps == [
            GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
        ]
        assert not GraphicNovel.objects.filter(pack=pack).exists()

        job.refresh_from_db()
        assert job.status == GenerationJob.Status.COMPLETED
        assert job.last_completed_step == GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES
