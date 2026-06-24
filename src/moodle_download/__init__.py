"""
Moodle Kurs-Downloader
======================
Lädt alle Inhalte eines Moodle-Kurses herunter.
"""

from pathlib import Path

__version__ = "2.0.0"
__author__ = "Julian"

# Paths
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # Go up from src/moodle_download/ to project root
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
