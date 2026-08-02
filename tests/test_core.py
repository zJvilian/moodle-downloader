"""Regression tests for structure, discovery, and AI-ready exports."""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


# The bundled verification runtime intentionally has no third-party packages.
# A minimal import stub lets pure discovery helpers be tested without networking.
if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    requests_stub.RequestException = RequestException
    requests_stub.get = lambda *args, **kwargs: None
    requests_stub.head = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_stub


from moodle_download.ai_export import build_ai_export
from moodle_download import cli
from moodle_download import downloader
from moodle_download.cli import _section_folder_name
from moodle_download.downloader import clean_filename, find_download_links_in_html
from moodle_download.state import DownloadState
from moodle_download.parsers import extract_content_regions, html_to_markdown
from moodle_download.scrapers import ACTIVITY_SCRAPERS, process_resource
from moodle_download.scrapers import external as external_scraper
from moodle_download.scrapers import url as url_scraper


class MarkdownTests(unittest.TestCase):
    def test_nested_lists_keep_hierarchy_and_word_spacing(self):
        source = """
        <p>Hello <strong>nested</strong> world</p>
        <ol><li>First<ul><li>Child <em>item</em></li></ul></li><li>Second</li></ol>
        """
        markdown = html_to_markdown(source)
        self.assertIn("Hello **nested** world", markdown)
        self.assertIn("1. First", markdown)
        self.assertIn("  - Child *item*", markdown)
        self.assertIn("2. Second", markdown)

    def test_region_extraction_balances_nested_divs(self):
        source = '<div class="no-overflow">A<div><span>B</span></div>C</div><p>outside</p>'
        regions = extract_content_regions(source, class_names=("no-overflow",))
        self.assertEqual(1, len(regions))
        self.assertEqual("A<div><span>B</span></div>C", regions[0])

    def test_region_extraction_can_select_semantic_tags(self):
        source = "<nav>ignore</nav><main><article><p>Keep this</p></article></main>"
        regions = extract_content_regions(source, tag_names=("main",))
        self.assertEqual(["<article><p>Keep this</p></article>"], regions)


class DiscoveryTests(unittest.TestCase):
    def test_discovers_links_images_folder_archives_and_deduplicates(self):
        source = """
        <a href="/pluginfile.php/1/file.pdf?forcedownload=1">PDF</a>
        <img src="/pluginfile.php/1/image.png">
        <a href="/pluginfile.php/1/file.pdf?forcedownload=1">duplicate</a>
        <a href="/mod/folder/download_folder.php?id=5">folder</a>
        <a href="https://example.test/course/notes.docx">document</a>
        """
        links = find_download_links_in_html(source, "https://example.test/course/view.php?id=1")
        self.assertEqual(4, len(links))
        self.assertTrue(any(item["embedded"] for item in links))
        self.assertEqual("file.pdf", links[0]["name"])

    def test_windows_reserved_names_are_safe(self):
        self.assertEqual("_CON.txt", clean_filename("CON.txt"))

    def test_download_is_atomic_recorded_and_skipped_when_unchanged(self):
        class Response:
            ok = True
            headers = {
                "Content-Type": "application/pdf",
                "Content-Disposition": 'attachment; filename="Lecture 1.pdf"',
                "Content-Length": "7",
            }

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield b"content"

        with tempfile.TemporaryDirectory() as temporary:
            course = Path(temporary)
            state = DownloadState(course)
            original_get, original_head = downloader.requests.get, downloader.requests.head
            try:
                downloader.requests.get = lambda *args, **kwargs: Response()
                downloader.requests.head = lambda *args, **kwargs: Response()
                downloader.set_download_options(state=state, update=False)
                url = "https://moodle.test/pluginfile.php/1/Lecture%201.pdf"
                self.assertTrue(downloader.download_file(url, course / "download", {}, "Lecture"))
                self.assertEqual(b"content", (course / "Lecture_1.pdf").read_bytes())
                self.assertEqual("Lecture_1.pdf", state.get_local_path(url))

                downloader.set_download_options(state=state, update=True)
                downloader.requests.get = lambda *args, **kwargs: self.fail("unchanged file fetched again")
                self.assertTrue(downloader.download_file(url, course / "download", {}, "Lecture"))
            finally:
                downloader.requests.get = original_get
                downloader.requests.head = original_head


