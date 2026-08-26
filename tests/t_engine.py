# -*- coding: utf-8 -*-
"""בדיקת מנוע ההחלטה - מה מצלצל בפועל ומה נחסם."""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BELLSYSTEM_DATA"] = os.path.join(os.environ["TEMP"], "BellSystemTest")

from bells import audio, config, engine  # noqa: E402

played = []
audio.play = lambda path, duration=5, volume=90, on_done=None: (played.append(os.path.basename(path)), True)[1]
engine.log = lambda *a, **k: None

cfg = config.get()
cfg["bells"] = [
    {"id": "morning", "time": "08:00", "label": "בוקר", "sound": "bell_classic",
     "duration": 5, "days": [0, 1, 2, 3, 4, 5], "enabled": True},
    {"id": "late_fri", "time": "18:45", "label": "שישי מאוחר", "sound": "chime",
     "duration": 5, "days": [5], "enabled": True},
    {"id": "early_fri", "time": "18:00", "label": "שישי מוקדם", "sound": "chime",
     "duration": 5, "days": [5], "enabled": True},
    {"id": "sat", "time": "10:00", "label": "שבת", "sound": "gong",
     "duration": 5, "days": [6], "enabled": True},
    {"id": "off", "time": "08:00", "label": "מושבת", "sound": "gong",
     "duration": 5, "days": [0, 1, 2, 3, 4, 5], "enabled": False},
]
cfg["settings"]["city"] = "ירושלים"
cfg["exceptions"] = []

fails = []


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name + ("  -> " + str(detail) if detail and not condition else ""))
    if not condition:
        fails.append(name)


def fire(iso, seconds=0):
    """מריץ טיק אחד בזמן נתון ומחזיר את הקבצים שנוגנו."""
    played.clear()
    engine._fired.clear()
    now = datetime.datetime.fromisoformat(iso).astimezone() + datetime.timedelta(seconds=seconds)
    engine._tick(now)
    return list(played)


# 2026-08-28 שישי: כניסת שבת 18:28, יציאה 2026-08-29 בשעה 19:49
print("--- שבת ---")
check("צלצול שישי לפני כניסת שבת מצלצל", fire("2026-08-28T18:00") == ["chime.wav"])
check("צלצול שישי אחרי כניסת שבת נחסם", fire("2026-08-28T18:45") == [])
check("צלצול בשבת בבוקר נחסם", fire("2026-08-29T10:00") == [])
check("בוקר רגיל מצלצל", fire("2026-08-27T08:00") == ["bell_classic.wav"])
check("צלצול מושבת לא מצלצל", "gong.wav" not in fire("2026-08-27T08:00"))

print("--- מוצאי שבת ---")
cfg["bells"].append({"id": "motzash", "time": "20:30", "label": "מוצ\"ש", "sound": "gong",
                     "duration": 5, "days": [6], "enabled": True})
check("צלצול אחרי צאת שבת מצלצל", fire("2026-08-29T20:30") == ["gong.wav"])
cfg["bells"] = [b for b in cfg["bells"] if b["id"] != "motzash"]

print("--- חגים ---")
check("יום א' של פסח נחסם", fire("2026-04-02T08:00") == [])
check("חול המועד פסח נחסם כברירת מחדל", fire("2026-04-05T08:00") == [])
config.get()["holidayFlags"]["Chol HaMoed Pesach"] = False
check("חול המועד מצלצל אחרי ביטול הדגל", fire("2026-04-05T08:00") == ["bell_classic.wav"])
check("ביטול חול המועד לא משפיע על יום טוב", fire("2026-04-02T08:00") == [])
config.get()["holidayFlags"]["Chol HaMoed Pesach"] = True
check("שביעי של פסח נחסם", fire("2026-04-08T08:00") == [])
check("יום אחרי פסח מצלצל", fire("2026-04-09T08:00") == ["bell_classic.wav"])
check("יום כיפור נחסם", fire("2026-09-21T08:00") == [])
check("פורים מצלצל כברירת מחדל", fire("2026-03-03T08:00") == ["bell_classic.wav"])

config.get()["holidayFlags"]["Purim"] = True
check("פורים נחסם אחרי סימון", fire("2026-03-03T08:00") == [])
config.get()["holidayFlags"]["Purim"] = False

print("--- השבתה ידנית ---")
cfg["exceptions"] = [{"id": "x1", "name": "חופשת קיץ", "type": "gregorian",
                      "from": "2026-07-01", "to": "2026-08-20", "enabled": True}]
check("יום בתוך החופשה נחסם", fire("2026-07-15T08:00") == [])
check("יום אחרי החופשה מצלצל", fire("2026-08-21T08:00") == ["bell_classic.wav"])
cfg["exceptions"] = [{"id": "x2", "name": "חנוכה", "type": "hebrew", "fromMonth": 9,
                      "fromDay": 25, "toMonth": 10, "toDay": 2, "enabled": True}]
check("טווח עברי חוצה חודשים נחסם", fire("2026-12-08T08:00") == [])
check("יום לפני הטווח העברי מצלצל", fire("2026-12-04T08:00") == ["bell_classic.wav"])
cfg["exceptions"] = []

print("--- השתקה וכיבוי ---")
cfg["settings"]["muted"] = True
check("השתקה ידנית חוסמת", fire("2026-08-27T08:00") == [])
cfg["settings"]["muted"] = False
cfg["settings"]["enabled"] = False
check("מערכת כבויה חוסמת", fire("2026-08-27T08:00") == [])
cfg["settings"]["enabled"] = True

print("--- חלון החסד ---")
check("איחור של 10 שניות עדיין מצלצל", fire("2026-08-27T08:00", 10) == ["bell_classic.wav"])
check("איחור של 60 שניות לא מצלצל", fire("2026-08-27T08:00", 60) == [])
check("צלצול לא מופעל פעמיים", (lambda: (fire("2026-08-27T08:00"),
      engine._tick(datetime.datetime.fromisoformat("2026-08-27T08:00:05").astimezone()),
      len(played))[2])() == 1)

print("--- כיבוי חישוב שבת ---")
cfg["settings"]["shabbatEnabled"] = False
check("ביטול חישוב השבת מאפשר צלצול בשבת", fire("2026-08-29T10:00") == ["gong.wav"])
cfg["settings"]["shabbatEnabled"] = True

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
