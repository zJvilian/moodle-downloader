"""Assignment scraper."""

from ..downloader import safe_filename, scrape_page_with_requests, download_file, find_download_links_in_html
from ..parsers import html_to_markdown, check_for_locked_content, format_markdown_with_url


def scrape_assignment_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    """Scrape an assignment: description and attached files."""
    count = 0
    safe = safe_filename(name)
    activity_dir = section_dir / safe
    
    html = scrape_page_with_requests(url, cookies)
    if not html:
        return 0
    
    is_locked, reason = check_for_locked_content(html)
    if is_locked:
        print(f"\n      🔒 {reason[:50]}")
        return -1
    
    import re
    desc_match = re.search(r'<div[^>]*class="[^"]*no-overflow[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    if not desc_match:
        desc_match = re.search(r'<div[^>]*id="intro"[^>]*>(.*?)</div>', html, re.DOTALL)
    
    if desc_match:
        md = html_to_markdown(desc_match.group(1))
        if md and len(md) > 10:
            activity_dir.mkdir(parents=True, exist_ok=True)
            desc_file = activity_dir / "Beschreibung.md"
            with open(desc_file, "w", encoding="utf-8") as f:
                f.write(format_markdown_with_url(name, url, md))
            print(f"\n      📝 Beschreibung.md")
            count += 1
    
    dl_links = find_download_links_in_html(html, url)
    for dl in dl_links:
        try:
            from urllib.parse import urlparse
            url_path = urlparse(dl['url']).path
            filename = url_path.split('/')[-1]
            if not filename or '.' not in filename:
                filename = f"file_{count + 1}.pdf"
            filename = safe_filename(filename)
            
            activity_dir.mkdir(parents=True, exist_ok=True)
            filepath = activity_dir / filename
            
            if download_file(dl['url'], filepath, cookies, name):
                print(f"\n      ✅ {filename[:50]}")
                count += 1
        except Exception:
            continue
    
    return count
