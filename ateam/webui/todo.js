/* Tab ✅ To-do — quản lý việc của riêng dự án: tag, hạn, ưu tiên, mô tả. Server lưu ngoài repo (ateam/todos.py) và
   gửi danh sách trong ảnh chụp trạng thái (S.state.todos / tags / notes), nên mọi tab trình duyệt thấy cùng một dữ
   liệu. Ô thêm nhanh hiểu "#tag !cao @mai 17:00" (bóc giống todos.parse_quick, server bóc lại khi lưu). TD là phần
   dùng chung với notes.js: tag, popup chọn hạn, popup Quản lý tag. */
"use strict";

window.TD = (() => {
  const PALETTE = ["#f07178", "#f0a070", "#e6b84d", "#8fd16a", "#7dd3c0", "#22d3ee", "#8ec8ff", "#a78bfa", "#f0a0c8",
    "#c4b5fd", "#a3a094", "#e8e6dc"];
  const tags = () => (S.state && S.state.tags) || [];
  const tagById = (id) => tags().find((x) => x.id === id);
  const pad = (n) => String(n).padStart(2, "0");
  const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const addDays = (d, n) => { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); x.setDate(x.getDate() + n); return x; };
  const wd = (d) => (d.getDay() + 6) % 7;  // thứ Hai = 0
  const WD = () => t("wd_short").split(" ");

  function normTag(s) {
    return String(s || "").normalize("NFC").trim().replace(/^#+/, "").toLowerCase().replace(/[\s,;#]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 32);
  }
  const ascii = (s) => s.toLowerCase().replace(/\u0111/g, "d").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[-_]/g, "");
  const TIME_RE = /^(\d{1,2})(?::(\d{2})|h(\d{2})?|(am|pm))$/i;
  const WEEKDAYS = { t2: 0, thu2: 0, mon: 0, t3: 1, thu3: 1, tue: 1, t4: 2, thu4: 2, wed: 2, t5: 3, thu5: 3, thu: 3,
    t6: 4, thu6: 4, fri: 4, t7: 5, thu7: 5, sat: 5, cn: 6, chunhat: 6, sun: 6 };
  const PRI_WORDS = { thap: 1, low: 1, vua: 2, med: 2, medium: 2, cao: 3, high: 3, 1: 1, 2: 2, 3: 3 };
  function parseTime(w) {
    const m = TIME_RE.exec(String(w || "").trim());
    if (!m) return null;
    let h = +m[1]; const mi = +(m[2] || m[3] || 0), ap = (m[4] || "").toLowerCase();
    if (ap === "pm" && h < 12) h += 12;
    if (ap === "am" && h === 12) h = 0;
    return h < 24 && mi < 60 ? [h, mi] : null;
  }
  function parseDate(word, today) {
    const w = ascii(word.trim()), raw = word.trim().toLowerCase();
    if (["homnay", "nay", "today"].includes(w)) return today;
    if (["mai", "ngaymai", "tomorrow", "tmr"].includes(w)) return addDays(today, 1);
    if (["mot", "ngaymot", "kia"].includes(w)) return addDays(today, 2);
    if (["tuansau", "nextweek"].includes(w)) return addDays(today, 7 - wd(today));
    if (["cuoituan", "weekend"].includes(w)) return addDays(today, (5 - wd(today) + 7) % 7);
    if (w in WEEKDAYS) return addDays(today, (WEEKDAYS[w] - wd(today) + 7) % 7);
    let m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(raw);
    const mk = (y, mo, d) => { const x = new Date(y, mo - 1, d); return x.getMonth() === mo - 1 && x.getDate() === d ? x : null; };
    if (m) return mk(+m[1], +m[2], +m[3]);
    m = /^(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?$/.exec(raw);
    if (!m) return null;
    let y = m[3] ? +m[3] : today.getFullYear();
    if (y < 100) y += 2000;
    let d = mk(y, +m[2], +m[1]);
    if (d && !m[3] && d < addDays(today, -60)) d = mk(y + 1, +m[2], +m[1]);  // 5/1 gõ vào tháng 10: năm sau
    return d;
  }
  /* "mai 17:00" / "t6" / "17h" / "" -> hạn ("" = bỏ hạn), null nếu không hiểu — như todos.parse_due */
  function parseDue(text) {
    const words = String(text || "").trim().replace(/^@/, "").split(/\s+/).filter(Boolean);
    if (!words.length) return "";
    if (words.length === 1 && /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/.test(words[0])) return words[0];
    const now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    let day = parseDate(words[0], today);
    const rest = day ? words.slice(1) : words;
    const hm = rest.length ? parseTime(rest[0]) : null;
    if ((rest.length && !hm) || rest.length > 1) return null;
    day = day || today;
    return ymd(day) + (hm ? `T${pad(hm[0])}:${pad(hm[1])}` : "");
  }
  /* chia ô thêm nhanh thành từng từ có loại (tag / pri / due / chữ thường) — dùng cho tô màu lẫn kết quả bóc */
  function quickTokens(text) {
    const parts = String(text || "").split(/(\s+)/), out = [];
    for (let i = 0; i < parts.length; i++) {
      const w = parts[i];
      if (!w || /^\s+$/.test(w)) { out.push({ s: w, k: "sp" }); continue; }
      if (w.length > 1 && w[0] === "#" && /\p{L}/u.test(w.slice(1)) && normTag(w)) out.push({ s: w, k: "tag", v: normTag(w) });
      else if (/^!{1,3}$/.test(w)) out.push({ s: w, k: "pri", v: w.length });
      else if (w[0] === "!" && ascii(w.slice(1)) in PRI_WORDS) out.push({ s: w, k: "pri", v: PRI_WORDS[ascii(w.slice(1))] });
      else if (w.length > 1 && w[0] === "@") {
        const nxt = parts[i + 2] || "";
        const two = nxt && parseTime(nxt) ? parseDue(w + " " + nxt) : null;
        const one = two || parseDue(w);
        if (one) {
          out.push({ s: w, k: "due", v: one });
          if (two) { out.push({ s: parts[i + 1], k: "sp" }, { s: nxt, k: "due", v: one, cont: true }); i += 2; }
        } else out.push({ s: w, k: "" });
      } else out.push({ s: w, k: "" });
    }
    return out;
  }
  function parseQuick(text) {
    const toks = quickTokens(text), words = [], tg = [];
    let due = null, pri = null;
    for (const x of toks) {
      if (x.k === "tag") { if (!tg.includes(x.v)) tg.push(x.v); } else if (x.k === "pri") pri = x.v;
      else if (x.k === "due") due = x.v;
      else if (x.k === "") words.push(x.s);
    }
    return { text: words.join(" "), tags: tg, due, priority: pri };
  }

  /* hạn -> {date, hm}; nhóm theo hạn như todos.bucket */
  function dueParts(due) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?$/.exec(due || "");
    return m ? { date: new Date(+m[1], +m[2] - 1, +m[3]), hm: m[4] ? [+m[4], +m[5]] : null } : null;
  }
  function bucket(x) {
    if (x.done) return "done";
    const p = dueParts(x.due);
    if (!p) return "none";
    const now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const d = p.date;
    if (d < today || (+d === +today && p.hm && p.hm[0] * 60 + p.hm[1] < now.getHours() * 60 + now.getMinutes())) return "over";
    if (+d === +today) return "today";
    if (d <= addDays(today, 6 - wd(today))) return "week";
    return "later";
  }
  function dayLabel(d) { return `${WD()[wd(d)]} ${pad(d.getDate())}/${pad(d.getMonth() + 1)}`; }
  /* nhãn hạn ngắn cho hàng việc: {text, cls} — cls: over · today · wk · "" */
  function dueLabel(x) {
    const p = dueParts(x.due);
    if (!p) return { text: "", cls: "" };
    const b = x.done ? "" : bucket(x), now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const hm = p.hm ? `${pad(p.hm[0])}:${pad(p.hm[1])}` : "";
    const days = Math.round((today - p.date) / 864e5);
    let s;
    if (days === 0) s = t("due_today") + (hm ? " " + hm : "");
    else if (days === -1) s = t("due_tomorrow") + (hm ? " " + hm : "");
    else if (b === "over" && days <= 3) s = t("due_over_days", { n: days });
    else s = dayLabel(p.date) + (hm ? " " + hm : "");
    return { text: (b === "over" ? "⏰ " : "") + s, cls: b === "over" ? "over" : b === "today" ? "today" : b === "week" ? "wk" : "" };
  }
  function dueLong(due) {
    const p = dueParts(due);
    if (!p) return t("no_due");
    const now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const days = Math.round((p.date - today) / 864e5);
    const head = days === 0 ? t("q_today") + ", " : days === 1 ? t("q_tomorrow") + ", " : "";
    return head + dayLabel(p.date) + (p.hm ? ` · ${pad(p.hm[0])}:${pad(p.hm[1])}` : "");
  }
  function when(ts) {
    if (!ts) return "";
    const d = new Date(ts * 1000), n = new Date();
    const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    return d.toDateString() === n.toDateString() ? hm : `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${hm}`;
  }

  function chip(id, opts = {}) {
    const g = typeof id === "object" ? id : tagById(id);
    if (!g) return "";
    return `<span class="ttag${opts.on ? " on" : ""}" style="--c:${esc(g.color)}" data-tag="${g.id}">${esc(g.name)}${opts.x ? `<span class="x" data-untag="${g.id}" title="${esc(t("todo_del"))}">✕</span>` : ""}</span>`;
  }
  /* số việc / ghi chú / việc chưa xong mang từng tag */
  function counts() {
    const out = {};
    for (const g of tags()) out[g.id] = { todos: 0, notes: 0, open: 0 };
    for (const x of (S.state && S.state.todos) || []) for (const i of new Set(x.tags || [])) if (out[i]) { out[i].todos++; if (!x.done) out[i].open++; }
    for (const n of (S.state && S.state.notes) || []) for (const i of new Set(n.tags || [])) if (out[i]) out[i].notes++;
    return out;
  }

  /* ---------------------------------------------------------------- popup nổi (lịch, menu, bảng màu) */
  let popEl = null;
  function closePop() { if (popEl) { popEl.remove(); popEl = null; return true; } return false; }
  function pop(anchor, html, cls = "") {
    closePop();
    const el = document.createElement("div");
    el.className = "tpop " + cls;
    el.innerHTML = html;
    document.body.appendChild(el);
    const r = anchor.getBoundingClientRect(), w = el.offsetWidth, h = el.offsetHeight;
    let left = Math.min(r.left, window.innerWidth - w - 8), top = r.bottom + 4;
    if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 4);
    el.style.left = Math.max(8, left) + "px"; el.style.top = top + "px";
    popEl = el;
    return el;
  }
  document.addEventListener("mousedown", (e) => { if (popEl && !popEl.contains(e.target) && !e.target.closest("[data-pop-anchor]")) closePop(); }, true);

  /* popup chọn hạn: nút nhanh, lịch tháng (chấm vàng = ngày có việc), giờ, Bỏ hạn. onPick("" | "YYYY-MM-DD[THH:MM]") */
  function datePicker(anchor, due, onPick) {
    const p = dueParts(due), now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    let month = p ? new Date(p.date.getFullYear(), p.date.getMonth(), 1) : new Date(today.getFullYear(), today.getMonth(), 1);
    let pick = p ? p.date : null, hm = p && p.hm ? `${pad(p.hm[0])}:${pad(p.hm[1])}` : "";
    const busy = new Set(((S.state && S.state.todos) || []).filter((x) => !x.done && x.due).map((x) => x.due.slice(0, 10)));
    const done = (d, time) => { closePop(); onPick(d ? ymd(d) + (time ? "T" + time : "") : ""); };
    const draw = () => {
      const first = wd(month), days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
      const cells = WD().map((x) => `<span class="cwd">${esc(x)}</span>`);
      for (let i = 0; i < first; i++) cells.push(`<span class="cd o"></span>`);
      for (let d = 1; d <= days; d++) {
        const x = new Date(month.getFullYear(), month.getMonth(), d), k = ymd(x);
        cells.push(`<button class="cd${+x === +today ? " today" : ""}${pick && +x === +pick ? " pick" : ""}${busy.has(k) ? " has" : ""}" data-day="${k}">${d}</button>`);
      }
      const title = month.toLocaleDateString(S.meta.lang || undefined, { month: "long", year: "numeric" });
      el.innerHTML = `
        <div class="tquick"><button class="chip" data-q="0">${esc(t("q_today"))}</button><button class="chip" data-q="1">${esc(t("q_tomorrow"))}</button>
          <button class="chip" data-q="w">${esc(t("q_nextweek"))}</button></div>
        <div class="calh"><button class="btn ghost sm" data-m="-1">‹</button><span>${esc(title)}</span><button class="btn ghost sm" data-m="1">›</button></div>
        <div class="cal">${cells.join("")}</div>
        <div class="timeb">${esc(t("cal_time"))} <input class="field one tbox" id="cal-time" value="${esc(hm)}" placeholder="17:00" maxlength="5">
          ${["09:00", "12:00", "17:00"].map((x) => `<button class="chip" data-t="${x}">${x}</button>`).join("")}</div>
        <div class="timeb"><input class="field one" id="cal-text" placeholder="${esc(t("cal_hint"))}"></div>
        <div class="timeb end"><button class="btn ghost sm danger" data-clear>${esc(t("cal_clear"))}</button></div>`;
    };
    const el = pop(anchor, "", "tcal");
    draw();
    el.style.left = Math.max(8, Math.min(parseFloat(el.style.left), window.innerWidth - el.offsetWidth - 8)) + "px";
    el.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      const time = ($("#cal-time", el).value.trim() && parseTime($("#cal-time", el).value)) ? $("#cal-time", el).value.trim().padStart(5, "0") : "";
      if (b.dataset.m) { month = new Date(month.getFullYear(), month.getMonth() + +b.dataset.m, 1); hm = $("#cal-time", el).value; draw(); return; }
      if (b.dataset.day) { const [y, m, d] = b.dataset.day.split("-").map(Number); done(new Date(y, m - 1, d), time); return; }
      if (b.dataset.q) { done(b.dataset.q === "w" ? addDays(today, 7 - wd(today)) : addDays(today, +b.dataset.q), time); return; }
      if (b.dataset.t) { done(pick || today, b.dataset.t); return; }
      if (b.hasAttribute("data-clear")) done(null);
    });
    el.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { e.stopPropagation(); closePop(); return; }
      if (e.key !== "Enter") return;
      if (e.target.id === "cal-text") { const v = parseDue(e.target.value); if (v != null) { closePop(); onPick(v); } else e.target.classList.add("bad"); }
      if (e.target.id === "cal-time") { const h = parseTime(e.target.value); if (h) done(pick || today, `${pad(h[0])}:${pad(h[1])}`); }
    });
    setTimeout(() => { const f = $("#cal-text", el); if (f) f.focus(); }, 20);
  }

  /* ô gắn tag (ngăn chi tiết việc, ghi chú): chip có ✕ + "＋ thêm tag" mở ô nhập có gợi ý */
  function tagRowHtml(ids) {
    return `${(ids || []).map((i) => typeof i === "string" ? chip({ id: 0, name: i, color: "var(--text-2)" }) : chip(i, { x: true })).join("")}<span class="ttag add" data-addtag>${esc(t("add_tag"))}</span>`;
  }
  function bindTagRow(box, getIds, setIds) {
    box.addEventListener("click", (e) => {
      const x = e.target.closest("[data-untag]");
      if (x) { setIds(getIds().filter((i) => i !== +x.dataset.untag)); return; }
      const add = e.target.closest("[data-addtag]");
      if (!add) return;
      add.outerHTML = `<input class="field one tag-in" list="tag-names" placeholder="${esc(t("add_tag_ph"))}" maxlength="32">`;
      if (!$("#tag-names")) document.body.insertAdjacentHTML("beforeend", `<datalist id="tag-names"></datalist>`);
      $("#tag-names").innerHTML = tags().map((g) => `<option value="${esc(g.name)}">`).join("");
      const inp = $(".tag-in", box);
      inp.focus();
      const commit = () => {
        const n = normTag(inp.value);
        if (!n) return false;
        const g = tags().find((x) => x.name === n);
        setIds(getIds().filter((i) => !g || i !== g.id).concat([g ? g.id : n]));
        return true;
      };
      inp.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && !ev.isComposing) { ev.preventDefault(); commit(); }
        if (ev.key === "Escape") { ev.stopPropagation(); setIds(getIds()); }
      });
      inp.addEventListener("blur", () => { if (!commit()) setIds(getIds()); });
    });
  }

  /* ---------------------------------------------------------------- popup Quản lý tag */
  let tagModalEl = null, tgEdit = null, tgMerge = null, tgDrag = null;
  function tagModal() {
    if (tagModalEl && document.body.contains(tagModalEl)) return;
    tgEdit = tgMerge = null;
    tagModalEl = openModal(`${modalHead(`<b>${esc(t("tag_title"))}</b> <span class="muted small">· ${esc(t("tag_sub"))}</span>`)}
      <div class="modal-pad tagm">
        <div class="newtag"><button class="sw" id="tg-new-c" style="--c:${PALETTE[tags().length % PALETTE.length]}" data-c="${PALETTE[tags().length % PALETTE.length]}" title="${esc(t("tg_color"))}" data-pop-anchor></button>
          <input class="field one" id="tg-new" placeholder="${esc(t("tg_new_ph"))}" maxlength="32" autofocus>
          <button class="btn sm primary" id="tg-add">${esc(t("tg_add"))}</button></div>
        <div class="muted small">${esc(t("tg_help"))}</div>
        <div id="tg-table"></div>
      </div>`, { box: "md", onClose: () => { closePop(); tagModalEl = null; } });
    const m = tagModalEl;
    const add = () => {
      const v = $("#tg-new", m).value;
      if (!normTag(v)) return;
      request("tag", { action: "add", name: v, color: $("#tg-new-c", m).dataset.c }).then((r) => {
        if (r.level !== "warn") { $("#tg-new", m).value = ""; const c = PALETTE[(tags().length + 1) % PALETTE.length]; $("#tg-new-c", m).dataset.c = c; $("#tg-new-c", m).style.setProperty("--c", c); }
      });
    };
    $("#tg-add", m).addEventListener("click", add);
    $("#tg-new", m).addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) add(); });
    m.addEventListener("click", (e) => {
      const b = e.target.closest("[data-tg]"), row = e.target.closest("[data-tid]"), id = row ? +row.dataset.tid : null;
      if (e.target.closest("#tg-new-c")) { colorPop(e.target.closest("#tg-new-c"), $("#tg-new-c", m).dataset.c, (c) => { const s = $("#tg-new-c", m); s.dataset.c = c; s.style.setProperty("--c", c); }); return; }
      if (!b) return;
      const act = b.dataset.tg, g = tagById(id);
      if (act === "color" && g) colorPop(b, g.color, (c) => send("tag", { action: "recolor", id, color: c }));
      if (act === "rename") { tgEdit = id; tgMerge = null; drawTags(true); }
      if (act === "save") saveRename(row);
      if (act === "cancel") { tgEdit = tgMerge = null; drawTags(true); }
      if (act === "merge") { tgMerge = id; tgEdit = null; drawTags(true); }
      if (act === "merge-go") { const into = +$("select", row).value; tgMerge = null; if (into) send("tag", { action: "merge", id, into }); drawTags(true); }
      if (act === "del" && g) confirmBox(t("tag_title"), t("tg_del_q", { v: g.name }), t("todo_del")).then((ok) => ok && send("tag", { action: "delete", id }));
    });
    m.addEventListener("keydown", (e) => {
      const row = e.target.closest("[data-tid]");
      if (!row || !e.target.classList.contains("tg-name")) return;
      if (e.key === "Enter" && !e.isComposing) saveRename(row);
      if (e.key === "Escape") { e.stopPropagation(); tgEdit = null; drawTags(true); }
    });
    m.addEventListener("dragstart", (e) => { const r = e.target.closest("[data-tid]"); tgDrag = r ? +r.dataset.tid : null; });
    m.addEventListener("dragover", (e) => { if (tgDrag != null && e.target.closest("[data-tid]")) e.preventDefault(); });
    m.addEventListener("drop", (e) => {
      const r = e.target.closest("[data-tid]");
      if (tgDrag == null || !r) return;
      e.preventDefault();
      const to = tags().findIndex((x) => x.id === +r.dataset.tid);
      if (+r.dataset.tid !== tgDrag && to >= 0) send("tag", { action: "move", id: tgDrag, to });
      tgDrag = null;
    });
    drawTags(true);
  }
  function saveRename(row) {
    const v = $(".tg-name", row).value, id = +row.dataset.tid;
    request("tag", { action: "rename", id, name: v }).then((r) => { if (r.level !== "warn") { tgEdit = null; drawTags(true); } });
  }
  function colorPop(anchor, cur, onPick) {
    const el = pop(anchor, `<div class="ph">${esc(t("tg_color"))}</div><div class="tpalette">${PALETTE.map((c) => `<button class="sw${c === cur ? " on" : ""}" style="--c:${c}" data-c="${c}"></button>`).join("")}</div>`, "tpal");
    el.addEventListener("click", (e) => { const b = e.target.closest("[data-c]"); if (b) { closePop(); onPick(b.dataset.c); } });
  }
  let tgSig = "";
  function drawTags(force) {
    const m = tagModalEl;
    if (!m || !document.body.contains(m)) { tagModalEl = null; return; }
    const sig = JSON.stringify([tags(), counts()]);
    if (!force && (sig === tgSig || m.contains(document.activeElement) && document.activeElement.classList.contains("tg-name"))) return;
    tgSig = sig;
    const c = counts();
    $("#tg-table", m).innerHTML = tags().length ? `<table class="tgt"><thead><tr><th></th><th>${esc(t("grp_tag"))}</th><th class="num">${esc(t("th_todos"))}</th>
      <th class="num">${esc(t("th_notes"))}</th><th class="num">${esc(t("th_open"))}</th><th></th></tr></thead><tbody>${tags().map((g) => {
      const n = c[g.id] || { todos: 0, notes: 0, open: 0 };
      let name = chip(g), acts = `<button class="btn sm ghost" data-tg="rename">${esc(t("tg_rename"))}</button>
        <button class="btn sm ghost" data-tg="merge"${tags().length < 2 ? " disabled" : ""}>${esc(t("tg_merge"))}</button>
        <button class="btn sm ghost danger" data-tg="del">${esc(t("todo_del"))}</button>`;
      if (tgEdit === g.id) {
        name = `<input class="field one tg-name" value="${esc(g.name)}" maxlength="32"> <span class="muted small">${esc(t("tg_hint"))}</span>`;
        acts = `<button class="btn sm ghost" data-tg="cancel">${esc(t("cancel_edit"))}</button><button class="btn sm primary" data-tg="save">${esc(t("tg_save"))}</button>`;
      } else if (tgMerge === g.id) {
        acts = `<select class="field one sm">${tags().filter((x) => x.id !== g.id).map((x) => `<option value="${x.id}">${esc(x.name)}</option>`).join("")}</select>
          <button class="btn sm ghost" data-tg="cancel">${esc(t("cancel_edit"))}</button><button class="btn sm primary" data-tg="merge-go">${esc(t("tg_merge_go"))}</button>`;
      }
      return `<tr data-tid="${g.id}" draggable="${tgEdit === g.id ? "false" : "true"}" class="${tgEdit === g.id || tgMerge === g.id ? "edit" : ""}">
        <td class="tg-first"><span class="todo-grip">⋮⋮</span><button class="sw" style="--c:${esc(g.color)}" data-tg="color" title="${esc(t("tg_color"))}" data-pop-anchor></button></td>
        <td>${name}</td><td class="num">${n.todos}</td><td class="num">${n.notes}</td><td class="num">${n.open}</td><td><div class="tacts">${acts}</div></td></tr>`;
    }).join("")}</tbody></table>` : `<div class="col-empty">${esc(t("tg_empty"))}</div>`;
    const inp = $(".tg-name", m);
    if (inp && force) { inp.focus(); inp.select(); }
  }

  return { PALETTE, tags, tagById, normTag, parseDue, parseTime, parseQuick, quickTokens, bucket, dueLabel, dueLong, dueParts,
    when, chip, counts, pop, closePop, datePicker, tagRowHtml, bindTagRow, tagModal, drawTags, ymd };
})();

