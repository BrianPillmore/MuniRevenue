from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


class TestApiSecurity(unittest.TestCase):
    def create_client(self, env_overrides: dict[str, str]) -> TestClient:
        patcher = patch.dict(os.environ, env_overrides, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        return TestClient(create_app())

    def test_health_endpoint_remains_public(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_API_AUTH_MODE": "token",
                "MUNIREV_API_KEYS": "top-secret",
            }
        )
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)

    def test_token_auth_rejects_missing_credentials(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_API_AUTH_MODE": "token",
                "MUNIREV_API_KEYS": "top-secret",
            }
        )
        response = client.get("/api/cities?limit=1")
        self.assertEqual(response.status_code, 401)
        self.assertIn("detail", response.json())
        self.assertIn("WWW-Authenticate", response.headers)

    def test_token_auth_accepts_api_key(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_API_AUTH_MODE": "token",
                "MUNIREV_API_KEYS": "top-secret",
            }
        )
        response = client.get("/api/cities?limit=1", headers={"X-API-Key": "top-secret"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Request-ID", response.headers)
        self.assertIn("X-Content-Type-Options", response.headers)

    def test_token_auth_accepts_bearer_token(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_API_AUTH_MODE": "token",
                "MUNIREV_BEARER_TOKENS": "bearer-secret",
            }
        )
        response = client.get(
            "/api/cities?limit=1",
            headers={"Authorization": "Bearer bearer-secret"},
        )
        self.assertEqual(response.status_code, 200)

    def test_proxy_auth_requires_header(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_API_AUTH_MODE": "proxy",
                "MUNIREV_PROXY_AUTH_HEADERS": "X-Authenticated-User",
            }
        )
        denied = client.get("/api/cities?limit=1")
        self.assertEqual(denied.status_code, 401)

        allowed = client.get(
            "/api/cities?limit=1",
            headers={"X-Authenticated-User": "munirev@example.com"},
        )
        self.assertEqual(allowed.status_code, 200)

    def test_rate_limit_returns_429_and_headers(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_API_AUTH_MODE": "off",
                "MUNIREV_RATE_LIMIT_ENABLED": "true",
                "MUNIREV_RATE_LIMIT_REQUESTS": "2",
                "MUNIREV_RATE_LIMIT_WINDOW_SECONDS": "60",
                "MUNIREV_TRUST_X_FORWARDED_FOR": "true",
            }
        )
        headers = {"X-Forwarded-For": "203.0.113.10"}

        first = client.get("/api/cities?limit=1", headers=headers)
        second = client.get("/api/cities?limit=1", headers=headers)
        third = client.get("/api/cities?limit=1", headers=headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)
        self.assertIn("Retry-After", third.headers)
        self.assertEqual(third.headers.get("X-RateLimit-Limit"), "2")
        self.assertEqual(third.headers.get("X-RateLimit-Remaining"), "0")


if __name__ == "__main__":
    unittest.main()
