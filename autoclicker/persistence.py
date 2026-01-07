"""
Persistenz-Funktionen für den Autoclicker.
Speichern/Laden von Sequenzen, Punkten, Slots, Items, Scans.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .config import SEQUENCES_DIR, DEFAULT_MIN_CONFIDENCE, CONFIG, save_config
from .models import (
    ClickPoint, SequenceStep, LoopPhase, Sequence,
    ItemProfile, ItemSlot, ItemScanConfig, AutoClickerState
)
from .utils import compact_json, sanitize_filename

if TYPE_CHECKING:
    pass

# Logger
logger = logging.getLogger("autoclicker")

# Verzeichnisse
ITEM_SCANS_DIR: str = "item_scans"
SLOTS_DIR: str = "slots"
ITEMS_DIR: str = "items"
SCREENSHOTS_DIR: str = os.path.join(SLOTS_DIR, "Screenshots")
TEMPLATES_DIR: str = os.path.join(ITEMS_DIR, "templates")
SLOT_PRESETS_DIR: str = os.path.join(SLOTS_DIR, "presets")
ITEM_PRESETS_DIR: str = os.path.join(ITEMS_DIR, "presets")


def _get_active_slot_preset_path() -> Path:
    """Gibt den Pfad zum aktiven Slot-Preset zurück."""
    preset_name = CONFIG.get("active_slot_preset", "default")
    return Path(SLOT_PRESETS_DIR) / f"{sanitize_filename(preset_name)}.json"


def _get_active_item_preset_path() -> Path:
    """Gibt den Pfad zum aktiven Item-Preset zurück."""
    preset_name = CONFIG.get("active_item_preset", "default")
    return Path(ITEM_PRESETS_DIR) / f"{sanitize_filename(preset_name)}.json"


def init_directories() -> None:
    """Erstellt alle benötigten Verzeichnisse."""
    for folder in [ITEM_SCANS_DIR, SLOTS_DIR, ITEMS_DIR, SCREENSHOTS_DIR,
                   TEMPLATES_DIR, SLOT_PRESETS_DIR, ITEM_PRESETS_DIR]:
        os.makedirs(folder, exist_ok=True)


def migrate_old_global_files() -> None:
    """Migriert alte slots.json/items.json zu default Presets.

    Wird beim Start aufgerufen um alte Dateien zu migrieren:
    - slots/slots.json → slots/presets/default.json
    - items/items.json → items/presets/default.json
    """
    # Alte Pfade
    old_slots_file = Path(SLOTS_DIR) / "slots.json"
    old_items_file = Path(ITEMS_DIR) / "items.json"

    # Neue Pfade (default Presets)
    new_slots_file = Path(SLOT_PRESETS_DIR) / "default.json"
    new_items_file = Path(ITEM_PRESETS_DIR) / "default.json"

    migrated = []

    # Slots migrieren
    if old_slots_file.exists() and not new_slots_file.exists():
        try:
            new_slots_file.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.move(str(old_slots_file), str(new_slots_file))
            migrated.append(f"slots.json → presets/default.json")
        except (IOError, OSError) as e:
            logger.error(f"Slot-Migration fehlgeschlagen: {e}")

    # Items migrieren
    if old_items_file.exists() and not new_items_file.exists():
        try:
            new_items_file.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.move(str(old_items_file), str(new_items_file))
            migrated.append(f"items.json → presets/default.json")
        except (IOError, OSError) as e:
            logger.error(f"Item-Migration fehlgeschlagen: {e}")

    if migrated:
        print(f"[MIGRATION] Alte Dateien migriert: {', '.join(migrated)}")


# =============================================================================
# SEQUENZ-PERSISTENZ
# =============================================================================
def ensure_sequences_dir() -> Path:
    """Stellt sicher, dass der Sequenzen-Ordner existiert."""
    path = Path(SEQUENCES_DIR)
    path.mkdir(exist_ok=True)
    return path


def save_data(state: AutoClickerState) -> None:
    """Speichert Punkte und Sequenzen in JSON-Dateien."""
    ensure_sequences_dir()

    # Punkte speichern (mit stabiler ID)
    points_data = [{"id": p.id, "x": p.x, "y": p.y, "name": p.name} for p in state.points]
    with open(Path(SEQUENCES_DIR) / "points.json", "w", encoding="utf-8") as f:
        f.write(compact_json(points_data))

    # Sequenzen speichern (mit Start + mehreren Loop-Phasen)
    def step_to_dict(s: SequenceStep) -> dict:
        return {"x": s.x, "y": s.y, "name": s.name, "delay_before": s.delay_before,
                "wait_pixel": s.wait_pixel, "wait_color": s.wait_color,
                "wait_until_gone": s.wait_until_gone,
                "item_scan": s.item_scan, "item_scan_mode": s.item_scan_mode,
                "wait_only": s.wait_only, "delay_max": s.delay_max,
                "key_press": s.key_press, "else_action": s.else_action,
                "else_x": s.else_x, "else_y": s.else_y, "else_delay": s.else_delay,
                "else_key": s.else_key, "else_name": s.else_name,
                "wait_number_region": s.wait_number_region,
                "wait_number_operator": s.wait_number_operator,
                "wait_number_target": s.wait_number_target,
                "wait_number_color": s.wait_number_color,
                "wait_scan": s.wait_scan,
                "wait_scan_item": s.wait_scan_item,
                "wait_scan_gone": s.wait_scan_gone}

    for name, seq in state.sequences.items():
        seq_data = {
            "name": seq.name,
            "total_cycles": seq.total_cycles,
            "start_steps": [step_to_dict(s) for s in seq.start_steps],
            "loop_phases": [
                {
                    "name": lp.name,
                    "repeat": lp.repeat,
                    "steps": [step_to_dict(s) for s in lp.steps]
                }
                for lp in seq.loop_phases
            ],
            "end_steps": [step_to_dict(s) for s in seq.end_steps]
        }
        filename = f"{sanitize_filename(name)}.json"
        with open(Path(SEQUENCES_DIR) / filename, "w", encoding="utf-8") as f:
            f.write(compact_json(seq_data))

    print(f"[SAVE] Daten gespeichert in '{SEQUENCES_DIR}/'")


def load_points(state: AutoClickerState) -> None:
    """Lädt gespeicherte Punkte."""
    points_file = Path(SEQUENCES_DIR) / "points.json"
    if points_file.exists():
        try:
            with open(points_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Lade Punkte mit ID (Fallback für alte Dateien ohne ID)
                state.points = []
                for i, p in enumerate(data):
                    point_id = p.get("id", i + 1)  # Fallback: Index + 1 für alte Dateien
                    state.points.append(ClickPoint(p["x"], p["y"], p.get("name", ""), point_id))
            print(f"[LOAD] {len(state.points)} Punkt(e) geladen")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"[WARNUNG] points.json konnte nicht geladen werden: {e}")
            print("[INFO] Starte mit leerer Punktliste.")
            state.points = []
    else:
        print("[INFO] Keine gespeicherten Punkte gefunden.")


def get_next_point_id(state: AutoClickerState) -> int:
    """Gibt die nächste freie Punkt-ID zurück."""
    if not state.points:
        return 1
    return max(p.id for p in state.points) + 1


def get_point_by_id(state: AutoClickerState, point_id: int) -> Optional[ClickPoint]:
    """Findet einen Punkt anhand seiner ID."""
    for p in state.points:
        if p.id == point_id:
            return p
    return None


def load_sequence_file(filepath: Path) -> Optional[Sequence]:
    """Lädt eine einzelne Sequenz-Datei (mit Start + mehreren Loop-Phasen)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

            def parse_steps(steps_data: list) -> list[SequenceStep]:
                steps = []
                for s in steps_data:
                    wait_pixel = s.get("wait_pixel")
                    if wait_pixel:
                        wait_pixel = tuple(int(v) for v in wait_pixel)
                    wait_color = s.get("wait_color")
                    if wait_color:
                        wait_color = tuple(int(v) for v in wait_color)
                    # Unterstütze beide Formate: delay_before (neu) und delay_after (alt)
                    delay_raw = s.get("delay_before")
                    if delay_raw is None:
                        delay_raw = s.get("delay_after")
                    if delay_raw is None:
                        delay_raw = 0
                    delay_max_raw = s.get("delay_max")
                    # Zahlenerkennung-Felder
                    wait_number_region = s.get("wait_number_region")
                    if wait_number_region:
                        wait_number_region = tuple(int(v) for v in wait_number_region)
                    wait_number_color = s.get("wait_number_color")
                    if wait_number_color:
                        wait_number_color = tuple(int(v) for v in wait_number_color)

                    step = SequenceStep(
                        x=s.get("x", 0),
                        y=s.get("y", 0),
                        delay_before=float(delay_raw),
                        name=s.get("name", ""),
                        wait_pixel=wait_pixel,
                        wait_color=wait_color,
                        wait_until_gone=s.get("wait_until_gone", False),
                        item_scan=s.get("item_scan"),
                        item_scan_mode=s.get("item_scan_mode", "all"),
                        wait_only=s.get("wait_only", False),
                        delay_max=float(delay_max_raw) if delay_max_raw is not None else None,
                        key_press=s.get("key_press"),
                        else_action=s.get("else_action"),
                        else_x=s.get("else_x", 0),
                        else_y=s.get("else_y", 0),
                        else_delay=s.get("else_delay", 0),
                        else_key=s.get("else_key"),
                        else_name=s.get("else_name", ""),
                        wait_number_region=wait_number_region,
                        wait_number_operator=s.get("wait_number_operator"),
                        wait_number_target=s.get("wait_number_target"),
                        wait_number_color=wait_number_color,
                        wait_scan=s.get("wait_scan"),
                        wait_scan_item=s.get("wait_scan_item"),
                        wait_scan_gone=s.get("wait_scan_gone", False)
                    )
                    steps.append(step)
                return steps

            start_steps = parse_steps(data.get("start_steps", []))
            end_steps = parse_steps(data.get("end_steps", []))

            # Neues Format mit loop_phases (mehrere Loop-Phasen)
            if "loop_phases" in data:
                loop_phases = []
                for lp_data in data["loop_phases"]:
                    lp = LoopPhase(
                        name=lp_data.get("name", "Loop"),
                        steps=parse_steps(lp_data.get("steps", [])),
                        repeat=lp_data.get("repeat", 1)
                    )
                    loop_phases.append(lp)
                total_cycles = data.get("total_cycles", 1)
                return Sequence(data["name"], start_steps, loop_phases, end_steps, total_cycles)

            # Altes Format mit loop_steps (eine Loop-Phase) - konvertieren
            elif "loop_steps" in data:
                loop_steps = parse_steps(data.get("loop_steps", []))
                max_loops = data.get("max_loops", 0)
                # Konvertiere zu neuem Format: eine LoopPhase
                if loop_steps:
                    loop_phases = [LoopPhase("Loop 1", loop_steps, max_loops if max_loops > 0 else 1)]
                    total_cycles = 0 if max_loops == 0 else 1  # 0 = unendlich
                else:
                    loop_phases = []
                    total_cycles = 1
                return Sequence(data["name"], start_steps, loop_phases, end_steps, total_cycles)

            # Uraltes Format (nur steps) - konvertieren
            elif "steps" in data:
                loop_steps = parse_steps(data["steps"])
                loop_phases = [LoopPhase("Loop 1", loop_steps, 1)] if loop_steps else []
                return Sequence(data["name"], [], loop_phases, [], 0)

            else:
                return Sequence(data["name"], [], [], [], 1)

    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


