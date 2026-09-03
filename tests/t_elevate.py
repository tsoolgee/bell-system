# -*- coding: utf-8 -*-
"""בקשת הרשאות מנהל.

שלוש הגדרות נוגעות במחשב כולו ולא במשתמש הנוכחי. במקום לומר למנהל
"הרץ כמנהל", המערכת מריצה משימה קצרה ומורמת. הבדיקה מוודאת שהמסלול
בנוי נכון: רשימת משימות סגורה, ביצוע ישיר כשכבר יש הרשאה, ודיווח כן
כשהמשתמש מבטל את חלון ההרשאות.
"""
import os
import shutil
import subprocess
import sys

DATA = os.path.join(os.environ["TEMP"], "BellElevateTest")
shutil.rmtree(DATA, ignore_errors=True)
os.makedirs(os.path.join(DATA, "sounds"), exist_ok=True)
os.environ["BELLSYSTEM_DATA"] = DATA

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from bells import elevate  # noqa: E402

fails = []


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name +
          ("  -> " + repr(detail) if not condition else ""))
    if not condition:
        fails.append(name)


print("--- רשימת המשימות ---")
check("כל המשימות מוגדרות",
      set(elevate.TASKS) == {"wake-on", "wake-off", "autostart-on",
                             "autostart-off", "share-data"}, elevate.TASKS)
ok, message = elevate.run_elevated("rm -rf /")
check("משימה לא מוכרת נדחית לפני שמבקשים הרשאה", not ok and "לא מוכרת" in message,
      message)
check("perform דוחה משימה לא מוכרת", elevate.perform("whatever") is False)

print("--- זיהוי הרשאות ---")
admin = elevate.is_admin()
print("       רץ כמנהל: %s" % admin)
check("is_admin מחזיר בוליאני", isinstance(admin, bool))

print("--- שורת הפקודה למשימה המורמת ---")
exe, prefix = elevate._command()
check("נבחר קובץ הרצה קיים", os.path.exists(exe), exe)
check("במצב פיתוח מועבר גם run.py", "run.py" in prefix, prefix)

print("--- המשימה מתקבלת כארגומנט תקין ---")
out = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"),
                      "--elevated-task", "not-a-task"],
                     capture_output=True, cwd=ROOT, timeout=60)
check("ארגומנט לא חוקי נדחה", out.returncode != 0)
check("argparse מסביר מה מותר",
      b"elevated-task" in (out.stderr or b""), (out.stderr or b"")[:120])

# משימה תקינה בלי הרשאות מנהל: אמורה להיכשל בנקי ולא לקרוס
out = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"),
                      "--elevated-task", "wake-off"],
                     capture_output=True, cwd=ROOT, timeout=90)
check("משימה תקינה רצה ומסתיימת בלי קריסה",
      out.returncode in (0, 1), (out.returncode, (out.stderr or b"")[:200]))
check("המשימה לא הפעילה שרת או מגש",
      b"Traceback" not in (out.stderr or b""), (out.stderr or b"")[:200])

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
