#!/bin/bash
# Builds a standalone Facet.app (with Python and all libraries) into dist/.
set -e
cd "$(dirname "$0")"
.venv/bin/python -m pip --version >/dev/null 2>&1 || .venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install pyinstaller
.venv/bin/pyinstaller --noconfirm --windowed --name Facet \
  --icon facet/assets/facet.icns --add-data "facet/assets:facet/assets" \
  --collect-all rawpy --collect-all pillow_heif \
  --osx-bundle-identifier app.facet.photos run.py
echo "Done: dist/Facet.app"
