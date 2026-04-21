from __future__ import annotations

from dataclasses import dataclass, field


TASK_NAME = "incident.notify_ticket"


@dataclass
class FakeBroker:
    available: bool
    registered_tasks: set[str]
    published: list[tuple[str, dict]] = field(default_factory=list)

    def publish(self, task_name: str, payload: dict) -> None:
        self.published.append((task_name, payload))


def broker_ready(broker: FakeBroker) -> bool:
    return broker.available and TASK_NAME in broker.registered_tasks


def create_ticket_and_queue_notification(
    broker: FakeBroker,
    degraded_events: list[dict],
    ticket: dict,
) -> dict:
    payload = {"ticket_id": ticket["id"], "recipient": ticket["recipient"]}

    if not broker_ready(broker):
        degraded_events.append({"task": TASK_NAME, "payload": payload})
        return {"ticket_id": ticket["id"], "delivery_mode": "degraded"}

    broker.publish(TASK_NAME, payload)
    return {"ticket_id": ticket["id"], "delivery_mode": "brokered"}
