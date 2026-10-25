import unittest
from unittest.mock import patch

from app.core.config import settings
from app.main import enqueue_notification


class NotificationDispatchTests(unittest.TestCase):
    def test_eager_dispatch_executes_task_without_connecting_to_redis(self):
        with (
            patch.object(settings, "celery_task_always_eager", True),
            patch("app.main.socket.create_connection") as connect,
            patch("app.main.notify_ticket_change") as task,
        ):
            enqueue_notification("assignment_changed", "ticket-1", "agent-1")

        task.apply.assert_called_once_with(args=("assignment_changed", "ticket-1", "agent-1"), throw=True)
        task.delay.assert_not_called()
        connect.assert_not_called()

    def test_eager_failure_does_not_escape_to_committed_ticket_request(self):
        with (
            patch.object(settings, "celery_task_always_eager", True),
            patch("app.main.notify_ticket_change.apply", side_effect=RuntimeError("task failed")) as apply,
        ):
            enqueue_notification("ticket_created", "ticket-1")
        apply.assert_called_once()

    def test_brokered_dispatch_queues_task_after_connection_check(self):
        with (
            patch.object(settings, "celery_task_always_eager", False),
            patch("app.main.socket.create_connection") as connect,
            patch("app.main.notify_ticket_change") as task,
        ):
            enqueue_notification("status_changed", "ticket-1", "reporter-1")

        connect.assert_called_once()
        task.delay.assert_called_once_with("status_changed", "ticket-1", "reporter-1")
        task.apply.assert_not_called()

    def test_unavailable_broker_skips_task_publish(self):
        with (
            patch.object(settings, "celery_task_always_eager", False),
            patch("app.main.socket.create_connection", side_effect=OSError("offline")),
            patch("app.main.notify_ticket_change") as task,
        ):
            enqueue_notification("ticket_created", "ticket-1")
        task.delay.assert_not_called()
