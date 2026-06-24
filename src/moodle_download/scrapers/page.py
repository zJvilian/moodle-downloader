"""Page scraper."""

import re
from ..downloader import safe_filename, scrape_page_with_requests, download_file, find_download_links_in_html
from ..parsers import html_to_markdown, check_for_locked_content, format_markdown_with_url


def scrape_page_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    """Scrape a page: save content as markdown."""
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
        r'<div[^>]*class="[^"]*page-content[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*class="[^"]*no-overflow[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*id="region-main"[^>]*>(.*?)</div>',
    ]:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            content_html = match.group(1)
            break
    
    if content_html:
        md = html_to_markdown(content_html)
        if md and len(md) > 10:
            md_file = section_dir / f"{safe}.md"
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(format_markdown_with_url(name, url, md))
            print(f"\n      📝 {safe[:50]}.md")
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
