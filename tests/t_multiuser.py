# -*- coding: utf-8 -*-
"""כמה משתמשי Windows על אותו מחשב.

שלושה דברים שחייבים לעבוד, אחרת מזכיר שמתחבר למשתמש שלו נשאר בלי צלצולים:
* ההגדרות משותפות, ולא נפרדות לכל פרופיל.
* מופע בסשן מנותק לא מצלצל - וגם לא מסמן את הצלצול כבוצע, אחרת המופע
  שכן נשמע ידלג עליו.
* שינוי שנעשה בסשן אחד נקלט בשני.
"""
import datetime
import json
import os
import shutil
import sys

DATA = os.path.join(os.environ["TEMP"], "BellMultiUserTest")
shutil.rmtree(DATA, ignore_errors=True)
os.makedirs(os.path.join(DATA, "sounds"), exist_ok=True)
os.environ["BELLSYSTEM_DATA"] = DATA

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import audio, config, engine, storage  # noqa: E402

fails = []


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name +
          ("  -> " + repr(detail) if not condition else ""))
    if not condition:
        fails.append(name)


played = []
audio.play = lambda path, duration=5, volume=90, device=None, on_done=None: (
    played.append(os.path.basename(path)), True)[1]
engine.log = lambda *a, **k: None

cfg = config.get()
cfg["bells"] = [{"id": "b1", "time": "08:00", "label": "בוקר", "sound": "bell_classic",
                 "duration": 5, "days": [0, 1, 2, 3, 4, 5], "enabled": True}]
cfg["exceptions"] = []
cfg["settings"]["city"] = "ירושלים"
config.save()

WHEN = datetime.datetime.fromisoformat("2026-08-27T08:00").astimezone()


def fire():
    played.clear()
    engine._fired.clear()
    engine._tick(WHEN)
    return list(played)


print("--- זיהוי הסשן ---")
mine, console = storage.current_session(), storage.active_console_session()
print("       סשן נוכחי=%s | סשן קונסולה=%s" % (mine, console))
check("זוהה מספר סשן", mine >= 0, mine)
check("אנחנו בסשן הפעיל בזמן הבדיקה", storage.is_active_session())

print("--- רק הסשן הפעיל מצלצל ---")
check("בסשן פעיל הצלצול מושמע", fire() == ["bell_classic.wav"])

real = storage.is_active_session
storage.is_active_session = lambda: False
engine.storage.is_active_session = storage.is_active_session
played.clear()
engine._fired.clear()
engine._tick(WHEN)
check("בסשן מנותק אין השמעה", played == [], played)
check("הצלצול לא סומן כבוצע", not engine._fired, engine._fired)

# עכשיו אותו רגע בדיוק, מהמופע שכן יושב מול המסך
storage.is_active_session = real
engine.storage.is_active_session = real
played.clear()
engine._tick(WHEN)
check("המופע הפעיל עדיין מצלצל את אותו צלצול", played == ["bell_classic.wav"], played)

print("--- שינוי מסשן אחר נקלט ---")
path = config.config_path()
with open(path, encoding="utf-8") as fh:
    raw = json.load(fh)
raw["bells"][0]["time"] = "09:30"
raw["bells"][0]["label"] = "שונה מהמזכיר"
raw["settings"]["volume"] = 55
os.utime(path, None)
with open(path, "w", encoding="utf-8") as fh:
    json.dump(raw, fh, ensure_ascii=False)

config.refresh()
check("השעה החדשה נקלטה", config.get()["bells"][0]["time"] == "09:30",
      config.get()["bells"][0]["time"])
check("התווית החדשה נקלטה", config.get()["bells"][0]["label"] == "שונה מהמזכיר")
check("ההגדרה החדשה נקלטה", config.settings()["volume"] == 55)

played.clear()
engine._fired.clear()
engine._tick(WHEN)
check("לא מצלצל לפי הלוח הישן", played == [], played)
played.clear()
engine._tick(datetime.datetime.fromisoformat("2026-08-27T09:30").astimezone())
check("מצלצל לפי הלוח החדש", played == ["bell_classic.wav"], played)

print("--- שמירה שלנו לא גורמת לטעינה מיותרת ---")
before = config.get()["bells"][0]["label"]
config.settings()["volume"] = 77
config.save()
config.refresh()
check("השמירה שלנו נשמרה", config.settings()["volume"] == 77)
check("שאר התצורה לא השתנתה", config.get()["bells"][0]["label"] == before)

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
