"""Activity scrapers package."""

from .assignment import scrape_assignment_fast
from .resource import scrape_resource_fast
from .folder import scrape_folder_fast
from .page import scrape_page_fast
from .url import scrape_url_fast
from .forum import scrape_forum_fast
from .book import scrape_book_fast
from .quiz import scrape_quiz_fast

# Activity scraper registry
ACTIVITY_SCRAPERS = {
    'assign': scrape_assignment_fast,
    'resource': scrape_resource_fast,
    'folder': scrape_folder_fast,
    'url': scrape_url_fast,
    'page': scrape_page_fast,
    'forum': scrape_forum_fast,
    'book': scrape_book_fast,
    'quiz': scrape_quiz_fast,
}


def scrape_generic_fast(url: str, section_dir, cookies: dict, name: str, activity_type: str) -> int:
    """Generic scraper for unknown activity types."""
    from ..downloader import safe_filename, scrape_page_with_requests, download_file, find_download_links_in_html
    from ..parsers import html_to_markdown, check_for_locked_content, format_markdown_with_url
    
    count = 0
    safe = safe_filename(name)
    
    html = scrape_page_with_requests(url, cookies)
    if not html:
        return 0
    
    is_locked, reason = check_for_locked_content(html)
    if is_locked:
        print(f"\n      🔒 {reason[:50]}")
        return -1
    
    content_html = ""
    for pattern in [
        r'<div[^>]*class="[^"]*no-overflow[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*id="intro"[^>]*>(.*?)</div>',
    ]:
        import re
        match = re.search(pattern, html, re.DOTALL)
        if match:
            content_html = match.group(1)
            break
    
    if content_html:
        md = html_to_markdown(content_html)
        if md and len(md) > 10:
            md_file = section_dir / f"{safe}.md"
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(format_markdown_with_url(name, url, md, f"*Activity-Typ: {activity_type}*"))
            print(f"\n      📄 {safe[:50]}.md")
            count += 1
    
    dl_links = find_download_links_in_html(html, url)
    for dl in dl_links:
        try:
            from urllib.parse import urlparse
            url_path = urlparse(dl['url']).path
            filename = url_path.split('/')[-1]
            if filename and '.' in filename:
                filename = safe_filename(filename)
                filepath = section_dir / filename
                if download_file(dl['url'], filepath, cookies, name):
                    print(f"\n      ✅ {filename[:50]}")
                    count += 1
        except Exception:
            continue
    
    return count


def process_resource(driver, resource: dict, section_dir, cookies: dict) -> int:
    """Process a single resource using the appropriate scraper."""
    url = resource["url"]
    name = resource["name"]
    activity_type = resource["type"]
    
    scraper = ACTIVITY_SCRAPERS.get(activity_type)
    
    if scraper:
        return scraper(url, section_dir, cookies, name)
    else:
        return scrape_generic_fast(url, section_dir, cookies, name, activity_type)
