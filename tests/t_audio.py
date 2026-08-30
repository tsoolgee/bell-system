# -*- coding: utf-8 -*-
"""בדיקת הנגן בדפוס התהליכונים האמיתי של האפליקציה.

הבאג שזה מכסה: MCI קושר alias לתהליכון שפתח אותו. כשהפתיחה קרתה
בתהליכון של השרת וההשמעה בתהליכון אחר, כל הפקודות נכשלו בשקט -
הלוג דיווח על צלצול, ושום צליל לא יצא.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import audio, config, sounds  # noqa: E402

sounds.ensure(config.sounds_dir())
path = os.path.join(config.sounds_dir(), "bell_classic.wav")
fails = []


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name + ("  -> " + str(detail) if detail and not condition else ""))
    if not condition:
        fails.append(name)


# מקליטים כל פקודת MCI ואת קוד השגיאה שלה
log = []
_real_send = audio._send


def spy(command):
    err, value = _real_send(command)
    log.append((command.split()[0], command, err, value))
    return err, value


audio._send = spy


def commands(verb):
    return [entry for entry in log if entry[0] == verb]


print("--- השמעה מתהליכון אחר (כמו בקשת HTTP) ---")
result = {}


def from_other_thread():
    result["ok"] = audio.play(path, duration=2, volume=90)


worker = threading.Thread(target=from_other_thread)
worker.start()
worker.join(timeout=10)

check("play מדווח על הצלחה", result.get("ok") is True, result)
check("הנגן מדווח שהוא מנגן", audio.is_playing())

opens = commands("open")
check("MCI פתח את הקובץ", opens and opens[0][2] == 0, opens[:1])
check("נבחר mpegvideo (תומך בעוצמה)", any("mpegvideo" in c[1] for c in opens), opens[:1])

vol = commands("setaudio")
check("עוצמה נקבעה בהצלחה", vol and vol[0][2] == 0, vol[:1])

plays = commands("play")
check("פקודת play התקבלה", plays and plays[0][2] == 0, plays[:1])

time.sleep(0.7)
modes = [c for c in commands("status") if " mode" in c[1]]
check("MCI מדווח playing מתוך תהליכון העבודה",
      any(c[3] == "playing" for c in modes), modes[-3:] or "לא נשאל בכלל")

print("--- עצירה ---")
audio.stop()
time.sleep(0.4)
check("הנגן נעצר", not audio.is_playing())
check("הקובץ נסגר", any(c[0] == "close" and c[2] == 0 for c in log))

print("--- קובץ שלא קיים ---")
check("קובץ חסר מוחזר כ-False", audio.play(os.path.join(config.sounds_dir(), "nope.wav")) is False)

print("--- השמעה חוזרת ברצף ---")
log.clear()
check("השמעה שנייה מצליחה", audio.play(path, duration=1, volume=80) is True)
check("השמעה שלישית מצליחה מיד אחריה", audio.play(path, duration=1, volume=80) is True)
audio.stop()
time.sleep(0.3)
errors = [c for c in log if c[2] != 0 and c[0] in ("play", "open")]
check("אין שגיאות MCI ברצף", not errors, errors[:3])

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
