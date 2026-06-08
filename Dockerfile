# Deterministic build for the Argos backend. Replaces Nixpacks, whose
# build-time fetch of the NixOS package archive from GitHub is flaky
# (intermittent HTTP 504s fail the whole build — see docs/DECISIONS.md
# 2026-06-08). python:3.11-slim is pulled from Docker Hub and layer-cached,
# so builds are reproducible and faster.
FROM python:3.11-slim

WORKDIR /app

# Install deps first for layer caching. All 8 runtime deps ship manylinux
# wheels, so -slim needs no compiler toolchain.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source + pre-run hero dossiers (read via ARGOS_DATA_ROOT=data).
COPY src ./src
COPY data ./data

ENV PYTHONPATH=/app/src
EXPOSE 8000
# Railway injects $PORT. CMD owns the start command (no railway.json startCommand).
CMD ["sh", "-c", "uvicorn argos.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
