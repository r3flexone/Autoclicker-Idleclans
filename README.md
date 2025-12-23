# Autoclicker for Idle Clans

Ein Windows-Autoclicker mit Sequenz-Unterstützung, Farberkennung und Item-Scan System.

## Features

- **Punkte aufnehmen**: Mausposition speichern mit automatischer Benennung
- **Sequenzen erstellen**: Punkte mit Wartezeiten oder Farb-Triggern verknüpfen
- **Mehrphasen-System**:
  - **START**: Wird einmal pro Zyklus ausgeführt
  - **LOOP-Phasen**: Mehrere Loops möglich, jeweils mit eigenen Wiederholungen
- **Farb-Trigger**: Warte bis eine bestimmte Farbe erscheint, dann klicke
- **Item-Scan System**: Items anhand von Marker-Farben erkennen und priorisieren
- **Konfigurierbar**: Toleranzen und Einstellungen via `config.json`
- **Persistenz**: Alle Daten werden als JSON gespeichert
- **Fail-Safe**: Maus in obere linke Ecke bewegen stoppt den Klicker

## Voraussetzungen

- Windows 10/11
- Python 3.10+
- **Optional**: Pillow für Farberkennung (`pip install pillow`)

## Installation

```bash
git clone https://github.com/r3flexone/Autoclicker-Idleclans.git
cd Autoclicker-Idleclans
pip install pillow  # Optional, für Farberkennung
python autoclicker.py
```

## Hotkeys

| Hotkey | Funktion |
|--------|----------|
| `CTRL+ALT+A` | Aktuelle Mausposition als Punkt speichern |
| `CTRL+ALT+U` | Letzten Punkt entfernen (Undo) |
| `CTRL+ALT+C` | Alle Punkte löschen |
| `CTRL+ALT+X` | Factory Reset (Punkte + Sequenzen löschen) |
| `CTRL+ALT+E` | Sequenz-Editor öffnen |
| `CTRL+ALT+N` | Item-Scan Editor (Items erkennen) |
| `CTRL+ALT+L` | Gespeicherte Sequenz laden |
| `CTRL+ALT+P` | Punkte anzeigen/testen/umbenennen |
| `CTRL+ALT+T` | Farb-Analysator |
| `CTRL+ALT+S` | Start/Stop der aktiven Sequenz |
| `CTRL+ALT+Q` | Programm beenden |

## Sequenz-Editor (`CTRL+ALT+E`)

### Editor-Befehle

| Befehl | Beschreibung |
|--------|--------------|
| `<Nr> <Zeit>` | Warte X Sekunden, dann klicke Punkt (z.B. `1 30`) |
| `<Nr> 0` | Sofort klicken ohne Wartezeit |
| `<Nr> pixel` | Warte auf Farbe, dann klicke |
| `<Nr> <Zeit> pixel` | Warte X Sek, dann auf Farbe warten, dann klicke |
| `wait <Zeit>` | Nur warten, KEIN Klick |
| `wait pixel` | Auf Farbe warten, KEIN Klick |
| `scan <Name>` | Item-Scan ausführen, bestes Item klicken |
| `scan <Name> all` | Item-Scan ausführen, ALLE Items klicken |
| `del <Nr>` | Schritt löschen |
| `clear` | Alle Schritte löschen |
| `show` | Aktuelle Schritte anzeigen |
| `fertig` | Phase abschließen |
| `abbruch` | Editor abbrechen |

### Beispiel-Sequenz

```
[START: 0] > 1 5           # Punkt 1 klicken, 5s warten
[START: 1] > 2 pixel       # Warten bis Farbe erscheint, dann Punkt 2 klicken
[START: 2] > fertig

[Loop 1: 0] > 3 30         # Punkt 3 klicken, 30s warten
[Loop 1: 1] > scan items   # Item-Scan "items" ausführen
[Loop 1: 2] > wait 10      # 10s warten ohne Klick
[Loop 1: 3] > fertig
```

## Item-Scan System (`CTRL+ALT+N`)

Das Item-Scan System erkennt Items anhand ihrer Marker-Farben:

1. **Slots definieren**: Bereiche wo Items erscheinen können
2. **Item-Profile erstellen**: Marker-Farben + Priorität (1 = beste)
3. **In Sequenz nutzen**: `scan <Name>` oder `scan <Name> all`

### Ablauf

- `scan items` → Scannt alle Slots, klickt das Item mit bester Priorität
- `scan items all` → Scannt alle Slots, klickt ALLE erkannten Items

## Konfiguration (`config.json`)

Wird beim ersten Start automatisch erstellt:

```json
{
  "clicks_per_point": 1,
  "max_total_clicks": null,
  "failsafe_enabled": true,
  "color_tolerance": 40,
  "pixel_wait_tolerance": 15,
  "pixel_wait_timeout": 60,
  "pixel_check_interval": 0.5,
  "debug_detection": true
}
```

| Option | Beschreibung |
|--------|--------------|
| `color_tolerance` | Toleranz für Item-Scan (höher = toleranter) |
| `pixel_wait_tolerance` | Toleranz für Pixel-Trigger (niedriger = genauer) |
| `pixel_wait_timeout` | Timeout in Sekunden für Farb-Trigger |
| `pixel_check_interval` | Wie oft auf Farbe prüfen (Sekunden) |
| `debug_detection` | Debug-Ausgaben für Farberkennung |

## Dateistruktur

```
Autoclicker-Idleclans/
├── autoclicker.py      # Hauptprogramm
├── config.json         # Konfiguration (auto-generiert)
├── README.md           # Diese Datei
├── sequences/          # Gespeicherte Sequenzen
│   ├── points.json     # Aufgenommene Punkte
│   └── *.json          # Sequenz-Dateien
└── item_scans/         # Item-Scan Konfigurationen
    └── *.json          # Item-Scan-Dateien
```

## Technische Details

- Windows API via `ctypes` (keine externen Abhängigkeiten für Basis-Funktionen)
- Pillow für Screenshot und Farberkennung (optional)
- Globale Hotkeys über `RegisterHotKey`
- Mausklicks über `SendInput`
- Thread-basierte Ausführung
- JSON-Persistenz

## Lizenz

MIT License
