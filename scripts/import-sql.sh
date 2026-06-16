#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: scripts/import-sql.sh <path-to-sql-or-sql.gz>" >&2
  exit 2
fi

input_file="$1"

if [ ! -f "$input_file" ]; then
  echo "Import file not found: $input_file" >&2
  exit 2
fi

case "$input_file" in
  *.gz)
    gzip -dc "$input_file" | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U home_search -d home_search
    ;;
  *)
    docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U home_search -d home_search < "$input_file"
    ;;
esac
