"""
Item-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Item-Definitionen für Item-Scans.
"""

from pathlib import Path
from typing import Optional

from ..models import ClickPoint, ItemProfile, AutoClickerState
from ..config import CONFIG, DEFAULT_MIN_CONFIDENCE
from ..utils import safe_input, sanitize_filename, is_cancel, confirm
from ..winapi import get_cursor_pos
from ..imaging import (
    PILLOW_AVAILABLE, OPENCV_AVAILABLE, take_screenshot, get_pixel_color,
    select_region, get_color_name, color_distance
)
from ..persistence import (
    save_global_items, list_item_presets, save_item_preset,
    load_item_preset, delete_item_preset, get_existing_categories,
    shift_category_priorities, get_point_by_id, update_item_in_scans,
    TEMPLATES_DIR
)



def run_global_item_editor(state: AutoClickerState) -> None:
    """Interaktiver Editor für globale Item-Definitionen."""
    print("\n" + "=" * 60)
    print("  ITEM-EDITOR (Globale Item-Definitionen)")
    print("=" * 60)

    if not PILLOW_AVAILABLE:
        print("\n[FEHLER] Pillow nicht installiert!")
        print("         Installieren mit: pip install pillow")
        return

    # Aktuelle Items anzeigen
    with state.lock:
        current_items = list(state.global_items.items())

    if current_items:
        print(f"\nAktuelle Items ({len(current_items)}):")
        for i, (name, item) in enumerate(current_items):
            print(f"  {i+1}. {item}")
    else:
        print("\n  (Keine Items vorhanden)")

    # Verfügbare Slots anzeigen
    with state.lock:
        slots = dict(state.global_slots)
    if slots:
        print(f"\nVerfügbare Slots für Item-Lernen ({len(slots)}):")
        for i, (name, slot) in enumerate(slots.items()):
            print(f"  {i+1}. {slot.name}")

    # Presets anzeigen
    presets = list_item_presets()
    if presets:
        print(f"\nVerfügbare Presets ({len(presets)}):")
        for name, path, count in presets:
            print(f"  - {name} ({count} Items)")

    def _print_item_help():
        print("\n" + "-" * 60)
        print("Befehle:")
        print("  learn <Nr>       - Item aus Slot lernen (automatisch!)")
        print("  learn <Nr>-<Nr>  - Bulk: Items fuer Slot-Bereich (mit Template)")
        print("  learn <Nr>-<Nr> simple - Bulk: ohne Template")
        print("  add              - Neues Item manuell hinzufuegen")
        print("  edit <Nr>        - Item bearbeiten")
        print("  rename <Nr>      - Item umbenennen (inkl. Template)")
        print("  del <Nr>         - Item loeschen")
        print("  del all          - Alle Items loeschen")
        print("  show             - Alle Items anzeigen")
        print("  template <Nr>    - Template fuer Item setzen/entfernen")
        print("  templates        - Verfuegbare Templates anzeigen")
        print("  save <Name>      - Als Preset speichern")
        print("  load <Name>      - Preset laden")
        print("  preset del <N>   - Preset loeschen")
        print("  help | done | cancel")
        print("-" * 60)

    _print_item_help()

    while True:
        try:
            with state.lock:
                item_count = len(state.global_items)
            prompt = f"[ITEMS: {item_count}]"
            user_input = safe_input(f"{prompt} > ").strip()
            cmd = user_input.lower()

            if cmd == "done":
                print("[OK] Item-Editor beendet.")
                return
            elif is_cancel(cmd):
                print("[ABBRUCH] Item-Editor beendet.")
                return
            elif cmd == "":
                continue
            elif cmd == "help":
                _print_item_help()
                continue
            elif cmd == "show":
                with state.lock:
                    if state.global_items:
                        print(f"\nItems ({len(state.global_items)}):")
                        sorted_items = sorted(state.global_items.values(), key=lambda x: x.priority)
                        for i, item in enumerate(sorted_items):
                            print(f"  {i+1}. {item}")
                    else:
                        print("  (Keine Items)")
                continue

            elif cmd.startswith("learn"):
                item_learn_command(state, cmd)
                continue

            elif cmd == "add":
                item = create_item(state)
                if item:
                    with state.lock:
                        state.global_items[item.name] = item
                    save_global_items(state)
                    print(f"  + Item '{item.name}' hinzugefügt")
                continue

            elif cmd.startswith("edit "):
                try:
                    edit_num = int(cmd[5:])
                    with state.lock:
                        item_list = list(state.global_items.items())
                        if 1 <= edit_num <= len(item_list):
                            name, item = item_list[edit_num - 1]
                            new_item = edit_item(state, item)
                            if new_item:
                                # Falls Name geändert wurde
                                if new_item.name != name:
                                    del state.global_items[name]
                                state.global_items[new_item.name] = new_item
                                save_global_items(state)
                                print(f"  + Item '{new_item.name}' aktualisiert")
                        else:
                            print(f"  -> Ungültig! Verfügbar: 1-{len(item_list)}")
                except ValueError:
                    print("  -> Format: edit <Nr>")
                continue

            elif cmd == "del all":
                with state.lock:
                    if not state.global_items:
                        print("  -> Keine Items vorhanden!")
                        continue
                    count = len(state.global_items)
                if confirm(f"  {count} Item(s) wirklich löschen?"):
                    with state.lock:
                        state.global_items.clear()
                    save_global_items(state)
                    print(f"  + {count} Item(s) gelöscht!")
                else:
                    print("  -> Abgebrochen")
                continue

            elif cmd.startswith("del "):
                try:
                    del_num = int(cmd[4:])
                    with state.lock:
                        item_list = list(state.global_items.keys())
                        if 1 <= del_num <= len(item_list):
                            name = item_list[del_num - 1]
                            del state.global_items[name]
                            save_global_items(state)
                            print(f"  + Item '{name}' gelöscht")
                        else:
                            print(f"  -> Ungültig! Verfügbar: 1-{len(item_list)}")
                except ValueError:
                    print("  -> Format: del <Nr>")
                continue

            elif cmd.startswith("rename "):
                handle_rename_command(state, cmd)
                continue

            elif cmd == "templates":
                handle_templates_command()
                continue

            elif cmd.startswith("template "):
                handle_template_command(state, cmd)
                continue

            elif cmd.startswith("save "):
                preset_name = user_input[5:].strip()
                if preset_name:
                    save_item_preset(state, preset_name)
                else:
                    print("  -> Format: save <Name>")
                continue

            elif cmd.startswith("load "):
                preset_name = user_input[5:].strip()
                if preset_name:
                    load_item_preset(state, preset_name)
                else:
                    print("  -> Format: load <Name>")
                continue

            elif cmd.startswith("preset del "):
                preset_name = user_input[11:].strip()
                if preset_name:
                    delete_item_preset(preset_name)
                else:
                    print("  -> Format: preset del <Name>")
                continue

            else:
                print("  -> Unbekannter Befehl")

        except (KeyboardInterrupt, EOFError):
            print("\n[ABBRUCH] Item-Editor beendet.")
            return


