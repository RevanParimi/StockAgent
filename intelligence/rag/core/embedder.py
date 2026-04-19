"""
tools/rag/embedder.py
=====================
Text embedding using sentence-transformers (local, no API key).

The model is downloaded on first use (~90MB) and cached locally.
Change EMBEDDING_MODEL in config/rag_config.py to swap models.

Public API
----------
Embedder().embed(text)         → list[float]
Embedder().embed_batch(texts)  → list[list[float]]
"""

from __future__ import annotations

import logging
from functools import lru_cache

from intelligence.rag import config as rag_config

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_model():
    """Load and cache the sentence-transformer model (singleton)."""
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("[Embedder] Loading model: %s", rag_config.EMBEDDING_MODEL)
        return SentenceTransformer(rag_config.EMBEDDING_MODEL)
    except ImportError:
        raise ImportError(
            "sentence-transformers is not installed. "
            "Run: pip install sentence-transformers"
        )


class Embedder:
    """
    Wraps sentence-transformers for consistent embedding calls.

    Usage
    -----
    embedder = Embedder()
    vector = embedder.embed("Maruti Suzuki Q3 FY26 revenue grew 12% YoY")
    """

    def embed(self, text: str) -> list[float]:
        """Embed a single string → list of floats."""
        model = _load_model()
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """
        Embed a list of strings in batches.

        Returns list of float vectors in the same order as input.
        """
        if not texts:
            return []
        model = _load_model()
        logger.debug("[Embedder] Embedding %d texts", len(texts))
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    @property
    def dimension(self) -> int:
        """Return embedding dimension of the loaded model."""
        return rag_config.EMBEDDING_DIMENSION
