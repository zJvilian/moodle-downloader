"""Moodle external URL scraper."""

import re
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

from ..downloader import activity_directory, clean_filename, scrape_page_with_requests
from ..parsers import check_for_locked_content, first_content_region
from .common import extract_links
from .external import download_youtube_video, is_youtube_url, is_youtube_video_url, scrape_external_page


def _without_redirect(url: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["redirect"] = "0"
    return urlunparse(parsed._replace(query=urlencode(query)))


def _nested_external_url(candidate: str, moodle_host: str) -> str:
    parsed = urlparse(candidate)
    if parsed.netloc.casefold() != moodle_host:
        return candidate
    query = parse_qs(parsed.query)
    for key in ("url", "target", "redirect"):
        nested = query.get(key, [""])[0]
        if urlparse(nested).scheme in {"http", "https"}:
            return nested
    return ""


def find_external_target(html: str, moodle_url: str) -> str:
    """Find the configured URL resource without selecting header/footer links."""
    moodle_host = urlparse(moodle_url).netloc.casefold()
    focused = first_content_region(
        html,
        class_names=("urlworkaround", "resourcecontent", "generalbox", "no-overflow"),
        element_ids=("intro",),
    )
    for source in (focused, html):
        if not source:
            continue
        for target, _ in extract_links(source, moodle_url):
            external = _nested_external_url(target, moodle_host)
            if external:
                return external
    refresh = re.search(r'(?:url=|location(?:\.href)?\s*=\s*["\'])(https?://[^"\'<>\s]+)', html, re.IGNORECASE)
    return refresh.group(1) if refresh else ""


def scrape_url_fast(
    url: str,
    section_dir,
    cookies: dict,
    name: str,
    *,
    download_youtube: bool = False,
    scrape_external: bool = True,
) -> int:
    html = scrape_page_with_requests(_without_redirect(url), cookies)
    if not html:
        return 0
    locked, reason = check_for_locked_content(html)
    if locked:
        print(f"\n      🔒 {reason[:60]}")
        return -1

    external = find_external_target(html, url)
    if not external:
        return 0

    activity_dir = activity_directory(section_dir, name)
    activity_dir.mkdir(parents=True, exist_ok=True)
    shortcut = activity_dir / f"{clean_filename(name)}.url"
    shortcut.write_text(f"[InternetShortcut]\nURL={external}\n", encoding="utf-8")
    print(f"\n      🔗 {activity_dir.name[:40]}/{shortcut.name[:40]}")
    count = 1

    if is_youtube_url(external):
        if download_youtube:
            if is_youtube_video_url(external):
                if download_youtube_video(external, activity_dir / "video"):
                    count += 1
            else:
                print("\n      ℹ️ Playlist/Kanal erkannt; aus Sicherheitsgründen bleibt es beim Link")
    elif scrape_external and scrape_external_page(external, activity_dir / "Webseite.md", name):
        count += 1
    return count


def extract_links_from_html(html: str, base_url: str) -> list[dict]:
    base_host = urlparse(base_url).netloc.casefold()
    return [
        {"url": url, "type": "external"}
        for url, _ in extract_links(html, base_url)
        if urlparse(url).netloc.casefold() != base_host
    ]
