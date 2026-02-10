#!/usr/bin/env bash
set -euo pipefail

# Example cron entry:
# 15 2 * * * cd /path/to/repo && bash scripts/cron_pipeline.sh >> data/logs/cron.log 2>&1

mkdir -p data/logs

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[$TS] sync-options"
bash scripts/sync_options.sh

echo "[$TS] sync-metadata"
bash scripts/sync_metadata.sh --skip-fields
