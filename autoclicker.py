#!/usr/bin/env python3
"""
Windows Autoclicker - Python 3.13
=================================
Ein Autoclicker für Windows 11, der nur die Standardbibliothek verwendet.

Starten: python autoclicker.py
Beenden: CTRL+ALT+Q oder Konsole schließen

Hotkeys:
  CTRL+ALT+A  - Aktuelle Mausposition aufnehmen (Add)
  CTRL+ALT+U  - Letzten Punkt entfernen
  CTRL+ALT+S  - Start/Stop Toggle
  CTRL+ALT+Q  - Programm beenden

Fail-Safe: Maus in obere linke Ecke bewegen (x<=2, y<=2) stoppt den Klicker.
"""

import ctypes
import ctypes.wintypes as wintypes
import threading
import time
import sys
from dataclasses import dataclass, field
from typing import Optional

# =============================================================================
# KONFIGURATION - Hier anpassen
# =============================================================================
DELAY_SECONDS: float = 1.0          # Wartezeit zwischen Klicks (Sekunden)
CLICKS_PER_POINT: int = 1           # Anzahl Klicks pro Punkt
MAX_TOTAL_CLICKS: Optional[int] = None  # None oder 0 = unendlich, sonst Limit
FAILSAFE_ENABLED: bool = True       # Fail-Safe aktivieren (Ecke oben links)

# =============================================================================
# WINDOWS API KONSTANTEN
# =============================================================================
# Modifier Keys
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000

# Virtual Key Codes
VK_A = 0x41  # A statt R (R oft von anderen Programmen belegt)
VK_U = 0x55
VK_S = 0x53
VK_Q = 0x51

# Hotkey IDs
HOTKEY_RECORD = 1
HOTKEY_UNDO = 2
HOTKEY_TOGGLE = 3
HOTKEY_QUIT = 4

# Window Messages
WM_HOTKEY = 0x0312

# Mouse Input
INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_MOVE = 0x0001

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

# GetCursorPos
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL

# SetCursorPos
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL

# SendInput
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

# RegisterHotKey / UnregisterHotKey
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL

user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL

# GetMessage / PeekMessage
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL

user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL

# PeekMessage Flags
PM_REMOVE = 0x0001

# PostThreadMessage (zum Beenden der Message Loop)
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

# GetCurrentThreadId
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

    def __str__(self) -> str:
        return f"({self.x}, {self.y})"

@dataclass
class AutoClickerState:
    """Zustand des Autoclickers."""
    points: list[ClickPoint] = field(default_factory=list)
    is_running: bool = False
    total_clicks: int = 0
    current_index: int = 0

    # Thread-sichere Events
    stop_event: threading.Event = field(default_factory=threading.Event)
    quit_event: threading.Event = field(default_factory=threading.Event)

    # Lock für thread-sichere Zugriffe
    lock: threading.Lock = field(default_factory=threading.Lock)

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
    # Maus bewegen
    set_cursor_pos(x, y)
    time.sleep(0.01)  # Kurze Pause für Stabilität

    # Linksklick: Down + Up
    inputs = (INPUT * 2)()

    # Mouse down
    inputs[0].type = INPUT_MOUSE
    inputs[0].union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN

    # Mouse up
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
        status = "RUNNING" if state.is_running else "STOPPED"
        points_str = f"{len(state.points)} Punkt(e)"
        clicks_str = f"Klicks: {state.total_clicks}"
        if MAX_TOTAL_CLICKS:
            clicks_str += f"/{MAX_TOTAL_CLICKS}"
        index_str = f"Index: {state.current_index}" if state.is_running else ""

        clear_line()
        print(f"[{status}] {points_str} | {clicks_str} {index_str}", flush=True)

def print_points(state: AutoClickerState) -> None:
    """Zeigt alle gespeicherten Punkte an."""
    with state.lock:
        if not state.points:
            print("  Keine Punkte gespeichert.")
            return
        for i, p in enumerate(state.points):
            print(f"  P{i+1}: {p}")

