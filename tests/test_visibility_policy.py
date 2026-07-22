from __future__ import annotations

import os
import unittest


os.environ["DATABASE_URL"] = "sqlite:///./data/test_incidents_policy.db"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6390/0"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "True"

from fastapi import HTTPException

from app.database import Base, SessionLocal, engine
from app.main import demo_users, ensure_agent_or_admin, enqueue_notification, list_visible_tickets, login, summarize_visible_tickets, visible_ticket_query
from app.models import Ticket, TicketStatus, TicketVisibility, User, UserRole
from app.schemas import LoginRequest
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
        priority: str = "medium",
        status: TicketStatus = TicketStatus.new,
        tags: list[str] | None = None,
    ) -> Ticket:
        ticket = Ticket(
            title=title,
            description="Detailed incident context for policy testing.",
            priority=priority,
            status=status,
            visibility=visibility,
            tags=tags or ["policy"],
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

    def test_ticket_list_filters_visible_results_by_status_priority_and_tag(self) -> None:
        self.internal_ticket.status = TicketStatus.investigating
        self.internal_ticket.priority = "high"
        self.internal_ticket.tags = ["policy", "checkout"]
        self.public_ticket.priority = "low"
        self.session.commit()

        tickets = list_visible_tickets(
            self.session,
            self.admin,
            status_filter=TicketStatus.investigating,
            priority="HIGH",
            tag="checkout",
        )

        self.assertEqual([ticket.title for ticket in tickets], ["Internal operations ticket"])

    def test_ticket_list_filters_visible_results_by_visibility(self) -> None:
        tickets = list_visible_tickets(self.session, self.admin, visibility=TicketVisibility.restricted)

        self.assertEqual({ticket.title for ticket in tickets}, {"Assigned restricted ticket", "Hidden restricted ticket", "Own restricted ticket"})

    def test_ticket_list_rejects_unknown_priority_filter(self) -> None:
        with self.assertRaises(HTTPException) as context:
            list_visible_tickets(self.session, self.admin, priority="urgent")

        self.assertEqual(context.exception.status_code, 400)

    def test_ticket_list_filters_by_assignment_owner(self) -> None:
        own_queue = list_visible_tickets(self.session, self.agent, assigned_to="me")
        unassigned = list_visible_tickets(self.session, self.admin, assigned_to="unassigned")
        explicit_owner = list_visible_tickets(self.session, self.admin, assigned_to=self.agent.id)

        self.assertEqual({ticket.title for ticket in own_queue}, {"Assigned restricted ticket"})
        self.assertIn("Public customer ticket", {ticket.title for ticket in unassigned})
        self.assertEqual({ticket.title for ticket in explicit_owner}, {"Assigned restricted ticket"})

    def test_ticket_list_ignores_blank_assignment_filter(self) -> None:
        baseline = list_visible_tickets(self.session, self.agent)
        filtered = list_visible_tickets(self.session, self.agent, assigned_to="   ")

        self.assertEqual([ticket.id for ticket in filtered], [ticket.id for ticket in baseline])

    def test_ticket_summary_counts_only_visible_tickets(self) -> None:
        self.internal_ticket.status = TicketStatus.investigating
        self.internal_ticket.priority = "high"
        self.session.commit()

        reporter_summary = summarize_visible_tickets(self.session, self.reporter)
        agent_summary = summarize_visible_tickets(self.session, self.agent)

        self.assertEqual(reporter_summary.visible_total, 3)
        self.assertEqual(reporter_summary.assigned_total, 1)
        self.assertEqual(reporter_summary.unassigned_total, 2)
        self.assertEqual(reporter_summary.status_counts["investigating"], 1)
        self.assertEqual(reporter_summary.priority_counts["high"], 1)
        self.assertEqual(list(reporter_summary.priority_counts.keys()), ["low", "medium", "high", "critical"])
        self.assertEqual(agent_summary.visible_total, 4)
        self.assertEqual(agent_summary.assigned_total, 1)
        self.assertEqual(agent_summary.unassigned_total, 3)

    def test_ticket_summary_accepts_same_filters_as_ticket_list(self) -> None:
        self.internal_ticket.status = TicketStatus.investigating
        self.internal_ticket.priority = "high"
        self.internal_ticket.tags = ["checkout"]
        self.session.commit()

        summary = summarize_visible_tickets(
            self.session,
            self.admin,
            status_filter=TicketStatus.investigating,
            priority="high",
            tag="checkout",
            visibility=TicketVisibility.internal,
        )

        self.assertEqual(summary.visible_total, 1)
        self.assertEqual(summary.status_counts["investigating"], 1)
        self.assertEqual(summary.priority_counts["high"], 1)

    def test_ticket_list_searches_visible_title_description_and_tags(self) -> None:
        self.internal_ticket.description = "Checkout webhook failures are affecting payments."
        self.internal_ticket.tags = ["checkout", "payments"]
        self.hidden_restricted_ticket.description = "Hidden checkout outage."
        self.hidden_restricted_ticket.tags = ["checkout"]
        self.session.commit()

        reporter_results = list_visible_tickets(self.session, self.reporter, query="checkout")
        agent_results = list_visible_tickets(self.session, self.agent, query="checkout")

        self.assertEqual({ticket.title for ticket in reporter_results}, {"Internal operations ticket"})
        self.assertEqual({ticket.title for ticket in agent_results}, {"Internal operations ticket"})

    def test_ticket_list_ignores_blank_search_and_tag_filters(self) -> None:
        baseline = list_visible_tickets(self.session, self.reporter)
        filtered = list_visible_tickets(self.session, self.reporter, query="   ", tag="   ")

        self.assertEqual([ticket.id for ticket in filtered], [ticket.id for ticket in baseline])

    def test_ticket_list_paginates_after_visibility_filters(self) -> None:
        baseline = list_visible_tickets(self.session, self.admin)
        paged = list_visible_tickets(self.session, self.admin, limit=2, offset=1)

        self.assertEqual([ticket.id for ticket in paged], [ticket.id for ticket in baseline][1:3])

    def test_inactive_user_cannot_login(self) -> None:
        self.reporter.is_active = False
        self.session.commit()

        with self.assertRaises(HTTPException) as context:
            login(LoginRequest(email=self.reporter.email, password="ChangeMe123!"), session=self.session)

        self.assertEqual(context.exception.status_code, 401)

    def test_login_matches_email_case_insensitively(self) -> None:
        token = login(LoginRequest(email="REPORTER@EXAMPLE.COM", password="ChangeMe123!"), session=self.session)

        self.assertEqual(token.token_type, "bearer")
        self.assertTrue(token.access_token)

    def test_demo_users_returns_only_active_accounts(self) -> None:
        self.reporter.is_active = False
        self.session.commit()

        users = demo_users(session=self.session)

        self.assertNotIn(self.reporter.email, {user.email for user in users})

    def test_notification_enqueue_degrades_without_redis(self) -> None:
        enqueue_notification("ticket_created", self.public_ticket.id)


if __name__ == "__main__":
    unittest.main()
