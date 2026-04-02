from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import os
import secrets
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote

from fastapi import HTTPException, Request, status

from app.db.psycopg import get_cursor


logger = logging.getLogger(__name__)


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int, *, minimum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, parsed)


def _parse_cookie_samesite(value: str | None, default: str = "lax") -> str:
    if not value:
        return default
    normalized = value.strip().lower()
    return normalized if normalized in {"lax", "strict", "none"} else default


@dataclass(frozen=True, slots=True)
class BrowserAuthSettings:
    enabled: bool
    base_url: str
    magic_link_ttl_minutes: int
    magic_link_rate_limit_window_seconds: int
    magic_link_rate_limit_per_email: int
    magic_link_rate_limit_per_ip: int
    session_days: int
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    session_secret: str
    email_mode: str
    email_from: str
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_use_tls: bool
    email_subject: str
    login_success_redirect: str
    debug_return_magic_link: bool


@dataclass(frozen=True, slots=True)
class UserSessionContext:
    user_id: str
    email: str
    display_name: str | None
    job_title: str | None
    organization_name: str | None
    session_id: str
    expires_at: datetime


AUTH_TABLES_DDL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS app_users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    email_normalized TEXT NOT NULL UNIQUE,
    display_name TEXT,
    job_title TEXT,
    organization_name TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE,
    email_verified_at TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_app_users_status CHECK (status IN ('active', 'disabled'))
);

