#!/usr/bin/env python3
"""
Sync-Tool für Autoclicker JSON-Dateien.

Bringt alle JSON-Dateien auf den aktuellen Code-Stand:
- Fehlende Felder mit Standardwerten ergaenzen
- Alte Formate konvertieren (z.B. confirm_point int -> [x,y])
- Feldordnung korrigieren

Reihenfolge (Global -> Unterordner):
1. Config          (config.json)
2. Points          (sequences/points.json)
3. Sequences       (sequences/*.json)
4. Slots global    (slots/slots.json)
5. Items global    (items/items.json)
6. Scans global    (item_scans/*.json)
7. Slot presets    (slots/presets/*.json)
8. Item presets    (items/presets/*.json)
"""

import json
from pathlib import Path

# ==============================================================================
# PFADE
# ==============================================================================
SCRIPT_DIR = Path(__file__).parent.parent

# Config
CONFIG_FILE = SCRIPT_DIR / "config.json"

# Sequences/Points
SEQUENCES_DIR = SCRIPT_DIR / "sequences"
POINTS_FILE = SEQUENCES_DIR / "points.json"

# Slots
SLOTS_DIR = SCRIPT_DIR / "slots"
SLOTS_FILE = SLOTS_DIR / "slots.json"
SLOT_PRESETS_DIR = SLOTS_DIR / "presets"

# Items
ITEMS_DIR = SCRIPT_DIR / "items"
ITEMS_FILE = ITEMS_DIR / "items.json"
ITEM_PRESETS_DIR = ITEMS_DIR / "presets"

# Scans
ITEM_SCANS_DIR = SCRIPT_DIR / "item_scans"

# Globale Punkte-Liste (fuer confirm_point Konvertierung)
POINTS = []

# ==============================================================================
# STANDARDWERTE
# ==============================================================================
CONFIG_DEFAULTS = {
    # === KLICK-EINSTELLUNGEN ===
    "clicks_per_point": 1,
    "max_total_clicks": None,
    "click_move_delay": 0.01,
    "post_click_delay": 0.05,

    # === SICHERHEIT ===
    "failsafe_enabled": True,
    "failsafe_x": 5,
    "failsafe_y": 5,

    # === FARB-/PIXEL-ERKENNUNG ===
    "color_tolerance": 0,
    "pixel_wait_tolerance": 10,
    "pixel_wait_timeout": 300,
    "pixel_check_interval": 1,
    "scan_pixel_step": 2,
    "show_pixel_delay": 0.3,

    # === ITEM-SCAN EINSTELLUNGEN ===
    "scan_reverse": False,
    "scan_slot_delay": 0.1,
    "item_click_delay": 1.0,
    "marker_count": 5,
    "require_all_markers": True,
    "min_markers_required": 2,
    "slot_hsv_tolerance": 25,
    "slot_inset": 10,
    "slot_color_distance": 25,
    "default_min_confidence": 0.8,
    "default_confirm_delay": 0.5,

    # === ZAHLENERKENNUNG ===
    "number_wait_timeout": 300,
    "number_check_interval": 2,
    "number_color_tolerance": 50,
    "number_min_confidence": 0.8,

    # === SCAN-WARTEN ===
    "scan_wait_timeout": 300,
    "scan_wait_interval": 2,

    # === TIMING ===
    "pause_check_interval": 0.5,

    # === DEBUG-EINSTELLUNGEN ===
    "debug_mode": False,
    "debug_detection": False,
    "show_pixel_position": False,
    "debug_save_templates": False,
}

POINT_DEFAULTS = {
    "id": 0,
    "x": 0,
    "y": 0,
    "name": ""
}

