#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
uv export --frozen --no-dev --no-emit-project --format requirements-txt \
  | uv pip install --python "$(command -v python3)" -r -
pnpm --filter @workspace/git-civic run build:auth