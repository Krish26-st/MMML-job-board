#!/bin/sh
# Render's free plan only offers the "Web Service" type for free -- it has
# no free tier for "Background Worker" services at all, which is what threw
# "service type is not available for this plan" for the worker/beat
# services. So instead of 3 separate Render services, everything runs
# inside this one container: the Celery worker and beat run as background
# processes, and uvicorn (the only thing Render's health check/port binding
# cares about) runs in the foreground as the container's main process.
#
# This does mean: if this free web service spins down from inactivity (as
# Render free web services do), the worker and beat go down with it, and
# come back up together on the next request. That trade-off was accepted
# explicitly in favor of staying fully free -- see README.
set -e

run_forever() {
  while true; do
    "$@" || true
    echo "[$(date)] '$*' exited -- restarting in 5s"
    sleep 5
  done
}

run_forever celery -A app.tasks.celery_app worker --loglevel=info --concurrency=1 &
run_forever celery -A app.tasks.celery_app beat --loglevel=info &

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