def list_available_sequences() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Sequenz-Dateien auf."""
    seq_dir = Path(SEQUENCES_DIR)
    if not seq_dir.exists():
        return []

    sequences = []
    for f in seq_dir.glob("*.json"):
        if f.name != "points.json":
            try:
                with open(f, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    name = data.get("name", f.stem)
                    sequences.append((name, f))
            except (json.JSONDecodeError, IOError, KeyError):
                pass  # Ungültige/korrupte Datei überspringen
    return sequences


# =============================================================================
# ITEM-SCAN PERSISTENZ
# =============================================================================
def ensure_item_scans_dir() -> Path:
    """Stellt sicher, dass der Item-Scans-Ordner existiert."""
    path = Path(ITEM_SCANS_DIR)
    path.mkdir(exist_ok=True)
    return path


def save_item_scan(config: ItemScanConfig) -> None:
    """Speichert eine Item-Scan Konfiguration."""
    ensure_item_scans_dir()

    data = {
        "name": config.name,
        "color_tolerance": config.color_tolerance,
        "slots": [_serialize_slot(slot) for slot in config.slots],
        "items": [_serialize_item(item) for item in config.items]
    }

    filename = f"{sanitize_filename(config.name)}.json"
    with open(Path(ITEM_SCANS_DIR) / filename, "w", encoding="utf-8") as f:
        f.write(compact_json(data))

    print(f"[SAVE] Item-Scan '{config.name}' gespeichert in '{ITEM_SCANS_DIR}/'")


def load_item_scan_file(filepath: Path) -> Optional[ItemScanConfig]:
    """Lädt eine Item-Scan Konfiguration."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return ItemScanConfig(
                name=data["name"],
                slots=[_deserialize_slot(s) for s in data.get("slots", [])],
                items=[_deserialize_item(i) for i in data.get("items", [])],
                color_tolerance=data.get("color_tolerance", 40)
            )
    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


