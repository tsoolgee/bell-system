# -*- coding: utf-8 -*-
"""מנוע ההרצה - רץ ברקע ובודק בכל שנייה אם יש צלצול להשמיע."""

import datetime
import os
import threading
import time
import traceback

from . import audio, config, jewcal, schedule, sounds, storage

# חלון החסד: צלצול שהגיע זמנו יופעל רק אם לא עברו יותר מכך שניות
# (כדי שצלצולים ישנים לא "יתפרצו" אחרי שהמחשב חוזר משינה).
GRACE_SECONDS = 25

_thread = None
_stop = threading.Event()
_fired = set()
_log = []
_log_lock = threading.Lock()
_listeners = []


def log(message, kind="info"):
    entry = {"time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
             "kind": kind, "message": message}
    with _log_lock:
        _log.append(entry)
        del _log[:-300]
    try:
        with open(config.log_path(), "a", encoding="utf-8") as fh:
            fh.write("%s\t%s\t%s\n" % (entry["time"], kind, message))
    except OSError:
        pass


def recent_log(limit=80):
    with _log_lock:
        return list(reversed(_log[-limit:]))


def add_listener(fn):
    _listeners.append(fn)


def _notify():
    for fn in list(_listeners):
        try:
            fn()
        except Exception:
            pass


def sound_path(sound_id):
    for snd in config.DEFAULT_SOUNDS:
        if snd["id"] == sound_id:
            return os.path.join(config.sounds_dir(), snd["file"])
    for snd in config.get().get("sounds", []):
        if snd["id"] == sound_id:
            return os.path.join(config.sounds_dir(), snd["file"])
    return None


def sound_name(sound_id):
    for snd in config.DEFAULT_SOUNDS + config.get().get("sounds", []):
        if snd["id"] == sound_id:
            return snd["name"]
    return sound_id or ""


def all_sounds():
    return config.DEFAULT_SOUNDS + config.get().get("sounds", [])


def ring(sound_id, duration=5, label="", manual=False):
    """השמעת צלצול בפועל."""
    st = config.settings()
    path = sound_path(sound_id) or sound_path("bell_classic")
    ok = audio.play(path, duration=duration, volume=st.get("volume", 90),
                    device=st.get("outputDevice") or None)
    log(("צלצול ידני: " if manual else "צלצול: ") + (label or sound_name(sound_id)),
        "ring" if ok else "error")
    _notify()
    return ok


def _tick(now):
    # משתמש אחר במחשב אולי שינה את הלוח מהסשן שלו
    config.refresh()
    st = config.settings()
    verdict = schedule.evaluate(now)
    # רק המופע שיושב מול המסך מצלצל. סשן מנותק לא מקבל ניתוב שמע
    # ב-Windows, ואם גם הוא היה מצלצל אף אחד לא היה שומע - ובמקביל
    # היינו מסמנים את הצלצול כאילו הופעל.
    on_console = storage.is_active_session()
    today = now.date()
    for bell in schedule.bells_for_day(today):
        key = (today.isoformat(), bell["id"])
        if key in _fired:
            continue
        when = schedule.bell_datetime(today, bell)
        delta = (now - when).total_seconds()
        if delta < 0 or delta > GRACE_SECONDS:
            continue
        if not on_console:
            continue   # לא מסמנים כבוצע - המופע הפעיל יטפל בזה
        _fired.add(key)
        if verdict["blocked"]:
            log("צלצול %s (%s) לא הופעל - %s" % (bell.get("time"), bell.get("label") or "",
                                                 verdict["label"]), "skip")
            continue
        ring(bell.get("sound"), int(bell.get("duration") or 5), bell.get("label"))


def _cleanup_fired(now):
    keep = {now.date().isoformat(), (now.date() - datetime.timedelta(days=1)).isoformat()}
    for key in [k for k in _fired if k[0] not in keep]:
        _fired.discard(key)


def _loop():
    log("המערכת עלתה", "system")
    last_cleanup = None
    while not _stop.is_set():
        try:
            now = datetime.datetime.now().astimezone()
            _tick(now)
            if last_cleanup != now.date():
                _cleanup_fired(now)
                last_cleanup = now.date()
        except Exception:
            log("שגיאה במנוע: " + traceback.format_exc(limit=2), "error")
        _stop.wait(0.5)


def start():
    global _thread
    sounds.ensure(config.sounds_dir())
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="bell-engine", daemon=True)
    _thread.start()


def shutdown():
    _stop.set()
    audio.stop()


def status():
    """מצב המערכת המלא - מה שהממשק והמגש מציגים."""
    now = datetime.datetime.now().astimezone()
    st = config.settings()
    verdict = schedule.evaluate(now)
    nxt = schedule.next_bell(now)
    window = schedule.next_holy_window(now, st)
    out = {
        "session": {
            "id": storage.current_session(),
            "active": storage.is_active_session(),
            "console": storage.active_console_session(),
        },
        "storage": config.storage_info(),
        "now": now.isoformat(timespec="seconds"),
        "time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%d/%m/%Y"),
        "weekday": jewcal.HEB_WEEKDAYS[jewcal.weekday_index(now.date())],
        "hebrewDate": jewcal.hebrew_date_string(now.date()),
        "blocked": verdict["blocked"],
        "reason": verdict["reason"],
        "statusLabel": verdict["label"],
        "blockedUntil": verdict.get("until"),
        "enabled": st.get("enabled", True),
        "muted": st.get("muted", False),
        "playing": audio.is_playing(),
        "todayHoliday": jewcal.holiday_name_he(now.date(), st.get("israel", True)),
        "bellsToday": len(schedule.bells_for_day(now.date())),
    }
    if nxt:
        seconds = int((nxt["at"] - now).total_seconds())
        out["next"] = {
            "time": nxt["at"].strftime("%H:%M"),
            "label": nxt["bell"].get("label") or "צלצול",
            "sound": sound_name(nxt["bell"].get("sound")),
            "date": nxt["at"].strftime("%d/%m/%Y"),
            "weekday": jewcal.HEB_WEEKDAYS[jewcal.weekday_index(nxt["at"].date())],
            "isToday": nxt["at"].date() == now.date(),
            "seconds": seconds,
        }
    if window:
        out["shabbat"] = {
            "kind": window["kind"],
            "name": window["name"],
            "start": window["start"].strftime("%H:%M"),
            "startDate": window["start"].strftime("%d/%m"),
            "end": window["end"].strftime("%H:%M"),
            "endDate": window["end"].strftime("%d/%m"),
        }
    return out


def notify():
    """רענון מיידי של מציגי המצב (מגש המערכת)."""
    _notify()
