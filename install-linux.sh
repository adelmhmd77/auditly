#!/usr/bin/env bash
# Install Auditly as a desktop app for the current user (no root needed).
# Adds it to the app menu / Activities with its icon.  Uninstall:  ./install-linux.sh --uninstall
set -e
cd "$(dirname "$0")"

APP_DIR="$HOME/.local/opt/auditly"
BIN_LINK="$HOME/.local/bin/auditly"
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
DESKTOP="$HOME/.local/share/applications/auditly.desktop"

if [ "$1" = "--uninstall" ]; then
  rm -rf "$APP_DIR" "$BIN_LINK" "$ICON_DIR/auditly.png" "$DESKTOP"
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
  echo "Auditly removed. (Your saved crawls and exports were kept.)"
  exit 0
fi

if [ ! -x dist/Auditly ]; then
  echo "Building Auditly first (one time, a few minutes)…"
  PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
  [ -x .venv/bin/python ] || { python3 -m venv .venv; PY=.venv/bin/python; }
  "$PY" build.py
fi

mkdir -p "$APP_DIR" "$(dirname "$BIN_LINK")" "$ICON_DIR" "$(dirname "$DESKTOP")"
install -m 755 dist/Auditly "$APP_DIR/Auditly"
install -m 644 auditly/assets/auditly.png "$ICON_DIR/auditly.png"
ln -sf "$APP_DIR/Auditly" "$BIN_LINK"

cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Auditly
GenericName=SEO Auditor
Comment=Crawl websites and find technical SEO issues
Exec=$APP_DIR/Auditly
Icon=auditly
Terminal=false
Categories=Development;WebDevelopment;
Keywords=SEO;crawler;audit;website;
StartupWMClass=auditly
EOF
chmod 644 "$DESKTOP"
update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true

echo "Auditly is installed. Open it from your app menu (search \"Auditly\")."
