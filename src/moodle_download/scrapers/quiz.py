"""Quiz scraper."""

import re
from ..downloader import safe_filename, scrape_page_with_requests
from ..parsers import html_to_markdown, check_for_locked_content


def scrape_quiz_fast(url: str, section_dir, cookies: dict, name: str) -> int:
    """Scrape a quiz: description and info."""
    count = 0
    safe = safe_filename(name)
    
    html = scrape_page_with_requests(url, cookies)
    if not html:
        return 0
    
    is_locked, reason = check_for_locked_content(html)
    if is_locked:
        print(f"\n      🔒 {reason[:50]}")
        return -1
    
    desc_content = ""
    for pattern in [
        r'<div[^>]*class="[^"]*quiz-intro[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*id="intro"[^>]*>(.*?)</div>',
        r'<div[^>]*class="[^"]*no-overflow[^"]*"[^>]*>(.*?)</div>',
    ]:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            desc_content = html_to_markdown(match.group(1))
            if desc_content:
                break
    
    quiz_info = ""
    info_parts = []
    for label, pattern in [('Zeitlimit', r'Zeitlimit.*?<.*?>([^<]+)'), ('Versuche', r'Versuche.*?<.*?>([^<]+)')]:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            info_parts.append(f"- **{label}:** {match.group(1).strip()}")
    if info_parts:
        quiz_info = "## Info\n\n" + "\n".join(info_parts)
    
    content_parts = [f"# {name}", f"\n[Quiz in Moodle oeffnen]({url})\n"]
    if desc_content:
        content_parts.append(f"\n## Beschreibung\n\n{desc_content}")
    if quiz_info:
        content_parts.append(f"\n{quiz_info}")
    
    if desc_content or quiz_info:
        md_file = section_dir / f"{safe}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write("\n".join(content_parts))
        print(f"\n      ❓ {safe[:50]}.md")
        count += 1
    
    return count
