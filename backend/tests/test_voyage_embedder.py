from unittest.mock import MagicMock, patch

from mem0.configs.embeddings.base import BaseEmbedderConfig

from app.memory.voyage_embedder import VoyageEmbedding


def _fake_voyage_module(embeddings: list[list[float]]):
    fake_client = MagicMock()
    fake_client.embed.return_value = MagicMock(embeddings=embeddings)
    fake_module = MagicMock()
    fake_module.Client.return_value = fake_client
    return fake_module, fake_client


def test_embed_returns_single_vector_no_network():
    fake_module, fake_client = _fake_voyage_module([[0.1, 0.2, 0.3]])
    with patch.dict("sys.modules", {"voyageai": fake_module}):
        embedder = VoyageEmbedding(BaseEmbedderConfig(api_key="fake-key"))
        vector = embedder.embed("hello world")

    assert vector == [0.1, 0.2, 0.3]
    fake_client.embed.assert_called_once()
    _, kwargs = fake_client.embed.call_args
    assert kwargs["input_type"] == "document"


def test_embed_uses_query_input_type_on_search():
    fake_module, fake_client = _fake_voyage_module([[0.4, 0.5]])
    with patch.dict("sys.modules", {"voyageai": fake_module}):
        embedder = VoyageEmbedding(BaseEmbedderConfig(api_key="fake-key"))
        embedder.embed("what's the price", memory_action="search")

    _, kwargs = fake_client.embed.call_args
    assert kwargs["input_type"] == "query"


def test_embed_batch_returns_all_vectors():
    fake_module, fake_client = _fake_voyage_module([[0.1], [0.2], [0.3]])
    with patch.dict("sys.modules", {"voyageai": fake_module}):
        embedder = VoyageEmbedding(BaseEmbedderConfig(api_key="fake-key"))
        vectors = embedder.embed_batch(["a", "b", "c"])

    assert vectors == [[0.1], [0.2], [0.3]]


def test_defaults_model_and_dims_when_unset():
    fake_module, _ = _fake_voyage_module([[0.1]])
    with patch.dict("sys.modules", {"voyageai": fake_module}):
        embedder = VoyageEmbedding(BaseEmbedderConfig(api_key="fake-key"))

    assert embedder.config.model == "voyage-3.5-lite"
    assert embedder.config.embedding_dims == 1024
