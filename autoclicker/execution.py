"""
Sequenz-Ausführung für den Autoclicker.
Enthält die Worker-Funktion und Step-Ausführungslogik.
"""

import time
from datetime import datetime
from pathlib import Path

from .config import CONFIG
from .models import AutoClickerState, SequenceStep
from .winapi import (
    send_click, send_key, check_failsafe, set_cursor_pos
)
from .utils import clear_line, wait_while_paused, safe_input, format_duration, col, ok, err, info, hint, dbg
from .imaging import (
    PILLOW_AVAILABLE, take_screenshot, color_distance, get_color_name,
    find_color_in_image, match_template_in_image
)
from .persistence import SEQUENCE_SCREENSHOTS_DIR as SCREENSHOTS_DIR


def _phase_color(phase: str) -> str:
    """Gibt die Farbe für eine Phase zurück."""
    p = phase.upper()
    if p.startswith("INIT"):
        return "green"
    if p.startswith("START"):
        return "blue"
    if p.startswith("END"):
        return "cyan"
    return "magenta"


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
            _c = _phase_color(phase)
            if debug_active:
                print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SKIP!", _c))
            else:
                clear_line()
                print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SKIP!", _c), end="", flush=True)
            return True

        if not wait_while_paused(state, message):
            return False

        current_remaining = int(remaining)
        if current_remaining != last_remaining:
            _c = _phase_color(phase)
            if debug_active:
                print(col(f"[{phase}] Schritt {step_num}/{total_steps} | {message} ({round(remaining, 1):g}s)...", _c))
            else:
                clear_line()
                print(col(f"[{phase}] Schritt {step_num}/{total_steps} | {message} ({round(remaining, 1):g}s)...", _c), end="", flush=True)
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

    debug = state.config.get("debug_mode", False)

    _c = _phase_color(phase)

    if step.else_action == "skip":
        if debug:
            print(dbg("ELSE: übersprungen"))
        else:
            clear_line()
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | ELSE: übersprungen", _c), end="", flush=True)
        return True

    elif step.else_action == "click":
        if step.else_delay > 0:
            if not wait_with_pause_skip(state, step.else_delay, phase, step_num, total_steps,
                                        f"ELSE: klicke in"):
                return False

        if state.stop_event.is_set():
            return False

        name = step.else_name or f"({step.else_x},{step.else_y})"
        send_click(step.else_x, step.else_y, state.config.get("click_move_delay", 0.01),
                   state.config.get("post_click_delay", 0.05))
        with state.lock:
            state.total_clicks += 1

        if debug:
            print(dbg(f"ELSE: Klick auf '{name}' ({step.else_x}, {step.else_y})"))
        else:
            clear_line()
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | ELSE: Klick auf {name}!", _c), end="", flush=True)
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
            if debug:
                print(dbg(f"ELSE: Taste '{step.else_key}'"))
            else:
                clear_line()
                print(col(f"[{phase}] Schritt {step_num}/{total_steps} | ELSE: Taste '{step.else_key}'!", _c), end="", flush=True)
        return True

    elif step.else_action == "restart":
        if debug:
            print(dbg("ELSE: Neustart!"))
        else:
            clear_line()
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | ELSE: Neustart!", _c), end="", flush=True)
        state.restart_event.set()
        return False

    elif step.else_action == "skip_cycle":
        if debug:
            print(dbg("ELSE: Zyklus überspringen!"))
        else:
            clear_line()
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | ELSE: Zyklus überspringen!", _c), end="", flush=True)
        state.skip_cycle_event.set()
        return False

    return True


