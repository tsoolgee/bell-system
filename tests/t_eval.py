# -*- coding: utf-8 -*-
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import schedule, config

tests = ['2026-08-28T17:00', '2026-08-28T18:27', '2026-08-28T18:29', '2026-08-28T18:35',
         '2026-08-29T10:00', '2026-08-29T19:49', '2026-08-29T19:52', '2026-08-30T08:00',
         '2026-04-01T10:00', '2026-04-02T10:00', '2026-04-04T10:00',
         '2026-03-03T09:00', '2026-04-22T09:00', '2026-12-06T09:00']
for iso in tests:
    now = datetime.datetime.fromisoformat(iso).astimezone()
    r = schedule.evaluate(now)
    print(iso, '->', (r['reason'] or 'OK'), '|', r['label'], '|', r.get('until', ''))
