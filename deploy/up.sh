#!/usr/bin/env bash
# Build and start the stack, then provision the CRM. Safe to re-run: this is
# the deploy command as well as the first-boot command.
#
#   bash deploy/up.sh          from the repo root
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="deploy/.env.production"
COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file $ENV_FILE"

[ -f "$ENV_FILE" ] || {
  echo "Missing $ENV_FILE - copy deploy/.env.production.example and fill it in." >&2
  exit 1
}

# Fail loudly now rather than half-way through a five-minute build.
for required in ARIA_DOMAIN ARIA_CRM_DOMAIN MARIADB_ROOT_PASSWORD MARIADB_PASSWORD ESPOCRM_ADMIN_PASSWORD; do
  value="$(grep -E "^${required}=" "$ENV_FILE" | cut -d= -f2-)"
  [ -n "$value" ] || { echo "$required is empty in $ENV_FILE" >&2; exit 1; }
done

echo "==> Building and starting"
$COMPOSE up -d --build

echo "==> Waiting for the backend to answer /healthz"
for _ in $(seq 1 60); do
  if $COMPOSE exec -T backend curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    echo "    up"
    break
  fi
  sleep 2
done

echo "==> Waiting for EspoCRM to finish installing (first boot takes a minute)"
for _ in $(seq 1 90); do
  code="$($COMPOSE exec -T espocrm curl -s -o /dev/null -w '%{http_code}' http://localhost/api/v1/App/user || true)"
  # 401 means it is serving and asking for credentials, which is what we want.
  [ "$code" = "401" ] && { echo "    up"; break; }
  sleep 2
done

cat <<NEXT

  Stack is up. Provision the CRM (entity, fields, layouts, role, API user).
  Run it on the HOST, not in a container - it installs Espo layouts with
  \`docker cp\` and so needs the Docker socket. Espo is on 127.0.0.1:8080
  for exactly this:

    set -a; . $ENV_FILE; set +a
    ESPOCRM_BASE_URL=http://localhost:8080 python3 scripts/provision_crm.py

  It prints ESPOCRM_API_KEY and ESPOCRM_ASSIGNED_USER_ID. Put both into
  $ENV_FILE, then restart the backend so it picks them up:

    docker compose -f deploy/docker-compose.prod.yml --env-file $ENV_FILE \
      up -d backend

NEXT
