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
SEQUENCES_DIR: str = "sequences"       # Ordner für gespeicherte Sequenzen
CLICKS_PER_POINT: int = 1              # Anzahl Klicks pro Punkt
MAX_TOTAL_CLICKS: Optional[int] = None # None = unendlich
FAILSAFE_ENABLED: bool = True          # Fail-Safe aktivieren

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
HOTKEY_LOAD = 6
HOTKEY_SHOW = 7
HOTKEY_TOGGLE = 8
HOTKEY_ANALYZE = 9
HOTKEY_QUIT = 10

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

    def __str__(self) -> str:
        pos_str = f"{self.name} ({self.x}, {self.y})" if self.name else f"({self.x}, {self.y})"
        if self.wait_pixel and self.wait_color:
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

@dataclass
class AutoClickerState:
    """Zustand des Autoclickers."""
    # Punkte-Pool (wiederverwendbar)
    points: list[ClickPoint] = field(default_factory=list)

    # Gespeicherte Sequenzen
    sequences: dict[str, Sequence] = field(default_factory=dict)

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
                "wait_pixel": s.wait_pixel, "wait_color": s.wait_color}

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
        with open(points_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            state.points = [ClickPoint(p["x"], p["y"], p.get("name", "")) for p in data]
        print(f"[LOAD] {len(state.points)} Punkt(e) geladen")

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
                        wait_pixel = tuple(wait_pixel)
                    wait_color = s.get("wait_color")
                    if wait_color:
                        wait_color = tuple(wait_color)
                    # Unterstütze beide Formate: delay_before (neu) und delay_after (alt)
                    delay = s.get("delay_before", s.get("delay_after", 0))
                    step = SequenceStep(
                        x=s["x"],
                        y=s["y"],
                        delay_before=delay,
                        name=s.get("name", ""),
                        wait_pixel=wait_pixel,
                        wait_color=wait_color
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
COLOR_TOLERANCE = 40                    # Farbtoleranz für Erkennung (erhöht)
DEBUG_DETECTION = True                  # Debug-Ausgaben aktivieren

def color_distance(c1: tuple, c2: tuple) -> float:
    """Berechnet die Distanz zwischen zwei RGB-Farben."""
    return ((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2) ** 0.5

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

    try:
        choice = input("> ").strip().lower()

        if choice == "abbruch":
            print("[ABBRUCH] Editor beendet.")
            return

        choice_num = int(choice)

        if choice_num == 0:
            # Neue Sequenz erstellen
            edit_sequence(state, None)
        elif 1 <= choice_num <= len(available_sequences):
            # Bestehende Sequenz bearbeiten
            name, path = available_sequences[choice_num - 1]
            existing_seq = load_sequence_file(path)
            if existing_seq:
                edit_sequence(state, existing_seq)
        else:
            print("[FEHLER] Ungültige Auswahl!")

    except ValueError:
        print("[FEHLER] Bitte eine Nummer eingeben!")
    except (KeyboardInterrupt, EOFError):
        print("\n[ABBRUCH] Editor beendet.")


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
    print("  <Nr> <Zeit>  - Warte Xs, dann klicke (z.B. '1 30' = 30s warten → P1 klicken)")
    print("  <Nr> 0       - Sofort klicken ohne Wartezeit (z.B. '1 0')")
    print("  <Nr> pixel   - Warte auf Farbe, dann klicke (z.B. '1 pixel')")
    print("  del <Nr>     - Schritt löschen (z.B. 'del 2')")
    print("  clear        - Alle Schritte löschen")
    print("  show         - Aktuelle Schritte anzeigen")
    print("  fertig       - Diese Phase abschließen")
    print("  abbruch      - Gesamten Editor abbrechen")
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

            # Neuen Schritt hinzufügen
            parts = user_input.split()
            if len(parts) != 2:
                print("  → Format: <Punkt-Nr> <Sekunden> oder <Punkt-Nr> pixel")
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

            # Prüfen ob Pixel-Wartezeit oder Zeit-Wartezeit
            if parts[1].lower() == "pixel":
                # Pixel-basierte Wartezeit (warte auf Farbe, dann klicke)
                print("\n  Farb-Trigger einrichten:")
                print("  Bewege die Maus zur Position wo die Farbe geprüft werden soll")
                print("  (Wenn diese Farbe erscheint, wird geklickt)")
                print("  Drücke Enter...")
                input()
                px, py = get_cursor_pos()
                print(f"  → Position: ({px}, {py})")

                # Farbe an dieser Position lesen
                if PILLOW_AVAILABLE:
                    img = take_screenshot((px, py, px+1, py+1))
                    if img:
                        color = img.getpixel((0, 0))[:3]
                        print(f"  → Gespeicherte Farbe: RGB{color}")
                        print(f"  → Wenn diese Farbe erscheint → klicke auf {point_name}")
                        step = SequenceStep(
                            x=point_x, y=point_y, delay_before=0, name=point_name,
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

    try:
        user_input = input("> ").strip().lower()

        if user_input == "abbruch":
            print("[ABBRUCH] Keine Sequenz geladen.")
            return

        idx = int(user_input) - 1
        if idx < 0 or idx >= len(sequences):
            print("[FEHLER] Ungültige Nummer!")
            return

        name, path = sequences[idx]
        seq = load_sequence_file(path)

        if seq:
            with state.lock:
                state.active_sequence = seq
            print(f"\n[ERFOLG] Sequenz '{seq.name}' geladen!")
            print("         Drücke CTRL+ALT+S zum Starten.\n")

    except ValueError:
        print("[FEHLER] Bitte eine Nummer eingeben!")
    except KeyboardInterrupt:
        print("\n[ABBRUCH]")

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

    # === PHASE 1: Warten VOR dem Klick (Zeit oder Farbe) ===
    if step.wait_pixel and step.wait_color:
        # Warten auf Farbe an Pixel-Position
        timeout = 300  # Max 5 Minuten warten
        start_time = time.time()
        while not state.stop_event.is_set():
            # Prüfe Farbe
            if PILLOW_AVAILABLE:
                img = take_screenshot((step.wait_pixel[0], step.wait_pixel[1],
                                      step.wait_pixel[0]+1, step.wait_pixel[1]+1))
                if img:
                    current_color = img.getpixel((0, 0))[:3]
                    if color_distance(current_color, step.wait_color) <= COLOR_TOLERANCE:
                        clear_line()
                        print(f"[{phase}] Schritt {step_num}/{total_steps} | Farbe erkannt! Klicke...", end="", flush=True)
                        break

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                print(f"\n[TIMEOUT] Farbe nicht erkannt nach {timeout}s")
                return False

            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | Warte auf Farbe... ({elapsed:.0f}s)", end="", flush=True)

            if state.stop_event.wait(1.0):
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
                  HOTKEY_EDITOR, HOTKEY_LOAD, HOTKEY_SHOW, HOTKEY_TOGGLE, HOTKEY_ANALYZE, HOTKEY_QUIT]:
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

    # Gespeicherte Punkte laden
    load_points(state)

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