# =============================================================================
# WORKER THREAD
# =============================================================================
def clicker_worker(state: AutoClickerState) -> None:
    """Worker-Thread, der die Klicks ausführt."""
    print("\n[WORKER] Klicker gestartet.")

    while not state.stop_event.is_set() and not state.quit_event.is_set():
        # Fail-Safe prüfen
        if check_failsafe():
            print("\n[FAILSAFE] Maus in Ecke erkannt! Stoppe...")
            state.stop_event.set()
            break

        # Punkte durchgehen
        with state.lock:
            if not state.points:
                break
            point = state.points[state.current_index]
            num_points = len(state.points)

        # Klicks für diesen Punkt
        for _ in range(CLICKS_PER_POINT):
            if state.stop_event.is_set() or state.quit_event.is_set():
                break

            # Fail-Safe erneut prüfen
            if check_failsafe():
                print("\n[FAILSAFE] Maus in Ecke erkannt! Stoppe...")
                state.stop_event.set()
                break

            send_click(point.x, point.y)

            with state.lock:
                state.total_clicks += 1
                total = state.total_clicks

            # Status ausgeben
            print_status(state)

            # Max-Klicks erreicht?
            if MAX_TOTAL_CLICKS and total >= MAX_TOTAL_CLICKS:
                print(f"\n[INFO] Maximum von {MAX_TOTAL_CLICKS} Klicks erreicht.")
                state.stop_event.set()
                break

            # Warten zwischen Klicks (unterbrechbar)
            if not state.stop_event.wait(DELAY_SECONDS):
                pass  # Timeout = weitermachen

        # Nächster Punkt
        with state.lock:
            state.current_index = (state.current_index + 1) % num_points

    with state.lock:
        state.is_running = False

    print("\n[WORKER] Klicker gestoppt.")
    print_status(state)

# =============================================================================
# HOTKEY HANDLER
# =============================================================================
def handle_record(state: AutoClickerState) -> None:
    """Nimmt die aktuelle Mausposition auf."""
    x, y = get_cursor_pos()
    point = ClickPoint(x, y)

    with state.lock:
        state.points.append(point)
        count = len(state.points)

    print(f"\n[RECORD] Punkt {count} hinzugefügt: {point}")
    print_status(state)

def handle_undo(state: AutoClickerState) -> None:
    """Entfernt den letzten Punkt."""
    with state.lock:
        if state.points:
            removed = state.points.pop()
            print(f"\n[UNDO] Punkt entfernt: {removed}")
        else:
            print("\n[UNDO] Keine Punkte zum Entfernen.")
    print_status(state)

def handle_toggle(state: AutoClickerState) -> None:
    """Startet oder stoppt den Klicker."""
    with state.lock:
        if state.is_running:
            # Stoppen
            state.stop_event.set()
            print("\n[TOGGLE] Stoppe Klicker...")
        else:
            # Starten
            if not state.points:
                print("\n[FEHLER] Keine Punkte gespeichert! Erst Punkte aufnehmen (CTRL+ALT+A).")
                return

            state.is_running = True
            state.stop_event.clear()
            state.current_index = 0

            # Worker-Thread starten
            worker = threading.Thread(target=clicker_worker, args=(state,), daemon=True)
            worker.start()

def handle_quit(state: AutoClickerState, main_thread_id: int) -> None:
    """Beendet das Programm."""
    print("\n[QUIT] Beende Programm...")

    # Alle Threads stoppen
    state.stop_event.set()
    state.quit_event.set()

    # Message Loop beenden
    WM_QUIT = 0x0012
    user32.PostThreadMessageW(main_thread_id, WM_QUIT, 0, 0)

