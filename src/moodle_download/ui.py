"""Moodle Downloader - GUI."""

import json
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path

from . import CREDENTIALS_FILE, DOWNLOADS_DIR
from .cli import main as cli_main


class GlassColors:
    """Color palette."""
    BASE = "#11111b"
    MANTLE = "#181825"
    CRUST = "#1e1e2e"
    SURFACE0 = "#313244"
    SURFACE1 = "#45475a"
    SURFACE2 = "#585b70"
    OVERLAY0 = "#6c7086"
    OVERLAY1 = "#7f849c"
    TEXT = "#cdd6f4"
    SUBTEXT0 = "#bac2de"
    SUBTEXT1 = "#a6adc8"
    BLUE = "#89b4fa"
    SAPPHIRE = "#74c7ec"
    SKY = "#89dceb"
    GREEN = "#a6e3a1"
    YELLOW = "#f9e2af"
    RED = "#f38ba8"
    MAUVE = "#cba6f7"


class MoodleDownloaderUI:
    """Main UI class."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Moodle Kurs-Downloader")
        self.root.geometry("800x1000")
        self.root.configure(bg=GlassColors.BASE)
        
        # Variables
        self.depth_var = tk.StringVar(value="deep")
        self.include_var = tk.StringVar(value="all")
        self.update_var = tk.BooleanVar(value=False)
        self.use_creds_var = tk.BooleanVar(value=True)
        
        # Load credentials
        self._saved_username = ""
        self._saved_password = ""
        self._load_credentials()
        
        # Build UI
        self._build_ui()
        
        self.is_running = False
    
    def _load_credentials(self):
        if CREDENTIALS_FILE.exists():
            try:
                with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
                    creds = json.load(f)
                    self._saved_username = creds.get('username', '')
                    self._saved_password = creds.get('password', '')
            except Exception:
                pass
    
    def _build_ui(self):
        main = tk.Frame(self.root, bg=GlassColors.BASE)
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        tk.Label(main, text="📚 Moodle Kurs-Downloader",
                bg=GlassColors.BASE, fg=GlassColors.BLUE,
                font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        tk.Label(main, text="Lade alle Kursinhalte herunter",
                bg=GlassColors.BASE, fg=GlassColors.OVERLAY1,
                font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 20))
        
        # URL
        url_frame = tk.LabelFrame(main, text="Kurs-URL(s)", bg=GlassColors.CRUST,
                                 fg=GlassColors.BLUE, font=('Segoe UI', 11, 'bold'))
        url_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(url_frame, text="Eine URL pro Zeile",
                bg=GlassColors.CRUST, fg=GlassColors.OVERLAY1,
                font=('Segoe UI', 9)).pack(anchor='w', padx=10, pady=(5, 0))
        
        self.url_text = scrolledtext.ScrolledText(url_frame, height=4,
                                                 bg=GlassColors.SURFACE0,
                                                 fg=GlassColors.TEXT,
                                                 insertbackground=GlassColors.TEXT,
                                                 font=('Consolas', 10),
                                                 relief=tk.FLAT)
        self.url_text.pack(fill=tk.X, padx=10, pady=5)
        self.url_text.insert('1.0', 'https://moodle.hs-augsburg.de/course/view.php?id=')
        
        # Output
        output_frame = tk.LabelFrame(main, text="Speicherort", bg=GlassColors.CRUST,
                                    fg=GlassColors.BLUE, font=('Segoe UI', 11, 'bold'))
        output_frame.pack(fill=tk.X, pady=(0, 10))
        
        output_row = tk.Frame(output_frame, bg=GlassColors.CRUST)
        output_row.pack(fill=tk.X, padx=10, pady=5)
        
        self.output_var = tk.StringVar(value=str(DOWNLOADS_DIR))
        tk.Entry(output_row, textvariable=self.output_var,
                bg=GlassColors.SURFACE0, fg=GlassColors.TEXT,
                font=('Segoe UI', 10), relief=tk.FLAT).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Button(output_row, text="Durchsuchen", bg=GlassColors.SURFACE1,
                 fg=GlassColors.TEXT, relief=tk.FLAT, font=('Segoe UI', 9),
                 command=self._browse).pack(side=tk.LEFT, padx=(5, 0))
        
        # Login & Options side by side
        bottom_row = tk.Frame(main, bg=GlassColors.BASE)
        bottom_row.pack(fill=tk.X, pady=(0, 10))
        
        # Login (left)
        login_frame = tk.LabelFrame(bottom_row, text="Login", bg=GlassColors.CRUST,
                                   fg=GlassColors.BLUE, font=('Segoe UI', 11, 'bold'))
        login_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        tk.Checkbutton(login_frame, text=" credentials.json verwenden",
                      variable=self.use_creds_var, bg=GlassColors.CRUST,
                      fg=GlassColors.TEXT, selectcolor=GlassColors.SURFACE0,
                      activebackground=GlassColors.CRUST,
                      command=self._toggle_creds).pack(anchor='w', padx=10, pady=5)
        
        self.creds_frame = tk.Frame(login_frame, bg=GlassColors.CRUST)
        self.creds_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        tk.Label(self.creds_frame, text="Benutzername:", bg=GlassColors.CRUST,
                fg=GlassColors.TEXT).grid(row=0, column=0, sticky='w')
        self.username_var = tk.StringVar(value=self._saved_username)
        tk.Entry(self.creds_frame, textvariable=self.username_var,
                bg=GlassColors.SURFACE0, fg=GlassColors.TEXT,
                font=('Segoe UI', 10), relief=tk.FLAT).grid(row=0, column=1, sticky='ew', padx=5)
        
        tk.Label(self.creds_frame, text="Passwort:", bg=GlassColors.CRUST,
                fg=GlassColors.TEXT).grid(row=1, column=0, sticky='w', pady=(5, 0))
        self.password_var = tk.StringVar(value=self._saved_password)
        tk.Entry(self.creds_frame, textvariable=self.password_var, show='•',
                bg=GlassColors.SURFACE0, fg=GlassColors.TEXT,
                font=('Segoe UI', 10), relief=tk.FLAT).grid(row=1, column=1, sticky='ew', padx=5, pady=(5, 0))
        
        if self.use_creds_var.get() and self._saved_username:
            self.creds_frame.pack_forget()
        
        # Options (right)
        options_frame = tk.LabelFrame(bottom_row, text="Optionen", bg=GlassColors.CRUST,
                                     fg=GlassColors.BLUE, font=('Segoe UI', 11, 'bold'))
        options_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        tk.Label(options_frame, text="Was herunterladen:", bg=GlassColors.CRUST,
                fg=GlassColors.TEXT, font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=10, pady=(5, 0))
        
        types_frame = tk.Frame(options_frame, bg=GlassColors.CRUST)
        types_frame.pack(fill=tk.X, padx=10, pady=5)
        
        for icon, text, value in [("📦", "Alles", "all"), ("📄", "Dateien", "file"),
                                  ("📝", "Beschr.", "description"), ("💬", "Foren", "forum"),
                                  ("❓", "Quizzes", "quiz"), ("📚", "Bücher", "book"), ("🔗", "Links", "link")]:
            tk.Radiobutton(types_frame, text=f" {icon} {text}", variable=self.include_var,
                          value=value, bg=GlassColors.CRUST, fg=GlassColors.TEXT,
                          selectcolor=GlassColors.SURFACE0, activebackground=GlassColors.CRUST,
                          font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=3)
        
        # Depth
        depth_frame = tk.Frame(options_frame, bg=GlassColors.CRUST)
        depth_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        tk.Label(depth_frame, text="Tiefe:", bg=GlassColors.CRUST, fg=GlassColors.TEXT,
                font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT)
        tk.Radiobutton(depth_frame, text=" Deep", variable=self.depth_var, value="deep",
                      bg=GlassColors.CRUST, fg=GlassColors.TEXT,
                      selectcolor=GlassColors.SURFACE0).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(depth_frame, text=" Shallow", variable=self.depth_var, value="shallow",
                      bg=GlassColors.CRUST, fg=GlassColors.TEXT,
                      selectcolor=GlassColors.SURFACE0).pack(side=tk.LEFT)
        
        # Update mode
        tk.Checkbutton(options_frame, text=" Nur neue/geaenderte Dateien (Update-Modus)",
                      variable=self.update_var, bg=GlassColors.CRUST,
                      fg=GlassColors.TEXT, selectcolor=GlassColors.SURFACE0,
                      activebackground=GlassColors.CRUST).pack(anchor='w', padx=10, pady=(0, 10))
        
        # Start button
        self.start_btn = tk.Button(main, text="🚀 Download starten",
                                  bg=GlassColors.BLUE, fg=GlassColors.BASE,
                                  font=('Segoe UI', 12, 'bold'), relief=tk.FLAT,
                                  padx=30, pady=10, command=self._start)
        self.start_btn.pack(pady=10)
        
        # Progress
        self.progress = ttk.Progressbar(main, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 10))
        
        # Log
        log_frame = tk.LabelFrame(main, text="Log", bg=GlassColors.CRUST,
                                 fg=GlassColors.BLUE, font=('Segoe UI', 11, 'bold'))
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20,
                                                 bg=GlassColors.MANTLE,
                                                 fg=GlassColors.SUBTEXT0,
                                                 font=('Cascadia Code', 9),
                                                 relief=tk.FLAT, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text.tag_configure('success', foreground=GlassColors.GREEN)
        self.log_text.tag_configure('error', foreground=GlassColors.RED)
        self.log_text.tag_configure('info', foreground=GlassColors.BLUE)
        
        # Status
        self.status_var = tk.StringVar(value="Bereit")
        tk.Label(main, textvariable=self.status_var, bg=GlassColors.BASE,
                fg=GlassColors.OVERLAY1, font=('Segoe UI', 9)).pack(anchor='w')
    
    def _toggle_creds(self):
        """Show/hide credentials fields."""
        if self.use_creds_var.get() and self._saved_username:
            self.creds_frame.pack_forget()
        else:
            self.creds_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
    
    def _browse(self):
        folder = filedialog.askdirectory(initialdir=self.output_var.get())
        if folder:
            self.output_var.set(folder)
    
    def _log(self, msg, tag=None):
        self.log_text.configure(state=tk.NORMAL)
        if tag:
            self.log_text.insert(tk.END, msg + '\n', tag)
        else:
            self.log_text.insert(tk.END, msg + '\n')
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
    
    def _start(self):
        urls_text = self.url_text.get('1.0', tk.END).strip()
        urls = [u.strip() for u in urls_text.split('\n') if u.strip() and 'id=' in u]
        
        if not urls:
            messagebox.showerror("Fehler", "Keine gültige URL gefunden.")
            return
        
        if self.use_creds_var.get() and self._saved_username:
            username = self._saved_username
            password = self._saved_password
        else:
            username = self.username_var.get()
            password = self.password_var.get()
            if not username or not password:
                messagebox.showerror("Fehler", "Bitte Benutzername und Passwort eingeben.")
                return
        
        cmd_args = [sys.executable, '-m', 'moodle_download',
                   '--output', self.output_var.get(),
                   '--depth', self.depth_var.get(),
                   '--username', username, '--password', password]
        
        for url in urls:
            cmd_args.extend(['--url', url])
        
        include = self.include_var.get()
        if include != 'all':
            cmd_args.extend(['--include', include])
        
        if self.update_var.get():
            cmd_args.append('--update')
        
        self.is_running = True
        self.start_btn.configure(state='disabled')
        self.progress.start(15)
        self.status_var.set(f"⏳ Download läuft... ({len(urls)} Kurse)")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self._log(f"🚀 Starte Download für {len(urls)} Kurs(e)...", 'info')
        
        import subprocess
        import os
        
        env = os.environ.copy()
        env['PYTHONPATH'] = str(Path(__file__).parent.parent)
        
        thread = threading.Thread(target=self._run, args=(cmd_args, env), daemon=True)
        thread.start()
    
    def _run(self, cmd_args, env):
        import subprocess
        try:
            process = subprocess.Popen(cmd_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding='utf-8', errors='replace',
                                      bufsize=1, env=env)
            
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    tag = None
                    if '✅' in line or 'abgeschlossen' in line:
                        tag = 'success'
                    elif '❌' in line or 'Fehler' in line:
                        tag = 'error'
                    elif '📚' in line or '📁' in line or '📂' in line:
                        tag = 'info'
                    self.root.after(0, self._log, line, tag)
            
            process.wait()
            self.root.after(0, self._done, process.returncode == 0)
        except Exception as e:
            self.root.after(0, self._log, f"❌ {str(e)}", 'error')
            self.root.after(0, self._done, False)
    
    def _done(self, success):
        self.is_running = False
        self.start_btn.configure(state='normal')
        self.progress.stop()
        
        if success:
            self.status_var.set("✅ Abgeschlossen!")
            self._log("✅ Download abgeschlossen!", 'success')
        else:
            self.status_var.set("❌ Fehler")
            self._log("❌ Fehler!", 'error')


def main():
    root = tk.Tk()
    app = MoodleDownloaderUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
