# Security Policy

This repository is a portfolio-grade incident-management API and backend repair case study. It is designed for local review and demonstration, but the security model mirrors the expectations of a real support or operations system.

## Supported Scope

Security review applies to the current `main` branch.

Covered areas:

- JWT authentication and token handling
- Role-based ticket visibility for `admin`, `agent`, and `reporter`
- Ticket assignment and status-transition authorization
- Notification dispatch behavior when Redis/Celery is degraded
- Health/readiness endpoint behavior
- Docker and dependency update hygiene

## Reporting

Please report suspected vulnerabilities privately through GitHub's vulnerability reporting tools when available. If private reporting is unavailable, open a minimal issue that describes the affected area without posting exploit details, credentials, tokens, or private data.

Useful report details:

- affected endpoint or workflow
- account role used during reproduction
- expected visibility or authorization behavior
- observed behavior
- impact and suggested severity

## Local Security Checks

Run the verification script before opening a pull request:

```powershell
.\scripts\verify.ps1
```

The script validates Docker Compose configuration, compiles the app, runs the incident tests, and runs the recreated case-study sample.

## Hardening Notes

- Never commit `.env`, local databases, logs, generated tokens, or secrets.
- Rotate `SECRET_KEY` and demo credentials before any real deployment.
- Keep Redis/Celery failures non-blocking for API writes but visible through readiness checks.
- Keep Dependabot alerts and GitHub Actions failures visible and triaged.
- Treat restricted tickets as sensitive operational data and test visibility changes carefully.
