from __future__ import annotations

from before_notification_pipeline import (
    BrokerUnavailable,
    FakeBroker as BeforeBroker,
    UnknownTask,
    create_ticket_and_queue_notification as before_pipeline,
)
from after_notification_pipeline import (
    FakeBroker as AfterBroker,
    create_ticket_and_queue_notification as after_pipeline,
)


TICKET = {"id": 42, "recipient": "agent@example.com"}


def test_before_breaks_when_broker_is_down() -> None:
    broker = BeforeBroker(available=False, registered_tasks={"incident.notify_ticket"})
    try:
        before_pipeline(broker, TICKET)
    except BrokerUnavailable:
        return
    raise AssertionError("Expected the before version to fail when the broker is unavailable.")


def test_before_breaks_when_task_is_missing() -> None:
    broker = BeforeBroker(available=True, registered_tasks=set())
    try:
        before_pipeline(broker, TICKET)
    except UnknownTask:
        return
    raise AssertionError("Expected the before version to fail when the task is not registered.")


def test_after_degrades_gracefully() -> None:
    broker = AfterBroker(available=False, registered_tasks=set())
    degraded_events: list[dict] = []
    result = after_pipeline(broker, degraded_events, TICKET)
    assert result["delivery_mode"] == "degraded"
    assert len(degraded_events) == 1
    assert broker.published == []


def test_after_brokers_when_ready() -> None:
    broker = AfterBroker(available=True, registered_tasks={"incident.notify_ticket"})
    degraded_events: list[dict] = []
    result = after_pipeline(broker, degraded_events, TICKET)
    assert result["delivery_mode"] == "brokered"
    assert degraded_events == []
    assert broker.published == [("incident.notify_ticket", {"ticket_id": 42, "recipient": "agent@example.com"})]


if __name__ == "__main__":
    test_before_breaks_when_broker_is_down()
    test_before_breaks_when_task_is_missing()
    test_after_degrades_gracefully()
    test_after_brokers_when_ready()
    print("notification pipeline case-study sample passed")
