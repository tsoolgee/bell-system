# -*- coding: utf-8 -*-
"""לאן Windows מנגן? רשימת התקני הפלט והברירת מחדל שביניהם."""
import sys

try:
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
except ImportError as exc:
    print("דילוג: pycaw לא זמין (%s)" % exc)
    sys.exit(0)

default = AudioUtilities.GetSpeakers()
default_id = getattr(default, "id", None)
print("ברירת המחדל של Windows: %s" % getattr(default, "FriendlyName", "?"))
print()
print("כל התקני הפלט הפעילים:")
for dev in AudioUtilities.GetAllDevices():
    name = dev.FriendlyName or ""
    if dev.state != "Active":
        continue
    raw = getattr(dev, "_dev", None)
    level = ""
    if raw is not None:
        try:
            vol = cast(raw.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                       POINTER(IAudioEndpointVolume))
            level = "  עוצמה %d%%%s" % (round(vol.GetMasterVolumeLevelScalar() * 100),
                                        "  (מושתק)" if vol.GetMute() else "")
        except Exception:
            level = ""
    mark = "  ← ברירת המחדל" if dev.id == default_id else ""
    print("  %-52s%s%s" % (name[:52], level, mark))
