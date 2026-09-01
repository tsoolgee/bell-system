# -*- coding: utf-8 -*-
"""נקודת הכניסה של מערכת הצלצולים."""

import argparse
import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser

from . import config, engine, server, sounds, tray

_mutex = None


def _mutex_name():
    """הנעילה היא על תצורה, לא על המחשב.

    שני מופעים שחולקים את אותה תיקיית נתונים ייאבקו על אותו config ואותם
    צלצולים. מופע שמצביע על תיקייה אחרת הוא התקנה נפרדת ולגיטימית.
    """
    digest = hashlib.sha256(config.data_dir().lower().encode("utf-8")).hexdigest()[:16]
    return "Global\\BellSystemSingleInstance_" + digest


def already_running():
    """נעילת מופע יחיד לכל תיקיית נתונים."""
    global _mutex
    if sys.platform != "win32":
        return False
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, _mutex_name())
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
        # מערכת צלצולים לא אמורה להיעלם בשקט. אם לולאת המגש הסתיימה בלי
        # שהמשתמש ביקש לצאת, מרימים אותה מחדש - הצלצולים חשובים יותר
        # מהאייקון, והמנוע והשרת ממשיכים לרוץ בינתיים בכל מקרה.
        for attempt in range(1, 6):
            if not icon.run():
                print("pystray לא מותקן - רץ בלי מגש מערכת. Ctrl+C ליציאה.")
                open_ui(port)
                try:
                    while True:
                        time.sleep(3600)
                except KeyboardInterrupt:
                    pass
                break
            engine.log("לולאת המגש הסתיימה (יציאה יזומה: %s)"
                       % icon.quit_requested, "system")
            if icon.quit_requested:
                break
            engine.log("מגש המערכת נסגר מעצמו - מרים מחדש (ניסיון %d)" % attempt, "error")
            time.sleep(2)
        else:
            engine.log("מגש המערכת נסגר שוב ושוב - ממשיך בלי אייקון", "error")
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
