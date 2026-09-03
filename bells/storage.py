# -*- coding: utf-8 -*-
"""איפה יושבים הנתונים, ומי מצלצל כשיש כמה משתמשים במחשב.

מערכת צלצולים היא של המוסד, לא של משתמש Windows מסוים. לכן ההגדרות
יושבות ב-ProgramData ומשותפות לכל מי שמתחבר למחשב. אם אין הרשאה לכתוב
לשם, נופלים לתיקייה האישית - והממשק אומר את זה במפורש, כי במצב הזה
מזכיר שיתחבר למשתמש שלו יקבל מערכת ריקה.
"""

import ctypes
import os
import shutil
import subprocess
import sys

APP_NAME = "BellSystem"
USERS_GROUP_SID = "*S-1-5-32-545"   # קבוצת Users, ללא תלות בשפת המערכת

_resolved = None
_shared = None
_reason = ""


def _per_user_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def _shared_dir():
    if sys.platform != "win32":
        return os.path.join("/var/lib", APP_NAME.lower())
    base = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
    return os.path.join(base, APP_NAME)


def _grant_all_users(path):
    """ProgramData נותן ל-CREATOR OWNER בלבד - בלי זה משתמש אחד לא יוכל
    לערוך קובץ שמשתמש אחר יצר."""
    try:
        subprocess.run(["icacls", path, "/grant", USERS_GROUP_SID + ":(OI)(CI)M", "/T", "/C"],
                       capture_output=True, timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        pass


def _writable(path):
    probe = os.path.join(path, ".write-probe")
    try:
        with open(probe, "w") as fh:
            fh.write("x")
        os.remove(probe)
        return True
    except OSError:
        return False


def _migrate(src, dst):
    """העברה חד-פעמית מהתיקייה האישית למשותפת, כדי שהלוח לא ילך לאיבוד."""
    if not os.path.exists(os.path.join(src, "config.json")):
        return False
    if os.path.exists(os.path.join(dst, "config.json")):
        return False
    try:
        for name in os.listdir(src):
            source = os.path.join(src, name)
            target = os.path.join(dst, name)
            if os.path.isdir(source):
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target)
        return True
    except OSError:
        return False


def prepare_shared():
    """יוצר את התיקייה המשותפת ונותן הרשאה לכל המשתמשים.

    נקרא מתוך התהליך המורם: יצירת התיקייה תחת ProgramData והענקת Modify
    לקבוצת Users הן פעולות שדורשות מנהל, ובלעדיהן כל משתמש היה מקבל
    הגדרות משלו.
    """
    shared = _shared_dir()
    try:
        os.makedirs(os.path.join(shared, "sounds"), exist_ok=True)
    except OSError:
        return False
    _grant_all_users(shared)
    if not _writable(shared):
        return False
    _migrate(_per_user_dir(), shared)
    return True


def reset():
    """שוכח את ההחלטה, כדי לזהות מחדש אחרי שההרשאות השתנו."""
    global _resolved, _shared, _reason
    _resolved = _shared = None
    _reason = ""


def resolve():
    """מחזיר (נתיב, האם משותף, הסבר). מחושב פעם אחת."""
    global _resolved, _shared, _reason
    if _resolved is not None:
        return _resolved, _shared, _reason

    override = os.environ.get("BELLSYSTEM_DATA")
    if override:
        os.makedirs(os.path.join(override, "sounds"), exist_ok=True)
        _resolved, _shared, _reason = override, False, "נתיב שנקבע ידנית"
        return _resolved, _shared, _reason

    shared = _shared_dir()
    created = not os.path.isdir(shared)
    try:
        os.makedirs(shared, exist_ok=True)
        if created:
            _grant_all_users(shared)
    except OSError:
        pass

    if os.path.isdir(shared) and _writable(shared):
        os.makedirs(os.path.join(shared, "sounds"), exist_ok=True)
        moved = _migrate(_per_user_dir(), shared)
        _resolved, _shared = shared, True
        _reason = "הועברו הגדרות קיימות" if moved else "משותף לכל המשתמשים"
        return _resolved, _shared, _reason

    personal = _per_user_dir()
    os.makedirs(os.path.join(personal, "sounds"), exist_ok=True)
    _resolved, _shared = personal, False
    _reason = ("אין הרשאת כתיבה ל-%s. הריצו את התוכנה פעם אחת כמנהל "
               "כדי שההגדרות יהיו משותפות לכל המשתמשים במחשב." % shared)
    return _resolved, _shared, _reason


# ---------------------------------------------------------------- סשנים

def current_session():
    """מזהה סשן ה-Windows של התהליך הזה."""
    if sys.platform != "win32":
        return 0
    sid = ctypes.c_ulong()
    pid = ctypes.windll.kernel32.GetCurrentProcessId()
    if ctypes.windll.kernel32.ProcessIdToSessionId(pid, ctypes.byref(sid)):
        return int(sid.value)
    return -1


def active_console_session():
    """הסשן שיושב מול המסך כרגע. משתנה בהחלפת משתמש."""
    if sys.platform != "win32":
        return 0
    try:
        return int(ctypes.windll.kernel32.WTSGetActiveConsoleSessionId())
    except Exception:
        return -1


def is_active_session():
    """האם *אנחנו* הסשן שהצליל שלו באמת יגיע לרמקולים.

    ב-Windows סשן מנותק (אחרי החלפת משתמש) לא מקבל ניתוב שמע. אם נצלצל
    משם, שום דבר לא יישמע ובמקביל המופע בסשן הפעיל ידלג - ולכן בדיוק
    מופע אחד צריך לצלצל: זה שנמצא בקונסולה.
    """
    if sys.platform != "win32":
        return True
    mine, active = current_session(), active_console_session()
    if mine < 0 or active < 0:
        return True   # אם אי אפשר לדעת, עדיף לצלצל מאשר לשתוק
    return mine == active
