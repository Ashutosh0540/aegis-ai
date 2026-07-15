"""
Embedding providers.

`HuggingFaceEmbeddingProvider` is the production implementation (local
sentence-transformers model, per the tech stack — no external API key or
per-token cost). `FakeEmbeddingProvider` is a deterministic, dependency-
free stand-in used in tests: this sandbox/CI environment can't always
reach huggingface.co to download model weights, so tests never depend on
that network call. Both honor the same `EmbeddingProvider` protocol, so
swapping one for the other doesn't touch any calling code.
"""
import hashlib
import math
from typing import Protocol


class EmbeddingProvider(Protocol):
    dimension: int

    def embed_text(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class HuggingFaceEmbeddingProvider:
    """
    Production embedding provider backed by a local sentence-transformers
    model (default: all-MiniLM-L6-v2, 384 dimensions — small and fast
    enough to run on CPU, which matters since this runs inside the Celery
    worker container alongside document processing).

    The heavy `sentence-transformers` import is deferred to __init__ so
    importing this module elsewhere (e.g. for type hints) never requires
    the dependency to be installed unless this class is actually
    instantiated.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.dimension = self._model.get_sentence_embedding_dimension()

    def embed_text(self, text: str) -> list[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()


class FakeEmbeddingProvider:
    """
    Deterministic, hash-based "embedding" for tests. Not semantically
    meaningful (it doesn't capture actual textual similarity beyond crude
    token overlap), but stable across calls — the same text always
    produces the same vector, and vectors are L2-normalized like real
    embeddings so cosine-similarity retrieval logic can be exercised
    end-to-end without network access or GPU/CPU-heavy model inference.
    """

    def __init__(self, dimension: int = 64):
        self.dimension = dimension

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = text.lower().split()
        if not tokens:
            tokens = [""]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(self.dimension):
                vector[i] += digest[i % len(digest)] / 255.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]
