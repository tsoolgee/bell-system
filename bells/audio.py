# -*- coding: utf-8 -*-
"""נגן השמע של המערכת.

שני מנועים:

* pygame/SDL - המנוע המועדף. הוא היחיד שמאפשר לנגן להתקן פלט *מסוים*,
  בלי קשר לברירת המחדל של Windows. בבית ספר זה קריטי: הצלצולים הולכים
  לרמקולי הכיתות גם אם המחשב עצמו מנגן לאוזניות.
* MCI (winmm) - גיבוי כשאין pygame. מנגן רק להתקן ברירת המחדל.

חשוב בשני המקרים: MCI קושר alias לתהליכון שפתח אותו, ופקודה מתהליכון
אחר נכשלת בשקט. לכן *כל* עבודת השמע רצה כאן בתהליכון עבודה יחיד.
"""

import ctypes
import itertools
import os
import queue
import sys
import threading
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

_counter = itertools.count(1)
_commands = queue.Queue()
_worker = None
_worker_lock = threading.Lock()
# המיקסר גלובלי ב-pygame: אתחול מתהליכון אחד בזמן השמעה באחר שובר אותו
_mixer_lock = threading.RLock()
_playing = threading.Event()

# ההתקן שהמיקסר מאותחל אליו בפועל (None = ברירת המחדל של Windows)
_active_device = None
_wanted_device = None

if sys.platform == "win32":
    _mci = ctypes.windll.winmm.mciSendStringW
else:
    _mci = None


# ---------------------------------------------------------------- MCI

def _send(command):
    if _mci is None:
        return 0, ""
    buf = ctypes.create_unicode_buffer(512)
    err = _mci(ctypes.c_wchar_p(command), buf, 512, 0)
    return err, buf.value


def _mci_open(path):
    """מחזיר (alias, האם ניתן לשלוט בעוצמה). חובה לקרוא מתהליכון העבודה."""
    alias = "bell%d" % next(_counter)
    for kind in ("mpegvideo", None, "waveaudio"):
        cmd = ('open "%s" alias %s' % (path, alias) if kind is None
               else 'open "%s" type %s alias %s' % (path, kind, alias))
        if _send(cmd)[0] == 0:
            return alias, kind == "mpegvideo"
    return None, False


def _mci_length(alias):
    try:
        return int(_send("status %s length" % alias)[1])
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------- pygame

def _pygame():
    try:
        import pygame
        return pygame
    except Exception:
        return None


def _enumerate_devices():
    pygame = _pygame()
    if pygame is None:
        return []
    try:
        import pygame._sdl2.audio as sdl2_audio
        with _mixer_lock:
            opened = pygame.mixer.get_init()
            if not opened:
                pygame.mixer.init()
            names = list(sdl2_audio.get_audio_device_names(False))
            if not opened:
                pygame.mixer.quit()
        return names
    except Exception:
        return []


def available_devices():
    """שמות התקני הפלט. רשימה ריקה = אי אפשר לבחור התקן."""
    return _on_worker(_enumerate_devices) or []


def _mixer_ready(device):
    """מאתחל את המיקסר להתקן המבוקש. מחזיר True אם יש מיקסר פעיל."""
    global _active_device
    pygame = _pygame()
    if pygame is None:
        return False
    with _mixer_lock:
        if pygame.mixer.get_init() and _active_device == device:
            return True
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        # אם ההתקן שנבחר נעלם (נותק, שונה שמו) - עדיין מצלצלים, בברירת המחדל
        for candidate in ([device] if device else []) + [None]:
            kwargs = {"frequency": 44100, "size": -16, "channels": 2, "buffer": 1024}
            if candidate:
                kwargs["devicename"] = candidate
            try:
                pygame.mixer.init(**kwargs)
                _active_device = candidate
                return True
            except Exception:
                continue
        _active_device = None
        return False


def active_device():
    """ההתקן שהצלצולים באמת יוצאים אליו כרגע, או None לברירת המחדל."""
    return _active_device


def current_backend():
    """'pygame' (תומך בבחירת התקן) או 'mci' (ברירת מחדל בלבד)."""
    pygame = _pygame()
    if pygame is None:
        return "mci"
    try:
        return "pygame" if pygame.mixer.get_init() else "mci"
    except Exception:
        return "mci"


def _probe_device(name):
    pygame = _pygame()
    if pygame is None or not name:
        return False
    with _mixer_lock:
        try:
            opened = pygame.mixer.get_init()
            keep = _active_device
            pygame.mixer.quit()
            pygame.mixer.init(frequency=44100, size=-16, channels=2,
                              buffer=1024, devicename=name)
            pygame.mixer.quit()
            if opened:
                _mixer_ready(keep)
            return True
        except Exception:
            return False


def can_choose_device(name):
    """האם ניתן באמת לפתוח את ההתקן הזה. חלק מההתקנים ברשימה נכשלים."""
    return bool(_on_worker(lambda: _probe_device(name)))


