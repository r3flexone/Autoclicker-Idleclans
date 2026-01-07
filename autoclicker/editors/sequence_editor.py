"""
Sequenz-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Klick-Sequenzen.
"""

import time
from typing import Optional

from ..models import ClickPoint, SequenceStep, LoopPhase, Sequence, AutoClickerState
from ..utils import safe_input
from ..winapi import get_cursor_pos, VK_CODES
from ..persistence import (
    save_data, list_available_sequences, load_sequence_file,
    get_next_point_id, get_point_by_id
)
from ..imaging import PILLOW_AVAILABLE, OPENCV_AVAILABLE, take_screenshot, get_pixel_color, select_region



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
            choice = safe_input("> ").strip().lower()

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


def run_sequence_loader(state: AutoClickerState) -> None:
    """Lädt eine gespeicherte Sequenz."""
    sequences = list_available_sequences()

    if not sequences:
        print("\n[INFO] Keine Sequenzen gefunden!")
        print("       Erstelle eine mit CTRL+ALT+E (Sequenz-Editor)")
        return

    print("\n" + "-" * 40)
    print("SEQUENZ LADEN")
    print("-" * 40)

    for i, (name, path) in enumerate(sequences):
        seq = load_sequence_file(path)
        if seq:
            active_marker = " <" if state.active_sequence and state.active_sequence.name == seq.name else ""
            print(f"  {i+1}. {seq}{active_marker}")

    print("\nNummer eingeben (Enter = abbrechen):")

    while True:
        try:
            choice = safe_input("> ").strip()
            if not choice:
                return

            idx = int(choice) - 1
            if 0 <= idx < len(sequences):
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
        seq_name = safe_input("Name der Sequenz: ").strip()
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
        print("\nAblauf: START -> Loop1 -> Loop2 -> ... -> (wieder von vorne?)")
        print("\nWie oft soll der GESAMTE Ablauf wiederholt werden?")
        print("  0 = Unendlich (manuell stoppen)")
        print("  1 = Einmal durchlaufen und stoppen")
        print("  >1 = X-mal wiederholen (START -> alle Loops -> START -> ...)")
        try:
            cycles_input = safe_input(f"\nAnzahl Zyklen (Enter = {total_cycles}): ").strip()
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
            user_input = safe_input(f"{prompt} > ").strip().lower()

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
                loop_name = safe_input(f"  Name der Loop-Phase (Enter = 'Loop {loop_num}'): ").strip()
                if not loop_name:
                    loop_name = f"Loop {loop_num}"

                print(f"\n  Schritte für {loop_name} hinzufügen:")
                steps = edit_phase(state, [], loop_name)
                if steps is None:
                    return None  # Abbruch durchreichen

                repeat = 1
                try:
                    repeat_input = safe_input(f"  Wie oft soll {loop_name} wiederholt werden? (Enter = 1): ").strip()
                    if repeat_input:
                        repeat = max(1, int(repeat_input))
                except ValueError:
                    repeat = 1

                loop_phases.append(LoopPhase(loop_name, steps, repeat))
                print(f"  + {loop_name} hinzugefügt ({len(steps)} Schritte x{repeat})")
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
                            repeat_input = safe_input(f"  Wiederholungen (aktuell {lp.repeat}, Enter = behalten): ").strip()
                            if repeat_input:
                                lp.repeat = max(1, int(repeat_input))
                        except ValueError:
                            pass
                        print(f"  + {lp.name} aktualisiert")
                    else:
                        print(f"  -> Ungültige Nr! Verfügbar: 1-{len(loop_phases)}")
                except ValueError:
                    print("  -> Format: edit <Nr>")
                continue

            elif user_input == "del all":
                if not loop_phases:
                    print("  -> Keine Loop-Phasen vorhanden!")
                    continue
                confirm = safe_input(f"  {len(loop_phases)} Loop-Phase(n) wirklich löschen? (j/n): ").strip().lower()
                if confirm == "j":
                    count = len(loop_phases)
                    loop_phases.clear()
                    print(f"  + {count} Loop-Phase(n) gelöscht!")
                else:
                    print("  -> Abgebrochen")
                continue

            elif user_input.startswith("del ") and "-" in user_input[4:]:
                # Bereich löschen: del 1-3
                try:
                    range_part = user_input[4:]
                    start, end = map(int, range_part.split("-"))
                    if start < 1 or end > len(loop_phases) or start > end:
                        print(f"  -> Ungültiger Bereich! Verfügbar: 1-{len(loop_phases)}")
                        continue
                    count = end - start + 1
                    confirm = safe_input(f"  {count} Loop-Phase(n) ({start}-{end}) wirklich löschen? (j/n): ").strip().lower()
                    if confirm == "j":
                        del loop_phases[start-1:end]
                        print(f"  + {count} Loop-Phase(n) gelöscht!")
                    else:
                        print("  -> Abgebrochen")
                except ValueError:
                    print("  -> Format: del <Nr>-<Nr>")
                continue

            elif user_input.startswith("del "):
                try:
                    del_num = int(user_input[4:])
                    if 1 <= del_num <= len(loop_phases):
                        removed = loop_phases.pop(del_num - 1)
                        print(f"  + {removed.name} gelöscht")
                    else:
                        print(f"  -> Ungültige Nr! Verfügbar: 1-{len(loop_phases)}")
                except ValueError:
                    print("  -> Format: del <Nr>")
                continue

            else:
                print("  -> Unbekannter Befehl")

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
        print(f"  -> Unbekannte Taste: '{key_name}'")
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
                print(f"  -> Punkt #{point_id} nicht gefunden!")
                return {}
    except ValueError:
        pass

    print(f"  -> Unbekanntes ELSE-Format: {' '.join(else_parts)}")
    print("     Formate: else skip | else restart | else <Nr> [delay] | else key <Taste>")
    return {}


