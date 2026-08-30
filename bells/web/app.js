/* ממשק הניהול של מערכת הצלצולים - עובד מול השרת המקומי בלבד */

const DAY_SHORT = ["א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "שבת"];
const DAY_LONG = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
const HEB_MONTHS = [
  [1, "ניסן"], [2, "אייר"], [3, "סיון"], [4, "תמוז"], [5, "אב"], [6, "אלול"],
  [7, "תשרי"], [8, "חשון"], [9, "כסלו"], [10, "טבת"], [11, "שבט"],
  [12, "אדר / אדר א׳"], [13, "אדר ב׳"]
];

const App = {
  cfg: null,
  state: null,
  activeDay: new Date().getDay(),
  token: sessionStorage.getItem("bellToken") || "",
  kiosk: false,

  /* ---------------- תשתית ---------------- */

  async api(path, options = {}) {
    const opts = Object.assign({ headers: {} }, options);
    if (this.token) opts.headers["X-Bell-Token"] = this.token;
    if (opts.json !== undefined) {
      opts.method = opts.method || "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.json);
      delete opts.json;
    }
    const res = await fetch(path, opts);
    if (res.status === 403) {
      this.openModal("loginModal");
      throw new Error("נדרשת כניסת מנהל");
    }
    const type = res.headers.get("Content-Type") || "";
    if (!type.includes("json")) return res;
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || "הפעולה נכשלה");
    return data;
  },

  toast(message, isError) {
    const el = document.getElementById("toast");
    el.textContent = message;
    el.className = "show" + (isError ? " err" : "");
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => { el.className = ""; }, 3200);
  },

  async guard(fn) {
    try { await fn(); } catch (err) { this.toast(err.message, true); }
  },

  openModal(id) { document.getElementById(id).classList.add("open"); },
  closeModal(id) { document.getElementById(id).classList.remove("open"); },

  show(view) {
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    document.getElementById("view-" + view).classList.add("active");
    document.querySelectorAll(".sidenav button").forEach(b =>
      b.classList.toggle("active", b.dataset.view === view));
    if (view === "calendar") this.loadPreview();
    if (view === "sounds") this.loadTts();
    if (view === "settings") this.loadLog();
  },

  esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g,
      c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  },

  /* ---------------- טעינה ---------------- */

  async boot() {
    this.buildStaticPickers();
    await this.loadConfig();
    await this.refresh();
    setInterval(() => this.refresh(), 1000);
    document.addEventListener("keydown", e => {
      if (e.key === "Escape") {
        if (this.kiosk) this.toggleKiosk();
        else document.querySelectorAll(".modal.open").forEach(m => m.classList.remove("open"));
      }
    });
  },

  async loadConfig() {
    this.cfg = await this.api("/api/config");
    this.renderBells();
    this.renderSounds();
    this.renderHolidays();
    this.renderExceptions();
    this.renderShabbatSettings();
    this.fillSettings();
    this.loadTts();
    this.loadAudioDevice();
  },

  async refresh() {
    try {
      this.state = await (await fetch("/api/state")).json();
    } catch (err) { return; }
    this.renderStatus();
    this.renderNext();
    this.renderToday();
    this.renderKiosk();
  },

  /* ---------------- מצב ותצוגה ראשית ---------------- */

  renderStatus() {
    const s = this.state;
    document.getElementById("hdrTime").textContent = s.time;
    document.getElementById("hdrDate").textContent = s.weekday + " · " + s.hebrewDate;

    const kind = !s.enabled ? "off"
      : s.muted ? "muted"
      : s.reason === "shabbat" ? "shabbat"
      : s.reason === "yomtov" ? "yomtov"
      : s.reason === "holiday" ? "holiday"
      : s.reason === "exception" ? "exception"
      : "ok";
    const titles = {
      off: "🔴 המערכת כבויה",
      muted: "🔇 הצלצולים מושתקים",
      shabbat: "🕯️ שבת — הצלצולים מושבתים",
      yomtov: "🕯️ " + s.statusLabel + " — הצלצולים מושבתים",
      holiday: "🟣 " + s.statusLabel + " — הצלצולים מושבתים",
      exception: "⏸️ " + s.statusLabel + " — הצלצולים מושבתים",
      ok: "🟢 המערכת פעילה"
    };
    const banner = document.getElementById("statusBanner");
    banner.className = "status " + kind;
    document.getElementById("statusTitle").textContent = titles[kind];
    let desc = s.weekday + " · " + s.date + " · " + s.hebrewDate;
    if (s.todayHoliday && kind === "ok") desc += " · " + s.todayHoliday;
    document.getElementById("statusDesc").textContent = desc;
    document.getElementById("statusMeta").innerHTML =
      s.blockedUntil && (kind === "shabbat" || kind === "yomtov")
        ? "חוזר לפעילות ב־<b>" + new Date(s.blockedUntil).toTimeString().slice(0, 5) + "</b>"
        : s.bellsToday === 1 ? "צלצול אחד מתוכנן היום"
        : s.bellsToday + " צלצולים מתוכננים היום";

    const muteBtn = document.getElementById("muteBtn");
    muteBtn.textContent = s.muted ? "🔇 צלצולים מושתקים — לחצו להפעלה" : "🔊 צלצולים פעילים";
    muteBtn.className = "btn big wide " + (s.muted ? "amber" : "green");

    if (s.shabbat) {
      const w = s.shabbat;
      document.getElementById("shabbatInfo").innerHTML =
        '<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:12px;font-size:13px">' +
        "<b>🕯️ " + this.esc(w.name) + " הקרובה</b><br>" +
        "כניסה: <b>" + w.start + "</b> (" + w.startDate + ") · יציאה: <b>" + w.end + "</b> (" + w.endDate + ")" +
        "</div>";
    }
  },

  renderNext() {
    const n = this.state.next;
    const box = document.getElementById("nextBell");
    if (!n) {
      box.innerHTML = '<div class="none">אין צלצולים מתוכננים</div>';
      return;
    }
    const total = Math.max(0, n.seconds);
    const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), sec = total % 60;
    const countdown = h > 0
      ? "בעוד " + h + " שעות ו־" + m + " דקות"
      : "בעוד " + String(m).padStart(2, "0") + ":" + String(sec).padStart(2, "0") + " דקות";
    box.innerHTML =
      '<div class="time">' + n.time + "</div>" +
      '<div class="label">' + this.esc(n.label) + "</div>" +
      '<div class="sound">🔔 ' + this.esc(n.sound) + (n.isToday ? "" : " · " + n.weekday + " " + n.date) + "</div>" +
      '<div class="countdown">' + countdown + "</div>";
  },

  renderToday() {
    if (!this.cfg) return;
    const today = new Date().getDay();
    document.getElementById("todayLabel").textContent = "יום " + DAY_LONG[today];
    const list = this.cfg.bells.filter(b => b.days.includes(today));
    const now = this.state ? this.state.time.slice(0, 5) : "00:00";
    document.getElementById("todayList").innerHTML = list.length
      ? list.map(b => {
          const past = b.time < now;
          return '<div class="bell-row' + (b.enabled ? "" : " off") + '" style="' + (past ? "opacity:.45" : "") + '">' +
            '<div class="t">' + b.time + "</div>" +
            '<div class="info"><b>' + this.esc(b.label || "צלצול") + "</b>" +
            "<small>🔔 " + this.esc(this.soundName(b.sound)) + " · " + b.duration + " שניות</small></div>" +
            (b.enabled ? (past ? '<span class="pill gray">הושמע</span>' : '<span class="pill blue">ממתין</span>')
                       : '<span class="pill red">מושבת</span>') +
            "</div>";
        }).join("")
      : '<div class="empty"><span class="big">😴</span>אין צלצולים ביום ' + DAY_LONG[today] + "</div>";
  },

  renderKiosk() {
    if (!this.kiosk) return;
    const s = this.state;
    document.getElementById("kClock").textContent = s.time.slice(0, 5);
    document.getElementById("kDate").textContent = s.weekday + " · " + s.date + " · " + s.hebrewDate;
    document.getElementById("kStatus").textContent =
      s.blocked ? "⛔ " + s.statusLabel : "🟢 המערכת פעילה";
    document.getElementById("kNext").innerHTML = s.next
      ? "הצלצול הבא: <b>" + s.next.time + "</b> · " + this.esc(s.next.label)
      : "אין צלצולים מתוכננים";
  },

  toggleKiosk() {
    this.kiosk = !this.kiosk;
    document.body.classList.toggle("kiosk", this.kiosk);
    if (this.kiosk) {
      if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {});
      this.renderKiosk();
    } else if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    }
  },

  /* ---------------- לוח צלצולים ---------------- */

  soundName(id) {
    const found = (this.cfg.sounds || []).find(s => s.id === id);
    return found ? found.name : "צליל";
  },

  buildStaticPickers() {
    document.getElementById("dayTabs").innerHTML = DAY_LONG.slice(0, 6).map((d, i) =>
      '<button data-day="' + i + '" onclick="App.pickDay(' + i + ')">יום ' + d + "</button>").join("") +
      '<button data-day="all" onclick="App.pickDay(\'all\')">כל השבוע</button>';
    document.getElementById("bellDays").innerHTML = DAY_SHORT.map((d, i) =>
      i === 6
        ? '<button type="button" class="shabbat" title="שבת אינה פעילה במערכת" disabled>' + d + "</button>"
        : '<button type="button" data-day="' + i + '" onclick="this.classList.toggle(\'on\')">' + d + "</button>"
    ).join("");
    const monthOptions = HEB_MONTHS.map(([n, name]) => '<option value="' + n + '">' + name + "</option>").join("");
    document.getElementById("excFromMonth").innerHTML = monthOptions;
    document.getElementById("excToMonth").innerHTML = monthOptions;
  },

  pickDay(day) {
    this.activeDay = day;
    this.renderBells();
  },

  renderBells() {
    if (!this.cfg) return;
    const day = this.activeDay === "all" ? "all" : Number(this.activeDay);
    document.querySelectorAll("#dayTabs button").forEach(b =>
      b.classList.toggle("on", b.dataset.day === String(day)));

    const list = this.cfg.bells.filter(b => day === "all" || b.days.includes(day));
    document.getElementById("bellsList").innerHTML = list.length
      ? list.map(b => this.bellRow(b)).join("")
      : '<div class="empty"><span class="big">🔔</span>אין צלצולים ' +
        (day === "all" ? "במערכת" : "ביום " + DAY_LONG[day]) + "<br><small>לחצו על „הוספת צלצול“ כדי להתחיל</small></div>";

    const rows = DAY_LONG.slice(0, 6).map((name, i) => {
      const bells = this.cfg.bells.filter(b => b.days.includes(i) && b.enabled);
      return "<tr><th style='white-space:nowrap'>יום " + name + "</th><td>" +
        (bells.length
          ? bells.map(b => '<span class="pill blue" style="margin:2px">' + b.time + " " + this.esc(b.label || "") + "</span>").join(" ")
          : '<span style="color:var(--muted)">—</span>') +
        "</td></tr>";
    }).join("");
    document.getElementById("weekTable").innerHTML =
      "<tr><th>יום</th><th>צלצולים</th></tr>" + rows +
      "<tr><th>שבת</th><td><span class='pill amber'>המערכת מושבתת מכניסת שבת ועד צאתה</span></td></tr>";
  },

  bellRow(b) {
    const days = b.days.map(d => DAY_SHORT[d]).join(" ");
    return '<div class="bell-row' + (b.enabled ? "" : " off") + '">' +
      '<div class="t">' + b.time + "</div>" +
      '<div class="info"><b>' + this.esc(b.label || "צלצול") + "</b>" +
      "<small>🔔 " + this.esc(this.soundName(b.sound)) + " · " + b.duration + " שניות · " + days + "</small></div>" +
      '<div class="acts">' +
      '<button onclick="App.previewBell(\'' + b.id + '\')">▶️ נגן</button>' +
      '<button onclick="App.editBell(\'' + b.id + '\')">✏️ ערוך</button>' +
      '<button onclick="App.duplicateBell(\'' + b.id + '\')">📋 שכפל</button>' +
      '<button onclick="App.toggleBell(\'' + b.id + '\')">' + (b.enabled ? "⏸️ השבת" : "▶️ הפעל") + "</button>" +
      '<button class="danger" onclick="App.deleteBell(\'' + b.id + '\')">🗑️ מחק</button>' +
      "</div></div>";
  },

  editBell(id) {
    const b = id ? this.cfg.bells.find(x => x.id === id) : null;
    document.getElementById("bellModalTitle").textContent = b ? "עריכת צלצול" : "הוספת צלצול";
    document.getElementById("bellId").value = b ? b.id : "";
    document.getElementById("bellTime").value = b ? b.time : "08:00";
    document.getElementById("bellLabel").value = b ? (b.label || "") : "";
    document.getElementById("bellDuration").value = b ? b.duration : 5;
    document.getElementById("bellEnabled").classList.toggle("on", b ? b.enabled : true);
    this.fillSoundSelect("bellSound", b ? b.sound : "bell_classic");
    const defaults = b ? b.days : (this.activeDay === "all" ? [0, 1, 2, 3, 4, 5] : [Number(this.activeDay)]);
    document.querySelectorAll("#bellDays button[data-day]").forEach(btn =>
      btn.classList.toggle("on", defaults.includes(Number(btn.dataset.day))));
    this.openModal("bellModal");
  },

  saveBell(event) {
    event.preventDefault();
    const days = [...document.querySelectorAll("#bellDays button.on")].map(b => Number(b.dataset.day));
    this.guard(async () => {
      await this.api("/api/bells/save", {
        json: {
          id: document.getElementById("bellId").value || null,
          time: document.getElementById("bellTime").value,
          label: document.getElementById("bellLabel").value,
          sound: document.getElementById("bellSound").value,
          duration: Number(document.getElementById("bellDuration").value),
          days: days,
          enabled: document.getElementById("bellEnabled").classList.contains("on")
        }
      });
      this.closeModal("bellModal");
      await this.loadConfig();
      this.toast("הצלצול נשמר");
    });
  },

  deleteBell(id) {
    const b = this.cfg.bells.find(x => x.id === id);
    if (!confirm("למחוק את הצלצול " + b.time + " " + (b.label || "") + "?")) return;
    this.guard(async () => {
      await this.api("/api/bells/delete", { json: { id } });
      await this.loadConfig();
      this.toast("הצלצול נמחק");
    });
  },

  toggleBell(id) {
    this.guard(async () => {
      await this.api("/api/bells/toggle", { json: { id } });
      await this.loadConfig();
    });
  },

  duplicateBell(id) {
    this.guard(async () => {
      const res = await this.api("/api/bells/duplicate", { json: { id } });
      await this.loadConfig();
      this.toast("שוכפל — ערכו את השעה");
      this.editBell(res.bell.id);
    });
  },

  previewBell(id) {
    const b = this.cfg.bells.find(x => x.id === id);
    this.guard(() => this.api("/api/ring", { json: { sound: b.sound, duration: Math.min(b.duration, 8) } }));
  },

  /* ---------------- צלילים ---------------- */

  fillSoundSelect(elementId, selected) {
    const el = document.getElementById(elementId);
    el.innerHTML = (this.cfg.sounds || []).map(s =>
      '<option value="' + s.id + '"' + (s.id === selected ? " selected" : "") + ">" + this.esc(s.name) + "</option>").join("");
  },

  renderSounds() {
    const list = this.cfg.sounds || [];
    document.getElementById("soundsList").innerHTML = list.map(s => {
      const used = this.cfg.bells.filter(b => b.sound === s.id).length;
      return '<div class="bell-row">' +
        '<div style="font-size:22px">' +
        (s.builtin ? "🔔" : s.announcement ? "📢" : "🎵") + "</div>" +
        '<div class="info"><b>' + this.esc(s.name) + "</b><small>" +
        (s.builtin ? "צליל מובנה" : s.announcement ? "כרוז מוקלט" : this.esc(s.file)) +
        (used ? " · בשימוש ב" + (used === 1 ? "צלצול אחד" : "־" + used + " צלצולים") : "") + "</small></div>" +
        '<div class="acts"><button onclick="App.previewSound(\'' + s.id + '\')">▶️ נגן</button>' +
        (s.builtin ? "" : '<button class="danger" onclick="App.deleteSound(\'' + s.id + '\')">🗑️ מחק</button>') +
        "</div></div>";
    }).join("");
  },

  previewSound(id) {
    this.guard(() => this.api("/api/ring", { json: { sound: id, duration: 5 } }));
  },

  previewSelected() {
    this.previewSound(document.getElementById("bellSound").value);
  },

  uploadSound(event) {
    const file = event.target.files[0];
    if (!file) return;
    event.target.value = "";
    this.guard(async () => {
      this.toast("מעלה " + file.name + "…");
      await this.api("/api/sounds/upload?name=" + encodeURIComponent(file.name),
        { method: "POST", body: file });
      await this.loadConfig();
      this.toast("הצליל נוסף לספרייה");
    });
  },

  deleteSound(id) {
    const used = this.cfg.bells.filter(b => b.sound === id).length;
    const name = this.soundName(id);
    let force = false;
    if (used) {
      if (!confirm("הצליל „" + name + "“ משמש " + used + " צלצולים.\nלמחוק בכל זאת? הצלצולים יעברו לצליל הרגיל.")) return;
      force = true;
    } else if (!confirm("למחוק את הצליל „" + name + "“?")) return;
    this.guard(async () => {
      await this.api("/api/sounds/delete", { json: { id, force } });
      await this.loadConfig();
      this.toast("הצליל נמחק");
    });
  },

  /* ---------------- כרוז ---------------- */

  async loadTts() {
    try {
      this.tts = await (await fetch("/api/tts")).json();
    } catch (err) { return; }
    document.getElementById("ttsProvider").value = this.tts.provider;
    document.getElementById("ttsKeyState").textContent = this.tts.hasKey
      ? "🔑 מפתח Gemini שמור — אפשר ליצור כרוז בעברית."
      : "⚠️ אין מפתח — כרגע זמינים רק קולות Windows שבמחשב.";
    this.ttsProviderChanged();
  },

  ttsProviderChanged() {
    if (!this.tts) return;
    const provider = document.getElementById("ttsProvider").value;
    const select = document.getElementById("ttsVoice");
    const notice = document.getElementById("ttsNotice");
    const button = document.getElementById("ttsCreateBtn");
    button.disabled = false;

    if (provider === "gemini") {
      select.innerHTML = this.tts.geminiVoices.map(v =>
        '<option value="' + v.id + '"' + (v.id === this.tts.voice ? " selected" : "") + ">" +
        this.esc(v.name) + "</option>").join("");
      notice.innerHTML = this.tts.hasKey
        ? '<div class="notice info">הטקסט יישלח ל־Google ליצירת ההקלטה, והקובץ יישמר במחשב. ' +
          "אחרי היצירה הכרוז עובד גם בלי אינטרנט.</div>"
        : '<div class="notice warn"><b>נדרש מפתח API.</b> קבלו מפתח חינם ב־Google AI Studio ' +
          "והזינו אותו במסך ההגדרות, או עברו לקולות Windows.</div>";
      button.disabled = !this.tts.hasKey;
      return;
    }

    const voices = this.tts.sapiVoices || [];
    select.innerHTML = voices.length
      ? voices.map(v => '<option value="' + this.esc(v.name) + '"' +
          (v.name === this.tts.sapiVoice ? " selected" : "") + ">" +
          this.esc(v.name) + " (" + this.esc(v.culture) + ")</option>").join("")
      : "<option value=''>לא נמצאו קולות</option>";
    const hebrew = voices.some(v => v.hebrew);
    notice.innerHTML = !voices.length
      ? '<div class="notice warn">לא נמצאו קולות Windows במחשב הזה.</div>'
      : hebrew
        ? '<div class="notice info">הכרוז ייווצר במחשב עצמו, בלי אינטרנט ובלי מפתח.</div>'
        : '<div class="notice warn"><b>אין קול עברי מותקן במחשב.</b> קול אנגלי יקריא טקסט ' +
          "עברי בצורה לא מובנת. להודעה בעברית השתמשו ב־Gemini, או התקינו קול עברי " +
          "דרך הגדרות Windows ← שעה ושפה ← דיבור.</div>";
    button.disabled = !voices.length;
  },

  createAnnouncement() {
    const text = document.getElementById("ttsText").value.trim();
    if (!text) { this.toast("נא להזין טקסט לכרוז", true); return; }
    const button = document.getElementById("ttsCreateBtn");
    button.classList.add("loading");
    button.textContent = "⏳ יוצר כרוז…";
    this.guard(async () => {
      try {
        const res = await this.api("/api/tts/create", {
          json: {
            text: text,
            provider: document.getElementById("ttsProvider").value,
            voice: document.getElementById("ttsVoice").value,
            name: document.getElementById("ttsName").value
          }
        });
        document.getElementById("ttsText").value = "";
        document.getElementById("ttsName").value = "";
        await this.loadConfig();
        this.toast("הכרוז נוסף לספריית הצלילים");
        this.previewSound(res.sound.id);
      } finally {
        button.classList.remove("loading");
        button.textContent = "📢 צור כרוז";
      }
    });
  },

  saveTtsKey() {
    const key = document.getElementById("setTtsKey").value.trim();
    this.guard(async () => {
      await this.api("/api/tts/key", { json: { key } });
      document.getElementById("setTtsKey").value = "";
      await this.loadTts();
      this.toast(key ? "המפתח נשמר" : "המפתח נמחק");
    });
  },

  /* ---------------- חגים והשבתות ---------------- */

  renderShabbatSettings() {
    const st = this.cfg.settings;
    document.getElementById("shabbatSettings").innerHTML =
      this.toggleRow("swShabbat", st.shabbatEnabled,
        "השבתה אוטומטית בשבת ויום טוב",
        "מכניסת שבת (" + st.candleMinutes + " דק׳ לפני השקיעה) ועד צאת השבת") +
      this.toggleRow("swHolidays", st.holidaysAuto,
        "זיהוי אוטומטי של חגים", "לפי הלוח העברי, בלי צורך לעדכן כל שנה") +
      this.toggleRow("swErev", st.erevChagStop,
        "השבתה בכל יום ערב חג", "לא רק מזמן כניסת החג אלא מתחילת היום") +
      '<div style="margin-top:14px;background:#eff6ff;border-radius:12px;padding:12px;font-size:13px;color:var(--slate)">' +
      "📍 המיקום הנוכחי: <b>" + this.esc(st.city) + "</b> — ניתן לשנות במסך ההגדרות.</div>";
    this.bindToggle("swShabbat", "shabbatEnabled");
    this.bindToggle("swHolidays", "holidaysAuto");
    this.bindToggle("swErev", "erevChagStop");
  },

  toggleRow(id, on, title, sub) {
    return '<div class="toggle"><div class="txt"><b>' + title + "</b><small>" + sub + "</small></div>" +
      '<div class="switch' + (on ? " on" : "") + '" id="' + id + '"></div></div>';
  },

  bindToggle(id, key) {
    document.getElementById(id).onclick = () => this.toggleSwitch(id, key);
  },

  toggleSwitch(id, key) {
    const el = document.getElementById(id);
    const next = !el.classList.contains("on");
    this.guard(async () => {
      await this.api("/api/settings", { json: { [key]: next } });
      el.classList.toggle("on", next);
      this.cfg.settings[key] = next;
      this.toast("ההגדרה עודכנה");
      if (document.getElementById("view-calendar").classList.contains("active")) this.loadPreview();
    });
  },

  renderHolidays() {
    document.getElementById("holidayFlags").innerHTML = this.cfg.holidayCatalog.map(h => {
      const on = !!this.cfg.holidayFlags[h.key];
      return '<div class="toggle"><div class="txt"><b>' + this.esc(h.name) + "</b><small>" +
        (h.yomtov ? "יום טוב — השבתה מכניסת החג עד צאתו" : "יום שלם") + "</small></div>" +
        '<div class="switch' + (on ? " on" : "") + '" onclick="App.toggleHoliday(this,\'' + h.key + '\')"></div></div>';
    }).join("");
  },

  toggleHoliday(el, key) {
    const next = !el.classList.contains("on");
    this.guard(async () => {
      await this.api("/api/holidays", { json: { flags: { [key]: next } } });
      el.classList.toggle("on", next);
      this.cfg.holidayFlags[key] = next;
      this.loadPreview();
    });
  },

  renderExceptions() {
    const list = this.cfg.exceptions || [];
    document.getElementById("exceptionsList").innerHTML = list.length
      ? list.map(e => {
          const when = e.type === "hebrew"
            ? e.fromDay + " " + this.monthName(e.fromMonth) + " – " + e.toDay + " " + this.monthName(e.toMonth) + " (כל שנה)"
            : this.dmy(e.from) + (e.to !== e.from ? " – " + this.dmy(e.to) : "");
          return '<div class="bell-row' + (e.enabled ? "" : " off") + '">' +
            '<div style="font-size:22px">' + (e.type === "hebrew" ? "✡️" : "📅") + "</div>" +
            '<div class="info"><b>' + this.esc(e.name) + "</b><small>" + when + "</small></div>" +
            '<div class="acts">' +
            '<button onclick="App.editException(\'' + e.id + '\')">✏️ ערוך</button>' +
            '<button class="danger" onclick="App.deleteException(\'' + e.id + '\')">🗑️ מחק</button>' +
            "</div></div>";
        }).join("")
      : '<div class="empty"><span class="big">📌</span>אין השבתות ידניות<br><small>למשל חופשת קיץ או יום עיון</small></div>';
  },

  monthName(n) {
    const found = HEB_MONTHS.find(m => m[0] === Number(n));
    return found ? found[1] : "";
  },

  dmy(iso) {
    if (!iso) return "";
    const [y, m, d] = iso.split("-");
    return d + "/" + m + "/" + y;
  },

  editException(id) {
    const e = id ? this.cfg.exceptions.find(x => x.id === id) : null;
    document.getElementById("excModalTitle").textContent = e ? "עריכת השבתה" : "הוספת השבתה";
    document.getElementById("excId").value = e ? e.id : "";
    document.getElementById("excName").value = e ? e.name : "";
    document.getElementById("excType").value = e ? e.type : "gregorian";
    const today = new Date().toISOString().slice(0, 10);
    document.getElementById("excFrom").value = e && e.from ? e.from : today;
    document.getElementById("excTo").value = e && e.to ? e.to : today;
    document.getElementById("excFromDay").value = e && e.fromDay ? e.fromDay : 1;
    document.getElementById("excToDay").value = e && e.toDay ? e.toDay : 1;
    document.getElementById("excFromMonth").value = e && e.fromMonth ? e.fromMonth : 1;
    document.getElementById("excToMonth").value = e && e.toMonth ? e.toMonth : 1;
    this.excTypeChanged();
    this.openModal("excModal");
  },

  excTypeChanged() {
    const hebrew = document.getElementById("excType").value === "hebrew";
    document.getElementById("excHeb").hidden = !hebrew;
    document.getElementById("excGreg").hidden = hebrew;
  },

  saveException(event) {
    event.preventDefault();
    const type = document.getElementById("excType").value;
    const payload = {
      id: document.getElementById("excId").value || null,
      name: document.getElementById("excName").value,
      type: type,
      enabled: true
    };
    if (type === "hebrew") {
      payload.fromDay = Number(document.getElementById("excFromDay").value);
      payload.fromMonth = Number(document.getElementById("excFromMonth").value);
      payload.toDay = Number(document.getElementById("excToDay").value);
      payload.toMonth = Number(document.getElementById("excToMonth").value);
    } else {
      payload.from = document.getElementById("excFrom").value;
      payload.to = document.getElementById("excTo").value;
    }
    this.guard(async () => {
      await this.api("/api/exceptions/save", { json: payload });
      this.closeModal("excModal");
      await this.loadConfig();
      this.loadPreview();
      this.toast("ההשבתה נשמרה");
    });
  },

  deleteException(id) {
    if (!confirm("למחוק את ההשבתה?")) return;
    this.guard(async () => {
      await this.api("/api/exceptions/delete", { json: { id } });
      await this.loadConfig();
      this.loadPreview();
    });
  },

  async loadPreview() {
    try {
      const data = await (await fetch("/api/calendar?days=30")).json();
      document.getElementById("previewTable").innerHTML =
        "<tr><th>תאריך</th><th>יום</th><th>תאריך עברי</th><th>ציון היום</th><th>מצב</th><th>צלצולים</th></tr>" +
        data.days.map(d => {
          const status = d.blocked
            ? '<span class="pill amber">⛔ ' + this.esc(d.reason) + "</span>"
            : '<span class="pill green">✓ פעיל</span>';
          const holiday = d.holiday ? '<span class="pill purple">' + this.esc(d.holiday) + "</span>" : "";
          let extra = "";
          if (d.candle) extra = ' <span class="pill blue">🕯️ ' + d.candle + "</span>";
          if (d.havdalah) extra = ' <span class="pill blue">✨ ' + d.havdalah + "</span>";
          return "<tr" + (d.blocked ? ' class="blocked"' : "") + "><td>" + d.date + "</td><td>" +
            d.weekday + "</td><td style='white-space:nowrap'>" + this.esc(d.hebrew) + extra + "</td><td>" +
            holiday + "</td><td>" + status + "</td><td>" +
            (d.blocked ? "—" : d.bells) + "</td></tr>";
        }).join("");
    } catch (err) { /* לא קריטי */ }
  },

  /* ---------------- הגדרות ---------------- */

  fillSettings() {
    const st = this.cfg.settings;
    document.getElementById("setCity").innerHTML = this.cfg.cities.map(c =>
      '<option value="' + this.esc(c.name) + '"' + (c.name === st.city ? " selected" : "") + ">" + this.esc(c.name) + "</option>").join("") +
      '<option value="__custom">מיקום מותאם אישית…</option>';
    document.getElementById("setLat").value = st.lat;
    document.getElementById("setLon").value = st.lon;
    document.getElementById("setCandle").value = st.candleMinutes;
    document.getElementById("setHavMode").value = st.havdalahMode;
    document.getElementById("setHavMin").value = st.havdalahMinutes;
    document.getElementById("setHavDeg").value = st.havdalahDegrees;
    document.getElementById("setVolume").value = st.volume;
    document.getElementById("volLabel").textContent = st.volume + "%";
    document.getElementById("dataDir").textContent = this.cfg.dataDir;
    document.getElementById("swAutostart").classList.toggle("on", st.autostart);
    document.getElementById("swMinimized").classList.toggle("on", st.startMinimized);
    document.getElementById("swPower").classList.toggle("on", st.enabled);
    document.getElementById("pinState").textContent = st.hasPin
      ? "🔐 נעילת מנהל פעילה."
      : "🔓 אין קוד מנהל — כל מי שפותח את המערכת יכול לשנות הגדרות.";
    this.havModeChanged();
  },

  havModeChanged() {
    const degrees = document.getElementById("setHavMode").value === "degrees";
    document.getElementById("havDegreesBox").hidden = !degrees;
    document.getElementById("havMinutesBox").hidden = degrees;
  },

  cityChanged() {
    const name = document.getElementById("setCity").value;
    const city = this.cfg.cities.find(c => c.name === name);
    if (!city) return;
    document.getElementById("setLat").value = city.lat;
    document.getElementById("setLon").value = city.lon;
    document.getElementById("setCandle").value = city.candle;
  },

  saveSettings() {
    this.guard(async () => {
      await this.api("/api/settings", {
        json: {
          city: document.getElementById("setCity").value,
          lat: Number(document.getElementById("setLat").value),
          lon: Number(document.getElementById("setLon").value),
          candleMinutes: Number(document.getElementById("setCandle").value),
          havdalahMode: document.getElementById("setHavMode").value,
          havdalahMinutes: Number(document.getElementById("setHavMin").value),
          havdalahDegrees: Number(document.getElementById("setHavDeg").value),
          volume: Number(document.getElementById("setVolume").value)
        }
      });
      await this.loadConfig();
      this.toast("ההגדרות נשמרו");
    });
  },

  savePin() {
    const pin = document.getElementById("setPin").value.trim();
    this.guard(async () => {
      await this.api("/api/pin", { json: { pin } });
      document.getElementById("setPin").value = "";
      await this.loadConfig();
      this.toast(pin ? "קוד המנהל נשמר" : "נעילת המנהל בוטלה");
    });
  },

  login(event) {
    event.preventDefault();
    const pin = document.getElementById("loginPin").value;
    this.guard(async () => {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin })
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "קוד שגוי");
      this.token = data.token;
      sessionStorage.setItem("bellToken", this.token);
      document.getElementById("loginPin").value = "";
      this.closeModal("loginModal");
      await this.loadConfig();
      this.toast("ברוכים הבאים");
    });
  },

  toggleAutostart() {
    const el = document.getElementById("swAutostart");
    const next = !el.classList.contains("on");
    this.guard(async () => {
      const res = await this.api("/api/autostart", { json: { enabled: next } });
      el.classList.toggle("on", res.enabled);
      this.toast(res.enabled ? "המערכת תעלה אוטומטית עם המחשב" : "ההפעלה האוטומטית בוטלה");
    });
  },

  togglePower() {
    const el = document.getElementById("swPower");
    const next = !el.classList.contains("on");
    this.guard(async () => {
      const res = await this.api("/api/power", { json: { enabled: next } });
      el.classList.toggle("on", res.enabled);
      this.toast(res.enabled ? "המערכת הופעלה" : "המערכת כובתה");
    });
  },

  toggleMute() {
    this.guard(async () => {
      const res = await this.api("/api/mute", { json: {} });
      this.toast(res.muted ? "הצלצולים הושתקו" : "הצלצולים חזרו לפעול");
      this.refresh();
    });
  },

  stopRinging() {
    this.guard(async () => {
      await this.api("/api/stop", { json: {} });
      this.toast("הצלצול נעצר");
    });
  },

  async loadAudioDevice() {
    let info;
    try {
      info = await (await fetch("/api/audio")).json();
    } catch (err) { return; }
    const box = document.getElementById("audioDevice");
    if (!info.available) { box.innerHTML = ""; return; }
    const problem = info.virtual || info.muted || info.volume < 20;
    let detail = "עוצמת ההתקן " + info.volume + "%";
    if (info.muted) detail += " · מושתק";
    box.innerHTML = '<div class="notice ' + (problem ? "warn" : "info") + '">' +
      (problem ? "⚠️ " : "🔈 ") + "הצליל יוצא אל <b>" + this.esc(info.name) + "</b><br>" + detail +
      (info.virtual
        ? "<br><b>זהו התקן וירטואלי, לא רמקולים.</b> אף אחד לא ישמע את הצלצולים. " +
          "שנו את התקן ברירת המחדל: לחיצה ימנית על סמל הרמקול בשורת המשימות ← " +
          "„הגדרות צליל“ ← בחירת הרמקולים."
        : "") +
      "</div>";
  },

  testSound() {
    const button = document.getElementById("audioTestBtn");
    const result = document.getElementById("audioTestResult");
    button.classList.add("loading");
    button.textContent = "⏳ בודק…";
    result.innerHTML = "";
    this.guard(async () => {
      try {
        const res = await this.api("/api/audio/test", { json: {} });
        await this.loadAudioDevice();
        if (res.heard === true) {
          result.innerHTML = '<div class="notice info" style="margin-top:12px">' +
            "✅ נמדד פלט שמע (שיא " + res.peak + "). אם לא שמעתם — בדקו את עוצמת הרמקולים עצמם.</div>";
        } else if (res.heard === false) {
          result.innerHTML = '<div class="notice warn" style="margin-top:12px">' +
            "❌ לא נמדד שום פלט שמע. הצלצול הופעל אבל שום צליל לא הגיע להתקן.</div>";
        } else {
          result.innerHTML = '<div class="notice info" style="margin-top:12px">' +
            (res.started ? "הצלצול הופעל." : "❌ הפעלת הצלצול נכשלה.") + "</div>";
        }
      } finally {
        button.classList.remove("loading");
        button.textContent = "▶️ בדיקת שמע";
      }
    });
  },

  openManual() {
    this.fillSoundSelect("manualSound", "bell_classic");
    this.openModal("manualModal");
  },

  ringNow() {
    this.guard(async () => {
      await this.api("/api/ring", {
        json: {
          sound: document.getElementById("manualSound").value,
          duration: Number(document.getElementById("manualDuration").value)
        }
      });
      this.closeModal("manualModal");
      this.toast("מצלצל…");
    });
  },

  /* ---------------- גיבוי ויומן ---------------- */

  backup() {
    window.location.href = "/api/backup";
    this.toast("הגיבוי יורד…");
  },

  restore(event) {
    const file = event.target.files[0];
    if (!file) return;
    event.target.value = "";
    if (!confirm("שחזור יחליף את כל הצלצולים וההגדרות הקיימים. להמשיך?")) return;
    this.guard(async () => {
      await this.api("/api/restore", { method: "POST", body: file });
      await this.loadConfig();
      this.toast("הגיבוי שוחזר בהצלחה");
    });
  },

  async loadLog() {
    try {
      const data = await (await fetch("/api/log")).json();
      document.getElementById("logList").innerHTML = data.entries.map(e =>
        '<div class="log-line ' + e.kind + '"><time>' + e.time.slice(11, 19) + "</time><span>" +
        this.esc(e.message) + "</span></div>").join("") ||
        '<div class="empty">היומן ריק</div>';
    } catch (err) { /* לא קריטי */ }
  }
};

App.boot();
