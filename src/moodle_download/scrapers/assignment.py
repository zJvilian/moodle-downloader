"""Moodle assignment scraper."""

from ..downloader import activity_directory, scrape_page_with_requests
from ..parsers import check_for_locked_content
from .common import content_markdown, download_all_links, write_markdown


def scrape_assignment_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    html = scrape_page_with_requests(url, cookies)
    if not html:
        return 0
    locked, reason = check_for_locked_content(html)
    if locked:
        print(f"\n      🔒 {reason[:60]}")
        return -1

    activity_dir = activity_directory(section_dir, name)
    count = download_all_links(html, url, activity_dir / "attachments", cookies, name)
    if write_markdown(activity_dir / "Beschreibung.md", name, url, content_markdown(html, url)):
        print(f"\n      📝 {activity_dir.name[:45]}/Beschreibung.md")
        count += 1
    return count
