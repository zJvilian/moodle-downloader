"""Moodle folder scraper."""

from ..downloader import activity_directory, scrape_page_with_requests
from ..parsers import check_for_locked_content
from .common import download_all_links


def scrape_folder_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    html = scrape_page_with_requests(url, cookies)
    if not html:
        return 0
    locked, reason = check_for_locked_content(html)
    if locked:
        print(f"\n      🔒 {reason[:60]}")
        return -1
    return download_all_links(html, url, activity_directory(section_dir, name), cookies, name)
