"""
Vector store backends.

`FAISSVectorStore` is the development backend — a real, local FAISS index
per organization, persisted to disk. It's fully exercised by the test
suite since FAISS itself needs no network access (unlike Pinecone or a
hosted embedding API).

`PineconeVectorStore` is the production backend, matching the tech stack.
It cannot be exercised in this environment (no Pinecone API key or network
access to Pinecone's API here) — written against the current Pinecone
client API and reviewed carefully, but genuinely untested locally, the
same honest limitation as the MinIO/Docker pieces in Milestone 2.

Both implement `VectorStoreBackend`, keyed by organization_id so a query
never crosses tenant boundaries, with optional further filtering by
document_id (e.g. "chat about just this one document").
"""
import os
import pickle
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class VectorMatch:
    chunk_id: str
    score: float
    metadata: dict = field(default_factory=dict)


class VectorStoreBackend(Protocol):
    def upsert(
        self, organization_id: str, chunk_id: str, vector: list[float], metadata: dict
    ) -> None: ...

    def query(
        self,
        organization_id: str,
        vector: list[float],
        top_k: int = 5,
        document_id: str | None = None,
    ) -> list[VectorMatch]: ...

    def delete(self, organization_id: str, chunk_id: str) -> None: ...


def _chunk_id_to_faiss_id(chunk_id: str) -> int:
    """FAISS's IDMap requires signed int64 ids; derive one deterministically
    from the chunk's UUID so the same chunk always maps to the same id."""
    return uuid.UUID(chunk_id).int & ((1 << 63) - 1)


class FAISSVectorStore:
    """
    One FAISS index per organization (`IndexFlatIP` wrapped in `IndexIDMap2`
    for delete support), persisted under `index_dir/{organization_id}.faiss`
    with a sidecar pickle holding `{faiss_id: {"chunk_id", "metadata"}}`
    (FAISS itself only stores vectors + integer ids, not arbitrary metadata).

    Vectors are expected to already be L2-normalized (both providers in
    `embeddings.py` do this) so inner product == cosine similarity.
    """

    def __init__(self, index_dir: str):
        self._index_dir = Path(index_dir)
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._indices: dict[str, "faiss.IndexIDMap2"] = {}  # noqa: F821
        self._metadata: dict[str, dict[int, dict]] = {}

    def _paths(self, organization_id: str) -> tuple[Path, Path]:
        return (
            self._index_dir / f"{organization_id}.faiss",
            self._index_dir / f"{organization_id}.meta.pkl",
        )

    def _load_index(self, organization_id: str, dimension: int):
        import faiss

        if organization_id in self._indices:
            return self._indices[organization_id]

        index_path, meta_path = self._paths(organization_id)
        if index_path.exists() and meta_path.exists():
            index = faiss.read_index(str(index_path))
            with open(meta_path, "rb") as f:
                metadata = pickle.load(f)
        else:
            index = faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))
            metadata = {}

        self._indices[organization_id] = index
        self._metadata[organization_id] = metadata
        return index

    def _save(self, organization_id: str) -> None:
        import faiss

        index_path, meta_path = self._paths(organization_id)
        faiss.write_index(self._indices[organization_id], str(index_path))
        with open(meta_path, "wb") as f:
            pickle.dump(self._metadata[organization_id], f)

    def upsert(
        self, organization_id: str, chunk_id: str, vector: list[float], metadata: dict
    ) -> None:
        import numpy as np

        index = self._load_index(organization_id, dimension=len(vector))
        faiss_id = _chunk_id_to_faiss_id(chunk_id)

        # Remove any existing entry for this chunk first (upsert semantics —
        # IndexIDMap2 doesn't overwrite in place on add_with_ids).
        index.remove_ids(np.array([faiss_id], dtype="int64"))

        vec = np.array([vector], dtype="float32")
        index.add_with_ids(vec, np.array([faiss_id], dtype="int64"))
        self._metadata[organization_id][faiss_id] = {"chunk_id": chunk_id, **metadata}
        self._save(organization_id)

    def query(
        self,
        organization_id: str,
        vector: list[float],
        top_k: int = 5,
        document_id: str | None = None,
    ) -> list[VectorMatch]:
        import numpy as np

        if organization_id not in self._indices:
            index_path, _ = self._paths(organization_id)
            if not index_path.exists():
                return []
            self._load_index(organization_id, dimension=len(vector))

        index = self._indices[organization_id]
        if index.ntotal == 0:
            return []

        # Over-fetch when filtering by document_id since FAISS's flat index
        # has no native metadata filter — post-filter in Python instead.
        fetch_k = top_k * 5 if document_id else top_k
        fetch_k = min(fetch_k, index.ntotal)

        query_vec = np.array([vector], dtype="float32")
        scores, ids = index.search(query_vec, fetch_k)

        results: list[VectorMatch] = []
        for score, faiss_id in zip(scores[0], ids[0]):
            if faiss_id == -1:
                continue
            meta = self._metadata[organization_id].get(int(faiss_id), {})
            if document_id and meta.get("document_id") != document_id:
                continue
            results.append(
                VectorMatch(chunk_id=meta.get("chunk_id", str(faiss_id)), score=float(score), metadata=meta)
            )
            if len(results) >= top_k:
                break
        return results

    def delete(self, organization_id: str, chunk_id: str) -> None:
        import numpy as np

        if organization_id not in self._indices:
            return
        faiss_id = _chunk_id_to_faiss_id(chunk_id)
        self._indices[organization_id].remove_ids(np.array([faiss_id], dtype="int64"))
        self._metadata[organization_id].pop(faiss_id, None)
        self._save(organization_id)


