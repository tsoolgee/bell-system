# -*- coding: utf-8 -*-
"""הוכחה: האם אפשר לנתב צליל להתקן מסוים, בלי לגעת בברירת המחדל של Windows?

מודדים את מד העוצמה של *כל* נקודת קצה בנפרד. אם רק ההתקן שנבחר מראה
אות - הניתוב עצמאי באמת.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from ctypes import POINTER, cast  # noqa: E402
from comtypes import CLSCTX_ALL  # noqa: E402
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation  # noqa: E402
from pycaw.constants import DEVICE_STATE, EDataFlow  # noqa: E402

from bells import config, sounds  # noqa: E402

TARGET = "Speakers (Realtek(R) Audio)"


def endpoints():
    """כל התקני הפלט הפעילים, עם מד עוצמה לכל אחד."""
    enumerator = AudioUtilities.GetDeviceEnumerator()
    collection = enumerator.EnumAudioEndpoints(EDataFlow.eRender.value,
                                               DEVICE_STATE.ACTIVE.value)
    out = []
    for i in range(collection.GetCount()):
        dev = collection.Item(i)
        name = AudioUtilities.CreateDevice(dev).FriendlyName
        meter = cast(dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None),
                     POINTER(IAudioMeterInformation))
        out.append((name, meter))
    return out


sounds.ensure(config.sounds_dir())
path = os.path.join(config.sounds_dir(), "bell_classic.wav")

default_name = AudioUtilities.GetSpeakers().FriendlyName
print("ברירת המחדל של Windows: %s" % default_name)
print("מנגנים במכוון אל:        %s" % TARGET)
print()

meters = endpoints()
print("התקנים שנמצאו:")
for name, _ in meters:
    print("   ", name)

peaks = {name: 0.0 for name, _ in meters}
stop = threading.Event()


def sample():
    while not stop.is_set():
        for name, meter in meters:
            try:
                peaks[name] = max(peaks[name], meter.GetPeakValue())
            except Exception:
                pass
        time.sleep(0.05)


watcher = threading.Thread(target=sample, daemon=True)
watcher.start()
time.sleep(0.8)
baseline = dict(peaks)

import pygame  # noqa: E402

pygame.mixer.quit()
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024, devicename=TARGET)
print("\nמיקסר אותחל:", pygame.mixer.get_init())
sound = pygame.mixer.Sound(path)
sound.play()
time.sleep(3.0)
sound.stop()
pygame.mixer.quit()
stop.set()
time.sleep(0.2)

print()
print("%-42s %-10s %-10s" % ("התקן", "רקע", "בהשמעה"))
ok = False
for name, _ in meters:
    got = peaks[name] > max(0.02, baseline.get(name, 0) * 3)
    mark = "  ← קיבל אות" if got else ""
    print("%-42s %-10.3f %-10.3f%s" % (name[:42], baseline.get(name, 0), peaks[name], mark))
    if got and name == TARGET:
        ok = True
    if got and name != TARGET:
        ok = False if name == default_name else ok

print()
print("תוצאה: ניתוב עצמאי עובד ✓" if ok else "תוצאה: הניתוב לא עבד ✗")
sys.exit(0 if ok else 1)
