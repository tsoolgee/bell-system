# -*- coding: utf-8 -*-
"""בדיקת קצה-לקצה מול השרת הרץ."""
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:%s" % (sys.argv[1] if len(sys.argv) > 1 else "8730")
fails = []


def call(path, payload=None, raw=None, headers=None):
    url = BASE + path
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    req = urllib.request.Request(url, data=data, headers=headers or {})
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            body = res.read()
            ctype = res.headers.get("Content-Type", "")
            return res.status, (json.loads(body) if "json" in ctype else body)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, body


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name + ("  " + str(detail) if detail and not condition else ""))
    if not condition:
        fails.append(name)


print("--- CRUD צלצולים ---")
code, res = call("/api/bells/save", {"time": "13:37", "label": "בדיקה", "sound": "gong",
                                     "duration": 3, "days": [0, 2, 4]})
check("יצירת צלצול", code == 200 and res.get("ok"), res)
bell_id = res.get("bell", {}).get("id")

code, res = call("/api/bells/save", {"time": "25:00", "days": [1]})
check("שעה לא תקינה נדחית", code == 400, res)

code, res = call("/api/bells/save", {"time": "10:00", "days": []})
check("צלצול בלי ימים נדחה", code == 400, res)

code, res = call("/api/bells/duplicate", {"id": bell_id})
check("שכפול צלצול", code == 200 and res.get("bell", {}).get("id") != bell_id, res)
clone_id = res.get("bell", {}).get("id")
check("השכפול שומר שעה וימים",
      res.get("bell", {}).get("time") == "13:37" and res.get("bell", {}).get("days") == [0, 2, 4])

code, res = call("/api/bells/toggle", {"id": bell_id})
check("השבתת צלצול", code == 200 and res.get("enabled") is False, res)
call("/api/bells/toggle", {"id": bell_id})

code, cfg = call("/api/config")
found = [b for b in cfg["bells"] if b["id"] == bell_id]
check("הצלצול נשמר בתצורה", len(found) == 1 and found[0]["sound"] == "gong")
check("הרשימה ממוינת לפי שעה",
      [b["time"] for b in cfg["bells"]] == sorted(b["time"] for b in cfg["bells"]))

print("--- השבתות ---")
# מתחילים ביום ראשון הקרוב: טווח יחסי כדי שהבדיקה לא תתיישן, ובלי שבת
# בתוכו. שבת או חג גוברים על השבתה ידנית - הם הסיבה החזקה יותר, והיא
# זו שתדווח. לכן הבדיקה דורשת שהימים יהיו חסומים, ושהסיבה תהיה ההשבתה
# או החג של אותו יום.
TODAY = datetime.date.today()
_sunday = TODAY + datetime.timedelta(days=(6 - TODAY.weekday()) % 7 or 7)
RANGE = [_sunday + datetime.timedelta(days=i) for i in (0, 1, 2)]
code, res = call("/api/exceptions/save", {"name": "חופשת בדיקה", "type": "gregorian",
                                          "from": RANGE[0].isoformat(),
                                          "to": RANGE[-1].isoformat()})
check("יצירת השבתה לועזית", code == 200, res)
exc_id = res.get("exception", {}).get("id")

code, res = call("/api/exceptions/save", {"name": "הפוך", "type": "gregorian",
                                          "from": RANGE[-1].isoformat(),
                                          "to": RANGE[0].isoformat()})
check("טווח הפוך נדחה", code == 400, res)

code, res = call("/api/calendar?days=10")
wanted = {d.strftime("%d/%m/%Y") for d in RANGE}
blocked = [d for d in res["days"] if d["date"] in wanted]
check("ההשבתה חוסמת את הימים",
      len(blocked) == 3 and all(d["blocked"] for d in blocked), blocked)
check("ההשבתה היא הסיבה, אלא אם חג גובר עליה",
      all(d["reason"] == "חופשת בדיקה" or d["reason"] == d["holiday"] for d in blocked),
      blocked)

code, res = call("/api/exceptions/save", {"name": "חנוכה עברי", "type": "hebrew",
                                          "fromMonth": 9, "fromDay": 25,
                                          "toMonth": 10, "toDay": 2})
check("יצירת השבתה עברית", code == 200, res)
heb_id = res.get("exception", {}).get("id")

print("--- צלילים ---")
# מהתיקייה שהשרת עצמו מדווח עליה, לא מנתיב מנוחש
_, _cfg = call("/api/config")
wav = open(os.path.join(_cfg["dataDir"], "sounds", "chime.wav"), "rb").read()
code, res = call("/api/sounds/upload?name=" + urllib.parse.quote("צלצול בדיקה.wav"), raw=wav)
check("העלאת צליל", code == 200 and res.get("ok"), res)
sound_id = res.get("sound", {}).get("id")

code, res = call("/api/sounds/upload?name=virus.exe", raw=b"MZ")
check("סיומת אסורה נדחית", code == 400, res)

code, res = call("/api/bells/save", {"id": bell_id, "time": "13:37", "sound": sound_id,
                                     "duration": 3, "days": [0, 2, 4], "label": "בדיקה"})
