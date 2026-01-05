"""
Ziffern-Editor für den Autoclicker.
Ermöglicht das Lernen von Ziffern für die Zahlenerkennung.
"""

from pathlib import Path
from typing import Optional

from ..models import AutoClickerState
from ..utils import safe_input
from ..winapi import get_cursor_pos
from ..imaging import (
    PILLOW_AVAILABLE, OPENCV_AVAILABLE, take_screenshot, get_pixel_color,
    select_region, get_color_name
)
from ..number_recognition import (
    DIGIT_CHARS, SEPARATOR_CHARS, SUFFIX_CHARS, ALL_LEARNABLE_CHARS,
    get_learned_digits, save_digit_template, delete_digit_template,
    load_digit_template, load_digit_config, save_digit_config,
    recognize_number, ensure_digits_dir
)


def run_digit_editor(state: AutoClickerState) -> None:
    """Interaktiver Editor zum Lernen von Ziffern für die Zahlenerkennung."""
    print("\n" + "=" * 60)
    print("  ZIFFERN-EDITOR (Zahlenerkennung)")
    print("=" * 60)

    if not PILLOW_AVAILABLE:
        print("\n[FEHLER] Pillow nicht installiert!")
        print("         Installieren mit: pip install pillow")
        return

    if not OPENCV_AVAILABLE:
        print("\n[FEHLER] OpenCV nicht installiert!")
        print("         Installieren mit: pip install opencv-python")
        return

    # Aktuelle Konfiguration laden
    config = load_digit_config()

    # Status anzeigen
    learned = get_learned_digits()
    print(f"\nGelernte Zeichen ({len(learned)}/{len(ALL_LEARNABLE_CHARS)}):")

    # Ziffern
    digit_status = ""
    for d in DIGIT_CHARS:
        digit_status += f"[{d}]" if d in learned else f" {d} "
    print(f"  Ziffern:    {digit_status}")

    # Trennzeichen
    sep_status = ""
    for s in SEPARATOR_CHARS:
        sep_status += f"[{s}]" if s in learned else f" {s} "
    print(f"  Trennzeichen: {sep_status}")

    # Suffixe
    suffix_status = ""
    for s in SUFFIX_CHARS.keys():
        suffix_status += f"[{s}]" if s in learned else f" {s} "
    print(f"  Suffixe:    {suffix_status}")

    # Textfarbe anzeigen
    if config.get("text_color"):
        color = tuple(config["text_color"])
        color_name = get_color_name(color)
        print(f"\n  Textfarbe: RGB{color} ({color_name})")
    else:
        print("\n  Textfarbe: (nicht gesetzt)")

    print(f"  Konfidenz: {config.get('min_confidence', 0.8):.0%}")
    print(f"  Farbtoleranz: {config.get('color_tolerance', 50)}")

    print("\n" + "-" * 60)
    print("Befehle:")
    print("  learn          - Einzelne Ziffer/Zeichen lernen")
    print("  learn all      - Alle Ziffern 0-9 nacheinander lernen")
    print("  show <Z>       - Template für Zeichen anzeigen (z.B. 'show 5')")
    print("  del <Z>        - Zeichen löschen (z.B. 'del 5')")
    print("  del all        - ALLE Zeichen löschen")
    print("  color          - Textfarbe setzen")
    print("  color clear    - Textfarbe entfernen")
    print("  conf <0-100>   - Mindest-Konfidenz setzen (z.B. 'conf 80')")
    print("  test           - Zahlenerkennung testen")
    print("  done | cancel")
    print("-" * 60)

    while True:
        try:
            learned = get_learned_digits()
            prompt = f"[{len(learned)} Zeichen]"
            user_input = safe_input(f"{prompt} > ").strip()
            cmd = user_input.lower()

            if cmd in ("done", "cancel", ""):
                if cmd == "done":
                    print("[OK] Ziffern-Editor beendet.")
                return

            elif cmd == "learn":
                learn_single_digit()

            elif cmd == "learn all":
                learn_all_digits()

            elif cmd.startswith("show "):
                char = user_input[5:].strip()
                if char:
                    show_digit_template(char)
                else:
                    print("  -> Format: show <Zeichen>")

            elif cmd.startswith("del "):
                arg = user_input[4:].strip()
                if arg.lower() == "all":
                    delete_all_digits()
                elif arg:
                    delete_single_digit(arg)
                else:
                    print("  -> Format: del <Zeichen> oder del all")

            elif cmd == "color":
                set_text_color()

            elif cmd == "color clear":
                config = load_digit_config()
                config["text_color"] = None
                save_digit_config(config)
                print("  + Textfarbe entfernt")

            elif cmd.startswith("conf "):
                try:
                    conf_val = int(cmd[5:])
                    if 1 <= conf_val <= 100:
                        config = load_digit_config()
                        config["min_confidence"] = conf_val / 100
                        save_digit_config(config)
                        print(f"  + Konfidenz auf {conf_val}% gesetzt")
                    else:
                        print("  -> Wert muss zwischen 1 und 100 liegen!")
                except ValueError:
                    print("  -> Format: conf <0-100>")

            elif cmd == "test":
                test_number_recognition()

            else:
                print("  -> Unbekannter Befehl")

        except (KeyboardInterrupt, EOFError):
            print("\n[ABBRUCH] Ziffern-Editor beendet.")
            return


