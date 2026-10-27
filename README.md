# Moodle Kurs-Downloader (Browser Web-App)

Lade **alle** Inhalte eines Moodle-Kurses über eine lokale, browserbasierte Oberfläche herunter: Dateien, Beschreibungen, Foren, Quizzes, Bücher und mehr.

## Features

- 🚀 **Ein-Klick-Start ohne Vorwissen** – `start.bat` (Windows) und `start.sh` (Linux/macOS) richten beim ersten Start alles vollautomatisch ein (inkl. portablem Python via `uv`, falls kein Python auf dem System installiert ist)
- 🔐 **Automatische `.env`-Ersteinrichtung** – Fragt beim allerersten Start nach deinen Moodle-Zugangsdaten und speichert sie direkt in `.env`
- 🌐 **Lokale Web-App** – Startet einen lokalen Webserver (`http://127.0.0.1:8765`) und öffnet das Interface direkt im Browser
- 📥 **Kompletter Download** aller Inhaltstypen (PDFs, ZIPs, Seiten, Foren, Bücher, Quizzes, Aufgaben)
- 🧭 **Verschachtelte Kursstruktur** mit sprechenden Ordnern wie `Abschnitt_5_Wahrscheinlichkeitsrechnung`
- 🔗 **Tiefes Scraping** – folgt sicheren Ansichten jeder Activity und lädt auch eingebettete Anhänge
- 🎬 **YouTube-Support** – Links immer als `.url` speichern oder optional das Video herunterladen
- 🌍 **Webseiten-Archivierung** – geeignete externe Webseiten zusätzlich als bereinigtes Markdown speichern
- 🔄 **Update- & Force-Modus** – nur neue/geänderte Dateien übertragen oder alles frisch laden
- 🧠 **AI-Ready Export** – erzeugt Strukturkarte (`course_structure.json`), Manifest (`manifest.jsonl`) und geordnete Kontext-Pakete (`chunks/`)
- 📂 **Kurs-Browser** – zeigt bereits heruntergeladene Kurse samt Dateianzahl, Größe und AI-Status direkt im Web-Interface

## Schnellstart (auch ohne installiertes Python)

Du kannst das Projekt einfach als ZIP weitergeben. Es ist **keine** manuelle Python-Installation nötig!

### Windows

Doppelklick auf [`start.bat`](start.bat):
1. **Beim ersten Start**: Falls kein Python 3.10+ installiert ist, lädt das Skript automatisch eine isolierte, portable Python-Umgebung (`.tools/` & `.venv/`) herunter, installiert alle Pakete und fragt einmalig deine Moodle-Zugangsdaten für die `.env`-Datei ab.
2. **Bei jedem weiteren Start**: Überspringt die Installation sofort und öffnet direkt die lokale Web-App im Browser.

### Linux & macOS

```bash
./start.sh
```

Genau wie unter Windows prüft `start.sh`, ob `.venv` bereits existiert. Beim ersten Start richtet es Python (bei Bedarf portabel über `uv`) sowie alle Abhängigkeiten ein, fragt die Moodle-Zugangsdaten für `.env` ab und startet danach direkt den Webserver.

## Voraussetzungen

- Einen unterstützten Browser für das Hintergrund-Scraping:
  - Mozilla Firefox, Google Chrome oder Microsoft Edge
- Internetverbindung

## Projektstruktur

```
moodle-download/
├── src/
│   └── moodle_download/
│       ├── __init__.py          # Version & Pfade (.env, downloads/)
│       ├── __main__.py          # Startet die lokale Web-App
│       ├── webapp.py            # Lokaler HTTP-Server, REST-API & Browser-UI
│       ├── engine.py            # Kernlogik, .env-Verwaltung & Job-Steuerung
│       ├── browser.py           # Headless-Browser & Moodle-Extraktion
│       ├── downloader.py        # Datei-Downloads & Dateinamen-Bereinigung
│       ├── ai_export.py         # AI-ready Struktur & Kontext-Pakete
│       ├── parsers.py           # HTML → Markdown Konvertierung
│       ├── logger.py            # Download-Protokollierung
│       ├── state.py             # Inkrementeller Update-Status (.state.json)
│       └── scrapers/            # Activity-Scraper (assign, book, forum, quiz, url, ...)
├── start.bat                    # All-in-One Windows-Starter (Setup + .env + Web-App)
├── start.sh                     # All-in-One Linux/macOS-Starter (Setup + .env + Web-App)
├── start.py                     # Python-Starter inkl. .env-Ersteinrichtung
├── requirements.txt             # Abhängigkeiten
├── pyproject.toml               # Paketkonfiguration
└── tests/                       # Unittests
```

## Lizenz

MIT License
