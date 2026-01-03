# Autoclicker Module

Diese Verzeichnisstruktur enthält die modulare Aufteilung des Autoclickers.

## Modulstruktur

```
autoclicker/
├── __init__.py       # Paket-Initialisierung
├── config.py         # Konfiguration (config.json)
├── models.py         # Datenklassen (ClickPoint, Sequence, etc.)
├── winapi.py         # Windows API (Maus, Tastatur, Hotkeys)
├── utils.py          # Hilfsfunktionen (JSON, Input, Zeit)
├── imaging.py        # Bildverarbeitung (Screenshots, Farben)
├── persistence.py    # Speichern/Laden (Sequenzen, Slots, Items)
├── execution.py      # Sequenz-Ausführung
├── handlers.py       # Hotkey-Handler
└── editors/
    ├── __init__.py
    ├── slot_editor.py     # Slot-Editor
    ├── item_editor.py     # Item-Editor
    ├── sequence_editor.py # Sequenz-Editor
    └── item_scan_editor.py # Item-Scan-Editor
```

## Module im Detail

### config.py
- `DEFAULT_CONFIG` - Standard-Konfiguration
- `load_config()` - Lädt config.json
- `save_config()` - Speichert config.json
- `CONFIG` - Globale Konfiguration

### models.py
- `ClickPoint` - Klickpunkt mit x,y Koordinaten
- `SequenceStep` - Schritt in einer Sequenz
- `LoopPhase` - Loop-Phase mit Wiederholungen
- `Sequence` - Vollständige Klick-Sequenz
- `ItemProfile` - Item-Definition
- `ItemSlot` - Slot-Definition
- `ItemScanConfig` - Item-Scan Konfiguration
- `AutoClickerState` - Globaler Zustand

### winapi.py
- Hotkey-Konstanten (VK_A, VK_S, etc.)
- Windows-Strukturen (INPUT, MOUSEINPUT, etc.)
- `get_cursor_pos()` - Mausposition lesen
- `set_cursor_pos()` - Maus bewegen
- `send_click()` - Mausklick senden
- `send_key()` - Tastendruck senden
- `check_failsafe()` - Fail-Safe prüfen
- `register_hotkeys()` / `unregister_hotkeys()`

### utils.py
- `sanitize_filename()` - Sichere Dateinamen
- `compact_json()` - Kompakte JSON-Formatierung
- `safe_input()` - Sicherer Input
- `confirm()` - Ja/Nein-Bestätigung
- `parse_time_input()` - Zeit-Parser
- `format_duration()` - Dauer formatieren

### imaging.py
- `get_pixel_color()` - Pixel-Farbe lesen
- `take_screenshot()` - Screenshot aufnehmen
- `find_color_in_image()` - Farbe suchen
- `match_template_in_image()` - Template-Matching
- `run_color_analyzer()` - Farb-Analysator
- `select_region()` - Region auswählen

### persistence.py
- `save_data()` / `load_points()` - Punkte
- `save_item_scan()` / `load_item_scan_file()` - Item-Scans
- `save_global_slots()` / `load_global_slots()` - Slots
- `save_global_items()` / `load_global_items()` - Items
- Preset-Funktionen für Slots und Items

## Migration

Die Editor-Module (editors/) enthalten momentan Stub-Funktionen,
die auf das Hauptskript `autoclicker.py` verweisen.

Um die vollständige Migration abzuschließen, müssen die entsprechenden
Funktionen aus `autoclicker.py` in die Editor-Module verschoben werden.

## Verwendung

```python
from autoclicker import CONFIG, AutoClickerState
from autoclicker.winapi import send_click, get_cursor_pos
from autoclicker.persistence import save_data, load_points
```
