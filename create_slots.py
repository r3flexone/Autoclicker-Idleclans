#!/usr/bin/env python3
"""
Hilfsskript zum automatischen Erstellen einer Slot-Reihe.
Erstellt die slots.json Datei für den Autoclicker.
"""

# DPI-Awareness MUSS vor allem anderen stehen (für Multi-Monitor)!
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import json
from ctypes import wintypes

# Windows API
user32 = ctypes.windll.user32

def get_cursor_pos():
    """Liest die aktuelle Mausposition."""
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y

def wait_for_position(prompt):
    """Wartet auf ENTER und gibt die Mausposition zurück."""
    print(prompt)
    input("  → Maus positionieren, ENTER drücken...")
    pos = get_cursor_pos()
    print(f"  → Position: {pos}")
    return pos

def main():
    print("=" * 60)
    print("  SLOT-REIHE ERSTELLEN")
    print("=" * 60)

    print("\nSchritt 1: Ersten Slot markieren")
    print("-" * 40)
    top_left_1 = wait_for_position("Ecke OBEN-LINKS des ERSTEN Slots:")
    bottom_right_1 = wait_for_position("Ecke UNTEN-RECHTS des ERSTEN Slots:")
    click_1 = wait_for_position("KLICK-Position des ERSTEN Slots (Mitte):")

    # Slot-Größe berechnen
    slot_width = bottom_right_1[0] - top_left_1[0]
    slot_height = bottom_right_1[1] - top_left_1[1]
    print(f"\n  Slot-Größe: {slot_width} x {slot_height} Pixel")

    print("\nSchritt 2: Letzten Slot markieren")
    print("-" * 40)
    top_left_last = wait_for_position("Ecke OBEN-LINKS des LETZTEN Slots:")

    # Anzahl Slots und Abstand berechnen
    try:
        num_slots = int(input("\nAnzahl Slots in der Reihe: ").strip())
    except ValueError:
        num_slots = 10

    if num_slots < 2:
        print("Mindestens 2 Slots erforderlich!")
        return

    # Abstand zwischen Slots berechnen
    total_distance = top_left_last[0] - top_left_1[0]
    spacing = total_distance / (num_slots - 1)
    print(f"  Abstand zwischen Slots: {spacing:.1f} Pixel")

    # Hintergrundfarbe optional
    print("\nSchritt 3: Hintergrundfarbe (optional)")
    print("-" * 40)
    bg_color = None
    if input("Hintergrundfarbe aufnehmen? (j/n): ").strip().lower() == "j":
        print("Maus auf den leeren Slot-Hintergrund bewegen...")
        input("  → ENTER drücken...")
        x, y = get_cursor_pos()

        # Pixel-Farbe lesen
        hdc = user32.GetDC(0)
        gdi32 = ctypes.windll.gdi32
        color = gdi32.GetPixel(hdc, x, y)
        user32.ReleaseDC(0, hdc)

        if color != -1:
            r = color & 0xFF
            g = (color >> 8) & 0xFF
            b = (color >> 16) & 0xFF
            # Auf 5er runden
            bg_color = [r // 5 * 5, g // 5 * 5, b // 5 * 5]
            print(f"  → Hintergrund: RGB{tuple(bg_color)}")

    # Slots generieren
    print("\n" + "=" * 60)
    print("  GENERIERE SLOTS")
    print("=" * 60)

    slots = {}
    for i in range(num_slots):
        name = f"Slot {i + 1}"

        # Position berechnen
        offset_x = int(i * spacing)

        scan_region = [
            top_left_1[0] + offset_x,
            top_left_1[1],
            top_left_1[0] + offset_x + slot_width,
            top_left_1[1] + slot_height
        ]

        # Klick-Position (relativ zum ersten Slot)
        click_offset_x = click_1[0] - top_left_1[0]
        click_offset_y = click_1[1] - top_left_1[1]
        click_pos = [
            top_left_1[0] + offset_x + click_offset_x,
            top_left_1[1] + click_offset_y
        ]

        slots[name] = {
            "name": name,
            "scan_region": scan_region,
            "click_pos": click_pos,
            "slot_color": bg_color
        }

        print(f"  {name}: Region ({scan_region[0]},{scan_region[1]})-({scan_region[2]},{scan_region[3]})")

    # Speichern
    print("\n" + "=" * 60)
    with open("slots.json", "w", encoding="utf-8") as f:
        json.dump(slots, f, indent=2, ensure_ascii=False)

    print(f"[ERFOLG] {num_slots} Slots in 'slots.json' gespeichert!")
    print("\nDu kannst den Autoclicker jetzt starten.")
    print("Die Slots werden automatisch geladen.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[ABBRUCH]")
    except Exception as e:
        print(f"\n[FEHLER] {e}")

    input("\nENTER zum Beenden...")
