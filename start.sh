#!/usr/bin/env bash
# MuniRev - Local deployment
# Builds the frontend and starts the backend on port 8000.
# The backend serves the API and the built frontend from a single process.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing backend dependencies..."
cd "$SCRIPT_DIR/backend"
if [ ! -d .venv ]; then
  python -m venv .venv
fi
.venv/Scripts/pip install -q -r requirements.txt 2>/dev/null || .venv/bin/pip install -q -r requirements.txt

echo "Building frontend..."
cd "$SCRIPT_DIR/frontend"
npm install --silent
npm run build

echo ""
echo "Starting MuniRev on http://127.0.0.1:8000"
echo "Press Ctrl+C to stop."
echo ""

cd "$SCRIPT_DIR/backend"
.venv/Scripts/uvicorn app.main:app --host 127.0.0.1 --port 8000 2>/dev/null || .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
