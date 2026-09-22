#!/usr/bin/env bash
# One-time setup for a container (a CodeSpace, or any Linux dev container).
#
# It installs both halves against SQLite, so a fresh container is a working
# install without installing anything else and without being configured.
# Everything here is idempotent: re-running it is safe, and a rebuild re-runs it.
#
# The instance it creates is yours alone. No API key is shipped, the secret is
# generated here, and the accounts below exist only inside this container.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend/cerebrumkit-vue"
PY="$BACKEND/venv/bin/python"

echo "==> Backend dependencies"
python3 -m venv "$BACKEND/venv"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r "$BACKEND/requirements.txt"

echo "==> Frontend dependencies"
npm install --prefix "$FRONTEND" --silent

if [ ! -f "$BACKEND/.env" ]; then
  echo "==> backend/.env"
  # SQLite, because this container is for looking around, not for deploying.
  # The SEED_* values decide the logins for this instance only - the file is
  # gitignored, and the password is not a secret on a machine that only you
  # can reach. DEEPSEEK_API_KEY is taken from the environment, so a CodeSpace
  # secret of that name is picked up; leave it empty and both panels still
  # work, the agents simply have no model to answer with until you add a key
  # in Admin -> Settings -> LLM Connections.
  cat > "$BACKEND/.env" <<ENV
DATABASE_URL=sqlite:///./cerebrumkit.db
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}
DEEPSEEK_MODEL=${DEEPSEEK_MODEL:-deepseek-chat}
DEEPSEEK_BASE_URL=${DEEPSEEK_BASE_URL:-https://api.deepseek.com/v1}
SEED_ADMIN_EMAIL=admin@cerebrumkit.test
SEED_CLIENT_EMAIL=client@cerebrumkit.test
SEED_PASSWORD=cerebrumkit-demo-password
SEED_ADMIN_COUNTRY=CN
SEED_CLIENT_COUNTRY=CN
ENV
fi

echo "==> Seeding the database (idempotent)"
cd "$BACKEND"
"$PY" seed_all.py

echo
echo "==> Setup finished. The servers start with the container:"
echo "    bash .devcontainer/start.sh"