def learn_single_digit() -> None:
    """Lernt eine einzelne Ziffer/Zeichen."""
    print("\n  Welches Zeichen lernen?")
    print(f"  Möglich: {ALL_LEARNABLE_CHARS}")

    char = safe_input("  Zeichen: ").strip()

    if not char:
        print("  -> Abgebrochen")
        return

    # Nur das erste Zeichen nehmen
    char = char[0]

    if char not in ALL_LEARNABLE_CHARS:
        print(f"  -> '{char}' ist kein gültiges Zeichen!")
        print(f"  -> Erlaubt: {ALL_LEARNABLE_CHARS}")
        return

    # Region auswählen wo die Ziffer steht
    print(f"\n  Wähle den Bereich wo '{char}' zu sehen ist:")
    print("  (Markiere NUR die einzelne Ziffer, nicht die ganze Zahl!)")

    region = select_region()
    if not region:
        print("  -> Abgebrochen")
        return

    # Screenshot machen
    img = take_screenshot(region)
    if not img:
        print("  -> Screenshot fehlgeschlagen!")
        return

    # Speichern
    if save_digit_template(char, img):
        width, height = img.size
        print(f"  + Zeichen '{char}' gelernt! ({width}x{height} Pixel)")
    else:
        print("  -> Speichern fehlgeschlagen!")


def learn_all_digits() -> None:
    """Lernt alle Ziffern 0-9 nacheinander."""
    print("\n  === ALLE ZIFFERN LERNEN ===")
    print("  Du wirst nacheinander für jede Ziffer 0-9 einen Bereich markieren.")
    print("  Tipp: Stelle sicher, dass alle Ziffern sichtbar sind!")
    print("\n  Fortfahren? (Enter = Ja, 'cancel' = Abbrechen)")

    if safe_input("  > ").strip().lower() == "cancel":
        print("  -> Abgebrochen")
        return

    for digit in DIGIT_CHARS:
        print(f"\n  --- Ziffer '{digit}' ---")
        print(f"  Markiere den Bereich wo '{digit}' zu sehen ist:")

        region = select_region()
        if not region:
            print(f"  -> '{digit}' übersprungen")
            continue

        img = take_screenshot(region)
        if not img:
            print(f"  -> Screenshot für '{digit}' fehlgeschlagen!")
            continue

        if save_digit_template(digit, img):
            width, height = img.size
            print(f"  + Ziffer '{digit}' gelernt! ({width}x{height} Pixel)")
        else:
            print(f"  -> Speichern von '{digit}' fehlgeschlagen!")

    learned = get_learned_digits()
    digits_learned = [d for d in DIGIT_CHARS if d in learned]
    print(f"\n  === FERTIG: {len(digits_learned)}/10 Ziffern gelernt ===")


def show_digit_template(char: str) -> None:
    """Zeigt Informationen über ein Template."""
    if char not in ALL_LEARNABLE_CHARS:
        print(f"  -> '{char}' ist kein gültiges Zeichen!")
        return

    img = load_digit_template(char)
    if img is None:
        print(f"  -> Zeichen '{char}' nicht gelernt!")
        return

    width, height = img.size
    print(f"\n  Zeichen '{char}':")
    print(f"    Größe: {width}x{height} Pixel")

    # Durchschnittsfarbe berechnen
    try:
        import numpy as np
        img_array = np.array(img)
        if len(img_array.shape) >= 3:
            avg_color = tuple(img_array[:, :, :3].mean(axis=(0, 1)).astype(int))
            color_name = get_color_name(avg_color)
            print(f"    Durchschnittsfarbe: RGB{avg_color} ({color_name})")
    except ImportError:
        pass

    from ..number_recognition import get_digit_template_path
    print(f"    Pfad: {get_digit_template_path(char)}")


