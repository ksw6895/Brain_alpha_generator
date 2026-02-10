#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="${PYTHONPATH:-src}"

"$PYTHON_BIN" -m brain_agent.cli sync-metadata "$@"
