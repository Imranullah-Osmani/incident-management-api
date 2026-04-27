# Monitoring Notes

This project includes lightweight operational notes to show how the API would be observed in a real deployment.

## What to monitor

- API latency and request error rate by route
- Ticket creation volume and status transition volume
- Celery queue depth and task failure count
- Redis connectivity and broker round-trip health
- Database availability and slow query behavior

## Health endpoints

- `/health/live` confirms the FastAPI process is running
- `/health/ready` checks database connectivity, Redis connectivity, and reports worker mode

## Docker health checks

Docker Compose now checks:

- the API process through `/health/live`
- Redis with `redis-cli ping`
- optional PostgreSQL with `pg_isready`

The Celery worker waits for Redis to become healthy before it starts. That keeps the local async demo closer to the startup order used in production-style deployments.

## Suggested production additions

- Structured JSON logging with request id correlation
- Prometheus metrics for route timings and queue size
- Sentry or equivalent exception alerting
- Dead-letter handling for failed notification tasks
- Postgres-backed migrations through Alembic
