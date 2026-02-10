#!/usr/bin/env bash
set -euo pipefail

CRED_PATH="${1:-$HOME/.brain_credentials}"

# Preferred variable names
if [[ -z "${BRAIN_CREDENTIAL_EMAIL:-}" && -n "${BRAIN_EMAIL:-}" ]]; then
  BRAIN_CREDENTIAL_EMAIL="$BRAIN_EMAIL"
fi
if [[ -z "${BRAIN_CREDENTIAL_PASSWORD:-}" && -n "${BRAIN_PASSWORD:-}" ]]; then
  BRAIN_CREDENTIAL_PASSWORD="$BRAIN_PASSWORD"
fi

if [[ -z "${BRAIN_CREDENTIAL_EMAIL:-}" ]]; then
  read -r -p "Email: " BRAIN_CREDENTIAL_EMAIL
fi

if [[ -z "${BRAIN_CREDENTIAL_PASSWORD:-}" ]]; then
  read -r -s -p "Password: " BRAIN_CREDENTIAL_PASSWORD
  echo
fi

mkdir -p "$(dirname "$CRED_PATH")"
printf '["%s", "%s"]\n' "$BRAIN_CREDENTIAL_EMAIL" "$BRAIN_CREDENTIAL_PASSWORD" > "$CRED_PATH"
chmod 600 "$CRED_PATH"

echo "Saved credentials to $CRED_PATH with 600 permissions"
