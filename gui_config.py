"""TG-MONTAGE Retro Desktop Config GUI - set credentials, watermark, account, Waterfox verify.

Retro look: Win95 grey beveled buttons, navy title bar, pixel-ish fonts.
Run: .venv\Scripts\python.exe gui_config.py  (or python gui_config.py)

Sets: BOT_TOKEN (Telegram bot API), ALLOWED_CHAT_ID, TIKTOK_HANDLE, WATERMARK_HANDLE,
      Waterfox profile + cookies, Templates 00/01 visibility.
Saves to .env + jobs/handle.json. Bottom CLI pops when deps are downloading.
"""
import importlib.util
import os
import re
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

REPO = Path(__file__).resolve().parent
ENV_PATH = REPO / ".env"
HANDLE_JSON = REPO / "jobs" / "handle.json"

# Retro palette
BG_GREY = "#C0C0C0"
BG_DARK = "#000080"
FG_WHITE = "white"
FG_BLACK = "black"
FG_GREEN = "#00FF00"
BTN_BG = "#C0C0C0"
ENTRY_BG = "white"

DEPS = ["telegram", "httpx", "yt_dlp", "playwright", "PIL", "arabic_reshaper", "bidi", "cv2", "fontTools"]

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
    # preserve .env.example order if .env missing keys: just write updates
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

def find_waterfox_profile():
    env = load_env()
    p = Path(env.get("WATERFOX_PROFILE", r"C:\Users\Mventor\AppData\Roaming\Waterfox\Profiles"))
    if (p / "cookies.sqlite").exists():
        return p
    for child in p.glob("*.default-release*"):
        if (child / "cookies.sqlite").exists():
            return child
    for child in p.glob("*"):
        if (child / "cookies.sqlite").exists():
            return child
    return None

def count_tiktok_cookies(profile):
    if not profile:
        return 0, "No profile"
    db = profile / "cookies.sqlite"
    if not db.exists():
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
        return n, "OK + sessionid" if has_sess else f"{n} cookies (no sessionid - not logged in)"
    except Exception as e:
        return 0, str(e)[:60]

