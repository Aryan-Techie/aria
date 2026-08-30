"""Thin wrapper around mem0's Memory class, configured to use Anthropic
(existing key) for its internal fact-extraction LLM calls, Voyage AI for
embeddings (see voyage_embedder.py), and a locally-embedded Qdrant instance
(no server required — Qdrant's client supports a local on-disk `path` mode)
for vector storage. Zero extra infra beyond one free-tier Voyage API key.
"""
from functools import lru_cache

from mem0 import Memory
from mem0.utils.factory import EmbedderFactory

from app.memory.voyage_embedder import VoyageEmbedding

# mem0's EmbedderFactory has no native "voyage" entry, AND separately
# mem0.embeddings.configs.EmbedderConfig has its own hardcoded pydantic
# field_validator whitelist of provider name strings — "voyage" fails that
# validator before EmbedderFactory is ever consulted, and that validator is
# baked into a compiled pydantic-core schema at class-definition time, so it
# can't be monkeypatched after the fact. Repurposing the "langchain" slot
# (already on that whitelist, and conceptually the closest fit — mem0's own
# langchain provider exists to wrap an arbitrary bring-your-own embeddings
# object) sidesteps both issues without pulling in the full `langchain`
# package. Only this one factory mapping is overridden; the provider string
# "langchain" appearing in build_config() below is this workaround, not an
# actual dependency on the langchain package.
EmbedderFactory.provider_to_class["langchain"] = "app.memory.voyage_embedder.VoyageEmbedding"
assert VoyageEmbedding  # imported for its registration side-effect above


def build_config(settings) -> dict:
    return {
        "llm": {
            "provider": "anthropic",
            "config": {
                "model": settings.anthropic_model,
                "api_key": settings.anthropic_api_key,
            },
        },
        "embedder": {
            "provider": "langchain",  # see the registration comment above — actually VoyageEmbedding
            "config": {
                "api_key": settings.voyage_api_key,
                "embedding_dims": 1024,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "aria_sessions",
                "embedding_model_dims": 1024,
                "path": settings.mem0_vector_store_path,
            },
        },
    }


@lru_cache
def get_memory() -> Memory:
    from app.config import get_settings

    settings = get_settings()
    return Memory.from_config(build_config(settings))
