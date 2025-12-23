#!/usr/bin/env python3
"""
Windows Autoclicker mit Sequenz-Unterstützung - Python 3.13
============================================================
Ein Autoclicker für Windows 11 mit sequenzieller Ausführung und Speicherung.

Starten: python autoclicker.py
Beenden: CTRL+ALT+Q oder Konsole schließen

Hotkeys:
  CTRL+ALT+A  - Aktuelle Mausposition als Punkt speichern
  CTRL+ALT+U  - Letzten Punkt entfernen
  CTRL+ALT+E  - Sequenz-Editor öffnen (Punkte mit Zeiten verknüpfen)
  CTRL+ALT+N  - Item-Scan Editor (Items erkennen + vergleichen)
  CTRL+ALT+L  - Gespeicherte Sequenz laden
  CTRL+ALT+P  - Alle Punkte und Sequenzen anzeigen
  CTRL+ALT+T  - Farb-Analysator (für Bilderkennung)
  CTRL+ALT+S  - Start/Stop Toggle (führt aktive Sequenz aus)
  CTRL+ALT+Q  - Programm beenden

Sequenzen:
  - Eine Sequenz besteht aus Schritten (Punkt + Wartezeit danach)
  - Der gleiche Punkt kann mehrmals verwendet werden
  - Sequenzen werden in 'sequences/' gespeichert

Fail-Safe: Maus in obere linke Ecke bewegen (x<=2, y<=2) stoppt den Klicker.
"""

import ctypes
import ctypes.wintypes as wintypes
import threading
import time
import sys
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable
from pathlib import Path

# Bilderkennung (optional - nur wenn pillow installiert)
try:
    from PIL import Image, ImageGrab
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("[WARNUNG] Pillow nicht installiert. Bilderkennung deaktiviert.")
    print("          Installieren mit: pip install pillow")

# =============================================================================
# KONFIGURATION
# =============================================================================
CONFIG_FILE = "config.json"
SEQUENCES_DIR: str = "sequences"       # Ordner für gespeicherte Sequenzen

