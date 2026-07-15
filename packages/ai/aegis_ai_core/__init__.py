"""Shared AI/RAG primitives: embeddings, vector storage, and LLM providers.

Used by both `apps/api` (query-time retrieval + chat) and `apps/worker`
(embedding generation right after a document is chunked). Lives outside
either app so it isn't duplicated or drift between the two processes.
"""
