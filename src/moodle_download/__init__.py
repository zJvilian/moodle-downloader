"""
Moodle Kurs-Downloader
======================
Lädt alle Inhalte eines Moodle-Kurses über ein lokales Browser-Webinterface herunter.
"""

from pathlib import Path

__version__ = "3.0.0"
__author__ = "Julian"

# Paths
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # Go up from src/moodle_download/ to project root
ENV_FILE = PROJECT_ROOT / ".env"
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
