# ============================================================
# StockAgent — Python FastAPI + C++ pybind11
# Multi-stage build: compile C++ indicators → slim runtime
# ============================================================

# ──────────────────────────────────────────────────────────
# Stage 1: C++ pybind11 build
# Compiles stockindicators.so (RSI, MACD, Bollinger Bands)
# Falls back gracefully if cmake/build fails — Python fallback exists
# ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS cpp-builder

ARG BUILD_CPP=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    python3-dev \
    pybind11-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY cpp/ ./cpp/

RUN if [ "$BUILD_CPP" = "true" ]; then \
        cmake -S cpp -B cpp/build \
              -DCMAKE_BUILD_TYPE=Release \
              -DPYTHON_EXECUTABLE=$(which python3) \
        && cmake --build cpp/build --config Release \
        && cmake --install cpp/build --config Release \
        && echo "C++ build succeeded" \
        || echo "C++ build failed — pure Python fallback will be used"; \
    fi

# ──────────────────────────────────────────────────────────
# Stage 2: Python runtime
# ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled C++ extension if it was built
# The try/except ImportError in fetcher.py handles the case where it's absent
COPY --from=cpp-builder /build/cpp/build/ /tmp/cpp_build/ 2>/dev/null || true
RUN find /tmp/cpp_build -name "stockindicators*.so" \
        -exec cp {} /usr/local/lib/python3.11/site-packages/ \; 2>/dev/null \
    && echo "Installed C++ extension" \
    || echo "No C++ extension found — pure Python fallback active"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY core/       ./core/
COPY config/     ./config/
COPY services/   ./services/
COPY scripts/    ./scripts/
COPY main.py     ./

# Create data directories — Docker volumes will mount here at runtime
# Nothing written here is persisted; volumes own these paths
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

CMD ["uvicorn", "services.api.server:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]
