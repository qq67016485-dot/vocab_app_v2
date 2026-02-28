"""
RED tests for embedding_service.py — these tests are written BEFORE the service exists.
They define the expected API for Qwen 2.5 vector embedding deduplication.
"""
import pytest
from unittest.mock import patch, MagicMock

from tests.factories import WordFactory, WordDefinitionFactory, DefinitionEmbeddingFactory


@pytest.mark.django_db
class TestGetEmbedding:
    """Test embedding_service.get_embedding()"""

    @patch('vocabulary.services.embedding_service._call_qwen_api')
    def test_returns_vector_list(self, mock_api):
        mock_api.return_value = [0.1] * 768
        from vocabulary.services.embedding_service import get_embedding
        result = get_embedding('a simple definition')
        assert isinstance(result, list)
        assert len(result) == 768

    @patch('vocabulary.services.embedding_service._call_qwen_api')
    def test_calls_api_with_text(self, mock_api):
        mock_api.return_value = [0.0] * 768
        from vocabulary.services.embedding_service import get_embedding
        get_embedding('test text')
        mock_api.assert_called_once()
        call_args = mock_api.call_args
        assert 'test text' in str(call_args)


@pytest.mark.django_db
class TestCosineSimilarity:
    """Test embedding_service.cosine_similarity()"""

    def test_identical_vectors(self):
        from vocabulary.services.embedding_service import cosine_similarity
        vec = [1.0, 0.0, 0.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        from vocabulary.services.embedding_service import cosine_similarity
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        assert cosine_similarity(vec_a, vec_b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        from vocabulary.services.embedding_service import cosine_similarity
        vec_a = [1.0, 0.0]
        vec_b = [-1.0, 0.0]
        assert cosine_similarity(vec_a, vec_b) == pytest.approx(-1.0)

    def test_similar_vectors(self):
        from vocabulary.services.embedding_service import cosine_similarity
        vec_a = [1.0, 0.5, 0.0]
        vec_b = [0.9, 0.6, 0.1]
        result = cosine_similarity(vec_a, vec_b)
        assert 0.9 < result < 1.0


@pytest.mark.django_db
class TestFindDuplicateDefinition:
    """Test embedding_service.find_duplicate_definition()"""

    @patch('vocabulary.services.embedding_service.get_embedding')
    def test_no_existing_word_returns_none(self, mock_embed):
        from vocabulary.services.embedding_service import find_duplicate_definition
        mock_embed.return_value = [0.1] * 768
        result = find_duplicate_definition('nonexistent', 'noun', 'some definition')
        assert result is None

    @patch('vocabulary.services.embedding_service.get_embedding')
    def test_existing_word_high_similarity_returns_word(self, mock_embed):
        from vocabulary.services.embedding_service import find_duplicate_definition
        word = WordFactory(text='bright', part_of_speech='adjective')
        defn = WordDefinitionFactory(word=word, definition_text='Giving out much light')
        DefinitionEmbeddingFactory(definition=defn, embedding=[0.1] * 768)

        # Return a vector very similar to the stored one
        mock_embed.return_value = [0.1] * 768
        result = find_duplicate_definition('bright', 'adjective', 'Emitting a lot of light')
        assert result is not None
        assert result.pk == word.pk

    @patch('vocabulary.services.embedding_service.get_embedding')
    def test_existing_word_low_similarity_returns_none(self, mock_embed):
        from vocabulary.services.embedding_service import find_duplicate_definition
        word = WordFactory(text='bank', part_of_speech='noun')
        defn = WordDefinitionFactory(word=word, definition_text='A financial institution')
        DefinitionEmbeddingFactory(definition=defn, embedding=[1.0, 0.0, 0.0] + [0.0] * 765)

        # Return a very different vector
        mock_embed.return_value = [0.0, 1.0, 0.0] + [0.0] * 765
        result = find_duplicate_definition('bank', 'noun', 'The side of a river')
        assert result is None

    @patch('vocabulary.services.embedding_service.get_embedding')
    def test_different_pos_not_matched(self, mock_embed):
        from vocabulary.services.embedding_service import find_duplicate_definition
        word = WordFactory(text='run', part_of_speech='verb')
        defn = WordDefinitionFactory(word=word, definition_text='To move quickly')
        DefinitionEmbeddingFactory(definition=defn, embedding=[0.1] * 768)

        mock_embed.return_value = [0.1] * 768
        result = find_duplicate_definition('run', 'noun', 'A period of running')
        assert result is None
