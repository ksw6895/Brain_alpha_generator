#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="${PYTHONPATH:-src}"
INTERACTIVE_LOGIN="${BRAIN_INTERACTIVE_LOGIN:-1}"

EXTRA_ARGS=()
if [[ "$INTERACTIVE_LOGIN" == "1" ]]; then
  EXTRA_ARGS+=(--interactive-login)
fi

"$PYTHON_BIN" -m brain_agent.cli sync-metadata "${EXTRA_ARGS[@]}" "$@"
