from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.db.psycopg import get_cursor
from app.services.forecasting import SUPPORTED_DRIVER_PROFILES, SUPPORTED_FORECAST_MODELS
from app.user_auth import (
    BrowserAuthSettings,
    UserSessionContext,
    consume_magic_link,
    ensure_safe_browser_origin,
    get_optional_user_session,
    request_magic_link,
    require_user_session,
    revoke_session,
    sanitize_next_path,
)


router = APIRouter(tags=["account"])

FOLLOW_UP_STATUSES = {"saved", "investigating", "resolved", "dismissed"}
ANOMALY_TYPES = {"yoy_spike", "yoy_drop", "mom_outlier", "missing_data", "naics_shift"}
BASELINE_METHODS = {
    "hybrid",
    "yoy",
    "trailing_mean_3",
    "trailing_mean_6",
    "trailing_mean_12",
    "trailing_median_12",
    "exp_weighted_12",
}
FORECAST_LOOKBACK_MONTHS = {24, 36, 48}


class MagicLinkRequest(BaseModel):
    email: str
    next_path: Optional[str] = None


class MagicLinkResponse(BaseModel):
    ok: bool = True
    message: str


class SessionUserResponse(BaseModel):
    user_id: str
    email: str
    display_name: Optional[str] = None
    job_title: Optional[str] = None
    organization_name: Optional[str] = None


class SessionResponse(BaseModel):
    authenticated: bool
    user: Optional[SessionUserResponse] = None


class ProfileResponse(BaseModel):
    user_id: str
    email: str
    display_name: Optional[str] = None
    job_title: Optional[str] = None
    organization_name: Optional[str] = None
    marketing_opt_in: bool = False


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    job_title: Optional[str] = None
    organization_name: Optional[str] = None
    marketing_opt_in: bool = False


class JurisdictionInterestItem(BaseModel):
    interest_id: str
    interest_type: str
    copo: Optional[str] = None
    county_name: Optional[str] = None
    label: str


class JurisdictionInterestWriteItem(BaseModel):
    interest_type: str
    copo: Optional[str] = None
    county_name: Optional[str] = None
    label: Optional[str] = None


class JurisdictionInterestsResponse(BaseModel):
    items: list[JurisdictionInterestItem] = Field(default_factory=list)


class JurisdictionInterestsUpdateRequest(BaseModel):
    items: list[JurisdictionInterestWriteItem] = Field(default_factory=list)


class ForecastPreferencesResponse(BaseModel):
    default_city_copo: Optional[str] = None
    default_county_name: Optional[str] = None
    default_tax_type: Optional[str] = None
    forecast_model: Optional[str] = None
    forecast_horizon_months: Optional[int] = None
    forecast_lookback_months: Optional[int] = None
    forecast_confidence_level: Optional[float] = None
    forecast_indicator_profile: Optional[str] = None
    forecast_scope: Optional[str] = None
    forecast_activity_code: Optional[str] = None


class ForecastPreferencesUpdateRequest(BaseModel):
    default_city_copo: Optional[str] = None
    default_county_name: Optional[str] = None
    default_tax_type: Optional[str] = None
    forecast_model: Optional[str] = None
    forecast_horizon_months: Optional[int] = None
    forecast_lookback_months: Optional[int] = None
    forecast_confidence_level: Optional[float] = None
    forecast_indicator_profile: Optional[str] = None
    forecast_scope: Optional[str] = None
    forecast_activity_code: Optional[str] = None


class SavedAnomalyItem(BaseModel):
    saved_anomaly_id: str
    copo: str
    tax_type: str
    anomaly_date: date
    anomaly_type: str
    activity_code: Optional[str] = None
    status: str
    note: Optional[str] = None
    city_name: Optional[str] = None


class SavedAnomalyCreateRequest(BaseModel):
    copo: str
    tax_type: str
    anomaly_date: date
    anomaly_type: str
    activity_code: Optional[str] = None
    status: str = "saved"
    note: Optional[str] = None


