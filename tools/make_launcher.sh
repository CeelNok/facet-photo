#!/bin/bash
# Rebuilds and ad-hoc signs the Facet.app launcher (macOS). Run after editing tools/launcher.c or launch.sh.
# Signing happens in a temporary folder: iCloud/File Provider folders add attributes that codesign refuses.
set -e
cd "$(dirname "$0")/.."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ditto --norsrc --noextattr --noqtn Facet.app "$TMP/Facet.app"
clang -O2 -arch arm64 -arch x86_64 -mmacosx-version-min=11.0 -o "$TMP/Facet.app/Contents/MacOS/Facet" tools/launcher.c
chmod +x "$TMP/Facet.app/Contents/MacOS/Facet" "$TMP/Facet.app/Contents/Resources/launch.sh"
codesign --force --deep --sign - "$TMP/Facet.app"
codesign --verify --deep --strict "$TMP/Facet.app"
rm -rf Facet.app
ditto --norsrc --noextattr --noqtn "$TMP/Facet.app" Facet.app
codesign --verify --deep "Facet.app" && echo "Facet.app launcher built and signed"
