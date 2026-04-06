from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.analytics import ensure_analytics_support_tables, router as analytics_router
from app.api.account import router as account_router
from app.api.cities import router as cities_router
from app.api.contacts import router as contacts_router
try:
    from app.api.gtm import router as gtm_router
except ModuleNotFoundError:
    gtm_router = None  # type: ignore[assignment]
try:
    from app.api.prospects import router as prospects_router
except ModuleNotFoundError:
    prospects_router = None  # type: ignore[assignment]
from app.api.report_page import router as report_page_router
from app.api.oktap import router as oktap_router
from app.api.system import router as system_router
from app.schemas import AnalysisResponse
from app.security import (
    TokenBucketRateLimiter,
    load_security_settings,
    require_scopes,
    security_middleware,
)
from app.user_auth import ensure_auth_support_tables, load_browser_auth_settings
from app.services.analysis import InputDataError, analyze_excel_bytes
from app.services.reporting import render_report_html


BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"


def validate_upload(file: UploadFile) -> None:
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx spreadsheet.")


def create_app() -> FastAPI:
    settings = load_security_settings()
    browser_auth_settings = load_browser_auth_settings()
    ensure_analytics_support_tables()
    ensure_auth_support_tables()
    rate_limiter = TokenBucketRateLimiter(
        capacity=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )

    app = FastAPI(
        title="MuniRev API",
        version="1.0.0",
        openapi_url="/openapi.json" if settings.openapi_enabled else None,
        docs_url="/docs" if settings.openapi_enabled else None,
        redoc_url="/redoc" if settings.openapi_enabled else None,
    )
    app.state.security_settings = settings
    app.state.browser_auth_settings = browser_auth_settings
    app.state.rate_limiter = rate_limiter
    app.state.magic_link_debug_links = {}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts,
    )
    if settings.force_https:
        app.add_middleware(HTTPSRedirectMiddleware)

    @app.middleware("http")
    async def apply_security(request, call_next):
        return await security_middleware(
            request,
            call_next,
            settings=settings,
            rate_limiter=rate_limiter,
            browser_auth_settings=browser_auth_settings,
        )

    app.include_router(cities_router)
    app.include_router(analytics_router)
    app.include_router(account_router)
    app.include_router(oktap_router)
    app.include_router(system_router)
    app.include_router(contacts_router)
    if gtm_router is not None:
        app.include_router(gtm_router)
    if prospects_router is not None:
        app.include_router(prospects_router)
    app.include_router(report_page_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/sample-data", dependencies=[Depends(require_scopes("api:read"))])
    def sample_data() -> FileResponse:
        return FileResponse(
            ASSETS_DIR / "sample-data.xlsx",
            filename="MuniRev-SampleData.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/api/sample-report", dependencies=[Depends(require_scopes("api:read"))])
    def sample_report() -> FileResponse:
        return FileResponse(
            ASSETS_DIR / "sample-report.pdf",
            filename="MuniRev-SampleReport.pdf",
            media_type="application/pdf",
        )

    @app.post(
        "/api/analyze",
        response_model=AnalysisResponse,
        dependencies=[Depends(require_scopes("analysis:run"))],
    )
    async def analyze(file: UploadFile = File(...)) -> AnalysisResponse:
        validate_upload(file)
        try:
            file_bytes = await file.read()
            return analyze_excel_bytes(file_bytes)
        except InputDataError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive API boundary
            raise HTTPException(status_code=500, detail="The spreadsheet could not be analyzed.") from exc

    @app.post(
        "/api/report",
        dependencies=[Depends(require_scopes("reports:generate"))],
    )
    async def generate_report(file: UploadFile = File(...)) -> HTMLResponse:
        validate_upload(file)
        try:
            file_bytes = await file.read()
            analysis = analyze_excel_bytes(file_bytes)
            report_html = render_report_html(analysis)
            headers = {"Content-Disposition": 'attachment; filename="MuniRev-Analysis-Report.html"'}
            return HTMLResponse(content=report_html, headers=headers)
        except InputDataError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive API boundary
            raise HTTPException(status_code=500, detail="The report could not be generated.") from exc

    if FRONTEND_DIST.is_dir():
        _assets_dir = FRONTEND_DIST / "assets"
        if _assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="static-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:
            """Serve the SPA index.html for any path not matched by API routes."""
            if not settings.openapi_enabled and (
                full_path == "openapi.json"
                or full_path == "docs"
                or full_path.startswith("docs/")
                or full_path == "redoc"
            ):
                raise HTTPException(status_code=404, detail="Not found.")
            file_path = FRONTEND_DIST / full_path
            if file_path.is_file() and not full_path.startswith("api"):
                return FileResponse(str(file_path))
            directory_index = file_path / "index.html"
            if directory_index.is_file() and not full_path.startswith("api"):
                return FileResponse(str(directory_index))
            return FileResponse(str(FRONTEND_DIST / "index.html"))

    return app


app = create_app()
