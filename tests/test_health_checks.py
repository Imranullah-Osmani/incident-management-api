from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.main import ready_health


class HealthCheckTests(unittest.TestCase):
    def test_ready_health_closes_redis_client_after_successful_ping(self) -> None:
        session = MagicMock()
        redis_client = MagicMock()

        with patch("app.main.Redis.from_url", return_value=redis_client):
            response = ready_health(session=session)

        session.execute.assert_called_once()
        redis_client.ping.assert_called_once()
        redis_client.close.assert_called_once()
        self.assertEqual(response.status, "ok")
        self.assertEqual(response.redis, "ok")

    def test_ready_health_closes_redis_client_after_failed_ping(self) -> None:
        session = MagicMock()
        redis_client = MagicMock()
        redis_client.ping.side_effect = RuntimeError("redis unavailable")

        with patch("app.main.Redis.from_url", return_value=redis_client):
            response = ready_health(session=session)

        redis_client.close.assert_called_once()
        self.assertEqual(response.status, "degraded")
        self.assertEqual(response.redis, "error")


if __name__ == "__main__":
    unittest.main()
