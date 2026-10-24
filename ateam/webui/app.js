/* ateam web — nói chuyện với server qua WebSocket (xem ateam/web.py). Mọi chữ hiển thị lấy từ S.T (dịch ở Python). */
"use strict";

const S = {
  T: {}, commands: [], agentNames: [], meta: {}, prefs: {}, state: null, ws: null, connected: false, retry: 0,
  pending: {}, refSeq: 0, branches: null, branchesAt: 0,
  view: "board", goalFilter: null, board: "list", fold: {}, openTask: null, drawerTab: "log", openJob: null,
  expanded: new Set(), editing: null, rejecting: false,
  logs: [], agentLogs: {}, jobLines: {}, scripts: null, scriptsAt: 0,
  live: {}, full: {}, ptys: {},  // live: dòng cuối của task đang chạy (tin "live"); full: prompt/kết quả đã tải của task
  suggest: { items: [], i: 0, kind: "", nav: false },
};
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const now = () => Date.now() / 1000;

function t(key, vars) {
  let s = S.T[key];
  if (s == null) s = key;
  if (vars) for (const k in vars) s = s.split("{" + k + "}").join(vars[k]);
  return s;
}
function hue(name) { let h = 0; for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }
function agentHtml(name, cls = "") {
  return `<span class="agent ${cls}"><span class="av" style="--h:${hue(name)}">${esc(String(name)[0] || "?")}</span>${esc(name)}</span>`;
}
function dur(sec) {
  sec = Math.max(0, Math.round(sec));
  if (sec < 60) return sec + "s";
  const m = Math.floor(sec / 60), s = sec % 60;
  if (m < 60) return m + "m" + (s ? " " + String(s).padStart(2, "0") + "s" : "");
  const h = Math.floor(m / 60);
  return h + "h " + String(m % 60).padStart(2, "0") + "m";
}
function clock(ts) { return ts ? new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—"; }
function badge(status, label, pulse) {
  return `<span class="badge s-${esc(status)}${pulse ? " pulse" : ""}"><span class="dot"></span>${esc(label || t(status))}</span>`;
}
function elapsedHtml(start, end) {
  if (!start) return "";
  return end ? `<span class="time">${dur(end - start)}</span>` : `<span class="time" data-since="${start}">${dur(now() - start)}</span>`;
}

/* ------------------------------------------------------------------ kết nối */
function connect() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  S.ws = ws;
  ws.onopen = () => { S.retry = 0; setConn(true); if (window.GridView) GridView.reset(); };
  ws.onclose = () => {
    setConn(false);
    // thao tác đang chờ sẽ không bao giờ được trả lời: tắt toast "đang chạy…", mở khoá nút
    for (const ref of Object.keys(S.pending)) { S.pending[ref]({ level: "error" }); delete S.pending[ref]; }
    if (S.restartToken) { waitRestart(Date.now()); return; }  // 📱 chạy lại từ xa: vào lại bằng token
    setTimeout(connect, Math.min(5000, 500 * 2 ** S.retry++));
  };
  ws.onmessage = (ev) => {
    let m;
    try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.t === "hello") onHello(m);
    else if (m.t === "state") { S.state = m; render(); }
    else if (m.t === "lines") onLines(m.items);
    else if (m.t === "pty") ptyData(m);
    else if (m.t === "pty_exit") ptyExit(m);
    else if (m.t === "grid" && window.GridView) GridView.onState(m);
    else if (m.t === "gpty" && window.GridView) GridView.onData(m);
    else if (m.t === "gpty_exit" && window.GridView) GridView.onExit(m);
    else if (m.t === "live") { S.live = m.last || {}; if (S.state && S.view === "board") renderBoard(); }
    else if (m.t === "toast") onToast(m);
    else if (m.t === "notice") onNotice(m);
    else if (m.t === "update") { Object.assign(S.meta, m); showUpdate(); }
    else if (m.t === "prefs") applyPrefs(m);
    else if (m.t === "quota" && window.QuotaView) QuotaView.onState(m);
    else if (m.t === "discovered" && window.Setup) Setup.discovered();
  };
}
function send(op, data = {}) {
  if (!S.ws || S.ws.readyState !== 1) { toast(t("disconnected"), "error"); return false; }
  S.ws.send(JSON.stringify(Object.assign({ op }, data)));
  return true;
}
/* gửi thao tác và chờ trả lời (toast cùng ref) — dùng khi cần kết quả: lưu file, commit…
   busy: chữ cho toast "đang chạy…" (spinner) — chỉ hiện khi chưa xong sau 300ms, tắt đúng lúc có kết quả */
function request(op, data = {}, busy = "") {
  const ref = ++S.refSeq;
  let bt = null;
  const timer = busy ? setTimeout(() => { bt = busyToast(busy); }, 300) : 0;
  return new Promise((resolve) => {
    S.pending[ref] = (m) => { clearTimeout(timer); if (bt) bt.done(); resolve(m); };
    // ref đặt sau cùng: dữ liệu có khoá "ref" cũng không ghi đè được mã chờ (nếu không, toast "đang chạy" treo mãi)
    if (!send(op, Object.assign({}, data, { ref }))) { const f = S.pending[ref]; delete S.pending[ref]; f({ level: "error" }); }
  });
}
/* nút đang chạy: khoá + spinner tới khi promise xong (nút không bị vẽ lại trong lúc chờ) */
async function busyBtn(btn, promise) {
  if (btn) { btn.disabled = true; btn.classList.add("busy"); }
  try { return await promise; } finally { if (btn) { btn.disabled = false; btn.classList.remove("busy"); } }
}
function setConn(ok) {
  S.connected = ok;
  $("#conn").classList.toggle("ok", ok);
  $("#conn-text").textContent = ok ? t("connected") : t(S.restartToken ? "phone_restarting" : S.switching ? "proj_switching" : "disconnected");
}
/* bản mới (server kiểm tra lúc mở + mỗi 6 giờ): ⬆ ở chân thanh bên + toast một lần mỗi phiên bản; chỉ báo,
   cập nhật vẫn bằng /update (bản cài từ mã nguồn: git pull, không có nút) */
