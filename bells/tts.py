# -*- coding: utf-8 -*-
"""יצירת כרוז מוקלט מטקסט.

שני מקורות:
* gemini - אונליין, קולות נוירונים איכותיים בעברית. דורש מפתח API של המשתמש.
* sapi   - אופליין, קולות Windows המותקנים במחשב. בלי מפתח ובלי אינטרנט,
           אבל איכותי רק אם מותקן קול בשפה המתאימה.

הטקסט נשלח החוצה רק במסלול gemini, ורק כשהמשתמש לוחץ על הכפתור.
"""

import array
import base64
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import wave

GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"

# תת-קבוצה מייצגת מתוך הקולות המובנים של Gemini
GEMINI_VOICES = [
    ("Kore", "כורה — נשי, ענייני"),
    ("Puck", "פאק — גברי, נמרץ"),
    ("Charon", "כארון — גברי, רגוע"),
    ("Aoede", "אאודה — נשי, חם"),
    ("Fenrir", "פנריר — גברי, סמכותי"),
    ("Leda", "לדה — נשי, צעיר"),
    ("Orus", "אורוס — גברי, יציב"),
    ("Zephyr", "זפיר — נשי, בהיר"),
]


class TTSError(Exception):
    pass


def _pcm_to_wav(pcm, rate=24000, channels=1, width=2):
    """Gemini מחזיר PCM גולמי - עוטפים אותו בכותרת WAV."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        with wave.open(tmp.name, "wb") as fh:
            fh.setnchannels(channels)
            fh.setsampwidth(width)
            fh.setframerate(rate)
            fh.writeframes(pcm)
        with open(tmp.name, "rb") as fh:
            return fh.read()
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


def _rate_from_mime(mime):
    match = re.search(r"rate=(\d+)", mime or "")
    return int(match.group(1)) if match else 24000


def _boost(wav_bytes, target_rms=0.20, max_gain=8.0, knee=0.70):
    """מגביר כרוז לעוצמה שנשמעת מעל רעש של כיתה.

    מכוון לפי RMS ולא לפי שיא, כי בדיבור השיא בודד והשאר חלש. מה שחורג
    מהברך נדחס ברכות במקום להיחתך, כדי לא לעוות את ההברות.
    """
    try:
        with wave.open(io.BytesIO(wav_bytes)) as fh:
            params = fh.getparams()
            frames = fh.readframes(fh.getnframes())
    except (wave.Error, EOFError):
        return wav_bytes
    if params.sampwidth != 2 or not frames:
        return wav_bytes

    samples = array.array("h")
    samples.frombytes(frames)
    if not samples:
        return wav_bytes
    rms = (sum(float(s) * s for s in samples) / len(samples)) ** 0.5 / 32767.0
    if rms < 1e-4:
        return wav_bytes
    gain = min(target_rms / rms, max_gain)
    if gain <= 1.02:
        return wav_bytes

    out = array.array("h", bytes(len(samples) * 2))
    for i, sample in enumerate(samples):
        value = sample / 32767.0 * gain
        magnitude = abs(value)
        if magnitude > knee:
            magnitude = knee + (1.0 - knee) * math.tanh((magnitude - knee) / (1.0 - knee))
            value = math.copysign(magnitude, value)
        out[i] = max(-32767, min(32767, int(value * 32767)))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as fh:
        fh.setnchannels(params.nchannels)
        fh.setsampwidth(2)
        fh.setframerate(params.framerate)
        fh.writeframes(out.tobytes())
    return buf.getvalue()


def gemini(text, voice="Kore", api_key="", timeout=60):
    if not api_key:
        raise TTSError("חסר מפתח API של Gemini. אפשר להזין אותו במסך ההגדרות.")
    payload = json.dumps({
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            },
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        GEMINI_URL % GEMINI_MODEL,
        data=payload,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8"))["error"]["message"]
        except Exception:
            pass
        if exc.code in (401, 403):
            raise TTSError("המפתח נדחה על ידי Google. %s" % detail)
        if exc.code == 429:
            raise TTSError("חריגה ממכסת השימוש ב-Gemini. נסו שוב מאוחר יותר.")
        raise TTSError("שגיאת Gemini %d: %s" % (exc.code, detail or "לא ידועה"))
    except urllib.error.URLError as exc:
        raise TTSError("אין חיבור לאינטרנט ליצירת הכרוז (%s)." % exc.reason)

    try:
        part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
    except (KeyError, IndexError, TypeError):
        raise TTSError("Gemini לא החזיר אודיו. ייתכן שהטקסט נחסם על ידי מסנני התוכן.")
    pcm = base64.b64decode(part["data"])
    if not pcm:
        raise TTSError("Gemini החזיר אודיו ריק.")
    return _pcm_to_wav(pcm, _rate_from_mime(part.get("mimeType")))


# מועבר כקובץ .ps1 עם param(): העברת ארגומנטים ל-powershell -Command
# לא נקשרת ל-$args, ומרכאות בטקסט חופשי מסוכנות מדי לשרשור לשורת פקודה.
_PS_SCRIPT = r"""param(
    [Parameter(Mandatory=$true)][string]$TextFile,
    [Parameter(Mandatory=$true)][string]$WavFile,
    [string]$Voice = "",
    [int]$Rate = 0
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$text = [System.IO.File]::ReadAllText($TextFile, [System.Text.Encoding]::UTF8)
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($Voice) { try { $synth.SelectVoice($Voice) } catch {} }
$synth.Rate = $Rate
$synth.SetOutputToWaveFile($WavFile)
$synth.Speak($text)
$synth.Dispose()
"""


def sapi_voices():
    """הקולות המותקנים במחשב."""
    if sys.platform != "win32":
        return []
    script = ("Add-Type -AssemblyName System.Speech; "
              "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
              ".GetInstalledVoices() | ForEach-Object "
              "{ $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, timeout=25, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return []
    voices = []
    for line in (out.stdout or "").splitlines():
        if "|" in line:
            name, culture = line.strip().split("|", 1)
            voices.append({"name": name, "culture": culture,
                           "hebrew": culture.lower().startswith("he")})
    return voices


def sapi(text, voice="", rate=0):
    if sys.platform != "win32":
        raise TTSError("קולות Windows זמינים רק ב-Windows.")
    paths = []
    for suffix in (".txt", ".wav", ".ps1"):
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        handle.close()
        paths.append(handle.name)
    txt_path, wav_path, ps_path = paths
    try:
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        with open(ps_path, "w", encoding="utf-8-sig") as fh:
            fh.write(_PS_SCRIPT)
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", ps_path,
             "-TextFile", txt_path, "-WavFile", wav_path,
             "-Voice", voice or "", "-Rate", str(int(rate))],
            capture_output=True, timeout=90, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 100:
            detail = (result.stderr or result.stdout or "").strip()
            raise TTSError("יצירת הכרוז נכשלה. %s" % detail[:200])
        with open(wav_path, "rb") as fh:
            return fh.read()
    except subprocess.TimeoutExpired:
        raise TTSError("יצירת הכרוז ארכה יותר מדי זמן.")
    finally:
        for path in paths:
            try:
                os.remove(path)
            except OSError:
                pass


def synthesize(text, provider="gemini", voice="", api_key="", rate=0):
    text = (text or "").strip()
    if not text:
        raise TTSError("לא הוזן טקסט לכרוז.")
    if len(text) > 1500:
        raise TTSError("הטקסט ארוך מדי (עד 1500 תווים).")
    audio = sapi(text, voice, rate) if provider == "sapi" else gemini(text, voice or "Kore", api_key)
    return _boost(audio)
