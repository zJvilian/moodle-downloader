"""HTML parsing and content conversion utilities."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin


_BLOCK_TAGS = {
    "address", "article", "aside", "details", "div", "dl", "fieldset", "figcaption",
    "figure", "footer", "form", "header", "main", "nav", "p", "section", "summary",
}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class _MoodleHTMLToMarkdown(HTMLParser):
    """Small dependency-free converter with correct nested-list handling."""

    def __init__(self, base_url: str = ""):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.output: list[str] = []
        self.list_stack: list[dict] = []
        self.link_stack: list[str] = []
        self.skip_depth = 0
        self.pre_depth = 0

    def _newline(self, count: int = 1) -> None:
        current = "".join(self.output[-2:])
        existing = len(current) - len(current.rstrip("\n"))
        if existing < count:
            self.output.append("\n" * (count - existing))

    def _text(self, value: str) -> None:
        if not value:
            return
        if self.pre_depth:
            self.output.append(value)
            return
        leading_space = value[:1].isspace()
        trailing_space = value[-1:].isspace()
        value = re.sub(r"\s+", " ", value).strip()
        if not value:
            if self.output and not self.output[-1].endswith((" ", "\n")):
                self.output.append(" ")
            return
        if leading_space and self.output and not self.output[-1].endswith((" ", "\n")):
            self.output.append(" ")
        self.output.append(value)
        if trailing_space:
            self.output.append(" ")

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        values = dict(attrs)
        if self.skip_depth:
            if tag not in _VOID_TAGS:
                self.skip_depth += 1
            return
        if tag in {"script", "style", "template", "noscript", "nav", "footer"}:
            self.skip_depth = 1
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._newline(2)
            self.output.append(f"{'#' * int(tag[1])} ")
        elif tag in _BLOCK_TAGS:
            self._newline(2)
        elif tag == "br":
            self._newline()
        elif tag in {"strong", "b"}:
            self.output.append("**")
        elif tag in {"em", "i"}:
            self.output.append("*")
        elif tag in {"s", "del"}:
            self.output.append("~~")
        elif tag == "a":
            self.link_stack.append(urljoin(self.base_url, values.get("href", "")))
            self.output.append("[")
        elif tag == "img":
            source = urljoin(self.base_url, values.get("src", ""))
            if source:
                self.output.append(f"![{values.get('alt', 'Bild')}]({source})")
        elif tag in {"ul", "ol"}:
            self.list_stack.append({"type": tag, "counter": 0})
            self._newline()
        elif tag == "li":
            self._newline()
            indent = "  " * max(0, len(self.list_stack) - 1)
            if self.list_stack and self.list_stack[-1]["type"] == "ol":
                self.list_stack[-1]["counter"] += 1
                marker = f"{self.list_stack[-1]['counter']}. "
            else:
                marker = "- "
            self.output.append(indent + marker)
        elif tag == "pre":
            self._newline(2)
            language = ""
            classes = values.get("class", "")
            match = re.search(r"(?:language|lang)-([\w+-]+)", classes)
            if match:
                language = match.group(1)
            self.output.append(f"```{language}\n")
            self.pre_depth += 1
        elif tag == "code" and not self.pre_depth:
            self.output.append("`")
        elif tag == "blockquote":
            self._newline(2)
            self.output.append("> ")
        elif tag == "hr":
            self._newline(2)
            self.output.append("---")
            self._newline(2)
        elif tag == "tr":
            self._newline()
            self.output.append("| ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} or tag in _BLOCK_TAGS:
            self._newline(2)
        elif tag in {"strong", "b"}:
            self.output.append("**")
        elif tag in {"em", "i"}:
            self.output.append("*")
        elif tag in {"s", "del"}:
            self.output.append("~~")
        elif tag == "a":
            href = self.link_stack.pop() if self.link_stack else ""
            self.output.append(f"]({href})" if href else "]")
        elif tag in {"ul", "ol"}:
            if self.list_stack:
                self.list_stack.pop()
            self._newline()
        elif tag == "li":
            self._newline()
        elif tag == "pre":
            self.pre_depth = max(0, self.pre_depth - 1)
            self._newline()
            self.output.append("```")
            self._newline(2)
        elif tag == "code" and not self.pre_depth:
            self.output.append("`")
        elif tag == "blockquote":
            self._newline(2)
        elif tag in {"td", "th"}:
            self.output.append(" | ")
        elif tag == "tr":
            self._newline()

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self._text(data)

    def markdown(self) -> str:
        result = "".join(self.output)
        result = re.sub(r"[ \t]+\n", "\n", result)
        result = re.sub(r"\n[ \t]+\n", "\n\n", result)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()


def html_to_markdown(html_content: str, base_url: str = "") -> str:
    """Convert HTML to clean Markdown, preserving nested lists and links."""
    if not html_content:
        return ""
    try:
        parser = _MoodleHTMLToMarkdown(base_url)
        parser.feed(html_content)
        parser.close()
        return parser.markdown()
    except Exception:
        clean = re.sub(r"<[^>]+>", " ", html_content)
        return re.sub(r"\s+", " ", clean).strip()


class _RegionExtractor(HTMLParser):
    """Extract matching elements while respecting arbitrarily nested markup."""

    def __init__(self, class_names: set[str], element_ids: set[str], tag_names: set[str]):
        super().__init__(convert_charrefs=False)
        self.class_names = class_names
        self.element_ids = element_ids
        self.tag_names = tag_names
        self.depth = 0
        self.current: list[str] = []
        self.regions: list[str] = []

    def _matches(self, tag: str, attrs) -> bool:
        values = dict(attrs)
        classes = set(values.get("class", "").split())
        return tag in self.tag_names or bool(classes & self.class_names) or values.get("id", "") in self.element_ids

    def handle_starttag(self, tag: str, attrs) -> None:
        if self.depth:
            self.current.append(self.get_starttag_text())
            if tag not in _VOID_TAGS:
                self.depth += 1
        elif self._matches(tag, attrs):
            self.depth = 1

    def handle_startendtag(self, tag: str, attrs) -> None:
        if self.depth:
            self.current.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        if not self.depth:
            return
        self.depth -= 1
        if self.depth:
            self.current.append(f"</{tag}>")
        else:
            self.regions.append("".join(self.current))
            self.current = []

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.current.append(data)

    def handle_entityref(self, name: str) -> None:
        if self.depth:
            self.current.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self.depth:
            self.current.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        if self.depth:
            self.current.append(f"<!--{data}-->")


def extract_content_regions(html: str, *, class_names=(), element_ids=(), tag_names=()) -> list[str]:
    """Return inner HTML for matching regions without regex nesting bugs."""
    parser = _RegionExtractor(set(class_names), set(element_ids), set(tag_names))
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        pass
    return parser.regions


def first_content_region(html: str, *, class_names=(), element_ids=(), tag_names=()) -> str:
    regions = extract_content_regions(
        html,
        class_names=class_names,
        element_ids=element_ids,
        tag_names=tag_names,
    )
    return regions[0] if regions else ""


def check_for_locked_content(html: str) -> tuple[bool, str]:
    """Check if a page clearly reports inaccessible content."""
    if not html:
        return False, ""
    patterns = [
        (r"you cannot access this activity", "Kein Zugriff"),
        (r"activity is currently hidden", "Nicht freigegeben"),
        (r'class=["\'][^"\']*availabilityinfo[^"\']*["\'][^>]*>.*?Nicht verf[üu]gbar', "Nicht verfügbar"),
        (r'class=["\'][^"\']*(?:alert-danger|accesshide)[^"\']*["\'][^>]*>.*?(?:Kein Zugriff|not available)', "Kein Zugriff"),
    ]
    for pattern, reason in patterns:
        if re.search(pattern, html, re.IGNORECASE):
            return True, reason
    return False, ""


def format_markdown_with_url(name: str, url: str, content: str, extra: str = "") -> str:
    """Format content with stable source metadata for people and AI tools."""
    parts = [f"# {name}", f"\n**Quelle:** [In Moodle öffnen]({url})"]
    if extra:
        parts.append(f"\n{extra}")
    if content:
        parts.append(f"\n{content.strip()}")
    return "\n".join(parts).strip() + "\n"
