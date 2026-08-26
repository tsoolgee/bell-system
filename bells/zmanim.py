# -*- coding: utf-8 -*-
"""חישוב זמני שקיעה/זריחה מקומי (NOAA) - ללא תלות באינטרנט."""

import datetime
import math

# זווית השמש לשקיעה גיאומטרית כולל שבירת אור ורדיוס השמש
SUNSET_ZENITH = 90.833


def _julian_day(d):
    y, m, day = d.year, d.month, d.day
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + day + b - 1524.5


def _jcent(jd):
    return (jd - 2451545.0) / 36525.0


def _geom_mean_long_sun(t):
    return (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360.0


def _geom_mean_anom_sun(t):
    return 357.52911 + t * (35999.05029 - 0.0001537 * t)


def _eccent_earth_orbit(t):
    return 0.016708634 - t * (0.000042037 + 0.0000001267 * t)


def _sun_eq_of_center(t):
    m = math.radians(_geom_mean_anom_sun(t))
    return (math.sin(m) * (1.914602 - t * (0.004817 + 0.000014 * t))
            + math.sin(2 * m) * (0.019993 - 0.000101 * t)
            + math.sin(3 * m) * 0.000289)


def _sun_apparent_long(t):
    o = _geom_mean_long_sun(t) + _sun_eq_of_center(t)
    omega = 125.04 - 1934.136 * t
    return o - 0.00569 - 0.00478 * math.sin(math.radians(omega))


def _obliquity_corrected(t):
    seconds = 21.448 - t * (46.8150 + t * (0.00059 - t * 0.001813))
    e0 = 23.0 + (26.0 + seconds / 60.0) / 60.0
    omega = 125.04 - 1934.136 * t
    return e0 + 0.00256 * math.cos(math.radians(omega))


def _sun_declination(t):
    e = math.radians(_obliquity_corrected(t))
    lam = math.radians(_sun_apparent_long(t))
    return math.degrees(math.asin(math.sin(e) * math.sin(lam)))


def _equation_of_time(t):
    """הפרש בין זמן שמש אמיתי לממוצע, בדקות."""
    epsilon = _obliquity_corrected(t)
    l0 = _geom_mean_long_sun(t)
    e = _eccent_earth_orbit(t)
    m = _geom_mean_anom_sun(t)
    y = math.tan(math.radians(epsilon) / 2.0) ** 2
    l0r, mr = math.radians(l0), math.radians(m)
    etime = (y * math.sin(2 * l0r)
             - 2 * e * math.sin(mr)
             + 4 * e * y * math.sin(mr) * math.cos(2 * l0r)
             - 0.5 * y * y * math.sin(4 * l0r)
             - 1.25 * e * e * math.sin(2 * mr))
    return math.degrees(etime) * 4.0


def _hour_angle_deg(lat, decl, zenith):
    latr, decr = math.radians(lat), math.radians(decl)
    cos_h = (math.cos(math.radians(zenith)) / (math.cos(latr) * math.cos(decr))
             - math.tan(latr) * math.tan(decr))
    if cos_h > 1.0 or cos_h < -1.0:
        return None  # השמש לא חוצה את הזווית הזו ביום הזה
    return math.degrees(math.acos(cos_h))


def solar_event(date, lat, lon, zenith=SUNSET_ZENITH, rising=False):
    """מחזיר datetime מקומי (aware) של אירוע השמש, או None אם אינו קיים.

    lon חיובי מזרחה, lat חיובי צפונה.
    """
    jd = _julian_day(date)
    minutes = None
    for _ in range(2):  # ריצת דיוק שנייה סביב הזמן המשוער
        t = _jcent(jd if minutes is None else jd + minutes / 1440.0)
        eq = _equation_of_time(t)
        decl = _sun_declination(t)
        ha = _hour_angle_deg(lat, decl, zenith)
        if ha is None:
            return None
        noon = 720.0 - 4.0 * lon - eq
        minutes = noon - 4.0 * ha if rising else noon + 4.0 * ha
    base = datetime.datetime(date.year, date.month, date.day, tzinfo=datetime.timezone.utc)
    return (base + datetime.timedelta(minutes=minutes)).astimezone()


def sunset(date, lat, lon):
    return solar_event(date, lat, lon, SUNSET_ZENITH, rising=False)


def sunrise(date, lat, lon):
    return solar_event(date, lat, lon, SUNSET_ZENITH, rising=True)


def dusk_degrees(date, lat, lon, degrees_below):
    """צאת הכוכבים לפי מספר מעלות מתחת לאופק (לדוגמה 8.5)."""
    return solar_event(date, lat, lon, 90.0 + degrees_below, rising=False)
