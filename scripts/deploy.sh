#!/usr/bin/env bash
# =============================================================================
# MuniRev -- Production deployment script for Hetzner VPS
# =============================================================================
#
# Usage:
#   ./scripts/deploy.sh <ssh-target>
#
# Example:
#   ./scripts/deploy.sh root@203.0.113.42
#   ./scripts/deploy.sh deploy@munirev.example.com
#
# Prerequisites on the server:
#   - Docker Engine and Docker Compose v2 installed
#   - Git installed
#   - Repository cloned to /opt/munirevenue
#   - deploy/hetzner/.env.hetzner populated
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REMOTE="${1:?Usage: $0 <ssh-target>}"
DEPLOY_DIR="/opt/munirevenue"
COMPOSE="docker compose --env-file ${DEPLOY_DIR}/deploy/hetzner/.env.hetzner -f ${DEPLOY_DIR}/deploy/hetzner/docker-compose.yml"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m[deploy]\033[0m %s\n' "$*"; }
err()   { printf '\033[1;31m[deploy]\033[0m %s\n' "$*" >&2; }

remote_exec() {
    ssh -o StrictHostKeyChecking=accept-new "${REMOTE}" "$@"
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
info "Running pre-flight checks on ${REMOTE} ..."

remote_exec bash -s <<'PREFLIGHT'
set -euo pipefail
command -v docker   >/dev/null 2>&1 || { echo "ERROR: docker not found";   exit 1; }
command -v git      >/dev/null 2>&1 || { echo "ERROR: git not found";      exit 1; }
docker compose version >/dev/null 2>&1 || { echo "ERROR: docker compose v2 not found"; exit 1; }
PREFLIGHT

ok "Pre-flight checks passed."

# ---------------------------------------------------------------------------
# Pull latest code
# ---------------------------------------------------------------------------
info "Pulling latest code ..."
remote_exec bash -s <<PULL
set -euo pipefail
cd ${DEPLOY_DIR}
git fetch --all --prune
git reset --hard origin/main
if [ ! -f deploy/hetzner/.env.hetzner ] && [ -f .env ]; then
    cp .env deploy/hetzner/.env.hetzner
fi
PULL

ok "Code updated."

# ---------------------------------------------------------------------------
# Build and start services
# ---------------------------------------------------------------------------
info "Building and starting services ..."
remote_exec bash -s <<BUILD
set -euo pipefail
cd ${DEPLOY_DIR}
${COMPOSE} pull postgres caddy
${COMPOSE} build --no-cache app
${COMPOSE} up -d --remove-orphans
BUILD

ok "Services started."

# ---------------------------------------------------------------------------
# Run database migrations (placeholder)
# ---------------------------------------------------------------------------
info "Running database migrations ..."
remote_exec bash -s <<MIGRATE
set -euo pipefail
cd ${DEPLOY_DIR}
# Uncomment once Alembic is wired up:
# ${COMPOSE} exec -T app alembic upgrade head
echo "  (no migrations configured yet -- skipping)"
MIGRATE

ok "Migrations complete."

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
info "Running health check ..."

MAX_ATTEMPTS=12
SLEEP_SECONDS=5

remote_exec bash -s <<HEALTH
set -euo pipefail
attempt=1
while [ \$attempt -le ${MAX_ATTEMPTS} ]; do
    if curl -sf http://localhost/api/health >/dev/null 2>&1; then
        echo "Health check passed on attempt \$attempt."
        exit 0
    fi
    echo "  Attempt \$attempt/${MAX_ATTEMPTS} failed -- retrying in ${SLEEP_SECONDS}s ..."
    sleep ${SLEEP_SECONDS}
    attempt=\$((attempt + 1))
done
echo "ERROR: Health check failed after ${MAX_ATTEMPTS} attempts."
${COMPOSE} logs --tail=50
exit 1
HEALTH

ok "Deployment to ${REMOTE} completed successfully."
