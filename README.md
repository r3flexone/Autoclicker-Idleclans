# Autoclicker for Idle Clans

Ein Windows-Autoclicker mit Sequenz-Unterstützung, automatischer Item-Erkennung und Farb-Triggern.

## Features

- **Punkte aufnehmen**: Mausposition speichern mit automatischer Benennung
- **Sequenzen erstellen**: Punkte mit Wartezeiten oder Farb-Triggern verknüpfen
- **Dreiphasen-System**:
  - **START**: Wird zu Beginn jedes Zyklus ausgeführt
  - **LOOP-Phasen**: Mehrere Loops möglich, jeweils mit eigenen Wiederholungen
  - **END**: Wird nach allen Zyklen ausgeführt (z.B. für Logout)
- **Farb-Trigger**: Warte bis eine bestimmte Farbe erscheint ODER verschwindet
- **Zufällige Verzögerung**: `1 30-45` = warte 30-45 Sekunden zufällig
- **Tastatureingaben**: Automatische Tastendrücke (Enter, Space, F1-F12, etc.)
- **Automatische Slot-Erkennung**: OpenCV-basierte Erkennung von Item-Slots
- **Item-Scan System**: Items anhand von Marker-Farben oder Templates erkennen
- **Kategorie-System**: Items gruppieren (z.B. Hosen, Jacken) - nur bestes pro Kategorie klicken
- **Template-Matching**: Items per Screenshot erkennen (OpenCV)
- **Preset-System**: Slots und Items als benannte Presets speichern
- **Bedingte Logik**: ELSE-Aktionen wenn Scan/Pixel-Trigger fehlschlägt
- **Zahlenerkennung**: Warte auf Zahlen-Bedingungen (z.B. > 100, < 50)
- **Wait Scan**: Warte bis Item erscheint/verschwindet (ohne Klick)
- **Pause/Resume**: Sequenz pausieren ohne Fortschritt zu verlieren
- **Skip**: Aktuelle Wartezeit überspringen
- **Statistiken**: Laufzeit, Klicks, Items gefunden
- **Quick-Switch**: Schnell zwischen Sequenzen wechseln
- **Zeitplan**: Sequenz zu bestimmter Zeit starten (z.B. 14:30, +30m, 2h)
- **Factory Reset**: Kompletter Reset wie frisch von GitHub
- **Konfigurierbar**: Toleranzen und Einstellungen via `config.json`
- **Fail-Safe**: Maus in obere linke Ecke bewegen stoppt den Klicker

## Voraussetzungen

- Windows 10/11
- Python 3.10+
- **Optional**: Pillow für Farberkennung (`pip install pillow`)
- **Optional**: OpenCV für automatische Slot-Erkennung (`pip install opencv-python numpy`)

## Installation

```bash
git clone https://github.com/r3flexone/Autoclicker-Idleclans.git
cd Autoclicker-Idleclans
pip install pillow opencv-python numpy  # Optional, für erweiterte Features
python main.py
```

## Hotkeys

| Hotkey | Funktion |
|--------|----------|
| `CTRL+ALT+A` | Aktuelle Mausposition als Punkt speichern |
| `CTRL+ALT+U` | Letzten Punkt entfernen (Undo) |
| `CTRL+ALT+C` | Alle Punkte löschen |
| `CTRL+ALT+X` | Factory Reset (ALLES löschen - wie frisch von GitHub) |
| `CTRL+ALT+E` | Sequenz-Editor öffnen |
| `CTRL+ALT+N` | Item-Scan System (Slots, Items, Scans) |
| `CTRL+ALT+L` | Gespeicherte Sequenz laden |
| `CTRL+ALT+P` | Punkte anzeigen/testen/umbenennen |
| `CTRL+ALT+T` | Farb-Analysator |
| `CTRL+ALT+S` | Start/Stop (öffnet Lade-Menü wenn keine Sequenz geladen) |
| `CTRL+ALT+G` | Pause/Resume (während Sequenz läuft) |
| `CTRL+ALT+K` | Skip (aktuelle Wartezeit überspringen) |
| `CTRL+ALT+W` | Quick-Switch (schnell Sequenz wechseln) |
| `CTRL+ALT+Z` | Zeitplan (Sequenz zu bestimmter Zeit starten) |
| `CTRL+ALT+Q` | Programm beenden |

## Item-Scan System (`CTRL+ALT+N`)

Das Item-Scan System bietet ein Menü mit folgenden Optionen:
- **[1] Slots bearbeiten** - Bereiche wo Items erscheinen können
- **[2] Items bearbeiten** - Item-Profile für die Erkennung
- **[3] Scans bearbeiten** - Slots und Items verknüpfen
- **[4] Ziffern lernen** - Ziffern für Zahlenerkennung trainieren

