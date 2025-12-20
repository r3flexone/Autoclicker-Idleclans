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
from typing import Optional
from pathlib import Path

# =============================================================================
# KONFIGURATION
# =============================================================================
SEQUENCES_DIR: str = "sequences"       # Ordner für gespeicherte Sequenzen
CLICKS_PER_POINT: int = 1              # Anzahl Klicks pro Punkt
MAX_TOTAL_CLICKS: Optional[int] = None # None = unendlich
FAILSAFE_ENABLED: bool = True          # Fail-Safe aktivieren
LOOP_SEQUENCE: bool = True             # Sequenz wiederholen?

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
HOTKEY_QUIT = 9

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
    """Ein Schritt in einer Sequenz: Koordinaten und Wartezeit danach."""
    x: int                # X-Koordinate (direkt gespeichert)
    y: int                # Y-Koordinate (direkt gespeichert)
    delay_after: float    # Wartezeit in Sekunden NACH diesem Klick
    name: str = ""        # Optionaler Name des Punktes

    def __str__(self) -> str:
        if self.name:
            return f"{self.name} ({self.x}, {self.y}) → warte {self.delay_after}s"
        return f"({self.x}, {self.y}) → warte {self.delay_after}s"

@dataclass
class Sequence:
    """Eine Klick-Sequenz mit Namen und Schritten."""
    name: str
    steps: list[SequenceStep] = field(default_factory=list)

    def __str__(self) -> str:
        return f"{self.name} ({len(self.steps)} Schritte)"

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

    # Sequenzen speichern (mit eingebetteten Koordinaten)
    for name, seq in state.sequences.items():
        seq_data = {
            "name": seq.name,
            "steps": [
                {"x": s.x, "y": s.y, "name": s.name, "delay_after": s.delay_after}
                for s in seq.steps
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
    """Lädt eine einzelne Sequenz-Datei (neues Format mit eingebetteten Koordinaten)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            steps = []
            for s in data["steps"]:
                # Neues Format: x, y, name, delay_after direkt gespeichert
                step = SequenceStep(
                    x=s["x"],
                    y=s["y"],
                    delay_after=s["delay_after"],
                    name=s.get("name", "")
                )
                steps.append(step)
            return Sequence(data["name"], steps)
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
            step_info = f"Schritt {state.current_step_index + 1}/{len(state.active_sequence.steps)}"
            print(f"[{status}] Sequenz: {seq_name} | {step_info} | Klicks: {state.total_clicks}", flush=True)
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
                for i, step in enumerate(seq.steps):
                    print(f"      {i+1}. {step}")

    with state.lock:
        if state.active_sequence:
            print(f"\n  [AKTIV] {state.active_sequence.name}")
    print()

# =============================================================================
# SEQUENZ-EDITOR (Konsolen-basiert)
# =============================================================================
def run_sequence_editor(state: AutoClickerState) -> None:
    """Interaktiver Sequenz-Editor."""
    print("\n" + "=" * 60)
    print("  SEQUENZ-EDITOR")
    print("=" * 60)

    with state.lock:
        if not state.points:
            print("\n[FEHLER] Erst Punkte aufnehmen (CTRL+ALT+A)!")
            return

        print("\nVerfügbare Punkte:")
        for i, p in enumerate(state.points):
            print(f"  P{i+1}: {p}")

    print("\n" + "-" * 60)
    print("Erstelle eine neue Sequenz.")
    print("Gib für jeden Schritt ein: <Punkt-Nr> <Wartezeit in Sekunden>")
    print("Beispiel: '1 30' = Punkt 1 klicken, dann 30s warten")
    print("Eingabe 'fertig' zum Speichern, 'abbruch' zum Abbrechen")
    print("-" * 60 + "\n")

    # Sequenz-Name abfragen
    seq_name = input("Name der Sequenz: ").strip()
    if not seq_name:
        seq_name = f"Sequenz_{int(time.time())}"

    steps: list[SequenceStep] = []

    while True:
        try:
            user_input = input(f"Schritt {len(steps) + 1} (Punkt Zeit): ").strip().lower()

            if user_input == "fertig":
                break
            elif user_input == "abbruch":
                print("[ABBRUCH] Sequenz nicht gespeichert.")
                return
            elif user_input == "":
                continue

            parts = user_input.split()
            if len(parts) != 2:
                print("  → Format: <Punkt-Nr> <Sekunden> (z.B. '1 30')")
                continue

            point_num = int(parts[0])
            delay = float(parts[1])

            with state.lock:
                if point_num < 1 or point_num > len(state.points):
                    print(f"  → Ungültiger Punkt! Verfügbar: 1-{len(state.points)}")
                    continue
                # Punkt-Daten direkt kopieren
                point = state.points[point_num - 1]
                point_x = point.x
                point_y = point.y
                point_name = point.name

            if delay < 0:
                print("  → Wartezeit muss >= 0 sein!")
                continue

            # Koordinaten direkt in den Step speichern (unabhängig von Punkten)
            step = SequenceStep(x=point_x, y=point_y, delay_after=delay, name=point_name)
            steps.append(step)
            print(f"  ✓ Hinzugefügt: {step}")

        except ValueError:
            print("  → Ungültige Eingabe! Format: <Punkt-Nr> <Sekunden>")
        except KeyboardInterrupt:
            print("\n[ABBRUCH] Editor beendet.")
            return

    if not steps:
        print("[FEHLER] Keine Schritte hinzugefügt!")
        return

    # Sequenz erstellen und speichern
    new_sequence = Sequence(name=seq_name, steps=steps)

    with state.lock:
        state.sequences[seq_name] = new_sequence
        state.active_sequence = new_sequence

    # In Datei speichern
    save_data(state)

    print(f"\n[ERFOLG] Sequenz '{seq_name}' mit {len(steps)} Schritten gespeichert!")
    print("         Drücke CTRL+ALT+S zum Starten.\n")

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
def sequence_worker(state: AutoClickerState) -> None:
    """Worker-Thread, der die Sequenz ausführt."""
    print("\n[WORKER] Sequenz gestartet.")

    with state.lock:
        sequence = state.active_sequence
        if not sequence or not sequence.steps:
            print("[FEHLER] Keine gültige Sequenz!")
            state.is_running = False
            return

    while not state.stop_event.is_set() and not state.quit_event.is_set():
        with state.lock:
            if state.current_step_index >= len(sequence.steps):
                if LOOP_SEQUENCE:
                    state.current_step_index = 0
                    print("\n[LOOP] Sequenz startet von vorne...")
                else:
                    break

            step = sequence.steps[state.current_step_index]

        # Fail-Safe prüfen
        if check_failsafe():
            print("\n[FAILSAFE] Maus in Ecke erkannt! Stoppe...")
            state.stop_event.set()
            break

        # Klick ausführen (Koordinaten direkt aus Step)
        for _ in range(CLICKS_PER_POINT):
            if state.stop_event.is_set():
                break

            if check_failsafe():
                print("\n[FAILSAFE] Stoppe...")
                state.stop_event.set()
                break

            send_click(step.x, step.y)

            with state.lock:
                state.total_clicks += 1

            print_status(state)

            if MAX_TOTAL_CLICKS and state.total_clicks >= MAX_TOTAL_CLICKS:
                print(f"\n[INFO] Maximum von {MAX_TOTAL_CLICKS} Klicks erreicht.")
                state.stop_event.set()
                break

        # Wartezeit nach diesem Schritt (unterbrechbar)
        if not state.stop_event.is_set() and step.delay_after > 0:
            # Countdown anzeigen
            remaining = step.delay_after
            while remaining > 0 and not state.stop_event.is_set():
                wait_time = min(1.0, remaining)
                if state.stop_event.wait(wait_time):
                    break
                remaining -= wait_time
                if remaining > 0:
                    with state.lock:
                        step_num = state.current_step_index + 1
                        total_steps = len(sequence.steps)
                    clear_line()
                    print(f"[WARTE] Schritt {step_num}/{total_steps} | Nächster Klick in {remaining:.0f}s...", end="", flush=True)

        # Nächster Schritt
        with state.lock:
            state.current_step_index += 1

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
                  HOTKEY_EDITOR, HOTKEY_LOAD, HOTKEY_SHOW, HOTKEY_TOGGLE, HOTKEY_QUIT]:
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
    print("  CTRL+ALT+S  - Start/Stop der aktiven Sequenz")
    print("  CTRL+ALT+Q  - Programm beenden")
    print()
    print("So funktioniert's:")
    print("  1. Punkte aufnehmen (CTRL+ALT+A an verschiedenen Positionen)")
    print("  2. Sequenz erstellen (CTRL+ALT+E) mit Punkt-Nr und Wartezeit")
    print("  3. Sequenz starten (CTRL+ALT+S)")
    print()
    print("Beispiel-Sequenz:")
    print("  Schritt 1: Punkt 1, warte 30s")
    print("  Schritt 2: Punkt 2, warte 30s")
    print("  Schritt 3: Punkt 3, warte 20s")
    print("  Schritt 4: Punkt 2, warte 30s  ← Punkt 2 nochmal!")
    print()
    print(f"Sequenzen werden in '{SEQUENCES_DIR}/' gespeichert.")
    print(f"Loop-Modus: {'Aktiviert' if LOOP_SEQUENCE else 'Deaktiviert'}")
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
