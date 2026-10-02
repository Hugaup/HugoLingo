#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Seeding verb conjugations (skipped if already seeded)..."
python scripts/seed_conjugations.py

echo "Seeding vocabulary (upsert, safe to re-run)..."
python scripts/seed_vocabulary.py

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
