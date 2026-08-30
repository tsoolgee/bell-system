# -*- coding: utf-8 -*-
"""שרת מקומי (127.0.0.1) שמגיש את ממשק הניהול ואת ה-API."""

import datetime
import io
import json
import mimetypes
import os
import posixpath
import re
import secrets
import shutil
import sys
import threading
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import audio, autostart, config, engine, jewcal, outdev, schedule, tts

MAX_UPLOAD = 25 * 1024 * 1024
ALLOWED_AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".wma", ".aac"}

_tokens = set()


def web_dir():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "web")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def _safe_name(name):
    name = os.path.basename(name or "sound")
    name = re.sub(r"[^\w֐-׿.\- ]+", "_", name).strip() or "sound"
    return name[:80]


def _unique_name(directory, name):
    stem, ext = os.path.splitext(name)
    candidate, i = name, 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = "%s_%d%s" % (stem, i, ext)
        i += 1
    return candidate


class Handler(BaseHTTPRequestHandler):
    server_version = "BellSystem"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # לא מזהמים את הקונסול

    # ---------- עזרי תגובה ----------

    def _send(self, code, body=b"", ctype="application/octet-stream", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _error(self, message, code=400):
        self._json({"ok": False, "error": message}, code)

    def _read_body(self):
        """נקרא פעם אחת לכל POST, לפני הניתוב.

        חובה לרוקן את הגוף גם עבור נתיבים שלא צריכים אותו: בחיבור
        keep-alive בייטים שלא נקראו נדבקים לתחילת הבקשה הבאה, והשרת
        מקבל שורת בקשה מעוותת כמו "{}GET /api/state".
        """
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            raise ValueError("file too large")
        return self.rfile.read(length) if length else b""

    def _body(self):
        return getattr(self, "_raw_body", b"")

    def _payload(self):
        raw = self._body()
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _authorized(self):
        if not config.settings().get("requirePin"):
            return True
        return self.headers.get("X-Bell-Token") in _tokens

    # ---------- ניתוב ----------

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                return self._api_get(path, query)
            return self._static(path)
        except Exception as exc:  # לעולם לא מפילים את השרת
            engine.log("שגיאת שרת: %r" % (exc,), "error")
            return self._error("שגיאה פנימית", 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        try:
            self._raw_body = self._read_body()
        except ValueError:
            self.close_connection = True  # הגוף לא רוקן, החיבור כבר לא אמין
            return self._error("הקובץ גדול מדי", 413)
        try:
            return self._api_post(path, query)
        except Exception as exc:
            engine.log("שגיאת שרת: %r" % (exc,), "error")
            return self._error("שגיאה פנימית", 500)

    # ---------- קבצים סטטיים ----------

    def _static(self, path):
        rel = posixpath.normpath(urllib.parse.unquote(path)).lstrip("/")
        if not rel or rel == ".":
            rel = "index.html"
        if rel.startswith(".."):
            return self._error("נתיב לא חוקי", 403)
        full = os.path.join(web_dir(), rel.replace("/", os.sep))
        if not os.path.isfile(full):
            return self._error("לא נמצא", 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or "javascript" in ctype:
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            return self._send(200, fh.read(), ctype)

    # ---------- API: קריאה ----------

    def _api_get(self, path, query):
        if path == "/api/state":
            return self._json(engine.status())
        if path == "/api/config":
            cfg = config.get()
            st = dict(cfg["settings"])
            st.pop("pinHash", None)
            st.pop("ttsApiKey", None)
            st["autostart"] = autostart.is_enabled()
            st["hasPin"] = bool(cfg["settings"].get("pinHash"))
            st["hasTtsKey"] = bool(cfg["settings"].get("ttsApiKey"))
            return self._json({
                "settings": st,
                "bells": cfg["bells"],
                "sounds": engine.all_sounds(),
                "holidayFlags": cfg["holidayFlags"],
                "holidayCatalog": [{"key": k, "name": he, "yomtov": yt}
                                   for k, he, yt in jewcal.HOLIDAY_CATALOG],
                "exceptions": cfg["exceptions"],
                "cities": [{"name": n, "lat": la, "lon": lo, "candle": c}
                           for n, la, lo, c in config.CITIES],
                "dataDir": config.data_dir(),
                "locked": bool(cfg["settings"].get("requirePin")) and not self._authorized(),
            })
        if path == "/api/log":
            return self._json({"entries": engine.recent_log()})
        if path == "/api/calendar":
            try:
                days = int(query.get("days", ["21"])[0])
            except ValueError:
                days = 21
            return self._json({"days": self._calendar_preview(days)})
        if path == "/api/tts":
            st = config.settings()
            return self._json({
                "provider": st.get("ttsProvider", "gemini"),
                "voice": st.get("ttsVoice", "Kore"),
                "sapiVoice": st.get("ttsSapiVoice", ""),
                "rate": st.get("ttsRate", 0),
                "hasKey": bool(st.get("ttsApiKey")),
                "geminiVoices": [{"id": v, "name": n} for v, n in tts.GEMINI_VOICES],
                "sapiVoices": tts.sapi_voices(),
            })
        if path == "/api/audio":
            st = config.settings()
            chosen = st.get("outputDevice") or ""
            data = outdev.info(chosen or None)
            data["devices"] = audio.available_devices()
            data["selected"] = chosen
            data["canChoose"] = bool(data["devices"])
            data["fellBack"] = audio.device_fell_back()
            return self._json(data)
        if path == "/api/backup":
            return self._backup()
        return self._error("לא נמצא", 404)

    def _calendar_preview(self, days=21):
        """תצוגה מקדימה: מה יקרה בכל אחד מהימים הקרובים."""
        st = config.settings()
        today = datetime.date.today()
        out = []
        for i in range(max(1, min(days, 120))):
            d = today + datetime.timedelta(days=i)
            noon = datetime.datetime.combine(d, datetime.time(12, 0)).astimezone()
            block = schedule.evaluate(noon, include_manual=False)
            dow = jewcal.weekday_index(d)
            row = {
                "date": d.strftime("%d/%m/%Y"),
                "weekday": jewcal.HEB_WEEKDAYS[dow],
                "hebrew": jewcal.hebrew_date_string(d),
                "holiday": jewcal.holiday_name_he(d, st.get("israel", True)),
                "blocked": block["blocked"],
                "reason": block["label"] if block["blocked"] else "",
                "bells": len(schedule.bells_for_day(d)),
            }
            if dow == 5:
                candle = schedule.candle_time(d, st)
                row["candle"] = candle.strftime("%H:%M") if candle else ""
            if dow == 6:
                hav = schedule.havdalah_time(d, st)
                row["havdalah"] = hav.strftime("%H:%M") if hav else ""
            out.append(row)
        return out

    def _backup(self):
        buf = io.BytesIO()
        cfg = config.snapshot()
        # סודות לא נוסעים בגיבוי
        cfg["settings"].pop("pinHash", None)
        cfg["settings"].pop("ttsApiKey", None)
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("config.json", json.dumps(cfg, ensure_ascii=False, indent=2))
            for snd in cfg.get("sounds", []):
                src = os.path.join(config.sounds_dir(), snd["file"])
                if os.path.exists(src):
                    zf.write(src, "sounds/" + snd["file"])
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
        name = "bell-backup-%s.zip" % stamp
        engine.log("נוצר גיבוי", "system")
        return self._send(200, buf.getvalue(), "application/zip",
                          {"Content-Disposition": "attachment; filename=\"%s\"" % name})

    # ---------- API: כתיבה ----------

    def _api_post(self, path, query):
        if path == "/api/login":
            pin = str(self._payload().get("pin", ""))
            if config.check_pin(pin):
                token = secrets.token_hex(16)
                _tokens.add(token)
                return self._json({"ok": True, "token": token})
            return self._error("קוד שגוי", 403)

        # פעולות שמותרות גם למשתמש רגיל
        if path == "/api/ring":
            data = self._payload()
            engine.ring(data.get("sound") or "bell_classic",
                        int(data.get("duration") or 5),
                        data.get("label") or "", manual=True)
            return self._json({"ok": True})
        if path == "/api/stop":
            audio.stop()
            return self._json({"ok": True})
        if path == "/api/audio/test":
            return self._audio_test()

        if not self._authorized():
            return self._error("נדרשת כניסת מנהל", 403)

        handlers = {
            "/api/settings": self._set_settings,
            "/api/pin": self._set_pin,
            "/api/mute": self._set_mute,
            "/api/power": self._set_power,
            "/api/bells/save": self._save_bell,
            "/api/bells/delete": self._delete_bell,
            "/api/bells/toggle": self._toggle_bell,
            "/api/bells/duplicate": self._duplicate_bell,
            "/api/holidays": self._set_holidays,
            "/api/exceptions/save": self._save_exception,
            "/api/exceptions/delete": self._delete_exception,
            "/api/sounds/delete": self._delete_sound,
            "/api/sounds/rename": self._rename_sound,
            "/api/autostart": self._set_autostart,
            "/api/tts/key": self._set_tts_key,
            "/api/tts/create": self._create_announcement,
        }
        if path in handlers:
            return handlers[path](self._payload())
        if path == "/api/sounds/upload":
            return self._upload_sound(query)
        if path == "/api/restore":
            return self._restore()
        return self._error("לא נמצא", 404)

    def _set_settings(self, data):
        st = config.settings()
        allowed = {"volume", "outputDevice", "city", "lat", "lon", "candleMinutes", "havdalahMode",
                   "havdalahMinutes", "havdalahDegrees", "shabbatEnabled", "holidaysAuto",
                   "israel", "erevChagStop", "startMinimized",
                   "ttsProvider", "ttsVoice", "ttsSapiVoice", "ttsRate"}
        for key, value in data.items():
            if key in allowed:
                st[key] = value
        config.save()
        engine.log("ההגדרות עודכנו", "system")
        return self._json({"ok": True})

    def _set_pin(self, data):
        st = config.settings()
        pin = str(data.get("pin") or "").strip()
        if pin:
            if not re.fullmatch(r"\d{4,10}", pin):
                return self._error("הקוד חייב להיות 4 עד 10 ספרות")
            st["pinHash"] = config.hash_pin(pin)
            st["requirePin"] = True
        else:
            st["pinHash"] = ""
            st["requirePin"] = False
        config.save()
        engine.log("קוד המנהל " + ("עודכן" if pin else "הוסר"), "system")
        return self._json({"ok": True})

    def _set_mute(self, data):
        st = config.settings()
        st["muted"] = bool(data.get("muted", not st.get("muted")))
        if st["muted"]:
            audio.stop()
        config.save()
        engine.log("השתקה כללית: " + ("פעילה" if st["muted"] else "בוטלה"), "system")
        engine.notify()
        return self._json({"ok": True, "muted": st["muted"]})

    def _set_power(self, data):
        st = config.settings()
        st["enabled"] = bool(data.get("enabled", not st.get("enabled")))
        if not st["enabled"]:
            audio.stop()
        config.save()
        engine.log("המערכת " + ("הופעלה" if st["enabled"] else "כובתה"), "system")
        engine.notify()
        return self._json({"ok": True, "enabled": st["enabled"]})

    def _save_bell(self, data):
        time_str = str(data.get("time") or "")
        if not re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", time_str):
            return self._error("שעה לא תקינה")
        try:
            days = sorted({int(x) for x in data.get("days") or [] if 0 <= int(x) <= 6})
        except (ValueError, TypeError):
            return self._error("ימים לא תקינים")
        if not days:
            return self._error("יש לבחור לפחות יום אחד")
        bells = config.get()["bells"]
        bell = {
            "id": data.get("id") or config.new_id(),
            "time": time_str,
            "label": (data.get("label") or "").strip()[:60],
            "sound": data.get("sound") or "bell_classic",
            "duration": max(1, min(120, int(data.get("duration") or 5))),
            "days": days,
            "enabled": bool(data.get("enabled", True)),
        }
        for i, existing in enumerate(bells):
            if existing["id"] == bell["id"]:
                bells[i] = bell
                break
        else:
            bells.append(bell)
        bells.sort(key=lambda b: b["time"])
        config.save()
        engine.log("נשמר צלצול %s %s" % (bell["time"], bell["label"]), "system")
        return self._json({"ok": True, "bell": bell})

    def _delete_bell(self, data):
        cfg = config.get()
        before = len(cfg["bells"])
        cfg["bells"] = [b for b in cfg["bells"] if b["id"] != data.get("id")]
        config.save()
        return self._json({"ok": before != len(cfg["bells"])})

    def _toggle_bell(self, data):
        for bell in config.get()["bells"]:
            if bell["id"] == data.get("id"):
                bell["enabled"] = not bell.get("enabled", True)
                config.save()
                return self._json({"ok": True, "enabled": bell["enabled"]})
        return self._error("צלצול לא נמצא", 404)

    def _duplicate_bell(self, data):
        bells = config.get()["bells"]
        for bell in bells:
            if bell["id"] == data.get("id"):
                clone = dict(bell)
                clone["id"] = config.new_id()
                clone["label"] = ((bell.get("label") or "צלצול") + " - עותק")[:60]
                bells.append(clone)
                bells.sort(key=lambda b: b["time"])
                config.save()
                return self._json({"ok": True, "bell": clone})
        return self._error("צלצול לא נמצא", 404)

    def _set_holidays(self, data):
        flags = config.get()["holidayFlags"]
        for key, value in (data.get("flags") or {}).items():
            if key in jewcal.HOLIDAY_HE:
                flags[key] = bool(value)
        config.save()
        return self._json({"ok": True})

    def _save_exception(self, data):
        exc = {
            "id": data.get("id") or config.new_id(),
            "name": (data.get("name") or "").strip()[:60] or "השבתה",
            "type": "hebrew" if data.get("type") == "hebrew" else "gregorian",
            "enabled": bool(data.get("enabled", True)),
        }
        if exc["type"] == "hebrew":
            try:
                exc["fromMonth"] = int(data["fromMonth"])
                exc["fromDay"] = int(data["fromDay"])
                exc["toMonth"] = int(data.get("toMonth") or data["fromMonth"])
                exc["toDay"] = int(data.get("toDay") or data["fromDay"])
            except (KeyError, ValueError, TypeError):
                return self._error("תאריך עברי לא תקין")
        else:
            try:
                exc["from"] = datetime.date.fromisoformat(data["from"]).isoformat()
                exc["to"] = datetime.date.fromisoformat(data.get("to") or data["from"]).isoformat()
            except (KeyError, ValueError, TypeError):
                return self._error("תאריך לא תקין")
            if exc["to"] < exc["from"]:
                return self._error("תאריך הסיום מוקדם מתאריך ההתחלה")
        items = config.get()["exceptions"]
        for i, existing in enumerate(items):
            if existing["id"] == exc["id"]:
                items[i] = exc
                break
        else:
            items.append(exc)
        config.save()
        return self._json({"ok": True, "exception": exc})

    def _delete_exception(self, data):
        cfg = config.get()
        cfg["exceptions"] = [e for e in cfg["exceptions"] if e["id"] != data.get("id")]
        config.save()
        return self._json({"ok": True})

    def _upload_sound(self, query):
        raw_name = urllib.parse.unquote(query.get("name", ["sound"])[0])
        ext = os.path.splitext(raw_name)[1].lower()
        if ext not in ALLOWED_AUDIO:
            return self._error("סוג קובץ לא נתמך. אפשר MP3, WAV, M4A, OGG")
        data = self._body()
        if not data:
            return self._error("הקובץ ריק")
        filename = _unique_name(config.sounds_dir(), _safe_name(raw_name))
        with open(os.path.join(config.sounds_dir(), filename), "wb") as fh:
            fh.write(data)
        snd = {"id": config.new_id(), "name": os.path.splitext(raw_name)[0][:50],
               "file": filename, "builtin": False}
        config.get()["sounds"].append(snd)
        config.save()
        engine.log("הועלה צליל: " + snd["name"], "system")
        return self._json({"ok": True, "sound": snd})

    def _rename_sound(self, data):
        for snd in config.get()["sounds"]:
            if snd["id"] == data.get("id"):
                snd["name"] = (data.get("name") or snd["name"]).strip()[:50]
                config.save()
                return self._json({"ok": True})
        return self._error("צליל לא נמצא", 404)

    def _delete_sound(self, data):
        cfg = config.get()
        target = [s for s in cfg["sounds"] if s["id"] == data.get("id")]
        if not target:
            return self._error("צליל לא נמצא", 404)
        used = [b for b in cfg["bells"] if b.get("sound") == data.get("id")]
        if used and not data.get("force"):
            return self._error("הצליל משמש %d צלצולים" % len(used))
        for bell in used:
            bell["sound"] = "bell_classic"
        try:
            os.remove(os.path.join(config.sounds_dir(), target[0]["file"]))
        except OSError:
            pass
        cfg["sounds"] = [s for s in cfg["sounds"] if s["id"] != data.get("id")]
        config.save()
        return self._json({"ok": True})

    def _audio_test(self):
        """בדיקת שמע אמיתית: מנגנת ומודדת את נקודת הקצה שאליה מנגנים."""
        chosen = config.settings().get("outputDevice") or ""
        started = engine.ring("bell_classic", 3, "בדיקת שמע", manual=True)
        # נמדוד את ההתקן שהנגן באמת פתח, לא את זה שביקשנו
        actual = audio.active_device() or ""
        peak = outdev.measure(2.5, actual or None)
        audio.stop()
        device = outdev.info(actual or None)
        result = {"ok": True, "started": started, "device": device,
                  "requested": chosen, "actual": actual,
                  "fellBack": audio.device_fell_back()}
        if peak is not None:
            result["peak"] = round(peak, 3)
            result["heard"] = peak > 0.02
        return self._json(result)

    def _set_tts_key(self, data):
        config.settings()["ttsApiKey"] = str(data.get("key") or "").strip()
        config.save()
        engine.log("מפתח הכרוז " + ("נשמר" if config.settings()["ttsApiKey"] else "הוסר"),
                   "system")
        return self._json({"ok": True, "hasKey": bool(config.settings()["ttsApiKey"])})

    def _create_announcement(self, data):
        """יוצר קובץ כרוז ומוסיף אותו לספריית הצלילים."""
        st = config.settings()
        provider = data.get("provider") or st.get("ttsProvider", "gemini")
        voice = data.get("voice") or (st.get("ttsSapiVoice") if provider == "sapi"
                                      else st.get("ttsVoice", "Kore"))
        text = data.get("text") or ""
        try:
            wav = tts.synthesize(text, provider=provider, voice=voice,
                                 api_key=st.get("ttsApiKey", ""),
                                 rate=int(st.get("ttsRate", 0)))
        except tts.TTSError as exc:
            engine.log("יצירת כרוז נכשלה: %s" % exc, "error")
            return self._error(str(exc))

        # זוכרים את הבחירה האחרונה כדי שלא יצטרכו לבחור כל פעם מחדש
        st["ttsProvider"] = provider
        if provider == "sapi":
            st["ttsSapiVoice"] = voice
        else:
            st["ttsVoice"] = voice

        label = (data.get("name") or "").strip() or ("כרוז: " + text.strip()[:28])
        filename = _unique_name(config.sounds_dir(), _safe_name(label) + ".wav")
        with open(os.path.join(config.sounds_dir(), filename), "wb") as fh:
            fh.write(wav)
        snd = {"id": config.new_id(), "name": label[:50], "file": filename,
               "builtin": False, "announcement": True}
        config.get()["sounds"].append(snd)
        config.save()
        engine.log("נוצר כרוז: " + snd["name"], "system")
        return self._json({"ok": True, "sound": snd})

    def _set_autostart(self, data):
        wanted = bool(data.get("enabled"))
        ok = autostart.set_enabled(wanted)
        config.settings()["autostart"] = autostart.is_enabled()
        config.save()
        return self._json({"ok": ok, "enabled": autostart.is_enabled()})

    def _restore(self):
        raw = self._body()
        if not raw:
            return self._error("לא התקבל קובץ")
        try:
            if raw[:2] == b"PK":
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    data = json.loads(zf.read("config.json").decode("utf-8"))
                    for item in zf.infolist():
                        if item.filename.startswith("sounds/") and not item.is_dir():
                            name = _safe_name(item.filename.split("/", 1)[1])
                            dest = os.path.join(config.sounds_dir(), name)
                            with zf.open(item) as src, open(dest, "wb") as out:
                                shutil.copyfileobj(src, out)
            else:
                data = json.loads(raw.decode("utf-8"))
        except (ValueError, KeyError, zipfile.BadZipFile, UnicodeDecodeError):
            return self._error("קובץ הגיבוי אינו תקין")
        keep = {k: config.settings().get(k)
                for k in ("pinHash", "port", "ttsApiKey")}
        config.replace(data)
        config.settings().update({k: v for k, v in keep.items() if v is not None})
        config.save()
        engine.log("שוחזר גיבוי", "system")
        return self._json({"ok": True})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start(port=None):
    """מרים את השרת על לוקאלהוסט בלבד. מחזיר (server, port)."""
    wanted = int(port or config.settings().get("port", 8730))
    last = None
    for candidate in [wanted] + [wanted + i for i in range(1, 12)]:
        try:
            httpd = Server(("127.0.0.1", candidate), Handler)
        except OSError as exc:
            last = exc
            continue
        threading.Thread(target=httpd.serve_forever, name="bell-http", daemon=True).start()
        if candidate != config.settings().get("port"):
            config.settings()["port"] = candidate
            config.save()
        engine.log("ממשק הניהול זמין בכתובת http://127.0.0.1:%d" % candidate, "system")
        return httpd, candidate
    raise OSError("לא נמצא פורט פנוי: %s" % last)
