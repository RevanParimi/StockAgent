"""
scripts/ingest_documents.py
============================
CLI tool to index documents into the ChromaDB vector store.

Usage
-----
# Ingest all PDFs/TXTs under data/ (default directories from rag_config)
python scripts/ingest_documents.py

# Ingest a specific directory
python scripts/ingest_documents.py --dir data/earnings_transcripts --ticker MARUTI

# Ingest a single file
python scripts/ingest_documents.py --file data/annual_reports/MARUTI_AR2025.pdf --ticker MARUTI

# Clear the collection and re-ingest everything
python scripts/ingest_documents.py --reset

# Show collection stats only
python scripts/ingest_documents.py --stats
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path so imports work when run from any directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def print_stats(ingester) -> None:
    count = ingester.collection_size
    print(f"\nVector store stats:")
    print(f"  Collection : {__import__('config.rag_config', fromlist=['rag_config']).rag_config.CHROMA_COLLECTION_NAME}")
    print(f"  Total chunks indexed: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest documents into the Automobile Agent RAG vector store"
    )
    parser.add_argument("--dir",    help="Directory to ingest (recursive)")
    parser.add_argument("--file",   help="Single file to ingest")
    parser.add_argument("--ticker", help="NSE ticker to tag documents with (e.g. MARUTI)")
    parser.add_argument("--doc-type", default="general",
                        help="Document type tag: earnings | annual_report | sector_report | news")
    parser.add_argument("--reset", action="store_true",
                        help="Delete and recreate the vector store before ingesting")
    parser.add_argument("--stats", action="store_true",
                        help="Show collection statistics and exit")

    args = parser.parse_args()

    # Lazy imports after sys.path fix
    from config import rag_config
    if not rag_config.RAG_ENABLED:
        print(
            "\nRAG is currently disabled.\n"
            "Set RAG_ENABLED=true in your .env file to activate it.\n"
        )
        sys.exit(0)

    from tools.rag.ingestion import DocumentIngester
    from tools.rag.vector_store import VectorStore

    ingester = DocumentIngester()

    if args.stats:
        print_stats(ingester)
        sys.exit(0)

    if args.reset:
        confirm = input("This will DELETE all indexed documents. Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)
        VectorStore().delete_collection()
        print("Collection cleared.")

    metadata: dict = {"doc_type": args.doc_type}
    if args.ticker:
        metadata["ticker"] = args.ticker.upper()

    total_chunks = 0

    if args.file:
        path = Path(args.file)
        print(f"\nIngesting file: {path}")
        n = ingester.ingest_file(path, metadata=metadata)
        total_chunks += n
        print(f"  → {n} chunks ingested")

    elif args.dir:
        directory = Path(args.dir)
        print(f"\nIngesting directory: {directory}")
        n = ingester.ingest_directory(directory, metadata=metadata)
        total_chunks += n
        print(f"  → {n} chunks ingested")

    else:
        # Default: ingest all configured directories from rag_config
        print("\nIngesting all configured knowledge-base directories...")
        from config import rag_config as rc
        for dir_path in rc.KB_DOCUMENT_DIRS:
            p = Path(dir_path)
            if p.is_dir():
                print(f"  Processing: {p}")
                n = ingester.ingest_directory(p, metadata=metadata)
                total_chunks += n
                print(f"    → {n} chunks")
            else:
                print(f"  Skipped (not found): {p}")

    print(f"\nDone. Total chunks ingested this run: {total_chunks}")
    print_stats(ingester)


if __name__ == "__main__":
    main()
