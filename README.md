# Autoclicker for Idle Clans

Ein Windows-Autoclicker mit Sequenz-Unterstützung, automatischer Item-Erkennung und Farb-Triggern.

## Features

- **Punkte aufnehmen**: Mausposition speichern mit automatischer Benennung
- **Sequenzen erstellen**: Punkte mit Wartezeiten oder Farb-Triggern verknüpfen
- **Dreiphasen-System**:
  - **START**: Wird zu Beginn jedes Zyklus ausgeführt
  - **LOOP-Phasen**: Mehrere Loops möglich, jeweils mit eigenen Wiederholungen
  - **END**: Wird nach allen Zyklen ausgeführt (z.B. für Logout)
- **Farb-Trigger**: Warte bis eine bestimmte Farbe erscheint ODER verschwindet
- **Zufällige Verzögerung**: `1 30-45` = warte 30-45 Sekunden zufällig
- **Tastatureingaben**: Automatische Tastendrücke (Enter, Space, F1-F12, etc.)
- **Automatische Slot-Erkennung**: OpenCV-basierte Erkennung von Item-Slots
- **Item-Scan System**: Items anhand von Marker-Farben oder Templates erkennen
- **Kategorie-System**: Items gruppieren (z.B. Hosen, Jacken) - nur bestes pro Kategorie klicken
- **Template-Matching**: Items per Screenshot erkennen (OpenCV)
- **Preset-System**: Slots und Items als benannte Presets speichern
- **Bedingte Logik**: ELSE-Aktionen wenn Scan/Pixel-Trigger fehlschlägt
- **Pause/Resume**: Sequenz pausieren ohne Fortschritt zu verlieren
- **Skip**: Aktuelle Wartezeit überspringen
- **Statistiken**: Laufzeit, Klicks, Items gefunden
- **Quick-Switch**: Schnell zwischen Sequenzen wechseln
- **Factory Reset**: Kompletter Reset wie frisch von GitHub
- **Konfigurierbar**: Toleranzen und Einstellungen via `config.json`
- **Fail-Safe**: Maus in obere linke Ecke bewegen stoppt den Klicker
- **Bounds-Checking**: Warnung bei Regionen außerhalb des Bildschirms

## Voraussetzungen

- Windows 10/11
- Python 3.10+
- **Optional**: Pillow für Farberkennung (`pip install pillow`)
- **Optional**: OpenCV für automatische Slot-Erkennung (`pip install opencv-python numpy`)

## Installation

```bash
git clone https://github.com/r3flexone/Autoclicker-Idleclans.git
cd Autoclicker-Idleclans
pip install pillow opencv-python numpy  # Optional, für erweiterte Features
python autoclicker.py
```

## Hotkeys

| Hotkey | Funktion |
|--------|----------|
| `CTRL+ALT+A` | Aktuelle Mausposition als Punkt speichern |
| `CTRL+ALT+U` | Letzten Punkt entfernen (Undo) |
| `CTRL+ALT+C` | Alle Punkte löschen |
| `CTRL+ALT+X` | Factory Reset (ALLES löschen - wie frisch von GitHub) |
| `CTRL+ALT+E` | Sequenz-Editor öffnen |
| `CTRL+ALT+N` | Item-Scan System (Slots, Items, Scans) |
| `CTRL+ALT+L` | Gespeicherte Sequenz laden |
| `CTRL+ALT+P` | Punkte anzeigen/testen/umbenennen |
| `CTRL+ALT+T` | Farb-Analysator |
| `CTRL+ALT+S` | Start/Stop (öffnet Lade-Menü wenn keine Sequenz geladen) |
| `CTRL+ALT+G` | Pause/Resume (während Sequenz läuft) |
| `CTRL+ALT+K` | Skip (aktuelle Wartezeit überspringen) |
| `CTRL+ALT+W` | Quick-Switch (schnell Sequenz wechseln) |
| `CTRL+ALT+Q` | Programm beenden |

## Item-Scan System (`CTRL+ALT+N`)

Das Item-Scan System bietet ein Menü mit folgenden Optionen:
- **[1] Slots bearbeiten** - Bereiche wo Items erscheinen können
- **[2] Items bearbeiten** - Item-Profile für die Erkennung
- **[3] Scans bearbeiten** - Slots und Items verknüpfen

