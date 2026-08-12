#!/usr/bin/env bash
set -euo pipefail

install_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
launch_after_install=1

if [[ "${1:-}" == "--no-launch" ]]; then
  launch_after_install=0
elif [[ $# -gt 0 ]]; then
  echo "Usage: ./install.sh [--no-launch]" >&2
  exit 2
fi

find_python() {
  local candidate
  for candidate in python3.13 python3.12 python3.11 python3; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>/dev/null; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

python_executable="$(find_python || true)"
if [[ -z "$python_executable" ]]; then
  echo "Delta Loop needs Python 3.11 or newer." >&2
  echo "Install a current Python from https://www.python.org/downloads/ and run this command again." >&2
  exit 1
fi

echo "Installing Delta Loop…"
"$python_executable" -m venv "$install_root/.venv"
"$install_root/.venv/bin/python" -m pip install --quiet --disable-pip-version-check -e "$install_root"

if [[ ! -f "$install_root/web/dist/index.html" ]]; then
  node_major="$(node -p "process.versions.node.split('.')[0]" 2>/dev/null || true)"
  if [[ -z "$node_major" || "$node_major" -lt 20 ]]; then
    echo "The ready-made web interface is missing, so rebuilding it needs Node.js 20 or newer." >&2
    echo "Download a complete Delta Loop release or install Node.js from https://nodejs.org/." >&2
    exit 1
  fi
  npm --prefix "$install_root/web" ci
  npm --prefix "$install_root/web" run build
fi

command_directory="${HOME}/.local/bin"
mkdir -p "$command_directory"
ln -sfn "$install_root/.venv/bin/delta-loop" "$command_directory/delta-loop"
ln -sfn "$install_root/.venv/bin/delta" "$command_directory/delta"

echo
echo "Delta Loop is installed."
echo "To open it later, run:"
echo "  $command_directory/delta-loop"
if [[ ":${PATH}:" != *":${command_directory}:"* ]]; then
  echo
  echo "Optional: add $command_directory to PATH so you can run 'delta-loop' from anywhere."
fi

if [[ "$launch_after_install" -eq 1 ]]; then
  echo
  exec "$install_root/.venv/bin/delta-loop"
fi
