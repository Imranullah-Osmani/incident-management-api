from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings
from app.security import ALGORITHM, create_access_token, decode_access_token


class TokenSecurityTests(unittest.TestCase):
    def test_access_token_round_trip_returns_subject(self) -> None:
        token = create_access_token("user-123")

        self.assertEqual(decode_access_token(token), "user-123")

    def test_decode_access_token_rejects_blank_subject(self) -> None:
        token = jwt.encode(
            {"sub": "   ", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            settings.secret_key,
            algorithm=ALGORITHM,
        )

        with self.assertRaises(ValueError):
            decode_access_token(token)

    def test_decode_access_token_rejects_non_string_subject(self) -> None:
        token = jwt.encode(
            {"sub": 123, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            settings.secret_key,
            algorithm=ALGORITHM,
        )

        with self.assertRaises(ValueError):
            decode_access_token(token)


if __name__ == "__main__":
    unittest.main()
