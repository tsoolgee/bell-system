# -*- coding: utf-8 -*-
"""הגברה מעל 100%.

שלוש הבטחות שחייבות להחזיק:

* הגברה לא שוברת את הצליל - הפלט לעולם לא חורג מטווח 16 ביט, כי דגימה
  שחורגת מתהפכת ונשמעת כרעש מרוסק ולא כצלצול חזק.
* הגברה באמת מגבירה - ה-RMS עולה, וזה מה שהאוזן שומעת. השיא כבר בתקרה
  ולא יעלה, ולכן דווקא הוא לא יכול לשמש עדות.
* הגברה מהירה - היא קורית ברגע שהצלצול מתחיל. חצי שנייה כאן היא חצי
  שנייה שבה הצלצול מאחר.
"""
import array
import math
import os
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import config, gain, sounds  # noqa: E402

fails = []


def check(name, condition, detail=""):
    print(("  OK  " if condition else " FAIL ") + name +
          ("  -> " + repr(detail) if not condition else ""))
    if not condition:
        fails.append(name)


def pcm(values):
    return array.array("h", values).tobytes()


def samples(raw):
    out = array.array("h")
    out.frombytes(raw)
    return out


print("--- טווח העוצמה ---")
check("מקסימום 200", gain.MAX_PERCENT == 200)
check("מעל המקסימום נחתך", gain.clamp(500) == 200)
check("שלילי נחתך לאפס", gain.clamp(-20) == 0)
check("מחרוזת מספרית מתקבלת", gain.clamp("150") == 150)
check("ערך לא מספרי חוזר לברירת המחדל", gain.clamp("חזק") == 100, gain.clamp("חזק"))
check("None חוזר לברירת המחדל", gain.clamp(None) == 100)
check("שבר מעוגל", gain.clamp(149.6) == 150)

print("--- עקומת ההגברה ---")
check("אפס נשאר אפס", gain.curve(0.0, 2.0) == 0.0)
check("מתחת לברך ההגברה לינארית",
      abs(gain.curve(0.2, 1.5) - 0.3) < 1e-9, gain.curve(0.2, 1.5))
check("לא חורג מ-1 גם בהגברה קיצונית",
      all(abs(gain.curve(x / 100.0, 2.0)) <= 1.0 for x in range(-100, 101)))
check("שומר על הסימן", gain.curve(-0.5, 2.0) < 0)
check("מונוטוני עולה",
      all(gain.curve(x / 200.0, 1.8) <= gain.curve((x + 1) / 200.0, 1.8)
          for x in range(-200, 200)))

print("--- טבלת התרגום ---")
table = gain.table(1.5)
check("65536 ערכים", len(table) == 65536)
check("אפס מתורגם לאפס", table[0] == 0)
check("הדגימה המקסימלית לא עוברת את הגבול", table[32767] <= 32767, table[32767])
check("אינדוקס שלילי מגיע לדגימות השליליות", table[-1] < 0, table[-1])
check("הדגימה המינימלית בטווח", table[-32768] >= -32768, table[-32768])
check("הטבלה נשמרת במטמון", gain.table(1.5) is table)

print("--- הגברת בלוק ---")
quiet = pcm([int(9000 * math.sin(i * 0.07)) for i in range(20000)])
check("100% מחזיר את המקור כמו שהוא", gain.apply_pcm16(quiet, 100) is quiet)
check("מתחת ל-100% לא נוגעים", gain.apply_pcm16(quiet, 60) is quiet)
loud = gain.apply_pcm16(quiet, 180)
check("האורך נשמר", len(loud) == len(quiet))
check("העוצמה עלתה", gain.rms_pcm16(loud) > gain.rms_pcm16(quiet) * 1.5,
      (gain.rms_pcm16(quiet), gain.rms_pcm16(loud)))
check("שום דגימה לא חרגה מהטווח",
      max(samples(loud)) <= 32767 and min(samples(loud)) >= -32768)
check("בלוק ריק לא מפיל", gain.apply_pcm16(b"", 200) == b"")
check("בייט עודף לא נאבד", len(gain.apply_pcm16(quiet + b"\x01", 200)) == len(quiet) + 1)

print("--- צליל שכבר בתקרה ---")
full = pcm([int(32000 * math.sin(i * 0.07)) for i in range(20000)])
boosted = gain.apply_pcm16(full, 200)
check("השיא לא חורג", gain.peak_pcm16(boosted) <= 1.0, gain.peak_pcm16(boosted))
check("העוצמה בכל זאת עלתה", gain.rms_pcm16(boosted) > gain.rms_pcm16(full),
      (gain.rms_pcm16(full), gain.rms_pcm16(boosted)))

print("--- דציבלים ---")
check("פי שניים הם 6 dB", abs(gain.db(2, 1) - 6.02) < 0.02, gain.db(2, 1))
check("ללא שינוי - אפס", gain.db(1, 1) == 0)
check("אפס לא מפיל", gain.db(0, 1) is None and gain.db(1, 0) is None)

print("--- על צליל אמיתי ---")
sounds.ensure(config.sounds_dir())
path = os.path.join(config.sounds_dir(), "bell_classic.wav")
check("100% אינו הגברה", gain.expected_db(path, 100) == 0.0)
value = gain.expected_db(path, 200)
check("200% מוסיף לפחות 2 dB", value and value >= 2.0, value)
check("150% מוסיף פחות מ-200%", gain.expected_db(path, 150) < value)

print("--- קובץ מוגבר למנוע שאין לו זיכרון (MCI) ---")
check("עד 100% אין קובץ", gain.amplified_file(path, 100) is None)
target = gain.amplified_file(path, 170)
check("נוצר קובץ", bool(target) and os.path.exists(target), target)
if target:
    with wave.open(path, "rb") as src, wave.open(target, "rb") as dst:
        check("אותו קצב דגימה", src.getframerate() == dst.getframerate())
        check("אותו מספר ערוצים", src.getnchannels() == dst.getnchannels())
        check("אותו מספר פריימים", src.getnframes() == dst.getnframes())
        check("הקובץ המוגבר חזק יותר",
              gain.rms_pcm16(dst.readframes(dst.getnframes())) >
              gain.rms_pcm16(src.readframes(src.getnframes())))
    check("הקובץ נשמר במטמון", gain.amplified_file(path, 170) == target)

print("--- מהירות ---")
big = pcm([int(20000 * math.sin(i * 0.05)) for i in range(44100 * 2 * 5)])
gain.table(1.9)          # הטבלה נבנית פעם אחת, לא בכל צלצול
start = time.time()
gain.apply_pcm16(big, 190)
elapsed = time.time() - start
print("       חמש שניות סטריאו הוגברו ב-%.3f שניות" % elapsed)
check("הגברה מהירה מספיק כדי לא לאחר צלצול", elapsed < 1.0, elapsed)

print()
print("נכשלו: %d" % len(fails))
sys.exit(1 if fails else 0)