def select_category(state: AutoClickerState, show_explanation: bool = True) -> Optional[str]:
    """Lässt den Benutzer eine Kategorie auswählen oder erstellen."""
    existing = get_existing_categories(state)

    if show_explanation:
        print("\n  Kategorie (z.B. 'Hosen', 'Jacken', 'Juwelen')")
        print("  Items derselben Kategorie konkurrieren - nur das beste wird geklickt.")

    if existing:
        print("  Vorhandene Kategorien:")
        for i, cat in enumerate(existing):
            print(f"    {i+1}. {cat}")
        print("  (Nummer waehlen oder neuen Namen eingeben)")

    user_input = safe_input("  Kategorie (Enter = keine): ").strip()

    if not user_input:
        return None

    try:
        num = int(user_input)
        if 1 <= num <= len(existing):
            return existing[num - 1]
        else:
            return user_input
    except ValueError:
        return user_input


def create_item(state: AutoClickerState) -> Optional[ItemProfile]:
    """Erstellt ein neues Item interaktiv."""
    with state.lock:
        item_num = len(state.global_items) + 1

    item_name = safe_input(f"  Item-Name (Enter = 'Item {item_num}', 'cancel'): ").strip()
    if is_cancel(item_name):
        print("  -> Item-Erstellung abgebrochen")
        return None
    if not item_name:
        item_name = f"Item {item_num}"

    # Prüfen ob Name schon existiert
    with state.lock:
        if item_name in state.global_items:
            print(f"  -> '{item_name}' existiert bereits!")
            return None

    # Template erstellen (Screenshot von Slot)
    template_file = None
    min_confidence = DEFAULT_MIN_CONFIDENCE

    if OPENCV_AVAILABLE:
        print("\n  Template erstellen?")
        print("  (Screenshot einer Region, die das Item zeigt)")
        print("  Enter = Ja, 'skip' = Nein")
        if safe_input().strip().lower() != "skip":
            print("\n  Region für Template auswählen...")
            region = select_region()
            if region:
                img = take_screenshot(region)
                if img:
                    safe_name = sanitize_filename(item_name)
                    template_file = f"{safe_name}.png"
                    template_path = Path(TEMPLATES_DIR) / template_file
                    template_path.parent.mkdir(parents=True, exist_ok=True)
                    img.save(template_path)
                    print(f"  -> Template gespeichert: {template_path}")

                    # Konfidenz abfragen
                    try:
                        conf_input = safe_input(f"  Min. Konfidenz % (Enter={int(DEFAULT_MIN_CONFIDENCE * 100)}): ").strip()
                        if conf_input:
                            min_confidence = max(0.1, min(1.0, float(conf_input) / 100))
                    except ValueError:
                        pass
    else:
        print("\n  [INFO] OpenCV nicht installiert - kein Template-Matching möglich")
        print("         Installieren mit: pip install opencv-python")

    # Kategorie
    category = select_category(state)

    # Priorität
    priority = 1
    try:
        prio_input = safe_input(f"  Priorität (1=beste, 0=beste+verschieben, Enter={priority}): ").strip()
        if prio_input:
            prio_val = int(prio_input)
            if prio_val == 0:
                if category:
                    shift_category_priorities(state, category)
                    priority = 1
                else:
                    print("  -> Priorität 0 nur mit Kategorie möglich!")
                    priority = 1
            else:
                priority = max(1, prio_val)
    except ValueError:
        pass

    # Bestätigungs-Klick
    confirm_point = None
    confirm_delay = CONFIG.get("default_confirm_delay", 0.5)
    print("\n  Bestätigungs-Punkt? (z.B. für Popup-Bestätigung)")
    confirm_input = safe_input("  Punkt-ID (Enter=Nein): ").strip()
    if confirm_input:
        try:
            point_id = int(confirm_input)
            with state.lock:
                found_point = get_point_by_id(state, point_id)
                if found_point:
                    confirm_point = ClickPoint(found_point.x, found_point.y)
                    try:
                        delay_input = safe_input("  Wartezeit vor Bestätigung (Enter=0.5s): ").strip()
                        if delay_input:
                            confirm_delay = float(delay_input)
                    except ValueError:
                        pass
                else:
                    print(f"  -> Punkt #{point_id} existiert nicht")
        except ValueError:
            pass

    return ItemProfile(
        name=item_name,
        marker_colors=[],
        category=category,
        priority=priority,
        confirm_point=confirm_point,
        confirm_delay=confirm_delay,
        template=template_file,
        min_confidence=min_confidence
    )


