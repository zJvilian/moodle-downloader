"""Command-line interface for Moodle Downloader."""

import argparse
import os
import re
import sys
from pathlib import Path

# Fix Windows console encoding for Unicode
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from .browser import setup_browser_driver, login_to_moodle, get_cookies_from_driver, get_course_content
from .downloader import clean_filename
from .logger import setup_logging
from .scrapers import process_resource
from . import DOWNLOADS_DIR


_GENERIC_SECTION_NAME = re.compile(r"^(?:abschnitt|section)(?:\s+\d+)?$", re.IGNORECASE)
_SECTION_NAME_PREFIX = re.compile(
    r"^(?:abschnitt|section)\s*\d*\s*(?:[-:._]\s*)?(.*)$",
    re.IGNORECASE,
)


def _is_generic_section_name(name: str) -> bool:
    return bool(_GENERIC_SECTION_NAME.fullmatch(" ".join(str(name or "").split())))


def _section_folder_name(position: int | str, title: str) -> str:
    """Combine a stable section position with its visible Moodle title."""
    number = re.sub(r"[^0-9A-Za-z-]+", "", str(position)) or "1"
    visible_title = " ".join(str(title or "").split())
    match = _SECTION_NAME_PREFIX.match(visible_title)
    if match:
        visible_title = match.group(1).strip()
    prefix = f"Abschnitt_{number}"
    if not visible_title or _is_generic_section_name(visible_title):
        return prefix
    suffix = clean_filename(visible_title, max_length=44, is_directory=True)
    return clean_filename(f"{prefix}_{suffix}", max_length=58, is_directory=True)


def _section_directory(
    course_dir: Path,
    raw_path: list[str],
    path_ids: list[str],
    cache: dict[tuple[str, ...], Path],
) -> Path:
    """Build stable nested paths; children always reuse their parent's path."""
    current = course_dir
    prefix: list[str] = []
    for index, part in enumerate(raw_path):
        prefix.append(str(path_ids[index] if index < len(path_ids) else part))
        key = tuple(prefix)
        if key in cache:
            current = cache[key]
            continue
        available = max(12, min(52, 172 - len(str(current)) - 1))
        current /= clean_filename(part, max_length=available, is_directory=True)
        cache[key] = current
    return current


def parse_course_url(url: str) -> tuple[str, str, str]:
    """Parse a Moodle course URL."""
    from urllib.parse import urlparse, parse_qs
    
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    course_id = query_params.get("id", [None])[0]
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    if not course_id:
        print("❌ Keine Kurs-ID in der URL gefunden")
        sys.exit(1)
    
    return url, course_id, base_url


