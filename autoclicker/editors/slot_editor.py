"""
Slot-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Slot-Definitionen für Item-Scans.
"""

from pathlib import Path
from typing import Optional

from ..models import ItemSlot, AutoClickerState
from ..config import CONFIG
from ..utils import safe_input, sanitize_filename
from ..winapi import get_cursor_pos
from ..imaging import (
    PILLOW_AVAILABLE, take_screenshot, get_pixel_color, select_region, get_color_name
)
from ..persistence import (
    save_global_slots, list_slot_presets, save_slot_preset,
    load_slot_preset, delete_slot_preset, SCREENSHOTS_DIR
)



def run_global_slot_editor(state: AutoClickerState) -> None:
    """Interaktiver Editor für globale Slot-Definitionen."""
    print("\n" + "=" * 60)
    print("  SLOT-EDITOR (Globale Slot-Definitionen)")
    print("=" * 60)

    if not PILLOW_AVAILABLE:
        print("\n[FEHLER] Pillow nicht installiert!")
        print("         Installieren mit: pip install pillow")
        return

    # Aktuelle Slots anzeigen
    with state.lock:
        current_slots = list(state.global_slots.items())

    if current_slots:
        print(f"\nAktuelle Slots ({len(current_slots)}):")
        for i, (name, slot) in enumerate(current_slots):
            print(f"  {i+1}. {slot}")
    else:
        print("\n  (Keine Slots vorhanden)")

    # Presets anzeigen
    presets = list_slot_presets()
    if presets:
        print(f"\nVerfügbare Presets ({len(presets)}):")
        for name, path, count, is_active in presets:
            marker = " [AKTIV]" if is_active else ""
            print(f"  - {name} ({count} Slots){marker}")

    print("\n" + "-" * 60)
    print("Befehle:")
    print("  add            - Neuen Slot hinzufügen")
    print("  edit <Nr>      - Slot bearbeiten")
    print("  del <Nr>       - Slot löschen")
    print("  del all        - ALLE Slots löschen")
    print("  show           - Alle Slots anzeigen")
    print("  save <Name>    - Als Preset speichern")
    print("  load <Name>    - Preset laden")
    print("  preset del <N> - Preset löschen")
    print("  done | cancel")
    print("-" * 60)

    while True:
        try:
            with state.lock:
                slot_count = len(state.global_slots)
            prompt = f"[SLOTS: {slot_count}]"
            user_input = safe_input(f"{prompt} > ").strip()
            cmd = user_input.lower()

            if cmd == "done":
                print("[OK] Slot-Editor beendet.")
                return
            elif cmd == "cancel":
                print("[ABBRUCH] Slot-Editor beendet.")
                return
            elif cmd == "":
                continue
            elif cmd == "show":
                with state.lock:
                    if state.global_slots:
                        print(f"\nSlots ({len(state.global_slots)}):")
                        for i, (name, slot) in enumerate(state.global_slots.items()):
                            print(f"  {i+1}. {slot}")
                    else:
                        print("  (Keine Slots)")
                continue

            elif cmd == "add":
                slot = create_slot(state)
                if slot:
                    with state.lock:
                        state.global_slots[slot.name] = slot
                    save_global_slots(state)
                    print(f"  + Slot '{slot.name}' hinzugefügt")
                continue

            elif cmd.startswith("edit "):
                try:
                    edit_num = int(cmd[5:])
                    with state.lock:
                        slot_list = list(state.global_slots.items())
                        if 1 <= edit_num <= len(slot_list):
                            name, slot = slot_list[edit_num - 1]
                            new_slot = edit_slot(state, slot)
                            if new_slot:
                                # Falls Name geändert wurde
                                if new_slot.name != name:
                                    del state.global_slots[name]
                                state.global_slots[new_slot.name] = new_slot
                                save_global_slots(state)
                                print(f"  + Slot '{new_slot.name}' aktualisiert")
                        else:
                            print(f"  -> Ungültig! Verfügbar: 1-{len(slot_list)}")
                except ValueError:
                    print("  -> Format: edit <Nr>")
                continue

            elif cmd == "del all":
                with state.lock:
                    if not state.global_slots:
                        print("  -> Keine Slots vorhanden!")
                        continue
                    count = len(state.global_slots)
                confirm = safe_input(f"  {count} Slot(s) wirklich löschen? (j/n): ").strip().lower()
                if confirm == "j":
                    with state.lock:
                        state.global_slots.clear()
                    save_global_slots(state)
                    print(f"  + {count} Slot(s) gelöscht!")
                else:
                    print("  -> Abgebrochen")
                continue

            elif cmd.startswith("del "):
                try:
                    del_num = int(cmd[4:])
                    with state.lock:
                        slot_list = list(state.global_slots.keys())
                        if 1 <= del_num <= len(slot_list):
                            name = slot_list[del_num - 1]
                            del state.global_slots[name]
                            save_global_slots(state)
                            print(f"  + Slot '{name}' gelöscht")
                        else:
                            print(f"  -> Ungültig! Verfügbar: 1-{len(slot_list)}")
                except ValueError:
                    print("  -> Format: del <Nr>")
                continue

            elif cmd.startswith("save "):
                preset_name = user_input[5:].strip()
                if preset_name:
                    save_slot_preset(state, preset_name)
                else:
                    print("  -> Format: save <Name>")
                continue

            elif cmd.startswith("load "):
                preset_name = user_input[5:].strip()
                if preset_name:
                    load_slot_preset(state, preset_name)
                else:
                    print("  -> Format: load <Name>")
                continue

            elif cmd.startswith("preset del "):
                preset_name = user_input[11:].strip()
                if preset_name:
                    delete_slot_preset(preset_name)
                else:
                    print("  -> Format: preset del <Name>")
                continue

            else:
                print("  -> Unbekannter Befehl")

        except (KeyboardInterrupt, EOFError):
            print("\n[ABBRUCH] Slot-Editor beendet.")
            return


