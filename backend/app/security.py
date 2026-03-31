from __future__ import annotations

import os
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse, Response


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(slots=True)
class SecuritySettings:
    auth_mode: str = "off"
    api_keys: set[str] = field(default_factory=set)
    bearer_tokens: set[str] = field(default_factory=set)
    proxy_auth_headers: tuple[str, ...] = ("x-authenticated-user", "x-forwarded-user")
    auth_exempt_paths: set[str] = field(default_factory=lambda: {"/api/health"})
    rate_limit_enabled: bool = False
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    rate_limit_exempt_paths: set[str] = field(default_factory=lambda: {"/api/health"})
    trust_forwarded_for: bool = False
    cors_origins: list[str] = field(default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"])
    allowed_hosts: list[str] = field(default_factory=lambda: ["localhost", "127.0.0.1", "testserver"])
    force_https: bool = False


def load_security_settings() -> SecuritySettings:
    auth_mode = os.environ.get("MUNIREV_API_AUTH_MODE", "off").strip().lower()
    if auth_mode not in {"off", "token", "proxy"}:
        auth_mode = "off"

    return SecuritySettings(
        auth_mode=auth_mode,
        api_keys=set(_parse_csv(os.environ.get("MUNIREV_API_KEYS"))),
        bearer_tokens=set(_parse_csv(os.environ.get("MUNIREV_BEARER_TOKENS"))),
        proxy_auth_headers=tuple(
            item.lower()
            for item in _parse_csv(os.environ.get("MUNIREV_PROXY_AUTH_HEADERS"))
        ) or ("x-authenticated-user", "x-forwarded-user"),
        auth_exempt_paths=set(
            _parse_csv(os.environ.get("MUNIREV_AUTH_EXEMPT_PATHS"))
        ) or {"/api/health"},
        rate_limit_enabled=_parse_bool(os.environ.get("MUNIREV_RATE_LIMIT_ENABLED"), False),
        rate_limit_requests=max(1, int(os.environ.get("MUNIREV_RATE_LIMIT_REQUESTS", "120"))),
        rate_limit_window_seconds=max(1, int(os.environ.get("MUNIREV_RATE_LIMIT_WINDOW_SECONDS", "60"))),
        rate_limit_exempt_paths=set(
            _parse_csv(os.environ.get("MUNIREV_RATE_LIMIT_EXEMPT_PATHS"))
        ) or {"/api/health"},
        trust_forwarded_for=_parse_bool(os.environ.get("MUNIREV_TRUST_X_FORWARDED_FOR"), False),
        cors_origins=_parse_csv(os.environ.get("MUNIREV_CORS_ORIGINS")) or ["http://127.0.0.1:5173", "http://localhost:5173"],
        allowed_hosts=_parse_csv(os.environ.get("MUNIREV_ALLOWED_HOSTS")) or ["localhost", "127.0.0.1", "testserver"],
        force_https=_parse_bool(os.environ.get("MUNIREV_FORCE_HTTPS"), False),
    )


class TokenBucketRateLimiter:
    def __init__(self, capacity: int, window_seconds: int) -> None:
        self.capacity = float(capacity)
        self.window_seconds = float(window_seconds)
        self.refill_rate = self.capacity / self.window_seconds
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = Lock()

    def consume(self, key: str) -> tuple[bool, int, int]:
        now = time.monotonic()
        with self._lock:
            tokens, last_seen = self._buckets.get(key, (self.capacity, now))
            elapsed = max(0.0, now - last_seen)
            replenished = min(self.capacity, tokens + elapsed * self.refill_rate)

            if replenished >= 1.0:
                remaining_tokens = replenished - 1.0
                self._buckets[key] = (remaining_tokens, now)
                remaining = max(0, int(remaining_tokens))
                reset_seconds = max(0, int((self.capacity - remaining_tokens) / self.refill_rate))
                return True, remaining, reset_seconds

            reset_seconds = max(1, int((1.0 - replenished) / self.refill_rate) + 1)
            self._buckets[key] = (replenished, now)
            return False, 0, reset_seconds


def is_api_request(path: str) -> bool:
    return path.startswith("/api")


def is_exempt_path(path: str, exempt_paths: set[str]) -> bool:
    return path in exempt_paths


def resolve_client_ip(request: Request, settings: SecuritySettings) -> str:
    if settings.trust_forwarded_for:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def authenticate_request(request: Request, settings: SecuritySettings) -> tuple[bool, Optional[str], str]:
    if settings.auth_mode == "off":
        return True, None, "auth disabled"

    if settings.auth_mode == "token":
        api_key = request.headers.get("x-api-key")
        if api_key and api_key in settings.api_keys:
            return True, f"api_key:{api_key[:8]}", "api key"

        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
            if token in settings.bearer_tokens:
                return True, f"bearer:{token[:8]}", "bearer token"

        return False, None, "Provide a valid X-API-Key or Authorization: Bearer token."

    for header_name in settings.proxy_auth_headers:
        header_value = request.headers.get(header_name)
        if header_value:
            return True, header_value, f"proxy header {header_name}"

    return False, None, "A trusted proxy authentication header is required."


def security_headers(path: str) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
    }
    if is_api_request(path):
        headers["Cache-Control"] = "no-store"
    return headers


async def security_middleware(
    request: Request,
    call_next,
    *,
    settings: SecuritySettings,
    rate_limiter: TokenBucketRateLimiter,
) -> Response:
    request_id = str(uuid.uuid4())
    path = request.url.path
    request.state.request_id = request_id

    if request.method == "OPTIONS" or not is_api_request(path):
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        for header, value in security_headers(path).items():
            response.headers.setdefault(header, value)
        return response

    if not is_exempt_path(path, settings.auth_exempt_paths):
        authenticated, subject, auth_reason = authenticate_request(request, settings)
        if not authenticated:
            response = JSONResponse(
                status_code=401,
                content={"detail": auth_reason},
            )
            response.headers["WWW-Authenticate"] = "Bearer"
            response.headers["X-Request-ID"] = request_id
            for header, value in security_headers(path).items():
                response.headers.setdefault(header, value)
            return response
        request.state.auth_subject = subject
        request.state.auth_method = auth_reason
    else:
        request.state.auth_subject = None
        request.state.auth_method = "exempt"

    limit_headers: dict[str, str] = {}
    if settings.rate_limit_enabled and not is_exempt_path(path, settings.rate_limit_exempt_paths):
        client_key = request.state.auth_subject or resolve_client_ip(request, settings)
        allowed, remaining, reset_seconds = rate_limiter.consume(client_key)
        limit_headers = {
            "X-RateLimit-Limit": str(settings.rate_limit_requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_seconds),
        }
        if not allowed:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please retry later."},
            )
            response.headers["Retry-After"] = str(reset_seconds)
            response.headers["X-Request-ID"] = request_id
            for header, value in security_headers(path).items():
                response.headers.setdefault(header, value)
            for header, value in limit_headers.items():
                response.headers[header] = value
            return response

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    for header, value in security_headers(path).items():
        response.headers.setdefault(header, value)
    for header, value in limit_headers.items():
        response.headers[header] = value
    return response
