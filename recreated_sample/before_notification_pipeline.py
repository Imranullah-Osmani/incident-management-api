from __future__ import annotations

from dataclasses import dataclass, field


class BrokerUnavailable(RuntimeError):
    pass


class UnknownTask(RuntimeError):
    pass


@dataclass
class FakeBroker:
    available: bool
    registered_tasks: set[str]
    published: list[tuple[str, dict]] = field(default_factory=list)

    def publish(self, task_name: str, payload: dict) -> None:
        if not self.available:
            raise BrokerUnavailable("Broker connection failed.")
        if task_name not in self.registered_tasks:
            raise UnknownTask(f"Task `{task_name}` is not registered.")
        self.published.append((task_name, payload))


def create_ticket_and_queue_notification(broker: FakeBroker, ticket: dict) -> dict:
    payload = {"ticket_id": ticket["id"], "recipient": ticket["recipient"]}
    broker.publish("incident.notify_ticket", payload)
    return {"ticket_id": ticket["id"], "delivery_mode": "brokered"}
