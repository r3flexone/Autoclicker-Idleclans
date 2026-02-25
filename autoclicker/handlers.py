"""
Hotkey-Handler für den Autoclicker.
Verarbeitet Tastenkombinationen und führt entsprechende Aktionen aus.
"""

import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import CONFIG_FILE, SEQUENCES_DIR, DEFAULT_CONFIG
from .models import AutoClickerState, ClickPoint
from .utils import safe_input, format_duration, parse_time_input, is_cancel, confirm, interactive_select, col, ok, err, info, warn, header, hint, coord_context
from .winapi import get_cursor_pos, set_cursor_pos, user32
from .persistence import (
    save_data, ensure_sequences_dir, list_available_sequences,
    load_sequence_file, get_next_point_id, get_point_by_id, print_points,
    ITEMS_DIR, SLOTS_DIR, ITEM_SCANS_DIR, init_directories
)
from .execution import sequence_worker, print_status
from .imaging import run_color_analyzer


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

    print(f"\n{col('[RECORD]', 'green')} #{new_id} {name} hinzugefügt: {coord_context(x, y)}")
    print_status(state)


def handle_undo(state: AutoClickerState) -> None:
    """Entfernt den letzten Punkt."""
    with state.lock:
        if state.points:
            removed = state.points.pop()
            print(f"\n{col('[UNDO]', 'yellow')} Punkt entfernt: {removed}")
            save_data(state)
        else:
            print(f"\n{col('[UNDO]', 'yellow')} Keine Punkte zum Entfernen.")
    print_status(state)


def handle_clear(state: AutoClickerState) -> None:
    """Löscht ALLE Punkte."""
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return

        count = len(state.points)
        if count == 0:
            print(f"\n{col('[CLEAR]', 'yellow')} Keine Punkte vorhanden.")
            return

        state.points.clear()
        state.active_sequence = None

    save_data(state)
    print(f"\n{ok(f'Alle {count} Punkte gelöscht!')}")
    print_status(state)


def handle_reset(state: AutoClickerState) -> None:
    """Löscht ALLES - kompletter Factory Reset wie frisch von GitHub."""
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return

    print(header("FACTORY RESET - ALLES WIRD GELÖSCHT!"))
    print("\nFolgendes wird gelöscht:")
    print(f"  - {len(state.points)} Punkt(e)")
    print(f"  - {len(list_available_sequences())} Sequenz-Datei(en)")
    print(f"  - {len(state.global_slots)} Slot(s)")
    print(f"  - {len(state.global_items)} Item(s)")
    print(f"  - {len(state.item_scans)} Item-Scan(s)")
    print(f"  - Config-Einstellungen")
    print("\nDas Programm wird danach wie frisch von GitHub sein!")
    print("\nBist du sicher? Tippe 'JA' zum Bestätigen:")

    try:
        confirm_text = safe_input("> ").strip().upper()
        if confirm_text != "JA":
            print(f"{col('[ABBRUCH]', 'yellow')} Nichts wurde gelöscht.")
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
                print(f"  - {folder}/ gelöscht")

        # Config löschen
        config_path = Path(CONFIG_FILE)
        if config_path.exists():
            config_path.unlink()
            print(f"  - {CONFIG_FILE} gelöscht")

        # Ordner neu erstellen
        ensure_sequences_dir()
        init_directories()

        # Config auf Standard zurücksetzen
        with state.lock:
            state.config = DEFAULT_CONFIG.copy()

        print(f"\n{ok('Factory Reset abgeschlossen!')}")
        print(ok("Das Programm ist jetzt wie frisch von GitHub."))
        print_status(state)

    except (KeyboardInterrupt, EOFError):
        print(f"\n{col('[ABBRUCH]', 'yellow')} Nichts wurde gelöscht.")


def handle_editor(state: AutoClickerState) -> None:
    """Öffnet den Sequenz-Editor."""
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
    from .editors.sequence_editor import run_sequence_editor
    run_sequence_editor(state)


