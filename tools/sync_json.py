#!/usr/bin/env python3
"""
Sync-Tool für Autoclicker JSON-Dateien.

Synchronisiert alle JSON-Dateien auf den aktuellen Code-Stand:
- Global Items: Feldordnung, fehlende Felder ergänzen
- Global Slots: Feldordnung aktualisieren
- Scan-Configs: Items mit globalen Items abgleichen
- Item-Presets: Feldordnung aktualisieren

Die Master-Dateien sind:
- items/items.json     (alle Items)
- slots/slots.json     (alle Slots)
- points.json          (Klick-Punkte)

Scan-Configs kopieren Teile aus den Master-Dateien.
"""

import json
import os
from pathlib import Path

# Pfade (relativ zum Hauptverzeichnis)
SCRIPT_DIR = Path(__file__).parent.parent  # Eine Ebene höher als tools/
ITEMS_DIR = SCRIPT_DIR / "items"
SLOTS_DIR = SCRIPT_DIR / "slots"
ITEM_SCANS_DIR = SCRIPT_DIR / "item_scans"
ITEMS_FILE = ITEMS_DIR / "items.json"
SLOTS_FILE = SLOTS_DIR / "slots.json"
ITEM_PRESETS_DIR = ITEMS_DIR / "presets"


def load_global_items() -> dict:
    """Lädt die globalen Items aus items.json."""
    if not ITEMS_FILE.exists():
        return {}

    try:
        with open(ITEMS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[FEHLER] Items laden: {e}")
        return {}


def load_global_slots() -> dict:
    """Lädt die globalen Slots aus slots.json."""
    if not SLOTS_FILE.exists():
        return {}

    try:
        with open(SLOTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[FEHLER] Slots laden: {e}")
        return {}


def sync_global_items(items: dict) -> int:
    """Speichert Items mit korrekter Feldordnung."""
    if not items:
        return 0

    updated_data = {}
    for name, item in items.items():
        updated_data[name] = {
            "name": item.get("name", name),
            "marker_colors": item.get("marker_colors", []),
            "category": item.get("category"),
            "priority": item.get("priority", 1),
            "confirm_point": item.get("confirm_point"),
            "confirm_delay": item.get("confirm_delay", 0.5),
            "template": item.get("template"),
            "min_confidence": item.get("min_confidence", 0.8)
        }

    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    with open(ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_data, f, indent=2, ensure_ascii=False)

    return len(updated_data)


def sync_global_slots(slots: dict) -> int:
    """Speichert Slots mit korrekter Feldordnung."""
    if not slots:
        return 0

    updated_data = {}
    for name, slot in slots.items():
        updated_data[name] = {
            "name": slot.get("name", name),
            "scan_region": slot.get("scan_region"),
            "click_pos": slot.get("click_pos"),
            "slot_color": slot.get("slot_color")
        }

    SLOTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SLOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_data, f, indent=2, ensure_ascii=False)

    return len(updated_data)


def sync_item_presets() -> int:
    """Aktualisiert alle Item-Presets auf korrekte Feldordnung."""
    if not ITEM_PRESETS_DIR.exists():
        return 0

    presets = list(ITEM_PRESETS_DIR.glob("*.json"))
    count = 0

    for preset_file in presets:
        try:
            with open(preset_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            updated_data = {}
            for name, item_data in data.items():
                updated_data[name] = {
                    "name": item_data.get("name", name),
                    "marker_colors": item_data.get("marker_colors", []),
                    "category": item_data.get("category"),
                    "priority": item_data.get("priority", 1),
                    "confirm_point": item_data.get("confirm_point"),
                    "confirm_delay": item_data.get("confirm_delay", 0.5),
                    "template": item_data.get("template"),
                    "min_confidence": item_data.get("min_confidence", 0.8)
                }

            with open(preset_file, "w", encoding="utf-8") as f:
                json.dump(updated_data, f, indent=2, ensure_ascii=False)

            print(f"    {preset_file.name}")
            count += 1
        except Exception as e:
            print(f"    [FEHLER] {preset_file.name}: {e}")

    return count


def sync_scan_configs(global_items: dict) -> tuple[int, int, int]:
    """Synchronisiert Scan-Configs mit globalen Items.

    Returns:
        Tuple (updated, removed, skipped)
    """
    if not ITEM_SCANS_DIR.exists():
        return 0, 0, 0

    scan_files = list(ITEM_SCANS_DIR.glob("*.json"))
    if not scan_files:
        return 0, 0, 0

    total_updated = 0
    total_removed = 0
    total_skipped = 0

    for scan_file in scan_files:
        try:
            with open(scan_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            scan_name = data.get("name", scan_file.stem)
            items = data.get("items", [])

            if not items:
                continue

            print(f"\n  [{scan_name}] {len(items)} Items prüfen...")

            modified = False
            items_to_keep = []

            for item in items:
                item_name = item.get("name", "")

                if item_name in global_items:
                    global_item = global_items[item_name]

                    # Prüfe auf Unterschiede
                    changes = []
                    if item.get("category") != global_item.get("category"):
                        old_cat = item.get("category", "None")
                        changes.append(f"category: {old_cat} -> {global_item.get('category')}")
                        item["category"] = global_item.get("category")

                    if item.get("priority") != global_item.get("priority"):
                        changes.append(f"priority: {item.get('priority')} -> {global_item.get('priority')}")
                        item["priority"] = global_item.get("priority")

                    if item.get("template") != global_item.get("template"):
                        old_tpl = item.get("template", "None")
                        changes.append(f"template: {old_tpl} -> {global_item.get('template')}")
                        item["template"] = global_item.get("template")

                    if item.get("min_confidence") != global_item.get("min_confidence"):
                        item["min_confidence"] = global_item.get("min_confidence")
                        changes.append("min_confidence")

                    if item.get("confirm_point") != global_item.get("confirm_point"):
                        item["confirm_point"] = global_item.get("confirm_point")
                        changes.append("confirm_point")

                    if item.get("confirm_delay") != global_item.get("confirm_delay"):
                        item["confirm_delay"] = global_item.get("confirm_delay")

                    if changes:
                        print(f"    + {item_name}: {', '.join(changes)}")
                        modified = True
                        total_updated += 1

                    items_to_keep.append(item)

                else:
                    # Item nicht in globalen Items
                    print(f"\n    ! '{item_name}' nicht in globalen Items!")
                    print(f"      Template: {item.get('template', 'keins')}")

                    # Zeige ähnliche Items
                    similar = [n for n in global_items.keys()
                              if item_name.lower() in n.lower() or n.lower() in item_name.lower()]

                    if similar:
                        print(f"      Aehnliche: {', '.join(similar)}")

                    print("      Optionen:")
                    print("        [Enter] = Behalten (unveraendert)")
                    print("        [d]     = Aus Scan entfernen")
                    print("        [Name]  = Durch globales Item ersetzen")

                    choice = input("      > ").strip()

                    if choice.lower() == "d":
                        print(f"      -> '{item_name}' entfernt")
                        modified = True
                        total_removed += 1
                    elif choice and choice in global_items:
                        global_item = global_items[choice]
                        item["name"] = global_item.get("name")
                        item["category"] = global_item.get("category")
                        item["priority"] = global_item.get("priority")
                        item["template"] = global_item.get("template")
                        item["min_confidence"] = global_item.get("min_confidence")
                        item["confirm_point"] = global_item.get("confirm_point")
                        item["confirm_delay"] = global_item.get("confirm_delay")
                        print(f"      -> Ersetzt durch '{choice}'")
                        items_to_keep.append(item)
                        modified = True
                        total_updated += 1
                    else:
                        items_to_keep.append(item)
                        total_skipped += 1
                        print("      -> Behalten (unveraendert)")

            # Items mit korrekter Feldordnung neu aufbauen
            rebuilt_items = []
            for item in items_to_keep:
                rebuilt_item = {
                    "name": item.get("name"),
                    "marker_colors": item.get("marker_colors", []),
                    "category": item.get("category"),
                    "priority": item.get("priority", 1),
                    "confirm_point": item.get("confirm_point"),
                    "confirm_delay": item.get("confirm_delay", 0.5),
                    "template": item.get("template"),
                    "min_confidence": item.get("min_confidence", 0.8)
                }
                rebuilt_items.append(rebuilt_item)

            data["items"] = rebuilt_items
            with open(scan_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            if modified:
                print(f"    -> {scan_name} gespeichert!")

        except Exception as e:
            print(f"  [FEHLER] {scan_file.name}: {e}")

    return total_updated, total_removed, total_skipped


def main():
    print("\n" + "=" * 60)
    print("  SYNC: Alle JSON-Dateien aktualisieren")
    print("=" * 60)
    print(f"\n  Arbeitsverzeichnis: {SCRIPT_DIR}")

    # 1. Global Items laden und sync
    global_items = load_global_items()
    print(f"\n  [1/4] Global Items ({len(global_items)})...")
    if global_items:
        count = sync_global_items(global_items)
        print(f"        + Feldordnung aktualisiert ({count} Items)")
    else:
        print("        - keine vorhanden")

    # 2. Global Slots laden und sync
    global_slots = load_global_slots()
    print(f"\n  [2/4] Global Slots ({len(global_slots)})...")
    if global_slots:
        count = sync_global_slots(global_slots)
        print(f"        + Feldordnung aktualisiert ({count} Slots)")
    else:
        print("        - keine vorhanden")

    # 3. Item-Presets sync
    print(f"\n  [3/4] Item-Presets...")
    preset_count = sync_item_presets()
    if preset_count:
        print(f"        + {preset_count} Preset(s) aktualisiert")
    else:
        print("        - keine vorhanden")

    # 4. Scan-Configs sync
    print(f"\n  [4/4] Scan-Konfigurationen...")
    if global_items:
        updated, removed, skipped = sync_scan_configs(global_items)

        print("\n" + "-" * 60)
        print(f"  Scan-Sync Ergebnis:")
        print(f"    Aktualisiert: {updated}")
        print(f"    Entfernt:     {removed}")
        print(f"    Uebersprungen: {skipped}")
    else:
        print("        - Keine globalen Items zum Abgleich")

    print("\n" + "=" * 60)
    print("  SYNC abgeschlossen!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[ABBRUCH]")
    except Exception as e:
        print(f"\n[FEHLER] {e}")

    input("\nENTER zum Beenden...")
