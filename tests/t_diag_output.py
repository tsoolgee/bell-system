# -*- coding: utf-8 -*-
"""האם באמת יוצא צליל מכרטיס הקול?

לא מסתמך על דיווח של MCI אלא קורא את מד העוצמה של נקודת הקצה
(IAudioMeterInformation). דורש pycaw - כלי אבחון בלבד, לא תלות של המערכת.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import audio, config, sounds  # noqa: E402

try:
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, IAudioMeterInformation
except ImportError as exc:
    print("דילוג: pycaw לא זמין (%s)" % exc)
    sys.exit(0)

device = AudioUtilities.GetSpeakers()
# בגרסאות pycaw חדשות GetSpeakers מחזיר עטיפה; ההתקן הגולמי הוא _dev
speakers = getattr(device, "_dev", device)
print("    התקן: %s" % getattr(device, "FriendlyName", "?"))

vol = cast(speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
           POINTER(IAudioEndpointVolume))
print("--- כרטיס הקול ---")
print("    עוצמה ראשית: %d%%" % round(vol.GetMasterVolumeLevelScalar() * 100))
print("    מושתק: %s" % ("כן" if vol.GetMute() else "לא"))

meter = cast(speakers.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None),
             POINTER(IAudioMeterInformation))

sounds.ensure(config.sounds_dir())
path = os.path.join(config.sounds_dir(), "bell_classic.wav")

print()
print("--- שקט לפני ההשמעה ---")
baseline = max(meter.GetPeakValue() for _ in range(10))
print("    שיא ברקע: %.4f" % baseline)

print()
print("--- מנגנים דרך audio.play (אותו מסלול כמו האפליקציה) ---")
started = audio.play(path, duration=3, volume=90)
print("    play החזיר:", started)
peaks = []
for _ in range(30):
    time.sleep(0.1)
    peaks.append(meter.GetPeakValue())
audio.stop()

top = max(peaks)
heard = sum(1 for p in peaks if p > 0.02)
print("    שיא בזמן ההשמעה: %.4f" % top)
print("    דגימות עם צליל: %d מתוך %d" % (heard, len(peaks)))
print()
if top > max(0.02, baseline * 3):
    print("תוצאה: יוצא צליל מכרטיס הקול ✓")
    sys.exit(0)
print("תוצאה: אין פלט אודיו ✗")
sys.exit(1)
