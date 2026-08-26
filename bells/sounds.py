# -*- coding: utf-8 -*-
"""יצירת ספריית הצלילים המובנית - נוצרת מקומית, ללא קבצים חיצוניים."""

import array
import math
import os
import wave

RATE = 44100


def _write(path, samples):
    data = array.array("h")
    for s in samples:
        data.append(max(-32767, min(32767, int(s * 32767))))
    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(RATE)
        fh.writeframes(data.tobytes())


def _tone(freqs, seconds, decay=4.0, amp=0.5):
    total = int(RATE * seconds)
    out = []
    for i in range(total):
        t = i / RATE
        env = math.exp(-decay * t)
        value = sum(math.sin(2 * math.pi * f * t) * w for f, w in freqs)
        out.append(value * env * amp)
    return out


def _silence(seconds):
    return [0.0] * int(RATE * seconds)


def _fade_edges(samples, ms=8):
    n = int(RATE * ms / 1000.0)
    for i in range(min(n, len(samples))):
        k = i / n
        samples[i] *= k
        samples[-1 - i] *= k
    return samples


def bell_classic():
    ring = _tone([(880, 0.55), (1320, 0.28), (2640, 0.12), (587, 0.18)], 0.45, decay=6.5)
    out = []
    for _ in range(6):
        out += ring + _silence(0.05)
    return _fade_edges(out)


def bell_break():
    ring = _tone([(660, 0.55), (990, 0.3), (1980, 0.12)], 0.6, decay=5.0)
    out = []
    for _ in range(4):
        out += ring + _silence(0.12)
    return _fade_edges(out)


def chime():
    notes = [523.25, 659.25, 783.99, 1046.50]
    out = []
    for f in notes:
        out += _tone([(f, 0.6), (f * 2, 0.2), (f * 3, 0.07)], 0.75, decay=3.2, amp=0.45)
    out += _tone([(523.25, 0.5), (783.99, 0.35), (1046.50, 0.25)], 1.6, decay=2.0, amp=0.45)
    return _fade_edges(out)


def gong():
    out = _tone([(110, 0.5), (164, 0.3), (220, 0.25), (277, 0.15), (330, 0.1)], 3.5,
                decay=1.1, amp=0.6)
    return _fade_edges(out)


def siren():
    out = []
    total = int(RATE * 4.0)
    phase = 0.0
    for i in range(total):
        t = i / RATE
        freq = 700 + 450 * math.sin(2 * math.pi * 0.7 * t)
        phase += 2 * math.pi * freq / RATE
        out.append(math.sin(phase) * 0.42)
    return _fade_edges(out, ms=60)


GENERATORS = {
    "bell_classic.wav": bell_classic,
    "bell_break.wav": bell_break,
    "chime.wav": chime,
    "gong.wav": gong,
    "siren.wav": siren,
}


def ensure(target_dir):
    """יוצר את קבצי הצליל המובנים אם הם חסרים."""
    os.makedirs(target_dir, exist_ok=True)
    for name, gen in GENERATORS.items():
        path = os.path.join(target_dir, name)
        if not os.path.exists(path) or os.path.getsize(path) < 1000:
            _write(path, gen())