def execute_item_scan(state: AutoClickerState, scan_name: str, mode: str = "all",
                      slots_override: list = None) -> list:
    """Führt einen Item-Scan aus und gibt Liste von (position, item, priority) zurück.
    slots_override: Wenn gesetzt, werden nur diese Slots gescannt (ohne Reverse-Logik)."""
    if scan_name not in state.item_scans:
        print(err(f"Item-Scan '{scan_name}' nicht gefunden!"))
        return []

    config = state.item_scans[scan_name]
    if not config.slots or not config.items:
        print(err(f"Item-Scan '{scan_name}' hat keine Slots oder Items!"))
        return []

    found_items = []

    if slots_override is not None:
        slots_to_scan = list(slots_override)
    else:
        slots_to_scan = list(config.slots)
        if state.config.get("scan_reverse", False):
            slots_to_scan = list(reversed(slots_to_scan))

    scan_delay = state.config.get("scan_slot_delay", 0.1)
    debug = state.config.get("debug_detection", False)

    # Maus vor dem Scannen wegparken (verhindert Tooltip/Hover-Störungen)
    park_pos = state.config.get("scan_park_mouse", False)
    if isinstance(park_pos, (list, tuple)) and len(park_pos) == 2:
        set_cursor_pos(int(park_pos[0]), int(park_pos[1]))
        time.sleep(0.05)  # Kurz warten bis Maus angekommen & Tooltip weg

    for idx, slot in enumerate(slots_to_scan):
        if state.stop_event.is_set():
            break

        if scan_delay > 0 and idx > 0:
            time.sleep(scan_delay)

        screenshot_start = time.time()
        img = take_screenshot(slot.scan_region)
        screenshot_ms = (time.time() - screenshot_start) * 1000

        if img is None:
            continue

        if debug:
            size_info = f"{img.size[0]}x{img.size[1]}" if img else "?"
            print(dbg(f"Scanne {slot.name}... (Screenshot: {screenshot_ms:.0f}ms, {size_info}px)"))

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
                    print(dbg(f"  → {item.name}: kein Template/Marker definiert"))
                elif template_ok and marker_ok:
                    print(dbg(f"  → {item.name} gefunden! ({', '.join(info_parts)})"))
                else:
                    print(dbg(f"  → {item.name}: {', '.join(info_parts)})"))

            # 4. Item gefunden wenn Template UND Marker OK
            if template_ok and marker_ok and (item.template or item.marker_colors):
                found_items.append((slot, item, item.priority))
                break

    if not found_items:
        return []

    if mode == "every":
        print(col(f"[SCAN] {len(found_items)} Item(s) gefunden - klicke alle!", "cyan"))
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
                        print(dbg(f"  → {item.name} übersprungen ('{cat}' bereits geklickt)"))
                    continue

        if cat not in best_per_category:
            ordered_categories.append(cat)  # Erste Kategorie-Erscheinung merken
            best_per_category[cat] = (slot, item, priority)
        elif priority < best_per_category[cat][2]:
            best_per_category[cat] = (slot, item, priority)

    # Items in Scan-Reihenfolge zurückgeben (bei scan_reverse: von hinten nach vorne)
    filtered_items = [best_per_category[cat] for cat in ordered_categories]

    if mode == "all":
        print(col(f"[SCAN] {len(filtered_items)} Item(s) gefunden - klicke alle!", "cyan"))
        return [(slot.click_pos, item, priority) for slot, item, priority in filtered_items]
    else:
        if not filtered_items:
            return []
        filtered_items.sort(key=lambda x: x[2])
        best_slot, best_item, best_priority = filtered_items[0]
        print(col(f"[SCAN] Bestes Item: {best_item.name} (P{best_priority})", "cyan"))
        return [(best_slot.click_pos, best_item, best_priority)]


def _click_scan_result(state: AutoClickerState, pos, item, priority, debug: bool) -> None:
    """Klickt ein gefundenes Item (inkl. Confirm-Klick und Delays)."""
    if debug:
        print(dbg(f"Item-Klick: '{item.name}' (P{priority}) @ ({pos[0]}, {pos[1]})"))

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
                print(dbg(f"Warte {item.confirm_delay}s vor Confirm..."))
            time.sleep(item.confirm_delay)

        if debug:
            print(dbg(f"Confirm-Klick @ ({item.confirm_point.x}, {item.confirm_point.y})"))

        send_click(item.confirm_point.x, item.confirm_point.y,
                   state.config.get("click_move_delay", 0.01),
                   state.config.get("post_click_delay", 0.05))
        with state.lock:
            state.total_clicks += 1

    click_delay = state.config.get("item_click_delay", 1.0)
    if click_delay > 0:
        time.sleep(click_delay)


