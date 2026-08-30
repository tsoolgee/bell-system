# -*- coding: utf-8 -*-
"""איזה התקן MCI מאפשר שליטה בעוצמה עבור WAV?"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import audio, config  # noqa: E402

path = os.path.join(config.sounds_dir(), "bell_classic.wav")

for kind in ("(auto)", "waveaudio", "mpegvideo"):
    alias = "probe"
    audio._send("close %s" % alias)
    cmd = ('open "%s" alias %s' % (path, alias) if kind == "(auto)"
           else 'open "%s" type %s alias %s' % (path, kind, alias))
    err, _ = audio._send(cmd)
    if err:
        print("%-12s open FAILED err=%s" % (kind, err))
        continue
    e1, _ = audio._send("setaudio %s volume to 300" % alias)
    e2, v = audio._send("status %s volume" % alias)
    e3, length = audio._send("status %s length" % alias)
    print("%-12s open=ok  setaudio_err=%-4s status_volume=%-5s(err=%s)  length=%s"
          % (kind, e1, v or "-", e2, length))
    audio._send("close %s" % alias)