class SavedAnomalyUpdateRequest(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None


class SavedAnomaliesResponse(BaseModel):
    items: list[SavedAnomalyItem] = Field(default_factory=list)


class SavedMissedFilingItem(BaseModel):
    saved_missed_filing_id: str
    copo: str
    tax_type: str
    anomaly_date: date
    activity_code: str
    baseline_method: str
    expected_value: Optional[float] = None
    actual_value: Optional[float] = None
    missing_amount: Optional[float] = None
    missing_pct: Optional[float] = None
    status: str
    note: Optional[str] = None
    city_name: Optional[str] = None


class SavedMissedFilingCreateRequest(BaseModel):
    copo: str
    tax_type: str
    anomaly_date: date
    activity_code: str
    baseline_method: str
    expected_value: Optional[float] = None
    actual_value: Optional[float] = None
    missing_amount: Optional[float] = None
    missing_pct: Optional[float] = None
    status: str = "saved"
    note: Optional[str] = None


class SavedMissedFilingUpdateRequest(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None


class SavedMissedFilingsResponse(BaseModel):
    items: list[SavedMissedFilingItem] = Field(default_factory=list)


def _auth_enabled(request: Request) -> bool:
    settings: BrowserAuthSettings = request.app.state.browser_auth_settings
    return settings.enabled


def _ensure_valid_status(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in FOLLOW_UP_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid follow-up status.")
    return normalized


def _session_user_response(user_session: UserSessionContext) -> SessionUserResponse:
    return SessionUserResponse(
        user_id=user_session.user_id,
        email=user_session.email,
        display_name=user_session.display_name,
        job_title=user_session.job_title,
        organization_name=user_session.organization_name,
    )


def _ensure_known_city(cur, copo: str) -> str:
    cur.execute("SELECT name FROM jurisdictions WHERE copo = %s", [copo])
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=400, detail="Unknown city jurisdiction.")
    return row["name"]


def _ensure_known_county(cur, county_name: str) -> str:
    normalized = county_name.strip()
    cur.execute(
        """
        SELECT county_name
        FROM jurisdictions
        WHERE county_name = %s
        LIMIT 1
        """,
        [normalized],
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=400, detail="Unknown county.")
    return row["county_name"]


def _ensure_known_activity_code(cur, activity_code: str) -> None:
    cur.execute(
        "SELECT 1 FROM naics_codes WHERE activity_code = %s",
        [activity_code],
    )
    if cur.fetchone() is None:
        raise HTTPException(status_code=400, detail="Unknown NAICS activity code.")


def _validate_tax_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in {"sales", "use", "lodging"}:
        raise HTTPException(status_code=400, detail="Invalid tax type.")
    return normalized


def _validate_missed_filing_tax_type(value: str) -> str:
    normalized = _validate_tax_type(value)
    if normalized not in {"sales", "use"}:
        raise HTTPException(status_code=400, detail="Missed filings only support sales or use tax.")
    return normalized


def _validate_forecast_scope(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in {"municipal", "naics"}:
        raise HTTPException(status_code=400, detail="Invalid forecast scope.")
    return normalized


def _validate_forecast_model(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_FORECAST_MODELS:
        raise HTTPException(status_code=400, detail="Invalid forecast model.")
    return normalized


def _validate_forecast_horizon_months(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    if value < 1 or value > 24:
        raise HTTPException(status_code=400, detail="Forecast horizon must be between 1 and 24 months.")
    return value


def _validate_forecast_lookback_months(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    if value not in FORECAST_LOOKBACK_MONTHS:
        raise HTTPException(status_code=400, detail="Forecast lookback must be one of 24, 36, or 48 months.")
    return value


def _validate_forecast_confidence_level(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if value < 0.80 or value > 0.99:
        raise HTTPException(status_code=400, detail="Forecast confidence must be between 0.80 and 0.99.")
    return value


def _validate_indicator_profile(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_DRIVER_PROFILES:
        raise HTTPException(status_code=400, detail="Invalid forecast indicator profile.")
    return normalized


def _validate_anomaly_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ANOMALY_TYPES:
        raise HTTPException(status_code=400, detail="Invalid anomaly type.")
    return normalized


def _validate_baseline_method(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in BASELINE_METHODS:
        raise HTTPException(status_code=400, detail="Invalid baseline method.")
    return normalized


def _fetch_profile(user_id: str) -> ProfileResponse:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                user_id,
                email,
                display_name,
                job_title,
                organization_name,
                marketing_opt_in
            FROM app_users
            WHERE user_id = %s
            """,
            [user_id],
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return ProfileResponse(
        user_id=str(row["user_id"]),
        email=row["email"],
        display_name=row["display_name"],
        job_title=row["job_title"],
        organization_name=row["organization_name"],
        marketing_opt_in=bool(row["marketing_opt_in"]),
    )


@router.post("/api/auth/magic-link/request", response_model=MagicLinkResponse)
def create_magic_link(request: Request, payload: MagicLinkRequest) -> MagicLinkResponse:
    if _auth_enabled(request):
        ensure_safe_browser_origin(request)
        request_magic_link(request=request, email=payload.email, next_path=payload.next_path)
    return MagicLinkResponse(message="If that email is eligible, a sign-in link has been sent.")


@router.get("/auth/verify", include_in_schema=False)
def verify_magic_link(
    request: Request,
    token: str = Query(...),
    next: Optional[str] = Query(None),
) -> RedirectResponse:
    settings: BrowserAuthSettings = request.app.state.browser_auth_settings
    if not settings.enabled:
        return RedirectResponse(url="/login?disabled=1", status_code=303)
    try:
        raw_session_token, expires_at, next_path = consume_magic_link(request=request, token=token)
    except HTTPException:
        return RedirectResponse(url="/login?error=invalid-link", status_code=303)
    if next:
        next_path = sanitize_next_path(next, next_path)
    response = RedirectResponse(url=next_path, status_code=303)
    response.set_cookie(
        key=settings.cookie_name,
        value=raw_session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=int((expires_at - datetime.now(expires_at.tzinfo)).total_seconds()),
        expires=int(expires_at.timestamp()),
        path="/",
    )
    return response


@router.get("/api/auth/session", response_model=SessionResponse)
def get_session(request: Request) -> SessionResponse:
    user_session = get_optional_user_session(request)
    if user_session is None:
        return SessionResponse(authenticated=False, user=None)
    return SessionResponse(authenticated=True, user=_session_user_response(user_session))


@router.post("/api/auth/logout", response_model=MagicLinkResponse)
def logout(
    request: Request,
    response: Response,
    user_session: UserSessionContext = Depends(require_user_session),
) -> MagicLinkResponse:
    del user_session
    settings: BrowserAuthSettings = request.app.state.browser_auth_settings
    revoke_session(request)
    response.delete_cookie(key=settings.cookie_name, path="/")
    return MagicLinkResponse(message="You have been logged out.")


@router.get("/api/account/profile", response_model=ProfileResponse)
def get_profile(user_session: UserSessionContext = Depends(require_user_session)) -> ProfileResponse:
    return _fetch_profile(user_session.user_id)


@router.put("/api/account/profile", response_model=ProfileResponse)
def update_profile(
    payload: ProfileUpdateRequest,
    user_session: UserSessionContext = Depends(require_user_session),
) -> ProfileResponse:
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE app_users
            SET
                display_name = %s,
                job_title = %s,
                organization_name = %s,
                marketing_opt_in = %s,
                updated_at = NOW()
            WHERE user_id = %s
            """,
            [
                payload.display_name,
                payload.job_title,
                payload.organization_name,
                payload.marketing_opt_in,
                user_session.user_id,
            ],
        )
    return _fetch_profile(user_session.user_id)


@router.get("/api/account/interests", response_model=JurisdictionInterestsResponse)
def get_interests(user_session: UserSessionContext = Depends(require_user_session)) -> JurisdictionInterestsResponse:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT interest_id, interest_type, copo, county_name, label
            FROM user_jurisdiction_interests
            WHERE user_id = %s
            ORDER BY interest_type, label
            """,
            [user_session.user_id],
        )
        rows = cur.fetchall()
    return JurisdictionInterestsResponse(
        items=[
            JurisdictionInterestItem(
                interest_id=str(row["interest_id"]),
                interest_type=row["interest_type"],
                copo=row["copo"],
                county_name=row["county_name"],
                label=row["label"],
            )
            for row in rows
        ]
    )


@router.put("/api/account/interests", response_model=JurisdictionInterestsResponse)
def replace_interests(
    payload: JurisdictionInterestsUpdateRequest,
    user_session: UserSessionContext = Depends(require_user_session),
) -> JurisdictionInterestsResponse:
    with get_cursor() as cur:
        cur.execute("DELETE FROM user_jurisdiction_interests WHERE user_id = %s", [user_session.user_id])
        for item in payload.items:
            interest_type = item.interest_type.strip().lower()
            if interest_type not in {"city", "county"}:
                raise HTTPException(status_code=400, detail="Invalid interest type.")
            label = item.label
            if interest_type == "city" and item.copo:
                label = label or _ensure_known_city(cur, item.copo)
            elif interest_type == "county" and item.county_name:
                label = label or _ensure_known_county(cur, item.county_name)
            else:
                raise HTTPException(status_code=400, detail="Interest target is incomplete.")
            cur.execute(
                """
                INSERT INTO user_jurisdiction_interests (
                    user_id,
                    interest_type,
                    copo,
                    county_name,
                    label
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                [
                    user_session.user_id,
                    interest_type,
                    item.copo if interest_type == "city" else None,
                    item.county_name if interest_type == "county" else None,
                    label,
                ],
            )
    return get_interests(user_session)


@router.get("/api/account/forecast-preferences", response_model=ForecastPreferencesResponse)
def get_forecast_preferences(
    user_session: UserSessionContext = Depends(require_user_session),
) -> ForecastPreferencesResponse:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                default_city_copo,
                default_county_name,
                default_tax_type,
                forecast_model,
                forecast_horizon_months,
                forecast_lookback_months,
                forecast_confidence_level,
                forecast_indicator_profile,
                forecast_scope,
                forecast_activity_code
            FROM user_profile_preferences
            WHERE user_id = %s
            """,
            [user_session.user_id],
        )
        row = cur.fetchone()
    if row is None:
        return ForecastPreferencesResponse()
    return ForecastPreferencesResponse(
        default_city_copo=row["default_city_copo"],
        default_county_name=row["default_county_name"],
        default_tax_type=row["default_tax_type"],
        forecast_model=row["forecast_model"],
        forecast_horizon_months=row["forecast_horizon_months"],
        forecast_lookback_months=row["forecast_lookback_months"],
        forecast_confidence_level=float(row["forecast_confidence_level"]) if row["forecast_confidence_level"] is not None else None,
        forecast_indicator_profile=row["forecast_indicator_profile"],
        forecast_scope=row["forecast_scope"],
        forecast_activity_code=row["forecast_activity_code"],
    )


@router.put("/api/account/forecast-preferences", response_model=ForecastPreferencesResponse)
def update_forecast_preferences(
    payload: ForecastPreferencesUpdateRequest,
    user_session: UserSessionContext = Depends(require_user_session),
) -> ForecastPreferencesResponse:
    normalized_tax_type = _validate_tax_type(payload.default_tax_type)
    normalized_scope = _validate_forecast_scope(payload.forecast_scope)
    normalized_model = _validate_forecast_model(payload.forecast_model)
    normalized_horizon = _validate_forecast_horizon_months(payload.forecast_horizon_months)
    normalized_lookback = _validate_forecast_lookback_months(payload.forecast_lookback_months)
    normalized_confidence = _validate_forecast_confidence_level(payload.forecast_confidence_level)
    normalized_indicator_profile = _validate_indicator_profile(payload.forecast_indicator_profile)
    with get_cursor() as cur:
        if payload.default_city_copo:
            _ensure_known_city(cur, payload.default_city_copo)
        if payload.default_county_name:
            _ensure_known_county(cur, payload.default_county_name)
        if payload.forecast_activity_code:
            _ensure_known_activity_code(cur, payload.forecast_activity_code)
        cur.execute(
            """
            INSERT INTO user_profile_preferences (
                user_id,
                default_city_copo,
                default_county_name,
                default_tax_type,
                forecast_model,
                forecast_horizon_months,
                forecast_lookback_months,
                forecast_confidence_level,
                forecast_indicator_profile,
                forecast_scope,
                forecast_activity_code,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET
                default_city_copo = EXCLUDED.default_city_copo,
                default_county_name = EXCLUDED.default_county_name,
                default_tax_type = EXCLUDED.default_tax_type,
                forecast_model = EXCLUDED.forecast_model,
                forecast_horizon_months = EXCLUDED.forecast_horizon_months,
                forecast_lookback_months = EXCLUDED.forecast_lookback_months,
                forecast_confidence_level = EXCLUDED.forecast_confidence_level,
                forecast_indicator_profile = EXCLUDED.forecast_indicator_profile,
                forecast_scope = EXCLUDED.forecast_scope,
                forecast_activity_code = EXCLUDED.forecast_activity_code,
                updated_at = NOW()
            """,
            [
                user_session.user_id,
                payload.default_city_copo,
                payload.default_county_name,
                normalized_tax_type,
                normalized_model,
                normalized_horizon,
                normalized_lookback,
                normalized_confidence,
                normalized_indicator_profile,
                normalized_scope,
                payload.forecast_activity_code,
            ],
        )
    return get_forecast_preferences(user_session)


@router.get("/api/account/saved-anomalies", response_model=SavedAnomaliesResponse)
def get_saved_anomalies(user_session: UserSessionContext = Depends(require_user_session)) -> SavedAnomaliesResponse:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                s.saved_anomaly_id,
                s.copo,
                s.tax_type,
                s.anomaly_date,
                s.anomaly_type,
                s.activity_code,
                s.status,
                s.note,
                j.name AS city_name
            FROM user_saved_anomalies s
            JOIN jurisdictions j ON j.copo = s.copo
            WHERE s.user_id = %s
            ORDER BY s.anomaly_date DESC, j.name ASC
            """,
            [user_session.user_id],
        )
        rows = cur.fetchall()
    return SavedAnomaliesResponse(
        items=[
            SavedAnomalyItem(
                saved_anomaly_id=str(row["saved_anomaly_id"]),
                copo=row["copo"],
                tax_type=row["tax_type"],
                anomaly_date=row["anomaly_date"],
                anomaly_type=row["anomaly_type"],
                activity_code=row["activity_code"],
                status=row["status"],
                note=row["note"],
                city_name=row["city_name"],
            )
            for row in rows
        ]
    )


@router.post("/api/account/saved-anomalies", response_model=SavedAnomaliesResponse)
def create_saved_anomaly(
    payload: SavedAnomalyCreateRequest,
    user_session: UserSessionContext = Depends(require_user_session),
) -> SavedAnomaliesResponse:
    status_value = _ensure_valid_status(payload.status) or "saved"
    normalized_tax_type = _validate_tax_type(payload.tax_type)
    normalized_anomaly_type = _validate_anomaly_type(payload.anomaly_type)
    with get_cursor() as cur:
        city_name = _ensure_known_city(cur, payload.copo)
        if payload.activity_code:
            _ensure_known_activity_code(cur, payload.activity_code)
        cur.execute(
            """
            SELECT saved_anomaly_id
            FROM user_saved_anomalies
            WHERE user_id = %s
              AND copo = %s
              AND tax_type = %s
              AND anomaly_date = %s
              AND anomaly_type = %s
              AND (
                (activity_code = %s)
                OR (activity_code IS NULL AND %s IS NULL)
              )
            """,
            [
                user_session.user_id,
                payload.copo,
                normalized_tax_type,
                payload.anomaly_date,
                normalized_anomaly_type,
                payload.activity_code,
                payload.activity_code,
            ],
        )
        existing = cur.fetchone()
        if existing is None:
            cur.execute(
                """
                INSERT INTO user_saved_anomalies (
                    user_id,
                    copo,
                    city_name,
                    tax_type,
                    anomaly_date,
                    anomaly_type,
                    activity_code,
                    status,
                    note
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    user_session.user_id,
                    payload.copo,
                    city_name,
                    normalized_tax_type,
                    payload.anomaly_date,
                    normalized_anomaly_type,
                    payload.activity_code,
                    status_value,
                    payload.note,
                ],
            )
        else:
            cur.execute(
                """
                UPDATE user_saved_anomalies
                SET
                    status = %s,
                    note = %s,
                    updated_at = NOW()
                WHERE saved_anomaly_id = %s
                """,
                [status_value, payload.note, existing["saved_anomaly_id"]],
            )
    return get_saved_anomalies(user_session)


@router.patch("/api/account/saved-anomalies/{saved_anomaly_id}", response_model=SavedAnomaliesResponse)
def update_saved_anomaly(
    saved_anomaly_id: str,
    payload: SavedAnomalyUpdateRequest,
    user_session: UserSessionContext = Depends(require_user_session),
) -> SavedAnomaliesResponse:
    status_value = _ensure_valid_status(payload.status) if payload.status is not None else None
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE user_saved_anomalies
            SET
                status = COALESCE(%s, status),
                note = COALESCE(%s, note),
                updated_at = NOW()
            WHERE saved_anomaly_id = %s
              AND user_id = %s
            """,
            [status_value, payload.note, saved_anomaly_id, user_session.user_id],
        )
    return get_saved_anomalies(user_session)


@router.delete("/api/account/saved-anomalies/{saved_anomaly_id}", response_model=SavedAnomaliesResponse)
def delete_saved_anomaly(
    saved_anomaly_id: str,
    user_session: UserSessionContext = Depends(require_user_session),
) -> SavedAnomaliesResponse:
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM user_saved_anomalies WHERE saved_anomaly_id = %s AND user_id = %s",
            [saved_anomaly_id, user_session.user_id],
        )
    return get_saved_anomalies(user_session)


@router.get("/api/account/saved-missed-filings", response_model=SavedMissedFilingsResponse)
def get_saved_missed_filings(
    user_session: UserSessionContext = Depends(require_user_session),
) -> SavedMissedFilingsResponse:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                s.saved_missed_filing_id,
                s.copo,
                s.tax_type,
                s.anomaly_date,
                s.activity_code,
                s.baseline_method,
                s.expected_value,
                s.actual_value,
                s.missing_amount,
                s.missing_pct,
                s.status,
                s.note,
                j.name AS city_name
            FROM user_saved_missed_filings s
            JOIN jurisdictions j ON j.copo = s.copo
            WHERE s.user_id = %s
            ORDER BY s.anomaly_date DESC, j.name ASC
            """,
            [user_session.user_id],
        )
        rows = cur.fetchall()
    return SavedMissedFilingsResponse(
        items=[
            SavedMissedFilingItem(
                saved_missed_filing_id=str(row["saved_missed_filing_id"]),
                copo=row["copo"],
                tax_type=row["tax_type"],
                anomaly_date=row["anomaly_date"],
                activity_code=row["activity_code"],
                baseline_method=row["baseline_method"],
                expected_value=float(row["expected_value"]) if row["expected_value"] is not None else None,
                actual_value=float(row["actual_value"]) if row["actual_value"] is not None else None,
                missing_amount=float(row["missing_amount"]) if row["missing_amount"] is not None else None,
                missing_pct=float(row["missing_pct"]) if row["missing_pct"] is not None else None,
                status=row["status"],
                note=row["note"],
                city_name=row["city_name"],
            )
            for row in rows
        ]
    )


@router.post("/api/account/saved-missed-filings", response_model=SavedMissedFilingsResponse)
def create_saved_missed_filing(
    payload: SavedMissedFilingCreateRequest,
    user_session: UserSessionContext = Depends(require_user_session),
) -> SavedMissedFilingsResponse:
    status_value = _ensure_valid_status(payload.status) or "saved"
    normalized_tax_type = _validate_missed_filing_tax_type(payload.tax_type)
    normalized_baseline_method = _validate_baseline_method(payload.baseline_method)
    with get_cursor() as cur:
        city_name = _ensure_known_city(cur, payload.copo)
        _ensure_known_activity_code(cur, payload.activity_code)
        cur.execute(
            """
            INSERT INTO user_saved_missed_filings (
                user_id,
                copo,
                city_name,
                tax_type,
                anomaly_date,
                activity_code,
                baseline_method,
                expected_value,
                actual_value,
                missing_amount,
                missing_pct,
                status,
                note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, copo, tax_type, anomaly_date, activity_code, baseline_method)
            DO UPDATE SET
                city_name = EXCLUDED.city_name,
                expected_value = EXCLUDED.expected_value,
                actual_value = EXCLUDED.actual_value,
                missing_amount = EXCLUDED.missing_amount,
                missing_pct = EXCLUDED.missing_pct,
                status = EXCLUDED.status,
                note = EXCLUDED.note,
                updated_at = NOW()
            """,
            [
                user_session.user_id,
                payload.copo,
                city_name,
                normalized_tax_type,
                payload.anomaly_date,
                payload.activity_code,
                normalized_baseline_method,
                payload.expected_value,
                payload.actual_value,
                payload.missing_amount,
                payload.missing_pct,
                status_value,
                payload.note,
            ],
        )
    return get_saved_missed_filings(user_session)


@router.patch("/api/account/saved-missed-filings/{saved_missed_filing_id}", response_model=SavedMissedFilingsResponse)
def update_saved_missed_filing(
    saved_missed_filing_id: str,
    payload: SavedMissedFilingUpdateRequest,
    user_session: UserSessionContext = Depends(require_user_session),
) -> SavedMissedFilingsResponse:
    status_value = _ensure_valid_status(payload.status) if payload.status is not None else None
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE user_saved_missed_filings
            SET
                status = COALESCE(%s, status),
                note = COALESCE(%s, note),
                updated_at = NOW()
            WHERE saved_missed_filing_id = %s
              AND user_id = %s
            """,
            [status_value, payload.note, saved_missed_filing_id, user_session.user_id],
        )
    return get_saved_missed_filings(user_session)


@router.delete("/api/account/saved-missed-filings/{saved_missed_filing_id}", response_model=SavedMissedFilingsResponse)
def delete_saved_missed_filing(
    saved_missed_filing_id: str,
    user_session: UserSessionContext = Depends(require_user_session),
) -> SavedMissedFilingsResponse:
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM user_saved_missed_filings WHERE saved_missed_filing_id = %s AND user_id = %s",
            [saved_missed_filing_id, user_session.user_id],
        )
    return get_saved_missed_filings(user_session)