def handle_item_scan_editor(state: AutoClickerState) -> None:
    """Öffnet das Item-Scan Menü (Slots, Items, Scans)."""
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
    from .editors.item_scan_editor import run_item_scan_menu
    run_item_scan_menu(state)


def handle_load(state: AutoClickerState) -> None:
    """Lädt eine Sequenz."""
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
    from .editors.sequence_editor import run_sequence_loader
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
    print("  done / d    - Zurück")
    print("  Enter       - Zurück")
    print("-" * 50)

    while True:
        try:
            user_input = safe_input("> ").strip()
            if not user_input:
                return
            if user_input.lower() in ("done", "d"):
                return

            # Löschen-Befehl (per ID)
            if user_input.lower().startswith("del "):
                try:
                    del_id = int(user_input[4:])
                    with state.lock:
                        point_to_del = get_point_by_id(state, del_id)
                        if not point_to_del:
                            print(f"{err(f'Punkt #{del_id} nicht gefunden!')} {hint('(Enter = Punkte anzeigen)')}")
                            continue
                        state.points.remove(point_to_del)
                        num_points = len(state.points)
                    save_data(state)
                    print(f"{ok(f'Punkt #{del_id} gelöscht: {point_to_del}')}")
                    if num_points == 0:
                        print(info("Keine Punkte mehr vorhanden."))
                        return
                except ValueError:
                    print(err("Format: del <ID>"))
                continue

            parts = user_input.split(maxsplit=1)
            point_id = int(parts[0])

            with state.lock:
                point = get_point_by_id(state, point_id)
                if not point:
                    print(err(f"Punkt #{point_id} nicht gefunden!"))
                    continue

            if len(parts) == 1:
                # Nur ID → Testen (Maus hinbewegen)
                print(f"{col('[TEST]', 'cyan')} Bewege Maus zu {point.name} {coord_context(point.x, point.y)}...")
                set_cursor_pos(point.x, point.y)
                print(f"{col('[TEST]', 'cyan')} Maus ist jetzt bei {point.name}. Neuer Name? (Enter = behalten)")

                new_name = safe_input("> ").strip()
                if new_name:
                    with state.lock:
                        point.name = new_name
                    save_data(state)
                    print(ok(f"Punkt #{point_id} umbenannt zu '{new_name}'"))
                else:
                    print(ok(f"Name '{point.name}' beibehalten."))

            else:
                # ID + Name → Direkt umbenennen
                new_name = parts[1]
                with state.lock:
                    point.name = new_name
                save_data(state)
                print(ok(f"Punkt #{point_id} umbenannt zu '{new_name}'"))

        except ValueError:
            print(f"{err('Ungültige Eingabe!')} {hint('(Zahl = testen, <Nr> <Name> = umbenennen, del <Nr> = löschen)')}")
        except (KeyboardInterrupt, EOFError):
            return


def handle_toggle(state: AutoClickerState) -> None:
    """Startet oder stoppt die Sequenz."""
    # Prüfe ob Countdown aktiv → nur abbrechen, nicht starten
    with state.lock:
        if state.countdown_active:
            state.stop_event.set()
            print(f"\n{col('[TOGGLE]', 'yellow')} Countdown abgebrochen.")
            return

    # Prüfe ob bereits läuft → stoppen
    with state.lock:
        if state.is_running:
            state.stop_event.set()
            print(f"\n{col('[TOGGLE]', 'yellow')} Stoppe Sequenz...")
            return

    # Keine Sequenz geladen → automatisch Lade-Menü öffnen
    if not state.active_sequence:
        print(f"\n{info('Keine Sequenz geladen - öffne Lade-Menü...')}")
        from .editors.sequence_editor import run_sequence_loader
        run_sequence_loader(state)
        # Nach dem Laden prüfen ob jetzt eine Sequenz da ist
        if not state.active_sequence:
            return  # Nichts geladen

    # Jetzt starten
    with state.lock:
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
            print(f"\n{info('Keine Sequenz läuft.')}")
            return

        if state.pause_event.is_set():
            state.pause_event.clear()
            print(f"\n{col('[RESUME]', 'green')} Sequenz fortgesetzt.")
        else:
            state.pause_event.set()
            print(f"\n{col('[PAUSE]', 'yellow')} Sequenz pausiert. Fortsetzen: {col('CTRL+ALT+G', 'yellow')}")


