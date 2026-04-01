# =============================================================================
# MuniRev Dockerfile -- Multi-stage build
# Stage 1: Build frontend (Vite/TypeScript)
# Stage 2: Python runtime serving FastAPI + static frontend
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1 -- Frontend build
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend-build

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
COPY backend/assets/copo_directory.csv /build/backend/assets/copo_directory.csv
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 -- Python runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install only the OS packages needed at runtime, then clean up
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN groupadd --gid 1000 munirev \
    && useradd --uid 1000 --gid munirev --shell /bin/bash --create-home munirev

# Set up the application directory structure
WORKDIR /app

# Install Python dependencies first (layer cache optimisation)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy backend source
COPY backend/ /app/backend/
COPY scripts/ /app/scripts/

# Copy built frontend from stage 1 into the location the backend expects:
#   BASE_DIR        = /app/backend
#   FRONTEND_DIST   = BASE_DIR.parent / "frontend" / "dist"  =>  /app/frontend/dist
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist

# Ownership
RUN chown -R munirev:munirev /app

# Switch to non-root user
USER munirev

# The FastAPI app module path is relative to this working directory
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