def _apply_else_to_step(step: SequenceStep, else_parts: list[str], state: AutoClickerState) -> None:
    """Wendet geparste Else-Bedingung auf einen Step an."""
    if else_parts:
        else_result = parse_else_condition(else_parts, state)
        step.else_action = else_result.get("else_action")
        step.else_x = else_result.get("else_x", 0)
        step.else_y = else_result.get("else_y", 0)
        step.else_delay = else_result.get("else_delay", 0)
        step.else_key = else_result.get("else_key")
        step.else_name = else_result.get("else_name", "")


def _select_pixel_for_wait() -> Optional[tuple]:
    """Wählt einen Pixel für wait pixel/gone aus.

    Returns:
        Tuple (x, y, color) oder None bei Fehler.
    """
    if not PILLOW_AVAILABLE:
        print("  -> Pillow nicht installiert!")
        return None
    print("  Bewege Maus zum Pixel, dann Enter...")
    safe_input()
    x, y = get_cursor_pos()
    color = get_pixel_color(x, y)
    if not color:
        print("  -> Farbe konnte nicht gelesen werden!")
        return None
    return (x, y, color)


def _parse_number_wait(parts: list[str], op_idx: int, target_idx: int, format_hint: str) -> Optional[dict]:
    """Parst Number-Wait-Parameter und wählt Region aus.

    Args:
        parts: Liste der zu parsenden Teile
        op_idx: Index des Operators in parts
        target_idx: Index des Zielwerts in parts
        format_hint: Formathinweis für Fehlermeldung

    Returns:
        Dict mit region, operator, target, text_color oder None bei Fehler.
    """
    if not OPENCV_AVAILABLE or not PILLOW_AVAILABLE:
        print("  -> OpenCV und Pillow erforderlich!")
        return None

    from ..number_recognition import get_learned_digits, DIGIT_CHARS, load_digit_config
    learned = get_learned_digits()
    digits_learned = [d for d in DIGIT_CHARS if d in learned]
    if len(digits_learned) < 5:
        print(f"  -> Nur {len(digits_learned)}/10 Ziffern gelernt!")
        print("     Lerne Ziffern mit CTRL+ALT+N -> Option 4")
        return None

    if len(parts) <= target_idx:
        print(f"  -> Format: {format_hint}")
        return None

    operator = parts[op_idx]
    if operator not in (">", "<", "=", ">=", "<=", "!=", "=="):
        print(f"  -> Ungültiger Operator: '{operator}'")
        print("     Erlaubt: >, <, =, >=, <=, !=")
        return None

    try:
        target_str = parts[target_idx].lower().replace(",", "")
        multiplier = 1
        if target_str.endswith("k"):
            multiplier = 1_000
            target_str = target_str[:-1]
        elif target_str.endswith("m"):
            multiplier = 1_000_000
            target_str = target_str[:-1]
        elif target_str.endswith("b"):
            multiplier = 1_000_000_000
            target_str = target_str[:-1]
        target_value = float(target_str) * multiplier
    except ValueError:
        print(f"  -> Ungültige Zahl: '{parts[target_idx]}'")
        return None

    print(f"\n  Wähle den Bereich wo die Zahl angezeigt wird:")
    print("  (Der Bereich kann größer sein als die Zahl)")
    region = select_region()
    if not region:
        print("  -> Abgebrochen")
        return None

    config = load_digit_config()
    text_color = None
    if config.get("text_color"):
        text_color = tuple(config["text_color"])
        print(f"  Verwende gelernte Textfarbe: RGB{text_color}")
    else:
        print("  Textfarbe definieren? (j/n, Enter=n)")
        if safe_input("  > ").strip().lower() == "j":
            print("  Bewege Maus auf eine Ziffer, Enter...")
            safe_input()
            px, py = get_cursor_pos()
            text_color = get_pixel_color(px, py)
            if text_color:
                print(f"  -> Textfarbe: RGB{text_color}")

    return {
        "region": region,
        "operator": operator,
        "target": target_value,
        "text_color": text_color
    }


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
    print("  wait number >|<|= <Zahl> - Auf Zahl warten (z.B. 'wait number > 100')")
    print("  <Nr> number >|<|= <Zahl> - Warte auf Zahl, dann klicke")
    print("  wait scan <Name>  - Warte bis Item gefunden (kein Klick)")
    print("  wait scan <Name> \"Item\" - Warte auf bestimmtes Item")
    print("  wait scan gone <Name> - Warte bis KEIN Item mehr da")
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
            print(f"  + Eingefügt an Position {insert_position}: {step}")
            insert_position = None  # Reset nach Einfügen
        else:
            steps.append(step)
            print(f"  + Hinzugefügt: {step}")

    while True:
        try:
            # Zeige Insert-Modus im Prompt an
            if insert_position is not None:
                prompt = f"[{phase_name}: {len(steps)}] (ins->{insert_position})"
            else:
                prompt = f"[{phase_name}: {len(steps)}]"
            user_input = safe_input(f"{prompt} > ").strip()

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
                    print("  -> Keine Schritte vorhanden!")
                    continue
                count = len(steps)
                steps.clear()
                print(f"  + Alle {count} Schritte gelöscht")
                continue
            elif user_input.lower().startswith("del ") and "-" in user_input[4:]:
                # Bereich löschen: del 1-5
                try:
                    range_str = user_input[4:].strip()
                    parts = range_str.split("-")
                    start = int(parts[0])
                    end = int(parts[1])
                    if start < 1 or end > len(steps) or start > end:
                        print(f"  -> Ungültiger Bereich! Verfügbar: 1-{len(steps)}")
                        continue
                    # Von hinten löschen um Indexe nicht zu verschieben
                    removed_count = 0
                    for i in range(end, start - 1, -1):
                        steps.pop(i - 1)
                        removed_count += 1
                    print(f"  + {removed_count} Schritte gelöscht ({start}-{end})")
                except (ValueError, IndexError):
                    print("  -> Format: del <start>-<end> (z.B. del 1-5)")
                continue
            elif user_input.lower().startswith("del "):
                try:
                    del_num = int(user_input[4:])
                    if 1 <= del_num <= len(steps):
                        removed = steps.pop(del_num - 1)
                        print(f"  + Schritt {del_num} gelöscht: {removed}")
                    else:
                        print(f"  -> Ungültiger Schritt! Verfügbar: 1-{len(steps)}")
                except ValueError:
                    print("  -> Format: del <Nr>")
                continue

            elif user_input.lower().startswith("ins "):
                # Insert-Modus: nächster Schritt wird an Position eingefügt
                try:
                    pos = int(user_input[4:])
                    if pos < 1:
                        print("  -> Position muss >= 1 sein!")
                        continue
                    if pos > len(steps) + 1:
                        print(f"  -> Position zu groß! Max: {len(steps) + 1}")
                        continue
                    insert_position = pos
                    print(f"  + Insert-Modus: Nächster Schritt wird an Position {pos} eingefügt")
                    print(f"    (Abbrechen mit 'ins 0' oder 'ins end')")
                except ValueError:
                    print("  -> Format: ins <Nr>")
                continue

            elif user_input.lower() in ("ins 0", "ins end"):
                if insert_position is not None:
                    insert_position = None
                    print("  + Insert-Modus beendet - Schritte werden wieder am Ende angefügt")
                else:
                    print("  -> Insert-Modus war nicht aktiv")
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
                    point_name = safe_input("  Punkt-Name: ").strip()
                    if not point_name or point_name.lower() in ("cancel", "abbruch"):
                        print("  -> Abgebrochen")
                        continue

                print(f"\n  Bewege die Maus zur Position für '{point_name}'")
                print("  Drücke Enter...")
                safe_input()
                x, y = get_cursor_pos()

                with state.lock:
                    new_id = get_next_point_id(state)
                    new_point = ClickPoint(x, y, point_name, new_id)
                    state.points.append(new_point)

                save_data(state)
                print(f"  + Punkt #{new_id} '{point_name}' erstellt bei ({x}, {y})")
                continue

            # === SCAN-BEFEHL ===
            elif user_input.lower().startswith("scan "):
                parts_raw = user_input.split()
                # Parse else-Bedingung
                else_parts = []
                main_parts = []
                in_else = False
                for p in parts_raw[1:]:  # Skip "scan"
                    if p.lower() == "else":
                        in_else = True
                        continue
                    if in_else:
                        else_parts.append(p)
                    else:
                        main_parts.append(p)

                if not main_parts:
                    print("  -> Format: scan <Name> [best|every] [else ...]")
                    continue

                scan_name = main_parts[0]
                mode = "all"
                if len(main_parts) > 1:
                    mode_str = main_parts[1].lower()
                    if mode_str in ("best", "every"):
                        mode = mode_str

                step = SequenceStep(
                    x=0, y=0, delay_before=0,
                    name=f"Scan:{scan_name}",
                    item_scan=scan_name,
                    item_scan_mode=mode
                )

                _apply_else_to_step(step, else_parts, state)

                add_step(step)
                continue

            # === KEY-BEFEHL ===
            elif user_input.lower().startswith("key "):
                parts = user_input.split()
                if len(parts) < 2:
                    print("  -> Format: key <Taste> oder key <Zeit> <Taste>")
                    continue

                # key <Taste> oder key <Zeit> <Taste>
                delay = 0
                key_name = None

                if len(parts) == 2:
                    # key <Taste>
                    key_name = parts[1].lower()
                else:
                    # key <Zeit> <Taste>
                    try:
                        delay = float(parts[1])
                        key_name = parts[2].lower()
                    except ValueError:
                        key_name = parts[1].lower()

                if key_name not in VK_CODES:
                    print(f"  -> Unbekannte Taste: '{key_name}'")
                    print(f"     Verfügbar: {', '.join(sorted(VK_CODES.keys())[:20])}...")
                    continue

                step = SequenceStep(
                    x=0, y=0, delay_before=delay,
                    name=f"Key:{key_name}",
                    key_press=key_name
                )
                add_step(step)
                continue

            # === WAIT-BEFEHL ===
            elif user_input.lower().startswith("wait "):
                parts_raw = user_input.split()
                # Parse else-Bedingung
                else_parts = []
                main_parts = []
                in_else = False
                for p in parts_raw[1:]:  # Skip "wait"
                    if p.lower() == "else":
                        in_else = True
                        continue
                    if in_else:
                        else_parts.append(p)
                    else:
                        main_parts.append(p)

                if not main_parts:
                    print("  -> Format: wait <Zeit> oder wait pixel oder wait gone")
                    continue

                arg = main_parts[0].lower()
                step = SequenceStep(x=0, y=0, delay_before=0, name="Wait", wait_only=True)

                if arg == "pixel":
                    # wait pixel - Farbe abfragen
                    pixel_result = _select_pixel_for_wait()
                    if not pixel_result:
                        continue
                    step.wait_pixel = (pixel_result[0], pixel_result[1])
                    step.wait_color = pixel_result[2]
                    step.name = "Wait:Pixel"
                elif arg == "gone":
                    # wait gone - Farbe weg
                    pixel_result = _select_pixel_for_wait()
                    if not pixel_result:
                        continue
                    step.wait_pixel = (pixel_result[0], pixel_result[1])
                    step.wait_color = pixel_result[2]
                    step.wait_until_gone = True
                    step.name = "Wait:Gone"
                elif arg == "number":
                    # wait number > 100 - Auf Zahl warten
                    num_result = _parse_number_wait(main_parts, 1, 2, "wait number > 100 oder wait number < 50")
                    if not num_result:
                        continue
                    step.wait_number_region = num_result["region"]
                    step.wait_number_operator = num_result["operator"]
                    step.wait_number_target = num_result["target"]
                    step.wait_number_color = num_result["text_color"]
                    target_val = num_result["target"]
                    target_display = f"{target_val:,.0f}" if target_val == int(target_val) else f"{target_val:,.2f}"
                    step.name = f"Wait:Number{num_result['operator']}{target_display}"
                elif arg == "scan":
                    # wait scan <Name> oder wait scan gone <Name> oder wait scan <Name> "Item"
                    if len(main_parts) < 2:
                        print("  -> Format: wait scan <Name> oder wait scan gone <Name>")
                        continue

                    # Prüfe ob "gone" als zweites Argument
                    gone_mode = False
                    scan_name = None
                    item_filter = None

                    if main_parts[1].lower() == "gone":
                        gone_mode = True
                        if len(main_parts) < 3:
                            print("  -> Format: wait scan gone <Name>")
                            continue
                        scan_name = main_parts[2]
                        # Optional: Item-Filter nach scan_name
                        if len(main_parts) > 3:
                            item_filter = " ".join(main_parts[3:]).strip('"\'')
                    else:
                        scan_name = main_parts[1]
                        # Optional: Item-Filter nach scan_name
                        if len(main_parts) > 2:
                            item_filter = " ".join(main_parts[2:]).strip('"\'')

                    # Prüfe ob Scan existiert
                    with state.lock:
                        if scan_name not in state.item_scans:
                            print(f"  -> Item-Scan '{scan_name}' nicht gefunden!")
                            if state.item_scans:
                                print(f"     Verfügbar: {', '.join(state.item_scans.keys())}")
                            continue

                    step.wait_scan = scan_name
                    step.wait_scan_item = item_filter
                    step.wait_scan_gone = gone_mode
                    if gone_mode:
                        item_str = f" '{item_filter}'" if item_filter else ""
                        step.name = f"Wait:ScanGone:{scan_name}{item_str}"
                    else:
                        item_str = f" '{item_filter}'" if item_filter else ""
                        step.name = f"Wait:Scan:{scan_name}{item_str}"
                else:
                    # wait <Zeit> oder wait <Min>-<Max>
                    if "-" in arg:
                        try:
                            min_val, max_val = map(float, arg.split("-"))
                            step.delay_before = min_val
                            step.delay_max = max_val
                            step.name = f"Wait:{min_val}-{max_val}s"
                        except ValueError:
                            print("  -> Format: wait <Min>-<Max>")
                            continue
                    else:
                        try:
                            step.delay_before = float(arg)
                            step.name = f"Wait:{arg}s"
                        except ValueError:
                            print("  -> Format: wait <Zeit>")
                            continue

                _apply_else_to_step(step, else_parts, state)

                add_step(step)
                continue

            # === PUNKT-BEFEHL (Standard) ===
            else:
                parts_raw = user_input.split()
                # Parse else-Bedingung
                else_parts = []
                main_parts = []
                in_else = False
                for p in parts_raw:
                    if p.lower() == "else":
                        in_else = True
                        continue
                    if in_else:
                        else_parts.append(p)
                    else:
                        main_parts.append(p)

                if not main_parts:
                    print("  -> Unbekannter Befehl")
                    continue

                # Punkt-ID
                try:
                    point_id = int(main_parts[0])
                except ValueError:
                    print("  -> Unbekannter Befehl")
                    continue

                with state.lock:
                    point = get_point_by_id(state, point_id)
                    if not point:
                        print(f"  -> Punkt #{point_id} nicht gefunden!")
                        continue

                # Delay und Optionen
                delay = 0
                delay_max = None
                wait_pixel = None
                wait_color = None
                wait_until_gone = False

                if len(main_parts) > 1:
                    arg = main_parts[1].lower()

                    if arg == "pixel":
                        # <Nr> pixel
                        pixel_result = _select_pixel_for_wait()
                        if pixel_result:
                            wait_pixel = (pixel_result[0], pixel_result[1])
                            wait_color = pixel_result[2]
                    elif arg == "gone":
                        # <Nr> gone
                        pixel_result = _select_pixel_for_wait()
                        if pixel_result:
                            wait_pixel = (pixel_result[0], pixel_result[1])
                            wait_color = pixel_result[2]
                            wait_until_gone = True
                    elif arg == "number":
                        # <Nr> number > 100 - Warte auf Zahl, dann klicke
                        num_result = _parse_number_wait(main_parts, 2, 3, "<Nr> number > 100")
                        if not num_result:
                            continue

                        target_val = num_result["target"]
                        target_display = f"{target_val:,.0f}" if target_val == int(target_val) else f"{target_val:,.2f}"
                        step = SequenceStep(
                            x=point.x, y=point.y, delay_before=0,
                            name=point.name or f"#{point_id}",
                            wait_number_region=num_result["region"],
                            wait_number_operator=num_result["operator"],
                            wait_number_target=target_val,
                            wait_number_color=num_result["text_color"]
                        )

                        _apply_else_to_step(step, else_parts, state)

                        add_step(step)
                        continue
                    elif "-" in arg:
                        # <Nr> <Min>-<Max>
                        try:
                            min_val, max_val = map(float, arg.split("-"))
                            delay = min_val
                            delay_max = max_val
                        except ValueError:
                            delay = 0
                    else:
                        # <Nr> <Zeit>
                        try:
                            delay = float(arg)
                        except ValueError:
                            delay = 0

                        # Optional: <Nr> <Zeit> pixel/gone
                        if len(main_parts) > 2:
                            opt = main_parts[2].lower()
                            if opt in ("pixel", "gone"):
                                pixel_result = _select_pixel_for_wait()
                                if pixel_result:
                                    wait_pixel = (pixel_result[0], pixel_result[1])
                                    wait_color = pixel_result[2]
                                    wait_until_gone = (opt == "gone")

                step = SequenceStep(
                    x=point.x, y=point.y, delay_before=delay,
                    name=point.name or f"#{point_id}",
                    wait_pixel=wait_pixel, wait_color=wait_color,
                    wait_until_gone=wait_until_gone,
                    delay_max=delay_max
                )

                _apply_else_to_step(step, else_parts, state)

                add_step(step)
                continue

        except (KeyboardInterrupt, EOFError):
            raise
