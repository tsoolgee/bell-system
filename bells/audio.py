# -*- coding: utf-8 -*-
"""נגן שמע מבוסס Windows MCI - תומך ב-MP3/WAV/M4A ללא ספריות חיצוניות.

חשוב: MCI קושר כל alias לתהליכון שפתח אותו. פקודה שנשלחת מתהליכון אחר
נכשלת בשקט - הקובץ נפתח, אבל שום צליל לא יוצא. לכן *כל* פקודות MCI
רצות כאן בתהליכון עבודה יחיד, וכל השאר רק שולח אליו בקשות.
"""

import ctypes
import itertools
import os
import queue
import sys
import threading
import time

_counter = itertools.count(1)
_commands = queue.Queue()
_worker = None
_worker_lock = threading.Lock()
_playing = threading.Event()

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
    """פותח את הקובץ ומחזיר (alias, האם ניתן לשלוט בעוצמה).

    mpegvideo (DirectShow) קודם בכוונה: הוא היחיד שתומך ב-setaudio volume,
    וגם קורא WAV, MP3 ו-M4A. waveaudio נשאר כגיבוי.
    חובה לקרוא לזה מתוך תהליכון העבודה.
    """
    alias = "bell%d" % next(_counter)
    for kind in ("mpegvideo", None, "waveaudio"):
        cmd = ('open "%s" alias %s' % (path, alias) if kind is None
               else 'open "%s" type %s alias %s' % (path, kind, alias))
        if _send(cmd)[0] == 0:
            return alias, kind == "mpegvideo"
    return None, False


def _length_ms(alias):
    try:
        return int(_send("status %s length" % alias)[1])
    except (TypeError, ValueError):
        return 0


def _is_done(alias):
    return _send("status %s mode" % alias)[1] != "playing"


class _Playback:
    __slots__ = ("alias", "deadline", "clip_ends")

    def __init__(self, alias, deadline, clip_ends):
        self.alias = alias
        self.deadline = deadline
        self.clip_ends = clip_ends


def _start(path, duration, volume):
    alias, can_set_volume = _open(path)
    if alias is None:
        return None
    if can_set_volume:
        _send("setaudio %s volume to %d" % (alias, max(0, min(1000, int(volume) * 10))))
    clip = (_length_ms(alias) / 1000.0) or 1.0
    now = time.time()
    _send("play %s from 0" % alias)
    _playing.set()
    return _Playback(alias, now + max(1, int(duration)), now + clip)


def _pump(current):
    """נקרא כל 50ms מתוך תהליכון העבודה. מחזיר את מצב ההשמעה או None."""
    now = time.time()
    if now >= current.deadline:
        return _close(current)
    if now >= current.clip_ends or _is_done(current.alias):
        # הקובץ קצר מהמשך המבוקש - חוזרים עליו עד סוף הזמן
        _send("play %s from 0" % current.alias)
        current.clip_ends = now + ((_length_ms(current.alias) / 1000.0) or 1.0)
    return current


def _close(current):
    if current:
        _send("stop %s" % current.alias)
        _send("close %s" % current.alias)
    _playing.clear()
    return None


def _loop():
    current = None
    while True:
        timeout = 0.05 if current else 0.5
        try:
            command = _commands.get(timeout=timeout)
        except queue.Empty:
            command = None
        if command:
            action = command[0]
            if action == "stop":
                current = _close(current)
            elif action == "play":
                _, path, duration, volume, done, result = command
                current = _close(current)
                current = _start(path, duration, volume)
                result.append(current is not None)
                done.set()
        if current:
            current = _pump(current)


def _ensure_worker():
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_loop, name="bell-audio", daemon=True)
            _worker.start()


def stop():
    """עצירה מיידית של הצלצול הנוכחי."""
    _ensure_worker()
    _commands.put(("stop",))


def is_playing():
    return _playing.is_set()


def play(path, duration=5, volume=90, on_done=None):
    """מנגן קובץ למשך duration שניות. אם הקובץ קצר יותר - חוזר עליו.

    מחזיר True אם ההשמעה אכן התחילה.
    """
    if not path or not os.path.exists(path):
        return False
    _ensure_worker()
    done, result = threading.Event(), []
    _commands.put(("play", path, duration, volume, done, result))
    # ממתינים לתשובה אמיתית מתהליכון העבודה, כדי שהיומן לא ידווח על
    # צלצול שלא באמת יצא.
    if not done.wait(timeout=5):
        return False
    ok = bool(result and result[0])
    if ok and on_done:
        threading.Timer(max(1, int(duration)), on_done).start()
    return ok
