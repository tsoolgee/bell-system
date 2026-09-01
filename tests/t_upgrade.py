# -*- coding: utf-8 -*-
"""שדרוג גרסה לא נוגע בהגדרות של המוסד.

ה-EXE מוחלף, תיקיית הנתונים לא. ובנוסף: קובץ הגדרות שנשמר בגרסה ישנה
ולא מכיר מפתחות חדשים חייב לשרוד - לקבל את הברירות החדשות ולשמור את
כל מה שהמנהל הגדיר.
"""
import json
import os
import shutil
import sys

DATA = os.path.join(os.environ["TEMP"], "BellUpgradeTest")
shutil.rmtree(DATA, ignore_errors=True)
os.makedirs(os.path.join(DATA, "sounds"), exist_ok=True)
os.environ["BELLSYSTEM_DATA"] = DATA

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import config  # noqa: E402

fails = []


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name +
          ("  -> " + repr(detail) if not condition else ""))
    if not condition:
        fails.append(name)


# --- תצורה כפי שגרסה ישנה שמרה אותה: בלי המפתחות שנוספו מאז ---
OLD = {
    "version": 1,
    "settings": {
        "enabled": True,
        "muted": False,
        "volume": 75,
        "city": "בני ברק",
        "lat": 32.0853,
        "lon": 34.8248,
        "candleMinutes": 22,
        "requirePin": True,
        "pinHash": "abc123",
        # אין outputDevice, אין ttsProvider, אין havdalahMode...
    },
    "bells": [
        {"id": "keepme", "time": "07:55", "label": "תפילה", "sound": "chime",
         "duration": 8, "days": [0, 1, 2, 3, 4], "enabled": True},
    ],
    "sounds": [{"id": "own1", "name": "צלצול של המוסד", "file": "custom.mp3"}],
    "holidayFlags": {"Purim": True},
    "exceptions": [{"id": "x", "name": "חופשת קיץ", "type": "gregorian",
                    "from": "2026-07-01", "to": "2026-08-20", "enabled": True}],
}
with open(os.path.join(DATA, "config.json"), "w", encoding="utf-8") as fh:
    json.dump(OLD, fh, ensure_ascii=False)
with open(os.path.join(DATA, "sounds", "custom.mp3"), "wb") as fh:
    fh.write(b"\x49\x44\x33 pretend this is the school's own recording")

cfg = config.get()
st = cfg["settings"]

print("--- מה שהמנהל הגדיר שורד ---")
check("עוצמה נשמרה", st["volume"] == 75, st["volume"])
check("עיר נשמרה", st["city"] == "בני ברק", st["city"])
check("דקות הדלקת נרות נשמרו", st["candleMinutes"] == 22, st["candleMinutes"])
check("קוד המנהל נשמר", st["pinHash"] == "abc123" and st["requirePin"] is True)
check("הצלצולים נשמרו", [b["id"] for b in cfg["bells"]] == ["keepme"], cfg["bells"])
check("שעה ותווית נשמרו",
      cfg["bells"][0]["time"] == "07:55" and cfg["bells"][0]["label"] == "תפילה")
check("ההשבתה הידנית נשמרה", len(cfg["exceptions"]) == 1, cfg["exceptions"])
check("דגל חג שהמנהל שינה נשמר", cfg["holidayFlags"]["Purim"] is True)
check("הצליל שהועלה נשמר ברשימה", cfg["sounds"] == OLD["sounds"], cfg["sounds"])
check("קובץ הצליל עצמו עדיין על הדיסק",
      os.path.exists(os.path.join(DATA, "sounds", "custom.mp3")))

print("--- מפתחות חדשים מקבלים ברירת מחדל ---")
check("outputDevice נוסף", st.get("outputDevice") == "", st.get("outputDevice"))
check("havdalahMode נוסף", st.get("havdalahMode") == "minutes", st.get("havdalahMode"))
check("ttsProvider נוסף", st.get("ttsProvider") == "gemini", st.get("ttsProvider"))
check("shabbatEnabled נוסף", st.get("shabbatEnabled") is True)
check("דגלי חגים שלא הוגדרו קיבלו ברירת מחדל",
      cfg["holidayFlags"].get("Yom Kippur") is True)
check("לא נזרע לוח לדוגמה על תצורה קיימת", len(cfg["bells"]) == 1, len(cfg["bells"]))

print("--- שמירה חוזרת לא מאבדת כלום ---")
config.save()
with open(os.path.join(DATA, "config.json"), encoding="utf-8") as fh:
    saved = json.load(fh)
check("הקובץ שנשמר מכיל את הצלצול", saved["bells"][0]["id"] == "keepme")
check("הקובץ שנשמר מכיל את העוצמה הישנה", saved["settings"]["volume"] == 75)
check("הקובץ שנשמר מכיל את המפתחות החדשים", "outputDevice" in saved["settings"])

print("--- תיקיית הנתונים אינה תלויה במיקום ה-EXE ---")
check("הנתונים תחת APPDATA ולא ליד התוכנה",
      config.data_dir() == DATA and "dist" not in config.data_dir(), config.data_dir())

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
