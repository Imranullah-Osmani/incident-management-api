from __future__ import annotations

import os
import unittest


os.environ["DATABASE_URL"] = "sqlite:///./data/test_incidents_lifecycle.db"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6390/0"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "True"

from fastapi import HTTPException
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.main import assign_ticket, create_ticket, update_ticket_status
from app.models import TicketEvent, TicketStatus, TicketVisibility, User, UserRole
from app.schemas import TicketAssign, TicketCreate, TicketStatusUpdate
from app.security import hash_password


class TicketLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.session = SessionLocal()

        self.admin = self.create_user("admin@example.com", UserRole.admin)
        self.agent = self.create_user("agent@example.com", UserRole.agent)
        self.reporter = self.create_user("reporter@example.com", UserRole.reporter)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    def create_user(self, email: str, role: UserRole) -> User:
        user = User(
            full_name=email.split("@")[0].title(),
            email=email,
            role=role,
            hashed_password=hash_password("ChangeMe123!"),
        )
        self.session.add(user)
        self.session.flush()
        return user

    def test_ticket_creation_writes_initial_timeline_event(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Checkout failure",
                description="Customers cannot complete checkout from the production storefront.",
                priority="high",
                visibility=TicketVisibility.internal,
                tags=["checkout", "production"],
            ),
            session=self.session,
            current_user=self.reporter,
        )

        events = self.session.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)).all()
        self.assertEqual(ticket.status, TicketStatus.new)
        self.assertEqual(ticket.created_by_id, self.reporter.id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "ticket_created")

    def test_agent_can_update_status_and_append_timeline_event(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Latency spike",
                description="API latency is above the internal incident threshold.",
                visibility=TicketVisibility.public,
            ),
            session=self.session,
            current_user=self.reporter,
        )

        updated = update_ticket_status(
            ticket.id,
            TicketStatusUpdate(status=TicketStatus.investigating, message="Agent started investigation."),
            session=self.session,
            current_user=self.agent,
        )

        status_events = [event for event in updated.events if event.event_type == "status_changed"]
        self.assertEqual(updated.status, TicketStatus.investigating)
        self.assertEqual(len(status_events), 1)
        self.assertEqual(status_events[0].previous_value, TicketStatus.new.value)
        self.assertEqual(status_events[0].new_value, TicketStatus.investigating.value)

    def test_assignment_requires_agent_or_admin_assignee(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Restricted production issue",
                description="Sensitive incident requiring controlled assignment.",
                visibility=TicketVisibility.restricted,
            ),
            session=self.session,
            current_user=self.reporter,
        )

        with self.assertRaises(HTTPException) as context:
            assign_ticket(
                ticket.id,
                TicketAssign(assigned_to_id=self.reporter.id, message="Invalid assignment"),
                session=self.session,
                current_user=self.admin,
            )

        self.assertEqual(context.exception.status_code, 400)

    def test_admin_can_assign_ticket_to_agent(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Payment processor outage",
                description="Payment provider webhook failures require support ownership.",
                visibility=TicketVisibility.public,
            ),
            session=self.session,
            current_user=self.reporter,
        )

        assigned = assign_ticket(
            ticket.id,
            TicketAssign(assigned_to_id=self.agent.id, message="Assigned to support agent."),
            session=self.session,
            current_user=self.admin,
        )

        assignment_events = [event for event in assigned.events if event.event_type == "assignment_changed"]
        self.assertEqual(assigned.assigned_to_id, self.agent.id)
        self.assertEqual(len(assignment_events), 1)
        self.assertEqual(assignment_events[0].new_value, self.agent.id)


if __name__ == "__main__":
    unittest.main()
