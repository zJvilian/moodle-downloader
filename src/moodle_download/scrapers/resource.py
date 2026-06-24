"""Resource scraper."""

from ..downloader import safe_filename, scrape_page_with_requests, download_file, find_download_links_in_html
from ..parsers import check_for_locked_content


def scrape_resource_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    """Scrape a file resource."""
    count = 0
    safe = safe_filename(name)
    
    html = scrape_page_with_requests(url, cookies)
    if not html:
        return 0
    
    is_locked, reason = check_for_locked_content(html)
    if is_locked:
        print(f"\n      🔒 {reason[:50]}")
        return -1
    
    dl_links = find_download_links_in_html(html, url)
    for dl in dl_links:
        try:
            from urllib.parse import urlparse
            url_path = urlparse(dl['url']).path
            filename = url_path.split('/')[-1]
            if not filename or '.' not in filename:
                filename = safe
            filename = safe_filename(filename)
            
            filepath = section_dir / filename
            if download_file(dl['url'], filepath, cookies, name):
                print(f"\n      ✅ {filename[:50]}")
                count += 1
            break
        except Exception:
            continue
    
    return count