### Slot-Editor (Menü → 1)

Verwaltet Bereiche wo Items erscheinen können. Arbeitet mit **Presets** - wie beim Sequenz-Editor wird am Anfang nach einem Namen gefragt.

**Ablauf:**
1. [0] Neues Preset erstellen → Name eingeben
2. [1-n] Bestehendes Preset bearbeiten
3. Slots hinzufügen/bearbeiten/löschen
4. `done` → Preset wird gespeichert
5. `cancel` → Änderungen werden verworfen

**Befehle im Editor:**

| Befehl | Beschreibung |
|--------|--------------|
| `auto` | Automatische Slot-Erkennung mit OpenCV |
| `add` | Manuell einen Slot hinzufügen |
| `del <Nr>` | Slot löschen |
| `del <Start>-<Ende>` | Mehrere Slots löschen (z.B. `del 1-7`) |
| `del all` | Alle Slots löschen |
| `edit <Nr>` | Slot bearbeiten |
| `show` | Alle Slots anzeigen |
| `done` | Preset speichern und Editor verlassen |
| `cancel` | Änderungen verwerfen und Editor verlassen |

### Automatische Erkennung

Mit `auto` werden Slots automatisch per Farbe erkannt:
1. Region markieren (oben-links, unten-rechts)
2. Screenshot wird erstellt
3. Hintergrundfarbe des Slots angeben
4. Slots werden automatisch erkannt und nummeriert
5. Screenshot und Vorschau werden in `Screenshots/` gespeichert

### Item-Editor (Menü → 2)

Verwaltet Item-Profile für die Erkennung. Arbeitet mit **Presets** - wie beim Sequenz-Editor wird am Anfang nach einem Namen gefragt.

**Ablauf:**
1. [0] Neues Preset erstellen → Name eingeben
2. [1-n] Bestehendes Preset bearbeiten
3. Items lernen/hinzufügen/bearbeiten/löschen
4. `done` → Preset wird gespeichert
5. `cancel` → Änderungen werden verworfen

**Befehle im Editor:**

| Befehl | Beschreibung |
|--------|--------------|
| `learn <Nr>` | Item von Slot Nr. lernen (scannt Marker-Farben + Template) |
| `add` | Manuell ein Item hinzufügen |
| `edit <Nr>` | Item bearbeiten (Priorität, Farben, Bestätigung) |
| `rename <Nr>` | Item umbenennen (inkl. Template-Datei) |
| `del <Nr>` | Item löschen |
| `del <Start>-<Ende>` | Mehrere Items löschen (z.B. `del 1-5`) |
| `del all` | Alle Items löschen |
| `template <Nr>` | Template für Item setzen/entfernen |
| `templates` | Verfügbare Templates anzeigen |
| `show` | Alle Items anzeigen |
| `done` | Preset speichern und Editor verlassen |
| `cancel` | Änderungen verwerfen und Editor verlassen |

### Item lernen

Mit `learn <Nr>` wird ein Item vom entsprechenden Slot gelernt:
1. Slot-Nummer eingeben
2. 1 Sekunde warten (Item muss sichtbar sein)
3. Marker-Farben werden automatisch gescannt
4. Name, Priorität und **Kategorie** eingeben
5. Optional: Template-Screenshot erstellen
6. Optional: Bestätigungs-Klick konfigurieren

### Kategorie-System

Items können einer **Kategorie** zugeordnet werden (z.B. "Hosen", "Jacken", "Juwelen"):

- Items **derselben Kategorie** konkurrieren - nur das mit der niedrigsten Priorität wird geklickt
- Items **verschiedener Kategorien** konkurrieren nicht - alle werden geklickt
- Ohne Kategorie ist jedes Item seine eigene Kategorie

**Beispiel:**
```
Pinkes Juwel   [Kategorie: Juwelen]  Priorität 1  ← wird geklickt
Blaues Juwel   [Kategorie: Juwelen]  Priorität 2  ← wird NICHT geklickt (P1 ist besser)
Rote Jacke     [Kategorie: Jacken]   Priorität 1  ← wird geklickt (andere Kategorie)
```

**JSON-Format:**
```json
{
  "Pinkes Juwel": {
    "name": "Pinkes Juwel",
    "priority": 1,
    "template": "pinkes_juwel.png",
    "min_confidence": 0.9,
    "category": "Juwelen"
  }
}
```

