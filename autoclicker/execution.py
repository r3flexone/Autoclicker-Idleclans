"""
Sequenz-Ausführung für den Autoclicker.
Enthält die Worker-Funktion und Step-Ausführungslogik.
"""

import time
from typing import TYPE_CHECKING

from .config import CONFIG, MAX_TOTAL_CLICKS, CLICKS_PER_POINT
from .models import AutoClickerState, SequenceStep
from .winapi import (
    send_click, send_key, check_failsafe, set_cursor_pos
)
from .utils import clear_line, wait_while_paused, safe_input, format_duration
from .imaging import (
    PILLOW_AVAILABLE, take_screenshot, color_distance, get_color_name,
    PIXEL_WAIT_TIMEOUT, PIXEL_CHECK_INTERVAL, find_color_in_image,
    match_template_in_image
)

if TYPE_CHECKING:
    pass


def wait_with_pause_skip(state: AutoClickerState, seconds: float, phase: str, step_num: int,
                         total_steps: int, message: str) -> bool:
    """Wartet die angegebene Zeit, respektiert Pause und Skip. Gibt False zurück wenn gestoppt."""
    remaining = seconds
    debug_active = state.config.get("debug_mode", False) or state.config.get("debug_detection", False)
    last_remaining = -1

    while remaining > 0:
        if state.stop_event.is_set():
            return False

        if state.skip_event.is_set():
            state.skip_event.clear()
            if debug_active:
                print(f"[{phase}] Schritt {step_num}/{total_steps} | SKIP!")
            else:
                clear_line()
                print(f"[{phase}] Schritt {step_num}/{total_steps} | SKIP!", end="", flush=True)
            return True

        if not wait_while_paused(state, message):
            return False

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
        if step.else_delay > 0:
            if not wait_with_pause_skip(state, step.else_delay, phase, step_num, total_steps,
                                        f"ELSE: klicke in"):
                return False

        if state.stop_event.is_set():
            return False

        send_click(step.else_x, step.else_y, state.config.get("click_move_delay", 0.01),
                   state.config.get("post_click_delay", 0.05))
        with state.lock:
            state.total_clicks += 1
        name = step.else_name or f"({step.else_x},{step.else_y})"
        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | ELSE: Klick auf {name}!", end="", flush=True)
        return True

    elif step.else_action == "key":
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
        return False

    return True


