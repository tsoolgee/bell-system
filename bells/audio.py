# -*- coding: utf-8 -*-
"""נגן שמע מבוסס Windows MCI - תומך ב-MP3/WAV/M4A ללא ספריות חיצוניות."""

import ctypes
import itertools
import os
import sys
import threading
import time

_counter = itertools.count(1)
_lock = threading.Lock()
_current = None  # (alias, stop_event)

if sys.platform == "win32":
    _mci = ctypes.windll.winmm.mciSendStringW
else:  # פיתוח מחוץ לווינדוס - הנגן פשוט לא עושה כלום
    _mci = None


def _send(command):
    if _mci is None:
        return 0, ""
    buf = ctypes.create_unicode_buffer(512)
    err = _mci(ctypes.c_wchar_p(command), buf, 512, 0)
    return err, buf.value


def _open(path):
    alias = "bell%d" % next(_counter)
    err, _ = _send('open "%s" alias %s' % (path, alias))
    if err:
        # ניסיון שני עם ציון סוג מפורש, לקבצים עם סיומת חריגה
        kind = "waveaudio" if path.lower().endswith(".wav") else "mpegvideo"
        err, _ = _send('open "%s" type %s alias %s' % (path, kind, alias))
        if err:
            return None
    return alias


def _length_ms(alias):
    err, val = _send("status %s length" % alias)
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def stop():
    """עצירה מיידית של הצלצול הנוכחי."""
    global _current
    with _lock:
        cur = _current
        _current = None
    if cur:
        cur[1].set()
        _send("stop %s" % cur[0])
        _send("close %s" % cur[0])


def is_playing():
    return _current is not None


def play(path, duration=5, volume=90, on_done=None):
    """מנגן קובץ למשך duration שניות. אם הקובץ קצר יותר - חוזר עליו.

    מחזיר True אם ההשמעה התחילה.
    """
    if not path or not os.path.exists(path):
        return False
    stop()
    alias = _open(path)
    if alias is None:
        return False
    _send("setaudio %s volume to %d" % (alias, max(0, min(1000, int(volume) * 10))))
    stop_event = threading.Event()
    with _lock:
        global _current
        _current = (alias, stop_event)

    def runner():
        deadline = time.time() + max(1, int(duration))
        try:
            while not stop_event.is_set() and time.time() < deadline:
                _send("play %s from 0" % alias)
                clip = _length_ms(alias) / 1000.0 or 1.0
                end = min(deadline, time.time() + clip)
                while not stop_event.is_set() and time.time() < end:
                    time.sleep(0.05)
        finally:
            _send("stop %s" % alias)
            _send("close %s" % alias)
            with _lock:
                global _current
                if _current and _current[0] == alias:
                    _current = None
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass

    threading.Thread(target=runner, daemon=True).start()
    return True
