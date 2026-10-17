#!/bin/sh
set -eu
cd "$(dirname "$0")"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

if [ ! -x .venv/bin/python ]; then
  ./install.sh || exit 1
fi

command -v uv >/dev/null 2>&1 || { echo "uv not found, run ./install.sh" >&2; exit 1; }

export PYTHONPATH=backend
url=http://127.0.0.1:7865
(
  sleep 4
  if command -v open >/dev/null 2>&1; then
    open "$url"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url"
  fi
) >/dev/null 2>&1 &

exec uv run --no-sync python -m somnia "$@"
