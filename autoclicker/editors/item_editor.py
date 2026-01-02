"""
Item-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Item-Definitionen.
"""

# TODO: Die vollständige Implementierung befindet sich noch in autoclicker.py
# und sollte hierher migriert werden.
#
# Enthaltene Funktionen:
# - run_global_item_editor()
# - edit_item_preset()
# - _item_learn_command()

def run_global_item_editor(state) -> None:
    """Editor für globale Item-Definitionen.

    HINWEIS: Diese Funktion ist ein Stub. Die vollständige Implementierung
    befindet sich noch in autoclicker.py (Zeilen 2625-3388).
    """
    print("\n[INFO] Item-Editor wird aus dem Hauptskript geladen...")
    try:
        from autoclicker import run_global_item_editor as _run
        _run(state)
    except ImportError:
        print("[FEHLER] Item-Editor noch nicht vollständig migriert!")
        print("         Bitte autoclicker.py direkt verwenden.")
