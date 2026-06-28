# =============================================================================
# FILE: src/core/Dockerfile
# =============================================================================
# DESCRIPTION:
#   Container definition for the NETTRADES Core LangGraph Service.
#   This service hosts the Supervisor Agent and all specialised sub-agents.
#
# USAGE:
#   docker build -t nettrades-core -f src/core/Dockerfile .
#   docker run -p 8000:8000 -e DATABASE_URL=... -e LANGGRAPH_API_KEY=... nettrades-core
#
# CRITICAL FIXES (2026-06-28):
#   1. Previously only `app.py` was copied → ModuleNotFoundError for supervisor.py.
#      Now we copy the ENTIRE `src/core/` directory.
#   2. Added `libpq-dev` to compile psycopg (required for the `psycopg[binary]` wheel).
#   3. Added HEALTHCHECK to verify the service is responsive.
#   4. Set PYTHONUNBUFFERED=1 for immediate log streaming.
# =============================================================================

FROM python:3.12-slim

# -----------------------------------------------------------------------------
# Environment Variables
# -----------------------------------------------------------------------------
# Prevent Python from buffering stdout/stderr (logs appear immediately)
ENV PYTHONUNBUFFERED=1 \
    # Do not write .pyc files (saves space)
    PYTHONDONTWRITEBYTECODE=1 \
    # Disable pip cache (saves image size)
    PIP_NO_CACHE_DIR=1 \
    # Disable pip version check (speeds up builds)
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# -----------------------------------------------------------------------------
# Step 1: Install System Dependencies
# -----------------------------------------------------------------------------
# Required for psycopg (PostgreSQL adapter) and other native extensions.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# Step 2: Install Python Dependencies (Layered for Caching)
# -----------------------------------------------------------------------------
# Copy only requirements.txt first – this layer is cached unless the file changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Step 3: Copy the Entire Application Source
# -----------------------------------------------------------------------------
# CRITICAL FIX: Previously only app.py was copied.
# Now we copy all files (supervisor.py, agents/, tools/, odoo_proxy/, etc.)
# The .dockerignore file (see below) excludes temporary files.
COPY . .

# -----------------------------------------------------------------------------
# Step 4: Expose Port and Set Healthcheck
# -----------------------------------------------------------------------------
EXPOSE 8000

# Healthcheck – verifies the /health endpoint returns 200 OK.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# -----------------------------------------------------------------------------
# Step 5: Start Uvicorn Server
# -----------------------------------------------------------------------------
# `app:app` refers to app.py's FastAPI instance.
# The working directory is /app, and all imports are absolute (see supervisor.py).
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]