### Slot-Editor (Menü → 1)

Verwaltet Bereiche wo Items erscheinen können. Arbeitet mit **Presets** - wie beim Sequenz-Editor wird am Anfang nach einem Namen gefragt.

**Ablauf:**
1. [0] Neues Preset erstellen → Name eingeben
2. [1-n] Bestehendes Preset bearbeiten
3. Slots hinzufügen/bearbeiten/löschen
4. `done` → Preset wird gespeichert
5. `cancel` → Änderungen werden verworfen

**Befehle im Editor:**

| Befehl | Beschreibung |
|--------|--------------|
| `auto` | Automatische Slot-Erkennung mit OpenCV |
| `add` | Manuell einen Slot hinzufügen |
| `del <Nr>` | Slot löschen |
| `del <Start>-<Ende>` | Mehrere Slots löschen (z.B. `del 1-7`) |
| `del all` | Alle Slots löschen |
| `edit <Nr>` | Slot bearbeiten |
| `show` | Alle Slots anzeigen |
| `done` | Preset speichern und Editor verlassen |
| `cancel` | Änderungen verwerfen und Editor verlassen |

### Automatische Erkennung

Mit `auto` werden Slots automatisch per Farbe erkannt:
1. Region markieren (oben-links, unten-rechts)
2. Screenshot wird erstellt
3. Hintergrundfarbe des Slots angeben
4. Slots werden automatisch erkannt und nummeriert
5. Screenshot und Vorschau werden in `Screenshots/` gespeichert

### Item-Editor (Menü → 2)

Verwaltet Item-Profile für die Erkennung. Arbeitet mit **Presets** - wie beim Sequenz-Editor wird am Anfang nach einem Namen gefragt.

**Ablauf:**
1. [0] Neues Preset erstellen → Name eingeben
2. [1-n] Bestehendes Preset bearbeiten
3. Items lernen/hinzufügen/bearbeiten/löschen
4. `done` → Preset wird gespeichert
5. `cancel` → Änderungen werden verworfen

**Befehle im Editor:**

| Befehl | Beschreibung |
|--------|--------------|
| `learn <Nr>` | Item von Slot Nr. lernen (scannt Marker-Farben + Template) |
| `add` | Manuell ein Item hinzufügen |
| `edit <Nr>` | Item bearbeiten (Priorität, Farben, Bestätigung) |
| `rename <Nr>` | Item umbenennen (inkl. Template-Datei) |
| `del <Nr>` | Item löschen |
| `del <Start>-<Ende>` | Mehrere Items löschen (z.B. `del 1-5`) |
| `del all` | Alle Items löschen |
| `template <Nr>` | Template für Item setzen/entfernen |
| `templates` | Verfügbare Templates anzeigen |
| `show` | Alle Items anzeigen |
| `done` | Preset speichern und Editor verlassen |
| `cancel` | Änderungen verwerfen und Editor verlassen |

### Item lernen

Mit `learn <Nr>` wird ein Item vom entsprechenden Slot gelernt:
1. Slot-Nummer eingeben
2. 1 Sekunde warten (Item muss sichtbar sein)
3. Marker-Farben werden automatisch gescannt
4. Name, Priorität und **Kategorie** eingeben
5. Optional: Template-Screenshot erstellen
6. Optional: Bestätigungs-Klick konfigurieren

### Bulk-Learn (mehrere Items auf einmal)

Mit `learn <Start>-<Ende>` können mehrere Items gleichzeitig gelernt werden:

```
learn 1-5               # Lernt Items von Slot 1 bis 5
```

**Ablauf:**
1. Gemeinsame Einstellungen eingeben (Name-Prefix, Kategorie, Template)
2. Für jeden Slot wird automatisch:
   - Screenshot erstellt
   - Marker-Farben gescannt
   - Item mit fortlaufender Nummer gespeichert (z.B. "Juwel_1", "Juwel_2", ...)
   - Template erstellt (falls gewählt)

### Kategorie-System

Items können einer **Kategorie** zugeordnet werden (z.B. "Hosen", "Jacken", "Juwelen"):

- Items **derselben Kategorie** konkurrieren - nur das mit der niedrigsten Priorität wird geklickt
- Items **verschiedener Kategorien** konkurrieren nicht - alle werden geklickt
- Ohne Kategorie ist jedes Item seine eigene Kategorie

