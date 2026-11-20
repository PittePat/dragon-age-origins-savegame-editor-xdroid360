# Dragon Age Origins Savegame Editor for XDroid360

Spielstand-Editor für **Dragon Age: Origins** (Xbox-360-Version, wie sie XDroid360 auf Android verwendet),
lauffähig unter Linux (getestet für Linux Mint). Python 3 + wxPython 4.

Basiert auf dem Savegame-Editor aus **pygff 1.0** (William Clark; Savegame-Editor von Mephales), der für
Python 2, wxPython 2.8 und Windows geschrieben war.

## Installation (Linux Mint 21/22)

```bash
sudo apt install python3-wxgtk4.0
./install.sh            # legt einen Menüeintrag unter "Spiele" an
```

Ohne Installation: `python3 daosavegame.py [datei.das]`

## Funktionen

* **File → Open File… / Save / Exit**
* **Open File** versteht `.das`-Dateien und **XDroid360-Exporte (`.zip`)**: Enthält die ZIP einen Spielstand, wird er
  direkt geöffnet; sind es mehrere, erscheint eine Auswahl mit Name, Charakter, Gebiet, **Spielzeit**, Level und
  Speicherzeitpunkt (längste Spielzeit = neuester Spielstand, steht oben). **Save** schreibt den Spielstand samt
  aktualisierter `.x`-Prüfsumme zurück **in die ZIP**; die ursprüngliche ZIP bleibt als `.orig` (beim ersten Mal)
  bzw. `.bak` erhalten. Die ZIP kann danach direkt wieder in XDroid360 importiert werden.
* **Inventory:** Money, Max Weight, Spielzeit (nur lesbar)
* **Items** (Backpack, Plot Items, Party Storage, Areas): ResRef, Count, Infinite direkt in der Tabelle ändern;
  Rechtsklick: Duplicate, Move Item, Edit All Fields…, Pick Item from List…
* **Party → Charaktername:** Stats ansehen/ändern; Rechtsklick: Add Known Attribute (z. B. Resistenzen),
  Add Attribute by Index…
* **Points:** Attribut-, Skill-, Talent/Zauber- und Spezialisierungspunkte je Charakter
* **Spells & Skills:** alle bekannten Zauber, Talente, Skills und Spezialisierungen mit Häkchen (= gelernt),
  Suche, Filter und „Add by ID…“. Die Gruppe „Immunities (experimental)“ ist ungetestet.

## XDroid360

Neben jeder Datei liegt (auch in der Export-ZIP) eine `<datei>.x` mit der CRC32-Prüfsumme (Big-Endian). Der Editor aktualisiert
`savegame.das.x` beim Speichern automatisch. Bei einzelnen Dateien **immer beide (`savegame.das` und
`savegame.das.x`) zurück aufs Gerät kopieren**; bei ZIPs steckt beides in der ZIP. Vorher den Save-Ordner sichern.

Beim Speichern wird zuerst in eine `.tmp`-Datei geschrieben; das Original wird danach als `.orig`
(beim ersten Mal) bzw. `.bak` gesichert.

## Einschränkungen

* Nur Dragon Age: Origins (GFF V4.0). Dragon Age II wird nicht unterstützt.
* Die Oberfläche wurde ohne echtes wxPython ausprobiert (die Logik ist mit echten Spielständen getestet).
  Kleine Fehler in den Fenstern sind möglich.
* Ob hinzugefügte Fähigkeiten, Resistenzen oder geänderte Items im Spiel vollständig wirken, ist nicht für
  jeden Fall geprüft. Immer mit einer Sicherheitskopie arbeiten.

## Entwicklung

```bash
python3 tests/test_core.py     # Tests der GFF-Bibliothek (ohne wxPython)
```

Releases entstehen automatisch: Tag `vX.Y.Z` pushen → GitHub Actions baut die ZIP und legt ein Release an.