def execute_item_scan(state: AutoClickerState, scan_name: str, mode: str = "all") -> list:
    """Führt einen Item-Scan aus und gibt Liste von (position, item, priority) zurück."""
    if scan_name not in state.item_scans:
        print(f"[FEHLER] Item-Scan '{scan_name}' nicht gefunden!")
        return []

    config = state.item_scans[scan_name]
    if not config.slots or not config.items:
        print(f"[FEHLER] Item-Scan '{scan_name}' hat keine Slots oder Items!")
        return []

    found_items = []
    slots_to_scan = list(config.slots)

    if state.config.get("scan_reverse", False):
        slots_to_scan = list(reversed(slots_to_scan))

    scan_delay = state.config.get("scan_slot_delay", 0.1)
    debug = state.config.get("debug_detection", False)

    for slot in slots_to_scan:
        if state.stop_event.is_set():
            break

        if scan_delay > 0 and slots_to_scan.index(slot) > 0:
            time.sleep(scan_delay)

        screenshot_start = time.time()
        img = take_screenshot(slot.scan_region)
        screenshot_ms = (time.time() - screenshot_start) * 1000

        if img is None:
            continue

        if debug:
            print(f"[DEBUG] Scanne {slot.name}... (Screenshot: {screenshot_ms:.0f}ms)")

        for item in config.items:
            template_ok = True
            template_info = ""
            marker_ok = True
            marker_info = ""

            # 1. Template-Matching (wenn vorhanden)
            if item.template:
                match, confidence, pos = match_template_in_image(
                    img, item.template, item.min_confidence
                )
                template_ok = match
                template_info = f"Template {confidence:.1%}" if match else f"Template {confidence:.1%} (min: {item.min_confidence:.0%})"

            # 2. Marker-Farben prüfen (wenn vorhanden)
            if item.marker_colors:
                tolerance = config.color_tolerance
                markers_total = len(item.marker_colors)
                markers_found = sum(1 for marker in item.marker_colors
                                   if find_color_in_image(img, marker, tolerance))

                # Config-Einstellungen für Marker-Anforderung
                require_all = state.config.get("require_all_markers", True)
                min_required = state.config.get("min_markers_required", 2)

                if require_all:
                    marker_ok = (markers_found == markers_total)
                else:
                    marker_ok = (markers_found >= min_required)

                marker_info = f"Marker {markers_found}/{markers_total}"

            # 3. Debug-Ausgabe
            if debug:
                # Kombiniere Info-Strings
                info_parts = []
                if item.template:
                    info_parts.append(template_info)
                if item.marker_colors:
                    info_parts.append(marker_info)

                if not info_parts:
                    print(f"[DEBUG]   → {item.name}: kein Template/Marker definiert")
                elif template_ok and marker_ok:
                    print(f"[DEBUG]   → {item.name} gefunden! ({', '.join(info_parts)})")
                else:
                    print(f"[DEBUG]   → {item.name}: {', '.join(info_parts)}")

            # 4. Item gefunden wenn Template UND Marker OK
            if template_ok and marker_ok and (item.template or item.marker_colors):
                found_items.append((slot, item, item.priority))
                break

    if not found_items:
        return []

    if mode == "every":
        print(f"[SCAN] {len(found_items)} Item(s) gefunden - klicke alle!")
        # Items werden in Scan-Reihenfolge geklickt (bei scan_reverse: von hinten nach vorne)
        return [(slot.click_pos, item, priority) for slot, item, priority in found_items]

    # Gruppiere nach Kategorie, aber behalte die Scan-Reihenfolge
    best_per_category = {}
    ordered_categories = []  # Reihenfolge merken
    for slot, item, priority in found_items:
        cat = item.category or item.name

        with state.lock:
            if cat in state.clicked_categories:
                best_clicked_prio = state.clicked_categories[cat]
                if priority >= best_clicked_prio:
                    if debug:
                        print(f"[DEBUG]   → {item.name} übersprungen ('{cat}' bereits geklickt)")
                    continue

        if cat not in best_per_category:
            ordered_categories.append(cat)  # Erste Kategorie-Erscheinung merken
            best_per_category[cat] = (slot, item, priority)
        elif priority < best_per_category[cat][2]:
            best_per_category[cat] = (slot, item, priority)

    # Items in Scan-Reihenfolge zurückgeben (bei scan_reverse: von hinten nach vorne)
    filtered_items = [best_per_category[cat] for cat in ordered_categories]

    if mode == "all":
        print(f"[SCAN] {len(filtered_items)} Item(s) gefunden - klicke alle!")
        return [(slot.click_pos, item, priority) for slot, item, priority in filtered_items]
    else:
        filtered_items.sort(key=lambda x: x[2])
        best_slot, best_item, best_priority = filtered_items[0]
        print(f"[SCAN] Bestes Item: {best_item.name} (P{best_priority})")
        return [(best_slot.click_pos, best_item, best_priority)]


