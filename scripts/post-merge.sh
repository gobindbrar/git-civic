#!/bin/bash
set -euo pipefail
pnpm install --frozen-lockfile
bash artifacts/git-civic/install-deps.sh
