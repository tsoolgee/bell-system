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


def measure(seconds=2.0, name=None, interval=0.08):
    """שיא הפלט בפועל בנקודת הקצה. None אם לא ניתן למדוד."""
    def watch():
        _, _, meter = _endpoint(name)
        peak = 0.0
        deadline = time.time() + seconds
        while time.time() < deadline:
            peak = max(peak, meter.GetPeakValue())
            time.sleep(interval)
        return peak

    return _run(watch, timeout=seconds + 10)
