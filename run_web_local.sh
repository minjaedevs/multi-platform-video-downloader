#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
exec ./run_public_api_test.sh
