# -*- coding: utf-8 -*-
"""עדכון אוטומטי מ-GitHub Releases.

הכלל שמנחה את כל המודול: מערכת צלצולים לא מתעדכנת ולא מתחילה מחדש
כשצלצול קרוב. בדיקה והורדה יכולות לקרות מתי שרוצים - ההחלפה עצמה
מחכה לחלון שבו אף אחד לא יפספס צלצול.
"""

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config, engine, schedule, storage, version

API = "https://api.github.com/repos/%s/releases/latest"
ALLOWED_HOSTS = ("github.com", "githubusercontent.com")

# כמה זמן צריך להיות פנוי לפני ובזמן ההחלפה
QUIET_MINUTES = 20
MIN_SIZE = 5 * 1024 * 1024
CHECK_EVERY = 6 * 3600

_state = {"checking": False, "latest": None, "notes": "", "downloaded": None,
          "error": "", "lastCheck": None}
_lock = threading.Lock()


def _host_ok(url):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return urllib.parse.urlparse(url).scheme == "https" and any(
        host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


def exe_path():
    return sys.executable if getattr(sys, "frozen", False) else ""


def cleanup():
    """מוחק את הגרסה הקודמת שנשארה אחרי עדכון."""
    exe = exe_path()
    if not exe:
        return
    for suffix in (".old", ".new"):
        stale = exe + suffix
        if os.path.exists(stale):
            try:
                os.remove(stale)
            except OSError:
                pass


def check(timeout=20):
    """שואל את GitHub מה הגרסה האחרונה. מחזיר את מצב העדכון."""
    with _lock:
        _state["checking"] = True
    try:
        req = urllib.request.Request(API % version.REPO,
                                     headers={"Accept": "application/vnd.github+json",
                                              "User-Agent": "BellSystem"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8"))
        tag = data.get("tag_name") or ""
        asset = next((a for a in data.get("assets") or []
                      if a.get("name") == version.ASSET), None)
        url = (asset or {}).get("browser_download_url") or ""
        with _lock:
            _state.update({
                "latest": tag.lstrip("vV"),
                "notes": (data.get("body") or "").strip()[:1500],
                "url": url if _host_ok(url) else "",
                "error": "" if url else "הגרסה שפורסמה אינה כוללת קובץ להורדה",
                "lastCheck": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            })
    except urllib.error.URLError as exc:
        with _lock:
            _state["error"] = "אין חיבור לבדיקת עדכונים (%s)" % exc.reason
    except Exception as exc:
        with _lock:
            _state["error"] = "בדיקת העדכונים נכשלה: %r" % (exc,)
    finally:
        with _lock:
            _state["checking"] = False
    return status()


def available():
    with _lock:
        latest = _state.get("latest")
    return bool(latest) and version.is_newer(latest)


def download(timeout=300):
    """מוריד את הגרסה החדשה לקובץ זמני. מחזיר נתיב או None."""
    with _lock:
        url = _state.get("url") or ""
    if not url or not _host_ok(url):
        return None
    exe = exe_path()
    if not exe:
        return None
    # לאותו כונן כמו ה-EXE, כדי שההחלפה תהיה פעולה אטומית ולא העתקה
    target = exe + ".new"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BellSystem"})
        with urllib.request.urlopen(req, timeout=timeout) as res, open(target, "wb") as fh:
            shutil.copyfileobj(res, fh)
    except Exception as exc:
        with _lock:
            _state["error"] = "ההורדה נכשלה: %r" % (exc,)
        try:
            os.remove(target)
        except OSError:
            pass
        return None

    # אימות בסיסי לפני שנחליף קובץ שרץ
    try:
        size = os.path.getsize(target)
        with open(target, "rb") as fh:
            magic = fh.read(2)
    except OSError:
        return None
    if size < MIN_SIZE or magic != b"MZ":
        with _lock:
            _state["error"] = "הקובץ שהתקבל אינו תוכנית תקינה"
        try:
            os.remove(target)
        except OSError:
            pass
        return None

    with _lock:
        _state["downloaded"] = target
        _state["error"] = ""
    engine.log("הורדה גרסה %s" % _state.get("latest"), "system")
    return target


def safe_to_restart(now=None):
    """(מותר?, סיבה) - האם אפשר להחליף גרסה ולהתחיל מחדש עכשיו."""
    from . import audio
    now = now or datetime.datetime.now().astimezone()
    if audio.is_playing():
        return False, "צלצול מתנגן כרגע"
    if not storage.is_active_session():
        return False, "המופע הזה אינו בסשן הפעיל"
    nxt = schedule.next_bell(now)
    if nxt:
        minutes = (nxt["at"] - now).total_seconds() / 60.0
        if minutes < QUIET_MINUTES:
            return False, "הצלצול הבא בעוד %d דקות" % max(0, int(minutes))
    return True, "אין צלצול בטווח %d דקות" % QUIET_MINUTES


def apply(path=None):
    """מחליף את ה-EXE ומפעיל מחדש. מחזיר True אם ההפעלה מחדש יצאה לדרך."""
    exe = exe_path()
    with _lock:
        path = path or _state.get("downloaded")
    if not exe or not path or not os.path.exists(path):
        return False

    backup = exe + ".old"
    try:
        if os.path.exists(backup):
            os.remove(backup)
    except OSError:
        pass
    try:
        # אפשר לשנות שם לקובץ רץ ב-Windows, אבל לא למחוק אותו
        os.replace(exe, backup)
    except OSError as exc:
        with _lock:
            _state["error"] = "אין הרשאה להחליף את התוכנה (%r)" % (exc,)
        return False
    try:
        os.replace(path, exe)
    except OSError as exc:
        os.replace(backup, exe)   # החזרה למצב הקודם
        with _lock:
            _state["error"] = "החלפת הקובץ נכשלה (%r)" % (exc,)
        return False

    engine.log("מתעדכן לגרסה %s ומופעל מחדש" % _state.get("latest"), "system")
    try:
        subprocess.Popen([exe, "--minimized", "--after-update", str(os.getpid())],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        with _lock:
            _state["error"] = "ההפעלה מחדש נכשלה (%r)" % (exc,)
        return False
    return True


def status():
    with _lock:
        data = dict(_state)
    data["current"] = version.VERSION
    data["frozen"] = bool(exe_path())
    data["available"] = available()
    data["auto"] = bool(config.settings().get("autoUpdate", True))
    if data["available"]:
        data["safe"], data["safeReason"] = safe_to_restart()
    else:
        data["safe"], data["safeReason"] = False, ""
    data.pop("url", None)
    return data


def _loop(on_quit):
    time.sleep(45)   # לא נוגסים בזמן העלייה
    while True:
        try:
            if config.settings().get("autoUpdate", True) and exe_path():
                if not available():
                    check()
                if available():
                    with _lock:
                        ready = _state.get("downloaded")
                    if not ready or not os.path.exists(ready):
                        ready = download()
                    if ready:
                        ok, reason = safe_to_restart()
                        if ok and apply(ready):
                            on_quit()
                            return
                        engine.log("עדכון ממתין: %s" % reason, "system")
        except Exception as exc:
            engine.log("שגיאה בעדכון: %r" % (exc,), "error")
        # כשיש עדכון מוכן בודקים שוב בקרוב, כדי לתפוס את החלון הפנוי
        time.sleep(300 if available() else CHECK_EVERY)


def start(on_quit):
    """מפעיל את הבדיקה התקופתית ברקע."""
    cleanup()
    threading.Thread(target=_loop, args=(on_quit,), name="bell-updater",
                     daemon=True).start()
