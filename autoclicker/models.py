"""
Datenklassen für den Autoclicker.
Definiert alle Datenstrukturen wie ClickPoint, SequenceStep, Sequence, etc.
"""

import random
import threading
from dataclasses import dataclass, field
from typing import Optional

from .config import DEFAULT_MIN_CONFIDENCE


# =============================================================================
# DATENKLASSEN
# =============================================================================
@dataclass
class ClickPoint:
    """Ein Klickpunkt mit x,y Koordinaten und stabiler ID."""
    x: int
    y: int
    name: str = ""  # Optionaler Name für den Punkt
    id: int = 0     # Stabile ID für Referenzierung (bleibt bei Umsortierung erhalten)

    def __str__(self) -> str:
        if self.name:
            return f"#{self.id} {self.name} ({self.x}, {self.y})"
        return f"#{self.id} ({self.x}, {self.y})"


@dataclass
class SequenceStep:
    """Ein Schritt in einer Sequenz: Erst warten/prüfen, DANN klicken."""
    x: int                # X-Koordinate (direkt gespeichert)
    y: int                # Y-Koordinate (direkt gespeichert)
    delay_before: float   # Wartezeit in Sekunden VOR diesem Klick (0 = sofort)
    name: str = ""        # Optionaler Name des Punktes
    # Optional: Warten auf Farbe statt Zeit (VOR dem Klick)
    wait_pixel: Optional[tuple] = None   # (x, y) Position zum Prüfen
    wait_color: Optional[tuple] = None   # (r, g, b) Farbe die erscheinen soll
    wait_until_gone: bool = False        # True = warte bis Farbe WEG ist, False = warte bis Farbe DA ist
    # Optional: Item-Scan ausführen statt direktem Klick
    item_scan: Optional[str] = None      # Name des Item-Scans
    item_scan_mode: str = "all"          # "all" = bestes pro Kategorie, "best" = nur 1 Item total
    # Optional: Nur warten, nicht klicken
    wait_only: bool = False              # True = nur warten, kein Klick
    # Optional: Zufällige Verzögerung (delay_before bis delay_max)
    delay_max: Optional[float] = None    # None = feste Zeit, sonst Bereich
    # Optional: Tastendruck statt Mausklick
    key_press: Optional[str] = None      # z.B. "enter", "space", "f1"
    # Optional: Fallback/Else-Aktion wenn Bedingung fehlschlägt
    else_action: Optional[str] = None    # "skip", "restart", "click", "key"
    else_x: int = 0                      # X für Fallback-Klick
    else_y: int = 0                      # Y für Fallback-Klick
    else_delay: float = 0                # Delay vor Fallback
    else_key: Optional[str] = None       # Taste für Fallback
    else_name: str = ""                  # Name des Fallback-Punkts
    # Optional: Warten auf Zahl (Zahlenerkennung)
    wait_number_region: Optional[tuple] = None    # (x1, y1, x2, y2) Bereich
    wait_number_operator: Optional[str] = None    # ">", "<", "=", ">=", "<=", "!="
    wait_number_target: Optional[float] = None    # Zielwert
    wait_number_color: Optional[tuple] = None     # (R, G, B) Textfarbe (optional)

    def __str__(self) -> str:
        else_str = self._else_str()
        if self.key_press:
            delay_str = self._delay_str()
            return f"{delay_str} → drücke Taste '{self.key_press}'{else_str}"
        if self.item_scan:
            mode_strs = {"all": "bestes/Kategorie", "best": "1 bestes", "every": "JEDES"}
            mode_str = mode_strs.get(self.item_scan_mode, self.item_scan_mode)
            return f"SCAN '{self.item_scan}' → klicke {mode_str}{else_str}"
        if self.wait_number_region and self.wait_number_operator and self.wait_number_target is not None:
            target_str = f"{self.wait_number_target:,.0f}" if self.wait_number_target == int(self.wait_number_target) else f"{self.wait_number_target:,.2f}"
            if self.wait_only:
                return f"WARTE bis Zahl {self.wait_number_operator} {target_str} (kein Klick){else_str}"
            pos_str = f"{self.name} ({self.x}, {self.y})" if self.name else f"({self.x}, {self.y})"
            return f"warte bis Zahl {self.wait_number_operator} {target_str} → klicke {pos_str}{else_str}"
        if self.wait_only:
            if self.wait_pixel and self.wait_color:
                gone_str = "WEG ist" if self.wait_until_gone else "DA ist"
                return f"WARTE bis Farbe {gone_str} bei ({self.wait_pixel[0]},{self.wait_pixel[1]}) (kein Klick){else_str}"
            return f"WARTE {self._delay_str()} (kein Klick)"
        pos_str = f"{self.name} ({self.x}, {self.y})" if self.name else f"({self.x}, {self.y})"
        if self.wait_pixel and self.wait_color:
            gone_str = "bis Farbe WEG" if self.wait_until_gone else "auf Farbe"
            delay_str = self._delay_str()
            if self.delay_before > 0:
                return f"warte {delay_str}, dann {gone_str} bei ({self.wait_pixel[0]},{self.wait_pixel[1]}) → klicke {pos_str}{else_str}"
            return f"warte {gone_str} bei ({self.wait_pixel[0]},{self.wait_pixel[1]}) → klicke {pos_str}{else_str}"
        elif self.delay_before > 0:
            return f"warte {self._delay_str()} → klicke {pos_str}"
        else:
            return f"sofort → klicke {pos_str}"

    def _else_str(self) -> str:
        """Hilfsfunktion für Else-Anzeige."""
        if not self.else_action:
            return ""
        if self.else_action == "skip":
            return " | ELSE: skip"
        elif self.else_action == "restart":
            return " | ELSE: restart"
        elif self.else_action == "click":
            name = self.else_name or f"({self.else_x},{self.else_y})"
            return f" | ELSE: klicke {name}"
        elif self.else_action == "key":
            return f" | ELSE: Taste '{self.else_key}'"
        return ""

    def _delay_str(self) -> str:
        """Hilfsfunktion für Delay-Anzeige (fest oder Bereich)."""
        if self.delay_max and self.delay_max > self.delay_before:
            return f"{self.delay_before:.0f}-{self.delay_max:.0f}s"
        return f"{self.delay_before:.0f}s"

    def get_actual_delay(self) -> float:
        """Gibt die tatsächliche Verzögerung zurück (bei Bereich: zufällig)."""
        if self.delay_max and self.delay_max > self.delay_before:
            return random.uniform(self.delay_before, self.delay_max)
        return self.delay_before


