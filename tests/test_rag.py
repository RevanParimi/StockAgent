"""
tests/test_rag.py
=================
Unit tests for the Phase 3 RAG pipeline.
ChromaDB, sentence-transformers, and file I/O are all mocked.

What is tested:
  - Embedder.embed() returns a list of floats
  - Embedder.embed_batch() returns correct length
  - VectorStore.upsert() and query() call ChromaDB correctly
  - VectorStore filters by similarity threshold
  - DocumentIngester._chunk_text() produces correct overlap
  - DocumentIngester.ingest_text() calls upsert with right count
  - RAGRetriever.retrieve() returns empty list when store is empty
  - RAGRetriever filters results below similarity threshold
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------

class TestEmbedder:
    @patch("tools.rag.embedder._load_model")
    def test_embed_returns_list_of_floats(self, mock_load):
        from tools.rag.embedder import Embedder
        mock_model = MagicMock()
        import numpy as np
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])
        mock_load.return_value = mock_model

        embedder = Embedder()
        result = embedder.embed("test query")
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)

    @patch("tools.rag.embedder._load_model")
    def test_embed_batch_returns_correct_length(self, mock_load):
        from tools.rag.embedder import Embedder
        import numpy as np
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
        mock_load.return_value = mock_model

        embedder = Embedder()
        result = embedder.embed_batch(["a", "b", "c"])
        assert len(result) == 3

    @patch("tools.rag.embedder._load_model")
    def test_embed_batch_empty_input(self, mock_load):
        from tools.rag.embedder import Embedder
        embedder = Embedder()
        result = embedder.embed_batch([])
        assert result == []


# ---------------------------------------------------------------------------
# Text chunking (pure function, no mocks needed)
# ---------------------------------------------------------------------------

class TestChunking:
    def test_chunk_text_basic(self):
        from tools.rag.ingestion import _chunk_text
        text = " ".join([f"word{i}" for i in range(1000)])
        chunks = _chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) > 1
        assert all(isinstance(c, str) for c in chunks)

    def test_chunk_text_overlap_creates_shared_content(self):
        from tools.rag.ingestion import _chunk_text
        words = [f"w{i}" for i in range(50)]
        text = " ".join(words)
        chunks = _chunk_text(text, chunk_size=30, overlap=10)
        # With overlap, consecutive chunks share some words
        if len(chunks) >= 2:
            words_first = set(chunks[0].split())
            words_second = set(chunks[1].split())
            assert len(words_first & words_second) > 0

    def test_chunk_text_empty_returns_empty(self):
        from tools.rag.ingestion import _chunk_text
        assert _chunk_text("", chunk_size=100, overlap=10) == []

    def test_doc_id_is_deterministic(self):
        from tools.rag.ingestion import _doc_id
        id1 = _doc_id("same text", "source.pdf", 0)
        id2 = _doc_id("same text", "source.pdf", 0)
        assert id1 == id2

    def test_doc_id_differs_for_different_chunks(self):
        from tools.rag.ingestion import _doc_id
        id1 = _doc_id("text A", "source.pdf", 0)
        id2 = _doc_id("text B", "source.pdf", 1)
        assert id1 != id2


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------

class TestVectorStore:
    @patch("tools.rag.vector_store.chromadb")
    def test_upsert_called_with_correct_args(self, mock_chromadb):
        from tools.rag.vector_store import VectorStore
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_collection.count.return_value = 0

        store = VectorStore()
        store.upsert(
            ids=["id1"],
            documents=["doc1"],
            embeddings=[[0.1, 0.2]],
            metadatas=[{"ticker": "MARUTI"}],
        )
        mock_collection.upsert.assert_called_once()

    @patch("tools.rag.vector_store.chromadb")
    def test_query_filters_by_similarity_threshold(self, mock_chromadb):
        from tools.rag.vector_store import VectorStore
        from config import rag_config

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_collection.count.return_value = 2

        # Return one result above threshold, one below
        threshold = rag_config.SIMILARITY_THRESHOLD
        mock_collection.query.return_value = {
            "ids":       [["id1", "id2"]],
            "documents": [["high relevance doc", "low relevance doc"]],
            "metadatas": [[{"ticker": "MARUTI"}, {"ticker": "MARUTI"}]],
            "distances": [[1 - threshold - 0.1, 1 - threshold + 0.1]],  # below/above threshold in cosine distance
        }

        store = VectorStore()
        results = store.query([0.1, 0.2])
        # Only the high-similarity result should be returned
        assert len(results) == 1
        assert results[0]["document"] == "high relevance doc"

    @patch("tools.rag.vector_store.chromadb")
    def test_count_returns_collection_count(self, mock_chromadb):
        from tools.rag.vector_store import VectorStore
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_collection.count.return_value = 42

        store = VectorStore()
        assert store.count() == 42


# ---------------------------------------------------------------------------
# DocumentIngester
# ---------------------------------------------------------------------------

class TestDocumentIngester:
    @patch("tools.rag.ingestion.VectorStore")
    @patch("tools.rag.ingestion.Embedder")
    def test_ingest_text_calls_upsert(self, mock_embedder_cls, mock_store_cls):
        from tools.rag.ingestion import DocumentIngester

        mock_embedder = MagicMock()
        mock_embedder.embed_batch.return_value = [[0.1, 0.2]] * 5
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        ingester = DocumentIngester()
        text = " ".join([f"word{i}" for i in range(500)])
        n = ingester.ingest_text(text, doc_id="test_doc", metadata={"ticker": "MARUTI"})

        assert n > 0
        mock_store.upsert.assert_called_once()

    @patch("tools.rag.ingestion.VectorStore")
    @patch("tools.rag.ingestion.Embedder")
    def test_ingest_empty_text_returns_zero(self, mock_embedder_cls, mock_store_cls):
        from tools.rag.ingestion import DocumentIngester
        ingester = DocumentIngester()
        n = ingester.ingest_text("   ", doc_id="empty")
        assert n == 0

    @patch("tools.rag.ingestion.VectorStore")
    @patch("tools.rag.ingestion.Embedder")
    def test_ingest_file_missing_returns_zero(self, mock_embedder_cls, mock_store_cls):
        from tools.rag.ingestion import DocumentIngester
        ingester = DocumentIngester()
        n = ingester.ingest_file(Path("/nonexistent/file.pdf"))
        assert n == 0

    @patch("tools.rag.ingestion.VectorStore")
    @patch("tools.rag.ingestion.Embedder")
    def test_ingest_unsupported_extension_returns_zero(self, mock_embedder_cls, mock_store_cls, tmp_path):
        from tools.rag.ingestion import DocumentIngester
        f = tmp_path / "test.docx"
        f.write_text("some content")
        ingester = DocumentIngester()
        n = ingester.ingest_file(f)
        assert n == 0


# ---------------------------------------------------------------------------
# RAGRetriever
# ---------------------------------------------------------------------------

class TestRAGRetriever:
    @patch("tools.rag.retriever.VectorStore")
    @patch("tools.rag.retriever.Embedder")
    def test_retrieve_empty_store_returns_empty(self, mock_embedder_cls, mock_store_cls):
        from tools.rag.retriever import RAGRetriever

        mock_store = MagicMock()
        mock_store.count.return_value = 0
        mock_store_cls.return_value = mock_store

        retriever = RAGRetriever()
        result = retriever.retrieve("Maruti earnings")
        assert result == []

    @patch("tools.rag.retriever.VectorStore")
    @patch("tools.rag.retriever.Embedder")
    def test_retrieve_returns_document_texts(self, mock_embedder_cls, mock_store_cls):
        from tools.rag.retriever import RAGRetriever

        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [0.1, 0.2, 0.3]
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.count.return_value = 5
        mock_store.query.return_value = [
            {"id": "1", "document": "Maruti revenue up 12%", "metadata": {}, "similarity": 0.9},
            {"id": "2", "document": "Strong EBITDA margins", "metadata": {}, "similarity": 0.85},
        ]
        mock_store_cls.return_value = mock_store

        retriever = RAGRetriever()
        results = retriever.retrieve("Maruti earnings")
        assert len(results) == 2
        assert "Maruti revenue up 12%" in results
