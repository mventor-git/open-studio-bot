#!/usr/bin/env python
"""Open Studio Bot — System Tray Controller.

- Green icon = bot running (polling Telegram)
- Red icon = bot stopped
- Menu: Start / Stop / Config / Quit
- Config opens the existing 8-bit Retro GUI (gui_config.py)
"""

from __future__ import annotations

import os
import sys
import subprocess
import threading
import time
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with: pip install pystray pillow")
    sys.exit(1)

# Add repo root to path
REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

class BotController:
    """Manages the bot subprocess and its state."""
    
    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.venv_python = str(REPO / ".venv" / "Scripts" / "python.exe")
        self.bot_script = str(REPO / "bot.py")
    
    def is_running(self) -> bool:
        with self.lock:
            return self.process is not None and self.process.poll() is None
    
    def start(self) -> bool:
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                return False  # already running
            try:
                # Start bot in a new console window (so it can show logs)
                self.process = subprocess.Popen(
                    [self.venv_python, self.bot_script],
                    cwd=str(REPO),
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                return True
            except Exception as e:
                print(f"Failed to start bot: {e}")
                return False
    
    def stop(self) -> bool:
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                return False  # not running
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
                self.process = None
                return True
            except subprocess.TimeoutExpired:
                try:
                    self.process.kill()
                    self.process.wait()
                except Exception:
                    pass
                self.process = None
                return True
            except Exception:
                self.process = None
                return False
    
    def toggle(self) -> bool:
        if self.is_running():
            return self.stop()
        else:
            return self.start()


def create_icon(color: str, size: tuple[int, int] = (64, 64)) -> "Image.Image":
    """Generate a simple tray icon: green circle (running) or red (stopped)."""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    box = [margin, margin, size[0] - margin, size[1] - margin]
    color_map = {"green": "#22c55e", "red": "#ef4444"}
    draw.ellipse(box, fill=color_map.get(color, "#64748b"))
    return img


class TrayApp:
    def __init__(self):
        self.controller = BotController()
        self.icon: pystray.Icon | None = None
        self._build_menu()
    
    def _build_menu(self):
        self.menu = pystray.Menu(
            pystray.MenuItem("▶ Start Bot", self.on_start, enabled=lambda item: not self.controller.is_running()),
            pystray.MenuItem("■ Stop Bot", self.on_stop, enabled=lambda item: self.controller.is_running()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("⚙️ Config", self.on_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Quit", self.on_quit),
        )
    
    def on_start(self, icon, item):
        if self.controller.start():
            self.update_icon()
            self.update_menu()
    
    def on_stop(self, icon, item):
        if self.controller.stop():
            self.update_icon()
            self.update_menu()
    
    def on_config(self, icon, item):
        # Launch the config GUI in a new thread
        threading.Thread(target=self.open_config_gui, daemon=True).start()
    
    def open_config_gui(self):
        try:
            # Run the config GUI from the repo's Python
            subprocess.Popen([
                str(REPO / ".venv" / "Scripts" / "python.exe"),
                str(REPO / "gui_config.py")
            ])
        except Exception as e:
            print(f"Failed to open config GUI: {e}")
    
    def on_quit(self, icon, item):
        self.controller.stop()
        if self.icon:
            self.icon.stop()
    
    def update_icon(self):
        if not self.icon:
            return
        color = "green" if self.controller.is_running() else "red"
        self.icon.icon = create_icon("green" if self.controller.is_running() else "red")
        self.icon.title = f"Open Studio Bot — {'Running' if self.controller.is_running() else 'Stopped'}"
    
    def update_menu(self):
        # pystray rebuilds menu on each click; just update title
        if self.icon:
            self.icon.title = f"Open Studio Bot — {'Running' if self.controller.is_running() else 'Stopped'}"
    
    def run(self):
        self.icon = pystray.Icon(
            "open_studio_bot",
            icon=create_icon("green" if self.controller.is_running() else "red"),
            title="Open Studio Bot — Stopped",
            menu=self.menu,
        )
        self.icon.run()


def main():
    app = TrayApp()
    # If .env is missing, auto-open config GUI on first run
    env_path = REPO / ".env"
    if not env_path.exists() or env_path.stat().st_size < 50:
        try:
            subprocess.Popen([str(REPO / ".venv" / "Scripts" / "python.exe"), str(REPO / "gui_config.py")])
        except Exception:
            pass
    app.run()


if __name__ == "__main__":
    main()