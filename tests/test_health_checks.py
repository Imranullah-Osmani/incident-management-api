from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import Response

from app.core.config import settings
from app.main import REDIS_HEALTH_TIMEOUT_SECONDS, ready_health


class HealthCheckTests(unittest.TestCase):
    def test_ready_health_closes_redis_client_after_successful_ping(self) -> None:
        session = MagicMock()
        fastapi_response = Response()
        redis_client = MagicMock()

        with patch("app.main.Redis.from_url", return_value=redis_client) as redis_from_url:
            response = ready_health(response=fastapi_response, session=session)

        session.execute.assert_called_once()
        redis_from_url.assert_called_once_with(
            settings.redis_url,
            socket_connect_timeout=REDIS_HEALTH_TIMEOUT_SECONDS,
            socket_timeout=REDIS_HEALTH_TIMEOUT_SECONDS,
        )
        redis_client.ping.assert_called_once()
        redis_client.close.assert_called_once()
        self.assertEqual(fastapi_response.status_code, 200)
        self.assertEqual(response.status, "ok")
        self.assertEqual(response.redis, "ok")

    def test_ready_health_closes_redis_client_after_failed_ping(self) -> None:
        session = MagicMock()
        fastapi_response = Response()
        redis_client = MagicMock()
        redis_client.ping.side_effect = RuntimeError("redis unavailable")

        with patch("app.main.Redis.from_url", return_value=redis_client):
            response = ready_health(response=fastapi_response, session=session)

        redis_client.close.assert_called_once()
        self.assertEqual(fastapi_response.status_code, 503)
        self.assertEqual(response.status, "degraded")
        self.assertEqual(response.redis, "error")

    def test_ready_health_marks_database_failure_as_service_unavailable(self) -> None:
        session = MagicMock()
        session.execute.side_effect = RuntimeError("database unavailable")
        fastapi_response = Response()
        redis_client = MagicMock()

        with patch("app.main.Redis.from_url", return_value=redis_client):
            response = ready_health(response=fastapi_response, session=session)

        self.assertEqual(fastapi_response.status_code, 503)
        self.assertEqual(response.status, "degraded")
        self.assertEqual(response.database, "error")


if __name__ == "__main__":
    unittest.main()
