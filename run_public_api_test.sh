#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

export VIDEOGET_HOST="${VIDEOGET_HOST:-0.0.0.0}"
export VIDEOGET_PORT="${VIDEOGET_PORT:-8787}"
export VIDEOGET_DOWNLOAD_DIR="${VIDEOGET_DOWNLOAD_DIR:-$(pwd)/processing_storage}"
export VIDEOGET_CHROME_EXE="${VIDEOGET_CHROME_EXE:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
export VIDEOGET_CHROME_PROFILE_DIR="${VIDEOGET_CHROME_PROFILE_DIR:-$(pwd)/chrome_profile}"
export VIDEOGET_ALLOWED_ORIGINS="${VIDEOGET_ALLOWED_ORIGINS:-*}"

if [ -z "${VIDEOGET_API_TOKEN:-}" ]; then
  export VIDEOGET_API_TOKEN="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
fi

mkdir -p .runtime
printf "%s\n" "$VIDEOGET_API_TOKEN" > .runtime/api_token.txt

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
if [ -z "$LAN_IP" ]; then
  LAN_IP="$(ipconfig getifaddr en1 2>/dev/null || true)"
fi

echo "Starting VideoGet public API test server..."
echo "Local API: http://127.0.0.1:${VIDEOGET_PORT}"
if [ -n "$LAN_IP" ]; then
  echo "LAN API:   http://${LAN_IP}:${VIDEOGET_PORT}"
fi
echo "API token: ${VIDEOGET_API_TOKEN}"
echo
echo "Public FE example:"
echo "https://your-frontend-domain/?api=https://your-public-api-domain&token=${VIDEOGET_API_TOKEN}"
echo
echo "Do not expose this permanently without a real reverse proxy, HTTPS, and stronger auth."

if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python web_downloader_app.py
fi

exec python3 web_downloader_app.py
