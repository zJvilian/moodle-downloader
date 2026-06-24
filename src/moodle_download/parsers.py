"""HTML parsing and content conversion utilities."""

import re
from html.parser import HTMLParser
from urllib.parse import unquote


def html_to_markdown(html_content: str, base_url: str = "") -> str:
    """Convert HTML content to clean Markdown."""
    if not html_content:
        return ""
    
    class MoodleHTMLToMarkdown(HTMLParser):
        def __init__(self):
            super().__init__()
            self.output = []
            self.tag_stack = []
            self.list_stack = []
            self.list_counter = []
            self.in_pre = False
            self.skip_content = False
            self.href = None
            
        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            self.tag_stack.append(tag)
            
            if tag in ('script', 'style', 'nav', 'footer', 'header'):
                self.skip_content = True
                return
            
            if tag == 'h1':
                self.output.append('\n# ')
            elif tag == 'h2':
                self.output.append('\n## ')
            elif tag == 'h3':
                self.output.append('\n### ')
            elif tag == 'h4':
                self.output.append('\n#### ')
            elif tag == 'p':
                self.output.append('\n\n')
            elif tag == 'br':
                self.output.append('\n')
            elif tag in ('strong', 'b'):
                self.output.append('**')
            elif tag in ('em', 'i'):
                self.output.append('*')
            elif tag == 'a':
                self.href = attrs_dict.get('href', '')
                self.output.append('[')
            elif tag == 'img':
                src = attrs_dict.get('src', '')
                alt = attrs_dict.get('alt', 'Bild')
                if src:
                    self.output.append(f'![{alt}]({src})')
            elif tag == 'ul':
                self.list_stack.append('ul')
                self.output.append('\n')
            elif tag == 'ol':
                self.list_stack.append('ol')
                self.list_counter.append(0)
                self.output.append('\n')
            elif tag == 'li':
                indent = '  ' * (len(self.list_stack) - 1)
                if self.list_stack and self.list_stack[-1] == 'ol':
                    self.list_counter[-1] += 1
                    self.output.append(f'{indent}{self.list_counter[-1]}. ')
                else:
                    self.output.append(f'{indent}- ')
            elif tag == 'pre':
                self.in_pre = True
                self.output.append('\n```\n')
            elif tag == 'code' and not self.in_pre:
                self.output.append('`')
            elif tag == 'blockquote':
                self.output.append('\n> ')
            elif tag == 'hr':
                self.output.append('\n---\n')
            elif tag == 'tr':
                self.output.append('| ')
                
        def handle_endtag(self, tag):
            if self.tag_stack and self.tag_stack[-1] == tag:
                self.tag_stack.pop()
            
            if tag in ('script', 'style', 'nav', 'footer', 'header'):
                self.skip_content = False
                return
            
            if tag in ('h1', 'h2', 'h3', 'h4'):
                self.output.append('\n')
            elif tag in ('strong', 'b'):
                self.output.append('**')
            elif tag in ('em', 'i'):
                self.output.append('*')
            elif tag == 'a':
                if self.href:
                    self.output.append(f']({self.href})')
                else:
                    self.output.append(']')
                self.href = None
            elif tag in ('ul', 'ol'):
                if self.list_stack:
                    self.list_stack.pop()
                if tag == 'ol' and self.list_counter:
                    self.list_counter.pop()
                self.output.append('\n')
            elif tag == 'li':
                self.output.append('\n')
            elif tag == 'pre':
                self.in_pre = False
                self.output.append('\n```\n')
            elif tag == 'code' and not self.in_pre:
                self.output.append('`')
            elif tag == 'blockquote':
                self.output.append('\n')
            elif tag in ('td', 'th'):
                self.output.append(' | ')
            elif tag == 'tr':
                self.output.append('\n')
                
        def handle_data(self, data):
            if self.skip_content:
                return
            text = data.strip()
            if text:
                self.output.append(text)
        
        def get_markdown(self) -> str:
            result = ''.join(self.output)
            result = re.sub(r'\n{3,}', '\n\n', result)
            return result.strip()
    
    try:
        parser = MoodleHTMLToMarkdown()
        parser.feed(html_content)
        return parser.get_markdown()
    except Exception:
        clean = re.sub(r'<[^>]+>', ' ', html_content)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()


def check_for_locked_content(html: str) -> tuple[bool, str]:
    """Check if the page contains locked/unavailable content."""
    if not html:
        return False, ""
    
    locked_patterns = [
        (r'Nicht verf[üu]gbar', "Nicht verfügbar"),
        (r'nicht freigegeben', "Nicht freigegeben"),
        (r'geschlossen', "Geschlossen"),
        (r'Gesperrt', "Gesperrt"),
        (r'Kein Zugriff', "Kein Zugriff"),
    ]
    
    for pattern, reason in locked_patterns:
        if re.search(pattern, html, re.IGNORECASE):
            return True, reason
    
    return False, ""


def format_markdown_with_url(name: str, url: str, content: str, extra: str = "") -> str:
    """Format markdown content with a link to the Moodle page."""
    parts = [f"# {name}"]
    parts.append(f"\n[In Moodle oeffnen]({url})\n")
    if extra:
        parts.append(f"\n{extra}")
    parts.append(f"\n{content}")
    return "\n".join(parts)
