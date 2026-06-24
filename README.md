# Moodle Kurs-Downloader

Lade **alle** Inhalte eines Moodle-Kurses herunter: Dateien, Beschreibungen, Foren, Quizzes, Bücher und mehr.

## Features

- 📥 Kompletter Download aller Inhaltstypen
- 🔗 Tiefes Scraping - folgt jedem Activity-Link
- 🧹 Saubere Dateinamen (URL-Encoding wird dekodiert)
- 📋 Download-Log mit Details
- 🎯 Filterbare Download-Typen
- 🔄 Update-Modus - nur neue/geänderte Dateien
- 🌐 Browser-Fallback (Firefox → Chrome → Edge)
- 🖥️ Drei Start-Methoden: BAT, Kommandozeile, GUI

## Installation

### Schritt 1: Python installieren

Python 3.8+ von [python.org](https://www.python.org/downloads/) herunterladen.

**Wichtig:** Bei der Installation "Add Python to PATH" aktivieren!

![Python PATH](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square&logo=python)

### Schritt 2: Repository klonen

```bash
git clone https://github.com/dein-benutzer/moodle-download.git
cd moodle-download
```

Oder als ZIP herunterladen und entpacken.

### Schritt 3: Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

Das installiert:
- `selenium` - Browser-Automatisierung
- `requests` - HTTP-Downloads
- `webdriver-manager` - Automatische Browser-Treiber

### Schritt 4: Browser installieren

Einer der folgenden Browser muss installiert sein:
- [Mozilla Firefox](https://www.mozilla.org/firefox/) (empfohlen)
- [Google Chrome](https://www.google.com/chrome/)
- [Microsoft Edge](https://www.microsoft.com/edge/)

Der passende WebDriver wird automatisch heruntergeladen.

### Schritt 5: Login-Daten konfigurieren

Erstelle eine `credentials.json` im Projektverzeichnis:

```json
{
    "username": "dein_benutzername",
    "password": "dein_passwort"
}
```

**Hinweis:** Die Datei wird nicht ins Git hochgeladen (siehe `.gitignore`).

## Nutzung

### Option 1: BAT-Menü (Einfachster Weg)

Doppelklick auf `download.bat`:

```
========================================
   Moodle Kurs-Downloader v2.0
========================================

[1] Download-Verzeichnis
[2] Login-Daten
[3] Moodle-Kurs-URL(s)
[4] Was herunterladen?
[5] Scraping-Tiefe
```

Folge den Anweisungen im Menü.

### Option 2: Kommandozeile

**Einzelner Kurs:**
```bash
python -m moodle_download https://moodle.hs-augsburg.de/course/view.php?id=69420
```

**Mehrere Kurse:**
```bash
python -m moodle_download URL1 URL2 URL3
```

**Mit Filtern:**
```bash
python -m moodle_download --url URL1 --include file,description
```

**Nur neue Dateien (Update):**
```bash
python -m moodle_download URL --update
```

**Alles neu herunterladen (Force):**
```bash
python -m moodle_download URL --force
```

### Option 3: GUI

Doppelklick auf `start_ui.py` oder:

```bash
python -m moodle_download.ui
```

Die GUI bietet:
- Eingabefeld für URL(s)
- Ausgabeverzeichnis auswählen
- Checkboxen für Download-Typen
- Update-Modus Checkbox
- Live-Log mit Fortschritt

## Parameter

| Parameter | Beschreibung | Beispiel |
|-----------|-------------|----------|
| `--url`, `-u` | Moodle Kurs-URL (mehrfach verwendbar) | `--url URL1 --url URL2` |
| `--output`, `-o` | Download-Verzeichnis | `--output ./meine_kurse` |
| `--username` | Benutzername | `--username max` |
| `--password` | Passwort | `--password geheim` |
| `--include`, `-i` | Nur diese Typen | `--include file,description` |
| `--exclude`, `-e` | Diese Typen ausschließen | `--exclude quiz,forum` |
| `--depth`, `-d` | Scraping-Tiefe | `--depth deep` |
| `--update` | Nur neue/geänderte Dateien | `--update` |
| `--force` | Alles neu herunterladen | `--force` |

### Verfügbare Typen für --include/--exclude

| Typ | Beschreibung |
|-----|-------------|
| `file` | Dateien, PDFs, ZIPs |
| `description` | Beschreibungen, Seiten |
| `forum` | Foren, Ankündigungen |
| `quiz` | Quizzes |
| `book` | Bücher |
| `link` | Externe Links |
| `assignment` | Aufgaben |

## Download-Struktur

```
downloads/
└── Programmierung_in_der_Wirtschaftsinformatik_(Strohmeier)/
    ├── .state.json                    # Status für Update-Modus
    ├── download_log_20260624.txt      # Download-Log
    ├── Allgemeines/
    │   ├── 📄_Vorlesung.pdf
    │   ├── 📝_Beschreibung.md
    │   └── 🔗_Externe_Ressource.url
    ├── Vorlesungen/
    │   ├── 01_klassenableitung.zip
    │   └── script.html
    ├── Interfaces/
    │   ├── 02_interfaces.zip
    │   └── Interfaces_Test_SKIP.md    # Gesperrter Inhalt
    └── Literatur/
        ├── 📚_Java_ist_auch_eine_Insel.url
        └── 📚_JAVA_Notbuch.url
```

## Update-Modus

Beim ersten Download wird eine `.state.json` erstellt, die alle heruntergeladenen Dateien trackt.

Beim nächsten Download mit `--update`:
- Bereits heruntergeladene Dateien werden übersprungen
- Geänderte Dateien (andere Größe) werden neu herunterladen
- Neue Dateien werden heruntergeladen

```bash
# Erster Download
python -m moodle_download URL

# Später nur Updates
python -m moodle_download URL --update
```

## Gesperrte Inhalte

Wenn eine Activity gesperrt ist (z.B. "Nicht verfügbar"), wird eine `*_SKIP.md` Datei erstellt:

```markdown
# Bonuspunkte  Aufgabe

⚠️ **Übersprungen**: Inhalt gesperrt

🔗 [In Moodle öffnen](https://moodle.hs-augsburg.de/mod/assign/view.php?id=12345)
```

## Fehlerbehebung

### "Kein unterstützter Browser gefunden"
Installiere Firefox, Chrome oder Edge.

### "Login fehlgeschlagen"
Prüfe `credentials.json` oder verwende `--username`/`--password`.

### "Filename or extension is too long"
Das Tool kürzt automatisch. Bei Problemen: kürzeren Pfad mit `--output` verwenden.

### Download hängt
Drücke `Ctrl+C` zum Abbrechen, dann mit `--update` weitermachen.

### WebDriver-Fehler
```bash
pip install --upgrade webdriver-manager
```

## Projektstruktur

```
moodle-download/
├── src/
│   └── moodle_download/
│       ├── __init__.py          # Version & Pfade
│       ├── __main__.py          # Entry Point
│       ├── cli.py               # Kommandozeile
│       ├── browser.py           # Browser-Detection
│       ├── downloader.py        # Download-Logik
│       ├── parsers.py           # HTML → Markdown
│       ├── logger.py            # Logging
│       ├── state.py             # Update-Modus
│       ├── ui.py                # GUI
│       └── scrapers/            # Activity-Scraper
│           ├── assignment.py
│           ├── quiz.py
│           └── ...
├── download.bat                 # Interaktives Menü
├── start_ui.py                  # GUI Starter
├── requirements.txt             # Abhängigkeiten
├── pyproject.toml               # Python-Paket
├── credentials.json             # Login-Daten (nicht im Git!)
└── README.md
```

## Lizenz

MIT License

## Support

Bei Problemen: [Issue erstellen](https://github.com/dein-benutzer/moodle-download/issues)
