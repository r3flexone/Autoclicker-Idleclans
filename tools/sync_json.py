#!/usr/bin/env python3
"""
Sync-Tool für Autoclicker JSON-Dateien.

Bringt alle JSON-Dateien auf den aktuellen Code-Stand:
- Fehlende Felder mit Standardwerten ergaenzen
- Alte Formate konvertieren (z.B. confirm_point int -> [x,y])
- Feldordnung korrigieren
- Scan-Configs mit globalen Items abgleichen

Standardwerte werden automatisch eingetragen.
Nur bei unklaren Faellen wird nachgefragt.
"""

import json
from pathlib import Path

# Pfade (relativ zum Hauptverzeichnis)
SCRIPT_DIR = Path(__file__).parent.parent
ITEMS_DIR = SCRIPT_DIR / "items"
SLOTS_DIR = SCRIPT_DIR / "slots"
SEQUENCES_DIR = SCRIPT_DIR / "sequences"
ITEM_SCANS_DIR = SCRIPT_DIR / "item_scans"
ITEMS_FILE = ITEMS_DIR / "items.json"
SLOTS_FILE = SLOTS_DIR / "slots.json"
POINTS_FILE = SEQUENCES_DIR / "points.json"  # Punkte sind in sequences/
ITEM_PRESETS_DIR = ITEMS_DIR / "presets"
SLOT_PRESETS_DIR = SLOTS_DIR / "presets"

# Globale Punkte-Liste
POINTS = []

# ==============================================================================
# STANDARDWERTE - Werden verwendet wenn Feld fehlt oder ungueltig
# ==============================================================================
ITEM_DEFAULTS = {
    "marker_colors": [],
    "category": None,
    "priority": 1,
    "confirm_point": None,
    "confirm_delay": 0.5,
    "template": None,
    "min_confidence": 0.8
}

SLOT_DEFAULTS = {
    "scan_region": None,
    "click_pos": None,
    "slot_color": None
}

SCAN_DEFAULTS = {
    "color_tolerance": 40,
    "slots": [],
    "items": []
}


# ==============================================================================
# HILFSFUNKTIONEN
# ==============================================================================
def load_json_safe(filepath: Path) -> dict | list | None:
    """Laedt JSON sicher, gibt None bei Fehler."""
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [FEHLER] {filepath.name}: {e}")
        return None


