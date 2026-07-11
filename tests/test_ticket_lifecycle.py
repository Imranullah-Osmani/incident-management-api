from __future__ import annotations

import os
import unittest

from pydantic import ValidationError

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

    def test_ticket_creation_normalizes_tags(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Tag normalization",
                description="Incoming tags should be cleaned before storage.",
                priority="medium",
                visibility=TicketVisibility.internal,
                tags=[" API ", "api", "", "Checkout", "checkout"],
            ),
            session=self.session,
            current_user=self.reporter,
        )

        self.assertEqual(ticket.tags, ["api", "checkout"])

    def test_ticket_creation_strips_title_and_description(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="  Checkout outage  ",
                description="  Customers cannot complete payment from the storefront.  ",
                priority="high",
                visibility=TicketVisibility.internal,
            ),
            session=self.session,
            current_user=self.reporter,
        )

        self.assertEqual(ticket.title, "Checkout outage")
        self.assertEqual(ticket.description, "Customers cannot complete payment from the storefront.")

    def test_ticket_creation_accepts_critical_priority(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Critical payment outage",
                description="Payments are unavailable for all customers.",
                priority="critical",
                visibility=TicketVisibility.internal,
            ),
            session=self.session,
            current_user=self.reporter,
        )

        self.assertEqual(ticket.priority, "critical")

    def test_ticket_creation_normalizes_priority(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Priority normalization",
                description="Priority values entered by operators should be normalized.",
                priority=" HIGH ",
                visibility=TicketVisibility.internal,
            ),
            session=self.session,
            current_user=self.reporter,
        )

        self.assertEqual(ticket.priority, "high")

    def test_ticket_creation_rejects_unknown_priority(self) -> None:
        with self.assertRaises(ValidationError):
            TicketCreate(
                title="Unknown priority",
                description="Priority must be one of the supported operational levels.",
                priority="urgent",
            )

    def test_ticket_creation_rejects_reporter_assignee(self) -> None:
        with self.assertRaises(HTTPException) as context:
            create_ticket(
                TicketCreate(
                    title="Invalid initial assignment",
                    description="Reporter accounts should not receive operational ownership.",
                    visibility=TicketVisibility.internal,
                    assigned_to_id=self.reporter.id,
                ),
                session=self.session,
                current_user=self.admin,
            )

        self.assertEqual(context.exception.status_code, 400)

    def test_ticket_creation_allows_initial_agent_assignment(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Preassigned escalation",
                description="A known support owner is selected when the ticket is opened.",
                visibility=TicketVisibility.internal,
                assigned_to_id=self.agent.id,
            ),
            session=self.session,
            current_user=self.admin,
        )

        self.assertEqual(ticket.assigned_to_id, self.agent.id)

    def test_ticket_creation_strips_initial_assignee_id(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Copied assignee id",
                description="Operators often paste assignee identifiers from another screen.",
                visibility=TicketVisibility.internal,
                assigned_to_id=f"  {self.agent.id}  ",
            ),
            session=self.session,
            current_user=self.admin,
        )

        self.assertEqual(ticket.assigned_to_id, self.agent.id)

    def test_ticket_creation_treats_blank_initial_assignee_as_unassigned(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Blank initial assignee",
                description="Optional assignment fields from web forms may submit whitespace.",
                visibility=TicketVisibility.internal,
                assigned_to_id="   ",
            ),
            session=self.session,
            current_user=self.admin,
        )

        self.assertIsNone(ticket.assigned_to_id)

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

    def test_same_status_update_does_not_append_timeline_event(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Repeated status update",
                description="Repeated lifecycle writes should not create misleading history.",
                visibility=TicketVisibility.public,
            ),
            session=self.session,
            current_user=self.reporter,
        )

        unchanged = update_ticket_status(
            ticket.id,
            TicketStatusUpdate(status=TicketStatus.new, message="Already in this state."),
            session=self.session,
            current_user=self.agent,
        )

        events = self.session.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)).all()
        self.assertEqual(unchanged.status, TicketStatus.new)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "ticket_created")

    def test_status_update_rejects_invalid_lifecycle_jump(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Skipped lifecycle state",
                description="Closed should not be reachable directly from new.",
                visibility=TicketVisibility.public,
            ),
            session=self.session,
            current_user=self.reporter,
        )

        with self.assertRaises(HTTPException) as context:
            update_ticket_status(
                ticket.id,
                TicketStatusUpdate(status=TicketStatus.closed, message="Invalid direct close."),
                session=self.session,
                current_user=self.agent,
            )

        self.assertEqual(context.exception.status_code, 400)

    def test_status_update_allows_expected_lifecycle_sequence(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Expected lifecycle path",
                description="Ticket moves through investigation, resolution, and closure.",
                visibility=TicketVisibility.public,
            ),
            session=self.session,
            current_user=self.reporter,
        )

        investigating = update_ticket_status(
            ticket.id,
            TicketStatusUpdate(status=TicketStatus.investigating, message="Investigation started."),
            session=self.session,
            current_user=self.agent,
        )
        resolved = update_ticket_status(
            investigating.id,
            TicketStatusUpdate(status=TicketStatus.resolved, message="Issue resolved."),
            session=self.session,
            current_user=self.agent,
        )
        closed = update_ticket_status(
            resolved.id,
            TicketStatusUpdate(status=TicketStatus.closed, message="Incident closed."),
            session=self.session,
            current_user=self.agent,
        )

        self.assertEqual(closed.status, TicketStatus.closed)

    def test_ticket_detail_returns_timeline_events_in_chronological_order(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Ordered incident timeline",
                description="Timeline events should render in the order operators created them.",
                visibility=TicketVisibility.public,
            ),
            session=self.session,
            current_user=self.reporter,
        )
        investigating = update_ticket_status(
            ticket.id,
            TicketStatusUpdate(status=TicketStatus.investigating, message="Investigation started."),
            session=self.session,
            current_user=self.agent,
        )
        assigned = assign_ticket(
            investigating.id,
            TicketAssign(assigned_to_id=self.agent.id, message="Assigned to support agent."),
            session=self.session,
            current_user=self.admin,
        )

        self.assertEqual(
            [event.event_type for event in assigned.events],
            ["ticket_created", "status_changed", "assignment_changed"],
        )

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

    def test_assignment_payload_strips_assignee_id(self) -> None:
        payload = TicketAssign(assigned_to_id=f"  {self.agent.id}  ", message=" Assigned to agent. ")

        self.assertEqual(payload.assigned_to_id, self.agent.id)
        self.assertEqual(payload.message, "Assigned to agent.")

    def test_assignment_payload_rejects_blank_assignee_id(self) -> None:
        with self.assertRaises(ValidationError):
            TicketAssign(assigned_to_id="   ", message="Assigned to agent.")

    def test_same_assignment_does_not_append_timeline_event(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Repeated assignment update",
                description="Repeated assignment writes should not create duplicate history.",
                visibility=TicketVisibility.public,
                assigned_to_id=self.agent.id,
            ),
            session=self.session,
            current_user=self.admin,
        )

        unchanged = assign_ticket(
            ticket.id,
            TicketAssign(assigned_to_id=self.agent.id, message="Already assigned."),
            session=self.session,
            current_user=self.admin,
        )

        events = self.session.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)).all()
        self.assertEqual(unchanged.assigned_to_id, self.agent.id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "ticket_created")

    def test_closed_ticket_cannot_be_reassigned(self) -> None:
        ticket = create_ticket(
            TicketCreate(
                title="Closed assignment guard",
                description="Closed incidents should not accept operational ownership changes.",
                visibility=TicketVisibility.public,
            ),
            session=self.session,
            current_user=self.reporter,
        )
        investigating = update_ticket_status(
            ticket.id,
            TicketStatusUpdate(status=TicketStatus.investigating, message="Investigation started."),
            session=self.session,
            current_user=self.agent,
        )
        resolved = update_ticket_status(
            investigating.id,
            TicketStatusUpdate(status=TicketStatus.resolved, message="Issue resolved."),
            session=self.session,
            current_user=self.agent,
        )
        closed = update_ticket_status(
            resolved.id,
            TicketStatusUpdate(status=TicketStatus.closed, message="Incident closed."),
            session=self.session,
            current_user=self.agent,
        )

        with self.assertRaises(HTTPException) as context:
            assign_ticket(
                closed.id,
                TicketAssign(assigned_to_id=self.agent.id, message="Assign after close."),
                session=self.session,
                current_user=self.admin,
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("Closed tickets cannot be reassigned", context.exception.detail)

    def test_timeline_messages_are_stripped_and_validated(self) -> None:
        update = TicketStatusUpdate(status=TicketStatus.acknowledged, message="  Acknowledged by support.  ")
        assignment = TicketAssign(assigned_to_id=self.agent.id, message="  Assigned to agent.  ")

        self.assertEqual(update.message, "Acknowledged by support.")
        self.assertEqual(assignment.message, "Assigned to agent.")
        with self.assertRaises(ValidationError):
            TicketStatusUpdate(status=TicketStatus.acknowledged, message="   ")


if __name__ == "__main__":
    unittest.main()