window.TodoView = (() => {
  const LS = "ateam-todo-view";
  let F = { q: "", tag: null, group: "due", due: "all", pri: "all", hideDone: false, fold: { done: true } };
  try { Object.assign(F, JSON.parse(localStorage.getItem(LS) || "{}")); } catch (e) { /* chặn lưu */ }
  const keep = () => { try { localStorage.setItem(LS, JSON.stringify(Object.assign({}, F, { q: "" }))); } catch (e) { /* chặn lưu */ } };
  let editing = null, dragId = null, sig = "", sel = null, drSig = "", ac = { items: [], i: 0, at: -1 }, descTimer = null;
  const el = () => $("#todo");
  const items = () => (S.state && S.state.todos) || [];
  const op = (action, data) => send("todo", Object.assign({ action }, data || {}));
  const item = (id) => items().find((x) => x.id === id);

  function layout() {
    if ($("#todo-add")) return;
    el().innerHTML = `
      <div class="tdv">
        <div class="tdv-main">
          <div class="qadd">
            <div class="qin"><div class="qin-hl" id="todo-hl" aria-hidden="true"></div>
              <input class="qin-in" id="todo-add" placeholder="${esc(t("todo_ph"))}" autocomplete="off" spellcheck="false" maxlength="500">
              <span class="qin-kb" id="todo-kb"><kbd>Enter</kbd></span></div>
            <div class="tac hidden" id="todo-ac"></div>
          </div>
          <div class="qprev hidden" id="todo-prev"></div>
          <div class="fbar">
            <span class="fsearch"><input class="field one" id="todo-q" placeholder="${esc(t("todo_search"))}" autocomplete="off"><kbd>/</kbd></span>
            <span class="tlbl">${esc(t("todo_group"))}</span>
            <span class="tseg" id="todo-grp">${["due", "tag", "pri", "manual"].map((g) => `<button data-g="${g}">${esc(t("grp_" + g))}</button>`).join("")}</span>
            <select class="field one sm" id="todo-fdue"><option value="all">${esc(t("f_due_all"))}</option>
              ${["over", "today", "week", "none"].map((k) => `<option value="${k}">${esc(t(k === "none" ? "b_none" : "b_" + k))}</option>`).join("")}</select>
            <select class="field one sm" id="todo-fpri"><option value="all">${esc(t("f_pri_all"))}</option>
              ${[3, 2, 1, 0].map((k) => `<option value="${k}">${"!".repeat(k)} ${esc(t("pri_" + k))}</option>`).join("")}</select>
            <span class="tsp"></span>
            <button class="btn sm ghost" id="todo-hide">◐ ${esc(t("todo_hide_done"))}</button>
          </div>
          <div class="fbar ftags" id="todo-tags"></div>
          <div class="tgroups" id="todo-list"></div>
        </div>
        <aside class="tdv-side" id="todo-side"></aside>
      </div>`;
    const add = $("#todo-add");
    add.addEventListener("input", quickChanged);
    add.addEventListener("click", quickChanged);
    add.addEventListener("keyup", (e) => { if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) quickChanged(); });
    add.addEventListener("scroll", () => { $("#todo-hl").scrollLeft = add.scrollLeft; });
    add.addEventListener("blur", () => setTimeout(() => hideAc(), 150));
    add.addEventListener("keydown", (e) => {
      if (!$("#todo-ac").classList.contains("hidden") && ac.items.length) {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); ac.i = (ac.i + (e.key === "ArrowDown" ? 1 : -1) + ac.items.length) % ac.items.length; drawAc(); return; }
        if ((e.key === "Tab" || e.key === "Enter") && !e.isComposing) { e.preventDefault(); pickAc(ac.i); return; }
        if (e.key === "Escape") { e.stopPropagation(); hideAc(); return; }
      }
      if (e.key !== "Enter" || e.isComposing || !add.value.trim()) return;
      if (!TD.parseQuick(add.value).text.trim()) { toast(t("todo_empty"), "warn"); return; }
      op("add", { text: add.value });
      add.value = "";
      quickChanged();
    });
    $("#todo-ac").addEventListener("mousedown", (e) => { const b = e.target.closest("[data-i]"); if (b) { e.preventDefault(); pickAc(+b.dataset.i); } });
    $("#todo-q").addEventListener("input", (e) => { F.q = e.target.value; sig = ""; render(); });
    $("#todo-q").addEventListener("keydown", (e) => { if (e.key === "Escape" && e.target.value) { e.stopPropagation(); e.target.value = ""; F.q = ""; sig = ""; render(); } });
    $("#todo-grp").addEventListener("click", (e) => { const b = e.target.closest("[data-g]"); if (b) { F.group = b.dataset.g; keep(); sig = ""; render(); } });
    $("#todo-fdue").addEventListener("change", (e) => { F.due = e.target.value; keep(); sig = ""; render(); });
    $("#todo-fpri").addEventListener("change", (e) => { F.pri = e.target.value; keep(); sig = ""; render(); });
    $("#todo-hide").addEventListener("click", () => { F.hideDone = !F.hideDone; keep(); sig = ""; render(); });
    $("#todo-tags").addEventListener("click", (e) => {
      if (e.target.closest("[data-manage]")) { TD.tagModal(); return; }
      const c = e.target.closest("[data-tag]");
      if (c) { F.tag = c.dataset.tag === "" ? null : (+c.dataset.tag === F.tag ? null : +c.dataset.tag); keep(); sig = ""; render(); }
    });
    const list = $("#todo-list");
    list.addEventListener("click", (e) => {
      if (e.target.closest("[data-clear]")) { op("clear"); return; }
      const gh = e.target.closest("[data-fold]");
      if (gh) { F.fold[gh.dataset.fold] = !F.fold[gh.dataset.fold]; keep(); sig = ""; render(); return; }
      const row = e.target.closest("[data-id]");
      if (!row || e.target.closest(".todo-edit")) return;
      const id = +row.dataset.id;
      if (e.target.closest(".tcb")) { op("toggle", { id }); return; }
      const tg = e.target.closest("[data-tag]");
      if (tg) { F.tag = +tg.dataset.tag; keep(); sig = ""; render(); return; }
      const due = e.target.closest(".tdue");
      if (due) { dueMenu(due, id); return; }
      const mb = e.target.closest("[data-menu]");
      if (mb) { rowMenu(mb, id); return; }
      openItem(id);
    });
    list.addEventListener("dblclick", (e) => {
      const row = e.target.closest("[data-id]");
      if (row && e.target.closest(".ttl")) startEdit(+row.dataset.id);
    });
    list.addEventListener("dragstart", (e) => { const r = e.target.closest("[data-id]"); dragId = r ? +r.dataset.id : null; });
    list.addEventListener("dragover", (e) => { if (dragId != null) e.preventDefault(); });
    list.addEventListener("drop", (e) => {
      const r = e.target.closest("[data-id]");
      if (dragId == null || !r) return;
      e.preventDefault();
      const to = items().findIndex((x) => x.id === +r.dataset.id);
      if (+r.dataset.id !== dragId && to >= 0) op("move", { id: dragId, to });
      dragId = null;
    });
    const side = $("#todo-side");
    side.addEventListener("click", sideClick);
    side.addEventListener("change", (e) => {
      if (e.target.id === "dr-title") commitTitle();
    });
    side.addEventListener("keydown", (e) => {
      if (e.target.id === "dr-title" && e.key === "Enter" && !e.isComposing) { e.preventDefault(); commitTitle(); e.target.blur(); }
      if (e.target.id === "dr-title" && e.key === "Escape") { e.stopPropagation(); const x = item(sel); e.target.value = x ? x.text : ""; e.target.blur(); }
      if (e.target.id === "dr-desc" && e.key === "Escape") { e.stopPropagation(); commitDesc(); e.target.blur(); }
    });
    side.addEventListener("input", (e) => { if (e.target.id === "dr-desc") { clearTimeout(descTimer); descTimer = setTimeout(commitDesc, 1000); } });
    side.addEventListener("focusout", (e) => { if (e.target.id === "dr-desc") commitDesc(); if (e.target.id === "dr-title") commitTitle(); });
  }

  /* ---------------------------------------------------------------- ô thêm nhanh: tô màu, gợi ý tag, xem trước */
  function quickChanged() {
    const add = $("#todo-add"), v = add.value, caret = add.selectionStart || 0;
    let pos = 0, mk = -1;
    const hl = TD.quickTokens(v).map((x) => {
      const start = pos; pos += x.s.length;
      const body = caret >= start && caret <= pos && mk < 0 ? (mk = 1, esc(x.s.slice(0, caret - start)) + `<span class="mk"></span>` + esc(x.s.slice(caret - start))) : esc(x.s);
      if (x.k === "tag") { const g = TD.tags().find((y) => y.name === x.v); return `<span class="tk tg" style="--c:${g ? g.color : "var(--text-2)"}">${body}</span>`; }
      return x.k === "pri" ? `<span class="tk pr">${body}</span>` : x.k === "due" ? `<span class="tk du">${body}</span>` : body;
    }).join("");
    $("#todo-hl").innerHTML = hl + (mk < 0 ? `<span class="mk"></span>` : "");
    $("#todo-hl").scrollLeft = add.scrollLeft;
    const q = TD.parseQuick(v), prev = $("#todo-prev");
    const any = q.tags.length || q.due || q.priority;
    prev.classList.toggle("hidden", !any);
    if (any) {
      prev.innerHTML = `→ <b>${esc(q.text)}</b>${q.tags.length ? `<span>${esc(t("qp_tags"))} ${q.tags.map((n) => TD.chip(TD.tags().find((g) => g.name === n) || { id: 0, name: n, color: "var(--text-2)" })).join(" ")}</span>` : ""}
        ${q.due ? `<span>${esc(t("qp_due"))} <b>${esc(TD.dueLong(q.due))}</b></span>` : ""}
        ${q.priority ? `<span>${esc(t("qp_pri"))} <b class="pri-${q.priority}">${esc(t("pri_" + q.priority))}</b></span>` : ""}`;
    }
    // gợi ý tag khi chữ ngay trước con trỏ là #…
    const m = /(^|\s)#([^\s#]*)$/.exec(v.slice(0, caret));
    if (!m) { hideAc(); return; }
    const word = TD.normTag(m[2]), c = TD.counts();
    const hits = TD.tags().filter((g) => !word || g.name.includes(word))
      .sort((a, b) => (b.name.startsWith(word) - a.name.startsWith(word)) || ((c[b.id] || {}).todos - (c[a.id] || {}).todos)).slice(0, 6);
    ac = { items: hits.map((g) => ({ name: g.name, g })), i: 0, at: caret - m[2].length - 1 };
    if (word && !hits.some((g) => g.name === word)) ac.items.push({ name: word, create: true });
    if (!ac.items.length) { hideAc(); return; }
    const box = $("#todo-ac"), mkEl = $("#todo-hl .mk");
    box.style.left = Math.max(0, Math.min((mkEl ? mkEl.offsetLeft - $("#todo-hl").scrollLeft : 0) - 20, $(".qadd").clientWidth - 300)) + "px";
    box.classList.remove("hidden");
    drawAc();
  }
  function drawAc() {
    const c = TD.counts();
    $("#todo-ac").innerHTML = `<div class="mh">${esc(t("grp_tag"))}</div>` + ac.items.map((x, i) => x.create
      ? `<div class="mi${i === ac.i ? " sel" : ""}" data-i="${i}">${esc(t("ac_new", { v: x.name }))}</div>`
      : `<div class="mi${i === ac.i ? " sel" : ""}" data-i="${i}"><span class="tdot" style="--c:${esc(x.g.color)}"></span>${esc(x.name)}<span class="k">${esc(t("ac_count", { n: (c[x.g.id] || {}).todos || 0, m: (c[x.g.id] || {}).notes || 0 }))}</span></div>`).join("");
    $("#todo-kb").innerHTML = `<kbd>Tab</kbd> ${esc(t("kb_pick"))} <kbd>Enter</kbd> ${esc(t("kb_add"))}`;
  }
  function hideAc() {
    const box = $("#todo-ac");
    if (box) box.classList.add("hidden");
    ac.items = [];
    if ($("#todo-kb")) $("#todo-kb").innerHTML = "<kbd>Enter</kbd>";
  }
  function pickAc(i) {
    const x = ac.items[i], add = $("#todo-add");
    if (!x || ac.at < 0) return;
    const caret = add.selectionStart || 0;
    const after = add.value.slice(caret).replace(/^[^\s]*/, "");
    add.value = add.value.slice(0, ac.at) + "#" + x.name + " " + after.replace(/^\s+/, "");
    const p = ac.at + x.name.length + 2;
    add.setSelectionRange(p, p);
    add.focus();
    hideAc();
    quickChanged();
  }

  /* ---------------------------------------------------------------- lọc + nhóm */
  function visible() {
    const q = F.q.trim().toLowerCase();
    return items().filter((x) => {
      if (F.hideDone && x.done) return false;
      if (F.tag != null && !(x.tags || []).includes(F.tag)) return false;
      if (F.pri !== "all" && (x.priority || 0) !== +F.pri) return false;
      if (F.due !== "all" && TD.bucket(x) !== F.due) return false;
      if (q) {
        const hay = [x.text, x.desc || "", ...(x.tags || []).map((i) => (TD.tagById(i) || {}).name || "")].join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }
  function byDue(a, b) {
    const da = a.due || "9999", db = b.due || "9999";
    return da < db ? -1 : da > db ? 1 : (b.priority || 0) - (a.priority || 0);
  }
  function groups(list) {
    const done = list.filter((x) => x.done).sort((a, b) => (b.done_at || 0) - (a.done_at || 0));
    const open = list.filter((x) => !x.done);
    let out = [];
    if (F.group === "manual") return [{ key: "all", title: t("b_all"), items: list, manual: true }];
    if (F.group === "due") {
      const now = new Date(), wd = TD.dueLong(TD.ymd(now)).split(", ").pop();
      out = ["over", "today", "week", "later", "none"].map((k) => ({ key: k, cls: k, title: (k === "over" ? "⚠ " : k === "today" ? "◉ " : "") + t("b_" + k) + (k === "today" ? " · " + wd : ""),
        items: open.filter((x) => TD.bucket(x) === k).sort(byDue) }));
    } else if (F.group === "tag") {
      out = TD.tags().map((g) => ({ key: "t" + g.id, title: TD.chip(g), html: true, items: open.filter((x) => (x.tags || []).includes(g.id)).sort(byDue) }));
      out.push({ key: "untagged", title: t("b_untagged"), items: open.filter((x) => !(x.tags || []).some((i) => TD.tagById(i))).sort(byDue) });
    } else {
      out = [3, 2, 1, 0].map((p) => ({ key: "p" + p, cls: "pri-" + p, title: (p ? "!".repeat(p) + " " : "") + t("pri_" + p), items: open.filter((x) => (x.priority || 0) === p).sort(byDue) }));
    }
    out = out.filter((g) => g.items.length);
    if (done.length) out.push({ key: "done", title: "✓ " + t("b_done"), items: done, done: true });
    return out;
  }
  function rowHtml(x, manual) {
    const d = TD.dueLabel(x), p = x.priority || 0;
    return `<div class="trow${x.done ? " done" : ""}${x.id === sel ? " sel" : ""}" data-id="${x.id}"${manual ? ' draggable="true"' : ""}>
      <span class="todo-grip" aria-hidden="true">${manual ? "⋮⋮" : ""}</span>
      <span class="tcb${x.done ? " on" : ""}" role="checkbox" aria-checked="${!!x.done}">${x.done ? "✓" : ""}</span>
      <span class="tpri p${p}" title="${esc(t("f_pri"))}: ${esc(t("pri_" + p))}">${p ? "!".repeat(p) : ""}</span>
      <span class="ttl" title="${esc(t("todo_edit"))}">${mdInline(x.text)}</span>
      ${x.desc ? `<span class="tico" title="${esc(t("f_desc"))}">≡</span>` : ""}
      <span class="trtags">${(x.tags || []).map((i) => TD.chip(i)).join("")}</span>
      <span class="tdue ${d.cls}" data-pop-anchor title="${esc(t("m_due"))}">${esc(d.text) || '<span class="tdue-add">＋</span>'}</span>
      <button class="icon-btn tmenu" data-menu data-pop-anchor title="⋯">⋯</button>
    </div>`;
  }
  function renderList() {
    const vis = visible(), gs = groups(vis);
    if (!items().length) { $("#todo-list").innerHTML = `<div class="col-empty">${esc(t("todo_empty"))}</div>`; return; }
    if (!vis.length) { $("#todo-list").innerHTML = `<div class="col-empty">${esc(t("todo_nomatch"))}</div>`; return; }
    $("#todo-list").innerHTML = gs.map((g) => {
      const fold = g.done ? F.fold.done !== false : !!F.fold[g.key];
      return `<div class="tgroup">
        <div class="tgh ${g.cls || ""}" data-fold="${g.key}"><span class="chev">${fold ? "▸" : "▾"}</span>${g.html ? g.title : esc(g.title)}<span class="n">${g.items.length}</span>
          ${g.done ? `<span class="tsp"></span><button class="btn ghost sm" data-clear>${esc(t("todo_clear"))}</button>` : ""}</div>
        ${fold ? "" : `<div class="tlist">${g.items.map((x) => rowHtml(x, g.manual)).join("")}</div>`}</div>`;
    }).join("");
  }
  function renderBars() {
    $$("#todo-grp [data-g]").forEach((b) => b.classList.toggle("on", b.dataset.g === F.group));
    $("#todo-fdue").value = F.due; $("#todo-fpri").value = String(F.pri);
    $("#todo-hide").classList.toggle("on", F.hideDone);
    if (F.tag != null && !TD.tagById(F.tag)) F.tag = null;
    $("#todo-tags").innerHTML = `<span class="tlbl">${esc(t("grp_tag"))}</span><span class="ttag all${F.tag == null ? " on" : ""}" data-tag="">${esc(t("tag_all"))}</span>`
      + TD.tags().map((g) => TD.chip(g, { on: g.id === F.tag })).join("") + `<span class="ttag add" data-manage>${esc(t("tag_manage"))}</span>`;
  }

  /* ---------------------------------------------------------------- cột phải: tổng quan hoặc chi tiết việc */
  function renderSide(force) {
    const side = $("#todo-side");
    if (sel != null && !item(sel)) sel = null;
    if (sel == null) {
      drSig = "";
      const all = items(), now = new Date(), mon = new Date(now.getFullYear(), now.getMonth(), now.getDate() - (now.getDay() + 6) % 7);
      const nb = (k) => all.filter((x) => TD.bucket(x) === k).length, c = TD.counts();
      side.className = "tdv-side";
      side.innerHTML = `
        <div class="tcard"><div class="ch">${esc(t("st_overview"))}</div><div class="tstats">
          <button class="tstat over" data-fdue="over"><b>${nb("over")}</b><span>${esc(t("st_over"))}</span></button>
          <button class="tstat today" data-fdue="today"><b>${nb("today")}</b><span>${esc(t("st_today"))}</span></button>
          <button class="tstat" data-fdue="all"><b>${all.filter((x) => !x.done).length}</b><span>${esc(t("st_open"))}</span></button>
          <button class="tstat ok"><b>${all.filter((x) => x.done && (x.done_at || 0) * 1000 >= +mon).length}</b><span>${esc(t("st_week"))}</span></button></div></div>
        <div class="tcard"><div class="ch">${esc(t("grp_tag"))}<span class="tsp"></span><button class="btn ghost sm" data-manage>${esc(t("tag_manage_btn"))}</button></div>
          <div class="ttlist">${TD.tags().map((g) => `<button class="ti${g.id === F.tag ? " on" : ""}" data-tag="${g.id}"><span class="tdot" style="--c:${esc(g.color)}"></span>${esc(g.name)}<span class="n">${(c[g.id] || {}).open || 0}</span></button>`).join("")
            || `<div class="muted small" style="padding:8px 11px">${esc(t("tg_empty"))}</div>`}</div></div>
        <div class="muted small where">${esc(t("todo_where", { path: S.meta.todo_file || "" }))}</div>`;
      return;
    }
    const x = item(sel), s = JSON.stringify([x, TD.tags()]);
    if (!force && s === drSig) return;
    if (!force && side.contains(document.activeElement) && /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) return;
    drSig = s;
    const p = x.priority || 0, md = side.dataset.md || "view";
    side.className = "tdv-side tdr";
    side.innerHTML = `
      <div class="dh">${esc(t("dr_todo", { id: x.id }))}<span class="tsp"></span><kbd>↑↓</kbd> ${esc(t("dr_nav"))} <kbd>Esc</kbd> ${esc(t("dr_close"))}
        <button class="icon-btn" data-dr="close" title="${esc(t("close"))}"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>
      <div class="db">
        <div class="dtitle"><span class="tcb${x.done ? " on" : ""}" data-dr="toggle">${x.done ? "✓" : ""}</span>
          <input class="dr-title" id="dr-title" value="${esc(x.text)}" maxlength="500"></div>
        <div class="fld">
          <span class="k">${esc(t("f_pri"))}</span><span class="tseg">${[0, 1, 2, 3].map((k) => `<button data-pri="${k}" class="${k === p ? "on pri-" + k : ""}">${k ? "!".repeat(k) + " " : ""}${esc(t("pri_" + k))}</button>`).join("")}</span>
          <span class="k">${esc(t("f_due"))}</span><span class="dcol"><span><button class="duebox ${TD.dueLabel(x).cls}" data-dr="due" data-pop-anchor>📅 ${esc(TD.dueLong(x.due))}</button>
            ${x.due ? `<button class="icon-btn" data-dr="nodue" title="${esc(t("cal_clear"))}">✕</button>` : ""}</span>
            <span class="tquick"><button class="chip" data-q="0">${esc(t("q_today"))}</button><button class="chip" data-q="1">${esc(t("q_tomorrow"))}</button>
              <button class="chip" data-q="w">${esc(t("q_nextweek"))}</button><button class="chip" data-dr="due" data-pop-anchor>${esc(t("q_pick"))}</button></span></span>
          <span class="k">${esc(t("f_tags"))}</span><span class="trtags wrap" id="dr-tags">${TD.tagRowHtml(x.tags || [])}</span>
          <span class="k">${esc(t("f_status"))}</span><span class="tseg"><button data-st="0" class="${x.done ? "" : "on"}">${esc(t("st_undone"))}</button><button data-st="1" class="${x.done ? "on" : ""}">${esc(t("st_done"))}</button></span>
        </div>
        <div class="dmd"><div class="dmh">${esc(t("f_desc"))}<span class="tsp"></span><span class="tseg sm">${["edit", "view"].map((k) => `<button data-md="${k}" class="${k === md ? "on" : ""}">${esc(t("md_" + k))}</button>`).join("")}</span></div>
          ${md === "edit" || !x.desc ? `<textarea class="field dr-desc" id="dr-desc" placeholder="${esc(t("desc_ph"))}">${esc(x.desc || "")}</textarea>`
            : `<div class="dr-prev md" data-md="edit">${mdHtml(x.desc)}</div>`}</div>
      </div>
      <div class="df"><span class="meta">${esc(t("created_at", { t: TD.when(x.created) }))}${x.updated ? " · " + esc(t("updated_at", { t: TD.when(x.updated) })) : ""}</span><span class="tsp"></span>
        <button class="btn sm" data-dr="lead" title="${esc(t("to_lead_tip"))}">${esc(t("to_lead"))}</button><button class="btn sm danger" data-dr="del">${esc(t("todo_del"))}</button></div>`;
    TD.bindTagRow($("#dr-tags"), () => (item(sel) || {}).tags || [], (ids) => { op("edit", { id: sel, tags: ids }); drSig = ""; setTimeout(() => renderSide(true), 0); });
  }
  function sideClick(e) {
    if (e.target.closest("[data-manage]")) { TD.tagModal(); return; }
    const fd = e.target.closest("[data-fdue]");
    if (fd) { F.due = fd.dataset.fdue; keep(); sig = ""; render(); return; }
    const tg = e.target.closest(".ttlist [data-tag]");
    if (tg) { F.tag = +tg.dataset.tag === F.tag ? null : +tg.dataset.tag; keep(); sig = ""; render(); return; }
    if (sel == null) return;
    const x = item(sel), b = e.target.closest("[data-dr], [data-pri], [data-st], [data-q], [data-md]");
    if (!b || !x) return;
    const side = $("#todo-side");
    if (b.dataset.md) { side.dataset.md = b.dataset.md; renderSide(true); if (b.dataset.md === "edit") { const d = $("#dr-desc"); if (d) d.focus(); } return; }
    if (b.dataset.pri != null) { op("edit", { id: x.id, priority: +b.dataset.pri }); return; }
    if (b.dataset.st != null) { if (!!x.done !== (b.dataset.st === "1")) op("toggle", { id: x.id }); return; }
    if (b.dataset.q != null) {
      const now = new Date(), d = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      d.setDate(d.getDate() + (b.dataset.q === "w" ? 7 - (d.getDay() + 6) % 7 : +b.dataset.q));
      const p = TD.dueParts(x.due);
      op("edit", { id: x.id, due: TD.ymd(d) + (p && p.hm ? `T${String(p.hm[0]).padStart(2, "0")}:${String(p.hm[1]).padStart(2, "0")}` : "") });
      return;
    }
    const a = b.dataset.dr;
    if (a === "close") closeItem();
    else if (a === "toggle") op("toggle", { id: x.id });
    else if (a === "due") TD.datePicker(b, x.due, (v) => op("edit", { id: x.id, due: v }));
    else if (a === "nodue") op("edit", { id: x.id, due: "" });
    else if (a === "lead") toLead(x);
    else if (a === "del") delItem(x);
  }
  function commitTitle() {
    const inp = $("#dr-title"), x = item(sel);
    if (!inp || !x) return;
    const v = inp.value.trim();
    if (v && v !== x.text) op("edit", { id: x.id, text: v });
    else inp.value = x.text;
  }
  function commitDesc() {
    clearTimeout(descTimer);
    const ta = $("#dr-desc"), x = item(sel);
    if (!ta || !x) return;
    if (ta.value.trimEnd() !== (x.desc || "")) op("edit", { id: x.id, desc: ta.value });
  }
  function toLead(x) {
    send("submit", { text: x.text + (x.desc ? "\n\n" + x.desc : "") });
    setView("board");
  }
  function delItem(x) {
    confirmBox(t("todo_del"), t("del_todo_q", { v: x.text }), t("todo_del")).then((ok) => { if (ok) { op("delete", { id: x.id }); if (sel === x.id) closeItem(); } });
  }
  function openItem(id) { if (sel === id) return; commitDesc(); sel = id; sig = ""; render(); }
  function closeItem() { commitDesc(); sel = null; sig = ""; render(); }
  function dueMenu(anchor, id) { const x = item(id); if (x) TD.datePicker(anchor, x.due, (v) => op("edit", { id, due: v })); }
  function rowMenu(anchor, id) {
    const x = item(id);
    if (!x) return;
    const m = TD.pop(anchor, `<div class="mi" data-m="open">${esc(t("m_open"))}</div><div class="mi" data-m="due">${esc(t("m_due"))}</div>
      <div class="mi" data-m="lead">${esc(t("to_lead"))}</div><div class="ms"></div><div class="mi danger" data-m="del">${esc(t("todo_del"))}</div>`, "tmenu-pop");
    m.addEventListener("click", (e) => {
      const b = e.target.closest("[data-m]");
      if (!b) return;
      TD.closePop();
      if (b.dataset.m === "open") openItem(id);
      if (b.dataset.m === "due") { const row = $(`#todo-list [data-id="${id}"] .tdue`); if (row) dueMenu(row, id); }
      if (b.dataset.m === "lead") toLead(x);
      if (b.dataset.m === "del") delItem(x);
    });
  }

  function startEdit(id) {
    const x = item(id), row = $(`#todo-list [data-id="${id}"]`);
    if (!x || !row) return;
    editing = id;
    const span = $(".ttl", row);
    span.innerHTML = `<input class="field one todo-edit" value="${esc(x.text)}" maxlength="500">`;
    const inp = $("input", span);
    inp.focus(); inp.select();
    const done = (keepIt) => {
      if (editing !== id) return;
      editing = null;
      if (keepIt && inp.value.trim() && inp.value.trim() !== x.text) op("edit", { id, text: inp.value });
      sig = ""; render();
    };
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing) done(true);
      if (e.key === "Escape") { e.stopPropagation(); done(false); }
    });
    inp.addEventListener("blur", () => done(true));
  }

  function navCount() {
    const nav = $("#count-todo"), left = items().filter((x) => !x.done).length, over = items().filter((x) => TD.bucket(x) === "over").length;
    if (!nav) return;
    nav.textContent = left || "";
    nav.classList.toggle("over", over > 0);
    nav.title = over ? `${over} ${t("st_over")}` : "";
  }
  function render() {
    navCount();
    TD.drawTags(false);
    if (S.view !== "todo" || editing != null) return;
    layout();
    const s = JSON.stringify([items(), TD.tags(), F, sel, new Date().getMinutes()]);
    if (s !== sig) {
      sig = s;
      renderBars();
      renderList();
    }
    renderSide(false);
  }
  /* Esc ở tab To-do: đóng popup nổi, rồi ngăn chi tiết. true = đã xử lý */
  function escape() {
    if (TD.closePop()) return true;
    if (sel != null) { closeItem(); return true; }
    return false;
  }
  document.addEventListener("keydown", (e) => {
    if (S.view !== "todo" || topModal()) return;
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
    if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey) { e.preventDefault(); $("#todo-q").focus(); return; }
    if (sel != null && !typing && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      const ids = $$("#todo-list [data-id]").map((r) => +r.dataset.id), i = ids.indexOf(sel);
      const n = ids[i + (e.key === "ArrowDown" ? 1 : -1)];
      if (n != null) { e.preventDefault(); openItem(n); const r = $(`#todo-list [data-id="${n}"]`); if (r) r.scrollIntoView({ block: "nearest" }); }
    }
  });

  return { render, escape, show() { sig = ""; drSig = ""; render(); const a = $("#todo-add"); if (a && sel == null) a.focus(); } };
})();
