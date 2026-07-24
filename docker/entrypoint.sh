#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] Waiting for database..."
# Run migrations to head. asyncpg URL is auto-swapped to psycopg2 in env.py.
alembic upgrade head

echo "[entrypoint] Starting uvicorn (single worker)..."
# Single worker is required: the cancellation registry lives in process memory
# (see design doc 5.6).
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