def should_download(activity_type: str, include_types: list, exclude_types: list) -> bool:
    """Check if an activity type should be downloaded."""
    type_categories = {
        'forum': ['forum', 'announcement'],
        'quiz': ['quiz'],
        'assign': ['file', 'assignment'],
        'resource': ['file', 'resource'],
        'folder': ['file', 'folder'],
        'page': ['description', 'page'],
        'book': ['book'],
        'url': ['link', 'url'],
        'choice': ['choice'],
        'label': ['description', 'label'],
        'lesson': ['description', 'lesson'],
        'feedback': ['description', 'feedback'],
        'glossary': ['description', 'glossary'],
        'wiki': ['description', 'wiki'],
        'workshop': ['description', 'file', 'workshop'],
        'database': ['description', 'file', 'database'],
        'data': ['description', 'file', 'database'],
        'h5pactivity': ['description', 'file', 'h5p'],
        'scorm': ['file', 'scorm'],
        'lti': ['link', 'lti'],
    }
    
    categories = type_categories.get(activity_type, [activity_type])
    
    if include_types:
        return any(cat in include_types for cat in categories)
    if exclude_types:
        return not any(cat in exclude_types for cat in categories)
    return True


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Moodle Kurs-Downloader',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  %(prog)s https://moodle.hs-augsburg.de/course/view.php?id=69420
  %(prog)s url1 url2 url3
  %(prog)s --url URL1 --url URL2 --include file,description
        """
    )
    
    parser.add_argument('urls', nargs='*', help='Moodle Kurs-URL(s)')
    parser.add_argument('--url', '-u', action='append', help='Moodle Kurs-URL')
    parser.add_argument('--output', '-o', help='Download-Verzeichnis')
    parser.add_argument('--username', help='Moodle Benutzername')
    parser.add_argument('--password', help='Moodle Passwort')
    parser.add_argument('--include', '-i', help='Nur diese Typen (kommagetrennt)')
    parser.add_argument('--exclude', '-e', help='Diese Typen ausschliessen')
    parser.add_argument('--depth', '-d', choices=['shallow', 'deep'], default='deep')
    parser.add_argument('--update', action='store_true', help='Nur neue/geaenderte Dateien herunterladen')
    parser.add_argument('--force', action='store_true', help='Alles neu herunterladen')
    parser.add_argument(
        '--optimize-ai', '--ai', dest='optimize_ai', action='store_true',
        help='Zusätzlich einen strukturierten AI-Ready-Export erzeugen',
    )
    parser.add_argument(
        '--download-youtube', action='store_true',
        help='YouTube-Videos herunterladen (Links werden immer gespeichert)',
    )
    parser.add_argument(
        '--scrape-external', action=argparse.BooleanOptionalAction, default=True,
        help='Geeignete externe Webseiten zusätzlich als Markdown archivieren',
    )
    
    args = parser.parse_args()
    
    all_urls = []
    if args.urls:
        all_urls.extend(args.urls)
    if args.url:
        all_urls.extend(args.url)
    
    if not all_urls:
        parser.error('Bitte gib mindestens eine Moodle-Kurs-URL an')
    
    args.urls = all_urls
    return args


def _create_skip_note(section_dir: Path, name: str, url: str, reason: str):
    """Create a note file for skipped activities."""
    safe = clean_filename(name, max_length=50, is_directory=False)
    note_file = section_dir / f"{safe}_SKIP.md"
    
    with open(note_file, "w", encoding="utf-8") as f:
        f.write(f"# {name}\n\n")
        f.write(f"⚠️ **Übersprungen**: {reason}\n\n")
        f.write(f"🔗 [In Moodle öffnen]({url})\n")


def process_single_course(driver, course_url: str, output_dir: Path, 
                         include_types: list, exclude_types: list, 
                         logger, course_num: int = 1, total_courses: int = 1,
                         update_mode: bool = False, force: bool = False,
                         depth: str = 'deep', optimize_ai: bool = False,
                         download_youtube: bool = False,
                         scrape_external: bool = True) -> dict:
    """Process a single course and return stats."""
    from .downloader import reset_download_tracker, set_download_options
    from .state import DownloadState
    
    reset_download_tracker()
    
    course_url, _course_id, _base_url = parse_course_url(course_url)
    
    prefix = f"[{course_num}/{total_courses}] " if total_courses > 1 else ""
    print(f"\n{prefix}📚 Kurs: {course_url}")
    print("=" * 50)
    
    sections, course_title = get_course_content(driver, course_url)
    
    if not sections:
        print("\n⚠️ Keine Kursinhalte gefunden!")
        logger.log_error("Kursinhalt", "Keine Sections gefunden")
        return {'errors': 1, 'files': 0, 'descriptions': 0, 'links': 0, 'skipped': 0, 'filtered': 0}
    
    safe_name = clean_filename(course_title, is_directory=True)
    course_dir = output_dir / safe_name
    course_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📂 Download-Verzeichnis: {course_dir}")
    print("=" * 50)
    
    # Always keep state so every URL retains a stable local path on reruns.
    state = DownloadState(course_dir)
    set_download_options(state=state, update=update_mode, force=force)
    if update_mode:
        print(f"📊 Update-Modus: {len(state.state)} Dateien bereits heruntergeladen")
    if force:
        print("🔁 Force-Modus: Alle erreichbaren Dateien werden neu geladen")
    
    cookies = get_cookies_from_driver(driver)
    
    stats = {'files': 0, 'descriptions': 0, 'links': 0, 'errors': 0, 'skipped': 0, 'filtered': 0}
    total_activities = sum(len(s['resources']) for s in sections)
    activity_num = 0
    
    used_section_dirs = {}
    section_path_cache = {(): course_dir}
    for section_idx, section in enumerate(sections):
        raw_path = section.get("path") or [section["name"]]
        path_positions = section.get("path_positions") or []
        folder_path = [
            _section_folder_name(
                path_positions[depth] if depth < len(path_positions) else (section_idx + 1 if depth == len(raw_path) - 1 else depth + 1),
                part,
            )
            for depth, part in enumerate(raw_path)
        ]
        path_ids = section.get("path_ids") or raw_path
        section_dir = _section_directory(course_dir, folder_path, path_ids, section_path_cache)
        if section_dir == course_dir:
            section_dir = course_dir / f"Abschnitt_{section_idx + 1}"
        directory_key = str(section_dir).casefold()
        section_id = str(section.get("id", section_idx))
        if directory_key in used_section_dirs and used_section_dirs[directory_key] != section_id:
            section_dir = section_dir.with_name(f"{section_dir.name}_{section_idx + 1}")
            directory_key = str(section_dir).casefold()
            section_path_cache[tuple(str(item) for item in path_ids)] = section_dir
        used_section_dirs[directory_key] = section_id
        section_dir.mkdir(parents=True, exist_ok=True)
        
        indent = "  " * int(section.get("level", 0))
        print(f"\n{indent}📁 [{section_idx + 1}/{len(sections)}] {' / '.join(raw_path)}")
        sys.stdout.flush()
        
        for resource in section["resources"]:
            activity_num += 1
            name = resource["name"]
            act_type = resource["type"]
            
            if not should_download(act_type, include_types, exclude_types):
                stats['filtered'] += 1
                logger.log_skip(name, f"Typ '{act_type}' nicht in Filter")
                continue
            
            print(f"   [{activity_num}/{total_activities}] {act_type}: {name[:40]}", end="")
            sys.stdout.flush()
            
            try:
                count = process_resource(
                    driver,
                    resource,
                    section_dir,
                    cookies,
                    depth=depth,
                    download_youtube=download_youtube,
                    scrape_external=scrape_external,
                )
                if count > 0:
                    if act_type == 'url':
                        stats['links'] += count
                    elif act_type in ('page', 'forum', 'book', 'quiz'):
                        stats['descriptions'] += count
                    else:
                        stats['files'] += count
                    print(f" → {count} Datei(en)")
                    logger.log_download(name, resource["url"])
                elif count == -1:
                    stats['skipped'] += 1
                    logger.log_skip(name, "Inhalt gesperrt")
                    _create_skip_note(section_dir, name, resource["url"], "Inhalt gesperrt")
                else:
                    stats['skipped'] += 1
                    print(" → übersprungen")
                    logger.log_skip(name, "Kein Inhalt gefunden")
                    _create_skip_note(section_dir, name, resource["url"], "Kein Inhalt gefunden")
                sys.stdout.flush()
            except Exception as e:
                stats['errors'] += 1
                print(f" → ❌ Fehler: {str(e)[:40]}")
                logger.log_error(name, str(e))
                sys.stdout.flush()
    
    state.save()
    print(f"   📊 Status gespeichert: {len(state.state)} Dateien")

    if optimize_ai:
        from .ai_export import build_ai_export
        ai_stats = build_ai_export(course_dir, course_title, course_url, sections)
        print(
            f"   🧠 AI-Ready: {ai_stats['file_count']} Dateien indexiert, "
            f"{ai_stats['chunk_count']} Kontext-Paket(e)"
        )
    
    logger.write_summary(course_title, course_url)
    
    print(f"\n{'=' * 50}")
    print(f"✅ Kurs abgeschlossen: {course_title}")
    print(f"   📄 Dateien: {stats['files']}, 📝 Beschreibungen: {stats['descriptions']}, 🔗 Links: {stats['links']}")
    print(f"   ⏭️ Übersprungen: {stats['skipped']}, 🚫 Gefiltert: {stats['filtered']}, ❌ Fehler: {stats['errors']}")
    print(f"   📂 Gespeichert in: {course_dir}")
    
    return stats


def main():
    """Main entry point."""
    args = parse_args()
    
    output_dir = Path(args.output) if args.output else DOWNLOADS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    
    include_types = [t.strip().lower() for t in args.include.split(',')] if args.include else None
    exclude_types = [t.strip().lower() for t in args.exclude.split(',')] if args.exclude else None
    
    logger = setup_logging(output_dir)
    
    print("📚 Moodle-Kurs-Downloader")
    print("=" * 50)
    print(f"Kurse:    {len(args.urls)}")
    print(f"Output:   {output_dir}")
    print(f"Tiefe:    {args.depth}")
    if include_types:
        print(f"Include:  {', '.join(include_types)}")
    if exclude_types:
        print(f"Exclude:  {', '.join(exclude_types)}")
    if args.optimize_ai:
        print("AI-Ready: aktiviert")
    print(f"YouTube:  {'Video + Link' if args.download_youtube else 'nur Link'}")
    print(f"Webseiten: {'Markdown + Link' if args.scrape_external else 'nur Link'}")
    
    creds = None
    if args.username and args.password:
        creds = {'username': args.username, 'password': args.password}
    elif os.environ.get("MOODLE_DOWNLOAD_USERNAME") and os.environ.get("MOODLE_DOWNLOAD_PASSWORD"):
        creds = {
            'username': os.environ["MOODLE_DOWNLOAD_USERNAME"],
            'password': os.environ["MOODLE_DOWNLOAD_PASSWORD"],
        }
    else:
        from . import CREDENTIALS_FILE
        if CREDENTIALS_FILE.exists():
            import json
            try:
                with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                    creds = json.load(f)
            except Exception:
                pass
    
    if not creds or not creds.get("username") or not creds.get("password"):
        print("\n❌ credentials.json nicht gefunden!")
        print('   {"username": "user", "password": "pass"}')
        sys.exit(1)
    
    print(f"Login:    {creds['username']}")
    
    driver = setup_browser_driver()
    
    try:
        if not login_to_moodle(driver, creds["username"], creds["password"], args.urls[0]):
            print("\n❌ Login fehlgeschlagen!")
            sys.exit(1)
        from urllib.parse import urlparse
        active_host = urlparse(args.urls[0]).netloc.casefold()
        
        all_stats = {'files': 0, 'descriptions': 0, 'links': 0, 'errors': 0, 'skipped': 0, 'filtered': 0}
        
        for i, url in enumerate(args.urls, 1):
            try:
                course_host = urlparse(url).netloc.casefold()
                if course_host != active_host:
                    if not login_to_moodle(driver, creds["username"], creds["password"], url):
                        raise RuntimeError(f"Login bei {course_host} fehlgeschlagen")
                    active_host = course_host
                stats = process_single_course(
                    driver, url, output_dir, include_types, exclude_types, 
                    logger, i, len(args.urls),
                    update_mode=args.update, force=args.force,
                    depth=args.depth, optimize_ai=args.optimize_ai,
                    download_youtube=args.download_youtube,
                    scrape_external=args.scrape_external,
                )
                for key in all_stats:
                    all_stats[key] += stats.get(key, 0)
            except Exception as e:
                print(f"\n❌ Fehler bei Kurs {i}: {e}")
                logger.log_error(f"Kurs {i}", str(e))
                all_stats['errors'] += 1
        
        print(f"\n{'=' * 50}")
        print("✅ Alle Kurse abgeschlossen!")
        print(f"\n📊 Gesamt ({len(args.urls)} Kurse):")
        print(f"   📄 Dateien: {all_stats['files']}")
        print(f"   📝 Beschreibungen: {all_stats['descriptions']}")
        print(f"   🔗 Links: {all_stats['links']}")
        print(f"   ⏭️ Übersprungen: {all_stats['skipped']}")
        print(f"   🚫 Gefiltert: {all_stats['filtered']}")
        if all_stats['errors'] > 0:
            print(f"   ❌ Fehler: {all_stats['errors']}")
        print(f"\n   Gespeichert in: {output_dir}")
        if all_stats['errors'] > 0:
            sys.exit(2)
        
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("\n🔧 Schließe Browser...")
        driver.quit()
