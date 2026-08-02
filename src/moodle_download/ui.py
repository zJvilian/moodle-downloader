"""Polished desktop interface for Moodle Downloader."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import CREDENTIALS_FILE, DOWNLOADS_DIR, __version__


class Palette:
    BACKGROUND = "#08111F"
    SIDEBAR = "#0C1728"
    CARD = "#111F33"
    CARD_ALT = "#15263D"
    BORDER = "#263A57"
    BORDER_ACTIVE = "#3B5B78"
    TEXT = "#F3F7FC"
    MUTED = "#91A4BD"
    FAINT = "#647892"
    PRIMARY = "#55D6C2"
    PRIMARY_HOVER = "#71E1CF"
    PRIMARY_DARK = "#072C2B"
    BLUE = "#79AFFF"
    GREEN = "#6EE7A8"
    AMBER = "#F7C873"
    RED = "#FF7A90"


class MoodleDownloaderUI:
    """Responsive two-pane Tk interface."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Moodle Downloader")
        self.root.geometry("1120x780")
        self.root.minsize(920, 650)
        self.root.configure(bg=Palette.BACKGROUND)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.depth_var = tk.StringVar(value="deep")
        self.include_var = tk.StringVar(value="all")
        self.scope_label_var = tk.StringVar(value="Alles herunterladen")
        self.update_var = tk.BooleanVar(value=False)
        self.optimize_ai_var = tk.BooleanVar(value=False)
        self.download_youtube_var = tk.BooleanVar(value=False)
        self.scrape_external_var = tk.BooleanVar(value=True)
        self.output_var = tk.StringVar(value=str(DOWNLOADS_DIR))
        self.status_var = tk.StringVar(value="Bereit für den Download")
        self.url_count_var = tk.StringVar(value="1 Kurs")
        self._saved_username = ""
        self._saved_password = ""
        self._process: subprocess.Popen | None = None
        self.is_running = False

        self._load_credentials()
        self.use_creds_var = tk.BooleanVar(value=bool(self._saved_username))
        self.username_var = tk.StringVar(value=self._saved_username)
        self.password_var = tk.StringVar(value=self._saved_password)

        self._configure_styles()
        self._build_ui()

    def _load_credentials(self) -> None:
        if not CREDENTIALS_FILE.exists():
            return
        try:
            credentials = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
            self._saved_username = credentials.get("username", "")
            self._saved_password = credentials.get("password", "")
        except (OSError, json.JSONDecodeError):
            pass

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor=Palette.CARD_ALT,
            background=Palette.PRIMARY,
            bordercolor=Palette.CARD_ALT,
            lightcolor=Palette.PRIMARY,
            darkcolor=Palette.PRIMARY,
            thickness=5,
        )
        style.configure(
            "App.TCombobox",
            fieldbackground=Palette.CARD_ALT,
            background=Palette.CARD_ALT,
            foreground=Palette.TEXT,
            arrowcolor=Palette.MUTED,
            bordercolor=Palette.BORDER,
            lightcolor=Palette.BORDER,
            darkcolor=Palette.BORDER,
            padding=7,
        )
        style.map(
            "App.TCombobox",
            fieldbackground=[("readonly", Palette.CARD_ALT)],
            foreground=[("readonly", Palette.TEXT)],
            selectbackground=[("readonly", Palette.CARD_ALT)],
            selectforeground=[("readonly", Palette.TEXT)],
        )
        style.configure(
            "App.TCheckbutton",
            background=Palette.CARD,
            foreground=Palette.TEXT,
            font=("Segoe UI", 9),
        )
        style.map(
            "App.TCheckbutton",
            background=[("active", Palette.CARD)],
            foreground=[("disabled", Palette.FAINT), ("active", Palette.TEXT)],
            indicatorcolor=[("selected", Palette.PRIMARY), ("!selected", Palette.CARD_ALT)],
        )
        style.configure(
            "App.TRadiobutton",
            background=Palette.CARD,
            foreground=Palette.MUTED,
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "App.TRadiobutton",
            background=[("active", Palette.CARD)],
            foreground=[("selected", Palette.PRIMARY), ("active", Palette.TEXT)],
            indicatorcolor=[("selected", Palette.PRIMARY), ("!selected", Palette.CARD_ALT)],
        )

    def _build_ui(self) -> None:
        self._build_header()

        body = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            bg=Palette.BACKGROUND,
            sashwidth=8,
            sashrelief=tk.FLAT,
            bd=0,
            showhandle=False,
        )
        body.pack(fill=tk.BOTH, expand=True, padx=22, pady=(0, 20))

        left_shell = tk.Frame(body, bg=Palette.BACKGROUND, width=430)
        right = tk.Frame(body, bg=Palette.BACKGROUND)
        body.add(left_shell, minsize=370, width=430, stretch="never")
        body.add(right, minsize=460, stretch="always")

        self._build_scrollable_settings(left_shell)
        self._build_activity_panel(right)

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=Palette.BACKGROUND)
        header.pack(fill=tk.X, padx=24, pady=(20, 16))

        mark = tk.Label(
            header,
            text="M",
            width=3,
            height=1,
            bg=Palette.PRIMARY,
            fg=Palette.PRIMARY_DARK,
            font=("Segoe UI", 18, "bold"),
        )
        mark.pack(side=tk.LEFT, padx=(0, 12))

        title_group = tk.Frame(header, bg=Palette.BACKGROUND)
        title_group.pack(side=tk.LEFT)
        tk.Label(
            title_group,
            text="Moodle Downloader",
            bg=Palette.BACKGROUND,
            fg=Palette.TEXT,
            font=("Segoe UI Semibold", 19),
        ).pack(anchor="w")
        tk.Label(
            title_group,
            text="Komplette Kurse. Saubere Struktur. Bereit für dich und deine AI.",
            bg=Palette.BACKGROUND,
            fg=Palette.MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        version = tk.Label(
            header,
            text=f"v{__version__}",
            bg=Palette.CARD,
            fg=Palette.MUTED,
            font=("Segoe UI Semibold", 8),
            padx=10,
            pady=5,
        )
        version.pack(side=tk.RIGHT)

    def _build_scrollable_settings(self, parent: tk.Frame) -> None:
        canvas = tk.Canvas(parent, bg=Palette.BACKGROUND, bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        content = tk.Frame(canvas, bg=Palette.BACKGROUND)
        window = canvas.create_window((0, 0), window=content, anchor="nw")

        content.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        def scroll_settings(event):
            pointer_x, pointer_y = self.root.winfo_pointerxy()
            left = canvas.winfo_rootx()
            top = canvas.winfo_rooty()
            if left <= pointer_x <= left + canvas.winfo_width() and top <= pointer_y <= top + canvas.winfo_height():
                canvas.yview_scroll(int(-event.delta / 120), "units")

        self.root.bind_all("<MouseWheel>", scroll_settings, add="+")

        self._build_course_card(content)
        self._build_destination_card(content)
        self._build_access_card(content)
        self._build_options_card(content)
        self._build_ai_card(content)
        tk.Frame(content, bg=Palette.BACKGROUND, height=8).pack()

    def _card(self, parent: tk.Widget, title: str, subtitle: str = "") -> tuple[tk.Frame, tk.Frame]:
        card = tk.Frame(
            parent,
            bg=Palette.CARD,
            highlightbackground=Palette.BORDER,
            highlightthickness=1,
            bd=0,
        )
        card.pack(fill=tk.X, padx=(0, 8), pady=(0, 12))
        heading = tk.Frame(card, bg=Palette.CARD)
        heading.pack(fill=tk.X, padx=16, pady=(13, 8 if subtitle else 11))
        tk.Label(
            heading,
            text=title,
            bg=Palette.CARD,
            fg=Palette.TEXT,
            font=("Segoe UI Semibold", 10),
        ).pack(side=tk.LEFT)
        if subtitle:
            tk.Label(
                heading,
                text=subtitle,
                bg=Palette.CARD,
                fg=Palette.FAINT,
                font=("Segoe UI", 8),
            ).pack(side=tk.RIGHT)
        content = tk.Frame(card, bg=Palette.CARD)
        content.pack(fill=tk.X, padx=16, pady=(0, 14))
        return card, content

    def _entry(self, parent: tk.Widget, variable: tk.Variable, *, show: str | None = None) -> tk.Entry:
        return tk.Entry(
            parent,
            textvariable=variable,
            show=show,
            bg=Palette.CARD_ALT,
            fg=Palette.TEXT,
            insertbackground=Palette.TEXT,
            selectbackground=Palette.BORDER_ACTIVE,
            disabledbackground=Palette.CARD,
            disabledforeground=Palette.FAINT,
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            highlightbackground=Palette.BORDER,
            highlightcolor=Palette.PRIMARY,
            highlightthickness=1,
        )

    def _build_course_card(self, parent: tk.Widget) -> None:
        _, content = self._card(parent, "Kursquellen", "eine URL pro Zeile")
        self.url_text = scrolledtext.ScrolledText(
            content,
            height=4,
            wrap=tk.WORD,
            bg=Palette.CARD_ALT,
            fg=Palette.TEXT,
            insertbackground=Palette.TEXT,
            selectbackground=Palette.BORDER_ACTIVE,
            font=("Cascadia Mono", 9),
            relief=tk.FLAT,
            padx=10,
            pady=8,
            highlightbackground=Palette.BORDER,
            highlightcolor=Palette.PRIMARY,
            highlightthickness=1,
        )
        self.url_text.pack(fill=tk.X)
        self.url_text.insert("1.0", "https://moodle.hs-augsburg.de/course/view.php?id=")
        self.url_text.bind("<KeyRelease>", self._update_url_count)
        tk.Label(
            content,
            textvariable=self.url_count_var,
            bg=Palette.CARD,
            fg=Palette.PRIMARY,
            font=("Segoe UI Semibold", 8),
        ).pack(anchor="e", pady=(6, 0))

    def _build_destination_card(self, parent: tk.Widget) -> None:
        _, content = self._card(parent, "Speicherort")
        row = tk.Frame(content, bg=Palette.CARD)
        row.pack(fill=tk.X)
        entry = self._entry(row, self.output_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=7)
        self._small_button(row, "Auswählen", self._browse).pack(side=tk.LEFT, padx=(8, 0))

    def _build_access_card(self, parent: tk.Widget) -> None:
        _, content = self._card(parent, "Moodle-Zugang")
        self.creds_check = ttk.Checkbutton(
            content,
            text="Gespeicherte credentials.json verwenden",
            variable=self.use_creds_var,
            style="App.TCheckbutton",
            command=self._toggle_creds,
        )
        self.creds_check.pack(anchor="w", pady=(0, 8))

        self.creds_frame = tk.Frame(content, bg=Palette.CARD)
        self.creds_frame.pack(fill=tk.X)
        tk.Label(
            self.creds_frame,
            text="Benutzername",
            bg=Palette.CARD,
            fg=Palette.FAINT,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(0, 4))
        self.username_entry = self._entry(self.creds_frame, self.username_var)
        self.username_entry.pack(fill=tk.X, ipady=6, pady=(0, 7))
        tk.Label(
            self.creds_frame,
            text="Passwort",
            bg=Palette.CARD,
            fg=Palette.FAINT,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(0, 4))
        self.password_entry = self._entry(self.creds_frame, self.password_var, show="•")
        self.password_entry.pack(fill=tk.X, ipady=6)
        self._toggle_creds()

    def _build_options_card(self, parent: tk.Widget) -> None:
        _, content = self._card(parent, "Download-Optionen")
        scopes = {
            "Alles herunterladen": "all",
            "Nur Dateien": "file",
            "Nur Beschreibungen": "description",
            "Nur Foren": "forum",
            "Nur Quizzes": "quiz",
            "Nur Bücher": "book",
            "Nur Links": "link",
        }
        scope = ttk.Combobox(
            content,
            textvariable=self.scope_label_var,
            values=list(scopes),
            state="readonly",
            style="App.TCombobox",
        )
        scope.pack(fill=tk.X)
        scope.bind("<<ComboboxSelected>>", lambda _: self.include_var.set(scopes[self.scope_label_var.get()]))

        depth_row = tk.Frame(content, bg=Palette.CARD)
        depth_row.pack(fill=tk.X, pady=(11, 4))
        tk.Label(depth_row, text="Scraping", bg=Palette.CARD, fg=Palette.MUTED, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        ttk.Radiobutton(
            depth_row, text="Tief", variable=self.depth_var, value="deep", style="App.TRadiobutton"
        ).pack(side=tk.RIGHT, padx=(12, 0))
        ttk.Radiobutton(
            depth_row, text="Nur Übersicht", variable=self.depth_var, value="shallow", style="App.TRadiobutton"
        ).pack(side=tk.RIGHT)
        ttk.Checkbutton(
            content,
            text="Nur neue oder geänderte Dateien übertragen",
            variable=self.update_var,
            style="App.TCheckbutton",
        ).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(
            content,
            text="YouTube-Videos herunterladen (sonst nur Link)",
            variable=self.download_youtube_var,
            style="App.TCheckbutton",
        ).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(
            content,
            text="Externe Webseiten als Markdown archivieren",
            variable=self.scrape_external_var,
            style="App.TCheckbutton",
        ).pack(anchor="w", pady=(8, 0))

    def _build_ai_card(self, parent: tk.Widget) -> None:
        self.ai_card = tk.Frame(
            parent,
            bg=Palette.CARD,
            highlightbackground=Palette.BORDER,
            highlightthickness=1,
        )
        self.ai_card.pack(fill=tk.X, padx=(0, 8), pady=(0, 12))
        inner = tk.Frame(self.ai_card, bg=Palette.CARD)
        inner.pack(fill=tk.X, padx=16, pady=14)

        copy = tk.Frame(inner, bg=Palette.CARD)
        copy.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(copy, text="AI-ready export", bg=Palette.CARD, fg=Palette.TEXT, font=("Segoe UI Semibold", 10)).pack(anchor="w")
        tk.Label(
            copy,
            text="Erstellt Strukturkarte, Manifest und\ngeordnete Kontext-Pakete für AI-Bots.",
            justify=tk.LEFT,
            bg=Palette.CARD,
            fg=Palette.MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(4, 0))
        self.ai_toggle = tk.Button(
            inner,
            command=self._toggle_ai,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 8),
            padx=12,
            pady=7,
        )
        self.ai_toggle.pack(side=tk.RIGHT, padx=(10, 0))
        self._sync_ai_button()

    def _build_activity_panel(self, parent: tk.Frame) -> None:
        panel = tk.Frame(
            parent,
            bg=Palette.CARD,
            highlightbackground=Palette.BORDER,
            highlightthickness=1,
        )
        panel.pack(fill=tk.BOTH, expand=True)

        toolbar = tk.Frame(panel, bg=Palette.CARD)
        toolbar.pack(fill=tk.X, padx=18, pady=(15, 11))
        tk.Label(toolbar, text="Aktivität", bg=Palette.CARD, fg=Palette.TEXT, font=("Segoe UI Semibold", 11)).pack(side=tk.LEFT)
        self._small_button(toolbar, "Log leeren", self._clear_log).pack(side=tk.RIGHT)
        self._small_button(toolbar, "Ordner öffnen", self._open_output).pack(side=tk.RIGHT, padx=(0, 8))

        divider = tk.Frame(panel, bg=Palette.BORDER, height=1)
        divider.pack(fill=tk.X)

        self.log_text = scrolledtext.ScrolledText(
            panel,
            wrap=tk.WORD,
            bg=Palette.SIDEBAR,
            fg=Palette.MUTED,
            insertbackground=Palette.TEXT,
            selectbackground=Palette.BORDER_ACTIVE,
            font=("Cascadia Mono", 9),
            relief=tk.FLAT,
            state=tk.DISABLED,
            padx=14,
            pady=12,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=14, pady=(13, 10))
        self.log_text.tag_configure("success", foreground=Palette.GREEN)
        self.log_text.tag_configure("error", foreground=Palette.RED)
        self.log_text.tag_configure("info", foreground=Palette.BLUE)
        self.log_text.tag_configure("warning", foreground=Palette.AMBER)

        footer = tk.Frame(panel, bg=Palette.CARD)
        footer.pack(fill=tk.X, padx=18, pady=(0, 17))
        status_row = tk.Frame(footer, bg=Palette.CARD)
        status_row.pack(fill=tk.X, pady=(0, 8))
        self.status_dot = tk.Label(status_row, text="●", bg=Palette.CARD, fg=Palette.PRIMARY, font=("Segoe UI", 8))
        self.status_dot.pack(side=tk.LEFT)
        tk.Label(
            status_row,
            textvariable=self.status_var,
            bg=Palette.CARD,
            fg=Palette.MUTED,
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(6, 0))

        self.progress = ttk.Progressbar(footer, mode="indeterminate", style="App.Horizontal.TProgressbar")
        self.progress.pack(fill=tk.X, pady=(0, 12))

        action_row = tk.Frame(footer, bg=Palette.CARD)
        action_row.pack(fill=tk.X)
        self.start_btn = self._primary_button(action_row, "Download starten", self._start)
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.cancel_btn = self._secondary_button(action_row, "Abbrechen", self._cancel)
        self.cancel_btn.pack(side=tk.LEFT, padx=(9, 0))
        self.cancel_btn.configure(state=tk.DISABLED)

    def _small_button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=Palette.CARD_ALT,
            fg=Palette.MUTED,
            activebackground=Palette.BORDER_ACTIVE,
            activeforeground=Palette.TEXT,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 8),
            padx=10,
            pady=7,
        )
        return button

    def _primary_button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=Palette.PRIMARY,
            fg=Palette.PRIMARY_DARK,
            activebackground=Palette.PRIMARY_HOVER,
            activeforeground=Palette.PRIMARY_DARK,
            disabledforeground=Palette.FAINT,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 10),
            pady=11,
        )
        button.bind("<Enter>", lambda _: button.configure(bg=Palette.PRIMARY_HOVER) if button["state"] != tk.DISABLED else None)
        button.bind("<Leave>", lambda _: button.configure(bg=Palette.PRIMARY) if button["state"] != tk.DISABLED else None)
        return button

    def _secondary_button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=Palette.CARD_ALT,
            fg=Palette.TEXT,
            activebackground=Palette.BORDER_ACTIVE,
            activeforeground=Palette.TEXT,
            disabledforeground=Palette.FAINT,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 9),
            padx=14,
            pady=11,
        )

    def _update_url_count(self, _event=None) -> None:
        count = len(self._valid_urls())
        self.url_count_var.set(f"{count} Kurs" if count == 1 else f"{count} Kurse")

    def _valid_urls(self) -> list[str]:
        lines = self.url_text.get("1.0", tk.END).splitlines()
        return [line.strip() for line in lines if line.strip().startswith(("http://", "https://")) and "id=" in line]

    def _toggle_creds(self) -> None:
        use_saved = self.use_creds_var.get() and bool(self._saved_username)
        state = tk.DISABLED if use_saved else tk.NORMAL
        self.username_entry.configure(state=state)
        self.password_entry.configure(state=state)

    def _toggle_ai(self) -> None:
        self.optimize_ai_var.set(not self.optimize_ai_var.get())
        self._sync_ai_button()

    def _sync_ai_button(self) -> None:
        enabled = self.optimize_ai_var.get()
        self.ai_toggle.configure(
            text="EIN" if enabled else "AUS",
            bg=Palette.PRIMARY if enabled else Palette.CARD_ALT,
            fg=Palette.PRIMARY_DARK if enabled else Palette.MUTED,
            activebackground=Palette.PRIMARY_HOVER if enabled else Palette.BORDER_ACTIVE,
            activeforeground=Palette.PRIMARY_DARK if enabled else Palette.TEXT,
        )
        self.ai_card.configure(highlightbackground=Palette.PRIMARY if enabled else Palette.BORDER)

    def _browse(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.output_var.get())
        if folder:
            self.output_var.set(folder)

    def _open_output(self) -> None:
        folder = Path(self.output_var.get()).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as error:
            messagebox.showerror("Ordner konnte nicht geöffnet werden", str(error))

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _log(self, message: str, tag: str | None = None) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n", tag or ())
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _credentials(self) -> tuple[str, str]:
        if self.use_creds_var.get() and self._saved_username:
            return self._saved_username, self._saved_password
        return self.username_var.get().strip(), self.password_var.get()

    def _start(self) -> None:
        urls = self._valid_urls()
        if not urls:
            messagebox.showerror("Kurs-URL fehlt", "Bitte füge mindestens eine gültige Moodle-Kurs-URL ein.")
            return
        username, password = self._credentials()
        if not username or not password:
            messagebox.showerror("Login fehlt", "Bitte gib Benutzername und Passwort ein.")
            return
        output = Path(self.output_var.get()).expanduser()
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            messagebox.showerror("Speicherort ungültig", str(error))
            return

        arguments = [
            sys.executable,
            "-m",
            "moodle_download",
            "--output",
            str(output),
            "--depth",
            self.depth_var.get(),
        ]
        for url in urls:
            arguments.extend(["--url", url])
        if self.include_var.get() != "all":
            arguments.extend(["--include", self.include_var.get()])
        if self.update_var.get():
            arguments.append("--update")
        if self.optimize_ai_var.get():
            arguments.append("--optimize-ai")
        if self.download_youtube_var.get():
            arguments.append("--download-youtube")
        if not self.scrape_external_var.get():
            arguments.append("--no-scrape-external")

        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).parent.parent)
        environment["PYTHONUNBUFFERED"] = "1"
        environment["MOODLE_DOWNLOAD_USERNAME"] = username
        environment["MOODLE_DOWNLOAD_PASSWORD"] = password

        self.is_running = True
        self.start_btn.configure(state=tk.DISABLED)
        self.cancel_btn.configure(state=tk.NORMAL)
        self.progress.start(12)
        self.status_dot.configure(fg=Palette.AMBER)
        self.status_var.set(f"Download läuft · {len(urls)} Kurs{'e' if len(urls) != 1 else ''}")
        self._clear_log()
        self._log("Download wird vorbereitet …", "info")
        threading.Thread(target=self._run, args=(arguments, environment), daemon=True).start()

    def _run(self, arguments: list[str], environment: dict) -> None:
        try:
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self._process = subprocess.Popen(
                arguments,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=environment,
                startupinfo=startupinfo,
            )
            assert self._process.stdout is not None
            for line in self._process.stdout:
                line = line.rstrip()
                if not line:
                    continue
                tag = None
                if "✅" in line or "abgeschlossen" in line.lower():
                    tag = "success"
                elif "❌" in line or "fehler" in line.lower():
                    tag = "error"
                elif "⚠" in line or "übersprungen" in line.lower():
                    tag = "warning"
                elif any(marker in line for marker in ("📚", "📁", "📂", "🧠")):
                    tag = "info"
                self.root.after(0, self._log, line, tag)
            return_code = self._process.wait()
            self.root.after(0, self._done, return_code == 0)
        except Exception as error:
            self.root.after(0, self._log, f"❌ {error}", "error")
            self.root.after(0, self._done, False)
        finally:
            self._process = None

    def _cancel(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self.status_var.set("Download wird abgebrochen …")
            self.cancel_btn.configure(state=tk.DISABLED)

    def _done(self, success: bool) -> None:
        self.is_running = False
        self.start_btn.configure(state=tk.NORMAL, bg=Palette.PRIMARY)
        self.cancel_btn.configure(state=tk.DISABLED)
        self.progress.stop()
        if success:
            self.status_dot.configure(fg=Palette.GREEN)
            self.status_var.set("Download vollständig abgeschlossen")
            self._log("Alle Aufgaben wurden abgeschlossen.", "success")
        else:
            self.status_dot.configure(fg=Palette.RED)
            self.status_var.set("Download beendet · Log prüfen")
            self._log("Der Vorgang wurde beendet oder ist fehlgeschlagen.", "error")

    def _on_close(self) -> None:
        if self.is_running and not messagebox.askyesno("Download läuft", "Download abbrechen und Fenster schließen?"):
            return
        if self._process and self._process.poll() is None:
            self._process.terminate()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    MoodleDownloaderUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
