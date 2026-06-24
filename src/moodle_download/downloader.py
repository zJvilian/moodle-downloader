"""Download utilities and filename handling."""

import re
import time
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote


# Max filename length (Windows limit is 260 for full path)
MAX_FILENAME_LENGTH = 100
MAX_DIRNAME_LENGTH = 60

# Rate limit delay between requests (seconds)
REQUEST_DELAY = 0.2

# Track downloaded files for post-download deduplication
_downloaded_files: dict[str, str] = {}  # hash -> filepath

# State for incremental downloads
_download_state = None


def clean_filename(name: str, max_length: int = None, is_directory: bool = False) -> str:
    """Create a safe, clean filename from a string."""
    if max_length is None:
        max_length = MAX_DIRNAME_LENGTH if is_directory else MAX_FILENAME_LENGTH
    
    cleaned = unquote(name)
    
    # Remove dates like (19.03.2026)
    cleaned = re.sub(r'\s*\(\d{2}\.\d{2}\.\d{4}\)\s*', '', cleaned)
    
    # Replace problematic characters
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', cleaned)
    
    # Replace multiple spaces/underscores
    cleaned = re.sub(r'[_\s]+', '_', cleaned)
    
    # Strip
    cleaned = cleaned.strip('. _')
    
    if not cleaned:
        return 'unnamed'
    
    # Remove trailing dots
    cleaned = cleaned.rstrip('.')
    
    # Shorten
    if len(cleaned) > max_length:
        if not is_directory:
            parts = cleaned.rsplit('.', 1)
            if len(parts) == 2 and len(parts[1]) <= 10 and len(parts[1]) > 0:
                ext = parts[1]
                name_part = parts[0][:max_length - len(ext) - 1]
                cleaned = f"{name_part}.{ext}"
            else:
                cleaned = cleaned[:max_length]
        else:
            cleaned = cleaned[:max_length]
    
    # Final cleanup
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', cleaned)
    
    return cleaned or 'unnamed'


def safe_filename(name: str, max_length: int = 100) -> str:
    """Legacy function - use clean_filename() instead."""
    return clean_filename(name, max_length, is_directory=False)


def unique_filepath(filepath: Path, activity_name: str = "") -> Path:
    """Generate a unique filepath if the file already exists."""
    if not filepath.exists():
        return filepath
    
    parent = filepath.parent
    stem = filepath.stem
    suffix = filepath.suffix
    
    if activity_name:
        prefix = clean_filename(activity_name, max_length=30, is_directory=False)
        new_path = parent / f"{prefix}_{stem}{suffix}"
        if not new_path.exists():
            return new_path
    
    counter = 2
    while counter < 100:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1
    
    return parent / f"{stem}_{int(time.time())}{suffix}"


def set_download_state(state):
    """Set the download state for incremental updates."""
    global _download_state
    _download_state = state


def download_file(url: str, filepath: Path, cookies: dict, activity_name: str = "", force: bool = False) -> bool:
    """Download a file using requests.
    
    Args:
        url: URL to download
        filepath: Local path to save file
        cookies: Authentication cookies
        activity_name: Name of parent activity (for deduplication)
        force: Force download even if already exists
    """
    global _download_state
    
    try:
        # Get file size from HEAD request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0'
        }
        
        # Check state for incremental update
        if not force and _download_state is not None:
            head = requests.head(url, cookies=cookies, headers=headers, timeout=10, allow_redirects=True)
            remote_size = int(head.headers.get('Content-Length', 0)) if head.status_code == 200 else None
            
            if _download_state.is_downloaded(url, remote_size):
                return False  # Already downloaded with same size
        
        time.sleep(REQUEST_DELAY)
        
        response = requests.get(url, cookies=cookies, headers=headers, 
                              stream=True, timeout=30, allow_redirects=True)
        
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            
            if 'text/html' in content_type and filepath.suffix not in ('.html', '.htm'):
                return False
            
            filepath = unique_filepath(filepath, activity_name)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            file_size = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    file_size += len(chunk)
            
            # Record in state
            if _download_state is not None:
                rel_path = str(filepath.relative_to(_download_state.course_dir))
                _download_state.record(url, rel_path, file_size)
            
            return True
        return False
    except Exception:
        return False


def remove_duplicate_files(directory: Path) -> int:
    """Remove duplicate files based on content hash. Returns number of removed files.
    
    Keeps files in section folders (direct subfolders of course dir).
    Removes duplicates from aggregate folders like 'Vorlesungen'.
    """
    import hashlib
    
    hash_map: dict[str, Path] = {}
    removed = 0
    
    # Get section folders (direct children of course dir)
    section_folders = set()
    for item in directory.iterdir():
        if item.is_dir():
            section_folders.add(item.name)
    
    for filepath in directory.rglob('*'):
        if not filepath.is_file():
            continue
        
        # Skip .url files (they are just links, not content)
        if filepath.suffix == '.url':
            continue
        
        # Calculate file hash
        try:
            with open(filepath, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            
            if file_hash in hash_map:
                existing = hash_map[file_hash]
                
                # Check if current file is in a section folder
                rel_path = filepath.relative_to(directory)
                is_in_section = rel_path.parts[0] in section_folders
                
                # Check if existing file is in a section folder
                rel_existing = existing.relative_to(directory)
                existing_in_section = rel_existing.parts[0] in section_folders
                
                if is_in_section and not existing_in_section:
                    # Current is in section, existing is in aggregate - keep current
                    existing.unlink()
                    hash_map[file_hash] = filepath
                    removed += 1
                elif not is_in_section and existing_in_section:
                    # Current is in aggregate, existing is in section - remove current
                    filepath.unlink()
                    removed += 1
                else:
                    # Both in same type - keep the first one
                    filepath.unlink()
                    removed += 1
            else:
                hash_map[file_hash] = filepath
        except Exception:
            continue
    
    return removed


def reset_download_tracker():
    """Reset the download tracker (for new sessions)."""
    global _downloaded_files
    _downloaded_files.clear()


def scrape_page_with_requests(url: str, cookies: dict) -> str:
    """Fetch a page using requests and return HTML content."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0'
        }
        response = requests.get(url, cookies=cookies, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
    except Exception:
        pass
    return ""


def find_download_links_in_html(html: str, base_url: str) -> list[dict]:
    """Extract download links from HTML content."""
    links = []
    for match in re.finditer(r'href=["\']([^"\']*/pluginfile\.php[^"\']*)["\']', html):
        href = match.group(1)
        if not href.startswith('http'):
            from urllib.parse import urljoin
            href = urljoin(base_url, href)
        links.append({'url': href, 'type': 'file'})
    
    for match in re.finditer(r'href=["\']([^"\']*forcedownload[^"\']*)["\']', html):
        href = match.group(1)
        if not href.startswith('http'):
            from urllib.parse import urljoin
            href = urljoin(base_url, href)
        links.append({'url': href, 'type': 'file'})
    
    return links