function showUpdate() {
  const m = S.meta, ver = $("#ver");
  ver.textContent = "ateam " + m.version;
  if (!m.latest) return;
  const can = !m.update_src && !m.readonly;
  const up = document.createElement(can ? "button" : "span");
  up.className = "ver-up";
  up.textContent = "⬆ " + m.latest;
  up.title = m.update_text;
  if (can) up.addEventListener("click", () => send("submit", { text: "/update" }));
  ver.append(" · ", up);
  if (S.updShown === m.latest) return;
  S.updShown = m.latest;
  toast(m.update_text, "info", can ? { label: t("update_now"), run: () => send("submit", { text: "/update" }) } : null);
}
function onHello(m) {
  // /open: server đã chạy lại ở dự án khác -> nạp lại trang (mọi view, buffer đều thuộc dự án cũ)
  if (S.meta.root && m.root !== S.meta.root) { S.switching = true; location.reload(); return; }
  const first = !S.meta.version;
  S.T = m.T; S.commands = m.commands; S.meta = m;
  S.agentNames = m.agents.map((a) => a.name);
  document.documentElement.lang = m.lang;
  $("#proj").textContent = m.project;
  $("#proj").title = m.remote ? m.root : m.root + " — " + t("proj_open");
  $("#proj").disabled = !!m.remote;
  showUpdate();
  $$("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });
  // màn hình hẹp chỉ còn icon: nút vẫn có tên cho trình đọc màn hình và tooltip (kèm phím Alt+số)
  $$(".nav-item").forEach((b) => {
    const lbl = $("[data-t]", b), i = $$("#nav .nav-item").indexOf(b);
    if (lbl) { b.setAttribute("aria-label", lbl.textContent); b.title = lbl.textContent + (i >= 0 && i < 10 ? `  (Alt+${(i + 1) % 10})` : ""); }
  });
  renderSideToggle();
  $("#btn-theme").title = t("theme");
  $("#btn-rules").title = t("rules_title");
  $("#btn-rules").setAttribute("aria-label", t("rules_title"));
  $("#btn-theme").setAttribute("aria-label", t("theme"));
  $("#kbd-hint").textContent = t("shortcuts");
  applyPrefs(m.prefs);
  document.body.classList.toggle("readonly", !!m.readonly);
  if (m.readonly && !$("#ro-banner")) document.body.insertAdjacentHTML("afterbegin", `<div id="ro-banner" class="ro-banner">${esc(t("readonly_banner"))}</div>`);
  setConn(true);
  if (S.openTask != null) loadLog(S.openTask);
  if (S.openJob != null) loadJob(S.openJob);
  for (const name of S.agentNames) loadAgentTail(name);
  if (first && m.needs_setup && window.Setup) Setup.open(true);  // lần đầu dùng ateam: wizard thiết lập
  if (first) {  // vừa chạy lại ở chế độ từ xa (remoteRestart): mở lại popup để quét mã QR
    let ph = null;
    try { ph = sessionStorage.getItem("ateam-phone"); sessionStorage.removeItem("ateam-phone"); } catch (e) { /* chặn lưu */ }
    if (ph) phoneModal();
  }
  if (S.state) render();
}
function applyPrefs(p) {
  S.prefs = Object.assign({}, S.prefs, p);
  const root = document.documentElement.style;
  if (S.prefs.accent_color) {
    root.setProperty("--accent", S.prefs.accent_color);
    root.setProperty("--accent-soft", S.prefs.accent_color + "24");
    root.setProperty("--ring", S.prefs.accent_color + "73");
  } else ["--accent", "--accent-soft", "--ring"].forEach((k) => root.removeProperty(k));
  if (window.CodeView) CodeView.prefsChanged();
}
function onToast(m) {
  if (m.ref != null && S.pending[m.ref]) { S.pending[m.ref](m); delete S.pending[m.ref]; }
  const o = m.open || {};
  // Ngăn chi tiết / popup chỉ mở khi người dùng chủ động (bấm, /log, /plan…). Kết quả của lệnh "làm việc"
  // (/continue, /update) chỉ báo bằng toast kèm nút "Xem" — đang gõ thì không bị che bảng việc.
  const link = o.task_link != null ? { label: t("view_task"), run: () => openTask(o.task_link) } : null;
  if (m.text) toast(m.text, m.level || "info", link);
  else if (link) toast("#" + o.task_link, "info", link);
  if (m.reload) setTimeout(() => location.reload(), 600);
  if (m.notify) { S.prefs = Object.assign({}, S.prefs, { notify: m.notify }); askNotifyPermission(); }
  if (o.job != null) { setView("term"); openJob(o.job); }
  if (o.diff != null) DiffView.task(o.diff);
  if (o.plan != null) planModal(o.plan);
  if (o.search != null) { setView("code"); CodeView.search(o.search); }
  if (o.task != null) openTask(o.task);
  if (o.view === "notes" && o.note != null && window.NotesView) NotesView.openNote(o.note);
  if (o.view) setView(o.view);
  if (o.modal === "tags" && window.TD) TD.tagModal();
  if (o.chat) setTimeout(() => chatModal(o.chat), 50);
  if (o.focus != null) setTimeout(() => focusAgent(o.focus), 50);
  if (o.pty != null) ptyModal(o.pty, o.title || "");  // /chat <agent>: tới ô 💬 của agent đó
  if (o.git_ai && window.GitView) GitView.aiMessage();
  if (o.modal === "help") helpModal();
  if (o.modal === "theme") themeModal();
  if (o.modal === "setup" && window.Setup) Setup.open(false);
  if (o.modal === "roles" && window.Setup) Setup.rolesModal();
  if (o.modal === "custom" && window.Setup) Setup.custom();
  if (o.modal === "rules") RulesView.open();
  if (o.modal === "flow" && window.Setup) Setup.flowModal({ onSaved: () => { if (S.view === "custom") Setup.showCustom(); } });
  if ((o.modal === "branches" || o.modal === "stash") && window.GitView) GitView[o.modal]();
  if (o.text) textModal(o.text.title, o.text.body);
  if (o.picker) pickerModal(o.picker);
  if (o.project != null) o.project ? openProject(o.project) : projectModal();
  if (o.prefill) prefill(o.prefill);
  if (o.theme) setThemeMode(o.theme);
  if (o.code && window.CodeView) { setView("code"); CodeView.open(o.code.path, o.code.line); }
}

/* ------------------------------------------------------------------ log */
const TS_RE = /^(\[\d\d:\d\d:\d\d\])\s?(.*)$/;
function lineClass(s) {
  if (s.startsWith("$ ")) return "l-head";
  if (/^\s*(SUMMARY:|✔ Summary)/i.test(s)) return "l-sum";
  if (/(<<<DELEGATE|⇒|➕)/.test(s)) return "l-del";  // khối giao việc / log "➕ Task #… giao cho …"
  if (/(<<<NOTE|📝)/.test(s)) return "l-note";
  if (/<<<ASK/.test(s)) return "l-ask";
  if (/^\s*(✗|error\b|Error\b|ERROR\b|Traceback|fatal:)/.test(s) || /^\[[\d:]+\]\s*✗/.test(s)) return "l-err";
  if (/^\s*(⚠|warning\b|Warning\b|WARN)/.test(s) || /^\[[\d:]+\]\s*⚠/.test(s)) return "l-warn";
  if (/^\[[\d:]+\]\s*(✓|✔|▶|🏁)/.test(s)) return "l-ok";
  if (/^\[[\d:]+\]\s*⚙/.test(s)) return "l-dim";
  if (TS_RE.test(s)) return "l-sys";
  return "";
}
function linkify(html) {
  return html.replace(/(https?:\/\/[^\s<>"']+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
}
function lineHtml(s, st) {
  if (st && (st.fence || st.block || (!TS_RE.test(s) && !s.startsWith("$ ")))) return mdLine(s, st);
  const cls = lineClass(s);
  const m = TS_RE.exec(s);
  const body = m ? `<span class="ts">${esc(m[1])}</span> ${linkify(esc(m[2]))}` : linkify(esc(s));
  return `<div class="l ${cls}">${body || "&nbsp;"}</div>`;
}

/* markdown của agent (log, kết quả, nội dung task) — từng dòng một vì log đến theo dòng;
   st giữ trạng thái giữa các dòng: đang trong ``` hay trong khối <<<NOTE>>>/<<<DELEGATE>>>/<<<ASK>>> */
function mdInline(s) {
  const keep = [];
  const stash = (h) => `\u0000${keep.push(h) - 1}\u0000`;
  s = s.replace(/`([^`]+)`/g, (_, c) => stash(`<code class="md-c">${esc(c)}</code>`))
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, txt, url) => stash(`<a href="${esc(url)}" target="_blank" rel="noopener">${esc(txt)}</a>`));
  return linkify(esc(s))
    .replace(/\*\*(?=\S)(.+?)\*\*/g, "<b>$1</b>")
    .replace(/~~(?=\S)(.+?)~~/g, "<s>$1</s>")
    .replace(/(^|[^\w*])\*(?=[^\s*])([^*]+?)\*(?![\w*])/g, "$1<i>$2</i>")
    .replace(/\u0000(\d+)\u0000/g, (_, i) => keep[+i]);
}
function mdCells(s) {
  return s.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
}
const MD_TSEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
function mdAsk(body) {  // {"question","why","options","recommended"} trọn một dòng -> câu hỏi + phương án (chỉ xem)
  let q;
  try { q = JSON.parse(body); } catch (e) { return null; }
  if (!q || typeof q.question !== "string") return null;
  const opts = Array.isArray(q.options) ? q.options.map(String) : [], rec = String(q.recommended || "");
  const star = `<span class="md-who">★ ${esc(t("recommended"))}</span>`;
  return `<b>${esc(q.question)}</b>${q.why ? `<br><span class="md-ask-why">${esc(String(q.why))}</span>` : ""}`
    + opts.map((o, i) => `<br>${i + 1}. ${esc(o)}${i === opts.indexOf(rec) ? " " + star : ""}`).join("")
    + (rec && !opts.includes(rec) ? `<br>${star}${esc(rec)}` : "");
}
function mdBlockOpen(s, st) {  // <<<NOTE>>> / <<<DELEGATE to=… title=…>>> / <<<ASK>>> — có thể kết thúc ngay trên dòng này
  const m = /<<<(NOTE|DELEGATE|ASK)\b([^>]*)>>>/.exec(s);
  if (!m) return null;
  let rest = s.slice(m.index + m[0].length), head;
  const kind = { NOTE: "note", DELEGATE: "del", ASK: "ask" }[m[1]];
  if (kind === "ask") {
    head = `<span class="md-tag">❓ ${esc(t("md_ask"))}</span>`;
  } else if (kind === "note") {
    const who = /^\s*\[([^\]]+)\]\s*/.exec(rest);
    if (who) rest = rest.slice(who[0].length);
    head = `<span class="md-tag">📝 ${esc(t("md_note"))}</span>${who ? `<span class="md-who">${esc(who[1])}</span>` : ""}`;
  } else {
    const attr = (k) => { const a = new RegExp(k + '="([^"]*)"').exec(m[2]); return a ? a[1] : ""; };
    head = `<span class="md-tag">⇒ ${esc(t("md_delegate"))}</span><span class="md-who">${esc(attr("to"))}</span>${attr("title") ? `<b>${esc(attr("title"))}</b>` : ""}`;
  }
  const end = rest.indexOf("<<<END>>>");
  if (end >= 0) rest = rest.slice(0, end); else st.block = kind;
  const pre = s.slice(0, m.index).trim();
  const ask = kind === "ask" && end >= 0 ? mdAsk(rest.trim()) : null;
  const body = ask || (rest.trim() ? mdInline(rest.trim()) : "");
  return (pre ? `<div class="l">${mdInline(pre)}</div>` : "")
    + `<div class="l md-${kind} md-start${end >= 0 ? " md-end" : ""}">${head}${body ? (kind === "note" ? " " : "<br>") + body : ""}</div>`;
}
function mdLine(s, st) {
  if (st.fence) {  // st.fence = số cấp thụt lề của ``` (khối code nằm trong danh sách) + 1
    const d = `style="--d:${st.fence - 1}"`;
    if (/^\s*```/.test(s)) { st.fence = 0; return `<div class="l md-pre md-pre-end" ${d}></div>`; }
    return `<div class="l md-pre" ${d}>${esc(s.replace(new RegExp(`^ {0,${(st.fence - 1) * 2}}`), "")) || "&nbsp;"}</div>`;
  }
  if (st.block) {
    const end = s.indexOf("<<<END>>>");
    const body = end >= 0 ? s.slice(0, end) : s;
    const cls = `l md-${st.block}${end >= 0 ? " md-end" : ""}`;
    if (end >= 0) st.block = null;
    return `<div class="${cls}">${mdInline(body) || "&nbsp;"}</div>`;
  }
  let m = /^(\s*)```\s*([\w+#.-]*)/.exec(s);
  if (m) {
    st.fence = Math.floor(m[1].length / 2) + 1;
    return `<div class="l md-pre md-pre-start" style="--d:${st.fence - 1}">${m[2] ? `<span class="md-lang">${esc(m[2])}</span>` : ""}</div>`;
  }
  const blk = mdBlockOpen(s, st);
  if (blk) return blk;
  if ((m = /^\s*SUMMARY:\s*(.*)$/.exec(s))) return `<div class="l md-sum"><span class="md-tag">✔ ${esc(t("md_summary"))}</span> ${mdInline(m[1])}</div>`;
  if ((m = /^\s{0,3}(#{1,6})\s+(.*?)[\s#]*$/.exec(s))) return `<div class="l md-h md-h${m[1].length}">${mdInline(m[2])}</div>`;
  if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(s)) return `<div class="l md-hr"></div>`;
  if ((m = /^\s*>\s?(.*)$/.exec(s))) return `<div class="l md-quote">${mdInline(m[1]) || "&nbsp;"}</div>`;
  if ((m = /^(\s*)[-*+]\s+(?:\[([ xX])\]\s+)?(.*)$/.exec(s))) {
    const box = m[2] ? (m[2] === " " ? "☐ " : "☑ ") : "";
    return `<div class="l md-li" style="--d:${Math.floor(m[1].length / 2)}"><span class="md-b">•</span>${box}${mdInline(m[3])}</div>`;
  }
  if ((m = /^(\s*)(\d+)[.)]\s+(.*)$/.exec(s))) {
    return `<div class="l md-li md-ol" style="--d:${Math.floor(m[1].length / 2)}"><span class="md-b">${m[2]}.</span>${mdInline(m[3])}</div>`;
  }
  if (MD_TSEP.test(s) && s.includes("|")) return `<div class="l md-tsep"></div>`;
  if (/^\s*\|.*\|\s*$/.test(s)) return `<div class="l md-tr">${mdCells(s).map((c) => `<span class="md-td">${mdInline(c)}</span>`).join('<span class="md-bar">│</span>')}</div>`;
  const cls = lineClass(s);
  return `<div class="l ${cls}">${mdInline(s) || "&nbsp;"}</div>`;
}
/* cả một đoạn markdown (kết quả, nội dung task): như log, thêm bảng thật cho các dòng | … | liền nhau */
function mdHtml(text) {
  const st = {}, out = [];
  let rows = [];
  const flush = () => {
    if (!rows.length) return;
    const head = rows.length > 1 && MD_TSEP.test(rows[1]);
    const body = rows.filter((r, i) => !(head && i === 1)).map((r, i) => {
      const tag = head && i === 0 ? "th" : "td";
      return `<tr>${mdCells(r).map((c) => `<${tag}>${mdInline(c)}</${tag}>`).join("")}</tr>`;
    });
    out.push(`<div class="md-table"><table>${body.join("")}</table></div>`);
    rows = [];
  };
  for (const s of String(text || "").replace(/\s+$/, "").split("\n")) {
    if (!st.fence && !st.block && /^\s*\|.*\|\s*$/.test(s)) { rows.push(s); continue; }
    flush();
    out.push(mdLine(s, st));
  }
  flush();
  return out.join("");
}
function appendLines(box, lines, max = 4000, md = true) {
  if (!box) return;
  if (!box.childElementCount) box._md = {};  // hộp vừa xoá: bắt đầu lại trạng thái markdown
  const st = md ? box._md || (box._md = {}) : null;
  const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
  box.insertAdjacentHTML("beforeend", lines.map((s) => lineHtml(s, st)).join(""));
  while (box.childElementCount > max) box.firstElementChild.remove();
  if (stick) box.scrollTop = box.scrollHeight;
}
function onLines(items) {  // server gom dòng log / output lệnh ~0,1 giây một lần: chèn DOM một lần mỗi hộp
  const task = [], agents = {}, jobs = [];
  for (const m of items) {
    if (m.k === "job") { if (m.id === S.openJob) jobs.push(m.line); continue; }
    if (S.openTask != null && m.task === S.openTask && S.drawerTab === "log") task.push(m.line);
    if (m.agent) (agents[m.agent] || (agents[m.agent] = [])).push(m.raw != null ? m.raw : m.line);
  }
  if (task.length) {
    S.logs.push(...task);
    if (S.logs.length > 4000) S.logs.splice(0, S.logs.length - 4000);
    appendLines($("#dr-log"), task);
  }
  for (const name in agents) {
    const arr = S.agentLogs[name] || (S.agentLogs[name] = []);
    arr.push(...agents[name]);
    if (arr.length > 300) arr.splice(0, arr.length - 300);
    appendLines($(`[data-mini="${CSS.escape(name)}"]`), agents[name], 300);
  }
  if (jobs.length) appendLines($("#tw-body"), jobs, 5000, false);
}
async function loadLog(tid) {
  const box = $("#dr-log");
  try {
    const r = await (await fetch(`/api/log/${tid}`)).json();
    if (S.openTask !== tid) return;
    S.logs = r.lines;
    if (box) {
      box.innerHTML = r.lines.length ? "" : `<div class="l l-dim">${esc(t("no_log"))}</div>`;
      appendLines(box, r.lines);
      box.scrollTop = box.scrollHeight;
    }
  } catch (e) { /* server đang khởi động lại */ }
}
async function loadAgentTail(name) {
  try {
    const r = await (await fetch(`/api/agent/${encodeURIComponent(name)}`)).json();
    S.agentLogs[name] = r.lines || [];
    const box = $(`[data-mini="${CSS.escape(name)}"]`);
    if (box) { box.innerHTML = ""; appendLines(box, S.agentLogs[name], 300); box.scrollTop = box.scrollHeight; }
  } catch (e) { /* bỏ qua */ }
}

/* ------------------------------------------------------------------ vẽ */
const STATUS_LABEL = (s) => t(s);
function counts() {
  const c = { running: 0, queued: 0, review: 0, failed: 0, draft: 0 };
  for (const x of boardTasks()) {
    if (x.status === "running") c.running++;
    else if (x.status === "queued") c.queued++;
    else if (x.status === "review" || x.status === "conflict" || x.status === "asking") c.review++;
    else if (x.status === "failed" || x.status === "blocked") c.failed++;
    else if (x.status === "draft") c.draft++;
  }
  return c;
}
function render() {
  if (!S.state) return;
  renderTop();
  renderComposerMode();
  if (S.view === "board") { renderGrill(); renderPlan(); renderBoard(); }
  if (S.view === "team") renderTeam();
  if (S.view === "term") renderTerm();
  if (window.TodoView) TodoView.render();  // cả số việc chưa xong trên thanh bên
  if (window.NotesView) NotesView.render();
  if (S.openTask != null) renderDrawer(false);
  if (S.view === "code" && window.CodeView) CodeView.stateChanged();
  renderContinueHint();
}
function renderTop() {
  const st = S.state, c = counts();
  const titles = { board: t("board"), team: t("team"), grid: t("grid"), term: t("terminal"), git: t("git"), code: t("code"), todo: t("todo"), notes: t("notes"), custom: t("custom"), dash: t("dash"), skills: t("skills") };
  $("#view-title").textContent = titles[S.view];
  const chips = [];
  if (c.running) chips.push(`<span class="chip s-running" style="color:var(--running)"><span class="dot"></span>${c.running} ${esc(t("running"))}</span>`);
  if (c.queued) chips.push(`<span class="chip"><span class="dot" style="background:var(--queued)"></span>${c.queued} ${esc(t("queued"))}</span>`);
  if (c.review) chips.push(`<span class="chip warn"><span class="dot"></span>${c.review} ${esc(t("review"))}</span>`);
  if (c.failed) chips.push(`<span class="chip" style="color:var(--failed)"><span class="dot"></span>${c.failed} ${esc(t("failed"))}</span>`);
  if (st.paused) chips.push(`<span class="chip warn">⏸ ${esc(t("paused"))}</span>`);
  chips.push(`<span class="chip">${esc(st.worktree ? t("worktree") : t("shared"))}</span>`);
  $("#chips").innerHTML = chips.join("");
  $("#btn-pause").textContent = st.paused ? "▶ " + t("resume") : "⏸ " + t("pause");
  const active = c.running + c.queued + c.review + c.draft;
  setCount("#count-board", active, c.running > 0);
  const busyAgents = st.agents.filter((a) => a.activities.length).length;
  setCount("#count-team", busyAgents, busyAgents > 0);
  const liveJobs = st.jobs.filter((j) => j.status === "running").length;
  setCount("#count-term", liveJobs || "", liveJobs > 0);
  setCount("#count-git", st.git_changes || 0);
  const pend = pendingCount(), base = "ateam · " + (S.meta.project || "");
  document.title = pend ? `(${pend}) ${base}` : base;
}
function setCount(sel, n, live) {
  const el = $(sel);
  el.textContent = n ? String(n) : "";
  el.classList.toggle("live", !!live);
}

/* hỏi đáp */
function questionHtml(q, n, pick) {  // câu hỏi + phương án (bấm để chọn) — dùng cho /grill và <<<ASK>>>
  const opts = (q.options || []).map((o, i) => `
    <button class="opt${o === q.rec ? " rec" : ""}" data-action="${pick}" data-i="${i}">
      <span class="n">${i + 1}</span><span>${esc(o)}</span>
      ${o === q.rec ? `<span class="rec-tag">★ ${esc(t("recommended"))}</span>` : ""}
    </button>`).join("");
  const recExtra = q.rec && !(q.options || []).includes(q.rec)
    ? `<div class="q-why">★ ${esc(t("recommended"))}: ${esc(q.rec)}</div>` : "";
  return `<div class="q-text"><span class="q-num">${esc(t("grill_q", { n }))} ·</span> ${esc(q.q)}</div>
    ${q.why ? `<div class="q-why">${esc(q.why)}</div>` : ""}
    ${opts ? `<div class="options">${opts}</div>` : ""}${recExtra}
    <div class="muted" style="font-size:12.5px">${esc(t("grill_hint"))}</div>`;
}
function renderAsk(box) {  // agent hỏi giữa task (<<<ASK>>>): cùng khung với /grill
  const a = S.state.ask;
  if (!a) { box.innerHTML = ""; box.dataset.sig = ""; return; }
  const sig = JSON.stringify(a);
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  box.innerHTML = `
    <div class="panel amber">
      <div class="panel-head">
        <div class="panel-title">❓ ${esc(t("ask_title"))}</div>
        <div class="panel-actions">
          <button class="btn sm ghost" data-action="ask-skip">⏭ ${esc(t("ask_skip"))}</button>
          <button class="btn sm" data-action="open-task" data-task="${a.task}">📜 ${esc(t("ask_view"))}</button>
          <button class="btn sm danger" data-action="ask-cancel">${esc(t("ask_cancel"))}</button>
        </div>
      </div>
      <div class="panel-sub">${esc(t("ask_head", { agent: a.agent, id: a.task }))} · ${esc(a.title)}${a.more > 0 ? ` · ${esc(t("ask_more", { n: a.more }))}` : ""}</div>
      <div class="panel-body">${questionHtml(a.question, a.n, "ask-pick")}</div>
    </div>`;
}
function renderGrill() {
  const g = S.state.grill, box = $("#grill");
  if (!g) { renderAsk(box); return; }
  const q = g.question;
  let body;
  if (g.busy) body = `<div class="thinking"><span class="spin"></span>${esc(t("grill_thinking", { lead: S.state.lead }))}</div>`;
  else if (g.error) body = `<div class="err-text">⚠ ${esc(g.error)}</div>`;
  else if (q) body = questionHtml(q, g.n, "grill-pick");
  else body = "";
  const sig = JSON.stringify(g);
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  box.innerHTML = `
    <div class="panel amber">
      <div class="panel-head">
        <div class="panel-title">🔎 ${esc(t("grill_title"))}</div>
        <div class="panel-actions">
          ${q ? `<button class="btn sm ghost" data-action="grill-skip">⏭ ${esc(t("grill_skip"))}</button>` : ""}
          ${!g.busy && !q ? `<button class="btn sm" data-action="grill-retry">↻ ${esc(t("grill_retry"))}</button>` : ""}
          <button class="btn sm danger" data-action="grill-cancel">${esc(t("grill_cancel"))}</button>
          <button class="btn sm success" data-action="grill-done" ${g.busy ? "disabled" : ""}>✓ ${esc(t("grill_done"))}</button>
        </div>
      </div>
      <div class="panel-sub">🎯 #${g.goal} ${esc(g.text)} · ${esc(t("grill_answered", { n: g.answered }))}</div>
      <div class="panel-body">${body}</div>
    </div>`;
}

/* ảnh trong dự án mà nội dung nhắc tới: @ảnh dán (`@.ateam/images/…`, `@"có dấu cách.png"`) hay đường dẫn trần trưởng nhóm
   viết trong prompt task. Hiện ảnh thu nhỏ (qua /api/raw), bấm để xem to; ảnh không có trong dự án thì tự ẩn */
const IMG_EXT = "png|jpe?g|gif|webp|bmp|avif|svg";
const IMG_RE = new RegExp(`(?:^|[\\s(\\[{"'\`])@?(?:"([^"\\n]+\\.(?:${IMG_EXT}))"|((?:[\\w.~-]+/)*[\\w.~-]+\\.(?:${IMG_EXT})))`
  + `(?=$|[\\s)\\]}"'\`,;:!?]|\\.(?:\\s|$))`, "gi");
function imagePaths(text) {
  const seen = new Set();
  for (const m of String(text || "").matchAll(IMG_RE)) seen.add((m[1] || m[2]).replace(/^\.\//, ""));
  return [...seen].slice(0, 12);
}
function imagesHtml(text) {
  const ps = imagePaths(text);
  return ps.length ? `<div class="img-strip">${ps.map((p) => `<button class="img-thumb" data-action="img-view" data-path="${esc(p)}" title="${esc(p)}">
    <img src="/api/raw?path=${encodeURIComponent(p)}" alt="${esc(p)}" loading="lazy"></button>`).join("")}</div>` : "";
}
document.addEventListener("error", (e) => {  // ảnh không tồn tại / ngoài dự án: bỏ ô đó (sự kiện error không nổi bọt)
  const b = e.target.closest && e.target.closest(".img-thumb");
  if (b) b.remove();
}, true);
function imageModal(p) {
  openModal(`${modalHead(`<span class="mono">${esc(p)}</span>`)}<div class="img-full"><a href="/api/raw?path=${encodeURIComponent(p)}" target="_blank" rel="noopener">
    <img src="/api/raw?path=${encodeURIComponent(p)}" alt="${esc(p)}"></a></div>`, { box: "lg" });
}

/* kế hoạch chờ duyệt */
function renderPlan() {
  const box = $("#plan");
  const goals = S.state.goals.filter((x) => x.status === "awaiting");  // mỗi kế hoạch chờ duyệt một khung
  if (!goals.length) { box.innerHTML = ""; delete box.dataset.sig; return; }
  const drafts = (g) => S.state.tasks.filter((x) => x.goal === g.id && x.status === "draft");
  if (S.editing != null && goals.some((g) => drafts(g).some((x) => x.id === S.editing))) return; // đang sửa: không vẽ đè
  const sig = JSON.stringify([goals, goals.map(drafts), [...S.expanded]]);
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  const opts = (sel) => S.agentNames.map((n) => `<option value="${esc(n)}"${n === sel ? " selected" : ""}>${esc(n)}</option>`).join("");
  const row = (x) => `
    <div class="plan-row">
      <div class="plan-line" data-action="plan-toggle" data-task="${x.id}">
        <span class="tid">#${x.id}</span>
        <span class="plan-sel"><select class="agent-select" data-action="plan-assign" data-task="${x.id}">${opts(x.agent)}</select></span>
        <span class="plan-title">${esc(x.title)}${SkillsView.chips(x.skills)}</span>
        <span class="deps">${x.deps.length ? esc(t("after", { v: x.deps.map((d) => "#" + d).join(", ") })) : ""}</span>
        <span class="muted" style="font-size:12px">${esc([x.model, x.effort].filter(Boolean).join(" · "))}</span>
      </div>
      ${S.expanded.has(x.id) ? `<div class="plan-detail">
        ${imagesHtml(x.prompt)}<div class="prompt-box md">${mdHtml(x.prompt)}</div>
        <div class="row-actions"><button class="btn sm" data-action="plan-edit" data-task="${x.id}">✎ ${esc(t("edit"))}</button></div>
      </div>` : ""}
    </div>`;
  box.innerHTML = goals.map((g, i) => {
    const ds = drafts(g);
    return `
    <div class="panel accent">
      <div class="panel-head">
        <div class="panel-title">📋 ${esc(t("plan_title", { id: g.id }))} <span class="badge s-draft">${esc(t("plan_count", { n: ds.length }))}</span></div>
        <div class="panel-actions">
          <button class="btn sm danger" data-action="plan-drop" data-goal="${g.id}">✗ ${esc(t("drop_plan"))}</button>
          <button class="btn sm primary" data-action="plan-approve" data-goal="${g.id}">▶ ${esc(t("approve"))}${i === 0 ? " <kbd>F2</kbd>" : ""}</button>
        </div>
      </div>
      <div class="plan-goal">🎯 ${esc(g.title)}${g.summary ? ` <span class="muted">— ${esc(g.summary)}</span>` : ""}</div>
      <div class="plan-rows" style="margin-top:8px">${ds.map(row).join("")}</div>
    </div>`;
  }).join("");
}
function startEdit(tid) {
  const x = S.state.tasks.find((y) => y.id === tid);
  const row = $(`.plan-line[data-task="${tid}"]`);
  if (!x || !row) return;
  S.editing = tid;
  const det = row.nextElementSibling && row.nextElementSibling.classList.contains("plan-detail")
    ? row.nextElementSibling : row.insertAdjacentElement("afterend", document.createElement("div"));
  det.className = "plan-detail";
  det.innerHTML = `<textarea class="field" id="edit-${tid}">${esc(x.prompt)}</textarea>
    <div class="row-actions">
      <button class="btn sm primary" data-action="plan-save" data-task="${tid}">${esc(t("save"))}</button>
      <button class="btn sm ghost" data-action="plan-unedit">${esc(t("cancel_edit"))}</button>
    </div>`;
  $(`#edit-${tid}`).focus();
}

/* mục tiêu */
function renderGoals() {
  const box = $("#goals"), goals = S.state.goals;
  if (!goals.length) {
    delete box.dataset.sig;
    box.innerHTML = `<div class="empty">
      <div class="empty-ico"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/></svg></div>
      <div class="big">${esc(t("no_goals"))}</div><div>${esc(t("no_goals_hint"))}</div></div>`;
    return;
  }
  if (S.goalFilter != null && !goals.some((g) => g.id === S.goalFilter)) S.goalFilter = null;
  const byGoal = {};
  for (const x of S.state.tasks) if (x.goal != null && x.status !== "draft") (byGoal[x.goal] || (byGoal[x.goal] = [])).push(x);
  const sig = JSON.stringify([goals, S.goalFilter, Object.entries(byGoal).map(([k, ts]) => [k, ts.map((x) => x.status)])]);
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  const cards = goals.slice().reverse().map((g) => {
    const ts = byGoal[g.id] || [];
    const n = ts.length || 1;
    const d = ts.filter((x) => x.status === "done").length, r = ts.filter((x) => x.status === "running").length;
    const b = ts.filter((x) => ["failed", "blocked", "cancelled"].includes(x.status)).length;
    const st = g.busy && !["awaiting", "grilling"].includes(g.status) ? (g.status === "reviewing" ? "reviewing" : "planning") : g.status;
    return `<div class="goal${S.goalFilter === g.id ? " sel" : ""}" data-action="goal-filter" data-goal="${g.id}">
      <div class="goal-head"><span class="goal-id">#${g.id}</span>
        ${badge(st, t("g_" + st), g.busy || st === "running")}
        ${g.round > 1 ? `<span class="muted" style="font-size:12px">${esc(t("round", { n: g.round }))}</span>` : ""}
        ${g.workflow ? `<span class="wf">⚙ ${esc(g.workflow)}</span>` : ""}
      </div>
      <div class="goal-title">${esc(g.title)}</div>
      ${g.summary ? `<div class="goal-sum">${esc(g.summary)}</div>` : ""}
      <div class="goal-foot">
        ${ts.length ? `<div class="progress"><i class="p-done" style="width:${d / n * 100}%"></i><i class="p-run" style="width:${r / n * 100}%"></i><i class="p-bad" style="width:${b / n * 100}%"></i></div><span>${d}/${ts.length}</span>` : ""}
        ${g.followups.length ? `<span>↪ ${esc(t("followups", { n: g.followups.length }))}</span>` : ""}
        ${ts.length ? `<button class="btn sm ghost" data-action="goal-plan" data-goal="${g.id}" style="margin-left:auto" title="${esc(t("goal_plan"))}">📋</button>` : ""}
        ${g.ended ? `<button class="btn sm" data-action="goal-continue" data-goal="${g.id}"${ts.length ? "" : ` style="margin-left:auto"`}>${esc(t("continue"))}</button>` : ""}
        ${g.status === "planning" ? `<button class="btn sm ghost danger" data-action="goal-cancel-plan" data-goal="${g.id}"${ts.length ? "" : ` style="margin-left:auto"`} title="${esc(t("cancel_plan_hint"))}">✕ ${esc(t("cancel_plan"))}</button>` : ""}
      </div>
    </div>`;
  }).join("");
  box.innerHTML = `<div class="goal goal-all${S.goalFilter == null ? " sel" : ""}" data-action="goal-filter" data-goal="">${esc(t("all_goals"))}</div>` + cards;
}

/* 📋 kế hoạch của một mục tiêu — xem lại cả khi đã duyệt / xong. Đọc từ trên xuống: đề bài → kế hoạch của trưởng
   nhóm (bảng các bước, bấm để nhảy tới kết quả) → kết quả từng agent (markdown đầy đủ, prompt thu gọn) → tổng kết */
const PLAN_SOURCES = ["plan", "workflow", "review", "followup", "delegate", "user"];
async function planModal(gid) {
  const r = await request("goal_plan", { goal: gid }, t("busy_loading"));
  const p = r.goal_plan;
  if (!p) return;
  const g = p.goal, ts = p.tasks;
  const src = (x) => { const k = (x.source || "plan").split(":")[0]; return PLAN_SOURCES.includes(k) ? k : "plan"; };
  const srcChip = (x) => ["plan", "workflow"].includes(src(x)) ? ""
    : ` <span class="chip pv-src">${esc(t("src_" + src(x)))}${x.source.startsWith("delegate:") ? " ← " + esc(x.source.slice(9)) : ""}</span>`;
  const after = (x) => x.deps.length ? esc(t("after", { v: x.deps.map((d) => "#" + d).join(", ") })) : "";
  const steps = ts.map((x) => `
    <div class="pv-step" data-jump="${x.id}">
      <span class="tid">#${x.id}</span><span>${agentHtml(x.agent)}</span>
      <span class="pv-step-title">${esc(x.title)}${srcChip(x)}</span>
      <span class="deps">${after(x)}</span>${badge(x.status, STATUS_LABEL(x.status), x.status === "running")}
    </div>`).join("");
  const cards = ts.map((x) => {
    const out = x.result || x.error;
    const meta = [x.model, x.effort].filter(Boolean).join(" · ");
    return `<div class="pv-card s-${esc(x.status)}" id="pv-task-${x.id}">
      <div class="pv-card-head">${agentHtml(x.agent)}<span class="tid">#${x.id}</span>
        <b class="pv-card-title">${esc(x.title)}</b>${meta ? `<span class="muted small">${esc(meta)}</span>` : ""}${SkillsView.chips(x.skills)}
        ${elapsedHtml(x.started, x.finished)}${badge(x.status, STATUS_LABEL(x.status), x.status === "running")}</div>
      <div class="pv-card-body md${x.error && !x.result ? " pv-err" : ""}">${out ? mdHtml(out) : `<span class="muted">${esc(t("no_result"))}</span>`}</div>
      ${imagesHtml(x.result)}
      <details class="pv-prompt"><summary>${esc(t("plan_show_prompt"))}</summary>${imagesHtml(x.prompt)}<div class="prompt-box md">${mdHtml(x.prompt)}</div></details>
    </div>`;
  }).join("");
  const toSkill = g.status === "done" ? `<button class="btn sm" data-to-flow="${g.id}" title="${esc(t("wf_from_goal_hint", { id: g.id }))}">🔀 ${esc(t("wf_from_goal"))}</button>
    <button class="btn sm" data-to-skill="${g.id}" title="${esc(t("sk_from_goal_hint", { id: g.id }))}">💾 ${esc(t("sk_from_goal"))}</button>` : "";
  const m = openModal(`${modalHead("📋 " + esc(t("goal_plan_title", { id: g.id })), toSkill)}<div class="modal-pad">
    <div class="pv-goal md">${mdHtml(g.text)}</div>${imagesHtml(g.text)}
    ${ts.length ? `<div class="pv-sec">📋 ${esc(t("plan_lead"))} <span class="muted">· ${esc(t("plan_count", { n: ts.length }))}</span></div>
      <div class="pv-steps">${steps}</div>
      <div class="pv-sec">🤖 ${esc(t("plan_agents"))}</div>${cards}`
    : `<div class="muted">${esc(t("plan_empty"))}</div>`}
    ${g.summary ? `<div class="pv-sec">✔ ${esc(t("plan_summary"))}</div><div class="pv-summary md">${mdHtml(g.summary)}</div>` : ""}
  </div>`, { box: "lg", cls: "pv" });
  m.addEventListener("click", (e) => {
    const k = e.target.closest("[data-to-skill]");
    if (k) { SkillsView.fromGoal(+k.dataset.toSkill); return; }
    const f = e.target.closest("[data-to-flow]");
    if (f) { Setup.flowFromGoal(+f.dataset.toFlow, f); return; }
    const s = e.target.closest("[data-jump]");
    if (!s) return;
    const card = $("#pv-task-" + s.dataset.jump, m);
    card.scrollIntoView({ behavior: "smooth", block: "start" });
    card.classList.add("flash");
    setTimeout(() => card.classList.remove("flash"), 900);
  });
}

/* kanban */
const COLUMNS = [
  { key: "draft", st: ["draft"], c: "var(--draft)", optional: true },
  { key: "queued", st: ["queued"], c: "var(--queued)" },
  { key: "running", st: ["running"], c: "var(--running)" },
  { key: "review", st: ["review", "conflict", "asking"], c: "var(--review)" },
  { key: "done", st: ["done"], c: "var(--done)" },
  { key: "bad", st: ["failed", "blocked", "cancelled"], c: "var(--failed)" },
];
const boardTasks = () => S.state.tasks.filter((x) => x.source !== "chat");  // lượt chat hiện ở popup 💬 (trang Agents)
function renderKanban() {
  const box = $("#kanban");
  let tasks = boardTasks();
  if (S.goalFilter != null) tasks = tasks.filter((x) => x.goal === S.goalFilter || x.goal == null);  // 📌 task ngoài kế hoạch luôn hiện
  const cols = COLUMNS.filter((c) => !c.optional || tasks.some((x) => c.st.includes(x.status)));
  if (box.childElementCount !== cols.length || box.dataset.cols !== cols.map((c) => c.key).join()) {
    box.dataset.cols = cols.map((c) => c.key).join();
    box.innerHTML = cols.map((c) => `<div class="col" style="--c:${c.c}">
      <div class="col-head"><span class="dot"></span>${esc(t("col_" + c.key))}<span class="n" data-n></span></div>
      <div class="col-body" data-col="${c.key}"></div></div>`).join("");
  }
  for (const c of cols) {
    const list = tasks.filter((x) => c.st.includes(x.status));
    list.sort((a, b) => (c.key === "done" || c.key === "bad") ? (b.finished || 0) - (a.finished || 0) : a.id - b.id);
    const body = $(`[data-col="${c.key}"]`, box);
    body.previousElementSibling.querySelector("[data-n]").textContent = list.length;
    patchList(body, list, (x) => {
      const last = x.status === "running" ? S.live[x.id] || "" : "";
      return [JSON.stringify([x.status, x.title, x.error, x.agent, x.model, x.effort, x.deps, x.goal, x.started,
        x.finished, last, S.openTask === x.id]), () => cardHtml(x, last)];
    }, `<div class="col-empty">${esc(t("empty_col"))}</div>`);
  }
}
/* vẽ danh sách theo khoá: chỉ dựng lại phần tử có chữ ký đổi, giữ nguyên phần còn lại (không mất hover/chọn chữ,
   không vẽ lại 400 thẻ mỗi lần một task đổi trạng thái). item(x) → [chữ ký, () => html]; x.id là khoá. */
function patchList(box, list, item, emptyHtml) {
  if (!list.length) {
    if (!box._empty) { box.innerHTML = emptyHtml; box._empty = true; box._sig = new Map(); }
    return;
  }
  if (box._empty || !box._sig) { box.innerHTML = ""; box._empty = false; box._sig = new Map(); }
  const old = new Map(), sigs = new Map();
  for (const el of box.children) old.set(el.dataset.key, el);
  let ref = box.firstElementChild;
  for (const x of list) {
    const k = String(x.id), [sig, html] = item(x);
    let el = old.get(k);
    old.delete(k);
    if (!el || box._sig.get(k) !== sig) {
      if (el) { if (el === ref) ref = ref.nextElementSibling; el.remove(); }
      const tpl = document.createElement("template");
      tpl.innerHTML = html().trim();
      el = tpl.content.firstElementChild;
      el.dataset.key = k;
    }
    sigs.set(k, sig);
    if (el === ref) ref = ref.nextElementSibling;
    else box.insertBefore(el, ref);
  }
  for (const el of old.values()) el.remove();
  box._sig = sigs;
}
function cardHtml(x, last) {
  const meta = [x.model, x.effort].filter(Boolean).join(" · ");
  return `<div class="card s-${x.status}${S.openTask === x.id ? " sel" : ""}" data-action="open-task" data-task="${x.id}">
    <div class="card-top"><span class="tid">#${x.id}</span>${badge(x.status, STATUS_LABEL(x.status), x.status === "running")}${elapsedHtml(x.started, x.finished)}</div>
    <div class="card-title">${esc(x.title)}</div>
    ${x.status === "running" && last ? `<div class="card-last">${esc(last)}</div>` : ""}
    ${x.error && ["failed", "blocked", "conflict"].includes(x.status) ? `<div class="card-err">${esc(x.error)}</div>` : ""}
    <div class="card-foot">${agentHtml(x.agent)}${meta ? `<span class="meta">${esc(meta)}</span>` : ""}
      ${x.deps.length ? `<span class="deps">↳ ${x.deps.map((d) => "#" + d).join(", ")}</span>` : ""}
      ${x.goal ? `<span class="meta" style="margin-left:auto">🎯 #${x.goal}</span>` : `<span class="meta adhoc" style="margin-left:auto">📌 ${esc(t("bl_adhoc_short"))}</span>`}</div>
  </div>`;
}

/* bảng việc dạng danh sách (mặc định): nhóm 📌 ngoài kế hoạch (task giao tay, goal = null) luôn ở trên cùng, rồi từng
   kế hoạch mới nhất trước — xem theo kế hoạch mà không phải lọc, nên task ngoài kế hoạch không bao giờ bị lọc mất.
   Kế hoạch đã kết thúc mặc định thu gọn; bấm tiêu đề nhóm để mở/đóng (nhớ trong localStorage). ▦ Kanban giữ làm chế độ phụ. */
const ADHOC = "adhoc";
const NEED_YOU = ["review", "conflict", "asking", "failed", "blocked"];
/* việc chờ bạn (cột phải), mới trước; task lỗi / bị chặn trong kế hoạch trưởng nhóm đã chốt hoàn thành thì thôi */
function needYou(tasks, goals) {
  const done = new Set(goals.filter((g) => g.status === "done").map((g) => g.id));
  return tasks.filter((x) => NEED_YOU.includes(x.status) && !(["failed", "blocked"].includes(x.status) && done.has(x.goal)))
    .sort((a, b) => b.id - a.id);
}
function loadBoardPrefs() {
  try {
    S.board = localStorage.getItem("ateam-board") === "kanban" ? "kanban" : "list";
    S.fold = JSON.parse(localStorage.getItem("ateam-board-fold") || "{}") || {};
  } catch (e) { /* chặn lưu: dùng mặc định */ }
}
loadBoardPrefs();
function setBoardMode(mode) {
  S.board = mode === "kanban" ? "kanban" : "list";
  try { localStorage.setItem("ateam-board", S.board); } catch (e) { /* chặn lưu */ }
  renderBoard();
}
function isFolded(key, g) { return key in S.fold ? !!S.fold[key] : !!(g && g.ended); }
function toggleFold(key) {
  const g = key === ADHOC ? null : S.state.goals.find((x) => String(x.id) === key) || { ended: true };
  S.fold[key] = !isFolded(key, g);
  const ids = new Set(S.state.goals.map((x) => String(x.id)));  // không giữ mãi khoá của kế hoạch đã dọn
  for (const k of Object.keys(S.fold)) if (k !== ADHOC && !ids.has(k) && k !== key) delete S.fold[k];
  try { localStorage.setItem("ateam-board-fold", JSON.stringify(S.fold)); } catch (e) { /* chặn lưu */ }
  renderBoardList();
}
function boardJump(key) {
  if (S.board !== "list") setBoardMode("list");
  if (isFolded(key, key === ADHOC ? null : S.state.goals.find((x) => String(x.id) === key))) toggleFold(key);
  const el = $(`#blist [data-grp="${key}"]`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 900);
}
function renderBoard() {
  const list = S.board === "list";
  renderBoardBar();
  $("#goals").classList.toggle("hidden", list);
  $("#kanban").classList.toggle("hidden", list);
  $("#blist").classList.toggle("hidden", !list);
  if (list) renderBoardList(); else { renderGoals(); renderKanban(); }
}
/* dữ liệu chung của thanh công cụ + danh sách: task theo nhóm và các kế hoạch (cả kế hoạch cũ đã rời ảnh chụp
   nhưng còn task trên bảng — hiện tiêu đề rút gọn) */
function boardGroups() {
  const adhoc = [], by = new Map();
  for (const x of boardTasks()) {
    if (x.status === "draft") continue;  // task nháp ở khung Duyệt kế hoạch phía trên
    if (x.goal == null) adhoc.push(x);
    else { if (!by.has(x.goal)) by.set(x.goal, []); by.get(x.goal).push(x); }
  }
  const known = new Map(S.state.goals.map((g) => [g.id, g]));
  const ids = new Set([...known.keys(), ...by.keys()]);
  const goals = [...ids].sort((a, b) => b - a)
    .map((id) => known.get(id) || { id, title: "", status: "done", ended: true, followups: [], stub: true });
  const rank = (x) => ["running", "asking", "review", "conflict", "queued", "failed", "blocked"].indexOf(x.status);
  adhoc.sort((a, b) => { const ra = rank(a), rb = rank(b); return (ra < 0) - (rb < 0) || b.id - a.id; });  // việc dở lên trước
  return { adhoc, goals, by };
}
function renderBoardBar() {
  const box = $("#board-bar");
  const { adhoc, goals, by } = boardGroups();
  const chips = S.board !== "list" ? "" : [`<button class="bchip pin" data-action="board-jump" data-key="${ADHOC}">📌 ${esc(t("bl_adhoc"))} <span class="n">${adhoc.length}</span></button>`]
    .concat(goals.filter((g) => by.has(g.id) || !g.ended).slice(0, 8).map((g) => {
      const ts = by.get(g.id) || [], d = ts.filter((x) => x.status === "done").length;
      return `<button class="bchip" data-action="board-jump" data-key="${g.id}" title="${esc(g.title)}">#${g.id}${ts.length ? ` <span class="bmini"><i style="width:${d / ts.length * 100}%"></i></span><span class="n">${d}/${ts.length}</span>` : ""}</button>`;
    })).join("");
  const html = `<span class="bseg">
      <button class="${S.board === "list" ? "on" : ""}" data-action="board-mode" data-mode="list">≡ ${esc(t("bl_list"))}</button>
      <button class="${S.board === "kanban" ? "on" : ""}" data-action="board-mode" data-mode="kanban">▦ ${esc(t("bl_kanban"))}</button></span>
    ${chips ? `<span class="muted small">${esc(t("bl_jump"))}</span>${chips}` : ""}`;
  if (box._html !== html) { box._html = html; box.innerHTML = html; }
}
function rowHtml(x) {
  const last = x.status === "running" ? S.live[x.id] || "" : "";
  const sub = x.error && ["failed", "blocked", "conflict"].includes(x.status) ? `<span class="br-err">${esc(x.error)}</span>`
    : last ? `<span class="br-last">${esc(last)}</span>` : "";
  const meta = [x.model, x.effort].filter(Boolean).join(" · ");
  return `<div class="tbrow s-${x.status}${S.openTask === x.id ? " sel" : ""}" data-action="open-task" data-task="${x.id}">
    ${badge(x.status, STATUS_LABEL(x.status), x.status === "running")}<span class="tid">#${x.id}</span>
    <span class="br-title"><span class="br-t">${esc(x.title)}</span>${sub}</span>
    <span class="br-agent">${agentHtml(x.agent)}${meta ? `<span class="meta">${esc(meta)}</span>` : ""}</span>
    <span class="br-deps">${x.deps.length ? "↳ " + x.deps.map((d) => "#" + d).join(", ") : ""}</span>
    ${elapsedHtml(x.started, x.finished) || `<span class="time"></span>`}</div>`;
}
function countsHtml(ts) {
  return COLUMNS.filter((c) => !c.optional).map((c) => {
    const n = ts.filter((x) => c.st.includes(x.status)).length;
    return n ? `<span class="bcount" style="--c:${c.c}" title="${esc(t("col_" + c.key))}">● ${n}</span>` : "";
  }).join("");
}
function goalHeadHtml(g, ts, folded) {
  const n = ts.length || 1, d = ts.filter((x) => x.status === "done").length, r = ts.filter((x) => x.status === "running").length;
  const b = ts.filter((x) => ["failed", "blocked", "cancelled"].includes(x.status)).length;
  const st = g.busy && !["awaiting", "grilling"].includes(g.status) ? (g.status === "reviewing" ? "reviewing" : "planning") : g.status;
  return `<div class="bl-gh" data-action="board-fold" data-key="${g.id}">
    <span class="chev">${folded ? "▸" : "▾"}</span><span class="goal-id">🎯 #${g.id}</span>
    ${g.stub ? "" : badge(st, t("g_" + st), g.busy || st === "running")}
    ${g.round > 1 ? `<span class="muted small">${esc(t("round", { n: g.round }))}</span>` : ""}
    ${g.workflow ? `<span class="wf">⚙ ${esc(g.workflow)}</span>` : ""}
    <span class="bl-title">${esc(g.title)}</span>
    ${ts.length ? `<span class="progress bl-prog"><i class="p-done" style="width:${d / n * 100}%"></i><i class="p-run" style="width:${r / n * 100}%"></i><i class="p-bad" style="width:${b / n * 100}%"></i></span><span class="muted small mono">${d}/${ts.length}</span>` : ""}
    ${g.followups && g.followups.length ? `<span class="muted small">↪ ${esc(t("followups", { n: g.followups.length }))}</span>` : ""}
    <span class="sp"></span>${folded ? countsHtml(ts) : ""}
    ${ts.length ? `<button class="btn sm ghost" data-action="goal-plan" data-goal="${g.id}" title="${esc(t("goal_plan"))}">📋</button>` : ""}
    ${g.ended && !g.stub ? `<button class="btn sm" data-action="goal-continue" data-goal="${g.id}">${esc(t("continue"))}</button>` : ""}
    ${g.status === "planning" ? `<button class="btn sm ghost danger" data-action="goal-cancel-plan" data-goal="${g.id}" title="${esc(t("cancel_plan_hint"))}">✕ ${esc(t("cancel_plan"))}</button>` : ""}
  </div>`;
}
function goalEmptyHtml(g) {
  const k = { planning: "bl_planning", awaiting: "bl_awaiting", grilling: "bl_grilling" }[g.status] || "bl_no_tasks";
  return `<div class="bl-empty">${esc(t(k))}</div>`;
}
/* vẽ một danh sách dòng theo khoá (giữ hover/chọn chữ, chỉ dựng lại dòng đổi) */
function patchRows(box, list, emptyHtml) {
  patchList(box, list, (x) => {
    const last = x.status === "running" ? S.live[x.id] || "" : "";
    return [JSON.stringify([x.status, x.title, x.error, x.agent, x.model, x.effort, x.deps, x.started, x.finished, last,
      S.openTask === x.id]), () => rowHtml(x)];
  }, emptyHtml);
}
function renderBoardList() {
  const box = $("#blist");
  if (!box._built) {  // khung cố định: nhóm 📌 (ô giao task giữ nguyên khi vẽ lại) + các kế hoạch + cột phải
    box._built = true;
    box.innerHTML = `<div class="bl-main">
        <div class="bl-grp bl-pin" data-grp="${ADHOC}"><div class="bl-gh" id="bl-adhoc-head" data-action="board-fold" data-key="${ADHOC}"></div>
          <div class="bl-body" id="bl-adhoc-body"><div class="blist-rows" id="bl-adhoc-rows"></div>
            <form class="bl-add" id="bl-add"><span class="muted">＋</span><input id="bl-add-text" autocomplete="off">
              <select id="bl-add-agent"></select><button class="btn sm primary" type="submit"></button></form></div></div>
        <div id="bl-goals"></div></div>
      <div class="bl-side" id="bl-side"></div>`;
    $("#bl-add-text").placeholder = t("bl_add_ph");
    $("#bl-add button").textContent = t("bl_add");
    $("#bl-add").addEventListener("submit", (e) => { e.preventDefault(); addAdhoc(); });
  }
  const { adhoc, goals, by } = boardGroups();
  // 📌 ngoài kế hoạch
  const pinFold = isFolded(ADHOC, null);
  const head = `<span class="chev">${pinFold ? "▸" : "▾"}</span><span class="pin-ico">📌</span><span class="bl-title">${esc(t("bl_adhoc"))}</span>
    <span class="muted small mono">${adhoc.length}</span><span class="muted small bl-hint">· ${esc(t("bl_adhoc_hint"))}</span>
    <span class="sp"></span>${pinFold ? countsHtml(adhoc) : ""}`;
  const hb = $("#bl-adhoc-head");
  if (hb._html !== head) { hb._html = head; hb.innerHTML = head; }
  $("#bl-adhoc-body").classList.toggle("hidden", pinFold);
  patchRows($("#bl-adhoc-rows"), adhoc, "");
  renderAdhocAgents();
  // kế hoạch: mỗi nhóm một khối, khoá theo id (patchList ở cấp nhóm, dòng bên trong vẽ theo khoá)
  const gbox = $("#bl-goals");
  if (!goals.length && !adhoc.length) {
    gbox.innerHTML = `<div class="empty"><div class="big">${esc(t("no_goals"))}</div><div>${esc(t("no_goals_hint"))}</div></div>`;
    gbox._empty = true; gbox._sig = new Map();
  } else {
    if (gbox._empty) { gbox.innerHTML = ""; gbox._empty = false; gbox._sig = new Map(); }
    const old = new Map([...gbox.children].map((el) => [el.dataset.grp, el]));
    let ref = gbox.firstElementChild;
    for (const g of goals) {
      const ts = by.get(g.id) || [], folded = isFolded(String(g.id), g), k = String(g.id);
      let el = old.get(k);
      old.delete(k);
      if (!el) {
        el = document.createElement("div");
        el.className = "bl-grp";
        el.dataset.grp = k;
        el.innerHTML = `<div class="bl-gh-wrap"></div><div class="bl-body"><div class="blist-rows"></div></div>`;
      }
      const head = goalHeadHtml(g, ts, folded), hw = el.firstElementChild;
      if (hw._html !== head) { hw._html = head; hw.innerHTML = head; }
      el.classList.toggle("folded", folded);
      el.lastElementChild.classList.toggle("hidden", folded);
      if (!folded) patchRows(el.lastElementChild.firstElementChild, ts, goalEmptyHtml(g));
      if (el === ref) ref = ref.nextElementSibling;
      else gbox.insertBefore(el, ref);
    }
    for (const el of old.values()) el.remove();
  }
  renderBoardSide(adhoc, by, goals);
}
function renderAdhocAgents() {
  const sel = $("#bl-add-agent"), names = S.agentNames;
  if (sel._sig === names.join()) return;
  sel._sig = names.join();
  let last = "";
  try { last = localStorage.getItem("ateam-adhoc-agent") || ""; } catch (e) { /* chặn lưu */ }
  const cur = sel.value || last;
  sel.innerHTML = names.map((n) => `<option value="${esc(n)}">${esc(n)}${n === S.state.lead ? " ★" : ""}</option>`).join("");
  if (names.includes(cur)) sel.value = cur;
}
/* giao task ngoài kế hoạch ngay trong nhóm 📌 — cùng lệnh /task <agent> <nội dung> như ô nhập dưới cùng */
async function addAdhoc() {
  const inp = $("#bl-add-text"), agent = $("#bl-add-agent").value, text = inp.value.trim();
  if (!text || !agent) { inp.focus(); return; }
  try { localStorage.setItem("ateam-adhoc-agent", agent); } catch (e) { /* chặn lưu */ }
  inp.value = "";
  const r = await request("submit", { text: `/task ${agent} ${text}` }, t("busy_cmd", { v: "/task" }));
  if (r && r.level === "error") inp.value = text;  // giữ chữ để sửa lại
  inp.focus();
}
function renderBoardSide(adhoc, by, goals) {
  const all = adhoc.concat(...by.values());
  const stats = COLUMNS.filter((c) => !c.optional).map((c) =>
    `<div class="bstat" style="--c:${c.c}"><div class="v">${all.filter((x) => c.st.includes(x.status)).length}</div><div class="k">${esc(t("col_" + c.key))}</div></div>`).join("")
    + `<div class="bstat"><div class="v">${by.size}</div><div class="k">${esc(t("bl_plans"))}</div></div>`;
  const need = needYou(all, goals);
  const btns = (x) => ["review", "conflict"].includes(x.status)
    ? `<button class="btn sm primary" data-action="diff" data-task="${x.id}">Δ ${esc(t("diff"))}</button>${x.status === "review" ? `<button class="btn sm" data-action="merge" data-task="${x.id}">✓ ${esc(t("merge"))}</button>` : ""}`
    : x.status === "asking" ? `<button class="btn sm primary" data-action="open-task" data-task="${x.id}">${esc(t("ask_view"))}</button>`
    : `<button class="btn sm" data-action="retry" data-task="${x.id}">↻ ${esc(t("retry"))}</button><button class="btn sm ghost" data-action="reassign" data-task="${x.id}">${esc(t("reassign"))}</button>`;
  const needs = need.map((x) => `<div class="bneed">
      <div class="bneed-top">${badge(x.status, STATUS_LABEL(x.status))}<span class="tid">#${x.id}</span>
        <span class="muted small mono" style="margin-left:auto">${x.goal ? "🎯 #" + x.goal : "📌 " + esc(t("bl_adhoc_short"))}</span></div>
      <div class="bneed-t" data-action="open-task" data-task="${x.id}">${esc(x.title)}</div><div class="bneed-acts">${btns(x)}</div></div>`).join("");
  const html = `<div class="bbox"><div class="bbox-h">${esc(t("bl_overview"))}</div><div class="bstats">${stats}</div></div>
    <div class="bbox${need.length ? "" : " none"}"><div class="bbox-h">${esc(t("bl_need"))}<span class="sp"></span>${need.length}</div>
      ${needs || `<div class="bl-empty">${esc(t("bl_need_none"))}</div>`}</div>`;
  const box = $("#bl-side");
  if (box._html !== html) { box._html = html; box.innerHTML = html; }
}

/* agents: block ⚡ Vai trò (sửa CLI · model · effort ngay trên trang, kèm trạng thái + chat của agent giữ vai trò) và block
   agent tuỳ chỉnh / ngoài vai trò; chat 💬 mở popup riêng */
function renderTeam() {
  const box = $("#team"), rolesBox = $("#team-roles"), cu = S.custom;
  const custom = new Set(cu ? cu.agents.map((x) => x.name) : []);
  const active = new Set(S.state.agents.map((a) => a.name));
  const sig = JSON.stringify(S.state.agents.map((a) => [a.name, a.model, a.effort, a.lead, a.role]));
  if (rolesBox._sig !== sig && window.Setup) {  // đội đổi (lưu vai trò, /setup…) → nạp lại bảng (bỏ qua khi đang sửa dở)
    rolesBox._sig = sig;
    Setup.rolesPanel($("#roles-head"), rolesBox, () => { if (S.view === "team") renderTeam(); });
  }
  const btn = (act, name, label, cls = "", title = "") => `<button class="btn sm ${cls}" type="button" data-action="${act}" data-agent="${esc(name)}"${title ? ` title="${esc(title)}" aria-label="${esc(title)}"` : ""}>${label}</button>`;
  const editBtns = (name) => custom.has(name) ? btn("agent-edit", name, esc(t("edit")), "ghost") + btn("agent-del", name, esc(t("remove")), "ghost danger") : "";
  const status = (a) => !a.installed ? badge("failed", t("not_installed"))
    : a.cooldown ? badge("review", t("cooldown", { v: a.cooldown }))
    : a.activities.length ? badge("running", t("agent_running", { n: a.activities.length }), true) : badge("queued", t("idle"));
  const actHtml = (a) => { const act = a.activities[0];
    return act ? `<span class="act-mini" ${act.task_id ? `data-action="open-task" data-task="${act.task_id}"` : ""}>${act.task_id ? "#" + act.task_id + " " : ""}${esc(act.title)}${elapsedHtml(act.started)}</span>` : ""; };
  const chatBtns = (a) => btn("agent-chat", a.name, "💬 " + esc(t("ag_chat")), "", t("ag_chat")) + btn("agent-term", a.name, "⌨", "ghost", t("open_term"));
  const byName = new Map(S.state.agents.map((a) => [a.name, a]));
  const roleRows = $$(".role-row", rolesBox), holders = new Set();
  for (const row of roleRows) {  // chỉ vẽ lại phần sống, không đụng các ô chọn đang sửa
    const a = byName.get(row.dataset.agent), act = $(".ag-act", row), live = $(".role-live", row);
    if (a) holders.add(a.name);
    row.classList.toggle("busy", !!(a && a.activities.length));
    row.classList.toggle("cool", !!(a && a.cooldown));
    const h = a ? actHtml(a) || `<span class="muted">${esc(act.dataset.desc)}</span>` : `<span class="muted">${esc(act.dataset.desc)}</span>`;
    const l = a ? `${status(a)}<div class="ag-btns">${chatBtns(a)}</div>` : "";
    if (act._h !== h) { act._h = h; act.innerHTML = h; }
    if (live._h !== l) { live._h = l; live.innerHTML = l; }
  }
  if (!roleRows.length) return;  // chờ bảng vai trò nạp xong mới biết agent nào ngoài vai trò
  const rows = S.state.agents.filter((a) => !holders.has(a.name)).map((a) => `<div class="ag-row${a.activities.length ? " busy" : ""}${a.cooldown ? " cool" : ""}" data-agent="${esc(a.name)}">
      <span class="av lg" style="--h:${hue(a.name)}">${esc(a.name[0])}</span>
      <div class="ag-main"><div class="agent-name">${esc(a.name)}${a.lead ? `<span class="lead-tag">★ ${esc(t("lead"))}</span>` : ""}${custom.has(a.name) ? `<span class="cu-tag">${esc(t("ag_custom"))}</span>` : ""}</div>
        <div class="ag-role">${esc(a.role || "")}</div></div>
      <button class="ag-model" type="button" data-action="agent-pick" data-agent="${esc(a.name)}" title="${esc(t("pick_hint"))}">${esc([a.model || t("default_value"), a.effort].filter(Boolean).join(" · "))}</button>
      <div class="ag-act">${actHtml(a)}</div>
      ${status(a)}
      <div class="ag-btns">${chatBtns(a)}${editBtns(a.name)}</div>
    </div>`);
  const off = cu ? cu.agents.filter((x) => !active.has(x.name)) : [];
  const offRows = off.map((x) => `<div class="ag-row off" data-agent="${esc(x.name)}">
      <span class="av lg" style="--h:${hue(x.name)}">${esc(x.name[0])}</span>
      <div class="ag-main"><div class="agent-name">${esc(x.name)}<span class="cu-tag">${esc(t("ag_custom"))}</span></div>
        <div class="ag-role mono">${esc(x.argv)}</div></div>
      <span class="ag-model muted">${x.installed ? "" : "✗ " + esc(t("not_installed"))}</span><div class="ag-act"></div>
      ${badge("cancelled", t("ag_off"))}
      <div class="ag-btns">${editBtns(x.name)}</div></div>`);
  const all = rows.concat(offRows);
  const html = all.length ? `<div class="ag-list">${all.join("")}</div>${offRows.length ? `<div class="muted small ag-note">${esc(t("ag_off_hint"))}</div>` : ""}`
    : cu ? `<div class="muted small">${esc(t("cu_no_agents"))}</div>` : "";
  if (box._html !== html) { box._html = html; box.innerHTML = html; }
}
async function loadCustom() {
  try { S.custom = await (await fetch("/api/custom")).json(); } catch (e) { return; }
  if (S.view === "team" && S.state) renderTeam();
}

document.addEventListener("submit", (e) => {  // ô 💬 trên thẻ agent
  const f = e.target.closest("form[data-chat]");
  if (!f) return;
  e.preventDefault();
  const inp = $(".chat-in", f), text = inp.value.trim();
  if (!text) return;
  if (text === "/term" || text === "/terminal") { inp.value = ""; agentTerminal(f.dataset.chat); return; }
  if (text === "/focus") { inp.value = ""; return; }  // đã ở popup chat
  if (send("chat", { agent: f.dataset.chat, text })) inp.value = "";
});

/* ⌨ "Mở trong terminal": CLI thật của agent (tiếp tục phiên chat) trong xterm.js — nạp khi dùng lần đầu */
function loadScript(src) {
  return new Promise((ok, fail) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = fail; document.head.appendChild(s); });
}
let termLib = null;
function loadTerm() {
  if (!termLib) {
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = "/static/vendor/xterm.css";
    document.head.appendChild(l);
    termLib = loadScript("/static/vendor/xterm.js").then(() => loadScript("/static/vendor/xterm-fit.js"));
  }
  return termLib;
}
async function agentTerminal(agent) {
  try { await loadTerm(); } catch (e) { toast(t("disconnected"), "error"); return; }
  send("pty_open", { agent, rows: 30, cols: 100 });
}
const PTY_KEYS = [["Esc", "\x1b"], ["Tab", "\t"], ["⇧Tab", "\x1b[Z"], ["Ctrl+C", "\x03"], ["↑", "\x1b[A"], ["↓", "\x1b[B"], ["Enter", "\r"]];
function ptyModal(id, title) {
  const m = openModal(`${modalHead("⌨ " + esc(title))}<div class="pty-box"></div>
    <div class="pty-keys">${PTY_KEYS.map(([k], i) => `<button class="btn sm ghost" data-k="${i}">${esc(k)}</button>`).join("")}</div>`,
    { box: "lg", cls: "pty", sticky: true, onClose: () => { send("pty_close", { id }); delete S.ptys[id]; } });
  const box = $(".pty-box", m), cs = getComputedStyle(document.documentElement);
  const term = new Terminal(Object.assign({ cursorBlink: true, fontSize: 13, scrollback: 5000,
    fontFamily: cs.getPropertyValue("--mono").trim() || "monospace" }, termOptions()));
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(box);
  S.ptys[id] = term;
  term.onData((data) => send("pty_in", { id, data }));
  term.onResize(({ rows, cols }) => send("pty_resize", { id, rows, cols }));
  const refit = () => { try { fit.fit(); } catch (e) { /* đang đóng */ } };
  new ResizeObserver(refit).observe(box);
  refit();
  send("pty_resize", { id, rows: term.rows, cols: term.cols });
  m.addEventListener("click", (e) => {  // phím khó gõ trên điện thoại
    const b = e.target.closest("[data-k]");
    if (b) { send("pty_in", { id, data: PTY_KEYS[+b.dataset.k][1] }); term.focus(); }
  });
  term.focus();
}
function ptyData(m) {
  const term = S.ptys[m.id];
  if (!term) return;
  const bin = atob(m.data), bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  term.write(bytes);
}
function ptyExit(m) {
  const term = S.ptys[m.id];
  if (term) term.write(`\r\n\x1b[2m[${esc(t("pty_exit", { rc: m.rc }))}]\x1b[0m\r\n`);
}
/* 💬 chat với một agent: popup có log trực tiếp của agent (S.agentLogs) + ô nhắn — mỗi tin một lượt --resume */
function chatModal(agent) {
  if (!agent || !S.state || !S.state.agents.some((a) => a.name === agent)) return;
  const open = $(`.modal.chat form[data-chat="${CSS.escape(agent)}"]`);
  if (open) { $(".chat-in", open).focus(); return; }
  const m = openModal(`${modalHead("💬 " + esc(agent))}<div class="chat-pop">
      <div class="mini-log log" data-mini="${esc(agent)}"></div>
      <form class="chat-row" data-chat="${esc(agent)}">
        <input class="field one chat-in" autocomplete="off" placeholder="${esc(t("chat_ph", { agent }))}">
        <button class="btn sm primary" type="submit">${esc(t("chat_send"))}</button>
        <button class="btn sm ghost" type="button" data-action="agent-term" data-agent="${esc(agent)}" title="${esc(t("open_term"))}" aria-label="${esc(t("open_term"))}">⌨</button>
      </form></div>`, { box: "lg", cls: "chat" });
  const log = $(".mini-log", m);
  if (S.agentLogs[agent]) { appendLines(log, S.agentLogs[agent], 300); log.scrollTop = log.scrollHeight; }
  else loadAgentTail(agent);
  setTimeout(() => $(".chat-in", m).focus(), 40);
}
function focusAgent(agent) { chatModal(agent || (S.state.agents.find((a) => a.lead) || {}).name); }
function focusChat(agent) { chatModal(agent); }

/* terminal */
function renderTerm() {
  const box = $("#term"), jobs = S.state.jobs.slice().reverse();
  if (S.openJob == null && jobs.length) S.openJob = jobs[0].id;
  const job = jobs.find((j) => j.id === S.openJob);
  if (!box.firstElementChild) {
    box.innerHTML = `<div class="jobs" id="jobs"></div><div class="termwin"><div class="termwin-head" id="tw-head"></div><div class="termwin-body log" id="tw-body"></div></div>`;
  }
  const label = (j) => ({ running: t("j_running"), done: t("j_done"), failed: t("j_failed"), stopped: t("j_stopped") }[j.status]);
  const scripts = (S.scripts || []).slice(0, 14).map((s) => `<button class="script" data-action="run-script" data-cmd="${esc(s.cmd)}"><b>${esc(s.cmd)}</b><span>${esc(s.desc)}</span></button>`).join("");
  $("#jobs").innerHTML = `<div class="jobs-head">${esc(t("jobs"))}</div>` + (jobs.length ? jobs.map((j) => `
    <div class="job${j.id === S.openJob ? " sel" : ""}" data-action="open-job" data-job="${j.id}">
      <div class="job-cmd">${j.status === "running" ? '<span class="spin" style="--c:var(--running);width:11px;height:11px"></span>' : ""}${esc(j.cmd)}</div>
      <div class="job-meta">${badge(j.status === "stopped" ? "cancelled" : j.status === "running" ? "running" : j.status, label(j))}${elapsedHtml(j.started, j.finished)}
        ${j.ports.map((p) => `<a class="port" href="http://localhost:${p}" target="_blank" rel="noopener">:${p}</a>`).join("")}</div>
    </div>`).join("") : `<div class="panel-sub" style="padding:4px 16px 8px">${esc(t("no_jobs_hint"))}</div>`)
    + (scripts ? `<div class="jobs-head">${esc(t("scripts"))}</div><div class="scripts">${scripts}</div>` : "");
  const head = $("#tw-head");
  const sig = job ? JSON.stringify([job.id, job.status, job.ports]) : "";
  if (head.dataset.sig !== sig) {
    head.dataset.sig = sig;
    head.innerHTML = job ? `<span class="lights"><i></i><i></i><i></i></span><span class="cmd">$ ${esc(job.cmd)}</span>
      ${job.ports.map((p) => `<a class="port" href="http://localhost:${p}" target="_blank" rel="noopener">localhost:${p}</a>`).join("")}
      <span style="margin-left:auto;display:flex;gap:6px">
        ${job.status === "running" ? `<button class="btn sm" data-action="job" data-act="stop" data-job="${job.id}">■ ${esc(t("stop"))}</button>` : ""}
        <button class="btn sm" data-action="job" data-act="restart" data-job="${job.id}">↻ ${esc(t("restart"))}</button>
        ${job.status !== "running" ? `<button class="btn sm" data-action="job" data-act="remove" data-job="${job.id}">✕ ${esc(t("remove"))}</button>` : ""}
      </span>` : `<span class="lights"><i></i><i></i><i></i></span><span class="cmd">${esc(t("no_jobs"))}</span>`;
    if (job && job.status !== "running" && job.rc != null && !$("#tw-body [data-exit]")) {
      $("#tw-body").insertAdjacentHTML("beforeend", `<div class="l ${job.rc === 0 ? "l-ok" : "l-err"}" data-exit>── ${esc(t("exit_code", { rc: job.rc }))} · ${dur(job.finished - job.started)} ──</div>`);
    }
  }
  if (S.scripts == null || now() - S.scriptsAt > 30) loadScripts();
}
function openJob(id) {
  S.openJob = id;
  $("#tw-body") && ($("#tw-body").innerHTML = "");
  $("#tw-head") && delete $("#tw-head").dataset.sig;
  loadJob(id);
  if (S.state) renderTerm();
}
async function loadJob(id) {
  try {
    const r = await (await fetch(`/api/job/${id}`)).json();
    if (S.openJob !== id) return;
    const body = $("#tw-body");
    if (!body) return;
    body.innerHTML = "";
    appendLines(body, r.lines, 5000, false);
    body.scrollTop = body.scrollHeight;
    delete $("#tw-head").dataset.sig;
    renderTerm();
  } catch (e) { /* bỏ qua */ }
}
async function loadScripts() {
  S.scriptsAt = now();
  const old = JSON.stringify(S.scripts);
  try { S.scripts = await (await fetch("/api/scripts")).json(); } catch (e) { S.scripts = []; }
  // vào trang Terminal lần đầu: danh sách vẽ trước khi script về — vẽ lại ngay, không đợi trạng thái đổi
  if (S.view === "term" && S.state && JSON.stringify(S.scripts) !== old) renderTerm();
}

/* ------------------------------------------------------------------ ngăn chi tiết task */
function openTask(tid) {
  S.openTask = tid; S.rejecting = false; S.logs = [];
  if (S.drawerTab !== "log" && tid === 0) S.drawerTab = "log";
  renderDrawer(true);
  $("#drawer").classList.add("open");
  if (S.drawerTab === "log") loadLog(tid);
  $$(".card.sel, .tbrow.sel").forEach((c) => c.classList.remove("sel"));
  $$(`.card[data-task="${tid}"], .tbrow[data-task="${tid}"]`).forEach((c) => c.classList.add("sel"));
}
function closeDrawer() {
  S.openTask = null;
  $("#drawer").classList.remove("open");
  $$(".card.sel, .tbrow.sel").forEach((c) => c.classList.remove("sel"));
}
function renderDrawer(full) {
  const tid = S.openTask, dr = $("#drawer");
  const x = tid ? S.state && S.state.tasks.find((y) => y.id === tid) : null;
  if (tid && !x) { if (S.state) closeDrawer(); return; }
  const fx = x && S.drawerTab !== "log" ? fullTask(x) : null;  // prompt + kết quả: ảnh chụp bảng việc không mang theo, tải qua /api/task
  const sig = x ? JSON.stringify([x.status, x.agent, x.title, x.started, x.finished, x.error, !!fx, S.drawerTab, S.rejecting]) : "sys" + S.drawerTab;
  if (!full && dr.dataset.sig === sig) return;
  const keepLog = !full && $("#dr-log") && S.drawerTab === "log";
  const logNode = keepLog ? $("#dr-log") : null;
  dr.dataset.sig = sig;
  const head = x ? `
    <div class="dr-top"><div class="dr-title"><span class="tid" style="font-size:14px">#${x.id}</span> ${esc(x.title)}</div>
      <button class="icon-btn" data-action="close-drawer" title="${esc(t("close"))}"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>
    <div class="dr-meta">${badge(x.status, STATUS_LABEL(x.status), x.status === "running")}${agentHtml(x.agent)}
      ${x.model || x.effort ? `<span class="kv">${esc([x.model, x.effort].filter(Boolean).join(" · "))}</span>` : ""}
      ${x.goal ? `<span class="kv">🎯 <b>#${x.goal}</b></span>` : ""}
      ${(x.skills || []).length ? SkillsView.chips(x.skills) : ""}
      ${x.deps.length ? `<span class="kv">${esc(t("deps"))}: <b>${x.deps.map((d) => "#" + d).join(", ")}</b></span>` : ""}
      <span class="kv">${esc(t("started"))}: <b>${clock(x.started)}</b></span>
      ${x.started ? `<span class="kv">${esc(t("duration"))}: <b>${elapsedHtml(x.started, x.finished).replace('class="time"', 'class="time" style="margin:0"')}</b></span>` : ""}
      ${x.attempts ? `<span class="kv">${esc(t("attempts"))}: <b>${x.attempts}</b></span>` : ""}
      ${x.branch ? `<span class="kv">${esc(t("branch"))}: <b class="mono">${esc(x.branch)}</b></span>` : ""}
    </div>
    <div class="dr-actions">${taskActions(x)}</div>
    ${S.rejecting ? `<div class="reject-box"><textarea class="field" id="reject-fb" placeholder="${esc(t("reject_ph"))}"></textarea>
      <div class="row-actions"><button class="btn sm danger" data-action="reject-send" data-task="${x.id}">${esc(t("reject"))}</button>
      <button class="btn sm ghost" data-action="reject-cancel">${esc(t("cancel_edit"))}</button></div></div>` : ""}` : `
    <div class="dr-top"><div class="dr-title">📜 ${esc(t("syslog"))}</div>
      <button class="icon-btn" data-action="close-drawer" title="${esc(t("close"))}"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>`;
  const tabs = x ? `<div class="tabs">${["log", "prompt", "result"].map((k) => `<button class="tab${S.drawerTab === k ? " on" : ""}" data-action="dr-tab" data-tab="${k}">${esc(t("tab_" + k))}</button>`).join("")}</div>` : "";
  let body;
  if (!x || S.drawerTab === "log") body = `<div class="dr-body dark"><div class="log" id="dr-log"></div></div>`;
  else if (!fx) body = `<div class="dr-body"><div class="muted">…</div></div>`;
  else if (S.drawerTab === "prompt") body = `<div class="dr-body">${imagesHtml(fx.prompt)}<div class="prompt-box md" style="max-height:none">${mdHtml(fx.prompt)}</div></div>`;
  else body = `<div class="dr-body">${x.error ? `<div class="sec-title">${esc(t("error"))}</div><div class="error-box">${esc(x.error)}</div>` : ""}
      ${imagesHtml(fx.result)}<div class="result-box md">${fx.result ? mdHtml(fx.result) : `<span class="muted">${esc(t("no_result"))}</span>`}</div></div>`;
  dr.innerHTML = `<div class="dr-head">${head}</div>${tabs}${body}`;
  if (logNode) $("#dr-log").replaceWith(logNode);  // giữ log đang hiện (và vị trí cuộn), chỉ vẽ lại phần đầu
  if (S.rejecting) $("#reject-fb").focus();
}
function fullTask(x) {
  // tải lại khi task đổi trạng thái / chạy xong (kết quả mới); đang tải thì trả null, vẽ lại khi về
  const key = JSON.stringify([x.status, x.finished, x.attempts]), f = S.full[x.id];
  if (f && f.key === key) return f.data;
  if (!f || f.key !== key) {
    S.full[x.id] = { key, data: f && f.data };
    fetch(`/api/task/${x.id}`).then((r) => r.json()).then((d) => {
      if (S.full[x.id] && S.full[x.id].key === key) S.full[x.id].data = d;
      if (S.openTask === x.id && S.drawerTab !== "log") renderDrawer(true);
    }).catch(() => { delete S.full[x.id]; });
  }
  return f && f.data;
}
function taskActions(x) {
  const b = [];
  const st = x.status;
  if (["review", "conflict"].includes(st)) {
    b.push(`<button class="btn sm success" data-action="merge" data-task="${x.id}">✓ ${esc(t("merge"))}</button>`);
    b.push(`<button class="btn sm danger" data-action="reject" data-task="${x.id}">✗ ${esc(t("reject"))}</button>`);
  }
  b.push(`<button class="btn sm" data-action="diff" data-task="${x.id}">Δ ${esc(t("diff"))}</button>`);
  if (["failed", "cancelled", "blocked", "done", "conflict"].includes(st)) b.push(`<button class="btn sm" data-action="retry" data-task="${x.id}">↻ ${esc(t("retry"))}</button>`);
  if (["failed", "cancelled", "blocked"].includes(st)) b.push(`<button class="btn sm" data-action="reassign" data-task="${x.id}" title="${esc(t("reassign_hint"))}">⇄ ${esc(t("reassign"))}</button>`);
  if (["done", "failed"].includes(st)) b.push(`<button class="btn sm" data-action="task-continue" data-task="${x.id}">↪ ${esc(t("continue_task"))}</button>`);
  if (["queued", "running", "draft", "review"].includes(st)) b.push(`<button class="btn sm danger" data-action="cancel" data-task="${x.id}">■ ${esc(t("cancel"))}</button>`);
  if (x.goal == null && TASK_FILTERS.delete.includes(st)) b.push(`<button class="btn sm danger" data-action="delete-task" data-task="${x.id}">🗑 ${esc(t("delete_task"))}</button>`);
  return b.join("");
}

/* ⇄ đổi agent cho task lỗi / bị huỷ rồi chạy lại ngay */
function reassignModal(tid) {
  const x = S.state.tasks.find((y) => y.id === tid);
  if (!x) return;
  const items = S.state.agents.filter((a) => a.installed).map((a) => `<button class="pick${a.name === x.agent ? " on" : ""}" data-v="${esc(a.name)}" title="${esc(a.role || "")}">${agentHtml(a.name)}${a.cooldown ? ` <span class="muted">⏸ ${esc(a.cooldown)}</span>` : ""}</button>`).join("");
  const m = openModal(`${modalHead("⇄ " + esc(t("reassign_title", { id: tid })))}
    <div class="modal-pad"><div class="muted small" style="margin-bottom:8px">${esc(t("reassign_hint"))}</div><div class="picks">${items}</div></div>`, { box: "sm" });
  m.addEventListener("click", (e) => {
    const b = e.target.closest(".pick");
    if (!b) return;
    closeModal(m);
    send("assign", { task: tid, agent: b.dataset.v, rerun: true });
  });
}

/* mở trên điện thoại: URL kèm token + mã QR (GET /api/remote); server chỉ nghe máy này thì có nút ↻ chạy lại từ xa */
async function phoneModal() {
  let r;
  try { r = await fetch("/api/remote").then((x) => x.json()); } catch (e) { return; }
  const m = openModal(`${modalHead("📱 " + esc(t("phone_title")))}<div class="modal-pad">${phoneBody(r)}</div>`);
  m.addEventListener("click", (e) => {
    const b = e.target.closest("[data-mode]");
    if (b) busyBtn(b, remoteRestart(b.dataset.mode, m));
  });
  // tunnel: cloudflared in URL sau vài giây -> hỏi lại tới khi có (hoặc popup đóng)
  while (r.pending && m.isConnected) {
    await new Promise((ok) => setTimeout(ok, 1500));
    try { r = await fetch("/api/remote").then((x) => x.json()); } catch (e) { return; }
    $(".modal-pad", m).innerHTML = phoneBody(r);
  }
}
function phoneBody(r) {
  const cmd = (mode, code, hint) => `<div class="phone-cmd"><div class="phone-cmd-row"><code>${code}</code>
    <button class="btn sm" data-mode="${mode}">${esc(t("phone_restart"))}</button></div><span class="muted small">${esc(t(hint))}</span></div>`;
  if (!r.enabled) {
    return `<p>${esc(t("phone_local"))}</p>${cmd("lan", "ateam web --host 0.0.0.0", "phone_local_lan")}${cmd("tunnel", "ateam web --tunnel", "phone_local_tunnel")}`;
  }
  return `<p class="muted small">${esc(t("phone_hint"))}${r.readonly ? " " + esc(t("phone_ro")) : ""}</p>
    ${r.pending ? `<p class="muted">${esc(t("phone_tunnel_wait"))}</p>` : ""}
    <div class="phone-grid">${r.urls.map((u) => `<div class="phone-item"><b>${esc(u.label)}</b>${u.svg ? `<img class="phone-qr" alt="QR" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(u.svg)}">` : ""}
      <div class="phone-url"><code>${esc(u.url)}</code><button class="btn sm" data-action="copy-url" data-url="${esc(u.url)}">${esc(t("phone_copy"))}</button></div></div>`).join("")}</div>`;
}
/* ↻ chạy lại server ở chế độ từ xa (cùng cổng): server mới cần token cả từ máy này -> waitRestart vào lại bằng token */
async function remoteRestart(mode, m) {
  let r = await request("remote_restart", { mode }, t("phone_restarting"));
  if (r.busy) {
    if (!await confirmBox(t("proj_busy"), t("phone_busy_q", { n: r.busy }), t("phone_busy_yes"))) return;
    r = await request("remote_restart", { mode, force: true }, t("phone_restarting"));
  }
  if (!r.restarting) return;
  S.restartToken = r.token;
  closeModal(m);
}
/* server cũ còn trả /api/remote với enabled=false; server mới (từ xa) trả 401 — hoặc enabled=true nếu cookie lần chạy từ
   xa trước còn hạn (token giữ qua các lần chạy) -> /?t=token đặt cookie rồi về "/" */
async function waitRestart(since) {
  let st = 0, on = false;
  try {
    const x = await fetch("/api/remote", { cache: "no-store" });
    st = x.status;
    on = x.ok && (await x.json()).enabled;
  } catch (e) { /* chưa nghe */ }
  if (st === 401 || on) {
    try { sessionStorage.setItem("ateam-phone", "1"); } catch (e) { /* chặn lưu */ }
    location.href = "/?t=" + encodeURIComponent(S.restartToken);
    return;
  }
  if (Date.now() - since > 20000 && !S.restartWarned) { S.restartWarned = true; toast(t("phone_restart_fail"), "error"); }
  setTimeout(() => waitRestart(since), 700);
}

/* ------------------------------------------------------------------ khung nổi (modal) xếp chồng */
function openModal(html, opts = {}) {
  const m = document.createElement("div");
  m.className = "modal" + (opts.cls ? " " + opts.cls : "");
  m.innerHTML = `<div class="modal-box ${opts.box || ""}">${html}</div>`;
  m.addEventListener("mousedown", (e) => { if (e.target === m && !opts.sticky) closeModal(m); });
  m._onClose = opts.onClose;
  document.body.appendChild(m);
  const f = m.querySelector("[autofocus], input, textarea, select, button.primary");
  if (f) setTimeout(() => f.focus(), 30);
  return m;
}
function topModal() { const ms = $$("body > .modal"); return ms[ms.length - 1] || null; }
function closeModal(m) {
  m = m || topModal();
  if (!m) return;
  if (m._onClose && m._onClose() === false) return;  // còn thay đổi chưa lưu…
  m.remove();
}
function modalHead(title, extra = "") {
  return `<div class="modal-head"><div class="panel-title">${title}</div>${extra}
    <button class="icon-btn" data-action="close-modal" title="${esc(t("close"))}"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>`;
}
/* hỏi xác nhận: Promise<bool> */
function confirmBox(title, text, yes, danger = true) {
  return new Promise((resolve) => {
    let done = false;
    const m = openModal(`${modalHead(esc(title))}<div class="modal-pad"><div class="confirm-text">${esc(text)}</div>
      <div class="row-actions end"><button class="btn ghost" data-act="no">${esc(t("cancel_edit"))}</button>
      <button class="btn ${danger ? "danger-solid" : "primary"}" data-act="yes" autofocus>${esc(yes)}</button></div></div>`,
      { box: "sm", onClose: () => { if (!done) { done = true; resolve(false); } } });
    m.addEventListener("click", (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      done = true; resolve(b.dataset.act === "yes"); m.remove();
    });
  });
}
/* hỏi một dòng chữ: Promise<string|null> */
function inputBox(title, label, value = "") {
  return new Promise((resolve) => {
    let done = false;
    const m = openModal(`${modalHead(esc(title))}<div class="modal-pad"><div class="confirm-text">${esc(label)}</div>
      <input class="field one" id="ib-val" value="${esc(value)}" autofocus>
      <div class="row-actions end"><button class="btn ghost" data-act="no">${esc(t("cancel_edit"))}</button>
      <button class="btn primary" data-act="yes">OK</button></div></div>`,
      { box: "sm", onClose: () => { if (!done) { done = true; resolve(null); } } });
    const finish = (ok) => { done = true; resolve(ok ? $("#ib-val", m).value.trim() : null); m.remove(); };
    m.addEventListener("click", (e) => { const b = e.target.closest("[data-act]"); if (b) finish(b.dataset.act === "yes"); });
    $("#ib-val", m).addEventListener("keydown", (e) => { if (e.key === "Enter") finish(true); });
  });
}
function textModal(title, body) {
  openModal(`${modalHead(esc(title))}<div class="modal-body plain"><pre class="text-pre">${linkify(esc(body))}</pre></div>`, { box: "md" });
}
/* chữ trợ giúp (HELP của tui.py) căn cột kiểu terminal: lệnh ở trái, mô tả từ một cột cố định, dòng chỉ có mô tả
   (thụt sâu) là phần tiếp của lệnh trên. Cột mô tả = độ thụt hay gặp nhất của các dòng thụt sâu. */
function helpRows(text) {
  const ls = String(text || "").split("\n"), ind = (l) => l.length - l.trimStart().length;
  const deep = ls.filter((l) => l.trim() && ind(l) > 12).map(ind);
  const freq = {};
  deep.forEach((n) => { freq[n] = (freq[n] || 0) + 1; });
  const col = deep.length ? +Object.keys(freq).sort((a, b) => freq[b] - freq[a])[0] : 36;
  const out = [];
  let last = null;
  for (const l of ls) {
    if (!l.trim()) { last = null; out.push({ gap: true }); continue; }
    if (last && ind(l) > 2 && ind(l) >= Math.min(last.at, col) - 1) { last.desc.push(l.trim()); continue; }
    if (!/^\s/.test(l) && !l.includes("  ")) { last = null; out.push({ head: l.trim() }); continue; }
    let cut = /^\s/.test(l) ? col : l.indexOf("  ");
    if (cut < l.length && l[cut - 1] !== " ") {  // lệnh dài lấn sang cột mô tả: tách ở khoảng trắng đôi kế tiếp
      const m = /\s{2,}/.exec(l.slice(cut));
      cut = m ? cut + m.index : l.length;
    }
    const rest = l.slice(cut), at = rest.trim() ? cut + rest.length - rest.trimStart().length : col;
    last = { cmd: l.slice(0, cut).trim(), desc: rest.trim() ? [rest.trim()] : [], at };
    out.push(last);
  }
  return out;
}
function helpModal() {
  const lines = helpRows(S.meta.help).map((r) => r.gap ? `<div class="h-gap"></div>`
    : r.head ? `<div class="h-head">${esc(r.head)}</div>`
    : `<div class="h-row"><code>${esc(r.cmd)}</code><span>${r.desc.map(esc).join("<br>")}</span></div>`).join("");
  openModal(`${modalHead(esc(t("help")))}<div class="modal-body plain help">${lines}</div>`, { box: "md" });
}
/* bảng chọn model/effort cho một agent (/model <agent>, bấm vào agent ở tab Đội) */
function pickerModal(p) {
  const items = p.items.map((v) => `<button class="pick${v === p.current ? " on" : ""}" data-v="${esc(v)}">${esc(v)}${v === p.current ? " ✓" : ""}</button>`).join("")
    + `<button class="pick" data-v=""><i>${esc(t("default_value"))}</i></button>`;
  const m = openModal(`${modalHead(esc(t("pick_title", { key: p.key, agent: p.agent, v: p.current || t("default_value") })))}
    <div class="modal-pad"><div class="picks">${items}</div>
    <input class="field one" id="pick-custom" placeholder="${esc(t("pick_custom"))}"></div>`, { box: "sm" });
  const choose = async (v) => {
    closeModal(m);
    const r = await request("agent_option", { agent: p.agent, key: p.key, value: v });
    const a = r.agent;  // mức effort theo model vừa chọn
    if (p.then_effort && p.key === "model" && a && a.efforts.length) pickerModal({ agent: p.agent, key: "effort", items: a.efforts, current: a.effort });
  };
  m.addEventListener("click", (e) => { const b = e.target.closest(".pick"); if (b) choose(b.dataset.v); });
  $("#pick-custom", m).addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.value.trim()) choose(e.target.value.trim()); });
}

/* mở folder / dự án khác (/open, bấm tên dự án): dự án gần đây hoặc gõ đường dẫn — Tab đi vào thư mục con.
   Server dừng rồi chạy lại ở dự án mới (cùng cổng); hello có root khác thì trang tự nạp lại. */
function projectModal(q = "") {
  const P = { vals: [], labels: [], sel: -1, seq: 0 };
  const m = openModal(`<div class="pal"><input class="field one pal-q" autocomplete="off" spellcheck="false" placeholder="${esc(t("proj_ph"))}">
    <div class="pal-list" role="listbox"></div><div class="pal-foot">${esc(t("proj_foot"))}</div></div>`, { box: "md", cls: "palette" });
  const inp = $(".pal-q", m), list = $(".pal-list", m);
  const paint = () => $$(".pal-item", list).forEach((r) => r.classList.toggle("on", +r.dataset.i === P.sel));
  const refill = async () => {
    const seq = ++P.seq, r = await request("projects", { q: inp.value });
    if (seq !== P.seq) return;
    const items = r.items || [];
    P.vals = items.map((it) => it.kind === "current" ? null : it.path);
    P.labels = items.map((it) => it.label);
    P.sel = P.vals.findIndex((v) => v);
    const head = !inp.value.trim() && items.length ? `<div class="pal-head">${esc(t("proj_recent"))}</div>` : "";
    list.innerHTML = head + (items.map((it, i) => `<div class="pal-item${it.kind === "current" ? " off" : ""}" data-i="${i}" role="option">${it.kind === "recent" ? "🕘" : "📁"} ${esc(it.name)}<span class="pal-where"><bdi>${esc(it.where)}</bdi></span>${it.kind === "current" ? ` <span class="pal-dim">${esc(t("proj_current"))}</span>` : `<button class="pal-win" data-win="${i}" title="${esc(t("proj_window"))}" aria-label="${esc(t("proj_window"))}">⧉</button>`}</div>`).join("")
      || `<div class="pal-head">${esc(t(inp.value.trim() ? "proj_none" : "proj_hint"))}</div>`);
    paint();
  };
  const move = (d) => {
    let i = P.sel;
    for (let k = 0; k < Math.abs(d); k++) {
      let j = i + Math.sign(d);
      while (j >= 0 && j < P.vals.length && !P.vals[j]) j += Math.sign(d);
      if (j < 0 || j >= P.vals.length) break;
      i = j;
    }
    P.sel = i; paint();
    const on = $(".pal-item.on", list);
    if (on) on.scrollIntoView({ block: "nearest" });
  };
  const choose = (i, win) => {
    const v = P.vals[i] || (inp.value.trim() && P.sel < 0 ? inp.value.trim() : "");
    if (v) { closeModal(m); win ? openWindow(v) : openProject(v); }
  };
  inp.value = q;
  inp.addEventListener("input", refill);
  inp.addEventListener("keydown", (e) => {
    const d = { ArrowDown: 1, ArrowUp: -1, PageDown: 10, PageUp: -10 }[e.key];
    if (d) { e.preventDefault(); move(d); }
    else if (e.key === "Enter") { e.preventDefault(); choose(P.sel, e.metaKey || e.ctrlKey); }
    else if (e.key === "Tab" && P.vals[P.sel]) {
      e.preventDefault();
      inp.value = P.labels[P.sel] + "/";
      refill();
    }
  });
  list.addEventListener("click", (e) => {
    const w = e.target.closest(".pal-win");
    if (w) { e.stopPropagation(); choose(+w.dataset.win, true); return; }
    const r = e.target.closest(".pal-item[data-i]");
    if (r) choose(+r.dataset.i, e.metaKey || e.ctrlKey);
  });
  refill();
}
async function openProject(path) {
  const unsaved = window.CodeView ? CodeView.unsaved() : [];
  if (unsaved.length && !await confirmBox(t("proj_open"), t("proj_unsaved_q", { v: unsaved.join(", ") }), t("proj_unsaved_yes"))) return;
  let r = await request("open_project", { path }, t("busy_opening_proj"));
  if (r.busy) {
    if (!await confirmBox(t("proj_busy"), t("proj_busy_q", { n: r.busy, v: r.path }), t("proj_busy_yes"))) return;
    r = await request("open_project", { path, force: true }, t("busy_opening_proj"));
  }
  if (!r.switching) return;
  S.switching = true;
  // dự án mới gửi hello -> trang nạp lại; quá lâu (cổng bị chiếm, server lỗi) thì chỉ người dùng xem terminal
  setTimeout(() => { if (!S.connected) toast(t("proj_switch_fail"), "error"); }, 20000);
}

/* mở dự án ở cửa sổ mới (⧉, ⌘/Ctrl+Enter): server chạy thêm một `ateam web` cho dự án đó. Cửa sổ mở ngay lúc bấm
   (sau await thì trình duyệt coi là popup tự bật và chặn), rồi trỏ tới địa chỉ khi server mới sẵn sàng. */
async function openWindow(path) {
  const w = window.open("", "_blank");
  if (w) { w.opener = null; w.document.title = "ateam…"; }
  const r = await request("open_window", { path }, t("busy_opening_proj"));
  if (!r.url) { if (w) w.close(); return; }
  if (w) w.location.href = r.url;
  else toast(t("proj_popup"), "warn", { label: t("proj_popup_open"), run: () => window.open(r.url, "_blank", "noopener") });
}

/* ------------------------------------------------------------------ giao diện sáng/tối + màu nhấn */
/* thanh bên thu gọn (chỉ icon): lưu theo trình duyệt; script đầu index.html áp trước khi vẽ để không nháy */
function setSideMin(on) {
  document.documentElement.classList.toggle("side-min", on);
  try { on ? localStorage.setItem("ateam-side", "min") : localStorage.removeItem("ateam-side"); } catch (e) { /* chặn lưu */ }
  renderSideToggle();
}
function renderSideToggle() {
  const b = $("#side-toggle");
  if (!b) return;
  const lbl = t(document.documentElement.classList.contains("side-min") ? "side_expand" : "side_collapse");
  b.title = lbl;
  b.setAttribute("aria-label", lbl);
}
function themeMode() { try { return localStorage.getItem("ateam-theme") || "system"; } catch (e) { return "system"; } }
function setThemeMode(mode) {
  try { mode === "system" ? localStorage.removeItem("ateam-theme") : localStorage.setItem("ateam-theme", mode); } catch (e) { /* chặn lưu */ }
  if (mode === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = mode;
  if (window.CodeView) CodeView.prefsChanged();
  applyTermTheme();
}
function isDark() {
  const d = document.documentElement.dataset.theme;
  return d ? d === "dark" : !matchMedia("(prefers-color-scheme: light)").matches;
}
/* Bảng ANSI mặc định của xterm.js làm cho nền tối: trắng/vàng/xanh lá gần như chìm trên nền kem */
const TERM_LIGHT_ANSI = { black: "#1c1914", red: "#c4233a", green: "#1a7f37", yellow: "#9a6700", blue: "#1d4ed8",
  magenta: "#7e22ce", cyan: "#0e7490", white: "#6f675c", brightBlack: "#6f675c", brightRed: "#a01d30",
  brightGreen: "#116329", brightYellow: "#7d5200", brightBlue: "#1e40af", brightMagenta: "#6b21a8",
  brightCyan: "#155e75", brightWhite: "#3d3830", selectionBackground: "rgba(109, 40, 217, .22)" };
function termOptions() {
  const cs = getComputedStyle(document.documentElement), dark = isDark();
  const fg = cs.getPropertyValue("--term-fg").trim() || "#e6e6e6";
  return { theme: Object.assign({ background: cs.getPropertyValue("--term-bg").trim() || "#0b0d10", foreground: fg, cursor: fg },
    dark ? {} : TERM_LIGHT_ANSI),
    // CLI như Claude Code tô màu truecolor theo theme tối của nó — bảng ANSI không đổi được, nên ép tương phản
    minimumContrastRatio: dark ? 1 : 4.5 };
}
function applyTermTheme() {
  const o = termOptions();
  for (const term of Object.values(S.ptys).concat(window.GridView ? GridView.terms() : [])) {
    term.options.theme = o.theme;
    term.options.minimumContrastRatio = o.minimumContrastRatio;
  }
}
matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => {
  if (!document.documentElement.dataset.theme) applyTermTheme();
});
function themeModal() {
  const modes = ["system", "light", "dark"].map((k) => `<button class="seg${themeMode() === k ? " on" : ""}" data-mode="${k}">${esc(t("mode_" + k))}</button>`).join("");
  const accents = [{ key: "", label: t("accent_default"), color: "" }].concat(S.meta.accents || []).map((a) => `
    <button class="swatch${(S.prefs.accent || "") === a.key ? " on" : ""}" data-acc="${esc(a.key)}" title="${esc(a.label)}">
      <i style="background:${a.color || "linear-gradient(135deg,#8b5cf6,#06b6d4)"}"></i><span>${esc(a.label)}</span></button>`).join("");
  const m = openModal(`${modalHead(esc(t("theme")))}<div class="modal-pad">
    <div class="sec-title">${esc(t("appearance"))}</div><div class="segs">${modes}</div>
    <div class="sec-title" style="margin-top:18px">${esc(t("accent"))}</div><div class="swatches">${accents}</div>
    <div class="muted small" style="margin-top:14px">${esc(t("accent_shared"))}</div>
    <div class="sec-title" style="margin-top:18px">${esc(t("sound"))}</div>
    <div class="sound-row"><label class="chk"><input type="checkbox" id="snd-on" ${soundVolume() > 0 ? "checked" : ""}> ${esc(t("sound_on"))}</label>
      <input type="range" id="snd-vol" min="5" max="100" step="5" value="${soundVolume() || 60}" aria-label="${esc(t("sound_volume"))}" ${soundVolume() > 0 ? "" : "disabled"}>
      <button class="btn sm" id="snd-test">▶ ${esc(t("sound_test"))}</button></div>
    <div class="muted small" style="margin-top:8px">${esc(t("sound_local"))}</div></div>`, { box: "sm" });
  const on = $("#snd-on", m), vol = $("#snd-vol", m);
  on.addEventListener("change", () => { vol.disabled = !on.checked; setSoundVolume(on.checked ? +vol.value : 0); if (on.checked) soundDemo(["review"]); });
  vol.addEventListener("change", () => { setSoundVolume(+vol.value); soundDemo(["review"]); });
  $("#snd-test", m).addEventListener("click", () => soundDemo(["plan", "ask", "failed", "task_done", "done"], on.checked ? +vol.value : 60));
  m.addEventListener("click", async (e) => {
    const mode = e.target.closest("[data-mode]"), acc = e.target.closest("[data-acc]");
    if (mode) { setThemeMode(mode.dataset.mode); $$(".seg", m).forEach((b) => b.classList.toggle("on", b === mode)); }
    if (acc) { await request("prefs", { accent: acc.dataset.acc }); $$(".swatch", m).forEach((b) => b.classList.toggle("on", b === acc)); }
  });
}

/* ------------------------------------------------------------------ thông báo */
/* Thông báo (notify.py): toast luôn; thông báo của trình duyệt khi tab đang ẩn (hoặc /notify test).
   Xin quyền ở lần bấm đầu tiên trên trang — trình duyệt chỉ cho hỏi sau một thao tác của người dùng. */
function onNotice(m) {
  if (m.cell && S.view === "grid" && !document.hidden && document.hasFocus() && window.GridView
      && GridView.focused() === m.cell) return;  // đang nhìn đúng ô đó trong Lưới
  toast(m.title + " — " + m.body, m.level === "warn" ? "warn" : "info");
  playSound(m.kind);
  if (!m.desktop || !("Notification" in window) || Notification.permission !== "granted") return;
  if (!document.hidden && !m.force) return;
  try {
    const n = new Notification(m.title, { body: m.body, tag: "ateam-" + m.kind + "-" + (m.task || m.goal || m.cell || "")});
    n.onclick = () => {
      window.focus(); n.close();
      if (m.cell) { setView("grid"); setTimeout(() => GridView.focusCell(m.cell), 60); }
      else if (m.task != null) openTask(m.task);
      else if (m.goal != null) setView("board");
    };
  } catch (e) { /* trình duyệt chặn (vd chạy trong iframe) */ }
}
function askNotifyPermission() {
  if (!("Notification" in window) || Notification.permission !== "default") return;
  if (S.prefs && S.prefs.notify && S.prefs.notify !== "all") return;
  try { Notification.requestPermission(); } catch (e) { /* trình duyệt cũ */ }
}
document.addEventListener("pointerdown", askNotifyPermission, { once: true });

/* Âm thanh (Web Audio, không file): mỗi loại thông báo một giai điệu ngắn. Âm lượng lưu theo trình duyệt
   (localStorage "ateam-sound", 0 = tắt). Trình duyệt chỉ cho phát sau một thao tác của người dùng → mở khoá
   AudioContext ở mỗi lần bấm/gõ (iOS tạm dừng lại khi tab bị ẩn). */
const SOUNDS = {  // nốt: [tần số Hz, bắt đầu (giây), dài (giây)]; gain: độ to so với mặc định (1)
  task_done: { wave: "sine", gain: 2.4, notes: [[784, 0, .5], [1047, .18, .55], [1319, .36, .6], [1568, .54, 1.5]] },  // task ngoài kế hoạch / ô Lưới xong
  plan: { wave: "sine", notes: [[659, 0, .2], [880, .13, .35]] },
  review: { wave: "sine", notes: [[1047, 0, .5]] },
  ask: { wave: "sine", notes: [[784, 0, .16], [988, .11, .16], [1175, .22, .38]] },
  failed: { wave: "triangle", notes: [[440, 0, .25], [330, .18, .45]] },
  done: { wave: "sine", notes: [[523, 0, .45], [659, .09, .45], [784, .18, .45], [1047, .27, .7]] },
};
SOUNDS.conflict = SOUNDS.goal_end = SOUNDS.failed;
SOUNDS.test = SOUNDS.review;
SOUNDS.grid_done = SOUNDS.task_done;  // ô Lưới xong lượt / cần bạn
SOUNDS.grid_ask = SOUNDS.ask;
const SOUND_RANK = ["test", "grid_done", "task_done", "done", "review", "plan", "grid_ask", "ask", "goal_end", "conflict", "failed"];  // sau = ưu tiên
let audioCtx = null, soundAt = 0, soundNext = null, soundTimer = 0;
function soundVolume() {
  try { const v = localStorage.getItem("ateam-sound"); return v == null ? 60 : Math.max(0, Math.min(100, +v || 0)); } catch (e) { return 60; }
}
function setSoundVolume(v) { try { localStorage.setItem("ateam-sound", String(v)); } catch (e) { /* chặn lưu */ } }
function unlockAudio() {
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return;
  try {
    if (!audioCtx) audioCtx = new AC();
    if (audioCtx.state === "suspended") audioCtx.resume();
  } catch (e) { /* trình duyệt chặn */ }
}
document.addEventListener("pointerdown", unlockAudio);
document.addEventListener("keydown", unlockAudio);
function playTune(kind, vol, delay) {
  const s = SOUNDS[kind], ctx = audioCtx;
  if (!s || !ctx || ctx.state !== "running" || vol <= 0) return false;
  const master = ctx.createGain();
  master.gain.value = .5 * (vol / 100) ** 2;  // tai nghe theo thang log: bình phương cho thanh trượt "đều" hơn
  master.connect(ctx.destination);
  const t0 = ctx.currentTime + .02 + (delay || 0);
  for (const [f, at, dur] of s.notes) {
    const o = ctx.createOscillator(), g = ctx.createGain(), t = t0 + at;
    o.type = s.wave;
    o.frequency.value = f;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(.35 * (s.gain || 1), t + .012);
    g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    o.connect(g).connect(master);
    o.start(t);
    o.stop(t + dur + .05);
  }
  return true;
}
function playSound(kind) {  // nhiều thông báo cùng lúc → một âm (loại quan trọng nhất), cách nhau ≥1,5 giây
  if (!SOUNDS[kind] || soundVolume() <= 0) return;
  if (!soundNext || SOUND_RANK.indexOf(kind) > SOUND_RANK.indexOf(soundNext)) soundNext = kind;
  clearTimeout(soundTimer);
  soundTimer = setTimeout(() => {
    const k = soundNext;
    soundNext = null;
    if (Date.now() - soundAt >= 1500 && playTune(k, soundVolume())) soundAt = Date.now();
  }, 150);
}
function soundDemo(kinds, vol) {
  unlockAudio();
  kinds.forEach((k, i) => playTune(k, vol == null ? soundVolume() || 60 : vol, i * 1.1));
}
function pendingCount() {  // việc chờ người dùng: kế hoạch chờ duyệt + task chờ duyệt diff/xung đột
  if (!S.state) return 0;
  return S.state.goals.filter((g) => g.status === "awaiting").length + S.state.tasks.filter((x) => ["review", "conflict", "asking"].includes(x.status)).length;
}
function busyToast(text) {  // toast "đang chạy…": spinner, không tự tắt — gọi done() khi có kết quả
  const el = document.createElement("div");
  el.className = "toast info busy";
  el.innerHTML = '<span class="spin"></span>';
  const msg = document.createElement("span");
  msg.className = "toast-msg";
  msg.textContent = text;
  el.appendChild(msg);
  $("#toasts").appendChild(el);
  return { done: () => { el.classList.add("out"); setTimeout(() => el.remove(), 250); } };
}
function toast(text, level = "info", action = null) {  // action = {label, run}: nút trên toast (vd "Xem" task vừa tạo)
  const el = document.createElement("div");
  el.className = "toast " + level;
  const msg = document.createElement("span");
  msg.className = "toast-msg";
  msg.textContent = text;
  el.appendChild(msg);
  const gone = () => { el.classList.add("out"); setTimeout(() => el.remove(), 250); };
  if (action) {
    const b = document.createElement("button");
    b.className = "toast-act";
    b.textContent = action.label;
    b.addEventListener("click", () => { gone(); action.run(); });
    el.appendChild(b);
  }
  $("#toasts").appendChild(el);
  const ms = action ? 8000 : level === "error" || level === "warn" ? 6000 : 3800;
  setTimeout(gone, ms);
  const olds = $$(".toast:not(.busy)", $("#toasts"));  // toast "đang chạy…" giữ tới khi xong
  while (olds.length > 5) olds.shift().remove();
}

/* ------------------------------------------------------------------ ô nhập + gợi ý */
const input = $("#input");
function autosize() { input.style.height = "auto"; input.style.height = Math.min(220, input.scrollHeight) + "px"; }
function grillWaiting() { return !!(S.state && ((S.state.grill && S.state.grill.question) || S.state.ask)); }
function renderComposerMode() {
  const v = input.value, mode = $("#mode"), box = $("#composer-box");
  const grill = grillWaiting() && !v.startsWith("/") && !v.startsWith("!");
  mode.className = "composer-mode" + (v.startsWith("/") ? " cmd" : v.startsWith("!") ? " sh" : grill ? " ans" : "");
  mode.textContent = v.startsWith("/") ? "/" : v.startsWith("!") ? "$" : grill ? "?" : "";
  box.classList.toggle("grill", grill);
  const wf = S.state && S.state.workflow;
  input.placeholder = grill ? t(S.state.grill ? "placeholder_grill" : "placeholder_ask") : wf ? t("placeholder_wf", { wf }) : t("placeholder");
  const fp = $("#flow-pick");
  fp.textContent = (wf ? "⚙ " + wf : t("mode_lead")) + " ▾";
  fp.title = t("mode_pick_title");
  $("#hint").textContent = t("send_hint");
}
function submit() {
  const text = input.value.trim();
  if (!text) return;
  // lệnh /… có thể chạy lâu (/commit, /push…): toast "đang chạy…" tới khi server trả lời
  if (text.startsWith("/")) request("submit", { text }, t("busy_cmd", { v: text.split(/\s/)[0] }));
  else send("submit", { text });
  input.value = "";
  hideSuggest();
  autosize();
  renderComposerMode();
}
let suggestSeq = 0;
const TASK_FILTERS = {
  retry: ["failed", "cancelled", "blocked", "done", "conflict"], cancel: ["draft", "queued", "running", "review"],
  merge: ["review", "conflict"], reject: ["review", "conflict"], edit: ["draft", "queued", "failed", "blocked", "cancelled"],
  assign: ["draft", "queued", "failed", "blocked", "cancelled"], set: ["draft", "queued", "failed", "blocked", "cancelled"],
  delete: ["draft", "queued", "asking", "done", "failed", "blocked", "cancelled"],  // + chỉ task ngoài kế hoạch
};
function aliasOf(c) { return (S.meta.aliases || {})[c] || c; }
function cmdAliases() {
  return { t: "task", c: "continue", tiep: "continue", "grill-me": "grill", hoi: "grill", h: "help", "?": "help",
    flows: "flow", workflow: "custom", workflows: "custom", "agent-moi": "custom", exit: "quit", q: "quit", open: "code", vi: "code" };
}
function agentItems(q, extra = "") {
  return (S.meta.agents || []).filter((a) => a.name.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => b.name.toLowerCase().startsWith(q.toLowerCase()) - a.name.toLowerCase().startsWith(q.toLowerCase()))
    .map((a) => ({ label: a.name + (a.lead ? " ★" : ""), desc: a.label + (a.role ? " · " + a.role : ""), value: a.name + extra }));
}
function taskItems(q, statuses, keep) {
  const ts = ((S.state && S.state.tasks) || []).slice().reverse().filter((x) => (!statuses || statuses.includes(x.status)) && (!keep || keep(x)));
  return ts.filter((x) => !q || String(x.id).startsWith(q.replace("#", "")) || x.title.toLowerCase().includes(q.toLowerCase()))
    .slice(0, 30).map((x) => ({ label: "#" + x.id, desc: `${t(x.status)} · ${x.agent} · ${x.title}`, value: String(x.id) }));
}
function goalItems(q, statuses) {
  return ((S.state && S.state.goals) || []).slice().reverse().filter((g) => !statuses || statuses.includes(g.status))
    .filter((g) => !q || String(g.id).startsWith(q.replace("#", "")) || g.title.toLowerCase().includes(q.toLowerCase()))
    .map((g) => ({ label: "#" + g.id, desc: `${t("g_" + g.status)} · ${g.title}`, value: String(g.id) }));
}
function words(list, q, descs = {}) {
  return list.filter((w) => w.toLowerCase().startsWith(q.toLowerCase())).map((w) => ({ label: w, desc: descs[w] || "", value: w }));
}
async function branchItems(q) {
  if (!S.branches || now() - S.branchesAt > 10) {
    try { S.branches = await (await fetch("/api/git/branches")).json(); S.branchesAt = now(); } catch (e) { S.branches = []; }
  }
  return S.branches.filter((b) => b.name.toLowerCase().includes(q.toLowerCase()))
    .map((b) => ({ label: b.name + (b.current ? " ●" : ""), desc: [b.track, b.subject].filter(Boolean).join(" · "), value: b.name }));
}
async function fileItems(q) {
  try {
    const files = await (await fetch("/api/files?q=" + encodeURIComponent(q))).json();
    return files.map((f) => ({ label: f, value: /\s/.test(f) ? `"${f}"` : f, dir: f.endsWith("/") }));
  } catch (e) { return []; }
}
/* gợi ý cho tham số của lệnh: trả {kind:"arg", items, head} — token đang gõ được thay bằng value */
async function argSuggestions(cmd, args, tok) {
  const pos = args.length, A = (S.meta.agents || []);
  const agentOf = (n) => A.find((a) => a.name === n);
  switch (cmd) {
    case "task": {
      if (pos) return null;
      const m = /^([^:@]*)(?::([^@]*))?(?:@(.*))?$/.exec(tok) || [];
      const a = agentOf(m[1]);
      if (tok.includes("@") && a) return { head: t("sg_effort", { v: a.name }), items: words(a.efforts, m[3] || "").map((i) => ({ ...i, value: tok.slice(0, tok.lastIndexOf("@") + 1) + i.value + " " })) };
      if (tok.includes(":") && a) return { head: t("sg_model", { v: a.name }), items: words(a.models, m[2] || "").map((i) => ({ ...i, value: m[1] + ":" + i.value })) };
      return { head: t("sg_agent_task"), items: agentItems(m[1] || "", " ") };
    }
    case "focus": return pos ? null : { head: t("sg_agent_focus"), items: agentItems(tok) };
    case "chat": return pos ? null : { head: t("sg_agent_chat"), items: agentItems(tok, " ") };
    case "grid": {  // agent có CLI tương tác + ô terminal trống (:shell)
      if (pos) return null;
      const tty = new Set(A.filter((a) => a.tty).map((a) => a.name));
      const sh = ":shell".startsWith(tok.toLowerCase()) ? [{ label: "⌨ :shell", desc: t("sg_shell"), value: ":shell" }] : [];
      return { head: t("sg_agent_grid"), items: sh.concat(agentItems(tok).filter((i) => tty.has(i.value))) };
    }
    case "model": case "effort": {
      if (pos === 0) return { head: t("sg_agent"), items: agentItems(tok, " ") };
      const a = agentOf(args[0]);
      if (pos === 1 && a) return { head: t(cmd === "model" ? "sg_model" : "sg_effort", { v: a.name }), items: words(cmd === "model" ? a.models : a.efforts, tok).concat([{ label: "-", desc: t("default_value"), value: "-" }]) };
      return null;
    }
    case "cooldown":
      if (pos === 0) return { head: t("sg_agent"), items: agentItems(tok, " ") };
      if (pos === 1) return { head: t("sg_minutes"), items: words(["15", "30", "60", "120", "off"], tok) };
      return null;
    case "models":
      if (pos === 0) return { head: t("sg_agent"), items: agentItems(tok, " ") };
      if (pos === 1) return { head: "", items: words(["refresh"], tok, { refresh: t("sg_refresh") }) };
      return null;
    case "assign":
      if (pos === 0) return { head: t("sg_task"), items: taskItems(tok, TASK_FILTERS.assign).map((i) => ({ ...i, value: i.value + " " })) };
      if (pos === 1) return { head: t("sg_agent"), items: agentItems(tok) };
      return null;
    case "set": {
      if (pos === 0) return { head: t("sg_task"), items: taskItems(tok, TASK_FILTERS.set).map((i) => ({ ...i, value: i.value + " " })) };
      if (pos === 1) return { head: "", items: words(["model", "effort"], tok).map((i) => ({ ...i, value: i.value + " " })) };
      const task = ((S.state && S.state.tasks) || []).find((x) => String(x.id) === args[0].replace("#", ""));
      const a = task && agentOf(task.agent);
      if (pos === 2 && a) return { head: t(args[1] === "effort" ? "sg_effort" : "sg_model", { v: a.name }), items: words(args[1] === "effort" ? a.efforts : a.models, tok).concat([{ label: "-", desc: t("default_value"), value: "-" }]) };
      return null;
    }
    case "edit":
      if (pos) return null;
      if (tok.startsWith("@")) return { kind: "file", head: t("files"), items: await fileItems(tok.slice(1)) };
      return { head: t("sg_task_or_file"), items: taskItems(tok, TASK_FILTERS.edit).map((i) => ({ ...i, value: i.value + " " })) };
    case "retry": case "cancel": case "merge": case "reject": case "diff": case "delete":
      return pos ? null : { head: t("sg_task"), items: taskItems(tok, TASK_FILTERS[cmd], cmd === "delete" ? (x) => x.goal == null : null).map((i) => ({ ...i, value: i.value + (cmd === "reject" ? " " : "") })) };
    case "log":
      return pos ? null : { head: t("sg_task"), items: [{ label: "sys", desc: t("syslog"), value: "sys" }].concat(taskItems(tok)) };
    case "go": case "drop":
      return pos ? null : { head: t("sg_goal"), items: goalItems(tok, ["awaiting"]) };
    case "review":
      return pos ? null : { head: t("sg_goal"), items: goalItems(tok, ["running", "reviewing", "incomplete", "done"]) };
    case "continue":
      return pos ? null : { head: t("sg_continue"), items: ((S.state && S.state.continue) || []).filter((c) => !tok || c.ref.includes(tok.replace("#", "")) || c.title.toLowerCase().includes(tok.toLowerCase()))
        .map((c) => ({ label: c.ref, desc: (c.kind === "goal" ? "🎯 " + t("g_" + c.status) : "💬 " + c.agent + " · " + t(c.status)) + " · " + c.title, value: c.ref + " " })) };
    case "flow":
      return pos ? null : { head: "Workflow", items: (S.meta.workflows || []).filter((w) => w.name.startsWith(tok)).map((w) => ({ label: w.name, desc: w.description || w.summary, value: w.name + " " })) };
    case "grill":
      return pos || !(S.state && S.state.grill) ? null : { head: "", items: words(["xong", "tiep", "bo"], tok, { xong: t("grill_done"), tiep: t("grill_retry"), bo: t("grill_cancel") }) };
    case "vim":
      if (pos) return null;
      if (tok.startsWith("@")) return { kind: "file", head: t("files"), items: await fileItems(tok.slice(1)) };
      return { head: "", items: words(["on", "off"], tok) };
    case "notify":
      return pos ? null : { head: "", items: words(["on", "app", "off", "test"], tok, { on: t("notify_on"), app: t("notify_app"), off: t("notify_off"), test: t("notify_test") }) };
    case "lang":
      return pos ? null : { head: "", items: (S.meta.langs || []).filter((l) => l.key.startsWith(tok)).map((l) => ({ label: l.key, desc: l.label, value: l.key })) };
    case "theme":
      return pos ? null : { head: t("theme"), items: words(["light", "dark", "system"], tok, { light: t("mode_light"), dark: t("mode_dark"), system: t("mode_system") })
        .concat((S.meta.accents || []).filter((a) => a.key.startsWith(tok)).map((a) => ({ label: a.key, desc: a.label, value: a.key, color: a.color }))) };
    case "checkout": case "branch":
      return pos ? null : { head: t("sg_branch"), items: await branchItems(tok) };
    case "stash":
      return pos ? null : { head: "", items: words(["pop", "apply", "list"], tok, { pop: t("stash_pop"), apply: t("stash_apply"), list: t("stash_list") }) };
    case "push":
      return pos ? null : { head: "", items: words(["-f"], tok, { "-f": t("force_push") }) };
    case "commit":
      return pos ? null : { head: "", items: words(["--no-verify"], tok, { "--no-verify": t("no_verify") }) };
    case "verify": {
      if (pos) return null;
      if (S.scripts == null) await loadScripts();
      return { head: t("scripts"), items: (S.scripts || []).filter((x) => x.cmd.includes(tok)).slice(0, 10).map((x) => ({ label: x.cmd, desc: x.desc, value: x.cmd }))
        .concat(words(["off"], tok, { off: t("verify_off") })) };
    }
    case "code":
      return pos ? null : { kind: "file", head: t("files"), items: await fileItems(tok.replace(/^@/, "")) };
    default:
      return null;
  }
}
async function updateSuggest() {
  const seq = ++suggestSeq;
  const v = input.value, caret = input.selectionStart;
  const before = v.slice(0, caret);
  const show = (kind, res) => {
    if (seq !== suggestSeq || input.value !== v) return;  // đã gõ tiếp / đã gửi trong lúc chờ
    if (!res || !res.items.length) { hideSuggest(); return; }
    showSuggest(res.kind || kind, res.items, res.head);
  };
  if (/^\/\S*$/.test(v)) {  // tên lệnh
    const q = v.slice(1).toLowerCase();
    const items = S.commands.filter((c) => c.name.startsWith(q)).concat(q.length > 1 ? S.commands.filter((c) => !c.name.startsWith(q) && c.name.includes(q)) : []);
    show("cmd", { head: t("cmds"), items: items.map((c) => ({ label: "/" + c.name, args: c.args, desc: c.desc, value: "/" + c.name + (c.args ? " " : ""), name: c.name, needs: c.args.startsWith("<") })) });
    return;
  }
  const at = /(^|[\s(\[{'`])@("?[^\s@"]*)$/.exec(before);
  if (at && !/^\/(task|t|vim|edit|code|open|vi)\s+\S*$/.test(before)) {
    show("file", { head: t("files"), items: await fileItems(at[2].replace(/^"/, "")) });
    return;
  }
  if (caret === v.length) {
    const m = /^\/(\S+)\s+(.*)$/s.exec(v);
    if (m) {
      const cmd = cmdAliases()[m[1].toLowerCase()] || m[1].toLowerCase();
      const parts = m[2].split(/\s+/);
      const tok = parts.pop();
      show("arg", await argSuggestions(cmd, parts, tok));
      return;
    }
    if (/^![^\n]*$/.test(v)) {
      if (S.scripts == null) await loadScripts();
      const q = v.slice(1).toLowerCase();
      const items = (S.scripts || []).filter((x) => x.cmd.toLowerCase().startsWith(q)).concat((S.scripts || []).filter((x) => !x.cmd.toLowerCase().startsWith(q) && (x.cmd + x.desc).toLowerCase().includes(q))).slice(0, 30);
      show("sh", { head: t("scripts"), items: items.filter((x) => "!" + x.cmd !== v).map((x) => ({ label: x.cmd, desc: x.desc, value: "!" + x.cmd })) });
      return;
    }
  }
  hideSuggest();
}
function showSuggest(kind, items, head) {
  const box = $("#suggest");
  if (!items.length) { hideSuggest(); return; }
  S.suggest = { items, i: 0, kind, nav: false };
  box.innerHTML = `<div class="sg-head">${esc(head)}</div>` + items.map((it, i) => `
    <div class="sg${i === 0 ? " on" : ""}" data-action="sg-pick" data-i="${i}">${it.color ? `<i class="sg-dot" style="background:${esc(it.color)}"></i>` : ""}<b>${esc(it.label)}</b>
      ${it.args ? `<span class="args">${esc(it.args)}</span>` : ""}${it.desc ? `<span class="desc">${esc(it.desc)}</span>` : ""}</div>`).join("");
  box.classList.remove("hidden");
}
/* ô chọn cạnh ô nhập: gõ mục tiêu → trưởng nhóm lập kế hoạch hay chạy một workflow (cfg.default_workflow) */
async function pickMode() {
  if (S.suggest.kind === "mode" && S.suggest.items.length) { hideSuggest(); return; }
  let d;
  try { d = await (await fetch("/api/custom")).json(); } catch (e) { return; }
  const cur = (S.state && S.state.workflow) || "";
  const items = [{ label: t("mode_lead_full"), desc: t("mode_lead_desc"), value: "" }]
    .concat(d.workflows.map((w) => ({ label: "⚙ " + w.name, desc: w.summary, value: w.name })))
    .concat([{ label: "⚙ " + t("df_title") + "…", desc: d.workflows.length ? "" : t("mode_no_flows"), cfg: true }]);
  items.forEach((it) => { if (!it.cfg && it.value === cur) it.label = "✓ " + it.label; });
  input.focus();
  showSuggest("mode", items, t("mode_head"));
  S.suggest.i = Math.max(0, items.findIndex((it) => !it.cfg && it.value === cur));
  moveSuggest(0);
}
function hideSuggest() { $("#suggest").classList.add("hidden"); S.suggest.items = []; }
function moveSuggest(d) {
  const n = S.suggest.items.length;
  S.suggest.i = (S.suggest.i + d + n) % n;
  S.suggest.nav = true;
  $$("#suggest .sg").forEach((el, i) => el.classList.toggle("on", i === S.suggest.i));
  const on = $("#suggest .sg.on");
  on && on.scrollIntoView({ block: "nearest" });
}
function pickSuggest(i) {
  const it = S.suggest.items[i];
  if (!it) return;
  const kind = S.suggest.kind, v = input.value, caret = input.selectionStart;
  if (kind === "mode") {
    hideSuggest();
    if (it.cfg) { if (window.Setup) Setup.flowModal({ onSaved: () => { if (S.view === "custom") Setup.showCustom(); } }); return; }
    request("input_mode", { name: it.value }).then(() => { if (S.view === "custom" && window.Setup) Setup.showCustom(); });
    input.focus();
    return;
  }
  if (kind === "file") {  // thay token @… (hoặc token cuối của /code, /edit @…)
    const start = Math.max(v.slice(0, caret).search(/@?"?[^\s@"]*$/), 0);
    const lead = v[start] === "@" || /^\/(task|t)\b/.test(v) || !/^\/(code|open|vi|vim|edit)\s/.test(v) ? "@" : "";
    const ins = lead + it.value + (it.dir ? "" : " ");
    input.value = v.slice(0, start) + ins + v.slice(caret);
    const pos = start + ins.length;
    input.setSelectionRange(pos, pos);
    hideSuggest();
    if (it.dir) updateSuggest();  // thư mục: gợi ý tiếp bên trong
  } else if (kind === "arg") {
    const start = v.search(/\S*$/);
    input.value = v.slice(0, start) + it.value;
    input.setSelectionRange(input.value.length, input.value.length);
    hideSuggest();
    if (/\s$/.test(it.value)) updateSuggest();  // còn tham số sau: gợi ý tiếp
  } else {
    input.value = it.value;
    input.setSelectionRange(input.value.length, input.value.length);
    hideSuggest();
    if (kind === "cmd" && it.needs) updateSuggest();  // lệnh cần tham số: gợi ý tham số luôn
  }
  input.focus();
  autosize();
  renderComposerMode();
  renderContinueHint();
}
let hintRef = "";
async function renderContinueHint() {
  const m = /^\/(?:continue|tiep|c) (\S+) /.exec(input.value), box = $("#continue-hint");
  if (!m) { box.classList.add("hidden"); hintRef = ""; return; }
  if (m[1] === hintRef) return;
  hintRef = m[1];
  try {
    const r = await (await fetch("/api/continue?ref=" + encodeURIComponent(m[1]))).json();
    if (hintRef !== m[1]) return;
    box.className = "continue-hint" + (r.ok ? "" : " warn");
    box.textContent = r.text;
  } catch (e) { box.classList.add("hidden"); }
}
function continueShortcut() {  // F6: tiếp tục mục tiêu của task đang mở / mục tiêu xong gần nhất
  let ref = "";
  const x = S.openTask && S.state && S.state.tasks.find((y) => y.id === S.openTask);
  if (x) ref = x.goal ? "m" + x.goal : "t" + x.id;
  else { const c = ((S.state && S.state.continue) || [])[0]; if (c) ref = c.ref; }
  setView("board");
  prefill("/continue " + (ref ? ref + " " : ""));
  if (!ref) updateSuggest();
}
function prefill(text) {
  input.value = text;
  input.focus();
  input.setSelectionRange(text.length, text.length);
  autosize();
  renderComposerMode();
}
input.addEventListener("input", () => { autosize(); renderComposerMode(); updateSuggest(); renderContinueHint(); });

/* dán (Ctrl/⌘+V) hoặc kéo-thả ảnh vào ô nhập: gửi byte ảnh lên server (lưu .ateam/images như Ctrl+V của TUI) rồi
   chèn @đường/dẫn tại con trỏ — agent nhận ảnh theo cú pháp CLI của nó (mentions.render) */
async function attachImages(files) {
  for (const f of files) {
    let r;
    try { r = await (await fetch("/api/image", { method: "POST", body: f, headers: { "Content-Type": "application/octet-stream" } })).json(); }
    catch (e) { r = { error: String(e) }; }
    if (r.error) { toast(r.error, "warn"); continue; }
    const at = input.selectionStart, before = input.value.slice(0, at);
    const text = (before && !/\s$/.test(before) ? " " : "") + r.mention + " ";
    input.setRangeText(text, at, input.selectionEnd, "end");
    input.dispatchEvent(new Event("input"));
    toast(t("image_pasted", { v: r.path }), "ok");
  }
  input.focus();
}
const imageFiles = (list) => [...(list || [])].filter((f) => f && /^image\//.test(f.type));
input.addEventListener("paste", (e) => {
  const dt = e.clipboardData;
  if (!dt) return;
  const files = imageFiles([...dt.items].filter((i) => i.kind === "file").map((i) => i.getAsFile()));
  if (!files.length || dt.getData("text/plain")) return;  // có chữ (vd copy từ trang web) thì dán chữ như thường
  e.preventDefault();
  attachImages(files);
});
const composerBox = $("#composer-box");
composerBox.addEventListener("dragover", (e) => {
  if ([...e.dataTransfer.items].some((i) => i.kind === "file")) { e.preventDefault(); composerBox.classList.add("drop"); }
});
composerBox.addEventListener("dragleave", () => composerBox.classList.remove("drop"));
composerBox.addEventListener("drop", (e) => {
  composerBox.classList.remove("drop");
  const files = imageFiles(e.dataTransfer.files);
  if (!files.length) return;
  e.preventDefault();
  attachImages(files);
});
input.addEventListener("keydown", (e) => {
  const open = S.suggest.items.length > 0;
  if (open && e.key === "ArrowDown") { e.preventDefault(); moveSuggest(1); return; }
  if (open && e.key === "ArrowUp") { e.preventDefault(); moveSuggest(-1); return; }
  if (open && e.key === "Tab") { e.preventDefault(); pickSuggest(S.suggest.i); return; }
  if (open && e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    const it = S.suggest.items[S.suggest.i], k = S.suggest.kind, v = input.value;
    // tên lệnh đang gõ dở / tham số đang gõ dở / file: Enter = chọn gợi ý; đã gõ đủ thì gửi
    const typedFull = k === "cmd" ? v.trim() === "/" + it.name && !it.needs : k === "sh" ? !S.suggest.nav && v !== "!" : false;
    const argDone = k === "arg" && !S.suggest.nav && /\s$/.test(v);
    if (!typedFull && !argDone) {
      e.preventDefault();
      if (k === "cmd" && v.trim() === "/" + it.name && !it.needs) { submit(); return; }
      pickSuggest(S.suggest.i);
      if (k === "cmd" && !it.needs) submit();
      return;
    }
  }
  if (open && e.key === "Escape") { e.preventDefault(); hideSuggest(); return; }
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
});
input.addEventListener("blur", () => setTimeout(hideSuggest, 150));

/* ------------------------------------------------------------------ hành động (bấm) */
const VIEWS = ["board", "team", "grid", "term", "git", "code", "todo", "notes", "dash", "custom", "skills"];
function setView(v) {
  if (!VIEWS.includes(v)) return;
  const prev = S.view;
  S.view = v;
  $$(".nav-item[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  $$(".view").forEach((s) => s.classList.toggle("hidden", s.id !== "view-" + v));
  $(".composer").classList.toggle("hidden", v === "code");  // tab Code dùng cả chiều cao cho editor
  render();
  if (v === "term" && S.openJob != null && prev !== "term") loadJob(S.openJob);
  if (v === "git" && window.GitView) GitView.show();
  if (prev === "git" && v !== "git" && window.GitView) GitView.hide();
  if (v === "code" && window.CodeView) CodeView.show();
  if (v === "custom" && window.Setup) Setup.showCustom();
  if (v === "skills" && window.SkillsView) SkillsView.show();
  if (v === "team") loadCustom();
  if (v === "dash" && window.DashView) DashView.show();
  if (v === "todo" && window.TodoView) TodoView.show();
  if (v === "notes" && window.NotesView) NotesView.show();
  if (prev === "notes" && v !== "notes" && window.NotesView) NotesView.hide();
  if (v === "grid" && window.GridView) GridView.show();
  if (prev === "grid" && v !== "grid") document.documentElement.classList.remove("grid-full");
}
const ACTIONS = {
  "send": () => submit(),
  "flow-pick": () => pickMode(),
  "pause": () => send("pause", { on: !S.state.paused }),
  "clear": () => send("clear"),
  "theme": () => themeModal(),
  "syslog": () => openTask(0),
  "phone": () => phoneModal(),
  "open-project": () => projectModal(),
  "rules": () => RulesView.open(),
  "lofi": () => Lofi.open(),
  "quota-refresh": (el, e) => { e.stopPropagation(); QuotaView.refresh(); },
  "quota-open": () => setView("dash"),
  "side-toggle": () => setSideMin(!document.documentElement.classList.contains("side-min")),
  "roles": () => Setup.rolesModal(),
  "goal-plan": (el, e) => { e.stopPropagation(); planModal(+el.dataset.goal); },
  "copy-url": (el) => { navigator.clipboard.writeText(el.dataset.url).then(() => toast(t("copied"), "ok")); },
  "close-drawer": () => closeDrawer(),
  "close-modal": (el) => closeModal(el.closest(".modal")),
  "open-task": (el) => openTask(+el.dataset.task),
  "skill-view": (el, e) => { e.stopPropagation(); SkillsView.view(el.dataset.name); },
  "img-view": (el, e) => { e.stopPropagation(); imageModal(el.dataset.path); },
  "dr-tab": (el) => { S.drawerTab = el.dataset.tab; renderDrawer(true); if (S.drawerTab === "log") loadLog(S.openTask); },
  "goal-filter": (el) => { S.goalFilter = el.dataset.goal ? +el.dataset.goal : null; renderGoals(); renderKanban(); },
  "board-mode": (el) => setBoardMode(el.dataset.mode),
  "board-fold": (el) => toggleFold(el.dataset.key),
  "board-jump": (el) => boardJump(el.dataset.key),
  "goal-continue": (el) => prefill(`/continue m${el.dataset.goal} `),
  "goal-cancel-plan": (el, e) => { e.stopPropagation(); send("cancel_plan", { goal: +el.dataset.goal }); },
  "reassign": (el) => reassignModal(+el.dataset.task),
  "task-continue": (el) => prefill(`/continue t${el.dataset.task} `),
  "grill-pick": (el) => { const q = S.state.grill.question; send("grill", { action: "answer", goal: S.state.grill.goal, text: q.options[+el.dataset.i] }); },
  "grill-skip": () => send("grill", { action: "skip", goal: S.state.grill.goal }),
  "ask-pick": (el) => { const a = S.state.ask; send("ask", { action: "answer", task: a.task, text: a.question.options[+el.dataset.i] }); },
  "ask-skip": () => send("ask", { action: "skip", task: S.state.ask.task }),
  "ask-cancel": () => send("cancel", { task: S.state.ask.task }),
  "grill-done": () => send("grill", { action: "done", goal: S.state.grill.goal }),
  "grill-retry": () => send("grill", { action: "retry", goal: S.state.grill.goal }),
  "grill-cancel": () => send("grill", { action: "cancel", goal: S.state.grill.goal }),
  "plan-approve": (el) => send("approve", { goal: +el.dataset.goal }),
  "plan-drop": (el) => send("drop", { goal: +el.dataset.goal }),
  "plan-toggle": (el, e) => {
    if (e.target.closest("select")) return;
    const id = +el.dataset.task;
    S.expanded.has(id) ? S.expanded.delete(id) : S.expanded.add(id);
    renderPlan();
  },
  "plan-edit": (el) => startEdit(+el.dataset.task),
  "plan-save": (el) => {
    const id = +el.dataset.task;
    send("edit", { task: id, prompt: $(`#edit-${id}`).value });
    S.editing = null; delete $("#plan").dataset.sig; renderPlan();
  },
  "plan-unedit": () => { S.editing = null; delete $("#plan").dataset.sig; renderPlan(); },
  "retry": (el) => send("retry", { task: +el.dataset.task }),
  "cancel": (el) => send("cancel", { task: +el.dataset.task }),
  "delete-task": async (el) => {
    const id = +el.dataset.task;
    if (await confirmBox(t("delete_task_q", { id }), t("delete_task_text"), t("delete_task"))) send("delete_task", { task: id });
  },
  "merge": (el) => { send("merge", { task: +el.dataset.task }); const m = el.closest(".modal"); if (m) closeModal(m); },
  "reject": (el) => { const m = el.closest(".modal"); if (m) closeModal(m); if (S.openTask !== +el.dataset.task) openTask(+el.dataset.task); S.rejecting = true; renderDrawer(true); },
  "reject-send": (el) => { send("reject", { task: +el.dataset.task, feedback: $("#reject-fb").value }); S.rejecting = false; renderDrawer(true); },
  "reject-cancel": () => { S.rejecting = false; renderDrawer(true); },
  "diff": (el) => DiffView.task(+el.dataset.task),
  "agent-term": (el) => agentTerminal(el.dataset.agent),
  "agent-chat": (el) => chatModal(el.dataset.agent),
  "agent-add": () => Setup.addAgent(loadCustom),
  "agent-edit": (el) => Setup.editAgent(el.dataset.agent, loadCustom),
  "agent-del": (el) => Setup.deleteAgent(el.dataset.agent, loadCustom),
  "agent-opt": (el) => { if (!el.classList.contains("on")) request("agent_option", { agent: el.dataset.agent, key: el.dataset.key, value: el.dataset.v }); },
  "agent-pick": (el) => { const a = S.meta.agents.find((x) => x.name === el.dataset.agent); if (a) pickerModal({ agent: a.name, key: "model", items: a.models, current: a.model, then_effort: true }); },
  "open-job": (el) => openJob(+el.dataset.job),
  "job": (el) => send("job", { id: +el.dataset.job, action: el.dataset.act }),
  "run-script": (el) => send("submit", { text: "!" + el.dataset.cmd }),
  "sg-pick": (el) => pickSuggest(+el.dataset.i),
};
document.addEventListener("click", (e) => {
  const nav = e.target.closest(".nav-item[data-view]");
  if (nav) { setView(nav.dataset.view); return; }
  if (e.target.closest("a")) return;
  const el = e.target.closest("[data-action]");
  if (el && el.tagName !== "SELECT" && ACTIONS[el.dataset.action]) ACTIONS[el.dataset.action](el, e);
});
document.addEventListener("mousedown", (e) => { if (e.target.closest("#suggest")) e.preventDefault(); });
document.addEventListener("change", (e) => {
  const el = e.target;
  if (el.dataset.action === "plan-assign") send("assign", { task: +el.dataset.task, agent: el.value });
});
document.addEventListener("keydown", (e) => {
  if (e.target.closest && e.target.closest(".xterm")) return;  // phím gõ trong terminal là của CLI (Esc, Ctrl+K…)
  if (e.altKey && !e.ctrlKey && !e.metaKey && /^Digit[0-9]$/.test(e.code)) {  // Alt+1…9, 0: tới thẳng tab (như TUI)
    const b = $$("#nav .nav-item")[(+e.code.slice(5) || 10) - 1];
    if (b) { e.preventDefault(); setView(b.dataset.view); }
    return;
  }
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); if (S.view === "code") setView("board"); input.focus(); return; }
  if (e.key === "F2") {
    e.preventDefault();
    const g = S.state && S.state.goals.find((x) => x.status === "awaiting");
    if (g) send("approve", { goal: g.id });
    return;
  }
  if (e.key === "F6" || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "o" && S.view !== "code")) {
    e.preventDefault(); continueShortcut(); return;
  }
  if (e.key === "F1") { e.preventDefault(); helpModal(); return; }
  if (e.key === "Escape") {
    if (e.target.closest && e.target.closest(".cm-editor")) return;  // Esc trong editor là của vim
    if (topModal()) { e.preventDefault(); closeModal(); }
    else if (window.Lofi && Lofi.popOpen()) Lofi.hidePop();
    else if (window.TodoPop && TodoPop.isOpen()) TodoPop.close();
    else if (S.view === "todo" && window.TodoView && TodoView.escape()) e.preventDefault();
    else if (S.view === "notes" && window.NotesView && NotesView.escape()) e.preventDefault();
    else if (S.openTask != null) closeDrawer();
  }
  if (e.key === "F7" && S.view === "team" && !topModal()) {  // như TUI: chat với agent đang trỏ (hoặc trưởng nhóm)
    e.preventDefault();
    const row = e.target.closest && e.target.closest(".ag-row");
    focusAgent(row ? row.dataset.agent : null);
  }
});

/* đồng hồ: cập nhật thời gian chạy mỗi giây mà không vẽ lại */
setInterval(() => {
  const n = now();
  $$("[data-since]").forEach((el) => { el.textContent = dur(n - +el.dataset.since); });
}, 1000);

autosize();
connect();
