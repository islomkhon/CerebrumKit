#!/usr/bin/env bash
# Starts both halves of CerebrumKit and leaves them running in the background.
#
# `postStartCommand` runs this on every start and every resume, so it has to be
# safe to run twice: each server is started only when its port is still closed.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend/cerebrumkit-vue"
PY="$BACKEND/venv/bin/python"
LOGS="${TMPDIR:-/tmp}"

port_open() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# A CodeSpace is reached through a forwarded hostname that is assigned when the
# container starts. It is not localhost and it is not in the repository, and
# VITE_API_URL is read by the REST client and by the chat websocket both, so the
# backend origin has to be derived here rather than written into the source.
#
# Vite refuses a request whose Host header it has not been told about, and the
# browser will send the forwarded hostname, so that name goes in too.
FORWARDED_DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}"
CODESPACE="${CODESPACE_NAME:-}"

if [ -n "$CODESPACE" ] && [ -n "$FORWARDED_DOMAIN" ]; then
  API_ORIGIN="https://${CODESPACE}-8000.${FORWARDED_DOMAIN}"
  PANEL_ORIGIN="https://${CODESPACE}-5173.${FORWARDED_DOMAIN}"
  CORS_ORIGIN_REGEX="https://.*[.]${FORWARDED_DOMAIN}"
  printf 'VITE_API_URL=%s\nVITE_ALLOWED_HOSTS=.%s\n' "$API_ORIGIN" "$FORWARDED_DOMAIN" > "$FRONTEND/.env"
else
  API_ORIGIN="http://localhost:8000"
  PANEL_ORIGIN="http://localhost:5173"
  CORS_ORIGIN_REGEX=""
  printf 'VITE_API_URL=%s\n' "$API_ORIGIN" > "$FRONTEND/.env"
fi

# ── Backend ──
if port_open 8000; then
  echo "[=] Backend already listening on 8000"
else
  echo "[+] Starting the backend on 8000"
  cd "$BACKEND" || exit 1
  CORS_ORIGIN_REGEX="$CORS_ORIGIN_REGEX" PYTHONUNBUFFERED=1 \
    nohup "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    >> "$LOGS/cerebrumkit-backend.log" 2>&1 &
fi

# ── Frontend ──
# --strictPort so a taken port fails loudly instead of moving to 5174, which is
# not the port that gets forwarded and would look like a broken panel.
if port_open 5173; then
  echo "[=] Frontend already listening on 5173"
else
  echo "[+] Starting the frontend on 5173"
  cd "$FRONTEND" || exit 1
  nohup npm run dev -- --host 0.0.0.0 --port 5173 --strictPort \
    >> "$LOGS/cerebrumkit-frontend.log" 2>&1 &
fi

# Wait for the backend to answer before printing an address nobody can use yet.
for _ in $(seq 1 30); do
  port_open 5173 && port_open 8000 && break
  sleep 1
done

cat <<MSG

  CerebrumKit
    Panel      $PANEL_ORIGIN
    API docs   $API_ORIGIN/docs
    Sign in    admin@cerebrumkit.test  /  cerebrumkit-demo-password
               client@cerebrumkit.test /  cerebrumkit-demo-password

    Logs       $LOGS/cerebrumkit-backend.log
               $LOGS/cerebrumkit-frontend.log
    Restart    bash .devcontainer/start.sh

  The agents answer only once an LLM connection exists. Add a key in
  Admin -> Settings -> LLM Connections, or set a CodeSpace secret named
  DEEPSEEK_API_KEY and rebuild. Everything else works without one.
MSG