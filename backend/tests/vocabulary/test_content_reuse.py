"""Tests for cross-wordset content reuse (services/generation/content_reuse.py).

Word-level pipeline steps (QUESTION_GEN, SENTENCE_WRITE_GEN, PRIMER_GEN,
TRANSLATION) skip the LLM call for a word when a prior job inside the Lexile
reuse window (CONTENT_REUSE_LEXILE_TOLERANCE, default +/-15% of the content
Lexile) already generated that content. Pack-level steps never reuse.
"""
import pytest
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType

from vocabulary.models import (
    Question, Translation, WordDefinition,
    GenerationJob, GenerationJobLog,
)
from vocabulary.services.generation.content_reuse import (
    content_lexile_for_target,
    definition_has_translations,
    find_reusable_primer_words,
    find_reusable_question_words,
    find_reusable_sentence_write_words,
    resolve_definition,
)
from vocabulary.services.generation.step_sentence_write import (
    _step_generate_sentence_write,
)
from vocabulary.services.generation_pipeline_service import (
    _step_generate_primers,
    _step_generate_questions,
    _step_generate_translations,
)
from tests.factories import (
    WordFactory, WordDefinitionFactory, PrimerCardContentFactory,
    QuestionFactory, GenerationJobFactory, MasteryLevelFactory,
)
from tests.vocabulary.generation_fixtures import PRIMER_RESPONSE

# Default job: target_lexile 650 -> content lexile 552, reuse window
# +/-15% -> [469.2, 634.8]. target 640 -> 544 (in), 750 -> 637 (out),
# 550 -> 467 (out).
THIS_CL = content_lexile_for_target(650)  # 552
IN_WINDOW_CL = content_lexile_for_target(640)  # 544
OUT_WINDOW_CL = content_lexile_for_target(750)  # 637


def _words_data(*terms):
    return [
        {
            'term': term,
            'part_of_speech': 'noun',
            'definition': f'Definition of {term}',
            'example_sentence': f'{term} is used in a sentence.',
        }
        for term in terms
    ]


def _seed_question_coverage(word, job, levels=(1, 2, 3, 4, 5), per_level=3):
    """Create ``per_level`` choice questions per level for ``word`` from ``job``."""
    for level in levels:
        for _ in range(per_level):
            q = QuestionFactory(word=word, generation_job=job)
            q.suitable_levels.add(level)


@pytest.mark.django_db
class TestFindReusableQuestionWords:
    @pytest.fixture(autouse=True)
    def seed_levels(self):
        for level_id in range(1, 6):
            MasteryLevelFactory(level_id=level_id)

    def test_full_coverage_in_window_is_reusable(self):
        authoring = GenerationJobFactory(target_lexile=640)
        word = WordFactory(text='bright')
        _seed_question_coverage(word, authoring)

        assert find_reusable_question_words([word], THIS_CL) == {word.id}

    def test_missing_level_is_not_covered(self):
        authoring = GenerationJobFactory(target_lexile=640)
        word = WordFactory(text='bright')
        _seed_question_coverage(word, authoring, levels=(1, 2, 3, 4))

        assert find_reusable_question_words([word], THIS_CL) == set()

    def test_underfilled_level_is_not_covered(self):
        """A truncated authoring run (2 questions at L5, not 3) never counts."""
        authoring = GenerationJobFactory(target_lexile=640)
        word = WordFactory(text='bright')
        _seed_question_coverage(word, authoring, levels=(1, 2, 3, 4))
        _seed_question_coverage(word, authoring, levels=(5,), per_level=2)

        assert find_reusable_question_words([word], THIS_CL) == set()

    def test_out_of_window_job_is_not_covered(self):
        authoring = GenerationJobFactory(target_lexile=750)  # content 637
        word = WordFactory(text='bright')
        _seed_question_coverage(word, authoring)

        assert find_reusable_question_words([word], THIS_CL) == set()

    def test_null_generation_job_is_never_covered(self):
        word = WordFactory(text='bright')
        _seed_question_coverage(word, None)

        assert find_reusable_question_words([word], THIS_CL) == set()

    def test_sentence_write_questions_do_not_count_toward_coverage(self):
        authoring = GenerationJobFactory(target_lexile=640)
        word = WordFactory(text='bright')
        _seed_question_coverage(word, authoring, levels=(1, 2, 3))
        for level, q_type in ((4, Question.QuestionType.SENTENCE_WRITE_GUIDED),
                              (5, Question.QuestionType.SENTENCE_WRITE_OPEN)):
            for _ in range(3):
                q = QuestionFactory(
                    word=word, generation_job=authoring,
                    question_type=q_type,
                )
                q.suitable_levels.add(level)

        assert find_reusable_question_words([word], THIS_CL) == set()


