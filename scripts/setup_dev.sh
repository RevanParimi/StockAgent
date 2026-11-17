#!/usr/bin/env bash
# Prepare a checkout for a "continue" session on any device: the Python packages the suite
# and the docs check need, and the Node packages and Chromium that the screen tests and the
# PDF build need.
#
#   bash scripts/setup_dev.sh --check   # say what is missing; install nothing
#   bash scripts/setup_dev.sh           # install what is missing, then check again
#
# AGENTS.md runs the check at the start of every "continue". This script installs only what
# the repository declares (requirements.txt, requirements-test.txt,
# scripts/docs/requirements.txt, package-lock.json) into ignored folders: the laptop's
# .stockai or a new .venv, and node_modules. It never reads or writes .env, never touches
# production and never changes git state. The suite itself needs no .env and no network
# (tests/hermetic.py).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

MODE=install
case "${1:-}" in
  --check) MODE=check ;;
  "") ;;
  *) echo "usage: bash scripts/setup_dev.sh [--check]" >&2; exit 2 ;;
esac

REQS=(-r requirements.txt -r requirements-test.txt -r scripts/docs/requirements.txt)
CHROMIUM_JS='const fs = require("fs"); process.exit(fs.existsSync(require("playwright").chromium.executablePath()) ? 0 : 1)'
MISSING=0
LOCK=""
say() { printf '%s\n' "$*"; }
release_lock() { [ -n "$LOCK" ] && rmdir "$LOCK" 2>/dev/null; return 0; }
trap release_lock EXIT

venv_python() {   # the checkout's own interpreter: the laptop's .stockai, else .venv
  local d p
  for d in .stockai .venv; do
    for p in "$d/bin/python" "$d/Scripts/python.exe"; do
      [ -x "$p" ] && { printf '%s\n' "$p"; return 0; }
    done
  done
  return 1
}

base_python() {   # the oldest Python from 3.11 up (CI and production use 3.11); prints its path
  local v c exe
  for v in 3.11 3.12 3.13 3.14; do
    for c in "python$v" "py -$v"; do   # "py" is the Windows launcher
      # shellcheck disable=SC2086  # $c is a command and its argument
      exe="$($c -c 'import sys; print(sys.executable)' 2>/dev/null)" && [ -n "$exe" ] &&
        { printf '%s\n' "$exe"; return 0; }
    done
  done
  for c in python3 python; do
    exe="$("$c" -c 'import sys; assert sys.version_info >= (3, 11); print(sys.executable)' 2>/dev/null)" &&
      [ -n "$exe" ] && { printf '%s\n' "$exe"; return 0; }
  done
  return 1
}

pending_packages() {   # what pip would still install, one "name==version" per line; "?" if pip cannot tell
  local report
  report="$(git rev-parse --git-dir)/setup_dev_report.json"   # inside .git: never committed
  if "$1" -m pip install --dry-run --quiet --disable-pip-version-check --report "$report" \
       "${REQS[@]}" >/dev/null 2>&1; then
    "$1" -I -c 'import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
for item in report.get("install", []):
    print(item["metadata"]["name"] + "==" + item["metadata"]["version"])' "$report"
  else
    echo "?"
  fi
  rm -f "$report"
}

check() {
  local py pending
  if py="$(venv_python)"; then
    pending="$(pending_packages "$py")"
    if [ -n "$pending" ]; then
      say "missing: Python packages for $py: $(printf '%s' "$pending" | tr '\n' ' ')"
      MISSING=1
    fi
  else
    say "missing: a Python environment (.venv)"
    MISSING=1
  fi
  if ! command -v npm >/dev/null 2>&1; then
    say "note: Node.js is not installed, so npm run test:frontend and the PDF build cannot run here"
  elif ! npm ls --depth=0 >/dev/null 2>&1; then
    say "missing: Node packages (npm ci)"
    MISSING=1
  elif ! node -e "$CHROMIUM_JS" >/dev/null 2>&1; then
    say "missing: Playwright's Chromium"
    MISSING=1
  fi
}

install() {
  local py base lock_path
  lock_path="$(git rev-parse --git-dir)/setup_dev.lock"
  mkdir "$lock_path" 2>/dev/null || {
    echo "another setup is running in this checkout (remove $lock_path if it is stale)" >&2
    exit 2
  }
  LOCK="$lock_path"
  if ! py="$(venv_python)"; then
    base="$(base_python)" || { echo "need Python 3.11 or newer on PATH" >&2; exit 1; }
    say "creating .venv with $("$base" --version 2>&1)"
    "$base" -m venv .venv
    py="$(venv_python)"
  fi
  if [ -n "$(pending_packages "$py")" ]; then
    say "installing Python packages into $py (a few minutes on a new device)"
    "$py" -m pip install --quiet --disable-pip-version-check "${REQS[@]}"
  fi
  if command -v npm >/dev/null 2>&1; then
    if ! npm ls --depth=0 >/dev/null 2>&1; then
      say "installing Node packages (npm ci)"
      npm ci --no-audit --no-fund --loglevel=error
    fi
    if ! node -e "$CHROMIUM_JS" >/dev/null 2>&1; then
      say "installing Playwright's Chromium"
      if [ "$(id -u 2>/dev/null || echo 1)" = 0 ]; then
        npx playwright install --with-deps chromium || npx playwright install chromium
      else
        npx playwright install chromium
      fi
    fi
  fi
}

[ "$MODE" = install ] && install
check
if [ "$MISSING" = 0 ]; then
  py="$(venv_python)"
  say "READY: $("$py" --version 2>&1) at $py. Tests: $py -m pytest -q"
else
  [ "$MODE" = check ] && say "run: bash scripts/setup_dev.sh"
  exit 1
fi