class AIExportTests(unittest.TestCase):
    def test_export_contains_structure_manifest_and_ordered_chunks(self):
        with tempfile.TemporaryDirectory() as temporary:
            course = Path(temporary) / "Course"
            nested = course / "Week 1" / "Topic A"
            nested.mkdir(parents=True)
            (nested / "notes.md").write_text("# Notes\n\nStructured content", encoding="utf-8")
            (nested / "slides.pdf").write_bytes(b"%PDF-test")
            sections = [{
                "id": "s1",
                "name": "Topic A",
                "path": ["Week 1", "Topic A"],
                "level": 1,
                "resources": [{"name": "Notes", "type": "page", "url": "https://moodle.test/mod/page/view.php?id=1"}],
            }]

            metadata = build_ai_export(course, "Course", "https://moodle.test/course/view.php?id=1", sections)
            ai_dir = course / "_AI_READY"
            self.assertEqual(2, metadata["file_count"])
            self.assertEqual(1, metadata["readable_source_count"])
            self.assertTrue((ai_dir / "manifest.jsonl").exists())
            self.assertTrue((ai_dir / "course_structure.json").exists())
            chunk = (ai_dir / "chunks" / "chunk_001.md").read_text(encoding="utf-8")
            self.assertIn('path="Week 1/Topic A/notes.md"', chunk)
            manifest = [json.loads(line) for line in (ai_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["Week 1", "Topic A"], manifest[0]["hierarchy"])


class ExternalLinkTests(unittest.TestCase):
    def test_youtube_detection_is_host_specific(self):
        self.assertTrue(external_scraper.is_youtube_url("https://youtu.be/abc123"))
        self.assertTrue(external_scraper.is_youtube_url("https://music.youtube.com/watch?v=abc123"))
        self.assertFalse(external_scraper.is_youtube_url("https://example.com/youtube.com/video"))
        self.assertTrue(external_scraper.is_youtube_video_url("https://www.youtube.com/watch?v=abc123&list=course"))
        self.assertFalse(external_scraper.is_youtube_video_url("https://www.youtube.com/playlist?list=course"))
        self.assertFalse(external_scraper.is_youtube_video_url("https://www.youtube.com/@channel"))

    def test_external_article_is_archived_as_markdown(self):
        html = b"""
        <html><head><title>Useful Article</title><meta name="description" content="Course reference"></head>
        <body><nav>Ignore navigation</nav><main><h1>Useful Article</h1>
        <p>This is a sufficiently long course reference with detailed explanations for students.</p>
        <a href="/details">Read details</a></main></body></html>
        """

        class Response:
            headers = {"Content-Type": "text/html; charset=utf-8", "Content-Length": str(len(html))}
            url = "https://public.test/article"
            encoding = "utf-8"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield html

        original_get = external_scraper.requests.get
        original_safe = external_scraper._safe_public_url
        try:
            external_scraper.requests.get = lambda *args, **kwargs: Response()
            external_scraper._safe_public_url = lambda *args, **kwargs: True
            with tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / "Webseite.md"
                self.assertTrue(external_scraper.scrape_external_page("https://public.test/article", target, "Reference"))
                markdown = target.read_text(encoding="utf-8")
                self.assertIn("# Useful Article", markdown)
                self.assertIn("Course reference", markdown)
                self.assertIn("https://public.test/details", markdown)
                self.assertNotIn("Ignore navigation", markdown)
        finally:
            external_scraper.requests.get = original_get
            external_scraper._safe_public_url = original_safe

    def test_youtube_link_is_always_saved_and_video_is_opt_in(self):
        moodle_html = '<a href="https://www.youtube.com/watch?v=abc123">Video</a>'
        original_fetch = url_scraper.scrape_page_with_requests
        original_download = url_scraper.download_youtube_video
        original_scrape = url_scraper.scrape_external_page
        calls = []
        try:
            url_scraper.scrape_page_with_requests = lambda *args: moodle_html
            url_scraper.download_youtube_video = lambda target, destination: calls.append(target) or True
            url_scraper.scrape_external_page = lambda *args: self.fail("YouTube must not use webpage scraper")
            with tempfile.TemporaryDirectory() as temporary:
                section = Path(temporary)
                count = url_scraper.scrape_url_fast(
                    "https://moodle.test/mod/url/view.php?id=1", section, {}, "Lecture Video"
                )
                self.assertEqual(1, count)
                self.assertEqual([], calls)
                self.assertEqual(1, len(list(section.rglob("*.url"))))

                count = url_scraper.scrape_url_fast(
                    "https://moodle.test/mod/url/view.php?id=1",
                    section,
                    {},
                    "Lecture Video",
                    download_youtube=True,
                )
                self.assertEqual(2, count)
                self.assertEqual(["https://www.youtube.com/watch?v=abc123"], calls)
        finally:
            url_scraper.scrape_page_with_requests = original_fetch
            url_scraper.download_youtube_video = original_download
            url_scraper.scrape_external_page = original_scrape

    def test_url_activity_prefers_configured_content_link(self):
        source = """
        <header><a href="https://support.example/header">Support</a></header>
        <div class="urlworkaround"><a href="https://reference.example/article">Open resource</a></div>
        """
        target = url_scraper.find_external_target(source, "https://moodle.test/mod/url/view.php?id=1")
        self.assertEqual("https://reference.example/article", target)

    def test_private_network_pages_are_not_scraped(self):
        self.assertFalse(external_scraper._safe_public_url("http://127.0.0.1/private"))
        self.assertFalse(external_scraper._safe_public_url("http://localhost/private"))

    def test_dispatch_forwards_link_preferences(self):
        captured = {}
        original = ACTIVITY_SCRAPERS["url"]
        try:
            def fake_scraper(url, section_dir, cookies, name, **kwargs):
                captured.update(kwargs)
                return 1

            ACTIVITY_SCRAPERS["url"] = fake_scraper
            with tempfile.TemporaryDirectory() as temporary:
                count = process_resource(
                    object(),
                    {"url": "https://moodle.test/mod/url/view.php?id=1", "name": "Link", "type": "url"},
                    Path(temporary),
                    {},
                    download_youtube=True,
                    scrape_external=False,
                )
            self.assertEqual(1, count)
            self.assertEqual({"download_youtube": True, "scrape_external": False}, captured)
        finally:
            ACTIVITY_SCRAPERS["url"] = original


class CourseStructureTests(unittest.TestCase):
    def test_section_folder_combines_position_and_visible_title(self):
        self.assertEqual("Abschnitt_5_Wahrscheinlichkeitsrechnung", _section_folder_name(5, "Wahrscheinlichkeitsrechnung"))
        self.assertEqual("Abschnitt_5_Wahrscheinlichkeitsrechnung", _section_folder_name(5, "Abschnitt 5: Wahrscheinlichkeitsrechnung"))
        self.assertEqual("Abschnitt_5", _section_folder_name(5, "Abschnitt 5"))

    def test_nested_sections_are_written_as_nested_directories(self):
        sections = [
            {"id": "parent", "name": "Week 1", "path": ["Week 1"], "level": 0,
             "resources": [{"name": "Overview", "type": "page", "url": "https://moodle.test/mod/page/view.php?id=2"}]},
            {"id": "child", "name": "Topic A", "path": ["Week 1", "Topic A"], "level": 1,
             "resources": [{"name": "Lesson", "type": "page", "url": "https://moodle.test/mod/page/view.php?id=3"}]},
        ]

        class Logger:
            def log_download(self, *args):
                pass

            def log_skip(self, *args):
                pass

            def log_error(self, *args):
                pass

            def write_summary(self, *args):
                return None

        originals = cli.get_course_content, cli.get_cookies_from_driver, cli.process_resource
        try:
            cli.get_course_content = lambda driver, url: (sections, "Course")
            cli.get_cookies_from_driver = lambda driver: {}

            def fake_process(driver, resource, section_dir, cookies, **kwargs):
                (section_dir / f"{resource['name']}.md").write_text("content", encoding="utf-8")
                return 1

            cli.process_resource = fake_process
            with tempfile.TemporaryDirectory() as temporary:
                cli.process_single_course(
                    object(),
                    "https://moodle.test/course/view.php?id=1",
                    Path(temporary),
                    None,
                    None,
                    Logger(),
                )
                course = Path(temporary) / "Course"
                self.assertTrue((course / "Abschnitt_1_Week_1" / "Overview.md").exists())
                self.assertTrue((course / "Abschnitt_1_Week_1" / "Abschnitt_2_Topic_A" / "Lesson.md").exists())
        finally:
            cli.get_course_content, cli.get_cookies_from_driver, cli.process_resource = originals


if __name__ == "__main__":
    unittest.main()
