#!/usr/bin/env python3
"""
Windows Autoclicker mit Sequenz-Unterstützung und Farberkennung
================================================================
Ein Autoclicker für Windows mit Sequenzen, Farb-Triggern und Item-Scan System.

Starten: python autoclicker.py
Beenden: CTRL+ALT+Q oder Konsole schließen

Hotkeys:
  CTRL+ALT+A  - Mausposition als Punkt speichern
  CTRL+ALT+U  - Letzten Punkt entfernen
  CTRL+ALT+C  - Alle Punkte löschen
  CTRL+ALT+X  - Factory Reset (Punkte + Sequenzen)
  CTRL+ALT+E  - Sequenz-Editor (Punkte + Zeiten/Farb-Trigger)
  CTRL+ALT+N  - Item-Scan Editor (Items erkennen + priorisieren)
  CTRL+ALT+L  - Gespeicherte Sequenz laden
  CTRL+ALT+P  - Punkte anzeigen/testen/umbenennen
  CTRL+ALT+T  - Farb-Analysator
  CTRL+ALT+S  - Start/Stop der aktiven Sequenz
  CTRL+ALT+Q  - Programm beenden

Features:
  - Mehrphasen-System: START + mehrere LOOP-Phasen
  - Farb-Trigger: Warte bis Farbe erscheint, dann klicke
  - Item-Scan: Items anhand von Marker-Farben erkennen
  - Konfigurierbar via config.json

Voraussetzungen:
  - Windows 10/11, Python 3.10+
  - Optional: pip install pillow (für Farberkennung)

Fail-Safe: Maus in obere linke Ecke (x<=2, y<=2) stoppt den Klicker.
"""

# DPI-Awareness MUSS vor allen anderen Imports stehen!
# Sonst cachen Windows-APIs falsche Koordinaten.
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except (AttributeError, OSError):
    # shcore nicht verfügbar (älteres Windows)
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Fallback für ältere Windows
    except (AttributeError, OSError):
        pass  # DPI-Awareness nicht unterstützt

import ctypes.wintypes as wintypes
import threading
import time
import sys
import os
import json
import shutil
import random
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, Callable
from pathlib import Path

# =============================================================================
# LOGGING SETUP (muss vor optionalen Imports stehen!)
# =============================================================================
# Logger für strukturierte Ausgaben (Fehler, Warnungen, Debug)
# Interaktive Ausgaben (Fortschritt, Status) verwenden weiterhin print()
logger = logging.getLogger("autoclicker")
logger.setLevel(logging.DEBUG)

# Console Handler mit Format
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)  # Standard: INFO, DEBUG nur wenn aktiviert
_console_formatter = logging.Formatter('[%(levelname)s] %(message)s')
_console_handler.setFormatter(_console_formatter)
logger.addHandler(_console_handler)

# Bilderkennung (optional - nur wenn pillow installiert)
try:
    from PIL import Image, ImageGrab
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow nicht installiert. Bilderkennung deaktiviert.")
    logger.warning("Installieren mit: pip install pillow")

# NumPy für optimierte Farberkennung (optional)
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# OpenCV für Template Matching (optional)
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger.warning("OpenCV nicht installiert. Template Matching deaktiviert.")
    logger.warning("Installieren mit: pip install opencv-python")

def set_log_level(level: str) -> None:
    """Setzt das Log-Level. Optionen: DEBUG, INFO, WARNING, ERROR"""
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR
    }
    if level.upper() in levels:
        _console_handler.setLevel(levels[level.upper()])
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


def parse_time_input(time_str: str) -> tuple[float, str]:
    """Parst Zeit-Eingaben in verschiedenen Formaten.

    Unterstützte Formate:
        30, 30s     → 30 Sekunden
        30m, 30min  → 30 Minuten
        2h, 2std    → 2 Stunden
        14:30       → Sekunden bis 14:30 Uhr (heute oder morgen)
        +30m        → In 30 Minuten (relativ)
        +2          → In 2 Minuten (+ ohne Einheit = Minuten)

    Returns:
        (sekunden: float, beschreibung: str)
        Bei Fehler: (-1, fehlermeldung)
    """
    from datetime import datetime, timedelta

    time_str = time_str.strip().lower()

    # Leere Eingabe
    if not time_str:
        return (-1, "Keine Zeit angegeben")

    # Relative Zeit mit + Präfix: +30m, +2h, +2 (ohne Einheit = Minuten)
    has_plus_prefix = time_str.startswith("+")
    if has_plus_prefix:
        time_str = time_str[1:]

    # Format: HH:MM (Uhrzeit)
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
            return (seconds, f"{day_str} um {hour:02d}:{minute:02d}")
        except ValueError:
            return (-1, f"Ungültiges Zeitformat: {time_str}")

    # Format: Zahl mit optionaler Einheit (30, 30s, 30m, 30min, 2h, 2std)
    try:
        # Einheit extrahieren
        # Bei + Präfix ohne Einheit: Default = Minuten (für Zeitplan sinnvoller)
        unit = "m" if has_plus_prefix else "s"
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

    # === SICHERHEIT ===
    "failsafe_enabled": True,           # Fail-Safe: Maus in Ecke stoppt alles
    "failsafe_x": 5,                    # Fail-Safe X-Bereich (Maus x <= Wert)
    "failsafe_y": 5,                    # Fail-Safe Y-Bereich (Maus y <= Wert)

    # === FARB-/PIXEL-ERKENNUNG ===
    "color_tolerance": 0,               # Farbtoleranz für Item-Scan (0 = exakt)
    "pixel_wait_tolerance": 10,         # Toleranz für Pixel-Trigger (10 = kleine Abweichungen OK)
    "pixel_wait_timeout": 300,          # Timeout für Pixel-Trigger in Sekunden (5 Min)
    "pixel_check_interval": 1,          # Prüf-Intervall für Farbe in Sekunden

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

# Konfiguration laden
CONFIG = load_config()

# Konfig-Werte als Variablen (für einfacheren Zugriff)
CLICKS_PER_POINT: int = CONFIG["clicks_per_point"]
MAX_TOTAL_CLICKS: Optional[int] = CONFIG["max_total_clicks"]
FAILSAFE_ENABLED: bool = CONFIG["failsafe_enabled"]
DEFAULT_MIN_CONFIDENCE: float = CONFIG["default_min_confidence"]

# =============================================================================
# WINDOWS API KONSTANTEN
# =============================================================================
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000

# Virtual Key Codes
VK_A = 0x41  # Add Point
VK_U = 0x55  # Undo
VK_C = 0x43  # Clear all points
VK_X = 0x58  # Reset all (points + sequences) - X statt R (R oft belegt)
VK_E = 0x45  # Editor
VK_N = 0x4E  # Item-Scan Editor (N für New/Scan)
VK_L = 0x4C  # Load
VK_P = 0x50  # Print/Show
VK_S = 0x53  # Start/Stop
VK_T = 0x54  # Test colors (Farb-Analysator)
VK_Q = 0x51  # Quit
VK_G = 0x47  # Pause/Resume (G statt R wegen Konflikten)
VK_K = 0x4B  # Skip current wait
VK_W = 0x57  # Quick-Switch (Wechseln)
VK_Z = 0x5A  # Schedule (Zeitplan)

# Hotkey IDs
HOTKEY_RECORD = 1
HOTKEY_UNDO = 2
HOTKEY_CLEAR = 3
HOTKEY_RESET = 4
HOTKEY_EDITOR = 5
HOTKEY_ITEM_SCAN = 6
HOTKEY_LOAD = 7
HOTKEY_SHOW = 8
HOTKEY_TOGGLE = 9
HOTKEY_ANALYZE = 10
HOTKEY_QUIT = 11
HOTKEY_PAUSE = 12
HOTKEY_SKIP = 13
HOTKEY_SWITCH = 14
HOTKEY_SCHEDULE = 15

# Window Messages
WM_HOTKEY = 0x0312

# Mouse Input
INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

# Keyboard Input
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

# Häufige Virtual Key Codes für Tastatureingaben
VK_CODES = {
    "enter": 0x0D, "return": 0x0D,
    "tab": 0x09,
    "space": 0x20, "leertaste": 0x20,
    "escape": 0x1B, "esc": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E, "del": 0x2E,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
    "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
    "f11": 0x7A, "f12": 0x7B,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45,
    "f": 0x46, "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A,
    "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E, "o": 0x4F,
    "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59, "z": 0x5A,
}

# =============================================================================
# WINDOWS API STRUKTUREN
# =============================================================================
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION),
    ]

# =============================================================================
# WINDOWS API FUNKTIONEN
# =============================================================================
user32 = ctypes.windll.user32

user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL

user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL

user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL

user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL

user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL

PM_REMOVE = 0x0001

user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

kernel32 = ctypes.windll.kernel32
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

# =============================================================================
# DATENKLASSEN
# =============================================================================
@dataclass
class ClickPoint:
    """Ein Klickpunkt mit x,y Koordinaten und stabiler ID."""
    x: int
    y: int
    name: str = ""  # Optionaler Name für den Punkt
    id: int = 0     # Stabile ID für Referenzierung (bleibt bei Umsortierung erhalten)

    def __str__(self) -> str:
        if self.name:
            return f"#{self.id} {self.name} ({self.x}, {self.y})"
        return f"#{self.id} ({self.x}, {self.y})"

@dataclass
class SequenceStep:
    """Ein Schritt in einer Sequenz: Erst warten/prüfen, DANN klicken."""
    x: int                # X-Koordinate (direkt gespeichert)
    y: int                # Y-Koordinate (direkt gespeichert)
    delay_before: float   # Wartezeit in Sekunden VOR diesem Klick (0 = sofort)
    name: str = ""        # Optionaler Name des Punktes
    # Optional: Warten auf Farbe statt Zeit (VOR dem Klick)
    wait_pixel: Optional[tuple] = None   # (x, y) Position zum Prüfen
    wait_color: Optional[tuple] = None   # (r, g, b) Farbe die erscheinen soll
    wait_until_gone: bool = False        # True = warte bis Farbe WEG ist, False = warte bis Farbe DA ist
    # Optional: Item-Scan ausführen statt direktem Klick
    item_scan: Optional[str] = None      # Name des Item-Scans
    item_scan_mode: str = "all"          # "all" = bestes pro Kategorie, "best" = nur 1 Item total
    # Optional: Nur warten, nicht klicken
    wait_only: bool = False              # True = nur warten, kein Klick
    # Optional: Zufällige Verzögerung (delay_before bis delay_max)
    delay_max: Optional[float] = None    # None = feste Zeit, sonst Bereich
    # Optional: Tastendruck statt Mausklick
    key_press: Optional[str] = None      # z.B. "enter", "space", "f1"
    # Optional: Fallback/Else-Aktion wenn Bedingung fehlschlägt
    else_action: Optional[str] = None    # "skip", "restart", "click", "key"
    else_x: int = 0                      # X für Fallback-Klick
    else_y: int = 0                      # Y für Fallback-Klick
    else_delay: float = 0                # Delay vor Fallback
    else_key: Optional[str] = None       # Taste für Fallback
    else_name: str = ""                  # Name des Fallback-Punkts

    def __str__(self) -> str:
        else_str = self._else_str()
        if self.key_press:
            delay_str = self._delay_str()
            return f"{delay_str} → drücke Taste '{self.key_press}'{else_str}"
        if self.item_scan:
            mode_strs = {"all": "bestes/Kategorie", "best": "1 bestes", "every": "JEDES"}
            mode_str = mode_strs.get(self.item_scan_mode, self.item_scan_mode)
            return f"SCAN '{self.item_scan}' → klicke {mode_str}{else_str}"
        if self.wait_only:
            if self.wait_pixel and self.wait_color:
                gone_str = "WEG ist" if self.wait_until_gone else "DA ist"
                return f"WARTE bis Farbe {gone_str} bei ({self.wait_pixel[0]},{self.wait_pixel[1]}) (kein Klick){else_str}"
            return f"WARTE {self._delay_str()} (kein Klick)"
        pos_str = f"{self.name} ({self.x}, {self.y})" if self.name else f"({self.x}, {self.y})"
        if self.wait_pixel and self.wait_color:
            gone_str = "bis Farbe WEG" if self.wait_until_gone else "auf Farbe"
            delay_str = self._delay_str()
            if self.delay_before > 0:
                return f"warte {delay_str}, dann {gone_str} bei ({self.wait_pixel[0]},{self.wait_pixel[1]}) → klicke {pos_str}{else_str}"
            return f"warte {gone_str} bei ({self.wait_pixel[0]},{self.wait_pixel[1]}) → klicke {pos_str}{else_str}"
        elif self.delay_before > 0:
            return f"warte {self._delay_str()} → klicke {pos_str}"
        else:
            return f"sofort → klicke {pos_str}"

    def _else_str(self) -> str:
        """Hilfsfunktion für Else-Anzeige."""
        if not self.else_action:
            return ""
        if self.else_action == "skip":
            return " | ELSE: skip"
        elif self.else_action == "restart":
            return " | ELSE: restart"
        elif self.else_action == "click":
            name = self.else_name or f"({self.else_x},{self.else_y})"
            return f" | ELSE: klicke {name}"
        elif self.else_action == "key":
            return f" | ELSE: Taste '{self.else_key}'"
        return ""

    def _delay_str(self) -> str:
        """Hilfsfunktion für Delay-Anzeige (fest oder Bereich)."""
        if self.delay_max and self.delay_max > self.delay_before:
            return f"{self.delay_before:.0f}-{self.delay_max:.0f}s"
        return f"{self.delay_before:.0f}s"

    def get_actual_delay(self) -> float:
        """Gibt die tatsächliche Verzögerung zurück (bei Bereich: zufällig)."""
        if self.delay_max and self.delay_max > self.delay_before:
            return random.uniform(self.delay_before, self.delay_max)
        return self.delay_before

@dataclass
class LoopPhase:
    """Eine Loop-Phase mit eigenen Schritten und Wiederholungen."""
    name: str
    steps: list[SequenceStep] = field(default_factory=list)
    repeat: int = 1  # Wie oft diese Phase wiederholt wird

    def __str__(self) -> str:
        step_count = len(self.steps)
        pixel_triggers = sum(1 for s in self.steps if s.wait_pixel)
        trigger_str = f" [Farb: {pixel_triggers}]" if pixel_triggers > 0 else ""
        return f"{self.name}: {step_count} Schritte x{self.repeat}{trigger_str}"

@dataclass
class Sequence:
    """Eine Klick-Sequenz mit Start-Phase, Loop-Phasen und End-Phase."""
    name: str
    start_steps: list[SequenceStep] = field(default_factory=list)  # Einmalig am Anfang
    loop_phases: list[LoopPhase] = field(default_factory=list)     # Mehrere Loop-Phasen
    end_steps: list[SequenceStep] = field(default_factory=list)    # Einmalig am Ende
    total_cycles: int = 1  # 0 = unendlich, >0 = wie oft alle Loops durchlaufen werden

    def __str__(self) -> str:
        start_count = len(self.start_steps)
        end_count = len(self.end_steps)
        loop_info = f"{len(self.loop_phases)} Loop(s)"
        if self.total_cycles == 0:
            loop_info += " ∞"
        elif self.total_cycles == 1:
            loop_info += " (1x)"
        else:
            loop_info += f" (x{self.total_cycles})"
        # Zähle alle Schritte mit Farb-Trigger
        all_steps = self.start_steps + [s for lp in self.loop_phases for s in lp.steps] + self.end_steps
        pixel_triggers = sum(1 for s in all_steps if s.wait_pixel)
        trigger_str = f" [Farb-Trigger: {pixel_triggers}]" if pixel_triggers > 0 else ""
        end_str = f", End: {end_count}" if end_count > 0 else ""
        return f"{self.name} (Start: {start_count}, {loop_info}{end_str}){trigger_str}"

    def total_steps(self) -> int:
        return len(self.start_steps) + sum(len(lp.steps) for lp in self.loop_phases) + len(self.end_steps)

# =============================================================================
# ITEM-SCAN SYSTEM (für Item-Erkennung und Vergleich)
# =============================================================================
ITEM_SCANS_DIR: str = "item_scans"  # Ordner für Item-Scan Konfigurationen
SLOTS_DIR: str = "slots"            # Ordner für Slots
ITEMS_DIR: str = "items"            # Ordner für Items
SCREENSHOTS_DIR: str = os.path.join(SLOTS_DIR, "Screenshots") # Ordner für Screenshots
TEMPLATES_DIR: str = os.path.join(ITEMS_DIR, "templates")     # Ordner für Item-Templates
SLOTS_FILE: str = os.path.join(SLOTS_DIR, "slots.json")
ITEMS_FILE: str = os.path.join(ITEMS_DIR, "items.json")

# Ordner erstellen falls nicht vorhanden
for folder in [ITEM_SCANS_DIR, SLOTS_DIR, ITEMS_DIR, SCREENSHOTS_DIR, TEMPLATES_DIR]:
    os.makedirs(folder, exist_ok=True)

@dataclass
class ItemProfile:
    """Ein Item-Typ mit Marker-Farben und/oder Template-Matching."""
    name: str
    marker_colors: list[tuple] = field(default_factory=list)  # Liste von (r,g,b) Marker-Farben
    # Kategorie für Prioritäts-Vergleich (z.B. "Hosen", "Jacken", "Juwelen")
    category: Optional[str] = None  # Wenn None, ist jedes Item seine eigene Kategorie
    priority: int = 1  # 1 = beste, höher = schlechter (innerhalb der Kategorie)
    confirm_point: Optional[ClickPoint] = None  # ClickPoint für Bestätigung nach Klick
    confirm_delay: float = 0.5  # Wartezeit vor Bestätigungs-Klick
    # Template Matching (optional - überschreibt marker_colors wenn gesetzt)
    template: Optional[str] = None  # Dateiname des Template-Bildes (in items/templates/)
    min_confidence: float = DEFAULT_MIN_CONFIDENCE  # Mindest-Konfidenz für Template-Match

    def __str__(self) -> str:
        if self.template:
            template_str = f"Template: {self.template} (≥{self.min_confidence:.0%})"
        else:
            colors_str = ", ".join([f"RGB{c}" for c in self.marker_colors[:3]])
            if len(self.marker_colors) > 3:
                colors_str += f" (+{len(self.marker_colors)-3})"
            template_str = colors_str if colors_str else "keine Marker"
        confirm_str = f" → ({self.confirm_point.x},{self.confirm_point.y})" if self.confirm_point else ""
        category_str = f" [{self.category}]" if self.category else ""
        return f"[P{self.priority}]{category_str} {self.name}: {template_str}{confirm_str}"

@dataclass
class ItemSlot:
    """Ein Slot wo Items erscheinen können."""
    name: str
    scan_region: tuple  # (x1, y1, x2, y2) Bereich zum Scannen
    click_pos: tuple    # (x, y) Wo geklickt werden soll
    slot_color: Optional[tuple] = None  # RGB-Farbe des leeren Slots (wird bei Items ausgeschlossen)

    def __str__(self) -> str:
        r = self.scan_region
        color_str = f", Hintergrund: RGB{self.slot_color}" if self.slot_color else ""
        return f"{self.name}: Scan ({r[0]},{r[1]})-({r[2]},{r[3]}){color_str}"

@dataclass
class ItemScanConfig:
    """Konfiguration für Item-Erkennung und -Vergleich."""
    name: str
    slots: list[ItemSlot] = field(default_factory=list)      # Wo gescannt wird
    items: list[ItemProfile] = field(default_factory=list)   # Welche Items erkannt werden
    color_tolerance: int = 40  # Farbtoleranz für Erkennung

    def __str__(self) -> str:
        return f"{self.name} ({len(self.slots)} Slots, {len(self.items)} Items)"

@dataclass
class AutoClickerState:
    """Zustand des Autoclickers."""
    # Punkte-Pool (wiederverwendbar)
    points: list[ClickPoint] = field(default_factory=list)

    # Gespeicherte Sequenzen
    sequences: dict[str, Sequence] = field(default_factory=dict)

    # Globale Slots und Items (wiederverwendbar)
    global_slots: dict[str, ItemSlot] = field(default_factory=dict)
    global_items: dict[str, ItemProfile] = field(default_factory=dict)

    # Item-Scan Konfigurationen (verknüpft Slots + Items)
    item_scans: dict[str, ItemScanConfig] = field(default_factory=dict)

    # Aktive Sequenz
    active_sequence: Optional[Sequence] = None

    # Laufzeit-Status
    is_running: bool = False
    total_clicks: int = 0

    # Statistiken
    items_found: int = 0
    key_presses: int = 0
    start_time: Optional[float] = None

    # Bereits geklickte Kategorien im aktuellen Zyklus mit bester Priorität
    # Dict: {kategorie: beste_priorität} - verhindert schlechtere Items derselben Kategorie
    clicked_categories: dict = field(default_factory=dict)

    # Thread-sichere Events
    stop_event: threading.Event = field(default_factory=threading.Event)
    quit_event: threading.Event = field(default_factory=threading.Event)
    pause_event: threading.Event = field(default_factory=threading.Event)
    skip_event: threading.Event = field(default_factory=threading.Event)
    restart_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # Flag für geplanten Start (überspringt Debug-Enter-Prompt)
    scheduled_start: bool = False

    # Konfiguration (thread-safe über lock)
    config: dict = field(default_factory=dict)

# =============================================================================
# PERSISTENZ (Speichern/Laden)
# =============================================================================
def ensure_sequences_dir() -> Path:
    """Stellt sicher, dass der Sequenzen-Ordner existiert."""
    path = Path(SEQUENCES_DIR)
    path.mkdir(exist_ok=True)
    return path

def save_data(state: AutoClickerState) -> None:
    """Speichert Punkte und Sequenzen in JSON-Dateien."""
    ensure_sequences_dir()

    # Punkte speichern (mit stabiler ID)
    points_data = [{"id": p.id, "x": p.x, "y": p.y, "name": p.name} for p in state.points]
    with open(Path(SEQUENCES_DIR) / "points.json", "w", encoding="utf-8") as f:
        json.dump(points_data, f, indent=2, ensure_ascii=False)

    # Sequenzen speichern (mit Start + mehreren Loop-Phasen)
    def step_to_dict(s: SequenceStep) -> dict:
        return {"x": s.x, "y": s.y, "name": s.name, "delay_before": s.delay_before,
                "wait_pixel": s.wait_pixel, "wait_color": s.wait_color,
                "wait_until_gone": s.wait_until_gone,
                "item_scan": s.item_scan, "item_scan_mode": s.item_scan_mode,
                "wait_only": s.wait_only, "delay_max": s.delay_max,
                "key_press": s.key_press, "else_action": s.else_action,
                "else_x": s.else_x, "else_y": s.else_y, "else_delay": s.else_delay,
                "else_key": s.else_key, "else_name": s.else_name}

    for name, seq in state.sequences.items():
        seq_data = {
            "name": seq.name,
            "total_cycles": seq.total_cycles,
            "start_steps": [step_to_dict(s) for s in seq.start_steps],
            "loop_phases": [
                {
                    "name": lp.name,
                    "repeat": lp.repeat,
                    "steps": [step_to_dict(s) for s in lp.steps]
                }
                for lp in seq.loop_phases
            ],
            "end_steps": [step_to_dict(s) for s in seq.end_steps]
        }
        filename = f"{sanitize_filename(name)}.json"
        with open(Path(SEQUENCES_DIR) / filename, "w", encoding="utf-8") as f:
            json.dump(seq_data, f, indent=2, ensure_ascii=False)

    print(f"[SAVE] Daten gespeichert in '{SEQUENCES_DIR}/'")

def load_points(state: AutoClickerState) -> None:
    """Lädt gespeicherte Punkte."""
    points_file = Path(SEQUENCES_DIR) / "points.json"
    if points_file.exists():
        try:
            with open(points_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Lade Punkte mit ID (Fallback für alte Dateien ohne ID)
                state.points = []
                for i, p in enumerate(data):
                    point_id = p.get("id", i + 1)  # Fallback: Index + 1 für alte Dateien
                    state.points.append(ClickPoint(p["x"], p["y"], p.get("name", ""), point_id))
            print(f"[LOAD] {len(state.points)} Punkt(e) geladen")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"[WARNUNG] points.json konnte nicht geladen werden: {e}")
            print("[INFO] Starte mit leerer Punktliste.")
            state.points = []
    else:
        print("[INFO] Keine gespeicherten Punkte gefunden.")

def get_next_point_id(state: 'AutoClickerState') -> int:
    """Gibt die nächste freie Punkt-ID zurück."""
    if not state.points:
        return 1
    return max(p.id for p in state.points) + 1

def get_point_by_id(state: 'AutoClickerState', point_id: int) -> Optional[ClickPoint]:
    """Findet einen Punkt anhand seiner ID."""
    for p in state.points:
        if p.id == point_id:
            return p
    return None

def get_existing_categories(state: 'AutoClickerState') -> list[str]:
    """Sammelt alle existierenden Kategorien aus den Items."""
    categories = set()
    for item in state.global_items.values():
        if item.category:
            categories.add(item.category)
    return sorted(categories)

def select_category(state: 'AutoClickerState', show_explanation: bool = True) -> Optional[str]:
    """Zeigt existierende Kategorien an und lässt Benutzer wählen oder neue eingeben."""
    categories = get_existing_categories(state)

    if show_explanation:
        print("\n  Kategorie (z.B. 'Hosen', 'Jacken', 'Juwelen')")
        print("  Items derselben Kategorie konkurrieren - nur das beste wird geklickt.")

    if categories:
        print("  Vorhandene Kategorien:")
        for i, cat in enumerate(categories, 1):
            print(f"    {i}. {cat}")
        print("  (Nummer wählen oder neuen Namen eingeben)")

    user_input = input("  Kategorie (Enter = keine): ").strip()

    if not user_input:
        return None

    # Prüfe ob es eine Nummer ist
    try:
        num = int(user_input)
        if 1 <= num <= len(categories):
            return categories[num - 1]
        else:
            # Nummer außerhalb des Bereichs - als neuer Name behandeln
            return user_input
    except ValueError:
        # Keine Nummer - neuer Kategorie-Name
        return user_input