# Standard-Konfiguration (wird von config.json überschrieben)
DEFAULT_CONFIG = {
    "clicks_per_point": 1,              # Anzahl Klicks pro Punkt
    "max_total_clicks": None,           # None = unendlich
    "failsafe_enabled": True,           # Fail-Safe aktivieren
    "color_tolerance": 40,              # Farbtoleranz für Item-Scan (größer = toleranter)
    "pixel_wait_tolerance": 15,         # Toleranz für Pixel-Trigger (kleiner = genauer)
    "pixel_wait_timeout": 60,           # Timeout in Sekunden für Pixel-Trigger
    "pixel_check_interval": 0.5,        # Wie oft auf Farbe prüfen (in Sekunden, kleiner = öfter)
    "debug_detection": True,            # Debug-Ausgaben für Item-Erkennung
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
    """Speichert Konfiguration in config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"[FEHLER] Config konnte nicht gespeichert werden: {e}")

# Konfiguration laden
CONFIG = load_config()

# Konfig-Werte als Variablen (für einfacheren Zugriff)
CLICKS_PER_POINT: int = CONFIG["clicks_per_point"]
MAX_TOTAL_CLICKS: Optional[int] = CONFIG["max_total_clicks"]
FAILSAFE_ENABLED: bool = CONFIG["failsafe_enabled"]

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

# Window Messages
WM_HOTKEY = 0x0312

# Mouse Input
INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

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
    """Ein Klickpunkt mit x,y Koordinaten."""
    x: int
    y: int
    name: str = ""  # Optionaler Name für den Punkt

    def __str__(self) -> str:
        if self.name:
            return f"{self.name} ({self.x}, {self.y})"
        return f"({self.x}, {self.y})"

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
    # Optional: Item-Scan ausführen statt direktem Klick
    item_scan: Optional[str] = None      # Name des Item-Scans
    item_scan_mode: str = "best"         # "best" = nur bestes Item, "all" = alle Items
    # Optional: Nur warten, nicht klicken
    wait_only: bool = False              # True = nur warten, kein Klick

    def __str__(self) -> str:
        if self.item_scan:
            mode_str = "ALLE Items" if self.item_scan_mode == "all" else "bestes Item"
            return f"SCAN '{self.item_scan}' → klicke {mode_str}"
        if self.wait_only:
            if self.wait_pixel and self.wait_color:
                return f"WARTE auf Farbe bei ({self.wait_pixel[0]},{self.wait_pixel[1]}) (kein Klick)"
            return f"WARTE {self.delay_before}s (kein Klick)"
        pos_str = f"{self.name} ({self.x}, {self.y})" if self.name else f"({self.x}, {self.y})"
        if self.wait_pixel and self.wait_color:
            if self.delay_before > 0:
                return f"warte {self.delay_before}s, dann auf Farbe bei ({self.wait_pixel[0]},{self.wait_pixel[1]}) → klicke {pos_str}"
            return f"warte auf Farbe bei ({self.wait_pixel[0]},{self.wait_pixel[1]}) → klicke {pos_str}"
        elif self.delay_before > 0:
            return f"warte {self.delay_before}s → klicke {pos_str}"
        else:
            return f"sofort → klicke {pos_str}"

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
    """Eine Klick-Sequenz mit Start-Phase und mehreren Loop-Phasen."""
    name: str
    start_steps: list[SequenceStep] = field(default_factory=list)  # Einmalig am Anfang
    loop_phases: list[LoopPhase] = field(default_factory=list)     # Mehrere Loop-Phasen
    total_cycles: int = 1  # 0 = unendlich, >0 = wie oft alle Loops durchlaufen werden

    def __str__(self) -> str:
        start_count = len(self.start_steps)
        loop_info = f"{len(self.loop_phases)} Loop(s)"
        if self.total_cycles == 0:
            loop_info += " ∞"
        elif self.total_cycles == 1:
            loop_info += " (1x)"
        else:
            loop_info += f" (x{self.total_cycles})"
        # Zähle alle Schritte mit Farb-Trigger
        all_steps = self.start_steps + [s for lp in self.loop_phases for s in lp.steps]
        pixel_triggers = sum(1 for s in all_steps if s.wait_pixel)
        trigger_str = f" [Farb-Trigger: {pixel_triggers}]" if pixel_triggers > 0 else ""
        return f"{self.name} (Start: {start_count}, {loop_info}){trigger_str}"

    def total_steps(self) -> int:
        return len(self.start_steps) + sum(len(lp.steps) for lp in self.loop_phases)

# =============================================================================
# ITEM-SCAN SYSTEM (für Item-Erkennung und Vergleich)
# =============================================================================
ITEM_SCANS_DIR: str = "item_scans"  # Ordner für Item-Scan Konfigurationen

@dataclass
class ItemProfile:
    """Ein Item-Typ mit Marker-Farben und Priorität."""
    name: str
    marker_colors: list[tuple] = field(default_factory=list)  # Liste von (r,g,b) Marker-Farben
    priority: int = 99  # 1 = beste, höher = schlechter

    def __str__(self) -> str:
        colors_str = ", ".join([f"RGB{c}" for c in self.marker_colors[:3]])
        if len(self.marker_colors) > 3:
            colors_str += f" (+{len(self.marker_colors)-3})"
        return f"[P{self.priority}] {self.name}: {colors_str}"

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
    slots: list[ItemSlot] = field(default_factory=list)      # Wo gescannt wird (max 20)
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

    # Item-Scan Konfigurationen
    item_scans: dict[str, ItemScanConfig] = field(default_factory=dict)

    # Aktive Sequenz
    active_sequence: Optional[Sequence] = None

    # Laufzeit-Status
    is_running: bool = False
    total_clicks: int = 0
    current_step_index: int = 0

    # Editor-Modus
    editor_mode: bool = False
    temp_sequence: Optional[Sequence] = None

    # Thread-sichere Events
    stop_event: threading.Event = field(default_factory=threading.Event)
    quit_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

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

    # Punkte speichern
    points_data = [{"x": p.x, "y": p.y, "name": p.name} for p in state.points]
    with open(Path(SEQUENCES_DIR) / "points.json", "w", encoding="utf-8") as f:
        json.dump(points_data, f, indent=2, ensure_ascii=False)

    # Sequenzen speichern (mit Start + mehreren Loop-Phasen)
    def step_to_dict(s: SequenceStep) -> dict:
        return {"x": s.x, "y": s.y, "name": s.name, "delay_before": s.delay_before,
                "wait_pixel": s.wait_pixel, "wait_color": s.wait_color,
                "item_scan": s.item_scan, "item_scan_mode": s.item_scan_mode,
                "wait_only": s.wait_only}

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
            ]
        }
        filename = f"{name.replace(' ', '_').lower()}.json"
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
                state.points = [ClickPoint(p["x"], p["y"], p.get("name", "")) for p in data]
            print(f"[LOAD] {len(state.points)} Punkt(e) geladen")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"[WARNUNG] points.json konnte nicht geladen werden: {e}")
            print("[INFO] Starte mit leerer Punktliste.")
            state.points = []
    else:
        print("[INFO] Keine gespeicherten Punkte gefunden.")

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
                    delay = s.get("delay_before", s.get("delay_after", 0))
                    step = SequenceStep(
                        x=s.get("x", 0),
                        y=s.get("y", 0),
                        delay_before=delay,
                        name=s.get("name", ""),
                        wait_pixel=wait_pixel,
                        wait_color=wait_color,
                        item_scan=s.get("item_scan"),
                        item_scan_mode=s.get("item_scan_mode", "best"),
                        wait_only=s.get("wait_only", False)
                    )
                    steps.append(step)
                return steps

            start_steps = parse_steps(data.get("start_steps", []))

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
                return Sequence(data["name"], start_steps, loop_phases, total_cycles)

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
                return Sequence(data["name"], start_steps, loop_phases, total_cycles)

            # Uraltes Format (nur steps) - konvertieren
            elif "steps" in data:
                loop_steps = parse_steps(data["steps"])
                loop_phases = [LoopPhase("Loop 1", loop_steps, 1)] if loop_steps else []
                return Sequence(data["name"], [], loop_phases, 0)

            else:
                return Sequence(data["name"], [], [], 1)

    except Exception as e:
        print(f"[FEHLER] Konnte {filepath} nicht laden: {e}")
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
            except Exception:
                pass
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
                "marker_colors": [list(c) for c in item.marker_colors],
                "priority": item.priority
            }
            for item in config.items
        ]
    }

    filename = f"{config.name.replace(' ', '_').lower()}.json"
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
                item = ItemProfile(
                    name=i["name"],
                    marker_colors=[tuple(c) for c in i.get("marker_colors", [])],
                    priority=i.get("priority", 99)
                )
                items.append(item)

            return ItemScanConfig(
                name=data["name"],
                slots=slots,
                items=items,
                color_tolerance=data.get("color_tolerance", 40)
            )

    except Exception as e:
        print(f"[FEHLER] Konnte {filepath} nicht laden: {e}")
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
        except Exception:
            pass
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
# HILFSFUNKTIONEN
# =============================================================================
def get_cursor_pos() -> tuple[int, int]:
    """Liest die aktuelle Mausposition."""
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y

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

def check_failsafe() -> bool:
    """Prüft, ob die Maus in der Fail-Safe-Ecke ist."""
    if not FAILSAFE_ENABLED:
        return False
    x, y = get_cursor_pos()
    return x <= 2 and y <= 2

def clear_line() -> None:
    """Löscht die aktuelle Konsolenzeile."""
    print("\r" + " " * 80 + "\r", end="", flush=True)

# =============================================================================
# BILDERKENNUNG (Screen Detection)
# =============================================================================
# Farben für UI-Elemente (RGB) - Mehrere Varianten für bessere Erkennung
LOBBY_BUTTON_COLORS = [
    (46, 204, 113),    # Grün (Material Design)
    (39, 174, 96),     # Dunkleres Grün
    (88, 214, 141),    # Helleres Grün
    (46, 139, 87),     # Sea Green
    (60, 179, 113),    # Medium Sea Green
    (50, 205, 50),     # Lime Green
    (34, 139, 34),     # Forest Green
    (0, 128, 0),       # Pure Green
    (85, 239, 196),    # Mint/Türkis-Grün
    (0, 230, 118),     # Leuchtendes Grün
    (72, 201, 176),    # Medium Aquamarine
    (32, 178, 170),    # Light Sea Green
]
RAID_SCREEN_COLORS = [
    (38, 166, 154),    # Türkis (Material Teal)
    (0, 150, 136),     # Dunkleres Teal
    (77, 182, 172),    # Helleres Teal
    (0, 188, 212),     # Cyan
    (0, 172, 193),     # Dark Cyan
    (128, 203, 196),   # Light Teal
    (0, 128, 128),     # Pure Teal
    (32, 178, 170),    # Light Sea Green
]
# Toleranzen aus Config laden
COLOR_TOLERANCE = CONFIG["color_tolerance"]
PIXEL_WAIT_TOLERANCE = CONFIG["pixel_wait_tolerance"]
PIXEL_WAIT_TIMEOUT = CONFIG["pixel_wait_timeout"]
PIXEL_CHECK_INTERVAL = CONFIG["pixel_check_interval"]
DEBUG_DETECTION = CONFIG["debug_detection"]

def color_distance(c1: tuple, c2: tuple) -> float:
    """Berechnet die Distanz zwischen zwei RGB-Farben."""
    return ((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2) ** 0.5

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
    Unterstützt mehrere Monitore (auch negative Koordinaten für linke Monitore).
    """
    if not PILLOW_AVAILABLE:
        return None
    try:
        # all_screens=True ermöglicht Erfassung aller Monitore
        if region:
            # Bei Region: Erst alle Screens erfassen, dann zuschneiden
            full_screenshot = ImageGrab.grab(all_screens=True)
            # Koordinaten anpassen (all_screens verschiebt den Ursprung)
            # Hole die tatsächlichen Bildschirmgrenzen
            import ctypes
            SM_XVIRTUALSCREEN = 76
            SM_YVIRTUALSCREEN = 77
            x_offset = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            y_offset = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)

            # Region relativ zum virtuellen Desktop anpassen
            adjusted_region = (
                region[0] - x_offset,
                region[1] - y_offset,
                region[2] - x_offset,
                region[3] - y_offset
            )
            return full_screenshot.crop(adjusted_region)
        else:
            return ImageGrab.grab(all_screens=True)
    except Exception as e:
        print(f"[FEHLER] Screenshot fehlgeschlagen: {e}")
        return None

