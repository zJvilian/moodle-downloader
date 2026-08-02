"""Moodle book scraper."""

from ..downloader import activity_directory, scrape_page_with_requests
from ..parsers import check_for_locked_content
from .common import content_markdown, crawl_activity_pages, download_all_links, write_markdown


def scrape_book_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    first_html = scrape_page_with_requests(url, cookies)
    if not first_html:
        return 0
    locked, reason = check_for_locked_content(first_html)
    if locked:
        print(f"\n      🔒 {reason[:60]}")
        return -1

    activity_dir = activity_directory(section_dir, name)
    chapters = []
    seen_content = set()
    seen_files: set[str] = set()
    count = 0
    for number, (chapter_url, html) in enumerate(crawl_activity_pages(url, cookies, "book", first_html=first_html), 1):
        content = content_markdown(html, chapter_url)
        if content and content not in seen_content:
            seen_content.add(content)
            chapters.append(f"## Kapitel {number}\n\n**Quelle:** {chapter_url}\n\n{content}")
        count += download_all_links(html, chapter_url, activity_dir / "attachments", cookies, name, seen_files)

    if write_markdown(activity_dir / "book.md", name, url, "\n\n---\n\n".join(chapters)):
        print(f"\n      📚 {activity_dir.name[:45]}/book.md ({len(chapters)} Kapitel)")
        count += 1
    return count
