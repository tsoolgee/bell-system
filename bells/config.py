# -*- coding: utf-8 -*-
"""טעינה ושמירה של הגדרות המערכת."""

import copy
import hashlib
import json
import os
import sys
import threading
import uuid

from . import jewcal

APP_NAME = "BellSystem"

_lock = threading.RLock()
_data = None
_data_dir = None

CITIES = [
    ("ירושלים", 31.7683, 35.2137, 40),
    ("בני ברק", 32.0853, 34.8248, 22),
    ("תל אביב", 32.0853, 34.7818, 22),
    ("חיפה", 32.7940, 34.9896, 30),
    ("באר שבע", 31.2530, 34.7915, 22),
    ("אשדוד", 31.8014, 34.6435, 22),
    ("פתח תקווה", 32.0878, 34.8878, 22),
    ("נתניה", 32.3215, 34.8532, 22),
    ("מודיעין עילית", 31.9316, 35.0424, 22),
    ("ביתר עילית", 31.6994, 35.1211, 40),
    ("אלעד", 32.0500, 34.9500, 22),
    ("רחובות", 31.8928, 34.8113, 22),
    ("צפת", 32.9646, 35.4960, 30),
    ("טבריה", 32.7922, 35.5312, 30),
    ("אשקלון", 31.6688, 34.5743, 22),
    ("רמת גן", 32.0684, 34.8248, 22),
    ("חולון", 32.0114, 34.7722, 22),
    ("קרית ספר", 31.9316, 35.0424, 22),
    ("בית שמש", 31.7497, 34.9887, 30),
]

DEFAULT_SOUNDS = [
    {"id": "bell_classic", "name": "צלצול רגיל", "file": "bell_classic.wav", "builtin": True},
    {"id": "bell_break", "name": "צלצול הפסקה", "file": "bell_break.wav", "builtin": True},
    {"id": "chime", "name": "מנגינה", "file": "chime.wav", "builtin": True},
    {"id": "gong", "name": "גונג", "file": "gong.wav", "builtin": True},
    {"id": "siren", "name": "צלצול חירום", "file": "siren.wav", "builtin": True},
]


def _defaults():
    return {
        "version": 1,
        "settings": {
            "enabled": True,
            "muted": False,
            "volume": 100,
            "outputDevice": "",        # ריק = התקן ברירת המחדל של Windows
            "port": 8730,
            "city": "ירושלים",
            "lat": 31.7683,
            "lon": 35.2137,
            "candleMinutes": 40,
            "havdalahMode": "minutes",   # minutes | degrees
            "havdalahMinutes": 42,
            "havdalahDegrees": 8.5,
            "shabbatEnabled": True,
            "holidaysAuto": True,
            "israel": True,
            "erevChagStop": False,       # השבתה כבר מהבוקר בערב חג
            "autostart": False,
            "startMinimized": True,
            "requirePin": False,
            "pinHash": "",
            "ttsProvider": "gemini",   # gemini (אונליין) | sapi (אופליין)
            "ttsVoice": "Kore",
            "ttsSapiVoice": "",
            "ttsRate": 0,
            "ttsApiKey": "",           # נשמר מקומית בלבד, לא נכלל בגיבוי
        },
        "bells": [],
        "sounds": [],
        "holidayFlags": dict(jewcal.DEFAULT_HOLIDAY_FLAGS),
        "exceptions": [],
    }


def data_dir():
    global _data_dir
    if _data_dir is None:
        override = os.environ.get("BELLSYSTEM_DATA")
        if override:
            _data_dir = override
        elif sys.platform == "win32":
            _data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
        else:
            _data_dir = os.path.join(os.path.expanduser("~"), "." + APP_NAME.lower())
        os.makedirs(_data_dir, exist_ok=True)
        os.makedirs(os.path.join(_data_dir, "sounds"), exist_ok=True)
    return _data_dir


def sounds_dir():
    return os.path.join(data_dir(), "sounds")


def config_path():
    return os.path.join(data_dir(), "config.json")


def log_path():
    return os.path.join(data_dir(), "bells.log")


def _merge(base, loaded):
    """מיזוג עמוק כדי שהגדרות חדשות בגרסאות עתידיות לא ישברו קובץ ישן."""
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


SEED_BELLS = [
    ("08:00", "תחילת היום", "bell_classic"),
    ("08:45", "סוף שיעור ראשון", "bell_break"),
    ("09:00", "תחילת שיעור שני", "bell_classic"),
    ("09:45", "הפסקה", "bell_break"),
    ("10:05", "סוף הפסקה", "bell_classic"),
    ("10:50", "סוף שיעור שלישי", "bell_break"),
    ("11:05", "תחילת שיעור רביעי", "bell_classic"),
    ("11:50", "סוף היום", "chime"),
]


def _seed(data):
    """לוח לדוגמה בהפעלה הראשונה, כדי שיהיה ממה להתחיל."""
    for time_str, label, sound in SEED_BELLS:
        data["bells"].append({
            "id": new_id(), "time": time_str, "label": label, "sound": sound,
            "duration": 5, "days": [0, 1, 2, 3, 4, 5], "enabled": True,
        })
    return data


def load():
    global _data
    with _lock:
        if _data is not None:
            return _data
        data = _defaults()
        path = config_path()
        if not os.path.exists(path):
            _seed(data)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    _merge(data, json.load(fh))
            except Exception:
                # קובץ פגום לא יפיל את המערכת - שומרים אותו בצד וממשיכים
                try:
                    os.replace(path, path + ".broken")
                except OSError:
                    pass
        _data = data
        return _data


def save():
    with _lock:
        path = config_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(_data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def get():
    return load()


def settings():
    return load()["settings"]


def new_id():
    return uuid.uuid4().hex[:12]


def hash_pin(pin):
    return hashlib.sha256(("bellsystem$" + str(pin)).encode("utf-8")).hexdigest()


def check_pin(pin):
    st = settings()
    if not st.get("requirePin"):
        return True
    return bool(st.get("pinHash")) and hash_pin(pin) == st["pinHash"]


def snapshot():
    with _lock:
        return copy.deepcopy(load())


def replace(new_data):
    """שחזור מגיבוי - מחליף את כל התצורה."""
    global _data
    with _lock:
        base = _defaults()
        _merge(base, new_data)
        _data = base
        save()
        return _data
