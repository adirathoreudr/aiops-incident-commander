"""
agent/retrieval/knowledge_store.py
FAISS-backed vector store for runbooks and historical incidents.
Falls back to keyword matching if embeddings unavailable.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("agent.knowledge_store")

RUNBOOKS_PATH   = Path(os.getenv("RUNBOOKS_PATH", "/app/knowledge-base/runbooks"))
INCIDENTS_PATH  = Path(os.getenv("INCIDENTS_PATH", "/app/knowledge-base/incidents"))
EMBED_MODEL     = os.getenv("EMBED_MODEL", "text-embedding-3-small")
USE_EMBEDDINGS  = os.getenv("USE_EMBEDDINGS", "true").lower() == "true"

try:
    from langchain_community.vectorstores import FAISS
    from langchain_openai import OpenAIEmbeddings
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    log.warning("FAISS/langchain not available — using keyword fallback")


class KnowledgeStore:
    """
    Provides semantic search over runbooks and historical incidents.
    Uses FAISS if available, keyword search otherwise.
    """

    def __init__(self) -> None:
        self._runbooks:   list[dict] = self._load_json_dir(RUNBOOKS_PATH)
        self._incidents:  list[dict] = self._load_json_dir(INCIDENTS_PATH)
        self._runbook_index  = None
        self._incident_index = None

        if FAISS_AVAILABLE and USE_EMBEDDINGS and os.getenv("OPENAI_API_KEY"):
            self._build_indexes()
        else:
            log.info("KnowledgeStore using keyword fallback (%d runbooks, %d incidents)",
                     len(self._runbooks), len(self._incidents))

    # ── Public API ─────────────────────────────────────────────────────────────

    def search_runbooks(self, query: str, k: int = 3) -> list[dict]:
        if self._runbook_index:
            return self._vector_search(self._runbook_index, query, k)
        return self._keyword_search(self._runbooks, query, k)

    def search_incidents(self, query: str, k: int = 3) -> list[dict]:
        if self._incident_index:
            return self._vector_search(self._incident_index, query, k)
        return self._keyword_search(self._incidents, query, k)

    # ── Private ────────────────────────────────────────────────────────────────

    def _load_json_dir(self, path: Path) -> list[dict]:
        docs = []
        if not path.exists():
            log.warning("Knowledge base path not found: %s", path)
            return docs
        for f in path.glob("*.json"):
            try:
                docs.append(json.loads(f.read_text()))
            except Exception as e:
                log.warning("Failed to load %s: %s", f, e)
        log.info("Loaded %d docs from %s", len(docs), path)
        return docs

    def _build_indexes(self) -> None:
        try:
            embeddings = OpenAIEmbeddings(model=EMBED_MODEL)
            if self._runbooks:
                texts = [self._doc_to_text(d) for d in self._runbooks]
                self._runbook_index = FAISS.from_texts(texts, embeddings, metadatas=self._runbooks)
            if self._incidents:
                texts = [self._doc_to_text(d) for d in self._incidents]
                self._incident_index = FAISS.from_texts(texts, embeddings, metadatas=self._incidents)
            log.info("FAISS indexes built (runbooks=%d, incidents=%d)",
                     len(self._runbooks), len(self._incidents))
        except Exception as e:
            log.exception("Failed to build FAISS indexes: %s", e)

    def _vector_search(self, index: Any, query: str, k: int) -> list[dict]:
        try:
            results = index.similarity_search(query, k=k)
            return [r.metadata for r in results]
        except Exception as e:
            log.warning("Vector search failed: %s", e)
            return []

    def _keyword_search(self, docs: list[dict], query: str, k: int) -> list[dict]:
        """Simple keyword overlap scoring."""
        tokens = set(query.lower().split())
        scored = []
        for doc in docs:
            text = self._doc_to_text(doc).lower()
            score = sum(1 for t in tokens if t in text)
            scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:k] if _ > 0]

    @staticmethod
    def _doc_to_text(doc: dict) -> str:
        return " ".join(str(v) for v in doc.values() if isinstance(v, (str, int, float)))
