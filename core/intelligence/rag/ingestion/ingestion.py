"""
tools/rag/ingestion.py
======================
Document ingestion pipeline for the RAG vector store.

Reads PDF and TXT files → chunks text → embeds → stores in ChromaDB.

Public API
----------
DocumentIngester().ingest_file(path, metadata)
DocumentIngester().ingest_directory(directory, metadata)
DocumentIngester().ingest_text(text, doc_id, metadata)
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from core.intelligence.rag import config as rag_config
from core.intelligence.rag.core.embedder import Embedder
from core.intelligence.rag.core.vector_store import VectorStore

logger = logging.getLogger(__name__)


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Split text into overlapping token-approximate chunks.
    Uses word-level splitting as a token proxy (1 token ≈ 0.75 words).
    """
    words = text.split()
    word_chunk = int(chunk_size * 0.75)
    word_overlap = int(overlap * 0.75)
    step = max(1, word_chunk - word_overlap)

    chunks = []
    for i in range(0, len(words), step):
        chunk = " ".join(words[i: i + word_chunk])
        if chunk.strip():
            chunks.append(chunk.strip())
        if i + word_chunk >= len(words):
            break
    return chunks


def _read_pdf(path: Path) -> str:
    """Extract text from a PDF file using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except ImportError:
        raise ImportError("pypdf not installed. Run: pip install pypdf")
    except Exception as exc:
        logger.error("[Ingestion] PDF read failed for %s: %s", path, exc)
        return ""


def _read_txt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        logger.error("[Ingestion] TXT read failed for %s: %s", path, exc)
        return ""


def _doc_id(text: str, source: str, chunk_idx: int) -> str:
    """Deterministic chunk ID based on content hash + source + index."""
    h = hashlib.md5(text.encode()).hexdigest()[:8]
    safe_source = re.sub(r"[^a-zA-Z0-9_-]", "_", source)[:40]
    return f"{safe_source}__{chunk_idx}__{h}"


class DocumentIngester:
    """
    Handles reading, chunking, embedding, and storing documents.

    Usage
    -----
    ingester = DocumentIngester()
    ingester.ingest_file(Path("data/earnings_transcripts/MARUTI_Q3FY26.pdf"),
                         metadata={"ticker": "MARUTI", "doc_type": "earnings"})
    """

    def __init__(self) -> None:
        self._embedder = Embedder()
        self._store = VectorStore()

    def ingest_text(
        self,
        text: str,
        doc_id: str,
        metadata: dict | None = None,
    ) -> int:
        """
        Chunk a raw text string and store in the vector store.

        Returns number of chunks ingested.
        """
        if not text.strip():
            return 0

        metadata = metadata or {}
        chunks = _chunk_text(text, rag_config.CHUNK_SIZE, rag_config.CHUNK_OVERLAP)
        if not chunks:
            return 0

        ids = [_doc_id(c, doc_id, i) for i, c in enumerate(chunks)]
        metas = [{**metadata, "source": doc_id, "chunk_index": i} for i in range(len(chunks))]
        embeddings = self._embedder.embed_batch(chunks)

        self._store.upsert(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metas)
        logger.info("[Ingestion] Ingested %d chunks from '%s'", len(chunks), doc_id)
        return len(chunks)

    def ingest_file(self, path: Path, metadata: dict | None = None) -> int:
        """
        Read and ingest a single PDF or TXT file.

        Returns number of chunks ingested.
        """
        path = Path(path)
        if not path.exists():
            logger.warning("[Ingestion] File not found: %s", path)
            return 0

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = _read_pdf(path)
        elif suffix in {".txt", ".md"}:
            text = _read_txt(path)
        else:
            logger.warning("[Ingestion] Unsupported file type: %s", suffix)
            return 0

        meta = {"filename": path.name, "file_type": suffix, **(metadata or {})}
        return self.ingest_text(text, doc_id=str(path), metadata=meta)

    def ingest_directory(
        self,
        directory: str | Path,
        metadata: dict | None = None,
        recursive: bool = True,
    ) -> int:
        """
        Ingest all PDF and TXT files in a directory.

        Returns total chunks ingested.
        """
        directory = Path(directory)
        if not directory.is_dir():
            logger.warning("[Ingestion] Directory not found: %s", directory)
            return 0

        pattern = "**/*" if recursive else "*"
        files = [
            f for f in directory.glob(pattern)
            if f.suffix.lower() in {".pdf", ".txt", ".md"} and f.is_file()
        ]
        logger.info("[Ingestion] Found %d files in %s", len(files), directory)

        total = 0
        for f in files:
            total += self.ingest_file(f, metadata=metadata)
        logger.info("[Ingestion] Total chunks ingested from directory: %d", total)
        return total

    @property
    def collection_size(self) -> int:
        return self._store.count()
