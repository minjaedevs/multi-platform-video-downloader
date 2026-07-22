#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p docs
cp web_static/index.html docs/index.html
cp web_static/client.js docs/client.js
cp web_static/styles.css docs/styles.css
echo "Synced client files from web_static to docs"
