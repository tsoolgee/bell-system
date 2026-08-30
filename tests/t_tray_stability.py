# -*- coding: utf-8 -*-
"""האם האפליקציה שורדת שימוש ב-API כשהמגש רץ?

הבאג שזה מכסה: אתחול/כיבוי של מיקסר SDL מתוך תהליכון HTTP שולח WM_QUIT
לתור ההודעות של התהליכון הראשי. לולאת המגש מסתיימת, והאפליקציה יוצאת
בשקט - באמצע יום לימודים. כל הבדיקות האחרות רצות ב---no-tray ולכן
מפספסות את זה לגמרי.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8749
BASE = "http://127.0.0.1:%d" % PORT
fails = []


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name +
          ("  -> " + str(detail) if not condition else ""))
    if not condition:
        fails.append(name)


def call(path, payload=None, timeout=45):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


env = dict(os.environ, BELLSYSTEM_DATA=os.path.join(os.environ["TEMP"], "BellTrayTest"))
proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "run.py"),
                         "--minimized", "--port", str(PORT)],
                        cwd=ROOT, env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
print("הופעל עם מגש מערכת, pid=%d" % proc.pid)

ready = False
for _ in range(40):
    time.sleep(1)
    try:
        call("/api/state", timeout=5)
        ready = True
        break
    except Exception:
        if proc.poll() is not None:
            break
check("המערכת עלתה", ready, "יצאה מיד עם קוד %s" % proc.poll())

if ready:
    print("--- מפציצים את נקודות הקצה שנוגעות ב-SDL ---")
    for i in range(6):
        try:
            info = call("/api/audio")
            call("/api/ring", {"sound": "bell_classic", "duration": 1})
            call("/api/stop", {})
            alive = proc.poll() is None
            print("      סבב %d: התקנים=%d | התהליך חי=%s"
                  % (i + 1, len(info.get("devices") or []), alive))
            if not alive:
                break
        except Exception as exc:
            check("סבב %d עבר" % (i + 1), False, exc)
            break
    check("התהליך שרד את סבבי ה-API", proc.poll() is None,
          "יצא עם קוד %s" % proc.poll())

    if proc.poll() is None:
        print("--- בדיקת שמע מלאה (מאתחלת מיקסר) ---")
        try:
            res = call("/api/audio/test", {})
            print("      בפועל=%s | נשמע=%s" % (res.get("actual"), res.get("heard")))
        except Exception as exc:
            check("בדיקת השמע לא הפילה את השרת", False, exc)
        time.sleep(2)
        check("התהליך שרד את בדיקת השמע", proc.poll() is None,
              "יצא עם קוד %s" % proc.poll())

try:
    proc.terminate()
    proc.wait(timeout=10)
except Exception:
    proc.kill()

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