@pytest.mark.django_db
class TestFindReusableSentenceWriteWords:
    @pytest.fixture(autouse=True)
    def seed_levels(self):
        for level_id in range(1, 6):
            MasteryLevelFactory(level_id=level_id)

    def _seed_sw(self, word, job, q_type, levels):
        q = QuestionFactory(word=word, generation_job=job, question_type=q_type)
        q.suitable_levels.add(*levels)
        return q

    def test_guided_only_mode_reuses_guided_with_both_levels(self):
        # This job cl 552 <= 600 -> guided-only; authoring 544, same mode.
        authoring = GenerationJobFactory(target_lexile=640)
        word = WordFactory(text='bright')
        self._seed_sw(word, authoring, Question.QuestionType.SENTENCE_WRITE_GUIDED, (4, 5))

        reusable = find_reusable_sentence_write_words([word], THIS_CL, guided_only=True)
        assert reusable[Question.QuestionType.SENTENCE_WRITE_GUIDED] == {word.id}

    def test_guided_only_mode_requires_l5_attachment(self):
        """A GUIDED row attached only to L4 came from an open-mode job and
        cannot serve the guided-only L5 slot."""
        authoring = GenerationJobFactory(target_lexile=640)
        word = WordFactory(text='bright')
        self._seed_sw(word, authoring, Question.QuestionType.SENTENCE_WRITE_GUIDED, (4,))

        reusable = find_reusable_sentence_write_words([word], THIS_CL, guided_only=True)
        assert reusable[Question.QuestionType.SENTENCE_WRITE_GUIDED] == set()

    def test_cross_mode_job_is_excluded_even_in_window(self):
        # Authoring cl = int(740*.85) = 629: in window of 552 but open-mode.
        authoring = GenerationJobFactory(target_lexile=740)
        word = WordFactory(text='bright')
        self._seed_sw(word, authoring, Question.QuestionType.SENTENCE_WRITE_GUIDED, (4,))

        reusable = find_reusable_sentence_write_words([word], THIS_CL, guided_only=True)
        assert reusable[Question.QuestionType.SENTENCE_WRITE_GUIDED] == set()

    def test_open_mode_reuses_both_variants(self):
        # Open mode: this cl 765 (target 900); authoring cl 748 (target 880).
        authoring = GenerationJobFactory(target_lexile=880)
        word = WordFactory(text='bright')
        self._seed_sw(word, authoring, Question.QuestionType.SENTENCE_WRITE_GUIDED, (4,))
        self._seed_sw(word, authoring, Question.QuestionType.SENTENCE_WRITE_OPEN, (5,))

        reusable = find_reusable_sentence_write_words([word], 765, guided_only=False)
        assert reusable[Question.QuestionType.SENTENCE_WRITE_GUIDED] == {word.id}
        assert reusable[Question.QuestionType.SENTENCE_WRITE_OPEN] == {word.id}

    def test_open_mode_without_open_row_is_not_covered(self):
        authoring = GenerationJobFactory(target_lexile=880)
        word = WordFactory(text='bright')
        self._seed_sw(word, authoring, Question.QuestionType.SENTENCE_WRITE_GUIDED, (4,))

        reusable = find_reusable_sentence_write_words([word], 765, guided_only=False)
        assert reusable[Question.QuestionType.SENTENCE_WRITE_GUIDED] == {word.id}
        assert reusable[Question.QuestionType.SENTENCE_WRITE_OPEN] == set()


