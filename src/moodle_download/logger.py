"""Logging module for Moodle Downloader."""

import time
from pathlib import Path


class DownloadLogger:
    """Logger for tracking download progress and results."""
    
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_file = log_dir / f"download_log_{timestamp}.txt"
        
        self.downloaded = []
        self.skipped = []
        self.errors = []
        self.start_time = time.time()
        
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write("Moodle Download Log\n")
            f.write(f"{'=' * 60}\n")
            f.write(f"Gestartet: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    def log_download(self, filepath: str, source_url: str = ""):
        """Log a successful download."""
        self.downloaded.append(filepath)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"[OK] {filepath}\n")
            if source_url:
                f.write(f"     Quelle: {source_url}\n")
    
    def log_skip(self, name: str, reason: str):
        """Log a skipped activity."""
        self.skipped.append((name, reason))
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"[SKIP] {name}\n")
            f.write(f"       Grund: {reason}\n")
    
    def log_error(self, name: str, error: str):
        """Log an error."""
        self.errors.append((name, error))
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"[ERROR] {name}\n")
            f.write(f"        Fehler: {error}\n")
    
    def write_summary(self, course_title: str, course_url: str) -> Path:
        """Write summary at end of log."""
        elapsed = time.time() - self.start_time
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 60}\n")
            f.write("ZUSAMMENFASSUNG\n")
            f.write(f"{'=' * 60}\n")
            f.write(f"Kurs: {course_title}\n")
            f.write(f"URL: {course_url}\n")
            f.write(f"Dauer: {elapsed:.1f} Sekunden\n\n")
            f.write(f"Heruntergeladen: {len(self.downloaded)} Dateien\n")
            f.write(f"Uebersprungen: {len(self.skipped)} Activities\n")
            f.write(f"Fehler: {len(self.errors)}\n\n")
            
            if self.skipped:
                f.write("\nUEBERSPRUNGENE ACTIVITIES:\n")
                for name, reason in self.skipped:
                    f.write(f"  - {name}: {reason}\n")
            
            if self.errors:
                f.write("\nFEHLER:\n")
                for name, error in self.errors:
                    f.write(f"  - {name}: {error}\n")
        
        return self.log_file


def setup_logging(output_dir: Path) -> DownloadLogger:
    """Set up logging for a download session."""
    return DownloadLogger(output_dir)
