"""Local browser-based web server and UI for Moodle Downloader."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import DOWNLOADS_DIR, ENV_FILE, __version__
from .browser import detect_installed_browsers
from .engine import (
    DownloadCancelled,
    DownloadConfig,
    load_saved_credentials,
    run_download_job,
    save_credentials,
    valid_course_url,
)


def classify_log_line(line: str) -> str:
    """Return a semantic level ('success', 'error', 'warning', 'info', 'default') for a log line."""
    lower = line.lower()
    if "✅" in line or "abgeschlossen" in lower or "erfolgreich" in lower:
        return "success"
    if "❌" in line or "fehler" in lower or "fehlgeschlagen" in lower:
        return "error"
    if "⚠" in line or "übersprungen" in lower or "gesperrt" in lower:
        return "warning"
    if any(marker in line for marker in ("📚", "📁", "📂", "🧠", "🔐", "🔧", "📊", "🔁")):
        return "info"
    return "default"


class _StreamInterceptor(io.TextIOBase):
    """Thread-aware stdout/stderr tee that captures lines from the worker thread."""

    def __init__(self, fallback, target_thread_id: int, on_line):
        self._fallback = fallback
        self._target_thread_id = target_thread_id
        self._on_line = on_line
        self._buffer = ""
        self._lock = threading.Lock()

    def write(self, s: str) -> int:
        if not s:
            return 0
        try:
            self._fallback.write(s)
        except Exception:
            pass
        if threading.get_ident() == self._target_thread_id:
            with self._lock:
                self._buffer += s
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    cleaned = line.rstrip("\r")
                    if cleaned.strip():
                        self._on_line(cleaned)
        return len(s)

    def flush(self) -> None:
        try:
            self._fallback.flush()
        except Exception:
            pass
        if threading.get_ident() == self._target_thread_id:
            with self._lock:
                cleaned = self._buffer.rstrip("\r\n")
                if cleaned.strip():
                    self._on_line(cleaned)
                self._buffer = ""


class JobManager:
    """Manages the state, logs, and background execution of download jobs."""

    def __init__(self, env_file: Path = ENV_FILE, default_output: Path = DOWNLOADS_DIR):
        self.env_file = env_file
        self.default_output = default_output
        self._lock = threading.Lock()
        self.status: str = "idle"  # idle, running, cancelling, completed, error, cancelled
        self.status_text: str = "Bereit für den Download"
        self.logs: list[dict[str, Any]] = []
        self.progress: dict[str, Any] = {
            "course_title": "",
            "course_num": 0,
            "total_courses": 0,
            "activity_num": 0,
            "total_activities": 0,
            "current_activity": "",
        }
        self.stats: dict[str, int] = {
            "files": 0,
            "descriptions": 0,
            "links": 0,
            "errors": 0,
            "skipped": 0,
            "filtered": 0,
        }
        self.last_output_dir: str = str(default_output)
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None

    def append_log(self, text: str, level: str | None = None) -> None:
        with self._lock:
            entry = {
                "id": len(self.logs) + 1,
                "timestamp": time.strftime("%H:%M:%S"),
                "text": text,
                "level": level or classify_log_line(text),
            }
            self.logs.append(entry)

    def clear_logs(self) -> None:
        with self._lock:
            self.logs.clear()

    def update_progress(self, data: dict[str, Any]) -> None:
        with self._lock:
            self.progress.update(data)
            c_num = self.progress.get("course_num", 0)
            c_tot = self.progress.get("total_courses", 0)
            a_num = self.progress.get("activity_num", 0)
            a_tot = self.progress.get("total_activities", 0)
            title = self.progress.get("course_title") or ""
            if a_tot > 0:
                self.status_text = f"Kurs {c_num}/{c_tot}: {title} · Aktivität {a_num}/{a_tot}"
            elif c_tot > 0:
                self.status_text = f"Lade Kurs {c_num}/{c_tot} …"

    def snapshot(self, since: int = 0) -> dict[str, Any]:
        with self._lock:
            saved = load_saved_credentials(self.env_file)
            return {
                "version": __version__,
                "status": self.status,
                "status_text": self.status_text,
                "is_running": self.status in {"running", "cancelling"},
                "progress": dict(self.progress),
                "stats": dict(self.stats),
                "output_dir": self.last_output_dir,
                "saved_username": saved["username"],
                "has_saved_credentials": bool(saved["username"] and saved["password"]),
                "logs": self.logs[since:] if since < len(self.logs) else [],
                "log_count": len(self.logs),
            }

    def start_job(self, payload: dict[str, Any]) -> tuple[bool, str]:
        with self._lock:
            if self.status in {"running", "cancelling"}:
                return False, "Ein Download läuft bereits."

            raw_urls = payload.get("urls") or []
            if isinstance(raw_urls, str):
                raw_urls = [line.strip() for line in raw_urls.splitlines() if line.strip()]
            valid_urls = [u.strip() for u in raw_urls if valid_course_url(u)]
            if not valid_urls:
                return False, "Bitte mindestens eine gültige Moodle-Kurs-URL (mit ?id=...) angeben."

            use_saved = bool(payload.get("use_saved_credentials"))
            username = str(payload.get("username") or "").strip()
            password = str(payload.get("password") or "")
            remember = bool(payload.get("save_credentials"))

            saved = load_saved_credentials(self.env_file)
            if use_saved and saved["username"] and saved["password"]:
                username, password = saved["username"], saved["password"]
            elif not username or not password:
                if saved["username"] and saved["password"] and not username and not password:
                    username, password = saved["username"], saved["password"]
                    use_saved = True
                else:
                    return False, "Bitte Benutzername und Passwort eingeben oder gespeicherte Zugangsdaten aktivieren."

            if remember and username and password:
                try:
                    save_credentials(username, password, self.env_file)
                except OSError as exc:
                    return False, f"Zugangsdaten konnten nicht gespeichert werden: {exc}"

            output_str = str(payload.get("output_dir") or self.default_output).strip()
            output_dir = Path(output_str).expanduser()
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return False, f"Speicherort ungültig: {exc}"

            include_raw = payload.get("include")
            include_types: list[str] | None = None
            if isinstance(include_raw, list):
                include_types = [str(item).strip().lower() for item in include_raw if str(item).strip()]
            elif isinstance(include_raw, str) and include_raw.strip() and include_raw.strip().lower() != "all":
                include_types = [part.strip().lower() for part in include_raw.split(",") if part.strip()]

            exclude_raw = payload.get("exclude")
            exclude_types: list[str] | None = None
            if isinstance(exclude_raw, list):
                exclude_types = [str(item).strip().lower() for item in exclude_raw if str(item).strip()]
            elif isinstance(exclude_raw, str) and exclude_raw.strip():
                exclude_types = [part.strip().lower() for part in exclude_raw.split(",") if part.strip()]

            mode = str(payload.get("mode") or "normal").lower()
            update_mode = bool(payload.get("update")) or mode == "update"
            force_mode = bool(payload.get("force")) or mode == "force"
            depth = "shallow" if str(payload.get("depth") or "deep").lower() == "shallow" else "deep"

            config = DownloadConfig(
                urls=valid_urls,
                output_dir=output_dir,
                username=username,
                password=password,
                use_saved_credentials=use_saved,
                include_types=include_types,
                exclude_types=exclude_types,
                depth=depth,
                update_mode=update_mode,
                force=force_mode,
                optimize_ai=bool(payload.get("optimize_ai")),
                download_youtube=bool(payload.get("download_youtube")),
                scrape_external=bool(payload.get("scrape_external", True)),
            )

            self.last_output_dir = str(output_dir)
            self.logs.clear()
            self.stats = {"files": 0, "descriptions": 0, "links": 0, "errors": 0, "skipped": 0, "filtered": 0}
            self.progress = {
                "course_title": "",
                "course_num": 0,
                "total_courses": len(valid_urls),
                "activity_num": 0,
                "total_activities": 0,
                "current_activity": "",
            }
            self.status = "running"
            self.status_text = f"Download läuft · {len(valid_urls)} Kurs{'e' if len(valid_urls) != 1 else ''}"
            self._cancel_event.clear()

            self._worker = threading.Thread(
                target=self._run_worker,
                args=(config,),
                daemon=True,
            )
            self._worker.start()
            return True, "Download gestartet."

    def cancel_job(self) -> tuple[bool, str]:
        with self._lock:
            if self.status not in {"running", "cancelling"}:
                return False, "Kein aktiver Download zum Abbrechen."
            self.status = "cancelling"
            self.status_text = "Download wird abgebrochen …"
            self._cancel_event.set()
        self.append_log("⏹️ Abbruch angefordert – warte auf laufende Aktion …", "warning")
        return True, "Abbruch angefordert."

    def _run_worker(self, config: DownloadConfig) -> None:
        thread_id = threading.get_ident()
        orig_stdout, orig_stderr = sys.stdout, sys.stderr
        interceptor = _StreamInterceptor(orig_stdout, thread_id, self.append_log)
        sys.stdout = interceptor  # type: ignore[assignment]
        sys.stderr = interceptor  # type: ignore[assignment]
        try:
            self.append_log("🚀 Download wird vorbereitet …", "info")
            stats = run_download_job(
                config,
                cancel_event=self._cancel_event,
                progress_callback=self.update_progress,
            )
            interceptor.flush()
            with self._lock:
                self.stats = stats
                if stats.get("errors", 0) > 0:
                    self.status = "completed"
                    self.status_text = f"Abgeschlossen mit {stats['errors']} Fehler(n)"
                else:
                    self.status = "completed"
                    self.status_text = "Download vollständig abgeschlossen"
        except DownloadCancelled:
            interceptor.flush()
            self.append_log("⏹️ Download wurde vom Benutzer abgebrochen.", "warning")
            with self._lock:
                self.status = "cancelled"
                self.status_text = "Download abgebrochen"
        except ( Exception, SystemExit ) as exc:
            interceptor.flush()
            self.append_log(f"❌ {exc}", "error")
            with self._lock:
                self.status = "error"
                self.status_text = "Download fehlgeschlagen · Log prüfen"
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr


def list_downloaded_courses(output_dir: Path) -> list[dict[str, Any]]:
    """Inspect downloaded courses in output_dir for the browser UI."""
    if not output_dir.exists() or not output_dir.is_dir():
        return []
    courses: list[dict[str, Any]] = []
    for entry in sorted(output_dir.iterdir(), key=lambda p: p.name.casefold()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        files_count = 0
        total_bytes = 0
        sections_count = 0
        has_ai = (entry / "_AI_READY").is_dir()
        for child in entry.iterdir():
            if child.is_dir() and not child.name.startswith(".") and child.name != "_AI_READY":
                sections_count += 1
        for f in entry.rglob("*"):
            if f.is_file() and f.name != ".state.json" and not f.name.startswith("download_log_"):
                files_count += 1
                with contextlib.suppress(OSError):
                    total_bytes += f.stat().st_size
        courses.append({
            "name": entry.name,
            "path": str(entry),
            "sections": sections_count,
            "files": files_count,
            "size_bytes": total_bytes,
            "has_ai_export": has_ai,
        })
    return courses


def open_local_folder(path_str: str) -> tuple[bool, str]:
    """Open a directory in the system file manager."""
    folder = Path(path_str).expanduser()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        return True, str(folder)
    except Exception as exc:
        return False, str(exc)


INDEX_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Moodle Downloader</title>
  <style>
    :root { color-scheme: dark; --bg:#101017; --bg-elevated:#111119; --card:#1a1924; --card-alt:#22212e; --card-hover:#2c293b; --border:#33303f; --border-active:#74658d; --text:#f2effa; --muted:#aaa5bb; --faint:#8c859f; --primary:#c5b1ff; --primary-hover:#d6c8ff; --primary-dark:#241443; --blue:#b5bfff; --green:#8edbb5; --amber:#f1cb8b; --red:#ff9baa; --radius:20px; --radius-sm:10px; --shadow:0 12px 36px #00000021; }
    * { box-sizing:border-box; margin:0; padding:0; }
    body { min-height:100vh; color:var(--text); background:radial-gradient(ellipse at 7% 0%,#44305d50,transparent 48%),radial-gradient(ellipse at 95% 42%,#283d5430,transparent 48%),var(--bg); font:14px/1.55 'Segoe UI',-apple-system,BlinkMacSystemFont,sans-serif; }
    button,input,select,textarea { font:inherit; } button { touch-action:manipulation; }
    header { max-width:1480px; margin:auto; padding:26px 40px; display:flex; align-items:center; justify-content:space-between; gap:20px; border-bottom:1px solid #ffffff0c; }
    .brand,.header-badges,.row-inline { display:flex; align-items:center; gap:12px; }
    .brand-mark { width:44px; height:44px; display:grid; place-items:center; border:1px solid #d5baff50; border-radius:14px; background:linear-gradient(140deg,#a992e8,#7660ad); color:white; box-shadow:0 6px 28px #ad87ff25; }
    .icon { width:19px; height:19px; fill:none; stroke:currentColor; stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round; flex-shrink:0; vertical-align:middle; }
    .brand-mark .icon { width:25px; height:25px; }
    .brand-title h1 { font-size:17px; font-weight:650; letter-spacing:-.5px; } .brand-title p { color:var(--faint); font-size:11px; margin-top:2px; }
    .badge { display:inline-flex; align-items:center; gap:8px; border:1px solid var(--border); border-radius:100px; padding:6px 11px; font-size:11px; color:var(--muted); background:#ffffff03; }
    .badge-dot,.status-dot { width:7px; height:7px; border-radius:50%; background:var(--green); flex-shrink:0; }
    .intro { max-width:1480px; margin:auto; padding:38px 40px 26px; display:flex; align-items:end; justify-content:space-between; gap:24px; }
    .eyebrow { font-size:10px; letter-spacing:2px; color:var(--primary); font-weight:700; text-transform:uppercase; margin-bottom:9px; }
    .intro h2 { font-size:clamp(26px,3vw,38px); line-height:1.2; font-weight:600; letter-spacing:-1.4px; } .intro p { margin-top:10px; color:var(--muted); font-size:13px; }
    .local-note { color:var(--faint); font-size:12px; display:flex; align-items:center; gap:8px; padding-bottom:3px; white-space:nowrap; }
    main { display:grid; grid-template-columns:minmax(360px,440px) minmax(0,1fr); align-items:start; gap:24px; max-width:1480px; margin:auto; padding:0 40px 40px; }
    .settings-column { display:flex; flex-direction:column; gap:14px; min-width:0; }
    .card,.activity-panel { border:1px solid var(--border); background:linear-gradient(135deg,#ffffff04,transparent 60%),#1a1924e8; border-radius:var(--radius); box-shadow:var(--shadow); backdrop-filter:blur(18px); }
    .card { padding:21px; transition:border-color .2s,box-shadow .2s; } .card.highlight { border-color:#bca1ff88; box-shadow:0 0 25px #a286ff10; }
    .card-header { display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:15px; } .card-title { font-size:13px; font-weight:650; display:inline-flex; align-items:center; gap:9px; } .card-title .icon { color:var(--primary); width:17px; height:17px; }
    .card-subtitle { font-size:10px; color:var(--faint); } .field-label { display:block; font-size:11px; color:var(--muted); margin-bottom:7px; }
    textarea,input[type=text],input[type=password],select { width:100%; min-width:0; border:1px solid var(--border); background:#11101980; color:var(--text); border-radius:var(--radius-sm); padding:11px 12px; outline:none; transition:border-color .2s,box-shadow .2s; font-size:12px; }
    textarea { resize:vertical; min-height:112px; font:12px/1.8 'Cascadia Mono',Consolas,monospace; } textarea::placeholder,input::placeholder { color:#777185; }
    textarea:focus,input:focus,select:focus { border-color:var(--primary); box-shadow:0 0 0 3px #c5b1ff14; }
    :focus-visible { outline:2px solid var(--primary); outline-offset:4px; } input:disabled { opacity:.45; }
    .helper-row { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-top:9px; font-size:10px; } .url-counter { color:var(--primary); white-space:nowrap; }
    .grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:12px; } .check-row { display:flex; align-items:start; gap:9px; padding:6px 0; color:var(--muted); font-size:11px; cursor:pointer; } .check-row input { accent-color:var(--primary); margin-top:2px; width:15px; height:15px; flex-shrink:0; }
    code { font: .95em Consolas,monospace; color:var(--primary); } .credential-note { color:var(--faint); font-size:10px; margin-top:7px; }
    .segmented { display:grid; grid-template-columns:repeat(3,1fr); background:#11101980; border:1px solid var(--border); border-radius:9px; padding:3px; gap:2px; } .segmented.two-col { grid-template-columns:repeat(2,1fr); }
    .segmented button { border:0; background:transparent; border-radius:6px; color:var(--muted); font-size:10px; padding:7px 3px; cursor:pointer; transition:background .2s,color .2s; } .segmented button.active { background:#c5b1ff24; color:var(--primary); box-shadow:0 1px 4px #0002; }
    .ai-banner { display:flex; align-items:center; justify-content:space-between; gap:16px; } .ai-banner p { font-size:11px; color:var(--faint); margin-top:6px; max-width:290px; }
    .btn { display:inline-flex; align-items:center; justify-content:center; gap:8px; padding:10px 14px; border:1px solid transparent; border-radius:10px; font-size:12px; font-weight:600; cursor:pointer; transition:background .2s,transform .2s,border-color .2s; white-space:nowrap; }
    .btn:hover:not(:disabled) { transform:translateY(-1px); } .btn:active:not(:disabled) { transform:translateY(0); } .btn:disabled { opacity:.35; cursor:not-allowed; }
    .btn-primary { color:var(--primary-dark); background:linear-gradient(115deg,#d0bfff,#b59bed); box-shadow:0 4px 18px #ad87ff20; } .btn-primary:hover:not(:disabled) { background:var(--primary-hover); }
    .btn-secondary { color:var(--muted); border-color:var(--border); background:#ffffff04; } .btn-secondary:hover:not(:disabled) { background:var(--card-hover); border-color:var(--border-active); color:var(--text); }
    .btn-danger { background:#ff9baa09; border-color:#ff9baa25; color:var(--red); } .btn-sm { padding:8px 10px; font-size:10px; }
    .activity-column { min-width:0; position:sticky; top:24px; } .activity-panel { overflow:hidden; display:flex; flex-direction:column; }
    .workspace-heading { padding:24px 24px 18px; display:flex; align-items:center; justify-content:space-between; } .workspace-heading h3 { font-size:17px; font-weight:600; letter-spacing:-.4px; } .workspace-heading p { font-size:11px; color:var(--faint); margin-top:4px; }
    .panel-toolbar { display:flex; justify-content:space-between; gap:8px; align-items:center; padding:0 24px 18px; border-bottom:1px solid var(--border); } .tabs { display:flex; gap:4px; background:#11101980; border-radius:10px; padding:4px; }
    .tab-btn { border:0; background:transparent; color:var(--faint); font-size:11px; font-weight:600; padding:9px 12px; border-radius:7px; cursor:pointer; transition:background .2s,color .2s; } .tab-btn.active { color:var(--text); background:#34303f; box-shadow:0 2px 6px #0002; }
    .stats-strip { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); padding:24px; gap:12px; border-bottom:1px solid var(--border); } .stat-box { border-right:1px solid var(--border); padding-right:6px; } .stat-box:last-child { border:0; } .stat-label { font-size:9px; color:var(--faint); letter-spacing:.4px; } .stat-value { font-size:28px; font-weight:500; letter-spacing:-1px; margin-top:4px; font-variant-numeric:tabular-nums; }
    .log-console,.courses-view { background:#100f1780; height:390px; overflow:auto; padding:20px 24px; scrollbar-width:thin; scrollbar-color:var(--border) transparent; } .log-console { font:11px/1.9 'Cascadia Mono',Consolas,monospace; } .courses-view { display:none; }
    .log-line { padding:3px 0; white-space:pre-wrap; overflow-wrap:anywhere; color:var(--muted); } .ts { color:var(--faint); margin-right:12px; font-size:10px; } .log-line.info { color:var(--blue); } .log-line.success { color:var(--green); } .log-line.warning { color:var(--amber); } .log-line.error { color:var(--red); }
    .empty-state { height:100%; min-height:240px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:24px; font-family:'Segoe UI',sans-serif; } .empty-icon { display:grid; place-items:center; width:60px; height:60px; background:linear-gradient(135deg,#c5b1ff15,#c5b1ff04); border:1px solid #c5b1ff20; border-radius:19px; color:var(--primary); margin-bottom:20px; } .empty-icon .icon { width:26px; height:26px; } .empty-state h4 { font-size:15px; font-weight:500; color:var(--text); margin-bottom:7px; } .empty-state p { font-size:12px; color:var(--faint); max-width:285px; line-height:1.8; }
    .course-item { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:16px; margin-bottom:10px; border:1px solid var(--border); border-radius:12px; background:#ffffff03; transition:border-color .2s; } .course-item:hover { border-color:var(--border-active); } .course-name { overflow-wrap:anywhere; font-size:13px; font-weight:600; } .course-meta { font-size:10px; color:var(--faint); margin-top:5px; }
    .panel-footer { padding:22px 24px 24px; display:flex; flex-direction:column; gap:16px; } .status-bar { display:flex; justify-content:space-between; gap:12px; color:var(--muted); font-size:11px; } .status-indicator { display:flex; align-items:center; gap:8px; min-width:0; } #statusText { overflow-wrap:anywhere; } .status-dot.running { background:var(--amber); animation:pulse 1.4s infinite; } .status-dot.error { background:var(--red); } .status-dot.success { background:var(--green); }
    .progress-track { height:4px; background:var(--card-alt); border-radius:9px; overflow:hidden; } .progress-fill { height:100%; width:0; border-radius:9px; background:linear-gradient(90deg,#9879d7,#d1bfff); transition:width .3s; } .progress-fill.indeterminate { width:35%; animation:slide 1.5s infinite; } .action-buttons { display:flex; gap:10px; } .action-buttons .btn-primary { flex:1; padding:13px; }
    .workspace-note { display:flex; justify-content:center; gap:6px; align-items:center; color:var(--faint); font-size:10px; padding:16px; } .workspace-note .icon { width:13px; height:13px; }
    .toast { position:fixed; bottom:24px; right:24px; max-width:min(440px,calc(100vw - 32px)); border:1px solid var(--border-active); border-radius:12px; background:#2b2639; box-shadow:var(--shadow); padding:14px 20px; font-size:12px; opacity:0; transform:translateY(12px); pointer-events:none; transition:opacity .2s,transform .2s; z-index:100; } .toast.visible { opacity:1; transform:translateY(0); }
    @keyframes pulse { 50% { opacity:.4; } } @keyframes slide { from { transform:translateX(-100%); } to { transform:translateX(300%); } }
    @media(min-width:1600px) { .log-console,.courses-view { height:440px; } }
    @media(max-width:1050px) { main { grid-template-columns:minmax(320px,390px) minmax(0,1fr); padding:0 24px 32px; gap:18px; } header,.intro { padding-left:24px; padding-right:24px; } .local-note { display:none; } .panel-toolbar { flex-wrap:wrap; } .stats-strip { gap:8px; padding:20px; } }
    @media(max-width:800px) { main { grid-template-columns:1fr; } .activity-column { position:static; } .intro { padding-top:28px; } .header-badges #browserBadge { display:none; } .log-console,.courses-view { height:340px; } }
    @media(max-width:440px) { header { padding:20px 16px; } main { padding:0 12px 24px; } .intro { padding:26px 18px 22px; } .brand-title p { font-size:9px; } .card { padding:17px; } .grid-2 { grid-template-columns:1fr; } .panel-toolbar,.workspace-heading,.panel-footer { padding-left:16px; padding-right:16px; } .stats-strip { padding:16px; gap:6px; } .stat-label { font-size:8px; letter-spacing:0; } .stat-value { font-size:24px; } .tab-btn { padding:8px; font-size:10px; } .course-item { align-items:start; flex-direction:column; } }
    @media(prefers-reduced-motion:reduce) { *,*::before,*::after { animation:none!important; transition:none!important; scroll-behavior:auto!important; } }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="brand-mark"><svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/></svg></div>
      <div class="brand-title">
        <h1>Moodle Downloader</h1>
        <p>Dein Wissen. Lokal gesammelt.</p>
      </div>
    </div>
    <div class="header-badges">
      <span class="badge" id="browserBadge">
        <span class="badge-dot"></span>
        <span id="browserBadgeText">Headless Browser bereit</span>
      </span>
      <span class="badge" id="versionBadge">v2.3.0</span>
    </div>
  </header>

  <div class="intro"><div><div class="eyebrow">Dein persönliches Kursarchiv</div><h2>Alles für dein nächstes Kapitel.</h2><p>Sammle deine Moodle-Kurse an einem Ort. Strukturiert, durchsuchbar und offline bereit.</p></div><span class="local-note"><svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/></svg> Läuft lokal auf deinem Rechner</span></div>
  <main>
    <!-- Settings Column -->
    <section class="settings-column">
      <div class="card">
        <div class="card-header">
          <label for="urlsInput" class="card-title"><svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="m10 13 4-4m-6 7-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 1 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"/></svg>Kursquellen</label>
          <span class="card-subtitle">Eine Moodle-URL pro Zeile</span>
        </div>
        <textarea id="urlsInput" placeholder="https://moodle.hs-augsburg.de/course/view.php?id=12345"></textarea>
        <div class="helper-row">
          <span style="color: var(--faint)">Unterstützt mehrere Kurse hintereinander</span>
          <span class="url-counter" id="urlCounter">0 gültige Kurse</span>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <label for="outputInput" class="card-title"><svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M3 7V5h6l2 2h10v13H3Z"/></svg>Speicherort</label>
          <span class="card-subtitle">Lokales Verzeichnis</span>
        </div>
        <div class="row-inline">
          <input type="text" id="outputInput" placeholder="./downloads">
          <button type="button" class="btn btn-secondary btn-sm" id="openFolderBtn" title="Im Dateimanager öffnen">Ordner öffnen</button>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title"><svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/></svg>Moodle-Zugang</span>
          <span class="card-subtitle" id="credsBadge">Login</span>
        </div>
        <label class="check-row" style="margin-bottom: 8px;">
          <input type="checkbox" id="useSavedCreds">
          <span>Gespeicherte Zugangsdaten (.env) verwenden</span>
        </label>
        <div class="grid-2" id="credsInputs">
          <div>
            <label class="field-label" for="usernameInput">Benutzername</label>
            <input type="text" id="usernameInput" autocomplete="username" placeholder="z.B. max.mustermann">
          </div>
          <div>
            <label class="field-label" for="passwordInput">Passwort</label>
            <input type="password" id="passwordInput" autocomplete="current-password" placeholder="••••••••">
          </div>
        </div>
        <label class="check-row" style="margin-top: 8px;">
          <input type="checkbox" id="saveCredsCheck">
          <span>Zugangsdaten lokal in <code>.env</code> speichern</span>
        </label>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title"><svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/></svg>Download-Optionen</span>
          <span class="card-subtitle">Filter &amp; Tiefe</span>
        </div>

        <label class="field-label" for="scopeSelect">Inhaltstypen</label>
        <select id="scopeSelect" style="margin-bottom: 12px;">
          <option value="all">Alles herunterladen</option>
          <option value="file">Nur Dateien (PDF, ZIP, Ressourcen)</option>
          <option value="description">Nur Beschreibungen &amp; Seiten</option>
          <option value="forum">Nur Foren &amp; Ankündigungen</option>
          <option value="quiz">Nur Quizzes</option>
          <option value="book">Nur Bücher</option>
          <option value="link">Nur externe Links</option>
          <option value="assignment">Nur Aufgaben</option>
        </select>

        <div class="grid-2" style="margin-bottom: 12px;">
          <div>
            <label class="field-label">Scraping-Tiefe</label>
            <div class="segmented two-col" id="depthGroup">
              <button type="button" data-depth="deep" class="active">Tief</button>
              <button type="button" data-depth="shallow">Übersicht</button>
            </div>
          </div>
          <div>
            <label class="field-label">Download-Modus</label>
            <div class="segmented" id="modeGroup">
              <button type="button" data-mode="normal" class="active">Normal</button>
              <button type="button" data-mode="update">Update</button>
              <button type="button" data-mode="force">Force</button>
            </div>
          </div>
        </div>

        <label class="check-row">
          <input type="checkbox" id="youtubeCheck">
          <span>YouTube-Videos herunterladen (sonst nur Link speichern)</span>
        </label>
        <label class="check-row">
          <input type="checkbox" id="externalCheck" checked>
          <span>Geeignete externe Webseiten als Markdown archivieren</span>
        </label>
      </div>

      <div class="card" id="aiCard">
        <div class="ai-banner">
          <div>
            <div class="card-title"><svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/></svg>AI-Ready Export</div>
            <p>Erstellt <code>_AI_READY/</code> mit Strukturkarte, Manifest und geordneten Kontext-Paketen für LLMs.</p>
          </div>
          <button type="button" class="btn btn-secondary btn-sm" id="aiToggleBtn" aria-pressed="false" aria-label="AI-Ready Export">AUS</button>
        </div>
      </div>
    </section>

    <!-- Activity & Course Explorer Column -->
    <section class="activity-column">
      <div class="activity-panel">
        <div class="workspace-heading"><div><h3>Dein Download-Workspace</h3><p>Fortschritt verfolgen. Kurse wiederfinden.</p></div><span class="badge">Lokal</span></div>
        <div class="panel-toolbar">
          <div class="tabs">
            <button type="button" class="tab-btn active" id="tabLogBtn">Live-Aktivität</button>
            <button type="button" class="tab-btn" id="tabCoursesBtn">Kursarchiv</button>
          </div>
          <div class="row-inline">
            <button type="button" class="btn btn-secondary btn-sm" id="refreshCoursesBtn" style="display:none;">Aktualisieren</button>
            <button type="button" class="btn btn-secondary btn-sm" id="clearLogBtn">Log leeren</button>
          </div>
        </div>

        <div class="stats-strip">
          <div class="stat-box">
            <div class="stat-label">Dateien</div>
            <div class="stat-value" id="statFiles">0</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Texte / MD</div>
            <div class="stat-value" id="statDescriptions">0</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Links</div>
            <div class="stat-value" id="statLinks">0</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Übersprungen</div>
            <div class="stat-value" id="statSkipped">0</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Fehler</div>
            <div class="stat-value" id="statErrors" style="color: var(--muted);">0</div>
          </div>
        </div>

        <div class="log-console" id="logConsole" role="log" aria-label="Download-Aktivität">
          <div class="empty-state"><div class="empty-icon"><svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/></svg></div><h4>Dein Kursarchiv beginnt hier.</h4><p>Füge deine Kurs-URLs hinzu und starte den Download. Hier siehst du jeden Schritt live.</p></div>
        </div>

        <div class="courses-view" id="coursesView"></div>

        <div class="panel-footer">
          <div class="status-bar">
            <div class="status-indicator">
              <span class="status-dot" id="statusDot"></span>
              <span id="statusText">Bereit für den Download</span>
            </div>
            <span id="progressPercent"></span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" id="progressFill"></div>
          </div>
          <div class="action-buttons">
            <button type="button" class="btn btn-primary" id="startBtn"><svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/></svg>Download starten</button>
            <button type="button" class="btn btn-danger" id="cancelBtn" disabled>Abbrechen</button>
          </div>
        </div>
      </div>
      <p class="workspace-note"><svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M3 7V5h6l2 2h10v13H3Z"/></svg> Dein Archiv bleibt auf deinem Rechner.</p>
    </section>
  </main>

  <div class="toast" id="toast" role="status" aria-live="polite"></div>

  <script>
    const state = {
      depth: 'deep',
      mode: 'normal',
      optimizeAi: false,
      logCursor: 0,
      isRunning: false,
    };

    const els = {
      urlsInput: document.getElementById('urlsInput'),
      urlCounter: document.getElementById('urlCounter'),
      outputInput: document.getElementById('outputInput'),
      openFolderBtn: document.getElementById('openFolderBtn'),
      useSavedCreds: document.getElementById('useSavedCreds'),
      usernameInput: document.getElementById('usernameInput'),
      passwordInput: document.getElementById('passwordInput'),
      saveCredsCheck: document.getElementById('saveCredsCheck'),
      credsBadge: document.getElementById('credsBadge'),
      scopeSelect: document.getElementById('scopeSelect'),
      depthGroup: document.getElementById('depthGroup'),
      modeGroup: document.getElementById('modeGroup'),
      youtubeCheck: document.getElementById('youtubeCheck'),
      externalCheck: document.getElementById('externalCheck'),
      aiCard: document.getElementById('aiCard'),
      aiToggleBtn: document.getElementById('aiToggleBtn'),
      logConsole: document.getElementById('logConsole'),
      coursesView: document.getElementById('coursesView'),
      tabLogBtn: document.getElementById('tabLogBtn'),
      tabCoursesBtn: document.getElementById('tabCoursesBtn'),
      refreshCoursesBtn: document.getElementById('refreshCoursesBtn'),
      clearLogBtn: document.getElementById('clearLogBtn'),
      statusDot: document.getElementById('statusDot'),
      statusText: document.getElementById('statusText'),
      progressPercent: document.getElementById('progressPercent'),
      progressFill: document.getElementById('progressFill'),
      startBtn: document.getElementById('startBtn'),
      cancelBtn: document.getElementById('cancelBtn'),
      statFiles: document.getElementById('statFiles'),
      statDescriptions: document.getElementById('statDescriptions'),
      statLinks: document.getElementById('statLinks'),
      statSkipped: document.getElementById('statSkipped'),
      statErrors: document.getElementById('statErrors'),
      versionBadge: document.getElementById('versionBadge'),
      browserBadgeText: document.getElementById('browserBadgeText'),
      toast: document.getElementById('toast'),
    };

    function showToast(msg) {
      els.toast.textContent = msg;
      els.toast.classList.add('visible');
      setTimeout(() => els.toast.classList.remove('visible'), 3200);
    }

    function parseValidUrls() {
      return els.urlsInput.value
        .split(/\\r?\\n/)
        .map(s => s.trim())
        .filter(s => (s.startsWith('http://') || s.startsWith('https://')) && /[?&]id=[^&]+/.test(s));
    }

    function updateUrlCounter() {
      const count = parseValidUrls().length;
      els.urlCounter.textContent = count === 1 ? '1 gültiger Kurs' : `${count} gültige Kurse`;
    }

    function syncCredsInputs() {
      const useSaved = els.useSavedCreds.checked;
      els.usernameInput.disabled = useSaved;
      els.passwordInput.disabled = useSaved;
    }

    function syncAiToggle() {
      els.aiToggleBtn.setAttribute('aria-pressed', String(state.optimizeAi));
      els.aiToggleBtn.textContent = state.optimizeAi ? 'EIN' : 'AUS';
      if (state.optimizeAi) {
        els.aiToggleBtn.classList.remove('btn-secondary');
        els.aiToggleBtn.classList.add('btn-primary');
        els.aiCard.classList.add('highlight');
      } else {
        els.aiToggleBtn.classList.remove('btn-primary');
        els.aiToggleBtn.classList.add('btn-secondary');
        els.aiCard.classList.remove('highlight');
      }
    }

    els.urlsInput.addEventListener('input', updateUrlCounter);
    els.useSavedCreds.addEventListener('change', syncCredsInputs);

    els.depthGroup.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-depth]');
      if (!btn) return;
      state.depth = btn.dataset.depth;
      els.depthGroup.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn));
    });

    els.modeGroup.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-mode]');
      if (!btn) return;
      state.mode = btn.dataset.mode;
      els.modeGroup.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn));
    });

    els.aiToggleBtn.addEventListener('click', () => {
      state.optimizeAi = !state.optimizeAi;
      syncAiToggle();
    });

    els.tabLogBtn.addEventListener('click', () => {
      els.tabLogBtn.classList.add('active');
      els.tabCoursesBtn.classList.remove('active');
      els.logConsole.style.display = 'block';
      els.coursesView.style.display = 'none';
      els.clearLogBtn.style.display = 'inline-flex';
      els.refreshCoursesBtn.style.display = 'none';
    });

    els.tabCoursesBtn.addEventListener('click', () => {
      els.tabCoursesBtn.classList.add('active');
      els.tabLogBtn.classList.remove('active');
      els.logConsole.style.display = 'none';
      els.coursesView.style.display = 'block';
      els.clearLogBtn.style.display = 'none';
      els.refreshCoursesBtn.style.display = 'inline-flex';
      loadCourses();
    });

    els.refreshCoursesBtn.addEventListener('click', loadCourses);

    els.clearLogBtn.addEventListener('click', async () => {
      await fetch('/api/logs/clear', { method: 'POST' });
      els.logConsole.innerHTML = '';
      state.logCursor = 0;
    });

    els.openFolderBtn.addEventListener('click', async () => {
      const res = await fetch('/api/open-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: els.outputInput.value }),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.error || 'Ordner konnte nicht geöffnet werden');
      } else {
        showToast('Ordner geöffnet: ' + data.path);
      }
    });

    els.startBtn.addEventListener('click', async () => {
      const urls = parseValidUrls();
      if (!urls.length) {
        showToast('Bitte gib mindestens eine gültige Moodle-Kurs-URL mit ?id=... ein.');
        return;
      }

      const payload = {
        urls,
        output_dir: els.outputInput.value.trim(),
        use_saved_credentials: els.useSavedCreds.checked,
        username: els.usernameInput.value.trim(),
        password: els.passwordInput.value,
        save_credentials: els.saveCredsCheck.checked,
        include: els.scopeSelect.value,
        depth: state.depth,
        mode: state.mode,
        optimize_ai: state.optimizeAi,
        download_youtube: els.youtubeCheck.checked,
        scrape_external: els.externalCheck.checked,
      };

      els.logConsole.innerHTML = '';
      state.logCursor = 0;

      const res = await fetch('/api/download/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.error || 'Fehler beim Starten');
        return;
      }
      pollStatus();
    });

    els.cancelBtn.addEventListener('click', async () => {
      await fetch('/api/download/cancel', { method: 'POST' });
      pollStatus();
    });

    function formatBytes(bytes) {
      if (!bytes) return '0 B';
      const units = ['B', 'KB', 'MB', 'GB'];
      let i = 0;
      let val = bytes;
      while (val >= 1024 && i < units.length - 1) {
        val /= 1024;
        i++;
      }
      return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
    }

    async function loadCourses() {
      const res = await fetch('/api/courses?output_dir=' + encodeURIComponent(els.outputInput.value.trim()));
      const data = await res.json();
      const courses = data.courses || [];
      els.coursesView.replaceChildren();
      if (!courses.length) {
        els.coursesView.innerHTML = '<div class="empty-state"><div class="empty-icon"><svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M3 7V5h6l2 2h10v13H3Z"/></svg></div><h4>Platz für dein Wissen.</h4><p>Noch keine Kurse in diesem Speicherort. Deine heruntergeladenen Kurse erscheinen hier.</p></div>';
        return;
      }
      for (const course of courses) {
        const item = document.createElement('div');
        item.className = 'course-item';
        const details = document.createElement('div');
        const name = document.createElement('div');
        name.className = 'course-name';
        name.textContent = course.name;
        const meta = document.createElement('div');
        meta.className = 'course-meta';
        meta.textContent = `${course.sections} Abschnitte · ${course.files} Dateien · ${formatBytes(course.size_bytes)}${course.has_ai_export ? ' · AI-Ready' : ''}`;
        details.append(name, meta);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary btn-sm';
        button.textContent = 'Ordner öffnen';
        button.addEventListener('click', () => openCoursePath(course.path));
        item.append(details, button);
        els.coursesView.appendChild(item);
      }
    }

    window.openCoursePath = async function(path) {
      await fetch('/api/open-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
    };

    async function initConfig() {
      const res = await fetch('/api/config');
      const data = await res.json();
      els.versionBadge.textContent = 'v' + data.version;
      els.outputInput.value = data.output_dir;
      if (data.browsers && data.browsers.length) {
        els.browserBadgeText.textContent = data.browsers.map(b => b.name).join(' / ') + ' erkannt';
      } else {
        els.browserBadgeText.textContent = 'Kein Browser erkannt';
      }
      if (data.has_saved_credentials) {
        els.useSavedCreds.checked = true;
        els.usernameInput.value = data.saved_username || '';
        els.credsBadge.textContent = `Gespeichert (${data.saved_username})`;
      } else {
        els.useSavedCreds.checked = false;
      }
      syncCredsInputs();
      updateUrlCounter();
    }

    async function pollStatus() {
      try {
        const res = await fetch(`/api/status?since=${state.logCursor}`);
        const data = await res.json();

        if (data.log_count < state.logCursor) {
          state.logCursor = 0;
          els.logConsole.replaceChildren();
          return;
        }
        if (data.logs && data.logs.length) {
          els.logConsole.querySelector('.empty-state')?.remove();
          for (const entry of data.logs) {
            const div = document.createElement('div');
            div.className = `log-line ${entry.level || 'default'}`;
            const ts = document.createElement('span');
            ts.className = 'ts';
            ts.textContent = entry.timestamp;
            div.appendChild(ts);
            div.appendChild(document.createTextNode(entry.text));
            els.logConsole.appendChild(div);
          }
          state.logCursor = data.log_count;
          els.logConsole.scrollTop = els.logConsole.scrollHeight;
        }

        els.statusText.textContent = data.status_text;
        els.startBtn.disabled = data.is_running;
        els.cancelBtn.disabled = !data.is_running;

        els.statusDot.className = 'status-dot';
        if (data.is_running) {
          els.statusDot.classList.add('running');
        } else if (data.status === 'completed') {
          els.statusDot.classList.add('success');
        } else if (data.status === 'error' || data.status === 'cancelled') {
          els.statusDot.classList.add('error');
        }

        const prog = data.progress || {};
        if (data.is_running) {
          if (prog.total_activities > 0) {
            const pct = Math.min(100, Math.round((prog.activity_num / prog.total_activities) * 100));
            els.progressFill.classList.remove('indeterminate');
            els.progressFill.style.width = `${pct}%`;
            els.progressPercent.textContent = `${pct}%`;
          } else {
            els.progressFill.classList.add('indeterminate');
            els.progressPercent.textContent = '';
          }
        } else {
          els.progressFill.classList.remove('indeterminate');
          els.progressFill.style.width = data.status === 'completed' ? '100%' : '0%';
          els.progressPercent.textContent = data.status === 'completed' ? '100%' : '';
        }

        const st = data.stats || {};
        els.statFiles.textContent = st.files || 0;
        els.statDescriptions.textContent = st.descriptions || 0;
        els.statLinks.textContent = st.links || 0;
        els.statSkipped.textContent = st.skipped || 0;
        els.statErrors.textContent = st.errors || 0;
        els.statErrors.style.color = (st.errors || 0) > 0 ? 'var(--red)' : 'var(--muted)';
      } catch (err) {
        // Ignore transient network errors while polling
      }
    }

    initConfig().catch(() => showToast('Verbindung fehlgeschlagen. Bitte lade die Seite neu.'));
    pollStatus();
    setInterval(pollStatus, 800);
  </script>
</body>
</html>
"""