SEQUENCE_STEP_DEFAULTS = {
    "x": 0,
    "y": 0,
    "name": "",
    "delay_before": 0.0,
    "wait_pixel": None,
    "wait_color": None,
    "wait_until_gone": False,
    "item_scan": None,
    "item_scan_mode": "all",
    "wait_only": False,
    "delay_max": None,
    "key_press": None,
    # Else-Aktion
    "else_action": None,
    "else_x": 0,
    "else_y": 0,
    "else_delay": 0,
    "else_key": None,
    "else_name": "",
    # Zahlenerkennung
    "wait_number_region": None,
    "wait_number_operator": None,
    "wait_number_target": None,
    "wait_number_color": None,
    # Scan-Warten
    "wait_scan": None,
    "wait_scan_item": None,
    "wait_scan_gone": False,
}

SLOT_DEFAULTS = {
    "scan_region": None,
    "click_pos": None,
    "slot_color": None
}

ITEM_DEFAULTS = {
    "marker_colors": [],
    "category": None,
    "priority": 1,
    "confirm_point": None,
    "confirm_delay": 0.5,
    "template": None,
    "min_confidence": 0.8
}

SCAN_DEFAULTS = {
    "color_tolerance": 40,
    "slots": [],
    "items": []
}


# ==============================================================================
# HILFSFUNKTIONEN
# ==============================================================================
def load_json_safe(filepath: Path):
    """Laedt JSON sicher, gibt None bei Fehler."""
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"    [FEHLER] {filepath.name}: {e}")
        return None