**Beispiel:**
```
Pinkes Juwel   [Kategorie: Juwelen]  Priorität 1  ← wird geklickt
Blaues Juwel   [Kategorie: Juwelen]  Priorität 2  ← wird NICHT geklickt (P1 ist besser)
Rote Jacke     [Kategorie: Jacken]   Priorität 1  ← wird geklickt (andere Kategorie)
```

**JSON-Format:**
```json
{
  "Pinkes Juwel": {
    "name": "Pinkes Juwel",
    "priority": 1,
    "template": "pinkes_juwel.png",
    "min_confidence": 0.8,
    "category": "Juwelen"
  }
}
```

### Template-Matching

Items können per **Template-Matching** (Screenshot-Vergleich) erkannt werden:

1. Bei `learn` wird automatisch ein Template erstellt
2. Mit `template <Nr>` kann ein Template nachträglich gesetzt werden
3. Templates werden in `items/templates/` gespeichert
4. `min_confidence` (0.0-1.0) bestimmt wie genau das Match sein muss

Template-Matching ist genauer als Marker-Farben, besonders bei ähnlichen Items.

### Ziffern-Editor (Menü → 4)

Lernt Ziffern für die Zahlenerkennung. Die gelernten Ziffern werden dann im Sequenz-Editor für `wait number`-Befehle verwendet.

**Befehle im Editor:**

| Befehl | Beschreibung |
|--------|--------------|
| `learn` | Eine einzelne Ziffer/Zeichen lernen |
| `learn all` | Alle Ziffern 0-9 nacheinander lernen |
| `show <Z>` | Info zu gelerntem Zeichen anzeigen (z.B. `show 5`) |
| `del <Z>` | Zeichen löschen (z.B. `del 5`) |
| `del all` | ALLE Zeichen löschen |
| `color` | Textfarbe für bessere Erkennung setzen |
| `color clear` | Textfarbe entfernen |
| `conf <0-100>` | Mindest-Konfidenz setzen (z.B. `conf 80`) |
| `test` | Zahlenerkennung an einem Bereich testen |
| `done` / `cancel` | Editor beenden |

**Lernbare Zeichen:**
- Ziffern: `0 1 2 3 4 5 6 7 8 9`
- Trennzeichen: `. ,`
- Suffixe: `K M B k m b` (für Tausend, Million, Milliarde)

**Ablauf:**
1. Ziffern lernen: Bei `learn` einen kleinen Bereich um EINE Ziffer markieren
2. Optional: Textfarbe setzen für bessere Erkennung bei farbigem Hintergrund
3. Im Sequenz-Editor `wait number > 100` verwenden
4. Bei Verwendung großen Bereich markieren - Ziffern werden automatisch gefunden

**Beispiel "25.9K":**
```
Gelernte Zeichen: 2, 5, 9, ., K
Erkannte Zeichen: "2" "5" "." "9" "K"
Berechnete Zahl: 25.9 × 1000 = 25900
```

## Sequenz-Editor (`CTRL+ALT+E`)

### Phasen

Eine Sequenz besteht aus drei Phasen:

1. **START**: Wird zu Beginn jedes Zyklus ausgeführt
2. **LOOP**: Wird wiederholt (konfigurierbare Anzahl)
3. **END**: Wird nach allen Zyklen ausgeführt

### Editor-Befehle

