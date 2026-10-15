#!/bin/bash
# Facet launcher for macOS (started by Contents/MacOS/Facet): runs Facet from this source folder.
# First start: creates a private Python environment (.venv) and installs the dependencies (~1–2 minutes).
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"  # Facet.app/Contents/Resources → project folder
LOG="$HOME/Library/Logs/Facet-launcher.log"
cd "$ROOT" || exit 1

alert() {
  osascript -e "display alert \"Facet\" message \"$1\" as critical" >/dev/null 2>&1
}

if [ ! -x .venv/bin/python ]; then
  PY=""
  for c in python3.13 python3.12 python3.11 python3.10 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  done
  UV="$(command -v uv || ls "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" 2>/dev/null | head -1)"
  if [ -z "$PY" ] && [ -z "$UV" ]; then
    alert "Facet needs Python 3.10 or newer. Install it from https://www.python.org/downloads/ and open Facet again."
    exit 1
  fi
  osascript -e 'display notification "Setting up Facet for the first time (about 1–2 minutes)…" with title "Facet"' >/dev/null 2>&1
  if [ -n "$PY" ]; then
    SETUP() { "$PY" -m venv .venv && .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -r requirements.txt; }
  else  # uv brings its own Python
    SETUP() { "$UV" venv --python 3.12 .venv && "$UV" pip install --python .venv/bin/python -r requirements.txt; }
  fi
  SETUP >"$LOG" 2>&1 || {
    rm -rf .venv
    alert "Installation failed. Details: ~/Library/Logs/Facet-launcher.log"
    exit 1
  }
fi
exec .venv/bin/python run.py "$@"
