"""Command-line interface for Moodle Downloader."""

import sys
import argparse
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


def parse_course_url(url: str) -> tuple[str, str, str]:
    """Parse a Moodle course URL."""
    from urllib.parse import urlparse, parse_qs
    
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    course_id = query_params.get("id", [None])[0]
    base_url = f"{parsed.scheme}://{parsed.hostname}"
    
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
                         update_mode: bool = False, force: bool = False) -> dict:
    """Process a single course and return stats."""
    from .downloader import reset_download_tracker, set_download_state
    from .state import DownloadState
    
    reset_download_tracker()
    
    course_url, course_id, base_url = parse_course_url(course_url)
    
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
    
    # Initialize state for incremental updates
    if update_mode:
        state = DownloadState(course_dir)
        set_download_state(state)
        print(f"📊 Update-Modus: {len(state.state)} Dateien bereits heruntergeladen")
    
    cookies = get_cookies_from_driver(driver)
    
    stats = {'files': 0, 'descriptions': 0, 'links': 0, 'errors': 0, 'skipped': 0, 'filtered': 0}
    total_activities = sum(len(s['resources']) for s in sections)
    activity_num = 0
    
    for section_idx, section in enumerate(sections):
        section_safe = clean_filename(section["name"], is_directory=True)
        section_dir = course_dir / section_safe
        section_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n📁 [{section_idx + 1}/{len(sections)}] {section['name']}")
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
                count = process_resource(driver, resource, section_dir, cookies)
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
                    print(f" → übersprungen")
                    logger.log_skip(name, "Kein Inhalt gefunden")
                    _create_skip_note(section_dir, name, resource["url"], "Kein Inhalt gefunden")
                sys.stdout.flush()
            except Exception as e:
                stats['errors'] += 1
                print(f" → ❌ Fehler: {str(e)[:40]}")
                logger.log_error(name, str(e))
                sys.stdout.flush()
    
    # Remove duplicate files after download
    from .downloader import remove_duplicate_files
    duplicates_removed = remove_duplicate_files(course_dir)
    if duplicates_removed > 0:
        print(f"   🗑️ {duplicates_removed} Duplikate entfernt")
    
    # Save state for incremental updates
    if update_mode and 'state' in locals():
        state.save()
        print(f"   📊 Status gespeichert: {len(state.state)} Dateien")
    
    log_file = logger.write_summary(course_title, course_url)
    
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
    
    print(f"📚 Moodle-Kurs-Downloader")
    print("=" * 50)
    print(f"Kurse:    {len(args.urls)}")
    print(f"Output:   {output_dir}")
    print(f"Tiefe:    {args.depth}")
    if include_types:
        print(f"Include:  {', '.join(include_types)}")
    if exclude_types:
        print(f"Exclude:  {', '.join(exclude_types)}")
    
    creds = None
    if args.username and args.password:
        creds = {'username': args.username, 'password': args.password}
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
        if not login_to_moodle(driver, creds["username"], creds["password"]):
            print("\n❌ Login fehlgeschlagen!")
            sys.exit(1)
        
        all_stats = {'files': 0, 'descriptions': 0, 'links': 0, 'errors': 0, 'skipped': 0, 'filtered': 0}
        
        for i, url in enumerate(args.urls, 1):
            try:
                stats = process_single_course(
                    driver, url, output_dir, include_types, exclude_types, 
                    logger, i, len(args.urls),
                    update_mode=args.update, force=args.force
                )
                for key in all_stats:
                    all_stats[key] += stats.get(key, 0)
            except Exception as e:
                print(f"\n❌ Fehler bei Kurs {i}: {e}")
                logger.log_error(f"Kurs {i}", str(e))
                all_stats['errors'] += 1
        
        print(f"\n{'=' * 50}")
        print(f"✅ Alle Kurse abgeschlossen!")
        print(f"\n📊 Gesamt ({len(args.urls)} Kurse):")
        print(f"   📄 Dateien: {all_stats['files']}")
        print(f"   📝 Beschreibungen: {all_stats['descriptions']}")
        print(f"   🔗 Links: {all_stats['links']}")
        print(f"   ⏭️ Übersprungen: {all_stats['skipped']}")
        print(f"   🚫 Gefiltert: {all_stats['filtered']}")
        if all_stats['errors'] > 0:
            print(f"   ❌ Fehler: {all_stats['errors']}")
        print(f"\n   Gespeichert in: {output_dir}")
        
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("\n🔧 Schließe Browser...")
        driver.quit()
