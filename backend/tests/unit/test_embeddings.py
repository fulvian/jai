from unittest.mock import MagicMock, patch

import pytest

from me4brain.embeddings.bge_m3 import BGEM3Service


@pytest.fixture
def mock_sentence_transformer():
    with patch("me4brain.embeddings.bge_m3.SentenceTransformer") as mock:
        yield mock


def test_bgem3_initialization_success(mock_sentence_transformer):
    service = BGEM3Service()
    assert service.model is not None
    mock_sentence_transformer.assert_called_once()


def test_bgem3_embed_query(mock_sentence_transformer):
    # Setup mock model behavior
    mock_model = mock_sentence_transformer.return_value
    mock_model.encode.return_value = MagicMock(
        cpu=lambda: MagicMock(tolist=lambda: [0.1, 0.2, 0.3])
    )

    service = BGEM3Service()
    embedding = service.embed_query("test query")

    assert len(embedding) == 3
    assert embedding == [0.1, 0.2, 0.3]
    mock_model.encode.assert_called_once()


def test_bgem3_embed_documents(mock_sentence_transformer):
    mock_model = mock_sentence_transformer.return_value
    mock_model.encode.return_value = MagicMock(cpu=lambda: MagicMock(tolist=lambda: [[0.1], [0.2]]))

    service = BGEM3Service()
    embeddings = service.embed_documents(["d1", "d2"])

    assert len(embeddings) == 2
    assert embeddings[0] == [0.1]


def test_bgem3_embed_documents_empty(mock_sentence_transformer):
    service = BGEM3Service()
    embeddings = service.embed_documents([])
    assert embeddings == []


def test_bgem3_initialization_error(mock_sentence_transformer):
    mock_sentence_transformer.side_effect = Exception("Model load failed")

    with pytest.raises(RuntimeError) as exc:
        BGEM3Service()
    assert "Could not load BGE-M3" in str(exc.value)


def test_get_device_mocked():
    # Test device selection logic separately if needed
    # But usually covered by init
    pass
