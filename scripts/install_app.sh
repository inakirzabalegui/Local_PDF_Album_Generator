#!/bin/bash
# Build "Album Generator.app" and install it into /Applications.
#
# Idempotent: regenera iconos, recompone el bundle y reemplaza la versión
# previa en /Applications. Pensado para reinstalación tras formatear el laptop.
#
# Requisitos previos:
#   - El repo está en su ubicación habitual (ver PROJECT_DIR abajo).
#   - El entorno virtual existe en .venv con las dependencias instaladas
#     (Pillow es necesario para generar el icono).
#
# Uso:
#   ./scripts/install_app.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="Album Generator"
DIST_APP="$PROJECT_DIR/dist/$APP_NAME.app"
INSTALL_APP="/Applications/$APP_NAME.app"
ICONSET="$PROJECT_DIR/assets/AppIcon.iconset"
ICNS="$PROJECT_DIR/assets/AppIcon.icns"

cd "$PROJECT_DIR"

if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "ERROR: no se encontró $PROJECT_DIR/.venv"
    echo "Crea el entorno virtual primero:"
    echo "  python3.13 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

echo "==> Generando iconos con scripts/generate_icon.py"
# shellcheck disable=SC1091
source "$PROJECT_DIR/.venv/bin/activate"
python scripts/generate_icon.py

echo "==> Compilando $ICNS desde $ICONSET"
iconutil -c icns "$ICONSET" -o "$ICNS"

echo "==> Componiendo bundle en $DIST_APP"
rm -rf "$DIST_APP"
mkdir -p "$DIST_APP/Contents/MacOS"
mkdir -p "$DIST_APP/Contents/Resources"
cp "$ICNS" "$DIST_APP/Contents/Resources/AppIcon.icns"

cat > "$DIST_APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Album Generator</string>
    <key>CFBundleDisplayName</key>
    <string>Album Generator</string>
    <key>CFBundleIdentifier</key>
    <string>com.jzabalegui.albumgenerator</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

# Launcher con PROJECT_DIR interpolado en tiempo de build (no es un heredoc
# 'quoted' para que ${PROJECT_DIR} se expanda; el resto de variables van
# escapadas con \$).
cat > "$DIST_APP/Contents/MacOS/launcher" <<LAUNCHER
#!/bin/bash
# Album Generator .app launcher
# Wraps the Flask server in a macOS app bundle.

PROJECT_DIR="${PROJECT_DIR}"
LOG_FILE="\$HOME/Library/Logs/AlbumGenerator.log"

mkdir -p "\$(dirname "\$LOG_FILE")"

fail() {
    /usr/bin/osascript -e "display dialog \"Album Generator: \$1\nSee log: \$LOG_FILE\" buttons {\"OK\"} default button \"OK\" with icon stop with title \"Album Generator\""
    exit 1
}

exec >> "\$LOG_FILE" 2>&1
echo ""
echo "=== \$(date) — launching Album Generator ==="

if [ ! -d "\$PROJECT_DIR" ]; then
    fail "Project directory not found: \$PROJECT_DIR"
fi

if [ ! -d "\$PROJECT_DIR/.venv" ]; then
    fail "Virtual environment not found at \$PROJECT_DIR/.venv"
fi

EXISTING_PID=\$(lsof -ti :5050 2>/dev/null)
if [ -n "\$EXISTING_PID" ]; then
    echo "Killing previous server (PID \$EXISTING_PID)..."
    kill -9 \$EXISTING_PID 2>/dev/null || true
    sleep 1
fi

cd "\$PROJECT_DIR" || fail "Could not cd into \$PROJECT_DIR"
# shellcheck disable=SC1091
source "\$PROJECT_DIR/.venv/bin/activate"

exec python make_album.py --app
LAUNCHER
chmod +x "$DIST_APP/Contents/MacOS/launcher"

echo "==> Instalando en $INSTALL_APP"
rm -rf "$INSTALL_APP"
cp -R "$DIST_APP" "$INSTALL_APP"

# Refresca el icono en Finder/Dock para que macOS no muestre uno cacheado
touch "$INSTALL_APP"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
    -f "$INSTALL_APP" >/dev/null 2>&1 || true

echo ""
echo "Listo. Lanza la app con:"
echo "  open \"$INSTALL_APP\""
echo "  # o desde Spotlight:  ⌘+espacio → \"Album Generator\""