def edit_item(state: AutoClickerState, item: ItemProfile) -> Optional[ItemProfile]:
    """Bearbeitet ein bestehendes Item."""
    print(f"\n  Bearbeite Item: {item.name}")
    print(f"    Kategorie: {item.category or '(keine)'}")
    print(f"    Priorität: {item.priority}")
    if item.template:
        print(f"    Template: {item.template} ({item.min_confidence:.0%})")
    if item.confirm_point:
        print(f"    Bestätigung: ({item.confirm_point.x}, {item.confirm_point.y}) nach {item.confirm_delay}s")

    print("\n  Was ändern?")
    print("    1. Name")
    print("    2. Kategorie")
    print("    3. Priorität")
    print("    4. Template")
    print("    5. Bestätigungs-Punkt")
    print("    0. Fertig")

    new_name = item.name
    new_category = item.category
    new_priority = item.priority
    new_template = item.template
    new_confidence = item.min_confidence
    new_confirm = item.confirm_point
    new_confirm_delay = item.confirm_delay

    while True:
        choice = safe_input("  Option: ").strip()

        if choice == "0" or choice.lower() == "done":
            break
        elif choice == "1":
            name_input = safe_input(f"  Neuer Name (Enter = '{new_name}'): ").strip()
            if name_input:
                new_name = name_input
                print(f"  -> Name geändert zu '{new_name}'")
        elif choice == "2":
            new_category = select_category(state)
            print(f"  -> Kategorie geändert zu '{new_category or '(keine)'}'")
        elif choice == "3":
            try:
                prio_input = safe_input(f"  Neue Priorität (Enter = {new_priority}): ").strip()
                if prio_input:
                    new_priority = max(1, int(prio_input))
                    print(f"  -> Priorität geändert zu {new_priority}")
            except ValueError:
                print("  -> Ungültige Eingabe")
        elif choice == "4":
            if OPENCV_AVAILABLE:
                print("\n  Neues Template erstellen...")
                region = select_region()
                if region:
                    img = take_screenshot(region)
                    if img:
                        safe_name = sanitize_filename(new_name)
                        new_template = f"{safe_name}.png"
                        template_path = Path(TEMPLATES_DIR) / new_template
                        template_path.parent.mkdir(parents=True, exist_ok=True)
                        img.save(template_path)
                        print(f"  -> Template gespeichert: {template_path}")

                        try:
                            conf_input = safe_input(f"  Min. Konfidenz % (Enter={int(new_confidence * 100)}): ").strip()
                            if conf_input:
                                new_confidence = max(0.1, min(1.0, float(conf_input) / 100))
                        except ValueError:
                            pass
            else:
                print("  -> OpenCV nicht installiert!")
        elif choice == "5":
            print("  Neuer Bestätigungs-Punkt?")
            confirm_input = safe_input("  Punkt-ID (Enter=entfernen): ").strip()
            if confirm_input:
                try:
                    point_id = int(confirm_input)
                    with state.lock:
                        found_point = get_point_by_id(state, point_id)
                        if found_point:
                            new_confirm = ClickPoint(found_point.x, found_point.y)
                            try:
                                delay_input = safe_input(f"  Wartezeit (Enter={new_confirm_delay}s): ").strip()
                                if delay_input:
                                    new_confirm_delay = float(delay_input)
                            except ValueError:
                                pass
                            print(f"  -> Bestätigung gesetzt")
                        else:
                            print(f"  -> Punkt #{point_id} existiert nicht")
                except ValueError:
                    print("  -> Ungültige Eingabe")
            else:
                new_confirm = None
                print("  -> Bestätigung entfernt")
        else:
            print("  -> Ungültige Option")
            continue

    return ItemProfile(
        name=new_name,
        marker_colors=item.marker_colors,
        category=new_category,
        priority=new_priority,
        confirm_point=new_confirm,
        confirm_delay=new_confirm_delay,
        template=new_template,
        min_confidence=new_confidence
    )


