"""
Hilfsfunktionen für den Autoclicker.
JSON-Handling, Input-Funktionen, Zeit-Parser, etc.
"""

import json
import logging
import msvcrt
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AutoClickerState

# Logger
logger = logging.getLogger("autoclicker")


def set_log_level(level: str) -> None:
    """Setzt das Log-Level. Optionen: DEBUG, INFO, WARNING, ERROR"""
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR
    }
    if level.upper() in levels:
        for handler in logger.handlers:
            handler.setLevel(levels[level.upper()])
        logger.debug(f"Log-Level auf {level.upper()} gesetzt")


def sanitize_filename(name: str) -> str:
    """Bereinigt einen Namen für sichere Dateinamen.

    Entfernt/ersetzt unsichere Zeichen wie ../, \\, :, *, ?, ", <, >, |
    """
    # Entferne Path-Traversal-Versuche
    name = name.replace("..", "").replace("/", "_").replace("\\", "_")
    # Entferne Windows-unsichere Zeichen
    name = re.sub(r'[<>:"|?*]', '', name)
    # Leerzeichen zu Unterstrichen
    name = name.replace(' ', '_')
    # Nur alphanumerische Zeichen, Unterstriche und Bindestriche erlauben
    name = re.sub(r'[^\w\-]', '', name)
    # Leere Namen verhindern
    if not name:
        name = "unnamed"
    return name.lower()


def compact_json(data: dict, indent: int = 2) -> str:
    """Formatiert JSON mit kompakten Arrays (Koordinaten/Farben auf einer Zeile).

    Wandelt:
        [
            55,
            15,
            50
        ]
    zu:
        [55, 15, 50]
    """
    json_str = json.dumps(data, indent=indent, ensure_ascii=False)
    # Regex: Finde Arrays die nur Zahlen enthalten und über mehrere Zeilen gehen
    # Pattern: [ gefolgt von Whitespace/Newlines, dann Zahlen mit Kommas, dann ]
    pattern = r'\[\s*\n\s*(\d+),\s*\n\s*(\d+),\s*\n\s*(\d+)\s*\n\s*\]'
    json_str = re.sub(pattern, r'[\1, \2, \3]', json_str)
    # Auch für 2er-Arrays (x, y Koordinaten)
    pattern2 = r'\[\s*\n\s*(\d+),\s*\n\s*(\d+)\s*\n\s*\]'
    json_str = re.sub(pattern2, r'[\1, \2]', json_str)
    return json_str


