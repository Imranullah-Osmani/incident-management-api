from app.celery_app import celery_app


@celery_app.task(name="incident.notify_ticket")
def notify_ticket_change(event_type: str, ticket_id: str, recipient: str | None = None) -> dict:
    return {
        "event_type": event_type,
        "ticket_id": ticket_id,
        "recipient": recipient,
        "status": "queued",
    }

