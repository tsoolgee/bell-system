# -*- coding: utf-8 -*-
"""מנגנון ההחלטה: האם מותר להשמיע צלצול ברגע נתון, ומתי הצלצול הבא."""

import datetime

from pyluach import dates

from . import config, jewcal, zmanim

# סיבות חסימה
BLOCK_SYSTEM_OFF = "system_off"
BLOCK_MUTED = "muted"
BLOCK_HOLIDAY = "holiday"
BLOCK_EXCEPTION = "exception"


def _loc(st):
    return float(st.get("lat", 31.7683)), float(st.get("lon", 35.2137))


def candle_time(d, st):
    """זמן כניסת שבת/חג ביום d (שקיעה פחות דקות ההדלקה)."""
    lat, lon = _loc(st)
    ss = zmanim.sunset(d, lat, lon)
    if ss is None:
        return None
    return ss - datetime.timedelta(minutes=int(st.get("candleMinutes", 40)))


def havdalah_time(d, st):
    """זמן צאת שבת/חג ביום d."""
    lat, lon = _loc(st)
    if st.get("havdalahMode") == "degrees":
        t = zmanim.dusk_degrees(d, lat, lon, float(st.get("havdalahDegrees", 8.5)))
        if t is not None:
            return t
    ss = zmanim.sunset(d, lat, lon)
    if ss is None:
        return None
    return ss + datetime.timedelta(minutes=int(st.get("havdalahMinutes", 42)))


def _holy_kind(d, st):
    """('shabbat'|'yomtov', שם) עבור יום שיש בו איסור מלאכה, אחרת (None, None)."""
    if jewcal.weekday_index(d) == 6:
        return "shabbat", "שבת"
    if st.get("holidaysAuto", True) and jewcal.is_yomtov(d, st.get("israel", True)):
        key = dates.GregorianDate(d.year, d.month, d.day).to_heb().festival(
            israel=st.get("israel", True), include_working_days=False)
        if config.get()["holidayFlags"].get(key, True):
            return "yomtov", jewcal.HOLIDAY_HE.get(key, key) or "יום טוב"
    return None, None


def holy_window(now, st):
    """אם הרגע הנוכחי נמצא בתוך שבת/יום טוב - מחזיר את פרטי החלון."""
    if not st.get("shabbatEnabled", True):
        return None
    today = now.date()
    for offset in (-1, 0, 1):
        d = today + datetime.timedelta(days=offset)
        kind, name = _holy_kind(d, st)
        if not kind:
            continue
        start = candle_time(d - datetime.timedelta(days=1), st)
        end = havdalah_time(d, st)
        if start and end and start <= now <= end:
            return {"kind": kind, "name": name, "start": start, "end": end, "date": d}
    return None


def next_holy_window(now, st, days=14):
    """חלון השבת/החג הקרוב הבא (לתצוגה בממשק)."""
    if not st.get("shabbatEnabled", True):
        return None
    for offset in range(0, days):
        d = now.date() + datetime.timedelta(days=offset)
        kind, name = _holy_kind(d, st)
        if not kind:
            continue
        start = candle_time(d - datetime.timedelta(days=1), st)
        end = havdalah_time(d, st)
        if start and end and now < end:
            return {"kind": kind, "name": name, "start": start, "end": end, "date": d}
    return None


def _hebrew_to_civil(hyear, hmonth, hday):
    try:
        return dates.HebrewDate(hyear, hmonth, hday).to_pydate()
    except Exception:
        # אדר ב' בשנה פשוטה, או ל' בחודש חסר - מצמצמים לתאריך תקף קרוב
        for m in (hmonth - 1, 12):
            for day in (hday, hday - 1, hday - 2):
                try:
                    return dates.HebrewDate(hyear, m, day).to_pydate()
                except Exception:
                    continue
        return None


