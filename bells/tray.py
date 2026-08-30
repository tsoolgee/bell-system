# -*- coding: utf-8 -*-
"""אייקון מגש המערכת - הפנים של המערכת כשהיא רצה ברקע."""

import threading

from PIL import Image, ImageDraw

try:
    import pystray
except ImportError:  # המערכת עובדת גם בלי מגש
    pystray = None

from . import audio, config, engine

COLORS = {
    "ok": (5, 150, 105),
    "muted": (217, 119, 6),
    "off": (220, 38, 38),
    "shabbat": (234, 88, 12),
    "yomtov": (124, 58, 237),
    "holiday": (139, 92, 246),
    "exception": (71, 85, 105),
}


def _kind(state):
    if not state.get("enabled"):
        return "off"
    if state.get("muted"):
        return "muted"
    return state.get("reason") or "ok"


def make_icon(kind="ok"):
    """מצייר פעמון לבן על עיגול בצבע המצב."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, size - 1, size - 1), fill=COLORS.get(kind, COLORS["ok"]))
    white = (255, 255, 255, 255)
    d.pieslice((17, 14, 47, 44), 180, 360, fill=white)      # כיפת הפעמון
    d.rectangle((17, 29, 47, 42), fill=white)               # גוף
    d.rectangle((13, 42, 51, 47), fill=white)               # שפה
    d.ellipse((29, 47, 35, 53), fill=white)                 # ענבל
    d.rectangle((30, 10, 34, 15), fill=white)               # ידית
    return img


class Tray:
    def __init__(self, port, on_open, on_quit):
        self.port = port
        self.on_open = on_open
        self.on_quit = on_quit
        self.icon = None
        self._kind = None
        # רק יציאה שהמשתמש ביקש נחשבת לגיטימית. אם לולאת המגש מסתיימת
        # מסיבה אחרת, המערכת מרימה אותה מחדש במקום להיעלם.
        self.quit_requested = False
        self._registered = False

    def _status_text(self):
        state = engine.status()
        text = "מערכת צלצולים — " + state["statusLabel"]
        if state.get("next"):
            n = state["next"]
            text += "\nהצלצול הבא: %s %s" % (n["time"], n["label"])
        return text[:127]  # מגבלת Windows לטולטיפ

    def _menu(self):
        muted = config.settings().get("muted")
        enabled = config.settings().get("enabled", True)
        return pystray.Menu(
            pystray.MenuItem("פתיחת ממשק הניהול", lambda: self.on_open(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("צלצול עכשיו", lambda: engine.ring("bell_classic", 5, manual=True)),
            pystray.MenuItem("עצירת צלצול", lambda: audio.stop()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("ביטול השתקה" if muted else "השתקת צלצולים", self._toggle_mute),
            pystray.MenuItem("הפעלת המערכת" if not enabled else "כיבוי המערכת", self._toggle_power),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("יציאה", self._quit),
        )

    def _quit(self):
        self.quit_requested = True
        if self.on_quit:
            self.on_quit()

    def _toggle_mute(self):
        st = config.settings()
        st["muted"] = not st.get("muted")
        if st["muted"]:
            audio.stop()
        config.save()
        engine.log("השתקה כללית: " + ("פעילה" if st["muted"] else "בוטלה"), "system")
        self.update()

    def _toggle_power(self):
        st = config.settings()
        st["enabled"] = not st.get("enabled", True)
        if not st["enabled"]:
            audio.stop()
        config.save()
        engine.log("המערכת " + ("הופעלה" if st["enabled"] else "כובתה"), "system")
        self.update()

    def update(self):
        if not self.icon:
            return
        try:
            kind = _kind(engine.status())
            if kind != self._kind:
                self._kind = kind
                self.icon.icon = make_icon(kind)
            self.icon.title = self._status_text()
            self.icon.menu = self._menu()
        except Exception:
            pass

    def _watcher(self):
        while True:
            self.update()
            threading.Event().wait(20)

    def run(self):
        """חוסם - חייב לרוץ בתהליכון הראשי."""
        if pystray is None:
            return False
        self._kind = _kind(engine.status())
        self.icon = pystray.Icon("BellSystem", make_icon(self._kind),
                                 "מערכת צלצולים", self._menu())
        if not self._registered:
            engine.add_listener(self.update)
            threading.Thread(target=self._watcher, daemon=True).start()
            self._registered = True
        self.icon.run()
        return True

    def stop(self):
        if self.icon:
            self.icon.stop()
