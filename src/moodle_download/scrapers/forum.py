"""Forum scraper."""

import re
from urllib.parse import urljoin
from ..downloader import safe_filename, scrape_page_with_requests
from ..parsers import html_to_markdown, check_for_locked_content, format_markdown_with_url


def scrape_forum_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    """Scrape a forum: save all posts as markdown."""
    count = 0
    safe = safe_filename(name)
    forum_dir = section_dir / safe
    
    html = scrape_page_with_requests(url, cookies)
    if not html:
        return 0
    
    is_locked, reason = check_for_locked_content(html)
    if is_locked:
        print(f"\n      🔒 {reason[:50]}")
        return -1
    
    discussions = []
    for match in re.finditer(r'href=["\']([^"\']*discuss[^"\']*)["\'][^>]*>([^<]+)', html):
        d_url = match.group(1)
        d_title = match.group(2).strip()
        if not d_url.startswith('http'):
            d_url = urljoin(url, d_url)
        discussions.append((d_url, d_title))
    
    for d_url, d_title in discussions[:20]:
        d_html = scrape_page_with_requests(d_url, cookies)
        if d_html:
            posts = []
            for post_match in re.finditer(r'<div[^>]*class="[^"]*forumpost[^"]*"[^>]*>(.*?)</div>', d_html, re.DOTALL):
                post_html = post_match.group(1)
                author_match = re.search(r'<div[^>]*class="[^"]*author[^"]*"[^>]*>(.*?)</div>', post_html)
                content_match = re.search(r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>', post_html)
                
                author = author_match.group(1).strip() if author_match else "Unbekannt"
                content = content_match.group(1) if content_match else post_html
                
                md = html_to_markdown(content)
                if md:
                    posts.append(f"### {author}\n\n{md}")
            
            if posts:
                forum_dir.mkdir(parents=True, exist_ok=True)
                d_safe = safe_filename(d_title[:50])
                md_file = forum_dir / f"{d_safe}.md"
                with open(md_file, "w", encoding="utf-8") as f:
                    f.write(format_markdown_with_url(d_title, d_url, "\n\n---\n\n".join(posts)))
                print(f"\n      💬 {safe[:30]}/{d_safe[:30]}.md")
                count += 1
    
    return count