| Befehl | Beschreibung |
|--------|--------------|
| `<Nr> <Zeit>` | Warte X Sekunden, dann klicke Punkt (z.B. `1 30`) |
| `<Nr> <Min>-<Max>` | Zufällige Wartezeit (z.B. `1 30-45`) |
| `<Nr> 0` | Sofort klicken ohne Wartezeit |
| `<Nr> pixel` | Warte auf Farbe, dann klicke |
| `<Nr> gone` | Warte bis Farbe VERSCHWINDET, dann klicke |
| `<Nr> <Zeit> pixel` | Warte X Sek, dann auf Farbe warten, dann klicke |
| `wait <Zeit>` | Nur warten, KEIN Klick (z.B. `wait 30`, `wait 30m`, `wait 2h`) |
| `wait <Min>-<Max>` | Zufällig warten, KEIN Klick (z.B. `wait 30-45`) |
| `wait 14:30` | Warte bis 14:30 Uhr (heute oder morgen), KEIN Klick |
| `wait pixel` | Auf Farbe warten, KEIN Klick |
| `wait gone` | Warten bis Farbe VERSCHWINDET, KEIN Klick |
| `wait number > 100` | Warte bis Zahl > 100 (Zahlenerkennung) |
| `<Nr> number > 100` | Warte auf Zahl, dann klicke |
| `wait scan <ScanName>` | Warte bis Item im Scan-Bereich gefunden (kein Klick) |
| `wait scan <ScanName> "ItemName"` | Warte auf bestimmtes Item im Scan (kein Klick) |
| `wait scan gone <ScanName>` | Warte bis KEIN Item mehr im Scan-Bereich (kein Klick) |
| `key <Taste>` | Taste sofort drücken (z.B. `key enter`) |
| `key <Zeit> <Taste>` | Warten, dann Taste drücken (z.B. `key 5 space`) |
| `key <Min>-<Max> <Taste>` | Zufällig warten, dann Taste (z.B. `key 30-45 enter`) |
| `scan <ScanName>` | Item-Scan ausführen (bestes pro Kategorie) |
| `scan <ScanName> best` | Item-Scan: nur 1 Item total (das absolute Beste) |
| `scan <ScanName> every` | Item-Scan: alle Treffer ohne Filter (für Duplikate) |
| `... else skip` | Bei Fehlschlag überspringen |
| `... else restart` | Bei Fehlschlag Sequenz neu starten |
| `... else <Nr> [s]` | Bei Fehlschlag Punkt klicken |
| `... else key <T>` | Bei Fehlschlag Taste drücken |
| `learn <Name>` | Neuen Punkt erstellen (direkt im Editor) |
| `points` | Alle verfügbaren Punkte anzeigen |
| `del <Nr>` | Schritt löschen |
| `clear` | Alle Schritte löschen |
| `show` | Aktuelle Schritte anzeigen |
| `done` | Phase abschließen und speichern |
| `cancel` | Editor abbrechen (ohne Speichern) |

### Verfügbare Tasten

`enter`, `space`, `tab`, `escape`, `backspace`, `delete`,
`left`, `up`, `right`, `down`,
`f1`-`f12`,
`0`-`9`, `a`-`z`

### Beispiel-Sequenz

```
[START: 0] > 1 5           # Punkt 1 klicken, 5s warten
[START: 1] > 2 pixel       # Warten bis Farbe erscheint, dann Punkt 2 klicken
[START: 2] > key enter     # Enter-Taste drücken
[START: 3] > done

[Loop 1: 0] > 3 30-45      # Punkt 3 klicken, 30-45s zufällig warten
[Loop 1: 1] > scan items   # Item-Scan ausführen (bestes pro Kategorie)
[Loop 1: 2] > wait 10-15   # 10-15s zufällig warten ohne Klick
[Loop 1: 3] > 4 gone       # Warten bis Farbe verschwindet, dann Punkt 4 klicken
[Loop 1: 4] > done

Zyklen: 10                 # 10 Durchläufe

[END: 0] > 5 0             # Am Ende: Punkt 5 klicken (z.B. Logout)
[END: 1] > key enter       # Enter drücken
[END: 2] > done
```

## Laufzeit-Steuerung

Während eine Sequenz läuft:

- **CTRL+ALT+S** - Stoppt die Sequenz komplett
- **CTRL+ALT+G** - Pausiert/Setzt fort (Fortschritt bleibt erhalten)
- **CTRL+ALT+K** - Überspringt die aktuelle Wartezeit

### Statistiken

Nach Sequenz-Ende werden Statistiken angezeigt:
```
STATISTIKEN:
  Laufzeit:     1h 23m 45s
  Zyklen:       5
  Klicks:       1234
  Items:        56
  Tasten:       12
```

### Zeitplan (`CTRL+ALT+Z`)

Startet eine Sequenz zu einem bestimmten Zeitpunkt. Unterstützte Formate:

| Format | Beschreibung |
|--------|-------------|
| `14:30` | Startet um 14:30 Uhr (heute, oder morgen wenn Zeit vorbei) |
| `+30m` | Startet in 30 Minuten (relativ) |
| `+2h` | Startet in 2 Stunden |
| `30m` | Wartet 30 Minuten |
| `2h` | Wartet 2 Stunden |

Der Countdown kann mit `CTRL+ALT+S` abgebrochen werden.

## Item-Scan System

Das Item-Scan System erkennt Items anhand ihrer Marker-Farben oder Templates:

1. **Slots erstellen** (`CTRL+ALT+N` → Menü 1): Bereiche wo Items erscheinen können
2. **Items lernen** (`CTRL+ALT+N` → Menü 2): Mit `learn <Nr>` Marker-Farben + Template scannen
3. **Kategorien zuweisen**: Items gruppieren (z.B. "Hosen", "Jacken")
4. **Scan konfigurieren** (`CTRL+ALT+N` → Menü 3): Slots und Items verknüpfen
5. **In Sequenz nutzen**: `scan <ScanName>`, `scan <ScanName> best` oder `scan <ScanName> every`

