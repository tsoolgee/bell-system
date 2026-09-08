# -*- coding: utf-8 -*-
"""הגברה מעל 100%.

בקרת העוצמה של הנגן ושל Windows נעצרת ב-100%: זה כל מה שאפשר לשלוח
לכרטיס הקול, ומעליו הוא פשוט לא מקבל יותר. כדי שהצלצול ייצא חזק יותר
צריך להגביר את הדגימות עצמן - ומעל הברך לדחוס אותן ברכה במקום לחתוך.
חיתוך ישר הופך צלצול לרעש מרוסק; דחיסה מעלה את האנרגיה הנשמעת ומשאירה
אותו צלצול. זו בדיוק העקומה שמייצרת את הצלילים המובנים (sounds._loudness).

מה זה אומר בפועל: מעל 100% השיא כבר נוגע בתקרה ולא יעלה, אבל ה-RMS -
מה שהאוזן שומעת כ"חזק" - כן עולה. לכן כל בדיקה של ההגברה מודדת ממוצע,
לא שיא.
"""

import array
import math
import os
import tempfile
import threading
import wave

KNEE = 0.72          # מתחת לזה ההגברה לינארית לגמרי
MAX_PERCENT = 200
FULL = 32767

_tables = {}
_files = {}
_lock = threading.RLock()


def clamp(percent, default=100):
    """כל עוצמה שמגיעה מבחוץ עוברת דרך כאן. 0..200."""
    try:
        value = int(round(float(percent)))
    except (TypeError, ValueError):
        return default
    return max(0, min(MAX_PERCENT, value))


def curve(value, factor, knee=KNEE):
    """מגביר ערך מנורמל (-1..1) פי factor בלי לחרוג מ-1."""
    value *= factor
    magnitude = abs(value)
    if magnitude > knee:
        magnitude = knee + (1.0 - knee) * math.tanh((magnitude - knee) / (1.0 - knee))
    return math.copysign(min(magnitude, 1.0), value)


def table(factor):
    """טבלת תרגום ל-16 ביט, 65536 ערכים.

    הסידור מנצל אינדוקס שלילי של Python: table[s] נכון גם לדגימה חיובית
    וגם לשלילית, ולכן אפשר להגביר בלוק שלם עם map בלי חשבון על כל דגימה.
    """
    key = round(float(factor), 3)
    with _lock:
        cached = _tables.get(key)
        if cached is not None:
            return cached
        values = [0] * 65536
        for i in range(32768):
            values[i] = int(round(curve(i / 32767.0, key) * FULL))
        for i in range(-32768, 0):
            values[65536 + i] = int(round(curve(i / 32768.0, key) * FULL))
        if len(_tables) > 8:
            _tables.clear()
        _tables[key] = values
        return values


def apply_pcm16(raw, percent):
    """מגביר בלוק PCM של 16 ביט. 100% ומטה מוחזר כמו שהוא."""
    factor = clamp(percent) / 100.0
    if factor <= 1.0 or not raw:
        return raw
    usable = len(raw) - (len(raw) % 2)
    samples = array.array("h")
    samples.frombytes(raw[:usable])
    out = array.array("h", map(table(factor).__getitem__, samples))
    return out.tobytes() + raw[usable:]


def rms_pcm16(raw, stride=7):
    """עוצמה נשמעת של בלוק PCM, 0..1. דוגמים בדילוגים - מספיק לדיוק כאן."""
    usable = len(raw) - (len(raw) % 2)
    if usable < 2:
        return 0.0
    samples = array.array("h")
    samples.frombytes(raw[:usable])
    chunk = samples[::max(1, int(stride))]
    total = 0.0
    for value in chunk:
        total += float(value) * value
    return math.sqrt(total / len(chunk)) / FULL


def peak_pcm16(raw):
    """השיא של הבלוק, 0..1."""
    usable = len(raw) - (len(raw) % 2)
    if usable < 2:
        return 0.0
    samples = array.array("h")
    samples.frombytes(raw[:usable])
    return max(max(samples), -min(samples)) / float(FULL)


def db(after, before):
    """היחס בין שתי עוצמות, בדציבלים. None כשאין מה להשוות."""
    try:
        if not after or not before or after <= 0 or before <= 0:
            return None
        return round(20.0 * math.log10(float(after) / float(before)), 2)
    except (TypeError, ValueError):
        return None


def expected_db(path, percent):
    """כמה dB ההגברה מוסיפה לקובץ עצמו - חישוב, לפני שמנגנים.

    זה המספר שלא תלוי בכרטיס הקול, ולכן הוא זה שמאפשר לומר אם מדידה
    שיצאה נמוכה מעידה על בעיה בהגברה או על בעיה בהתקן.
    """
    if clamp(percent) <= 100:
        return 0.0
    try:
        with wave.open(path, "rb") as fh:
            if fh.getsampwidth() != 2:
                return None
            raw = fh.readframes(fh.getnframes())
    except (OSError, wave.Error, EOFError):
        return None
    return db(rms_pcm16(apply_pcm16(raw, percent)), rms_pcm16(raw))


def amplified_file(path, percent):
    """קובץ WAV מוגבר, לשימוש המנוע שלא יודע לקבל דגימות בזיכרון (MCI).

    None כשאי אפשר - קובץ שאינו PCM 16 ביט, או כתיבה שנכשלה. הקורא
    ממשיך אז עם המקור, בעוצמה רגילה, במקום לא לצלצל בכלל.
    """
    percent = clamp(percent)
    if percent <= 100:
        return None
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return None
    key = (os.path.abspath(path), percent, stamp)
    with _lock:
        cached = _files.get(key)
    if cached and os.path.exists(cached):
        return cached
    try:
        with wave.open(path, "rb") as src:
            if src.getsampwidth() != 2:
                return None
            params = src.getparams()
            raw = src.readframes(src.getnframes())
        target = os.path.join(tempfile.gettempdir(),
                              "bell-boost-%d-%s.wav" % (percent, _short(key[0])))
        with wave.open(target, "wb") as dst:
            dst.setnchannels(params.nchannels)
            dst.setsampwidth(2)
            dst.setframerate(params.framerate)
            dst.writeframes(apply_pcm16(raw, percent))
    except (OSError, wave.Error, EOFError, ValueError):
        return None
    with _lock:
        _files[key] = target
    return target


def _short(text):
    return "%08x" % (abs(hash(text)) & 0xFFFFFFFF)


def forget():
    """שוכח מה שנשמר במטמון. נקרא כשמאתחלים את השמע מחדש."""
    with _lock:
        _tables.clear()
        _files.clear()
