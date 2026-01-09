"""
Tests für tools/sync_json.py

Testet die Normalisierungs- und Konvertierungsfunktionen.
"""

import sys
from pathlib import Path

# Füge tools/ zum Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from sync_json import (
    normalize_color,
    normalize_region,
    normalize_pos,
    convert_confirm_point,
    POINTS,
)


# ==============================================================================
# Tests für normalize_color
# ==============================================================================

class TestNormalizeColor:
    """Tests für normalize_color()"""

    def test_none_returns_none(self):
        assert normalize_color(None) is None

    def test_list_with_3_values(self):
        assert normalize_color([255, 128, 0]) == [255, 128, 0]

    def test_tuple_with_3_values(self):
        assert normalize_color((255, 128, 0)) == [255, 128, 0]

    def test_list_with_more_than_3_values_truncates(self):
        assert normalize_color([255, 128, 0, 255]) == [255, 128, 0]

    def test_converts_floats_to_int(self):
        assert normalize_color([255.5, 128.9, 0.1]) == [255, 128, 0]

    def test_list_with_less_than_3_values_returns_none(self):
        assert normalize_color([255, 128]) is None

    def test_empty_list_returns_none(self):
        assert normalize_color([]) is None

    def test_string_returns_none(self):
        assert normalize_color("red") is None

    def test_int_returns_none(self):
        assert normalize_color(255) is None


# ==============================================================================
# Tests für normalize_region
# ==============================================================================

class TestNormalizeRegion:
    """Tests für normalize_region()"""

    def test_none_returns_none(self):
        assert normalize_region(None) is None

    def test_list_with_4_values(self):
        assert normalize_region([0, 0, 100, 100]) == [0, 0, 100, 100]

    def test_tuple_with_4_values(self):
        assert normalize_region((10, 20, 30, 40)) == [10, 20, 30, 40]

    def test_list_with_more_than_4_values_truncates(self):
        assert normalize_region([0, 0, 100, 100, 200]) == [0, 0, 100, 100]

    def test_converts_floats_to_int(self):
        assert normalize_region([0.5, 10.9, 100.1, 200.8]) == [0, 10, 100, 200]

    def test_list_with_less_than_4_values_returns_none(self):
        assert normalize_region([0, 0, 100]) is None

    def test_empty_list_returns_none(self):
        assert normalize_region([]) is None


# ==============================================================================
# Tests für normalize_pos
# ==============================================================================

class TestNormalizePos:
    """Tests für normalize_pos()"""

    def test_none_returns_none(self):
        assert normalize_pos(None) is None

    def test_list_with_2_values(self):
        assert normalize_pos([100, 200]) == [100, 200]

    def test_tuple_with_2_values(self):
        assert normalize_pos((100, 200)) == [100, 200]

    def test_list_with_more_than_2_values_truncates(self):
        assert normalize_pos([100, 200, 300]) == [100, 200]

    def test_converts_floats_to_int(self):
        assert normalize_pos([100.5, 200.9]) == [100, 200]

    def test_list_with_less_than_2_values_returns_none(self):
        assert normalize_pos([100]) is None

    def test_empty_list_returns_none(self):
        assert normalize_pos([]) is None


# ==============================================================================
# Tests für convert_confirm_point
# ==============================================================================

class TestConvertConfirmPoint:
    """Tests für convert_confirm_point()"""

    def test_none_returns_none(self):
        assert convert_confirm_point(None) is None

    def test_dict_format_already_correct(self):
        """Bereits korrektes Format bleibt unverändert."""
        result = convert_confirm_point({"x": 100, "y": 200})
        assert result == {"x": 100, "y": 200}

    def test_dict_format_converts_to_int(self):
        """Float-Werte werden zu int konvertiert."""
        result = convert_confirm_point({"x": 100.5, "y": 200.9})
        assert result == {"x": 100, "y": 200}

    def test_list_format_converts_to_dict(self):
        """Altes [x, y] Format wird zu {"x": x, "y": y} konvertiert."""
        result = convert_confirm_point([100, 200])
        assert result == {"x": 100, "y": 200}

    def test_list_with_wrong_length_returns_none(self):
        """Liste mit falscher Länge gibt None zurück."""
        assert convert_confirm_point([100]) is None
        assert convert_confirm_point([100, 200, 300]) is None

    def test_int_without_points_returns_none(self):
        """Int ohne geladene Punkte gibt None zurück."""
        # POINTS ist leer
        POINTS.clear()
        assert convert_confirm_point(1) is None

    def test_int_with_points_converts(self):
        """Int mit geladenen Punkten wird konvertiert."""
        POINTS.clear()
        POINTS.extend([[100, 200], [300, 400]])

        result = convert_confirm_point(1)
        assert result == {"x": 100, "y": 200}

        result = convert_confirm_point(2)
        assert result == {"x": 300, "y": 400}

        POINTS.clear()

    def test_int_out_of_range_returns_none(self):
        """Int außerhalb des Bereichs gibt None zurück."""
        POINTS.clear()
        POINTS.extend([[100, 200]])

        assert convert_confirm_point(2) is None
        assert convert_confirm_point(0) is None
        assert convert_confirm_point(-1) is None

        POINTS.clear()

    def test_invalid_type_returns_none(self):
        """Ungültige Typen geben None zurück."""
        assert convert_confirm_point("invalid") is None
        assert convert_confirm_point(3.14) is None
