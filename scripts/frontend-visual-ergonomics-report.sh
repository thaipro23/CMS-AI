#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT_DIR="${1:-/tmp/frontend-visual-ergonomics}"
mkdir -p "$OUT_DIR"
PYTHONPATH=backend pytest -q backend/app/tests/test_v25_9_16_7_2_64_16_5_7_2_3_frontend_visual_ergonomics.py | tee "$OUT_DIR/tests.log"
echo 'READY — frontend visual ergonomics and navigation contracts passed.' | tee "$OUT_DIR/summary.txt"
