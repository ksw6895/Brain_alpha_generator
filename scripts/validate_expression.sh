#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 '<FASTEXPR>'"
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="${PYTHONPATH:-src}"

"$PYTHON_BIN" -m brain_agent.cli validate-expression "$1"
