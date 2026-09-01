# -*- coding: utf-8 -*-
"""האם Windows מנמיך דווקא את האפליקציה שלנו במיקסר?"""
import sys

try:
    from pycaw.pycaw import AudioUtilities
except ImportError as exc:
    print("דילוג: pycaw לא זמין (%s)" % exc)
    sys.exit(0)

print("%-34s %8s %8s" % ("אפליקציה", "עוצמה", "מושתק"))
for session in AudioUtilities.GetAllSessions():
    if not session.Process:
        name = "(צלילי מערכת)"
    else:
        name = session.Process.name()
    vol = session.SimpleAudioVolume
    mark = "  <-- מערכת הצלצולים" if "צלצול" in name or "BellSystem" in name else ""
    print("%-34s %7d%% %8s%s" % (name[:34], round(vol.GetMasterVolume() * 100),
                                 "כן" if vol.GetMute() else "לא", mark))
