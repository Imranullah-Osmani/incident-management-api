from __future__ import annotations

import os
import unittest


os.environ["DATABASE_URL"] = "sqlite:///./data/test_incidents_policy.db"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6390/0"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "True"

from fastapi import HTTPException

from app.database import Base, SessionLocal, engine
from app.main import ensure_agent_or_admin, enqueue_notification, visible_ticket_query
from app.models import Ticket, TicketVisibility, User, UserRole
from app.security import hash_password


class VisibilityPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.session = SessionLocal()

        self.admin = self.create_user("admin@example.com", UserRole.admin)
        self.agent = self.create_user("agent@example.com", UserRole.agent)
        self.reporter = self.create_user("reporter@example.com", UserRole.reporter)
        self.second_reporter = self.create_user("second-reporter@example.com", UserRole.reporter)

        self.public_ticket = self.create_ticket(
            "Public customer ticket",
            TicketVisibility.public,
            created_by_id=self.reporter.id,
        )
        self.internal_ticket = self.create_ticket(
            "Internal operations ticket",
            TicketVisibility.internal,
            created_by_id=self.reporter.id,
        )
        self.assigned_restricted_ticket = self.create_ticket(
            "Assigned restricted ticket",
            TicketVisibility.restricted,
            created_by_id=self.reporter.id,
            assigned_to_id=self.agent.id,
        )
        self.hidden_restricted_ticket = self.create_ticket(
            "Hidden restricted ticket",
            TicketVisibility.restricted,
            created_by_id=self.second_reporter.id,
        )
        self.own_restricted_ticket = self.create_ticket(
            "Own restricted ticket",
            TicketVisibility.restricted,
            created_by_id=self.agent.id,
        )

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    def create_user(self, email: str, role: UserRole) -> User:
        user = User(
            full_name=email.split("@")[0].replace("-", " ").title(),
            email=email,
            role=role,
            hashed_password=hash_password("ChangeMe123!"),
        )
        self.session.add(user)
        self.session.flush()
        return user

    def create_ticket(
        self,
        title: str,
        visibility: TicketVisibility,
        *,
        created_by_id: str,
        assigned_to_id: str | None = None,
    ) -> Ticket:
        ticket = Ticket(
            title=title,
            description="Detailed incident context for policy testing.",
            priority="medium",
            visibility=visibility,
            tags=["policy"],
            created_by_id=created_by_id,
            assigned_to_id=assigned_to_id,
        )
        self.session.add(ticket)
        self.session.flush()
        return ticket

    def visible_titles_for(self, user: User) -> set[str]:
        tickets = self.session.scalars(visible_ticket_query(self.session, user)).all()
        return {ticket.title for ticket in tickets}

    def test_admin_can_see_all_tickets(self) -> None:
        self.assertEqual(
            self.visible_titles_for(self.admin),
            {
                "Public customer ticket",
                "Internal operations ticket",
                "Assigned restricted ticket",
                "Hidden restricted ticket",
                "Own restricted ticket",
            },
        )

    def test_agent_sees_public_internal_assigned_and_self_created_tickets(self) -> None:
        self.assertEqual(
            self.visible_titles_for(self.agent),
            {
                "Public customer ticket",
                "Internal operations ticket",
                "Assigned restricted ticket",
                "Own restricted ticket",
            },
        )

    def test_reporter_sees_only_own_tickets(self) -> None:
        self.assertEqual(
            self.visible_titles_for(self.reporter),
            {
                "Public customer ticket",
                "Internal operations ticket",
                "Assigned restricted ticket",
            },
        )

    def test_reporter_cannot_perform_agent_actions(self) -> None:
        with self.assertRaises(HTTPException) as context:
            ensure_agent_or_admin(self.reporter)

        self.assertEqual(context.exception.status_code, 403)

    def test_notification_enqueue_degrades_without_redis(self) -> None:
        enqueue_notification("ticket_created", self.public_ticket.id)


if __name__ == "__main__":
    unittest.main()
