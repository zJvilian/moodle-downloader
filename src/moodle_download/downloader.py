"""Download utilities, URL discovery, and safe filename handling."""

from __future__ import annotations

import html as html_module
import os
import re
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests


MAX_FILENAME_LENGTH = 120
MAX_DIRNAME_LENGTH = 72
MAX_ABSOLUTE_FILE_PATH = 245
MAX_ABSOLUTE_ACTIVITY_PATH = 190
REQUEST_DELAY = 0.12
REQUEST_TIMEOUT = 45

_download_state = None
_force_download = False
_update_mode = False
_claimed_paths: dict[str, str] = {}


def clean_filename(name: str, max_length: int | None = None, is_directory: bool = False) -> str:
    """Create a portable, readable filename while preserving its extension."""
    if max_length is None:
        max_length = MAX_DIRNAME_LENGTH if is_directory else MAX_FILENAME_LENGTH

    cleaned = html_module.unescape(unquote(str(name or "")))
    cleaned = re.sub(r"\s*\(\d{2}\.\d{2}\.\d{4}\)\s*", " ", cleaned)
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", cleaned)
    cleaned = re.sub(r"[_\s]+", "_", cleaned).strip(". _")
    if not cleaned:
        return "unnamed"

    # Windows reserves these names, even when an extension is present.
    stem = cleaned.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        cleaned = f"_{cleaned}"

    if len(cleaned) > max_length:
        suffix = "" if is_directory else Path(cleaned).suffix
        if suffix and len(suffix) < max_length - 8:
            cleaned = f"{cleaned[:max_length - len(suffix)]}{suffix}"
        else:
            cleaned = cleaned[:max_length]
    return cleaned.rstrip(". ") or "unnamed"


def safe_filename(name: str, max_length: int = MAX_FILENAME_LENGTH) -> str:
    """Backward-compatible alias for :func:`clean_filename`."""
    return clean_filename(name, max_length=max_length)


def activity_directory(parent: Path, name: str) -> Path:
    """Create a bounded activity path with room left for attachments."""
    available = max(12, min(MAX_DIRNAME_LENGTH, MAX_ABSOLUTE_ACTIVITY_PATH - len(str(parent)) - 1))
    return parent / clean_filename(name, max_length=available, is_directory=True)


def _bounded_file_path(path: Path) -> Path:
    if len(str(path)) <= MAX_ABSOLUTE_FILE_PATH:
        return path
    available = max(12, MAX_ABSOLUTE_FILE_PATH - len(str(path.parent)) - 1)
    return path.with_name(clean_filename(path.name, max_length=available))


def unique_filepath(filepath: Path, activity_name: str = "") -> Path:
    """Return a collision-free sibling path."""
    if not filepath.exists() and str(filepath).casefold() not in _claimed_paths:
        return filepath
    stem, suffix = filepath.stem, filepath.suffix
    if activity_name:
        prefix = clean_filename(activity_name, max_length=32)
        candidate = filepath.with_name(f"{prefix}_{stem}{suffix}")
        if not candidate.exists() and str(candidate).casefold() not in _claimed_paths:
            return candidate
    for counter in range(2, 1000):
        candidate = filepath.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists() and str(candidate).casefold() not in _claimed_paths:
            return candidate
    return filepath.with_name(f"{stem}_{time.time_ns()}{suffix}")


def set_download_state(state):
    """Set the incremental state object (kept for API compatibility)."""
    global _download_state
    _download_state = state


def set_download_options(*, state=None, update: bool = False, force: bool = False) -> None:
    """Configure one course download and reset per-course collision tracking."""
    global _download_state, _update_mode, _force_download
    _download_state = state
    _update_mode = update
    _force_download = force
    _claimed_paths.clear()


def _content_disposition_filename(value: str) -> str:
    if not value:
        return ""
    encoded = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", value, re.IGNORECASE)
    if encoded:
        return unquote(encoded.group(1).strip().strip('"'))
    plain = re.search(r"filename\s*=\s*(?:\"([^\"]+)\"|([^;]+))", value, re.IGNORECASE)
    if plain:
        return (plain.group(1) or plain.group(2) or "").strip().strip('"')
    return ""


