"""
Sequenz-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Klick-Sequenzen.
"""

# TODO: Die vollständige Implementierung befindet sich noch in autoclicker.py
# und sollte hierher migriert werden.
#
# Enthaltene Funktionen:
# - run_sequence_editor()
# - edit_sequence()
# - edit_loop_phases()
# - edit_phase()
# - parse_else_condition()
# - run_sequence_loader()

def run_sequence_editor(state) -> None:
    """Interaktiver Sequenz-Editor.

    HINWEIS: Diese Funktion ist ein Stub. Die vollständige Implementierung
    befindet sich noch in autoclicker.py (Zeilen 4648-5540).
    """
    print("\n[INFO] Sequenz-Editor wird aus dem Hauptskript geladen...")
    try:
        from autoclicker import run_sequence_editor as _run
        _run(state)
    except ImportError:
        print("[FEHLER] Sequenz-Editor noch nicht vollständig migriert!")
        print("         Bitte autoclicker.py direkt verwenden.")


def run_sequence_loader(state) -> None:
    """Lädt eine gespeicherte Sequenz.

    HINWEIS: Diese Funktion ist ein Stub. Die vollständige Implementierung
    befindet sich noch in autoclicker.py (Zeilen 5542-5615).
    """
    print("\n[INFO] Sequenz-Loader wird aus dem Hauptskript geladen...")
    try:
        from autoclicker import run_sequence_loader as _run
        _run(state)
    except ImportError:
        print("[FEHLER] Sequenz-Loader noch nicht vollständig migriert!")
        print("         Bitte autoclicker.py direkt verwenden.")
