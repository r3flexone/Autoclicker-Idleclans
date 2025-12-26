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
- **Item-Scan System**: Items anhand von Marker-Farben erkennen und priorisieren
- **Bedingte Logik**: ELSE-Aktionen wenn Scan/Pixel-Trigger fehlschlägt
- **Pause/Resume**: Sequenz pausieren ohne Fortschritt zu verlieren
- **Skip**: Aktuelle Wartezeit überspringen
- **Statistiken**: Laufzeit, Klicks, Items gefunden
- **Quick-Switch**: Schnell zwischen Sequenzen wechseln
- **Factory Reset**: Kompletter Reset wie frisch von GitHub
- **Konfigurierbar**: Toleranzen und Einstellungen via `config.json`
- **Fail-Safe**: Maus in obere linke Ecke bewegen stoppt den Klicker

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
| `CTRL+ALT+S` | Start/Stop der aktiven Sequenz |
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

Verwaltet Bereiche wo Items erscheinen können.

### Befehle

| Befehl | Beschreibung |
|--------|--------------|
| `detect` | Automatische Slot-Erkennung mit OpenCV |
| `add` | Manuell einen Slot hinzufügen |
| `del <Nr>` | Slot löschen |
| `del <Start>-<Ende>` | Mehrere Slots löschen (z.B. `del 1-7`) |
| `del all` | Alle Slots löschen |
| `edit <Nr>` | Slot bearbeiten |
| `list` | Alle Slots anzeigen |
| `exit` | Editor verlassen |

### Automatische Erkennung

Mit `detect` werden Slots automatisch per Farbe erkannt:
1. Screenshot aufnehmen oder aus Datei laden
2. Hintergrundfarbe des Slots angeben
3. Slots werden automatisch erkannt und nummeriert

### Item-Editor (Menü → 2)

Verwaltet Item-Profile für die Erkennung.

### Befehle

| Befehl | Beschreibung |
|--------|--------------|
| `learn <Nr>` | Item von Slot Nr. lernen (scannt Marker-Farben) |
| `add` | Manuell ein Item hinzufügen |
| `del <Nr>` | Item löschen |
| `del all` | Alle Items löschen |
| `edit <Nr>` | Item bearbeiten (Name, Priorität, Bestätigung) |
| `list` | Alle Items anzeigen |
| `exit` | Editor verlassen |

### Item lernen

Mit `learn <Nr>` wird ein Item vom entsprechenden Slot gelernt:
1. Slot-Nummer eingeben
2. 1 Sekunde warten (Item muss sichtbar sein)
3. Marker-Farben werden automatisch gescannt
4. Name und Priorität eingeben
5. Optional: Bestätigungs-Klick konfigurieren

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
| `scan <Name>` | Item-Scan ausführen, bestes Item klicken |
| `scan <Name> all` | Item-Scan ausführen, ALLE Items klicken |
| `... else skip` | Bei Fehlschlag überspringen |
| `... else <Nr> [s]` | Bei Fehlschlag Punkt klicken |
| `... else key <T>` | Bei Fehlschlag Taste drücken |
| `del <Nr>` | Schritt löschen |
| `clear` | Alle Schritte löschen |
| `show` | Aktuelle Schritte anzeigen |
| `fertig` | Phase abschließen |
| `abbruch` | Editor abbrechen |

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
[START: 3] > fertig

[Loop 1: 0] > 3 30-45      # Punkt 3 klicken, 30-45s zufällig warten
[Loop 1: 1] > scan items   # Item-Scan "items" ausführen
[Loop 1: 2] > wait 10-15   # 10-15s zufällig warten ohne Klick
[Loop 1: 3] > 4 gone       # Warten bis Farbe verschwindet, dann Punkt 4 klicken
[Loop 1: 4] > fertig

Zyklen: 10                 # 10 Durchläufe

[END: 0] > 5 0             # Am Ende: Punkt 5 klicken (z.B. Logout)
[END: 1] > key enter       # Enter drücken
[END: 2] > fertig
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

Das Item-Scan System erkennt Items anhand ihrer Marker-Farben:

1. **Slots erstellen** (`CTRL+ALT+N` → Menü 1): Bereiche wo Items erscheinen können
2. **Items lernen** (`CTRL+ALT+N` → Menü 2): Mit `learn <Nr>` Marker-Farben von Slot scannen
3. **Scan konfigurieren** (`CTRL+ALT+N` → Menü 3): Slots und Items verknüpfen
4. **In Sequenz nutzen**: `scan <Name>` oder `scan <Name> all`

### Ablauf

- `scan items` → Scannt alle Slots, klickt das Item mit bester Priorität
- `scan items all` → Scannt alle Slots, klickt ALLE erkannten Items

## Bedingte Logik (ELSE)

Für Schritte mit Bedingungen (Scan, Pixel-Trigger) können Fallback-Aktionen definiert werden:

### ELSE-Syntax

| Befehl | Beschreibung |
|--------|--------------|
| `else skip` | Schritt überspringen, Sequenz fortsetzen |
| `else <Nr>` | Anderen Punkt klicken |
| `else <Nr> <Sek>` | Warten, dann anderen Punkt klicken |
| `else key <Taste>` | Taste drücken |

### Beispiele

```
scan items else skip           # Wenn kein Item: überspringen
scan items else 2              # Wenn kein Item: Punkt 2 klicken
scan items else 2 5            # Wenn kein Item: 5s warten, dann Punkt 2 klicken
1 pixel else skip              # Wenn Timeout: überspringen
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
  "min_markers_required": 2
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

## Dateistruktur

```
Autoclicker-Idleclans/
├── autoclicker.py      # Hauptprogramm
├── config.json         # Konfiguration (auto-generiert)
├── README.md           # Diese Datei
├── sequences/          # Gespeicherte Sequenzen
│   ├── points.json     # Aufgenommene Punkte
│   └── *.json          # Sequenz-Dateien
├── slots/              # Slot-Definitionen
│   ├── slots.json      # Gespeicherte Slots
│   └── *.png           # Screenshots und Vorschauen
├── items/              # Item-Profile
│   └── items.json      # Gespeicherte Items
├── item_scans/         # Item-Scan Konfigurationen
│   └── *.json          # Scan-Konfigurationen
└── tools/              # Hilfs-Skripte
    ├── create_slots.py # Manuelles Slot-Erstellen
    └── detect_slots.py # Standalone Slot-Erkennung
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

## Lizenz

MIT License
