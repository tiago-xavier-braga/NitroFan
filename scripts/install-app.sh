#!/usr/bin/env bash
# Installs the menu entry and icon for NitroFan (per-user).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
ICONS=$HOME/.local/share/icons/hicolor/scalable/apps
APPS=$HOME/.local/share/applications

mkdir -p "$ICONS" "$APPS"
cp "$ROOT/app/nitrofan.svg" "$ICONS/"
cat > "$APPS/nitrofan.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=NitroFan
Comment=Fan control for Acer Nitro laptops
Exec=python3 $ROOT/app/nitrofan.py
Icon=nitrofan
Categories=System;Settings;
DESKTOP

gtk-update-icon-cache -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database "$APPS" 2>/dev/null || true
echo "Installed. Look for \"NitroFan\" in your app menu."
