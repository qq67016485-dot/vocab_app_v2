"""
RED tests for llm_service.py — written BEFORE the service exists.
Defines the API for low-level LLM wrappers (Anthropic + Gemini).
"""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
import json


@pytest.mark.django_db
class TestCallAnthropic:
    """Test llm_service.call_anthropic()"""

    @patch('vocabulary.services.llm_service.anthropic')
    def test_returns_parsed_json(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.text = '{"words": [{"term": "vivid"}]}'
        mock_message.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_message

        from vocabulary.services.llm_service import call_anthropic
        result = call_anthropic(
            model='claude-sonnet-4-20250514',
            system_prompt='You are a dictionary.',
            user_prompt='Define: vivid',
        )
        assert result == {"words": [{"term": "vivid"}]}

    @patch('vocabulary.services.llm_service.anthropic')
    def test_strips_markdown_fences(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.text = '```json\n{"result": "ok"}\n```'
        mock_message.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_message

        from vocabulary.services.llm_service import call_anthropic
        result = call_anthropic('model', 'sys', 'usr')
        assert result == {"result": "ok"}

    @patch('vocabulary.services.llm_service.anthropic')
    def test_extracts_json_from_surrounding_text(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.text = 'Here is the result:\n{"data": 42}\nHope this helps!'
        mock_message.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_message

        from vocabulary.services.llm_service import call_anthropic
        result = call_anthropic('model', 'sys', 'usr')
        assert result == {"data": 42}

    @patch('vocabulary.services.llm_service.anthropic')
    def test_raises_on_unparseable_response(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.text = 'This is not JSON at all.'
        mock_message.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_message

        from vocabulary.services.llm_service import call_anthropic
        with pytest.raises(ValueError, match="Could not parse JSON"):
            call_anthropic('model', 'sys', 'usr')

    @patch('vocabulary.services.llm_service.anthropic')
    def test_uses_base_url_when_configured(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.text = '{"ok": true}'
        mock_message.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_message

        from vocabulary.services.llm_service import call_anthropic
        with patch('vocabulary.services.llm_service.settings') as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = 'test-key'
            mock_settings.ANTHROPIC_BASE_URL = 'https://proxy.example.com'
            call_anthropic('model', 'sys', 'usr')
            mock_anthropic.Anthropic.assert_called_with(
                api_key='test-key', base_url='https://proxy.example.com',
            )


@pytest.mark.django_db
class TestCallGeminiImage:
    """Test llm_service.call_gemini_image()"""

    @patch('vocabulary.services.llm_service.genai')
    def test_returns_image_bytes(self, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        mock_image_part = MagicMock()
        mock_image_part.inline_data.data = b'\x89PNG_FAKE_IMAGE'
        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_image_part]
        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_client.models.generate_content.return_value = mock_response

        from vocabulary.services.llm_service import call_gemini_image
        result = call_gemini_image('A colorful illustration of a cat')
        assert isinstance(result, bytes)
        assert result == b'\x89PNG_FAKE_IMAGE'

    @patch('vocabulary.services.llm_service.genai')
    def test_passes_prompt_to_client(self, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        mock_image_part = MagicMock()
        mock_image_part.inline_data.data = b'img'
        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_image_part]
        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_client.models.generate_content.return_value = mock_response

        from vocabulary.services.llm_service import call_gemini_image
        call_gemini_image('test prompt')
        mock_client.models.generate_content.assert_called_once()
        call_args = mock_client.models.generate_content.call_args
        assert call_args.kwargs['contents'] == 'test prompt'


class TestLoadPromptTemplate:
    """Test llm_service.load_prompt_template()"""

    def test_loads_existing_template(self, tmp_path):
        template_file = tmp_path / "test_prompt.txt"
        template_file.write_text("Define these words: {word_list}")

        from vocabulary.services.llm_service import load_prompt_template
        with patch('vocabulary.services.llm_service.PROMPTS_DIR', str(tmp_path)):
            result = load_prompt_template('test_prompt')
            assert result == "Define these words: {word_list}"

    def test_raises_on_missing_template(self):
        from vocabulary.services.llm_service import load_prompt_template
        with patch('vocabulary.services.llm_service.PROMPTS_DIR', '/nonexistent'):
            with pytest.raises(FileNotFoundError):
                load_prompt_template('does_not_exist')
