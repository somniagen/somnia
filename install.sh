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

build_web() (
  cd web
  # node_modules copied from another os has the wrong native binaries (rollup, esbuild)
  plat=$(node -p 'process.platform + "-" + process.arch')
  if [ -d node_modules ] && [ "$(cat node_modules/.somnia-platform 2>/dev/null)" != "$plat" ]; then
    echo "removing node_modules installed for another platform..."
    rm -rf node_modules
  fi
  # drives without symlink support (ntfs/exfat mounts, some shares) break npm's .bin links
  links=""
  if ! ln -s package.json .somnia-link-test 2>/dev/null; then
    links="--no-bin-links"
  fi
  rm -f .somnia-link-test
  # no lifecycle scripts: none are needed (esbuild/rollup ship prebuilt binaries) and they fail on noexec or
  # permission restricted drives; the native binaries just need their exec bit back
  npm ci --no-audit --no-fund --ignore-scripts $links ||
    { rm -rf node_modules && npm install --no-audit --no-fund --ignore-scripts $links; } || return 1
  chmod +x node_modules/@esbuild/*/bin/esbuild node_modules/esbuild/bin/esbuild 2>/dev/null || true
  echo "$plat" > node_modules/.somnia-platform
  node node_modules/vite/bin/vite.js build
)

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
    command -v node >/dev/null 2>&1 || fail "node not found, install Node.js LTS (20.19+): https://nodejs.org"
    command -v npm >/dev/null 2>&1 || fail "npm not found, install Node.js LTS: https://nodejs.org"
    node -e 'const [a, b] = process.versions.node.split(".").map(Number); process.exit(a > 22 || (a === 22 && b >= 12) || (a === 20 && b >= 19) ? 0 : 1)' ||
      fail "Node.js $(node -v) is too old, the frontend needs 20.19+ or 22.12+: https://nodejs.org"
    echo "building frontend..."
    build_web || fail "frontend build failed"
  fi
else
  echo "frontend up to date"
fi

if [ "$check" -eq 1 ]; then
  echo "[check] would prefetch the danbooru tag list"
else
  echo "prefetching small assets..."
  .venv/bin/python -c "import sys; sys.path.insert(0, 'backend'); from somnia import tags; tags.download_csv()" || echo "warning: asset prefetch failed, continuing"
fi

echo
if [ "$check" -eq 1 ]; then
  echo "[check] done, nothing was changed"
else
  echo "Done. Start Somnia with ./run.sh"
fi
