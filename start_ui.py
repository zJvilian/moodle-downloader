#!/usr/bin/env python3
"""Start the Moodle Downloader UI."""
import sys
import os
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from moodle_download.ui import main

if __name__ == "__main__":
    main()
