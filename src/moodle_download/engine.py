"""Core course download engine for Moodle Downloader."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from . import DOWNLOADS_DIR, ENV_FILE
from .browser import get_cookies_from_driver, get_course_content, login_to_moodle, setup_browser_driver
from .downloader import clean_filename, reset_download_tracker, set_download_options
from .logger import setup_logging
from .scrapers import process_resource
from .state import DownloadState


_GENERIC_SECTION_NAME = re.compile(r"^(?:abschnitt|section)(?:\s+\d+)?$", re.IGNORECASE)
_SECTION_NAME_PREFIX = re.compile(
    r"^(?:abschnitt|section)\s*\d*\s*(?:[-:._]\s*)?(.*)$",
    re.IGNORECASE,
)


class DownloadCancelled(Exception):
    """Raised when a running download job is cancelled."""


@dataclass
class DownloadConfig:
    """Configuration for a course download job."""

    urls: list[str]
    output_dir: Path = field(default_factory=lambda: DOWNLOADS_DIR)
    username: str = ""
    password: str = ""
    use_saved_credentials: bool = False
    include_types: list[str] | None = None
    exclude_types: list[str] | None = None
    depth: str = "deep"
    update_mode: bool = False
    force: bool = False
    optimize_ai: bool = False
    download_youtube: bool = False
    scrape_external: bool = True


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


def valid_course_url(value: str) -> bool:
    """Return True if value is a valid Moodle course URL with an id parameter."""
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and bool(parse_qs(parsed.query).get("id"))


def parse_course_url(url: str) -> tuple[str, str, str]:
    """Parse a Moodle course URL."""
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    course_id = query_params.get("id", [None])[0]
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    if not course_id:
        raise ValueError("Keine Kurs-ID in der URL gefunden")

    return url, course_id, base_url


def should_download(
    activity_type: str,
    include_types: list[str] | None,
    exclude_types: list[str] | None,
) -> bool:
    """Check if an activity type should be downloaded."""
    type_categories = {
        "forum": ["forum", "announcement"],
        "quiz": ["quiz"],
        "assign": ["file", "assignment"],
        "resource": ["file", "resource"],
        "folder": ["file", "folder"],
        "page": ["description", "page"],
        "book": ["book"],
        "url": ["link", "url"],
        "choice": ["choice"],
        "label": ["description", "label"],
        "lesson": ["description", "lesson"],
        "feedback": ["description", "feedback"],
        "glossary": ["description", "glossary"],
        "wiki": ["description", "wiki"],
        "workshop": ["description", "file", "workshop"],
        "database": ["description", "file", "database"],
        "data": ["description", "file", "database"],
        "h5pactivity": ["description", "file", "h5p"],
        "scorm": ["file", "scorm"],
        "lti": ["link", "lti"],
    }

    categories = type_categories.get(activity_type, [activity_type])

    if include_types:
        return any(cat in include_types for cat in categories)
    if exclude_types:
        return not any(cat in exclude_types for cat in categories)
    return True


def _create_skip_note(section_dir: Path, name: str, url: str, reason: str) -> None:
    """Create a note file for skipped activities."""
    safe = clean_filename(name, max_length=50, is_directory=False)
    note_file = section_dir / f"{safe}_SKIP.md"

    with open(note_file, "w", encoding="utf-8") as f:
        f.write(f"# {name}\n\n")
        f.write(f"⚠️ **Übersprungen**: {reason}\n\n")
        f.write(f"🔗 [In Moodle öffnen]({url})\n")


def _unquote_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        inner = value[1:-1]
        if value[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return value


def _quote_env_value(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "")
    return f'"{escaped}"'


def parse_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """Parse key=value pairs from a .env file."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, val = stripped.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key[7:].strip()
            if key:
                result[key] = _unquote_env_value(val)
    except OSError:
        pass
    return result


def load_saved_credentials(env_path: Path = ENV_FILE) -> dict[str, str]:
    """Read saved credentials from .env or environment variables."""
    env_values = parse_env_file(env_path)
    env_user = (
        env_values.get("MOODLE_USERNAME")
        or env_values.get("MOODLE_DOWNLOAD_USERNAME")
        or os.environ.get("MOODLE_USERNAME")
        or os.environ.get("MOODLE_DOWNLOAD_USERNAME")
        or ""
    ).strip()
    env_pass = (
        env_values.get("MOODLE_PASSWORD")
        or env_values.get("MOODLE_DOWNLOAD_PASSWORD")
        or os.environ.get("MOODLE_PASSWORD")
        or os.environ.get("MOODLE_DOWNLOAD_PASSWORD")
        or ""
    )
    return {"username": env_user, "password": env_pass}