def handle_skip(state: AutoClickerState) -> None:
    """Überspringt die aktuelle Wartezeit."""
    with state.lock:
        if not state.is_running:
            print(f"\n{info('Keine Sequenz läuft.')}")
            return

        state.skip_event.set()
        print(f"\n{col('[SKIP]', 'cyan')} Wartezeit übersprungen!")


def handle_switch(state: AutoClickerState) -> None:
    """Schneller Wechsel zwischen gespeicherten Sequenzen."""
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return

    sequences = list_available_sequences()

    if not sequences:
        print(f"\n{info('Keine Sequenzen vorhanden!')} Erstelle eine mit {col('CTRL+ALT+E', 'yellow')}")
        return

    # Sequenzen einmal laden und cachen
    loaded_sequences = []
    menu_options = []
    for name, path in sequences:
        seq = load_sequence_file(path)
        if seq:
            loaded_sequences.append(seq)
            active_marker = " *AKTIV*" if state.active_sequence and state.active_sequence.name == seq.name else ""
            menu_options.append(f"{seq.name}{active_marker}")

    choice = interactive_select(menu_options, title="\nQUICK-SWITCH: Sequenz wählen")

    if choice == -1 or choice >= len(loaded_sequences):
        return

    seq = loaded_sequences[choice]
    with state.lock:
        state.active_sequence = seq
    print(f"\n{ok(f'Gewechselt zu: {seq.name}')}")
    print(f"     Starten mit {col('CTRL+ALT+S', 'yellow')}")


