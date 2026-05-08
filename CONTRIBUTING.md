# Contributing

This repository is maintained as a compact incident-management API and backend repair case study. Contributions should strengthen the runnable service, the debugging story, or the operational reliability of the example.

## Local Setup

```powershell
copy .env.example .env
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Docker users can run the API plus async infrastructure with:

```powershell
docker compose --profile infra up --build api redis worker
```

## Verification

Run the full local verification script before opening a pull request:

```powershell
.\scripts\verify.ps1
```

The script validates Docker Compose configuration, compiles the application, runs incident tests, and verifies the recreated case-study sample.

## Change Guidelines

- Preserve role visibility boundaries for `admin`, `agent`, and `reporter`.
- Keep notification dispatch non-blocking when Redis or Celery is unavailable.
- Add or update tests when changing authentication, ticket visibility, assignment, lifecycle transitions, readiness checks, or notification behavior.
- Keep the recreated sample sanitized and independent from any confidential production code.
- Do not commit local `.env` files, databases, logs, generated tokens, or secrets.

## Pull Request Checklist

- The README or docs are updated when setup, endpoints, or workflows change.
- `.\scripts\verify.ps1` passes locally.
- New behavior has focused regression coverage.
- Security-sensitive changes are checked against [SECURITY.md](SECURITY.md).