check("שיוך הצליל לצלצול", code == 200, res)
code, res = call("/api/sounds/delete", {"id": sound_id})
check("מחיקת צליל בשימוש נחסמת", code == 400, res)
code, res = call("/api/sounds/delete", {"id": sound_id, "force": True})
check("מחיקה כפויה עוברת", code == 200, res)
code, cfg = call("/api/config")
check("הצלצול חזר לצליל ברירת מחדל",
      [b for b in cfg["bells"] if b["id"] == bell_id][0]["sound"] == "bell_classic")

print("--- גיבוי ---")
code, backup = call("/api/backup")
check("ייצוא גיבוי", code == 200 and backup[:2] == b"PK", code)
open(os.path.join(os.environ["TEMP"], "bell-test-backup.zip"), "wb").write(backup)

print("--- ניקוי ---")
for cid in (bell_id, clone_id):
    call("/api/bells/delete", {"id": cid})
for eid in (exc_id, heb_id):
    call("/api/exceptions/delete", {"id": eid})
code, cfg = call("/api/config")
check("הניקוי הצליח",
      not any(b["id"] in (bell_id, clone_id) for b in cfg["bells"]) and not cfg["exceptions"])

print("--- שחזור ---")
code, res = call("/api/restore", raw=open(os.path.join(os.environ["TEMP"], "bell-test-backup.zip"), "rb").read())
check("שחזור מגיבוי", code == 200, res)
code, cfg = call("/api/config")
check("הגיבוי החזיר את הצלצולים שנמחקו",
      any(b["id"] == bell_id for b in cfg["bells"]) and len(cfg["exceptions"]) == 2)
for cid in (bell_id, clone_id):
    call("/api/bells/delete", {"id": cid})
code, cfg = call("/api/config")
for e in list(cfg["exceptions"]):
    call("/api/exceptions/delete", {"id": e["id"]})

code, res = call("/api/restore", raw=b"not a backup at all")
check("קובץ גיבוי פגום נדחה", code == 400, res)

print("--- עוצמה והגברה ---")
code, audio_before = call("/api/audio")
started_volume = audio_before.get("appVolume")

call("/api/settings", {"volume": 999})
code, res = call("/api/audio")
check("עוצמה מעל המקסימום נחתכת ל-200", res.get("appVolume") == 200, res.get("appVolume"))
call("/api/settings", {"volume": -50})
code, res = call("/api/audio")
check("עוצמה שלילית נחתכת לאפס", res.get("appVolume") == 0, res.get("appVolume"))
call("/api/settings", {"volume": 160})

if not audio_before.get("available"):
    print("       דילוג: אין שליטה בעוצמת ההתקן במכונה הזו")
else:
    # הבדיקה נוגעת בעוצמה האמיתית של המחשב, ולכן היא מחזירה אותה בסוף
    device_before, muted_before = audio_before["volume"], audio_before["muted"]
    code, res = call("/api/audio/device-volume", {"volume": 55})
    check("עוצמת ההתקן נקבעת", code == 200 and res.get("volume") == 55, res)
    code, res = call("/api/audio/device-volume", {"volume": 400})
    check("עוצמת התקן מעל 100 נחתכת", res.get("volume") == 100, res)
    code, res = call("/api/audio/device-volume", {"muted": True})
    check("השתקת ההתקן", res.get("muted") is True, res)
    code, res = call("/api/audio/device-volume", {"volume": 60})
    check("העלאת עוצמה מבטלת השתקה", res.get("muted") is False, res)
    call("/api/audio/device-volume", {"volume": device_before})
    if muted_before:
        call("/api/audio/device-volume", {"muted": True})
    code, res = call("/api/audio")
    check("הבדיקה החזירה את עוצמת ההתקן לקדמותה",
          res.get("volume") == device_before and res.get("muted") == muted_before,
          (device_before, muted_before, res.get("volume"), res.get("muted")))

code, res = call("/api/audio/boost-test", {"volume": 180})
check("בדיקת ההגברה רצה", code == 200 and res.get("ok"), code)
if code == 200:
    check("נמדדו שלוש רמות", len(res.get("steps", [])) == 3, res.get("steps"))
    check("הרמות הן 50, 100 והנבחרת",
          [s["volume"] for s in res.get("steps", [])] == [50, 100, 180], res.get("steps"))
    if res.get("backend") == "pygame":
        check("ההגברה הופעלה בפועל", res.get("boosted") is True, res)
        sam = res.get("samples") or {}
        check("ההגברה נמדדה על הדגימות", sam.get("db", 0) > 0.5, sam)
        check("הדגימות המוגברות לא חורגות מהתקרה",
              sam.get("boostedPeak", 2) <= 1.0, sam)
    else:
        print("       מנוע השמע: %s - אין הגברה למדוד" % res.get("backend"))

code, res = call("/api/audio/boost-test", {"volume": 100})
check("ב-100% לא מנסים להגביר", res.get("boosted") is False, res.get("boosted"))
check("ב-100% נמדדות שתי רמות בלבד", len(res.get("steps", [])) == 2, res.get("steps"))

if started_volume is not None:
    call("/api/settings", {"volume": started_volume})

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
