"""Tests for the graphic novel image generation step."""
import pytest
from unittest.mock import patch

from vocabulary.models import (
    WordPack,
    GraphicNovel, GraphicNovelPage,
    GenerationJob, GenerationJobLog,
)
from vocabulary.services.generation_pipeline_service import (
    _step_graphic_novel_images,
)
from tests.factories import GenerationJobFactory


@pytest.mark.django_db
class TestStepGraphicNovelImages:
    @patch('vocabulary.services.llm_service.call_openai_image')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_creates_page_image(self, mock_load, mock_image):
        mock_load.return_value = "Page {page_number} {panel_details}"
        mock_image.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        job = GenerationJobFactory(input_words=['bright'])
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        novel = GraphicNovel.objects.create(
            pack=pack,
            title='Test Novel',
            synopsis='A test synopsis.',
            style_prompt='Readable comic art.',
            reading_level=650,
        )
        page = GraphicNovelPage.objects.create(
            novel=novel,
            page_number=1,
            panel_count=1,
            layout_description='Single splash page.',
            panel_descriptions=[{'panel_number': 1, 'narration': 'Bright!'}],
            vocab_words_used=['bright'],
        )

        _step_graphic_novel_images(job, [pack])

        page.refresh_from_db()
        assert page.image
        assert page.prompt_used
        assert page.generation_status == GraphicNovelPage.GenerationStatus.COMPLETED
        assert page.generation_attempts == 1
        assert page.generation_error == ''
        mock_image.assert_called_once()
        assert mock_image.call_args.kwargs['size'] == '1792x1024'

    @patch('vocabulary.services.llm_service.call_openai_image')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_stops_on_page_failure_after_retry(self, mock_load, mock_image):
        mock_load.return_value = "Page {page_number} {panel_details}"
        mock_image.side_effect = [Exception('API error'), Exception('API error again')]
        job = GenerationJobFactory(input_words=['bright'])
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        novel = GraphicNovel.objects.create(
            pack=pack,
            title='Test Novel',
            synopsis='A test synopsis.',
            style_prompt='Readable comic art.',
            reading_level=650,
        )
        GraphicNovelPage.objects.create(novel=novel, page_number=1, panel_count=1)
        GraphicNovelPage.objects.create(novel=novel, page_number=2, panel_count=1)

        with pytest.raises(RuntimeError, match='failed for 1 page'):
            _step_graphic_novel_images(job, [pack])

        assert GraphicNovelPage.objects.exclude(image='').count() == 0
        failed_page = GraphicNovelPage.objects.get(
            generation_status=GraphicNovelPage.GenerationStatus.FAILED,
        )
        assert failed_page.page_number == 1
        assert failed_page.generation_attempts == 2
        assert 'API error again' in failed_page.generation_error
        pending_page = GraphicNovelPage.objects.get(page_number=2)
        assert pending_page.generation_status == GraphicNovelPage.GenerationStatus.PENDING
        assert GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
            status=GenerationJob.Status.FAILED,
        ).exists()

    @patch('vocabulary.services.llm_service.call_openai_image')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_resume_skips_completed_pages_and_retries_missing_pages(self, mock_load, mock_image):
        mock_load.return_value = "Page {page_number} {panel_details}"
        mock_image.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        job = GenerationJobFactory(input_words=['bright'])
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        novel = GraphicNovel.objects.create(
            pack=pack,
            title='Test Novel',
            synopsis='A test synopsis.',
            style_prompt='Readable comic art.',
            reading_level=650,
        )
        completed_page = GraphicNovelPage.objects.create(
            novel=novel,
            page_number=1,
            image='graphic_novels/existing.png',
            generation_status=GraphicNovelPage.GenerationStatus.COMPLETED,
            panel_count=1,
        )
        retry_page = GraphicNovelPage.objects.create(
            novel=novel,
            page_number=2,
            generation_status=GraphicNovelPage.GenerationStatus.FAILED,
            generation_attempts=1,
            generation_error='Previous failure',
            panel_count=1,
        )

        _step_graphic_novel_images(job, [pack])

        completed_page.refresh_from_db()
        retry_page.refresh_from_db()
        assert completed_page.generation_attempts == 0
        assert retry_page.image
        assert retry_page.generation_status == GraphicNovelPage.GenerationStatus.COMPLETED
        assert retry_page.generation_attempts == 2
        mock_image.assert_called_once()

    @patch('vocabulary.services.llm_service.call_openai_image')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_image_prompt_uses_page_characters_and_vault_context(self, mock_load, mock_image):
        mock_load.return_value = (
            "Page {page_number}\nCharacters:\n{characters}\nSetting:\n{setting_context}\n"
            "Panels:\n{panel_details}"
        )
        mock_image.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        job = GenerationJobFactory(input_words=['bright'])
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        novel = GraphicNovel.objects.create(
            pack=pack,
            title='Test Novel',
            synopsis='A test synopsis.',
            characters=[
                {'name': 'Leo', 'visual_description': 'Leo wears a bright red hoodie.'},
                {'name': 'Amara', 'visual_description': 'Amara wears a purple cloak.'},
            ],
            metadata={
                'away_team': ['Leo', 'Amara'],
                'age_band': '9yo',
                'vault_framing': True,
                'review_artifact_type': 'Vault clue board',
            },
            style_prompt='Readable comic art.',
            reading_level=650,
        )
        vault_page = GraphicNovelPage.objects.create(
            novel=novel,
            page_number=1,
            panel_count=1,
            panel_descriptions=[{'panel_number': 1, 'narration': 'Bright!'}],
            characters_featured=['Leo'],
            setting_key='the_vault',
            vault_zone='map_platform',
            is_vault_page=True,
            vocab_words_used=['bright'],
        )
        non_vault_page = GraphicNovelPage.objects.create(
            novel=novel,
            page_number=2,
            panel_count=1,
            panel_descriptions=[{'panel_number': 1, 'narration': 'A quiet clue.'}],
            characters_featured=['Amara'],
            setting_key='story_realm',
            vault_zone='',
            is_vault_page=False,
            vocab_words_used=['bright'],
        )

        _step_graphic_novel_images(job, [pack])

        vault_page.refresh_from_db()
        non_vault_page.refresh_from_db()
        assert 'CHARACTER_DESIGN_LOCK: Leo' in vault_page.prompt_used
        assert 'CHARACTER_DESIGN_LOCK: Amara' not in vault_page.prompt_used
        assert 'SETTING: The Vault' in vault_page.prompt_used
        assert 'CHARACTER_DESIGN_LOCK: Amara' in non_vault_page.prompt_used
        assert 'CHARACTER_DESIGN_LOCK: Leo' not in non_vault_page.prompt_used
        assert 'SETTING: The Vault' not in non_vault_page.prompt_used