### Scan-Modi

| Modus | Beschreibung |
|-------|-------------|
| `scan items` | Bestes Item pro Kategorie (Standard) |
| `scan items best` | Nur 1 Item total (das absolute Beste) |
| `scan items every` | Alle Treffer ohne Filter (für Duplikate) |

**Wann welchen Modus?**
- **all** (Standard): Für Spiele wo jedes Item nur 1x im Inventar erscheint
- **best**: Wenn nur das allerbeste Item geklickt werden soll
- **every**: Für Spiele wo dasselbe Item in mehreren Slots liegen kann

### Beispiel mit Kategorien

Gefundene Items:
- Pinkes Juwel (Kategorie: Juwelen, P1)
- Blaues Juwel (Kategorie: Juwelen, P2)
- Rote Jacke (Kategorie: Jacken, P1)

Ergebnis von `scan items`:
- ✓ Pinkes Juwel wird geklickt (bestes Juwel)
- ✗ Blaues Juwel wird NICHT geklickt (P2 < P1)
- ✓ Rote Jacke wird geklickt (bestes/einziges bei Jacken)

## Bedingte Logik (ELSE)

Für Schritte mit Bedingungen (Scan, Pixel-Trigger) können Fallback-Aktionen definiert werden:

### ELSE-Syntax

| Befehl | Beschreibung |
|--------|--------------|
| `else skip` | Schritt überspringen, Sequenz fortsetzen |
| `else restart` | Sequenz komplett neu starten |
| `else <Nr>` | Anderen Punkt klicken |
| `else <Nr> <Sek>` | Warten, dann anderen Punkt klicken |
| `else key <Taste>` | Taste drücken |

### Beispiele

```
scan items else skip           # Wenn kein Item: überspringen
scan items else restart        # Wenn kein Item: Sequenz neu starten
scan items else 2              # Wenn kein Item: Punkt 2 klicken
scan items else 2 5            # Wenn kein Item: 5s warten, dann Punkt 2 klicken
1 pixel else skip              # Wenn Timeout: überspringen
1 pixel else restart           # Wenn Timeout: von vorne beginnen
1 pixel else key enter         # Wenn Timeout: Enter drücken
wait gone else skip            # Wenn Farbe nicht verschwindet: überspringen
wait scan items else skip      # Wenn kein Item nach Timeout: überspringen
wait scan gone items else 2    # Wenn Item nicht verschwindet: Punkt 2 klicken
```

### Wann wird ELSE ausgelöst?

- **Item-Scan**: Wenn kein Item gefunden wird
- **Pixel-Trigger**: Wenn Timeout erreicht wird (Standard: 60s)
- **Wait Gone**: Wenn Farbe nicht verschwindet
- **Wait Scan**: Wenn Timeout erreicht wird (Standard: 300s)
- **Wait Number**: Wenn Timeout erreicht wird (Standard: 300s)

Ohne `else` stoppt die Sequenz bei Fehlschlag.

## Konfiguration (`config.json`)

Wird beim ersten Start automatisch erstellt:

```json
{
  "clicks_per_point": 1,
  "max_total_clicks": null,
  "click_move_delay": 0.01,
  "post_click_delay": 0.05,
  "failsafe_enabled": true,
  "failsafe_x": 5,
  "failsafe_y": 5,
  "color_tolerance": 0,
  "pixel_wait_tolerance": 10,
  "pixel_wait_timeout": 300,
  "pixel_check_interval": 1,
  "scan_pixel_step": 2,
  "show_pixel_delay": 0.3,
  "scan_reverse": false,
  "scan_slot_delay": 0.1,
  "item_click_delay": 1.0,
  "marker_count": 5,
  "require_all_markers": true,
  "min_markers_required": 2,
  "slot_hsv_tolerance": 25,
  "slot_inset": 10,
  "slot_color_distance": 25,
  "default_min_confidence": 0.8,
  "default_confirm_delay": 0.5,
  "pause_check_interval": 0.5,
  "debug_mode": false,
  "debug_detection": false,
  "show_pixel_position": false,
  "debug_save_templates": false
}
```

### Klick-Einstellungen

| Option | Beschreibung |
|--------|--------------|
| `clicks_per_point` | Anzahl Klicks pro Punkt (Standard: 1) |
| `max_total_clicks` | Maximale Klicks gesamt (`null` = unendlich) |
| `click_move_delay` | Pause zwischen Mausbewegung und Klick in Sekunden (Standard: 0.01) |
| `post_click_delay` | Pause NACH dem Klick bevor Maus weiterbewegt wird (Standard: 0.05) |

