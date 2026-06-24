"""URL scraper - always creates .url shortcuts for external links."""

import re
from urllib.parse import urljoin
from ..downloader import safe_filename, scrape_page_with_requests


def scrape_url_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    """Scrape a URL resource: always save as .url shortcut."""
    count = 0
    safe = safe_filename(name)
    
    html = scrape_page_with_requests(url, cookies)
    if not html:
        return 0
    
    # Try multiple patterns to find the external URL
    ext_url = None
    
    # Pattern 1: target="_blank"
    match = re.search(r'href=["\']([^"\']*)["\'][^>]*target=["\']_blank["\']', html)
    if match:
        ext_url = match.group(1)
    
    # Pattern 2: url_redirect
    if not ext_url:
        match = re.search(r'href=["\']([^"\']*url_redirect[^"\']*)["\']', html)
        if match:
            ext_url = match.group(1)
    
    # Pattern 3: external link class
    if not ext_url:
        match = re.search(r'class="[^"]*urlworkaround[^"]*"[^>]*href=["\']([^"\']*)["\']', html)
        if match:
            ext_url = match.group(1)
    
    # Pattern 4: any link that's not to moodle
    if not ext_url:
        matches = re.findall(r'href=["\']([^"\']*)["\']', html)
        for m in matches:
            if m.startswith('http') and 'moodle.hs-augsburg.de' not in m:
                ext_url = m
                break
    
    if ext_url:
        # Make sure it's a full URL
        if not ext_url.startswith('http'):
            ext_url = urljoin(url, ext_url)
        
        # Skip if it's still a moodle URL
        if 'moodle.hs-augsburg.de' in ext_url:
            return 0
        
        # Create .url file
        url_file = section_dir / f"{safe}.url"
        with open(url_file, "w", encoding="utf-8") as f:
            f.write(f"[InternetShortcut]\nURL={ext_url}")
        print(f"\n      🔗 {safe[:50]}.url")
        count += 1
    
    return count


def extract_links_from_html(html: str, base_url: str) -> list[dict]:
    """Extract all external links from HTML content."""
    links = []
    
    # Find all href attributes
    for match in re.finditer(r'href=["\']([^"\']*)["\']', html):
        href = match.group(1)
        
        # Make absolute URL
        if not href.startswith('http'):
            href = urljoin(base_url, href)
        
        # Skip moodle internal links
        if 'moodle.hs-augsburg.de' in href:
            continue
        
        # Skip anchors, javascript, mailto
        if href.startswith(('#', 'javascript:', 'mailto:')):
            continue
        
        links.append({
            'url': href,
            'type': 'external'
        })
    
    return links