### Template-Matching

Items können per **Template-Matching** (Screenshot-Vergleich) erkannt werden:

1. Bei `learn` wird automatisch ein Template erstellt
2. Mit `template <Nr>` kann ein Template nachträglich gesetzt werden
3. Templates werden in `items/templates/` gespeichert
4. `min_confidence` (0.0-1.0) bestimmt wie genau das Match sein muss

Template-Matching ist genauer als Marker-Farben, besonders bei ähnlichen Items.

## Sequenz-Editor (`CTRL+ALT+E`)

### Phasen

Eine Sequenz besteht aus drei Phasen:

1. **START**: Wird zu Beginn jedes Zyklus ausgeführt
2. **LOOP**: Wird wiederholt (konfigurierbare Anzahl)
3. **END**: Wird nach allen Zyklen ausgeführt

### Editor-Befehle

| Befehl | Beschreibung |
|--------|--------------|
| `<Nr> <Zeit>` | Warte X Sekunden, dann klicke Punkt (z.B. `1 30`) |
| `<Nr> <Min>-<Max>` | Zufällige Wartezeit (z.B. `1 30-45`) |
| `<Nr> 0` | Sofort klicken ohne Wartezeit |
| `<Nr> pixel` | Warte auf Farbe, dann klicke |
| `<Nr> gone` | Warte bis Farbe VERSCHWINDET, dann klicke |
| `<Nr> <Zeit> pixel` | Warte X Sek, dann auf Farbe warten, dann klicke |
| `wait <Zeit>` | Nur warten, KEIN Klick |
| `wait <Min>-<Max>` | Zufällig warten, KEIN Klick (z.B. `wait 30-45`) |
| `wait pixel` | Auf Farbe warten, KEIN Klick |
| `wait gone` | Warten bis Farbe VERSCHWINDET, KEIN Klick |
| `key <Taste>` | Taste sofort drücken (z.B. `key enter`) |
| `key <Zeit> <Taste>` | Warten, dann Taste drücken (z.B. `key 5 space`) |
| `key <Min>-<Max> <Taste>` | Zufällig warten, dann Taste (z.B. `key 30-45 enter`) |
| `scan <Name>` | Item-Scan ausführen (bestes pro Kategorie) |
| `scan <Name> best` | Item-Scan: nur 1 Item total (das absolute Beste) |
| `... else skip` | Bei Fehlschlag überspringen |
| `... else <Nr> [s]` | Bei Fehlschlag Punkt klicken |
| `... else key <T>` | Bei Fehlschlag Taste drücken |
| `learn <Name>` | Neuen Punkt erstellen (direkt im Editor) |
| `points` | Alle verfügbaren Punkte anzeigen |
| `del <Nr>` | Schritt löschen |
| `clear` | Alle Schritte löschen |
| `show` | Aktuelle Schritte anzeigen |
| `done` | Phase abschließen und speichern |
| `cancel` | Editor abbrechen (ohne Speichern) |

### Verfügbare Tasten

`enter`, `space`, `tab`, `escape`, `backspace`, `delete`,
`left`, `up`, `right`, `down`,
`f1`-`f12`,
`0`-`9`, `a`-`z`

### Beispiel-Sequenz

```
[START: 0] > 1 5           # Punkt 1 klicken, 5s warten
[START: 1] > 2 pixel       # Warten bis Farbe erscheint, dann Punkt 2 klicken
[START: 2] > key enter     # Enter-Taste drücken
[START: 3] > done

[Loop 1: 0] > 3 30-45      # Punkt 3 klicken, 30-45s zufällig warten
[Loop 1: 1] > scan items   # Item-Scan ausführen (bestes pro Kategorie)
[Loop 1: 2] > wait 10-15   # 10-15s zufällig warten ohne Klick
[Loop 1: 3] > 4 gone       # Warten bis Farbe verschwindet, dann Punkt 4 klicken
[Loop 1: 4] > done

Zyklen: 10                 # 10 Durchläufe

[END: 0] > 5 0             # Am Ende: Punkt 5 klicken (z.B. Logout)
[END: 1] > key enter       # Enter drücken
[END: 2] > done
```

## Laufzeit-Steuerung

Während eine Sequenz läuft:

