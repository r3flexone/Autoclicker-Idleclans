#!/usr/bin/env python3
"""
Automatische Slot-Erkennung per Bilderkennung.
Erkennt die türkisen Slot-Rahmen und erstellt slots.json.

Benötigt: pip install opencv-python pillow
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
import sys
from ctypes import wintypes

try:
    import cv2
    import numpy as np
    from PIL import ImageGrab
except ImportError:
    print("[FEHLER] Benötigte Pakete nicht installiert!")
    print("         pip install opencv-python pillow numpy")
    sys.exit(1)

# Windows API
user32 = ctypes.windll.user32

def get_cursor_pos():
    """Liest die aktuelle Mausposition."""
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y

def select_region():
    """Lässt den User einen Bereich auswählen."""
    print("\n  Bereich auswählen:")
    print("  Maus auf OBEN-LINKS bewegen, ENTER drücken...")
    input()
    x1, y1 = get_cursor_pos()
    print(f"  → Ecke 1: ({x1}, {y1})")

    print("  Maus auf UNTEN-RECHTS bewegen, ENTER drücken...")
    input()
    x2, y2 = get_cursor_pos()
    print(f"  → Ecke 2: ({x2}, {y2})")

    # Sicherstellen dass x1 < x2 und y1 < y2
    if x1 > x2:
        x1, x2 = x2, x1
    if y1 > y2:
        y1, y2 = y2, y1

    return (x1, y1, x2, y2)

def take_screenshot(region=None):
    """Macht einen Screenshot (optional nur von einem Bereich)."""
    img = ImageGrab.grab(bbox=region)
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def find_slots(image, color_lower, color_upper, min_width=40, min_height=40, debug=False):
    """
    Findet Slots basierend auf Hintergrundfarbe.
    Returns: Liste von (x, y, w, h) Rechtecken
    """
    # In HSV konvertieren für bessere Farberkennung
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Maske für die Slot-Farbe erstellen
    mask = cv2.inRange(hsv, color_lower, color_upper)

    # Debug: Originale Maske speichern
    if debug:
        cv2.imwrite("debug_mask_original.png", mask)
        pixel_count = np.count_nonzero(mask)
        print(f"  [DEBUG] Originale Maske: {pixel_count} weiße Pixel")
        if pixel_count == 0:
            print("  [DEBUG] KEINE Pixel gefunden! Farbe stimmt nicht.")

    # Nur kleine Löcher füllen (nicht die ganze Fläche!)
    kernel_close = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)

    # Kleine Störungen/Rauschen entfernen
    kernel_open = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)

    # Debug: Nach Verarbeitung
    if debug:
        cv2.imwrite("debug_mask_processed.png", mask)
        print(f"  [DEBUG] Nach Verarbeitung: {np.count_nonzero(mask)} weiße Pixel")

    # Konturen finden
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if debug:
        print(f"  [DEBUG] {len(contours)} Konturen gefunden")

    slots = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)

        if debug and w > 20 and h > 20:
            print(f"  [DEBUG] Kontur: ({x},{y}) {w}x{h}")

        # Nur Rechtecke mit Mindestgröße
        if w >= min_width and h >= min_height:
            # Prüfe ob es annähernd quadratisch/rechteckig ist
            aspect_ratio = w / h
            if 0.5 < aspect_ratio < 2.0:  # Slots sind meist quadratisch
                slots.append((x, y, w, h))

    # Nach X-Position sortieren (links nach rechts)
    slots.sort(key=lambda s: s[0])

    # Größen normalisieren: Alle Slots sollten gleich groß sein
    if len(slots) >= 2:
        # Median-Größe berechnen
        widths = [s[2] for s in slots]
        heights = [s[3] for s in slots]
        median_w = sorted(widths)[len(widths) // 2]
        median_h = sorted(heights)[len(heights) // 2]

        if debug:
            print(f"  [DEBUG] Median-Größe: {median_w}x{median_h}")

        # Alle Slots auf Median-Größe anpassen (Position bleibt, Größe wird vereinheitlicht)
        normalized = []
        for x, y, w, h in slots:
            # Nur Slots behalten die ähnlich groß sind (±30%)
            if 0.7 * median_w <= w <= 1.3 * median_w and 0.7 * median_h <= h <= 1.3 * median_h:
                # Zentrieren: Position anpassen wenn Größe geändert wird
                new_x = x + (w - median_w) // 2
                new_y = y + (h - median_h) // 2
                normalized.append((new_x, new_y, median_w, median_h))
            elif debug:
                print(f"  [DEBUG] Slot ({x},{y}) {w}x{h} entfernt (falsche Größe)")

        slots = normalized

    return slots

def main():
    print("=" * 60)
    print("  AUTOMATISCHE SLOT-ERKENNUNG")
    print("=" * 60)

    print("\nOptionen:")
    print("  [1] Screenshot aus Zwischenablage (Win+Shift+S) - EMPFOHLEN")
    print("  [2] Automatischer Screenshot (funktioniert nicht bei allen Spielen)")
    print("  [3] Bild-Datei laden")

    choice = input("\n> ").strip()

    # Offset für absolute Koordinaten
    offset_x, offset_y = 0, 0
    region = None

    if choice == "1":
        # Clipboard - einfachste Methode
        print("\n" + "=" * 50)
        print("ANLEITUNG:")
        print("  1. Drücke Win+Shift+S")
        print("  2. Ziehe einen Rahmen um die Slots")
        print("  3. Drücke hier ENTER")
        print("=" * 50)
        input("\nENTER wenn Screenshot in Zwischenablage...")

        clipboard_img = ImageGrab.grabclipboard()
        if clipboard_img is None:
            print("[FEHLER] Kein Bild in der Zwischenablage!")
            return

        image = cv2.cvtColor(np.array(clipboard_img), cv2.COLOR_RGB2BGR)
        print(f"[OK] Bild geladen: {image.shape[1]}x{image.shape[0]}")

        # Offset wird SPÄTER berechnet (User klickt auf Slot 1)
        offset_x, offset_y = None, None

    elif choice == "2":
        # Automatischer Screenshot
        print("\nMache Screenshot in 3 Sekunden...")
        print("Stelle sicher, dass das Spiel sichtbar ist!")
        import time
        for i in range(3, 0, -1):
            print(f"  {i}...")
            time.sleep(1)
        image = take_screenshot()
        print(f"[OK] Screenshot: {image.shape[1]}x{image.shape[0]}")
        # offset bleibt 0,0 da ganzer Bildschirm

    elif choice == "3":
        filepath = input("Pfad zur Bild-Datei: ").strip().strip('"')
        image = cv2.imread(filepath)
        if image is None:
            print(f"[FEHLER] Konnte '{filepath}' nicht laden!")
            return
        print(f"[OK] Bild geladen: {image.shape[1]}x{image.shape[0]}")

        # Offset wird SPÄTER berechnet (User klickt auf Slot 1)
        offset_x, offset_y = None, None

    else:
        print("[FEHLER] Ungültige Option!")
        return

    # Screenshot speichern für Debugging
    cv2.imwrite("screenshot_debug.png", image)
    print("     (Gespeichert als 'screenshot_debug.png')")

    # Türkis/Teal Farbe der Slot-Hintergründe (HSV)
    print("\nSuche nach türkisen Slot-Hintergründen...")

    # Verschiedene Türkis-Töne probieren (angepasst für Idle Clans)
    color_presets = {
        "idle-clans-teal": (np.array([75, 80, 100]), np.array([95, 200, 180])),
        "türkis (breit)": (np.array([70, 60, 80]), np.array([100, 220, 200])),
        "türkis (hell)": (np.array([75, 100, 120]), np.array([90, 200, 180])),
        "türkis (dunkel)": (np.array([75, 80, 80]), np.array([95, 200, 150])),
    }

    best_slots = []
    best_preset = None

    for name, (lower, upper) in color_presets.items():
        slots = find_slots(image, lower, upper)
        if len(slots) > len(best_slots):
            best_slots = slots
            best_preset = name

    if not best_slots:
        print("\n[WARNUNG] Keine Slots automatisch erkannt!")
        print("\nOptionen:")
        print("  [1] Farbe aus BILD samplen (Pixel-Position eingeben)")
        print("  [2] Top-Farben im Bild analysieren")
        print("  [3] HSV-Werte manuell eingeben")
        print("  [0] Abbrechen")

        sub_choice = input("\n> ").strip()

        if sub_choice == "1":
            # Farbe aus dem geladenen Bild samplen
            print("\nÖffne 'screenshot_debug.png' in einem Bildbetrachter.")
            print("Finde die Pixel-Position des TÜRKISEN HINTERGRUNDS eines Slots.")
            print("(In Paint: Maus auf Türkis bewegen, Position unten ablesen)")
            print(f"\nBild-Größe: {image.shape[1]} x {image.shape[0]}")

            try:
                px = int(input("\n  X-Position im Bild: ").strip())
                py = int(input("  Y-Position im Bild: ").strip())

                if 0 <= px < image.shape[1] and 0 <= py < image.shape[0]:
                    # BGR aus Bild lesen
                    b, g, r = image[py, px]
                    pixel_bgr = np.array([[[b, g, r]]], dtype=np.uint8)
                    pixel_hsv = cv2.cvtColor(pixel_bgr, cv2.COLOR_BGR2HSV)[0][0]

                    print(f"\n  Farbe bei ({px}, {py}):")
                    print(f"    RGB: ({r}, {g}, {b})")
                    print(f"    HSV: ({pixel_hsv[0]}, {pixel_hsv[1]}, {pixel_hsv[2]})")

                    tol = int(input("\n  Toleranz (Standard: 30): ").strip() or "30")

                    h, s, v = pixel_hsv
                    lower = np.array([max(0, h - tol), max(0, s - 50), max(0, v - 50)])
                    upper = np.array([min(180, h + tol), min(255, s + 50), min(255, v + 50)])

                    print(f"\n  Suche mit HSV-Bereich: {list(lower)} - {list(upper)}")
                    best_slots = find_slots(image, lower, upper, debug=True)
                    best_preset = "aus Bild gesampelt"
                else:
                    print("  [FEHLER] Position außerhalb des Bildes!")
            except ValueError:
                print("  [FEHLER] Ungültige Eingabe!")

        elif sub_choice == "2":
            # Top-Farben analysieren
            print("\nAnalysiere häufigste Farben im Bild...")
            hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

            # Farben zählen (gruppiert)
            color_counts = {}
            for y in range(0, hsv_image.shape[0], 2):
                for x in range(0, hsv_image.shape[1], 2):
                    h, s, v = hsv_image[y, x]
                    if s > 50 and v > 50:  # Nur gesättigte Farben
                        key = (h // 5 * 5, s // 20 * 20, v // 20 * 20)
                        color_counts[key] = color_counts.get(key, 0) + 1

            # Top 10 anzeigen
            sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            print("\nTop 10 Farben (HSV):")
            for i, ((h, s, v), count) in enumerate(sorted_colors):
                print(f"  {i+1}. HSV({h}, {s}, {v}) - {count} Pixel")

            try:
                choice_num = int(input("\nWelche Farbe verwenden? (1-10): ").strip())
                if 1 <= choice_num <= len(sorted_colors):
                    h, s, v = sorted_colors[choice_num - 1][0]
                    tol = int(input("Toleranz (Standard: 15): ").strip() or "15")

                    lower = np.array([max(0, h - tol), max(0, s - 40), max(0, v - 40)])
                    upper = np.array([min(180, h + tol), min(255, s + 40), min(255, v + 40)])

                    best_slots = find_slots(image, lower, upper)
                    best_preset = f"Farbe #{choice_num}"
            except ValueError:
                print("  Ungültige Eingabe!")

        elif sub_choice == "3":
            # HSV manuell eingeben
            try:
                print("\nHSV-Werte eingeben:")
                h = int(input("  Hue (0-180): ").strip())
                s = int(input("  Saturation (0-255): ").strip())
                v = int(input("  Value (0-255): ").strip())
                tolerance = int(input("  Toleranz (Standard: 15): ").strip() or "15")

                lower = np.array([max(0, h - tolerance), max(0, s - 50), max(0, v - 50)])
                upper = np.array([min(180, h + tolerance), min(255, s + 50), min(255, v + 50)])

                best_slots = find_slots(image, lower, upper, debug=True)
                best_preset = "manuell HSV"
            except ValueError:
                print("  Ungültige Eingabe!")

    if not best_slots:
        print("\n[FEHLER] Keine Slots gefunden!")
        print("         Versuche das manuelle Skript: python create_slots.py")
        return

    print(f"\n[OK] {len(best_slots)} Slots erkannt! (Preset: {best_preset})")

    # Slots anzeigen
    print("\nErkannte Slots:")
    for i, (x, y, w, h) in enumerate(best_slots):
        print(f"  {i+1}. Position: ({x}, {y}), Größe: {w}x{h}")

    # Vorschau erstellen
    preview = image.copy()
    for i, (x, y, w, h) in enumerate(best_slots):
        cv2.rectangle(preview, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(preview, str(i + 1), (x + 5, y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.imwrite("slots_preview.png", preview)
    print("\n[OK] Vorschau gespeichert: 'slots_preview.png'")

    # Bestätigung
    print("\nSlots übernehmen? (j/n)")
    if input("> ").strip().lower() != "j":
        print("[ABBRUCH]")
        return

    # Offset berechnen falls noch nicht gesetzt (bei Clipboard-Screenshot)
    if offset_x is None:
        print("\n" + "=" * 50)
        print("POSITION KALIBRIEREN:")
        print("  Klicke auf die MITTE von SLOT 1 auf dem Bildschirm")
        print("  (Der erste erkannte Slot, oben links)")
        print("=" * 50)
        input("ENTER wenn Maus auf Slot 1 ist...")

        screen_x, screen_y = get_cursor_pos()

        # Slot 1 im Bild
        slot1_x, slot1_y, slot1_w, slot1_h = best_slots[0]
        slot1_center_x = slot1_x + slot1_w // 2
        slot1_center_y = slot1_y + slot1_h // 2

        # Offset = Bildschirmposition - Position im Bild
        offset_x = screen_x - slot1_center_x
        offset_y = screen_y - slot1_center_y

        print(f"  → Offset berechnet: ({offset_x}, {offset_y})")

    # Hintergrundfarbe
    bg_color = None
    print("\nHintergrundfarbe aus erstem Slot extrahieren? (j/n)")
    if input("> ").strip().lower() == "j":
        x, y, w, h = best_slots[0]
        # Mitte des Slots
        center_x, center_y = x + w // 2, y + h // 2
        pixel = image[center_y, center_x]
        bg_color = [int(pixel[2]) // 5 * 5, int(pixel[1]) // 5 * 5, int(pixel[0]) // 5 * 5]
        print(f"  → Hintergrund: RGB{tuple(bg_color)}")

    # JSON erstellen (mit Offset für absolute Bildschirm-Koordinaten)
    slots_json = {}
    print(f"\nBerechne absolute Koordinaten (Offset: +{offset_x}, +{offset_y})...")

    for i, (x, y, w, h) in enumerate(best_slots):
        name = f"Slot {i + 1}"

        # Absolute Koordinaten = relative + offset
        abs_x = x + offset_x
        abs_y = y + offset_y

        slots_json[name] = {
            "name": name,
            "scan_region": [abs_x, abs_y, abs_x + w, abs_y + h],
            "click_pos": [abs_x + w // 2, abs_y + h // 2],  # Mitte
            "slot_color": bg_color
        }

        print(f"  {name}: Bildschirm-Position ({abs_x}, {abs_y})")

    # Speichern
    with open("slots.json", "w", encoding="utf-8") as f:
        json.dump(slots_json, f, indent=2, ensure_ascii=False)

    print(f"\n[ERFOLG] {len(best_slots)} Slots in 'slots.json' gespeichert!")

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
