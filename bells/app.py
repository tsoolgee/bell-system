# -*- coding: utf-8 -*-
"""נקודת הכניסה של מערכת הצלצולים."""

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser

from . import config, engine, server, sounds, tray

MUTEX_NAME = "Global\\BellSystemSingleInstance"
_mutex = None


def already_running():
    """נעילת מופע יחיד - שתי מערכות צלצולים לא יכולות לרוץ יחד."""
    global _mutex
    if sys.platform != "win32":
        return False
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def running_port():
    """מאתר את הפורט של מופע שכבר רץ, כדי רק לפתוח לו את הממשק."""
    base = int(config.settings().get("port", 8730))
    for candidate in [base] + [base + i for i in range(1, 12)]:
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/api/state" % candidate, timeout=1) as res:
                if res.status == 200:
                    return candidate
        except Exception:
            continue
    return None


def _browser_command():
    """דפדפן שאפשר לפתוח בו חלון אפליקציה נקי (בלי סרגלי דפדפן)."""
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        shutil.which("msedge"),
        shutil.which("chrome"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def open_ui(port):
    url = "http://127.0.0.1:%d/" % port
    browser = _browser_command()
    if browser:
        try:
            subprocess.Popen([browser, "--app=" + url, "--window-size=1180,860"],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return
        except OSError:
            pass
    webbrowser.open(url)


def main(argv=None):
    parser = argparse.ArgumentParser(description="מערכת ניהול צלצולים")
    parser.add_argument("--minimized", action="store_true", help="עלייה שקטה למגש המערכת")
    parser.add_argument("--port", type=int, help="פורט לממשק הניהול")
    parser.add_argument("--no-tray", action="store_true", help="ריצה בלי מגש (לבדיקות)")
    args = parser.parse_args(argv)

    if already_running():
        port = running_port()
        if port:
            open_ui(port)
        return 0

    sounds.ensure(config.sounds_dir())
    engine.start()
    httpd, port = server.start(args.port)

    show = not (args.minimized or config.settings().get("startMinimized", True))
    if show:
        # שנייה של חסד כדי שהשרת יספיק לענות לבקשה הראשונה
        time.sleep(0.4)
        open_ui(port)

    if args.no_tray:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    else:
        icon = tray.Tray(port, lambda: open_ui(port), None)
        icon.on_quit = icon.stop
        if not icon.run():
            print("pystray לא מותקן - רץ בלי מגש מערכת. Ctrl+C ליציאה.")
            open_ui(port)
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass

    engine.log("המערכת נסגרה", "system")
    engine.shutdown()
    httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
