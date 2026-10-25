import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.main import get_current_user, security
from app.security import create_access_token


class BearerAuthenticationTests(unittest.TestCase):
    def assert_unauthorized(self, credentials, session):
        with self.assertRaises(HTTPException) as error:
            get_current_user(credentials=credentials, session=session)
        self.assertEqual(error.exception.status_code, 401)
        self.assertEqual(error.exception.headers, {"WWW-Authenticate": "Bearer"})

    def test_missing_empty_or_wrong_scheme_challenges_without_database_lookup(self):
        for header in (None, "Bearer", "Basic dXNlcjpwYXNz"):
            with self.subTest(header=header):
                request = Request({
                    "type": "http", "method": "GET", "path": "/tickets",
                    "headers": [] if header is None else [(b"authorization", header.encode())],
                })
                credentials = asyncio.run(security(request))
                session = MagicMock()
                self.assert_unauthorized(credentials, session)
                session.scalar.assert_not_called()

    def test_invalid_token_challenges_without_database_lookup(self):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")
        session = MagicMock()
        self.assert_unauthorized(credentials, session)
        session.scalar.assert_not_called()

    def test_missing_or_disabled_account_challenges(self):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_access_token("user-1"))
        for user in (None, SimpleNamespace(is_active=False)):
            with self.subTest(user=user):
                session = MagicMock()
                session.scalar.return_value = user
                self.assert_unauthorized(credentials, session)

    def test_valid_token_for_active_account_is_accepted(self):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_access_token("user-1"))
        user = SimpleNamespace(id="user-1", is_active=True)
        session = MagicMock()
        session.scalar.return_value = user
        self.assertIs(get_current_user(credentials=credentials, session=session), user)