def _execute_item_scan_step(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Item-Scan Schritt aus."""
    debug = state.config.get("debug_mode", False)
    mode = step.item_scan_mode
    mode_str = "alle" if mode == "all" else "bestes"

    if debug:
        print(f"[DEBUG] Starte Scan '{step.item_scan}' ({mode_str})...")
    else:
        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | Scan '{step.item_scan}' ({mode_str})...", end="", flush=True)

    scan_results = execute_item_scan(state, step.item_scan, mode)

    if scan_results:
        for i, (pos, item, priority) in enumerate(scan_results):
            if state.stop_event.is_set():
                return False

            if debug:
                print(f"[DEBUG] Item-Klick: '{item.name}' (P{priority}) @ ({pos[0]}, {pos[1]})")

            send_click(pos[0], pos[1], state.config.get("click_move_delay", 0.01),
                       state.config.get("post_click_delay", 0.05))
            with state.lock:
                state.total_clicks += 1
                state.items_found += 1
                cat = item.category or item.name
                if cat not in state.clicked_categories or priority < state.clicked_categories[cat]:
                    state.clicked_categories[cat] = priority

            if item.confirm_point is not None:
                if item.confirm_delay > 0:
                    if debug:
                        print(f"[DEBUG] Warte {item.confirm_delay}s vor Confirm...")
                    time.sleep(item.confirm_delay)

                if debug:
                    print(f"[DEBUG] Confirm-Klick @ ({item.confirm_point.x}, {item.confirm_point.y})")

                send_click(item.confirm_point.x, item.confirm_point.y,
                           state.config.get("click_move_delay", 0.01),
                           state.config.get("post_click_delay", 0.05))
                with state.lock:
                    state.total_clicks += 1

            click_delay = state.config.get("item_click_delay", 1.0)
            if click_delay > 0:
                time.sleep(click_delay)

        if debug:
            print(f"[DEBUG] Scan fertig: {len(scan_results)} Item(s) geklickt")
        else:
            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | {len(scan_results)} Item(s)!", end="", flush=True)
    else:
        if step.else_action:
            return execute_else_action(state, step, phase, step_num, total_steps)
        if debug:
            print(f"[DEBUG] Scan fertig: kein Item gefunden")
        else:
            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | Scan: kein Item gefunden", end="", flush=True)

    return True


def _execute_key_press_step(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Tastendruck-Schritt aus."""
    actual_delay = step.get_actual_delay()
    if actual_delay > 0:
        if not wait_with_pause_skip(state, actual_delay, phase, step_num, total_steps,
                                    f"Taste '{step.key_press}' in"):
            return False

    if state.stop_event.is_set():
        return False

    if send_key(step.key_press):
        with state.lock:
            state.key_presses += 1
        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | Taste '{step.key_press}'!", end="", flush=True)

    return True


def _execute_wait_for_color(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Wartet auf eine Farbe an einer Pixel-Position."""
    actual_delay = step.get_actual_delay()
    if actual_delay > 0:
        if not wait_with_pause_skip(state, actual_delay, phase, step_num, total_steps, "Vor Farbprüfung"):
            return False

    if state.config.get("show_pixel_position", False):
        set_cursor_pos(step.wait_pixel[0], step.wait_pixel[1])
        time.sleep(state.config.get("show_pixel_delay", 0.3))

    timeout = state.config.get("pixel_wait_timeout", PIXEL_WAIT_TIMEOUT)
    start_time = time.time()
    expected_name = get_color_name(step.wait_color)
    wait_mode = "WEG" if step.wait_until_gone else "DA"

    while not state.stop_event.is_set():
        if state.skip_event.is_set():
            state.skip_event.clear()
            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | SKIP Farbwarten!", end="", flush=True)
            break

        if not wait_while_paused(state, "Warte auf Farbe..."):
            break

        if PILLOW_AVAILABLE:
            img = take_screenshot((step.wait_pixel[0], step.wait_pixel[1],
                                   step.wait_pixel[0]+1, step.wait_pixel[1]+1))
            if img:
                current_color = img.getpixel((0, 0))[:3]
                dist = color_distance(current_color, step.wait_color)
                pixel_tolerance = state.config.get("pixel_wait_tolerance", 10)
                color_matches = dist <= pixel_tolerance
                condition_met = (not color_matches) if step.wait_until_gone else color_matches

                # Debug-Ausgabe: Zeige erwartete und aktuelle Farbe
                elapsed = time.time() - start_time
                debug = state.config.get("debug_mode", False)
                current_name = get_color_name(current_color)

                if condition_met:
                    msg = "Farbe weg!" if step.wait_until_gone else "Farbe erkannt!"
                    if debug:
                        print(f"[DEBUG] {msg} | Erwartet: {expected_name} RGB{step.wait_color} | Aktuell: {current_name} RGB{current_color} Dist={dist:.0f}")
                    else:
                        clear_line()
                        print(f"[{phase}] Schritt {step_num}/{total_steps} | {msg}", end="", flush=True)
                    break

                if debug:
                    # Debug: Auf neuer Zeile ausgeben (nicht überschreiben)
                    print(f"[DEBUG] Warte auf {expected_name} RGB{step.wait_color} ({elapsed:.0f}s) | Aktuell: {current_name} RGB{current_color} Dist={dist:.0f}")
                else:
                    # Ohne Debug: Auf gleicher Zeile überschreiben
                    clear_line()
                    print(f"[{phase}] Schritt {step_num}/{total_steps} | Warte auf {expected_name}... ({elapsed:.0f}s)", end="", flush=True)

        elapsed = time.time() - start_time
        if elapsed >= timeout:
            if step.else_action:
                clear_line()
                print(f"[{phase}] Schritt {step_num}/{total_steps} | TIMEOUT", end="", flush=True)
                return execute_else_action(state, step, phase, step_num, total_steps)
            print(f"\n[TIMEOUT] Farbe nicht erkannt nach {timeout}s!")
            state.stop_event.set()
            return False

        check_interval = state.config.get("pixel_check_interval", 1)
        if state.stop_event.wait(check_interval):
            return False

    return True


def _execute_click(state: AutoClickerState, step: SequenceStep,
                   step_num: int, total_steps: int, phase: str) -> bool:
    """Führt den eigentlichen Klick aus."""
    debug = state.config.get("debug_mode", False)
    clicks = state.config.get("clicks_per_point", CLICKS_PER_POINT)
    for _ in range(clicks):
        if state.stop_event.is_set():
            return False

        if check_failsafe(state):
            print("\n[FAILSAFE] Stoppe...")
            state.stop_event.set()
            return False

        send_click(step.x, step.y, state.config.get("click_move_delay", 0.01),
                   state.config.get("post_click_delay", 0.05))

        with state.lock:
            state.total_clicks += 1

        if debug:
            name = step.name if step.name else f"Punkt"
            print(f"[DEBUG] Klick auf '{name}' ({step.x}, {step.y}) | Gesamt: {state.total_clicks}")
        else:
            clear_line()
            print(f"[{phase}] Schritt {step_num}/{total_steps} | Klick! (Gesamt: {state.total_clicks})", end="", flush=True)

        max_clicks = state.config.get("max_total_clicks", MAX_TOTAL_CLICKS)
        if max_clicks and state.total_clicks >= max_clicks:
            print(f"\n[INFO] Maximum von {max_clicks} Klicks erreicht.")
            state.stop_event.set()
            return False

    return True


def execute_step(state: AutoClickerState, step: SequenceStep, step_num: int,
                 total_steps: int, phase: str) -> bool:
    """Führt einen einzelnen Schritt aus: Erst warten/prüfen, DANN klicken."""
    if check_failsafe(state):
        print("\n[FAILSAFE] Maus in Ecke erkannt! Stoppe...")
        state.stop_event.set()
        return False

    if state.config.get("debug_mode", False):
        print(f"[DEBUG] Step {step_num}: name='{step.name}', x={step.x}, y={step.y}")

    if step.item_scan:
        return _execute_item_scan_step(state, step, step_num, total_steps, phase)

    if step.key_press:
        return _execute_key_press_step(state, step, step_num, total_steps, phase)

    if step.wait_pixel and step.wait_color:
        if not _execute_wait_for_color(state, step, step_num, total_steps, phase):
            return False
    elif step.delay_before > 0 or step.delay_max:
        actual_delay = step.get_actual_delay()
        action = "Warten" if step.wait_only else "Klicke in"
        if not wait_with_pause_skip(state, actual_delay, phase, step_num, total_steps, action):
            return False

    if state.stop_event.is_set():
        return False

    if step.wait_only:
        clear_line()
        print(f"[{phase}] Schritt {step_num}/{total_steps} | Warten beendet (kein Klick)")
        return True

    return _execute_click(state, step, step_num, total_steps, phase)


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


def sequence_worker(state: AutoClickerState) -> None:
    """Worker-Thread, der die Sequenz ausführt."""
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

        if state.config.get("debug_mode", False):
            print("\n" + "=" * 60)
            print("[DEBUG] GELADENE SEQUENZ-SCHRITTE:")
            for i, step in enumerate(sequence.start_steps):
                print(f"  START[{i+1}]: {step.name or 'unnamed'}")
            for lp in sequence.loop_phases:
                print(f"  --- {lp.name} (x{lp.repeat}) ---")
                for i, step in enumerate(lp.steps):
                    print(f"  {lp.name}[{i+1}]: {step.name or 'unnamed'}")
            print("=" * 60)
            if not state.scheduled_start:
                print("[DEBUG] Drücke Enter zum Starten...")
                safe_input()
            state.scheduled_start = False

        state.total_clicks = 0
        state.items_found = 0
        state.key_presses = 0
        state.start_time = time.time()

    cycle_count = 0

    while not state.stop_event.is_set() and not state.quit_event.is_set():
        if state.restart_event.is_set():
            state.restart_event.clear()
            cycle_count = 0
            print("\n[RESTART] Sequenz wird neu gestartet...")

        cycle_count += 1

        with state.lock:
            state.clicked_categories.clear()

        if total_cycles > 0 and cycle_count > total_cycles:
            print(f"\n[FERTIG] Alle {total_cycles} Zyklen abgeschlossen!")
            break

        cycle_str = f"Zyklus {cycle_count}" if total_cycles == 0 else f"Zyklus {cycle_count}/{total_cycles}"

        # START-Phase
        if has_start and not state.stop_event.is_set():
            print(f"\n[START] Führe Start-Sequenz aus... ({cycle_str})")
            total_start = len(sequence.start_steps)

            for i, step in enumerate(sequence.start_steps):
                if state.stop_event.is_set() or state.quit_event.is_set():
                    break
                if not execute_step(state, step, i + 1, total_start, "START"):
                    break

            if state.restart_event.is_set():
                continue
            if state.stop_event.is_set():
                break

        # LOOP-Phasen
        if has_loops and not state.stop_event.is_set():
            for loop_phase in sequence.loop_phases:
                if state.stop_event.is_set() or state.quit_event.is_set():
                    break

                total_steps = len(loop_phase.steps)
                if total_steps == 0:
                    continue

                print(f"\n[{loop_phase.name}] Starte ({loop_phase.repeat}x) | {cycle_str}")

                for repeat_num in range(1, loop_phase.repeat + 1):
                    if state.stop_event.is_set() or state.quit_event.is_set():
                        break

                    if state.config.get("debug_mode", False):
                        print(f"[DEBUG] Loop {repeat_num}/{loop_phase.repeat} von '{loop_phase.name}'")

                    for i, step in enumerate(loop_phase.steps):
                        if state.stop_event.is_set() or state.quit_event.is_set():
                            break

                        phase_label = f"{loop_phase.name} #{repeat_num}/{loop_phase.repeat}"
                        if not execute_step(state, step, i + 1, total_steps, phase_label):
                            break

                    if state.restart_event.is_set():
                        break

                if state.restart_event.is_set():
                    break

                if not state.stop_event.is_set():
                    print(f"\n[{loop_phase.name}] Abgeschlossen.")

            if state.restart_event.is_set():
                continue
            if state.stop_event.is_set():
                break

        if state.restart_event.is_set():
            continue

        if not has_loops or total_cycles == 1:
            print("\n[FERTIG] Sequenz einmal durchgelaufen.")
            break

    # END-Phase
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
