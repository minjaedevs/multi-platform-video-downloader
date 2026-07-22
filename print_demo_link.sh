#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

mkdir -p .runtime

url=""
token=""

if [ -f ".runtime/ngrok_url.txt" ]; then
  url="$(tr -d '\r\n' < .runtime/ngrok_url.txt)"
fi

if [ -f ".runtime/api_token.txt" ]; then
  token="$(tr -d '\r\n' < .runtime/api_token.txt)"
fi

if [ -z "$url" ] && command -v curl >/dev/null 2>&1; then
  url="$(curl -fsS --max-time 3 http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c 'import json,sys; data=json.load(sys.stdin); print(next((t.get("public_url","") for t in data.get("tunnels",[]) if t.get("proto")=="https"), ""))' || true)"
  if [ -n "$url" ]; then
    printf "%s\n" "$url" > .runtime/ngrok_url.txt
  fi
fi

if [ -z "$token" ]; then
  echo "Missing .runtime/api_token.txt. Run backend first:"
  echo "  ./run_public_api_test.sh"
  exit 1
fi

if [ -z "$url" ]; then
  echo "Missing ngrok public URL. Run ngrok in another terminal first:"
  echo "  ./run_ngrok_8787.sh"
  echo
  echo "If ngrok is already open, wait a few seconds then run this command again."
  exit 1
fi

echo
echo "Client demo link:"
echo "https://minjaedevs.github.io/multi-platform-video-downloader/?api=${url}&token=${token}"
echo
echo "API:"
echo "$url"
echo
echo "Admin local:"
echo "http://127.0.0.1:8787/admin"