def count_color_pixels(image: 'Image.Image', target_color: tuple, tolerance: int = COLOR_TOLERANCE) -> int:
    """Zählt Pixel einer bestimmten Farbe im Bild."""
    if image is None:
        return 0
    count = 0
    pixels = image.load()
    width, height = image.size
    for x in range(width):
        for y in range(height):
            pixel = pixels[x, y][:3]  # RGB ohne Alpha
            if color_distance(pixel, target_color) <= tolerance:
                count += 1
    return count

def count_multi_color_pixels(image: 'Image.Image', target_colors: list, tolerance: int = COLOR_TOLERANCE) -> int:
    """Zählt Pixel die einer der Zielfarben entsprechen."""
    if image is None:
        return 0
    count = 0
    pixels = image.load()
    width, height = image.size
    for x in range(width):
        for y in range(height):
            pixel = pixels[x, y][:3]  # RGB ohne Alpha
            for target_color in target_colors:
                if color_distance(pixel, target_color) <= tolerance:
                    count += 1
                    break  # Zähle Pixel nur einmal
    return count

def analyze_screen_colors(region: tuple = None) -> dict:
    """
    Analysiert die häufigsten Farben in einem Screenshot.
    Nützlich um die richtigen Farben für die Erkennung zu finden.
    """
    if not PILLOW_AVAILABLE:
        print("[FEHLER] Pillow nicht installiert!")
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

def run_color_analyzer():
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
    print("\nAuswahl (oder 'abbruch'):")

    try:
        choice = input("> ").strip()

        if choice == "abbruch":
            return

        if choice == "1":
            # Farbe unter Mauszeiger
            print("\nBewege die Maus zur gewünschten Position und drücke Enter...")
            input()
            x, y = get_cursor_pos()

            img = take_screenshot((x, y, x+1, y+1))
            if img:
                pixel = img.getpixel((0, 0))[:3]
                print(f"\n[FARBE] Position ({x}, {y})")
                print(f"        RGB: {pixel}")
                print(f"        Hex: #{pixel[0]:02x}{pixel[1]:02x}{pixel[2]:02x}")

                # Prüfen ob ähnlich zu bekannten Farben
                for lobby_color in LOBBY_BUTTON_COLORS:
                    dist = color_distance(pixel, lobby_color)
                    if dist <= COLOR_TOLERANCE:
                        print(f"        → Ähnlich zu Lobby-Farbe {lobby_color} (Distanz: {dist:.1f})")
                        break
                for raid_color in RAID_SCREEN_COLORS:
                    dist = color_distance(pixel, raid_color)
                    if dist <= COLOR_TOLERANCE:
                        print(f"        → Ähnlich zu Raid-Farbe {raid_color} (Distanz: {dist:.1f})")
                        break

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

def analyze_and_print_colors(region: tuple = None):
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
    print("Tipp: Suche nach grünen Farben für Lobby-Button,")
    print("      türkise Farben für Raid-Screen!")

def detect_lobby_screen(region: tuple = None, min_pixels: int = 500) -> bool:
    """
    Erkennt ob die Lobby (Schlachtzug-Auswahl) sichtbar ist.
    Sucht nach dem grünen "Schlachtzug beginnen" Button.
    Verwendet mehrere Farbvarianten für bessere Erkennung.
    """
    if not PILLOW_AVAILABLE:
        return False

    img = take_screenshot(region)
    if img is None:
        return False

    green_pixels = count_multi_color_pixels(img, LOBBY_BUTTON_COLORS)
    detected = green_pixels >= min_pixels

    if DEBUG_DETECTION:
        if detected:
            print(f"[DETECT] Lobby erkannt! ({green_pixels} grüne Pixel)")
        else:
            print(f"[DEBUG] Lobby: {green_pixels} Pixel gefunden (benötigt: {min_pixels})")

    return detected

def detect_raid_screen(region: tuple = None, min_pixels: int = 1000) -> bool:
    """
    Erkennt ob der Raid-Bildschirm mit Aktivitäten sichtbar ist.
    Sucht nach den türkisen Aktivitäts-Icons.
    Verwendet mehrere Farbvarianten für bessere Erkennung.
    """
    if not PILLOW_AVAILABLE:
        return False

    img = take_screenshot(region)
    if img is None:
        return False

    teal_pixels = count_multi_color_pixels(img, RAID_SCREEN_COLORS)
    detected = teal_pixels >= min_pixels

    if DEBUG_DETECTION:
        if detected:
            print(f"[DETECT] Raid-Screen erkannt! ({teal_pixels} türkise Pixel)")
        else:
            print(f"[DEBUG] Raid: {teal_pixels} Pixel gefunden (benötigt: {min_pixels})")

    return detected