- **CTRL+ALT+S** - Stoppt die Sequenz komplett
- **CTRL+ALT+G** - Pausiert/Setzt fort (Fortschritt bleibt erhalten)
- **CTRL+ALT+K** - Überspringt die aktuelle Wartezeit

### Statistiken

Nach Sequenz-Ende werden Statistiken angezeigt:
```
STATISTIKEN:
  Laufzeit:     1h 23m 45s
  Zyklen:       5
  Klicks:       1234
  Items:        56
  Tasten:       12
```

## Item-Scan System

Das Item-Scan System erkennt Items anhand ihrer Marker-Farben oder Templates:

1. **Slots erstellen** (`CTRL+ALT+N` → Menü 1): Bereiche wo Items erscheinen können
2. **Items lernen** (`CTRL+ALT+N` → Menü 2): Mit `learn <Nr>` Marker-Farben + Template scannen
3. **Kategorien zuweisen**: Items gruppieren (z.B. "Hosen", "Jacken")
4. **Scan konfigurieren** (`CTRL+ALT+N` → Menü 3): Slots und Items verknüpfen
5. **In Sequenz nutzen**: `scan <Name>` oder `scan <Name> best`

### Ablauf

- `scan items` → Scannt alle Slots, klickt das **beste Item pro Kategorie**
- `scan items best` → Scannt alle Slots, klickt nur **1 Item total** (das absolute Beste)

### Beispiel mit Kategorien

Gefundene Items:
- Pinkes Juwel (Kategorie: Juwelen, P1)
- Blaues Juwel (Kategorie: Juwelen, P2)
- Rote Jacke (Kategorie: Jacken, P1)

Ergebnis von `scan items`:
- ✓ Pinkes Juwel wird geklickt (bestes Juwel)
- ✗ Blaues Juwel wird NICHT geklickt (P2 < P1)
- ✓ Rote Jacke wird geklickt (bestes/einziges bei Jacken)

## Bedingte Logik (ELSE)

Für Schritte mit Bedingungen (Scan, Pixel-Trigger) können Fallback-Aktionen definiert werden:

### ELSE-Syntax

| Befehl | Beschreibung |
|--------|--------------|
| `else skip` | Schritt überspringen, Sequenz fortsetzen |
| `else restart` | Sequenz komplett neu starten |
| `else <Nr>` | Anderen Punkt klicken |
| `else <Nr> <Sek>` | Warten, dann anderen Punkt klicken |
| `else key <Taste>` | Taste drücken |

### Beispiele

```
scan items else skip           # Wenn kein Item: überspringen
scan items else restart        # Wenn kein Item: Sequenz neu starten
scan items else 2              # Wenn kein Item: Punkt 2 klicken
scan items else 2 5            # Wenn kein Item: 5s warten, dann Punkt 2 klicken
1 pixel else skip              # Wenn Timeout: überspringen
1 pixel else restart           # Wenn Timeout: von vorne beginnen
1 pixel else key enter         # Wenn Timeout: Enter drücken
wait gone else skip            # Wenn Farbe nicht verschwindet: überspringen
```

### Wann wird ELSE ausgelöst?

- **Item-Scan**: Wenn kein Item gefunden wird
- **Pixel-Trigger**: Wenn Timeout erreicht wird (Standard: 60s)
- **Wait Gone**: Wenn Farbe nicht verschwindet

Ohne `else` stoppt die Sequenz bei Fehlschlag.

## Konfiguration (`config.json`)

Wird beim ersten Start automatisch erstellt:

```json
{
  "clicks_per_point": 1,
  "max_total_clicks": null,
  "failsafe_enabled": true,
  "color_tolerance": 40,
  "pixel_wait_tolerance": 10,
  "pixel_wait_timeout": 60,
  "pixel_check_interval": 1,
  "debug_detection": true,
  "scan_reverse": false,
  "marker_count": 5,
  "require_all_markers": true,
  "min_markers_required": 2,
  "slot_hsv_tolerance": 25,
  "slot_inset": 10,
  "slot_color_distance": 25
}
```