def filename_from_url(url: str, fallback: str = "download") -> str:
    """Derive a decoded filename from a Moodle file URL."""
    path = unquote(urlparse(html_module.unescape(url)).path).rstrip("/")
    name = path.rsplit("/", 1)[-1] if path else ""
    if not name or name.lower() in {"view.php", "pluginfile.php", "download.php", "download_folder.php"}:
        name = fallback
    return clean_filename(name)


def _target_for_download(url: str, requested: Path, response) -> Path:
    server_name = _content_disposition_filename(response.headers.get("Content-Disposition", ""))
    target = requested
    if server_name:
        clean_server_name = clean_filename(server_name)
        if not requested.suffix or requested.name.startswith("file_") or requested.name == "download":
            target = requested.with_name(clean_server_name)

    # Reuse the recorded location for a URL, which prevents duplicate files on reruns.
    if _download_state is not None:
        recorded = _download_state.get_local_path(url)
        if recorded:
            target = _download_state.course_dir / recorded

    target = _bounded_file_path(target)

    key = str(target.resolve()).casefold()
    owner = _claimed_paths.get(key)
    if owner and owner != url:
        target = unique_filepath(target)
        key = str(target.resolve()).casefold()
    _claimed_paths[key] = url
    return target


def download_file(url: str, filepath: Path, cookies: dict, activity_name: str = "", force: bool = False) -> bool:
    """Download a file atomically.

    ``True`` means the file is available locally, including an unchanged file in
    update mode. This distinction prevents valid existing downloads from being
    reported as missing activities.
    """
    url = normalize_url(url)
    should_force = force or _force_download
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
        "Accept": "*/*",
    }
    try:
        if _update_mode and not should_force and _download_state is not None:
            remote_size = None
            try:
                head = requests.head(url, cookies=cookies, headers=headers, timeout=12, allow_redirects=True)
                size_header = head.headers.get("Content-Length") if head.ok else None
                remote_size = int(size_header) if size_header and size_header.isdigit() else None
            except requests.RequestException:
                pass
            # Without a trustworthy remote size we cannot prove the file is
            # unchanged, so fetch it instead of risking a stale local copy.
            if remote_size is not None and _download_state.is_downloaded(url, remote_size):
                recorded = _download_state.get_local_path(url)
                if recorded:
                    _claimed_paths[str((_download_state.course_dir / recorded).resolve()).casefold()] = url
                return True

        time.sleep(REQUEST_DELAY)
        response = requests.get(
            url,
            cookies=cookies,
            headers=headers,
            stream=True,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type and filepath.suffix.lower() not in {".html", ".htm"}:
            print(f"\n      ⚠️ Statt einer Datei wurde HTML geliefert: {url[:100]}")
            return False

        target = _target_for_download(url, filepath, response)
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".part", dir=target.parent)
        file_size = 0
        try:
            with os.fdopen(handle, "wb") as output:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        output.write(chunk)
                        file_size += len(chunk)
            os.replace(temp_name, target)
        except Exception:
            try:
                os.close(handle)
            except OSError:
                pass
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass
            raise

        if _download_state is not None:
            relative = str(target.relative_to(_download_state.course_dir))
            _download_state.record(url, relative, file_size)
        return True
    except (OSError, ValueError, requests.RequestException) as error:
        print(f"\n      ⚠️ Download fehlgeschlagen ({type(error).__name__}): {url[:100]}")
        return False


def remove_duplicate_files(directory: Path) -> int:
    """Compatibility no-op.

    Identical files may intentionally occur in two Moodle sections. Removing one
    breaks the course hierarchy, so completeness now takes precedence over
    destructive content deduplication.
    """
    return 0


def reset_download_tracker() -> None:
    """Reset per-course target tracking."""
    _claimed_paths.clear()


def scrape_page_with_requests(url: str, cookies: dict) -> str:
    """Fetch an authenticated HTML page."""
    try:
        response = requests.get(
            normalize_url(url),
            cookies=cookies,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MoodleDownloader/2.2)"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if response.ok and "text/html" in response.headers.get("Content-Type", "text/html").lower():
            return response.text
    except requests.RequestException:
        pass
    return ""


