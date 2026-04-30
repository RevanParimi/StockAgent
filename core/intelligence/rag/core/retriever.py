"""
tools/rag/retriever.py
======================
Semantic retrieval from the ChromaDB vector store.

Public API
----------
RAGRetriever().retrieve(query, ticker, n)  → list[str]  (text chunks)
RAGRetriever().retrieve_with_scores(query) → list[dict]
"""

from __future__ import annotations

import logging

from core.intelligence.rag import config as rag_config
from core.intelligence.rag.core.embedder import Embedder
from core.intelligence.rag.core.vector_store import VectorStore

logger = logging.getLogger(__name__)


class RAGRetriever:
    """
    Retrieves relevant document chunks for a natural-language query.

    Optional reranking is supported when RERANKER_ENABLED=true
    in config/rag_config.py.

    Usage
    -----
    retriever = RAGRetriever()
    chunks = retriever.retrieve("Maruti Q3 FY26 EBITDA margin")
    # Returns list of text strings ready to concatenate into the prompt
    """

    def __init__(self) -> None:
        self._embedder = Embedder()
        self._store = VectorStore()
        self._reranker = None
        if rag_config.RERANKER_ENABLED:
            self._reranker = self._load_reranker()

    def retrieve(
        self,
        query: str,
        ticker: str | None = None,
        n: int = rag_config.TOP_K_RESULTS,
    ) -> list[str]:
        """
        Retrieve the top-N most relevant text chunks for `query`.

        Parameters
        ----------
        query  : natural language search query
        ticker : optional NSE ticker to filter results (e.g. "MARUTI")
        n      : number of chunks to return

        Returns
        -------
        list of raw text strings, ordered by relevance (most relevant first)
        """
        results = self.retrieve_with_scores(query, ticker=ticker, n=n)
        return [r["document"] for r in results]

    def retrieve_with_scores(
        self,
        query: str,
        ticker: str | None = None,
        n: int = rag_config.TOP_K_RESULTS,
    ) -> list[dict]:
        """
        Retrieve chunks with similarity scores and metadata.

        Returns list of dicts: {id, document, metadata, similarity}
        """
        if self._store.count() == 0:
            logger.warning("[RAGRetriever] Vector store is empty — no documents ingested yet")
            return []

        query_embedding = self._embedder.embed(query)

        where: dict | None = {"ticker": ticker} if ticker else None
        results = self._store.query(
            query_embedding=query_embedding,
            n_results=n,
            where=where,
        )

        if self._reranker and results:
            results = self._rerank(query, results)

        logger.debug(
            "[RAGRetriever] Query '%s' → %d results (ticker=%s)",
            query[:60], len(results), ticker,
        )
        return results

    # ------------------------------------------------------------------
    # Optional reranker
    # ------------------------------------------------------------------

    def _load_reranker(self):
        try:
            from sentence_transformers import CrossEncoder
            logger.info("[RAGRetriever] Loading reranker: %s", rag_config.RERANKER_MODEL)
            return CrossEncoder(rag_config.RERANKER_MODEL)
        except ImportError:
            logger.warning("[RAGRetriever] CrossEncoder not available — reranking disabled")
            return None
        except Exception as exc:
            logger.warning("[RAGRetriever] Reranker load failed: %s", exc)
            return None

    def _rerank(self, query: str, results: list[dict]) -> list[dict]:
        """Re-score and re-order results using a cross-encoder."""
        pairs = [(query, r["document"]) for r in results]
        scores = self._reranker.predict(pairs)
        for r, score in zip(results, scores):
            r["reranker_score"] = float(score)
        return sorted(results, key=lambda x: x.get("reranker_score", 0), reverse=True)