def list_available_item_scans() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Item-Scan Konfigurationen auf."""
    scan_dir = Path(ITEM_SCANS_DIR)
    if not scan_dir.exists():
        return []

    scans = []
    for f in scan_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                name = data.get("name", f.stem)
                scans.append((name, f))
        except (json.JSONDecodeError, IOError, KeyError):
            pass  # Ungültige/korrupte Datei überspringen
    return scans


def load_all_item_scans(state: AutoClickerState) -> None:
    """Lädt alle Item-Scan Konfigurationen."""
    for name, path in list_available_item_scans():
        config = load_item_scan_file(path)
        if config:
            state.item_scans[config.name] = config
    if state.item_scans:
        print(f"[LOAD] {len(state.item_scans)} Item-Scan(s) geladen")


# =============================================================================
# SLOTS UND ITEMS PERSISTENZ (direkt aus aktiven Presets)
# =============================================================================
def save_global_slots(state: AutoClickerState) -> None:
    """Speichert Slots in das aktive Preset."""
    preset_path = _get_active_slot_preset_path()
    preset_path.parent.mkdir(parents=True, exist_ok=True)

    data = {name: _serialize_slot(slot) for name, slot in state.global_slots.items()}
    with open(preset_path, "w", encoding="utf-8") as f:
        f.write(compact_json(data))

    preset_name = CONFIG.get("active_slot_preset", "default")
    print(f"[SAVE] {len(state.global_slots)} Slot(s) → '{preset_name}'")


def load_global_slots(state: AutoClickerState) -> None:
    """Lädt Slots aus dem aktiven Preset."""
    preset_path = _get_active_slot_preset_path()
    preset_name = CONFIG.get("active_slot_preset", "default")

    if not preset_path.exists():
        # Erstelle leeres default Preset falls nicht vorhanden
        if preset_name == "default":
            preset_path.parent.mkdir(parents=True, exist_ok=True)
            with open(preset_path, "w", encoding="utf-8") as f:
                f.write("{}")
        return

    try:
        with open(preset_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        state.global_slots.clear()
        for name, s in data.items():
            state.global_slots[name] = _deserialize_slot(s)
        if state.global_slots:
            print(f"[LOAD] {len(state.global_slots)} Slot(s) ← '{preset_name}'")
    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Slots laden fehlgeschlagen: {e}")


def save_global_items(state: AutoClickerState) -> None:
    """Speichert Items in das aktive Preset."""
    preset_path = _get_active_item_preset_path()
    preset_path.parent.mkdir(parents=True, exist_ok=True)

    data = {name: _serialize_item(item) for name, item in state.global_items.items()}
    with open(preset_path, "w", encoding="utf-8") as f:
        f.write(compact_json(data))

    preset_name = CONFIG.get("active_item_preset", "default")
    print(f"[SAVE] {len(state.global_items)} Item(s) → '{preset_name}'")


def load_global_items(state: AutoClickerState) -> None:
    """Lädt Items aus dem aktiven Preset."""
    preset_path = _get_active_item_preset_path()
    preset_name = CONFIG.get("active_item_preset", "default")

    if not preset_path.exists():
        # Erstelle leeres default Preset falls nicht vorhanden
        if preset_name == "default":
            preset_path.parent.mkdir(parents=True, exist_ok=True)
            with open(preset_path, "w", encoding="utf-8") as f:
                f.write("{}")
        return

    try:
        with open(preset_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        state.global_items.clear()
        for name, i in data.items():
            state.global_items[name] = _deserialize_item(i)
        if state.global_items:
            print(f"[LOAD] {len(state.global_items)} Item(s) ← '{preset_name}'")
    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Items laden fehlgeschlagen: {e}")


# =============================================================================
# SLOT UND ITEM PRESETS
# =============================================================================
def list_slot_presets() -> list[tuple[str, Path, int, bool]]:
    """Listet alle verfügbaren Slot-Presets auf.

    Returns:
        Liste von (name, path, count, is_active) Tupeln
    """
    preset_dir = Path(SLOT_PRESETS_DIR)
    if not preset_dir.exists():
        return []

    active_preset = CONFIG.get("active_slot_preset", "default")
    presets = []
    for f in preset_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                name = f.stem
                count = len(data)
                is_active = (name == active_preset)
                presets.append((name, f, count, is_active))
        except (json.JSONDecodeError, IOError, KeyError, TypeError):
            pass
    return presets


def save_slot_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Speichert aktuelle Slots als neues Preset und wechselt dorthin."""
    if not state.global_slots:
        print("[FEHLER] Keine Slots vorhanden zum Speichern!")
        return False

    safe_name = sanitize_filename(preset_name)

    # Wechsle zum neuen Preset
    CONFIG["active_slot_preset"] = safe_name
    save_config(CONFIG)

    # Speichere in das neue Preset
    save_global_slots(state)
    return True


