# Use official Python runtime with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Set working directory
WORKDIR /app

# Enable bytecode compilation and unbuffered stdout
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    CHARTS_DIR="/app/charts" \
    DATA_DIR="/app/data"

# Copy dependency specifications first for Docker layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy application source code
COPY app/ ./app/
COPY README.md ./

# Complete project installation
RUN uv sync --frozen --no-dev

# Create data directories
RUN mkdir -p /app/data /app/charts

# Expose default port
EXPOSE 8080

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/utils/Ping')" || exit 1

# Start FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
