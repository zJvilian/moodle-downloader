"""Book scraper."""

import re
from urllib.parse import urljoin
from ..downloader import safe_filename, scrape_page_with_requests
from ..parsers import html_to_markdown, check_for_locked_content, format_markdown_with_url


def scrape_book_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    """Scrape a book: combine all chapters into one markdown."""
    count = 0
    safe = safe_filename(name)
    
    html = scrape_page_with_requests(url, cookies)
    if not html:
        return 0
    
    is_locked, reason = check_for_locked_content(html)
    if is_locked:
        print(f"\n      🔒 {reason[:50]}")
        return -1
    
    chapters = []
    for match in re.finditer(r'href=["\']([^"\']*chapter=[^"\']*)["\'][^>]*>([^<]+)', html):
        ch_url = match.group(1)
        ch_title = match.group(2).strip()
        if not ch_url.startswith('http'):
            ch_url = urljoin(url, ch_url)
        chapters.append((ch_url, ch_title))
    
    all_chapters = []
    for ch_url, ch_title in chapters:
        ch_html = scrape_page_with_requests(ch_url, cookies)
        if ch_html:
            for pattern in [
                r'<div[^>]*class="[^"]*book_content[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]*class="[^"]*no-overflow[^"]*"[^>]*>(.*?)</div>',
            ]:
                match = re.search(pattern, ch_html, re.DOTALL)
                if match:
                    md = html_to_markdown(match.group(1))
                    if md:
                        all_chapters.append(f"## {ch_title}\n\n{md}")
                    break
    
    if all_chapters:
        md_file = section_dir / f"{safe}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(format_markdown_with_url(name, url, "\n\n---\n\n".join(all_chapters)))
        print(f"\n      📚 {safe[:50]}.md ({len(all_chapters)} Kapitel)")
        count += 1
    
    return count