def load_slot_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Wechselt zum angegebenen Slot-Preset."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(SLOT_PRESETS_DIR) / f"{safe_name}.json"

    if not filepath.exists():
        print(f"[FEHLER] Preset '{preset_name}' nicht gefunden!")
        return False

    # Wechsle zum Preset
    CONFIG["active_slot_preset"] = safe_name
    save_config(CONFIG)

    # Lade Slots aus dem neuen Preset
    load_global_slots(state)
    return True


def delete_slot_preset(preset_name: str) -> bool:
    """Löscht ein Slot-Preset (nicht das aktive!)."""
    safe_name = sanitize_filename(preset_name)
    active_preset = CONFIG.get("active_slot_preset", "default")

    if safe_name == active_preset:
        print(f"[FEHLER] Kann aktives Preset '{preset_name}' nicht löschen!")
        return False

    filepath = Path(SLOT_PRESETS_DIR) / f"{safe_name}.json"
    if not filepath.exists():
        print(f"[FEHLER] Preset '{preset_name}' nicht gefunden!")
        return False

    filepath.unlink()
    print(f"[DELETE] Slot-Preset '{preset_name}' gelöscht")
    return True


def list_item_presets() -> list[tuple[str, Path, int, bool]]:
    """Listet alle verfügbaren Item-Presets auf.

    Returns:
        Liste von (name, path, count, is_active) Tupeln
    """
    preset_dir = Path(ITEM_PRESETS_DIR)
    if not preset_dir.exists():
        return []

    active_preset = CONFIG.get("active_item_preset", "default")
    presets = []
    for f in preset_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                name = f.stem
                count = len(data)
                is_active = (name == active_preset)
                presets.append((name, f, count, is_active))
        except (json.JSONDecodeError, IOError, KeyError, TypeError):
            pass
    return presets