@pytest.mark.django_db
class TestFindReusablePrimerWords:
    def test_in_window_primer_is_reusable(self):
        word = WordFactory(text='bright')
        PrimerCardContentFactory(word=word, generated_content_lexile=IN_WINDOW_CL)

        assert find_reusable_primer_words([word], THIS_CL) == {word.id}

    def test_out_of_window_primer_is_not_reusable(self):
        word = WordFactory(text='bright')
        PrimerCardContentFactory(word=word, generated_content_lexile=OUT_WINDOW_CL)

        assert find_reusable_primer_words([word], THIS_CL) == set()

    def test_unstamped_legacy_primer_is_not_reusable(self):
        word = WordFactory(text='bright')
        PrimerCardContentFactory(word=word, generated_content_lexile=None)

        assert find_reusable_primer_words([word], THIS_CL) == set()


@pytest.mark.django_db
class TestDefinitionReuseHelpers:
    def _translation(self, definition, field_name, language='zh-CN'):
        Translation.objects.create(
            content_type=ContentType.objects.get_for_model(WordDefinition),
            object_id=definition.id,
            field_name=field_name,
            language=language,
            translated_text='译文',
        )

    def test_definition_has_translations_requires_all_fields(self):
        definition = WordDefinitionFactory(example_sentence='An example.')
        assert not definition_has_translations(definition, 'zh-CN')

        self._translation(definition, 'definition_text')
        assert not definition_has_translations(definition, 'zh-CN')

        self._translation(definition, 'example_sentence')
        assert definition_has_translations(definition, 'zh-CN')

    def test_definition_without_example_needs_only_definition_translation(self):
        definition = WordDefinitionFactory(example_sentence='')
        self._translation(definition, 'definition_text')

        assert definition_has_translations(definition, 'zh-CN')

    def test_other_language_does_not_count(self):
        definition = WordDefinitionFactory(example_sentence='')
        self._translation(definition, 'definition_text', language='zh-CN')

        assert not definition_has_translations(definition, 'es')

    def test_resolve_definition_matches_snapshot_text(self):
        word = WordFactory(text='bank')
        other = WordDefinitionFactory(
            word=word, definition_text='A financial institution.', lexile_score=400,
        )
        matched = WordDefinitionFactory(
            word=word, definition_text='The side of a river.', lexile_score=600,
        )

        assert resolve_definition(word, {'definition': 'The side of a river.'}) == matched
        # Unknown/absent text falls back to the first (lowest-Lexile) definition.
        assert resolve_definition(word, {'definition': 'No such text.'}) == other
        assert resolve_definition(word, {}) == other


@pytest.mark.django_db
class TestQuestionStepReuse:
    @pytest.fixture(autouse=True)
    def seed_levels(self):
        for level_id in range(1, 6):
            MasteryLevelFactory(level_id=level_id)

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_fully_reused_word_skips_llm(self, mock_load, mock_gemini):
        mock_load.return_value = 'Question gen template {input_json}'
        authoring = GenerationJobFactory(target_lexile=640)
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        _seed_question_coverage(word, authoring)
        job = GenerationJobFactory(input_words=['bright'])  # target 650

        _step_generate_questions(job, [word], _words_data('bright'))

        mock_gemini.assert_not_called()
        assert Question.objects.filter(generation_job=job).count() == 0
        log = GenerationJobLog.objects.get(
            job=job, step=GenerationJobLog.Step.QUESTION_GEN,
        )
        assert log.output_data['words_reused'] == 1

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_mixed_batch_sends_only_uncovered_word(self, mock_load, mock_gemini):
        mock_load.return_value = 'Question gen template {input_json}'
        authoring = GenerationJobFactory(target_lexile=640)
        reused_word = WordFactory(text='alpha')
        WordDefinitionFactory(word=reused_word)
        _seed_question_coverage(reused_word, authoring)
        new_word = WordFactory(text='beta')
        WordDefinitionFactory(word=new_word)
        mock_gemini.return_value = {
            'generated_question_sets': [{
                'term': 'beta',
                'questions': [{
                    'question_type': 'DEFINITION_MC_SINGLE',
                    'question_text': "What does 'beta' mean?",
                    'options': ['A', 'B', 'C', 'D'],
                    'correct_answers': ['A'],
                    'explanation': 'beta explanation.',
                    'example_sentence': 'The beta example.',
                    'lexile_score': 600,
                }],
            }],
        }
        job = GenerationJobFactory(input_words=['alpha', 'beta'])

        _step_generate_questions(
            job, [reused_word, new_word], _words_data('alpha', 'beta'),
        )

        assert mock_gemini.call_count == 1
        prompt_sent = mock_gemini.call_args[0][1]
        assert 'beta' in prompt_sent
        assert 'alpha' not in prompt_sent
        assert Question.objects.filter(generation_job=job, word=new_word).count() == 1
        assert Question.objects.filter(generation_job=job, word=reused_word).count() == 0

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_allow_reuse_false_regenerates(self, mock_load, mock_gemini):
        """The manual restart path passes allow_reuse=False: reusable coverage
        from another job must not defeat an explicit rerun."""
        mock_load.return_value = 'Question gen template {input_json}'
        authoring = GenerationJobFactory(target_lexile=640)
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        _seed_question_coverage(word, authoring)
        mock_gemini.return_value = {
            'generated_question_sets': [{
                'term': 'bright',
                'questions': [{
                    'question_type': 'DEFINITION_MC_SINGLE',
                    'question_text': "What does 'bright' mean?",
                    'options': ['A', 'B', 'C', 'D'],
                    'correct_answers': ['A'],
                    'explanation': 'bright explanation.',
                    'example_sentence': 'The bright example.',
                    'lexile_score': 600,
                }],
            }],
        }
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_questions(job, [word], _words_data('bright'), allow_reuse=False)

        assert mock_gemini.call_count == 1
        assert Question.objects.filter(generation_job=job, word=word).count() == 1