def save_json(filepath: Path, data, indent=2):
    """Speichert JSON mit korrekter Kodierung."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def load_points() -> list:
    """Laedt Punkte aus points.json."""
    data = load_json_safe(POINTS_FILE)
    if not data:
        return []

    points = []
    for p in data:
        if isinstance(p, list) and len(p) == 2:
            points.append(p)
        elif isinstance(p, dict) and "x" in p and "y" in p:
            points.append([p["x"], p["y"]])
    return points


def convert_confirm_point(cp, item_name=""):
    """Konvertiert confirm_point in korrektes Format.

    - [x, y] Liste -> behalten
    - int (Punkt-Nr) -> Koordinaten aus POINTS
    - Alles andere -> None
    """
    # Bereits korrekt
    if isinstance(cp, list) and len(cp) == 2:
        return cp

    # Alte int-Werte konvertieren
    if isinstance(cp, int) and cp >= 1:
        if cp <= len(POINTS):
            coords = POINTS[cp - 1]
            print(f"      {item_name}: Punkt {cp} -> ({coords[0]}, {coords[1]})")
            return coords
        else:
            print(f"      {item_name}: Punkt {cp} existiert nicht -> None")
            return None

    return None


def normalize_color(color):
    """Stellt sicher dass Farbe als Liste gespeichert wird."""
    if color is None:
        return None
    if isinstance(color, (list, tuple)) and len(color) >= 3:
        return list(color[:3])
    return None


def normalize_region(region):
    """Stellt sicher dass Region als Liste [x1,y1,x2,y2] gespeichert wird."""
    if region is None:
        return None
    if isinstance(region, (list, tuple)) and len(region) >= 4:
        return list(region[:4])
    return None


def normalize_pos(pos):
    """Stellt sicher dass Position als Liste [x,y] gespeichert wird."""
    if pos is None:
        return None
    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        return list(pos[:2])
    return None


# ==============================================================================
# ITEM SYNC
# ==============================================================================
def sync_item(name: str, item: dict) -> tuple[dict, list]:
    """Synchronisiert ein einzelnes Item.

    Returns: (fixed_item, list_of_fixes)
    """
    fixes = []

    # Name muss vorhanden sein
    if not item.get("name"):
        item["name"] = name
        fixes.append("name ergaenzt")

    # Marker-Colors normalisieren
    mc = item.get("marker_colors", [])
    if not isinstance(mc, list):
        mc = []
        fixes.append("marker_colors repariert")
    else:
        mc = [normalize_color(c) for c in mc if normalize_color(c)]

    # Priority muss >= 1 sein
    priority = item.get("priority")
    if not isinstance(priority, int) or priority < 1:
        priority = ITEM_DEFAULTS["priority"]
        fixes.append(f"priority -> {priority}")

    # confirm_point konvertieren
    old_cp = item.get("confirm_point")
    new_cp = convert_confirm_point(old_cp, name)
    if old_cp is not None and old_cp != new_cp:
        if new_cp:
            fixes.append(f"confirm_point konvertiert")
        else:
            fixes.append(f"confirm_point geloescht (ungueltig)")

    # confirm_delay
    delay = item.get("confirm_delay")
    if not isinstance(delay, (int, float)) or delay < 0:
        delay = ITEM_DEFAULTS["confirm_delay"]
        fixes.append(f"confirm_delay -> {delay}")

    # min_confidence
    conf = item.get("min_confidence")
    if not isinstance(conf, (int, float)) or not (0 < conf <= 1):
        conf = ITEM_DEFAULTS["min_confidence"]
        fixes.append(f"min_confidence -> {conf}")

    # Item mit korrekter Feldordnung aufbauen
    fixed = {
        "name": name,
        "marker_colors": mc,
        "category": item.get("category"),  # None ist OK
        "priority": priority,
        "confirm_point": new_cp,
        "confirm_delay": delay,
        "template": item.get("template"),  # None ist OK
        "min_confidence": conf
    }

    return fixed, fixes


def sync_global_items() -> tuple[int, int]:
    """Synchronisiert items/items.json.

    Returns: (count, fixes_count)
    """
    data = load_json_safe(ITEMS_FILE)
    if not data:
        return 0, 0

    if not isinstance(data, dict):
        print("    [FEHLER] items.json ist kein Dictionary!")
        return 0, 0

    updated = {}
    total_fixes = 0

    for name, item in data.items():
        if not isinstance(item, dict):
            print(f"    [WARNUNG] '{name}' uebersprungen (kein Dictionary)")
            continue

        fixed, fixes = sync_item(name, item)
        updated[name] = fixed

        if fixes:
            total_fixes += len(fixes)
            print(f"    {name}: {', '.join(fixes)}")

    save_json(ITEMS_FILE, updated)
    return len(updated), total_fixes


# ==============================================================================
# SLOT SYNC
# ==============================================================================
def sync_slot(name: str, slot: dict) -> tuple[dict, list]:
    """Synchronisiert einen einzelnen Slot."""
    fixes = []

    # Name
    if not slot.get("name"):
        slot["name"] = name
        fixes.append("name ergaenzt")

    # scan_region normalisieren
    region = normalize_region(slot.get("scan_region"))
    if slot.get("scan_region") and not region:
        fixes.append("scan_region repariert")

    # click_pos normalisieren
    pos = normalize_pos(slot.get("click_pos"))
    if slot.get("click_pos") and not pos:
        fixes.append("click_pos repariert")

    # slot_color normalisieren
    color = normalize_color(slot.get("slot_color"))

    fixed = {
        "name": name,
        "scan_region": region,
        "click_pos": pos,
        "slot_color": color
    }

    return fixed, fixes


def sync_global_slots() -> tuple[int, int]:
    """Synchronisiert slots/slots.json."""
    data = load_json_safe(SLOTS_FILE)
    if not data:
        return 0, 0

    if not isinstance(data, dict):
        print("    [FEHLER] slots.json ist kein Dictionary!")
        return 0, 0

    updated = {}
    total_fixes = 0

    for name, slot in data.items():
        if not isinstance(slot, dict):
            print(f"    [WARNUNG] '{name}' uebersprungen")
            continue

        fixed, fixes = sync_slot(name, slot)
        updated[name] = fixed

        if fixes:
            total_fixes += len(fixes)
            print(f"    {name}: {', '.join(fixes)}")

    save_json(SLOTS_FILE, updated)
    return len(updated), total_fixes


# ==============================================================================
# PRESET SYNC
# ==============================================================================
def sync_item_presets() -> tuple[int, int]:
    """Synchronisiert alle Item-Presets."""
    if not ITEM_PRESETS_DIR.exists():
        return 0, 0

    presets = list(ITEM_PRESETS_DIR.glob("*.json"))
    total_count = 0
    total_fixes = 0

    for preset_file in presets:
        data = load_json_safe(preset_file)
        if not data or not isinstance(data, dict):
            continue

        updated = {}
        fixes_in_file = 0

        for name, item in data.items():
            if not isinstance(item, dict):
                continue

            fixed, fixes = sync_item(name, item)
            updated[name] = fixed
            fixes_in_file += len(fixes)

        if fixes_in_file > 0:
            print(f"    {preset_file.name}: {fixes_in_file} Korrekturen")
            total_fixes += fixes_in_file

        save_json(preset_file, updated)
        total_count += 1

    return total_count, total_fixes


# ==============================================================================
# SLOT PRESET SYNC
# ==============================================================================
def sync_slot_presets() -> tuple[int, int]:
    """Synchronisiert alle Slot-Presets."""
    if not SLOT_PRESETS_DIR.exists():
        return 0, 0

    presets = list(SLOT_PRESETS_DIR.glob("*.json"))
    total_count = 0
    total_fixes = 0

    for preset_file in presets:
        data = load_json_safe(preset_file)
        if not data or not isinstance(data, dict):
            continue

        updated = {}
        fixes_in_file = 0

        for name, slot in data.items():
            if not isinstance(slot, dict):
                continue

            fixed, fixes = sync_slot(name, slot)
            updated[name] = fixed
            fixes_in_file += len(fixes)

        if fixes_in_file > 0:
            print(f"    {preset_file.name}: {fixes_in_file} Korrekturen")
            total_fixes += fixes_in_file

        save_json(preset_file, updated)
        total_count += 1

    return total_count, total_fixes


# ==============================================================================
# SCAN CONFIG SYNC
# ==============================================================================
def sync_scan_configs(global_items: dict) -> tuple[int, int, int]:
    """Synchronisiert Scan-Configs mit globalen Items.

    Returns: (updated, auto_fixed, user_input_needed)
    """
    if not ITEM_SCANS_DIR.exists():
        return 0, 0, 0

    scan_files = list(ITEM_SCANS_DIR.glob("*.json"))
    if not scan_files:
        return 0, 0, 0

    total_updated = 0
    total_fixed = 0
    total_user_input = 0

    for scan_file in scan_files:
        data = load_json_safe(scan_file)
        if not data or not isinstance(data, dict):
            continue

        scan_name = data.get("name", scan_file.stem)

        # Name sicherstellen
        if not data.get("name"):
            data["name"] = scan_file.stem

        # color_tolerance mit Default
        if "color_tolerance" not in data:
            data["color_tolerance"] = SCAN_DEFAULTS["color_tolerance"]

        # Slots normalisieren
        slots = data.get("slots", [])
        if isinstance(slots, list):
            fixed_slots = []
            for i, slot in enumerate(slots):
                if isinstance(slot, dict):
                    name = slot.get("name", f"Slot {i+1}")
                    fixed, _ = sync_slot(name, slot)
                    fixed_slots.append(fixed)
            data["slots"] = fixed_slots

        # Items verarbeiten
        items = data.get("items", [])
        if not isinstance(items, list):
            items = []

        fixed_items = []
        file_fixes = 0

        print(f"\n  [{scan_name}]")

        for item in items:
            if not isinstance(item, dict):
                continue

            item_name = item.get("name", "")

            # Item in globalen Items?
            if item_name and item_name in global_items:
                global_item = global_items[item_name]

                # Werte aus globalem Item uebernehmen
                changes = []

                for field in ["category", "priority", "template", "min_confidence",
                              "confirm_point", "confirm_delay"]:
                    if item.get(field) != global_item.get(field):
                        item[field] = global_item.get(field)
                        changes.append(field)

                if changes:
                    print(f"    {item_name}: {', '.join(changes)} aktualisiert")
                    total_updated += 1

                # Item normalisieren
                fixed, fixes = sync_item(item_name, item)
                # marker_colors aus Original behalten (scan-spezifisch)
                fixed["marker_colors"] = item.get("marker_colors", [])
                fixed_items.append(fixed)
                file_fixes += len(fixes)

            elif item_name:
                # Item nicht in globalen Items - User fragen
                print(f"\n    ! '{item_name}' nicht in globalen Items")

                # Aehnliche suchen
                similar = [n for n in global_items.keys()
                          if item_name.lower() in n.lower() or n.lower() in item_name.lower()]
                if similar:
                    print(f"      Aehnliche: {', '.join(similar[:5])}")

                print("      [Enter]=behalten, [d]=loeschen, [Name]=ersetzen")
                choice = input("      > ").strip()

                if choice.lower() == "d":
                    print(f"      -> geloescht")
                    total_user_input += 1
                elif choice in global_items:
                    # Durch globales Item ersetzen
                    global_item = global_items[choice]
                    fixed, _ = sync_item(choice, dict(global_item))
                    fixed["marker_colors"] = item.get("marker_colors", [])
                    fixed_items.append(fixed)
                    print(f"      -> ersetzt durch '{choice}'")
                    total_user_input += 1
                    total_updated += 1
                else:
                    # Behalten aber normalisieren
                    fixed, fixes = sync_item(item_name, item)
                    fixed_items.append(fixed)
                    file_fixes += len(fixes)
                    print(f"      -> behalten")

        data["items"] = fixed_items
        total_fixed += file_fixes

        # Speichern mit korrekter Struktur
        save_json(scan_file, {
            "name": data["name"],
            "color_tolerance": data.get("color_tolerance", SCAN_DEFAULTS["color_tolerance"]),
            "slots": data.get("slots", []),
            "items": data["items"]
        })

    return total_updated, total_fixed, total_user_input


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    global POINTS

    print("\n" + "=" * 60)
    print("  SYNC-TOOL: JSON-Dateien aktualisieren")
    print("=" * 60)
    print(f"\n  Verzeichnis: {SCRIPT_DIR}")

    # Punkte laden (fuer confirm_point Konvertierung)
    POINTS = load_points()
    print(f"  Punkte geladen: {len(POINTS)}")

    # 1. Global Items
    print(f"\n  [1/5] Global Items...")
    count, fixes = sync_global_items()
    if count:
        print(f"        {count} Items, {fixes} Korrekturen")
    else:
        print("        - keine vorhanden")

    # 2. Global Slots
    print(f"\n  [2/5] Global Slots...")
    count, fixes = sync_global_slots()
    if count:
        print(f"        {count} Slots, {fixes} Korrekturen")
    else:
        print("        - keine vorhanden")

    # 3. Item-Presets
    print(f"\n  [3/5] Item-Presets...")
    count, fixes = sync_item_presets()
    if count:
        print(f"        {count} Presets, {fixes} Korrekturen")
    else:
        print("        - keine vorhanden")

    # 4. Slot-Presets
    print(f"\n  [4/5] Slot-Presets...")
    count, fixes = sync_slot_presets()
    if count:
        print(f"        {count} Presets, {fixes} Korrekturen")
    else:
        print("        - keine vorhanden")

    # 5. Scan-Configs
    print(f"\n  [5/5] Scan-Konfigurationen...")

    # Globale Items nochmal laden (nach Sync aktualisiert)
    global_items = load_json_safe(ITEMS_FILE) or {}

    if global_items:
        updated, fixed, user = sync_scan_configs(global_items)
        print(f"\n        Aktualisiert: {updated}, Auto-Fixes: {fixed}, User-Input: {user}")
    else:
        print("        - Keine Items zum Abgleich")

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
        import traceback
        traceback.print_exc()

    input("\nENTER zum Beenden...")
