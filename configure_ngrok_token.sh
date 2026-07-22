#!/usr/bin/env bash
set -euo pipefail

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok not found. Install it first:"
  echo "  brew install ngrok"
  exit 1
fi

printf "Paste your ngrok authtoken: "
read -r NGROK_TOKEN
ngrok config add-authtoken "$NGROK_TOKEN"
unset NGROK_TOKEN
echo "ngrok authtoken configured."
