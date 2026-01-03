"""
Item-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Item-Definitionen für Item-Scans.
"""

from pathlib import Path
from typing import Optional

from ..models import ClickPoint, ItemProfile, AutoClickerState
from ..config import CONFIG, DEFAULT_MIN_CONFIDENCE
from ..utils import safe_input, sanitize_filename
from ..winapi import get_cursor_pos
from ..imaging import (
    PILLOW_AVAILABLE, OPENCV_AVAILABLE, take_screenshot, get_pixel_color,
    select_region, get_color_name
)
from ..persistence import (
    save_global_items, list_item_presets, save_item_preset,
    load_item_preset, delete_item_preset, get_existing_categories,
    shift_category_priorities, get_point_by_id, TEMPLATES_DIR
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

    # Presets anzeigen
    presets = list_item_presets()
    if presets:
        print(f"\nVerfügbare Presets ({len(presets)}):")
        for name, path, count in presets:
            print(f"  - {name} ({count} Items)")

    print("\n" + "-" * 60)
    print("Befehle:")
    print("  add            - Neues Item hinzufügen")
    print("  edit <Nr>      - Item bearbeiten")
    print("  del <Nr>       - Item löschen")
    print("  del all        - ALLE Items löschen")
    print("  show           - Alle Items anzeigen")
    print("  save <Name>    - Als Preset speichern")
    print("  load <Name>    - Preset laden")
    print("  preset del <N> - Preset löschen")
    print("  done | cancel")
    print("-" * 60)

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
            elif cmd == "cancel":
                print("[ABBRUCH] Item-Editor beendet.")
                return
            elif cmd == "":
                continue
            elif cmd == "show":
                with state.lock:
                    if state.global_items:
                        print(f"\nItems ({len(state.global_items)}):")
                        for i, (name, item) in enumerate(state.global_items.items()):
                            print(f"  {i+1}. {item}")
                    else:
                        print("  (Keine Items)")
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
                confirm = safe_input(f"  {count} Item(s) wirklich löschen? (j/n): ").strip().lower()
                if confirm == "j":
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


def select_category(state: AutoClickerState) -> Optional[str]:
    """Lässt den Benutzer eine Kategorie auswählen oder erstellen."""
    existing = get_existing_categories(state)

    if existing:
        print("\n  Existierende Kategorien:")
        for i, cat in enumerate(existing):
            print(f"    {i+1}. {cat}")
        print("    0. Neue Kategorie")
        print("    Enter = Keine Kategorie")

        choice = safe_input("  Kategorie: ").strip()
        if not choice:
            return None

        try:
            num = int(choice)
            if num == 0:
                new_cat = safe_input("  Neue Kategorie: ").strip()
                return new_cat if new_cat else None
            elif 1 <= num <= len(existing):
                return existing[num - 1]
        except ValueError:
            # Eingabe als neue Kategorie interpretieren
            return choice if choice else None
    else:
        cat = safe_input("  Kategorie (Enter = keine): ").strip()
        return cat if cat else None


def create_item(state: AutoClickerState) -> Optional[ItemProfile]:
    """Erstellt ein neues Item interaktiv."""
    with state.lock:
        item_num = len(state.global_items) + 1

    item_name = safe_input(f"  Item-Name (Enter = 'Item {item_num}', 'cancel'): ").strip()
    if item_name.lower() in ("cancel", "abbruch"):
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