@dataclass
class LoopPhase:
    """Eine Loop-Phase mit eigenen Schritten und Wiederholungen."""
    name: str
    steps: list[SequenceStep] = field(default_factory=list)
    repeat: int = 1  # Wie oft diese Phase wiederholt wird

    def __str__(self) -> str:
        step_count = len(self.steps)
        pixel_triggers = sum(1 for s in self.steps if s.wait_pixel)
        trigger_str = f" [Farb: {pixel_triggers}]" if pixel_triggers > 0 else ""
        return f"{self.name}: {step_count} Schritte x{self.repeat}{trigger_str}"


@dataclass
class Sequence:
    """Eine Klick-Sequenz mit Start-Phase, Loop-Phasen und End-Phase."""
    name: str
    start_steps: list[SequenceStep] = field(default_factory=list)  # Einmalig am Anfang
    loop_phases: list[LoopPhase] = field(default_factory=list)     # Mehrere Loop-Phasen
    end_steps: list[SequenceStep] = field(default_factory=list)    # Einmalig am Ende
    total_cycles: int = 1  # 0 = unendlich, >0 = wie oft alle Loops durchlaufen werden

    def __str__(self) -> str:
        start_count = len(self.start_steps)
        end_count = len(self.end_steps)
        loop_info = f"{len(self.loop_phases)} Loop(s)"
        if self.total_cycles == 0:
            loop_info += " ∞"
        elif self.total_cycles == 1:
            loop_info += " (1x)"
        else:
            loop_info += f" (x{self.total_cycles})"
        # Zähle alle Schritte mit Farb-Trigger
        all_steps = self.start_steps + [s for lp in self.loop_phases for s in lp.steps] + self.end_steps
        pixel_triggers = sum(1 for s in all_steps if s.wait_pixel)
        trigger_str = f" [Farb-Trigger: {pixel_triggers}]" if pixel_triggers > 0 else ""
        end_str = f", End: {end_count}" if end_count > 0 else ""
        return f"{self.name} (Start: {start_count}, {loop_info}{end_str}){trigger_str}"

    def total_steps(self) -> int:
        return len(self.start_steps) + sum(len(lp.steps) for lp in self.loop_phases) + len(self.end_steps)