def create_slot(state: AutoClickerState) -> Optional[ItemSlot]:
    """Erstellt einen neuen Slot interaktiv."""
    with state.lock:
        slot_num = len(state.global_slots) + 1

    slot_name = safe_input(f"  Slot-Name (Enter = 'Slot {slot_num}', 'cancel'): ").strip()
    if slot_name.lower() in ("cancel", "abbruch"):
        print("  -> Slot-Erstellung abgebrochen")
        return None
    if not slot_name:
        slot_name = f"Slot {slot_num}"

    # Scan-Region auswählen
    print("\n  Scan-Region definieren (Bereich wo das Item angezeigt wird):")
    print("  ('cancel' in Konsole = abbrechen)")
    region = select_region()
    if not region:
        print("  -> Slot-Erstellung abgebrochen")
        return None

    # Sofort Farben in dieser Region anzeigen
    print("\n  Analysiere Farben in diesem Bereich...")
    img = take_screenshot(region)
    if img:
        color_counts = {}
        pixels = img.load()
        width, height = img.size
        for x in range(width):
            for y in range(height):
                pixel = pixels[x, y][:3]
                rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
                color_counts[rounded] = color_counts.get(rounded, 0) + 1
        marker_count = CONFIG.get("marker_count", 5)
        sorted_colors = sorted(color_counts.items(), key=lambda c: c[1], reverse=True)[:marker_count]
        print(f"  Top {marker_count} Farben in {slot_name}:")
        for i, (color, count) in enumerate(sorted_colors):
            color_name = get_color_name(color)
            print(f"    {i+1}. RGB{color} - {color_name} ({count} Pixel)")

    # Slot-Hintergrundfarbe (wird bei Items ausgeschlossen)
    slot_color = None
    print("\n  Hintergrundfarbe des leeren Slots markieren:")
    print("  (Diese Farbe wird bei Item-Erkennung ignoriert)")
    print("  Bewege Maus auf den Slot-Hintergrund, Enter (oder 'skip')...")
    bg_input = safe_input().strip().lower()
    if bg_input in ("cancel", "abbruch"):
        print("  -> Slot-Erstellung abgebrochen")
        return None
    elif bg_input != "skip":
        x, y = get_cursor_pos()
        slot_color = get_pixel_color(x, y)
        if slot_color:
            color_name = get_color_name(slot_color)
            print(f"  -> Hintergrundfarbe: RGB{slot_color} ({color_name})")
        else:
            print("  -> Farbe konnte nicht gelesen werden, überspringe...")

    # Klickposition
    print("\n  Klickposition definieren (wo geklickt wird wenn Item gefunden):")
    print("  Bewege Maus zur Klickposition, Enter (oder 'center' für Mitte)...")
    click_input = safe_input().strip().lower()

    if click_input == "center":
        # Mitte der Region berechnen
        x1, y1, x2, y2 = region
        click_x = (x1 + x2) // 2
        click_y = (y1 + y2) // 2
    else:
        click_x, click_y = get_cursor_pos()

    print(f"  -> Klickposition: ({click_x}, {click_y})")

    # Optional: Screenshot speichern
    if img:
        try:
            screenshots_dir = Path(SCREENSHOTS_DIR)
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            safe_name = sanitize_filename(slot_name)
            screenshot_path = screenshots_dir / f"{safe_name}.png"
            img.save(screenshot_path)
            print(f"  -> Screenshot gespeichert: {screenshot_path}")
        except Exception as e:
            print(f"  -> Screenshot speichern fehlgeschlagen: {e}")

    return ItemSlot(
        name=slot_name,
        scan_region=region,
        click_pos=(click_x, click_y),
        slot_color=slot_color
    )


def edit_slot(state: AutoClickerState, slot: ItemSlot) -> Optional[ItemSlot]:
    """Bearbeitet einen bestehenden Slot."""
    print(f"\n  Bearbeite Slot: {slot.name}")
    print(f"    Region: {slot.scan_region}")
    print(f"    Klickpos: {slot.click_pos}")
    if slot.slot_color:
        print(f"    Hintergrund: RGB{slot.slot_color}")

    print("\n  Was ändern?")
    print("    1. Name")
    print("    2. Scan-Region")
    print("    3. Klickposition")
    print("    4. Hintergrundfarbe")
    print("    0. Fertig (nichts ändern)")

    new_name = slot.name
    new_region = slot.scan_region
    new_click = slot.click_pos
    new_color = slot.slot_color

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
            print("\n  Neue Scan-Region definieren...")
            region = select_region()
            if region:
                new_region = region
                print(f"  -> Region geändert zu {new_region}")
        elif choice == "3":
            print("  Bewege Maus zur neuen Klickposition, Enter...")
            safe_input()
            new_click = get_cursor_pos()
            print(f"  -> Klickposition geändert zu {new_click}")
        elif choice == "4":
            print("  Bewege Maus zum Slot-Hintergrund, Enter...")
            safe_input()
            x, y = get_cursor_pos()
            color = get_pixel_color(x, y)
            if color:
                new_color = color
                print(f"  -> Hintergrundfarbe geändert zu RGB{new_color}")
        else:
            print("  -> Ungültige Option")
            continue

    return ItemSlot(
        name=new_name,
        scan_region=new_region,
        click_pos=new_click,
        slot_color=new_color
    )
