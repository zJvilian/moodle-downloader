"""Complete fallback scraper for every Moodle activity type."""

from pathlib import Path

from ..downloader import activity_directory, clean_filename, scrape_page_with_requests
from ..parsers import check_for_locked_content, format_markdown_with_url, html_to_markdown
from .common import content_markdown, crawl_activity_pages, download_all_links


def scrape_inline_label(section_dir: Path, name: str, html: str, source_url: str, cookies: dict) -> int:
    content = html_to_markdown(html, source_url)
    activity_dir = activity_directory(section_dir, name)
    count = download_all_links(html, source_url, activity_dir / "attachments", cookies, name)
    if content:
        target = activity_dir / "content.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(format_markdown_with_url(name, source_url, content, "*Kurs-Hinweis*"), encoding="utf-8")
        print(f"\n      📝 {activity_dir.name[:45]}/content.md")
        count += 1
    return count


def scrape_generic_fast(
    url: str,
    section_dir: Path,
    cookies: dict,
    name: str,
    activity_type: str,
    *,
    depth: str = "deep",
) -> int:
    """Save readable content and attachments from otherwise unknown modules."""
    safe = clean_filename(name)
    activity_dir = activity_directory(section_dir, name)
    first_html = scrape_page_with_requests(url, cookies)
    if not first_html:
        return 0
    locked, reason = check_for_locked_content(first_html)
    if locked:
        print(f"\n      🔒 {reason[:60]}")
        return -1

    pages = [(url, first_html)]
    if depth == "deep":
        pages = list(crawl_activity_pages(url, cookies, activity_type, first_html=first_html))

    count = 0
    seen_files: set[str] = set()
    seen_content: set[str] = set()
    documents: list[str] = []
    for page_number, (page_url, html) in enumerate(pages, 1):
        content = content_markdown(html, page_url)
        if content and content not in seen_content:
            seen_content.add(content)
            heading = f"## Seite {page_number}\n\n**Quelle:** {page_url}\n\n"
            documents.append(heading + content)
        count += download_all_links(
            html,
            page_url,
            activity_dir / "attachments",
            cookies,
            name,
            seen_files,
        )

    if documents:
        activity_dir.mkdir(parents=True, exist_ok=True)
        target = activity_dir / "content.md"
        body = "\n\n---\n\n".join(documents)
        target.write_text(
            format_markdown_with_url(name, url, body, f"*Moodle-Aktivität: {activity_type}*"),
            encoding="utf-8",
        )
        print(f"\n      📝 {safe[:45]}/content.md")
        count += 1
    return count