def _exception_match(d, exc):
    if not exc.get("enabled", True):
        return False
    if exc.get("type") == "hebrew":
        hy = dates.GregorianDate(d.year, d.month, d.day).to_heb().year
        fm, fd = int(exc["fromMonth"]), int(exc["fromDay"])
        tm = int(exc.get("toMonth") or fm)
        td = int(exc.get("toDay") or fd)
        for year in (hy, hy - 1):
            start = _hebrew_to_civil(year, fm, fd)
            end = _hebrew_to_civil(year, tm, td)
            if start and end and end < start:
                end = _hebrew_to_civil(year + 1, tm, td)
            if start and end and start <= d <= end:
                return True
        return False
    try:
        start = datetime.date.fromisoformat(exc["from"])
        end = datetime.date.fromisoformat(exc.get("to") or exc["from"])
    except (KeyError, ValueError, TypeError):
        return False
    return start <= d <= end


def day_block(d, st):
    """חסימה שחלה על יום לועזי שלם (חג שאינו יום טוב, חופשה ידנית)."""
    cfg = config.get()
    for exc in cfg.get("exceptions", []):
        if _exception_match(d, exc):
            return {"reason": BLOCK_EXCEPTION, "label": exc.get("name") or "השבתה"}
    if st.get("holidaysAuto", True):
        key = jewcal.holiday_key(d, st.get("israel", True))
        if key and cfg["holidayFlags"].get(key) and not jewcal.is_yomtov(d, st.get("israel", True)):
            return {"reason": BLOCK_HOLIDAY, "label": jewcal.HOLIDAY_HE.get(key, key)}
        if st.get("erevChagStop"):
            nxt = d + datetime.timedelta(days=1)
            if jewcal.is_yomtov(nxt, st.get("israel", True)):
                name = jewcal.yomtov_name_he(nxt, st.get("israel", True))
                return {"reason": BLOCK_HOLIDAY, "label": "ערב " + (name or "חג")}
    return None


def evaluate(now=None, include_manual=True):
    """הבדיקה המלאה, לפי סדר העדיפויות שבאפיון."""
    st = config.settings()
    now = now or datetime.datetime.now().astimezone()
    if include_manual:
        if not st.get("enabled", True):
            return {"blocked": True, "reason": BLOCK_SYSTEM_OFF, "label": "המערכת כבויה"}
        if st.get("muted"):
            return {"blocked": True, "reason": BLOCK_MUTED, "label": "השתקה ידנית"}
    window = holy_window(now, st)
    if window:
        return {"blocked": True, "reason": window["kind"], "label": window["name"],
                "until": window["end"].isoformat()}
    blocked = day_block(now.date(), st)
    if blocked:
        return {"blocked": True, "reason": blocked["reason"], "label": blocked["label"]}
    return {"blocked": False, "reason": None, "label": "המערכת פעילה"}


def bell_matches_day(bell, d):
    return jewcal.weekday_index(d) in [int(x) for x in bell.get("days", [])]


def bells_for_day(d, only_enabled=True):
    out = []
    for bell in config.get()["bells"]:
        if only_enabled and not bell.get("enabled", True):
            continue
        if bell_matches_day(bell, d):
            out.append(bell)
    return sorted(out, key=lambda b: b.get("time", "00:00"))


def bell_datetime(d, bell):
    hh, mm = (bell.get("time") or "00:00").split(":")[:2]
    return datetime.datetime(d.year, d.month, d.day, int(hh), int(mm)).astimezone()


def next_bell(now=None, days=21):
    """הצלצול הבא שיושמע בפועל - מדלג על שבתות, חגים והשבתות."""
    now = now or datetime.datetime.now().astimezone()
    for offset in range(0, days):
        d = now.date() + datetime.timedelta(days=offset)
        for bell in bells_for_day(d):
            when = bell_datetime(d, bell)
            if when <= now:
                continue
            if evaluate(when, include_manual=False)["blocked"]:
                continue
            return {"bell": bell, "at": when}
    return None
