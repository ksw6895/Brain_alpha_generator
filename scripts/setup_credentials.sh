#!/usr/bin/env bash
set -euo pipefail

CRED_PATH="${1:-$HOME/.brain_credentials}"

if [[ -z "${BRAIN_EMAIL:-}" ]]; then
  read -r -p "Email: " BRAIN_EMAIL
fi

if [[ -z "${BRAIN_PASSWORD:-}" ]]; then
  read -r -s -p "Password: " BRAIN_PASSWORD
  echo
fi

mkdir -p "$(dirname "$CRED_PATH")"
printf '["%s", "%s"]\n' "$BRAIN_EMAIL" "$BRAIN_PASSWORD" > "$CRED_PATH"
chmod 600 "$CRED_PATH"

echo "Saved credentials to $CRED_PATH with 600 permissions"
