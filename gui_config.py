"""Open Studio Bot Retro Desktop Config GUI — Game Boy 8-bit edition.

Run: .venv\\Scripts\\python.exe gui_config.py

Sets: BOT_TOKEN (Telegram Bot API), ALLOWED_CHAT_ID, TIKTOK_HANDLE,
      WATERMARK_HANDLE, Waterfox profile + cookies, Templates 00/01.
Saves to .env + jobs/handle.json. Bottom CLI pops when deps are downloading.
"""
import importlib.util
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:
    print("tkinter not available")
    sys.exit(1)

try:
    import winsound
    # soft pop: lower freq + shorter duration - keyboard feel, not alarm
    def beep(): winsound.Beep(520, 35)  # was 800Hz 80ms; now soft 520Hz 35ms
except ImportError:
    def beep(): pass

REPO = Path(__file__).resolve().parent
ENV_PATH = REPO / ".env"
HANDLE_JSON = REPO / "jobs" / "handle.json"

# Game Boy 4-color palette
C0 = "#0f380f"  # darkest
C1 = "#306230"  # dark
C2 = "#8bac0f"  # light
C3 = "#9bbc0f"  # lightest (bg)
C_BG = C3
C_BTN = C2
C_BTN_ACTIVE = C1
TEXT = C0
ENTRY_BG = "#e0f0a0"
CLI_BG = C0
CLI_FG = C3

DEPS = ["telegram", "httpx", "yt_dlp", "playwright", "PIL", "arabic_reshaper", "bidi", "cv2", "fontTools"]
PIXEL_FONT = ("Courier", 9, "bold")
PIXEL_SMALL = ("Courier", 7)
TITLE_FONT = ("Courier", 11, "bold")

def load_env():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k,_,v = line.partition("=")
            env[k.strip()] = v.strip()
    return env

