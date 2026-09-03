# -*- coding: utf-8 -*-
"""העָרה של המחשב לקראת צלצול.

מחשב שנרדם הוא מערכת צלצולים מושבתת. Windows יודע להעיר את עצמו בזמן
שנקבע מראש (waitable timer עם fResume), וזה בדיוק מה שנחוץ כאן: קובעים
טיימר לצלצול הבא, המחשב מתעורר מעט לפניו, והמנוע מצלצל בזמן.

שתי מגבלות שחשוב להכיר, ושהממשק אומר אותן במפורש:
* התכונה תלויה בהגדרת "אפשר טיימרים להערה" בתוכנית צריכת החשמל.
* משום טיימר אי אפשר להעיר מחשב **כבוי**. רק משינה או תרדמת.
"""

import ctypes
import datetime
import re
import subprocess
import sys
import threading

from . import engine

SUB_SLEEP = "238c9fa8-0aad-41ed-83f4-97be242c8f20"
ALLOW_WAKE_TIMERS = "bd3b718a-0680-4d9d-8ab2-e1d2b4ac806d"

_timer = None
_target = None
_thread = None
_lock = threading.RLock()
_woke = threading.Event()

if sys.platform == "win32":
    _k32 = ctypes.windll.kernel32
    _k32.CreateWaitableTimerW.restype = ctypes.c_void_p
    _k32.CreateWaitableTimerW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    _k32.SetWaitableTimer.restype = ctypes.c_int
    _k32.SetWaitableTimer.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_longlong),
                                      ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.c_int]
    _k32.CancelWaitableTimer.argtypes = [ctypes.c_void_p]
    _k32.WaitForSingleObject.restype = ctypes.c_ulong
    _k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
else:
    _k32 = None


# ---------------------------------------------------------------- הרשאת המערכת

def _powercfg(args, timeout=20):
    """מריץ powercfg ומחזיר (קוד יציאה, טקסט).

    הפלט מתורגם לשפת המערכת ויוצא בקודפייג המקומי, ולכן קוראים בייטים
    ומפענחים בסובלנות - אחרת בעברית הפענוח נופל והבדיקה מחזירה "לא ידוע".
    """
    try:
        out = subprocess.run(["powercfg"] + args, capture_output=True, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None, ""
    text = (out.stdout or b"").decode("utf-8", "replace")
    if "�" in text:
        text = (out.stdout or b"").decode("cp1255", "replace")
    return out.returncode, text


def timers_allowed(both=False):
    """האם תוכנית החשמל מרשה טיימרים להערה. None אם לא ניתן לברר.

    0 = כבוי, 1 = מאופשר, 2 = רק טיימרים חשובים. במחשב נייד ההגדרה
    לסוללה נפרדת מזו לחשמל, ולרוב כבויה - ולכן מחזירים את שתיהן.
    """
    if sys.platform != "win32":
        return (None, None) if both else None
    code, text = _powercfg(["/query", "SCHEME_CURRENT", SUB_SLEEP, ALLOW_WAKE_TIMERS])
    if code != 0:
        return (None, None) if both else None
    # שני ערכי ההגדרה האחרונים בפלט הם AC ואחריו DC
    values = re.findall(r"0x([0-9a-fA-F]{8})", text)
    if len(values) < 2:
        return (None, None) if both else None
    ac, dc = int(values[-2], 16), int(values[-1], 16)
    return (ac, dc) if both else ac


def set_timers_allowed(enabled):
    """מאפשר או מבטל טיימרים להערה בתוכנית החשמל הנוכחית."""
    if sys.platform != "win32":
        return False
    value = "1" if enabled else "0"
    for verb in ("/setacvalueindex", "/setdcvalueindex"):
        code, _ = _powercfg([verb, "SCHEME_CURRENT", SUB_SLEEP, ALLOW_WAKE_TIMERS, value])
        if code != 0:
            return False
    _powercfg(["/setactive", "SCHEME_CURRENT"])
    return timers_allowed() == (1 if enabled else 0)


def supported():
    """האם המחשב בכלל יודע להיכנס למצב שינה שאפשר להתעורר ממנו."""
    if sys.platform != "win32":
        return False
    code, text = _powercfg(["/availablesleepstates"])
    if code is None:
        return False
    low = text.lower()
    return any(k in low for k in ("s3", "s4", "s0 ", "standby", "המתנה", "שינה"))


# ---------------------------------------------------------------- הטיימר עצמו

def _ensure_timer():
    global _timer
    if _k32 is None:
        return None
    if _timer is None:
        handle = _k32.CreateWaitableTimerW(None, 0, None)   # אוטו-איפוס
        _timer = handle or None
    return _timer


def arm(when, lead_seconds=60):
    """קובע העָרה ל-lead שניות לפני המועד. מחזיר את הזמן שנקבע או None."""
    global _target
    with _lock:
        handle = _ensure_timer()
        if handle is None or when is None:
            return None
        target = when - datetime.timedelta(seconds=max(0, int(lead_seconds)))
        now = datetime.datetime.now().astimezone()
        seconds = (target - now).total_seconds()
        if seconds <= 1:
            return None   # כבר עכשיו, אין מה להעיר
        # זמן שלילי ביחידות של 100 ננו-שניות = מרווח יחסי מעכשיו
        due = ctypes.c_longlong(int(-seconds * 10_000_000))
        ok = _k32.SetWaitableTimer(handle, ctypes.byref(due), 0, None, None, 1)
        if not ok:
            return None
        _target = target
        return target


def cancel():
    global _target
    with _lock:
        if _timer is not None and _k32 is not None:
            _k32.CancelWaitableTimer(_timer)
        _target = None


def target():
    with _lock:
        return _target


def _watch():
    """ממתין לטיימר. כשהוא נפתח - המחשב ער, ורק צריך לרשום זאת."""
    while True:
        handle = _ensure_timer()
        if handle is None:
            return
        result = _k32.WaitForSingleObject(handle, 0xFFFFFFFF)
        if result == 0:
            engine.log("המחשב הועֵר לקראת צלצול", "system")
            _woke.set()


def start():
    global _thread
    if _k32 is None:
        return
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_watch, name="bell-wake", daemon=True)
            _thread.start()


def pending():
    """מה Windows מדווח על טיימרים להערה שממתינים. דורש הרשאת מנהל.

    מחזיר (זמין?, טקסט) - בלי הרשאה אין דרך לדעת, וזה לא אומר שאין
    טיימר. לכן מבדילים בין "אין" לבין "אי אפשר לבדוק".
    """
    code, text = _powercfg(["/waketimers"])
    return (code == 0, text.strip())


def status():
    ac, dc = timers_allowed(both=True)
    with _lock:
        armed = _target
    return {
        "supported": supported(),
        "allowed": ac,               # 0 כבוי, 1 מאופשר, 2 חשובים בלבד, None לא ידוע
        "allowedBattery": dc,
        "armedFor": armed.isoformat(timespec="seconds") if armed else None,
        "armedAt": armed.strftime("%H:%M") if armed else None,
    }
