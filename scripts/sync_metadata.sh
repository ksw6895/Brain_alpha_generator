#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="${PYTHONPATH:-src}"
INTERACTIVE_LOGIN="${BRAIN_INTERACTIVE_LOGIN:-1}"
MAX_FIELD_DATASETS="${BRAIN_MAX_FIELD_DATASETS:-0}"
WAIT_ON_RATE_LIMIT="${BRAIN_WAIT_ON_RATE_LIMIT:-1}"

EXTRA_ARGS=()
if [[ "$INTERACTIVE_LOGIN" == "1" ]]; then
  EXTRA_ARGS+=(--interactive-login)
fi

if [[ "$WAIT_ON_RATE_LIMIT" != "1" ]]; then
  EXTRA_ARGS+=(--no-wait-on-rate-limit)
fi

"$PYTHON_BIN" -m brain_agent.cli sync-metadata "${EXTRA_ARGS[@]}" --max-field-datasets "$MAX_FIELD_DATASETS" "$@"