def save_env(updates):
    env = load_env()
    env.update(updates)
    lines = []
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                lines.append(line)
                continue
            k,_,_ = line.partition("=")
            k=k.strip()
            if k in env:
                lines.append(f"{k}={env.pop(k)}")
            else:
                lines.append(line)
    for k,v in env.items():
        lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines)+"\n", encoding="utf-8")
    try:
        import json
        HANDLE_JSON.parent.mkdir(parents=True, exist_ok=True)
        HANDLE_JSON.write_text(__import__("json").dumps({"tiktok_handle": updates["TIKTOK_HANDLE"], "watermark_handle": updates[ "WATERMARK_HANDLE"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def load_env_as_dict():
    return load_env()

def count_tiktok_cookies(profile):
    if not profile:
        return 0, "No profile"
    db = Path(profile) / "cookies.sqlite"
    if not db.exists():
        # try as direct file
        if Path(profile).is_file() and Path(profile).name=="cookies.sqlite":
            db = Path(profile)
        else:
            return 0, "No cookies.sqlite"
    try:
        tmp = Path(tempfile.gettempdir()) / "wf_gui_cookies.sqlite"
        import shutil
        shutil.copy2(db, tmp)
        con = sqlite3.connect(str(tmp))
        cur = con.cursor()
        cur.execute("SELECT count(*) FROM moz_cookies WHERE host LIKE '%tiktok.com%'")
        n = cur.fetchone()[0]
        cur.execute("SELECT name FROM moz_cookies WHERE host LIKE '%tiktok.com%' AND name='sessionid'")
        has_sess = cur.fetchone() is not None
        con.close()
        return n, "OK + sessionid" if has_sess else f"{n} cookies (no sessionid!)"
    except Exception as e:
        return 0, str(e)[:60]

def verify_waterfox_status():
    """Return (status_code, message) where status_code: 0=bad, 1=warning, 2=good"""
    env = load_env()
    p = Path(env.get("WATERFOX_PROFILE", os.path.join(os.environ.get("APPDATA", ""), "Waterfox", "Profiles")))
    profile = None
    if (p / "cookies.sqlite").exists():
        profile = p
    else:
        for child in p.glob("*.default-release*"):
            if (child / "cookies.sqlite").exists():
                profile = child
                break
        if not profile:
            for child in p.glob("*"):
                if (child / "cookies.sqlite").exists():
                    profile = child
                    break
    if not profile:
        return 0, f"Waterfox profile not found at {p}"
    n, msg = count_tiktok_cookies(profile)
    if n >= 5 and "sessionid" in msg:
        return 2, f"✓ {profile.name} — {n} cookies — {msg}"
    elif n > 0:
        return 1, f"⚠ {profile.name} — {n} cookies — {msg} — RE-LOGIN!"
    else:
        return 0, f"✗ {profile.name} — 0 cookies — NOT LOGGED IN"

def check_missing_deps():
    missing = []
    for mod in DEPS:
        if importlib.util.find_spec(mod) is None:
            missing.append(mod)
    ff = REPO / "tools" / "ffmpeg-9.0.1-essentials_build" / "bin" / "ffmpeg.exe"
    if not ff.exists():
        missing.append("ffmpeg")
    return missing

class Retro8BitGUI:
    def __init__(self, root):
        self.root = root
        root.title(" OPEN STUDIO BOT [ GAME BOY EDITION ] ")
        root.geometry("680x740")
        root.configure(bg=C0)
        # outer bezel
        outer = tk.Frame(root, bg=C0, bd=4, relief="flat")
        outer.pack(fill="both", expand=True, padx=6, pady=6)
        inner = tk.Frame(outer, bg=C_BG, bd=3, relief="raised")
        inner.pack(fill="both", expand=True, padx=4, pady=4)

        env = load_env()

        # Title bar - Game Boy style with custom buttons
        self.root.overrideredirect(True)

        title_bar = tk.Frame(inner, bg=C0, height=32)
        title_bar.pack(fill="x", padx=3, pady=3)

        # Title label
        tk.Label(title_bar, text=" ▓ OPEN STUDIO BOT [ GAME BOY EDITION ] ▓ ", bg=C0, fg=TEXT, font=TITLE_FONT).pack(side="left", padx=8, pady=6)

        # Minimize button
        minimize_btn = tk.Button(title_bar, text="–", bg=C0, fg=TEXT, font=("Courier", 10, "bold"),
                                 relief="raised", bd=3, width=2, command=self.minimize_window)
        minimize_btn.pack(side="right", padx=2, pady=2)

        # Close button
        close_btn = tk.Button(title_bar, text="✖", bg=C0, fg=TEXT, font=("Courier", 10, "bold"),
                              relief="raised", bd=3, width=2, command=self.root.destroy)
        close_btn.pack(side="right", padx=2, pady=2)

        # Make the title bar draggable
        title_bar.bind("<Button-1>", self.start_move)
        title_bar.bind("<B1-Motion>", self.on_move)
        # Also bind the label for easier dragging
        tk.Label(title_bar, text=" ▓ OPEN STUDIO BOT [ GAME BOY EDITION ] ▓ ", bg=C0, fg=TEXT, font=TITLE_FONT).bind("<Button-1>", self.start_move)
        tk.Label(title_bar, text=" ▓ OPEN STUDIO BOT [ GAME BOY EDITION ] ▓ ", bg=C0, fg=TEXT, font=TITLE_FONT).bind("<B1-Motion>", self.on_move)

        # Scanline
        tk.Frame(inner, bg=C1, height=2).pack(fill="x", padx=3)
        tk.Label(inner, text="— INSERT CARTRIDGE —  TELEGRAM BOT API  ( @BotFather )  —", bg=C_BG, fg=C1, font=PIXEL_SMALL).pack(pady=2)

        body = tk.Frame(inner, bg=C_BG)
        body.pack(fill="both", expand=True, padx=10, pady=6)

        self._pix_section(body, " [ TELEGRAM BOT API ] ")
        self.bot_token = self._pix_field(body, "BOT TOKEN:", env.get("BOT_TOKEN",""), show="*")
        self.chat_id = self._pix_field(body, "CHAT ID:", env.get("ALLOWED_CHAT_ID",""))

        self._pix_section(body, " [ TIKTOK ACCOUNT + WATERMARK ] ")
        self.tiktok_handle = self._pix_field(body, "TIKTOK @:", env.get("TIKTOK_HANDLE",""))
        self.watermark_handle = self._pix_field(body, "WATERMARK @:", env.get("WATERMARK_HANDLE",""))

        self._pix_section(body, " [ WATERFOX PROFILE ] ")
        wf_row = tk.Frame(body, bg=C_BG)
        wf_row.pack(fill="x", pady=3)
        tk.Label(wf_row, text="PROFILE:", bg=C_BG, fg=TEXT, font=PIXEL_FONT, width=14, anchor="w").pack(side="left")
        self.wf_entry = tk.Entry(wf_row, bg=ENTRY_BG, fg=TEXT, relief="sunken", bd=3, font=("Courier", 8), insertbackground=C0)
        self.wf_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.wf_entry.insert(0, env.get("WATERFOX_PROFILE", os.path.join(os.environ.get("APPDATA", ""), "Waterfox", "Profiles")))
        self._pix_btn(wf_row, "VERIFY!", self.verify_waterfox).pack(side="left", padx=4)
        self.wf_status = tk.Label(body, text="> Press VERIFY! to check Waterfox + cookies", bg=C_BG, fg=C1, font=PIXEL_SMALL, anchor="w")
        self.wf_status.pack(fill="x", padx=4, pady=2)
        # T11.4: last known-good cookie banner
        self.cookie_ok_label = tk.Label(body, text="> Last cookie OK: never — log in to TikTok in Waterfox", bg=C_BG, fg=C1, font=PIXEL_SMALL, anchor="w")
        self.cookie_ok_label.pack(fill="x", padx=4, pady=0)

        self._pix_section(body, " [ TEMPLATES ] ")
        self.tmpl00 = tk.BooleanVar(value=True)
        self.tmpl01 = tk.BooleanVar(value=True)
        enabled = env.get("ENABLED_TEMPLATES","00,01")
        self.tmpl00.set("00" in enabled)
        self.tmpl01.set("01" in enabled)
        cb_frame = tk.Frame(body, bg=C_BG)
        cb_frame.pack(fill="x", pady=4)
        self._pix_check(cb_frame, " [X] Template 00 — Raw 9:16 (clean)", self.tmpl00).pack(anchor="w", padx=12, pady=2)
        self._pix_check(cb_frame, " [X] Template 01 — TikTok Card (Majalla)", self.tmpl01).pack(anchor="w", padx=12, pady=2)

        # Action row - chunky 8-bit buttons
        btn_row = tk.Frame(body, bg=C_BG)
        btn_row.pack(fill="x", pady=12)
        self._pix_btn(btn_row, " ▓ SAVE ▓ ", self.save_all, width=14, bg=C1, fg=TEXT).pack(side="left", padx=6)
        self._pix_btn(btn_row, " CHECK DEPS ", self.check_deps, width=14).pack(side="left", padx=6)
        self._pix_btn(btn_row, " BEEP ", lambda: beep(), width=8).pack(side="left", padx=6)

        # Bottom CLI - Game Boy screen
        cli_outer = tk.Frame(inner, bg=C0, bd=3, relief="sunken")
        cli_outer.pack(fill="both", expand=True, padx=6, pady=6)
        tk.Label(cli_outer, text=" ▓ CLI OUTPUT ▓ ", bg=C0, fg=CLI_FG, font=PIXEL_SMALL).pack(fill="x")
        self.cli_text = tk.Text(cli_outer, bg=CLI_BG, fg=CLI_FG, font=("Courier", 8), height=9, wrap="word", relief="flat", bd=0, insertbackground=CLI_FG)
        self.cli_text.pack(fill="both", expand=True, padx=4, pady=4)
        self.cli_text.insert("1.0", "▔ SYSTEM READY. Press CHECK DEPS to scan clean PC...\n▔ Use SAVE to write .env\n")
        self.cli_text.config(state="disabled")

        tk.Label(inner, text=" © 2026 OPEN STUDIO BOT  —  PRESS START  —  8-BIT EDITION ", bg=C_BG, fg=C1, font=PIXEL_SMALL).pack(pady=2)

        # Run initial status checks
        self.root.after(100, self._run_initial_checks)

    def _pix_section(self, parent, title):
        f = tk.Frame(parent, bg=C1, height=2)
        f.pack(fill="x", pady=(10,2))
        tk.Label(parent, text=title, bg=C_BG, fg=TEXT, font=("Courier", 8, "bold"), anchor="w").pack(fill="x")

    def _pix_field(self, parent, label, value, show=None):
        row = tk.Frame(parent, bg=C_BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg=C_BG, fg=TEXT, font=PIXEL_FONT, width=16, anchor="w").pack(side="left")
        e = tk.Entry(row, bg=ENTRY_BG, fg=TEXT, relief="sunken", bd=3, font=("Courier", 8), show=show or "", insertbackground=C0)
        e.pack(side="left", fill="x", expand=True, padx=6)
        e.insert(0, value)
        return e

    def _pix_btn(self, parent, text, cmd, width=10, bg=C_BTN, fg=TEXT):
        def wrapped():
            beep()
            cmd()
        b = tk.Button(parent, text=text, command=wrapped, bg=bg, fg=fg, font=PIXEL_FONT, relief="raised", bd=4, padx=8, pady=4, width=width, activebackground=C2, activeforeground=C0)
        return b

    def _pix_check(self, parent, text, var):
        return tk.Checkbutton(parent, text=text, variable=var, bg=C_BG, fg=TEXT, selectcolor=ENTRY_BG, font=PIXEL_FONT, activebackground=C_BG, relief="flat", bd=0)

    def _log(self, msg):
        def _do():
            self.cli_text.config(state="normal")
            self.cli_text.insert("end", msg+"\n")
            self.cli_text.see("end")
            self.cli_text.config(state="disabled")
        self.root.after(0, _do)

    def minimize_window(self):
        """Minimize: hide title bar temporarily so taskbar icon works."""
        self.root.overrideredirect(False)
        self.root.iconify()
        self.root.bind("<Map>", lambda e: self.root.after_idle(self._restore_titlebar))

    def _restore_titlebar(self):
        self.root.after(50, lambda: self.root.overrideredirect(True))  # delay + idle ensures restore works

    def start_move(self, event):
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root

    def on_move(self, event):
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        x = max(0, self.root.winfo_x() + dx)
        y = max(0, self.root.winfo_y() + dy)
        self.root.geometry(f"+{x}+{y}")

    def _refresh_cookie_banner(self):
        """T11.4: show last known-good cookie time + live DB age."""
        try:
            import datetime as _dt
            import sys as _sys
            _sys.path.insert(0, str(REPO))
            from core.cookies import last_cookie_ok, cookies_db_mtime
            last_ok = last_cookie_ok()
            mtime = cookies_db_mtime()
            now = __import__("time").time()
            if last_ok:
                ago = _dt.timedelta(seconds=int(now - last_ok))
                txt = f"> Last cookie OK: {_dt.datetime.fromtimestamp(last_ok).strftime('%Y-%m-%d %H:%M')} ({ago} ago)"
                fg = C1
            else:
                txt = "> Last cookie OK: never — log in to TikTok in Waterfox, then VERIFY!"
                fg = "#8b0000"
            if mtime:
                db_age = _dt.timedelta(seconds=int(now - mtime))
                txt += f" | cookies.sqlite {db_age} old"
            self.cookie_ok_label.config(text=txt, fg=fg)
            self._log(f"> {txt}")
        except Exception as e:
            self._log(f"> cookie banner fail: {e}")

    def _run_initial_checks(self):
        # Check Waterfox status
        status_code, msg = verify_waterfox_status()
        if status_code == 0:
            self.wf_status.config(text=msg, fg="#8b0000")
        elif status_code == 1:
            self.wf_status.config(text=msg, fg="#8b5a00")
        else:
            self.wf_status.config(text=msg, fg=C1)
        self._log(f"> Waterfox check: {msg}")

        # Check deps (non-installing)
        missing = check_missing_deps()
        if missing:
            self._log(f"> Missing deps: {', '.join(missing)}")
        else:
            self._log("> All core deps present")

        # Warn if handles empty
        env = load_env()
        if not env.get("TIKTOK_HANDLE"):
            self._log("⚠️ TikTok handle not set — use /set_handle in Telegram")
        if not env.get("WATERMARK_HANDLE"):
            self._log("⚠️ Watermark handle not set — use /set_handle in Telegram")

        # T11.4: cookie last-OK banner
        self._refresh_cookie_banner()

    def verify_waterfox(self):
        beep()
        p = Path(self.wf_entry.get().strip())
        # try as dir or file's parent
        profile = None
        if (p / "cookies.sqlite").exists():
            profile = p
        else:
            # search children
            for child in p.glob("*.default-release*"):
                if (child / "cookies.sqlite").exists():
                    profile = child
                    break
            if not profile:
                for child in p.glob("*"):
                    if (child / "cookies.sqlite").exists():
                        profile = child
                        break
        if not profile:
            self.wf_status.config(text=f"✗ NOT FOUND: {p}", fg="#8b0000")
            self._log(f"> WF FAIL: {p}")
            return
        n, msg = count_tiktok_cookies(profile)
        if n >= 5 and "sessionid" in msg:
            self.wf_status.config(text=f"✓ {profile.name} — {n} cookies — {msg}", fg=C1)
            self._log(f"> WF OK: {profile.name} {n} cookies")
        elif n > 0:
            self.wf_status.config(text=f"⚠ {profile.name} — {n} cookies — {msg} — RE-LOGIN!", fg="#8b5a00")
            self._log(f"> WF WARN: {msg}")
        else:
            self.wf_status.config(text=f"✗ {profile.name} — 0 cookies — NOT LOGGED IN", fg="#8b0000")
            self._log("> WF FAIL: 0 cookies")
        self._refresh_cookie_banner()

    def save_all(self):
        updates = {
            "BOT_TOKEN": self.bot_token.get().strip(),
            "ALLOWED_CHAT_ID": self.chat_id.get().strip(),
            "TIKTOK_HANDLE": self.tiktok_handle.get().strip(),
            "WATERMARK_HANDLE": self.watermark_handle.get().strip(),
            "WATERFOX_PROFILE": self.wf_entry.get().strip(),
            "ENABLED_TEMPLATES": ",".join([x for x, v in [("00", self.tmpl00.get()), ( "01", self.tmpl01.get())] if v]),
        }
        for k in ("TIKTOK_HANDLE","WATERMARK_HANDLE"):
            if updates[k] and not updates[k].startswith("@"):
                updates[k] = "@"+updates[k]
        # save .env
        env = {}
        if ENV_PATH.exists():
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.strip().startswith("#") or "=" not in line:
                    continue
                kk,_,vv = line.partition("=")
                env[kk.strip()] = vv.strip()
        env.update(updates)
        lines = []
        if ENV_PATH.exists():
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.strip().startswith("#") or "=" not in line:
                    lines.append(line)
                    continue
                kk,_,_ = line.partition("=")
                kk=kk.strip()
                if kk in env:
                    lines.append(f"{kk}={env.pop(kk)}")
                else:
                    lines.append(line)
        for kk,vv in env.items():
            lines.append(f"{kk}={vv}")
        ENV_PATH.write_text("\n".join(lines)+"\n", encoding="utf-8")
        try:
            import json
            HANDLE_JSON.parent.mkdir(parents=True, exist_ok=True)
            HANDLE_JSON.write_text(__import__("json").dumps({"tiktok_handle": updates["TIKTOK_HANDLE"], "watermark_handle": updates[ "WATERMARK_HANDLE"]}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self._log(f"> SAVED to .env + handle.json | Templates: {updates['ENABLED_TEMPLATES'] or 'none'}")
        beep()
        messagebox.showinfo("SAVED!", "8-BIT SAVE OK!\nRestart bot via run_forever.bat", parent=self.root)

    def check_deps(self):
        beep()
        self._log(">>> CHECKING DEPS for clean Windows...")
        def run():
            import importlib.util
            for mod in DEPS:
                ok = importlib.util.find_spec(mod) is not None
                self._log(f"  {'[OK]' if ok else '[MISS]'} {mod}")
            ff = REPO / "tools" / "ffmpeg-9.0.1-essentials_build" / "bin" / "ffmpeg.exe"
            self._log(f"  {'[OK]' if ff.exists() else '[MISS]'} ffmpeg")
            wf = Path(self.wf_entry.get().strip())
            has_wf = (wf / "cookies.sqlite").exists() if wf.exists() else False
            self._log(f"  {'[OK]' if has_wf else '[MISS]'} Waterfox")
            missing = [m for m in DEPS if importlib.util.find_spec(m) is None]
            if not ff.exists():
                missing.append("ffmpeg")
            if missing:
                self._log(f"\n>>> INSTALLING {', '.join(missing)} ...")
                try:
                    proc = subprocess.Popen([sys.executable, "-m", "pip", "install", "-r", str(REPO / "requirements.txt")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                    for line in proc.stdout:
                        self._log(line.rstrip())
                    proc.wait()
                    self._log(f">>> pip exit {proc.returncode}")
                except Exception as e:
                    self._log(str(e))
                try:
                    self._log(">>> playwright install chromium ...")
                    proc = subprocess.Popen([sys.executable, "-m", "playwright", "install", "chromium"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                    for line in proc.stdout:
                        self._log(line.rstrip())
                    proc.wait()
                    self._log(f">>> playwright {proc.returncode}")
                except Exception as e:
                    self._log(str(e))
            else:
                self._log("\n>>> ALL DEPS OK - CLEAN PC READY! *BEEP*")
                beep()
            self._log(">>> DONE.")
        threading.Thread(target=run, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    Retro8BitGUI(root)
    root.mainloop()