def handle_schedule(state: AutoClickerState) -> None:
    """Plant den Start einer Sequenz zu einem bestimmten Zeitpunkt."""
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return

    # Keine Sequenz geladen → automatisch Lade-Menü öffnen
    if not state.active_sequence:
        print(f"\n{info('Keine Sequenz geladen - öffne Lade-Menü...')}")
        from .editors.sequence_editor import run_sequence_loader
        run_sequence_loader(state)
        # Nach dem Laden prüfen ob jetzt eine Sequenz da ist
        if not state.active_sequence:
            return  # Nichts geladen

    print("\n" + "=" * 50)
    print("ZEITPLAN: Sequenz zu bestimmter Zeit starten")
    print("=" * 50)
    print(f"\nAktive Sequenz: {state.active_sequence.name}")
    print("\nZeit-Formate:")
    print("  14:30    - Startet um 14:30 Uhr")
    print("  1430     - Startet um 14:30 Uhr (4-stellig, 0000-2359)")
    print("  +30s     - Startet in 30 Sekunden")
    print("  +30m     - Startet in 30 Minuten (+5 = +5m)")
    print("  +2h      - Startet in 2 Stunden")
    print("  30s/30m/2h - Wartet (Einheit s/m/h erforderlich!)")
    print("\nZeit eingeben (oder 'cancel'):")

    try:
        time_input = safe_input("> ").strip()

        if not time_input or is_cancel(time_input):
            print(col("[ABBRUCH]", "yellow"))
            return

        seconds, desc, target_timestamp = parse_time_input(time_input)

        # Debug: Zeige was geparst wurde
        if state.config.get("debug_mode", False):
            print(f"[DEBUG] Eingabe: '{time_input}' -> seconds={seconds}, desc='{desc}', target_timestamp={target_timestamp}")

        if seconds < 0:
            print(err(desc))
            return

        if seconds < 1:
            print(info("Zeit zu kurz - starte sofort..."))
            # Starte sofort
            handle_toggle(state)
            return

        # Zeige Countdown-Info und warte auf Bestätigung
        # Bei absoluten Zeiten: target_timestamp enthält die Zielzeit
        # Bei relativen Zeiten: target_timestamp ist None, wird nach Enter berechnet
        if target_timestamp is not None:
            target_time = target_timestamp
        else:
            target_time = datetime.now().timestamp() + seconds
        target_dt = datetime.fromtimestamp(target_time)
        print(f"\n{col('[GEPLANT]', 'cyan')} Sequenz '{state.active_sequence.name}' startet {desc}")
        print(f"          Zielzeit: {target_dt.strftime('%H:%M:%S')}")
        print(f"          Wartezeit: {format_duration(seconds)}")
        print("\n          Enter drücken zum Starten, 'cancel' zum Abbrechen")

        # Bestätigung abwarten
        confirm_input = safe_input("> ").strip()
        if is_cancel(confirm_input):
            print(col("[ABBRUCH]", "yellow"))
            return

        # Nach Enter: Bei relativen Zeiten jetzt die Zielzeit berechnen
        # Bei absoluten Zeiten bleibt target_time unverändert (das ist der Fix!)
        if target_timestamp is None:
            # Relative Zeit: Jetzt erst die tatsächliche Zielzeit setzen
            target_time = time.time() + seconds

        # Countdown in separatem Thread starten, damit Hotkeys weiter funktionieren
        def countdown_worker():
            nonlocal target_time  # Zugriff auf target_time aus dem äußeren Scope
            with state.lock:
                state.countdown_active = True

            try:
                while not state.stop_event.is_set() and not state.quit_event.is_set():
                    # Verbleibende Zeit dynamisch berechnen (funktioniert für beide Fälle)
                    remaining = target_time - time.time()

                    if remaining <= 0:
                        break

                    # Zeige Countdown
                    print(f"\r{col('[COUNTDOWN]', 'cyan')} Noch {format_duration(remaining)}... ({col('CTRL+ALT+S', 'yellow')} zum Abbrechen)    ", end="", flush=True)

                    # Kurz warten
                    if state.stop_event.wait(0.5):
                        break  # Stop-Event wurde gesetzt

                if state.stop_event.is_set():
                    print(f"\n{col('[ABBRUCH]', 'yellow')} Zeitplan abgebrochen.")
                    state.stop_event.clear()  # Reset für nächsten Start
                    return

                if state.quit_event.is_set():
                    return

                # Zeit erreicht - starte Sequenz
                print(f"\n{col('[START]', 'green')} Zeit erreicht - starte Sequenz!")
                state.stop_event.clear()  # Reset falls gesetzt
                state.scheduled_start = True  # Überspringt Debug-Enter-Prompt
            finally:
                with state.lock:
                    state.countdown_active = False

            # Sequenz starten (außerhalb von finally, damit countdown_active schon False ist)
            handle_toggle(state)

        print(f"\n{col('[COUNTDOWN]', 'cyan')} Warte auf Startzeit... (Abbrechen mit {col('CTRL+ALT+S', 'yellow')})")
        countdown_thread = threading.Thread(target=countdown_worker, daemon=True)
        countdown_thread.start()
        # Kehre zur Haupt-Event-Loop zurück, damit Hotkeys funktionieren
        return

    except (KeyboardInterrupt, EOFError):
        print(f"\n{col('[ABBRUCH]', 'yellow')}")
    except ValueError as e:
        print(err(str(e)))


def handle_analyze(state: AutoClickerState) -> None:
    """Startet den Farb-Analysator."""
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
    run_color_analyzer()


def handle_quit(state: AutoClickerState, main_thread_id: int) -> None:
    """Beendet das Programm."""
    print(f"\n{col('[QUIT]', 'red')} Beende Programm...")

    state.stop_event.set()
    state.quit_event.set()

    WM_QUIT = 0x0012
    user32.PostThreadMessageW(main_thread_id, WM_QUIT, 0, 0)
