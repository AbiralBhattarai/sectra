#!/usr/bin/env bash
# Usage: scripts/make_migration.sh "add videos table"
set -euo pipefail
cd "$(dirname "$0")/.."
uv run alembic revision --autogenerate -m "$1"