class RetroGUI:
    def __init__(self, root):
        self.root = root
        root.title("TG-MONTAGE CONFIG v1.0  —  Retro Desktop Configuration")
        root.geometry("640x720")
        root.configure(bg=BG_GREY)
        env = load_env()

        # Title bar
        title = tk.Frame(root, bg=BG_DARK, height=28)
        title.pack(fill="x", padx=2, pady=2)
        tk.Label(title, text="  TG-MONTAGE  —  Telegram  +  Montage  +  Upload  —  CONFIG", bg=BG_DARK, fg=FG_WHITE, font=("Courier", 10, "bold")).pack(side="left", pady=4)
        tk.Label(title, text="RETRO", bg=BG_DARK, fg="#FFCC00", font=("Courier", 8)).pack(side="right", padx=10)

        body = tk.Frame(root, bg=BG_GREY)
        body.pack(fill="both", expand=True, padx=8, pady=6)

        # Telegram Bot API (NOT opencode!)
        self._section(body, "TELEGRAM BOT API  (from @BotFather)")
        self.bot_token = self._field(body, "BOT_TOKEN (Bot API):", env.get("BOT_TOKEN",""), show="*")
        self.chat_id = self._field(body, "ALLOWED_CHAT_ID:", env.get("ALLOWED_CHAT_ID",""))

        self._section(body, "TIKTOK ACCOUNT  &  WATERMARK  (configurable, not hardcoded)")
        self.tiktok_handle = self._field(body, "TIKTOK_HANDLE (@):", env.get("TIKTOK_HANDLE",""))
        self.watermark_handle = self._field(body, "WATERMARK_HANDLE (@):", env.get("WATERMARK_HANDLE",""))

        self._section(body, "WATERFOX  —  verify profile + cookies")
        wf_row = tk.Frame(body, bg=BG_GREY)
        wf_row.pack(fill="x", pady=2)
        tk.Label(wf_row, text="WATERFOX_PROFILE:", bg=BG_GREY, fg=FG_BLACK, font=("MS Sans Serif", 8), width=22, anchor="w").pack(side="left")
        self.wf_entry = tk.Entry(wf_row, bg=ENTRY_BG, fg=FG_BLACK, relief="sunken", bd=2, font=("Courier", 8))
        self.wf_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.wf_entry.insert(0, env.get("WATERFOX_PROFILE", r"C:\Users\Mventor\AppData\Roaming\Waterfox\Profiles"))
        self._retro_btn(wf_row, "VERIFY", self.verify_waterfox).pack(side="left", padx=4)
        self.wf_status = tk.Label(body, text="Click VERIFY to check Waterfox + TikTok cookies", bg=BG_GREY, fg="#000080", font=("Courier", 8), anchor="w")
        self.wf_status.pack(fill="x", padx=4)

        self._section(body, "TEMPLATES  —  visible by checkbox")
        self.tmpl00 = tk.BooleanVar(value=True)
        self.tmpl01 = tk.BooleanVar(value=True)
        # load from env if present: ENABLED_TEMPLATES=00,01
        enabled = env.get("ENABLED_TEMPLATES","00,01")
        self.tmpl00.set("00" in enabled)
        self.tmpl01.set("01" in enabled)
        cb_frame = tk.Frame(body, bg=BG_GREY)
        cb_frame.pack(fill="x", pady=4)
        tk.Checkbutton(cb_frame, text="Template 00  —  Raw 9:16  (clean, no card)", variable=self.tmpl00, bg=BG_GREY, fg=FG_BLACK, selectcolor=ENTRY_BG, font=("MS Sans Serif", 8)).pack(anchor="w", padx=12)
        tk.Checkbutton(cb_frame, text="Template 01  —  TikTok Card  (Majalla + @watermark, 9:16)", variable=self.tmpl01, bg=BG_GREY, fg=FG_BLACK, selectcolor=ENTRY_BG, font=("MS Sans Serif", 8)).pack(anchor="w", padx=12)

        # Action buttons
        btn_row = tk.Frame(body, bg=BG_GREY)
        btn_row.pack(fill="x", pady=10)
        self._retro_btn(btn_row, "SAVE ALL", self.save_all, width=14).pack(side="left", padx=4)
        self._retro_btn(btn_row, "CHECK DEPS", self.check_deps, width=14).pack(side="left", padx=4)
        self._retro_btn(btn_row, "VERIFY", self.verify_waterfox, width=10).pack(side="left", padx=4)

        # Bottom CLI (hidden until deps downloading)
        self.cli_frame = tk.Frame(root, bg="black", bd=2, relief="sunken")
        self.cli_label = tk.Label(self.cli_frame, text=" CLI  —  deps download log ", bg="black", fg=FG_GREEN, font=("Courier", 8), anchor="w")
        self.cli_label.pack(fill="x")
        self.cli_text = tk.Text(self.cli_frame, bg="black", fg=FG_GREEN, font=("Courier", 8), height=10, wrap="word")
        self.cli_text.pack(fill="both", expand=True, padx=2, pady=2)

        # Status bar
        self.status = tk.Label(root, text=" Ready — edit fields, then SAVE ALL.  Templates checked = visible in Telegram.", bg=BG_GREY, fg=FG_BLACK, font=("Courier", 7), anchor="w", relief="sunken", bd=1)
        self.status.pack(fill="x", padx=2, pady=2)

    def _section(self, parent, title):
        tk.Label(parent, text=title, bg=BG_GREY, fg="#800000", font=("Courier", 8, "bold"), anchor="w").pack(fill="x", pady=(10,2))

    def _field(self, parent, label, value, show=None):
        row = tk.Frame(parent, bg=BG_GREY)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=label, bg=BG_GREY, fg=FG_BLACK, font=("MS Sans Serif", 8), width=22, anchor="w").pack(side="left")
        e = tk.Entry(row, bg=ENTRY_BG, fg=FG_BLACK, relief="sunken", bd=2, font=("Courier", 8), show=show or "")
        e.pack(side="left", fill="x", expand=True, padx=4)
        e.insert(0, value)
        return e

    def _retro_btn(self, parent, text, cmd, width=10):
        b = tk.Button(parent, text=text, command=cmd, bg=BTN_BG, fg=FG_BLACK, font=("MS Sans Serif", 8, "bold"), relief="raised", bd=3, padx=6, pady=2, width=width, activebackground="#DFDFDF")
        return b

    def verify_waterfox(self):
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
            self.wf_status.config(text=f"✗ Waterfox not found at {p}", fg="red")
            return
        n, msg = count_tiktok_cookies(profile)
        if n >= 5 and "sessionid" in msg:
            self.wf_status.config(text=f"✓ {profile.name} — {n} tiktok cookies — {msg}", fg="#008000")
        elif n > 0:
            self.wf_status.config(text=f"⚠ {profile.name} — {n} cookies — {msg} — re-login in Waterfox!", fg="#CC6600")
        else:
            self.wf_status.config(text=f"✗ {profile.name} — 0 tiktok cookies — not logged in", fg="red")

    def save_all(self):
        updates = {
            "BOT_TOKEN": self.bot_token.get().strip(),
            "ALLOWED_CHAT_ID": self.chat_id.get().strip(),
            "TIKTOK_HANDLE": self.tiktok_handle.get().strip(),
            "WATERMARK_HANDLE": self.watermark_handle.get().strip(),
            "WATERFOX_PROFILE": self.wf_entry.get().strip(),
            "ENABLED_TEMPLATES": ",".join([x for x, v in [("00", self.tmpl00.get()), ("01", self.tmpl01.get())] if v]),
        }
        # remove empty handle @ prefix handling: ensure @
        for k in ("TIKTOK_HANDLE","WATERMARK_HANDLE"):
            if updates[k] and not updates[k].startswith("@"):
                updates[k] = "@"+updates[k]
        save_env(updates)
        # also persist handles to jobs/handle.json for bot runtime
        try:
            import json
            HANDLE_JSON.parent.mkdir(parents=True, exist_ok=True)
            HANDLE_JSON.write_text(json.dumps({"tiktok_handle": updates["TIKTOK_HANDLE"], "watermark_handle": updates["WATERMARK_HANDLE"]}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self.status.config(text=f" Saved to .env + handle.json  |  Templates: {updates['ENABLED_TEMPLATES'] or 'none'} ")
        messagebox.showinfo("Saved", "Credentials + handles + templates saved to .env\nRestart bot via run_forever.bat to apply.", parent=self.root)

    def check_deps(self):
        self.cli_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self.cli_text.delete("1.0", "end")
        self.cli_text.insert("end", ">>> Checking deps for clean Windows...\n")
        self.cli_text.see("end")
        def run():
            missing = []
            for mod in DEPS:
                if importlib.util.find_spec(mod) is None:
                    missing.append(mod)
                    self._log(f"  MISSING: {mod}")
                else:
                    self._log(f"  OK: {mod}")
            # ffmpeg
            ff = REPO / "tools" / "ffmpeg-9.0.1-essentials_build" / "bin" / "ffmpeg.exe"
            if not ff.exists():
                missing.append("ffmpeg")
                self._log(f"  MISSING: ffmpeg at {ff}")
            else:
                self._log(f"  OK: ffmpeg")
            # Waterfox
            wf = find_waterfox_profile()
            self._log(f"  Waterfox: {wf if wf else 'NOT FOUND'}")
            # playwright browsers
            try:
                out = subprocess.run([sys.executable, "-m", "playwright", "--help"], capture_output=True, text=True, timeout=10)
                self._log(f"  playwright: { 'OK' if out.returncode==0 else 'MISSING'}")
            except Exception as e:
                self._log(f"  playwright check fail: {e}")
            if missing:
                self._log(f"\n>>> Installing missing: {', '.join(missing)} ...\n")
                try:
                    proc = subprocess.Popen([sys.executable, "-m", "pip", "install", "-r", str(REPO / "requirements.txt")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                    for line in proc.stdout:
                        self._log(line.rstrip())
                    proc.wait()
                    self._log(f"\n>>> pip done code {proc.returncode}")
                except Exception as e:
                    self._log(f"pip error: {e}")
                # playwright browsers
                try:
                    self._log(">>> playwright install chromium ...")
                    proc = subprocess.Popen([sys.executable, "-m", "playwright", "install", "chromium"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                    for line in proc.stdout:
                        self._log(line.rstrip())
                    proc.wait()
                    self._log(f">>> playwright done {proc.returncode}")
                except Exception as e:
                    self._log(str(e))
            else:
                self._log("\n>>> All deps OK — clean PC ready!")
            self._log("\n>>> Done.")
        threading.Thread(target=run, daemon=True).start()

    def _log(self, msg):
        self.root.after(0, lambda: (self.cli_text.insert("end", msg+"\n"), self.cli_text.see("end")))

if __name__ == "__main__":
    root = tk.Tk()
    RetroGUI(root)
    root.mainloop()
