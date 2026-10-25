# API Examples

These examples assume the service is running at `http://localhost:8002`.

Demo accounts:

When demo mode is enabled, the public `/demo/users` directory lists only the three known demo emails and omits disabled accounts. Ordinary application accounts are never included in this directory. Set `DEMO_MODE=False` to disable the directory entirely.

- `admin@example.com` / `ChangeMe123!`
- `agent@example.com` / `ChangeMe123!`
- `reporter@example.com` / `ChangeMe123!`

Startup creates demo accounts only when their email is missing (case-insensitive). Existing passwords, roles, profile names, and disabled states are preserved across restarts. The credentials above apply to newly seeded accounts; restarting does not reset changed credentials.

## 1. Issue a JWT

```bash
curl -s -X POST http://localhost:8002/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"ChangeMe123!"}'
```

Use the returned `access_token` as a bearer token in the remaining requests.

Bearer tokens must contain a subject and an expiration claim. Expired tokens, missing or null expirations, and invalid signatures return HTTP 401 with the same invalid-credentials response.

## 2. Check readiness

```bash
curl -s http://localhost:8002/health/ready
```

The readiness response reports database and Redis status plus the worker mode.
It returns HTTP `200` only when required dependencies are ready; if the database or Redis check fails, the API returns HTTP `503` with a degraded payload similar to:

```json
{
  "status": "degraded",
  "database": "ok",
  "redis": "error",
  "worker_mode": "brokered"
}
```

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

Reporters can create tickets, but only `admin` and `agent` users can set `assigned_to_id` during creation.

Restricted ticket ownership always requires an admin, including initial assignment during creation. Agents can create unassigned restricted tickets and request admin assignment later. Attempts to preassign a restricted ticket as an agent return HTTP 403 before a ticket or timeline event is written.

## 4. List visible tickets

```bash
curl -s "http://localhost:8002/tickets?visibility=internal&limit=25&offset=0" \
  -H "Authorization: Bearer <access-token>"
```

Admins see all tickets. Agents see operational tickets except restricted tickets assigned elsewhere. Reporters see only their own tickets.
Use `visibility`, `status`, `priority`, `tag`, `assigned_to`, `q`, `limit`, and `offset` for browser or dashboard filtering after RBAC visibility rules are applied. Text filters are capped at 100 characters to keep dashboard requests bounded. The summary endpoint accepts the same visibility-safe filters, for example `GET /tickets/summary?visibility=internal&status=investigating&priority=high`.

## 5. Move a ticket through the lifecycle

```bash
curl -s -X PATCH http://localhost:8002/tickets/<ticket-id>/status \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"status":"investigating","message":"Agent started the incident investigation."}'
```

The status change appends a timeline event and queues a notification when Redis/Celery is available. Ticket detail responses include each timeline event's `actor_id`, previous value, new value, message, and timestamp so dashboards can show who changed the incident.

## 6. Assign operational ownership

```bash
curl -s -X PATCH http://localhost:8002/tickets/<ticket-id>/assign \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"assigned_to_id":"<agent-or-admin-user-id>","message":"Assigned to the support owner."}'
```

Only active `admin` or `agent` users can be assigned to a ticket. Closed tickets reject reassignment so the incident timeline stays stable after resolution.

To return a ticket to the unassigned queue:

```bash
curl -s -X DELETE http://localhost:8002/tickets/<ticket-id>/assign \
  -H "Authorization: Bearer <access-token>"
```
