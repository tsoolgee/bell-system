# -*- coding: utf-8 -*-
"""עדכון אוטומטי.

הכלל שחייב להחזיק: המערכת לא מחליפה גרסה ולא מתחילה מחדש כשצלצול קרוב.
עדכון שמפספס צלצול גרוע יותר מעדכון שמחכה עוד יום.
"""
import datetime
import os
import shutil
import sys

DATA = os.path.join(os.environ["TEMP"], "BellUpdateTest")
shutil.rmtree(DATA, ignore_errors=True)
os.makedirs(os.path.join(DATA, "sounds"), exist_ok=True)
os.environ["BELLSYSTEM_DATA"] = DATA

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import audio, config, storage, updater, version  # noqa: E402

fails = []


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name +
          ("  -> " + repr(detail) if not condition else ""))
    if not condition:
        fails.append(name)


print("--- השוואת גרסאות ---")
check("גרסה גבוהה מזוהה כחדשה", version.is_newer("1.2.0", "1.1.0"))
check("אותה גרסה אינה חדשה", not version.is_newer("1.1.0", "1.1.0"))
check("גרסה נמוכה אינה חדשה", not version.is_newer("1.0.9", "1.1.0"))
check("תחילית v מתעלמים ממנה", version.is_newer("v1.1.1", "1.1.0"))
check("גרסה עם תווית עדיין מושווית", version.is_newer("1.2.0-beta", "1.1.0"))
check("מחרוזת ריקה אינה מפילה", not version.is_newer("", "1.1.0"))
check("השלמת חלקים חסרים", version.as_tuple("2") == (2, 0, 0), version.as_tuple("2"))

print("--- מאיפה מותר להוריד ---")
check("קישור GitHub מאושר",
      updater._host_ok("https://github.com/tsoolgee/bell-system/releases/download/v1/BellSystem.exe"))
check("objects.githubusercontent מאושר",
      updater._host_ok("https://objects.githubusercontent.com/x/y"))
check("אתר אחר נדחה", not updater._host_ok("https://evil.example.com/BellSystem.exe"))
check("אתר שמתחזה נדחה", not updater._host_ok("https://github.com.evil.example/x"))
check("http לא מוצפן נדחה", not updater._host_ok("http://github.com/x"))
check("קישור ריק נדחה", not updater._host_ok(""))

print("--- מתי מותר להתחיל מחדש ---")
cfg = config.get()
cfg["settings"]["city"] = "ירושלים"
cfg["exceptions"] = []


def with_bell_in(minutes):
    when = datetime.datetime.now().astimezone() + datetime.timedelta(minutes=minutes)
    cfg["bells"] = [{"id": "b", "time": when.strftime("%H:%M"), "label": "בדיקה",
                     "sound": "bell_classic", "duration": 5,
                     "days": [0, 1, 2, 3, 4, 5, 6], "enabled": True}]
    return updater.safe_to_restart()


ok, reason = with_bell_in(3)
check("צלצול בעוד 3 דקות חוסם עדכון", not ok, reason)
ok, reason = with_bell_in(10)
check("צלצול בעוד 10 דקות חוסם עדכון", not ok, reason)
ok, reason = with_bell_in(90)
check("צלצול בעוד 90 דקות מאפשר עדכון", ok, reason)
print("       %s" % reason)

cfg["bells"] = []
ok, reason = updater.safe_to_restart()
check("בלי צלצולים בכלל מותר לעדכן", ok, reason)

real_playing = audio.is_playing
audio.is_playing = lambda: True
updater.audio = audio
ok, reason = updater.safe_to_restart()
check("צלצול שמתנגן כרגע חוסם עדכון", not ok, reason)
audio.is_playing = real_playing

real_session = storage.is_active_session
storage.is_active_session = lambda: False
ok, reason = updater.safe_to_restart()
check("מופע בסשן מנותק לא מעדכן", not ok, reason)
storage.is_active_session = real_session

print("--- מצב ---")
st = updater.status()
check("המצב מדווח גרסה נוכחית", st["current"] == version.VERSION, st.get("current"))
check("מזוהה שרץ מהמקור ולא כ-EXE", st["frozen"] is False, st.get("frozen"))
check("apply לא עושה כלום בלי EXE", updater.apply("nope.exe") is False)
check("download לא עושה כלום בלי EXE", updater.download() is None)

print("--- בדיקה מול GitHub ---")
st = updater.check()
if st.get("error"):
    print("       דילוג: %s" % st["error"])
else:
    check("התקבלה גרסה מהשרת", bool(st.get("latest")), st)
    check("הגרסה שהתקבלה בפורמט תקין",
          version.as_tuple(st["latest"]) != (0, 0, 0), st.get("latest"))
    print("       גרסה אחרונה שפורסמה: %s" % st["latest"])

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
