"""Moodle file-resource scraper."""

from ..downloader import clean_filename, download_file, scrape_page_with_requests
from ..parsers import check_for_locked_content
from .common import download_all_links


def scrape_resource_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    html = scrape_page_with_requests(url, cookies)
    if not html:
        # Some Moodle configurations redirect view.php directly to the binary.
        return int(download_file(url, section_dir / clean_filename(name), cookies, name))
    locked, reason = check_for_locked_content(html)
    if locked:
        print(f"\n      🔒 {reason[:60]}")
        return -1
    return download_all_links(html, url, section_dir, cookies, name)
