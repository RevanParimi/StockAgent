"""
tools/rag/vector_store.py
=========================
ChromaDB wrapper for storing and querying document embeddings.

Public API
----------
VectorStore().upsert(ids, documents, embeddings, metadatas)
VectorStore().query(query_embedding, n_results)  → list[dict]
VectorStore().count()                            → int
VectorStore().delete_collection()
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.intelligence.rag import config as rag_config

logger = logging.getLogger(__name__)


class VectorStore:
    """
    ChromaDB-backed vector store for the RAG pipeline.

    The collection persists to disk at rag_config.CHROMA_PERSIST_DIR.
    """

    def __init__(self) -> None:
        self._client = None
        self._collection = None
        self._init_chroma()

    def _init_chroma(self) -> None:
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            persist_dir = Path(rag_config.CHROMA_PERSIST_DIR)
            persist_dir.mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=rag_config.CHROMA_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "[VectorStore] Collection '%s' loaded — %d documents",
                rag_config.CHROMA_COLLECTION_NAME,
                self._collection.count(),
            )
        except ImportError:
            raise ImportError(
                "chromadb is not installed. Run: pip install chromadb"
            )
        except Exception as exc:
            logger.error("[VectorStore] Init failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict] | None = None,
    ) -> None:
        """
        Insert or update documents in the collection.

        Parameters
        ----------
        ids         : unique string IDs for each document chunk
        documents   : raw text of each chunk
        embeddings  : pre-computed embedding vectors
        metadatas   : optional dicts with source, ticker, date, etc.
        """
        if not ids:
            return
        if metadatas is None:
            metadatas = [{} for _ in ids]

        self._collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info("[VectorStore] Upserted %d chunks", len(ids))

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query(
        self,
        query_embedding: list[float],
        n_results: int = rag_config.TOP_K_RESULTS,
        where: dict | None = None,
    ) -> list[dict]:
        """
        Semantic search for the top-K most similar chunks.

        Parameters
        ----------
        query_embedding : embedding vector of the search query
        n_results       : number of results to return
        where           : optional metadata filter, e.g. {"ticker": "MARUTI"}

        Returns
        -------
        list of dicts: {id, document, metadata, distance}
        """
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": min(n_results, self._collection.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        output = []
        for i, doc in enumerate(results["documents"][0]):
            distance = results["distances"][0][i]
            # Convert cosine distance to similarity (1 - distance)
            similarity = 1.0 - distance
            if similarity >= rag_config.SIMILARITY_THRESHOLD:
                output.append({
                    "id":       results["ids"][0][i],
                    "document": doc,
                    "metadata": results["metadatas"][0][i],
                    "similarity": round(similarity, 4),
                })
        return output

    def count(self) -> int:
        """Return total number of chunks in the collection."""
        return self._collection.count()

    def delete_collection(self) -> None:
        """Drop and recreate the collection (use with caution)."""
        self._client.delete_collection(rag_config.CHROMA_COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=rag_config.CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.warning("[VectorStore] Collection deleted and recreated")
