"""
config/rag_config.py
====================
RAG (Retrieval-Augmented Generation) pipeline configuration.

Currently a stub — the pipeline is not yet active.
All settings here are forward-declared so that enabling RAG only requires
flipping RAG_ENABLED = True and filling in your vector-store credentials.
"""

import os

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------
RAG_ENABLED: bool = os.getenv("RAG_ENABLED", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------
EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "groq")
# When provider == "groq": uses Groq's embedding endpoint (if available)
# When provider == "openai": uses text-embedding-3-small
# When provider == "local": uses sentence-transformers (no API key needed)
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text-v1.5")
EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "768"))

# ---------------------------------------------------------------------------
# Vector store
# ---------------------------------------------------------------------------
VECTOR_STORE_PROVIDER: str = os.getenv("VECTOR_STORE_PROVIDER", "chromadb")
# Supported: chromadb | pinecone | weaviate | qdrant

CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db")
CHROMA_COLLECTION_NAME: str = os.getenv("CHROMA_COLLECTION_NAME", "automobile_agent_kb")

PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
PINECONE_ENVIRONMENT: str = os.getenv("PINECONE_ENVIRONMENT", "")
PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "automobile-agent")

QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "automobile_agent")

# ---------------------------------------------------------------------------
# Retrieval settings
# ---------------------------------------------------------------------------
TOP_K_RESULTS: int = int(os.getenv("RAG_TOP_K", "5"))
SIMILARITY_THRESHOLD: float = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.75"))
CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "512"))          # tokens per chunk
CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "64"))     # token overlap

# ---------------------------------------------------------------------------
# Knowledge-base document sources
# ---------------------------------------------------------------------------
# Local directories that will be indexed into the vector store
KB_DOCUMENT_DIRS: list[str] = [
    "data/earnings_transcripts",
    "data/annual_reports",
    "data/sector_reports",
    "data/news_archive",
]

# ---------------------------------------------------------------------------
# Re-ranker (optional second-stage ranking)
# ---------------------------------------------------------------------------
RERANKER_ENABLED: bool = os.getenv("RERANKER_ENABLED", "false").lower() == "true"
RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