# =============================================================================
# MARKER-FARBEN SAMMLUNG
# =============================================================================

def collect_marker_colors(region: tuple = None, exclude_color: tuple = None) -> list[tuple]:
    """Sammelt Marker-Farben fuer ein Item-Profil durch Region-Scan."""

    # Wenn keine Region uebergeben, manuell auswaehlen
    if not region:
        print("\n  Waehle einen Bereich auf dem Item aus:")
        print("  (Die 5 haeufigsten Farben werden automatisch genommen)")
        region = select_region()
        if not region:
            return []

    # Screenshot der Region
    print(f"\n  Scanne Region ({region[0]},{region[1]}) - ({region[2]},{region[3]})...")
    img = take_screenshot(region)
    if img is None:
        print("  -> Fehler beim Screenshot!")
        return []

    # Farben zaehlen (mit Rundung fuer Gruppierung)
    color_counts = {}
    pixels = img.load()
    width, height = img.size

    for x in range(width):
        for y in range(height):
            pixel = pixels[x, y][:3]
            # Runde auf 5er-Schritte fuer Gruppierung aehnlicher Farben
            rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
            color_counts[rounded] = color_counts.get(rounded, 0) + 1

    # Slot-Hintergrundfarbe ausschliessen (falls vorhanden)
    if exclude_color:
        exclude_rounded = (exclude_color[0] // 5 * 5, exclude_color[1] // 5 * 5, exclude_color[2] // 5 * 5)

        slot_color_dist = CONFIG.get("slot_color_distance", 25)
        colors_to_remove = []
        for color in color_counts.keys():
            if color_distance(color, exclude_rounded) <= slot_color_dist:
                colors_to_remove.append(color)

        total_excluded = 0
        for color in colors_to_remove:
            total_excluded += color_counts.pop(color)

        if total_excluded > 0:
            color_name = get_color_name(exclude_color)
            print(f"  -> Slot-Hintergrund ~RGB{exclude_color} ({color_name}) ausgeschlossen ({total_excluded} Pixel, {len(colors_to_remove)} Farbtoene)")

    # Top N haeufigste Farben (aus Config)
    marker_count = CONFIG.get("marker_count", 5)
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:marker_count]
    colors = [color for color, count in sorted_colors]

    print(f"\n  Top {marker_count} Farben gefunden:")
    for i, (color, count) in enumerate(sorted_colors):
        color_name = get_color_name(color)
        print(f"    {i+1}. RGB{color} - {color_name} ({count} Pixel)")

    return colors


