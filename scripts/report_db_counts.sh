#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${1:-data/brain_agent.db}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "DB not found: $DB_PATH"
  exit 1
fi

sqlite3 "$DB_PATH" <<'SQL'
.headers on
.mode column
SELECT 'operators' AS table_name, COUNT(*) AS row_count FROM operators;
SELECT 'datasets' AS table_name, COUNT(*) AS row_count FROM datasets;
SELECT 'data_fields' AS table_name, COUNT(*) AS row_count FROM data_fields;
SELECT 'alpha_results' AS table_name, COUNT(*) AS row_count FROM alpha_results;
SQL