def device_fell_back():
    """True אם נבחר התקן אבל בפועל מנגנים למשהו אחר."""
    return bool(_wanted_device) and _active_device != _wanted_device


# ---------------------------------------------------------------- השמעה

class _Playback:
    __slots__ = ("kind", "alias", "sound", "channel", "deadline", "clip_ends")

    def __init__(self, kind, deadline):
        self.kind = kind
        self.alias = None
        self.sound = None
        self.channel = None
        self.deadline = deadline
        self.clip_ends = 0.0


def _start(path, duration, volume, device):
    global _wanted_device
    _wanted_device = device or None
    deadline = time.time() + max(1, int(duration))

    if _mixer_ready(device or None):
        pygame = _pygame()
        try:
            play = _Playback("pygame", deadline)
            play.sound = pygame.mixer.Sound(path)
            play.sound.set_volume(max(0, min(100, int(volume))) / 100.0)
            # לולאה אינסופית ועצירה בזמן: כך קובץ קצר ממלא את כל המשך
            play.channel = play.sound.play(loops=-1)
            _playing.set()
            return play
        except Exception:
            pass  # נופלים ל-MCI

    alias, can_set_volume = _mci_open(path)
    if alias is None:
        return None
    if can_set_volume:
        _send("setaudio %s volume to %d" % (alias, max(0, min(1000, int(volume) * 10))))
    play = _Playback("mci", deadline)
    play.alias = alias
    play.clip_ends = time.time() + ((_mci_length(alias) / 1000.0) or 1.0)
    _send("play %s from 0" % alias)
    _playing.set()
    return play


def _pump(current):
    """נקרא כל 50ms מתוך תהליכון העבודה. מחזיר את מצב ההשמעה או None."""
    now = time.time()
    if now >= current.deadline:
        return _close(current)
    if current.kind == "mci":
        done = _send("status %s mode" % current.alias)[1] != "playing"
        if now >= current.clip_ends or done:
            _send("play %s from 0" % current.alias)
            current.clip_ends = now + ((_mci_length(current.alias) / 1000.0) or 1.0)
    return current


def _close(current):
    if current:
        if current.kind == "mci":
            _send("stop %s" % current.alias)
            _send("close %s" % current.alias)
        else:
            try:
                current.sound.stop()
            except Exception:
                pass
    _playing.clear()
    return None


def _loop():
    current = None
    while True:
        try:
            command = _commands.get(timeout=0.05 if current else 0.5)
        except queue.Empty:
            command = None
        if command:
            action = command[0]
            if action == "call":
                _, fn, done, out = command
                try:
                    out.append(fn())
                except Exception:
                    out.append(None)
                done.set()
            elif action == "stop":
                current = _close(current)
            elif action == "play":
                _, path, duration, volume, device, done, result = command
                current = _close(current)
                try:
                    current = _start(path, duration, volume, device)
                except Exception:
                    current = None
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


def _on_worker(fn, timeout=25):
    """מריץ פעולת SDL על תהליכון השמע.

    חובה: אתחול/כיבוי של מיקסר SDL מתהליכון אחר שולח WM_QUIT לתור ההודעות
    של התהליכון הראשי, ולולאת המגש מסתיימת - האפליקציה יוצאת בשקט באמצע
    יום לימודים. כל נגיעה ב-SDL חייבת לקרות כאן.
    """
    _ensure_worker()
    done, out = threading.Event(), []
    _commands.put(("call", fn, done, out))
    if not done.wait(timeout):
        return None
    return out[0] if out else None


def reset():
    """זורק את המיקסר כדי שההשמעה הבאה תאתחל אותו מחדש.

    אחרי חזרה משינה התקני השמע נספרים מחדש ב-Windows, וההתקן שהמיקסר
    אחז בו כבר לא בהכרח תקף. בלי אתחול מחדש הצלצול הראשון אחרי ההערה
    היה יוצא לשום מקום.
    """
    global _active_device
    stop()

    def drop():
        global _active_device
        pygame = _pygame()
        if pygame is None:
            return True
        with _mixer_lock:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
            _active_device = None
        return True

    _on_worker(drop, timeout=15)


def stop():
    """עצירה מיידית של הצלצול הנוכחי."""
    _ensure_worker()
    _commands.put(("stop",))


def is_playing():
    return _playing.is_set()


def play(path, duration=5, volume=90, device=None, on_done=None):
    """מנגן קובץ למשך duration שניות אל ההתקן המבוקש.

    מחזיר True אם ההשמעה אכן התחילה.
    """
    if not path or not os.path.exists(path):
        return False
    _ensure_worker()
    done, result = threading.Event(), []
    _commands.put(("play", path, duration, volume, device, done, result))
    # ממתינים לתשובה אמיתית מתהליכון העבודה, כדי שהיומן לא ידווח על
    # צלצול שלא באמת יצא.
    if not done.wait(timeout=10):
        return False
    ok = bool(result and result[0])
    if ok and on_done:
        threading.Timer(max(1, int(duration)), on_done).start()
    return ok