def make_request_handler(manager: JobManager):
    """Create an HTTP request handler bound to the given JobManager."""

    class MoodleWebHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            # Keep terminal output clean from routine polling logs
            return

        def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                body = INDEX_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/config":
                saved = load_saved_credentials(manager.env_file)
                self._send_json({
                    "version": __version__,
                    "output_dir": manager.last_output_dir,
                    "saved_username": saved["username"],
                    "has_saved_credentials": bool(saved["username"] and saved["password"]),
                    "browsers": detect_installed_browsers(),
                })
                return

            if parsed.path == "/api/status":
                from urllib.parse import parse_qs

                query = parse_qs(parsed.query)
                try:
                    since = int(query.get("since", ["0"])[0])
                except ValueError:
                    since = 0
                self._send_json(manager.snapshot(since=max(0, since)))
                return

            if parsed.path == "/api/courses":
                from urllib.parse import parse_qs

                query = parse_qs(parsed.query)
                dir_str = query.get("output_dir", [manager.last_output_dir])[0] or manager.last_output_dir
                courses = list_downloaded_courses(Path(dir_str).expanduser())
                self._send_json({"courses": courses})
                return

            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            payload = self._read_json()

            if parsed.path == "/api/download/start":
                ok, message = manager.start_job(payload)
                status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
                self._send_json({"ok": ok, "message": message, "error": None if ok else message}, status=status)
                return

            if parsed.path == "/api/download/cancel":
                ok, message = manager.cancel_job()
                self._send_json({"ok": ok, "message": message})
                return

            if parsed.path == "/api/logs/clear":
                manager.clear_logs()
                self._send_json({"ok": True})
                return

            if parsed.path == "/api/open-folder":
                target = str(payload.get("path") or manager.last_output_dir)
                ok, info = open_local_folder(target)
                status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
                self._send_json({"ok": ok, "path": info if ok else None, "error": None if ok else info}, status=status)
                return

            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    return MoodleWebHandler


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    manager: JobManager | None = None,
) -> tuple[ThreadingHTTPServer, JobManager]:
    """Create a ThreadingHTTPServer bound to host:port (with automatic port fallback if busy)."""
    job_manager = manager or JobManager()
    handler_cls = make_request_handler(job_manager)
    try:
        server = ThreadingHTTPServer((host, port), handler_cls)
    except OSError:
        server = ThreadingHTTPServer((host, 0), handler_cls)
    return server, job_manager


def main() -> None:
    """Start the local Moodle Downloader web app and open it in the browser."""
    host = os.environ.get("MOODLE_DOWNLOAD_HOST", "127.0.0.1")
    port = int(os.environ.get("MOODLE_DOWNLOAD_PORT", "8765"))
    no_browser = os.environ.get("MOODLE_DOWNLOAD_NO_BROWSER", "").lower() in {"1", "true", "yes"}

    server, _ = create_server(host=host, port=port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}"

    print("=" * 54)
    print(f"  🌐 Moodle Downloader Web-App v{__version__}")
    print("=" * 54)
    print(f"  Lokale Adresse: {url}")
    print("  Drücke Strg+C (Ctrl+C), um den Server zu beenden.")
    print("=" * 54)

    if not no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeende Server …")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