# =============================================================================
# HOTKEY REGISTRIERUNG
# =============================================================================
def register_hotkeys() -> bool:
    """Registriert alle globalen Hotkeys."""
    modifiers = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT

    hotkeys = [
        (HOTKEY_RECORD, VK_A, "CTRL+ALT+A (Aufnehmen)"),
        (HOTKEY_UNDO, VK_U, "CTRL+ALT+U (Rückgängig)"),
        (HOTKEY_TOGGLE, VK_S, "CTRL+ALT+S (Start/Stop)"),
        (HOTKEY_QUIT, VK_Q, "CTRL+ALT+Q (Beenden)"),
    ]

    success = True
    for hk_id, vk, name in hotkeys:
        if not user32.RegisterHotKey(None, hk_id, modifiers, vk):
            print(f"[FEHLER] Konnte Hotkey nicht registrieren: {name}")
            success = False
        else:
            print(f"  Hotkey registriert: {name}")

    return success

def unregister_hotkeys() -> None:
    """Deregistriert alle Hotkeys."""
    for hk_id in [HOTKEY_RECORD, HOTKEY_UNDO, HOTKEY_TOGGLE, HOTKEY_QUIT]:
        user32.UnregisterHotKey(None, hk_id)

# =============================================================================
# HAUPTPROGRAMM
# =============================================================================
def print_help() -> None:
    """Zeigt die Hilfe an."""
    print("=" * 60)
    print("  WINDOWS AUTOCLICKER - Python 3.13")
    print("=" * 60)
    print()
    print("Hotkeys:")
    print("  CTRL+ALT+A  - Aktuelle Mausposition aufnehmen (Add)")
    print("  CTRL+ALT+U  - Letzten Punkt entfernen (Undo)")
    print("  CTRL+ALT+S  - Start/Stop Toggle")
    print("  CTRL+ALT+Q  - Programm beenden (Quit)")
    print()
    print("Einstellungen:")
    print(f"  Verzögerung:      {DELAY_SECONDS} Sekunde(n)")
    print(f"  Klicks pro Punkt: {CLICKS_PER_POINT}")
    print(f"  Max. Klicks:      {MAX_TOTAL_CLICKS if MAX_TOTAL_CLICKS else 'Unbegrenzt'}")
    print(f"  Fail-Safe:        {'Aktiviert' if FAILSAFE_ENABLED else 'Deaktiviert'}")
    print()
    print("Fail-Safe: Maus in obere linke Ecke (x<=2, y<=2) stoppt den Klicker.")
    print("=" * 60)
    print()

def main() -> int:
    """Hauptfunktion."""
    # Hilfe anzeigen
    print_help()

    # Zustand initialisieren
    state = AutoClickerState()
    main_thread_id = kernel32.GetCurrentThreadId()

    # Hotkeys registrieren
    print("Registriere Hotkeys...")
    if not register_hotkeys():
        print("[WARNUNG] Nicht alle Hotkeys konnten registriert werden.")
        print("          Möglicherweise werden sie von einem anderen Programm verwendet.")
    print()

    print("Bereit! Drücke CTRL+ALT+A um Punkte aufzunehmen.")
    print_status(state)
    print()

    # Message Loop (non-blocking mit PeekMessage)
    msg = wintypes.MSG()

    try:
        while not state.quit_event.is_set():
            # Nachrichten prüfen (non-blocking)
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY:
                    hk_id = msg.wParam

                    if hk_id == HOTKEY_RECORD:
                        handle_record(state)
                    elif hk_id == HOTKEY_UNDO:
                        handle_undo(state)
                    elif hk_id == HOTKEY_TOGGLE:
                        handle_toggle(state)
                    elif hk_id == HOTKEY_QUIT:
                        handle_quit(state, main_thread_id)
                        break
            else:
                # Keine Nachricht - kurz warten um CPU zu schonen
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[ABBRUCH] Programm wird beendet...")
        state.stop_event.set()
        state.quit_event.set()

    finally:
        # Aufräumen
        unregister_hotkeys()
        print("\n[INFO] Hotkeys deregistriert.")

        # Kurz warten, damit Worker-Thread beenden kann
        time.sleep(0.2)

        print("[INFO] Programm beendet.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