def collect_marker_colors_free() -> list[tuple]:
    """Sammelt Marker-Farben aus einem frei gewaehlten Bereich mit optionalem Hintergrund-Ausschluss."""
    print("\n  Waehle einen Bereich auf dem Item aus:")
    print("  (Die 5 haeufigsten Farben werden automatisch genommen)")
    region = select_region()
    if not region:
        return []

    # Optional Hintergrundfarbe ausschliessen
    exclude_color = None
    bg_input = safe_input("  Hintergrundfarbe entfernen? (Enter = Nein, 'j' = Farbe aufnehmen): ").strip().lower()
    if bg_input == "j":
        print("  -> Bewege die Maus auf den Hintergrund und druecke ENTER...")
        safe_input()
        try:
            x, y = get_cursor_pos()
            exclude_color = get_pixel_color(x, y)
            if exclude_color:
                exclude_color = (exclude_color[0] // 5 * 5, exclude_color[1] // 5 * 5, exclude_color[2] // 5 * 5)
                color_name = get_color_name(exclude_color)
                print(f"  -> Hintergrund: RGB{exclude_color} ({color_name}) wird ausgeschlossen")
        except (OSError, TypeError, AttributeError):
            print("  -> Konnte Hintergrundfarbe nicht aufnehmen, fahre ohne fort")

    return collect_marker_colors(region, exclude_color)


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

    colors_to_remove = []
    for color in common_colors:
        color_name = get_color_name(color)
        answer = safe_input(f"    RGB{color} ({color_name}) entfernen? (j/n): ").strip().lower()
        if answer == "j":
            colors_to_remove.append(color)
            print(f"      -> wird entfernt")
        else:
            print(f"      -> behalten")

    if not colors_to_remove:
        print("  Keine Farben entfernt.")
        return items

    for item in items:
        item.marker_colors = [c for c in item.marker_colors if c not in colors_to_remove]
        if not item.marker_colors:
            print(f"  [WARNUNG] {item.name} hat keine eindeutigen Farben mehr!")

    print(f"  {len(colors_to_remove)} Farbe(n) entfernt")
    return items


# =============================================================================
# LEARN-BEFEHL (Bulk und Single)
# =============================================================================

def item_learn_command(state: AutoClickerState, user_input: str) -> bool:
    """Verarbeitet den learn-Befehl (Bulk und Single). Gibt True zurueck wenn verarbeitet."""
    with state.lock:
        slot_list = list(state.global_slots.values())

    if not slot_list:
        print("  -> Keine Slots vorhanden! Erst Slots mit 'auto' im Slot-Editor erstellen.")
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
                print(f"  -> Ungueltiger Bereich! Verfuegbar: 1-{len(slot_list)}")
                return True

            use_template = mode_part.lower() in ("template", "t")
            mode_str = "MIT Template" if use_template else "OHNE Template"

            print(f"\n  === BULK LEARN: Slots {start_slot}-{end_slot} ({mode_str}) ===")

            # Kategorie einmal fuer alle abfragen
            print("  Kategorie fuer alle Items (Enter = keine):")
            category = select_category(state, show_explanation=False)

            # Bestaetigungs-Punkt einmal fuer alle abfragen
            confirm_point = None
            confirm_delay = state.config.get("default_confirm_delay", CONFIG.get("default_confirm_delay", 0.5))
            confirm_input = safe_input("  Bestaetigungs-Punkt-ID fuer alle (Enter = keine): ").strip()
            if confirm_input:
                try:
                    point_id = int(confirm_input)
                    found_point = get_point_by_id(state, point_id)
                    if found_point:
                        confirm_point = ClickPoint(found_point.x, found_point.y)
                        delay_input = safe_input(f"  Wartezeit vor Bestaetigung (Enter = {confirm_delay}s): ").strip()
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

                # Template speichern wenn gewuenscht
                if use_template and OPENCV_AVAILABLE:
                    template_img = take_screenshot(slot.scan_region)
                    if template_img:
                        safe_name = sanitize_filename(item_name)
                        template_file = f"{safe_name}.png"
                        template_path = Path(TEMPLATES_DIR) / template_file
                        template_path.parent.mkdir(parents=True, exist_ok=True)
                        template_img.save(template_path)
                        item.template = template_file

                with state.lock:
                    state.global_items[item_name] = item
                created_count += 1

                template_str = f" + {item.template}" if item.template else ""
                print(f"    + {item_name} (P{priority}){template_str}")

            save_global_items(state)
            print(f"\n  === {created_count} Items erstellt! ===")
            return True

        except (ValueError, IndexError):
            print("  -> Format: learn <von>-<bis> [template|simple]")
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
        print(f"\n  Verfuegbare Slots (1-{len(slot_list)}):")
        for i, slot in enumerate(slot_list):
            print(f"    {i+1}. {slot.name}")
        try:
            slot_input = safe_input("  Slot-Nr wo das Item liegt: ").strip()
            if is_cancel(slot_input):
                return True
            slot_num = int(slot_input)
        except ValueError:
            print("  -> Ungueltige Eingabe!")
            return True

    if slot_num < 1 or slot_num > len(slot_list):
        print(f"  -> Ungueltiger Slot! Verfuegbar: 1-{len(slot_list)}")
        return True

    selected_slot = slot_list[slot_num - 1]
    print(f"\n  Scanne Slot '{selected_slot.name}'...")

    # Item-Name abfragen
    item_num = len(state.global_items) + 1
    item_name = safe_input(f"  Item-Name (Enter = 'Item {item_num}'): ").strip()
    if is_cancel(item_name):
        return True
    if not item_name:
        item_name = f"Item {item_num}"

    # Pruefen ob Name schon existiert
    with state.lock:
        if item_name in state.global_items:
            print(f"  -> Item '{item_name}' existiert bereits!")
            return True

    # Kategorie zuerst (fuer Prioritaets-Verschiebung)
    category = select_category(state)

    # Prioritaet
    priority = 1
    try:
        prio_input = safe_input(f"  Prioritaet (1=beste, 0=beste+verschieben, Enter={priority}): ").strip()
        if is_cancel(prio_input):
            print("  -> Abgebrochen")
            return True
        if prio_input:
            prio_val = int(prio_input)
            if prio_val == 0:
                if category:
                    shift_category_priorities(state, category)
                    priority = 1
                else:
                    print("  -> Prioritaet 0 nur mit Kategorie moeglich!")
                    priority = 1
            else:
                priority = max(1, prio_val)
    except ValueError:
        pass

    # Screenshot des Slots machen und Farben extrahieren
    print(f"  Scanne Farben in Region {selected_slot.scan_region}...")
    marker_colors = collect_marker_colors(selected_slot.scan_region, selected_slot.slot_color)

    if not marker_colors:
        print("  -> Keine Farben gefunden!")
        return True

    # Bestaetigungs-Klick abfragen
    confirm_point = None
    confirm_delay = state.config.get("default_confirm_delay", CONFIG.get("default_confirm_delay", 0.5))
    print("\n  Soll nach dem Item-Klick noch ein Bestaetigungs-Klick erfolgen?")
    print("  (z.B. auf einen 'Accept' oder 'Craft' Button)")
    confirm_input = safe_input("  Punkt-ID fuer Bestaetigung (Enter = Nein): ").strip()
    if is_cancel(confirm_input):
        print("  -> Abgebrochen")
        return True
    if confirm_input:
        try:
            point_id = int(confirm_input)
            found_point = get_point_by_id(state, point_id)
            if found_point:
                confirm_point = ClickPoint(found_point.x, found_point.y)
                delay_input = safe_input(f"  Wartezeit vor Bestaetigung in Sek (Enter = {confirm_delay}): ").strip()
                if delay_input:
                    try:
                        confirm_delay = float(delay_input)
                    except ValueError:
                        pass
            else:
                print(f"  -> Punkt #{point_id} existiert nicht")
        except ValueError:
            print("  -> Keine gueltige Zahl, keine Bestaetigung")

    # Item erstellen und speichern
    item = ItemProfile(item_name, marker_colors, category, priority, confirm_point, confirm_delay)

    # Optional: Auch als Template speichern?
    if OPENCV_AVAILABLE:
        save_template = safe_input("  Auch als Template speichern? (j/n, Enter=n): ").strip().lower()
        if save_template == "j":
            template_img = take_screenshot(selected_slot.scan_region)
            if template_img:
                safe_name = sanitize_filename(item_name)
                template_file = f"{safe_name}.png"
                template_path = Path(TEMPLATES_DIR) / template_file
                template_path.parent.mkdir(parents=True, exist_ok=True)
                template_img.save(template_path)
                item.template = template_file

                # Konfidenz abfragen
                conf_input = safe_input(f"  Min. Konfidenz fuer Template (Enter={item.min_confidence:.0%}): ").strip()
                if conf_input:
                    try:
                        conf = float(conf_input.replace("%", "")) / 100
                        item.min_confidence = max(0.1, min(1.0, conf))
                    except ValueError:
                        pass

                print(f"  + Template gespeichert: {template_file}")

    with state.lock:
        state.global_items[item_name] = item

    save_global_items(state)

    confirm_str = f" -> ({confirm_point.x},{confirm_point.y}) nach {confirm_delay}s" if confirm_point else ""
    template_str = f" + Template" if item.template else ""
    print(f"  + Item '{item_name}' gelernt mit {len(marker_colors)} Marker-Farben!{confirm_str}{template_str}")
    return True


# =============================================================================
# RENAME-BEFEHL
# =============================================================================

def handle_rename_command(state: AutoClickerState, cmd: str) -> None:
    """Verarbeitet den rename-Befehl im Item-Editor."""
    try:
        rename_num = int(cmd[7:])
        with state.lock:
            item_names = list(state.global_items.keys())
            if 1 <= rename_num <= len(item_names):
                old_name = item_names[rename_num - 1]
                item = state.global_items[old_name]

                print(f"\n  Aktueller Name: '{old_name}'")
                if item.template:
                    print(f"  Template: {item.template}")

                new_name = safe_input("  Neuer Name (Enter = abbrechen): ").strip()
                if not new_name or is_cancel(new_name):
                    print("  -> Abgebrochen")
                    return

                if new_name == old_name:
                    print("  -> Name ist identisch, nichts geaendert")
                    return

                if new_name in state.global_items:
                    print(f"  -> Name '{new_name}' existiert bereits!")
                    return

                # Template umbenennen falls vorhanden
                old_template = item.template
                if old_template:
                    old_template_path = Path(TEMPLATES_DIR) / old_template
                    safe_name = sanitize_filename(new_name)
                    new_template = f"{safe_name}.png"
                    new_template_path = Path(TEMPLATES_DIR) / new_template

                    item.template = new_template

                    if old_template_path.exists():
                        try:
                            old_template_path.rename(new_template_path)
                            print(f"  + Template umbenannt: {old_template} -> {new_template}")
                        except (OSError, IOError) as e:
                            print(f"  -> Template-Datei Umbenennung fehlgeschlagen: {e}")
                            print(f"    Template-Pfad aktualisiert: {new_template}")
                    else:
                        print(f"  -> Template-Datei nicht gefunden: {old_template}")
                        print(f"    Template-Pfad aktualisiert: {new_template}")

                # Item umbenennen
                item.name = new_name
                del state.global_items[old_name]
                state.global_items[new_name] = item
                save_global_items(state)

                # Auch in allen Scan-Konfigurationen aktualisieren
                updated_scans = update_item_in_scans(old_name, new_name, item.template)
                if updated_scans > 0:
                    print(f"  + {updated_scans} Scan-Konfiguration(en) aktualisiert")

                print(f"  + Item umbenannt: '{old_name}' -> '{new_name}' (gespeichert)")
            else:
                print(f"  -> Ungueltiges Item! Verfuegbar: 1-{len(item_names)}")
    except ValueError:
        print("  -> Format: rename <Nr>")


# =============================================================================
# TEMPLATE-BEFEHLE
# =============================================================================

def handle_templates_command() -> None:
    """Zeigt verfuegbare Templates an."""
    if not Path(TEMPLATES_DIR).exists():
        print("  -> Keine Templates vorhanden")
        return
    templates = list(Path(TEMPLATES_DIR).glob("*.png"))
    if not templates:
        print("  -> Keine Templates vorhanden")
        print(f"    (Ordner: {TEMPLATES_DIR})")
    else:
        print(f"\n  Verfuegbare Templates ({len(templates)}):")
        for t in sorted(templates):
            print(f"    - {t.name}")


def handle_template_command(state: AutoClickerState, cmd: str) -> None:
    """Verarbeitet den template-Befehl im Item-Editor."""
    try:
        item_num = int(cmd[9:])
        with state.lock:
            item_names = list(state.global_items.keys())
            if 1 <= item_num <= len(item_names):
                name = item_names[item_num - 1]
                item = state.global_items[name]

                # Verfuegbare Templates anzeigen
                templates = list(Path(TEMPLATES_DIR).glob("*.png")) if Path(TEMPLATES_DIR).exists() else []
                if templates:
                    print(f"\n  Verfuegbare Templates:")
                    for i, t in enumerate(sorted(templates)):
                        print(f"    {i+1}. {t.name}")

                current = item.template if item.template else "Keins"
                print(f"\n  Item: {item.name}")
                print(f"  Aktuelles Template: {current}")
                print(f"  Aktuelle Konfidenz: {item.min_confidence:.0%}")

                print("\n  Optionen:")
                print("    <Dateiname.png> - Template setzen")
                print("    <Nr>            - Template aus Liste waehlen")
                print("    capture         - Screenshot als Template speichern")
                print("    remove          - Template entfernen")
                print("    Enter           - Abbrechen")

                template_input = safe_input("  Template: ").strip()
                if not template_input:
                    return

                if template_input.lower() == "remove":
                    item.template = None
                    save_global_items(state)
                    print("  + Template entfernt!")
                elif template_input.lower() == "capture":
                    # Screenshot-Region abfragen
                    with state.lock:
                        slot_list = list(state.global_slots.values())
                    if slot_list:
                        print(f"\n  Screenshot von:")
                        print("    0. Freie Region waehlen")
                        for i, slot in enumerate(slot_list):
                            print(f"    {i+1}. {slot.name}")
                        try:
                            slot_choice = safe_input("  Auswahl: ").strip()
                            if slot_choice == "0":
                                region = select_region()
                            else:
                                slot_idx = int(slot_choice) - 1
                                if 0 <= slot_idx < len(slot_list):
                                    region = slot_list[slot_idx].scan_region
                                else:
                                    print("  -> Ungueltiger Slot!")
                                    return
                        except ValueError:
                            region = select_region()
                    else:
                        region = select_region()

                    if region:
                        img = take_screenshot(region)
                        if img:
                            safe_name = sanitize_filename(item.name)
                            template_file = f"{safe_name}.png"
                            template_path = Path(TEMPLATES_DIR) / template_file
                            template_path.parent.mkdir(parents=True, exist_ok=True)
                            img.save(template_path)
                            item.template = template_file

                            conf_input = safe_input(f"  Min. Konfidenz (Enter={item.min_confidence:.0%}): ").strip()
                            if conf_input:
                                try:
                                    conf = float(conf_input.replace("%", "")) / 100
                                    item.min_confidence = max(0.1, min(1.0, conf))
                                except ValueError:
                                    pass

                            save_global_items(state)
                            print(f"  + Template gespeichert: {template_file}")
                        else:
                            print("  -> Screenshot fehlgeschlagen!")
                else:
                    # Dateiname oder Nummer
                    try:
                        template_num = int(template_input)
                        if 1 <= template_num <= len(templates):
                            item.template = sorted(templates)[template_num - 1].name
                        else:
                            print("  -> Ungueltige Nummer!")
                            return
                    except ValueError:
                        if not template_input.endswith(".png"):
                            template_input += ".png"
                        item.template = template_input

                    # Konfidenz abfragen
                    conf_input = safe_input(f"  Min. Konfidenz (aktuell {item.min_confidence:.0%}, Enter=behalten): ").strip()
                    if conf_input:
                        try:
                            conf = float(conf_input.replace("%", "")) / 100
                            item.min_confidence = max(0.1, min(1.0, conf))
                        except ValueError:
                            pass

                    save_global_items(state)
                    print(f"  + Template gesetzt: {item.template} (>={item.min_confidence:.0%})")
            else:
                print(f"  -> Ungueltiges Item!")
    except ValueError:
        print("  -> Format: template <Nr>")