### Sicherheit

| Option | Beschreibung |
|--------|--------------|
| `failsafe_enabled` | Fail-Safe: Maus in Ecke stoppt alles |
| `failsafe_x` | Fail-Safe X-Bereich: Maus x <= Wert löst aus (Standard: 5) |
| `failsafe_y` | Fail-Safe Y-Bereich: Maus y <= Wert löst aus (Standard: 5) |

### Farb-/Pixel-Erkennung

| Option | Beschreibung |
|--------|--------------|
| `color_tolerance` | Toleranz für Item-Scan (0 = exakt, höher = toleranter) |
| `pixel_wait_tolerance` | Toleranz für Pixel-Trigger (niedriger = genauer) |
| `pixel_wait_timeout` | Timeout in Sekunden für Farb-Trigger (Standard: 300) |
| `pixel_check_interval` | Wie oft auf Farbe prüfen (Sekunden) |
| `scan_pixel_step` | Pixel-Schrittweite bei Farbsuche (1=genauer, 2=schneller) |
| `show_pixel_delay` | Wie lange Pixel-Position angezeigt wird in Sekunden (Standard: 0.3) |

### Item-Scan Einstellungen

| Option | Beschreibung |
|--------|--------------|
| `scan_reverse` | Slots von hinten nach vorne scannen |
| `scan_slot_delay` | Pause zwischen Slot-Scans in Sekunden (Standard: 0.1) |
| `item_click_delay` | Pause nach Item-Klick in Sekunden (Standard: 1.0) |
| `marker_count` | Anzahl Marker-Farben pro Item (Standard: 5) |
| `require_all_markers` | Alle Marker müssen gefunden werden (true/false) |
| `min_markers_required` | Mindestanzahl Marker wenn `require_all_markers: false` |
| `slot_hsv_tolerance` | HSV-Toleranz für automatische Slot-Erkennung |
| `slot_inset` | Pixel-Einzug vom Slot-Rand für genauere Klick-Position |
| `slot_color_distance` | Farbdistanz für Hintergrund-Ausschluss bei Item-Lernen |
| `default_min_confidence` | Standard-Konfidenz für Template-Matching (Standard: 0.8 = 80%) |
| `default_confirm_delay` | Standard-Wartezeit vor Bestätigungs-Klick in Sekunden (Standard: 0.5) |

### Zahlenerkennung

| Option | Beschreibung |
|--------|--------------|
| `number_wait_timeout` | Timeout für Zahlenerkennung in Sekunden (Standard: 300) |
| `number_check_interval` | Wie oft auf Zahl prüfen in Sekunden (Standard: 2) |
| `number_color_tolerance` | Farbtoleranz für Textfarbe (Standard: 50) |
| `number_min_confidence` | Konfidenz für Ziffern-Matching (Standard: 0.8 = 80%) |

### Wait Scan

| Option | Beschreibung |
|--------|--------------|
| `scan_wait_timeout` | Timeout für Wait-Scan in Sekunden (Standard: 300) |
| `scan_wait_interval` | Wie oft auf Item prüfen in Sekunden (Standard: 2) |

### Timing

| Option | Beschreibung |
|--------|--------------|
| `pause_check_interval` | Prüf-Intervall während Pause in Sekunden (Standard: 0.5) |

### Debug-Einstellungen

| Option | Beschreibung |
|--------|--------------|
| `debug_mode` | Zeigt Schritte VOR Start und wartet auf Enter |
| `debug_detection` | Alle Ausgaben persistent (nicht überschrieben) |
| `show_pixel_position` | Maus kurz zum Prüf-Pixel bewegen beim Start |
| `debug_save_templates` | Speichert Scan+Template in `items/debug/` für Debugging |

## Dateistruktur

