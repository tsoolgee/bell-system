# -*- coding: utf-8 -*-
"""לאן הצליל באמת יוצא.

בבית ספר זו שאלה קריטית: אם התקן ברירת המחדל של Windows הוא כבל וירטואלי
או כרטיס לא מחובר, הצלצולים "מתנגנים" בלי שאיש שומע. המודול הזה מזהה את
המצב ומאפשר בדיקת שמע אמיתית שמודדת פלט ולא רק מדווחת הצלחה.

התלות ב-pycaw אופציונלית לגמרי - בלעדיה המערכת עובדת רגיל, רק בלי האבחון.
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


def _endpoint():
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


def _read_info():
    name, volume, _ = _endpoint()
    lowered = name.lower()
    return {
        "name": name,
        "volume": round(volume.GetMasterVolumeLevelScalar() * 100),
        "muted": bool(volume.GetMute()),
        "virtual": any(hint in lowered for hint in _VIRTUAL_HINTS),
        "available": True,
    }


def info():
    """פרטי התקן הפלט הנוכחי, או available=False אם אי אפשר לבדוק."""
    return _run(_read_info) or {"available": False}


def measure(seconds=2.0, interval=0.08):
    """מודד את שיא הפלט בפועל במשך פרק זמן. מחזיר None אם לא ניתן."""
    def watch():
        _, _, meter = _endpoint()
        peak = 0.0
        deadline = time.time() + seconds
        while time.time() < deadline:
            peak = max(peak, meter.GetPeakValue())
            time.sleep(interval)
        return peak

    return _run(watch, timeout=seconds + 10)
