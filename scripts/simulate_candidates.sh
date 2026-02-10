#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <candidate_json_list_path> [output_path]"
  exit 1
fi

INPUT_PATH="$1"
OUTPUT_PATH="${2:-data/simulation_results/latest.json}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="${PYTHONPATH:-src}"

"$PYTHON_BIN" -m brain_agent.cli simulate-candidates --input "$INPUT_PATH" --output "$OUTPUT_PATH"
