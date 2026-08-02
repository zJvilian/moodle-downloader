"""Safe helpers for external webpages and opt-in YouTube downloads."""

from __future__ import annotations

import ipaddress
import json
import re
import shutil
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests

from ..parsers import first_content_region, format_markdown_with_url, html_to_markdown


MAX_EXTERNAL_HTML_BYTES = 5_000_000
MAX_EXTERNAL_MARKDOWN_CHARS = 1_500_000
YOUTUBE_HOSTS = {
    "youtu.be",
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}


def is_youtube_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").casefold().rstrip(".")
    return host in YOUTUBE_HOSTS or host.endswith(".youtube.com")


def is_youtube_video_url(url: str) -> bool:
    """Return true only for a single video, never a bare playlist or channel."""
    if not is_youtube_url(url):
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    path = parsed.path.rstrip("/")
    if host == "youtu.be":
        return bool(path.strip("/"))
    if path == "/watch":
        from urllib.parse import parse_qs

        return bool(parse_qs(parsed.query).get("v", [""])[0])
    return any(path.startswith(prefix) and len(path) > len(prefix) for prefix in ("/shorts/", "/live/", "/embed/"))


def _safe_public_url(url: str, *, resolve_host: bool = False) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.casefold().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local")):
        return False
    addresses = []
    try:
        addresses.append(ipaddress.ip_address(host))
    except ValueError:
        if not resolve_host:
            return True
        try:
            addresses.extend(
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
            )
        except (OSError, ValueError):
            return False
    return bool(addresses) and all(
        not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )
        for address in addresses
    )


class _PageMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts: list[str] = []
        self.description = ""
        self.robots = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {str(key).casefold(): value or "" for key, value in attrs}
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            name = values.get("name", "").casefold()
            property_name = values.get("property", "").casefold()
            if name == "description" or property_name == "og:description":
                self.description = self.description or values.get("content", "").strip()
            elif name in {"robots", "googlebot"}:
                self.robots = f"{self.robots},{values.get('content', '')}".casefold()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.title_parts)).strip()


def _response_encoding(response) -> str:
    content_type = response.headers.get("Content-Type", "")
    match = re.search(r"charset=([^;\s]+)", content_type, re.IGNORECASE)
    if match:
        return match.group(1).strip('"\'')
    return response.encoding or "utf-8"


def scrape_external_page(url: str, destination: Path, link_name: str) -> bool:
    """Archive one suitable public HTML page as cleaned Markdown."""
    if not _safe_public_url(url, resolve_host=True):
        print("\n      ⚠️ Private oder unsichere Webadresse wird nicht automatisch ausgelesen")
        return False
    try:
        with requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MoodleDownloader/2.2; +local-course-archive)",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
            },
            stream=True,
            timeout=30,
            allow_redirects=True,
        ) as response:
            response.raise_for_status()
            final_url = response.url
            if not _safe_public_url(final_url, resolve_host=True):
                return False
            content_type = response.headers.get("Content-Type", "").casefold()
            if content_type and not any(kind in content_type for kind in ("text/html", "application/xhtml+xml", "text/plain")):
                return False
            length = response.headers.get("Content-Length", "")
            if length.isdigit() and int(length) > MAX_EXTERNAL_HTML_BYTES:
                return False
            chunks = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_EXTERNAL_HTML_BYTES:
                    return False
                chunks.append(chunk)
            source = b"".join(chunks).decode(_response_encoding(response), errors="replace")
    except (LookupError, OSError, UnicodeError, requests.RequestException) as error:
        print(f"\n      ⚠️ Webseite konnte nicht archiviert werden ({type(error).__name__})")
        return False

    metadata = _PageMetadataParser()
    try:
        metadata.feed(source)
        metadata.close()
    except Exception:
        pass
    if "noarchive" in metadata.robots:
        print("\n      ℹ️ Webseite untersagt Archivierung per robots-Metadaten")
        return False

    if "text/plain" in content_type:
        markdown = source.strip()
    else:
        region = first_content_region(
            source,
            class_names=("article-body", "article-content", "entry-content", "main-content", "post-content"),
            element_ids=("main", "content", "article"),
            tag_names=("article", "main"),
        )
        markdown = html_to_markdown(region or source, final_url)
    if len(markdown) < 80:
        return False
    if len(markdown) > MAX_EXTERNAL_MARKDOWN_CHARS:
        markdown = markdown[:MAX_EXTERNAL_MARKDOWN_CHARS].rstrip() + "\n\n*[Inhalt gekürzt]*"

    title = metadata.title or link_name
    extra = "*Automatisch archivierte externe Webseite*"
    if metadata.description:
        extra += f"\n\n> {metadata.description}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(format_markdown_with_url(title, final_url, markdown, extra), encoding="utf-8")
    print(f"\n      🌐 {destination.name[:60]}")
    return True


class _YtDlpLogger:
    def debug(self, message: str) -> None:
        if not message.startswith("[debug] ") and "has already been downloaded" in message:
            print("\n      ℹ️ YouTube-Video ist bereits vorhanden")

    def info(self, message: str) -> None:
        return None

    def warning(self, message: str) -> None:
        print(f"\n      ⚠️ yt-dlp: {message[:120]}")

    def error(self, message: str) -> None:
        print(f"\n      ❌ yt-dlp: {message[:120]}")


def download_youtube_video(url: str, destination: Path) -> bool:
    """Download one YouTube video and machine-readable metadata via yt-dlp."""
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        print("\n      ⚠️ yt-dlp fehlt; der YouTube-Link wurde nur gespeichert")
        return False

    destination.mkdir(parents=True, exist_ok=True)
    has_ffmpeg = bool(shutil.which("ffmpeg"))
    options = {
        "format": "bv*+ba/b" if has_ffmpeg else "best[ext=mp4]/best",
        "outtmpl": str(destination / "%(title).100B [%(id)s].%(ext)s"),
        "noplaylist": True,
        "ignoreconfig": True,
        "windowsfilenames": True,
        "continuedl": True,
        "overwrites": False,
        "retries": 3,
        "fragment_retries": 3,
        "writeinfojson": True,
        "logger": _YtDlpLogger(),
        "quiet": True,
    }
    if has_ffmpeg:
        options["merge_output_format"] = "mp4"
    try:
        with YoutubeDL(options) as downloader:
            result = downloader.download([url])
        if result == 0:
            marker = destination / "source.json"
            marker.write_text(json.dumps({"source_url": url}, indent=2), encoding="utf-8")
            print("\n      🎬 YouTube-Video gespeichert")
            return True
    except Exception as error:
        print(f"\n      ⚠️ YouTube-Download fehlgeschlagen ({type(error).__name__}); Link bleibt erhalten")
    return False