| Option | Beschreibung |
|--------|--------------|
| `color_tolerance` | Toleranz für Item-Scan (höher = toleranter) |
| `pixel_wait_tolerance` | Toleranz für Pixel-Trigger (niedriger = genauer) |
| `pixel_wait_timeout` | Timeout in Sekunden für Farb-Trigger |
| `pixel_check_interval` | Wie oft auf Farbe prüfen (Sekunden) |
| `debug_detection` | Debug-Ausgaben für Farberkennung |
| `scan_reverse` | Slots von hinten nach vorne scannen |
| `marker_count` | Anzahl Marker-Farben pro Item (Standard: 5) |
| `require_all_markers` | Alle Marker müssen gefunden werden (true/false) |
| `min_markers_required` | Mindestanzahl Marker wenn `require_all_markers: false` |
| `slot_hsv_tolerance` | HSV-Toleranz für automatische Slot-Erkennung |
| `slot_inset` | Pixel-Einzug vom Slot-Rand für genauere Klick-Position |
| `slot_color_distance` | Farbdistanz für Hintergrund-Ausschluss bei Item-Lernen |

## Dateistruktur

```
Autoclicker-Idleclans/
├── autoclicker.py          # Hauptprogramm
├── config.json             # Konfiguration (auto-generiert)
├── README.md               # Diese Datei
├── sequences/              # Gespeicherte Sequenzen
│   ├── points.json         # Aufgenommene Punkte
│   └── *.json              # Sequenz-Dateien
├── slots/                  # Slot-Konfigurationen
│   ├── slots.json          # Aktive Slots
│   └── presets/            # Slot-Presets
│       └── *.json          # Benannte Slot-Presets
├── items/                  # Item-Konfigurationen
│   ├── items.json          # Aktive Items
│   ├── templates/          # Template-Bilder für Matching
│   │   └── *.png           # Item-Screenshots
│   └── presets/            # Item-Presets
│       └── *.json          # Benannte Item-Presets
├── Screenshots/            # Screenshots und Vorschau-Bilder
│   ├── screenshot_*.png    # Original-Screenshots
│   └── preview_*.png       # Vorschau mit Markierungen
├── item_scans/             # Item-Scan Konfigurationen
│   └── *.json              # Scan-Konfigurationen
└── configs/                # Config-Presets
    └── *.json              # Gespeicherte Konfigurationen
```

## Technische Details

- Windows API via `ctypes` (keine externen Abhängigkeiten für Basis-Funktionen)
- Pillow für Screenshot und Farberkennung (optional)
- OpenCV für automatische Slot-Erkennung (optional)
- Globale Hotkeys über `RegisterHotKey`
- Mausklicks und Tastatureingaben über `SendInput`
- BitBlt für Game-Screenshots (funktioniert mit Hardware-Beschleunigung)
- Thread-basierte Ausführung
- JSON-Persistenz
- Multi-Monitor Unterstützung
- Sichere Dateinamen (Path-Traversal-Schutz)
- Bounds-Checking für Bildschirmregionen

## Changelog

### Neueste Änderungen

- **ELSE Restart**: `else restart` Option zum Neustart der Sequenz bei Fehlschlag
- **Kategorie-System**: Items gruppieren (Hosen, Jacken, Juwelen) - nur bestes pro Kategorie klicken
- **Template-Matching**: Items per Screenshot erkennen (OpenCV)
- **Befehle vereinheitlicht**: `done`/`cancel` statt `fertig`/`abbruch` (beide funktionieren)
- **CTRL+ALT+S Auto-Load**: Öffnet Lade-Menü wenn keine Sequenz geladen
- **Step-Editor**: `learn` und `points` Befehle zum Punkte erstellen
- **Item-Editor**: `rename` Befehl zum Umbenennen (inkl. Template-Datei)
- **Scan-Modus**: Default ist jetzt `all` (bestes pro Kategorie), `best` für nur 1 Item
- **Unicode-Support**: Templates mit Umlauten (ü, ä, ö) funktionieren jetzt

### Ältere Änderungen

- **Preset-System**: Slots und Items werden als benannte Presets gespeichert
- **Screenshots-Ordner**: Alle Screenshots landen jetzt in `Screenshots/`
- **Konsistente Befehle**: `del all`, `del <Nr>-<Nr>` in allen Editoren
- **Performance**: Early-Exit bei Marker-Erkennung
- **Sicherheit**: Path-Traversal-Schutz für Dateinamen
- **Bounds-Checking**: Warnung bei Regionen außerhalb des Bildschirms
- **Konfigurierbar**: Neue Optionen für Slot-Erkennung

## Lizenz

MIT License
