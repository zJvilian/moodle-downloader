"""Folder scraper."""

from ..downloader import safe_filename, scrape_page_with_requests, download_file, find_download_links_in_html
from ..parsers import check_for_locked_content


def scrape_folder_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    """Scrape a folder: download all contained files."""
    count = 0
    safe = safe_filename(name)
    folder_dir = section_dir / safe
    
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
                filename = f"file_{count + 1}"
            filename = safe_filename(filename)
            
            folder_dir.mkdir(parents=True, exist_ok=True)
            filepath = folder_dir / filename
            if download_file(dl['url'], filepath, cookies, name):
                print(f"\n      ✅ {safe}/{filename[:30]}")
                count += 1
        except Exception:
            continue
    
    return count
