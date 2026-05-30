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

    def _make_stream_mock(self, mock_anthropic, text):
        """Helper: set up mock_anthropic so client.messages.stream(...) yields text."""
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = 'text'
        mock_text_block.text = text
        mock_message.content = [mock_text_block]

        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.__iter__ = MagicMock(return_value=iter([]))
        mock_stream.get_final_message.return_value = mock_message
        mock_client.messages.stream.return_value = mock_stream

        return mock_client

    @patch('vocabulary.services.llm_service.anthropic')
    def test_returns_parsed_json(self, mock_anthropic):
        self._make_stream_mock(mock_anthropic, '{"words": [{"term": "vivid"}]}')

        from vocabulary.services.llm_service import call_anthropic
        result = call_anthropic(
            model='claude-sonnet-4-20250514',
            system_prompt='You are a dictionary.',
            user_prompt='Define: vivid',
        )
        assert result == {"words": [{"term": "vivid"}]}

    @patch('vocabulary.services.llm_service.anthropic')
    def test_strips_markdown_fences(self, mock_anthropic):
        self._make_stream_mock(mock_anthropic, '```json\n{"result": "ok"}\n```')

        from vocabulary.services.llm_service import call_anthropic
        result = call_anthropic('model', 'sys', 'usr')
        assert result == {"result": "ok"}

    @patch('vocabulary.services.llm_service.anthropic')
    def test_extracts_json_from_surrounding_text(self, mock_anthropic):
        self._make_stream_mock(mock_anthropic, 'Here is the result:\n{"data": 42}\nHope this helps!')

        from vocabulary.services.llm_service import call_anthropic
        result = call_anthropic('model', 'sys', 'usr')
        assert result == {"data": 42}

    @patch('vocabulary.services.llm_service.anthropic')
    def test_raises_on_unparseable_response(self, mock_anthropic):
        self._make_stream_mock(mock_anthropic, 'This is not JSON at all.')

        from vocabulary.services.llm_service import call_anthropic
        with pytest.raises(ValueError, match="Could not parse JSON"):
            call_anthropic('model', 'sys', 'usr')

    @patch('vocabulary.services.llm_service.anthropic')
    def test_uses_base_url_when_configured(self, mock_anthropic):
        self._make_stream_mock(mock_anthropic, '{"ok": true}')

        from vocabulary.services.llm_service import call_anthropic
        with patch('vocabulary.services.llm_service.settings') as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = 'test-key'
            mock_settings.ANTHROPIC_BASE_URL = 'https://proxy.example.com'
            call_anthropic('model', 'sys', 'usr')
            mock_anthropic.Anthropic.assert_called_with(
                api_key='test-key', base_url='https://proxy.example.com',
            )


@pytest.mark.django_db
class TestCallOpenaiImage:
    """Test llm_service.call_openai_image()"""

    @patch('httpx.get')
    @patch('openai.OpenAI')
    def test_returns_image_bytes(self, mock_openai_cls, mock_httpx_get):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_image = MagicMock()
        mock_image.url = 'https://example.com/image.png'
        mock_image.b64_json = None
        mock_response = MagicMock()
        mock_response.data = [mock_image]
        mock_client.images.generate.return_value = mock_response

        mock_httpx_get.return_value = MagicMock(content=b'\x89PNG_FAKE_IMAGE')

        from vocabulary.services.llm_service import call_openai_image
        result = call_openai_image('A colorful illustration of a cat')
        assert isinstance(result, bytes)
        assert result == b'\x89PNG_FAKE_IMAGE'
        mock_httpx_get.assert_called_once_with(
            'https://example.com/image.png', follow_redirects=True, timeout=60,
        )

    @patch('httpx.get')
    @patch('openai.OpenAI')
    def test_passes_prompt_to_client(self, mock_openai_cls, mock_httpx_get):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_image = MagicMock()
        mock_image.url = 'https://example.com/image.png'
        mock_image.b64_json = None
        mock_response = MagicMock()
        mock_response.data = [mock_image]
        mock_client.images.generate.return_value = mock_response

        mock_httpx_get.return_value = MagicMock(content=b'img')

        from vocabulary.services.llm_service import call_openai_image
        call_openai_image('test prompt')
        mock_client.images.generate.assert_called_once()
        call_args = mock_client.images.generate.call_args
        assert call_args.kwargs['prompt'] == 'test prompt'
        assert call_args.kwargs['model'] == 'gpt-image-2'

    @patch('vocabulary.services.llm_service._log_llm_call')
    @patch('httpx.get')
    @patch('openai.OpenAI')
    def test_logs_image_prompt(self, mock_openai_cls, mock_httpx_get, mock_log):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_image = MagicMock()
        mock_image.url = 'https://example.com/image.png'
        mock_image.b64_json = None
        mock_response = MagicMock()
        mock_response.data = [mock_image]
        mock_client.images.generate.return_value = mock_response

        mock_httpx_get.return_value = MagicMock(content=b'img')

        from vocabulary.services.llm_service import call_openai_image
        call_openai_image('exact image prompt')

        mock_log.assert_called_once()
        assert mock_log.call_args.args[0] == 'gpt-image-2_image'
        assert mock_log.call_args.args[1] == 'OpenAI image generation'
        assert mock_log.call_args.args[2] == 'exact image prompt'


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
