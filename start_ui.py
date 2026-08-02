#!/usr/bin/env python3
"""Start the Moodle Downloader UI with a visible Windows error fallback."""

import ctypes
import sys
import traceback
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))


def show_startup_error(error: Exception) -> None:
    message = (
        "Moodle Downloader konnte nicht gestartet werden.\n\n"
        f"{type(error).__name__}: {error}\n\n"
        "Starte bitte start_ui.bat. Das Fenster zeigt auch fehlende "
        "Python-Abhaengigkeiten an."
    )
    print(message, file=sys.stderr)
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(0, message, "Moodle Downloader - Startfehler", 0x10)
        except Exception:
            pass


def launch() -> None:
    try:
        from moodle_download.ui import main

        main()
    except Exception as error:
        traceback.print_exc()
        show_startup_error(error)
        raise SystemExit(1) from error

if __name__ == "__main__":
    launch()