def detect_pixel_color(pixel_pos: tuple, target_colors: list, trigger_type: str) -> bool:
    """
    Prüft ob die Farbe an einer bestimmten Pixel-Position einer Zielfarbe entspricht.
    pixel_pos: (x, y) - Position auf dem Bildschirm
    target_colors: Liste von RGB-Farben die als Treffer gelten
    trigger_type: "lobby" oder "raid" für Debug-Ausgaben
    """
    if not PILLOW_AVAILABLE:
        return False

    x, y = pixel_pos
    # Screenshot von einem kleinen Bereich um den Pixel (für Toleranz)
    img = take_screenshot((x-2, y-2, x+3, y+3))
    if img is None:
        return False

    # Prüfe den mittleren Pixel und seine Nachbarn
    pixels = img.load()
    width, height = img.size

    for px in range(width):
        for py in range(height):
            pixel = pixels[px, py][:3]
            for target_color in target_colors:
                if color_distance(pixel, target_color) <= COLOR_TOLERANCE:
                    if DEBUG_DETECTION:
                        print(f"[DETECT] {trigger_type.upper()} erkannt! Pixel ({x},{y}) = RGB{pixel}")
                    return True

    if DEBUG_DETECTION:
        # Zeige die tatsächliche Farbe am Mittelpunkt
        center_pixel = pixels[width//2, height//2][:3]
        print(f"[DEBUG] {trigger_type}: Pixel ({x},{y}) = RGB{center_pixel} - nicht erkannt")

    return False

def select_pixel_position() -> Optional[tuple]:
    """
    Lässt den Benutzer eine Pixel-Position per Maus auswählen.
    Returns (x, y) oder None bei Abbruch.
    """
    print("\n  Bewege die Maus zur gewünschten Position")
    print("  (z.B. auf den grünen Button) und drücke Enter...")
    try:
        input()
        x, y = get_cursor_pos()
        print(f"  → Position: ({x}, {y})")

        # Zeige die Farbe an dieser Position
        img = take_screenshot((x, y, x+1, y+1))
        if img and PILLOW_AVAILABLE:
            pixel = img.getpixel((0, 0))[:3]
            print(f"  → Farbe: RGB{pixel}")

            # Prüfen ob es eine bekannte Farbe ist
            for lobby_color in LOBBY_BUTTON_COLORS:
                if color_distance(pixel, lobby_color) <= COLOR_TOLERANCE:
                    print(f"  → Erkannt als: LOBBY-Farbe (grün)")
                    break
            for raid_color in RAID_SCREEN_COLORS:
                if color_distance(pixel, raid_color) <= COLOR_TOLERANCE:
                    print(f"  → Erkannt als: RAID-Farbe (türkis)")
                    break

        return (x, y)

    except (KeyboardInterrupt, EOFError):
        print("\n  [ABBRUCH] Keine Position ausgewählt.")
        return None

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

        return (x1, y1, x2, y2)

    except (KeyboardInterrupt, EOFError):
        print("\n  [ABBRUCH] Keine Region ausgewählt.")
        return None

def wait_for_screen(detect_func: Callable, timeout: float = 60, check_interval: float = 1.0,
                    stop_event: threading.Event = None) -> bool:
    """
    Wartet bis ein bestimmter Screen erkannt wird.
    Returns True wenn erkannt, False bei Timeout oder Stop.
    """
    start_time = time.time()

    while True:
        if stop_event and stop_event.is_set():
            return False

        if detect_func():
            return True

        elapsed = time.time() - start_time
        if elapsed >= timeout:
            print(f"[TIMEOUT] Screen nicht erkannt nach {timeout}s")
            return False

        clear_line()
        print(f"[WARTE] Suche Screen... ({elapsed:.0f}s/{timeout}s)", end="", flush=True)

        if stop_event:
            stop_event.wait(check_interval)
        else:
            time.sleep(check_interval)

def print_status(state: AutoClickerState) -> None:
    """Gibt den aktuellen Status aus."""
    with state.lock:
        if state.editor_mode:
            status = "EDITOR"
        elif state.is_running:
            status = "RUNNING"
        else:
            status = "STOPPED"

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
            for i, p in enumerate(state.points):
                print(f"  P{i+1}: {p}")

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
# ITEM-SCAN EDITOR
# =============================================================================
def run_item_scan_editor(state: AutoClickerState) -> None:
    """Interaktiver Editor für Item-Scan Konfigurationen."""
    print("\n" + "=" * 60)
    print("  ITEM-SCAN EDITOR")
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

    print("\nAuswahl (oder 'abbruch'):")

    while True:
        try:
            choice = input("> ").strip().lower()

            if choice == "abbruch":
                print("[ABBRUCH] Editor beendet.")
                return

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
    """Bearbeitet eine Item-Scan Konfiguration."""

    if existing:
        print(f"\n--- Bearbeite Item-Scan: {existing.name} ---")
        scan_name = existing.name
        slots = list(existing.slots)
        items = list(existing.items)
        tolerance = existing.color_tolerance
    else:
        print("\n--- Neuen Item-Scan erstellen ---")
        scan_name = input("Name des Item-Scans: ").strip()
        if not scan_name:
            scan_name = f"ItemScan_{int(time.time())}"
        slots = []
        items = []
        tolerance = 40

    # Schritt 1: Slots definieren
    print("\n" + "=" * 60)
    print("  SCHRITT 1: SLOTS DEFINIEREN (wo Items erscheinen)")
    print("=" * 60)
    slots = edit_item_slots(slots)

    if not slots:
        print("\n[FEHLER] Mindestens 1 Slot erforderlich!")
        return

    # Schritt 2: Item-Profile definieren (optional)
    print("\n" + "=" * 60)
    print("  SCHRITT 2: ITEM-PROFILE DEFINIEREN (was erkannt wird)")
    print("=" * 60)
    print("  (Optional - du kannst Items auch später hinzufügen)")
    items = edit_item_profiles(items, slots)

    if not items:
        print("\n[INFO] Keine Item-Profile definiert.")
        save_anyway = input("Trotzdem speichern? (j/n): ").strip().lower()
        if save_anyway != "j":
            print("[ABBRUCH] Item-Scan nicht gespeichert.")
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

    print(f"\n[ERFOLG] Item-Scan '{scan_name}' gespeichert!")
    print(f"         {len(slots)} Slots, {len(items)} Item-Profile")
    print(f"         Nutze im Sequenz-Editor: '<Nr> scan {scan_name}'")


def edit_item_slots(slots: list[ItemSlot]) -> list[ItemSlot]:
    """Bearbeitet die Slot-Liste für einen Item-Scan."""

    if slots:
        print(f"\nAktuelle Slots ({len(slots)}):")
        for i, slot in enumerate(slots):
            print(f"  {i+1}. {slot}")

    print("\n" + "-" * 60)
    print("Befehle:")
    print("  add      - Neuen Slot hinzufügen (Region + Klickpunkt)")
    print("  del <Nr> - Slot löschen")
    print("  show     - Alle Slots anzeigen")
    print("  fertig   - Slots abschließen")
    print("-" * 60)

    while True:
        try:
            prompt = f"[SLOTS: {len(slots)}/20]"
            user_input = input(f"{prompt} > ").strip().lower()

            if user_input == "fertig":
                return slots
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
                if len(slots) >= 20:
                    print("  → Maximum 20 Slots erreicht!")
                    continue

                slot_num = len(slots) + 1
                slot_name = input(f"  Slot-Name (Enter = 'Slot {slot_num}'): ").strip()
                if not slot_name:
                    slot_name = f"Slot {slot_num}"

                # Scan-Region auswählen
                print("\n  Scan-Region definieren (Bereich wo das Item angezeigt wird):")
                region = select_region()
                if not region:
                    print("  → Abbruch")
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
                    sorted_colors = sorted(color_counts.items(), key=lambda c: c[1], reverse=True)[:5]
                    print(f"  Top 5 Farben in {slot_name}:")
                    for i, (color, count) in enumerate(sorted_colors):
                        color_name = get_color_name(color)
                        print(f"    {i+1}. RGB{color} - {color_name} ({count} Pixel)")

                # Slot-Hintergrundfarbe (wird bei Items ausgeschlossen)
                slot_color = None
                print("\n  Hintergrundfarbe des leeren Slots markieren:")
                print("  (Diese Farbe wird bei Item-Erkennung ignoriert)")
                print("  Bewege Maus auf den Slot-Hintergrund, Enter (oder Enter = überspringen)...")
                bg_input = input().strip()
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
                print("  Bewege die Maus zur Klick-Position und drücke Enter...")
                input()
                click_x, click_y = get_cursor_pos()
                print(f"  → Klick-Position: ({click_x}, {click_y})")

                slot = ItemSlot(slot_name, region, (click_x, click_y), slot_color)
                slots.append(slot)
                print(f"  ✓ {slot_name} hinzugefügt")
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
    print("  add       - Neues Item-Profil erstellen")
    print("  edit <Nr> - Item-Profil bearbeiten")
    print("  del <Nr>  - Item-Profil löschen")
    print("  show      - Alle Profile anzeigen")
    print("  fertig    - Profile abschließen")
    print("-" * 60)

    while True:
        try:
            prompt = f"[ITEMS: {len(items)}]"
            user_input = input(f"{prompt} > ").strip().lower()

            if user_input == "fertig":
                # Entferne Farben die bei allen Items gleich sind (Hintergrund)
                items = remove_common_colors(items)
                return items
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
                item_name = input("  Item-Name (z.B. 'Legendary', 'Epic'): ").strip()
                if not item_name:
                    print("  → Name erforderlich!")
                    continue

                # Priorität
                priority = len(items) + 1
                try:
                    prio_input = input(f"  Priorität (1=beste, Enter={priority}): ").strip()
                    if prio_input:
                        priority = max(1, int(prio_input))
                except ValueError:
                    pass

                # Marker-Farben aus Slot scannen
                if slots:
                    print(f"\n  Lege das Item in einen Slot und gib die Slot-Nr ein (1-{len(slots)}):")
                    try:
                        slot_input = input("  Slot-Nr: ").strip()
                        slot_num = int(slot_input)
                        if slot_num < 1 or slot_num > len(slots):
                            print(f"  → Ungültiger Slot! Verfügbar: 1-{len(slots)}")
                            continue
                        selected_slot = slots[slot_num - 1]
                        marker_colors = collect_marker_colors(selected_slot.scan_region, selected_slot.slot_color)
                    except ValueError:
                        print("  → Bitte eine Nummer eingeben!")
                        continue
                else:
                    # Fallback: Manuell Region auswählen
                    print("\n  Marker-Farben für dieses Item sammeln:")
                    marker_colors = collect_marker_colors()

                if not marker_colors:
                    print("  → Keine Farben gefunden!")
                    continue

                item = ItemProfile(item_name, marker_colors, priority)
                items.append(item)
                print(f"  ✓ {item_name} hinzugefügt mit {len(marker_colors)} Marker-Farben")
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

                        print(f"  ✓ {item.name} aktualisiert")
                    else:
                        print(f"  → Ungültiges Item! Verfügbar: 1-{len(items)}")
                except ValueError:
                    print("  → Format: edit <Nr>")
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
    if exclude_color and exclude_color in color_counts:
        excluded_count = color_counts.pop(exclude_color)
        color_name = get_color_name(exclude_color)
        print(f"  → Slot-Hintergrund RGB{exclude_color} ({color_name}) ausgeschlossen ({excluded_count} Pixel)")

    # Top 5 häufigste Farben
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    colors = [color for color, count in sorted_colors]

    print(f"\n  Top 5 Farben gefunden:")
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
def execute_item_scan(state: AutoClickerState, scan_name: str, mode: str = "best") -> list[tuple]:
    """
    Führt einen Item-Scan aus.
    mode="best": Gibt nur die Klick-Position des besten Items zurück
    mode="all": Gibt alle Klick-Positionen mit erkannten Items zurück
    Returns Liste von (x, y) Positionen (leer wenn nichts gefunden)
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

    mode_str = "ALLE" if mode == "all" else "BESTES"
    print(f"\n[SCAN] Scanne {len(config.slots)} Slots für '{scan_name}' (Modus: {mode_str})...")

    for slot in config.slots:
        # Screenshot der Scan-Region
        img = take_screenshot(slot.scan_region)
        if img is None:
            continue

        pixels = img.load()
        width, height = img.size

        # Prüfe alle Item-Profile für diesen Slot
        slot_best_item = None
        slot_best_priority = 999

        for item in config.items:
            # Prüfe ob Marker-Farben vorhanden sind
            markers_found = 0

            for marker_color in item.marker_colors:
                color_found = False
                # Suche nach dieser Marker-Farbe im Bild
                for x in range(0, width, 2):  # Jeden 2. Pixel für Geschwindigkeit
                    if color_found:
                        break
                    for y in range(0, height, 2):
                        pixel = pixels[x, y][:3]
                        if color_distance(pixel, marker_color) <= config.color_tolerance:
                            color_found = True
                            break

                if color_found:
                    markers_found += 1

            # Item erkannt wenn mindestens 1 Marker-Farbe gefunden
            if markers_found >= 1:
                print(f"  → {slot.name}: {item.name} erkannt (P{item.priority}, {markers_found}/{len(item.marker_colors)} Marker)")
                if item.priority < slot_best_priority:
                    slot_best_priority = item.priority
                    slot_best_item = item

        # Merke das beste Item für diesen Slot
        if slot_best_item:
            found_items.append((slot, slot_best_item, slot_best_priority))

    if not found_items:
        print("[SCAN] Kein Item erkannt.")
        return []

    if mode == "all":
        # Alle gefundenen Slots zurückgeben
        print(f"[SCAN] {len(found_items)} Items gefunden - klicke alle!")
        return [slot.click_pos for slot, item, priority in found_items]
    else:
        # Nur das beste Item zurückgeben
        found_items.sort(key=lambda x: x[2])  # Nach Priorität sortieren
        best_slot, best_item, best_priority = found_items[0]
        print(f"[SCAN] Bestes Item: {best_item.name} in {best_slot.name} (P{best_priority})")
        return [best_slot.click_pos]


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

    print("\nAuswahl (oder 'abbruch'):")

    while True:
        try:
            choice = input("> ").strip().lower()

            if choice == "abbruch":
                print("[ABBRUCH] Editor beendet.")
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
        total_cycles = existing.total_cycles
    else:
        print("\n--- Neue Sequenz erstellen ---")
        seq_name = input("Name der Sequenz: ").strip()
        if not seq_name:
            seq_name = f"Sequenz_{int(time.time())}"
        start_steps = []
        loop_phases = []
        total_cycles = 1

    # Verfügbare Punkte anzeigen
    with state.lock:
        print("\nVerfügbare Punkte:")
        for i, p in enumerate(state.points):
            print(f"  P{i+1}: {p}")

    # Erst START-Phase bearbeiten
    print("\n" + "=" * 60)
    print("  PHASE 1: START-SEQUENZ (wird einmal pro Zyklus ausgeführt)")
    print("=" * 60)
    start_steps = edit_phase(state, start_steps, "START")

    # Dann LOOP-Phasen bearbeiten (mehrere möglich)
    print("\n" + "=" * 60)
    print("  PHASE 2: LOOP-PHASEN (können mehrere sein)")
    print("=" * 60)
    loop_phases = edit_loop_phases(state, loop_phases)

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

    # Sequenz erstellen und speichern
    new_sequence = Sequence(
        name=seq_name,
        start_steps=start_steps,
        loop_phases=loop_phases,
        total_cycles=total_cycles
    )

    with state.lock:
        state.sequences[seq_name] = new_sequence
        state.active_sequence = new_sequence

    save_data(state)

    # Zusammenfassung
    all_steps = start_steps + [s for lp in loop_phases for s in lp.steps]
    pixel_triggers = sum(1 for s in all_steps if s.wait_pixel)

    print(f"\n[ERFOLG] Sequenz '{seq_name}' gespeichert!")
    print(f"         Start: {len(start_steps)} Schritte (einmal pro Zyklus)")
    for i, lp in enumerate(loop_phases):
        print(f"         {lp.name}: {len(lp.steps)} Schritte x{lp.repeat}")
    if total_cycles == 0:
        print(f"         Gesamt: Unendlich wiederholen")
    elif total_cycles == 1:
        print(f"         Gesamt: Einmal durchlaufen")
    else:
        print(f"         Gesamt: {total_cycles}x wiederholen")
    if pixel_triggers > 0:
        print(f"         Farb-Trigger: {pixel_triggers} Schritt(e)")
    print("         Drücke CTRL+ALT+S zum Starten.\n")


def edit_loop_phases(state: AutoClickerState, loop_phases: list[LoopPhase]) -> list[LoopPhase]:
    """Bearbeitet mehrere Loop-Phasen."""

    if loop_phases:
        print(f"\nAktuelle Loop-Phasen ({len(loop_phases)}):")
        for i, lp in enumerate(loop_phases):
            print(f"  {i+1}. {lp}")

    print("\n" + "-" * 60)
    print("Befehle:")
    print("  add        - Neue Loop-Phase hinzufügen")
    print("  edit <Nr>  - Loop-Phase bearbeiten (z.B. 'edit 1')")
    print("  del <Nr>   - Loop-Phase löschen")
    print("  show       - Alle Loop-Phasen anzeigen")
    print("  fertig     - Loop-Phasen abschließen")
    print("-" * 60)

    while True:
        try:
            prompt = f"[LOOPS: {len(loop_phases)}]"
            user_input = input(f"{prompt} > ").strip().lower()

            if user_input == "fertig":
                return loop_phases
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
                        lp.steps = edit_phase(state, lp.steps, lp.name)
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
                print("  → Unbekannter Befehl. Nutze: add, edit <Nr>, del <Nr>, show, fertig")

        except (KeyboardInterrupt, EOFError):
            raise


def edit_phase(state: AutoClickerState, steps: list[SequenceStep], phase_name: str) -> list[SequenceStep]:
    """Bearbeitet eine Phase (Start oder Loop) der Sequenz."""

    if steps:
        print(f"\nAktuelle {phase_name}-Schritte ({len(steps)}):")
        for i, step in enumerate(steps):
            print(f"  {i+1}. {step}")

    print("\n" + "-" * 60)
    print("Befehle (Logik: erst warten, DANN klicken):")
    print("  <Nr> <Zeit>       - Warte Xs, dann klicke (z.B. '1 30')")
    print("  <Nr> 0            - Sofort klicken")
    print("  <Nr> pixel        - Warte auf Farbe, dann klicke")
    print("  <Nr> <Zeit> pixel - Erst Xs warten, dann auf Farbe (z.B. '1 30 pixel')")
    print("  wait <Zeit>       - Nur warten, KEIN Klick (z.B. 'wait 10')")
    print("  wait pixel        - Auf Farbe warten, KEIN Klick")
    print("  scan <Name>       - Item-Scan: klicke BESTES Item")
    print("  scan <Name> all   - Item-Scan: klicke ALLE Items")
    print("  del <Nr>          - Schritt löschen")
    print("  clear / show / fertig / abbruch")
    print("-" * 60)

    while True:
        try:
            prompt = f"[{phase_name}: {len(steps)}]"
            user_input = input(f"{prompt} > ").strip()

            if user_input.lower() == "fertig":
                return steps
            elif user_input.lower() == "abbruch":
                print("[ABBRUCH] Sequenz nicht gespeichert.")
                raise KeyboardInterrupt
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
            elif user_input.lower() == "clear":
                steps.clear()
                print("  ✓ Alle Schritte gelöscht")
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

            elif user_input.lower().startswith("scan "):
                # Item-Scan Schritt hinzufügen
                # Format: "scan <Name>" oder "scan <Name> all"
                scan_parts = user_input[5:].strip().split()
                if not scan_parts:
                    print("  → Format: scan <Name> [all]")
                    continue

                scan_name = scan_parts[0]
                scan_mode = "best"  # Standard: nur bestes Item
                if len(scan_parts) > 1 and scan_parts[1].lower() == "all":
                    scan_mode = "all"

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
                mode_str = "alle" if scan_mode == "all" else "bestes"
                step = SequenceStep(x=0, y=0, delay_before=0, name=f"Scan:{scan_name}",
                                   item_scan=scan_name, item_scan_mode=scan_mode)
                steps.append(step)
                print(f"  ✓ Hinzugefügt: {step}")
                continue

            elif user_input.lower().startswith("wait "):
                # Nur warten, kein Klick
                # Format: "wait <Zeit>" oder "wait pixel"
                wait_parts = user_input[5:].strip().split()
                if not wait_parts:
                    print("  → Format: wait <Sekunden> | wait pixel")
                    continue

                if wait_parts[0].lower() == "pixel":
                    # Auf Farbe warten ohne Klick
                    print("\n  Farb-Trigger einrichten (ohne Klick):")
                    print("  Bewege die Maus zur Position wo die Farbe geprüft werden soll")
                    print("  Drücke Enter...")
                    input()
                    px, py = get_cursor_pos()
                    print(f"  → Position: ({px}, {py})")

                    if PILLOW_AVAILABLE:
                        img = take_screenshot((px, py, px+1, py+1))
                        if img:
                            color = img.getpixel((0, 0))[:3]
                            color_name = get_color_name(color)
                            print(f"  → Warte auf Farbe: RGB{color} ({color_name})")
                            step = SequenceStep(
                                x=0, y=0, delay_before=0, name="Wait-Pixel",
                                wait_pixel=(px, py), wait_color=color, wait_only=True
                            )
                            steps.append(step)
                            print(f"  ✓ Hinzugefügt: {step}")
                        else:
                            print("  → Fehler: Konnte Farbe nicht lesen!")
                    else:
                        print("  → Fehler: Pillow nicht installiert!")
                else:
                    # Zeit warten ohne Klick
                    try:
                        wait_time = float(wait_parts[0])
                        if wait_time < 0:
                            print("  → Wartezeit muss >= 0 sein!")
                            continue
                        step = SequenceStep(x=0, y=0, delay_before=wait_time, name="Wait", wait_only=True)
                        steps.append(step)
                        print(f"  ✓ Hinzugefügt: {step}")
                    except ValueError:
                        print("  → Format: wait <Sekunden> | wait pixel")
                continue

            # Neuen Schritt hinzufügen (Punkt + Zeit oder Pixel)
            parts = user_input.split()
            if len(parts) < 2 or len(parts) > 3:
                print("  → Format: <Nr> <Sek> | <Nr> pixel | <Nr> <Sek> pixel")
                continue

            point_num = int(parts[0])

            with state.lock:
                if point_num < 1 or point_num > len(state.points):
                    print(f"  → Ungültiger Punkt! Verfügbar: 1-{len(state.points)}")
                    continue
                point = state.points[point_num - 1]
                point_x = point.x
                point_y = point.y
                point_name = point.name

            # Format: <Nr> pixel (sofort auf Farbe warten)
            # Format: <Nr> <Sek> pixel (erst warten, dann auf Farbe)
            # Format: <Nr> <Sek> (nur Zeit warten)
            use_pixel = "pixel" in [p.lower() for p in parts]
            delay = 0

            if use_pixel:
                # Delay ermitteln falls angegeben
                if len(parts) == 3:
                    delay = float(parts[1])
                    if delay < 0:
                        print("  → Wartezeit muss >= 0 sein!")
                        continue

                # Pixel-basierte Wartezeit (optional mit Delay davor)
                print("\n  Farb-Trigger einrichten:")
                print("  Bewege die Maus zur Position wo die Farbe geprüft werden soll")
                if delay > 0:
                    print(f"  (Erst {delay}s warten, dann auf Farbe prüfen)")
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
                        print(f"  → Gespeicherte Farbe: RGB{color} ({color_name})")
                        print(f"  → Wenn diese Farbe erscheint → klicke auf {point_name}")
                        step = SequenceStep(
                            x=point_x, y=point_y, delay_before=delay, name=point_name,
                            wait_pixel=(px, py), wait_color=color
                        )
                        steps.append(step)
                        print(f"  ✓ Hinzugefügt: {step}")
                    else:
                        print("  → Fehler: Konnte Farbe nicht lesen!")
                else:
                    print("  → Fehler: Pillow nicht installiert! (pip install pillow)")
            else:
                # Zeit-basierte Wartezeit (warte X Sekunden, dann klicke)
                delay = float(parts[1])
                if delay < 0:
                    print("  → Wartezeit muss >= 0 sein!")
                    continue

                step = SequenceStep(x=point_x, y=point_y, delay_before=delay, name=point_name)
                steps.append(step)
                print(f"  ✓ Hinzugefügt: {step}")

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

    print("\nNummer eingeben (oder 'abbruch'):")

    while True:
        try:
            user_input = input("> ").strip().lower()

            if user_input == "abbruch":
                print("[ABBRUCH] Keine Sequenz geladen.")
                return

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
def execute_step(state: AutoClickerState, step: SequenceStep, step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen einzelnen Schritt aus: Erst warten/prüfen, DANN klicken. Gibt False zurück wenn abgebrochen."""

    # Fail-Safe prüfen
    if check_failsafe():
        print("\n[FAILSAFE] Maus in Ecke erkannt! Stoppe...")
        state.stop_event.set()
        return False

    # === SONDERFALL: Item-Scan Schritt ===
    if step.item_scan:
        mode = step.item_scan_mode
        mode_str = "alle" if mode == "all" else "bestes"
        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | Scan '{step.item_scan}' ({mode_str})...", end="", flush=True)

        click_positions = execute_item_scan(state, step.item_scan, mode)
        if click_positions:
            # Klicke alle gefundenen Positionen
            for i, pos in enumerate(click_positions):
                if state.stop_event.is_set():
                    return False
                send_click(pos[0], pos[1])
                with state.lock:
                    state.total_clicks += 1
                # Kurze Pause zwischen Klicks
                if i < len(click_positions) - 1:
                    time.sleep(0.2)
            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | {len(click_positions)} Scan-Klick(s)! (Gesamt: {state.total_clicks})", end="", flush=True)
        else:
            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | Scan: kein Item gefunden", end="", flush=True)
        return True

    # === PHASE 1: Warten VOR dem Klick (Zeit oder Farbe) ===
    if step.wait_pixel and step.wait_color:
        # Optional: Erst delay_before warten, dann auf Farbe prüfen
        if step.delay_before > 0:
            remaining = step.delay_before
            while remaining > 0 and not state.stop_event.is_set():
                clear_line()
                print(f"[{phase}] Schritt {step_num}/{total_steps} | Warte {remaining:.0f}s vor Farbprüfung...", end="", flush=True)
                wait_time = min(1.0, remaining)
                if state.stop_event.wait(wait_time):
                    return False
                remaining -= wait_time

        # Warten auf Farbe an Pixel-Position
        timeout = PIXEL_WAIT_TIMEOUT  # Aus Config
        start_time = time.time()
        while not state.stop_event.is_set():
            # Prüfe Farbe
            if PILLOW_AVAILABLE:
                img = take_screenshot((step.wait_pixel[0], step.wait_pixel[1],
                                      step.wait_pixel[0]+1, step.wait_pixel[1]+1))
                if img:
                    current_color = img.getpixel((0, 0))[:3]
                    if color_distance(current_color, step.wait_color) <= PIXEL_WAIT_TOLERANCE:
                        clear_line()
                        if step.wait_only:
                            print(f"[{phase}] Schritt {step_num}/{total_steps} | Farbe erkannt!", end="", flush=True)
                        else:
                            print(f"[{phase}] Schritt {step_num}/{total_steps} | Farbe erkannt! Klicke...", end="", flush=True)
                        break

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                print(f"\n[TIMEOUT] Farbe nicht erkannt nach {timeout}s - Sequenz gestoppt!")
                state.stop_event.set()  # Stoppt die ganze Sequenz
                return False

            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | Warte auf Farbe... ({elapsed:.1f}s)", end="", flush=True)

            if state.stop_event.wait(PIXEL_CHECK_INTERVAL):
                return False

    elif step.delay_before > 0:
        # Zeit-basierte Wartezeit VOR dem Klick
        remaining = step.delay_before
        while remaining > 0 and not state.stop_event.is_set():
            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | Klicke in {remaining:.0f}s...", end="", flush=True)
            wait_time = min(1.0, remaining)
            if state.stop_event.wait(wait_time):
                return False
            remaining -= wait_time

    if state.stop_event.is_set():
        return False

    # === SONDERFALL: Nur warten, kein Klick ===
    if step.wait_only:
        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | Warten beendet (kein Klick)", end="", flush=True)
        return True

    # === PHASE 2: Klick ausführen ===
    for _ in range(CLICKS_PER_POINT):
        if state.stop_event.is_set():
            return False

        if check_failsafe():
            print("\n[FAILSAFE] Stoppe...")
            state.stop_event.set()
            return False

        send_click(step.x, step.y)

        with state.lock:
            state.total_clicks += 1

        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | Klick! (Gesamt: {state.total_clicks})", end="", flush=True)

        if MAX_TOTAL_CLICKS and state.total_clicks >= MAX_TOTAL_CLICKS:
            print(f"\n[INFO] Maximum von {MAX_TOTAL_CLICKS} Klicks erreicht.")
            state.stop_event.set()
            return False

    return True


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
        total_cycles = sequence.total_cycles

        if not has_start and not has_loops:
            print("[FEHLER] Sequenz ist leer!")
            state.is_running = False
            return

    cycle_count = 0

    # Äußere Schleife für Zyklen (START → alle Loops → START → alle Loops → ...)
    while not state.stop_event.is_set() and not state.quit_event.is_set():
        cycle_count += 1

        # Prüfen ob max Zyklen erreicht (0 = unendlich)
        if total_cycles > 0 and cycle_count > total_cycles:
            print(f"\n[FERTIG] Alle {total_cycles} Zyklen abgeschlossen!")
            break

        # === PHASE 1: START-SEQUENZ ===
        if has_start and not state.stop_event.is_set():
            if cycle_count == 1:
                print("\n[START] Führe Start-Sequenz aus...")
            else:
                print(f"\n[ZYKLUS #{cycle_count}] Starte erneut...")
            total_start = len(sequence.start_steps)

            for i, step in enumerate(sequence.start_steps):
                if state.stop_event.is_set() or state.quit_event.is_set():
                    break
                if not execute_step(state, step, i + 1, total_start, "START"):
                    break

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

                print(f"\n[{loop_phase.name}] Starte ({loop_phase.repeat}x)...")

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

                if not state.stop_event.is_set():
                    print(f"\n[{loop_phase.name}] Abgeschlossen.")

            if state.stop_event.is_set():
                break

        # Wenn keine Loops oder total_cycles==1 → nach einem Durchlauf fertig
        if not has_loops or total_cycles == 1:
            print("\n[FERTIG] Sequenz einmal durchgelaufen.")
            break

    with state.lock:
        state.is_running = False

    print("\n[WORKER] Sequenz gestoppt.")
    print_status(state)

# =============================================================================
# HOTKEY HANDLER
# =============================================================================
def handle_record(state: AutoClickerState) -> None:
    """Nimmt die aktuelle Mausposition auf - sofort ohne Eingabe."""
    x, y = get_cursor_pos()

    with state.lock:
        count = len(state.points) + 1
        name = f"P{count}"
        point = ClickPoint(x, y, name)
        state.points.append(point)

    # Auto-speichern
    save_data(state)

    print(f"\n[RECORD] {name} hinzugefügt: ({x}, {y})")
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
    """Löscht ALLES - Punkte UND Sequenzen (Factory Reset)."""
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
    print("\nBist du sicher? Tippe 'JA' zum Bestätigen:")

    try:
        confirm = input("> ").strip()
        if confirm != "JA":
            print("[ABBRUCH] Nichts wurde gelöscht.")
            return

        # Punkte löschen
        with state.lock:
            state.points.clear()
            state.sequences.clear()
            state.active_sequence = None

        # Alle Dateien im Sequenz-Ordner löschen
        seq_dir = Path(SEQUENCES_DIR)
        if seq_dir.exists():
            import shutil
            shutil.rmtree(seq_dir)
        ensure_sequences_dir()

        print("\n[RESET] ✓ Alles wurde gelöscht!")
        print("[RESET] Das Programm ist jetzt wie neu.")
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
    """Öffnet den Item-Scan Editor."""
    with state.lock:
        if state.is_running:
            print("\n[FEHLER] Stoppe zuerst den Klicker (CTRL+ALT+S)!")
            return
    run_item_scan_editor(state)

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
    print("  Enter       - Zurück")
    print("-" * 50)

    while True:
        try:
            user_input = input("> ").strip()
            if not user_input:
                return

            parts = user_input.split(maxsplit=1)
            point_num = int(parts[0])

            with state.lock:
                if point_num < 1 or point_num > num_points:
                    print(f"[FEHLER] Ungültiger Punkt! Verfügbar: 1-{num_points}")
                    continue

                point = state.points[point_num - 1]

            if len(parts) == 1:
                # Nur Nummer → Testen (Maus hinbewegen)
                print(f"[TEST] Bewege Maus zu {point.name} ({point.x}, {point.y})...")
                set_cursor_pos(point.x, point.y)
                print(f"[TEST] Maus ist jetzt bei {point.name}. Neuer Name? (Enter = behalten)")

                new_name = input("> ").strip()
                if new_name:
                    with state.lock:
                        state.points[point_num - 1].name = new_name
                    save_data(state)
                    print(f"[OK] Punkt {point_num} umbenannt zu '{new_name}'")
                else:
                    print(f"[OK] Name '{point.name}' beibehalten.")

            else:
                # Nummer + Name → Direkt umbenennen
                new_name = parts[1]
                with state.lock:
                    state.points[point_num - 1].name = new_name
                save_data(state)
                print(f"[OK] Punkt {point_num} umbenannt zu '{new_name}'")

        except ValueError:
            print("[FEHLER] Ungültige Eingabe!")
        except (KeyboardInterrupt, EOFError):
            return

def handle_toggle(state: AutoClickerState) -> None:
    """Startet oder stoppt die Sequenz."""
    with state.lock:
        if state.is_running:
            state.stop_event.set()
            print("\n[TOGGLE] Stoppe Sequenz...")
        else:
            if not state.active_sequence:
                print("\n[FEHLER] Keine Sequenz geladen!")
                print("         Erstelle eine mit CTRL+ALT+E oder lade eine mit CTRL+ALT+L")
                return

            if not state.points:
                print("\n[FEHLER] Keine Punkte gespeichert!")
                return

            state.is_running = True
            state.stop_event.clear()
            state.current_step_index = 0

            worker = threading.Thread(target=sequence_worker, args=(state,), daemon=True)
            worker.start()

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
        (HOTKEY_ANALYZE, VK_T, "CTRL+ALT+T (Farb-Analysator)"),
        (HOTKEY_QUIT, VK_Q, "CTRL+ALT+Q (Beenden)"),
    ]

    success = True
    for hk_id, vk, name in hotkeys:
        if not user32.RegisterHotKey(None, hk_id, modifiers, vk):
            print(f"[FEHLER] Hotkey nicht registriert: {name}")
            success = False
        else:
            print(f"  ✓ {name}")

    return success

