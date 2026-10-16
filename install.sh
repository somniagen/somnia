#!/bin/sh
set -eu
cd "$(dirname "$0")"

check=0
case "${1:-}" in
  --check) check=1 ;;
  -h|--help)
    echo "usage: ./install.sh [--check]"
    echo "  --check  show what would be done, change nothing"
    exit 0
    ;;
  "") ;;
  *) echo "unknown option: $1" >&2; exit 1 ;;
esac

fail() {
  echo "error: $*" >&2
  exit 1
}

run() {
  if [ "$check" -eq 1 ]; then
    echo "[check] would run: $*"
  else
    "$@"
  fi
}

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export UV_PYTHON_PREFERENCE=only-managed

echo "Somnia install"
[ "$check" -eq 1 ] && echo "[check] dry run, nothing will be changed"

if ! command -v uv >/dev/null 2>&1; then
  if [ "$check" -eq 1 ]; then
    echo "[check] uv missing, would install it from astral.sh"
  else
    echo "installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh || fail "could not install uv, see https://docs.astral.sh/uv/"
    command -v uv >/dev/null 2>&1 || fail "uv not found after install, see https://docs.astral.sh/uv/"
  fi
fi

if [ "$check" -eq 0 ]; then
  echo "installing python 3.12..."
  uv python install 3.12 || fail "could not install python 3.12"
else
  echo "[check] would run: uv python install 3.12"
fi

sync_args=""
if [ "$(uname -s)" = "Linux" ] && command -v nvidia-smi >/dev/null 2>&1; then
  :
else
  sync_args="--no-sources"
  echo "no nvidia gpu detected, torch comes from pypi (cu128 index skipped)"
fi

echo "installing python packages..."
if [ "$check" -eq 0 ]; then
  uv sync $sync_args || fail "uv sync failed"
else
  echo "[check] would run: uv sync $sync_args"
fi

need_web=0
if [ ! -f web/dist/index.html ]; then
  need_web=1
elif [ -n "$(find web/src web/index.html web/package.json -newer web/dist/index.html 2>/dev/null | head -n 1)" ]; then
  need_web=1
fi

if [ "$need_web" -eq 1 ]; then
  if [ "$check" -eq 1 ]; then
    echo "[check] would build the frontend in web/"
  else
    command -v npm >/dev/null 2>&1 || fail "npm not found, install Node.js LTS: https://nodejs.org"
    echo "building frontend..."
    (cd web && { npm ci || npm install; } && npm run build) || fail "frontend build failed"
  fi
else
  echo "frontend up to date"
fi

if [ -f scripts/fetch_tags.py ]; then
  if [ "$check" -eq 1 ]; then
    echo "[check] would run: scripts/fetch_tags.py"
  else
    echo "prefetching small assets..."
    .venv/bin/python scripts/fetch_tags.py || echo "warning: asset prefetch failed, continuing"
  fi
fi

echo
if [ "$check" -eq 1 ]; then
  echo "[check] done, nothing was changed"
else
  echo "Done. Start Somnia with ./run.sh"
fi
