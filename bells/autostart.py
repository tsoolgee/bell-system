# -*- coding: utf-8 -*-
"""הפעלה אוטומטית עם הדלקת המחשב.

מערכת צלצולים צריכה לעלות לכל מי שמתחבר למחשב, לא רק למי שהתקין אותה:
אם המזכיר מתחבר למשתמש שלו והתוכנה רשומה רק אצל המנהל, אין צלצולים.
לכן מעדיפים את רשומת HKLM שחלה על כל המשתמשים, ונופלים ל-HKCU כשאין
הרשאות מנהל - עם דיווח ברור איזה מהשניים בתוקף.
"""

import ctypes
import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "BellSystem"


def is_admin():
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _command():
    if getattr(sys, "frozen", False):
        return '"%s" --minimized' % sys.executable
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run.py")
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    return '"%s" "%s" --minimized' % (pythonw, script)


def _read(root):
    import winreg
    try:
        with winreg.OpenKey(root, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return value or ""
    except OSError:
        return ""


def _write(root, command):
    import winreg
    with winreg.CreateKey(root, RUN_KEY) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)


def _delete(root):
    import winreg
    try:
        with winreg.OpenKey(root, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except OSError:
        pass


def status():
    """מה בתוקף כרגע: לכל המשתמשים, למשתמש הזה בלבד, או כלל לא."""
    if sys.platform != "win32":
        return {"enabled": False, "scope": None, "canSetAllUsers": False}
    import winreg
    all_users = bool(_read(winreg.HKEY_LOCAL_MACHINE))
    this_user = bool(_read(winreg.HKEY_CURRENT_USER))
    return {
        "enabled": all_users or this_user,
        "scope": "all" if all_users else ("user" if this_user else None),
        "canSetAllUsers": is_admin(),
    }


def is_enabled():
    return status()["enabled"]


def set_enabled(enabled, all_users=True):
    """מפעיל/מבטל עלייה אוטומטית. מחזיר את המצב שהושג בפועל."""
    if sys.platform != "win32":
        return status()
    import winreg
    if not enabled:
        _delete(winreg.HKEY_CURRENT_USER)
        if is_admin():
            _delete(winreg.HKEY_LOCAL_MACHINE)
        return status()

    command = _command()
    if all_users and is_admin():
        try:
            _write(winreg.HKEY_LOCAL_MACHINE, command)
            # רשומה אישית מיותרת עכשיו, ותגרום להרצה כפולה באותו סשן
            _delete(winreg.HKEY_CURRENT_USER)
            return status()
        except OSError:
            pass
    try:
        _write(winreg.HKEY_CURRENT_USER, command)
    except OSError:
        pass
    return status()
