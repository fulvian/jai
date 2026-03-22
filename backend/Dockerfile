# =============================================================================
# Me4BrAIn - Multi-Stage Production Dockerfile
# =============================================================================
# Compatibile con: macOS (Apple Silicon), Linux x86_64, ARM64
# =============================================================================
# NOTE: BGE-M3 model (~800MB) is downloaded at first startup for lightweight image.
# For production deployment, consider using a Docker volume for model caching.
# =============================================================================

# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock README.md ./

# Install dependencies (no dev)
RUN uv sync --frozen --no-dev --no-editable

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Security: non-root user
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ ./src/

# Create directories and set ownership
RUN mkdir -p /app/models /home/appuser/.cache/huggingface && \
    chown -R appuser:appgroup /app /home/appuser/.cache

# Set environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HF_HOME="/home/appuser/.cache/huggingface"

# Switch to non-root user
USER appuser

# Health check (increased start period for model loading on first run)
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Default command
CMD ["uvicorn", "me4brain.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--loop", "asyncio"]
