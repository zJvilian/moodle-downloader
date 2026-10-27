#!/usr/bin/env python3
"""Start the local Moodle Downloader Web App (prompts for .env credentials on first run)."""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from moodle_download import ENV_FILE  # noqa: E402
from moodle_download.engine import load_saved_credentials, save_credentials  # noqa: E402
from moodle_download.webapp import main  # noqa: E402


def ensure_first_run_credentials(env_file: Path = ENV_FILE) -> None:
    """Ask the user for Moodle credentials on first launch and write them to .env."""
    saved = load_saved_credentials(env_path=env_file)
    if saved["username"] and saved["password"]:
        return

    if not sys.stdin or not sys.stdin.isatty():
        return

    print()
    print("=" * 54)
    print("  🔐 Ersteinrichtung – Moodle-Zugangsdaten")
    print("=" * 54)
    print("  Noch keine Zugangsdaten in .env gefunden.")
    print("  Gib deine Moodle-Login-Daten ein (Enter überspringt dies,")
    print("  du kannst sie auch später im Browser eingeben).")
    print("-" * 54)

    try:
        username = input("  Moodle-Benutzername: ").strip()
        if not username:
            print("  ➔ Übersprungen. Zugangsdaten können im Browser gesetzt werden.\n")
            return
        while True:
            password = getpass.getpass("  Moodle-Passwort (wird verborgen): ")
            if password:
                break
            print("  Bitte ein Passwort eingeben (oder Strg+C zum Überspringen).")
    except (EOFError, KeyboardInterrupt):
        print("\n  ➔ Übersprungen.\n")
        return

    save_credentials(username, password, env_path=env_file)
    print(f"  ✅ Zugangsdaten erfolgreich in {env_file.name} gespeichert!\n")


if __name__ == "__main__":
    if "--setup-env" in sys.argv:
        ensure_first_run_credentials()
    else:
        ensure_first_run_credentials()
        main()