def save_item_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Speichert aktuelle Items als neues Preset und wechselt dorthin."""
    if not state.global_items:
        print("[FEHLER] Keine Items vorhanden zum Speichern!")
        return False

    safe_name = sanitize_filename(preset_name)

    # Wechsle zum neuen Preset
    CONFIG["active_item_preset"] = safe_name
    save_config(CONFIG)

    # Speichere in das neue Preset
    save_global_items(state)
    return True


def load_item_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Wechselt zum angegebenen Item-Preset."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(ITEM_PRESETS_DIR) / f"{safe_name}.json"

    if not filepath.exists():
        print(f"[FEHLER] Preset '{preset_name}' nicht gefunden!")
        return False

    # Wechsle zum Preset
    CONFIG["active_item_preset"] = safe_name
    save_config(CONFIG)

    # Lade Items aus dem neuen Preset
    load_global_items(state)
    return True


def delete_item_preset(preset_name: str) -> bool:
    """Löscht ein Item-Preset (nicht das aktive!)."""
    safe_name = sanitize_filename(preset_name)
    active_preset = CONFIG.get("active_item_preset", "default")

    if safe_name == active_preset:
        print(f"[FEHLER] Kann aktives Preset '{preset_name}' nicht löschen!")
        return False

    filepath = Path(ITEM_PRESETS_DIR) / f"{safe_name}.json"
    if not filepath.exists():
        print(f"[FEHLER] Preset '{preset_name}' nicht gefunden!")
        return False

    filepath.unlink()
    print(f"[DELETE] Item-Preset '{preset_name}' gelöscht")
    return True


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================
def _serialize_slot(slot: ItemSlot) -> dict:
    """Serialisiert einen ItemSlot zu dict."""
    return {
        "name": slot.name,
        "scan_region": list(slot.scan_region),
        "click_pos": list(slot.click_pos),
        "slot_color": list(slot.slot_color) if slot.slot_color else None
    }


def _deserialize_slot(data: dict) -> ItemSlot:
    """Deserialisiert dict zu ItemSlot."""
    slot_color = tuple(data["slot_color"]) if data.get("slot_color") else None
    return ItemSlot(
        name=data["name"],
        scan_region=tuple(data["scan_region"]),
        click_pos=tuple(data["click_pos"]),
        slot_color=slot_color
    )


def _serialize_item(item: ItemProfile) -> dict:
    """Serialisiert ein ItemProfile zu dict."""
    return {
        "name": item.name,
        "marker_colors": [list(c) for c in item.marker_colors] if item.marker_colors else [],
        "category": item.category,
        "priority": item.priority,
        "confirm_point": {"x": item.confirm_point.x, "y": item.confirm_point.y} if item.confirm_point else None,
        "confirm_delay": item.confirm_delay,
        "template": item.template,
        "min_confidence": item.min_confidence
    }


def _deserialize_item(data: dict) -> ItemProfile:
    """Deserialisiert dict zu ItemProfile."""
    # confirm_point: kann {x, y} Dict, [x,y] Liste (alt) oder None sein
    cp_data = data.get("confirm_point")
    cp = None
    if cp_data:
        if isinstance(cp_data, dict) and "x" in cp_data and "y" in cp_data:
            cp = ClickPoint(cp_data["x"], cp_data["y"])
        elif isinstance(cp_data, list) and len(cp_data) == 2:
            cp = ClickPoint(cp_data[0], cp_data[1])  # Alte Format-Unterstützung
    return ItemProfile(
        name=data["name"],
        marker_colors=[tuple(c) for c in data.get("marker_colors", [])],
        category=data.get("category"),
        priority=data.get("priority", 1),
        confirm_point=cp,
        confirm_delay=data.get("confirm_delay", 0.5),
        template=data.get("template"),
        min_confidence=data.get("min_confidence", DEFAULT_MIN_CONFIDENCE)
    )


def get_existing_categories(state: AutoClickerState) -> list[str]:
    """Sammelt alle existierenden Kategorien aus den Items."""
    categories = set()
    for item in state.global_items.values():
        if item.category:
            categories.add(item.category)
    return sorted(categories)


def shift_category_priorities(state: AutoClickerState, category: str) -> int:
    """Verschiebt alle Items einer Kategorie um +1 in der Priorität."""
    if not category:
        return 0

    shifted = 0
    with state.lock:
        for item in state.global_items.values():
            if item.category == category:
                item.priority += 1
                shifted += 1

    if shifted > 0:
        save_global_items(state)
        print(f"  → {shifted} Item(s) in Kategorie '{category}' nach hinten verschoben")

    return shifted


def update_item_in_scans(old_name: str, new_name: str, new_template: Optional[str] = None) -> int:
    """Aktualisiert ein Item in allen Scan-Konfigurationen."""
    updated_scans = 0
    scan_dir = Path(ITEM_SCANS_DIR)

    if not scan_dir.exists():
        return 0

    for scan_file in scan_dir.glob("*.json"):
        try:
            with open(scan_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            modified = False
            for item in data.get("items", []):
                if item.get("name") == old_name:
                    item["name"] = new_name
                    if new_template:
                        item["template"] = new_template
                    modified = True

            if modified:
                with open(scan_file, "w", encoding="utf-8") as f:
                    f.write(compact_json(data))
                updated_scans += 1

        except (json.JSONDecodeError, IOError, KeyError) as e:
            print(f"  [WARNUNG] Konnte {scan_file.name} nicht aktualisieren: {e}")

    return updated_scans


def print_points(state: AutoClickerState) -> None:
    """Zeigt alle gespeicherten Punkte an."""
    with state.lock:
        if not state.points:
            print("\n[INFO] Keine Punkte vorhanden.")
            print("       Punkte mit CTRL+ALT+A aufnehmen.")
            return

        print(f"\nGespeicherte Punkte ({len(state.points)}):")
        print("-" * 50)
        for p in state.points:
            print(f"  #{p.id:3d} {p.name:20s} ({p.x:4d}, {p.y:4d})")
        print("-" * 50)
