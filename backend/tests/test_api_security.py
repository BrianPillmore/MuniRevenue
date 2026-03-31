from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_hs256_jwt(secret: str, claims: dict[str, object]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_segment = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_segment = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_segment}.{payload_segment}.{_b64url_encode(signature)}"


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

    def test_token_auth_accepts_api_key_for_read_scope(self) -> None:
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

    def test_viewer_token_cannot_access_admin_endpoint(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_API_AUTH_MODE": "token",
                "MUNIREV_API_KEYS": "top-secret",
                "MUNIREV_TOKEN_DEFAULT_ROLES": "viewer",
            }
        )
        response = client.get("/api/admin/security", headers={"X-API-Key": "top-secret"})
        self.assertEqual(response.status_code, 403)
        self.assertIn("Missing required scopes", response.json()["detail"])

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
                "MUNIREV_PROXY_SUBJECT_HEADERS": "X-Authenticated-User",
            }
        )
        denied = client.get("/api/cities?limit=1")
        self.assertEqual(denied.status_code, 401)

        allowed = client.get(
            "/api/cities?limit=1",
            headers={"X-Authenticated-User": "munirev@example.com"},
        )
        self.assertEqual(allowed.status_code, 200)

    def test_proxy_groups_expand_to_analyst_scopes(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_API_AUTH_MODE": "proxy",
                "MUNIREV_PROXY_SUBJECT_HEADERS": "X-Authenticated-User",
                "MUNIREV_PROXY_ROLE_HEADERS": "X-Authenticated-Roles",
            }
        )
        response = client.get(
            "/api/auth/me",
            headers={
                "X-Authenticated-User": "munirev@example.com",
                "X-Authenticated-Roles": "analyst",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("analyst", data["roles"])
        self.assertIn("analysis:run", data["scopes"])
        self.assertIn("reports:generate", data["scopes"])

    def test_proxy_write_requests_require_trusted_origin(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_API_AUTH_MODE": "proxy",
                "MUNIREV_PROXY_SUBJECT_HEADERS": "X-Authenticated-User",
                "MUNIREV_PROXY_ROLE_HEADERS": "X-Authenticated-Roles",
                "MUNIREV_CSRF_TRUSTED_ORIGINS": "https://munirev.example.com",
            }
        )
        response = client.post(
            "/api/analyze",
            headers={
                "X-Authenticated-User": "munirev@example.com",
                "X-Authenticated-Roles": "analyst",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("trusted origin", response.json()["detail"])

    def test_proxy_write_requests_accept_trusted_origin(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_API_AUTH_MODE": "proxy",
                "MUNIREV_PROXY_SUBJECT_HEADERS": "X-Authenticated-User",
                "MUNIREV_PROXY_ROLE_HEADERS": "X-Authenticated-Roles",
                "MUNIREV_CSRF_TRUSTED_ORIGINS": "https://munirev.example.com",
            }
        )
        response = client.post(
            "/api/analyze",
            headers={
                "X-Authenticated-User": "munirev@example.com",
                "X-Authenticated-Roles": "analyst",
                "Origin": "https://munirev.example.com",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_jwt_admin_token_can_access_admin_endpoint(self) -> None:
        secret = "unit-test-secret"
        token = make_hs256_jwt(
            secret,
            {
                "sub": "deploy-admin",
                "roles": ["admin"],
                "scope": "api:admin",
                "iss": "munirev-tests",
                "aud": "munirev-api",
                "exp": int(time.time()) + 600,
            },
        )
        client = self.create_client(
            {
                "MUNIREV_API_AUTH_MODE": "token",
                "MUNIREV_JWT_SECRET": secret,
                "MUNIREV_JWT_ISSUER": "munirev-tests",
                "MUNIREV_JWT_AUDIENCE": "munirev-api",
            }
        )
        response = client.get(
            "/api/admin/security",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["auth_mode"], "token")

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

    def test_openapi_docs_can_be_disabled(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_OPENAPI_ENABLED": "false",
            }
        )
        docs_response = client.get("/docs")
        openapi_response = client.get("/openapi.json")
        self.assertEqual(docs_response.status_code, 404)
        self.assertEqual(openapi_response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