def _execute_item_scan_step(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Item-Scan Schritt aus."""
    debug = state.config.get("debug_mode", False)
    mode = step.item_scan_mode
    mode_str = "alle" if mode == "all" else "bestes"
    immediate = state.config.get("scan_click_immediate", False)

    if debug:
        im_str = " [IMMEDIATE]" if immediate else ""
        print(dbg(f"Starte Scan '{step.item_scan}' ({mode_str}{im_str})..."))
    else:
        clear_line()
        print(col(f"[{phase}] Schritt {step_num}/{total_steps} | Scan '{step.item_scan}' ({mode_str})...", _phase_color(phase)), flush=True)

    if immediate:
        return _execute_item_scan_immediate(state, step, step_num, total_steps, phase, mode, debug)

    scan_results = execute_item_scan(state, step.item_scan, mode)

    if scan_results:
        for i, (pos, item, priority) in enumerate(scan_results):
            if state.stop_event.is_set():
                return False
            _click_scan_result(state, pos, item, priority, debug)

        if debug:
            print(dbg(f"Scan fertig: {len(scan_results)} Item(s) geklickt"))
        else:
            clear_line()
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | {len(scan_results)} Item(s)!", _phase_color(phase)), end="", flush=True)
    else:
        if step.else_action:
            return execute_else_action(state, step, phase, step_num, total_steps)
        if debug:
            print(dbg("Scan fertig: kein Item gefunden"))
        else:
            clear_line()
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | Scan: kein Item gefunden", _phase_color(phase)), end="", flush=True)

    return True


def _execute_item_scan_immediate(state: AutoClickerState, step: SequenceStep,
                                  step_num: int, total_steps: int, phase: str,
                                  mode: str, debug: bool) -> bool:
    """Immediate-Modus: Scan→Klick pro Slot statt alle scannen, dann alle klicken."""
    config = state.item_scans.get(step.item_scan)
    if not config or not config.slots or not config.items:
        return True

    slots = list(config.slots)
    if state.config.get("scan_reverse", False):
        slots = list(reversed(slots))

    total_clicked = 0
    for slot in slots:
        if state.stop_event.is_set():
            return False

        # Einen einzelnen Slot scannen
        results = execute_item_scan(state, step.item_scan, mode, slots_override=[slot])

        if results:
            for pos, item, priority in results:
                if state.stop_event.is_set():
                    return False
                _click_scan_result(state, pos, item, priority, debug)
                total_clicked += 1

    if total_clicked > 0:
        if debug:
            print(dbg(f"Scan fertig: {total_clicked} Item(s) geklickt (immediate)"))
        else:
            clear_line()
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | {total_clicked} Item(s)!", _phase_color(phase)), end="", flush=True)
    else:
        if step.else_action:
            return execute_else_action(state, step, phase, step_num, total_steps)
        if debug:
            print(dbg("Scan fertig: kein Item gefunden (immediate)"))
        else:
            clear_line()
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | Scan: kein Item gefunden", _phase_color(phase)), end="", flush=True)

    return True


def _execute_key_press_step(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Tastendruck-Schritt aus."""
    debug = state.config.get("debug_mode", False)
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
        if debug:
            print(dbg(f"Taste '{step.key_press}' | Gesamt: {state.key_presses}"))
        else:
            clear_line()
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | Taste '{step.key_press}'!", _phase_color(phase)), end="", flush=True)

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

    timeout = state.config.get("pixel_wait_timeout", 30)
    start_time = time.time()
    expected_name = get_color_name(step.wait_color)

    while not state.stop_event.is_set():
        if state.skip_event.is_set():
            state.skip_event.clear()
            clear_line()
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SKIP Farbwarten!", _phase_color(phase)), end="", flush=True)
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
                        print(dbg(f"{msg} | Erwartet: {expected_name} RGB{step.wait_color} | Aktuell: {current_name} RGB{current_color} Dist={dist:.0f}"))
                    else:
                        clear_line()
                        print(col(f"[{phase}] Schritt {step_num}/{total_steps} | {msg}", _phase_color(phase)), end="", flush=True)
                    break

                if debug:
                    # Debug: Auf neuer Zeile ausgeben (nicht überschreiben)
                    print(dbg(f"Warte auf {expected_name} RGB{step.wait_color} ({elapsed:.0f}s) | Aktuell: {current_name} RGB{current_color} Dist={dist:.0f}"))
                else:
                    # Ohne Debug: Auf gleicher Zeile überschreiben
                    clear_line()
                    print(col(f"[{phase}] Schritt {step_num}/{total_steps} | Warte auf {expected_name}... ({elapsed:.0f}s)", _phase_color(phase)), end="", flush=True)

        elapsed = time.time() - start_time
        if timeout > 0 and elapsed >= timeout:
            with state.lock:
                state.timeouts += 1
            clear_line()
            print(col(f"\n[TIMEOUT] Farbe nicht erkannt nach {timeout}s!", "red"), end="", flush=True)
            if step.else_action:
                return execute_else_action(state, step, phase, step_num, total_steps)
            # Kein else definiert → globale Config-Option auswerten
            timeout_action = state.config.get("pixel_timeout_action", "skip_cycle")
            if timeout_action == "skip_cycle":
                print(col(f" → Zyklus wird übersprungen", "yellow"))
                state.skip_cycle_event.set()
            elif timeout_action == "restart":
                print(col(f" → Sequenz wird neu gestartet (inkl. INIT)", "yellow"))
                state.restart_event.set()
            else:
                print(col(f" → Stoppe.", "red"))
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
    clicks = state.config.get("clicks_per_point", 1)
    for _ in range(clicks):
        if state.stop_event.is_set():
            return False

        if check_failsafe(state):
            print(col("\n[FAILSAFE] Stoppe...", "red"))
            state.stop_event.set()
            return False

        send_click(step.x, step.y, state.config.get("click_move_delay", 0.01),
                   state.config.get("post_click_delay", 0.05))

        with state.lock:
            state.total_clicks += 1

        if debug:
            name = step.name if step.name else f"Punkt"
            print(dbg(f"Klick auf '{name}' ({step.x}, {step.y}) | Gesamt: {state.total_clicks}"))
        else:
            clear_line()
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | Klick! (Gesamt: {state.total_clicks})", _phase_color(phase)), end="", flush=True)

        max_clicks = state.config.get("max_total_clicks", None)
        if max_clicks and state.total_clicks >= max_clicks:
            print(f"\n{info(f'Maximum von {max_clicks} Klicks erreicht.')}")
            state.stop_event.set()
            return False

    return True


def _execute_screenshot_step(state: AutoClickerState, step: SequenceStep,
                              step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Screenshot-Schritt aus: macht ein Bild und speichert es."""
    if not PILLOW_AVAILABLE:
        print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SCREENSHOT übersprungen (Pillow fehlt)", "yellow"))
        return True

    region = step.screenshot_region  # (x1,y1,x2,y2) oder None
    img = take_screenshot(region)
    if img is None:
        print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SCREENSHOT fehlgeschlagen", "red"))
        return True  # Nicht als Fehler werten, Sequenz läuft weiter

    if not state.session_screenshots_dir:
        session_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        state.session_screenshots_dir = str(Path(SCREENSHOTS_DIR) / session_ts)
    screenshots_dir = Path(state.session_screenshots_dir)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"seq_{timestamp}.png"
    path = screenshots_dir / filename
    img.save(str(path))

    region_str = f"({region[0]},{region[1]})→({region[2]},{region[3]})" if region else "Vollbild"
    print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SCREENSHOT {region_str} → {filename}", _phase_color(phase)))
    return True


def execute_step(state: AutoClickerState, step: SequenceStep, step_num: int,
                 total_steps: int, phase: str) -> bool:
    """Führt einen einzelnen Schritt aus: Erst warten/prüfen, DANN klicken."""
    if check_failsafe(state):
        print(col("\n[FAILSAFE] Maus in Ecke erkannt! Stoppe...", "red"))
        state.stop_event.set()
        return False

    if state.config.get("debug_mode", False):
        print(dbg(f"Step {step_num}: name='{step.name}', x={step.x}, y={step.y}"))

    if step.screenshot_only:
        return _execute_screenshot_step(state, step, step_num, total_steps, phase)

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
        print(col(f"[{phase}] Schritt {step_num}/{total_steps} | Warten beendet (kein Klick)", _phase_color(phase)))
        return True

    return _execute_click(state, step, step_num, total_steps, phase)


def print_status(state: AutoClickerState) -> None:
    """Gibt den aktuellen Status aus."""
    with state.lock:
        is_running = state.is_running
        seq_name = state.active_sequence.name if state.active_sequence else "Keine"
        points_str = f"{len(state.points)} Punkt(e)"

        clear_line()
        if is_running and state.active_sequence:
            status_tag = col("[RUNNING]", "green")
            duration = format_duration(time.time() - state.start_time) if state.start_time else "0:00"
            stats = f"Klicks: {state.total_clicks}"
            if state.items_found > 0:
                stats += f" | Items: {state.items_found}"
            print(f"{status_tag} {seq_name} | {stats} | {hint(duration)}", flush=True)
        else:
            # "BEREIT" wenn noch nie gestartet, "STOPPED" wenn Sequenz lief und gestoppt wurde
            if state.total_clicks > 0:
                status_tag = col("[STOPPED]", "red")
            else:
                status_tag = col("[BEREIT]", "green")
            if state.active_sequence:
                _seq = state.active_sequence
                init_part = f"Init: {len(_seq.init_steps)}, " if _seq.init_steps else ""
                seq_info = f"{init_part}Loops: {len(_seq.loop_phases)}"
                print(f"{status_tag} {points_str} | Sequenz: {col(seq_name, 'cyan')} ({seq_info})", flush=True)
            else:
                print(f"{status_tag} {points_str} | Sequenz: {seq_name}", flush=True)


def sequence_worker(state: AutoClickerState) -> None:
    """Worker-Thread, der die Sequenz ausführt."""
    print(col("\n[START] Sequenz gestartet.", "green"))

    with state.lock:
        sequence = state.active_sequence
        if not sequence:
            print(err("Keine gültige Sequenz!"))
            state.is_running = False
            return

        has_init = len(sequence.init_steps) > 0
        has_loops = len(sequence.loop_phases) > 0
        has_end = len(sequence.end_steps) > 0
        total_cycles = sequence.total_cycles

        if not has_init and not has_loops:
            print(err("Sequenz ist leer!"))
            state.is_running = False
            return

        if state.config.get("debug_mode", False):
            print("\n" + col("=" * 60, 'gray'))
            print(dbg("GELADENE SEQUENZ-SCHRITTE:"))
            for i, step in enumerate(sequence.init_steps):
                print(col(f"  INIT[{i+1}]: {step.name or 'unnamed'}", 'green'))
            for lp in sequence.loop_phases:
                print(col(f"  --- {lp.name} (x{lp.repeat}) ---", 'magenta'))
                for i, step in enumerate(lp.steps):
                    print(col(f"  {lp.name}[{i+1}]: {step.name or 'unnamed'}", 'magenta'))
            print(col("=" * 60, 'gray'))
            if not state.scheduled_start:
                print(dbg("Drücke Enter zum Starten..."))
                safe_input()
            state.scheduled_start = False

        state.total_clicks = 0
        state.items_found = 0
        state.key_presses = 0
        state.skipped_cycles = 0
        state.restarts = 0
        state.timeouts = 0
        state.start_time = time.time()
        state.session_screenshots_dir = None  # Wird beim ersten Screenshot-Schritt angelegt
        state.finish_event.clear()

    # Äußere Schleife: Ermöglicht kompletten Neustart (inkl. INIT) bei restart_event
    do_restart = True  # Erster Durchlauf startet immer
    while do_restart and not state.stop_event.is_set() and not state.quit_event.is_set():
        do_restart = False

        # INIT-Phase
        if has_init and not state.stop_event.is_set():
            print(col("\n[INIT] Führe Initialisierung aus...", "green"))
            total_init = len(sequence.init_steps)
            for i, step in enumerate(sequence.init_steps):
                if state.stop_event.is_set() or state.quit_event.is_set():
                    break
                if not execute_step(state, step, i + 1, total_init, "INIT"):
                    break
            if not state.stop_event.is_set() and not state.quit_event.is_set():
                print(col("\n[INIT] Initialisierung abgeschlossen.", "green"))

        cycle_count = 0

        while not state.stop_event.is_set() and not state.quit_event.is_set():
            if state.skip_cycle_event.is_set():
                state.skip_cycle_event.clear()
                with state.lock:
                    state.skipped_cycles += 1
                print(col("\n[SKIP] Zyklus übersprungen, starte nächsten...", "yellow"))

            if state.restart_event.is_set():
                state.restart_event.clear()
                do_restart = True
                with state.lock:
                    state.restarts += 1
                print(col("\n[RESTART] Kompletter Neustart (inkl. INIT)...", "yellow"))
                break  # Bricht innere Schleife ab → äußere Schleife startet INIT erneut

            cycle_count += 1

            with state.lock:
                state.clicked_categories.clear()

            if total_cycles > 0 and cycle_count > total_cycles:
                print(f"\n{ok(f'Alle {total_cycles} Zyklen abgeschlossen!')}")
                break

            cycle_str = f"Zyklus {cycle_count}" if total_cycles == 0 else f"Zyklus {cycle_count}/{total_cycles}"

            # LOOP-Phasen
            if has_loops and not state.stop_event.is_set():
                for loop_phase in sequence.loop_phases:
                    if state.stop_event.is_set() or state.quit_event.is_set():
                        break

                    total_steps = len(loop_phase.steps)
                    if total_steps == 0:
                        continue

                    print(col(f"\n[{loop_phase.name}] Starte ({loop_phase.repeat}x) | {cycle_str}", "magenta"))

                    for repeat_num in range(1, loop_phase.repeat + 1):
                        if state.stop_event.is_set() or state.quit_event.is_set():
                            break

                        if state.config.get("debug_mode", False):
                            print(dbg(f"Loop {repeat_num}/{loop_phase.repeat} von '{loop_phase.name}'"))

                        for i, step in enumerate(loop_phase.steps):
                            if state.stop_event.is_set() or state.quit_event.is_set():
                                break

                            phase_label = f"{loop_phase.name} #{repeat_num}/{loop_phase.repeat}"
                            if not execute_step(state, step, i + 1, total_steps, phase_label):
                                break

                        if state.skip_cycle_event.is_set() or state.restart_event.is_set():
                            break

                    if state.skip_cycle_event.is_set() or state.restart_event.is_set():
                        break

                    if not state.stop_event.is_set() and not state.skip_cycle_event.is_set():
                        print(col(f"\n[{loop_phase.name}] Abgeschlossen.", "magenta"))

                if state.skip_cycle_event.is_set():
                    continue
                if state.restart_event.is_set():
                    continue  # → wird oben in der inneren Schleife per break behandelt
                if state.stop_event.is_set():
                    break

            if state.skip_cycle_event.is_set():
                continue
            if state.restart_event.is_set():
                continue

            if not has_loops or total_cycles == 1:
                print(f"\n{ok('Sequenz einmal durchgelaufen.')}")
                break

            if state.finish_event.is_set():
                print(f"\n{ok('Sanfter Abbruch: Zyklus abgeschlossen.')}")
                break

    # END-Phase
    if has_end and not state.quit_event.is_set():
        print(col("\n[END] Führe End-Sequenz aus...", "cyan"))
        total_end = len(sequence.end_steps)

        for i, step in enumerate(sequence.end_steps):
            if state.quit_event.is_set():
                break
            execute_step(state, step, i + 1, total_end, "END")

        if not state.quit_event.is_set():
            print(col("\n[END] End-Sequenz abgeschlossen.", "cyan"))

    with state.lock:
        state.is_running = False
        duration = time.time() - state.start_time if state.start_time else 0

    print(col("\n[STOP] Sequenz gestoppt.", "red"))
    print(col("-" * 50, 'cyan'))
    print(col("STATISTIKEN:", 'bold'))
    print(f"  {col('Laufzeit:', 'cyan'):22s} {format_duration(duration)}")
    print(f"  {col('Zyklen:', 'cyan'):22s} {cycle_count}")
    print(f"  {col('Klicks:', 'cyan'):22s} {state.total_clicks}")
    if state.items_found > 0:
        print(f"  {col('Items:', 'cyan'):22s} {state.items_found}")
    if state.key_presses > 0:
        print(f"  {col('Tasten:', 'cyan'):22s} {state.key_presses}")
    if state.timeouts > 0:
        print(f"  {col('Timeouts:', 'yellow'):22s} {state.timeouts}")
    if state.skipped_cycles > 0:
        print(f"  {col('Übersprungen:', 'yellow'):22s} {state.skipped_cycles}")
    if state.restarts > 0:
        print(f"  {col('Neustarts:', 'yellow'):22s} {state.restarts}")
    print(col("-" * 50, 'cyan'))
    print_status(state)
