from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Iterable, Optional

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse, Response

from app.user_auth import BrowserAuthSettings, resolve_user_session


ROLE_SCOPE_MAP: dict[str, set[str]] = {
    "viewer": {"api:read"},
    "analyst": {"api:read", "analysis:run", "reports:generate"},
    "operator": {"api:read", "analysis:run", "reports:generate", "data:import"},
    "service": {"api:read", "analysis:run", "reports:generate", "data:import"},
    "admin": {"api:admin"},
}

SCOPE_IMPLICATIONS: dict[str, set[str]] = {
    "api:admin": {"api:read", "api:write", "analysis:run", "reports:generate", "data:import", "ops:read"},
    "api:write": {"api:read"},
    "analysis:run": {"api:read"},
    "reports:generate": {"api:read"},
    "data:import": {"api:write", "api:read"},
}


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_membership_values(value: str | None) -> set[str]:
    if not value:
        return set()

    normalized = value.replace(";", ",").replace("|", ",")
    values: set[str] = set()
    for chunk in normalized.split(","):
        token = chunk.strip()
        if not token:
            continue
        if " " in token:
            values.update(part.strip() for part in token.split() if part.strip())
        else:
            values.add(token)
    return values


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return list(_parse_membership_values(value))
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _header_values(request: Request, header_names: Iterable[str]) -> set[str]:
    values: set[str] = set()
    for header_name in header_names:
        header_value = request.headers.get(header_name)
        values.update(_parse_membership_values(header_value))
    return values


def _first_header_value(request: Request, header_names: Iterable[str]) -> Optional[str]:
    for header_name in header_names:
        header_value = request.headers.get(header_name)
        if header_value and header_value.strip():
            return header_value.strip()
    return None


def _expand_scopes(scopes: Iterable[str]) -> set[str]:
    expanded = {scope.strip() for scope in scopes if scope and scope.strip()}
    pending = list(expanded)
    while pending:
        scope = pending.pop()
        for implied_scope in SCOPE_IMPLICATIONS.get(scope, set()):
            if implied_scope not in expanded:
                expanded.add(implied_scope)
                pending.append(implied_scope)
    return expanded


def _scopes_from_roles(roles: Iterable[str]) -> set[str]:
    scopes: set[str] = set()
    for role in roles:
        scopes.update(ROLE_SCOPE_MAP.get(role, set()))
    return scopes


def _normalize_roles(roles: Iterable[str]) -> set[str]:
    return {role.strip().lower() for role in roles if role and role.strip()}


def _normalize_scopes(scopes: Iterable[str]) -> set[str]:
    return _expand_scopes(scope.strip().lower() for scope in scopes if scope and scope.strip())


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _verify_hs256_jwt(
    token: str,
    *,
    secret: str,
    issuer: str | None,
    audience: str | None,
    clock_skew_seconds: int,
) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:  # pragma: no cover - defensive parsing
        raise ValueError("Malformed JWT.") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    actual_signature = _b64url_decode(signature_b64)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise ValueError("JWT signature verification failed.")

    header = json.loads(_b64url_decode(header_b64))
    if header.get("alg") != "HS256":
        raise ValueError("Only HS256 JWT tokens are supported.")

    payload = json.loads(_b64url_decode(payload_b64))
    now = int(time.time())
    skew = max(0, clock_skew_seconds)

    exp = payload.get("exp")
    if exp is not None and int(exp) < now - skew:
        raise ValueError("JWT has expired.")

    nbf = payload.get("nbf")
    if nbf is not None and int(nbf) > now + skew:
        raise ValueError("JWT is not active yet.")

    iat = payload.get("iat")
    if iat is not None and int(iat) > now + skew:
        raise ValueError("JWT issued-at time is in the future.")

    if issuer and payload.get("iss") != issuer:
        raise ValueError("JWT issuer mismatch.")

    if audience:
        aud_claim = payload.get("aud")
        if isinstance(aud_claim, str):
            audiences = {aud_claim}
        elif isinstance(aud_claim, list):
            audiences = {str(item) for item in aud_claim}
        else:
            audiences = set()
        if audience not in audiences:
            raise ValueError("JWT audience mismatch.")

    return payload


