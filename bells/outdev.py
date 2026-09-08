# -*- coding: utf-8 -*-
"""לאן הצליל באמת יוצא, ומדידה שמאמתת שהוא באמת יצא.

בבית ספר זו שאלה קריטית: אם הצלצולים הולכים להתקן ברירת המחדל של Windows,
מספיק שמישהו יחבר אוזניות כדי שהכיתות יישארו בשקט. המערכת מנגנת להתקן
שנבחר במפורש, והמודול הזה מודד את נקודת הקצה הזו כדי לאמת.

התלות ב-pycaw אופציונלית - בלעדיה המערכת עובדת רגיל, רק בלי האבחון.
"""

import queue
import threading
import time

# שמות שמעידים על התקן שאינו רמקול פיזי
_VIRTUAL_HINTS = ("cable", "virtual", "voicemeeter", "vb-audio", "steam streaming",
                  "nvidia broadcast", "obs", "loopback")

_jobs = queue.Queue()
_thread = None
_lock = threading.Lock()


def is_virtual(name):
    lowered = (name or "").lower()
    return any(hint in lowered for hint in _VIRTUAL_HINTS)


def _worker():
    """כל עבודות ה-COM רצות כאן.

    כל בקשת HTTP מגיעה בתהליכון חדש שבו COM לא מאותחל, ומחזור של
    CoInitialize/CoUninitialize סביב כל קריאה שובר את האובייקטים
    ש-pycaw שומר ב-cache. לכן אפרטמנט אחד, שנפתח פעם אחת וחי לתמיד.
    """
    import comtypes
    comtypes.CoInitialize()
    while True:
        fn, done, out = _jobs.get()
        try:
            out.append(fn())
        except Exception:
            out.append(None)
        done.set()


def _run(fn, timeout=15):
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_worker, name="bell-audiodev", daemon=True)
            _thread.start()
    done, out = threading.Event(), []
    _jobs.put((fn, done, out))
    if not done.wait(timeout):
        return None
    return out[0] if out else None


def _default_endpoint():
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, IAudioMeterInformation

    device = AudioUtilities.GetSpeakers()
    raw = getattr(device, "_dev", device)
    volume = cast(raw.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                  POINTER(IAudioEndpointVolume))
    meter = cast(raw.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None),
                 POINTER(IAudioMeterInformation))
    return getattr(device, "FriendlyName", "") or "", volume, meter


def _named_endpoint(name):
    """נקודת קצה לפי שם ידידותי. SDL ו-Windows מדווחים אותם שמות."""
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, IAudioMeterInformation
    from pycaw.constants import DEVICE_STATE, EDataFlow

    enumerator = AudioUtilities.GetDeviceEnumerator()
    collection = enumerator.EnumAudioEndpoints(EDataFlow.eRender.value,
                                               DEVICE_STATE.ACTIVE.value)
    for i in range(collection.GetCount()):
        dev = collection.Item(i)
        friendly = AudioUtilities.CreateDevice(dev).FriendlyName or ""
        if friendly == name:
            volume = cast(dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                          POINTER(IAudioEndpointVolume))
            meter = cast(dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None),
                         POINTER(IAudioMeterInformation))
            return friendly, volume, meter
    raise LookupError(name)


def _endpoint(name=None):
    if name:
        try:
            return _named_endpoint(name)
        except Exception:
            pass  # ההתקן נעלם - נופלים לברירת המחדל, כמו הנגן עצמו
    return _default_endpoint()


def info(name=None):
    """פרטי ההתקן שהצלצולים יוצאים אליו, או available=False אם אין אבחון."""
    def read():
        found, volume, _ = _endpoint(name)
        return {
            "name": found,
            "volume": round(volume.GetMasterVolumeLevelScalar() * 100),
            "muted": bool(volume.GetMute()),
            "virtual": is_virtual(found),
            "isDefault": not name or found != name,
            "available": True,
        }

    return _run(read) or {"available": False}


def set_volume(percent, name=None, unmute=True):
    """קובע את עוצמת ההתקן ב-Windows ומחזיר את מה שנקרא ממנו בחזרה.

    הקריאה חוזרת ולא מסתמכת על ההצבה: זו כל ההוכחה שההגברה באמת נכנסה.
    התקן מושתק על 100% הוא עדיין שקט, ולכן העלאת עוצמה מבטלת השתקה.
    """
    target = max(0.0, min(1.0, float(percent) / 100.0))

    def apply():
        found, volume, _ = _endpoint(name)
        volume.SetMasterVolumeLevelScalar(target, None)
        if unmute and target > 0 and volume.GetMute():
            volume.SetMute(0, None)
        return {
            "name": found,
            "requested": round(target * 100),
            "volume": round(volume.GetMasterVolumeLevelScalar() * 100),
            "muted": bool(volume.GetMute()),
            "available": True,
        }

    return _run(apply) or {"available": False}


def set_mute(muted, name=None):
    def apply():
        found, volume, _ = _endpoint(name)
        volume.SetMute(1 if muted else 0, None)
        return {
            "name": found,
            "volume": round(volume.GetMasterVolumeLevelScalar() * 100),
            "muted": bool(volume.GetMute()),
            "available": True,
        }

    return _run(apply) or {"available": False}


def measure_detail(seconds=2.0, name=None, interval=0.05):
    """שיא *וגם* ממוצע של הפלט בפועל. None אם לא ניתן למדוד.

    הממוצע הוא מה שמעיד על הגברה. השיא נעצר ב-1.0, ולכן צליל שכבר נוגע
    בתקרה לא יזוז שם גם כשמגבירים - אבל האנרגיה כן עולה, והיא נמדדת
    בממוצע הקריאות. זה בדיוק ההבדל בין "יש אות" ל"יצא חזק יותר".
    """
    def watch():
        _, _, meter = _endpoint(name)
        peak = 0.0
        total = 0.0
        count = 0
        deadline = time.time() + seconds
        while time.time() < deadline:
            value = meter.GetPeakValue()
            peak = max(peak, value)
            total += value
            count += 1
            time.sleep(interval)
        return {"peak": peak, "mean": (total / count) if count else 0.0,
                "samples": count}

    return _run(watch, timeout=seconds + 10)


def measure(seconds=2.0, name=None, interval=0.08):
    """שיא הפלט בפועל בנקודת הקצה. None אם לא ניתן למדוד."""
    detail = measure_detail(seconds, name, interval)
    return None if detail is None else detail["peak"]
