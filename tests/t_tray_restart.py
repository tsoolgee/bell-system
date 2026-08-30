# -*- coding: utf-8 -*-
"""רשת הביטחון: מגש שנסגר מעצמו חייב לקום מחדש, לא להפיל את המערכת."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BELLSYSTEM_DATA"] = os.path.join(os.environ["TEMP"], "BellRestartTest")

from bells import app, engine, server, sounds, tray  # noqa: E402

fails = []


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name +
          ("  -> " + str(detail) if not condition else ""))
    if not condition:
        fails.append(name)


class FakeHttpd:
    def shutdown(self):
        pass


logged = []
engine.log = lambda msg, kind="info": logged.append((kind, msg))
engine.start = lambda: None
engine.shutdown = lambda: None
sounds.ensure = lambda d: None
server.start = lambda port=None: (FakeHttpd(), 8730)
app.already_running = lambda: False
app.open_ui = lambda port: None


def run_with(stub_factory):
    logged.clear()
    original = tray.Tray
    tray.Tray = stub_factory
    try:
        app.main(["--minimized"])
    finally:
        tray.Tray = original


print("--- מגש שנסגר מעצמו פעמיים ומקבל יציאה יזומה בשלישית ---")
calls = {"n": 0}


class FlakyTray:
    def __init__(self, port, on_open, on_quit):
        self.quit_requested = False
        self.on_quit = on_quit

    def run(self):
        calls["n"] += 1
        # פעמיים הלולאה מסתיימת בלי שהמשתמש ביקש, בשלישית הוא לוחץ יציאה
        self.quit_requested = calls["n"] >= 3
        return True

    def stop(self):
        pass


run_with(FlakyTray)
check("המגש הורם מחדש עד ליציאה יזומה", calls["n"] == 3, calls["n"])
restarts = [m for k, m in logged if "מרים מחדש" in m]
check("כל הרמה נרשמה ביומן", len(restarts) == 2, restarts)
check("היציאה נרשמה בסוף", any("המערכת נסגרה" in m for _, m in logged))

print("--- יציאה יזומה מיד ---")
calls["n"] = 0


class CleanTray(FlakyTray):
    def run(self):
        calls["n"] += 1
        self.quit_requested = True
        return True


run_with(CleanTray)
check("יציאה יזומה לא מרימה מחדש", calls["n"] == 1, calls["n"])
check("לא נרשמה הרמה מיותרת", not [m for k, m in logged if "מרים מחדש" in m])

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
