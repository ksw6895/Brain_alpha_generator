#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-$HOME/wqbrain-agent}"

mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip wheel setuptools
