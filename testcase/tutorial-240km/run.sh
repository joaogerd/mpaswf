#!/usr/bin/env bash
# Reproduce the historic MPAS-JEDI/NMC forecast case on an installed JACI runtime.
set -euo pipefail
CASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${MPASWF_CASE_CONFIG:-$CASE_DIR/jaci.yaml}"
COMMAND="${1:-check}"
case "$COMMAND" in
  check)
    exec mpaswf check-config --config "$CONFIG"
    ;;
  run)
    mpaswf check-config --config "$CONFIG"
    mpaswf run --phase prepare --config "$CONFIG"
    mpaswf run --phase init --config "$CONFIG" --submit --wait
    mpaswf run --phase forecast --config "$CONFIG" --submit --wait
    mpaswf run --phase manifest --config "$CONFIG"
    ;;
  manifest)
    exec mpaswf run --phase manifest --config "$CONFIG"
    ;;
  *)
    echo "Usage: bash testcase/tutorial-240km/run.sh [check|run|manifest]" >&2
    exit 2
    ;;
esac