def unregister_hotkeys() -> None:
    """Deregistriert alle Hotkeys."""
    for hk_id in [HOTKEY_RECORD, HOTKEY_UNDO, HOTKEY_CLEAR, HOTKEY_RESET,
                  HOTKEY_EDITOR, HOTKEY_ITEM_SCAN, HOTKEY_LOAD, HOTKEY_SHOW,
                  HOTKEY_TOGGLE, HOTKEY_ANALYZE, HOTKEY_QUIT]:
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
    print("  - Nutze CTRL+ALT+T um Farben im Spiel zu analysieren")
    print("  - Erfordert Pillow: pip install pillow")
    print()
    print(f"Sequenzen werden in '{SEQUENCES_DIR}/' gespeichert.")
    print("=" * 65)
    print()

def main() -> int:
    """Hauptfunktion."""
    print_help()

    state = AutoClickerState()
    main_thread_id = kernel32.GetCurrentThreadId()

    # Ordner erstellen
    ensure_sequences_dir()
    ensure_item_scans_dir()

    # Gespeicherte Punkte und Item-Scans laden
    load_points(state)
    load_all_item_scans(state)

    # Hotkeys registrieren
    print("Registriere Hotkeys...")
    if not register_hotkeys():
        print("[WARNUNG] Nicht alle Hotkeys registriert.")
    print()

    print("Bereit! Starte mit CTRL+ALT+A um Punkte aufzunehmen.")
    print_status(state)
    print()

    msg = wintypes.MSG()

    try:
        while not state.quit_event.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY:
                    hk_id = msg.wParam

                    if hk_id == HOTKEY_RECORD:
                        handle_record(state)
                    elif hk_id == HOTKEY_UNDO:
                        handle_undo(state)
                    elif hk_id == HOTKEY_CLEAR:
                        handle_clear(state)
                    elif hk_id == HOTKEY_RESET:
                        handle_reset(state)
                    elif hk_id == HOTKEY_EDITOR:
                        handle_editor(state)
                    elif hk_id == HOTKEY_ITEM_SCAN:
                        handle_item_scan_editor(state)
                    elif hk_id == HOTKEY_LOAD:
                        handle_load(state)
                    elif hk_id == HOTKEY_SHOW:
                        handle_show(state)
                    elif hk_id == HOTKEY_TOGGLE:
                        handle_toggle(state)
                    elif hk_id == HOTKEY_ANALYZE:
                        handle_analyze(state)
                    elif hk_id == HOTKEY_QUIT:
                        handle_quit(state, main_thread_id)
                        break
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
