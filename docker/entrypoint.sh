#!/bin/sh
set -e
echo "Running migrations..."
alembic upgrade head
echo "Seeding database..."
python scripts/seed.py || true
echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
