# -*- coding: utf-8 -*-
"""אבחון: האם הקבצים חלשים, או שההשמעה עצמה לא רצה?"""
import array
import os
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import audio, config  # noqa: E402

sdir = config.sounds_dir()
print("--- עוצמת הקבצים ---")
for name in sorted(os.listdir(sdir)):
    if not name.endswith(".wav"):
        continue
    with wave.open(os.path.join(sdir, name)) as fh:
        frames = fh.readframes(fh.getnframes())
        rate, ch, width = fh.getframerate(), fh.getnchannels(), fh.getsampwidth()
    data = array.array("h")
    data.frombytes(frames)
    peak = max(max(data), -min(data)) / 32767.0
    rms = (sum(float(s) * s for s in data) / len(data)) ** 0.5 / 32767.0
    print("%-20s %5.2fs  %dHz ch=%d w=%d  peak=%.2f  rms=%.3f"
          % (name, len(data) / rate / ch, rate, ch, width, peak, rms))

print()
print("--- האם MCI באמת מנגן? (מעקב אחרי position) ---")
path = os.path.join(sdir, "bell_classic.wav")
alias, has_volume = audio._open(path)
print("open ->", alias, "| volume control:", has_volume)
err, val = audio._send("setaudio %s volume to 900" % alias)
print("setaudio volume -> err=%s val=%r" % (err, val))
err, val = audio._send("status %s volume" % alias)
print("status volume   -> err=%s val=%r" % (err, val))
audio._send("play %s from 0" % alias)
for _ in range(6):
    time.sleep(0.25)
    _, mode = audio._send("status %s mode" % alias)
    _, pos = audio._send("status %s position" % alias)
    print("  mode=%-8s position=%s" % (mode, pos))
audio._send("stop %s" % alias)
audio._send("close %s" % alias)

print()
print("--- winsound (WAV נטו) ---")
import winsound  # noqa: E402
t = time.time()
winsound.PlaySound(path, winsound.SND_FILENAME)
print("PlaySound חסם למשך %.2fs (אורך הקובץ 3.0s)" % (time.time() - t))
