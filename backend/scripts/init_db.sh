#!/usr/bin/env bash
# Initialize the platform database: create it when missing, then run the migrations.
#
# Usage:
#   ./scripts/init_db.sh                      # create database if needed + upgrade head
#   ./scripts/init_db.sh --create-db          # only create the database
#   ./scripts/init_db.sh --reset              # downgrade base, then upgrade head
#   ./scripts/init_db.sh --revision 0001      # upgrade to a specific revision
#
# The DSN comes from the environment (.env / POSTGRES_*), never from a literal
# in this script.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
cd "$BACKEND_DIR"

PYTHON_BIN="${PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$BACKEND_DIR/.venv/Scripts/python.exe" ]; then
    PYTHON_BIN="$BACKEND_DIR/.venv/Scripts/python.exe"
  elif [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"
  else
    PYTHON_BIN="python"
  fi
fi
exec "$PYTHON_BIN" scripts/init_db.py "$@"
