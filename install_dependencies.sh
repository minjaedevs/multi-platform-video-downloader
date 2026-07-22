#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_EXE="${PYTHON_EXE:-python3}"

if [ ! -d ".venv" ]; then
  "$PYTHON_EXE" -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt aiohttp

echo "Dependencies installed in .venv"
