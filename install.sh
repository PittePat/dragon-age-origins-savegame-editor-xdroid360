#!/bin/sh
# Installiert den Dragon Age Origins Savegame Editor for XDroid360 für den aktuellen Benutzer
# (Linux Mint / Ubuntu / Debian). Eine frühere Installation wird dabei ersetzt.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/dragonage-savegame-editor"

if ! python3 -c "import wx, wx.dataview" 2>/dev/null; then
    echo "wxPython 4 fehlt. Installiere es zuerst mit:"
    echo "    sudo apt install python3-wxgtk4.0"
    exit 1
fi

rm -rf "$DEST"
mkdir -p "$DEST" "$HOME/.local/share/applications"
cp "$HERE"/*.py "$DEST/"
cp -r "$HERE/gff4" "$DEST/"
chmod +x "$DEST/daosavegame.py"

cat > "$HOME/.local/share/applications/dragonage-savegame-editor.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Dragon Age Origins Savegame Editor for XDroid360
Comment=Dragon Age Origins (Xbox 360 / XDroid360) Spielstände bearbeiten
Exec=python3 "$DEST/daosavegame.py" %f
Icon=applications-games
Terminal=false
Categories=Game;Utility;
DESKTOP

echo "Fertig. Du findest das Programm jetzt im Menü unter 'Spiele' (Dragon Age Origins Savegame Editor for XDroid360)."
echo "Oder starte es direkt:  python3 \"$DEST/daosavegame.py\""