@pytest.mark.django_db
class TestSentenceWriteStepReuse:
    @pytest.fixture(autouse=True)
    def seed_levels(self):
        for level_id in range(1, 6):
            MasteryLevelFactory(level_id=level_id)

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_reused_word_skips_llm_guided_only(self, mock_load, mock_gemini):
        mock_load.return_value = 'SW template'
        authoring = GenerationJobFactory(target_lexile=640)
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        q = QuestionFactory(
            word=word, generation_job=authoring,
            question_type=Question.QuestionType.SENTENCE_WRITE_GUIDED,
        )
        q.suitable_levels.add(4, 5)
        job = GenerationJobFactory(input_words=['bright'])  # cl 552 -> guided-only

        _step_generate_sentence_write(job, [word], _words_data('bright'))

        mock_gemini.assert_not_called()
        assert Question.objects.filter(generation_job=job).count() == 0

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_open_mode_generates_only_missing_variant(self, mock_load, mock_gemini):
        mock_load.return_value = 'SW template'
        authoring = GenerationJobFactory(target_lexile=880)  # cl 748, open mode
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        q = QuestionFactory(
            word=word, generation_job=authoring,
            question_type=Question.QuestionType.SENTENCE_WRITE_GUIDED,
        )
        q.suitable_levels.add(4)
        mock_gemini.return_value = {
            'sentence_tasks': [{
                'term': 'bright',
                'scenario': 'Write about a bright idea.',
                'model_sentence': 'The bright idea worked.',
                'lexile_score': 760,
            }],
        }
        job = GenerationJobFactory(input_words=['bright'], target_lexile=900)

        _step_generate_sentence_write(job, [word], _words_data('bright'))

        # GUIDED was reused; exactly one LLM call, for the OPEN variant.
        assert mock_gemini.call_count == 1
        assert 'bright' in mock_gemini.call_args[0][2]
        open_q = Question.objects.get(
            generation_job=job, question_type=Question.QuestionType.SENTENCE_WRITE_OPEN,
        )
        assert list(open_q.suitable_levels.values_list('level_id', flat=True)) == [5]