def save_json(filepath: str, data: dict) -> bool:
    """Speichert JSON mit kompakter Formatierung."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(compact_json(data))
        return True
    except IOError as e:
        print(f"[FEHLER] Konnte nicht speichern: {filepath} - {e}")
        return False


def load_json_file(filepath: Path, default=None):
    """Lädt JSON-Datei sicher mit Fallback."""
    try:
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return default


def flush_input_buffer() -> None:
    """Leert den Tastatur-Input-Buffer (entfernt gepufferte Tastendrücke)."""
    while msvcrt.kbhit():
        msvcrt.getch()


def safe_input(prompt: str = "") -> str:
    """Sicherer Input der UnicodeDecodeError abfängt."""
    flush_input_buffer()  # Buffer leeren vor Input
    try:
        return input(prompt)
    except UnicodeDecodeError:
        # Sonderzeichen im Buffer (z.B. ESC) - ignorieren und leeren String zurückgeben
        flush_input_buffer()
        return ""


def confirm(message: str, default: bool = False) -> bool:
    """Fragt Benutzer nach Bestätigung (j/n)."""
    suffix = " (J/n): " if default else " (j/N): "
    response = safe_input(message + suffix).strip().lower()
    if not response:
        return default
    return response in ("j", "ja", "y", "yes")


def get_input(prompt: str = "> ", allow_empty: bool = True) -> str:
    """Liest Benutzereingabe mit Strip."""
    value = safe_input(prompt).strip()
    if not allow_empty and not value:
        return ""
    return value


def clear_line() -> None:
    """Löscht die aktuelle Konsolenzeile."""
    print("\r" + " " * 80 + "\r", end="", flush=True)


def wait_while_paused(state: 'AutoClickerState', message: str) -> bool:
    """
    Wartet solange pausiert ist. Gibt False zurück wenn gestoppt wurde.

    Args:
        state: AutoClickerState
        message: Nachricht die während der Pause angezeigt wird

    Returns:
        True wenn fortgesetzt, False wenn gestoppt
    """
    pause_interval = state.config.get("pause_check_interval", 0.5)
    while state.pause_event.is_set() and not state.stop_event.is_set():
        clear_line()
        print(f"[PAUSE] {message} | Fortsetzen: CTRL+ALT+G", end="", flush=True)
        time.sleep(pause_interval)
    return not state.stop_event.is_set()


def parse_time_input(time_str: str) -> tuple[float, str]:
    """Parst Zeit-Eingaben in verschiedenen Formaten.

    Unterstützte Formate:
        14:30       → Sekunden bis 14:30 Uhr (heute oder morgen)
        1430        → Sekunden bis 14:30 Uhr (4-stellig, 0000-2359)
        30s         → 30 Sekunden
        30m, 30min  → 30 Minuten
        2h, 2std    → 2 Stunden
        +30m        → In 30 Minuten (relativ)
        +2          → In 2 Minuten (+ ohne Einheit = Minuten)

    Returns:
        (sekunden: float, beschreibung: str)
        Bei Fehler: (-1, fehlermeldung)
    """
    time_str = time_str.strip().lower()

    # Leere Eingabe
    if not time_str:
        return (-1, "Keine Zeit angegeben")

    # Relative Zeit mit + Präfix: +30m, +2h, +2 (ohne Einheit = Minuten)
    has_plus_prefix = time_str.startswith("+")
    if has_plus_prefix:
        time_str = time_str[1:]

    # Format: HH:MM (Uhrzeit mit Doppelpunkt)
    if ":" in time_str:
        try:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0

            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return (-1, f"Ungültige Uhrzeit: {time_str}")

            now = datetime.now()
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # Wenn Zielzeit bereits vorbei ist, nimm morgen
            if target <= now:
                target += timedelta(days=1)
                day_str = "morgen"
            else:
                day_str = "heute"

            seconds = (target - now).total_seconds()

            # Debug-Info (wird immer gezeigt bei Uhrzeiten um Bugs zu finden)
            print(f"[DEBUG] Jetzt: {now.strftime('%H:%M:%S')} | Ziel: {target.strftime('%Y-%m-%d %H:%M:%S')} | Sekunden: {seconds:.0f}")

            return (seconds, f"{day_str} um {hour:02d}:{minute:02d}")
        except ValueError:
            return (-1, f"Ungültiges Zeitformat: {time_str}")

    # Format: HHMM (4-stellige Uhrzeit ohne Doppelpunkt, 0000-2359)
    if time_str.isdigit() and len(time_str) == 4:
        try:
            hour = int(time_str[:2])
            minute = int(time_str[2:])

            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return (-1, f"Ungültige Uhrzeit: {time_str} (gültig: 0000-2359)")

            now = datetime.now()
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # Wenn Zielzeit bereits vorbei ist, nimm morgen
            if target <= now:
                target += timedelta(days=1)
                day_str = "morgen"
            else:
                day_str = "heute"

            seconds = (target - now).total_seconds()

            # Debug-Info
            print(f"[DEBUG] Jetzt: {now.strftime('%H:%M:%S')} | Ziel: {target.strftime('%Y-%m-%d %H:%M:%S')} | Sekunden: {seconds:.0f}")

            return (seconds, f"{day_str} um {hour:02d}:{minute:02d}")
        except ValueError:
            return (-1, f"Ungültiges Zeitformat: {time_str}")

    # Format: Zahl mit Einheit (30s, 30m, 30min, 2h, 2std)
    # Bei + Präfix ohne Einheit: Default = Minuten
    try:
        unit = None
        value_str = time_str

        if time_str.endswith("std"):
            unit = "h"
            value_str = time_str[:-3]
        elif time_str.endswith("min"):
            unit = "m"
            value_str = time_str[:-3]
        elif time_str.endswith("h"):
            unit = "h"
            value_str = time_str[:-1]
        elif time_str.endswith("m"):
            unit = "m"
            value_str = time_str[:-1]
        elif time_str.endswith("s"):
            unit = "s"
            value_str = time_str[:-1]
        elif has_plus_prefix:
            # + Präfix ohne Einheit = Minuten
            unit = "m"
        else:
            # Keine Einheit und kein + Präfix = Fehler
            return (-1, f"Einheit fehlt! Nutze z.B. '{time_str}s', '{time_str}m' oder '{time_str}h'")

        value = float(value_str)

        if value < 0:
            return (-1, "Zeit muss positiv sein")

        if unit == "h":
            seconds = value * 3600
            desc = f"{value:.0f}h" if value == int(value) else f"{value}h"
        elif unit == "m":
            seconds = value * 60
            desc = f"{value:.0f}m" if value == int(value) else f"{value}m"
        else:
            seconds = value
            desc = f"{value:.0f}s" if value == int(value) else f"{value}s"

        return (seconds, desc)
    except ValueError:
        return (-1, f"Ungültige Zahl: {time_str}")


def format_duration(seconds: float) -> str:
    """Formatiert Sekunden als hh:mm:ss oder mm:ss."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
