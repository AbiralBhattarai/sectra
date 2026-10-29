#!/usr/bin/env bash
# Usage: scripts/rollback_migration.sh [steps]   (default 1)
set -euo pipefail
cd "$(dirname "$0")/.."
uv run alembic downgrade "-${1:-1}"
