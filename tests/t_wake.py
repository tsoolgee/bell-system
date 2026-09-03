# -*- coding: utf-8 -*-
"""העָרת המחשב לקראת צלצול.

מחשב שנרדם הוא מערכת צלצולים מושבתת, ולכן המערכת קובעת ל-Windows טיימר
שמעיר אותו מעט לפני הצלצול הבא. את ההערה עצמה אי אפשר לבדוק בלי להרדים
את המחשב, אבל אפשר לבדוק את כל מה שסביבה: שהטיימר נקבע, שהוא נפתח בזמן,
שהוא מכוון לצלצול הנכון, ושהוא מבוטל כשאין למה להעיר.
"""
import datetime
import os
import shutil
import sys
import time

DATA = os.path.join(os.environ["TEMP"], "BellWakeTest")
shutil.rmtree(DATA, ignore_errors=True)
os.makedirs(os.path.join(DATA, "sounds"), exist_ok=True)
os.environ["BELLSYSTEM_DATA"] = DATA

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import config, engine, wake  # noqa: E402

fails = []


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name +
          ("  -> " + repr(detail) if not condition else ""))
    if not condition:
        fails.append(name)


print("--- יכולת המחשב ---")
print("       תומך בשינה: %s" % wake.supported())
ac, dc = wake.timers_allowed(both=True)
names = {0: "כבוי", 1: "מאופשר", 2: "חשובים בלבד", None: "לא ידוע"}
print("       טיימרים להערה: חשמל=%s  סוללה=%s" % (names.get(ac), names.get(dc)))
check("ההגדרה נקראה מתוכנית החשמל", ac is not None, ac)

allowed_admin, text = wake.pending()
print("       דיווח Windows על טיימרים ממתינים: %s"
      % ("זמין" if allowed_admin else "דורש הרשאת מנהל"))
check("חוסר הרשאה אינו מדווח כ'אין טיימר'", isinstance(allowed_admin, bool))

print("--- קביעת טיימר ---")
wake.start()
now = datetime.datetime.now().astimezone()
bell = now + datetime.timedelta(minutes=30)
at = wake.arm(bell, lead_seconds=60)
check("הטיימר נקבע", at is not None, at)
check("ההערה דקה לפני הצלצול", at and abs((bell - at).total_seconds() - 60) < 1.5,
      at and (bell - at).total_seconds())
check("הטיימר נשמר במצב", wake.target() == at)

st = wake.status()
check("המצב מדווח את שעת ההערה", st["armedAt"] == at.strftime("%H:%M"), st.get("armedAt"))

print("--- מקרים שאין בהם מה להעיר ---")
check("מועד שכבר עבר אינו נקבע",
      wake.arm(now - datetime.timedelta(minutes=5), 60) is None)
check("מועד בתוך זמן ההקדמה אינו נקבע",
      wake.arm(now + datetime.timedelta(seconds=30), 60) is None)
check("None אינו מפיל", wake.arm(None, 60) is None)

wake.cancel()
check("ביטול מנקה את המצב", wake.target() is None)
check("אחרי ביטול אין שעת הערה", wake.status()["armedAt"] is None)

print("--- הטיימר נפתח בזמן ---")
wake._woke.clear()
start = time.time()
at = wake.arm(datetime.datetime.now().astimezone() + datetime.timedelta(seconds=4),
              lead_seconds=0)
check("נקבע לארבע שניות", at is not None)
fired = wake._woke.wait(timeout=15)
elapsed = time.time() - start
check("הטיימר נפתח", fired, "לא נפתח תוך 15 שניות")
check("נפתח בזמן הנכון", fired and 3.0 < elapsed < 7.0, "%.1fs" % elapsed)
print("       נפתח אחרי %.1f שניות" % elapsed)

print("--- המנוע מכוון לצלצול הבא ---")
cfg = config.get()
cfg["settings"]["city"] = "ירושלים"
cfg["settings"]["wakeFromSleep"] = True
cfg["exceptions"] = []
soon = datetime.datetime.now().astimezone() + datetime.timedelta(hours=3)
cfg["bells"] = [{"id": "b", "time": soon.strftime("%H:%M"), "label": "בדיקה",
                 "sound": "bell_classic", "duration": 5,
                 "days": [0, 1, 2, 3, 4, 5, 6], "enabled": True}]
engine._armed_for = None
engine._arm_wake()
armed = wake.target()
check("המנוע קבע הערה", armed is not None, armed)
check("ההערה לפני הצלצול", armed and armed < soon, (armed, soon))

engine._arm_wake()
check("קריאה חוזרת לא מכווננת מחדש לחינם", wake.target() == armed)

cfg["settings"]["wakeFromSleep"] = False
engine._arm_wake()
check("כיבוי ההגדרה מבטל את הטיימר", wake.target() is None)
cfg["settings"]["wakeFromSleep"] = True

cfg["bells"] = []
engine._armed_for = None
engine._arm_wake()
check("בלי צלצולים אין הערה", wake.target() is None)

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
