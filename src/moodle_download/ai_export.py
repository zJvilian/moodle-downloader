"""Create a deterministic, model-friendly view of a downloaded course."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .parsers import html_to_markdown


AI_DIR_NAME = "_AI_READY"
MAX_SOURCE_BYTES = 2_000_000
MAX_CHUNK_CHARS = 180_000
TEXT_EXTENSIONS = {
    ".c", ".cpp", ".css", ".csv", ".h", ".html", ".htm", ".ini", ".java", ".js",
    ".json", ".jsonl", ".md", ".php", ".py", ".r", ".rst", ".sql", ".tex", ".toml",
    ".description", ".srt", ".ts", ".tsv", ".txt", ".url", ".vtt", ".xml", ".yaml", ".yml",
}


def _category(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt", ".rst"}:
        return "text"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".odt", ".ods", ".odp"}:
        return "document"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".tif", ".tiff"}:
        return "image"
    if suffix in {".mp3", ".wav", ".m4a", ".aac", ".mp4", ".webm", ".mov", ".mkv", ".avi"}:
        return "media"
    if suffix in {".zip", ".7z", ".rar", ".tar", ".gz"}:
        return "archive"
    if suffix == ".url":
        return "link"
    return "file"


def _read_source(path: Path) -> str:
    if path.suffix.lower() not in TEXT_EXTENSIONS or path.stat().st_size > MAX_SOURCE_BYTES:
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".html", ".htm"}:
        return html_to_markdown(text)
    return text.strip()


def _flush_chunk(chunks_dir: Path, number: int, documents: list[str]) -> str:
    filename = f"chunk_{number:03d}.md"
    body = (
        "---\n"
        "schema: moodle-ai-context/v1\n"
        f"chunk: {number}\n"
        "---\n\n"
        + "\n\n".join(documents).strip()
        + "\n"
    )
    (chunks_dir / filename).write_text(body, encoding="utf-8")
    return filename


def build_ai_export(course_dir: Path, course_title: str, course_url: str, sections: list[dict]) -> dict:
    """Build indexes and bounded text chunks without duplicating binary assets."""
    ai_dir = course_dir / AI_DIR_NAME
    chunks_dir = ai_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    files = []
    documents = []
    current_chars = 0
    chunk_files = []
    readable_count = 0

    source_files = sorted(
        (
            path for path in course_dir.rglob("*")
            if path.is_file()
            and AI_DIR_NAME not in path.relative_to(course_dir).parts
            and path.name != ".state.json"
            and not path.name.startswith("download_log_")
        ),
        key=lambda item: item.relative_to(course_dir).as_posix().casefold(),
    )

    for number, path in enumerate(source_files, 1):
        relative = path.relative_to(course_dir).as_posix()
        entry = {
            "id": f"doc-{number:05d}",
            "path": relative,
            "name": path.name,
            "extension": path.suffix.lower(),
            "category": _category(path),
            "size_bytes": path.stat().st_size,
            "hierarchy": list(path.relative_to(course_dir).parts[:-1]),
            "text_included": False,
        }
        content = _read_source(path)
        if content:
            readable_count += 1
            entry["text_included"] = True
            document = (
                f'<document id="{entry["id"]}" path="{relative}" category="{entry["category"]}">\n\n'
                f"# Source: {relative}\n\n{content}\n\n</document>"
            )
            if documents and current_chars + len(document) > MAX_CHUNK_CHARS:
                chunk_files.append(_flush_chunk(chunks_dir, len(chunk_files) + 1, documents))
                documents = []
                current_chars = 0
            documents.append(document)
            current_chars += len(document)
        files.append(entry)

    if documents:
        chunk_files.append(_flush_chunk(chunks_dir, len(chunk_files) + 1, documents))

    # Stale generated chunks are safe to remove and would otherwise confuse importers.
    active_chunks = set(chunk_files)
    for stale in chunks_dir.glob("chunk_*.md"):
        if stale.name not in active_chunks:
            stale.unlink()

    safe_sections = []
    for section in sections:
        safe_sections.append({
            "id": section.get("id", ""),
            "name": section.get("name", ""),
            "path": section.get("path") or [section.get("name", "")],
            "level": section.get("level", 0),
            "activities": [
                {
                    "name": resource.get("name", ""),
                    "type": resource.get("type", "unknown"),
                    "source_url": resource.get("url", ""),
                }
                for resource in section.get("resources", [])
            ],
        })

    metadata = {
        "schema": "moodle-ai-export/v1",
        "course_title": course_title,
        "source_url": course_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "readable_source_count": readable_count,
        "chunk_count": len(chunk_files),
        "chunks": [f"chunks/{name}" for name in chunk_files],
    }
    (ai_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    (ai_dir / "course_structure.json").write_text(json.dumps(safe_sections, indent=2, ensure_ascii=False), encoding="utf-8")
    with (ai_dir / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for entry in files:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    chunk_list = "\n".join(f"- [{name}](chunks/{name})" for name in chunk_files) or "- Keine textlesbaren Quellen gefunden"
    readme = f"""# AI-ready course context: {course_title}

This directory is a deterministic index over the complete course download.
Feed the chunk files to an AI tool in numerical order. Binary documents remain
in their original locations and are described in `manifest.jsonl`.

## Import order

1. `metadata.json`
2. `course_structure.json`
3. `manifest.jsonl`
4. The context chunks below

{chunk_list}

## Source

{course_url}
"""
    (ai_dir / "README.md").write_text(readme, encoding="utf-8")
    return metadata