```
Autoclicker-Idleclans/
├── main.py                 # Einstiegspunkt
├── autoclicker/            # Hauptmodul (~5800 Zeilen)
│   ├── __init__.py
│   ├── config.py           # Konfiguration (Hotkeys, Defaults)
│   ├── models.py           # Datenmodelle (ClickPoint, Sequence, etc.)
│   ├── utils.py            # Hilfsfunktionen (Input, Zeit-Parsing)
│   ├── winapi.py           # Windows API (Maus/Tastatur)
│   ├── imaging.py          # Bildverarbeitung (Screenshots, OpenCV)
│   ├── persistence.py      # Speichern/Laden (JSON)
│   ├── handlers.py         # Hotkey-Handler
│   ├── execution.py        # Sequenz-Ausführung
│   └── editors/            # Interaktive Editoren
│       ├── __init__.py
│       ├── sequence_editor.py
│       ├── item_scan_editor.py
│       ├── item_editor.py
│       ├── slot_editor.py
│       └── digit_editor.py
├── config.json             # Konfiguration (auto-generiert)
├── README.md               # Diese Datei
├── sequences/              # Gespeicherte Sequenzen
│   ├── points.json         # Aufgenommene Punkte (mit ID und Name)
│   └── *.json              # Sequenz-Dateien
├── slots/                  # Slot-Konfigurationen
│   ├── slots.json          # Aktive Slots
│   ├── Screenshots/        # Screenshots und Vorschau-Bilder
│   └── presets/            # Slot-Presets
├── items/                  # Item-Konfigurationen
│   ├── items.json          # Aktive Items
│   ├── templates/          # Template-Bilder für Matching
│   ├── digits/             # Gelernte Ziffern für Zahlenerkennung
│   ├── debug/              # Debug-Bilder (wenn debug_save_templates=true)
│   └── presets/            # Item-Presets
├── item_scans/             # Item-Scan Konfigurationen
│   └── *.json              # Scan-Konfigurationen (verknüpft Slots + Items)
└── tools/                  # Hilfswerkzeuge
    ├── sync_json.py        # JSON-Dateien synchronisieren/migrieren
    └── slot_tester.py      # Slot-Erkennung testen
```

## Technische Details

### Architektur

Das Programm ist modular aufgebaut (~5800 Zeilen in 15 Dateien):

```
main.py                      Einstiegspunkt, Event-Loop
    │
    └── autoclicker/
        ├── config.py        Konstanten, Hotkey-IDs
        ├── models.py        Datenklassen (ClickPoint, Sequence, ...)
        ├── utils.py         Hilfsfunktionen (Input, Zeit-Parsing)
        ├── winapi.py        Windows API (Maus, Tastatur, Hotkeys)
        ├── imaging.py       Screenshots, Farberkennung, OpenCV
        ├── persistence.py   JSON-Persistenz, Presets
        ├── handlers.py      Hotkey-Callbacks
        ├── execution.py     Sequenz-Ausführung, Item-Scans
        └── editors/
            ├── sequence_editor.py    Sequenz erstellen/bearbeiten
            ├── item_scan_editor.py   Scans konfigurieren
            ├── item_editor.py        Items definieren
            └── slot_editor.py        Slots definieren
```

**Datenfluss:**
```
[Hotkey] → handlers.py → execution.py → winapi.py (Klicks/Tasten)
                │                   └──→ imaging.py (Screenshots)
                └──→ editors/*.py → persistence.py (Speichern)
```

### Thread-Modell

```
┌──────────────────┐     ┌──────────────────────────────────┐
│   Main Thread    │     │       Worker Thread              │
│                  │     │                                  │
│  Event-Loop:     │     │  sequence_worker():              │
│  - Hotkey-Check  │────►│  - START-Phase ausführen         │
│  - Handler rufen │     │  - LOOP-Phasen wiederholen       │
│                  │◄────│  - END-Phase ausführen           │
│  Events:         │     │                                  │
│  - stop_event    │     │  Prüft Events:                   │
│  - pause_event   │     │  - stop_event → Abbruch          │
│  - skip_event    │     │  - pause_event → Warten          │
│  - quit_event    │     │  - skip_event → Wartezeit skip   │
└──────────────────┘     └──────────────────────────────────┘
```

### Abhängigkeiten

| Paket | Funktion | Erforderlich |
|-------|----------|--------------|
| ctypes (builtin) | Windows API, Hotkeys, Maus/Tastatur | Ja |
| Pillow | Screenshots, Farberkennung | Optional |
| NumPy | Optimierte Farberkennung | Optional |
| OpenCV | Template Matching, Slot-Erkennung | Optional |

### Technologien

- Windows API via `ctypes` (keine externen Abhängigkeiten für Basis-Funktionen)
- Pillow für Screenshot und Farberkennung (optional)
- OpenCV für automatische Slot-Erkennung und Template Matching (optional)
- Globale Hotkeys über `RegisterHotKey`
- Mausklicks und Tastatureingaben über `SendInput`
- BitBlt für Game-Screenshots (funktioniert mit Hardware-Beschleunigung/DirectX)
- Thread-basierte Ausführung mit Events für Synchronisation
- JSON-Persistenz für alle Daten
- Multi-Monitor Unterstützung (DPI-aware)
- Sichere Dateinamen (Path-Traversal-Schutz)

