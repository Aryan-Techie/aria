"""Voyage AI embedder implementing mem0's EmbeddingBase interface directly.

mem0's built-in provider registry (mem0.utils.factory.EmbedderFactory) has no
native "voyage" entry in the installed version, and the alternative — its
"langchain" provider — requires installing the full `langchain` meta-package
just to reach langchain_voyageai. This is a small, self-contained adapter
instead: a plain REST-API embedding call (no local model download, unlike
the Chroma default embedder this project deliberately avoided elsewhere),
registered into mem0's factory at import time in app/memory/client.py.
"""
from typing import Literal, Optional

from mem0.configs.embeddings.base import BaseEmbedderConfig
from mem0.embeddings.base import EmbeddingBase

DEFAULT_MODEL = "voyage-3.5-lite"
DEFAULT_DIMS = 1024


class VoyageEmbedding(EmbeddingBase):
    def __init__(self, config: Optional[BaseEmbedderConfig] = None):
        super().__init__(config)
        import voyageai

        self.config.model = self.config.model or DEFAULT_MODEL
        self.config.embedding_dims = self.config.embedding_dims or DEFAULT_DIMS
        self.client = voyageai.Client(api_key=self.config.api_key)

    def _input_type(self, memory_action: Optional[str]) -> str:
        return "query" if memory_action == "search" else "document"

    def embed(self, text: str, memory_action: Optional[Literal["add", "search", "update"]] = None) -> list[float]:
        result = self.client.embed([text], model=self.config.model, input_type=self._input_type(memory_action))
        return result.embeddings[0]

    def embed_batch(self, texts: list[str], memory_action: str = "add") -> list[list[float]]:
        result = self.client.embed(list(texts), model=self.config.model, input_type=self._input_type(memory_action))
        return result.embeddings
