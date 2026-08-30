# -*- coding: utf-8 -*-
"""בקשות רצופות על אותו חיבור keep-alive.

הבאג שזה מכסה: נתיב POST שלא קורא את גוף הבקשה משאיר בייטים בשקע,
והם נדבקים לשורת הבקשה הבאה - "{}GET /api/state" ואז 501.
"""
import http.client
import json
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8730
fails = []


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name + ("  -> " + str(detail) if detail and not condition else ""))
    if not condition:
        fails.append(name)


conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=40)

# רצף שמערבב POST עם גוף, POST בלי צורך בגוף, ו-GET - הכל על חיבור אחד
sequence = [
    ("POST", "/api/stop", "{}"),
    ("GET", "/api/state", None),
    ("POST", "/api/audio/test", "{}"),
    ("GET", "/api/config", None),
    ("POST", "/api/stop", '{"ignored": true}'),
    ("GET", "/api/state", None),
    ("POST", "/api/ring", '{"sound": "bell_classic", "duration": 1}'),
    ("GET", "/api/state", None),
    ("POST", "/api/stop", "{}"),
    ("GET", "/api/log", None),
]

for method, path, body in sequence:
    headers = {"Content-Type": "application/json"} if body is not None else {}
    conn.request(method, path, body=body, headers=headers)
    res = conn.getresponse()
    payload = res.read()
    label = "%-4s %-18s" % (method, path)
    ok = res.status == 200
    detail = "status=%d" % res.status
    if ok and b"json" in (res.getheader("Content-Type") or "").encode():
        try:
            json.loads(payload.decode("utf-8"))
        except ValueError:
            ok, detail = False, "גוף התשובה אינו JSON תקין"
    check(label, ok, detail)

conn.close()
print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