## Tools

### Sync-Tool (`tools/sync_json.py`)

Bringt alle JSON-Dateien auf den aktuellen Code-Stand:

```bash
python tools/sync_json.py
```

- Fehlende Felder mit Standardwerten ergänzen
- Alte Formate konvertieren (z.B. `confirm_point` int → Koordinaten)
- Presets erben Werte von globalen Dateien

### Slot-Tester (`tools/slot_tester.py`)

Testet die automatische Slot-Erkennung mit Debug-Ausgaben:

```bash
python tools/slot_tester.py
```

## Changelog

### Neueste Änderungen

- **Wait Scan**: Warte auf Item-Erscheinen/Verschwinden (ohne Klick)
  - Neue Befehle: `wait scan <ScanName>`, `wait scan gone <ScanName>`
  - Optional: Filter auf bestimmtes Item mit `wait scan <ScanName> "ItemName"`
  - `<ScanName>` = Name eines Item-Scans (aus Item-Scan-Editor)
  - Nutzt bestehende Item-Scans - kein neuer Scan nötig
  - Konfigurierbar: `scan_wait_timeout`, `scan_wait_interval`

- **Zahlenerkennung**: Warte auf Zahlen-Bedingungen in Sequenzen
  - Neuer Ziffern-Editor zum Lernen der Schriftart (`CTRL+ALT+N` → Option 4)
  - Neue Befehle: `wait number > 100`, `wait number < 50`, `1 number > 100`
  - Unterstützt Suffixe wie K, M, B (z.B. "25.9K" = 25900)
  - Per Template-Matching der gelernten Ziffern (OpenCV)

### Vorherige Änderungen

- **Modulare Architektur**: Code in 15 Dateien aufgeteilt (~5800 Zeilen)
  - `main.py` als Einstiegspunkt
  - `autoclicker/` Package mit spezialisierten Modulen
  - `editors/` Subpackage für alle interaktiven Editoren
- **Bug-Fixes**: Slot-Editor Hintergrundfarbe, Performance-Optimierungen
- **Code-Qualität**: Duplizierung entfernt, toter Code bereinigt

### Vorherige Änderungen

- **Bulk-Learn**: `learn 1-5` lernt mehrere Items auf einmal mit gemeinsamen Einstellungen
- **Konfigurierbare Fail-Safe Zone**: `failsafe_x` und `failsafe_y` in config.json
- **Konfigurierbare Delays**: `scan_slot_delay` und `item_click_delay` für feinere Kontrolle
- **Screenshot-Optimierung**: BitBlt als primäre Methode (besser für DirectX-Spiele)
- **Sync-Tool**: JSON-Dateien automatisch aktualisieren und reparieren
- **Slot-Tester**: Debug-Tool für Slot-Erkennung
- **confirm_point als Koordinaten**: Robuster bei Punkt-Änderungen
- **Scan-Modus "every"**: Alle Treffer ohne Filter klicken (für Spiele mit Duplikaten)
- **ELSE Restart**: `else restart` Option zum Neustart der Sequenz bei Fehlschlag
- **Kategorie-System**: Items gruppieren (Hosen, Jacken, Juwelen) - nur bestes pro Kategorie klicken
- **Template-Matching**: Items per Screenshot erkennen (OpenCV)
- **Befehle vereinheitlicht**: `done`/`cancel` statt `fertig`/`abbruch` (beide funktionieren)
- **CTRL+ALT+S Auto-Load**: Öffnet Lade-Menü wenn keine Sequenz geladen
- **Step-Editor**: `learn` und `points` Befehle zum Punkte erstellen
- **Item-Editor**: `rename` Befehl zum Umbenennen (inkl. Template-Datei)
- **Scan-Modus**: Default ist jetzt `all` (bestes pro Kategorie), `best` für nur 1 Item
- **Unicode-Support**: Templates mit Umlauten (ü, ä, ö) funktionieren jetzt

### Ältere Änderungen

- **Preset-System**: Slots und Items werden als benannte Presets gespeichert
- **Screenshots-Ordner**: Alle Screenshots landen jetzt in `Screenshots/`
- **Konsistente Befehle**: `del all`, `del <Nr>-<Nr>` in allen Editoren
- **Performance**: Early-Exit bei Marker-Erkennung
- **Sicherheit**: Path-Traversal-Schutz für Dateinamen
- **Bounds-Checking**: Warnung bei Regionen außerhalb des Bildschirms
- **Konfigurierbar**: Neue Optionen für Slot-Erkennung

## Lizenz

MIT License
