# -*- coding: utf-8 -*-
"""בדיקת קצה-לקצה מול השרת הרץ."""
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
code, res = call("/api/exceptions/save", {"name": "חופשת בדיקה", "type": "gregorian",
                                          "from": "2026-09-01", "to": "2026-09-03"})
check("יצירת השבתה לועזית", code == 200, res)
exc_id = res.get("exception", {}).get("id")

code, res = call("/api/exceptions/save", {"name": "הפוך", "type": "gregorian",
                                          "from": "2026-09-05", "to": "2026-09-01"})
check("טווח הפוך נדחה", code == 400, res)

code, res = call("/api/calendar?days=10")
rows = {d["date"]: d for d in res["days"]}
blocked = [d for d in res["days"] if d["date"] in ("01/09/2026", "02/09/2026", "03/09/2026")]
check("ההשבתה חוסמת את הימים",
      len(blocked) == 3 and all(d["blocked"] and d["reason"] == "חופשת בדיקה" for d in blocked),
      blocked)

code, res = call("/api/exceptions/save", {"name": "חנוכה עברי", "type": "hebrew",
                                          "fromMonth": 9, "fromDay": 25,
                                          "toMonth": 10, "toDay": 2})
check("יצירת השבתה עברית", code == 200, res)
heb_id = res.get("exception", {}).get("id")

print("--- צלילים ---")
wav = open(os.path.join(os.environ["APPDATA"], "BellSystem", "sounds", "chime.wav"), "rb").read()
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

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
