@echo off
REM MuniRev - Local deployment (Windows)
REM Builds the frontend and starts the backend on port 8000.

cd /d "%~dp0"

echo Installing backend dependencies...
cd backend
if not exist .venv (python -m venv .venv)
.venv\Scripts\pip install -q -r requirements.txt

echo Building frontend...
cd ..\frontend
call npm install --silent
call npm run build

echo.
echo Starting MuniRev on http://127.0.0.1:8000
echo Press Ctrl+C to stop.
echo.

cd ..\backend
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
