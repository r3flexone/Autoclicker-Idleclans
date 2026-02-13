"""
Hilfsfunktionen für den Autoclicker.
JSON-Handling, Input-Funktionen, Zeit-Parser, etc.
"""

import ctypes
import json
import logging
import msvcrt
import os
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


def is_cancel(value: str) -> bool:
    """Prüft ob die Eingabe ein Abbruch-Befehl ist.

    Akzeptiert: cancel, abbruch, q, quit (case-insensitive).
    """
    return value.strip().lower() in ("cancel", "abbruch", "q", "quit")


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


# =============================================================================
# ANSI-SUPPORT UND PFEILTASTEN-NAVIGATION
# =============================================================================

def _enable_ansi() -> bool:
    """Aktiviert ANSI-Escape-Codes in der Windows-Konsole.

    Nötig für Cursor-Bewegung (hoch/runter) beim Menü-Neuzeichnen.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        STD_OUTPUT_HANDLE = -11
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
        return True
    except (AttributeError, OSError):
        return False

# Beim Import einmalig aktivieren
_ANSI_ENABLED = _enable_ansi()


def read_key() -> str:
    """Liest einen einzelnen Tastendruck (blockierend).

    Behandelt Pfeiltasten (2-Byte-Sequenz auf Windows) korrekt.

    Returns:
        'up', 'down', 'left', 'right', 'enter', 'escape',
        'backspace', oder das gedrückte Zeichen als String.
    """
    byte = msvcrt.getch()

    # Pfeiltasten und andere erweiterte Tasten (0xE0 oder 0x00 Prefix)
    if byte in (b'\xe0', b'\x00'):
        next_byte = msvcrt.getch()
        if next_byte == b'H':
            return 'up'
        elif next_byte == b'P':
            return 'down'
        elif next_byte == b'K':
            return 'left'
        elif next_byte == b'M':
            return 'right'
        return 'unknown'

    if byte == b'\r':
        return 'enter'
    if byte == b'\x1b':
        return 'escape'
    if byte == b'\x08':
        return 'backspace'

    # Normales Zeichen
    try:
        return byte.decode('utf-8')
    except UnicodeDecodeError:
        return 'unknown'


def interactive_select(options: list[str], title: str = "",
                       allow_cancel: bool = True) -> int:
    """Interaktive Menü-Auswahl mit Pfeiltasten.

    Navigation:
        Hoch/Runter  - Auswahl bewegen
        Enter/Rechts - Bestätigen
        Escape/Links - Abbrechen (gibt -1 zurück)
        0-9          - Direkte Nummern-Eingabe

    Args:
        options: Liste der Optionen (werden als Text angezeigt)
        title: Optionaler Titel über dem Menü
        allow_cancel: Ob Escape/Links erlaubt ist

    Returns:
        Index der gewählten Option (0-basiert), oder -1 bei Abbruch.
    """
    if not options:
        return -1

    if not _ANSI_ENABLED:
        # Fallback: Klassische Nummern-Eingabe
        return _fallback_select(options, title, allow_cancel)

    selected = 0
    num_options = len(options)

    flush_input_buffer()

    # Titel anzeigen
    if title:
        print(title)

    # Hilfe-Zeile
    cancel_hint = ", Esc=Abbruch" if allow_cancel else ""
    print(f"  (Pfeiltasten: navigieren, Enter: wählen{cancel_hint})")

    # Menü initial zeichnen
    _draw_menu(options, selected)

    while True:
        key = read_key()

        if key == 'up':
            selected = (selected - 1) % num_options
        elif key == 'down':
            selected = (selected + 1) % num_options
        elif key in ('enter', 'right'):
            _clear_menu_lines(num_options)
            print(f"  > {options[selected]}")
            return selected
        elif key in ('escape', 'left') and allow_cancel:
            _clear_menu_lines(num_options)
            print("  (Abgebrochen)")
            return -1
        elif key.isdigit():
            # Direkte Nummern-Eingabe (1-basiert)
            num = int(key)
            if 1 <= num <= num_options:
                _clear_menu_lines(num_options)
                print(f"  > {options[num - 1]}")
                return num - 1
            elif num == 0 and allow_cancel:
                _clear_menu_lines(num_options)
                print("  (Abgebrochen)")
                return -1
            continue
        else:
            continue

        # Menü neu zeichnen
        _clear_menu_lines(num_options)
        _draw_menu(options, selected)


def _draw_menu(options: list[str], selected: int) -> None:
    """Zeichnet das Menü mit Auswahl-Markierung."""
    for i, opt in enumerate(options):
        if i == selected:
            print(f"  \033[7m {i+1}. {opt} \033[0m")  # Invertiert (highlighted)
        else:
            print(f"   {i+1}. {opt}")


def _clear_menu_lines(num_lines: int) -> None:
    """Bewegt den Cursor num_lines nach oben und löscht jede Zeile."""
    for _ in range(num_lines):
        print(f"\033[A\033[2K", end="", flush=True)


def _fallback_select(options: list[str], title: str,
                     allow_cancel: bool) -> int:
    """Fallback-Auswahl ohne ANSI (klassische Nummern-Eingabe)."""
    if title:
        print(title)
    for i, opt in enumerate(options):
        print(f"  [{i+1}] {opt}")
    if allow_cancel:
        print("  [0] Abbrechen")

    while True:
        try:
            choice = safe_input("> ").strip()
            if is_cancel(choice):
                return -1
            num = int(choice)
            if 1 <= num <= len(options):
                return num - 1
            if num == 0 and allow_cancel:
                return -1
            print(f"  -> Ungültig! (1-{len(options)})")
        except ValueError:
            print("  -> Bitte eine Nummer eingeben")


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


def parse_time_input(time_str: str) -> tuple[float, str, float | None]:
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
        (sekunden: float, beschreibung: str, zielzeit_timestamp: float | None)
        - zielzeit_timestamp: Absolute Zielzeit bei Uhrzeiten (HH:MM, HHMM), sonst None
        Bei Fehler: (-1, fehlermeldung, None)
    """
    time_str = time_str.strip().lower()

    # Leere Eingabe
    if not time_str:
        return (-1, "Keine Zeit angegeben", None)

    # Relative Zeit mit + Präfix: +30m, +2h, +2 (ohne Einheit = Minuten)
    has_plus_prefix = time_str.startswith("+")
    if has_plus_prefix:
        time_str = time_str[1:]

    # Hilfsfunktion für Uhrzeiten (vermeidet Code-Duplizierung)
    def calculate_time_to_target(hour: int, minute: int) -> tuple[float, str, float]:
        """Berechnet Sekunden bis zur Zielzeit und gibt (seconds, description, timestamp) zurück."""
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # Wenn Zielzeit bereits vorbei ist, nimm morgen
        if target <= now:
            target += timedelta(days=1)
            day_str = "morgen"
        else:
            day_str = "heute"

        seconds = (target - now).total_seconds()
        target_timestamp = target.timestamp()

        # Debug-Info
        print(f"[DEBUG] Jetzt: {now.strftime('%H:%M:%S')} | Ziel: {target.strftime('%Y-%m-%d %H:%M:%S')} | Sekunden: {seconds:.0f}")

        return (seconds, f"{day_str} um {hour:02d}:{minute:02d}", target_timestamp)

    # Format: HH:MM (Uhrzeit mit Doppelpunkt)
    if ":" in time_str:
        try:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0

            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return (-1, f"Ungültige Uhrzeit: {time_str}", None)

            return calculate_time_to_target(hour, minute)
        except ValueError:
            return (-1, f"Ungültiges Zeitformat: {time_str}", None)

    # Format: HHMM (4-stellige Uhrzeit ohne Doppelpunkt, 0000-2359)
    if time_str.isdigit() and len(time_str) == 4:
        try:
            hour = int(time_str[:2])
            minute = int(time_str[2:])

            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return (-1, f"Ungültige Uhrzeit: {time_str} (gültig: 0000-2359)", None)

            return calculate_time_to_target(hour, minute)
        except ValueError:
            return (-1, f"Ungültiges Zeitformat: {time_str}", None)

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
            return (-1, f"Einheit fehlt! Nutze z.B. '{time_str}s', '{time_str}m' oder '{time_str}h'", None)

        value = float(value_str)

        if value < 0:
            return (-1, "Zeit muss positiv sein", None)

        if unit == "h":
            seconds = value * 3600
            desc = f"{value:.0f}h" if value == int(value) else f"{value}h"
        elif unit == "m":
            seconds = value * 60
            desc = f"{value:.0f}m" if value == int(value) else f"{value}m"
        else:
            seconds = value
            desc = f"{value:.0f}s" if value == int(value) else f"{value}s"

        # Relative Zeiten haben keine absolute Zielzeit
        return (seconds, desc, None)
    except ValueError:
        return (-1, f"Ungültige Zahl: {time_str}", None)


def format_duration(seconds: float) -> str:
    """Formatiert Sekunden als hh:mm:ss oder mm:ss."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