def save_json(filepath: Path, data, indent=2):
    """Speichert JSON mit korrekter Kodierung."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def normalize_color(color):
    """Farbe als Liste [r,g,b]."""
    if color is None:
        return None
    if isinstance(color, (list, tuple)) and len(color) >= 3:
        return [int(c) for c in color[:3]]
    return None


def normalize_region(region):
    """Region als Liste [x1,y1,x2,y2]."""
    if region is None:
        return None
    if isinstance(region, (list, tuple)) and len(region) >= 4:
        return [int(v) for v in region[:4]]
    return None


def normalize_pos(pos):
    """Position als Liste [x,y]."""
    if pos is None:
        return None
    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        return [int(v) for v in pos[:2]]
    return None


def convert_confirm_point(cp, item_name=""):
    """Konvertiert confirm_point zu neuem Format: {"x": x, "y": y}.

    Unterstuetzte alte Formate:
    - int: Punkt-ID aus POINTS
    - [x, y]: Liste
    - {"x": x, "y": y}: Bereits neues Format
    """
    # Bereits neues Format
    if isinstance(cp, dict) and "x" in cp and "y" in cp:
        return {"x": int(cp["x"]), "y": int(cp["y"])}

    # Altes Listen-Format [x, y]
    if isinstance(cp, list) and len(cp) == 2:
        print(f"      {item_name}: [x,y] -> {{x,y}} konvertiert")
        return {"x": int(cp[0]), "y": int(cp[1])}

    # Altes int-Format (Punkt-ID)
    if isinstance(cp, int) and cp >= 1:
        if cp <= len(POINTS):
            coords = POINTS[cp - 1]
            print(f"      {item_name}: Punkt {cp} -> {{x:{coords[0]}, y:{coords[1]}}}")
            return {"x": coords[0], "y": coords[1]}
        else:
            print(f"      {item_name}: Punkt {cp} nicht vorhanden -> None")

    return None


# ==============================================================================
# 1. CONFIG SYNC
# ==============================================================================
def sync_config() -> tuple[int, int]:
    """Synchronisiert config.json."""
    data = load_json_safe(CONFIG_FILE)

    if data is None:
        # Erstelle neue Config
        save_json(CONFIG_FILE, CONFIG_DEFAULTS)
        print("    config.json erstellt mit Standardwerten")
        return 1, len(CONFIG_DEFAULTS)

    if not isinstance(data, dict):
        print("    [FEHLER] config.json ist kein Dictionary!")
        return 0, 0

    fixes = 0
    updated = {}

    # Alle Defaults durchgehen (in richtiger Reihenfolge)
    for key, default in CONFIG_DEFAULTS.items():
        if key in data:
            updated[key] = data[key]
        else:
            updated[key] = default
            print(f"    + {key} = {default}")
            fixes += 1

    # Unbekannte Keys am Ende behalten
    for key in data:
        if key not in updated:
            updated[key] = data[key]

    save_json(CONFIG_FILE, updated)
    return 1, fixes


# ==============================================================================
# 2. POINTS SYNC
# ==============================================================================
def sync_points() -> tuple[int, int]:
    """Synchronisiert sequences/points.json und laedt POINTS."""
    global POINTS

    data = load_json_safe(POINTS_FILE)
    if not data:
        POINTS = []
        return 0, 0

    if not isinstance(data, list):
        print("    [FEHLER] points.json ist keine Liste!")
        POINTS = []
        return 0, 0

    fixes = 0
    updated = []

    # Finde hoechste ID fuer neue Punkte ohne ID
    max_id = 0
    for point in data:
        if isinstance(point, dict) and "id" in point:
            max_id = max(max_id, int(point.get("id", 0)))

    for i, point in enumerate(data):
        if not isinstance(point, dict):
            continue

        point_fixes = 0

        # Fehlende Felder pruefen
        if "id" not in point:
            max_id += 1
            point["id"] = max_id
            point_fixes += 1
        if "x" not in point:
            point_fixes += 1
        if "y" not in point:
            point_fixes += 1
        if "name" not in point:
            point_fixes += 1

        # Normalisieren (id zuerst fuer bessere Lesbarkeit)
        fixed = {
            "id": int(point.get("id", i + 1)),
            "x": int(point.get("x", 0)),
            "y": int(point.get("y", 0)),
            "name": str(point.get("name", ""))
        }

        if point_fixes > 0:
            print(f"      Punkt #{fixed['id']}: {point_fixes} Feld(er) ergaenzt")
            fixes += point_fixes

        updated.append(fixed)
        POINTS.append([fixed["x"], fixed["y"]])

    save_json(POINTS_FILE, updated)
    return len(updated), fixes


# ==============================================================================
# 3. SEQUENCES SYNC
# ==============================================================================
def sync_step(step: dict) -> tuple[dict, int]:
    """Synchronisiert einen Sequenz-Schritt."""
    fixes = 0
    fixed = {}

    for key, default in SEQUENCE_STEP_DEFAULTS.items():
        if key in step:
            fixed[key] = step[key]
        else:
            fixed[key] = default
            fixes += 1

    return fixed, fixes


def sync_sequences() -> tuple[int, int]:
    """Synchronisiert sequences/*.json (ausser points.json)."""
    if not SEQUENCES_DIR.exists():
        return 0, 0

    seq_files = [f for f in SEQUENCES_DIR.glob("*.json") if f.name != "points.json"]
    total_count = 0
    total_fixes = 0

    for seq_file in seq_files:
        data = load_json_safe(seq_file)
        if not data or not isinstance(data, dict):
            continue

        fixes = 0

        # Name sicherstellen
        if "name" not in data:
            data["name"] = seq_file.stem
            fixes += 1

        # total_cycles
        if "total_cycles" not in data:
            data["total_cycles"] = None
            fixes += 1

        # start_steps
        if "start_steps" in data and isinstance(data["start_steps"], list):
            fixed_steps = []
            for step in data["start_steps"]:
                if isinstance(step, dict):
                    fixed, f = sync_step(step)
                    fixed_steps.append(fixed)
                    fixes += f
            data["start_steps"] = fixed_steps
        else:
            data["start_steps"] = []

        # loop_phases
        if "loop_phases" in data and isinstance(data["loop_phases"], list):
            fixed_phases = []
            for phase in data["loop_phases"]:
                if isinstance(phase, dict):
                    fixed_phase = {
                        "name": phase.get("name", "Loop"),
                        "repeat": phase.get("repeat", 1),
                        "steps": []
                    }
                    if "steps" in phase and isinstance(phase["steps"], list):
                        for step in phase["steps"]:
                            if isinstance(step, dict):
                                fixed, f = sync_step(step)
                                fixed_phase["steps"].append(fixed)
                                fixes += f
                    fixed_phases.append(fixed_phase)
            data["loop_phases"] = fixed_phases
        else:
            data["loop_phases"] = []

        # end_steps
        if "end_steps" in data and isinstance(data["end_steps"], list):
            fixed_steps = []
            for step in data["end_steps"]:
                if isinstance(step, dict):
                    fixed, f = sync_step(step)
                    fixed_steps.append(fixed)
                    fixes += f
            data["end_steps"] = fixed_steps
        else:
            data["end_steps"] = []

        if fixes > 0:
            print(f"    {seq_file.name}: {fixes} Korrekturen")
            total_fixes += fixes

        save_json(seq_file, {
            "name": data["name"],
            "total_cycles": data["total_cycles"],
            "start_steps": data["start_steps"],
            "loop_phases": data["loop_phases"],
            "end_steps": data["end_steps"]
        })
        total_count += 1

    return total_count, total_fixes


# ==============================================================================
# 4. SLOTS SYNC
# ==============================================================================
def sync_slot(name: str, slot: dict) -> tuple[dict, int]:
    """Synchronisiert einen Slot."""
    fixes = 0

    if not slot.get("name"):
        fixes += 1

    region = normalize_region(slot.get("scan_region"))
    pos = normalize_pos(slot.get("click_pos"))
    color = normalize_color(slot.get("slot_color"))

    return {
        "name": name,
        "scan_region": region,
        "click_pos": pos,
        "slot_color": color
    }, fixes


def sync_global_slots() -> tuple[dict, int, int]:
    """Synchronisiert slots/slots.json.

    Returns:
        tuple: (synced_data, count, fixes)
    """
    data = load_json_safe(SLOTS_FILE)
    if not data:
        return {}, 0, 0

    if not isinstance(data, dict):
        print("    [FEHLER] slots.json ist kein Dictionary!")
        return {}, 0, 0

    updated = {}
    total_fixes = 0

    for name, slot in data.items():
        if isinstance(slot, dict):
            fixed, fixes = sync_slot(name, slot)
            updated[name] = fixed
            if fixes:
                print(f"    {name}: {fixes} Korrekturen")
                total_fixes += fixes

    save_json(SLOTS_FILE, updated)
    return updated, len(updated), total_fixes


def sync_slot_presets(global_slots: dict) -> tuple[int, int]:
    """Synchronisiert slots/presets/*.json mit globalen Slots."""
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

            # Globalen Slot als Basis nehmen (falls vorhanden)
            if name in global_slots:
                global_slot = global_slots[name]
                fixes = 0

                # Felder von global übernehmen wenn lokal fehlt
                for field in ["scan_region", "click_pos", "slot_color"]:
                    if field not in slot or slot[field] is None:
                        if global_slot.get(field) is not None:
                            slot[field] = global_slot[field]
                            fixes += 1

                fixed, extra_fixes = sync_slot(name, slot)
                updated[name] = fixed
                fixes_in_file += fixes

                if fixes > 0:
                    print(f"      {name}: {fixes} von global uebernommen")
            else:
                # Slot nicht in global -> nur normalisieren
                fixed, fixes = sync_slot(name, slot)
                updated[name] = fixed
                fixes_in_file += fixes

        save_json(preset_file, updated)
        total_count += 1
        total_fixes += fixes_in_file

    return total_count, total_fixes


# ==============================================================================
# 5. ITEMS SYNC
# ==============================================================================
def sync_item(name: str, item: dict) -> tuple[dict, int]:
    """Synchronisiert ein Item."""
    fixes = 0

    # marker_colors
    mc = item.get("marker_colors", [])
    if not isinstance(mc, list):
        mc = []
        fixes += 1
    else:
        mc = [normalize_color(c) for c in mc if normalize_color(c)]

    # priority
    priority = item.get("priority")
    if not isinstance(priority, int) or priority < 1:
        priority = ITEM_DEFAULTS["priority"]
        fixes += 1

    # confirm_point
    old_cp = item.get("confirm_point")
    new_cp = convert_confirm_point(old_cp, name)
    if old_cp is not None and old_cp != new_cp:
        fixes += 1

    # confirm_delay
    delay = item.get("confirm_delay")
    if not isinstance(delay, (int, float)) or delay < 0:
        delay = ITEM_DEFAULTS["confirm_delay"]
        fixes += 1

    # min_confidence
    conf = item.get("min_confidence")
    if not isinstance(conf, (int, float)) or not (0 < conf <= 1):
        conf = ITEM_DEFAULTS["min_confidence"]
        fixes += 1

    return {
        "name": name,
        "marker_colors": mc,
        "category": item.get("category"),
        "priority": priority,
        "confirm_point": new_cp,
        "confirm_delay": delay,
        "template": item.get("template"),
        "min_confidence": conf
    }, fixes


def sync_global_items() -> tuple[dict, int, int]:
    """Synchronisiert items/items.json.

    Returns:
        tuple: (synced_data, count, fixes)
    """
    data = load_json_safe(ITEMS_FILE)
    if not data:
        return {}, 0, 0

    if not isinstance(data, dict):
        print("    [FEHLER] items.json ist kein Dictionary!")
        return {}, 0, 0

    updated = {}
    total_fixes = 0

    for name, item in data.items():
        if isinstance(item, dict):
            fixed, fixes = sync_item(name, item)
            updated[name] = fixed
            if fixes:
                print(f"    {name}: {fixes} Korrekturen")
                total_fixes += fixes

    save_json(ITEMS_FILE, updated)
    return updated, len(updated), total_fixes


def sync_item_presets(global_items: dict) -> tuple[int, int]:
    """Synchronisiert items/presets/*.json mit globalen Items."""
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

            # Globales Item als Basis nehmen (falls vorhanden)
            if name in global_items:
                global_item = global_items[name]
                fixes = 0

                # Felder von global übernehmen wenn lokal fehlt
                for field in ["category", "priority", "confirm_point", "confirm_delay",
                              "template", "min_confidence"]:
                    if field not in item or item[field] is None:
                        if global_item.get(field) is not None:
                            item[field] = global_item[field]
                            fixes += 1

                fixed, extra_fixes = sync_item(name, item)
                updated[name] = fixed
                fixes_in_file += fixes

                if fixes > 0:
                    print(f"      {name}: {fixes} von global uebernommen")
            else:
                # Item nicht in global -> nur Defaults
                fixed, fixes = sync_item(name, item)
                updated[name] = fixed
                fixes_in_file += fixes
                if fixes > 0:
                    print(f"      {name}: {fixes} Fixes (nicht in global)")

        save_json(preset_file, updated)
        total_count += 1
        total_fixes += fixes_in_file

    return total_count, total_fixes


# ==============================================================================
# 6. SCAN CONFIGS SYNC
# ==============================================================================
def sync_scan_configs(global_items: dict) -> tuple[int, int, int]:
    """Synchronisiert item_scans/*.json mit globalen Items."""
    if not ITEM_SCANS_DIR.exists():
        return 0, 0, 0

    scan_files = list(ITEM_SCANS_DIR.glob("*.json"))
    total_updated = 0
    total_fixed = 0
    total_user = 0

    for scan_file in scan_files:
        data = load_json_safe(scan_file)
        if not data or not isinstance(data, dict):
            continue

        scan_name = data.get("name", scan_file.stem)
        print(f"\n    [{scan_name}]")

        # Basis-Felder
        if not data.get("name"):
            data["name"] = scan_file.stem
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
        fixed_items = []
        file_fixes = 0

        for item in items:
            if not isinstance(item, dict):
                continue

            item_name = item.get("name", "")

            if item_name and item_name in global_items:
                global_item = global_items[item_name]
                changes = []

                for field in ["category", "priority", "template", "min_confidence",
                              "confirm_point", "confirm_delay"]:
                    if item.get(field) != global_item.get(field):
                        item[field] = global_item.get(field)
                        changes.append(field)

                if changes:
                    print(f"      {item_name}: {', '.join(changes)}")
                    total_updated += 1

                fixed, fixes = sync_item(item_name, item)
                fixed["marker_colors"] = item.get("marker_colors", [])
                fixed_items.append(fixed)
                file_fixes += fixes

            elif item_name:
                print(f"\n      ! '{item_name}' nicht in globalen Items")
                similar = [n for n in global_items.keys()
                          if item_name.lower() in n.lower() or n.lower() in item_name.lower()]
                if similar:
                    print(f"        Aehnliche: {', '.join(similar[:5])}")

                print("        [Enter]=behalten, [d]=loeschen, [Name]=ersetzen")
                choice = input("        > ").strip()

                if choice.lower() == "d":
                    print("        -> geloescht")
                    total_user += 1
                elif choice in global_items:
                    fixed, _ = sync_item(choice, dict(global_items[choice]))
                    fixed["marker_colors"] = item.get("marker_colors", [])
                    fixed_items.append(fixed)
                    print(f"        -> ersetzt durch '{choice}'")
                    total_user += 1
                    total_updated += 1
                else:
                    fixed, fixes = sync_item(item_name, item)
                    fixed_items.append(fixed)
                    file_fixes += fixes
                    print("        -> behalten")

        data["items"] = fixed_items
        total_fixed += file_fixes

        save_json(scan_file, {
            "name": data["name"],
            "color_tolerance": data["color_tolerance"],
            "slots": data["slots"],
            "items": data["items"]
        })

    return total_updated, total_fixed, total_user


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    global POINTS

    print("\n" + "=" * 60)
    print("  SYNC-TOOL: Alle JSON-Dateien aktualisieren")
    print("=" * 60)
    print(f"\n  Verzeichnis: {SCRIPT_DIR}")
    print("\n  === GLOBALE DATEIEN ===")

    # 1. Config (global)
    print(f"\n  [1/8] Config...")
    count, fixes = sync_config()
    print(f"        {len(CONFIG_DEFAULTS)} Optionen, {fixes} Fixes")

    # 2. Points (laedt auch POINTS fuer spaeter)
    print(f"\n  [2/8] Points...")
    count, fixes = sync_points()
    print(f"        {count} Punkte, {fixes} Fixes")

    # 3. Sequences
    print(f"\n  [3/8] Sequences...")
    count, fixes = sync_sequences()
    print(f"        {count} Sequenzen, {fixes} Fixes")

    # 4. Slots (global) - gibt synced data direkt zurueck
    print(f"\n  [4/8] Slots global...")
    global_slots, count, fixes = sync_global_slots()
    print(f"        {count} Slots, {fixes} Fixes")

    # 5. Items (global) - gibt synced data direkt zurueck
    print(f"\n  [5/8] Items global...")
    global_items, count, fixes = sync_global_items()
    print(f"        {count} Items, {fixes} Fixes")

    # 6. Scans (global)
    print(f"\n  [6/8] Scans global...")
    updated, fixed, user = sync_scan_configs(global_items)
    print(f"        {updated} Scans, {fixed} Fixes")

    print("\n  === UNTERORDNER (PRESETS) ===")

    # 7. Slot presets (mit globalen Slots)
    print(f"\n  [7/8] Slot presets...")
    count, fixes = sync_slot_presets(global_slots)
    print(f"        {count} Presets, {fixes} Fixes")

    # 8. Item presets (mit globalen Items)
    print(f"\n  [8/8] Item presets...")
    count, fixes = sync_item_presets(global_items)
    print(f"        {count} Presets, {fixes} Fixes")

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