class PineconeVectorStore:
    """
    Production vector store. Uses one Pinecone index (created out-of-band
    or on first use) with one *namespace* per organization for tenant
    isolation, and document_id as a metadata filter for per-document scoping.

    NOTE: untested in this environment — no Pinecone API key/network access
    here. Written against the pinecone-client v5+ API.
    """

    def __init__(self, api_key: str, index_name: str):
        from pinecone import Pinecone

        self._client = Pinecone(api_key=api_key)
        self._index = self._client.Index(index_name)

    def upsert(
        self, organization_id: str, chunk_id: str, vector: list[float], metadata: dict
    ) -> None:
        self._index.upsert(
            vectors=[{"id": chunk_id, "values": vector, "metadata": metadata}],
            namespace=organization_id,
        )

    def query(
        self,
        organization_id: str,
        vector: list[float],
        top_k: int = 5,
        document_id: str | None = None,
    ) -> list[VectorMatch]:
        query_filter = {"document_id": {"$eq": document_id}} if document_id else None
        response = self._index.query(
            vector=vector,
            top_k=top_k,
            namespace=organization_id,
            filter=query_filter,
            include_metadata=True,
        )
        return [
            VectorMatch(chunk_id=match["id"], score=match["score"], metadata=match.get("metadata", {}))
            for match in response.get("matches", [])
        ]

    def delete(self, organization_id: str, chunk_id: str) -> None:
        self._index.delete(ids=[chunk_id], namespace=organization_id)


_singleton: VectorStoreBackend | None = None


def get_vector_store(
    environment: str, faiss_index_dir: str, pinecone_api_key: str | None, pinecone_index_name: str
) -> VectorStoreBackend:
    """Factory selecting FAISS (dev) or Pinecone (production), cached as a
    process-wide singleton. Overridden in tests via dependency injection."""
    global _singleton
    if _singleton is not None:
        return _singleton

    if environment == "production":
        if not pinecone_api_key:
            raise ValueError("PINECONE_API_KEY is required when ENVIRONMENT=production")
        _singleton = PineconeVectorStore(pinecone_api_key, pinecone_index_name)
    else:
        _singleton = FAISSVectorStore(faiss_index_dir)
    return _singleton