def normalize_url(url: str, base_url: str = "") -> str:
    """Resolve and de-HTML-escape a URL while dropping its fragment."""
    resolved = urljoin(base_url, html_module.unescape(str(url or "").strip()))
    return resolved.split("#", 1)[0]


_FILE_EXTENSIONS = {
    ".7z", ".aac", ".avi", ".bmp", ".csv", ".doc", ".docx", ".epub", ".gif",
    ".gz", ".h5p", ".jpeg", ".jpg", ".json", ".m4a", ".mkv", ".mov", ".mp3",
    ".mp4", ".odp", ".ods", ".odt", ".pdf", ".png", ".ppt", ".pptx", ".rar",
    ".rtf", ".svg", ".tar", ".tex", ".tif", ".tiff", ".tsv", ".txt", ".wav",
    ".webm", ".webp", ".xls", ".xlsx", ".xml", ".zip",
}


def _looks_downloadable(url: str, tag: str, has_download_attr: bool = False) -> bool:
    parsed = urlparse(url)
    lower = url.lower()
    path = parsed.path.lower()
    if parsed.scheme not in {"http", "https"}:
        return False
    if any(token in lower for token in ("/user/icon/", "/theme/image.php", "/pix/", "/emoji/")):
        return False
    if any(token in lower for token in (
        "/pluginfile.php", "/draftfile.php", "/webservice/pluginfile.php",
        "/download.php", "/download_folder.php", "/export.php", "/package.php",
        "/backupfile.php", "/portfolio/download/", "forcedownload=1", "download=1",
    )):
        return True
    query_values = [value for values in parse_qs(parsed.query).values() for value in values]
    query_has_filename = any(Path(value.lower()).suffix in _FILE_EXTENSIONS for value in query_values)
    return tag == "a" and (has_download_attr or Path(path).suffix in _FILE_EXTENSIONS or query_has_filename)


class _DownloadLinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[dict] = []
        self.seen: set[str] = set()

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        candidates: list[tuple[str, str]] = []
        if tag == "a":
            candidates.append((values.get("href", ""), values.get("download", "")))
        if tag in {"img", "source", "audio", "video", "embed", "iframe"}:
            candidates.extend((values.get(key, ""), "") for key in ("src", "data-src", "poster"))
            for srcset_item in values.get("srcset", "").split(","):
                candidates.append((srcset_item.strip().split(" ", 1)[0], ""))
        if tag == "object":
            candidates.append((values.get("data", ""), ""))
        candidates.extend((values.get(key, ""), "") for key in ("data-downloadurl", "data-file-url"))

        for candidate, suggested in candidates:
            if not candidate:
                continue
            # Moodle sometimes stores data-downloadurl as "mime:filename:url".
            if candidate.count(":") >= 2 and not candidate.startswith(("http://", "https://")):
                http_position = candidate.find("http")
                candidate = candidate[http_position:] if http_position >= 0 else candidate.rsplit(":", 1)[-1]
            absolute = normalize_url(candidate, self.base_url)
            if not _looks_downloadable(absolute, tag, "download" in values):
                continue
            key = absolute.casefold()
            if key in self.seen:
                continue
            self.seen.add(key)
            self.links.append({
                "url": absolute,
                "type": "file",
                "name": clean_filename(suggested) if suggested else filename_from_url(absolute),
                "embedded": tag != "a",
            })


def find_download_links_in_html(html: str, base_url: str) -> list[dict]:
    """Extract every accessible Moodle file/attachment URL from HTML."""
    parser = _DownloadLinkParser(base_url)
    try:
        parser.feed(html or "")
    except Exception:
        pass
    # Some Moodle plugins place pluginfile URLs inside JSON or style attributes.
    for match in re.finditer(r"(?:https?://[^\s\"'<>]+|/[^\s\"'<>]*(?:pluginfile|draftfile)\.php[^\s\"'<>]*)", html_module.unescape(html or ""), re.IGNORECASE):
        candidate = normalize_url(match.group(0).rstrip(")],;"), base_url)
        key = candidate.casefold()
        if key in parser.seen or not _looks_downloadable(candidate, "embed"):
            continue
        parser.seen.add(key)
        parser.links.append({"url": candidate, "type": "file", "name": filename_from_url(candidate), "embedded": True})
    return parser.links
