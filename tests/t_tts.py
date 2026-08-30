# -*- coding: utf-8 -*-
"""בדיקת מנגנון הכרוז. מסלול Gemini נבדק רק אם קיים מפתח בסביבה."""
import array
import io
import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import tts  # noqa: E402

fails = []


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name + ("  -> " + str(detail) if detail and not condition else ""))
    if not condition:
        fails.append(name)


def wav_stats(data):
    with wave.open(io.BytesIO(data)) as fh:
        frames = fh.readframes(fh.getnframes())
        rate, width = fh.getframerate(), fh.getsampwidth()
    samples = array.array("h")
    samples.frombytes(frames)
    peak = max(max(samples), -min(samples)) / 32767.0 if samples else 0
    return len(samples) / rate, rate, width, peak


print("--- אימות קלט ---")
for bad, label in [("", "טקסט ריק נדחה"), ("א" * 1600, "טקסט ארוך מדי נדחה")]:
    try:
        tts.synthesize(bad, provider="sapi")
        check(label, False, "לא נזרקה שגיאה")
    except tts.TTSError:
        check(label, True)

print("--- עטיפת PCM ל-WAV ---")
pcm = array.array("h", (int(20000 * ((i % 50) / 50.0 - 0.5)) for i in range(24000))).tobytes()
wav = tts._pcm_to_wav(pcm, 24000)
dur, rate, width, peak = wav_stats(wav)
check("כותרת WAV תקינה", wav[:4] == b"RIFF" and wav[8:12] == b"WAVE")
check("קצב דגימה נשמר", rate == 24000, rate)
check("אורך נכון (שנייה אחת)", abs(dur - 1.0) < 0.01, dur)
check("רוחב דגימה 16 ביט", width == 2, width)
check("קצב מתוך mimeType", tts._rate_from_mime("audio/L16;codec=pcm;rate=24000") == 24000)
check("קצב ברירת מחדל כשחסר", tts._rate_from_mime("audio/L16") == 24000)

print("--- Gemini ללא מפתח ---")
try:
    tts.synthesize("שלום", provider="gemini", api_key="")
    check("חוסר מפתח נתפס", False, "לא נזרקה שגיאה")
except tts.TTSError as exc:
    check("חוסר מפתח נתפס", "מפתח" in str(exc), exc)

print("--- קולות Windows ---")
voices = tts.sapi_voices()
check("נמצאו קולות מותקנים", len(voices) > 0, voices)
for v in voices:
    print("       %s (%s)%s" % (v["name"], v["culture"], "  ← עברית" if v["hebrew"] else ""))

if voices:
    data = tts.sapi("Attention please, the break is over.", voices[0]["name"])
    dur, rate, width, peak = wav_stats(data)
    check("SAPI יצר WAV", data[:4] == b"RIFF")
    check("ההקלטה אינה ריקה", dur > 0.5 and peak > 0.05, "dur=%.2f peak=%.2f" % (dur, peak))
    print("       אורך %.2fs  קצב %dHz  שיא %.2f" % (dur, rate, peak))

key = os.environ.get("GEMINI_API_KEY", "")
print("--- Gemini אונליין ---")
if not key:
    print("       דילוג: לא הוגדר GEMINI_API_KEY")
else:
    try:
        data = tts.gemini("תלמידים יקרים, ההפסקה הסתיימה.", "Kore", key)
        dur, rate, width, peak = wav_stats(data)
        check("Gemini החזיר אודיו", dur > 0.5 and peak > 0.05,
              "dur=%.2f peak=%.2f" % (dur, peak))
        print("       אורך %.2fs  קצב %dHz" % (dur, rate))
    except tts.TTSError as exc:
        check("Gemini החזיר אודיו", False, exc)

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
