"""Moodle forum scraper."""

from ..downloader import activity_directory, scrape_page_with_requests
from ..parsers import check_for_locked_content, extract_content_regions, html_to_markdown
from .common import crawl_activity_pages, download_all_links, write_markdown


def scrape_forum_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    first_html = scrape_page_with_requests(url, cookies)
    if not first_html:
        return 0
    locked, reason = check_for_locked_content(first_html)
    if locked:
        print(f"\n      🔒 {reason[:60]}")
        return -1

    forum_dir = activity_directory(section_dir, name)
    seen_files: set[str] = set()
    seen_posts = set()
    discussions = []
    count = 0
    for page_number, (page_url, html) in enumerate(crawl_activity_pages(url, cookies, "forum", first_html=first_html), 1):
        post_regions = extract_content_regions(html, class_names=("forumpost", "post-content-container", "post-content"))
        page_posts = []
        for region in post_regions:
            markdown = html_to_markdown(region, page_url)
            if markdown and markdown not in seen_posts:
                seen_posts.add(markdown)
                page_posts.append(markdown)
        if page_posts:
            discussions.append(f"## Diskussion {page_number}\n\n**Quelle:** {page_url}\n\n" + "\n\n---\n\n".join(page_posts))
        count += download_all_links(html, page_url, forum_dir / "attachments", cookies, name, seen_files)

    if write_markdown(forum_dir / "forum.md", name, url, "\n\n---\n\n".join(discussions)):
        print(f"\n      💬 {forum_dir.name[:45]}/forum.md")
        count += 1
    return count
