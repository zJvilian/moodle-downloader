"""Shared activity scraping helpers."""

from __future__ import annotations

from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..downloader import (
    clean_filename,
    download_file,
    filename_from_url,
    find_download_links_in_html,
    normalize_url,
    scrape_page_with_requests,
)
from ..parsers import first_content_region, format_markdown_with_url, html_to_markdown


CONTENT_CLASSES = (
    "no-overflow", "page-content", "book_content", "activity-description",
    "activity-information", "generalbox", "contentwithoutlink", "contentafterlink",
    "wiki-content", "entry-content", "glossarypost", "feedback_description",
    "lesson-content", "workshop-description",
)
CONTENT_IDS = ("intro", "region-main", "page-content")


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href", "")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self.links.append((normalize_url(self._href, self.base_url), " ".join(self._text).strip()))
            self._href = ""
            self._text = []


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    parser = _LinkParser(base_url)
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        pass
    seen = set()
    result = []
    for url, text in parser.links:
        if url and url not in seen:
            seen.add(url)
            result.append((url, text))
    return result


def content_markdown(html: str, base_url: str) -> str:
    region = first_content_region(html, class_names=CONTENT_CLASSES, element_ids=CONTENT_IDS)
    return html_to_markdown(region, base_url) if region else ""


def write_markdown(path: Path, name: str, source_url: str, content: str, extra: str = "") -> bool:
    if not content or len(content.strip()) < 2:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_markdown_with_url(name, source_url, content, extra), encoding="utf-8")
    return True


def download_all_links(
    html: str,
    base_url: str,
    destination: Path,
    cookies: dict,
    activity_name: str,
    seen_urls: set[str] | None = None,
) -> int:
    """Download every unique attachment and embedded Moodle file in a page."""
    count = 0
    destination.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(find_download_links_in_html(html, base_url), 1):
        if seen_urls is not None:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
        filename = item.get("name") or filename_from_url(item["url"], f"file_{index}")
        if not Path(filename).suffix:
            filename = filename_from_url(item["url"], f"file_{index}")
        target = destination / clean_filename(filename)
        target_cookies = cookies if urlparse(item["url"]).netloc == urlparse(base_url).netloc else {}
        if download_file(item["url"], target, target_cookies, activity_name):
            print(f"\n      ✅ {target.name[:60]}")
            count += 1
    return count


_DANGEROUS_QUERY_KEYS = {
    "action", "add", "attempt", "cancel", "confirm", "delete", "edit", "finishattempt",
    "logout", "mark", "move", "sesskey", "submit", "subscribe", "unsubscribe",
}


def _safe_activity_page(url: str, origin, mod_type: str, activity_id: str) -> bool:
    parsed = urlparse(url)
    if (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc):
        return False
    if f"/mod/{mod_type}/" not in parsed.path:
        return False
    query = parse_qs(parsed.query)
    candidate_id = query.get("id", [""])[0]
    if activity_id and candidate_id and candidate_id != activity_id:
        return False
    return not (_DANGEROUS_QUERY_KEYS & {key.lower() for key in query})


def crawl_activity_pages(
    start_url: str,
    cookies: dict,
    activity_type: str,
    *,
    first_html: str = "",
    max_pages: int | None = None,
):
    """Yield safe, read-only pages belonging to one Moodle activity."""
    origin = urlparse(start_url)
    activity_id = parse_qs(origin.query).get("id", [""])[0]
    queue = deque([normalize_url(start_url)])
    queued = set(queue)
    visited = set()
    while queue and (max_pages is None or len(visited) < max_pages):
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        html = first_html if url == normalize_url(start_url) and first_html else scrape_page_with_requests(url, cookies)
        if not html:
            continue
        yield url, html
        for linked, _ in extract_links(html, url):
            linked = normalize_url(linked)
            if linked not in visited and linked not in queued and _safe_activity_page(linked, origin, activity_type, activity_id):
                queued.add(linked)
                queue.append(linked)
