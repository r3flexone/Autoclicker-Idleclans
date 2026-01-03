#!/usr/bin/env python3
"""
Windows Autoclicker mit Sequenz-Unterstützung und Item-Erkennung.
Neues modulares Hauptskript - ersetzt autoclicker.py
"""

import ctypes
import ctypes.wintypes as wintypes
import sys
import time

# Modulare Imports
from autoclicker.config import CONFIG, SEQUENCES_DIR, CONFIG_FILE
from autoclicker.models import AutoClickerState
from autoclicker.winapi import (
    user32, kernel32,
    WM_HOTKEY, PM_REMOVE,
    HOTKEY_RECORD, HOTKEY_UNDO, HOTKEY_CLEAR, HOTKEY_RESET,
    HOTKEY_EDITOR, HOTKEY_ITEM_SCAN, HOTKEY_LOAD, HOTKEY_SHOW,
    HOTKEY_TOGGLE, HOTKEY_PAUSE, HOTKEY_SKIP, HOTKEY_SWITCH,
    HOTKEY_SCHEDULE, HOTKEY_ANALYZE, HOTKEY_QUIT,
    register_hotkeys, unregister_hotkeys
)
from autoclicker.persistence import (
    ensure_sequences_dir, ensure_item_scans_dir, init_directories,
    load_points, load_global_slots, load_global_items, load_all_item_scans
)
from autoclicker.execution import print_status
from autoclicker.handlers import (
    handle_record, handle_undo, handle_clear, handle_reset,
    handle_editor, handle_item_scan_editor, handle_load, handle_show,
    handle_toggle, handle_pause, handle_skip, handle_switch,
    handle_schedule, handle_analyze, handle_quit
)


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

    # State initialisieren
    state = AutoClickerState()
    state.config = CONFIG.copy()
    main_thread_id = kernel32.GetCurrentThreadId()

    # Ordner erstellen
    ensure_sequences_dir()
    ensure_item_scans_dir()
    init_directories()

    # Gespeicherte Daten laden
    load_points(state)
    load_global_slots(state)
    load_global_items(state)
    load_all_item_scans(state)

    # Hotkeys registrieren
    if not register_hotkeys():
        print("[WARNUNG] Nicht alle Hotkeys konnten registriert werden.")
        print()

    print("Bereit! Starte mit CTRL+ALT+A um Punkte aufzunehmen.")
    print_status(state)
    print()

    # Message-Struktur für Windows-Nachrichten
    msg = wintypes.MSG()

    # Hotkey-Handler Zuordnung
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
        # Haupt-Event-Loop
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