def save_credentials(
    username: str,
    password: str,
    env_path: Path = ENV_FILE,
) -> None:
    """Persist credentials directly into .env (and update os.environ)."""
    clean_user = username.strip()
    existing_lines: list[str] = []
    if env_path.exists():
        try:
            existing_lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            existing_lines = []

    target_keys = {"MOODLE_USERNAME", "MOODLE_PASSWORD", "MOODLE_DOWNLOAD_USERNAME", "MOODLE_DOWNLOAD_PASSWORD"}
    kept_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key.startswith("export "):
                key = key[7:].strip()
            if key in target_keys:
                continue
        kept_lines.append(line)

    kept_lines.append(f"MOODLE_USERNAME={_quote_env_value(clean_user)}")
    kept_lines.append(f"MOODLE_PASSWORD={_quote_env_value(password)}")
    env_path.write_text("\n".join(kept_lines).strip() + "\n", encoding="utf-8")

    os.environ["MOODLE_USERNAME"] = clean_user
    os.environ["MOODLE_PASSWORD"] = password


def resolve_credentials(config: DownloadConfig, env_path: Path = ENV_FILE) -> tuple[str, str]:
    """Resolve credentials from config, .env, or environment."""
    if config.use_saved_credentials:
        saved = load_saved_credentials(env_path)
        if saved["username"] and saved["password"]:
            return saved["username"], saved["password"]
    if config.username and config.password:
        return config.username.strip(), config.password
    saved = load_saved_credentials(env_path)
    return saved["username"], saved["password"]