def load_sequence_file(filepath: Path) -> Optional[Sequence]:
    """Lädt eine einzelne Sequenz-Datei (mit Start + mehreren Loop-Phasen)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

            def parse_steps(steps_data: list) -> list[SequenceStep]:
                steps = []
                for s in steps_data:
                    wait_pixel = s.get("wait_pixel")
                    if wait_pixel:
                        wait_pixel = tuple(int(v) for v in wait_pixel)
                    wait_color = s.get("wait_color")
                    if wait_color:
                        wait_color = tuple(int(v) for v in wait_color)
                    # Unterstütze beide Formate: delay_before (neu) und delay_after (alt)
                    # None-Check: s.get() returned None wenn Wert null ist oder Key fehlt
                    delay_raw = s.get("delay_before")
                    if delay_raw is None:
                        delay_raw = s.get("delay_after")
                    if delay_raw is None:
                        delay_raw = 0
                    delay_max_raw = s.get("delay_max")
                    step = SequenceStep(
                        x=s.get("x", 0),
                        y=s.get("y", 0),
                        delay_before=float(delay_raw),
                        name=s.get("name", ""),
                        wait_pixel=wait_pixel,
                        wait_color=wait_color,
                        wait_until_gone=s.get("wait_until_gone", False),
                        item_scan=s.get("item_scan"),
                        item_scan_mode=s.get("item_scan_mode", "all"),
                        wait_only=s.get("wait_only", False),
                        delay_max=float(delay_max_raw) if delay_max_raw is not None else None,
                        key_press=s.get("key_press"),
                        else_action=s.get("else_action"),
                        else_x=s.get("else_x", 0),
                        else_y=s.get("else_y", 0),
                        else_delay=s.get("else_delay", 0),
                        else_key=s.get("else_key"),
                        else_name=s.get("else_name", "")
                    )
                    steps.append(step)
                return steps

            start_steps = parse_steps(data.get("start_steps", []))
            end_steps = parse_steps(data.get("end_steps", []))

            # Neues Format mit loop_phases (mehrere Loop-Phasen)
            if "loop_phases" in data:
                loop_phases = []
                for lp_data in data["loop_phases"]:
                    lp = LoopPhase(
                        name=lp_data.get("name", "Loop"),
                        steps=parse_steps(lp_data.get("steps", [])),
                        repeat=lp_data.get("repeat", 1)
                    )
                    loop_phases.append(lp)
                total_cycles = data.get("total_cycles", 1)
                return Sequence(data["name"], start_steps, loop_phases, end_steps, total_cycles)

            # Altes Format mit loop_steps (eine Loop-Phase) - konvertieren
            elif "loop_steps" in data:
                loop_steps = parse_steps(data.get("loop_steps", []))
                max_loops = data.get("max_loops", 0)
                # Konvertiere zu neuem Format: eine LoopPhase
                if loop_steps:
                    loop_phases = [LoopPhase("Loop 1", loop_steps, max_loops if max_loops > 0 else 1)]
                    total_cycles = 0 if max_loops == 0 else 1  # 0 = unendlich
                else:
                    loop_phases = []
                    total_cycles = 1
                return Sequence(data["name"], start_steps, loop_phases, end_steps, total_cycles)

            # Uraltes Format (nur steps) - konvertieren
            elif "steps" in data:
                loop_steps = parse_steps(data["steps"])
                loop_phases = [LoopPhase("Loop 1", loop_steps, 1)] if loop_steps else []
                return Sequence(data["name"], [], loop_phases, [], 0)

            else:
                return Sequence(data["name"], [], [], [], 1)

    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None

def list_available_sequences() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Sequenz-Dateien auf."""
    seq_dir = Path(SEQUENCES_DIR)
    if not seq_dir.exists():
        return []

    sequences = []
    for f in seq_dir.glob("*.json"):
        if f.name != "points.json":
            try:
                with open(f, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    name = data.get("name", f.stem)
                    sequences.append((name, f))
            except (json.JSONDecodeError, IOError, KeyError):
                pass  # Ungültige/korrupte Datei überspringen
    return sequences

# =============================================================================
# ITEM-SCAN PERSISTENZ
# =============================================================================
def ensure_item_scans_dir() -> Path:
    """Stellt sicher, dass der Item-Scans-Ordner existiert."""
    path = Path(ITEM_SCANS_DIR)
    path.mkdir(exist_ok=True)
    return path

def save_item_scan(config: ItemScanConfig) -> None:
    """Speichert eine Item-Scan Konfiguration."""
    ensure_item_scans_dir()

    data = {
        "name": config.name,
        "color_tolerance": config.color_tolerance,
        "slots": [
            {
                "name": slot.name,
                "scan_region": list(slot.scan_region),
                "click_pos": list(slot.click_pos),
                "slot_color": list(slot.slot_color) if slot.slot_color else None
            }
            for slot in config.slots
        ],
        "items": [
            {
                "name": item.name,
                "marker_colors": [list(c) for c in item.marker_colors] if item.marker_colors else [],
                "category": item.category,
                "priority": item.priority,
                "confirm_point": {"x": item.confirm_point.x, "y": item.confirm_point.y} if item.confirm_point else None,
                "confirm_delay": item.confirm_delay,
                "template": item.template,
                "min_confidence": item.min_confidence
            }
            for item in config.items
        ]
    }

    filename = f"{sanitize_filename(config.name)}.json"
    with open(Path(ITEM_SCANS_DIR) / filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[SAVE] Item-Scan '{config.name}' gespeichert in '{ITEM_SCANS_DIR}/'")

def load_item_scan_file(filepath: Path) -> Optional[ItemScanConfig]:
    """Lädt eine Item-Scan Konfiguration."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

            slots = []
            for s in data.get("slots", []):
                slot_color = s.get("slot_color")
                if slot_color:
                    slot_color = tuple(slot_color)
                slot = ItemSlot(
                    name=s["name"],
                    scan_region=tuple(s["scan_region"]),
                    click_pos=tuple(s["click_pos"]),
                    slot_color=slot_color
                )
                slots.append(slot)

            items = []
            for i in data.get("items", []):
                # confirm_point: kann {x, y} Dict, [x,y] Liste (alt) oder None sein
                cp_data = i.get("confirm_point")
                cp = None
                if cp_data:
                    if isinstance(cp_data, dict) and "x" in cp_data and "y" in cp_data:
                        cp = ClickPoint(cp_data["x"], cp_data["y"])
                    elif isinstance(cp_data, list) and len(cp_data) == 2:
                        cp = ClickPoint(cp_data[0], cp_data[1])  # Alte Format-Unterstützung
                item = ItemProfile(
                    name=i["name"],
                    marker_colors=[tuple(c) for c in i.get("marker_colors", [])],
                    category=i.get("category"),
                    priority=i.get("priority", 1),
                    confirm_point=cp,
                    confirm_delay=i.get("confirm_delay", 0.5),
                    template=i.get("template"),
                    min_confidence=i.get("min_confidence", DEFAULT_MIN_CONFIDENCE)
                )
                items.append(item)

            return ItemScanConfig(
                name=data["name"],
                slots=slots,
                items=items,
                color_tolerance=data.get("color_tolerance", 40)
            )

    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None

def list_available_item_scans() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Item-Scan Konfigurationen auf."""
    scan_dir = Path(ITEM_SCANS_DIR)
    if not scan_dir.exists():
        return []

    scans = []
    for f in scan_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                name = data.get("name", f.stem)
                scans.append((name, f))
        except (json.JSONDecodeError, IOError, KeyError):
            pass  # Ungültige/korrupte Datei überspringen
    return scans

def load_all_item_scans(state: AutoClickerState) -> None:
    """Lädt alle Item-Scan Konfigurationen."""
    for name, path in list_available_item_scans():
        config = load_item_scan_file(path)
        if config:
            state.item_scans[config.name] = config
    if state.item_scans:
        print(f"[LOAD] {len(state.item_scans)} Item-Scan(s) geladen")

# =============================================================================
# GLOBALE SLOTS UND ITEMS PERSISTENZ
# =============================================================================
def save_global_slots(state: AutoClickerState) -> None:
    """Speichert alle globalen Slots."""
    data = {
        name: {
            "name": slot.name,
            "scan_region": list(slot.scan_region),
            "click_pos": list(slot.click_pos),
            "slot_color": list(slot.slot_color) if slot.slot_color else None
        }
        for name, slot in state.global_slots.items()
    }
    with open(SLOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[SAVE] {len(state.global_slots)} Slot(s) gespeichert")

def load_global_slots(state: AutoClickerState) -> None:
    """Lädt alle globalen Slots."""
    if not Path(SLOTS_FILE).exists():
        return
    try:
        with open(SLOTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for name, s in data.items():
            slot_color = tuple(s["slot_color"]) if s.get("slot_color") else None
            state.global_slots[name] = ItemSlot(
                name=s["name"],
                scan_region=tuple(s["scan_region"]),
                click_pos=tuple(s["click_pos"]),
                slot_color=slot_color
            )
        if state.global_slots:
            print(f"[LOAD] {len(state.global_slots)} Slot(s) geladen")
    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Slots laden fehlgeschlagen: {e}")

def save_global_items(state: AutoClickerState) -> None:
    """Speichert alle globalen Items."""
    data = {
        name: {
            "name": item.name,
            "marker_colors": [list(c) for c in item.marker_colors] if item.marker_colors else [],
            "category": item.category,
            "priority": item.priority,
            "confirm_point": {"x": item.confirm_point.x, "y": item.confirm_point.y} if item.confirm_point else None,
            "confirm_delay": item.confirm_delay,
            "template": item.template,
            "min_confidence": item.min_confidence
        }
        for name, item in state.global_items.items()
    }
    with open(ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[SAVE] {len(state.global_items)} Item(s) gespeichert")


def shift_category_priorities(state: AutoClickerState, category: str) -> int:
    """Verschiebt alle Items einer Kategorie um +1 in der Priorität.

    Returns: Anzahl der verschobenen Items.
    """
    if not category:
        return 0

    shifted = 0
    with state.lock:
        for item in state.global_items.values():
            if item.category == category:
                item.priority += 1
                shifted += 1

    if shifted > 0:
        save_global_items(state)
        print(f"  → {shifted} Item(s) in Kategorie '{category}' nach hinten verschoben")

    return shifted


def update_item_in_scans(old_name: str, new_name: str, new_template: Optional[str] = None) -> int:
    """Aktualisiert ein Item in allen Scan-Konfigurationen.

    Returns: Anzahl der aktualisierten Scans.
    """
    updated_scans = 0
    scan_dir = Path(ITEM_SCANS_DIR)

    if not scan_dir.exists():
        return 0

    for scan_file in scan_dir.glob("*.json"):
        try:
            with open(scan_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            modified = False
            for item in data.get("items", []):
                if item.get("name") == old_name:
                    item["name"] = new_name
                    if new_template:
                        item["template"] = new_template
                    modified = True

            if modified:
                with open(scan_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                updated_scans += 1

        except (json.JSONDecodeError, IOError, KeyError) as e:
            print(f"  [WARNUNG] Konnte {scan_file.name} nicht aktualisieren: {e}")

    return updated_scans


def load_global_items(state: AutoClickerState) -> None:
    """Lädt alle globalen Items."""
    if not Path(ITEMS_FILE).exists():
        return
    try:
        with open(ITEMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for name, i in data.items():
            # confirm_point: kann {x, y} Dict, [x,y] Liste (alt) oder None sein
            cp_data = i.get("confirm_point")
            cp = None
            if cp_data:
                if isinstance(cp_data, dict) and "x" in cp_data and "y" in cp_data:
                    cp = ClickPoint(cp_data["x"], cp_data["y"])
                elif isinstance(cp_data, list) and len(cp_data) == 2:
                    cp = ClickPoint(cp_data[0], cp_data[1])  # Alte Format-Unterstützung
            state.global_items[name] = ItemProfile(
                name=i["name"],
                marker_colors=[tuple(c) for c in i.get("marker_colors", [])],
                category=i.get("category"),
                priority=i.get("priority", 1),
                confirm_point=cp,
                confirm_delay=i.get("confirm_delay", 0.5),
                template=i.get("template"),
                min_confidence=i.get("min_confidence", DEFAULT_MIN_CONFIDENCE)
            )
        if state.global_items:
            print(f"[LOAD] {len(state.global_items)} Item(s) geladen")
    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Items laden fehlgeschlagen: {e}")

# =============================================================================
# SLOT UND ITEM PRESETS
# =============================================================================
SLOT_PRESETS_DIR: str = os.path.join(SLOTS_DIR, "presets")
ITEM_PRESETS_DIR: str = os.path.join(ITEMS_DIR, "presets")

# Preset-Ordner erstellen
for folder in [SLOT_PRESETS_DIR, ITEM_PRESETS_DIR]:
    os.makedirs(folder, exist_ok=True)

def list_slot_presets() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Slot-Presets auf."""
    preset_dir = Path(SLOT_PRESETS_DIR)
    if not preset_dir.exists():
        return []
    presets = []
    for f in preset_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                name = f.stem
                count = len(data)
                presets.append((name, f, count))
        except (json.JSONDecodeError, IOError, KeyError, TypeError):
            pass  # Ungültige/korrupte Datei überspringen
    return presets

def save_slot_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Speichert aktuelle Slots als Preset."""
    if not state.global_slots:
        print("[FEHLER] Keine Slots vorhanden zum Speichern!")
        return False

    data = {
        name: {
            "name": slot.name,
            "scan_region": list(slot.scan_region),
            "click_pos": list(slot.click_pos),
            "slot_color": list(slot.slot_color) if slot.slot_color else None
        }
        for name, slot in state.global_slots.items()
    }

    safe_name = sanitize_filename(preset_name)
    filepath = Path(SLOT_PRESETS_DIR) / f"{safe_name}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[SAVE] Slot-Preset '{preset_name}' gespeichert ({len(state.global_slots)} Slots)")
    return True

def load_slot_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Lädt ein Slot-Preset."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(SLOT_PRESETS_DIR) / f"{safe_name}.json"
    if not filepath.exists():
        print(f"[FEHLER] Preset '{preset_name}' nicht gefunden!")
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        with state.lock:
            state.global_slots.clear()
            for name, s in data.items():
                slot_color = tuple(s["slot_color"]) if s.get("slot_color") else None
                state.global_slots[name] = ItemSlot(
                    name=s["name"],
                    scan_region=tuple(s["scan_region"]),
                    click_pos=tuple(s["click_pos"]),
                    slot_color=slot_color
                )

        # Auch in aktive Datei speichern
        save_global_slots(state)
        print(f"[LOAD] Slot-Preset '{preset_name}' geladen ({len(state.global_slots)} Slots)")
        return True
    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        print(f"[FEHLER] Preset laden fehlgeschlagen: {e}")
        return False

def delete_slot_preset(preset_name: str) -> bool:
    """Löscht ein Slot-Preset."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(SLOT_PRESETS_DIR) / f"{safe_name}.json"
    if not filepath.exists():
        print(f"[FEHLER] Preset '{preset_name}' nicht gefunden!")
        return False
    filepath.unlink()
    print(f"[DELETE] Slot-Preset '{preset_name}' gelöscht")
    return True

def list_item_presets() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Item-Presets auf."""
    preset_dir = Path(ITEM_PRESETS_DIR)
    if not preset_dir.exists():
        return []
    presets = []
    for f in preset_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                name = f.stem
                count = len(data)
                presets.append((name, f, count))
        except (json.JSONDecodeError, IOError, KeyError, TypeError):
            pass  # Ungültige/korrupte Datei überspringen
    return presets

def save_item_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Speichert aktuelle Items als Preset."""
    if not state.global_items:
        print("[FEHLER] Keine Items vorhanden zum Speichern!")
        return False

    data = {
        name: {
            "name": item.name,
            "marker_colors": [list(c) for c in item.marker_colors] if item.marker_colors else [],
            "category": item.category,
            "priority": item.priority,
            "confirm_point": {"x": item.confirm_point.x, "y": item.confirm_point.y} if item.confirm_point else None,
            "confirm_delay": item.confirm_delay,
            "template": item.template,
            "min_confidence": item.min_confidence
        }
        for name, item in state.global_items.items()
    }

    safe_name = sanitize_filename(preset_name)
    filepath = Path(ITEM_PRESETS_DIR) / f"{safe_name}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[SAVE] Item-Preset '{preset_name}' gespeichert ({len(state.global_items)} Items)")
    return True

def load_item_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Lädt ein Item-Preset."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(ITEM_PRESETS_DIR) / f"{safe_name}.json"
    if not filepath.exists():
        print(f"[FEHLER] Preset '{preset_name}' nicht gefunden!")
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        with state.lock:
            state.global_items.clear()
            for name, i in data.items():
                # confirm_point: kann {x, y} Dict, [x,y] Liste (alt) oder None sein
                cp_data = i.get("confirm_point")
                cp = None
                if cp_data:
                    if isinstance(cp_data, dict) and "x" in cp_data and "y" in cp_data:
                        cp = ClickPoint(cp_data["x"], cp_data["y"])
                    elif isinstance(cp_data, list) and len(cp_data) == 2:
                        cp = ClickPoint(cp_data[0], cp_data[1])  # Alte Format-Unterstützung
                state.global_items[name] = ItemProfile(
                    name=i["name"],
                    marker_colors=[tuple(c) for c in i.get("marker_colors", [])],
                    category=i.get("category"),
                    priority=i.get("priority", 1),
                    confirm_point=cp,
                    confirm_delay=i.get("confirm_delay", 0.5),
                    template=i.get("template"),
                    min_confidence=i.get("min_confidence", DEFAULT_MIN_CONFIDENCE)
                )

        # Auch in aktive Datei speichern
        save_global_items(state)
        print(f"[LOAD] Item-Preset '{preset_name}' geladen ({len(state.global_items)} Items)")
        return True
    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        print(f"[FEHLER] Preset laden fehlgeschlagen: {e}")
        return False

def delete_item_preset(preset_name: str) -> bool:
    """Löscht ein Item-Preset."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(ITEM_PRESETS_DIR) / f"{safe_name}.json"
    if not filepath.exists():
        print(f"[FEHLER] Preset '{preset_name}' nicht gefunden!")
        return False
    filepath.unlink()
    print(f"[DELETE] Item-Preset '{preset_name}' gelöscht")
    return True

# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================
def get_cursor_pos() -> tuple[int, int]:
    """Liest die aktuelle Mausposition."""
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y

def get_pixel_color(x: int, y: int) -> tuple[int, int, int] | None:
    """Liest die Farbe eines einzelnen Pixels an der angegebenen Position."""
    if not PILLOW_AVAILABLE:
        return None
    try:
        img = ImageGrab.grab(bbox=(x, y, x + 1, y + 1), all_screens=True)
        if img:
            return img.getpixel((0, 0))[:3]
    except (OSError, ValueError):
        pass  # Screenshot fehlgeschlagen
    return None

def set_cursor_pos(x: int, y: int) -> bool:
    """Setzt die Mausposition."""
    return bool(user32.SetCursorPos(x, y))

def send_click(x: int, y: int) -> None:
    """Führt einen Linksklick an der angegebenen Position aus."""
    set_cursor_pos(x, y)
    time.sleep(0.01)

    inputs = (INPUT * 2)()
    inputs[0].type = INPUT_MOUSE
    inputs[0].union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
    inputs[1].type = INPUT_MOUSE
    inputs[1].union.mi.dwFlags = MOUSEEVENTF_LEFTUP

    user32.SendInput(2, inputs, ctypes.sizeof(INPUT))

def send_key(key_name: str) -> bool:
    """Führt einen Tastendruck aus. Gibt True zurück wenn erfolgreich."""
    key_lower = key_name.lower()
    if key_lower not in VK_CODES:
        print(f"[FEHLER] Unbekannte Taste: '{key_name}'")
        print(f"         Verfügbar: {', '.join(sorted(VK_CODES.keys()))}")
        return False

    vk_code = VK_CODES[key_lower]

    inputs = (INPUT * 2)()
    # Key down
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].union.ki.wVk = vk_code
    inputs[0].union.ki.dwFlags = 0
    # Key up
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].union.ki.wVk = vk_code
    inputs[1].union.ki.dwFlags = KEYEVENTF_KEYUP

    user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
    return True

def check_failsafe(state: 'AutoClickerState' = None) -> bool:
    """Prüft, ob die Maus in der Fail-Safe-Ecke ist."""
    if not FAILSAFE_ENABLED:
        return False
    x, y = get_cursor_pos()
    # Nutze state.config wenn vorhanden, sonst globale CONFIG
    cfg = state.config if state else CONFIG
    failsafe_x = cfg.get("failsafe_x", 5)
    failsafe_y = cfg.get("failsafe_y", 5)
    return x <= failsafe_x and y <= failsafe_y

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
    while state.pause_event.is_set() and not state.stop_event.is_set():
        clear_line()
        print(f"[PAUSE] {message} | Fortsetzen: CTRL+ALT+G", end="", flush=True)
        time.sleep(0.5)
    return not state.stop_event.is_set()

def require_pillow(func_name: str) -> bool:
    """Prüft ob Pillow verfügbar ist und gibt Fehlermeldung aus."""
    if not PILLOW_AVAILABLE:
        print(f"[FEHLER] {func_name}: Pillow nicht installiert!")
        print("         Installieren mit: pip install pillow")
        return False
    return True

# =============================================================================
# BILDERKENNUNG (Screen Detection)
# =============================================================================
# Toleranzen aus Config laden
COLOR_TOLERANCE = CONFIG["color_tolerance"]
PIXEL_WAIT_TOLERANCE = CONFIG["pixel_wait_tolerance"]
PIXEL_WAIT_TIMEOUT = CONFIG["pixel_wait_timeout"]
PIXEL_CHECK_INTERVAL = CONFIG["pixel_check_interval"]

def color_distance(c1: tuple, c2: tuple) -> float:
    """Berechnet die Distanz zwischen zwei RGB-Farben."""
    return ((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2) ** 0.5

def find_color_in_image(img: 'Image.Image', target_color: tuple, tolerance: float) -> bool:
    """
    Prüft ob eine Farbe im Bild vorhanden ist (optimiert mit NumPy wenn verfügbar).

    Args:
        img: PIL Image
        target_color: RGB-Tuple (r, g, b)
        tolerance: Maximale Farbdistanz

    Returns:
        True wenn Farbe gefunden, sonst False
    """
    if NUMPY_AVAILABLE:
        # Schnelle NumPy-Version (ca. 100x schneller)
        img_array = np.array(img)
        if len(img_array.shape) == 3 and img_array.shape[2] >= 3:
            # Nur RGB-Kanäle verwenden
            rgb = img_array[:, :, :3].astype(np.float32)
            target = np.array(target_color, dtype=np.float32)
            # Euklidische Distanz für alle Pixel gleichzeitig berechnen
            distances = np.sqrt(np.sum((rgb - target) ** 2, axis=2))
            return bool(np.any(distances <= tolerance))
        return False
    else:
        # Fallback: Langsame PIL-Version (jeden 2. Pixel prüfen)
        pixels = img.load()
        width, height = img.size
        for x in range(0, width, 2):
            for y in range(0, height, 2):
                pixel = pixels[x, y][:3]
                if color_distance(pixel, target_color) <= tolerance:
                    return True
        return False

def match_template_in_image(img: 'Image.Image', template_name: str, min_confidence: float = DEFAULT_MIN_CONFIDENCE) -> tuple:
    """
    Sucht ein Template-Bild im gegebenen Bild mittels OpenCV Template Matching.

    Args:
        img: PIL Image (Suchbereich)
        template_name: Dateiname des Templates (in items/templates/)
        min_confidence: Mindest-Konfidenz für Match (0.0-1.0)

    Returns:
        (match_found: bool, confidence: float, position: tuple or None)
        position ist (x, y) relativ zum Suchbereich
    """
    if not OPENCV_AVAILABLE:
        logger.warning("OpenCV nicht verfügbar für Template Matching")
        return (False, 0.0, None)

    if not NUMPY_AVAILABLE:
        logger.warning("NumPy nicht verfügbar für Template Matching")
        return (False, 0.0, None)

    # Template-Pfad erstellen
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    if not os.path.exists(template_path):
        logger.error(f"Template nicht gefunden: {template_path}")
        return (False, 0.0, None)

    try:
        # PIL-Bild zu OpenCV-Format konvertieren (RGB -> BGR)
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        # Template laden (mit Unicode-Pfad-Unterstützung für Windows)
        # cv2.imread hat Probleme mit Umlauten (ü, ä, ö) - daher imdecode verwenden
        template_cv = cv2.imdecode(np.fromfile(template_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if template_cv is None:
            logger.error(f"Konnte Template nicht laden: {template_path}")
            return (False, 0.0, None)

        # Debug: Scan-Bild und Template speichern zum Vergleich
        if CONFIG.get("debug_save_templates", False):
            debug_dir = os.path.join(ITEMS_DIR, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            # Basis-Name aus Template (ohne .png)
            base_name = os.path.splitext(template_name)[0]
            # Aktuelles Scan-Bild (was im Slot ist)
            img.save(os.path.join(debug_dir, f"{base_name}_scan.png"))
            # Template/Maske (was cv2 zum Vergleich verwendet)
            cv2.imwrite(os.path.join(debug_dir, f"{base_name}_template.png"), template_cv)

        # Template Matching mit TM_CCOEFF_NORMED (beste Methode für farbige Bilder)
        result = cv2.matchTemplate(img_cv, template_cv, cv2.TM_CCOEFF_NORMED)

        # Bestes Match finden
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # max_val ist die Konfidenz (0.0 - 1.0)
        if max_val >= min_confidence:
            # Position ist obere linke Ecke des Matches
            return (True, max_val, max_loc)
        else:
            return (False, max_val, None)

    except (ValueError, TypeError, AttributeError) as e:
        logger.error(f"Template Matching Fehler: {e}")
        return (False, 0.0, None)

def get_color_name(rgb: tuple) -> str:
    """Gibt einen ungefähren Farbnamen für RGB zurück."""
    r, g, b = rgb

    # Graustufen
    if abs(r - g) < 30 and abs(g - b) < 30 and abs(r - b) < 30:
        if r < 50:
            return "Schwarz"
        elif r < 120:
            return "Dunkelgrau"
        elif r < 200:
            return "Grau"
        else:
            return "Weiß"

    # Dominante Farbe bestimmen
    if r > g and r > b:
        if g > b + 50:
            return "Orange" if r > 200 else "Braun"
        elif b > g + 30:
            return "Pink/Magenta"
        else:
            return "Rot"
    elif g > r and g > b:
        if r > b + 30:
            return "Gelb/Lime"
        elif b > r + 30:
            return "Türkis/Cyan"
        else:
            return "Grün"
    elif b > r and b > g:
        if r > g + 30:
            return "Lila/Violett"
        elif g > r + 30:
            return "Türkis/Cyan"
        else:
            return "Blau"
    elif r > 200 and g > 200 and b < 100:
        return "Gelb"
    elif r > 200 and g < 100 and b > 200:
        return "Magenta"
    elif r < 100 and g > 200 and b > 200:
        return "Cyan"
    else:
        return "Gemischt"

def take_screenshot(region: tuple = None) -> Optional['Image.Image']:
    """
    Nimmt einen Screenshot auf. region=(x1, y1, x2, y2) oder None für Vollbild.
    Verwendet BitBlt (schneller, besser für Spiele) mit ImageGrab-Fallback.
    Unterstützt mehrere Monitore (auch negative Koordinaten für linke Monitore).
    """
    # Versuche BitBlt (schneller, besser für DirectX-Spiele)
    img = take_screenshot_bitblt(region)
    if img is not None:
        return img

    # Fallback auf ImageGrab (falls BitBlt fehlschlägt, z.B. kein NumPy)
    if not PILLOW_AVAILABLE:
        return None
    try:
        if region:
            # Bei Region: Erst alle Screens erfassen, dann zuschneiden
            full_screenshot = ImageGrab.grab(all_screens=True)
            SM_XVIRTUALSCREEN = 76
            SM_YVIRTUALSCREEN = 77
            x_offset = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            y_offset = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
            adjusted_region = (
                region[0] - x_offset,
                region[1] - y_offset,
                region[2] - x_offset,
                region[3] - y_offset
            )
            return full_screenshot.crop(adjusted_region)
        else:
            return ImageGrab.grab(all_screens=True)
    except (OSError, ValueError) as e:
        logger.error(f"Screenshot fehlgeschlagen: {e}")
        return None

def take_screenshot_bitblt(region: tuple = None) -> Optional['Image.Image']:
    """
    Screenshot mit BitBlt (Windows API) - funktioniert besser mit Spielen!
    Unterstützt Multi-Monitor (auch negative Koordinaten für linke Monitore).
    Returns: PIL Image oder None
    """
    try:
        # Virtual Screen Metriken für Multi-Monitor-Support
        SM_XVIRTUALSCREEN = 76   # Linke Kante des virtuellen Desktops
        SM_YVIRTUALSCREEN = 77   # Obere Kante des virtuellen Desktops
        SM_CXVIRTUALSCREEN = 78  # Breite des virtuellen Desktops
        SM_CYVIRTUALSCREEN = 79  # Höhe des virtuellen Desktops

        virtual_left = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        virtual_top = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)

        if region:
            left, top, right, bottom = region
            width = right - left
            height = bottom - top
        else:
            # Vollbild: gesamter virtueller Desktop (alle Monitore)
            left = virtual_left
            top = virtual_top
            width = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
            height = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

        # Device Contexts - GetWindowDC(GetDesktopWindow()) liefert DC für gesamten virtuellen Desktop
        hwnd = ctypes.windll.user32.GetDesktopWindow()
        hwndDC = ctypes.windll.user32.GetWindowDC(hwnd)
        memDC = ctypes.windll.gdi32.CreateCompatibleDC(hwndDC)
        bmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hwndDC, width, height)
        old_bmp = ctypes.windll.gdi32.SelectObject(memDC, bmp)

        # BitBlt - Koordinaten funktionieren auch negativ (linker Monitor)
        ctypes.windll.gdi32.BitBlt(memDC, 0, 0, width, height, hwndDC, left, top, 0x00CC0020)

        # Bitmap-Daten auslesen
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', ctypes.c_uint32), ('biWidth', ctypes.c_int32),
                ('biHeight', ctypes.c_int32), ('biPlanes', ctypes.c_uint16),
                ('biBitCount', ctypes.c_uint16), ('biCompression', ctypes.c_uint32),
                ('biSizeImage', ctypes.c_uint32), ('biXPelsPerMeter', ctypes.c_int32),
                ('biYPelsPerMeter', ctypes.c_int32), ('biClrUsed', ctypes.c_uint32),
                ('biClrImportant', ctypes.c_uint32),
            ]

        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = width
        bi.biHeight = -height
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0

        buffer = (ctypes.c_char * (width * height * 4))()
        ctypes.windll.gdi32.GetDIBits(memDC, bmp, 0, height, buffer, ctypes.byref(bi), 0)

        # Aufräumen
        ctypes.windll.gdi32.SelectObject(memDC, old_bmp)
        ctypes.windll.gdi32.DeleteObject(bmp)
        ctypes.windll.gdi32.DeleteDC(memDC)
        ctypes.windll.user32.ReleaseDC(hwnd, hwndDC)

        # In PIL Image konvertieren (benötigt NumPy)
        if not NUMPY_AVAILABLE:
            return None
        img_array = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, 4))
        # BGRA -> RGB
        img_rgb = img_array[:, :, [2, 1, 0]]
        return Image.fromarray(img_rgb)
    except (OSError, ValueError, AttributeError) as e:
        logger.error(f"BitBlt Screenshot fehlgeschlagen: {e}")
        return None

def analyze_screen_colors(region: tuple = None) -> dict:
    """
    Analysiert die häufigsten Farben in einem Screenshot.
    Nützlich um die richtigen Farben für die Erkennung zu finden.
    """
    if not PILLOW_AVAILABLE:
        logger.error("Pillow nicht installiert!")
        return {}

    img = take_screenshot(region)
    if img is None:
        return {}

    # Farben zählen (mit Rundung auf 10er-Schritte für Gruppierung)
    color_counts = {}
    pixels = img.load()
    width, height = img.size

    for x in range(0, width, 2):  # Jeden 2. Pixel für Geschwindigkeit
        for y in range(0, height, 2):
            pixel = pixels[x, y][:3]
            # Runde auf 5er-Schritte für Gruppierung
            rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
            color_counts[rounded] = color_counts.get(rounded, 0) + 1

    return color_counts

def run_color_analyzer() -> None:
    """Interaktive Farbanalyse für die aktuelle Mausposition oder Region."""
    print("\n" + "=" * 60)
    print("  FARB-ANALYSATOR")
    print("=" * 60)

    if not PILLOW_AVAILABLE:
        print("\n[FEHLER] Pillow nicht installiert!")
        print("         Installieren mit: pip install pillow")
        return

    print("\nWas möchtest du analysieren?")
    print("  [1] Farbe unter Mauszeiger")
    print("  [2] Region (Bereich auswählen)")
    print("  [3] Vollbild")
    print("\nAuswahl (oder 'cancel'):")

    try:
        choice = input("> ").strip()

        if choice.lower() in ("cancel", "abbruch"):
            return

        if choice == "1":
            # Farbe unter Mauszeiger
            print("\nBewege die Maus zur gewünschten Position und drücke Enter...")
            input()
            x, y = get_cursor_pos()

            img = take_screenshot((x, y, x+1, y+1))
            if img:
                pixel = img.getpixel((0, 0))[:3]
                color_name = get_color_name(pixel)
                print(f"\n[FARBE] Position ({x}, {y})")
                print(f"        RGB: {pixel}")
                print(f"        Hex: #{pixel[0]:02x}{pixel[1]:02x}{pixel[2]:02x}")
                print(f"        Name: {color_name}")

        elif choice == "2":
            # Region analysieren
            region = select_region()
            if region:
                analyze_and_print_colors(region)

        elif choice == "3":
            # Vollbild analysieren
            analyze_and_print_colors(None)

    except (KeyboardInterrupt, EOFError):
        print("\n[ABBRUCH]")

def analyze_and_print_colors(region: tuple = None) -> None:
    """Analysiert und zeigt die häufigsten Farben."""
    print("\n[ANALYSE] Analysiere Farben...")

    color_counts = analyze_screen_colors(region)
    if not color_counts:
        print("[FEHLER] Keine Farben gefunden!")
        return

    # Top 20 häufigste Farben
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:20]

    print("\nTop 20 häufigste Farben:")
    print("-" * 50)
    for i, (color, count) in enumerate(sorted_colors, 1):
        # Prüfen ob grün/türkis
        is_green = (color[1] > color[0] and color[1] > color[2] and color[1] > 100)
        is_teal = (color[1] > 100 and color[2] > 100 and abs(color[1] - color[2]) < 80 and color[0] < 100)

        marker = ""
        if is_green:
            marker = " ← GRÜN"
        elif is_teal:
            marker = " ← TÜRKIS"

        print(f"  {i:2}. RGB({color[0]:3}, {color[1]:3}, {color[2]:3}) - {count:5} Pixel{marker}")

    print("-" * 50)


def select_region() -> Optional[tuple]:
    """
    Lässt den Benutzer eine Region per Maus auswählen.
    Returns (x1, y1, x2, y2) oder None bei Abbruch.
    """
    print("\n  Bewege die Maus zur OBEREN LINKEN Ecke des Bereichs")
    print("  und drücke Enter...")
    try:
        input()
        x1, y1 = get_cursor_pos()
        print(f"  → Obere linke Ecke: ({x1}, {y1})")

        print("\n  Bewege die Maus zur UNTEREN RECHTEN Ecke des Bereichs")
        print("  und drücke Enter...")
        input()
        x2, y2 = get_cursor_pos()
        print(f"  → Untere rechte Ecke: ({x2}, {y2})")

        # Koordinaten sortieren (falls falsche Reihenfolge)
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1

        width = x2 - x1
        height = y2 - y1
        print(f"\n  Region: {width}x{height} Pixel ({x1},{y1}) → ({x2},{y2})")

        region = (x1, y1, x2, y2)
        return region

    except (KeyboardInterrupt, EOFError):
        print("\n  [ABBRUCH] Keine Region ausgewählt.")
        return None

def print_status(state: AutoClickerState) -> None:
    """Gibt den aktuellen Status aus."""
    with state.lock:
        status = "RUNNING" if state.is_running else "STOPPED"

        seq_name = state.active_sequence.name if state.active_sequence else "Keine"
        points_str = f"{len(state.points)} Punkt(e)"

        clear_line()
        if state.is_running and state.active_sequence:
            print(f"[{status}] Sequenz: {seq_name} | Klicks: {state.total_clicks}", flush=True)
        else:
            if state.active_sequence:
                seq_info = f"Start: {len(state.active_sequence.start_steps)}, Loops: {len(state.active_sequence.loop_phases)}"
                print(f"[{status}] {points_str} | Sequenz: {seq_name} ({seq_info})", flush=True)
            else:
                print(f"[{status}] {points_str} | Sequenz: {seq_name}", flush=True)

def print_points(state: AutoClickerState) -> None:
    """Zeigt alle gespeicherten Punkte an."""
    print("\n" + "=" * 50)
    print("GESPEICHERTE PUNKTE:")
    print("=" * 50)
    with state.lock:
        if not state.points:
            print("  Keine Punkte gespeichert.")
        else:
            for p in state.points:
                print(f"  {p}")

    print("\n" + "=" * 50)
    print("VERFÜGBARE SEQUENZEN:")
    print("=" * 50)
    sequences = list_available_sequences()
    if not sequences:
        print("  Keine Sequenzen gespeichert.")
    else:
        for name, path in sequences:
            seq = load_sequence_file(path)
            if seq:
                print(f"  • {seq}")
                if seq.start_steps:
                    print("      START:")
                    for i, step in enumerate(seq.start_steps):
                        print(f"        {i+1}. {step}")
                for lp in seq.loop_phases:
                    print(f"      {lp.name} (x{lp.repeat}):")
                    for i, step in enumerate(lp.steps):
                        print(f"        {i+1}. {step}")

    with state.lock:
        if state.active_sequence:
            print(f"\n  [AKTIV] {state.active_sequence.name}")
    print()

# =============================================================================
# GLOBALER SLOT-EDITOR
# =============================================================================
def run_global_slot_editor(state: AutoClickerState) -> None:
    """Editor für globale Slot-Definitionen - wie Sequenz-Editor mit Preset-Auswahl."""
    print("\n" + "=" * 60)
    print("  SLOT-EDITOR")
    print("=" * 60)

    if not PILLOW_AVAILABLE:
        print("\n[FEHLER] Pillow nicht installiert!")
        return

    # Verfügbare Slot-Presets laden
    available_presets = list_slot_presets()

    print("\nWas möchtest du tun?")
    print("  [0] Neues Slot-Preset erstellen")

    if available_presets:
        print("\nBestehende Slot-Presets bearbeiten:")
        for i, (name, path, count) in enumerate(available_presets):
            print(f"  [{i+1}] {name} ({count} Slots)")
        print("\n  del <Nr> - Preset löschen")

    print("\nAuswahl (oder 'cancel'):")

    # Preset-Auswahl
    preset_name = None
    while True:
        try:
            choice = input("> ").strip().lower()

            if choice in ("cancel", "abbruch"):
                print("[CANCEL] Editor beendet.")
                return

            # Löschen-Befehl
            if choice.startswith("del "):
                try:
                    del_num = int(choice[4:])
                    if 1 <= del_num <= len(available_presets):
                        name, path, count = available_presets[del_num - 1]
                        confirm = input(f"Preset '{name}' wirklich löschen? (j/n): ").strip().lower()
                        if confirm == "j":
                            delete_slot_preset(name)
                            # Liste aktualisieren
                            available_presets = list_slot_presets()
                            print("\nAktualisierte Liste:")
                            print("  [0] Neues Slot-Preset erstellen")
                            for i, (n, p, c) in enumerate(available_presets):
                                print(f"  [{i+1}] {n} ({c} Slots)")
                        else:
                            print("[ABBRUCH] Nicht gelöscht.")
                    else:
                        print(f"[FEHLER] Ungültiges Preset! Verfügbar: 1-{len(available_presets)}")
                except ValueError:
                    print("[FEHLER] Format: del <Nr>")
                continue

            choice_num = int(choice)

            if choice_num == 0:
                # Neues Preset erstellen
                preset_name = input("\nName des Slot-Presets: ").strip()
                if not preset_name:
                    preset_name = f"Slots_{int(time.time())}"
                # Slots für neues Preset leeren
                with state.lock:
                    state.global_slots.clear()
                break
            elif 1 <= choice_num <= len(available_presets):
                # Bestehendes Preset bearbeiten
                preset_name, path, count = available_presets[choice_num - 1]
                load_slot_preset(state, preset_name)
                break
            else:
                print("[FEHLER] Ungültige Auswahl! Nochmal versuchen...")

        except ValueError:
            print("[FEHLER] Bitte eine Nummer eingeben! Nochmal versuchen...")
        except (KeyboardInterrupt, EOFError):
            print("\n[ABBRUCH] Editor beendet.")
            return

    # Jetzt den eigentlichen Editor mit dem gewählten Preset starten
    print(f"\n--- Bearbeite Slot-Preset: {preset_name} ---")
    edit_slot_preset(state, preset_name)


def _slot_auto_detect(state: AutoClickerState) -> bool:
    """Automatische Slot-Erkennung. Gibt True zurück wenn erfolgreich."""
    print("\n" + "=" * 50)
    print("  AUTOMATISCHE SLOT-ERKENNUNG")
    print("=" * 50)
    print("\nMarkiere den Bereich mit den Slots:")
    print("  1. Maus auf OBEN-LINKS, ENTER")
    print("  2. Maus auf UNTEN-RECHTS, ENTER")

    region = select_region()
    if not region:
        print("  → Keine Region ausgewählt")
        return False

    offset_x, offset_y = region[0], region[1]
    print(f"\n  Region: {region}")
    print("  Mache Screenshot mit BitBlt in 2 Sekunden...")
    time.sleep(2)

    # Screenshot mit BitBlt (funktioniert mit Spielen)
    img = take_screenshot_bitblt(region)
    if img is None:
        print("  [FEHLER] Screenshot fehlgeschlagen!")
        return False

    print(f"  Screenshot: {img.size[0]}x{img.size[1]}")

    # Farbe für Slot-Erkennung scannen
    print("\n  Bewege Maus auf den SLOT-HINTERGRUND...")
    input("  ENTER wenn bereit...")
    mx, my = get_cursor_pos()

    # Farbe vom Bildschirm lesen
    hdc = ctypes.windll.user32.GetDC(0)
    color = ctypes.windll.gdi32.GetPixel(hdc, mx, my)
    ctypes.windll.user32.ReleaseDC(0, hdc)

    if color == -1:
        print("  [FEHLER] Konnte Farbe nicht lesen!")
        return False

    r = color & 0xFF
    g = (color >> 8) & 0xFF
    b = (color >> 16) & 0xFF
    print(f"  Farbe: RGB({r}, {g}, {b})")

    # RGB zu HSV
    r_n, g_n, b_n = r / 255, g / 255, b / 255
    max_c, min_c = max(r_n, g_n, b_n), min(r_n, g_n, b_n)
    diff = max_c - min_c

    if diff == 0:
        h = 0
    elif max_c == r_n:
        h = (60 * ((g_n - b_n) / diff) + 360) % 360
    elif max_c == g_n:
        h = (60 * ((b_n - r_n) / diff) + 120) % 360
    else:
        h = (60 * ((r_n - g_n) / diff) + 240) % 360

    s = 0 if max_c == 0 else (diff / max_c) * 255
    v = max_c * 255
    h = h / 2  # OpenCV Hue: 0-180

    print(f"  HSV: ({int(h)}, {int(s)}, {int(v)})")

    # Slots im Bild suchen (benötigt NumPy)
    if not NUMPY_AVAILABLE:
        print("  [FEHLER] NumPy nicht installiert! pip install numpy")
        return False

    img_array = np.array(img)
    img_bgr = img_array[:, :, ::-1].copy()

    try:
        import cv2
    except ImportError:
        print("  [FEHLER] OpenCV nicht installiert! pip install opencv-python")
        return False

    hsv_img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    tol = state.config.get("slot_hsv_tolerance", 25)
    lower = np.array([max(0, int(h) - tol), max(0, int(s) - 50), max(0, int(v) - 50)])
    upper = np.array([min(180, int(h) + tol), min(255, int(s) + 50), min(255, int(v) + 50)])

    mask = cv2.inRange(hsv_img, lower, upper)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Slots filtern
    detected_slots = []
    for contour in contours:
        x, y, w, h_box = cv2.boundingRect(contour)
        if w >= 40 and h_box >= 40:
            aspect = w / h_box
            if 0.5 < aspect < 2.0:
                detected_slots.append((x, y, w, h_box))

    detected_slots.sort(key=lambda s: (s[1] // 50, s[0]))

    if not detected_slots:
        print("\n  [FEHLER] Keine Slots erkannt!")
        print("  Versuche es mit einer anderen Farbe.")
        return False

    # Größen normalisieren
    if len(detected_slots) >= 2:
        widths = [s[2] for s in detected_slots]
        heights = [s[3] for s in detected_slots]
        median_w = sorted(widths)[len(widths) // 2]
        median_h = sorted(heights)[len(heights) // 2]

        normalized = []
        for x, y, w, h_box in detected_slots:
            if 0.7 * median_w <= w <= 1.3 * median_w:
                new_x = x + (w - median_w) // 2
                new_y = y + (h_box - median_h) // 2
                normalized.append((new_x, new_y, median_w, median_h))
        detected_slots = normalized

    print(f"\n  {len(detected_slots)} Slots erkannt!")

    # Hintergrundfarbe
    slot_color = [r, g, b]

    # Slots hinzufügen
    inset = state.config.get("slot_inset", 10)
    added = 0
    start_num = len(state.global_slots) + 1

    for i, (x, y, w, h_box) in enumerate(detected_slots):
        slot_name = f"Slot {start_num + i}"

        # Mit Offset und Inset
        abs_x = x + offset_x + inset
        abs_y = y + offset_y + inset
        abs_w = w - (2 * inset)
        abs_h = h_box - (2 * inset)

        scan_region = (abs_x, abs_y, abs_x + abs_w, abs_y + abs_h)
        click_pos = (abs_x + abs_w // 2, abs_y + abs_h // 2)

        new_slot = ItemSlot(
            name=slot_name,
            scan_region=scan_region,
            click_pos=click_pos,
            slot_color=slot_color
        )

        with state.lock:
            state.global_slots[slot_name] = new_slot
        added += 1
        print(f"    + {slot_name}: {scan_region}")

    print(f"\n  [OK] {added} Slots hinzugefügt!")

    # Screenshots speichern
    try:
        import cv2 as cv2_save
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        screenshot_path = os.path.join(SCREENSHOTS_DIR, f"screenshot_{timestamp}.png")
        img.save(screenshot_path)
        print(f"  Screenshot: {screenshot_path}")

        # Vorschau mit Markierungen
        preview_path = os.path.join(SCREENSHOTS_DIR, f"preview_{timestamp}.png")
        preview = img_bgr.copy()
        for i, (dx, dy, dw, dh) in enumerate(detected_slots):
            cv2_save.rectangle(preview, (dx, dy), (dx + dw, dy + dh), (0, 255, 0), 2)
            cv2_save.rectangle(preview, (dx + inset, dy + inset),
                              (dx + dw - inset, dy + dh - inset), (0, 255, 255), 1)

            click_x = dx + dw // 2
            click_y = dy + dh // 2
            cross_size = 8
            cv2_save.line(preview, (click_x - cross_size, click_y), (click_x + cross_size, click_y), (0, 0, 255), 2)
            cv2_save.line(preview, (click_x, click_y - cross_size), (click_x, click_y + cross_size), (0, 0, 255), 2)

            slot_num_text = str(start_num + i)
            font = cv2_save.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            thickness = 2
            text_x = dx + 5
            text_y = dy + 20
            (text_w, text_h), _ = cv2_save.getTextSize(slot_num_text, font, font_scale, thickness)
            cv2_save.rectangle(preview, (text_x - 2, text_y - text_h - 2),
                              (text_x + text_w + 2, text_y + 2), (0, 0, 0), -1)
            cv2_save.putText(preview, slot_num_text, (text_x, text_y), font, font_scale, (255, 255, 255), thickness)
        cv2_save.imwrite(preview_path, preview)
        print(f"  Vorschau: {preview_path}")
    except (OSError, IOError, ValueError) as e:
        print(f"  [WARNUNG] Screenshots speichern: {e}")

    return True


def edit_slot_preset(state: AutoClickerState, preset_name: str) -> None:
    """Bearbeitet ein Slot-Preset (alle Änderungen werden unter diesem Namen gespeichert)."""

    # Aktuelle Slots anzeigen
    with state.lock:
        slots = dict(state.global_slots)

    if slots:
        print(f"\nVorhandene Slots ({len(slots)}):")
        for i, (name, slot) in enumerate(slots.items()):
            print(f"  {i+1}. {slot}")

    print("\n" + "-" * 60)
    print("Befehle:")
    print("  auto             - AUTOMATISCHE Slot-Erkennung (empfohlen)")
    print("  add              - Neuen Slot manuell hinzufügen")
    print("  edit <Nr>        - Slot bearbeiten")
    print("  del <Nr>         - Slot löschen")
    print("  del <Nr>-<Nr>    - Bereich löschen (z.B. del 1-7)")
    print("  del all          - ALLE Slots löschen")
    print("  show             - Alle Slots anzeigen")
    print("  done | cancel")
    print("-" * 60)

    while True:
        try:
            user_input = input("[Slots] > ").strip().lower()

            if user_input == "done":
                # Speichere mit dem Preset-Namen
                save_slot_preset(state, preset_name)
                # Auch als aktive Konfiguration speichern
                save_global_slots(state)
                print(f"\n[SAVE] Preset '{preset_name}' gespeichert!")
                return
            elif user_input == "cancel":
                print("\n[CANCEL] Änderungen verworfen!")
                return
            elif user_input == "":
                continue
            elif user_input == "show":
                with state.lock:
                    if state.global_slots:
                        print("\nSlots:")
                        for i, (name, slot) in enumerate(state.global_slots.items()):
                            print(f"  {i+1}. {slot}")
                    else:
                        print("  (Keine Slots)")
                continue

            elif user_input == "auto":
                _slot_auto_detect(state)
                continue

            elif user_input == "add":
                slot_num = len(state.global_slots) + 1
                slot_name = input(f"  Slot-Name (Enter = 'Slot {slot_num}', 'cancel'): ").strip()
                if slot_name.lower() in ("cancel", "abbruch"):
                    print("  → Slot-Erstellung abgebrochen")
                    continue
                if not slot_name:
                    slot_name = f"Slot {slot_num}"

                # Prüfen ob Name schon existiert
                with state.lock:
                    if slot_name in state.global_slots:
                        print(f"  → Slot '{slot_name}' existiert bereits!")
                        continue

                print(f"\n  --- Scan-Region für '{slot_name}' ---")
                print("  Wähle den Bereich wo das Item erscheint:")
                scan_region = select_region()
                if not scan_region:
                    print("  → Keine Region ausgewählt")
                    continue

                print(f"\n  --- Klick-Position für '{slot_name}' ---")
                print("  Maus auf die Klick-Position bewegen, ENTER drücken:")
                input()
                click_pos = get_cursor_pos()
                print(f"  → Klick-Position: {click_pos}")

                print("\n  Hintergrundfarbe aufnehmen? (j/n, Enter = n):")
                slot_color = None
                if input("  > ").strip().lower() == "j":
                    print("  Maus auf den leeren Slot-Hintergrund bewegen, ENTER drücken:")
                    input()
                    x, y = get_cursor_pos()
                    slot_color = get_pixel_color(x, y)
                    if slot_color:
                        slot_color = (slot_color[0] // 5 * 5, slot_color[1] // 5 * 5, slot_color[2] // 5 * 5)
                        color_name = get_color_name(slot_color)
                        print(f"  → Hintergrund: RGB{slot_color} ({color_name})")

                slot = ItemSlot(slot_name, scan_region, click_pos, slot_color)
                with state.lock:
                    state.global_slots[slot_name] = slot
                print(f"  ✓ Slot '{slot_name}' hinzugefügt!")
                continue

            elif user_input == "del all":
                with state.lock:
                    count = len(state.global_slots)
                    if count == 0:
                        print("  → Keine Slots vorhanden")
                    else:
                        state.global_slots.clear()
                        print(f"  ✓ Alle {count} Slots gelöscht!")
                continue

            elif user_input.startswith("del "):
                del_arg = user_input[4:].strip()
                with state.lock:
                    slot_names = list(state.global_slots.keys())
                    if not slot_names:
                        print("  → Keine Slots vorhanden!")
                        continue

                    # Bereichs-Löschen: del 1-7
                    if "-" in del_arg:
                        try:
                            parts = del_arg.split("-")
                            start = int(parts[0])
                            end = int(parts[1])
                            if start > end:
                                start, end = end, start
                            if start < 1 or end > len(slot_names):
                                print(f"  → Ungültiger Bereich! Verfügbar: 1-{len(slot_names)}")
                                continue
                            # Von hinten löschen damit Indizes stimmen
                            deleted = []
                            for i in range(end, start - 1, -1):
                                name = slot_names[i - 1]
                                del state.global_slots[name]
                                deleted.append(name)
                            print(f"  ✓ {len(deleted)} Slots gelöscht ({start}-{end})")
                        except (ValueError, IndexError):
                            print("  → Format: del <start>-<end> (z.B. del 1-7)")
                            continue
                    else:
                        # Einzelnes Löschen
                        try:
                            del_num = int(del_arg)
                            if 1 <= del_num <= len(slot_names):
                                name = slot_names[del_num - 1]
                                del state.global_slots[name]
                                print(f"  ✓ Slot '{name}' gelöscht!")
                            else:
                                print(f"  → Ungültiger Slot! Verfügbar: 1-{len(slot_names)}")
                                continue
                        except ValueError:
                            print("  → Format: del <Nr> oder del <start>-<end>")
                            continue

                    # Auto-Renummerierung wenn alle Slots "Slot X" heißen
                    remaining = list(state.global_slots.items())
                    if remaining:
                        all_numbered = all(
                            name.startswith("Slot ") and name[5:].isdigit()
                            for name, _ in remaining
                        )
                        if all_numbered:
                            # Neu nummerieren
                            new_slots = {}
                            for i, (old_name, slot) in enumerate(remaining):
                                new_name = f"Slot {i + 1}"
                                slot.name = new_name
                                new_slots[new_name] = slot
                            state.global_slots = new_slots
                            print(f"  → Slots neu nummeriert (1-{len(new_slots)})")
                continue

            elif user_input.startswith("edit "):
                try:
                    edit_num = int(user_input[5:])
                    with state.lock:
                        slot_names = list(state.global_slots.keys())
                        if 1 <= edit_num <= len(slot_names):
                            name = slot_names[edit_num - 1]
                            slot = state.global_slots[name]
                            print(f"\n  Bearbeite '{name}':")
                            print("  Scan-Region neu aufnehmen? (j/n):")
                            if input("  > ").strip().lower() == "j":
                                new_region = select_region()
                                if new_region:
                                    slot.scan_region = new_region
                            print("  Klick-Position neu aufnehmen? (j/n):")
                            if input("  > ").strip().lower() == "j":
                                print("  Maus positionieren, ENTER drücken:")
                                input()
                                slot.click_pos = get_cursor_pos()
                            print("  Hintergrundfarbe neu aufnehmen? (j/n):")
                            if input("  > ").strip().lower() == "j":
                                print("  Maus auf Hintergrund bewegen, ENTER drücken:")
                                input()
                                x, y = get_cursor_pos()
                                slot.slot_color = get_pixel_color(x, y)
                                if slot.slot_color:
                                    slot.slot_color = (slot.slot_color[0] // 5 * 5, slot.slot_color[1] // 5 * 5, slot.slot_color[2] // 5 * 5)
                            print(f"  ✓ Slot aktualisiert!")
                        else:
                            print(f"  → Ungültiger Slot!")
                except ValueError:
                    print("  → Format: edit <Nr>")
                continue

            else:
                print("  → Unbekannter Befehl")

        except (KeyboardInterrupt, EOFError):
            # Speichere mit dem Preset-Namen
            save_slot_preset(state, preset_name)
            save_global_slots(state)
            print(f"\n[SAVE] Preset '{preset_name}' gespeichert!")
            return


# =============================================================================
# GLOBALER ITEM-EDITOR
# =============================================================================
def run_global_item_editor(state: AutoClickerState) -> None:
    """Editor für globale Item-Definitionen - wie Sequenz-Editor mit Preset-Auswahl."""
    print("\n" + "=" * 60)
    print("  ITEM-EDITOR")
    print("=" * 60)

    if not PILLOW_AVAILABLE:
        print("\n[FEHLER] Pillow nicht installiert!")
        return

    # Verfügbare Item-Presets laden
    available_presets = list_item_presets()

    print("\nWas möchtest du tun?")
    print("  [0] Neues Item-Preset erstellen")

    if available_presets:
        print("\nBestehende Item-Presets bearbeiten:")
        for i, (name, path, count) in enumerate(available_presets):
            print(f"  [{i+1}] {name} ({count} Items)")
        print("\n  del <Nr> - Preset löschen")

    print("\nAuswahl (oder 'cancel'):")

    # Preset-Auswahl
    preset_name = None
    while True:
        try:
            choice = input("> ").strip().lower()

            if choice in ("cancel", "abbruch"):
                print("[CANCEL] Editor beendet.")
                return

            # Löschen-Befehl
            if choice.startswith("del "):
                try:
                    del_num = int(choice[4:])
                    if 1 <= del_num <= len(available_presets):
                        name, path, count = available_presets[del_num - 1]
                        confirm = input(f"Preset '{name}' wirklich löschen? (j/n): ").strip().lower()
                        if confirm == "j":
                            delete_item_preset(name)
                            # Liste aktualisieren
                            available_presets = list_item_presets()
                            print("\nAktualisierte Liste:")
                            print("  [0] Neues Item-Preset erstellen")
                            for i, (n, p, c) in enumerate(available_presets):
                                print(f"  [{i+1}] {n} ({c} Items)")
                        else:
                            print("[ABBRUCH] Nicht gelöscht.")
                    else:
                        print(f"[FEHLER] Ungültiges Preset! Verfügbar: 1-{len(available_presets)}")
                except ValueError:
                    print("[FEHLER] Format: del <Nr>")
                continue

            choice_num = int(choice)

            if choice_num == 0:
                # Neues Preset erstellen
                preset_name = input("\nName des Item-Presets: ").strip()
                if not preset_name:
                    preset_name = f"Items_{int(time.time())}"
                # Items für neues Preset leeren
                with state.lock:
                    state.global_items.clear()
                break
            elif 1 <= choice_num <= len(available_presets):
                # Bestehendes Preset bearbeiten
                preset_name, path, count = available_presets[choice_num - 1]
                load_item_preset(state, preset_name)
                break
            else:
                print("[FEHLER] Ungültige Auswahl! Nochmal versuchen...")

        except ValueError:
            print("[FEHLER] Bitte eine Nummer eingeben! Nochmal versuchen...")
        except (KeyboardInterrupt, EOFError):
            print("\n[ABBRUCH] Editor beendet.")
            return

    # Jetzt den eigentlichen Editor mit dem gewählten Preset starten
    print(f"\n--- Bearbeite Item-Preset: {preset_name} ---")
    edit_item_preset(state, preset_name)


def _item_learn_command(state: AutoClickerState, user_input: str) -> bool:
    """Verarbeitet den learn-Befehl (Bulk und Single). Gibt True zurück wenn verarbeitet."""
    with state.lock:
        slot_list = list(state.global_slots.values())

    if not slot_list:
        print("  → Keine Slots vorhanden! Erst Slots mit 'auto' im Slot-Editor erstellen.")
        return True

    # Bulk-Learn: learn 5-10 [template|simple]
    learn_arg = user_input[5:].strip() if user_input.startswith("learn ") else ""
    if "-" in learn_arg:
        parts = learn_arg.split()
        range_part = parts[0]
        mode_part = parts[1] if len(parts) > 1 else "template"

        try:
            range_parts = range_part.split("-")
            start_slot = int(range_parts[0])
            end_slot = int(range_parts[1])

            if start_slot < 1 or end_slot > len(slot_list) or start_slot > end_slot:
                print(f"  → Ungültiger Bereich! Verfügbar: 1-{len(slot_list)}")
                return True

            use_template = mode_part.lower() in ("template", "t")
            mode_str = "MIT Template" if use_template else "OHNE Template"

            print(f"\n  === BULK LEARN: Slots {start_slot}-{end_slot} ({mode_str}) ===")

            # Kategorie einmal für alle abfragen
            print("  Kategorie für alle Items (Enter = keine):")
            category = select_category(state, show_explanation=False)

            # Bestätigungs-Punkt einmal für alle abfragen
            confirm_point = None
            confirm_delay = 0.5
            confirm_input = input("  Bestätigungs-Punkt-ID für alle (Enter = keine): ").strip()
            if confirm_input:
                try:
                    point_id = int(confirm_input)
                    found_point = get_point_by_id(state, point_id)
                    if found_point:
                        confirm_point = found_point
                        delay_input = input("  Wartezeit vor Bestätigung (Enter = 0.5s): ").strip()
                        if delay_input:
                            try:
                                confirm_delay = float(delay_input)
                            except ValueError:
                                pass
                except ValueError:
                    pass

            created_count = 0
            for slot_idx in range(start_slot - 1, end_slot):
                slot = slot_list[slot_idx]
                item_name = f"{slot.name} Item"

                # Eindeutigen Namen sicherstellen
                base_name = item_name
                counter = 1
                while item_name in state.global_items:
                    counter += 1
                    item_name = f"{base_name} {counter}"

                priority = slot_idx - start_slot + 2

                # Item erstellen
                item = ItemProfile(
                    name=item_name,
                    marker_colors=[],
                    category=category,
                    priority=priority,
                    confirm_point=confirm_point,
                    confirm_delay=confirm_delay,
                    min_confidence=DEFAULT_MIN_CONFIDENCE
                )

                # Template speichern wenn gewünscht
                if use_template and OPENCV_AVAILABLE:
                    template_img = take_screenshot(slot.scan_region)
                    if template_img:
                        safe_name = sanitize_filename(item_name)
                        template_file = f"{safe_name}.png"
                        template_path = Path(TEMPLATES_DIR) / template_file
                        template_img.save(template_path)
                        item.template = template_file

                with state.lock:
                    state.global_items[item_name] = item
                created_count += 1

                template_str = f" + {item.template}" if item.template else ""
                print(f"    ✓ {item_name} (P{priority}){template_str}")

            save_global_items(state)
            print(f"\n  === {created_count} Items erstellt! ===")
            return True

        except (ValueError, IndexError):
            print("  → Format: learn <von>-<bis> [template|simple]")
            print("    Beispiel: learn 1-5 template  (mit Screenshot)")
            print("    Beispiel: learn 1-5 simple    (ohne Screenshot)")
            return True

    # Single-Learn: Slot-Nummer aus Befehl oder nachfragen
    slot_num = None
    if user_input.startswith("learn "):
        try:
            slot_num = int(user_input[6:])
        except ValueError:
            pass

    if slot_num is None:
        print(f"\n  Verfügbare Slots (1-{len(slot_list)}):")
        for i, slot in enumerate(slot_list):
            print(f"    {i+1}. {slot.name}")
        try:
            slot_input = input("  Slot-Nr wo das Item liegt: ").strip()
            if slot_input.lower() in ("cancel", "abbruch"):
                return True
            slot_num = int(slot_input)
        except ValueError:
            print("  → Ungültige Eingabe!")
            return True

    if slot_num < 1 or slot_num > len(slot_list):
        print(f"  → Ungültiger Slot! Verfügbar: 1-{len(slot_list)}")
        return True

    selected_slot = slot_list[slot_num - 1]
    print(f"\n  Scanne Slot '{selected_slot.name}'...")

    # Item-Name abfragen
    item_num = len(state.global_items) + 1
    item_name = input(f"  Item-Name (Enter = 'Item {item_num}'): ").strip()
    if item_name.lower() in ("cancel", "abbruch"):
        return True
    if not item_name:
        item_name = f"Item {item_num}"

    # Prüfen ob Name schon existiert
    with state.lock:
        if item_name in state.global_items:
            print(f"  → Item '{item_name}' existiert bereits!")
            return True

    # Kategorie zuerst (für Prioritäts-Verschiebung)
    category = select_category(state)

    # Priorität
    priority = 1
    try:
        prio_input = input(f"  Priorität (1=beste, 0=beste+verschieben, Enter={priority}): ").strip()
        if prio_input.lower() in ("cancel", "abbruch"):
            print("  → Abgebrochen")
            return True
        if prio_input:
            prio_val = int(prio_input)
            if prio_val == 0:
                if category:
                    shift_category_priorities(state, category)
                    priority = 1
                else:
                    print("  → Priorität 0 nur mit Kategorie möglich!")
                    priority = 1
            else:
                priority = max(1, prio_val)
    except ValueError:
        pass

    # Screenshot des Slots machen und Farben extrahieren
    print(f"  Scanne Farben in Region {selected_slot.scan_region}...")
    marker_colors = collect_marker_colors(selected_slot.scan_region, selected_slot.slot_color)

    if not marker_colors:
        print("  → Keine Farben gefunden!")
        return True

    # Bestätigungs-Klick abfragen
    confirm_point = None
    confirm_delay = 0.5
    print("\n  Soll nach dem Item-Klick noch ein Bestätigungs-Klick erfolgen?")
    print("  (z.B. auf einen 'Accept' oder 'Craft' Button)")
    confirm_input = input("  Punkt-ID für Bestätigung (Enter = Nein): ").strip()
    if confirm_input.lower() in ("cancel", "abbruch"):
        print("  → Abgebrochen")
        return True
    if confirm_input:
        try:
            point_id = int(confirm_input)
            found_point = get_point_by_id(state, point_id)
            if found_point:
                confirm_point = found_point
                delay_input = input("  Wartezeit vor Bestätigung in Sek (Enter = 0.5): ").strip()
                if delay_input:
                    try:
                        confirm_delay = float(delay_input)
                    except ValueError:
                        pass
            else:
                print(f"  → Punkt #{point_id} existiert nicht")
        except ValueError:
            print("  → Keine gültige Zahl, keine Bestätigung")

    # Item erstellen und speichern
    item = ItemProfile(item_name, marker_colors, category, priority, confirm_point, confirm_delay)

    # Optional: Auch als Template speichern?
    if OPENCV_AVAILABLE:
        save_template = input("  Auch als Template speichern? (j/n, Enter=n): ").strip().lower()
        if save_template == "j":
            template_img = take_screenshot(selected_slot.scan_region)
            if template_img:
                safe_name = sanitize_filename(item_name)
                template_file = f"{safe_name}.png"
                template_path = Path(TEMPLATES_DIR) / template_file
                template_img.save(template_path)
                item.template = template_file

                # Konfidenz abfragen
                conf_input = input(f"  Min. Konfidenz für Template (Enter={item.min_confidence:.0%}): ").strip()
                if conf_input:
                    try:
                        conf = float(conf_input.replace("%", "")) / 100
                        item.min_confidence = max(0.1, min(1.0, conf))
                    except ValueError:
                        pass

                print(f"  ✓ Template gespeichert: {template_file}")

    with state.lock:
        state.global_items[item_name] = item

    save_global_items(state)

    confirm_str = f" → ({confirm_point.x},{confirm_point.y}) nach {confirm_delay}s" if confirm_point else ""
    template_str = f" + Template" if item.template else ""
    print(f"  ✓ Item '{item_name}' gelernt mit {len(marker_colors)} Marker-Farben!{confirm_str}{template_str}")
    return True


def edit_item_preset(state: AutoClickerState, preset_name: str) -> None:
    """Bearbeitet ein Item-Preset (alle Änderungen werden unter diesem Namen gespeichert)."""

    # Aktuelle Items anzeigen
    with state.lock:
        items = dict(state.global_items)

    if items:
        print(f"\nVorhandene Items ({len(items)}):")
        for i, (name, item) in enumerate(items.items()):
            print(f"  {i+1}. {item}")

    # Verfügbare Slots anzeigen
    with state.lock:
        slots = dict(state.global_slots)
    if slots:
        print(f"\nVerfügbare Slots für Item-Lernen ({len(slots)}):")
        for i, (name, slot) in enumerate(slots.items()):
            print(f"  {i+1}. {slot.name}")

    print("\n" + "-" * 60)
    print("Befehle:")
    print("  learn <Nr>       - Item aus Slot lernen (automatisch!)")
    print("  learn <Nr>-<Nr>  - Bulk: Items für Slot-Bereich (mit Template)")
    print("  learn <Nr>-<Nr> simple - Bulk: ohne Template")
    print("  add              - Neues Item manuell hinzufügen")
    print("  edit <Nr>        - Item bearbeiten")
    print("  rename <Nr>      - Item umbenennen (inkl. Template)")
    print("  del <Nr>         - Item löschen")
    print("  del all          - Alle Items löschen")
    print("  show             - Alle Items anzeigen")
    print("  template <Nr>    - Template für Item setzen/entfernen")
    print("  templates        - Verfügbare Templates anzeigen")
    print("  done | cancel")
    print("-" * 60)

    while True:
        try:
            user_input = input("[Items] > ").strip().lower()

            if user_input == "done":
                # Speichere mit dem Preset-Namen
                save_item_preset(state, preset_name)
                # Auch als aktive Konfiguration speichern
                save_global_items(state)
                print(f"\n[SAVE] Preset '{preset_name}' gespeichert!")
                return
            elif user_input == "cancel":
                print("\n[CANCEL] Änderungen verworfen!")
                return
            elif user_input == "":
                continue
            elif user_input == "show":
                with state.lock:
                    if state.global_items:
                        print("\nItems (sortiert nach Priorität):")
                        sorted_items = sorted(state.global_items.values(), key=lambda x: x.priority)
                        for i, item in enumerate(sorted_items):
                            print(f"  {i+1}. {item}")
                    else:
                        print("  (Keine Items)")
                continue

            elif user_input.startswith("learn"):
                _item_learn_command(state, user_input)
                continue

            elif user_input == "del all":
                with state.lock:
                    count = len(state.global_items)
                    if count == 0:
                        print("  → Keine Items vorhanden!")
                        continue
                    confirm = input(f"  {count} Item(s) wirklich löschen? (j/n): ").strip().lower()
                    if confirm == "j":
                        state.global_items.clear()
                        print(f"  ✓ {count} Item(s) gelöscht!")
                    else:
                        print("  → Abgebrochen")
                continue

            elif user_input == "add":
                item_num = len(state.global_items) + 1
                item_name = input(f"  Item-Name (Enter = 'Item {item_num}', 'cancel'): ").strip()
                if item_name.lower() in ("cancel", "abbruch"):
                    print("  → Item-Erstellung abgebrochen")
                    continue
                if not item_name:
                    item_name = f"Item {item_num}"

                # Prüfen ob Name schon existiert
                with state.lock:
                    if item_name in state.global_items:
                        print(f"  → Item '{item_name}' existiert bereits!")
                        continue

                # Kategorie zuerst (für Prioritäts-Verschiebung)
                category = select_category(state)

                # Priorität (0 = alle in Kategorie verschieben und P1 werden)
                priority = 1
                try:
                    prio_input = input(f"  Priorität (1=beste, 0=beste+verschieben, Enter={priority}, 'cancel'): ").strip()
                    if prio_input.lower() in ("cancel", "abbruch"):
                        print("  → Item-Erstellung abgebrochen")
                        continue
                    if prio_input:
                        prio_val = int(prio_input)
                        if prio_val == 0:
                            if category:
                                shift_category_priorities(state, category)
                                priority = 1
                            else:
                                print("  → Priorität 0 nur mit Kategorie möglich!")
                                priority = 1
                        else:
                            priority = max(1, prio_val)
                except ValueError:
                    pass

                # Marker-Farben sammeln (immer freier Bereich bei globalem Item)
                marker_colors = collect_marker_colors_free()
                if not marker_colors:
                    print("  → Keine Farben gefunden, Item-Erstellung abgebrochen")
                    continue

                # Bestätigungs-Punkt abfragen
                confirm_point = None
                confirm_delay = 0.5
                confirm_input = input("  Bestätigung nötig? (Enter = Nein, Punkt-ID = Ja): ").strip()
                if confirm_input:
                    try:
                        point_id = int(confirm_input)
                        found_point = get_point_by_id(state, point_id)
                        if found_point:
                            confirm_point = found_point  # Koordinaten speichern
                            delay_input = input("  Wartezeit vor Bestätigung (Enter = 0.5s): ").strip()
                            if delay_input:
                                try:
                                    confirm_delay = float(delay_input)
                                except ValueError:
                                    pass
                        else:
                            print(f"  → Punkt #{point_id} existiert nicht")
                    except ValueError:
                        pass

                item = ItemProfile(item_name, marker_colors, category, priority, confirm_point, confirm_delay)
                with state.lock:
                    state.global_items[item_name] = item
                save_global_items(state)
                confirm_str = f" → ({confirm_point.x},{confirm_point.y})" if confirm_point else ""
                cat_str = f" [{category}]" if category else ""
                print(f"  ✓ Item '{item_name}'{cat_str} hinzugefügt!{confirm_str}")
                continue

            elif user_input.startswith("del "):
                try:
                    del_num = int(user_input[4:])
                    with state.lock:
                        item_names = list(state.global_items.keys())
                        if 1 <= del_num <= len(item_names):
                            name = item_names[del_num - 1]
                            del state.global_items[name]
                            print(f"  ✓ Item '{name}' gelöscht!")
                        else:
                            print(f"  → Ungültiges Item! Verfügbar: 1-{len(item_names)}")
                except ValueError:
                    print("  → Format: del <Nr>")
                continue

            elif user_input.startswith("edit "):
                try:
                    edit_num = int(user_input[5:])
                    with state.lock:
                        item_names = list(state.global_items.keys())
                        if 1 <= edit_num <= len(item_names):
                            name = item_names[edit_num - 1]
                            item = state.global_items[name]
                            print(f"\n  Bearbeite '{name}':")

                            # Priorität
                            try:
                                prio_input = input(f"  Priorität (aktuell {item.priority}, Enter=behalten): ").strip()
                                if prio_input:
                                    item.priority = max(1, int(prio_input))
                            except ValueError:
                                pass

                            # Farben neu sammeln?
                            if input("  Marker-Farben neu sammeln? (j/n): ").strip().lower() == "j":
                                new_colors = collect_marker_colors_free()
                                if new_colors:
                                    item.marker_colors = new_colors

                            # Bestätigung
                            current_confirm = f"({item.confirm_point.x},{item.confirm_point.y})" if item.confirm_point else "Keine"
                            confirm_input = input(f"  Bestätigung (aktuell {current_confirm}, Punkt-ID=setzen, 0=entfernen, Enter=behalten): ").strip()
                            if confirm_input == "0":
                                item.confirm_point = None
                            elif confirm_input:
                                try:
                                    point_id = int(confirm_input)
                                    found_point = get_point_by_id(state, point_id)
                                    if found_point:
                                        item.confirm_point = found_point  # Koordinaten speichern
                                        delay_input = input(f"  Wartezeit (aktuell {item.confirm_delay}s, Enter=behalten): ").strip()
                                        if delay_input:
                                            try:
                                                item.confirm_delay = float(delay_input)
                                            except ValueError:
                                                pass
                                    else:
                                        print(f"  → Punkt #{point_id} existiert nicht")
                                except ValueError:
                                    pass

                            print(f"  ✓ Item aktualisiert!")
                        else:
                            print(f"  → Ungültiges Item!")
                except ValueError:
                    print("  → Format: edit <Nr>")
                continue

            elif user_input.startswith("rename "):
                try:
                    rename_num = int(user_input[7:])
                    with state.lock:
                        item_names = list(state.global_items.keys())
                        if 1 <= rename_num <= len(item_names):
                            old_name = item_names[rename_num - 1]
                            item = state.global_items[old_name]

                            print(f"\n  Aktueller Name: '{old_name}'")
                            if item.template:
                                print(f"  Template: {item.template}")

                            new_name = input("  Neuer Name (Enter = abbrechen): ").strip()
                            if not new_name or new_name.lower() in ("cancel", "abbruch"):
                                print("  → Abgebrochen")
                                continue

                            if new_name == old_name:
                                print("  → Name ist identisch, nichts geändert")
                                continue

                            if new_name in state.global_items:
                                print(f"  → Name '{new_name}' existiert bereits!")
                                continue

                            # Template umbenennen falls vorhanden
                            old_template = item.template
                            if old_template:
                                old_template_path = Path(TEMPLATES_DIR) / old_template
                                # Neuer Template-Name basierend auf Item-Name
                                safe_name = new_name.lower().replace(" ", "_").replace("/", "_")
                                new_template = f"{safe_name}.png"
                                new_template_path = Path(TEMPLATES_DIR) / new_template

                                # Template-Pfad im Item IMMER aktualisieren
                                item.template = new_template

                                # Versuche auch die Datei umzubenennen
                                if old_template_path.exists():
                                    try:
                                        old_template_path.rename(new_template_path)
                                        print(f"  ✓ Template umbenannt: {old_template} → {new_template}")
                                    except Exception as e:
                                        print(f"  → Template-Datei Umbenennung fehlgeschlagen: {e}")
                                        print(f"    Template-Pfad aktualisiert: {new_template}")
                                else:
                                    print(f"  → Template-Datei nicht gefunden: {old_template}")
                                    print(f"    Template-Pfad aktualisiert: {new_template}")

                            # Item umbenennen
                            item.name = new_name
                            del state.global_items[old_name]
                            state.global_items[new_name] = item
                            save_global_items(state)

                            # Auch in allen Scan-Konfigurationen aktualisieren
                            updated_scans = update_item_in_scans(old_name, new_name, item.template)
                            if updated_scans > 0:
                                print(f"  ✓ {updated_scans} Scan-Konfiguration(en) aktualisiert")

                            print(f"  ✓ Item umbenannt: '{old_name}' → '{new_name}' (gespeichert)")
                        else:
                            print(f"  → Ungültiges Item! Verfügbar: 1-{len(item_names)}")
                except ValueError:
                    print("  → Format: rename <Nr>")
                continue

            elif user_input == "templates":
                # Zeige verfügbare Templates
                if not Path(TEMPLATES_DIR).exists():
                    print("  → Keine Templates vorhanden")
                    continue
                templates = list(Path(TEMPLATES_DIR).glob("*.png"))
                if not templates:
                    print("  → Keine Templates vorhanden")
                    print(f"    (Ordner: {TEMPLATES_DIR})")
                else:
                    print(f"\n  Verfügbare Templates ({len(templates)}):")
                    for t in sorted(templates):
                        print(f"    - {t.name}")
                continue

            elif user_input.startswith("template "):
                try:
                    item_num = int(user_input[9:])
                    with state.lock:
                        item_names = list(state.global_items.keys())
                        if 1 <= item_num <= len(item_names):
                            name = item_names[item_num - 1]
                            item = state.global_items[name]

                            # Verfügbare Templates anzeigen
                            templates = list(Path(TEMPLATES_DIR).glob("*.png")) if Path(TEMPLATES_DIR).exists() else []
                            if templates:
                                print(f"\n  Verfügbare Templates:")
                                for i, t in enumerate(sorted(templates)):
                                    print(f"    {i+1}. {t.name}")

                            current = item.template if item.template else "Keins"
                            print(f"\n  Item: {item.name}")
                            print(f"  Aktuelles Template: {current}")
                            print(f"  Aktuelle Konfidenz: {item.min_confidence:.0%}")

                            print("\n  Optionen:")
                            print("    <Dateiname.png> - Template setzen")
                            print("    <Nr>            - Template aus Liste wählen")
                            print("    capture         - Screenshot als Template speichern")
                            print("    remove          - Template entfernen")
                            print("    Enter           - Abbrechen")

                            template_input = input("  Template: ").strip()
                            if not template_input:
                                continue

                            if template_input.lower() == "remove":
                                item.template = None
                                print("  ✓ Template entfernt!")
                            elif template_input.lower() == "capture":
                                # Screenshot-Region abfragen
                                with state.lock:
                                    slot_list = list(state.global_slots.values())
                                if slot_list:
                                    print(f"\n  Screenshot von:")
                                    print("    0. Freie Region wählen")
                                    for i, slot in enumerate(slot_list):
                                        print(f"    {i+1}. {slot.name}")
                                    try:
                                        slot_choice = input("  Auswahl: ").strip()
                                        if slot_choice == "0":
                                            region = select_screen_region()
                                        else:
                                            slot_idx = int(slot_choice) - 1
                                            if 0 <= slot_idx < len(slot_list):
                                                region = slot_list[slot_idx].scan_region
                                            else:
                                                print("  → Ungültiger Slot!")
                                                continue
                                    except ValueError:
                                        region = select_screen_region()
                                else:
                                    region = select_screen_region()

                                if region:
                                    # Screenshot machen
                                    img = take_screenshot(region)
                                    if img:
                                        # Dateiname
                                        safe_name = sanitize_filename(item.name)
                                        template_file = f"{safe_name}.png"
                                        template_path = Path(TEMPLATES_DIR) / template_file
                                        img.save(template_path)
                                        item.template = template_file

                                        # Konfidenz abfragen
                                        conf_input = input(f"  Min. Konfidenz (Enter={item.min_confidence:.0%}): ").strip()
                                        if conf_input:
                                            try:
                                                conf = float(conf_input.replace("%", "")) / 100
                                                item.min_confidence = max(0.1, min(1.0, conf))
                                            except ValueError:
                                                pass

                                        print(f"  ✓ Template gespeichert: {template_file}")
                                    else:
                                        print("  → Screenshot fehlgeschlagen!")
                            else:
                                # Dateiname oder Nummer
                                try:
                                    template_num = int(template_input)
                                    if 1 <= template_num <= len(templates):
                                        item.template = sorted(templates)[template_num - 1].name
                                    else:
                                        print("  → Ungültige Nummer!")
                                        continue
                                except ValueError:
                                    # Direkter Dateiname
                                    if not template_input.endswith(".png"):
                                        template_input += ".png"
                                    item.template = template_input

                                # Konfidenz abfragen
                                conf_input = input(f"  Min. Konfidenz (aktuell {item.min_confidence:.0%}, Enter=behalten): ").strip()
                                if conf_input:
                                    try:
                                        conf = float(conf_input.replace("%", "")) / 100
                                        item.min_confidence = max(0.1, min(1.0, conf))
                                    except ValueError:
                                        pass

                                print(f"  ✓ Template gesetzt: {item.template} (≥{item.min_confidence:.0%})")
                        else:
                            print(f"  → Ungültiges Item!")
                except ValueError:
                    print("  → Format: template <Nr>")
                continue

            else:
                print("  → Unbekannter Befehl")

        except (KeyboardInterrupt, EOFError):
            # Speichere mit dem Preset-Namen
            save_item_preset(state, preset_name)
            save_global_items(state)
            print(f"\n[SAVE] Preset '{preset_name}' gespeichert!")
            return


# =============================================================================
# ITEM-SCAN HAUPTMENÜ
# =============================================================================
def run_item_scan_menu(state: AutoClickerState) -> None:
    """Hauptmenü für Slots, Items und Scans."""
    print("\n" + "=" * 60)
    print("  ITEM-SCAN SYSTEM")
    print("=" * 60)

    with state.lock:
        slot_count = len(state.global_slots)
        item_count = len(state.global_items)
        scan_count = len(state.item_scans)

    print(f"\n  [1] Slots bearbeiten     ({slot_count} vorhanden)")
    print(f"  [2] Items bearbeiten     ({item_count} vorhanden)")
    print(f"  [3] Scans bearbeiten     ({scan_count} vorhanden)")
    print("\n  [0] Abbrechen")

    try:
        choice = input("\n> ").strip()
        if choice == "1":
            run_global_slot_editor(state)
        elif choice == "2":
            run_global_item_editor(state)
        elif choice == "3":
            run_item_scan_editor(state)
        elif choice == "0" or choice.lower() in ("cancel", "abbruch"):
            return
        else:
            print("[FEHLER] Ungültige Auswahl")
    except (KeyboardInterrupt, EOFError):
        return


# =============================================================================
# ITEM-SCAN EDITOR (Verknüpfung)
# =============================================================================
def run_item_scan_editor(state: AutoClickerState) -> None:
    """Interaktiver Editor für Item-Scan Konfigurationen (verknüpft Slots + Items)."""
    print("\n" + "=" * 60)
    print("  SCAN-EDITOR (Slots + Items verknüpfen)")
    print("=" * 60)

    if not PILLOW_AVAILABLE:
        print("\n[FEHLER] Pillow nicht installiert!")
        print("         Installieren mit: pip install pillow")
        return

    # Bestehende Item-Scans anzeigen
    available_scans = list_available_item_scans()

    print("\nWas möchtest du tun?")
    print("  [0] Neuen Item-Scan erstellen")

    if available_scans:
        print("\nBestehende Item-Scans bearbeiten:")
        for i, (name, path) in enumerate(available_scans):
            config = load_item_scan_file(path)
            if config:
                print(f"  [{i+1}] {config}")
        print("\n  del <Nr> - Item-Scan löschen")

    print("\nAuswahl (oder 'cancel'):")

    while True:
        try:
            choice = input("> ").strip().lower()

            if choice in ("cancel", "abbruch"):
                print("[CANCEL] Editor beendet.")
                return

            # Löschen-Befehl
            if choice.startswith("del "):
                try:
                    del_num = int(choice[4:])
                    if 1 <= del_num <= len(available_scans):
                        name, path = available_scans[del_num - 1]
                        confirm = input(f"Item-Scan '{name}' wirklich löschen? (j/n): ").strip().lower()
                        if confirm == "j":
                            Path(path).unlink()
                            with state.lock:
                                if name in state.item_scans:
                                    del state.item_scans[name]
                            print(f"[OK] Item-Scan '{name}' gelöscht!")
                            return
                        else:
                            print("[ABBRUCH] Nicht gelöscht.")
                    else:
                        print(f"[FEHLER] Ungültiger Scan! Verfügbar: 1-{len(available_scans)}")
                except ValueError:
                    print("[FEHLER] Format: del <Nr>")
                continue

            choice_num = int(choice)

            if choice_num == 0:
                edit_item_scan(state, None)
                return
            elif 1 <= choice_num <= len(available_scans):
                name, path = available_scans[choice_num - 1]
                existing = load_item_scan_file(path)
                if existing:
                    edit_item_scan(state, existing)
                return
            else:
                print("[FEHLER] Ungültige Auswahl! Nochmal versuchen...")

        except ValueError:
            print("[FEHLER] Bitte eine Nummer eingeben! Nochmal versuchen...")
        except (KeyboardInterrupt, EOFError):
            print("\n[ABBRUCH] Editor beendet.")
            return


def edit_item_scan(state: AutoClickerState, existing: Optional[ItemScanConfig]) -> None:
    """Bearbeitet eine Item-Scan Konfiguration (verknüpft globale Slots + Items)."""

    # === SCHRITT 0: Presets auswählen ===
    print("\n" + "=" * 60)
    print("  PRESETS AUSWÄHLEN")
    print("=" * 60)

    # Slot-Presets anzeigen
    slot_presets = list_slot_presets()
    print("\nSlot-Presets:")
    if slot_presets:
        for i, (name, path, count) in enumerate(slot_presets):
            print(f"  [{i+1}] {name} ({count} Slots)")
    print("  [0] Aktuelle Slots verwenden")

    # Slot-Preset auswählen
    while True:
        try:
            slot_choice = input("\nSlot-Preset wählen (Enter=0, 'cancel'): ").strip()
            if slot_choice.lower() in ("cancel", "abbruch"):
                print("  → Abgebrochen")
                return
            if not slot_choice or slot_choice == "0":
                break
            slot_num = int(slot_choice)
            if 1 <= slot_num <= len(slot_presets):
                preset_name, _, _ = slot_presets[slot_num - 1]
                load_slot_preset(state, preset_name)
                break
            else:
                print(f"  → Ungültig! 0-{len(slot_presets)}")
        except ValueError:
            print("  → Bitte eine Nummer eingeben!")
        except (KeyboardInterrupt, EOFError):
            return

    # Item-Presets anzeigen
    item_presets = list_item_presets()
    print("\nItem-Presets:")
    if item_presets:
        for i, (name, path, count) in enumerate(item_presets):
            print(f"  [{i+1}] {name} ({count} Items)")
    print("  [0] Aktuelle Items verwenden / Keine (neu erstellen)")

    # Item-Preset auswählen
    while True:
        try:
            item_choice = input("\nItem-Preset wählen (Enter=0, 'cancel'): ").strip()
            if item_choice.lower() in ("cancel", "abbruch"):
                print("  → Abgebrochen")
                return
            if not item_choice or item_choice == "0":
                break
            item_num = int(item_choice)
            if 1 <= item_num <= len(item_presets):
                preset_name, _, _ = item_presets[item_num - 1]
                load_item_preset(state, preset_name)
                break
            else:
                print(f"  → Ungültig! 0-{len(item_presets)}")
        except ValueError:
            print("  → Bitte eine Nummer eingeben!")
        except (KeyboardInterrupt, EOFError):
            return

    # Prüfe ob globale Slots vorhanden sind
    with state.lock:
        available_slots = dict(state.global_slots)
        available_items = dict(state.global_items)

    if not available_slots:
        print("\n[FEHLER] Keine Slots im gewählten Preset!")
        print("         Erstelle zuerst Slots im Slot-Editor (Option 1)")
        return

    # Items sind optional - können im Scan-Editor erstellt werden
    if not available_items:
        print("\n[INFO] Keine Items im gewählten Preset.")
        print("       Du kannst sie gleich per Template erstellen!")

    if existing:
        print(f"\n--- Bearbeite Scan: {existing.name} ---")
        scan_name = existing.name
        selected_slot_names = [s.name for s in existing.slots]
        selected_item_names = [i.name for i in existing.items]
        tolerance = existing.color_tolerance
    else:
        print("\n--- Neuen Scan erstellen ---")
        scan_name = input("Name des Scans: ").strip()
        if not scan_name:
            scan_name = f"Scan_{int(time.time())}"
        selected_slot_names = []
        selected_item_names = []
        tolerance = 40

    # Schritt 1: Slots auswählen
    print("\n" + "=" * 60)
    print("  SCHRITT 1: SLOTS AUSWÄHLEN")
    print("=" * 60)
    print("\nVerfügbare Slots:")
    slot_list = list(available_slots.keys())
    for i, name in enumerate(slot_list):
        selected = "✓" if name in selected_slot_names else " "
        print(f"  [{selected}] {i+1}. {available_slots[name]}")

    print("\nBefehle: '<Nr>', '<Von>-<Bis>' (z.B. 1-5), 'all', 'clear', 'done', 'cancel'")
    while True:
        try:
            inp = input("[Slots] > ").strip().lower()
            if inp == "done":
                break
            elif inp == "cancel":
                return
            elif inp == "all":
                selected_slot_names = list(slot_list)
                print(f"  ✓ Alle {len(slot_list)} Slots ausgewählt")
            elif inp == "clear":
                selected_slot_names = []
                print("  ✓ Auswahl gelöscht")
            elif inp == "show":
                print(f"\nAusgewählt: {', '.join(selected_slot_names) if selected_slot_names else '(keine)'}")
            elif "-" in inp:
                # Bereich: 1-5
                try:
                    parts = inp.split("-")
                    start = int(parts[0])
                    end = int(parts[1])
                    if 1 <= start <= len(slot_list) and 1 <= end <= len(slot_list):
                        for num in range(min(start, end), max(start, end) + 1):
                            name = slot_list[num - 1]
                            if name not in selected_slot_names:
                                selected_slot_names.append(name)
                        print(f"  + Slots {start}-{end} hinzugefügt")
                    else:
                        print(f"  → Ungültig! 1-{len(slot_list)}")
                except (ValueError, IndexError):
                    print("  → Format: <Von>-<Bis> (z.B. 1-5)")
            else:
                try:
                    num = int(inp)
                    if 1 <= num <= len(slot_list):
                        name = slot_list[num - 1]
                        if name in selected_slot_names:
                            selected_slot_names.remove(name)
                            print(f"  - {name} entfernt")
                        else:
                            selected_slot_names.append(name)
                            print(f"  + {name} hinzugefügt")
                    else:
                        print(f"  → Ungültig! 1-{len(slot_list)}")
                except ValueError:
                    print("  → Unbekannter Befehl")
        except (KeyboardInterrupt, EOFError):
            return

    if not selected_slot_names:
        print("\n[FEHLER] Mindestens 1 Slot erforderlich!")
        return

    # Schritt 2: Items auswählen oder erstellen
    print("\n" + "=" * 60)
    print("  SCHRITT 2: ITEMS AUSWÄHLEN / ERSTELLEN")
    print("=" * 60)

    # Zeige verfügbare Templates
    templates = list(Path(TEMPLATES_DIR).glob("*.png")) if Path(TEMPLATES_DIR).exists() else []
    if templates:
        print(f"\nVerfügbare Templates ({len(templates)}):")
        for t in sorted(templates)[:10]:  # Max 10 anzeigen
            print(f"    {t.name}")
        if len(templates) > 10:
            print(f"    ... und {len(templates) - 10} weitere")

    # Aktualisiere available_items
    with state.lock:
        available_items = dict(state.global_items)

    print("\nVerfügbare Items:")
    item_list = list(available_items.keys())
    if item_list:
        for i, name in enumerate(item_list):
            selected = "✓" if name in selected_item_names else " "
            print(f"  [{selected}] {i+1}. {available_items[name]}")
    else:
        print("  (Keine Items - erstelle welche mit 'new')")

    print("\n" + "-" * 40)
    print("Befehle:")
    print("  <Nr>              - Item auswählen/abwählen")
    print("  <Von>-<Bis>       - Bereich auswählen (z.B. 1-5)")
    print("  all | clear       - Alle auswählen / Auswahl löschen")
    print("  new <Slot-Nr>     - Neues Item per Template von Slot erstellen")
    print("  done | cancel")
    print("-" * 40)

    while True:
        try:
            inp = input("[Items] > ").strip()
            inp_lower = inp.lower()

            if inp_lower == "done":
                break
            elif inp_lower == "cancel":
                return
            elif inp_lower == "all":
                selected_item_names = list(item_list)
                print(f"  ✓ Alle {len(item_list)} Items ausgewählt")
            elif inp_lower == "clear":
                selected_item_names = []
                print("  ✓ Auswahl gelöscht")
            elif inp_lower == "show":
                print(f"\nAusgewählt: {', '.join(selected_item_names) if selected_item_names else '(keine)'}")

            elif inp_lower.startswith("new"):
                # Neues Item per Template erstellen
                if not OPENCV_AVAILABLE:
                    print("  → OpenCV nicht installiert! (pip install opencv-python)")
                    continue

                # Slot-Nummer parsen
                slot_num = None
                if inp_lower.startswith("new "):
                    try:
                        slot_num = int(inp[4:])
                    except ValueError:
                        pass

                if slot_num is None:
                    print(f"\n  Von welchem Slot Screenshot machen? (1-{len(slot_list)})")
                    try:
                        slot_num = int(input("  Slot-Nr: ").strip())
                    except ValueError:
                        print("  → Ungültige Eingabe!")
                        continue

                if slot_num < 1 or slot_num > len(slot_list):
                    print(f"  → Ungültiger Slot! Verfügbar: 1-{len(slot_list)}")
                    continue

                # Screenshot vom Slot machen
                slot_name = slot_list[slot_num - 1]
                slot = available_slots[slot_name]
                print(f"\n  Mache Screenshot von {slot_name}...")

                template_img = take_screenshot(slot.scan_region)
                if not template_img:
                    print("  → Screenshot fehlgeschlagen!")
                    continue

                # Item-Name abfragen
                item_name = input("  Item-Name: ").strip()
                if not item_name:
                    item_name = f"Item_{len(item_list) + 1}"

                # Prüfen ob Name schon existiert
                if item_name in available_items:
                    print(f"  → '{item_name}' existiert bereits!")
                    continue

                # Template speichern
                safe_name = sanitize_filename(item_name)
                template_file = f"{safe_name}.png"
                template_path = Path(TEMPLATES_DIR) / template_file
                template_img.save(template_path)

                # Kategorie zuerst (für Prioritäts-Verschiebung)
                category = select_category(state)

                # Priorität (0 = alle in Kategorie verschieben und P1 werden)
                priority = 1
                try:
                    prio_input = input(f"  Priorität (1=beste, 0=beste+verschieben, Enter={priority}): ").strip()
                    if prio_input:
                        prio_val = int(prio_input)
                        if prio_val == 0:
                            if category:
                                shift_category_priorities(state, category)
                                priority = 1
                            else:
                                print("  → Priorität 0 nur mit Kategorie möglich!")
                                priority = 1
                        else:
                            priority = max(1, prio_val)
                except ValueError:
                    pass

                # Konfidenz
                min_confidence = DEFAULT_MIN_CONFIDENCE
                try:
                    conf_input = input(f"  Min. Konfidenz % (Enter={int(DEFAULT_MIN_CONFIDENCE * 100)}): ").strip()
                    if conf_input:
                        min_confidence = max(0.1, min(1.0, float(conf_input) / 100))
                except ValueError:
                    pass

                # Bestätigungs-Klick?
                confirm_point = None
                confirm_delay = 0.5
                confirm_input = input("  Bestätigungs-Punkt ID (Enter=Nein): ").strip()
                if confirm_input:
                    try:
                        point_id = int(confirm_input)
                        found_point = get_point_by_id(state, point_id)
                        if found_point:
                            confirm_point = found_point  # Koordinaten speichern
                            delay_input = input("  Wartezeit vor Bestätigung (Enter=0.5s): ").strip()
                            if delay_input:
                                confirm_delay = float(delay_input)
                        else:
                            print(f"  → Punkt #{point_id} existiert nicht")
                    except ValueError:
                        pass

                # Item erstellen
                new_item = ItemProfile(
                    name=item_name,
                    marker_colors=[],
                    category=category,
                    priority=priority,
                    confirm_point=confirm_point,
                    confirm_delay=confirm_delay,
                    template=template_file,
                    min_confidence=min_confidence
                )

                # Global speichern
                with state.lock:
                    state.global_items[item_name] = new_item
                save_global_items(state)

                # Listen aktualisieren
                available_items[item_name] = new_item
                item_list.append(item_name)
                selected_item_names.append(item_name)

                cat_str = f" [{category}]" if category else ""
                print(f"  ✓ Item '{item_name}'{cat_str} erstellt mit Template '{template_file}' ({min_confidence:.0%})")
                print(f"  ✓ Automatisch zum Scan hinzugefügt")

            elif "-" in inp_lower and not inp_lower.startswith("new"):
                # Bereich: 1-5
                try:
                    parts = inp_lower.split("-")
                    start = int(parts[0])
                    end = int(parts[1])
                    if 1 <= start <= len(item_list) and 1 <= end <= len(item_list):
                        for num in range(min(start, end), max(start, end) + 1):
                            name = item_list[num - 1]
                            if name not in selected_item_names:
                                selected_item_names.append(name)
                        print(f"  + Items {start}-{end} hinzugefügt")
                    else:
                        print(f"  → Ungültig! 1-{len(item_list)}")
                except (ValueError, IndexError):
                    print("  → Format: <Von>-<Bis> (z.B. 1-5)")
            else:
                try:
                    num = int(inp)
                    if 1 <= num <= len(item_list):
                        name = item_list[num - 1]
                        if name in selected_item_names:
                            selected_item_names.remove(name)
                            print(f"  - {name} entfernt")
                        else:
                            selected_item_names.append(name)
                            print(f"  + {name} hinzugefügt")
                    else:
                        print(f"  → Ungültig! 1-{len(item_list)}")
                except ValueError:
                    print("  → Unbekannter Befehl")
        except (KeyboardInterrupt, EOFError):
            return

    if not selected_item_names:
        print("\n[INFO] Keine Items ausgewählt.")
        if input("Trotzdem speichern? (j/n): ").strip().lower() != "j":
            print("[ABBRUCH] Scan nicht gespeichert.")
            return

    # Schritt 3: Toleranz
    print("\n" + "=" * 60)
    print("  SCHRITT 3: FARBTOLERANZ")
    print("=" * 60)
    print(f"\nAktuelle Toleranz: {tolerance}")
    print("(Höher = mehr Farben werden als 'gleich' erkannt)")
    try:
        tol_input = input(f"Neue Toleranz (Enter = {tolerance}): ").strip()
        if tol_input:
            tolerance = max(1, min(100, int(tol_input)))
    except ValueError:
        pass

    # Slots und Items aus globalen Definitionen holen
    with state.lock:
        slots = [state.global_slots[n] for n in selected_slot_names if n in state.global_slots]
        items = [state.global_items[n] for n in selected_item_names if n in state.global_items]

    # Speichern
    config = ItemScanConfig(
        name=scan_name,
        slots=slots,
        items=items,
        color_tolerance=tolerance
    )

    with state.lock:
        state.item_scans[scan_name] = config

    save_item_scan(config)

    print(f"\n[ERFOLG] Scan '{scan_name}' gespeichert!")
    print(f"         {len(slots)} Slots, {len(items)} Items")
    print(f"         Nutze im Sequenz-Editor: 'scan {scan_name}'")


def edit_item_slots(slots: list[ItemSlot]) -> list[ItemSlot]:
    """Bearbeitet die Slot-Liste für einen Item-Scan."""

    if slots:
        print(f"\nAktuelle Slots ({len(slots)}):")
        for i, slot in enumerate(slots):
            print(f"  {i+1}. {slot}")

    print("\n" + "-" * 60)
    print("Befehle:")
    print("  add            - Neuen Slot hinzufügen (Region + Klickpunkt)")
    print("  del <Nr>       - Slot löschen")
    print("  del <Nr>-<Nr>  - Bereich löschen (z.B. del 1-7)")
    print("  del all        - ALLE Slots löschen")
    print("  show           - Alle Slots anzeigen")
    print("  done | cancel")
    print("-" * 60)

    while True:
        try:
            prompt = f"[SLOTS: {len(slots)}]"
            user_input = input(f"{prompt} > ").strip().lower()

            if user_input == "done":
                return slots
            elif user_input == "cancel":
                return slots  # Gibt aktuelle Liste zurück (Sub-Editor)
            elif user_input == "":
                continue
            elif user_input == "show":
                if slots:
                    print("\nSlots:")
                    for i, slot in enumerate(slots):
                        print(f"  {i+1}. {slot}")
                else:
                    print("  (Keine Slots)")
                continue

            elif user_input == "add":
                slot_num = len(slots) + 1
                slot_name = input(f"  Slot-Name (Enter = 'Slot {slot_num}', 'cancel'): ").strip()
                if slot_name.lower() in ("cancel", "abbruch"):
                    print("  → Slot-Erstellung abgebrochen")
                    continue
                if not slot_name:
                    slot_name = f"Slot {slot_num}"

                # Scan-Region auswählen
                print("\n  Scan-Region definieren (Bereich wo das Item angezeigt wird):")
                print("  ('cancel' in Konsole = abbrechen)")
                region = select_region()
                if not region:
                    print("  → Slot-Erstellung abgebrochen")
                    continue

                # Sofort Farben in dieser Region anzeigen
                print("\n  Analysiere Farben in diesem Bereich...")
                img = take_screenshot(region)
                if img:
                    color_counts = {}
                    pixels = img.load()
                    width, height = img.size
                    for x in range(width):
                        for y in range(height):
                            pixel = pixels[x, y][:3]
                            rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
                            color_counts[rounded] = color_counts.get(rounded, 0) + 1
                    marker_count = CONFIG.get("marker_count", 5)
                    sorted_colors = sorted(color_counts.items(), key=lambda c: c[1], reverse=True)[:marker_count]
                    print(f"  Top {marker_count} Farben in {slot_name}:")
                    for i, (color, count) in enumerate(sorted_colors):
                        color_name = get_color_name(color)
                        print(f"    {i+1}. RGB{color} - {color_name} ({count} Pixel)")

                # Slot-Hintergrundfarbe (wird bei Items ausgeschlossen)
                slot_color = None
                print("\n  Hintergrundfarbe des leeren Slots markieren:")
                print("  (Diese Farbe wird bei Item-Erkennung ignoriert)")
                print("  Bewege Maus auf den Slot-Hintergrund, Enter (oder 'cancel')...")
                bg_input = input().strip()
                if bg_input.lower() in ("cancel", "abbruch"):
                    print("  → Slot-Erstellung abgebrochen")
                    continue
                if bg_input == "":
                    # User hat Enter gedrückt - prüfe Mausposition
                    px, py = get_cursor_pos()
                    # Prüfe ob Maus im Scan-Bereich ist
                    if region[0] <= px <= region[2] and region[1] <= py <= region[3]:
                        bg_img = take_screenshot((px, py, px+1, py+1))
                        if bg_img:
                            slot_color = bg_img.getpixel((0, 0))[:3]
                            slot_color = (slot_color[0] // 5 * 5, slot_color[1] // 5 * 5, slot_color[2] // 5 * 5)
                            color_name = get_color_name(slot_color)
                            print(f"  → Hintergrundfarbe: RGB{slot_color} ({color_name})")
                    else:
                        print("  → Übersprungen (Maus war außerhalb des Bereichs)")

                # Klick-Position
                print("\n  Klick-Position (wo geklickt wird um das Item zu nehmen):")
                print("  Bewege die Maus zur Klick-Position und drücke Enter (oder 'cancel')...")
                click_input = input().strip()
                if click_input.lower() in ("cancel", "abbruch"):
                    print("  → Slot-Erstellung abgebrochen")
                    continue
                click_x, click_y = get_cursor_pos()
                print(f"  → Klick-Position: ({click_x}, {click_y})")

                slot = ItemSlot(slot_name, region, (click_x, click_y), slot_color)
                slots.append(slot)
                print(f"  ✓ {slot_name} hinzugefügt")
                continue

            elif user_input == "del all":
                if not slots:
                    print("  → Keine Slots vorhanden!")
                    continue
                confirm = input(f"  {len(slots)} Slot(s) wirklich löschen? (j/n): ").strip().lower()
                if confirm == "j":
                    count = len(slots)
                    slots.clear()
                    print(f"  ✓ {count} Slot(s) gelöscht!")
                else:
                    print("  → Abgebrochen")
                continue

            elif user_input.startswith("del ") and "-" in user_input[4:]:
                # Bereich löschen: del 1-7
                try:
                    range_part = user_input[4:]
                    start, end = map(int, range_part.split("-"))
                    if start < 1 or end > len(slots) or start > end:
                        print(f"  → Ungültiger Bereich! Verfügbar: 1-{len(slots)}")
                        continue
                    count = end - start + 1
                    confirm = input(f"  {count} Slot(s) ({start}-{end}) wirklich löschen? (j/n): ").strip().lower()
                    if confirm == "j":
                        del slots[start-1:end]
                        print(f"  ✓ {count} Slot(s) gelöscht!")
                    else:
                        print("  → Abgebrochen")
                except ValueError:
                    print("  → Format: del <Nr>-<Nr>")
                continue

            elif user_input.startswith("del "):
                try:
                    del_num = int(user_input[4:])
                    if 1 <= del_num <= len(slots):
                        removed = slots.pop(del_num - 1)
                        print(f"  ✓ {removed.name} gelöscht")
                    else:
                        print(f"  → Ungültiger Slot! Verfügbar: 1-{len(slots)}")
                except ValueError:
                    print("  → Format: del <Nr>")
                continue

            else:
                print("  → Unbekannter Befehl")

        except (KeyboardInterrupt, EOFError):
            raise


def edit_item_profiles(items: list[ItemProfile], slots: list[ItemSlot] = None) -> list[ItemProfile]:
    """Bearbeitet die Item-Profile für einen Item-Scan."""

    if items:
        print(f"\nAktuelle Item-Profile ({len(items)}):")
        for i, item in enumerate(items):
            print(f"  {i+1}. {item}")

    if slots:
        print(f"\nVerfügbare Slots für Farb-Scan:")
        for i, slot in enumerate(slots):
            print(f"  {i+1}. {slot.name}")

    print("\n" + "-" * 60)
    print("Befehle:")
    print("  add            - Neues Item-Profil erstellen")
    print("  edit <Nr>      - Item-Profil bearbeiten")
    print("  del <Nr>       - Item-Profil löschen")
    print("  del <Nr>-<Nr>  - Bereich löschen (z.B. del 1-5)")
    print("  del all        - ALLE Profile löschen")
    print("  show           - Alle Profile anzeigen")
    print("  done | cancel")
    print("-" * 60)

    while True:
        try:
            prompt = f"[ITEMS: {len(items)}]"
            user_input = input(f"{prompt} > ").strip().lower()

            if user_input == "done":
                # Entferne Farben die bei allen Items gleich sind (Hintergrund)
                items = remove_common_colors(items)
                return items
            elif user_input == "cancel":
                return items  # Gibt aktuelle Liste zurück (Sub-Editor)
            elif user_input == "":
                continue
            elif user_input == "show":
                if items:
                    print("\nItem-Profile (sortiert nach Priorität):")
                    for item in sorted(items, key=lambda x: x.priority):
                        print(f"  {item}")
                else:
                    print("  (Keine Item-Profile)")
                continue

            elif user_input == "add":
                item_num = len(items) + 1
                item_name = input(f"  Item-Name (Enter = 'Item {item_num}', 'cancel'): ").strip()
                if item_name.lower() in ("cancel", "abbruch"):
                    print("  → Item-Erstellung abgebrochen")
                    continue
                if not item_name:
                    item_name = f"Item {item_num}"

                # Kategorie zuerst
                category = select_category(state)

                # Priorität
                priority = 1
                try:
                    prio_input = input(f"  Priorität (1=beste, Enter={priority}, 'cancel'): ").strip()
                    if prio_input.lower() in ("cancel", "abbruch"):
                        print("  → Item-Erstellung abgebrochen")
                        continue
                    if prio_input:
                        priority = max(1, int(prio_input))
                except ValueError:
                    pass

                # Marker-Farben sammeln - Slot oder freier Bereich
                if slots:
                    print(f"\n  Slot-Nr (1-{len(slots)}) oder '0' für freien Bereich ('cancel'):")
                    try:
                        slot_input = input("  > ").strip()
                        if slot_input.lower() in ("cancel", "abbruch"):
                            print("  → Item-Erstellung abgebrochen")
                            continue
                        slot_num = int(slot_input)
                        if slot_num == 0:
                            # Freier Bereich - manuell scannen
                            marker_colors = collect_marker_colors_free()
                        elif slot_num < 1 or slot_num > len(slots):
                            print(f"  → Ungültiger Slot! Verfügbar: 1-{len(slots)} oder 0")
                            continue
                        else:
                            selected_slot = slots[slot_num - 1]
                            marker_colors = collect_marker_colors(selected_slot.scan_region, selected_slot.slot_color)
                    except ValueError:
                        print("  → Bitte eine Nummer eingeben!")
                        continue
                else:
                    # Keine Slots - freier Bereich
                    print("\n  Keine Slots vorhanden - freier Bereich wird verwendet:")
                    marker_colors = collect_marker_colors_free()

                if not marker_colors:
                    print("  → Keine Farben gefunden, Item-Erstellung abgebrochen")
                    continue

                # Bestätigungs-Punkt abfragen
                confirm_point = None
                confirm_delay = 0.5
                confirm_input = input("  Bestätigung nötig? (Enter = Nein, Punkt-ID = Ja, 'cancel'): ").strip()
                if confirm_input.lower() in ("cancel", "abbruch"):
                    print("  → Item-Erstellung abgebrochen")
                    continue
                if confirm_input:
                    try:
                        point_id = int(confirm_input)
                        found_point = get_point_by_id(state, point_id)
                        if found_point:
                            confirm_point = found_point  # Koordinaten speichern
                            delay_input = input("  Wartezeit vor Bestätigung (Enter = 0.5s): ").strip()
                            if delay_input:
                                try:
                                    confirm_delay = float(delay_input)
                                except ValueError:
                                    confirm_delay = 0.5
                        else:
                            print(f"  → Punkt #{point_id} existiert nicht")
                    except ValueError:
                        print("  → Keine gültige Zahl, Bestätigung übersprungen")

                item = ItemProfile(item_name, marker_colors, category, priority, confirm_point, confirm_delay)
                items.append(item)
                confirm_str = f" → ({confirm_point.x},{confirm_point.y}) nach {confirm_delay}s" if confirm_point else ""
                cat_str = f" [{category}]" if category else ""
                print(f"  ✓ {item_name}{cat_str} hinzugefügt mit {len(marker_colors)} Marker-Farben{confirm_str}")
                continue

            elif user_input.startswith("edit "):
                try:
                    edit_num = int(user_input[5:])
                    if 1 <= edit_num <= len(items):
                        item = items[edit_num - 1]
                        print(f"\n  Bearbeite {item.name}:")

                        # Neue Priorität?
                        try:
                            prio_input = input(f"  Priorität (aktuell {item.priority}, Enter=behalten): ").strip()
                            if prio_input:
                                item.priority = max(1, int(prio_input))
                        except ValueError:
                            pass

                        # Farben neu sammeln?
                        if input("  Marker-Farben neu sammeln? (j/n): ").strip().lower() == "j":
                            if slots:
                                print(f"  In welchem Slot liegt das Item? (1-{len(slots)}):")
                                try:
                                    slot_num = int(input("  Slot-Nr: ").strip())
                                    if 1 <= slot_num <= len(slots):
                                        sel_slot = slots[slot_num - 1]
                                        new_colors = collect_marker_colors(sel_slot.scan_region, sel_slot.slot_color)
                                    else:
                                        new_colors = collect_marker_colors()  # Fallback
                                except ValueError:
                                    new_colors = collect_marker_colors()  # Fallback
                            else:
                                new_colors = collect_marker_colors()
                            if new_colors:
                                item.marker_colors = new_colors

                        # Bestätigung bearbeiten
                        current_confirm = f"({item.confirm_point.x},{item.confirm_point.y})" if item.confirm_point else "Keine"
                        confirm_input = input(f"  Bestätigung (aktuell {current_confirm}, Punkt-ID=setzen, 0=entfernen, Enter=behalten): ").strip()
                        if confirm_input == "0":
                            item.confirm_point = None
                            print("  → Bestätigung entfernt")
                        elif confirm_input:
                            try:
                                point_id = int(confirm_input)
                                found_point = get_point_by_id(state, point_id)
                                if found_point:
                                    item.confirm_point = found_point  # Koordinaten speichern
                                    delay_input = input(f"  Wartezeit (aktuell {item.confirm_delay}s, Enter=behalten): ").strip()
                                    if delay_input:
                                        try:
                                            item.confirm_delay = float(delay_input)
                                        except ValueError:
                                            pass
                                else:
                                    print(f"  → Punkt #{point_id} existiert nicht")
                            except ValueError:
                                pass

                        print(f"  ✓ {item.name} aktualisiert")
                    else:
                        print(f"  → Ungültiges Item! Verfügbar: 1-{len(items)}")
                except ValueError:
                    print("  → Format: edit <Nr>")
                continue

            elif user_input == "del all":
                if not items:
                    print("  → Keine Items vorhanden!")
                    continue
                confirm = input(f"  {len(items)} Item(s) wirklich löschen? (j/n): ").strip().lower()
                if confirm == "j":
                    count = len(items)
                    items.clear()
                    print(f"  ✓ {count} Item(s) gelöscht!")
                else:
                    print("  → Abgebrochen")
                continue

            elif user_input.startswith("del ") and "-" in user_input[4:]:
                # Bereich löschen: del 1-5
                try:
                    range_part = user_input[4:]
                    start, end = map(int, range_part.split("-"))
                    if start < 1 or end > len(items) or start > end:
                        print(f"  → Ungültiger Bereich! Verfügbar: 1-{len(items)}")
                        continue
                    count = end - start + 1
                    confirm = input(f"  {count} Item(s) ({start}-{end}) wirklich löschen? (j/n): ").strip().lower()
                    if confirm == "j":
                        del items[start-1:end]
                        print(f"  ✓ {count} Item(s) gelöscht!")
                    else:
                        print("  → Abgebrochen")
                except ValueError:
                    print("  → Format: del <Nr>-<Nr>")
                continue

            elif user_input.startswith("del "):
                try:
                    del_num = int(user_input[4:])
                    if 1 <= del_num <= len(items):
                        removed = items.pop(del_num - 1)
                        print(f"  ✓ {removed.name} gelöscht")
                    else:
                        print(f"  → Ungültiges Item! Verfügbar: 1-{len(items)}")
                except ValueError:
                    print("  → Format: del <Nr>")
                continue

            else:
                print("  → Unbekannter Befehl")

        except (KeyboardInterrupt, EOFError):
            raise


def collect_marker_colors_free() -> list[tuple]:
    """Sammelt Marker-Farben aus einem frei gewählten Bereich mit optionalem Hintergrund-Ausschluss."""
    print("\n  Wähle einen Bereich auf dem Item aus:")
    print("  (Die 5 häufigsten Farben werden automatisch genommen)")
    region = select_region()
    if not region:
        return []

    # Optional Hintergrundfarbe ausschließen
    exclude_color = None
    bg_input = input("  Hintergrundfarbe entfernen? (Enter = Nein, 'j' = Farbe aufnehmen): ").strip().lower()
    if bg_input == "j":
        print("  → Bewege die Maus auf den Hintergrund und drücke ENTER...")
        input()
        try:
            x, y = get_cursor_pos()
            exclude_color = get_pixel_color(x, y)
            if exclude_color:
                # Auf 5er-Schritte runden (wie in collect_marker_colors)
                exclude_color = (exclude_color[0] // 5 * 5, exclude_color[1] // 5 * 5, exclude_color[2] // 5 * 5)
                color_name = get_color_name(exclude_color)
                print(f"  → Hintergrund: RGB{exclude_color} ({color_name}) wird ausgeschlossen")
        except (OSError, TypeError, AttributeError):
            print("  → Konnte Hintergrundfarbe nicht aufnehmen, fahre ohne fort")

    return collect_marker_colors(region, exclude_color)


def collect_marker_colors(region: tuple = None, exclude_color: tuple = None) -> list[tuple]:
    """Sammelt Marker-Farben für ein Item-Profil durch Region-Scan."""

    # Wenn keine Region übergeben, manuell auswählen
    if not region:
        print("\n  Wähle einen Bereich auf dem Item aus:")
        print("  (Die 5 häufigsten Farben werden automatisch genommen)")
        region = select_region()
        if not region:
            return []

    # Screenshot der Region
    print(f"\n  Scanne Region ({region[0]},{region[1]}) - ({region[2]},{region[3]})...")
    img = take_screenshot(region)
    if img is None:
        print("  → Fehler beim Screenshot!")
        return []

    # Farben zählen (mit Rundung für Gruppierung)
    color_counts = {}
    pixels = img.load()
    width, height = img.size

    for x in range(width):
        for y in range(height):
            pixel = pixels[x, y][:3]
            # Runde auf 5er-Schritte für Gruppierung ähnlicher Farben
            rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
            color_counts[rounded] = color_counts.get(rounded, 0) + 1

    # Slot-Hintergrundfarbe ausschließen (falls vorhanden)
    # Entferne alle Farben die der Slot-Farbe ähnlich sind (mit Toleranz)
    if exclude_color:
        # Runde die exclude_color auf 5er-Schritte (wie die anderen Farben)
        exclude_rounded = (exclude_color[0] // 5 * 5, exclude_color[1] // 5 * 5, exclude_color[2] // 5 * 5)

        # Finde alle ähnlichen Farben (Toleranz aus Config)
        slot_color_dist = CONFIG.get("slot_color_distance", 25)
        colors_to_remove = []
        for color in color_counts.keys():
            if color_distance(color, exclude_rounded) <= slot_color_dist:
                colors_to_remove.append(color)

        # Entferne alle ähnlichen Farben
        total_excluded = 0
        for color in colors_to_remove:
            total_excluded += color_counts.pop(color)

        if total_excluded > 0:
            color_name = get_color_name(exclude_color)
            print(f"  → Slot-Hintergrund ~RGB{exclude_color} ({color_name}) ausgeschlossen ({total_excluded} Pixel, {len(colors_to_remove)} Farbtöne)")

    # Top N häufigste Farben (aus Config)
    marker_count = CONFIG.get("marker_count", 5)
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:marker_count]
    colors = [color for color, count in sorted_colors]

    print(f"\n  Top {marker_count} Farben gefunden:")
    for i, (color, count) in enumerate(sorted_colors):
        color_name = get_color_name(color)
        print(f"    {i+1}. RGB{color} - {color_name} ({count} Pixel)")

    return colors


def remove_common_colors(items: list) -> list:
    """Entfernt Farben die bei ALLEN Items vorkommen (= Hintergrund)."""
    if len(items) < 2:
        return items

    # Finde Farben die in ALLEN Items vorkommen
    common_colors = set(items[0].marker_colors)
    for item in items[1:]:
        common_colors &= set(item.marker_colors)

    if not common_colors:
        return items

    print(f"\n  {len(common_colors)} gemeinsame Farbe(n) gefunden (bei allen Items gleich):")

    # Für jede gemeinsame Farbe nachfragen
    colors_to_remove = []
    for color in common_colors:
        color_name = get_color_name(color)
        answer = input(f"    RGB{color} ({color_name}) entfernen? (j/n): ").strip().lower()
        if answer == "j":
            colors_to_remove.append(color)
            print(f"      → wird entfernt")
        else:
            print(f"      → behalten")

    if not colors_to_remove:
        print("  Keine Farben entfernt.")
        return items

    # Entferne bestätigte Farben von allen Items
    for item in items:
        item.marker_colors = [c for c in item.marker_colors if c not in colors_to_remove]
        # Mindestens 1 Farbe behalten
        if not item.marker_colors:
            print(f"  [WARNUNG] {item.name} hat keine eindeutigen Farben mehr!")

    print(f"  ✓ {len(colors_to_remove)} Farbe(n) entfernt")
    return items


# =============================================================================
# ITEM-SCAN AUSFÜHRUNG
# =============================================================================
def execute_item_scan(state: AutoClickerState, scan_name: str, mode: str = "all") -> list[tuple]:
    """
    Führt einen Item-Scan aus.
    mode="all": Bestes Item pro Kategorie (Standard)
    mode="best": Nur das eine beste Item insgesamt
    mode="every": Alle gefundenen Items (keine Filterung, für Duplikate)
    Returns Liste von ((x, y), ItemProfile) Tupeln (leer wenn nichts gefunden)
    """
    with state.lock:
        if scan_name not in state.item_scans:
            print(f"\n[FEHLER] Item-Scan '{scan_name}' nicht gefunden!")
            return []
        config = state.item_scans[scan_name]

    if not PILLOW_AVAILABLE:
        print("\n[FEHLER] Pillow nicht installiert für Item-Scan!")
        return []

    # Sammle alle erkannten Items
    found_items = []  # Liste von (slot, item, priority)

    # Scan-Reihenfolge: normal (1,2,3,4) oder reverse (4,3,2,1)
    slots_to_scan = config.slots
    if state.config.get("scan_reverse", False):
        slots_to_scan = list(reversed(config.slots))
        direction = "rückwärts"
    else:
        direction = "vorwärts"

    mode_names = {"all": "ALLE (pro Kategorie)", "best": "BESTES", "every": "JEDES (keine Filter)"}
    mode_str = mode_names.get(mode, mode)
    print(f"\n[SCAN] Scanne {len(slots_to_scan)} Slots für '{scan_name}' ({direction}, Modus: {mode_str})...")

    for slot_idx, slot in enumerate(slots_to_scan):
        # Delay zwischen Slots (außer beim ersten)
        slot_delay = state.config.get("scan_slot_delay", 0)
        if slot_idx > 0 and slot_delay > 0:
            time.sleep(slot_delay)

        # Screenshot der Scan-Region
        img = take_screenshot(slot.scan_region)
        if img is None:
            continue

        if state.config.get("debug_detection", False):
            print(f"[DEBUG] Scanne {slot.name}...")

        # Prüfe alle Item-Profile für diesen Slot
        for item in config.items:
            template_matched = False
            markers_matched = False
            match_info_parts = []

            # Schritt 1: Template Matching (wenn Template definiert)
            if item.template:
                if not OPENCV_AVAILABLE:
                    print(f"  [WARNUNG] OpenCV nicht verfügbar für Template '{item.template}'")
                    continue
                matched, confidence, pos = match_template_in_image(img, item.template, item.min_confidence)

                if state.config.get("debug_detection", False):
                    status = "✓" if matched else "✗"
                    threshold_info = f"≥{item.min_confidence:.0%}" if not matched else ""
                    print(f"[DEBUG]   {status} {item.name}: Template {confidence:.0%} {threshold_info}")

                if matched:
                    template_matched = True
                    match_info_parts.append(f"Template {confidence:.0%}")
                else:
                    # Template nicht erkannt → Item nicht erkannt
                    continue

            # Schritt 2: Marker-Farben prüfen (immer wenn vorhanden, auch nach Template-Match)
            if item.marker_colors:
                # Berechne min_required vor der Schleife für Early-Exit
                if state.config.get("require_all_markers", True):
                    min_required = len(item.marker_colors)
                else:
                    min_required = min(state.config.get("min_markers_required", 2), len(item.marker_colors))

                # Prüfe ob Marker-Farben vorhanden sind (mit Early-Exit-Optimierung)
                markers_found = 0
                markers_missing = 0
                max_allowed_missing = len(item.marker_colors) - min_required

                for marker_color in item.marker_colors:
                    if find_color_in_image(img, marker_color, config.color_tolerance):
                        markers_found += 1
                        # Early exit: Genug Marker gefunden
                        if markers_found >= min_required:
                            break
                    else:
                        markers_missing += 1
                        # Early exit: Zu viele Marker fehlen
                        if markers_missing > max_allowed_missing:
                            break

                if state.config.get("debug_detection", False):
                    status = "✓" if markers_found >= min_required else "✗"
                    print(f"[DEBUG]   {status} {item.name}: {markers_found}/{len(item.marker_colors)} Marker (min {min_required})")

                # Marker erkannt wenn genug gefunden
                if markers_found >= min_required:
                    markers_matched = True
                    match_info_parts.append(f"{markers_found}/{len(item.marker_colors)} Marker")
                else:
                    # Marker nicht erkannt → Item nicht erkannt
                    continue

            # Item erkannt wenn alle definierten Checks bestanden
            # (Template UND/ODER Marker je nach Konfiguration)
            item_matched = False
            if item.template and item.marker_colors:
                # Beides definiert → beides muss passen
                item_matched = template_matched and markers_matched
            elif item.template:
                # Nur Template definiert
                item_matched = template_matched
            elif item.marker_colors:
                # Nur Marker definiert
                item_matched = markers_matched

            match_info = " + ".join(match_info_parts)

            # Item erkannt? → Sofort hinzufügen und zum nächsten Slot
            # (Ein Slot enthält maximal 1 Item, keine Prioritäts-Konkurrenz)
            if item_matched:
                print(f"  → {slot.name}: {item.name} erkannt ({match_info})")
                found_items.append((slot, item, item.priority))
                break  # Nächster Slot - dieses Item ist gefunden

    if not found_items:
        print("[SCAN] Kein Item erkannt.")
        return []

    # Modus "every": Alle Treffer ohne Filterung (für Spiele mit Duplikaten)
    if mode == "every":
        print(f"[SCAN] {len(found_items)} Item(s) gefunden - klicke alle (ohne Filter)!")
        return [(slot.click_pos, item) for slot, item, priority in found_items]

    # Gruppiere nach Kategorie und behalte nur das beste pro Kategorie
    # Kategorie = item.category oder item.name (falls keine Kategorie gesetzt)
    # Überspringe Kategorien, die in diesem Zyklus bereits geklickt wurden
    best_per_category = {}  # {category: (slot, item, priority)}
    for slot, item, priority in found_items:
        cat = item.category or item.name  # Fallback auf Item-Name

        # Überspringe wenn Kategorie bereits mit besserer/gleicher Priorität geklickt wurde
        with state.lock:
            if cat in state.clicked_categories:
                best_clicked_prio = state.clicked_categories[cat]
                if priority >= best_clicked_prio:
                    # Item ist schlechter oder gleich → überspringen
                    if state.config.get("debug_detection", False):
                        print(f"[DEBUG]   → {item.name} (P{priority}) übersprungen ('{cat}' bereits mit P{best_clicked_prio} geklickt)")
                    continue
                # Item ist besser → wird später geklickt (nicht überspringen)

        if cat not in best_per_category or priority < best_per_category[cat][2]:
            best_per_category[cat] = (slot, item, priority)

    # Debug: Zeige Kategorie-Filterung
    if state.config.get("debug_detection", False) and len(found_items) != len(best_per_category):
        print(f"[DEBUG] {len(found_items)} Items gefunden, {len(best_per_category)} nach Kategorie-Filter")
        for cat, (slot, item, prio) in best_per_category.items():
            print(f"[DEBUG]   [{cat}] → {item.name} (P{prio}) in {slot.name}")

    filtered_items = list(best_per_category.values())

    if mode == "all":
        # Alle besten pro Kategorie zurückgeben (mit Priorität für clicked_categories)
        print(f"[SCAN] {len(filtered_items)} Item(s) gefunden - klicke alle!")
        return [(slot.click_pos, item, priority) for slot, item, priority in filtered_items]
    else:
        # Nur das absolute beste Item zurückgeben
        filtered_items.sort(key=lambda x: x[2])  # Nach Priorität sortieren
        best_slot, best_item, best_priority = filtered_items[0]
        print(f"[SCAN] Bestes Item: {best_item.name} in {best_slot.name} (P{best_priority})")
        return [(best_slot.click_pos, best_item, best_priority)]


# =============================================================================
# SEQUENZ-EDITOR (Konsolen-basiert)
# =============================================================================
def run_sequence_editor(state: AutoClickerState) -> None:
    """Interaktiver Sequenz-Editor - neu erstellen oder bestehende bearbeiten."""
    print("\n" + "=" * 60)
    print("  SEQUENZ-EDITOR")
    print("=" * 60)

    with state.lock:
        if not state.points:
            print("\n[FEHLER] Erst Punkte aufnehmen (CTRL+ALT+A)!")
            return

    # Bestehende Sequenzen laden
    available_sequences = list_available_sequences()

    print("\nWas möchtest du tun?")
    print("  [0] Neue Sequenz erstellen")

    if available_sequences:
        print("\nBestehende Sequenzen bearbeiten:")
        for i, (name, path) in enumerate(available_sequences):
            seq = load_sequence_file(path)
            if seq:
                print(f"  [{i+1}] {seq}")

    print("\nAuswahl (oder 'cancel'):")

    while True:
        try:
            choice = input("> ").strip().lower()

            if choice in ("cancel", "abbruch"):
                print("[CANCEL] Editor beendet.")
                return

            choice_num = int(choice)

            if choice_num == 0:
                # Neue Sequenz erstellen
                edit_sequence(state, None)
                return
            elif 1 <= choice_num <= len(available_sequences):
                # Bestehende Sequenz bearbeiten
                name, path = available_sequences[choice_num - 1]
                existing_seq = load_sequence_file(path)
                if existing_seq:
                    edit_sequence(state, existing_seq)
                return
            else:
                print("[FEHLER] Ungültige Auswahl! Nochmal versuchen...")

        except ValueError:
            print("[FEHLER] Bitte eine Nummer eingeben! Nochmal versuchen...")
        except (KeyboardInterrupt, EOFError):
            print("\n[ABBRUCH] Editor beendet.")
            return


def edit_sequence(state: AutoClickerState, existing: Optional[Sequence]) -> None:
    """Bearbeitet eine Sequenz (neu oder bestehend) mit Start + mehreren Loop-Phasen."""

    if existing:
        print(f"\n--- Bearbeite Sequenz: {existing.name} ---")
        seq_name = existing.name
        start_steps = list(existing.start_steps)
        loop_phases = [LoopPhase(lp.name, list(lp.steps), lp.repeat) for lp in existing.loop_phases]
        end_steps = list(existing.end_steps)
        total_cycles = existing.total_cycles
    else:
        print("\n--- Neue Sequenz erstellen ---")
        seq_name = input("Name der Sequenz: ").strip()
        if not seq_name:
            seq_name = f"Sequenz_{int(time.time())}"
        start_steps = []
        loop_phases = []
        end_steps = []
        total_cycles = 1

    # Verfügbare Punkte anzeigen
    with state.lock:
        print("\nVerfügbare Punkte:")
        for p in state.points:
            print(f"  {p}")

    # Erst START-Phase bearbeiten
    print("\n" + "=" * 60)
    print("  PHASE 1: START-SEQUENZ (wird einmal pro Zyklus ausgeführt)")
    print("=" * 60)
    result = edit_phase(state, start_steps, "START")
    if result is None:
        print("[ABBRUCH] Sequenz nicht gespeichert.")
        return
    start_steps = result

    # Dann LOOP-Phasen bearbeiten (mehrere möglich)
    print("\n" + "=" * 60)
    print("  PHASE 2: LOOP-PHASEN (können mehrere sein)")
    print("=" * 60)
    loop_phases = edit_loop_phases(state, loop_phases)
    if loop_phases is None:
        print("[ABBRUCH] Sequenz nicht gespeichert.")
        return

    # Gesamt-Zyklen abfragen
    if loop_phases:
        print("\n" + "=" * 60)
        print("  GESAMT-WIEDERHOLUNGEN")
        print("=" * 60)
        print("\nAblauf: START → Loop1 → Loop2 → ... → (wieder von vorne?)")
        print("\nWie oft soll der GESAMTE Ablauf wiederholt werden?")
        print("  0 = Unendlich (manuell stoppen)")
        print("  1 = Einmal durchlaufen und stoppen")
        print("  >1 = X-mal wiederholen (START → alle Loops → START → ...)")
        try:
            cycles_input = input(f"\nAnzahl Zyklen (Enter = {total_cycles}): ").strip()
            if cycles_input:
                total_cycles = int(cycles_input)
                if total_cycles < 0:
                    total_cycles = 0
        except ValueError:
            print(f"Ungültige Eingabe, behalte {total_cycles}.")

    # END-Phase bearbeiten (optional)
    print("\n" + "=" * 60)
    print("  PHASE 3: END-SEQUENZ (wird einmal am Ende ausgeführt)")
    print("=" * 60)
    print("\n  (Optional: Aufräumen, Logout, etc.)")
    result = edit_phase(state, end_steps, "END")
    if result is None:
        print("[ABBRUCH] Sequenz nicht gespeichert.")
        return
    end_steps = result

    # Sequenz erstellen und speichern
    new_sequence = Sequence(
        name=seq_name,
        start_steps=start_steps,
        loop_phases=loop_phases,
        end_steps=end_steps,
        total_cycles=total_cycles
    )

    with state.lock:
        state.sequences[seq_name] = new_sequence
        state.active_sequence = new_sequence

    save_data(state)

    # Zusammenfassung
    all_steps = start_steps + [s for lp in loop_phases for s in lp.steps] + end_steps
    pixel_triggers = sum(1 for s in all_steps if s.wait_pixel)

    print(f"\n[ERFOLG] Sequenz '{seq_name}' gespeichert!")
    print(f"         Start: {len(start_steps)} Schritte (einmal pro Zyklus)")
    for i, lp in enumerate(loop_phases):
        print(f"         {lp.name}: {len(lp.steps)} Schritte x{lp.repeat}")
    if end_steps:
        print(f"         End: {len(end_steps)} Schritte (einmal am Ende)")
    if total_cycles == 0:
        print(f"         Gesamt: Unendlich wiederholen")
    elif total_cycles == 1:
        print(f"         Gesamt: Einmal durchlaufen")
    else:
        print(f"         Gesamt: {total_cycles}x wiederholen")
    if pixel_triggers > 0:
        print(f"         Farb-Trigger: {pixel_triggers} Schritt(e)")
    print("         Drücke CTRL+ALT+S zum Starten.\n")


def edit_loop_phases(state: AutoClickerState, loop_phases: list[LoopPhase]) -> Optional[list[LoopPhase]]:
    """Bearbeitet mehrere Loop-Phasen.

    Returns:
        Liste der Loop-Phasen bei 'fertig', None bei 'cancel'.
    """

    if loop_phases:
        print(f"\nAktuelle Loop-Phasen ({len(loop_phases)}):")
        for i, lp in enumerate(loop_phases):
            print(f"  {i+1}. {lp}")

    print("\n" + "-" * 60)
    print("Befehle:")
    print("  add            - Neue Loop-Phase hinzufügen")
    print("  edit <Nr>      - Loop-Phase bearbeiten (z.B. 'edit 1')")
    print("  del <Nr>       - Loop-Phase löschen")
    print("  del <Nr>-<Nr>  - Bereich löschen (z.B. del 1-3)")
    print("  del all        - ALLE Loop-Phasen löschen")
    print("  show           - Alle Loop-Phasen anzeigen")
    print("  done | cancel")
    print("-" * 60)

    while True:
        try:
            prompt = f"[LOOPS: {len(loop_phases)}]"
            user_input = input(f"{prompt} > ").strip().lower()

            if user_input == "done":
                return loop_phases
            elif user_input == "cancel":
                return None  # Abbruch signalisieren
            elif user_input == "":
                continue
            elif user_input == "show":
                if loop_phases:
                    print(f"\nLoop-Phasen:")
                    for i, lp in enumerate(loop_phases):
                        print(f"  {i+1}. {lp}")
                        for j, step in enumerate(lp.steps):
                            print(f"       {j+1}. {step}")
                else:
                    print("  (Keine Loop-Phasen)")
                continue
            elif user_input == "add":
                # Neue Loop-Phase
                loop_num = len(loop_phases) + 1
                loop_name = input(f"  Name der Loop-Phase (Enter = 'Loop {loop_num}'): ").strip()
                if not loop_name:
                    loop_name = f"Loop {loop_num}"

                print(f"\n  Schritte für {loop_name} hinzufügen:")
                steps = edit_phase(state, [], loop_name)
                if steps is None:
                    return None  # Abbruch durchreichen

                repeat = 1
                try:
                    repeat_input = input(f"  Wie oft soll {loop_name} wiederholt werden? (Enter = 1): ").strip()
                    if repeat_input:
                        repeat = max(1, int(repeat_input))
                except ValueError:
                    repeat = 1

                loop_phases.append(LoopPhase(loop_name, steps, repeat))
                print(f"  ✓ {loop_name} hinzugefügt ({len(steps)} Schritte x{repeat})")
                continue

            elif user_input.startswith("edit "):
                try:
                    edit_num = int(user_input[5:])
                    if 1 <= edit_num <= len(loop_phases):
                        lp = loop_phases[edit_num - 1]
                        print(f"\n  Bearbeite {lp.name}:")
                        new_steps = edit_phase(state, lp.steps, lp.name)
                        if new_steps is None:
                            return None  # Abbruch durchreichen
                        lp.steps = new_steps
                        try:
                            repeat_input = input(f"  Wiederholungen (aktuell {lp.repeat}, Enter = behalten): ").strip()
                            if repeat_input:
                                lp.repeat = max(1, int(repeat_input))
                        except ValueError:
                            pass
                        print(f"  ✓ {lp.name} aktualisiert")
                    else:
                        print(f"  → Ungültige Nr! Verfügbar: 1-{len(loop_phases)}")
                except ValueError:
                    print("  → Format: edit <Nr>")
                continue

            elif user_input == "del all":
                if not loop_phases:
                    print("  → Keine Loop-Phasen vorhanden!")
                    continue
                confirm = input(f"  {len(loop_phases)} Loop-Phase(n) wirklich löschen? (j/n): ").strip().lower()
                if confirm == "j":
                    count = len(loop_phases)
                    loop_phases.clear()
                    print(f"  ✓ {count} Loop-Phase(n) gelöscht!")
                else:
                    print("  → Abgebrochen")
                continue

            elif user_input.startswith("del ") and "-" in user_input[4:]:
                # Bereich löschen: del 1-3
                try:
                    range_part = user_input[4:]
                    start, end = map(int, range_part.split("-"))
                    if start < 1 or end > len(loop_phases) or start > end:
                        print(f"  → Ungültiger Bereich! Verfügbar: 1-{len(loop_phases)}")
                        continue
                    count = end - start + 1
                    confirm = input(f"  {count} Loop-Phase(n) ({start}-{end}) wirklich löschen? (j/n): ").strip().lower()
                    if confirm == "j":
                        del loop_phases[start-1:end]
                        print(f"  ✓ {count} Loop-Phase(n) gelöscht!")
                    else:
                        print("  → Abgebrochen")
                except ValueError:
                    print("  → Format: del <Nr>-<Nr>")
                continue

            elif user_input.startswith("del "):
                try:
                    del_num = int(user_input[4:])
                    if 1 <= del_num <= len(loop_phases):
                        removed = loop_phases.pop(del_num - 1)
                        print(f"  ✓ {removed.name} gelöscht")
                    else:
                        print(f"  → Ungültige Nr! Verfügbar: 1-{len(loop_phases)}")
                except ValueError:
                    print("  → Format: del <Nr>")
                continue

            else:
                print("  → Unbekannter Befehl")

        except (KeyboardInterrupt, EOFError):
            raise


def parse_else_condition(else_parts: list[str], state: AutoClickerState) -> dict:
    """Parst eine ELSE-Bedingung und gibt ein Dict mit den Else-Feldern zurück.

    Formate:
    - else skip          -> überspringen
    - else restart       -> Sequenz neu starten
    - else <Nr> [delay]  -> Punkt klicken (optional mit Verzögerung)
    - else key <Taste>   -> Taste drücken

    Gibt leeres Dict zurück wenn Parsing fehlschlägt.
    """
    if not else_parts:
        return {}

    first = else_parts[0].lower()

    # else skip
    if first == "skip":
        return {"else_action": "skip"}

    # else restart
    if first == "restart":
        return {"else_action": "restart"}

    # else key <Taste>
    if first == "key" and len(else_parts) >= 2:
        key_name = else_parts[1].lower()
        if key_name in VK_CODES:
            return {"else_action": "key", "else_key": key_name}
        print(f"  → Unbekannte Taste: '{key_name}'")
        return {}

    # else <ID> [delay] - Punkt klicken (per ID)
    try:
        point_id = int(first)
        with state.lock:
            point = get_point_by_id(state, point_id)
            if point:
                result = {
                    "else_action": "click",
                    "else_x": point.x,
                    "else_y": point.y,
                    "else_name": point.name or f"Punkt #{point_id}"
                }
                # Optional: Delay
                if len(else_parts) >= 2:
                    try:
                        result["else_delay"] = float(else_parts[1])
                    except ValueError:
                        pass
                return result
            else:
                print(f"  → Punkt #{point_id} nicht gefunden!")
                return {}
    except ValueError:
        pass

    print(f"  → Unbekanntes ELSE-Format: {' '.join(else_parts)}")
    print("     Formate: else skip | else restart | else <Nr> [delay] | else key <Taste>")
    return {}


def edit_phase(state: AutoClickerState, steps: list[SequenceStep], phase_name: str) -> Optional[list[SequenceStep]]:
    """Bearbeitet eine Phase (Start oder Loop) der Sequenz.

    Returns:
        Liste der Schritte bei 'fertig', None bei 'cancel'.
    """

    if steps:
        print(f"\nAktuelle {phase_name}-Schritte ({len(steps)}):")
        for i, step in enumerate(steps):
            print(f"  {i+1}. {step}")

    print("\n" + "-" * 60)
    print("Befehle (Logik: erst warten, DANN klicken):")
    print("  <Nr> <Zeit>       - Warte Xs, dann klicke (z.B. '1 30')")
    print("  <Nr> <Min>-<Max>  - Zufällig warten (z.B. '1 30-45')")
    print("  <Nr> 0            - Sofort klicken")
    print("  <Nr> pixel        - Warte auf Farbe, dann klicke")
    print("  <Nr> <Zeit> pixel - Erst Xs warten, dann auf Farbe")
    print("  <Nr> gone         - Warte bis Farbe WEG, dann klicke")
    print("  <Nr> <Zeit> gone  - Erst Xs warten, dann bis Farbe WEG")
    print("  wait <Zeit>       - Nur warten, KEIN Klick (z.B. 'wait 10')")
    print("  wait <Min>-<Max>  - Zufällig warten (z.B. 'wait 30-45')")
    print("  wait pixel        - Auf Farbe warten, KEIN Klick")
    print("  wait gone         - Warten bis Farbe WEG ist, KEIN Klick")
    print("  key <Taste>       - Taste sofort drücken (z.B. 'key enter')")
    print("  key <Zeit> <Taste> - Warten, dann Taste (z.B. 'key 5 space')")
    print("  scan <Name>       - Item-Scan: bestes pro Kategorie (Standard)")
    print("  scan <Name> best  - Item-Scan: nur 1 Item total")
    print("  scan <Name> every - Item-Scan: alle Treffer (für Duplikate)")
    print("ELSE-Bedingungen (falls Scan/Pixel fehlschlägt):")
    print("  ... else skip     - Überspringen (z.B. 'scan items else skip')")
    print("  ... else restart  - Sequenz neu starten (z.B. 'scan items else restart')")
    print("  ... else <Nr> [s] - Punkt klicken (z.B. 'scan items else 2 5')")
    print("  ... else key <T>  - Taste drücken (z.B. '1 pixel else key enter')")
    print("Punkte verwalten:")
    print("  learn <Name>      - Neuen Punkt erstellen")
    print("  points            - Alle Punkte anzeigen")
    print("  del <Nr>          - Schritt löschen")
    print("  del <Nr>-<Nr>     - Bereich löschen (z.B. del 1-5)")
    print("  del all           - ALLE Schritte löschen")
    print("  ins <Nr>          - Nächsten Schritt an Position einfügen")
    print("  show | done | cancel")
    print("-" * 60)

    insert_position = None  # None = am Ende anfügen, Zahl = an Position einfügen

    def add_step(step):
        """Fügt Schritt hinzu - entweder an insert_position oder am Ende."""
        nonlocal insert_position
        if insert_position is not None:
            steps.insert(insert_position - 1, step)
            print(f"  ✓ Eingefügt an Position {insert_position}: {step}")
            insert_position = None  # Reset nach Einfügen
        else:
            steps.append(step)
            print(f"  ✓ Hinzugefügt: {step}")

    while True:
        try:
            # Zeige Insert-Modus im Prompt an
            if insert_position is not None:
                prompt = f"[{phase_name}: {len(steps)}] (ins→{insert_position})"
            else:
                prompt = f"[{phase_name}: {len(steps)}]"
            user_input = input(f"{prompt} > ").strip()

            if user_input.lower() == "done":
                return steps
            elif user_input.lower() == "cancel":
                print("[CANCEL] Phase abgebrochen.")
                return None
            elif user_input.lower() == "":
                continue
            elif user_input.lower() == "show":
                if steps:
                    print(f"\n{phase_name}-Schritte:")
                    for i, step in enumerate(steps):
                        print(f"  {i+1}. {step}")
                else:
                    print("  (Keine Schritte)")
                continue
            elif user_input.lower() == "del all":
                if not steps:
                    print("  → Keine Schritte vorhanden!")
                    continue
                count = len(steps)
                steps.clear()
                print(f"  ✓ Alle {count} Schritte gelöscht")
                continue
            elif user_input.lower().startswith("del ") and "-" in user_input[4:]:
                # Bereich löschen: del 1-5
                try:
                    range_str = user_input[4:].strip()
                    parts = range_str.split("-")
                    start = int(parts[0])
                    end = int(parts[1])
                    if start < 1 or end > len(steps) or start > end:
                        print(f"  → Ungültiger Bereich! Verfügbar: 1-{len(steps)}")
                        continue
                    # Von hinten löschen um Indexe nicht zu verschieben
                    removed_count = 0
                    for i in range(end, start - 1, -1):
                        steps.pop(i - 1)
                        removed_count += 1
                    print(f"  ✓ {removed_count} Schritte gelöscht ({start}-{end})")
                except (ValueError, IndexError):
                    print("  → Format: del <start>-<end> (z.B. del 1-5)")
                continue
            elif user_input.lower().startswith("del "):
                try:
                    del_num = int(user_input[4:])
                    if 1 <= del_num <= len(steps):
                        removed = steps.pop(del_num - 1)
                        print(f"  ✓ Schritt {del_num} gelöscht: {removed}")
                    else:
                        print(f"  → Ungültiger Schritt! Verfügbar: 1-{len(steps)}")
                except ValueError:
                    print("  → Format: del <Nr>")
                continue

            elif user_input.lower().startswith("ins "):
                # Insert-Modus: nächster Schritt wird an Position eingefügt
                try:
                    pos = int(user_input[4:])
                    if pos < 1:
                        print("  → Position muss >= 1 sein!")
                        continue
                    if pos > len(steps) + 1:
                        print(f"  → Position zu groß! Max: {len(steps) + 1}")
                        continue
                    insert_position = pos
                    print(f"  ✓ Insert-Modus: Nächster Schritt wird an Position {pos} eingefügt")
                    print(f"    (Abbrechen mit 'ins 0' oder 'ins end')")
                except ValueError:
                    print("  → Format: ins <Nr>")
                continue

            elif user_input.lower() in ("ins 0", "ins end"):
                if insert_position is not None:
                    insert_position = None
                    print("  ✓ Insert-Modus beendet - Schritte werden wieder am Ende angefügt")
                else:
                    print("  → Insert-Modus war nicht aktiv")
                continue

            elif user_input.lower() == "points":
                # Alle Punkte anzeigen
                with state.lock:
                    if state.points:
                        print("\n  Verfügbare Punkte:")
                        for p in state.points:
                            print(f"    {p}")
                    else:
                        print("  (Keine Punkte vorhanden)")
                continue

            elif user_input.lower().startswith("learn"):
                # Neuen Punkt erstellen
                # Format: "learn" oder "learn <Name>"
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    point_name = parts[1].strip()
                else:
                    point_name = input("  Punkt-Name: ").strip()
                    if not point_name or point_name.lower() in ("cancel", "abbruch"):
                        print("  → Abgebrochen")
                        continue

                print(f"\n  Bewege die Maus zur Position für '{point_name}'")
                print("  Drücke Enter...")
                input()
                x, y = get_cursor_pos()

                with state.lock:
                    new_id = get_next_point_id(state)
                    new_point = ClickPoint(x, y, point_name, new_id)
                    state.points.append(new_point)

                save_data(state)
                print(f"  ✓ Punkt #{new_id} erstellt: '{point_name}' bei ({x}, {y})")
                print(f"    → Verwenden mit: {new_id} <Zeit>")
                continue

            elif user_input.lower().startswith("scan "):
                # Item-Scan Schritt hinzufügen
                # Format: "scan <Name> [all|best|every] [else ...]"
                scan_input = user_input[5:].strip()
                if not scan_input:
                    print("  → Format: scan <Name> [all|best|every] [else ...]")
                    print("    all:   bestes Item pro Kategorie (Standard)")
                    print("    best:  nur 1 Item total (das absolute Beste)")
                    print("    every: alle Treffer ohne Filter (für Duplikate)")
                    continue

                scan_mode = "all"  # Standard: bestes pro Kategorie
                else_data = {}

                # Von hinten parsen: erst "else ...", dann Modus, dann Name
                scan_parts = scan_input.split()

                # 1. Prüfe auf "else" und extrahiere alles danach
                else_index = -1
                for i, part in enumerate(scan_parts):
                    if part.lower() == "else":
                        else_index = i
                        break

                if else_index >= 0:
                    else_parts = scan_parts[else_index + 1:]
                    scan_parts = scan_parts[:else_index]
                    if else_parts:
                        else_data = parse_else_condition(else_parts, state)
                        if not else_data:
                            continue  # Fehler wurde schon ausgegeben

                # 2. Prüfe ob letztes Wort ein Modus ist
                if scan_parts and scan_parts[-1].lower() in ("best", "all", "every"):
                    scan_mode = scan_parts[-1].lower()
                    scan_parts = scan_parts[:-1]

                # 3. Rest ist der Name (kann mehrere Wörter haben)
                scan_name = " ".join(scan_parts)

                if not scan_name:
                    print("  → Kein Scan-Name angegeben!")
                    continue

                # Prüfen ob Item-Scan existiert
                with state.lock:
                    if scan_name not in state.item_scans:
                        available = list(state.item_scans.keys())
                        if available:
                            print(f"  → Item-Scan '{scan_name}' nicht gefunden!")
                            print(f"     Verfügbar: {', '.join(available)}")
                        else:
                            print(f"  → Keine Item-Scans vorhanden!")
                            print(f"     Erstelle einen mit CTRL+ALT+N")
                        continue

                # Scan-Schritt erstellen (x, y werden nicht verwendet)
                step = SequenceStep(
                    x=0, y=0, delay_before=0, name=f"Scan:{scan_name}",
                    item_scan=scan_name, item_scan_mode=scan_mode,
                    else_action=else_data.get("else_action"),
                    else_x=else_data.get("else_x", 0),
                    else_y=else_data.get("else_y", 0),
                    else_delay=else_data.get("else_delay", 0),
                    else_key=else_data.get("else_key"),
                    else_name=else_data.get("else_name", "")
                )
                add_step(step)
                continue

            elif user_input.lower().startswith("key "):
                # Tastendruck
                # Format: "key <Taste>" oder "key <Zeit> <Taste>" oder "key <Min>-<Max> <Taste>"
                key_parts = user_input[4:].strip().split()
                if not key_parts:
                    print("  → Format: key <Taste> | key <Zeit> <Taste>")
                    continue

                delay_min = 0.0
                delay_max = None
                key_name = ""

                if len(key_parts) == 1:
                    # key enter
                    key_name = key_parts[0]
                elif len(key_parts) == 2:
                    # key 5 enter oder key 30-45 enter
                    time_str = key_parts[0]
                    key_name = key_parts[1]
                    if "-" in time_str:
                        try:
                            parts_range = time_str.split("-")
                            delay_min = float(parts_range[0])
                            delay_max = float(parts_range[1])
                        except (ValueError, IndexError):
                            print("  → Format: key <Min>-<Max> <Taste>")
                            continue
                    else:
                        try:
                            delay_min = float(time_str)
                        except ValueError:
                            print("  → Format: key <Zeit> <Taste>")
                            continue
                else:
                    print("  → Format: key <Taste> | key <Zeit> <Taste>")
                    continue

                # Prüfen ob Taste bekannt ist
                if key_name.lower() not in VK_CODES:
                    print(f"  → Unbekannte Taste: '{key_name}'")
                    available_keys = sorted(VK_CODES.keys())
                    print(f"     Verfügbar: {', '.join(available_keys[:15])}...")
                    continue

                step = SequenceStep(x=0, y=0, delay_before=delay_min, name=f"Key:{key_name}",
                                   key_press=key_name, delay_max=delay_max)
                add_step(step)
                continue

            elif user_input.lower().startswith("wait "):
                # Nur warten, kein Klick
                # Format: "wait <Zeit>" oder "wait <Min>-<Max>" oder "wait pixel [else ...]"
                wait_parts = user_input[5:].strip().split()
                if not wait_parts:
                    print("  → Format: wait <Sekunden> | wait <Min>-<Max> | wait pixel [else ...]")
                    continue

                if wait_parts[0].lower() == "pixel" or wait_parts[0].lower() == "gone":
                    # Auf Farbe warten ohne Klick
                    # Format: "wait pixel [else ...]" oder "wait gone [else ...]"
                    wait_until_gone = wait_parts[0].lower() == "gone"
                    else_data = {}
                    if len(wait_parts) > 1 and wait_parts[1].lower() == "else":
                        else_data = parse_else_condition(wait_parts[2:], state)
                        if not else_data and wait_parts[2:]:
                            continue

                    if wait_until_gone:
                        print("\n  Farb-Trigger einrichten (warte bis Farbe WEG ist):")
                        print("  Bewege die Maus zur Position mit der Farbe die VERSCHWINDEN soll")
                    else:
                        print("\n  Farb-Trigger einrichten (ohne Klick):")
                        print("  Bewege die Maus zur Position wo die Farbe geprüft werden soll")
                    if else_data:
                        print(f"  Bei Timeout: {else_data.get('else_action', 'skip')}")
                    print("  Drücke Enter...")
                    input()
                    px, py = get_cursor_pos()
                    print(f"  → Position: ({px}, {py})")

                    if PILLOW_AVAILABLE:
                        img = take_screenshot((px, py, px+1, py+1))
                        if img:
                            color = img.getpixel((0, 0))[:3]
                            color_name = get_color_name(color)
                            if wait_until_gone:
                                print(f"  → Warte bis Farbe WEG: RGB{color} ({color_name})")
                            else:
                                print(f"  → Warte auf Farbe: RGB{color} ({color_name})")
                            step = SequenceStep(
                                x=0, y=0, delay_before=0, name="Wait-Gone" if wait_until_gone else "Wait-Pixel",
                                wait_pixel=(px, py), wait_color=color, wait_only=True,
                                wait_until_gone=wait_until_gone,
                                else_action=else_data.get("else_action"),
                                else_x=else_data.get("else_x", 0),
                                else_y=else_data.get("else_y", 0),
                                else_delay=else_data.get("else_delay", 0),
                                else_key=else_data.get("else_key"),
                                else_name=else_data.get("else_name", "")
                            )
                            add_step(step)
                        else:
                            print("  → Fehler: Konnte Farbe nicht lesen!")
                    else:
                        print("  → Fehler: Pillow nicht installiert!")
                elif "-" in wait_parts[0] and not any(c.isalpha() for c in wait_parts[0]):
                    # Zufällige Wartezeit: wait 30-45 (nur Zahlen, keine Einheiten)
                    try:
                        parts_range = wait_parts[0].split("-")
                        wait_min = float(parts_range[0])
                        wait_max = float(parts_range[1])
                        if wait_min < 0 or wait_max < 0 or wait_max < wait_min:
                            print("  → Wartezeit muss >= 0 und Max >= Min sein!")
                            continue
                        step = SequenceStep(x=0, y=0, delay_before=wait_min, name="Wait",
                                           wait_only=True, delay_max=wait_max)
                        add_step(step)
                    except (ValueError, IndexError):
                        print("  → Format: wait <Min>-<Max>")
                else:
                    # Zeit warten mit optionaler Einheit: wait 30, wait 30s, wait 30m, wait 2h, wait 14:30
                    seconds, desc = parse_time_input(wait_parts[0])
                    if seconds < 0:
                        print(f"  → Fehler: {desc}")
                        print("  → Format: wait <Sek> | wait 30m | wait 2h | wait 14:30 | wait pixel")
                        continue
                    step = SequenceStep(x=0, y=0, delay_before=seconds, name=f"Wait ({desc})", wait_only=True)
                    add_step(step)
                continue

            # Neuen Schritt hinzufügen (Punkt + Zeit oder Pixel)
            # Format: <Nr> <Sek> | <Nr> pixel | <Nr> <Sek> pixel [else ...]
            parts = user_input.split()
            if len(parts) < 2:
                print("  → Format: <Nr> <Sek> | <Nr> pixel | <Nr> <Sek> pixel [else ...]")
                continue

            point_id = int(parts[0])

            with state.lock:
                point = get_point_by_id(state, point_id)
                if not point:
                    print(f"  → Punkt #{point_id} nicht gefunden!")
                    continue
                point_x = point.x
                point_y = point.y
                point_name = point.name

            # Finde "else", "pixel" und "gone" in den parts
            lower_parts = [p.lower() for p in parts]
            else_index = -1
            pixel_index = -1
            gone_index = -1
            if "else" in lower_parts:
                else_index = lower_parts.index("else")
            if "pixel" in lower_parts:
                pixel_index = lower_parts.index("pixel")
            if "gone" in lower_parts:
                gone_index = lower_parts.index("gone")

            # Parse else condition wenn vorhanden
            else_data = {}
            if else_index > 0:
                else_data = parse_else_condition(parts[else_index + 1:], state)
                if not else_data and parts[else_index + 1:]:
                    continue  # Fehler wurde schon ausgegeben
                parts = parts[:else_index]  # Remove else from parts

            use_pixel = pixel_index > 0 and (else_index < 0 or pixel_index < else_index)
            use_gone = gone_index > 0 and (else_index < 0 or gone_index < else_index)
            delay = 0

            if use_pixel or use_gone:
                # Delay ermitteln falls angegeben (z.B. "1 5 pixel" oder "1 5 gone")
                for i, p in enumerate(parts[1:], 1):
                    if p.lower() not in ("pixel", "gone"):
                        try:
                            delay = float(p)
                            if delay < 0:
                                print("  → Wartezeit muss >= 0 sein!")
                                delay = -1
                                break
                        except ValueError:
                            pass
                if delay < 0:
                    continue

                # Pixel-basierte oder Gone-Wartezeit (optional mit Delay davor)
                if use_gone:
                    print("\n  Farb-Trigger einrichten (warte bis Farbe WEG):")
                    print("  Bewege die Maus zur Position mit der Farbe die VERSCHWINDEN soll")
                else:
                    print("\n  Farb-Trigger einrichten:")
                    print("  Bewege die Maus zur Position wo die Farbe geprüft werden soll")
                if delay > 0:
                    print(f"  (Erst {delay}s warten, dann auf Farbe prüfen)")
                if else_data:
                    print(f"  Bei Timeout: {else_data.get('else_action', 'skip')}")
                print("  Drücke Enter...")
                input()
                px, py = get_cursor_pos()
                print(f"  → Position: ({px}, {py})")

                # Farbe an dieser Position lesen
                if PILLOW_AVAILABLE:
                    img = take_screenshot((px, py, px+1, py+1))
                    if img:
                        color = img.getpixel((0, 0))[:3]
                        color_name = get_color_name(color)
                        if use_gone:
                            print(f"  → Gespeicherte Farbe: RGB{color} ({color_name})")
                            print(f"  → Wenn diese Farbe WEG ist → klicke auf {point_name}")
                        else:
                            print(f"  → Gespeicherte Farbe: RGB{color} ({color_name})")
                            print(f"  → Wenn diese Farbe erscheint → klicke auf {point_name}")
                        step = SequenceStep(
                            x=point_x, y=point_y, delay_before=delay, name=point_name,
                            wait_pixel=(px, py), wait_color=color,
                            wait_until_gone=use_gone,
                            else_action=else_data.get("else_action"),
                            else_x=else_data.get("else_x", 0),
                            else_y=else_data.get("else_y", 0),
                            else_delay=else_data.get("else_delay", 0),
                            else_key=else_data.get("else_key"),
                            else_name=else_data.get("else_name", "")
                        )
                        add_step(step)
                    else:
                        print("  → Fehler: Konnte Farbe nicht lesen!")
                else:
                    print("  → Fehler: Pillow nicht installiert! (pip install pillow)")
            else:
                # Zeit-basierte Wartezeit (warte X Sekunden, dann klicke)
                # Unterstützt: "1 30" oder "1 30-45" (zufällige Verzögerung)
                time_str = parts[1]
                delay_min = 0.0
                delay_max = None

                if "-" in time_str:
                    # Zufällige Verzögerung: 1 30-45
                    try:
                        range_parts = time_str.split("-")
                        delay_min = float(range_parts[0])
                        delay_max = float(range_parts[1])
                        if delay_min < 0 or delay_max < 0 or delay_max < delay_min:
                            print("  → Wartezeit muss >= 0 und Max >= Min sein!")
                            continue
                    except (ValueError, IndexError):
                        print("  → Format: <Nr> <Min>-<Max>")
                        continue
                else:
                    delay_min = float(time_str)
                    if delay_min < 0:
                        print("  → Wartezeit muss >= 0 sein!")
                        continue

                step = SequenceStep(x=point_x, y=point_y, delay_before=delay_min,
                                   name=point_name, delay_max=delay_max)
                add_step(step)

        except ValueError:
            print("  → Ungültige Eingabe!")
        except KeyboardInterrupt:
            raise

# =============================================================================
# SEQUENZ LADEN
# =============================================================================
def run_sequence_loader(state: AutoClickerState) -> None:
    """Lädt eine gespeicherte Sequenz."""
    print("\n" + "=" * 60)
    print("  SEQUENZ LADEN")
    print("=" * 60)

    sequences = list_available_sequences()

    if not sequences:
        print("\nKeine Sequenzen gefunden!")
        print(f"Erstelle zuerst eine Sequenz mit CTRL+ALT+E\n")
        return

    print("\nVerfügbare Sequenzen:")
    for i, (name, path) in enumerate(sequences):
        seq = load_sequence_file(path)
        if seq:
            print(f"  {i+1}. {seq}")

    print("\nNummer eingeben | del <Nr> zum Löschen | 'cancel':")

    while True:
        try:
            user_input = input("> ").strip().lower()

            if user_input in ("cancel", "abbruch"):
                print("[CANCEL] Keine Sequenz geladen.")
                return

            # Löschen-Befehl
            if user_input.startswith("del "):
                try:
                    del_num = int(user_input[4:])
                    if 1 <= del_num <= len(sequences):
                        name, path = sequences[del_num - 1]
                        confirm = input(f"Sequenz '{name}' wirklich löschen? (j/n): ").strip().lower()
                        if confirm == "j":
                            Path(path).unlink()
                            with state.lock:
                                if state.active_sequence and state.active_sequence.name == name:
                                    state.active_sequence = None
                            print(f"[OK] Sequenz '{name}' gelöscht!")
                            return
                        else:
                            print("[ABBRUCH] Nicht gelöscht.")
                    else:
                        print(f"[FEHLER] Ungültige Nummer! Verfügbar: 1-{len(sequences)}")
                except ValueError:
                    print("[FEHLER] Format: del <Nr>")
                continue

            idx = int(user_input) - 1
            if idx < 0 or idx >= len(sequences):
                print("[FEHLER] Ungültige Nummer! Nochmal versuchen...")
                continue

            name, path = sequences[idx]
            seq = load_sequence_file(path)

            if seq:
                with state.lock:
                    state.active_sequence = seq
                print(f"\n[ERFOLG] Sequenz '{seq.name}' geladen!")
                print("         Drücke CTRL+ALT+S zum Starten.\n")
            return

        except ValueError:
            print("[FEHLER] Bitte eine Nummer eingeben! Nochmal versuchen...")
        except (KeyboardInterrupt, EOFError):
            print("\n[ABBRUCH]")
            return

# =============================================================================
# WORKER THREAD
# =============================================================================
def wait_with_pause_skip(state: AutoClickerState, seconds: float, phase: str, step_num: int,
                         total_steps: int, message: str) -> bool:
    """Wartet die angegebene Zeit, respektiert Pause und Skip. Gibt False zurück wenn gestoppt."""
    remaining = seconds
    debug_active = state.config.get("debug_mode", False) or state.config.get("debug_detection", False)
    last_remaining = -1  # Track um doppelte Ausgaben zu vermeiden

    while remaining > 0:
        # Check stop
        if state.stop_event.is_set():
            return False

        # Check skip
        if state.skip_event.is_set():
            state.skip_event.clear()
            if debug_active:
                print(f"[{phase}] Schritt {step_num}/{total_steps} | SKIP!")
            else:
                clear_line()
                print(f"[{phase}] Schritt {step_num}/{total_steps} | SKIP!", end="", flush=True)
            return True

        # Check pause
        if not wait_while_paused(state, message):
            return False

        # Ausgabe nur wenn sich remaining geändert hat (weniger Spam bei Debug)
        current_remaining = int(remaining)
        if current_remaining != last_remaining:
            if debug_active:
                print(f"[{phase}] Schritt {step_num}/{total_steps} | {message} ({remaining:.0f}s)...")
            else:
                clear_line()
                print(f"[{phase}] Schritt {step_num}/{total_steps} | {message} ({remaining:.0f}s)...", end="", flush=True)
            last_remaining = current_remaining

        wait_time = min(1.0, remaining)
        if state.stop_event.wait(wait_time):
            return False
        remaining -= wait_time

    return True

def execute_else_action(state: AutoClickerState, step: SequenceStep, phase: str,
                        step_num: int, total_steps: int) -> bool:
    """Führt die Else-Aktion eines Schritts aus. Gibt False zurück wenn abgebrochen."""
    if not step.else_action:
        return True

    if step.else_action == "skip":
        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | ELSE: übersprungen", end="", flush=True)
        return True

    elif step.else_action == "click":
        # Warten falls Delay angegeben
        if step.else_delay > 0:
            if not wait_with_pause_skip(state, step.else_delay, phase, step_num, total_steps,
                                        f"ELSE: klicke in"):
                return False

        if state.stop_event.is_set():
            return False

        send_click(step.else_x, step.else_y)
        with state.lock:
            state.total_clicks += 1
        name = step.else_name or f"({step.else_x},{step.else_y})"
        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | ELSE: Klick auf {name}!", end="", flush=True)
        return True

    elif step.else_action == "key":
        # Warten falls Delay angegeben
        if step.else_delay > 0:
            if not wait_with_pause_skip(state, step.else_delay, phase, step_num, total_steps,
                                        f"ELSE: Taste in"):
                return False

        if state.stop_event.is_set():
            return False

        if send_key(step.else_key):
            with state.lock:
                state.key_presses += 1
            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | ELSE: Taste '{step.else_key}'!", end="", flush=True)
        return True

    elif step.else_action == "restart":
        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | ELSE: Neustart!", end="", flush=True)
        state.restart_event.set()
        return False  # Beendet aktuelle Ausführung, sequence_worker prüft restart_event

    return True


def _execute_item_scan_step(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Item-Scan Schritt aus. Gibt False zurück wenn abgebrochen."""
    mode = step.item_scan_mode
    mode_str = "alle" if mode == "all" else "bestes"
    clear_line()
    print(f"[{phase}] Schritt {step_num}/{total_steps} | Scan '{step.item_scan}' ({mode_str})...", end="", flush=True)

    scan_results = execute_item_scan(state, step.item_scan, mode)
    if state.config.get("debug_detection", False):
        print()  # Neue Zeile nach end=""
        print(f"[DEBUG] scan_results = {scan_results}")

    if scan_results:
        # Klicke alle gefundenen Positionen
        for i, (pos, item, priority) in enumerate(scan_results):
            if state.stop_event.is_set():
                return False
            if state.config.get("debug_detection", False):
                print(f"[DEBUG] Klicke Item '{item.name}' (P{priority}) bei ({pos[0]}, {pos[1]})")
            send_click(pos[0], pos[1])
            with state.lock:
                state.total_clicks += 1
                state.items_found += 1
                # Kategorie mit Priorität speichern
                cat = item.category or item.name
                if cat not in state.clicked_categories or priority < state.clicked_categories[cat]:
                    state.clicked_categories[cat] = priority

            # Bestätigungs-Klick falls definiert
            if item.confirm_point is not None:
                confirm_x, confirm_y = item.confirm_point.x, item.confirm_point.y
                if state.config.get("debug_detection", False):
                    print(f"[DEBUG] Item hat confirm_point=({confirm_x},{confirm_y}), confirm_delay={item.confirm_delay}")
                if item.confirm_delay > 0:
                    time.sleep(item.confirm_delay)
                send_click(confirm_x, confirm_y)
                if state.config.get("debug_detection", False):
                    print(f"[DEBUG] Bestätigungs-Klick ausgeführt")
                with state.lock:
                    state.total_clicks += 1

            # Konfigurierbare Pause nach Item-Klick
            click_delay = state.config.get("item_click_delay", 1.0)
            if click_delay > 0:
                time.sleep(click_delay)

        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | {len(scan_results)} Item(s)! "
              f"(Items: {state.items_found}, Klicks: {state.total_clicks})", end="", flush=True)
    else:
        # Kein Item gefunden - Else-Aktion ausführen
        if step.else_action:
            return execute_else_action(state, step, phase, step_num, total_steps)
        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | Scan: kein Item gefunden", end="", flush=True)

    return True


def _execute_key_press_step(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Tastendruck-Schritt aus. Gibt False zurück wenn abgebrochen."""
    # Erst warten (mit zufälliger Verzögerung)
    actual_delay = step.get_actual_delay()
    if actual_delay > 0:
        if not wait_with_pause_skip(state, actual_delay, phase, step_num, total_steps,
                                    f"Taste '{step.key_press}' in"):
            return False

    if state.stop_event.is_set():
        return False

    # Taste drücken
    if send_key(step.key_press):
        with state.lock:
            state.key_presses += 1
        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | Taste '{step.key_press}'! "
              f"(Tasten: {state.key_presses})", end="", flush=True)

    return True


def _execute_wait_for_color(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Wartet auf eine Farbe an einer Pixel-Position. Gibt False zurück wenn abgebrochen."""
    # Optional: Erst delay_before warten
    actual_delay = step.get_actual_delay()
    if actual_delay > 0:
        if not wait_with_pause_skip(state, actual_delay, phase, step_num, total_steps, "Vor Farbprüfung"):
            return False

    # Maus kurz zum Prüf-Pixel bewegen wenn aktiviert
    if state.config.get("show_pixel_position", False):
        set_cursor_pos(step.wait_pixel[0], step.wait_pixel[1])
        time.sleep(0.3)

    timeout = PIXEL_WAIT_TIMEOUT
    start_time = time.time()
    expected_name = get_color_name(step.wait_color)
    wait_mode = "WEG" if step.wait_until_gone else "DA"

    while not state.stop_event.is_set():
        # Check skip
        if state.skip_event.is_set():
            state.skip_event.clear()
            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | SKIP Farbwarten!", end="", flush=True)
            break

        # Check pause
        if not wait_while_paused(state, "Warte auf Farbe..."):
            break

        # Prüfe Farbe
        if PILLOW_AVAILABLE:
            img = take_screenshot((step.wait_pixel[0], step.wait_pixel[1],
                                  step.wait_pixel[0]+1, step.wait_pixel[1]+1))
            if img:
                current_color = img.getpixel((0, 0))[:3]
                dist = color_distance(current_color, step.wait_color)
                pixel_tolerance = state.config.get("pixel_wait_tolerance", PIXEL_WAIT_TOLERANCE)
                color_matches = dist <= pixel_tolerance
                condition_met = (not color_matches) if step.wait_until_gone else color_matches

                # Debug-Ausgabe
                if state.config.get("debug_detection", False):
                    current_name = get_color_name(current_color)
                    elapsed = time.time() - start_time
                    if step.wait_until_gone:
                        print(f"[DEBUG] Aktuell: RGB{current_color} ({current_name}) | "
                              f"Warte auf WEG: RGB{step.wait_color} ({expected_name}) | "
                              f"Diff: {dist:.0f} (Tol: {pixel_tolerance}) | Match: {color_matches} ({elapsed:.0f}s)")
                    else:
                        print(f"[DEBUG] Aktuell: RGB{current_color} ({current_name}) | "
                              f"Erwartet: RGB{step.wait_color} ({expected_name}) | "
                              f"Diff: {dist:.0f} (Tol: {pixel_tolerance}) | Match: {color_matches} ({elapsed:.0f}s)")

                if condition_met:
                    msg = "Farbe weg!" if step.wait_until_gone else "Farbe erkannt!"
                    if state.config.get("debug_detection", False):
                        if step.wait_only:
                            print(f"[{phase}] Schritt {step_num}/{total_steps} | {msg}")
                        else:
                            print(f"[{phase}] Schritt {step_num}/{total_steps} | {msg} Klicke...")
                    else:
                        clear_line()
                        if step.wait_only:
                            print(f"[{phase}] Schritt {step_num}/{total_steps} | {msg}", end="", flush=True)
                        else:
                            print(f"[{phase}] Schritt {step_num}/{total_steps} | {msg} Klicke...", end="", flush=True)
                    break

        # Timeout-Check (MUSS vor dem wait kommen, sonst wird er bei debug_detection übersprungen)
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            # Timeout - Else-Aktion ausführen falls vorhanden
            if step.else_action:
                if state.config.get("debug_detection", False):
                    print(f"[{phase}] Schritt {step_num}/{total_steps} | TIMEOUT nach {timeout}s")
                else:
                    clear_line()
                    print(f"[{phase}] Schritt {step_num}/{total_steps} | TIMEOUT nach {timeout}s", end="", flush=True)
                return execute_else_action(state, step, phase, step_num, total_steps)
            print(f"[TIMEOUT] Farbe nicht erkannt nach {timeout}s - Sequenz gestoppt!")
            state.stop_event.set()
            return False

        # Status-Ausgabe
        if not state.config.get("debug_detection", False):
            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | Warte bis Farbe {wait_mode}... ({elapsed:.0f}s)", end="", flush=True)

        check_interval = state.config.get("pixel_check_interval", PIXEL_CHECK_INTERVAL)
        if state.stop_event.wait(check_interval):
            return False

    return True


def _execute_click(state: AutoClickerState, step: SequenceStep,
                   step_num: int, total_steps: int, phase: str) -> bool:
    """Führt den eigentlichen Klick aus. Gibt False zurück wenn abgebrochen."""
    for _ in range(CLICKS_PER_POINT):
        if state.stop_event.is_set():
            return False

        if check_failsafe(state):
            print("\n[FAILSAFE] Stoppe...")
            state.stop_event.set()
            return False

        send_click(step.x, step.y)

        with state.lock:
            state.total_clicks += 1

        if state.config.get("debug_mode", False) or state.config.get("debug_detection", False):
            print(f"[{phase}] Schritt {step_num}/{total_steps} | Klick! (Gesamt: {state.total_clicks})")
        else:
            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | Klick! (Gesamt: {state.total_clicks})", end="", flush=True)

        if MAX_TOTAL_CLICKS and state.total_clicks >= MAX_TOTAL_CLICKS:
            print(f"\n[INFO] Maximum von {MAX_TOTAL_CLICKS} Klicks erreicht.")
            state.stop_event.set()
            return False

    return True


def execute_step(state: AutoClickerState, step: SequenceStep, step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen einzelnen Schritt aus: Erst warten/prüfen, DANN klicken. Gibt False zurück wenn abgebrochen."""

    # Fail-Safe prüfen
    if check_failsafe(state):
        print("\n[FAILSAFE] Maus in Ecke erkannt! Stoppe...")
        state.stop_event.set()
        return False

    # Debug: Zeige Schritt-Details
    if state.config.get("debug_mode", False):
        print(f"[DEBUG] Step {step_num}: name='{step.name}', x={step.x}, y={step.y}, "
              f"delay_before={step.delay_before}, wait_pixel={step.wait_pixel}, wait_only={step.wait_only}")

    # === SONDERFALL: Item-Scan Schritt ===
    if step.item_scan:
        return _execute_item_scan_step(state, step, step_num, total_steps, phase)

    # === SONDERFALL: Tastendruck ===
    if step.key_press:
        return _execute_key_press_step(state, step, step_num, total_steps, phase)

    # === PHASE 1: Warten VOR dem Klick (Zeit oder Farbe) ===
    if step.wait_pixel and step.wait_color:
        if not _execute_wait_for_color(state, step, step_num, total_steps, phase):
            return False
    elif step.delay_before > 0 or step.delay_max:
        # Zeit-basierte Wartezeit VOR dem Klick (mit zufälliger Verzögerung)
        actual_delay = step.get_actual_delay()
        if state.config.get("debug_mode", False):
            print(f"[DEBUG] Step {step_num}: Warte {actual_delay:.1f}s")
        action = "Warten" if step.wait_only else "Klicke in"
        if not wait_with_pause_skip(state, actual_delay, phase, step_num, total_steps, action):
            return False
    else:
        if state.config.get("debug_mode", False):
            print(f"[DEBUG] Step {step_num}: Keine Wartezeit -> sofort klicken")

    if state.stop_event.is_set():
        return False

    # === SONDERFALL: Nur warten, kein Klick ===
    if step.wait_only:
        if state.config.get("debug_mode", False) or state.config.get("debug_detection", False):
            print(f"[{phase}] Schritt {step_num}/{total_steps} | Warten beendet (kein Klick)")
        else:
            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | Warten beendet (kein Klick)")
        return True

    # === PHASE 2: Klick ausführen ===
    return _execute_click(state, step, step_num, total_steps, phase)


def format_duration(seconds: float) -> str:
    """Formatiert Sekunden als hh:mm:ss oder mm:ss."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    elif minutes > 0:
        return f"{minutes}m {secs:02d}s"
    else:
        return f"{secs}s"

def sequence_worker(state: AutoClickerState) -> None:
    """Worker-Thread, der die Sequenz ausführt (Start + mehrere Loop-Phasen mit Zyklen)."""
    print("\n[WORKER] Sequenz gestartet.")

    with state.lock:
        sequence = state.active_sequence
        if not sequence:
            print("[FEHLER] Keine gültige Sequenz!")
            state.is_running = False
            return

        has_start = len(sequence.start_steps) > 0
        has_loops = len(sequence.loop_phases) > 0
        has_end = len(sequence.end_steps) > 0
        total_cycles = sequence.total_cycles

        if not has_start and not has_loops:
            print("[FEHLER] Sequenz ist leer!")
            state.is_running = False
            return

        # Debug: Zeige alle Schritte (mit Rahmen damit es nicht überschrieben wird)
        if state.config.get("debug_mode", False):
            print("\n" + "=" * 60)
            print("[DEBUG] GELADENE SEQUENZ-SCHRITTE:")
            print("-" * 60)
            for i, step in enumerate(sequence.start_steps):
                print(f"  START[{i+1}]: {step.name or 'unnamed'} | delay={step.delay_before}s | wait_only={step.wait_only}")
            for lp in sequence.loop_phases:
                print(f"  --- {lp.name} (x{lp.repeat}) ---")
                for i, step in enumerate(lp.steps):
                    print(f"  {lp.name}[{i+1}]: {step.name or 'unnamed'} | delay={step.delay_before}s | wait_only={step.wait_only}")
            for i, step in enumerate(sequence.end_steps):
                print(f"  END[{i+1}]: {step.name or 'unnamed'} | delay={step.delay_before}s")
            print("=" * 60)
            # Bei geplantem Start kein Enter nötig (wurde bereits vorher bestätigt)
            if state.scheduled_start:
                state.scheduled_start = False  # Reset für nächstes Mal
                print("[DEBUG] Geplanter Start - überspringe Enter-Bestätigung")
            else:
                print("[DEBUG] Drücke Enter zum Starten...")
                input()  # Warte auf Bestätigung damit man die Werte sehen kann

        # Statistiken zurücksetzen
        state.total_clicks = 0
        state.items_found = 0
        state.key_presses = 0
        state.start_time = time.time()

    cycle_count = 0

    # Äußere Schleife für Zyklen (START → alle Loops → START → alle Loops → ...)
    while not state.stop_event.is_set() and not state.quit_event.is_set():
        # Prüfe ob Neustart angefordert wurde
        if state.restart_event.is_set():
            state.restart_event.clear()
            cycle_count = 0
            print("\n[RESTART] Sequenz wird neu gestartet...")

        cycle_count += 1

        # Geklickte Kategorien zurücksetzen für neuen Zyklus
        with state.lock:
            state.clicked_categories.clear()

        # Prüfen ob max Zyklen erreicht (0 = unendlich)
        if total_cycles > 0 and cycle_count > total_cycles:
            print(f"\n[FERTIG] Alle {total_cycles} Zyklen abgeschlossen!")
            break

        cycle_str = f"Zyklus {cycle_count}" if total_cycles == 0 else f"Zyklus {cycle_count}/{total_cycles}"

        # === PHASE 1: START-SEQUENZ ===
        if has_start and not state.stop_event.is_set():
            if cycle_count == 1:
                print(f"\n[START] Führe Start-Sequenz aus... ({cycle_str})")
            else:
                print(f"\n[{cycle_str}] Starte erneut...")
            total_start = len(sequence.start_steps)

            for i, step in enumerate(sequence.start_steps):
                if state.stop_event.is_set() or state.quit_event.is_set():
                    break
                if not execute_step(state, step, i + 1, total_start, "START"):
                    break

            if state.restart_event.is_set():
                continue  # Neustart von oben
            if state.stop_event.is_set():
                break

        # === PHASE 2: ALLE LOOP-PHASEN ===
        if has_loops and not state.stop_event.is_set():
            for loop_phase in sequence.loop_phases:
                if state.stop_event.is_set() or state.quit_event.is_set():
                    break

                total_steps = len(loop_phase.steps)
                if total_steps == 0:
                    continue

                print(f"\n[{loop_phase.name}] Starte ({loop_phase.repeat}x) | {cycle_str}")

                # Diese Loop-Phase X-mal wiederholen
                for repeat_num in range(1, loop_phase.repeat + 1):
                    if state.stop_event.is_set() or state.quit_event.is_set():
                        break

                    for i, step in enumerate(loop_phase.steps):
                        if state.stop_event.is_set() or state.quit_event.is_set():
                            break

                        phase_label = f"{loop_phase.name} #{repeat_num}/{loop_phase.repeat}"
                        if not execute_step(state, step, i + 1, total_steps, phase_label):
                            break

                    # Restart innerhalb Loop-Phase?
                    if state.restart_event.is_set():
                        break

                # Restart innerhalb Loop-Phase?
                if state.restart_event.is_set():
                    break

                if not state.stop_event.is_set():
                    print(f"\n[{loop_phase.name}] Abgeschlossen.")

            if state.restart_event.is_set():
                continue  # Neustart von oben
            if state.stop_event.is_set():
                break

        # Restart angefordert?
        if state.restart_event.is_set():
            continue  # Neustart von oben

        # Wenn keine Loops oder total_cycles==1 → nach einem Durchlauf fertig
        if not has_loops or total_cycles == 1:
            print("\n[FERTIG] Sequenz einmal durchgelaufen.")
            break

    # === PHASE 3: END-SEQUENZ (nach allen Zyklen) ===
    if has_end and not state.quit_event.is_set():
        print(f"\n[END] Führe End-Sequenz aus...")
        total_end = len(sequence.end_steps)

        for i, step in enumerate(sequence.end_steps):
            if state.quit_event.is_set():
                break
            execute_step(state, step, i + 1, total_end, "END")

        if not state.quit_event.is_set():
            print("\n[END] End-Sequenz abgeschlossen.")

    with state.lock:
        state.is_running = False
        duration = time.time() - state.start_time if state.start_time else 0

    # Statistiken ausgeben
    print("\n[WORKER] Sequenz gestoppt.")
    print("-" * 50)
    print("STATISTIKEN:")
    print(f"  Laufzeit:     {format_duration(duration)}")
    print(f"  Zyklen:       {cycle_count}")
    print(f"  Klicks:       {state.total_clicks}")
    if state.items_found > 0:
        print(f"  Items:        {state.items_found}")
    if state.key_presses > 0:
        print(f"  Tasten:       {state.key_presses}")
    print("-" * 50)
    print_status(state)

# =============================================================================
# HOTKEY HANDLER
# =============================================================================
def handle_record(state: AutoClickerState) -> None:
    """Nimmt die aktuelle Mausposition auf - sofort ohne Eingabe."""
    x, y = get_cursor_pos()

    with state.lock:
        new_id = get_next_point_id(state)
        name = f"P{new_id}"
        point = ClickPoint(x, y, name, new_id)
        state.points.append(point)

    # Auto-speichern
    save_data(state)

    print(f"\n[RECORD] #{new_id} {name} hinzugefügt: ({x}, {y})")
    print_status(state)

def handle_undo(state: AutoClickerState) -> None:
    """Entfernt den letzten Punkt."""
    with state.lock:
        if state.points:
            removed = state.points.pop()
            print(f"\n[UNDO] Punkt entfernt: {removed}")
            save_data(state)
        else:
            print("\n[UNDO] Keine Punkte zum Entfernen.")
    print_status(state)

def handle_clear(state: AutoClickerState) -> None:
    """Löscht ALLE Punkte."""
    with state.lock:
        if state.is_running:
            print("\n[FEHLER] Stoppe zuerst den Klicker (CTRL+ALT+S)!")
            return

        count = len(state.points)
        if count == 0:
            print("\n[CLEAR] Keine Punkte vorhanden.")
            return

        state.points.clear()
        state.active_sequence = None

    save_data(state)
    print(f"\n[CLEAR] Alle {count} Punkte gelöscht!")
    print_status(state)

def handle_reset(state: AutoClickerState) -> None:
    """Löscht ALLES - kompletter Factory Reset wie frisch von GitHub."""
    with state.lock:
        if state.is_running:
            print("\n[FEHLER] Stoppe zuerst den Klicker (CTRL+ALT+S)!")
            return

    print("\n" + "=" * 60)
    print("  ⚠️  FACTORY RESET - ALLES WIRD GELÖSCHT!")
    print("=" * 60)
    print("\nFolgendes wird gelöscht:")
    print(f"  • {len(state.points)} Punkt(e)")
    print(f"  • {len(list_available_sequences())} Sequenz-Datei(en)")
    print(f"  • {len(state.global_slots)} Slot(s)")
    print(f"  • {len(state.global_items)} Item(s)")
    print(f"  • {len(state.item_scans)} Item-Scan(s)")
    print(f"  • Config-Einstellungen")
    print("\nDas Programm wird danach wie frisch von GitHub sein!")
    print("\nBist du sicher? Tippe 'JA' zum Bestätigen:")

    try:
        confirm = input("> ").strip().upper()
        if confirm != "JA":
            print("[ABBRUCH] Nichts wurde gelöscht.")
            return

        # Speicher löschen
        with state.lock:
            state.points.clear()
            state.sequences.clear()
            state.active_sequence = None
            state.global_slots.clear()
            state.global_items.clear()
            state.item_scans.clear()

        # Alle Ordner löschen
        folders_to_delete = [SEQUENCES_DIR, ITEMS_DIR, SLOTS_DIR, ITEM_SCANS_DIR]
        for folder in folders_to_delete:
            folder_path = Path(folder)
            if folder_path.exists():
                shutil.rmtree(folder_path)
                print(f"  ✓ {folder}/ gelöscht")

        # Config löschen
        config_path = Path(CONFIG_FILE)
        if config_path.exists():
            config_path.unlink()
            print(f"  ✓ {CONFIG_FILE} gelöscht")

        # Ordner neu erstellen
        ensure_sequences_dir()
        for folder in [ITEMS_DIR, SLOTS_DIR, ITEM_SCANS_DIR]:
            Path(folder).mkdir(exist_ok=True)

        # Config auf Standard zurücksetzen (nur state.config, nicht globale Variable)
        with state.lock:
            state.config = DEFAULT_CONFIG.copy()

        print("\n[RESET] ✓ Factory Reset abgeschlossen!")
        print("[RESET] Das Programm ist jetzt wie frisch von GitHub.")
        print_status(state)

    except (KeyboardInterrupt, EOFError):
        print("\n[ABBRUCH] Nichts wurde gelöscht.")

def handle_editor(state: AutoClickerState) -> None:
    """Öffnet den Sequenz-Editor."""
    with state.lock:
        if state.is_running:
            print("\n[FEHLER] Stoppe zuerst den Klicker (CTRL+ALT+S)!")
            return
    run_sequence_editor(state)

def handle_item_scan_editor(state: AutoClickerState) -> None:
    """Öffnet das Item-Scan Menü (Slots, Items, Scans)."""
    with state.lock:
        if state.is_running:
            print("\n[FEHLER] Stoppe zuerst den Klicker (CTRL+ALT+S)!")
            return
    run_item_scan_menu(state)

def handle_load(state: AutoClickerState) -> None:
    """Lädt eine Sequenz."""
    with state.lock:
        if state.is_running:
            print("\n[FEHLER] Stoppe zuerst den Klicker (CTRL+ALT+S)!")
            return
    run_sequence_loader(state)

def handle_show(state: AutoClickerState) -> None:
    """Zeigt alle Punkte an, ermöglicht Testen und Umbenennen."""
    print_points(state)

    with state.lock:
        if not state.points:
            return
        num_points = len(state.points)

    print("-" * 50)
    print("Optionen:")
    print("  <Nr>        - Punkt testen (Maus hinbewegen ohne Klick)")
    print("  <Nr> <Name> - Punkt umbenennen")
    print("  del <Nr>    - Punkt löschen")
    print("  Enter       - Zurück")
    print("-" * 50)

    while True:
        try:
            user_input = input("> ").strip()
            if not user_input:
                return

            # Löschen-Befehl (per ID)
            if user_input.lower().startswith("del "):
                try:
                    del_id = int(user_input[4:])
                    with state.lock:
                        point_to_del = get_point_by_id(state, del_id)
                        if not point_to_del:
                            print(f"[FEHLER] Punkt #{del_id} nicht gefunden!")
                            continue
                        state.points.remove(point_to_del)
                        num_points = len(state.points)
                    save_data(state)
                    print(f"[OK] Punkt #{del_id} gelöscht: {point_to_del}")
                    if num_points == 0:
                        print("[INFO] Keine Punkte mehr vorhanden.")
                        return
                except ValueError:
                    print("[FEHLER] Format: del <ID>")
                continue

            parts = user_input.split(maxsplit=1)
            point_id = int(parts[0])

            with state.lock:
                point = get_point_by_id(state, point_id)
                if not point:
                    print(f"[FEHLER] Punkt #{point_id} nicht gefunden!")
                    continue

            if len(parts) == 1:
                # Nur ID → Testen (Maus hinbewegen)
                print(f"[TEST] Bewege Maus zu {point.name} ({point.x}, {point.y})...")
                set_cursor_pos(point.x, point.y)
                print(f"[TEST] Maus ist jetzt bei {point.name}. Neuer Name? (Enter = behalten)")

                new_name = input("> ").strip()
                if new_name:
                    with state.lock:
                        point.name = new_name
                    save_data(state)
                    print(f"[OK] Punkt #{point_id} umbenannt zu '{new_name}'")
                else:
                    print(f"[OK] Name '{point.name}' beibehalten.")

            else:
                # ID + Name → Direkt umbenennen
                new_name = parts[1]
                with state.lock:
                    point.name = new_name
                save_data(state)
                print(f"[OK] Punkt #{point_id} umbenannt zu '{new_name}'")

        except ValueError:
            print("[FEHLER] Ungültige Eingabe!")
        except (KeyboardInterrupt, EOFError):
            return

def handle_toggle(state: AutoClickerState) -> None:
    """Startet oder stoppt die Sequenz."""
    # Prüfe ob bereits läuft → stoppen
    with state.lock:
        if state.is_running:
            state.stop_event.set()
            print("\n[TOGGLE] Stoppe Sequenz...")
            return

    # Keine Sequenz geladen → automatisch Lade-Menü öffnen
    if not state.active_sequence:
        print("\n[INFO] Keine Sequenz geladen - öffne Lade-Menü...")
        run_sequence_loader(state)
        # Nach dem Laden prüfen ob jetzt eine Sequenz da ist
        if not state.active_sequence:
            return  # Nichts geladen

    # Jetzt starten
    with state.lock:
        if not state.points:
            print("\n[FEHLER] Keine Punkte gespeichert!")
            return

        state.is_running = True
        state.stop_event.clear()
        state.pause_event.clear()
        state.skip_event.clear()

        worker = threading.Thread(target=sequence_worker, args=(state,), daemon=True)
        worker.start()

def handle_pause(state: AutoClickerState) -> None:
    """Pausiert oder setzt die Sequenz fort."""
    with state.lock:
        if not state.is_running:
            print("\n[INFO] Keine Sequenz läuft.")
            return

        if state.pause_event.is_set():
            state.pause_event.clear()
            print("\n[RESUME] Sequenz fortgesetzt.")
        else:
            state.pause_event.set()
            print("\n[PAUSE] Sequenz pausiert. Fortsetzen: CTRL+ALT+G")

def handle_skip(state: AutoClickerState) -> None:
    """Überspringt die aktuelle Wartezeit."""
    with state.lock:
        if not state.is_running:
            print("\n[INFO] Keine Sequenz läuft.")
            return

        state.skip_event.set()
        print("\n[SKIP] Wartezeit übersprungen!")

def handle_switch(state: AutoClickerState) -> None:
    """Schneller Wechsel zwischen gespeicherten Sequenzen."""
    with state.lock:
        if state.is_running:
            print("\n[FEHLER] Stoppe zuerst den Klicker (CTRL+ALT+S)!")
            return

    sequences = list_available_sequences()

    if not sequences:
        print("\n[INFO] Keine Sequenzen vorhanden! Erstelle eine mit CTRL+ALT+E")
        return

    print("\n" + "-" * 40)
    print("QUICK-SWITCH: Sequenz wählen")
    print("-" * 40)

    for i, (name, path) in enumerate(sequences):
        seq = load_sequence_file(path)
        if seq:
            # Markiere aktive Sequenz
            active_marker = " ◄" if state.active_sequence and state.active_sequence.name == seq.name else ""
            print(f"  {i+1}. {seq.name}{active_marker}")

    print("\nNummer eingeben (Enter = abbrechen):")

    try:
        choice = input("> ").strip()
        if not choice:
            return

        idx = int(choice) - 1
        if idx < 0 or idx >= len(sequences):
            print("[FEHLER] Ungültige Nummer!")
            return

        name, path = sequences[idx]
        seq = load_sequence_file(path)

        if seq:
            with state.lock:
                state.active_sequence = seq
            print(f"\n[OK] Gewechselt zu: {seq.name}")
            print("     Starten mit CTRL+ALT+S")

    except ValueError:
        print("[FEHLER] Ungültige Eingabe!")
    except (KeyboardInterrupt, EOFError):
        pass

def handle_schedule(state: AutoClickerState) -> None:
    """Plant den Start einer Sequenz zu einem bestimmten Zeitpunkt."""
    from datetime import datetime

    with state.lock:
        if state.is_running:
            print("\n[FEHLER] Stoppe zuerst den Klicker (CTRL+ALT+S)!")
            return

    # Keine Sequenz geladen → automatisch Lade-Menü öffnen
    if not state.active_sequence:
        print("\n[INFO] Keine Sequenz geladen - öffne Lade-Menü...")
        run_sequence_loader(state)
        # Nach dem Laden prüfen ob jetzt eine Sequenz da ist
        if not state.active_sequence:
            return  # Nichts geladen

    print("\n" + "=" * 50)
    print("ZEITPLAN: Sequenz zu bestimmter Zeit starten")
    print("=" * 50)
    print(f"\nAktive Sequenz: {state.active_sequence.name}")
    print("\nZeit-Formate:")
    print("  14:30    → Startet um 14:30 Uhr")
    print("  +30m     → Startet in 30 Minuten")
    print("  +2h      → Startet in 2 Stunden")
    print("  30m      → Wartet 30 Minuten")
    print("\nZeit eingeben (oder 'cancel'):")

    try:
        time_input = input("> ").strip()

        if not time_input or time_input.lower() == "cancel":
            print("[ABBRUCH]")
            return

        seconds, desc = parse_time_input(time_input)

        if seconds < 0:
            print(f"[FEHLER] {desc}")
            return

        if seconds < 1:
            print("[INFO] Zeit zu kurz - starte sofort...")
            # Starte sofort
            handle_toggle(state)
            return

        # Zeige Countdown-Info und warte auf Bestätigung
        target_time = datetime.now().timestamp() + seconds
        target_dt = datetime.fromtimestamp(target_time)
        print(f"\n[GEPLANT] Sequenz '{state.active_sequence.name}' startet {desc}")
        print(f"          Zielzeit: {target_dt.strftime('%H:%M:%S')}")
        print(f"          Wartezeit: {format_duration(seconds)}")
        print("\n          Enter drücken zum Starten, 'cancel' zum Abbrechen")

        # Bestätigung abwarten
        confirm = input("> ").strip().lower()
        if confirm == "cancel":
            print("[ABBRUCH]")
            return

        # Jetzt startet der Countdown - ab hier läuft alles automatisch
        print("\n[COUNTDOWN] Warte auf Startzeit... (Abbrechen mit CTRL+ALT+S)")

        # Zeitpunkt neu berechnen (nach Enter-Bestätigung)
        target_time = datetime.now().timestamp() + seconds
        target_dt = datetime.fromtimestamp(target_time)

        # Warte bis zur Startzeit
        start_time = time.time()
        while not state.stop_event.is_set() and not state.quit_event.is_set():
            remaining = seconds - (time.time() - start_time)

            if remaining <= 0:
                break

            # Zeige Countdown
            print(f"\r[COUNTDOWN] Noch {format_duration(remaining)}...    ", end="", flush=True)

            # Warte 1 Sekunde (oder bis Stop-Event)
            if state.stop_event.wait(min(1.0, remaining)):
                print("\n[ABBRUCH] Zeitplan abgebrochen.")
                state.stop_event.clear()  # Reset für nächsten Start
                return

        if state.quit_event.is_set():
            return

        # Zeit erreicht - starte Sequenz
        print("\n[START] Zeit erreicht - starte Sequenz!")
        state.stop_event.clear()  # Reset falls gesetzt
        state.scheduled_start = True  # Überspringt Debug-Enter-Prompt
        handle_toggle(state)

    except (KeyboardInterrupt, EOFError):
        print("\n[ABBRUCH]")
    except ValueError as e:
        print(f"[FEHLER] {e}")

def handle_analyze(state: AutoClickerState) -> None:
    """Startet den Farb-Analysator."""
    with state.lock:
        if state.is_running:
            print("\n[FEHLER] Stoppe zuerst den Klicker (CTRL+ALT+S)!")
            return
    run_color_analyzer()

def handle_quit(state: AutoClickerState, main_thread_id: int) -> None:
    """Beendet das Programm."""
    print("\n[QUIT] Beende Programm...")

    state.stop_event.set()
    state.quit_event.set()

    WM_QUIT = 0x0012
    user32.PostThreadMessageW(main_thread_id, WM_QUIT, 0, 0)

# =============================================================================
# HOTKEY REGISTRIERUNG
# =============================================================================
def register_hotkeys() -> bool:
    """Registriert alle globalen Hotkeys."""
    modifiers = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT

    hotkeys = [
        (HOTKEY_RECORD, VK_A, "CTRL+ALT+A (Punkt hinzufügen)"),
        (HOTKEY_UNDO, VK_U, "CTRL+ALT+U (Rückgängig)"),
        (HOTKEY_CLEAR, VK_C, "CTRL+ALT+C (Punkte löschen)"),
        (HOTKEY_RESET, VK_X, "CTRL+ALT+X (FACTORY RESET)"),
        (HOTKEY_EDITOR, VK_E, "CTRL+ALT+E (Sequenz-Editor)"),
        (HOTKEY_ITEM_SCAN, VK_N, "CTRL+ALT+N (Item-Scan Editor)"),
        (HOTKEY_LOAD, VK_L, "CTRL+ALT+L (Sequenz laden)"),
        (HOTKEY_SHOW, VK_P, "CTRL+ALT+P (Punkte/Sequenzen anzeigen)"),
        (HOTKEY_TOGGLE, VK_S, "CTRL+ALT+S (Start/Stop)"),
        (HOTKEY_PAUSE, VK_G, "CTRL+ALT+G (Pause/Resume)"),
        (HOTKEY_SKIP, VK_K, "CTRL+ALT+K (Skip Wartezeit)"),
        (HOTKEY_SWITCH, VK_W, "CTRL+ALT+W (Quick-Switch)"),
        (HOTKEY_SCHEDULE, VK_Z, "CTRL+ALT+Z (Zeitplan)"),
        (HOTKEY_ANALYZE, VK_T, "CTRL+ALT+T (Farb-Analysator)"),
        (HOTKEY_QUIT, VK_Q, "CTRL+ALT+Q (Beenden)"),
    ]

    failed = []
    for hk_id, vk, name in hotkeys:
        if not user32.RegisterHotKey(None, hk_id, modifiers, vk):
            failed.append(name)

    # Nur Fehler anzeigen
    if failed:
        print("[FEHLER] Folgende Hotkeys konnten nicht registriert werden:")
        for name in failed:
            print(f"  ✗ {name}")
        return False

    return True

def unregister_hotkeys() -> None:
    """Deregistriert alle Hotkeys."""
    for hk_id in [HOTKEY_RECORD, HOTKEY_UNDO, HOTKEY_CLEAR, HOTKEY_RESET,
                  HOTKEY_EDITOR, HOTKEY_ITEM_SCAN, HOTKEY_LOAD, HOTKEY_SHOW,
                  HOTKEY_TOGGLE, HOTKEY_PAUSE, HOTKEY_SKIP, HOTKEY_SWITCH,
                  HOTKEY_SCHEDULE, HOTKEY_ANALYZE, HOTKEY_QUIT]:
        user32.UnregisterHotKey(None, hk_id)

# =============================================================================
# HAUPTPROGRAMM
# =============================================================================
def print_help() -> None:
    """Zeigt die Hilfe an."""
    print("=" * 65)
    print("  WINDOWS AUTOCLICKER MIT SEQUENZ-UNTERSTÜTZUNG")
    print("=" * 65)
    print()
    print("Hotkeys:")
    print("  CTRL+ALT+A  - Mausposition als Punkt speichern")
    print("  CTRL+ALT+U  - Letzten Punkt entfernen")
    print("  CTRL+ALT+C  - Alle Punkte löschen")
    print("  CTRL+ALT+X  - FACTORY RESET (Punkte + Sequenzen)")
    print("  CTRL+ALT+E  - Sequenz-Editor (Punkte + Zeiten verknüpfen)")
    print("  CTRL+ALT+N  - Item-Scan Editor (Items erkennen + vergleichen)")
    print("  CTRL+ALT+L  - Gespeicherte Sequenz laden")
    print("  CTRL+ALT+P  - Punkte testen/anzeigen/umbenennen")
    print("  CTRL+ALT+T  - Farb-Analysator (für Bilderkennung)")
    print("  CTRL+ALT+S  - Start/Stop der aktiven Sequenz")
    print("  CTRL+ALT+G  - Pause/Resume (während Sequenz läuft)")
    print("  CTRL+ALT+K  - Skip (aktuelle Wartezeit überspringen)")
    print("  CTRL+ALT+W  - Quick-Switch (schnell Sequenz wechseln)")
    print("  CTRL+ALT+Z  - Zeitplan (Start zu bestimmter Zeit)")
    print("  CTRL+ALT+Q  - Programm beenden")
    print()
    print("So funktioniert's:")
    print("  1. Punkte aufnehmen (CTRL+ALT+A an verschiedenen Positionen)")
    print("  2. Sequenz erstellen (CTRL+ALT+E)")
    print("     - START-Phase: wird EINMAL ausgeführt")
    print("     - LOOP-Phase:  wird WIEDERHOLT")
    print("     - Trigger: Optional auf Screen warten (Bilderkennung)")
    print("  3. Sequenz starten (CTRL+ALT+S)")
    print()
    print("Bilderkennung:")
    print("  - Nutze CTRL+ALT+T um Farben zu analysieren")
    print("  - Item-Scan mit CTRL+ALT+N erstellen")
    print("  - Erfordert Pillow: pip install pillow")
    print()
    print(f"Daten: '{SEQUENCES_DIR}/' | Einstellungen: '{CONFIG_FILE}'")
    print("=" * 65)
    print()

def main() -> int:
    """Hauptfunktion."""
    print_help()

    state = AutoClickerState()
    state.config = CONFIG.copy()  # Kopie der globalen Config für thread-sicheren Zugriff
    main_thread_id = kernel32.GetCurrentThreadId()

    # Ordner erstellen
    ensure_sequences_dir()
    ensure_item_scans_dir()

    # Gespeicherte Daten laden
    load_points(state)
    load_global_slots(state)
    load_global_items(state)
    load_all_item_scans(state)

    # Hotkeys registrieren (zeigt nur Fehler an)
    if not register_hotkeys():
        logger.warning("Nicht alle Hotkeys registriert.")
        print()

    print("Bereit! Starte mit CTRL+ALT+A um Punkte aufzunehmen.")
    print_status(state)
    print()

    msg = wintypes.MSG()

    # Hotkey-Handler Zuordnung (ID → Funktion)
    hotkey_handlers = {
        HOTKEY_RECORD: handle_record,
        HOTKEY_UNDO: handle_undo,
        HOTKEY_CLEAR: handle_clear,
        HOTKEY_RESET: handle_reset,
        HOTKEY_EDITOR: handle_editor,
        HOTKEY_ITEM_SCAN: handle_item_scan_editor,
        HOTKEY_LOAD: handle_load,
        HOTKEY_SHOW: handle_show,
        HOTKEY_TOGGLE: handle_toggle,
        HOTKEY_PAUSE: handle_pause,
        HOTKEY_SKIP: handle_skip,
        HOTKEY_SWITCH: handle_switch,
        HOTKEY_SCHEDULE: handle_schedule,
        HOTKEY_ANALYZE: handle_analyze,
    }

    try:
        while not state.quit_event.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY:
                    hk_id = msg.wParam

                    if hk_id == HOTKEY_QUIT:
                        handle_quit(state, main_thread_id)
                        break
                    elif hk_id in hotkey_handlers:
                        hotkey_handlers[hk_id](state)
            else:
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[ABBRUCH] Programm wird beendet...")
        state.stop_event.set()
        state.quit_event.set()

    finally:
        unregister_hotkeys()
        print("\n[INFO] Hotkeys deregistriert.")
        time.sleep(0.2)
        print("[INFO] Programm beendet.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
