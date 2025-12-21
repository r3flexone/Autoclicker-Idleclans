# Autoclicker for Idle Clans

Ein Windows-Autoclicker mit Sequenz-Unterstützung, speziell für das Spiel "Idle Clans" entwickelt.

## Features

- **Punkte aufnehmen**: Mausposition speichern mit automatischer Benennung (P1, P2, P3...)
- **Sequenzen erstellen**: Punkte mit individuellen Wartezeiten verknüpfen
- **Zwei-Phasen-System**:
  - **START**: Wird einmal am Anfang ausgeführt
  - **LOOP**: Wird wiederholt (unendlich oder X-mal)
- **Cycling**: Nach X Loop-Durchläufen automatisch zurück zu START
- **Persistenz**: Alle Punkte und Sequenzen werden als JSON gespeichert
- **Fail-Safe**: Maus in obere linke Ecke bewegen stoppt den Klicker

## Voraussetzungen

- Windows 10/11
- Python 3.10+ (nur Standardbibliothek, keine externen Pakete nötig)

## Installation

```bash
git clone https://github.com/r3flexone/Autoclicker-Idleclans.git
cd Autoclicker-Idleclans
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
| `CTRL+ALT+L` | Gespeicherte Sequenz laden |
| `CTRL+ALT+P` | Punkte anzeigen/testen/umbenennen |
| `CTRL+ALT+S` | Start/Stop der aktiven Sequenz |
| `CTRL+ALT+Q` | Programm beenden |

## Anleitung

### 1. Punkte aufnehmen

Bewege die Maus an die gewünschte Position und drücke `CTRL+ALT+A`. Der Punkt wird automatisch als P1, P2, P3... benannt.

### 2. Sequenz erstellen (`CTRL+ALT+E`)

Der Editor führt dich durch zwei Phasen:

**START-Phase** (wird einmal ausgeführt):
```
[START: 0] > 1 5      # Punkt 1 klicken, 5 Sekunden warten
[START: 1] > 2 3      # Punkt 2 klicken, 3 Sekunden warten
[START: 2] > fertig   # Phase abschließen
```

**LOOP-Phase** (wird wiederholt):
```
[LOOP: 0] > 3 60      # Punkt 3 klicken, 60 Sekunden warten
[LOOP: 1] > 1 30      # Punkt 1 klicken, 30 Sekunden warten
[LOOP: 2] > fertig    # Phase abschließen
```

**Loop-Einstellungen**:
```
Wie oft soll der Loop wiederholt werden?
  0 = Unendlich (manuell stoppen)
  >0 = Anzahl Durchläufe, dann zurück zu START

Anzahl Loops: 5
```

### 3. Sequenz starten (`CTRL+ALT+S`)

Die Sequenz läuft wie folgt ab:
1. START-Phase wird einmal ausgeführt
2. LOOP-Phase wird X-mal wiederholt (oder unendlich bei 0)
3. Bei max_loops > 0: Zurück zu Schritt 1 (Cycling)

### Editor-Befehle

| Befehl | Beschreibung |
|--------|--------------|
| `<Nr> <Zeit>` | Schritt hinzufügen (z.B. `1 30` = Punkt 1, 30s warten) |
| `del <Nr>` | Schritt löschen |
| `clear` | Alle Schritte löschen |
| `show` | Aktuelle Schritte anzeigen |
| `fertig` | Phase abschließen |
| `abbruch` | Editor abbrechen |

## Dateistruktur

```
Autoclicker-Idleclans/
├── autoclicker.py      # Hauptprogramm
├── README.md           # Diese Datei
└── sequences/          # Gespeicherte Daten (wird automatisch erstellt)
    ├── points.json     # Aufgenommene Punkte
    └── *.json          # Gespeicherte Sequenzen
```

## Beispiel: Idle Clans Farming

1. **Punkte aufnehmen**:
   - P1: Ressource 1 Position
   - P2: Ressource 2 Position
   - P3: Sammeln-Button

2. **Sequenz erstellen**:
   - START: Login-Klicks, initiale Navigation
   - LOOP: P1 (5s) → P2 (5s) → P3 (60s)
   - Max Loops: 10 (dann neu starten für Fresh Session)

## Technische Details

- Verwendet Windows API via `ctypes` (keine externen Abhängigkeiten)
- Globale Hotkeys über `RegisterHotKey`
- Mausklicks über `SendInput`
- Thread-basierte Ausführung für non-blocking Operation
- JSON-Persistenz für Punkte und Sequenzen

## Lizenz

MIT License