@dataclass(frozen=True, slots=True)
class AuthContext:
    subject: Optional[str]
    roles: tuple[str, ...]
    scopes: tuple[str, ...]
    auth_mode: str
    auth_method: str

    @property
    def is_authenticated(self) -> bool:
        return self.auth_mode == "off" or bool(self.subject)

    def has_scopes(self, required_scopes: Iterable[str]) -> bool:
        required = _normalize_scopes(required_scopes)
        if self.auth_mode == "off":
            return True
        return required.issubset(set(self.scopes))


@dataclass(slots=True)
class SecuritySettings:
    auth_mode: str = "off"
    api_keys: set[str] = field(default_factory=set)
    bearer_tokens: set[str] = field(default_factory=set)
    proxy_auth_headers: tuple[str, ...] = (
        "x-authenticated-user",
        "x-forwarded-user",
        "x-auth-request-email",
        "x-auth-request-user",
    )
    proxy_role_headers: tuple[str, ...] = (
        "x-authenticated-roles",
        "x-forwarded-groups",
        "x-auth-request-groups",
    )
    proxy_scope_headers: tuple[str, ...] = (
        "x-authenticated-scopes",
        "x-forwarded-scopes",
        "x-auth-request-scopes",
    )
    proxy_default_roles: set[str] = field(default_factory=lambda: {"viewer"})
    proxy_default_scopes: set[str] = field(default_factory=set)
    token_default_roles: set[str] = field(default_factory=lambda: {"viewer"})
    token_default_scopes: set[str] = field(default_factory=set)
    jwt_secret: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwt_clock_skew_seconds: int = 30
    auth_exempt_paths: set[str] = field(default_factory=lambda: {"/api/health"})
    rate_limit_enabled: bool = False
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    rate_limit_exempt_paths: set[str] = field(default_factory=lambda: {"/api/health"})
    trust_forwarded_for: bool = False
    cors_origins: list[str] = field(default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"])
    csrf_trusted_origins: list[str] = field(default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"])
    allowed_hosts: list[str] = field(default_factory=lambda: ["localhost", "127.0.0.1", "testserver"])
    force_https: bool = False
    openapi_enabled: bool = True


def load_security_settings() -> SecuritySettings:
    auth_mode = os.environ.get("MUNIREV_API_AUTH_MODE", "off").strip().lower()
    if auth_mode not in {"off", "token", "proxy"}:
        auth_mode = "off"

    proxy_subject_headers = _parse_csv(os.environ.get("MUNIREV_PROXY_SUBJECT_HEADERS"))
    if not proxy_subject_headers:
        proxy_subject_headers = _parse_csv(os.environ.get("MUNIREV_PROXY_AUTH_HEADERS"))

    cors_origins = _parse_csv(os.environ.get("MUNIREV_CORS_ORIGINS")) or [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    csrf_trusted_origins = _parse_csv(os.environ.get("MUNIREV_CSRF_TRUSTED_ORIGINS")) or list(cors_origins)

    return SecuritySettings(
        auth_mode=auth_mode,
        api_keys=set(_parse_csv(os.environ.get("MUNIREV_API_KEYS"))),
        bearer_tokens=set(_parse_csv(os.environ.get("MUNIREV_BEARER_TOKENS"))),
        proxy_auth_headers=tuple(header.lower() for header in proxy_subject_headers) or (
            "x-authenticated-user",
            "x-forwarded-user",
            "x-auth-request-email",
            "x-auth-request-user",
        ),
        proxy_role_headers=tuple(
            header.lower() for header in _parse_csv(os.environ.get("MUNIREV_PROXY_ROLE_HEADERS"))
        ) or (
            "x-authenticated-roles",
            "x-forwarded-groups",
            "x-auth-request-groups",
        ),
        proxy_scope_headers=tuple(
            header.lower() for header in _parse_csv(os.environ.get("MUNIREV_PROXY_SCOPE_HEADERS"))
        ) or (
            "x-authenticated-scopes",
            "x-forwarded-scopes",
            "x-auth-request-scopes",
        ),
        proxy_default_roles=_normalize_roles(_parse_csv(os.environ.get("MUNIREV_PROXY_DEFAULT_ROLES")) or ["viewer"]),
        proxy_default_scopes=_normalize_scopes(_parse_csv(os.environ.get("MUNIREV_PROXY_DEFAULT_SCOPES"))),
        token_default_roles=_normalize_roles(_parse_csv(os.environ.get("MUNIREV_TOKEN_DEFAULT_ROLES")) or ["viewer"]),
        token_default_scopes=_normalize_scopes(_parse_csv(os.environ.get("MUNIREV_TOKEN_DEFAULT_SCOPES"))),
        jwt_secret=os.environ.get("MUNIREV_JWT_SECRET") or None,
        jwt_issuer=os.environ.get("MUNIREV_JWT_ISSUER") or None,
        jwt_audience=os.environ.get("MUNIREV_JWT_AUDIENCE") or None,
        jwt_clock_skew_seconds=max(0, int(os.environ.get("MUNIREV_JWT_CLOCK_SKEW_SECONDS", "30"))),
        auth_exempt_paths=set(_parse_csv(os.environ.get("MUNIREV_AUTH_EXEMPT_PATHS"))) or {"/api/health"},
        rate_limit_enabled=_parse_bool(os.environ.get("MUNIREV_RATE_LIMIT_ENABLED"), False),
        rate_limit_requests=max(1, int(os.environ.get("MUNIREV_RATE_LIMIT_REQUESTS", "120"))),
        rate_limit_window_seconds=max(1, int(os.environ.get("MUNIREV_RATE_LIMIT_WINDOW_SECONDS", "60"))),
        rate_limit_exempt_paths=set(_parse_csv(os.environ.get("MUNIREV_RATE_LIMIT_EXEMPT_PATHS"))) or {"/api/health"},
        trust_forwarded_for=_parse_bool(os.environ.get("MUNIREV_TRUST_X_FORWARDED_FOR"), False),
        cors_origins=cors_origins,
        csrf_trusted_origins=csrf_trusted_origins,
        allowed_hosts=_parse_csv(os.environ.get("MUNIREV_ALLOWED_HOSTS")) or ["localhost", "127.0.0.1", "testserver"],
        force_https=_parse_bool(os.environ.get("MUNIREV_FORCE_HTTPS"), False),
        openapi_enabled=_parse_bool(os.environ.get("MUNIREV_OPENAPI_ENABLED"), auth_mode == "off"),
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


def _build_auth_context(
    *,
    subject: Optional[str],
    roles: Iterable[str],
    scopes: Iterable[str],
    auth_mode: str,
    auth_method: str,
) -> AuthContext:
    normalized_roles = _normalize_roles(roles)
    normalized_scopes = _normalize_scopes(set(scopes) | _scopes_from_roles(normalized_roles))
    return AuthContext(
        subject=subject,
        roles=tuple(sorted(normalized_roles)),
        scopes=tuple(sorted(normalized_scopes)),
        auth_mode=auth_mode,
        auth_method=auth_method,
    )


def authenticate_request(request: Request, settings: SecuritySettings) -> tuple[bool, Optional[AuthContext], str]:
    if settings.auth_mode == "off":
        return True, _build_auth_context(
            subject=None,
            roles=set(),
            scopes=set(),
            auth_mode="off",
            auth_method="auth disabled",
        ), "auth disabled"

    if settings.auth_mode == "token":
        api_key = request.headers.get("x-api-key")
        if api_key and api_key in settings.api_keys:
            return True, _build_auth_context(
                subject=f"api_key:{api_key[:8]}",
                roles=settings.token_default_roles,
                scopes=settings.token_default_scopes,
                auth_mode="token",
                auth_method="api key",
            ), "api key"

        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
            if token in settings.bearer_tokens:
                return True, _build_auth_context(
                    subject=f"bearer:{token[:8]}",
                    roles=settings.token_default_roles,
                    scopes=settings.token_default_scopes,
                    auth_mode="token",
                    auth_method="static bearer token",
                ), "static bearer token"
            if settings.jwt_secret:
                try:
                    claims = _verify_hs256_jwt(
                        token,
                        secret=settings.jwt_secret,
                        issuer=settings.jwt_issuer,
                        audience=settings.jwt_audience,
                        clock_skew_seconds=settings.jwt_clock_skew_seconds,
                    )
                except ValueError as exc:
                    return False, None, str(exc)

                subject = (
                    claims.get("sub")
                    or claims.get("preferred_username")
                    or claims.get("email")
                    or claims.get("client_id")
                )
                roles = set(_as_string_list(claims.get("roles"))) | set(_as_string_list(claims.get("role")))
                roles |= set(_as_string_list(claims.get("groups")))
                scopes = set(_as_string_list(claims.get("scp"))) | set(_as_string_list(claims.get("scope")))
                scopes |= settings.token_default_scopes
                roles |= settings.token_default_roles

                return True, _build_auth_context(
                    subject=str(subject) if subject is not None else "jwt",
                    roles=roles,
                    scopes=scopes,
                    auth_mode="token",
                    auth_method="jwt bearer token",
                ), "jwt bearer token"

        return False, None, "Provide a valid X-API-Key or Authorization: Bearer token."

    subject = _first_header_value(request, settings.proxy_auth_headers)
    if not subject:
        return False, None, "A trusted proxy authentication header is required."

    roles = _header_values(request, settings.proxy_role_headers) | settings.proxy_default_roles
    scopes = _header_values(request, settings.proxy_scope_headers) | settings.proxy_default_scopes
    return True, _build_auth_context(
        subject=subject,
        roles=roles,
        scopes=scopes,
        auth_mode="proxy",
        auth_method="trusted proxy headers",
    ), "trusted proxy headers"


def security_headers(path: str) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
    }
    if is_api_request(path):
        headers["Cache-Control"] = "no-store"
    return headers


def _origin_matches_trusted_origin(candidate: str, trusted_origins: Iterable[str]) -> bool:
    return any(candidate.startswith(origin.rstrip("/")) for origin in trusted_origins if origin)


def _enforce_proxy_csrf(request: Request, settings: SecuritySettings) -> Optional[str]:
    if settings.auth_mode != "proxy":
        return None
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return None

    origin = request.headers.get("origin")
    referer = request.headers.get("referer")

    if origin and _origin_matches_trusted_origin(origin, settings.csrf_trusted_origins):
        return None
    if referer and _origin_matches_trusted_origin(referer, settings.csrf_trusted_origins):
        return None

    return "Unsafe browser requests require an Origin or Referer that matches a trusted origin."


_OPTIONAL_BROWSER_AUTH_PATHS = frozenset(
    {
        "/api/auth/magic-link/request",
        "/api/auth/session",
        "/api/auth/logout",
    }
)
_OPTIONAL_BROWSER_AUTH_PREFIXES = ("/api/account/",)
_PUBLIC_API_EXACT_PATHS = frozenset(
    {
        "/api/cities",
        "/api/stats/overview",
        "/api/stats/statewide-trend",
        "/api/stats/rankings",
        "/api/stats/naics-sectors",
    }
)


def _is_optional_browser_auth_path(path: str, browser_auth_settings: BrowserAuthSettings) -> bool:
    if not browser_auth_settings.enabled:
        return False
    if path in _OPTIONAL_BROWSER_AUTH_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _OPTIONAL_BROWSER_AUTH_PREFIXES)


def _is_public_api_path(path: str) -> bool:
    if path in _PUBLIC_API_EXACT_PATHS:
        return True

    if path.startswith("/api/counties/") and path.endswith("/summary"):
        return True

    if not path.startswith("/api/cities/"):
        return False

    parts = [segment for segment in path[len("/api/cities/"):].split("/") if segment]
    if not parts:
        return False
    if len(parts) == 1:
        return True
    if len(parts) == 2 and parts[1] in {"ledger", "naics", "seasonality", "anomalies"}:
        return parts[1] != "anomalies"
    if len(parts) == 3 and parts[1] == "ledger" and parts[2] == "export":
        return True
    if len(parts) == 3 and parts[1] == "naics" and parts[2] == "top":
        return True
    if len(parts) == 4 and parts[1] == "naics" and parts[2] == "timeseries":
        return True

    return False


async def security_middleware(
    request: Request,
    call_next,
    *,
    settings: SecuritySettings,
    rate_limiter: TokenBucketRateLimiter,
    browser_auth_settings: BrowserAuthSettings,
) -> Response:
    request_id = str(uuid.uuid4())
    path = request.url.path
    request.state.request_id = request_id
    request.state.auth_context = _build_auth_context(
        subject=None,
        roles=set(),
        scopes=set(),
        auth_mode=settings.auth_mode,
        auth_method="uninitialized",
    )
    _ = browser_auth_settings
    user_session = resolve_user_session(request)
    request.state.user_session = user_session

    if request.method == "OPTIONS" or not is_api_request(path):
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        for header, value in security_headers(path).items():
            response.headers.setdefault(header, value)
        return response

    optional_browser_auth = _is_optional_browser_auth_path(path, browser_auth_settings)
    public_api_path = _is_public_api_path(path)
    if not is_exempt_path(path, settings.auth_exempt_paths) and not optional_browser_auth and not public_api_path:
        authenticated, auth_context, auth_reason = authenticate_request(request, settings)
        if not authenticated and user_session is not None:
            auth_context = _build_auth_context(
                subject=f"user:{user_session.user_id}",
                roles={"viewer"},
                scopes={"api:read"},
                auth_mode="session",
                auth_method="browser session",
            )
            authenticated = True
            auth_reason = "browser session"
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
        request.state.auth_context = auth_context
        request.state.auth_subject = auth_context.subject if auth_context else None
        request.state.auth_method = auth_reason

        csrf_error = _enforce_proxy_csrf(request, settings) if settings.auth_mode == "proxy" else None
        if csrf_error:
            response = JSONResponse(
                status_code=403,
                content={"detail": csrf_error},
            )
            response.headers["X-Request-ID"] = request_id
            for header, value in security_headers(path).items():
                response.headers.setdefault(header, value)
            return response
    elif optional_browser_auth:
        authenticated, auth_context, auth_reason = authenticate_request(request, settings)
        if not authenticated and user_session is not None:
            auth_context = _build_auth_context(
                subject=f"user:{user_session.user_id}",
                roles={"viewer"},
                scopes={"api:read"},
                auth_mode="session",
                auth_method="browser session",
            )
            authenticated = True
            auth_reason = "browser session"

        if authenticated and auth_context is not None:
            request.state.auth_context = auth_context
            request.state.auth_subject = auth_context.subject if auth_context else None
            request.state.auth_method = auth_reason
        else:
            optional_context = _build_auth_context(
                subject=None,
                roles=set(),
                scopes=set(),
                auth_mode=settings.auth_mode,
                auth_method="optional browser auth",
            )
            request.state.auth_context = optional_context
            request.state.auth_subject = None
            request.state.auth_method = "optional browser auth"
    elif public_api_path:
        public_context = _build_auth_context(
            subject=None,
            roles=set(),
            scopes=set(),
            auth_mode=settings.auth_mode,
            auth_method="public",
        )
        request.state.auth_context = public_context
        request.state.auth_subject = None
        request.state.auth_method = "public"
    else:
        exempt_context = _build_auth_context(
            subject=None,
            roles=set(),
            scopes=set(),
            auth_mode=settings.auth_mode,
            auth_method="exempt",
        )
        request.state.auth_context = exempt_context
        request.state.auth_subject = None
        request.state.auth_method = "exempt"

    limit_headers: dict[str, str] = {}
    if settings.rate_limit_enabled and not is_exempt_path(path, settings.rate_limit_exempt_paths):
        auth_context = request.state.auth_context
        client_key = auth_context.subject if auth_context and auth_context.subject else resolve_client_ip(request, settings)
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


def get_auth_context(request: Request) -> AuthContext:
    auth_context = getattr(request.state, "auth_context", None)
    if auth_context is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication context was not initialized.",
        )
    return auth_context


def require_scopes(*required_scopes: str) -> Callable[[Request], AuthContext]:
    normalized_required_scopes = tuple(sorted(_normalize_scopes(required_scopes)))

    def dependency(request: Request) -> AuthContext:
        settings: SecuritySettings = request.app.state.security_settings
        auth_context = get_auth_context(request)

        if settings.auth_mode == "off":
            return auth_context

        if not auth_context.is_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication is required.",
            )

        if not auth_context.has_scopes(normalized_required_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Missing required scopes: "
                    + ", ".join(normalized_required_scopes)
                ),
            )

        return auth_context

    return dependency
