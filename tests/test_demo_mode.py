import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, Request

from app.core.config import settings
from app.main import demo_users, homepage, on_startup


class DemoModeTests(unittest.TestCase):
    def test_disabled_mode_does_not_seed_accounts_on_startup(self):
        with (
            patch.object(settings, "demo_mode", False),
            patch("app.main.Base.metadata.create_all") as create_tables,
            patch("app.main.SessionLocal") as sessions,
            patch("app.main.seed_demo_users") as seed,
        ):
            on_startup()
        create_tables.assert_called_once()
        sessions.assert_not_called()
        seed.assert_not_called()

    def test_enabled_mode_seeds_accounts(self):
        with (
            patch.object(settings, "demo_mode", True),
            patch("app.main.Base.metadata.create_all"),
            patch("app.main.SessionLocal") as sessions,
            patch("app.main.seed_demo_users") as seed,
        ):
            on_startup()
        seed.assert_called_once_with(sessions.return_value.__enter__.return_value)

    def test_disabled_demo_directory_returns_404_without_querying_users(self):
        session = MagicMock()
        with patch.object(settings, "demo_mode", False):
            with self.assertRaises(HTTPException) as error:
                demo_users(session=session)
        self.assertEqual(error.exception.status_code, 404)
        session.scalars.assert_not_called()

    def test_disabled_mode_removes_demo_credentials_from_rendered_homepage(self):
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})
        with patch.object(settings, "demo_mode", False):
            response = homepage(request)
        self.assertNotIn("ChangeMe123!", response.body.decode())
        self.assertNotIn("admin@example.com", response.body.decode())
        self.assertEqual(response.context["demo_accounts"], [])