CREATE TABLE IF NOT EXISTS user_magic_links (
    magic_link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    next_path TEXT,
    requested_ip INET,
    requested_user_agent_hash TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_magic_links_active
    ON user_magic_links (user_id, expires_at DESC)
    WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS user_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    session_token_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_ip INET,
    last_seen_ip INET,
    user_agent_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_active
    ON user_sessions (user_id, expires_at DESC)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS user_profile_preferences (
    user_id UUID PRIMARY KEY REFERENCES app_users(user_id) ON DELETE CASCADE,
    default_city_copo VARCHAR(4) REFERENCES jurisdictions(copo),
    default_county_name VARCHAR(50),
    default_tax_type TEXT,
    forecast_model TEXT,
    forecast_horizon_months INTEGER,
    forecast_lookback_months INTEGER,
    forecast_confidence_level NUMERIC(5,4),
    forecast_indicator_profile TEXT,
    forecast_scope TEXT,
    forecast_activity_code VARCHAR(6) REFERENCES naics_codes(activity_code),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_user_profile_preferences_scope CHECK (
        forecast_scope IS NULL OR forecast_scope IN ('municipal', 'naics')
    )
);

CREATE TABLE IF NOT EXISTS user_jurisdiction_interests (
    interest_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    interest_type TEXT NOT NULL,
    copo VARCHAR(4) REFERENCES jurisdictions(copo),
    county_name VARCHAR(50),
    label TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_user_jurisdiction_interests_type CHECK (
        interest_type IN ('city', 'county')
    ),
    CONSTRAINT ck_user_jurisdiction_interests_target CHECK (
        (interest_type = 'city' AND copo IS NOT NULL AND county_name IS NULL)
        OR (interest_type = 'county' AND county_name IS NOT NULL AND copo IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_interest_unique_city
    ON user_jurisdiction_interests (user_id, interest_type, copo)
    WHERE copo IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_interest_unique_county
    ON user_jurisdiction_interests (user_id, interest_type, county_name)
    WHERE county_name IS NOT NULL;

CREATE TABLE IF NOT EXISTS user_saved_anomalies (
    saved_anomaly_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    copo VARCHAR(4) NOT NULL REFERENCES jurisdictions(copo),
    city_name TEXT,
    tax_type TEXT NOT NULL,
    anomaly_date DATE NOT NULL,
    anomaly_type TEXT NOT NULL,
    activity_code VARCHAR(6) REFERENCES naics_codes(activity_code),
    severity TEXT,
    description TEXT,
    expected_value NUMERIC(14,2),
    actual_value NUMERIC(14,2),
    deviation_pct NUMERIC(9,4),
    status TEXT NOT NULL DEFAULT 'saved',
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_user_saved_anomalies_status CHECK (
        status IN ('saved', 'investigating', 'resolved', 'dismissed')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_saved_anomalies_unique
    ON user_saved_anomalies (user_id, copo, tax_type, anomaly_date, anomaly_type, COALESCE(activity_code, ''));

CREATE TABLE IF NOT EXISTS user_saved_missed_filings (
    saved_missed_filing_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    copo VARCHAR(4) NOT NULL REFERENCES jurisdictions(copo),
    city_name TEXT,
    tax_type TEXT NOT NULL,
    anomaly_date DATE NOT NULL,
    activity_code VARCHAR(6) NOT NULL REFERENCES naics_codes(activity_code),
    activity_description TEXT,
    baseline_method TEXT NOT NULL,
    expected_value NUMERIC(14,2),
    actual_value NUMERIC(14,2),
    missing_amount NUMERIC(14,2),
    missing_pct NUMERIC(9,4),
    severity TEXT,
    recommendation TEXT,
    status TEXT NOT NULL DEFAULT 'saved',
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_user_saved_missed_filings_status CHECK (
        status IN ('saved', 'investigating', 'resolved', 'dismissed')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_saved_missed_filings_unique
    ON user_saved_missed_filings (user_id, copo, tax_type, anomaly_date, activity_code, baseline_method);
"""


def load_browser_auth_settings() -> BrowserAuthSettings:
    email_mode = (os.environ.get("MUNIREV_EMAIL_MODE") or "log").strip().lower()
    if email_mode not in {"log", "smtp"}:
        email_mode = "log"

    return BrowserAuthSettings(
        enabled=_parse_bool(os.environ.get("MUNIREV_AUTH_MAGIC_LINK_ENABLED"), False),
        base_url=(os.environ.get("MUNIREV_AUTH_MAGIC_LINK_BASE_URL") or "http://localhost:8000").rstrip("/"),
        magic_link_ttl_minutes=_parse_int(
            os.environ.get("MUNIREV_AUTH_MAGIC_LINK_TTL_MINUTES"),
            15,
            minimum=5,
        ),
        magic_link_rate_limit_window_seconds=_parse_int(
            os.environ.get("MUNIREV_AUTH_MAGIC_LINK_RATE_LIMIT_WINDOW_SECONDS"),
            900,
            minimum=60,
        ),
        magic_link_rate_limit_per_email=_parse_int(
            os.environ.get("MUNIREV_AUTH_MAGIC_LINK_RATE_LIMIT_PER_EMAIL"),
            5,
            minimum=1,
        ),
        magic_link_rate_limit_per_ip=_parse_int(
            os.environ.get("MUNIREV_AUTH_MAGIC_LINK_RATE_LIMIT_PER_IP"),
            20,
            minimum=1,
        ),
        session_days=_parse_int(
            os.environ.get("MUNIREV_AUTH_SESSION_DAYS"),
            30,
            minimum=1,
        ),
        cookie_name=(os.environ.get("MUNIREV_AUTH_COOKIE_NAME") or "munirev_session").strip(),
        cookie_secure=_parse_bool(os.environ.get("MUNIREV_AUTH_COOKIE_SECURE"), True),
        cookie_samesite=_parse_cookie_samesite(os.environ.get("MUNIREV_AUTH_COOKIE_SAMESITE")),
        session_secret=(os.environ.get("MUNIREV_AUTH_SESSION_SECRET") or "development-session-secret").strip(),
        email_mode=email_mode,
        email_from=(os.environ.get("MUNIREV_EMAIL_FROM") or "noreply@munirevenue.com").strip(),
        smtp_host=(os.environ.get("SMTP_HOST") or "").strip() or None,
        smtp_port=_parse_int(os.environ.get("SMTP_PORT"), 587, minimum=1),
        smtp_username=(os.environ.get("SMTP_USERNAME") or "").strip() or None,
        smtp_password=(os.environ.get("SMTP_PASSWORD") or "").strip() or None,
        smtp_use_tls=_parse_bool(os.environ.get("SMTP_USE_TLS"), True),
        email_subject=(os.environ.get("MUNIREV_AUTH_MAGIC_LINK_SUBJECT") or "Your MuniRevenue sign-in link").strip(),
        login_success_redirect=(os.environ.get("MUNIREV_AUTH_LOGIN_SUCCESS_REDIRECT") or "/account").strip() or "/account",
        debug_return_magic_link=_parse_bool(os.environ.get("MUNIREV_AUTH_DEBUG_RETURN_MAGIC_LINK"), False),
    )


def ensure_auth_support_tables() -> None:
    with get_cursor() as cur:
        cur.execute(AUTH_TABLES_DDL)


def normalize_email(value: str) -> str:
    return value.strip().lower()


def sanitize_next_path(value: str | None, fallback: str = "/account") -> str:
    if value is None:
        return fallback
    candidate = value.strip()
    if not candidate:
        return fallback
    if not candidate.startswith("/"):
        return fallback
    if candidate.startswith("//"):
        return fallback
    if "://" in candidate:
        return fallback
    if candidate.startswith("/api"):
        return fallback
    if candidate.startswith("/auth/verify"):
        return fallback
    return candidate


def hash_secret(value: str, secret: str | None = None) -> str:
    material = value.encode("utf-8")
    if secret:
        return hmac.new(secret.encode("utf-8"), material, hashlib.sha256).hexdigest()
    return hashlib.sha256(material).hexdigest()


def hash_user_agent(value: str | None) -> str | None:
    if not value:
        return None
    session_secret = os.environ.get("MUNIREV_AUTH_SESSION_SECRET") or "development-session-secret"
    return hash_secret(value, session_secret)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_request_ip(request: Request) -> str | None:
    if request.client and request.client.host:
        try:
            return str(ipaddress.ip_address(request.client.host))
        except ValueError:
            return None
    return None


def _origin_matches(candidate: str, trusted_origins: list[str]) -> bool:
    return any(candidate.startswith(origin.rstrip("/")) for origin in trusted_origins if origin)


def ensure_safe_browser_origin(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return
    security_settings = request.app.state.security_settings
    trusted_origins = getattr(security_settings, "csrf_trusted_origins", [])
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    if origin and _origin_matches(origin, trusted_origins):
        return
    if referer and _origin_matches(referer, trusted_origins):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Unsafe browser requests require a trusted Origin or Referer.",
    )


def _is_magic_link_rate_limited(
    *,
    cur,
    user_id: str,
    requested_ip: str | None,
    settings: BrowserAuthSettings,
    now: datetime,
) -> bool:
    window_start = now - timedelta(seconds=settings.magic_link_rate_limit_window_seconds)
    cur.execute(
        """
        SELECT COUNT(*) AS request_count
        FROM user_magic_links
        WHERE user_id = %s
          AND created_at >= %s
        """,
        [user_id, window_start],
    )
    email_count = int(cur.fetchone()["request_count"])
    if email_count >= settings.magic_link_rate_limit_per_email:
        return True

    if requested_ip:
        cur.execute(
            """
            SELECT COUNT(*) AS request_count
            FROM user_magic_links
            WHERE requested_ip = %s
              AND created_at >= %s
            """,
            [requested_ip, window_start],
        )
        ip_count = int(cur.fetchone()["request_count"])
        if ip_count >= settings.magic_link_rate_limit_per_ip:
            return True

    return False


def _send_via_smtp(settings: BrowserAuthSettings, recipient: str, link: str) -> None:
    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST must be configured when MUNIREV_EMAIL_MODE=smtp.")

    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = recipient
    message["Subject"] = settings.email_subject
    message.set_content(
        "\n".join(
            [
                "Use this one-time link to sign in to MuniRevenue.",
                "",
                link,
                "",
                f"This link expires in {settings.magic_link_ttl_minutes} minutes.",
                "If you did not request it, you can ignore this email.",
            ]
        )
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


def send_magic_link_email(
    *,
    settings: BrowserAuthSettings,
    recipient: str,
    link: str,
    app_state: object | None = None,
) -> None:
    if settings.email_mode == "smtp":
        _send_via_smtp(settings, recipient, link)
        return

    logger.info("Magic link for %s: %s", recipient, link)
    if app_state is not None and (settings.debug_return_magic_link or settings.email_mode == "log"):
        debug_links = getattr(app_state, "magic_link_debug_links", None)
        if isinstance(debug_links, dict):
            debug_links[normalize_email(recipient)] = link


def request_magic_link(
    *,
    request: Request,
    email: str,
    next_path: str | None,
) -> None:
    settings: BrowserAuthSettings = request.app.state.browser_auth_settings
    normalized_email = normalize_email(email)
    if not normalized_email or "@" not in normalized_email:
        return

    safe_next = sanitize_next_path(next_path, settings.login_success_redirect)
    now = _utc_now()
    expires_at = now + timedelta(minutes=settings.magic_link_ttl_minutes)
    requested_ip = _resolve_request_ip(request)

    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO app_users (email, email_normalized)
            VALUES (%s, %s)
            ON CONFLICT (email_normalized)
            DO UPDATE SET email = EXCLUDED.email
            RETURNING user_id, email
            """,
            [email.strip(), normalized_email],
        )
        user_row = cur.fetchone()
        if _is_magic_link_rate_limited(
            cur=cur,
            user_id=str(user_row["user_id"]),
            requested_ip=requested_ip,
            settings=settings,
            now=now,
        ):
            logger.warning(
                "Suppressed magic link for %s due to rate limit.",
                normalized_email,
            )
            return
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_secret(raw_token, settings.session_secret)
        cur.execute(
            """
            INSERT INTO user_magic_links (
                user_id,
                token_hash,
                next_path,
                requested_ip,
                requested_user_agent_hash,
                expires_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                user_row["user_id"],
                token_hash,
                safe_next,
                requested_ip,
                hash_user_agent(request.headers.get("user-agent")),
                expires_at,
            ],
        )

    link = f"{settings.base_url}/auth/verify?token={quote(raw_token)}"
    send_magic_link_email(
        settings=settings,
        recipient=user_row["email"],
        link=link,
        app_state=request.app.state,
    )


def _create_session(
    *,
    user_id: str,
    request: Request,
    settings: BrowserAuthSettings,
) -> tuple[str, datetime]:
    raw_session_token = secrets.token_urlsafe(32)
    token_hash = hash_secret(raw_session_token, settings.session_secret)
    now = _utc_now()
    expires_at = now + timedelta(days=settings.session_days)
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_sessions (
                user_id,
                session_token_hash,
                expires_at,
                created_ip,
                last_seen_ip,
                user_agent_hash
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                user_id,
                token_hash,
                expires_at,
                _resolve_request_ip(request),
                _resolve_request_ip(request),
                hash_user_agent(request.headers.get("user-agent")),
            ],
        )
    return raw_session_token, expires_at


def consume_magic_link(
    *,
    request: Request,
    token: str,
) -> tuple[str, datetime, str]:
    settings: BrowserAuthSettings = request.app.state.browser_auth_settings
    token_hash = hash_secret(token, settings.session_secret)
    now = _utc_now()

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                ml.magic_link_id,
                ml.user_id,
                ml.next_path,
                u.status
            FROM user_magic_links ml
            JOIN app_users u ON u.user_id = ml.user_id
            WHERE ml.token_hash = %s
              AND ml.consumed_at IS NULL
              AND ml.expires_at >= %s
            """,
            [token_hash, now],
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This sign-in link is invalid or has expired.",
            )
        if row["status"] != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account is not active.",
            )

        cur.execute(
            """
            UPDATE user_magic_links
            SET consumed_at = %s
            WHERE magic_link_id = %s
            """,
            [now, row["magic_link_id"]],
        )
        cur.execute(
            """
            UPDATE app_users
            SET
                email_verified_at = COALESCE(email_verified_at, %s),
                last_login_at = %s,
                updated_at = %s
            WHERE user_id = %s
            """,
            [now, now, now, row["user_id"]],
        )

    raw_session_token, expires_at = _create_session(
        user_id=str(row["user_id"]),
        request=request,
        settings=settings,
    )
    next_path = sanitize_next_path(row["next_path"], settings.login_success_redirect)
    return raw_session_token, expires_at, next_path


def resolve_user_session(request: Request) -> UserSessionContext | None:
    settings: BrowserAuthSettings = request.app.state.browser_auth_settings
    if not settings.enabled:
        return None
    token = request.cookies.get(settings.cookie_name)
    if not token:
        return None

    token_hash = hash_secret(token, settings.session_secret)
    now = _utc_now()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                s.session_id,
                s.user_id,
                s.expires_at,
                u.email,
                u.display_name,
                u.job_title,
                u.organization_name,
                u.status
            FROM user_sessions s
            JOIN app_users u ON u.user_id = s.user_id
            WHERE s.session_token_hash = %s
              AND s.revoked_at IS NULL
              AND s.expires_at >= %s
            """,
            [token_hash, now],
        )
        row = cur.fetchone()
        if row is None or row["status"] != "active":
            return None

        cur.execute(
            """
            UPDATE user_sessions
            SET
                last_seen_at = %s,
                last_seen_ip = %s
            WHERE session_id = %s
            """,
            [now, _resolve_request_ip(request), row["session_id"]],
        )

    return UserSessionContext(
        user_id=str(row["user_id"]),
        email=row["email"],
        display_name=row["display_name"],
        job_title=row["job_title"],
        organization_name=row["organization_name"],
        session_id=str(row["session_id"]),
        expires_at=row["expires_at"],
    )


def revoke_session(request: Request) -> None:
    settings: BrowserAuthSettings = request.app.state.browser_auth_settings
    token = request.cookies.get(settings.cookie_name)
    if not token:
        return

    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE user_sessions
            SET revoked_at = %s
            WHERE session_token_hash = %s
              AND revoked_at IS NULL
            """,
            [_utc_now(), hash_secret(token, settings.session_secret)],
        )


def get_optional_user_session(request: Request) -> UserSessionContext | None:
    return getattr(request.state, "user_session", None)


def require_user_session(request: Request) -> UserSessionContext:
    user_session = get_optional_user_session(request)
    settings: BrowserAuthSettings = request.app.state.browser_auth_settings
    if not settings.enabled or user_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login is required for this feature.",
        )
    ensure_safe_browser_origin(request)
    return user_session


def require_feature_access(request: Request):
    user_session = get_optional_user_session(request)
    if user_session is not None:
        return user_session

    from app.security import get_auth_context

    auth_context = get_auth_context(request)
    settings = request.app.state.security_settings
    if settings.auth_mode != "off" and auth_context.is_authenticated and auth_context.has_scopes({"api:read"}):
        return auth_context

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Login is required for this feature.",
    )
