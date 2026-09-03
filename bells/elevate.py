# -*- coding: utf-8 -*-
"""בקשת הרשאות מנהל כשפעולה דורשת אותן.

שלוש הגדרות במערכת נוגעות במחשב כולו ולא רק במשתמש הנוכחי: טיימרים
להערה בתוכנית החשמל, עלייה אוטומטית לכל המשתמשים, ותיקיית הגדרות
משותפת. במקום לומר למנהל "צריך להריץ כמנהל" ולהשאיר אותו להסתדר, מריצים
משימה קצרה ומורמת שעושה בדיוק את הפעולה הזו ונסגרת. שאר הזמן המערכת
ממשיכה לרוץ בהרשאות רגילות.
"""

import ctypes
import os
import sys

TASKS = ("wake-on", "wake-off", "autostart-on", "autostart-off", "share-data")

SEE_MASK_NOCLOSEPROCESS = 0x00000040
SEE_MASK_NO_CONSOLE = 0x00008000
SW_HIDE = 0
ERROR_CANCELLED = 1223


class _ShellExecuteInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("fMask", ctypes.c_ulong),
        ("hwnd", ctypes.c_void_p),
        ("lpVerb", ctypes.c_wchar_p),
        ("lpFile", ctypes.c_wchar_p),
        ("lpParameters", ctypes.c_wchar_p),
        ("lpDirectory", ctypes.c_wchar_p),
        ("nShow", ctypes.c_int),
        ("hInstApp", ctypes.c_void_p),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", ctypes.c_wchar_p),
        ("hkeyClass", ctypes.c_void_p),
        ("dwHotKey", ctypes.c_ulong),
        ("hIcon", ctypes.c_void_p),
        ("hProcess", ctypes.c_void_p),
    ]


def is_admin():
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _command():
    """(קובץ, ארגומנטים לפני שם המשימה) להרצה מורמת."""
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return sys.executable, '"%s" ' % os.path.join(root, "run.py")


def run_elevated(task, timeout_ms=120000):
    """מריץ משימה מורמת אחת וממתין לה.

    מחזיר (הצליח, הודעה). ביטול של המשתמש בחלון ההרשאות אינו שגיאה -
    הוא בחירה, ומדווח ככזו.
    """
    if task not in TASKS:
        return False, "משימה לא מוכרת"
    if sys.platform != "win32":
        return False, "נתמך ב-Windows בלבד"

    exe, prefix = _command()
    info = _ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE
    info.lpVerb = "runas"          # זה מה שמציג את חלון ההרשאות
    info.lpFile = exe
    info.lpParameters = prefix + "--elevated-task " + task
    info.nShow = SW_HIDE

    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        code = ctypes.get_last_error() or ctypes.windll.kernel32.GetLastError()
        if code == ERROR_CANCELLED:
            return False, "בקשת ההרשאה בוטלה"
        return False, "לא ניתן לבקש הרשאות מנהל (שגיאה %s)" % code

    handle = info.hProcess
    if not handle:
        return False, "ההרצה המורמת לא התחילה"
    ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_ms)
    status = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(status))
    ctypes.windll.kernel32.CloseHandle(handle)
    if status.value == 0:
        return True, ""
    return False, "הפעולה נכשלה גם עם הרשאות מנהל"


def perform(task):
    """מריץ את המשימה עצמה. נקרא רק מתוך התהליך המורם."""
    from . import autostart, storage, wake
    if task == "wake-on":
        return wake.set_timers_allowed(True)
    if task == "wake-off":
        return wake.set_timers_allowed(False)
    if task == "autostart-on":
        return autostart.set_enabled(True, all_users=True)["scope"] == "all"
    if task == "autostart-off":
        autostart.set_enabled(False)
        return True
    if task == "share-data":
        return storage.prepare_shared()
    return False
