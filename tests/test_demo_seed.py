from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.core.config import settings
from app.main import demo_users, seed_demo_users
from app.models import User, UserRole
from app.security import hash_password, verify_password


class DemoSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_seed_creates_missing_demo_users_and_can_be_repeated(self) -> None:
        seed_demo_users(self.session)
        original = {
            user.email: (user.id, user.hashed_password)
            for user in self.session.scalars(select(User))
        }

        seed_demo_users(self.session)
        repeated = {
            user.email: (user.id, user.hashed_password)
            for user in self.session.scalars(select(User))
        }

        self.assertEqual(len(original), 3)
        self.assertEqual(original, repeated)
        self.assertTrue(all(verify_password("ChangeMe123!", hashed) for _, hashed in original.values()))

    def test_seed_preserves_existing_password_role_profile_and_disabled_state(self) -> None:
        user = User(
            full_name="Renamed Operator",
            email="admin@example.com",
            role=UserRole.reporter,
            is_active=False,
            hashed_password=hash_password("ChangedPassword456!"),
        )
        self.session.add(user)
        self.session.commit()

        seed_demo_users(self.session)
        self.session.refresh(user)

        self.assertEqual(user.full_name, "Renamed Operator")
        self.assertEqual(user.role, UserRole.reporter)
        self.assertFalse(user.is_active)
        self.assertTrue(verify_password("ChangedPassword456!", user.hashed_password))
        self.assertFalse(verify_password("ChangeMe123!", user.hashed_password))
        self.assertEqual(len(list(self.session.scalars(select(User)))), 3)

    def test_seed_recognizes_existing_email_case_insensitively(self) -> None:
        user = User(
            full_name="Existing Admin",
            email="ADMIN@EXAMPLE.COM",
            role=UserRole.admin,
            hashed_password=hash_password("ChangedPassword456!"),
        )
        self.session.add(user)
        self.session.commit()

        seed_demo_users(self.session)

        users = list(self.session.scalars(select(User)))
        self.assertEqual(len(users), 3)
        self.assertEqual(sum(item.email.lower() == "admin@example.com" for item in users), 1)

    def test_public_demo_directory_excludes_ordinary_accounts(self) -> None:
        seed_demo_users(self.session)
        self.session.add(User(
            full_name="Private Customer", email="private.customer@example.com", role=UserRole.reporter,
            hashed_password=hash_password("PrivatePassword456!"),
        ))
        self.session.commit()

        with patch.object(settings, "demo_mode", True):
            directory = demo_users(session=self.session)

        self.assertEqual({user.email for user in directory}, {
            "admin@example.com", "agent@example.com", "reporter@example.com",
        })

    def test_public_demo_directory_matches_case_and_omits_disabled_demo_users(self) -> None:
        self.session.add(User(
            full_name="Existing Admin", email="ADMIN@EXAMPLE.COM", role=UserRole.admin,
            hashed_password=hash_password("ChangedPassword456!"),
        ))
        self.session.commit()
        seed_demo_users(self.session)
        reporter = self.session.scalar(select(User).where(User.email == "reporter@example.com"))
        reporter.is_active = False
        self.session.commit()

        with patch.object(settings, "demo_mode", True):
            directory = demo_users(session=self.session)

        self.assertEqual({user.email for user in directory}, {"ADMIN@EXAMPLE.COM", "agent@example.com"})


if __name__ == "__main__":
    unittest.main()
