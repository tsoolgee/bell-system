# -*- coding: utf-8 -*-
"""יצירת ספריית הצלילים המובנית - נוצרת מקומית, ללא קבצים חיצוניים.

הצלילים מנורמלים לעוצמה גבוהה: צלצול בית ספר צריך לחתוך רעש של כיתה,
ולכן הם רצופים ולא דועכים מיד.
"""

import array
import math
import os
import wave

RATE = 22050          # די והותר לצלצול, וחוסך חצי מזמן היצירה
TARGET_PEAK = 0.97


def _write(path, samples):
    data = array.array("h", (max(-32767, min(32767, int(s * 32767))) for s in samples))
    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(RATE)
        fh.writeframes(data.tobytes())


def _normalize(samples, peak=TARGET_PEAK):
    top = max(abs(s) for s in samples) or 1.0
    gain = peak / top
    return [s * gain for s in samples]


def _saturate(samples, drive=1.6):
    """הגברה רכה - מעלה את העוצמה הנשמעת בלי עיוות דיגיטלי צורם."""
    return [math.tanh(s * drive) for s in samples]


def _fade_edges(samples, ms=12):
    n = int(RATE * ms / 1000.0)
    for i in range(min(n, len(samples) // 2)):
        k = i / n
        samples[i] *= k
        samples[-1 - i] *= k
    return samples


def _electric_bell(seconds, base=680.0, strike=23.0, depth=0.72):
    """פעמון חשמלי: צליל רצוף שהפטיש מכה בו עשרות פעמים בשנייה."""
    partials = [(base, 1.0), (base * 1.003, 0.55), (base * 1.98, 0.62),
                (base * 2.97, 0.34), (base * 4.13, 0.16)]
    out = []
    for i in range(int(RATE * seconds)):
        t = i / RATE
        tremolo = (1.0 - depth) + depth * abs(math.sin(math.pi * strike * t))
        out.append(sum(math.sin(2 * math.pi * f * t) * w for f, w in partials) * tremolo)
    return out


def _struck(freqs, seconds, decay=2.0):
    """צליל מוכה שדועך - לגונג ולמנגינה."""
    out = []
    for i in range(int(RATE * seconds)):
        t = i / RATE
        env = math.exp(-decay * t)
        out.append(sum(math.sin(2 * math.pi * f * t) * w for f, w in freqs) * env)
    return out


def _mix(layers, seconds):
    """ערבוב שכבות שמתחילות בזמנים שונים (offset בשניות, דגימות)."""
    total = int(RATE * seconds)
    out = [0.0] * total
    for offset, samples in layers:
        start = int(RATE * offset)
        for i, value in enumerate(samples):
            j = start + i
            if j >= total:
                break
            out[j] += value
    return out


def bell_classic():
    return _fade_edges(_saturate(_normalize(_electric_bell(4.0, 680.0, 23.0)), 1.9))


def bell_break():
    return _fade_edges(_saturate(_normalize(_electric_bell(4.0, 505.0, 15.0, depth=0.8)), 1.7))


def chime():
    notes = [523.25, 659.25, 783.99, 1046.50]
    layers = []
    for i, f in enumerate(notes):
        layers.append((i * 0.55, _struck([(f, 1.0), (f * 2, 0.35), (f * 3, 0.12)], 3.2, decay=1.5)))
    layers.append((2.2, _struck([(523.25, 0.9), (783.99, 0.7), (1046.50, 0.5)], 3.0, decay=1.0)))
    return _fade_edges(_saturate(_normalize(_mix(layers, 5.0)), 1.5))


def gong():
    body = _struck([(110, 1.0), (164, 0.7), (220, 0.55), (277, 0.35),
                    (330, 0.25), (441, 0.15)], 4.0, decay=0.75)
    return _fade_edges(_saturate(_normalize(body), 2.2))


def siren():
    out, phase = [], 0.0
    for i in range(int(RATE * 4.0)):
        freq = 700 + 480 * math.sin(2 * math.pi * 0.75 * (i / RATE))
        phase += 2 * math.pi * freq / RATE
        out.append(math.sin(phase))
    return _fade_edges(_saturate(_normalize(out), 1.5), ms=50)


GENERATORS = {
    "bell_classic.wav": bell_classic,
    "bell_break.wav": bell_break,
    "chime.wav": chime,
    "gong.wav": gong,
    "siren.wav": siren,
}

# מזהה גרסה: שינוי כאן מייצר מחדש את הצלילים המובנים אצל מי שכבר התקין.
REVISION = 2


def ensure(target_dir):
    """יוצר את קבצי הצליל המובנים אם הם חסרים או מגרסה ישנה."""
    os.makedirs(target_dir, exist_ok=True)
    stamp = os.path.join(target_dir, ".builtin-revision")
    current = ""
    try:
        with open(stamp, encoding="utf-8") as fh:
            current = fh.read().strip()
    except OSError:
        pass
    fresh = current == str(REVISION)
    for name, gen in GENERATORS.items():
        path = os.path.join(target_dir, name)
        if fresh and os.path.exists(path) and os.path.getsize(path) > 1000:
            continue
        _write(path, gen())
    with open(stamp, "w", encoding="utf-8") as fh:
        fh.write(str(REVISION))
