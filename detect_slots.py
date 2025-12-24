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

def find_slots(image, color_lower, color_upper, min_width=40, min_height=40):
    """
    Findet Slots basierend auf Rahmenfarbe.
    Returns: Liste von (x, y, w, h) Rechtecken
    """
    # In HSV konvertieren für bessere Farberkennung
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Maske für die Rahmenfarbe erstellen
    mask = cv2.inRange(hsv, color_lower, color_upper)

    # Rauschen entfernen
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # Konturen finden
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    slots = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)

        # Nur Rechtecke mit Mindestgröße
        if w >= min_width and h >= min_height:
            # Prüfe ob es annähernd quadratisch/rechteckig ist
            aspect_ratio = w / h
            if 0.5 < aspect_ratio < 2.0:
                slots.append((x, y, w, h))

    # Nach X-Position sortieren (links nach rechts)
    slots.sort(key=lambda s: s[0])

    return slots

def main():
    print("=" * 60)
    print("  AUTOMATISCHE SLOT-ERKENNUNG")
    print("=" * 60)

    print("\nOptionen:")
    print("  [1] Bereich auswählen (empfohlen)")
    print("  [2] Ganzer Bildschirm")
    print("  [3] Bild-Datei laden")

    choice = input("\n> ").strip()

    # Offset für absolute Koordinaten
    offset_x, offset_y = 0, 0
    region = None

    if choice == "3":
        filepath = input("Pfad zur Bild-Datei: ").strip().strip('"')
        image = cv2.imread(filepath)
        if image is None:
            print(f"[FEHLER] Konnte '{filepath}' nicht laden!")
            return
        print(f"[OK] Bild geladen: {image.shape[1]}x{image.shape[0]}")

        # Bei Bild-Datei: Nach Offset fragen
        print("\nWo befindet sich dieser Bereich auf dem Bildschirm?")
        print("(Für korrekte Klick-Koordinaten)")
        try:
            offset_x = int(input("  X-Offset (links): ").strip() or "0")
            offset_y = int(input("  Y-Offset (oben): ").strip() or "0")
        except ValueError:
            pass

    elif choice == "1":
        print("\nWähle den Bereich mit den Slots aus:")
        region = select_region()
        offset_x, offset_y = region[0], region[1]

        print(f"\n[OK] Bereich: ({region[0]}, {region[1]}) - ({region[2]}, {region[3]})")
        print(f"     Offset für Koordinaten: +{offset_x}, +{offset_y}")

        print("\nMache Screenshot in 2 Sekunden...")
        import time
        time.sleep(2)
        image = take_screenshot(region)
        print(f"[OK] Screenshot: {image.shape[1]}x{image.shape[0]}")

    else:
        print("\nMache Screenshot in 3 Sekunden...")
        print("Stelle sicher, dass das Spiel sichtbar ist!")
        import time
        for i in range(3, 0, -1):
            print(f"  {i}...")
            time.sleep(1)
        image = take_screenshot()
        print(f"[OK] Screenshot: {image.shape[1]}x{image.shape[0]}")

    # Screenshot speichern für Debugging
    cv2.imwrite("screenshot_debug.png", image)
    print("     (Gespeichert als 'screenshot_debug.png')")

    # Türkis/Cyan Farbe der Slot-Rahmen (HSV)
    # Türkis ist ca. Hue 80-100 in OpenCV (0-180 Skala)
    print("\nSuche nach türkisen Slot-Rahmen...")

    # Verschiedene Türkis-Töne probieren
    color_presets = {
        "türkis (hell)": (np.array([75, 100, 100]), np.array([95, 255, 255])),
        "türkis (dunkel)": (np.array([80, 50, 80]), np.array([100, 255, 200])),
        "cyan": (np.array([85, 100, 100]), np.array([95, 255, 255])),
        "grün-türkis": (np.array([70, 80, 80]), np.array([90, 255, 255])),
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
        print("  [1] Rahmenfarbe manuell scannen (empfohlen)")
        print("  [2] HSV-Werte manuell eingeben")
        print("  [3] Top-Farben im Bild analysieren")
        print("  [0] Abbrechen")

        sub_choice = input("\n> ").strip()

        if sub_choice == "1":
            # Farbe direkt vom Bildschirm scannen
            print("\nBewege die Maus auf den RAHMEN eines Slots...")
            print("(Die türkise/farbige Umrandung)")
            input("ENTER wenn bereit...")

            mx, my = get_cursor_pos()

            # Pixel vom Screenshot holen (relative Koordinate)
            rel_x = mx - offset_x
            rel_y = my - offset_y

            if 0 <= rel_x < image.shape[1] and 0 <= rel_y < image.shape[0]:
                pixel_bgr = image[rel_y, rel_x]
                pixel_hsv = cv2.cvtColor(np.array([[pixel_bgr]], dtype=np.uint8), cv2.COLOR_BGR2HSV)[0][0]

                print(f"\n  Gescannte Farbe:")
                print(f"    RGB: ({pixel_bgr[2]}, {pixel_bgr[1]}, {pixel_bgr[0]})")
                print(f"    HSV: ({pixel_hsv[0]}, {pixel_hsv[1]}, {pixel_hsv[2]})")

                # Toleranz fragen
                try:
                    tol = int(input("\n  Toleranz (Standard: 20): ").strip() or "20")
                except ValueError:
                    tol = 20

                h, s, v = pixel_hsv
                lower = np.array([max(0, h - tol), max(0, s - 60), max(0, v - 60)])
                upper = np.array([min(180, h + tol), min(255, s + 60), min(255, v + 60)])

                print(f"\n  Suche mit HSV-Bereich: {list(lower)} - {list(upper)}")
                best_slots = find_slots(image, lower, upper)
                best_preset = "manuell gescannt"
            else:
                print("  [FEHLER] Mausposition außerhalb des Screenshot-Bereichs!")

        elif sub_choice == "2":
            # HSV manuell eingeben
            try:
                print("\nHSV-Werte eingeben:")
                h = int(input("  Hue (0-180): ").strip())
                s = int(input("  Saturation (0-255): ").strip())
                v = int(input("  Value (0-255): ").strip())
                tolerance = int(input("  Toleranz (Standard: 15): ").strip() or "15")

                lower = np.array([max(0, h - tolerance), max(0, s - 50), max(0, v - 50)])
                upper = np.array([min(180, h + tolerance), min(255, s + 50), min(255, v + 50)])

                best_slots = find_slots(image, lower, upper)
                best_preset = "manuell HSV"
            except ValueError:
                print("  Ungültige Eingabe!")

        elif sub_choice == "3":
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