def process_single_course(
    driver,
    course_url: str,
    output_dir: Path,
    include_types: list[str] | None,
    exclude_types: list[str] | None,
    logger,
    course_num: int = 1,
    total_courses: int = 1,
    update_mode: bool = False,
    force: bool = False,
    depth: str = "deep",
    optimize_ai: bool = False,
    download_youtube: bool = False,
    scrape_external: bool = True,
    cancel_event: threading.Event | None = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> dict:
    """Process a single course and return stats."""
    if cancel_event and cancel_event.is_set():
        raise DownloadCancelled("Download abgebrochen")

    reset_download_tracker()

    course_url, _course_id, _base_url = parse_course_url(course_url)

    prefix = f"[{course_num}/{total_courses}] " if total_courses > 1 else ""
    print(f"\n{prefix}📚 Kurs: {course_url}")
    print("=" * 50)

    sections, course_title = get_course_content(driver, course_url)

    if not sections:
        print("\n⚠️ Keine Kursinhalte gefunden!")
        logger.log_error("Kursinhalt", "Keine Sections gefunden")
        return {"errors": 1, "files": 0, "descriptions": 0, "links": 0, "skipped": 0, "filtered": 0}

    safe_name = clean_filename(course_title, is_directory=True)
    course_dir = output_dir / safe_name
    course_dir.mkdir(parents=True, exist_ok=True)

    print(f"📂 Download-Verzeichnis: {course_dir}")
    print("=" * 50)

    state = DownloadState(course_dir)
    set_download_options(state=state, update=update_mode, force=force)
    if update_mode:
        print(f"📊 Update-Modus: {len(state.state)} Dateien bereits heruntergeladen")
    if force:
        print("🔁 Force-Modus: Alle erreichbaren Dateien werden neu geladen")

    cookies = get_cookies_from_driver(driver)

    stats = {"files": 0, "descriptions": 0, "links": 0, "errors": 0, "skipped": 0, "filtered": 0}
    total_activities = sum(len(s["resources"]) for s in sections)
    activity_num = 0

    if progress_callback:
        progress_callback({
            "course_title": course_title,
            "course_num": course_num,
            "total_courses": total_courses,
            "activity_num": 0,
            "total_activities": total_activities,
        })

    used_section_dirs = {}
    section_path_cache = {(): course_dir}
    for section_idx, section in enumerate(sections):
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Download abgebrochen")

        raw_path = section.get("path") or [section["name"]]
        path_positions = section.get("path_positions") or []
        folder_path = [
            _section_folder_name(
                path_positions[d] if d < len(path_positions) else (section_idx + 1 if d == len(raw_path) - 1 else d + 1),
                part,
            )
            for d, part in enumerate(raw_path)
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
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Download abgebrochen")

            activity_num += 1
            name = resource["name"]
            act_type = resource["type"]

            if progress_callback:
                progress_callback({
                    "course_title": course_title,
                    "course_num": course_num,
                    "total_courses": total_courses,
                    "activity_num": activity_num,
                    "total_activities": total_activities,
                    "current_activity": name,
                })

            if not should_download(act_type, include_types, exclude_types):
                stats["filtered"] += 1
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
                    if act_type == "url":
                        stats["links"] += count
                    elif act_type in ("page", "forum", "book", "quiz"):
                        stats["descriptions"] += count
                    else:
                        stats["files"] += count
                    print(f" → {count} Datei(en)")
                    logger.log_download(name, resource["url"])
                elif count == -1:
                    stats["skipped"] += 1
                    logger.log_skip(name, "Inhalt gesperrt")
                    _create_skip_note(section_dir, name, resource["url"], "Inhalt gesperrt")
                else:
                    stats["skipped"] += 1
                    print(" → übersprungen")
                    logger.log_skip(name, "Kein Inhalt gefunden")
                    _create_skip_note(section_dir, name, resource["url"], "Kein Inhalt gefunden")
                sys.stdout.flush()
            except Exception as e:
                stats["errors"] += 1
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


def run_download_job(
    config: DownloadConfig,
    cancel_event: threading.Event | None = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> dict:
    """Execute a complete download job across one or more courses."""
    urls = [u.strip() for u in config.urls if valid_course_url(u)]
    if not urls:
        raise ValueError("Bitte gib mindestens eine gültige Moodle-Kurs-URL mit id-Parameter an.")

    username, password = resolve_credentials(config)
    if not username or not password:
        raise ValueError("Benutzername und Passwort fehlen. Bitte Zugangsdaten eingeben oder in .env hinterlegen.")

    output_dir = Path(config.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    include_types = [t.strip().lower() for t in config.include_types if t.strip() and t.strip().lower() != "all"] if config.include_types else None
    exclude_types = [t.strip().lower() for t in config.exclude_types if t.strip()] if config.exclude_types else None

    logger = setup_logging(output_dir)

    print("📚 Moodle-Kurs-Downloader")
    print("=" * 50)
    print(f"Kurse:     {len(urls)}")
    print(f"Output:    {output_dir}")
    print(f"Tiefe:     {config.depth}")
    if include_types:
        print(f"Include:   {', '.join(include_types)}")
    if exclude_types:
        print(f"Exclude:   {', '.join(exclude_types)}")
    if config.optimize_ai:
        print("AI-Ready:  aktiviert")
    print(f"YouTube:   {'Video + Link' if config.download_youtube else 'nur Link'}")
    print(f"Webseiten: {'Markdown + Link' if config.scrape_external else 'nur Link'}")
    print(f"Login:     {username}")

    driver = setup_browser_driver()
    try:
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Download abgebrochen")

        if not login_to_moodle(driver, username, password, urls[0]):
            raise RuntimeError("Login fehlgeschlagen! Bitte Benutzername und Passwort prüfen.")

        active_host = urlparse(urls[0]).netloc.casefold()
        all_stats = {"files": 0, "descriptions": 0, "links": 0, "errors": 0, "skipped": 0, "filtered": 0}

        for i, url in enumerate(urls, 1):
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Download abgebrochen")
            try:
                course_host = urlparse(url).netloc.casefold()
                if course_host != active_host:
                    if not login_to_moodle(driver, username, password, url):
                        raise RuntimeError(f"Login bei {course_host} fehlgeschlagen")
                    active_host = course_host
                stats = process_single_course(
                    driver,
                    url,
                    output_dir,
                    include_types,
                    exclude_types,
                    logger,
                    i,
                    len(urls),
                    update_mode=config.update_mode,
                    force=config.force,
                    depth=config.depth,
                    optimize_ai=config.optimize_ai,
                    download_youtube=config.download_youtube,
                    scrape_external=config.scrape_external,
                    cancel_event=cancel_event,
                    progress_callback=progress_callback,
                )
                for key in all_stats:
                    all_stats[key] += stats.get(key, 0)
            except DownloadCancelled:
                raise
            except Exception as e:
                print(f"\n❌ Fehler bei Kurs {i}: {e}")
                logger.log_error(f"Kurs {i}", str(e))
                all_stats["errors"] += 1

        print(f"\n{'=' * 50}")
        print("✅ Alle Kurse abgeschlossen!")
        print(f"\n📊 Gesamt ({len(urls)} Kurse):")
        print(f"   📄 Dateien: {all_stats['files']}")
        print(f"   📝 Beschreibungen: {all_stats['descriptions']}")
        print(f"   🔗 Links: {all_stats['links']}")
        print(f"   ⏭️ Übersprungen: {all_stats['skipped']}")
        print(f"   🚫 Gefiltert: {all_stats['filtered']}")
        if all_stats["errors"] > 0:
            print(f"   ❌ Fehler: {all_stats['errors']}")
        print(f"\n   Gespeichert in: {output_dir}")
        return all_stats
    finally:
        print("\n🔧 Schließe Browser...")
        try:
            driver.quit()
        except Exception:
            pass
