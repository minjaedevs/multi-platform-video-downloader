#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok not found. Install it first:"
  echo "  brew install ngrok"
  exit 1
fi

mkdir -p .runtime logs

echo "Starting ngrok tunnel for VideoGet API..."
echo "Local API: http://127.0.0.1:8787"
echo "Dashboard: http://127.0.0.1:4040"
echo

ngrok http 8787 2>&1 | while IFS= read -r line; do
  printf "%s\n" "$line"
  printf "%s\n" "$line" >> logs/ngrok.out.log
  url="$(printf "%s\n" "$line" | grep -Eo 'https://[a-zA-Z0-9.-]+\.ngrok(-free)?\.(app|dev)' | head -n 1 || true)"
  if [ -n "$url" ]; then
    printf "%s\n" "$url" > .runtime/ngrok_url.txt
  fi
done
