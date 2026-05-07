# ============================================================
# StockAgent — Python FastAPI
# Single-stage build (C++ pybind11 uses pure Python fallback
# when stockindicators.so is absent — fetcher.py handles it)
# ============================================================
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
# Note: config/ lives inside core/ — no separate top-level config dir
COPY core/       ./core/
COPY services/   ./services/
COPY src/backend/ ./backend/
COPY main.py     ./
COPY src/frontend/prototypes/ ./frontend/prototypes/

# Create data directories — volumes mount here at runtime
RUN mkdir -p \
    data/predictions \
    data/chroma_db \
    data/earnings_transcripts \
    data/annual_reports \
    data/sector_reports \
    data/news_archive \
    logs \
    outputs

EXPOSE 8000

# Railway injects $PORT — use shell form so the variable is expanded
CMD uvicorn services.api.server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --log-level info
