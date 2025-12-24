#!/usr/bin/env python3
"""
Automatische Slot-Erkennung per Bilderkennung.
Erkennt die türkisen Slot-Rahmen und erstellt slots.json.

Benötigt: pip install opencv-python pillow
"""

import json
import sys

try:
    import cv2
    import numpy as np
    from PIL import ImageGrab
except ImportError:
    print("[FEHLER] Benötigte Pakete nicht installiert!")
    print("         pip install opencv-python pillow numpy")
    sys.exit(1)

def take_screenshot():
    """Macht einen Screenshot des gesamten Bildschirms."""
    img = ImageGrab.grab()
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
    print("  [1] Screenshot machen (Spiel muss sichtbar sein)")
    print("  [2] Bild-Datei laden")

    choice = input("\n> ").strip()

    if choice == "2":
        filepath = input("Pfad zur Bild-Datei: ").strip().strip('"')
        image = cv2.imread(filepath)
        if image is None:
            print(f"[FEHLER] Konnte '{filepath}' nicht laden!")
            return
        print(f"[OK] Bild geladen: {image.shape[1]}x{image.shape[0]}")
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
        print("          Versuche manuelle Farbanpassung...")

        # Zeige häufigste Farben im Bild
        print("\nMöchtest du eine eigene HSV-Farbe eingeben? (j/n)")
        if input("> ").strip().lower() == "j":
            try:
                print("HSV-Werte eingeben (z.B. für Türkis: 85, 150, 150)")
                h = int(input("  Hue (0-180): ").strip())
                s = int(input("  Saturation (0-255): ").strip())
                v = int(input("  Value (0-255): ").strip())
                tolerance = int(input("  Toleranz (Standard: 15): ").strip() or "15")

                lower = np.array([max(0, h - tolerance), max(0, s - 50), max(0, v - 50)])
                upper = np.array([min(180, h + tolerance), min(255, s + 50), min(255, v + 50)])

                best_slots = find_slots(image, lower, upper)
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

    # JSON erstellen
    slots_json = {}
    for i, (x, y, w, h) in enumerate(best_slots):
        name = f"Slot {i + 1}"
        slots_json[name] = {
            "name": name,
            "scan_region": [x, y, x + w, y + h],
            "click_pos": [x + w // 2, y + h // 2],  # Mitte
            "slot_color": bg_color
        }

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
