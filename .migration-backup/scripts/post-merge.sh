#!/usr/bin/env bash
set -euo pipefail

# Reconcile locked Python dependencies into Replit's existing interpreter.
# Do not create a virtual environment or remove unrelated installed packages.
uv export --frozen --no-dev --no-emit-project --format requirements-txt \
  | uv pip install --python "$(command -v python)" -r -