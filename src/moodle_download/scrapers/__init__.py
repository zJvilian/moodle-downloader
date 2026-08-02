"""Activity scraper registry and dispatch."""

from pathlib import Path

from ..downloader import clean_filename, download_file
from .assignment import scrape_assignment_fast
from .book import scrape_book_fast
from .folder import scrape_folder_fast
from .forum import scrape_forum_fast
from .generic import scrape_generic_fast, scrape_inline_label
from .page import scrape_page_fast
from .quiz import scrape_quiz_fast
from .resource import scrape_resource_fast
from .url import scrape_url_fast


ACTIVITY_SCRAPERS = {
    "assign": scrape_assignment_fast,
    "resource": scrape_resource_fast,
    "folder": scrape_folder_fast,
    "url": scrape_url_fast,
    "page": scrape_page_fast,
    "forum": scrape_forum_fast,
    "book": scrape_book_fast,
    "quiz": scrape_quiz_fast,
}


def process_resource(
    driver,
    resource: dict,
    section_dir: Path,
    cookies: dict,
    *,
    depth: str = "deep",
    download_youtube: bool = False,
    scrape_external: bool = True,
) -> int:
    """Process a resource while preserving inline and directly linked files."""
    url = resource.get("url", "")
    name = resource.get("name") or "Unbenannte Aktivität"
    activity_type = resource.get("type", "unknown")

    if activity_type == "label":
        return scrape_inline_label(section_dir, name, resource.get("html", ""), url, cookies)
    if resource.get("direct_file"):
        filename = resource.get("filename") or clean_filename(name)
        target_cookies = cookies if resource.get("same_origin", True) else {}
        return int(download_file(url, section_dir / filename, target_cookies, name))
    if depth == "shallow":
        shortcut = section_dir / f"{clean_filename(name)}.url"
        shortcut.write_text(f"[InternetShortcut]\nURL={url}\n", encoding="utf-8")
        print(f"\n      🔗 {shortcut.name[:60]}")
        return 1

    scraper = ACTIVITY_SCRAPERS.get(activity_type)
    if scraper:
        if activity_type == "url":
            return scraper(
                url,
                section_dir,
                cookies,
                name,
                download_youtube=download_youtube,
                scrape_external=scrape_external,
            )
        return scraper(url, section_dir, cookies, name)
    return scrape_generic_fast(url, section_dir, cookies, name, activity_type, depth=depth)