def delete_single_digit(char: str) -> None:
    """Löscht ein einzelnes Zeichen-Template."""
    if char not in ALL_LEARNABLE_CHARS:
        print(f"  -> '{char}' ist kein gültiges Zeichen!")
        return

    if delete_digit_template(char):
        print(f"  + Zeichen '{char}' gelöscht!")
    else:
        print(f"  -> Zeichen '{char}' nicht vorhanden!")


def delete_all_digits() -> None:
    """Löscht alle Zeichen-Templates."""
    learned = get_learned_digits()
    if not learned:
        print("  -> Keine Zeichen vorhanden!")
        return

    confirm = safe_input(f"  {len(learned)} Zeichen wirklich löschen? (j/n): ").strip().lower()
    if confirm != "j":
        print("  -> Abgebrochen")
        return

    count = 0
    for char in learned:
        if delete_digit_template(char):
            count += 1

    print(f"  + {count} Zeichen gelöscht!")


def set_text_color() -> None:
    """Setzt die Textfarbe für bessere Erkennung."""
    print("\n  Textfarbe setzen:")
    print("  Bewege die Maus auf eine Ziffer und drücke Enter.")
    print("  (Die Farbe der Ziffer wird verwendet)")

    safe_input("  Bereit? Enter drücken...")

    x, y = get_cursor_pos()
    color = get_pixel_color(x, y)

    if not color:
        print("  -> Farbe konnte nicht gelesen werden!")
        return

    color_name = get_color_name(color)
    print(f"  -> Farbe erkannt: RGB{color} ({color_name})")

    confirm = safe_input("  Diese Farbe verwenden? (j/n): ").strip().lower()
    if confirm != "j":
        print("  -> Abgebrochen")
        return

    # Toleranz abfragen
    config = load_digit_config()
    print(f"\n  Farbtoleranz (aktuell: {config.get('color_tolerance', 50)}):")
    print("  (Höher = mehr ähnliche Farben werden als Text erkannt)")

    try:
        tol_input = safe_input("  Toleranz (Enter = beibehalten): ").strip()
        if tol_input:
            tolerance = max(1, min(200, int(tol_input)))
            config["color_tolerance"] = tolerance
    except ValueError:
        pass

    config["text_color"] = list(color)
    save_digit_config(config)

    print(f"  + Textfarbe auf RGB{color} gesetzt!")


def test_number_recognition() -> None:
    """Testet die Zahlenerkennung an einem Bereich."""
    learned = get_learned_digits()
    digits_learned = [d for d in DIGIT_CHARS if d in learned]

    if len(digits_learned) < 5:
        print(f"\n  [WARNUNG] Nur {len(digits_learned)}/10 Ziffern gelernt!")
        print("  Lerne mehr Ziffern für bessere Erkennung.")

    print("\n  === ZAHLENERKENNUNG TESTEN ===")
    print("  Wähle den Bereich wo eine Zahl zu sehen ist:")
    print("  (Der Bereich kann größer sein als die Zahl)")

    region = select_region()
    if not region:
        print("  -> Abgebrochen")
        return

    # Screenshot machen
    img = take_screenshot(region)
    if not img:
        print("  -> Screenshot fehlgeschlagen!")
        return

    # Erkennung durchführen
    print("\n  Analysiere...")
    number, char_string, details = recognize_number(img)

    print("\n  === ERGEBNIS ===")
    if number is not None:
        print(f"  Erkannte Zeichen: '{char_string}'")
        print(f"  Erkannte Zahl:    {number:,.2f}")

        if details:
            print("\n  Details:")
            for char, x_pos, conf in details:
                print(f"    '{char}' bei x={x_pos} ({conf:.0%} Konfidenz)")
    else:
        if char_string:
            print(f"  Erkannte Zeichen: '{char_string}' (keine gültige Zahl)")
        else:
            print("  Keine Zeichen erkannt!")
            print("\n  Mögliche Gründe:")
            print("  - Ziffern nicht gelernt")
            print("  - Textfarbe nicht gesetzt oder falsch")
            print("  - Konfidenz zu hoch eingestellt")
            print("  - Bereich zu klein/groß")

    # Screenshot speichern für Debug
    try:
        debug_path = ensure_digits_dir() / "last_test.png"
        img.save(debug_path)
        print(f"\n  Screenshot gespeichert: {debug_path}")
    except (IOError, OSError):
        pass
