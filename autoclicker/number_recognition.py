"""
Zahlenerkennung für den Autoclicker.
Erkennt Zahlen in Screenshots per Template-Matching der gelernten Ziffern.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .config import CONFIG

if TYPE_CHECKING:
    from PIL import Image

# Logger
logger = logging.getLogger("autoclicker")

# Verzeichnis für Ziffern-Templates
DIGITS_DIR: str = os.path.join("items", "digits")

# Optionale Imports
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False


# Lernbare Zeichen und ihre Multiplikatoren
DIGIT_CHARS = "0123456789"
SEPARATOR_CHARS = ".,"
SUFFIX_CHARS = {
    "K": 1_000,
    "k": 1_000,
    "M": 1_000_000,
    "m": 1_000_000,
    "B": 1_000_000_000,
    "b": 1_000_000_000,
}

ALL_LEARNABLE_CHARS = DIGIT_CHARS + SEPARATOR_CHARS + "".join(SUFFIX_CHARS.keys())


def ensure_digits_dir() -> Path:
    """Stellt sicher dass das Ziffern-Verzeichnis existiert."""
    digits_path = Path(DIGITS_DIR)
    digits_path.mkdir(parents=True, exist_ok=True)
    return digits_path


def get_digit_template_path(char: str) -> Path:
    """Gibt den Pfad zum Template einer Ziffer/Zeichen zurück."""
    # Sonderzeichen umbenennen für Dateisystem
    if char == ".":
        filename = "dot.png"
    elif char == ",":
        filename = "comma.png"
    else:
        filename = f"{char}.png"
    return ensure_digits_dir() / filename


def get_digit_config_path() -> Path:
    """Gibt den Pfad zur Ziffern-Konfigurationsdatei zurück."""
    return ensure_digits_dir() / "digit_config.json"


def load_digit_config() -> dict:
    """Lädt die Ziffern-Konfiguration (Textfarbe etc.)."""
    config_path = get_digit_config_path()
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "text_color": None,  # (R, G, B) oder None
        "color_tolerance": 50,  # Toleranz für Textfarbe
        "min_confidence": 0.8,  # Mindest-Konfidenz für Match
    }


def save_digit_config(config: dict) -> None:
    """Speichert die Ziffern-Konfiguration."""
    config_path = get_digit_config_path()
    ensure_digits_dir()
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_learned_digits() -> list[str]:
    """Gibt eine Liste aller gelernten Zeichen zurück."""
    learned = []
    for char in ALL_LEARNABLE_CHARS:
        template_path = get_digit_template_path(char)
        if template_path.exists():
            learned.append(char)
    return learned


def save_digit_template(char: str, img: 'Image.Image') -> bool:
    """Speichert ein Ziffern-Template."""
    try:
        template_path = get_digit_template_path(char)
        ensure_digits_dir()
        img.save(template_path)
        logger.info(f"Ziffern-Template gespeichert: {template_path}")
        return True
    except (IOError, OSError) as e:
        logger.error(f"Fehler beim Speichern des Templates: {e}")
        return False


def delete_digit_template(char: str) -> bool:
    """Löscht ein Ziffern-Template."""
    try:
        template_path = get_digit_template_path(char)
        if template_path.exists():
            template_path.unlink()
            return True
        return False
    except (IOError, OSError):
        return False


def load_digit_template(char: str) -> Optional['Image.Image']:
    """Lädt ein Ziffern-Template als PIL Image."""
    if not PILLOW_AVAILABLE:
        return None
    template_path = get_digit_template_path(char)
    if not template_path.exists():
        return None
    try:
        return Image.open(template_path)
    except (IOError, OSError):
        return None


def filter_by_text_color(img: 'Image.Image', text_color: tuple, tolerance: int = 50) -> 'Image.Image':
    """
    Filtert ein Bild nach Textfarbe - macht alles außer der Textfarbe schwarz.
    Dies verbessert die Template-Erkennung erheblich.
    """
    if not NUMPY_AVAILABLE or not PILLOW_AVAILABLE:
        return img

    img_array = np.array(img)
    if len(img_array.shape) < 3:
        return img  # Bereits Graustufen

    # Nur RGB verwenden (ignoriere Alpha falls vorhanden)
    rgb = img_array[:, :, :3].astype(np.float32)
    target = np.array(text_color, dtype=np.float32)

    # Euklidische Distanz für alle Pixel
    distances = np.sqrt(np.sum((rgb - target) ** 2, axis=2))

    # Maske: Pixel innerhalb der Toleranz bleiben weiß, Rest schwarz
    mask = distances <= tolerance

    # Neues Bild erstellen: Textfarbe wird weiß, Rest schwarz
    result = np.zeros_like(img_array[:, :, :3])
    result[mask] = [255, 255, 255]

    return Image.fromarray(result.astype(np.uint8))


def find_digits_in_image(
    img: 'Image.Image',
    text_color: Optional[tuple] = None,
    color_tolerance: int = 50,
    min_confidence: float = 0.8
) -> list[tuple[str, int, float]]:
    """
    Findet alle Ziffern/Zeichen in einem Bild per Template-Matching.

    Args:
        img: PIL Image (der Bereich wo die Zahl steht)
        text_color: Optional (R, G, B) zum Filtern
        color_tolerance: Toleranz für Textfarbe
        min_confidence: Mindest-Konfidenz für Match

    Returns:
        Liste von (zeichen, x_position, konfidenz) sortiert nach x_position
    """
    if not OPENCV_AVAILABLE or not NUMPY_AVAILABLE or not PILLOW_AVAILABLE:
        logger.error("OpenCV, NumPy oder Pillow nicht verfügbar!")
        return []

    # Gelernte Zeichen laden
    learned = get_learned_digits()
    if not learned:
        logger.warning("Keine Ziffern gelernt! Nutze Ctrl+Alt+N → Option 4")
        return []

    # Optional: Nach Textfarbe filtern
    if text_color:
        img = filter_by_text_color(img, text_color, color_tolerance)

    # Bild zu OpenCV-Format konvertieren
    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    img_gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

    found_chars = []

    # Für jedes gelernte Zeichen Template-Matching durchführen
    for char in learned:
        template_img = load_digit_template(char)
        if template_img is None:
            continue

        # Template auch filtern wenn Textfarbe gesetzt
        if text_color:
            template_img = filter_by_text_color(template_img, text_color, color_tolerance)

        # Template zu OpenCV-Format
        template_cv = cv2.cvtColor(np.array(template_img), cv2.COLOR_RGB2BGR)
        template_gray = cv2.cvtColor(template_cv, cv2.COLOR_BGR2GRAY)

        # Prüfe ob Template kleiner als Bild
        if template_gray.shape[0] > img_gray.shape[0] or template_gray.shape[1] > img_gray.shape[1]:
            continue

        # Template Matching
        result = cv2.matchTemplate(img_gray, template_gray, cv2.TM_CCOEFF_NORMED)

        # Alle Matches über der Schwelle finden
        locations = np.where(result >= min_confidence)

        # Non-Maximum Suppression: Nur das beste Match pro Region
        template_width = template_gray.shape[1]

        for y, x in zip(*locations):
            confidence = result[y, x]

            # Prüfe ob es ein besseres Match in der Nähe gibt
            is_best = True
            for existing_char, existing_x, existing_conf in found_chars:
                if abs(existing_x - x) < template_width * 0.5:
                    if existing_conf >= confidence:
                        is_best = False
                        break

            if is_best:
                # Entferne schlechtere Überlappungen
                found_chars = [
                    (c, ex, ec) for c, ex, ec in found_chars
                    if abs(ex - x) >= template_width * 0.5 or ec > confidence
                ]
                found_chars.append((char, int(x), float(confidence)))

    # Nach X-Position sortieren (links nach rechts)
    found_chars.sort(key=lambda x: x[1])

    return found_chars


def chars_to_number(chars: list[tuple[str, int, float]]) -> Optional[float]:
    """
    Konvertiert gefundene Zeichen zu einer Zahl.

    Args:
        chars: Liste von (zeichen, x_position, konfidenz)

    Returns:
        Die erkannte Zahl oder None bei Fehler
    """
    if not chars:
        return None

    # Zeichen zu String zusammenfügen
    char_string = "".join(c[0] for c in chars)

    # Suffix erkennen und entfernen
    multiplier = 1
    for suffix, mult in SUFFIX_CHARS.items():
        if char_string.endswith(suffix):
            char_string = char_string[:-1]
            multiplier = mult
            break

    # Komma durch Punkt ersetzen für float()
    char_string = char_string.replace(",", ".")

    # Mehrere Punkte? Dann ist der erste ein Tausender-Trennzeichen
    if char_string.count(".") > 1:
        # Entferne alle Punkte außer dem letzten
        parts = char_string.split(".")
        char_string = "".join(parts[:-1]) + "." + parts[-1]

    try:
        number = float(char_string) * multiplier
        return number
    except ValueError:
        logger.warning(f"Konnte '{char_string}' nicht in Zahl umwandeln")
        return None


def recognize_number(
    img: 'Image.Image',
    text_color: Optional[tuple] = None,
    color_tolerance: int = 50,
    min_confidence: float = 0.8
) -> tuple[Optional[float], str, list]:
    """
    Hauptfunktion: Erkennt eine Zahl in einem Bild.

    Args:
        img: PIL Image (der Bereich wo die Zahl steht)
        text_color: Optional (R, G, B) zum Filtern
        color_tolerance: Toleranz für Textfarbe
        min_confidence: Mindest-Konfidenz für Match

    Returns:
        (erkannte_zahl, zeichen_string, details_liste)
        - erkannte_zahl: float oder None
        - zeichen_string: Die erkannten Zeichen als String
        - details_liste: Liste mit (zeichen, x_pos, konfidenz)
    """
    # Config laden falls nicht übergeben
    if text_color is None:
        config = load_digit_config()
        text_color = config.get("text_color")
        if text_color:
            text_color = tuple(text_color)
        color_tolerance = config.get("color_tolerance", 50)
        min_confidence = config.get("min_confidence", 0.8)

    # Zeichen finden
    found_chars = find_digits_in_image(img, text_color, color_tolerance, min_confidence)

    if not found_chars:
        return None, "", []

    # Zu Zahl konvertieren
    char_string = "".join(c[0] for c in found_chars)
    number = chars_to_number(found_chars)

    return number, char_string, found_chars


def check_number_condition(
    number: Optional[float],
    operator: str,
    target: float
) -> bool:
    """
    Prüft eine Zahlen-Bedingung.

    Args:
        number: Die erkannte Zahl (oder None)
        operator: Vergleichsoperator (>, <, =, >=, <=, !=)
        target: Der Zielwert

    Returns:
        True wenn Bedingung erfüllt, sonst False
    """
    if number is None:
        return False

    if operator == ">":
        return number > target
    elif operator == "<":
        return number < target
    elif operator == "=" or operator == "==":
        return abs(number - target) < 0.001  # Float-Vergleich
    elif operator == ">=":
        return number >= target
    elif operator == "<=":
        return number <= target
    elif operator == "!=" or operator == "<>":
        return abs(number - target) >= 0.001
    else:
        logger.warning(f"Unbekannter Operator: {operator}")
        return False
