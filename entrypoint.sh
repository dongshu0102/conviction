#!/bin/sh
# Runs pending Alembic migrations before starting the app. Necessary
# because init_db()/create_all() was deliberately removed from app
# startup (see src/api/main.py) — that was the source of the multi-worker
# race condition hit during development. Alembic is now the only thing
# that creates or alters schema.
#
# Known limitation for production: if App Runner scales to multiple
# concurrent instances, each container runs `alembic upgrade head` on
# startup, and Alembic has no built-in distributed lock — two instances
# starting simultaneously against a brand-new database could race on the
# same migration. For a single-developer MVP with low deploy frequency
# this is an acceptable risk; the real fix (running migrations as a
# separate one-off step before the new revision receives traffic) is
# worth doing before this has meaningful concurrent deploy traffic.
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 1
