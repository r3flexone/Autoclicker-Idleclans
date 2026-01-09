"""
Tests für Parsing-Logik.

Testet die Parsing-Funktionen für Sequenz-Befehle.
Diese Tests sind unabhängig von der GUI.
"""

import re


# ==============================================================================
# Extrahierte Parsing-Funktionen (aus sequence_editor.py)
# ==============================================================================

def parse_delay_range(text: str) -> tuple[float, float] | None:
    """
    Parst Zeit-Bereich wie '5-10' oder einzelne Zahl.

    Returns:
        (min, max) oder None bei Fehler
    """
    text = text.strip()

    # Bereich: 5-10
    if "-" in text:
        parts = text.split("-")
        if len(parts) == 2:
            try:
                min_val = float(parts[0])
                max_val = float(parts[1])
                if min_val <= max_val:
                    return (min_val, max_val)
            except ValueError:
                pass
        return None

    # Einzelne Zahl
    try:
        val = float(text)
        return (val, val)
    except ValueError:
        return None


def parse_number_condition(text: str) -> dict | None:
    """
    Parst Zahlen-Bedingung wie '> 100', '< 50', '= 1000'.

    Returns:
        {"operator": str, "target": float} oder None bei Fehler
    """
    text = text.strip()

    # Pattern: operator + optional space + number
    match = re.match(r'^([><=])\s*(\d+(?:\.\d+)?(?:[kKmM])?)$', text)
    if not match:
        return None

    operator = match.group(1)
    value_str = match.group(2).lower()

    # Multiplier für k/m
    multiplier = 1
    if value_str.endswith('k'):
        multiplier = 1000
        value_str = value_str[:-1]
    elif value_str.endswith('m'):
        multiplier = 1000000
        value_str = value_str[:-1]

    try:
        value = float(value_str) * multiplier
        return {"operator": operator, "target": value}
    except ValueError:
        return None


def validate_scan_name(name: str) -> bool:
    """
    Prüft ob ein Scan-Name gültig ist (keine Leerzeichen).

    Returns:
        True wenn gültig, False sonst
    """
    return " " not in name and len(name) > 0


def parse_else_action(text: str) -> dict | None:
    """
    Parst else-Aktion wie 'skip', 'restart', '2', '2 5', 'key enter'.

    Returns:
        {"type": str, ...} oder None bei Fehler
    """
    text = text.strip().lower()

    if text == "skip":
        return {"type": "skip"}

    if text == "restart":
        return {"type": "restart"}

    if text.startswith("key "):
        key = text[4:].strip()
        if key:
            return {"type": "key", "key": key}
        return None

    # Punkt-Referenz: "2" oder "2 5" (Punkt + optionale Wartezeit)
    parts = text.split()
    if parts:
        try:
            point_num = int(parts[0])
            delay = float(parts[1]) if len(parts) > 1 else 0
            return {"type": "point", "point": point_num, "delay": delay}
        except ValueError:
            pass

    return None


# ==============================================================================
# Tests für parse_delay_range
# ==============================================================================

class TestParseDelayRange:
    """Tests für parse_delay_range()"""

    def test_single_number(self):
        assert parse_delay_range("5") == (5.0, 5.0)

    def test_single_float(self):
        assert parse_delay_range("5.5") == (5.5, 5.5)

    def test_range(self):
        assert parse_delay_range("5-10") == (5.0, 10.0)

    def test_float_range(self):
        assert parse_delay_range("2.5-7.5") == (2.5, 7.5)

    def test_same_values(self):
        assert parse_delay_range("5-5") == (5.0, 5.0)

    def test_invalid_range_reversed(self):
        """Max kleiner als min ist ungültig."""
        assert parse_delay_range("10-5") is None

    def test_invalid_not_a_number(self):
        assert parse_delay_range("abc") is None

    def test_invalid_partial_range(self):
        assert parse_delay_range("5-") is None
        assert parse_delay_range("-10") is None

    def test_whitespace_trimmed(self):
        assert parse_delay_range("  5  ") == (5.0, 5.0)


# ==============================================================================
# Tests für parse_number_condition
# ==============================================================================

class TestParseNumberCondition:
    """Tests für parse_number_condition()"""

    def test_greater_than(self):
        result = parse_number_condition("> 100")
        assert result == {"operator": ">", "target": 100.0}

    def test_less_than(self):
        result = parse_number_condition("< 50")
        assert result == {"operator": "<", "target": 50.0}

    def test_equals(self):
        result = parse_number_condition("= 1000")
        assert result == {"operator": "=", "target": 1000.0}

    def test_no_space(self):
        result = parse_number_condition(">100")
        assert result == {"operator": ">", "target": 100.0}

    def test_float_value(self):
        result = parse_number_condition("> 99.5")
        assert result == {"operator": ">", "target": 99.5}

    def test_k_multiplier(self):
        result = parse_number_condition("> 10k")
        assert result == {"operator": ">", "target": 10000.0}

    def test_m_multiplier(self):
        result = parse_number_condition("> 1m")
        assert result == {"operator": ">", "target": 1000000.0}

    def test_K_uppercase(self):
        result = parse_number_condition("> 5K")
        assert result == {"operator": ">", "target": 5000.0}

    def test_invalid_no_operator(self):
        assert parse_number_condition("100") is None

    def test_invalid_wrong_operator(self):
        assert parse_number_condition("!= 100") is None

    def test_invalid_no_number(self):
        assert parse_number_condition("> abc") is None


# ==============================================================================
# Tests für validate_scan_name
# ==============================================================================

class TestValidateScanName:
    """Tests für validate_scan_name()"""

    def test_valid_name(self):
        assert validate_scan_name("inventar") is True

    def test_valid_with_underscore(self):
        assert validate_scan_name("my_scan") is True

    def test_valid_with_hyphen(self):
        assert validate_scan_name("my-scan") is True

    def test_valid_with_numbers(self):
        assert validate_scan_name("scan123") is True

    def test_invalid_with_space(self):
        assert validate_scan_name("my scan") is False

    def test_invalid_empty(self):
        assert validate_scan_name("") is False

    def test_invalid_only_spaces(self):
        assert validate_scan_name("   ") is False


# ==============================================================================
# Tests für parse_else_action
# ==============================================================================

class TestParseElseAction:
    """Tests für parse_else_action()"""

    def test_skip(self):
        assert parse_else_action("skip") == {"type": "skip"}

    def test_restart(self):
        assert parse_else_action("restart") == {"type": "restart"}

    def test_key_enter(self):
        assert parse_else_action("key enter") == {"type": "key", "key": "enter"}

    def test_key_space(self):
        assert parse_else_action("key space") == {"type": "key", "key": "space"}

    def test_point_number(self):
        assert parse_else_action("2") == {"type": "point", "point": 2, "delay": 0}

    def test_point_with_delay(self):
        assert parse_else_action("2 5") == {"type": "point", "point": 2, "delay": 5.0}

    def test_uppercase_converted(self):
        assert parse_else_action("SKIP") == {"type": "skip"}
        assert parse_else_action("RESTART") == {"type": "restart"}

    def test_invalid_key_without_name(self):
        assert parse_else_action("key") is None
        assert parse_else_action("key ") is None

    def test_invalid_unknown(self):
        assert parse_else_action("unknown") is None
