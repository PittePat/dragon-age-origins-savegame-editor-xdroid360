# Changelog

## v0.5
- Quests: lesbare Titel und Quest-Texte aus den Spiel-Textdateien (`*.tlk`, Huffman-komprimiertes GFF-Format der
  Xbox-360-Version) über „Load game text (.tlk)…“; weibliche Textvarianten (`*_f.tlk`) werden berücksichtigt,
  die gewählten Dateien werden gemerkt. Detailfeld mit dem aktuellen Quest-Text.
- Versionsnummer im About-Dialog.

## v0.2
- Open File öffnet auch XDroid360-Export-ZIPs; bei mehreren Spielständen Auswahl mit Spielzeit, Level, Gebiet und
  Speicherzeitpunkt. Speichern schreibt in die ZIP zurück (inkl. `.x`-Prüfsumme, Backup `.orig`/`.bak`).
- Neue Seiten „Equipment“ (ausgerüstete Items bearbeiten), „Quests“ (Journal, nur Anzeige, mit technischen Namen) und
  „Location“ (Gebiet und Position, nur Anzeige).
- „Change class (experimental)…“ für den Spielercharakter (Klassenmarkierung tauschen, Zauber/Talente der alten
  Klasse entfernen). Im Spiel nicht verifiziert.

## v0.1
- Python-3/wxPython-4-Portierung des pygff-Savegame-Editors für Linux, angepasst an Xbox-360-Spielstände (XDroid360).
- Automatische Aktualisierung der `.x`-Prüfsummendatei beim Speichern.
- Items: ResRef, alle Felder bearbeiten, Item-Auswahl, Duplizieren mit neuer Objekt-ID.
- Stats: bekannte Attribute oder per Index hinzufügen.
- Menüs „Points“ und „Spells & Skills“; Spielzeit unter Inventory; „Max Weight“.
- Aufgeräumt: nur Dragon Age: Origins, keine ungenutzten Dateien.
