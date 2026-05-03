# API Examples

These examples assume the service is running at `http://localhost:8002`.

Demo accounts:

- `admin@example.com` / `ChangeMe123!`
- `agent@example.com` / `ChangeMe123!`
- `reporter@example.com` / `ChangeMe123!`

## 1. Issue a JWT

```bash
curl -s -X POST http://localhost:8002/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"ChangeMe123!"}'
```

Use the returned `access_token` as a bearer token in the remaining requests.

## 2. Check readiness

```bash
curl -s http://localhost:8002/health/ready
```

The readiness response reports database and Redis status plus the worker mode.

## 3. Create an incident ticket

```bash
curl -s -X POST http://localhost:8002/tickets \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Checkout latency spike",
    "description": "Checkout requests are timing out for customers.",
    "priority": "high",
    "visibility": "internal",
    "tags": ["checkout", "latency"]
  }'
```

## 4. List visible tickets

```bash
curl -s http://localhost:8002/tickets \
  -H "Authorization: Bearer <access-token>"
```

Admins see all tickets. Agents see operational tickets except restricted tickets assigned elsewhere. Reporters see only their own tickets.

## 5. Move a ticket through the lifecycle

```bash
curl -s -X PATCH http://localhost:8002/tickets/<ticket-id>/status \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"status":"investigating","message":"Agent started the incident investigation."}'
```

The status change appends a timeline event and queues a notification when Redis/Celery is available.

## 6. Assign operational ownership

```bash
curl -s -X PATCH http://localhost:8002/tickets/<ticket-id>/assign \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"assigned_to_id":"<agent-or-admin-user-id>","message":"Assigned to the support owner."}'
```

Only active `admin` or `agent` users can be assigned to a ticket.
