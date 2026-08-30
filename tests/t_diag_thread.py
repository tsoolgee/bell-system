# -*- coding: utf-8 -*-
"""האם MCI באמת מרנדר כשפותחים בתהליכון אחד ומנגנים באחר?

זה בדיוק מה שקורה באפליקציה: הבקשה נפתחת בתהליכון של השרת/המנוע,
וההשמעה רצה בתהליכון נפרד.
"""
import array
import ctypes
import os
import sys
import threading
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import audio, config  # noqa: E402

path = os.path.join(config.sounds_dir(), "bell_classic.wav")

print("--- הקובץ שהאפליקציה באמת מנגנת ---")
print("   ", path)
with wave.open(path) as fh:
    raw = fh.readframes(fh.getnframes())
    rate = fh.getframerate()
samples = array.array("h")
samples.frombytes(raw)
rms = (sum(float(s) * s for s in samples) / len(samples)) ** 0.5 / 32767.0
print("    אורך %.1fs  קצב %dHz  RMS %.3f" % (len(samples) / rate, rate, rms))
print("    עוצמה בהגדרות:", config.settings().get("volume"))

print()
print("--- עוצמת המערכת ומצב ההשתקה ---")
try:
    from ctypes import POINTER, cast
    import comtypes  # noqa: F401
    print("    comtypes זמין")
except ImportError:
    print("    comtypes לא מותקן - בודקים דרך MCI בלבד")


def probe(kind, cross_thread):
    """פותח ומנגן, ומחזיר את התקדמות ה-position."""
    alias = "probe_%s_%d" % (kind or "auto", cross_thread)
    audio._send("close %s" % alias)
    cmd = ('open "%s" alias %s' % (path, alias) if kind is None
           else 'open "%s" type %s alias %s' % (path, kind, alias))
    if audio._send(cmd)[0]:
        return "open נכשל"
    positions = []

    def play_and_watch():
        audio._send("play %s from 0" % alias)
        for _ in range(5):
            time.sleep(0.2)
            positions.append(audio._send("status %s position" % alias)[1])

    if cross_thread:
        t = threading.Thread(target=play_and_watch)
        t.start()
        t.join()
    else:
        play_and_watch()
    audio._send("stop %s" % alias)
    audio._send("close %s" % alias)
    return positions


print()
print("--- התקדמות ההשמעה ---")
for kind in ("mpegvideo", "waveaudio", None):
    same = probe(kind, cross_thread=False)
    cross = probe(kind, cross_thread=True)
    print("%-11s אותו תהליכון: %-28s תהליכון אחר: %s"
          % (kind or "(auto)", same, cross))
