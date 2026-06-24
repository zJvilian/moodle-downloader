"""State management for incremental downloads."""

import json
import time
from pathlib import Path
from urllib.parse import urlparse


class DownloadState:
    """Track downloaded files for incremental updates."""
    
    def __init__(self, course_dir: Path):
        self.course_dir = course_dir
        self.state_file = course_dir / ".state.json"
        self.state: dict = {}
        self._load()
    
    def _load(self):
        """Load state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.state = {}
    
    def save(self):
        """Save state to file."""
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
    
    def is_downloaded(self, url: str, expected_size: int = None) -> bool:
        """Check if URL was already downloaded with same size."""
        if url not in self.state:
            return False
        
        entry = self.state[url]
        local_path = self.course_dir / entry["local_path"]
        
        # Check if file exists
        if not local_path.exists():
            return False
        
        # Check size if provided
        if expected_size is not None:
            return local_path.stat().st_size == expected_size
        
        return True
    
    def record(self, url: str, local_path: str, size: int = None):
        """Record a downloaded file."""
        self.state[url] = {
            "local_path": local_path,
            "size": size,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    
    def get_local_path(self, url: str) -> str | None:
        """Get local path for a URL."""
        if url in self.state:
            return self.state[url]["local_path"]
        return None
    
    def get_stats(self) -> dict:
        """Get state statistics."""
        return {
            "total": len(self.state),
            "urls": list(self.state.keys())
        }