# =============================================================================
# ITEM-SCAN DATENKLASSEN
# =============================================================================
@dataclass
class ItemProfile:
    """Ein Item-Typ mit Marker-Farben und/oder Template-Matching."""
    name: str
    marker_colors: list[tuple] = field(default_factory=list)  # Liste von (r,g,b) Marker-Farben
    # Kategorie für Prioritäts-Vergleich (z.B. "Hosen", "Jacken", "Juwelen")
    category: Optional[str] = None  # Wenn None, ist jedes Item seine eigene Kategorie
    priority: int = 1  # 1 = beste, höher = schlechter (innerhalb der Kategorie)
    confirm_point: Optional[ClickPoint] = None  # ClickPoint für Bestätigung nach Klick
    confirm_delay: float = 0.5  # Wartezeit vor Bestätigungs-Klick
    # Template Matching (optional - überschreibt marker_colors wenn gesetzt)
    template: Optional[str] = None  # Dateiname des Template-Bildes (in items/templates/)
    min_confidence: float = DEFAULT_MIN_CONFIDENCE  # Mindest-Konfidenz für Template-Match

    def __str__(self) -> str:
        if self.template:
            template_str = f"Template: {self.template} (≥{self.min_confidence:.0%})"
        else:
            colors_str = ", ".join([f"RGB{c}" for c in self.marker_colors[:3]])
            if len(self.marker_colors) > 3:
                colors_str += f" (+{len(self.marker_colors)-3})"
            template_str = colors_str if colors_str else "keine Marker"
        confirm_str = f" → ({self.confirm_point.x},{self.confirm_point.y})" if self.confirm_point else ""
        category_str = f" [{self.category}]" if self.category else ""
        return f"[P{self.priority}]{category_str} {self.name}: {template_str}{confirm_str}"


@dataclass
class ItemSlot:
    """Ein Slot wo Items erscheinen können."""
    name: str
    scan_region: tuple  # (x1, y1, x2, y2) Bereich zum Scannen
    click_pos: tuple    # (x, y) Wo geklickt werden soll
    slot_color: Optional[tuple] = None  # RGB-Farbe des leeren Slots (wird bei Items ausgeschlossen)

    def __str__(self) -> str:
        r = self.scan_region
        color_str = f", Hintergrund: RGB{self.slot_color}" if self.slot_color else ""
        return f"{self.name}: Scan ({r[0]},{r[1]})-({r[2]},{r[3]}){color_str}"


@dataclass
class ItemScanConfig:
    """Konfiguration für Item-Erkennung und -Vergleich."""
    name: str
    slots: list[ItemSlot] = field(default_factory=list)      # Wo gescannt wird
    items: list[ItemProfile] = field(default_factory=list)   # Welche Items erkannt werden
    color_tolerance: int = 40  # Farbtoleranz für Erkennung

    def __str__(self) -> str:
        return f"{self.name} ({len(self.slots)} Slots, {len(self.items)} Items)"


# =============================================================================
# AUTOCLICKER STATE
# =============================================================================
@dataclass
class AutoClickerState:
    """Zustand des Autoclickers."""
    # Punkte-Pool (wiederverwendbar)
    points: list[ClickPoint] = field(default_factory=list)

    # Gespeicherte Sequenzen
    sequences: dict[str, Sequence] = field(default_factory=dict)

    # Globale Slots und Items (wiederverwendbar)
    global_slots: dict[str, ItemSlot] = field(default_factory=dict)
    global_items: dict[str, ItemProfile] = field(default_factory=dict)

    # Item-Scan Konfigurationen (verknüpft Slots + Items)
    item_scans: dict[str, ItemScanConfig] = field(default_factory=dict)

    # Aktive Sequenz
    active_sequence: Optional[Sequence] = None

    # Laufzeit-Status
    is_running: bool = False
    total_clicks: int = 0

    # Statistiken
    items_found: int = 0
    key_presses: int = 0
    start_time: Optional[float] = None

    # Bereits geklickte Kategorien im aktuellen Zyklus mit bester Priorität
    # Dict: {kategorie: beste_priorität} - verhindert schlechtere Items derselben Kategorie
    clicked_categories: dict = field(default_factory=dict)

    # Thread-sichere Events
    stop_event: threading.Event = field(default_factory=threading.Event)
    quit_event: threading.Event = field(default_factory=threading.Event)
    pause_event: threading.Event = field(default_factory=threading.Event)
    skip_event: threading.Event = field(default_factory=threading.Event)
    restart_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # Flag für geplanten Start (überspringt Debug-Enter-Prompt)
    scheduled_start: bool = False

    # Flag für aktiven Countdown (verhindert Sequenz-Start durch CTRL+ALT+S)
    countdown_active: bool = False

    # Konfiguration (thread-safe über lock)
    config: dict = field(default_factory=dict)
