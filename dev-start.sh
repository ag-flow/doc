#!/usr/bin/env bash
# Démarre (ou redémarre) les serveurs de dev locaux : backend FastAPI + frontend Vite.
# Config backend lue depuis backend/.env (gitignoré). Idempotent : coupe les
# instances déjà en écoute sur les ports avant de relancer.
#
#   ./dev-start.sh          # (re)démarre backend + frontend
#   ./dev-start.sh stop     # arrête les deux
#   ./dev-start.sh backend  # (re)démarre le backend seul
#   ./dev-start.sh frontend # (re)démarre le frontend seul
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
LOG_DIR="$ROOT/.dev-logs"
BACKEND_PORT=8000
FRONTEND_PORT=5173

mkdir -p "$LOG_DIR"

kill_port() {
  local port="$1" pids
  pids="$(ss -ltnpH "sport = :$port" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | sort -u || true)"
  if [ -n "$pids" ]; then
    echo "  arrêt du process sur :$port ($pids)"
    kill $pids 2>/dev/null || true
    sleep 2
  fi
}

wait_http() {
  local url="$1" label="$2" i
  for i in $(seq 1 30); do
    if [ "$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null)" = "200" ]; then
      echo "  ✅ $label prêt ($url)"
      return 0
    fi
    sleep 1
  done
  echo "  ❌ $label ne répond pas après 30s — voir $LOG_DIR"
  return 1
}

start_backend() {
  echo "› backend (FastAPI/uvicorn) :$BACKEND_PORT"
  kill_port "$BACKEND_PORT"
  [ -f "$BACKEND_DIR/.env" ] || { echo "  ❌ $BACKEND_DIR/.env absent"; exit 1; }
  # L'application ne lit aucun fichier de config : elle ne connaît que
  # l'environnement. C'est donc ici qu'on exporte backend/.env, et nulle part
  # ailleurs — ainsi un .env de dev ne peut pas fuiter dans les tests.
  ( cd "$BACKEND_DIR" \
      && set -a && . ./.env && set +a \
      && nohup .venv/bin/uvicorn docflow.app:app --reload \
           --host 0.0.0.0 --port "$BACKEND_PORT" > "$LOG_DIR/backend.log" 2>&1 & )
  wait_http "http://localhost:$BACKEND_PORT/health" "backend"
}

start_frontend() {
  echo "› frontend (Vite) :$FRONTEND_PORT"
  kill_port "$FRONTEND_PORT"
  ( cd "$FRONTEND_DIR" && nohup node node_modules/.bin/vite --host \
      > "$LOG_DIR/frontend.log" 2>&1 & )
  wait_http "http://localhost:$FRONTEND_PORT/" "frontend"
}

case "${1:-all}" in
  stop)     echo "arrêt des serveurs de dev"; kill_port "$BACKEND_PORT"; kill_port "$FRONTEND_PORT" ;;
  backend)  start_backend ;;
  frontend) start_frontend ;;
  all)      start_backend; start_frontend ;;
  *)        echo "usage: $0 [all|stop|backend|frontend]"; exit 2 ;;
esac
