# -*- coding: utf-8 -*-
"""לוח עברי, חגים, וחישוב חלון הזמן של שבת/יום טוב."""

import datetime

from pyluach import dates

# חגים שהמערכת מזהה לבד. yomtov=True פירושו איסור מלאכה, ולכן
# ההשבתה שלו מחושבת לפי כניסה/יציאה אסטרונומית ולא לפי יום לועזי.
HOLIDAY_CATALOG = [
    ("Rosh Hashana",  "ראש השנה",     True),
    ("Yom Kippur",    "יום כיפור",     True),
    ("Succos",        "סוכות",         True),
    ("Shmini Atzeres", "שמיני עצרת / שמחת תורה", True),
    ("Pesach",        "פסח",           True),
    ("Shavuos",       "שבועות",        True),
    ("Chol HaMoed Pesach", "חול המועד פסח", False),
    ("Chol HaMoed Succos", "חול המועד סוכות", False),
    ("Chanuka",       "חנוכה",         False),
    ("Purim",         "פורים",         False),
    ("Shushan Purim", "שושן פורים",    False),
    ("Taanis Esther", "תענית אסתר",    False),
    ("Tzom Gedalia",  "צום גדליה",     False),
    ("10 of Teves",   "י' בטבת",       False),
    ("17 of Tamuz",   "י\"ז בתמוז",    False),
    ("9 of Av",       "ט' באב",        False),
    ("Tu B'shvat",    "ט\"ו בשבט",     False),
    ("Lag Ba'omer",   "ל\"ג בעומר",    False),
    ("Pesach Sheni",  "פסח שני",       False),
    ("Tu B'av",       "ט\"ו באב",      False),
    ("Yom HaShoah",   "יום השואה",     False),
    ("Yom HaZikaron", "יום הזיכרון",   False),
    ("Yom HaAtzmaut", "יום העצמאות",   False),
    ("Yom Yerushalayim", "יום ירושלים", False),
]

HOLIDAY_HE = {k: he for k, he, _ in HOLIDAY_CATALOG}
YOMTOV_KEYS = {k for k, _, yt in HOLIDAY_CATALOG if yt}

CHOL_HAMOED = {"Pesach": "Chol HaMoed Pesach", "Succos": "Chol HaMoed Succos"}

# ברירת מחדל: משביתים בימי איסור מלאכה ובחול המועד, ולא בשאר.
DEFAULT_HOLIDAY_FLAGS = {k: (k in YOMTOV_KEYS or k in CHOL_HAMOED.values())
                         for k, _, _ in HOLIDAY_CATALOG}

NISSAN, IYAR = 1, 2

HEB_WEEKDAYS = ["יום ראשון", "יום שני", "יום שלישי", "יום רביעי",
                "יום חמישי", "יום שישי", "שבת"]


def weekday_index(d):
    """0=ראשון ... 6=שבת (בניגוד ל-Python שמתחיל בשני)."""
    return (d.weekday() + 1) % 7


def hebrew_date_string(d):
    try:
        return dates.GregorianDate(d.year, d.month, d.day).to_heb().hebrew_date_string()
    except Exception:
        return ""


def _national_days(d):
    """ימי זיכרון ועצמאות, כולל כללי ההקדמה/דחייה שנהוגים בישראל."""
    hd = dates.GregorianDate(d.year, d.month, d.day).to_heb()
    day, dow = hd.day, weekday_index(d)
    if hd.month == NISSAN:
        # יום השואה - כ"ז בניסן. חל בשישי -> מוקדם לחמישי, חל בראשון -> נדחה לשני.
        if day == 27 and dow not in (5, 0):
            return "Yom HaShoah"
        if day == 26 and dow == 4:
            return "Yom HaShoah"
        if day == 28 and dow == 1:
            return "Yom HaShoah"
    if hd.month == IYAR:
        if day == 28:
            return "Yom Yerushalayim"
        # יום העצמאות - ה' באייר, עם הקדמה/דחייה כדי לא לפגוע בשבת.
        fifth_dow = weekday_index(dates.HebrewDate(hd.year, IYAR, 5).to_pydate())
        atzmaut = {6: 3, 5: 4, 1: 6}.get(fifth_dow, 5)
        if day == atzmaut:
            return "Yom HaAtzmaut"
        if day == atzmaut - 1:
            return "Yom HaZikaron"
    return None


def holiday_key(d, israel=True):
    """שם החג (מפתח אנגלי יציב) של תאריך לועזי, או None.

    ימי חול המועד מקבלים מפתח נפרד, כדי שאפשר יהיה להשבית אותם
    בנפרד מימי היום טוב עצמם.
    """
    hd = dates.GregorianDate(d.year, d.month, d.day).to_heb()
    key = hd.holiday(israel=israel)
    if key:
        if key in CHOL_HAMOED and hd.festival(israel=israel, include_working_days=False) is None:
            return CHOL_HAMOED[key]
        return key
    return _national_days(d)


def holiday_name_he(d, israel=True):
    key = holiday_key(d, israel)
    return HOLIDAY_HE.get(key, key) if key else None


def is_yomtov(d, israel=True):
    """האם התאריך הוא יום טוב שאסור בעשיית מלאכה."""
    hd = dates.GregorianDate(d.year, d.month, d.day).to_heb()
    return hd.festival(israel=israel, include_working_days=False) is not None


def yomtov_name_he(d, israel=True):
    hd = dates.GregorianDate(d.year, d.month, d.day).to_heb()
    key = hd.festival(israel=israel, include_working_days=False)
    return HOLIDAY_HE.get(key, key) if key else None
