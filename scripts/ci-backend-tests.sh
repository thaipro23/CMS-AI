#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT_DIR/backend"
pytest -q \
  app/tests/test_v25_9_16_7_2_64_16_5_4_production_security_closure.py \
  app/tests/test_v25_9_16_7_2_64_16_5_5_performance_worker_reliability.py \
  app/tests/test_v25_9_16_7_2_64_16_5_7_release_contract.py
pytest -q app/tests/test_v25_9_16_7_2_64_16_5_6_release_contract.py -k 'not version_is_synchronized_across_runtime_artifacts'
pytest -q -m integration app/tests/integration