@pytest.mark.django_db
class TestPrimerStepReuse:
    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_in_window_primer_skips_llm_and_is_kept(self, mock_load, mock_gemini):
        mock_load.return_value = 'Primer {target_lexile}'
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        primer = PrimerCardContentFactory(
            word=word, kid_friendly_definition='kept definition',
            generated_content_lexile=IN_WINDOW_CL,
        )
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_primers(job, [word], _words_data('bright'))

        mock_gemini.assert_not_called()
        primer.refresh_from_db()
        assert primer.kid_friendly_definition == 'kept definition'

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_out_of_window_primer_is_regenerated_and_restamped(
        self, mock_load, mock_gemini,
    ):
        mock_load.return_value = 'Primer {target_lexile}'
        mock_gemini.return_value = PRIMER_RESPONSE
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        primer = PrimerCardContentFactory(
            word=word, kid_friendly_definition='stale definition',
            generated_content_lexile=OUT_WINDOW_CL,
        )
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_primers(job, [word], _words_data('bright'))

        assert mock_gemini.call_count == 1
        primer.refresh_from_db()
        assert primer.kid_friendly_definition == 'Something that shines a lot.'
        assert primer.generated_content_lexile == THIS_CL

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_fresh_generation_stamps_provenance(self, mock_load, mock_gemini):
        mock_load.return_value = 'Primer {target_lexile}'
        mock_gemini.return_value = PRIMER_RESPONSE
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_primers(job, [word], _words_data('bright'))

        assert mock_gemini.call_count == 1
        assert word.primer_content.generated_content_lexile == THIS_CL


@pytest.mark.django_db
class TestTranslationStepReuse:
    def _translation(self, definition, field_name):
        Translation.objects.create(
            content_type=ContentType.objects.get_for_model(WordDefinition),
            object_id=definition.id,
            field_name=field_name,
            language='zh-CN',
            translated_text='已有翻译',
        )

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_already_translated_word_skips_llm(self, mock_load, mock_gemini):
        mock_load.return_value = 'Translate {items_to_translate} into {target_language}'
        word = WordFactory(text='bright')
        definition = WordDefinitionFactory(
            word=word, definition_text='Definition of bright',
        )
        self._translation(definition, 'definition_text')
        self._translation(definition, 'example_sentence')
        job = GenerationJobFactory(input_words=['bright'], target_language='zh-CN')

        _step_generate_translations(job, [word], _words_data('bright'))

        mock_gemini.assert_not_called()

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_only_untranslated_words_are_sent(self, mock_load, mock_gemini):
        mock_load.return_value = 'Translate {items_to_translate} into {target_language}'
        done_word = WordFactory(text='alpha')
        done_def = WordDefinitionFactory(
            word=done_word, definition_text='Definition of alpha',
        )
        self._translation(done_def, 'definition_text')
        self._translation(done_def, 'example_sentence')
        new_word = WordFactory(text='beta')
        WordDefinitionFactory(word=new_word, definition_text='Definition of beta')
        mock_gemini.return_value = {
            'translations': [
                {
                    'term': 'beta',
                    'source_field': 'definition_text',
                    'translated_text': 'beta 释义',
                },
                {
                    'term': 'beta',
                    'source_field': 'example_sentence',
                    'translated_text': 'beta 例句',
                },
            ],
        }
        job = GenerationJobFactory(input_words=['alpha', 'beta'], target_language='zh-CN')

        _step_generate_translations(
            job, [done_word, new_word], _words_data('alpha', 'beta'),
        )

        assert mock_gemini.call_count == 1
        prompt_sent = mock_gemini.call_args[0][1]
        assert 'beta' in prompt_sent
        assert 'alpha' not in prompt_sent
        assert Translation.objects.filter(object_id=new_word.definitions.first().id).count() == 2

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_translation_attaches_to_the_matched_definition(self, mock_load, mock_gemini):
        """A shared word with several definitions must attach the translation
        to the definition this job's snapshot describes, not the lowest-Lexile
        one (definitions.first())."""
        mock_load.return_value = 'Translate {items_to_translate} into {target_language}'
        word = WordFactory(text='bank')
        WordDefinitionFactory(
            word=word, definition_text='A financial institution.', lexile_score=400,
        )
        river = WordDefinitionFactory(
            word=word, definition_text='The side of a river.', lexile_score=600,
        )
        mock_gemini.return_value = {
            'translations': [{
                'term': 'bank',
                'source_field': 'definition_text',
                'translated_text': '河岸',
            }],
        }
        job = GenerationJobFactory(input_words=['bank'], target_language='zh-CN')

        _step_generate_translations(
            job, [word], [{
                'term': 'bank',
                'part_of_speech': 'noun',
                'definition': 'The side of a river.',
                'example_sentence': '',
            }],
        )

        translation = Translation.objects.get()
        assert translation.object_id == river.id
