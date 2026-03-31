from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.security import AuthContext, SecuritySettings, require_scopes


router = APIRouter(prefix="/api", tags=["system"])


class AuthMeResponse(BaseModel):
    subject: str | None
    roles: list[str]
    scopes: list[str]
    auth_mode: str
    auth_method: str
    request_id: str | None = None


class SecurityStatusResponse(BaseModel):
    auth_mode: str
    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_window_seconds: int
    force_https: bool
    trust_forwarded_for: bool
    allowed_hosts: list[str]
    cors_origins: list[str]
    csrf_trusted_origins: list[str]
    proxy_subject_headers: list[str]
    proxy_role_headers: list[str]
    proxy_scope_headers: list[str]
    openapi_enabled: bool


@router.get(
    "/auth/me",
    response_model=AuthMeResponse,
    dependencies=[Depends(require_scopes("api:read"))],
)
def get_auth_me(request: Request) -> AuthMeResponse:
    auth_context: AuthContext = request.state.auth_context
    return AuthMeResponse(
        subject=auth_context.subject,
        roles=list(auth_context.roles),
        scopes=list(auth_context.scopes),
        auth_mode=auth_context.auth_mode,
        auth_method=auth_context.auth_method,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get(
    "/admin/security",
    response_model=SecurityStatusResponse,
    dependencies=[Depends(require_scopes("api:admin"))],
)
def get_security_status(request: Request) -> SecurityStatusResponse:
    settings: SecuritySettings = request.app.state.security_settings
    return SecurityStatusResponse(
        auth_mode=settings.auth_mode,
        rate_limit_enabled=settings.rate_limit_enabled,
        rate_limit_requests=settings.rate_limit_requests,
        rate_limit_window_seconds=settings.rate_limit_window_seconds,
        force_https=settings.force_https,
        trust_forwarded_for=settings.trust_forwarded_for,
        allowed_hosts=settings.allowed_hosts,
        cors_origins=settings.cors_origins,
        csrf_trusted_origins=settings.csrf_trusted_origins,
        proxy_subject_headers=list(settings.proxy_auth_headers),
        proxy_role_headers=list(settings.proxy_role_headers),
        proxy_scope_headers=list(settings.proxy_scope_headers),
        openapi_enabled=settings.openapi_enabled,
    )
