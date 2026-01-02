"""
Konfiguration für den Autoclicker.
Lädt und speichert config.json mit Standard-Werten.
"""

import json
import logging
from pathlib import Path
from typing import Optional

# Logger
logger = logging.getLogger("autoclicker")

# =============================================================================
# KONFIGURATION
# =============================================================================
CONFIG_FILE = "config.json"
SEQUENCES_DIR: str = "sequences"       # Ordner für gespeicherte Sequenzen
CONFIGS_DIR: str = "configs"           # Ordner für Config-Presets

# Standard-Konfiguration (wird von config.json überschrieben)
# Die Reihenfolge hier bestimmt die Reihenfolge in der gespeicherten config.json
DEFAULT_CONFIG = {
    # === KLICK-EINSTELLUNGEN ===
    "clicks_per_point": 1,              # Anzahl Klicks pro Punkt
    "max_total_clicks": None,           # None = unendlich
    "click_move_delay": 0.01,           # Pause zwischen Mausbewegung und Klick (Sekunden)
    "post_click_delay": 0.05,           # Pause NACH dem Klick bevor Maus weiterbewegt werden darf (Sekunden)

    # === SICHERHEIT ===
    "failsafe_enabled": True,           # Fail-Safe: Maus in Ecke stoppt alles
    "failsafe_x": 5,                    # Fail-Safe X-Bereich (Maus x <= Wert)
    "failsafe_y": 5,                    # Fail-Safe Y-Bereich (Maus y <= Wert)

    # === FARB-/PIXEL-ERKENNUNG ===
    "color_tolerance": 0,               # Farbtoleranz für Item-Scan (0 = exakt)
    "pixel_wait_tolerance": 10,         # Toleranz für Pixel-Trigger (10 = kleine Abweichungen OK)
    "pixel_wait_timeout": 300,          # Timeout für Pixel-Trigger in Sekunden (5 Min)
    "pixel_check_interval": 1,          # Prüf-Intervall für Farbe in Sekunden
    "scan_pixel_step": 2,               # Pixel-Schrittweite bei Farbsuche (1=genauer, 2=schneller)
    "show_pixel_delay": 0.3,            # Wie lange Pixel-Position angezeigt wird (Sekunden)

    # === ITEM-SCAN EINSTELLUNGEN ===
    "scan_reverse": False,              # True = Slots rückwärts scannen (4,3,2,1)
    "scan_slot_delay": 0.1,             # Pause zwischen Slot-Scans in Sekunden (0 = keine)
    "item_click_delay": 1.0,            # Pause nach Item-Klick in Sekunden
    "marker_count": 5,                  # Anzahl Marker-Farben beim Item-Lernen
    "require_all_markers": True,        # True = ALLE Marker müssen gefunden werden
    "min_markers_required": 2,          # Minimum Marker (nur wenn require_all_markers=False)
    "slot_hsv_tolerance": 25,           # HSV-Toleranz für Slot-Erkennung
    "slot_inset": 10,                   # Pixel-Einzug vom Slot-Rand
    "slot_color_distance": 25,          # Farbdistanz für Hintergrund-Ausschluss
    "default_min_confidence": 0.8,      # Standard-Konfidenz für Template-Matching (80%)
    "default_confirm_delay": 0.5,       # Standard-Wartezeit vor Bestätigungs-Klick (Sekunden)

    # === TIMING ===
    "pause_check_interval": 0.5,        # Prüf-Intervall während Pause (Sekunden)

    # === DEBUG-EINSTELLUNGEN ===
    "debug_mode": False,                # Zeigt Schritte VOR Start + wartet auf Enter
    "debug_detection": False,           # Alle Ausgaben persistent (nicht überschrieben)
    "show_pixel_position": False,       # Maus kurz zum Prüf-Pixel bewegen beim Start
    "debug_save_templates": False,      # Speichert Scan+Template in items/debug/ (für Template-Debugging)
}


def load_config() -> dict:
    """Lädt Konfiguration aus config.json oder erstellt Standard-Config."""
    config_path = Path(CONFIG_FILE)

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                # Merge mit Default-Config (falls neue Optionen hinzugefügt wurden)
                config = DEFAULT_CONFIG.copy()
                config.update(loaded)

                # Prüfe ob neue Optionen hinzugefügt wurden
                missing_keys = set(DEFAULT_CONFIG.keys()) - set(loaded.keys())
                if missing_keys:
                    save_config(config)
                    print(f"[CONFIG] Geladen + {len(missing_keys)} neue Option(en) ergänzt: {', '.join(missing_keys)}")
                else:
                    print(f"[CONFIG] Geladen aus {CONFIG_FILE}")
                return config
        except (json.JSONDecodeError, IOError) as e:
            print(f"[WARNUNG] Config konnte nicht geladen werden: {e}")
            print("[CONFIG] Verwende Standard-Konfiguration")
    else:
        # Erstelle Standard-Config-Datei
        save_config(DEFAULT_CONFIG)
        print(f"[CONFIG] Standard-Konfiguration erstellt: {CONFIG_FILE}")

    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Speichert Konfiguration in config.json (in sortierter Reihenfolge)."""
    try:
        # Sortiere nach DEFAULT_CONFIG Reihenfolge, dann unbekannte Keys am Ende
        ordered_config = {}
        for key in DEFAULT_CONFIG:
            if key in config:
                ordered_config[key] = config[key]
        # Füge unbekannte Keys am Ende hinzu (falls vorhanden)
        for key in config:
            if key not in ordered_config:
                ordered_config[key] = config[key]

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(ordered_config, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"[FEHLER] Config konnte nicht gespeichert werden: {e}")


# Konfiguration laden (wird beim Import ausgeführt)
CONFIG = load_config()

# Konfig-Werte als Variablen (für einfacheren Zugriff)
CLICKS_PER_POINT: int = CONFIG["clicks_per_point"]
MAX_TOTAL_CLICKS: Optional[int] = CONFIG["max_total_clicks"]
FAILSAFE_ENABLED: bool = CONFIG["failsafe_enabled"]
DEFAULT_MIN_CONFIDENCE: float = CONFIG["default_min_confidence"]
