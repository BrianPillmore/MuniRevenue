from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.analytics import router as analytics_router
from app.api.cities import router as cities_router
from app.api.oktap import router as oktap_router
from app.schemas import AnalysisResponse
from app.security import (
    TokenBucketRateLimiter,
    load_security_settings,
    security_middleware,
)
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
    rate_limiter = TokenBucketRateLimiter(
        capacity=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )

    app = FastAPI(title="MuniRev API", version="1.0.0")
    app.state.security_settings = settings
    app.state.rate_limiter = rate_limiter

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
        )

    app.include_router(cities_router)
    app.include_router(analytics_router)
    app.include_router(oktap_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/sample-data")
    def sample_data() -> FileResponse:
        return FileResponse(
            ASSETS_DIR / "sample-data.xlsx",
            filename="MuniRev-SampleData.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/api/sample-report")
    def sample_report() -> FileResponse:
        return FileResponse(
            ASSETS_DIR / "sample-report.pdf",
            filename="MuniRev-SampleReport.pdf",
            media_type="application/pdf",
        )

    @app.post("/api/analyze", response_model=AnalysisResponse)
    async def analyze(file: UploadFile = File(...)) -> AnalysisResponse:
        validate_upload(file)
        try:
            file_bytes = await file.read()
            return analyze_excel_bytes(file_bytes)
        except InputDataError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive API boundary
            raise HTTPException(status_code=500, detail="The spreadsheet could not be analyzed.") from exc

    @app.post("/api/report")
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
            file_path = FRONTEND_DIST / full_path
            if file_path.is_file() and not full_path.startswith("api"):
                return FileResponse(str(file_path))
            return FileResponse(str(FRONTEND_DIST / "index.html"))

    return app


app = create_app()
