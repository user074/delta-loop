#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ ! -x "$project_root/.venv/bin/delta" ]]; then
  echo "Missing .venv. Follow the setup steps in README.md first." >&2
  exit 1
fi

node_major="$(node -p "process.versions.node.split('.')[0]" 2>/dev/null || true)"
if [[ -z "$node_major" || "$node_major" -lt 20 ]]; then
  echo "Delta Loop needs Node.js 20 or newer. Activate a current Node.js version, then try again." >&2
  exit 1
fi

"$project_root/.venv/bin/delta" serve --host 127.0.0.1 --port 4318 &
api_pid=$!

cleanup() {
  kill "$api_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

npm --prefix "$project_root/web" run dev -- --host 127.0.0.1 --port 4317
