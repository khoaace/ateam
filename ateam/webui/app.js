/* ateam web — nói chuyện với server qua WebSocket (xem ateam/web.py). Mọi chữ hiển thị lấy từ S.T (dịch ở Python). */
"use strict";

const S = {
  T: {}, commands: [], agentNames: [], meta: {}, prefs: {}, state: null, ws: null, connected: false, retry: 0,
  pending: {}, refSeq: 0, branches: null, branchesAt: 0,
  view: "board", goalFilter: null, openTask: null, drawerTab: "log", openJob: null,
  expanded: new Set(), editing: null, rejecting: false,
  logs: [], agentLogs: {}, jobLines: {}, scripts: null, scriptsAt: 0,
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
  ws.onopen = () => { S.retry = 0; setConn(true); };
  ws.onclose = () => {
    setConn(false);
    setTimeout(connect, Math.min(5000, 500 * 2 ** S.retry++));
  };
  ws.onmessage = (ev) => {
    let m;
    try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.t === "hello") onHello(m);
    else if (m.t === "state") { S.state = m; render(); }
    else if (m.t === "log") onLog(m);
    else if (m.t === "job") onJobLine(m);
    else if (m.t === "toast") onToast(m);
    else if (m.t === "notice") onNotice(m);
    else if (m.t === "prefs") applyPrefs(m);
    else if (m.t === "discovered" && window.Setup) Setup.discovered();
  };
}
function send(op, data = {}) {
  if (!S.ws || S.ws.readyState !== 1) { toast(t("disconnected"), "error"); return false; }
  S.ws.send(JSON.stringify(Object.assign({ op }, data)));
  return true;
}
/* gửi thao tác và chờ trả lời (toast cùng ref) — dùng khi cần kết quả: lưu file, commit… */
function request(op, data = {}) {
  const ref = ++S.refSeq;
  return new Promise((resolve) => {
    S.pending[ref] = resolve;
    if (!send(op, Object.assign({ ref }, data))) { delete S.pending[ref]; resolve({ level: "error" }); }
  });
}
function setConn(ok) {
  S.connected = ok;
  $("#conn").classList.toggle("ok", ok);
  $("#conn-text").textContent = ok ? t("connected") : t("disconnected");
}
function onHello(m) {
  const first = !S.meta.version;
  S.T = m.T; S.commands = m.commands; S.meta = m;
  S.agentNames = m.agents.map((a) => a.name);
  document.documentElement.lang = m.lang;
  $("#proj").textContent = m.project;
  $("#proj").title = m.root;
  $("#ver").textContent = "ateam " + m.version;
  $$("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });
  $("#btn-theme").title = t("theme");
  $("#kbd-hint").textContent = t("shortcuts");
  applyPrefs(m.prefs);
  document.body.classList.toggle("readonly", !!m.readonly);
  if (m.readonly && !$("#ro-banner")) document.body.insertAdjacentHTML("afterbegin", `<div id="ro-banner" class="ro-banner">${esc(t("readonly_banner"))}</div>`);
  setConn(true);
  if (S.openTask != null) loadLog(S.openTask);
  if (S.openJob != null) loadJob(S.openJob);
  for (const name of S.agentNames) loadAgentTail(name);
  if (first && m.needs_setup && window.Setup) Setup.open(true);  // lần đầu dùng ateam: wizard thiết lập
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
  if (m.text) toast(m.text, m.level || "info");
  if (m.reload) setTimeout(() => location.reload(), 600);
  if (m.notify) { S.prefs = Object.assign({}, S.prefs, { notify: m.notify }); askNotifyPermission(); }
  const o = m.open || {};
  if (o.job != null) { setView("term"); openJob(o.job); }
  if (o.diff != null) DiffView.task(o.diff);
  if (o.plan != null) planModal(o.plan);
  if (o.task != null) openTask(o.task);
  if (o.view) setView(o.view);
  if (o.git_ai && window.GitView) GitView.aiMessage();
  if (o.modal === "help") helpModal();
  if (o.modal === "theme") themeModal();
  if (o.modal === "setup" && window.Setup) Setup.open(false);
  if (o.modal === "roles" && window.Setup) Setup.rolesModal();
  if (o.modal === "custom" && window.Setup) Setup.custom();
  if (o.modal === "flow" && window.Setup) Setup.flowModal({ onSaved: () => { if (S.view === "custom") Setup.showCustom(); } });
  if ((o.modal === "branches" || o.modal === "stash") && window.GitView) GitView[o.modal]();
  if (o.text) textModal(o.text.title, o.text.body);
  if (o.picker) pickerModal(o.picker);
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
   st giữ trạng thái giữa các dòng: đang trong ``` hay trong khối <<<NOTE>>>/<<<DELEGATE>>> */
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
function mdBlockOpen(s, st) {  // <<<NOTE>>> / <<<DELEGATE to=… title=…>>> — có thể kết thúc ngay trên dòng này
  const m = /<<<(NOTE|DELEGATE)\b([^>]*)>>>/.exec(s);
  if (!m) return null;
  let rest = s.slice(m.index + m[0].length), head;
  const kind = m[1] === "NOTE" ? "note" : "del";
  if (kind === "note") {
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
  return (pre ? `<div class="l">${mdInline(pre)}</div>` : "")
    + `<div class="l md-${kind} md-start${end >= 0 ? " md-end" : ""}">${head}${rest.trim() ? (kind === "note" ? " " : "<br>") + mdInline(rest.trim()) : ""}</div>`;
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
function onLog(m) {
  if (S.openTask != null && m.task === S.openTask && S.drawerTab === "log") {
    S.logs.push(m.line);
    appendLines($("#dr-log"), [m.line]);
  }
  if (m.agent) {
    const arr = S.agentLogs[m.agent] || (S.agentLogs[m.agent] = []);
    arr.push(m.raw);
    if (arr.length > 300) arr.splice(0, arr.length - 300);
    appendLines($(`[data-mini="${CSS.escape(m.agent)}"]`), [m.raw], 300);
  }
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
  for (const x of S.state.tasks) {
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
  if (S.view === "board") { renderGrill(); renderPlan(); renderGoals(); renderKanban(); }
  if (S.view === "team") renderTeam();
  if (S.view === "term") renderTerm();
  if (window.TodoView) TodoView.render();  // cả số việc chưa xong trên thanh bên
  if (S.openTask != null) renderDrawer(false);
  renderContinueHint();
}
function renderTop() {
  const st = S.state, c = counts();
  const titles = { board: t("board"), team: t("team"), term: t("terminal"), git: t("git"), code: t("code"), todo: t("todo"), custom: t("custom"), dash: t("dash") };
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
        <span class="plan-title">${esc(x.title)}</span>
        <span class="deps">${x.deps.length ? esc(t("after", { v: x.deps.map((d) => "#" + d).join(", ") })) : ""}</span>
        <span class="muted" style="font-size:12px">${esc([x.model, x.effort].filter(Boolean).join(" · "))}</span>
      </div>
      ${S.expanded.has(x.id) ? `<div class="plan-detail">
        <div class="prompt-box md">${mdHtml(x.prompt)}</div>
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
    box.innerHTML = `<div class="empty">
      <div class="empty-ico"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/></svg></div>
      <div class="big">${esc(t("no_goals"))}</div><div>${esc(t("no_goals_hint"))}</div></div>`;
    return;
  }
  if (S.goalFilter != null && !goals.some((g) => g.id === S.goalFilter)) S.goalFilter = null;
  const cards = goals.slice().reverse().map((g) => {
    const ts = S.state.tasks.filter((x) => x.goal === g.id && x.status !== "draft");
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
      </div>
    </div>`;
  }).join("");
  box.innerHTML = `<div class="goal goal-all${S.goalFilter == null ? " sel" : ""}" data-action="goal-filter" data-goal="">${esc(t("all_goals"))}</div>` + cards;
}

/* 📋 kế hoạch của một mục tiêu — xem lại sau khi đã duyệt / xong: mọi task, nhóm theo nguồn, bấm dòng xem prompt */
const PLAN_SOURCES = ["plan", "workflow", "review", "followup", "delegate", "user"];
async function planModal(gid) {
  const r = await request("goal_plan", { goal: gid });
  const p = r.goal_plan;
  if (!p) return;
  const groups = {};
  for (const x of p.tasks) {
    const k = (x.source || "plan").split(":")[0];
    (groups[PLAN_SOURCES.includes(k) ? k : "plan"] = groups[PLAN_SOURCES.includes(k) ? k : "plan"] || []).push(x);
  }
  const row = (x) => `
    <div class="plan-row">
      <div class="plan-line" data-pv="${x.id}">
        <span class="tid">#${x.id}</span>
        <span>${agentHtml(x.agent)}</span>
        <span class="plan-title">${esc(x.title)}${x.source && x.source.startsWith("delegate:") ? ` <span class="muted small">← ${esc(x.source.slice(9))}</span>` : ""}</span>
        <span class="deps">${x.deps.length ? esc(t("after", { v: x.deps.map((d) => "#" + d).join(", ") })) : esc([x.model, x.effort].filter(Boolean).join(" · "))}</span>
        ${badge(x.status, STATUS_LABEL(x.status), x.status === "running")}
      </div>
      <div class="plan-detail hidden"><div class="prompt-box md">${mdHtml(x.prompt)}</div></div>
    </div>`;
  const body = PLAN_SOURCES.filter((k) => groups[k]).map((k) => `
    <div class="sec-title" style="margin:14px 0 6px">${esc(t("src_" + k))} <span class="muted">· ${groups[k].length}</span></div>
    <div class="plan-rows plan-box">${groups[k].map(row).join("")}</div>`).join("");
  const g = p.goal;
  const m = openModal(`${modalHead("📋 " + esc(t("goal_plan_title", { id: g.id })))}<div class="modal-pad">
    <div class="prompt-box md">${mdHtml(g.text)}</div>
    ${g.summary ? `<div class="goal-sum" style="margin-top:8px">${esc(g.summary)}</div>` : ""}
    ${body || `<div class="muted" style="margin-top:12px">${esc(t("plan_empty"))}</div>`}</div>`, { box: "lg" });
  m.addEventListener("click", (e) => {
    const line = e.target.closest("[data-pv]");
    if (line) line.nextElementSibling.classList.toggle("hidden");
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
function renderKanban() {
  const box = $("#kanban");
  let tasks = S.state.tasks;
  if (S.goalFilter != null) tasks = tasks.filter((x) => x.goal === S.goalFilter);
  const lastLine = {};
  for (const a of S.state.agents) for (const act of a.activities) if (act.task_id) lastLine[act.task_id] = act.last_line;
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
    body.innerHTML = list.length ? list.map((x) => cardHtml(x, lastLine[x.id])).join("") : `<div class="col-empty">${esc(t("empty_col"))}</div>`;
  }
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
      ${x.goal ? `<span class="meta" style="margin-left:auto">🎯 #${x.goal}</span>` : ""}</div>
  </div>`;
}

/* đội */
function renderTeam() {
  const box = $("#team");
  const sig = S.state.agents.map((a) => a.name).join();
  if (box.dataset.sig !== sig) {
    box.dataset.sig = sig;
    box.innerHTML = S.state.agents.map((a) => `<div class="agent-card" data-agent="${esc(a.name)}">
      <div class="agent-head" data-head></div><div class="acts" data-acts></div>
      <div class="mini-log log" data-mini="${esc(a.name)}"></div></div>`).join("");
    for (const a of S.state.agents) {
      const mini = $(`[data-mini="${CSS.escape(a.name)}"]`);
      appendLines(mini, S.agentLogs[a.name] || [], 300);
      mini.scrollTop = mini.scrollHeight;
    }
  }
  for (const a of S.state.agents) {
    const card = $(`.agent-card[data-agent="${CSS.escape(a.name)}"]`);
    if (!card) continue;
    const busy = a.activities.length > 0;
    card.classList.toggle("busy", busy);
    card.classList.toggle("cool", !!a.cooldown);
    const st = !a.installed ? badge("failed", t("not_installed"))
      : a.cooldown ? badge("review", t("cooldown", { v: a.cooldown }))
      : busy ? badge("running", t("agent_running", { n: a.activities.length }), true) : badge("queued", t("idle"));
    $("[data-head]", card).innerHTML = `<span class="av lg" style="--h:${hue(a.name)}">${esc(a.name[0])}</span>
      <div style="min-width:0;cursor:pointer" data-action="agent-pick" data-agent="${esc(a.name)}" title="${esc(t("pick_hint"))}"><div class="agent-name">${esc(a.name)}${a.lead ? `<span class="lead-tag">★ ${esc(t("lead"))}</span>` : ""}</div>
      <div class="agent-label">${esc(a.label)}</div></div>${st}`;
    $("[data-acts]", card).innerHTML = a.activities.map((act) => `
      <div class="act" ${act.task_id ? `data-action="open-task" data-task="${act.task_id}"` : ""}>
        <span class="spin" style="--c:var(--running)"></span>
        <span class="title">${act.task_id ? "#" + act.task_id + " " : ""}${esc(act.title)}</span>
        <span class="lbl">${esc(act.label)}</span>${elapsedHtml(act.started)}
      </div>`).join("");
  }
}

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
function onJobLine(m) { if (m.id === S.openJob) appendLines($("#tw-body"), [m.line], 5000, false); }
async function loadScripts() {
  S.scriptsAt = now();
  try { S.scripts = await (await fetch("/api/scripts")).json(); } catch (e) { S.scripts = []; }
}

/* ------------------------------------------------------------------ ngăn chi tiết task */
function openTask(tid) {
  S.openTask = tid; S.rejecting = false; S.logs = [];
  if (S.drawerTab !== "log" && tid === 0) S.drawerTab = "log";
  renderDrawer(true);
  $("#drawer").classList.add("open");
  if (S.drawerTab === "log") loadLog(tid);
  $$(".card.sel").forEach((c) => c.classList.remove("sel"));
  $$(`.card[data-task="${tid}"]`).forEach((c) => c.classList.add("sel"));
}
function closeDrawer() {
  S.openTask = null;
  $("#drawer").classList.remove("open");
  $$(".card.sel").forEach((c) => c.classList.remove("sel"));
}
function renderDrawer(full) {
  const tid = S.openTask, dr = $("#drawer");
  const x = tid ? S.state && S.state.tasks.find((y) => y.id === tid) : null;
  if (tid && !x) { if (S.state) closeDrawer(); return; }
  const sig = x ? JSON.stringify([x.status, x.agent, x.title, x.started, x.finished, x.result, x.error, S.drawerTab, S.rejecting]) : "sys" + S.drawerTab;
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
  else if (S.drawerTab === "prompt") body = `<div class="dr-body"><div class="prompt-box md" style="max-height:none">${mdHtml(x.prompt)}</div></div>`;
  else body = `<div class="dr-body">${x.error ? `<div class="sec-title">${esc(t("error"))}</div><div class="error-box">${esc(x.error)}</div>` : ""}
      <div class="result-box md">${x.result ? mdHtml(x.result) : `<span class="muted">${esc(t("no_result"))}</span>`}</div></div>`;
  dr.innerHTML = `<div class="dr-head">${head}</div>${tabs}${body}`;
  if (logNode) $("#dr-log").replaceWith(logNode);  // giữ log đang hiện (và vị trí cuộn), chỉ vẽ lại phần đầu
  if (S.rejecting) $("#reject-fb").focus();
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
  if (["done", "failed"].includes(st)) b.push(`<button class="btn sm" data-action="task-continue" data-task="${x.id}">↪ ${esc(t("continue_task"))}</button>`);
  if (["queued", "running", "draft", "review"].includes(st)) b.push(`<button class="btn sm danger" data-action="cancel" data-task="${x.id}">■ ${esc(t("cancel"))}</button>`);
  return b.join("");
}

/* mở trên điện thoại: URL kèm token + mã QR (GET /api/remote) */
async function phoneModal() {
  let r;
  try { r = await fetch("/api/remote").then((x) => x.json()); } catch (e) { return; }
  let body;
  if (!r.enabled) {
    body = `<p>${esc(t("phone_local"))}</p>
      <div class="phone-cmd"><code>ateam web --host 0.0.0.0</code><span class="muted small">${esc(t("phone_local_lan"))}</span></div>
      <div class="phone-cmd"><code>ateam web --tunnel</code><span class="muted small">${esc(t("phone_local_tunnel"))}</span></div>`;
  } else {
    body = `<p class="muted small">${esc(t("phone_hint"))}${r.readonly ? " " + esc(t("phone_ro")) : ""}</p>
      <div class="phone-grid">${r.urls.map((u) => `<div class="phone-item"><b>${esc(u.label)}</b>${u.svg ? `<img class="phone-qr" alt="QR" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(u.svg)}">` : ""}
        <div class="phone-url"><code>${esc(u.url)}</code><button class="btn sm" data-action="copy-url" data-url="${esc(u.url)}">${esc(t("phone_copy"))}</button></div></div>`).join("")}</div>`;
  }
  openModal(`${modalHead("📱 " + esc(t("phone_title")))}<div class="modal-pad">${body}</div>`);
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
    await request("agent_option", { agent: p.agent, key: p.key, value: v });
    const a = S.meta.agents.find((x) => x.name === p.agent);
    if (p.then_effort && p.key === "model" && a && a.efforts.length) pickerModal({ agent: p.agent, key: "effort", items: a.efforts, current: a.effort });
  };
  m.addEventListener("click", (e) => { const b = e.target.closest(".pick"); if (b) choose(b.dataset.v); });
  $("#pick-custom", m).addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.value.trim()) choose(e.target.value.trim()); });
}

/* ------------------------------------------------------------------ giao diện sáng/tối + màu nhấn */
function themeMode() { try { return localStorage.getItem("ateam-theme") || "system"; } catch (e) { return "system"; } }
function setThemeMode(mode) {
  try { mode === "system" ? localStorage.removeItem("ateam-theme") : localStorage.setItem("ateam-theme", mode); } catch (e) { /* chặn lưu */ }
  if (mode === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = mode;
  if (window.CodeView) CodeView.prefsChanged();
}
function isDark() {
  const d = document.documentElement.dataset.theme;
  return d ? d === "dark" : !matchMedia("(prefers-color-scheme: light)").matches;
}
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
  $("#snd-test", m).addEventListener("click", () => soundDemo(["plan", "ask", "failed", "done"], on.checked ? +vol.value : 60));
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
  toast(m.title + " — " + m.body, m.level === "warn" ? "warn" : "info");
  playSound(m.kind);
  if (!m.desktop || !("Notification" in window) || Notification.permission !== "granted") return;
  if (!document.hidden && !m.force) return;
  try {
    const n = new Notification(m.title, { body: m.body, tag: "ateam-" + m.kind + "-" + (m.task || m.goal || "")});
    n.onclick = () => {
      window.focus(); n.close();
      if (m.task != null) openTask(m.task);
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
const SOUNDS = {  // nốt: [tần số Hz, bắt đầu (giây), dài (giây)]
  plan: { wave: "sine", notes: [[659, 0, .2], [880, .13, .35]] },
  review: { wave: "sine", notes: [[1047, 0, .5]] },
  ask: { wave: "sine", notes: [[784, 0, .16], [988, .11, .16], [1175, .22, .38]] },
  failed: { wave: "triangle", notes: [[440, 0, .25], [330, .18, .45]] },
  done: { wave: "sine", notes: [[523, 0, .45], [659, .09, .45], [784, .18, .45], [1047, .27, .7]] },
};
SOUNDS.conflict = SOUNDS.goal_end = SOUNDS.failed;
SOUNDS.test = SOUNDS.review;
const SOUND_RANK = ["test", "done", "review", "plan", "ask", "goal_end", "conflict", "failed"];  // sau = ưu tiên
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
    g.gain.linearRampToValueAtTime(.35, t + .012);
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
function toast(text, level = "info") {
  const el = document.createElement("div");
  el.className = "toast " + level;
  el.textContent = text;
  $("#toasts").appendChild(el);
  const ms = level === "error" || level === "warn" ? 6000 : 3800;
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 250); }, ms);
  while ($("#toasts").childElementCount > 5) $("#toasts").firstElementChild.remove();
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
  $("#hint").textContent = t("send_hint");
}
function submit() {
  const text = input.value.trim();
  if (!text) return;
  send("submit", { text });
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
function taskItems(q, statuses) {
  const ts = ((S.state && S.state.tasks) || []).slice().reverse().filter((x) => !statuses || statuses.includes(x.status));
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
    case "retry": case "cancel": case "merge": case "reject": case "diff":
      return pos ? null : { head: t("sg_task"), items: taskItems(tok, TASK_FILTERS[cmd]).map((i) => ({ ...i, value: i.value + (cmd === "reject" ? " " : "") })) };
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
const VIEWS = ["board", "team", "term", "git", "code", "todo", "dash", "custom"];
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
  if (v === "dash" && window.DashView) DashView.show();
  if (v === "todo" && window.TodoView) TodoView.show();
}
const ACTIONS = {
  "send": () => submit(),
  "pause": () => send("pause", { on: !S.state.paused }),
  "clear": () => send("clear"),
  "theme": () => themeModal(),
  "syslog": () => openTask(0),
  "phone": () => phoneModal(),
  "lofi": () => Lofi.open(),
  "roles": () => Setup.rolesModal(),
  "goal-plan": (el, e) => { e.stopPropagation(); planModal(+el.dataset.goal); },
  "copy-url": (el) => { navigator.clipboard.writeText(el.dataset.url).then(() => toast(t("copied"), "ok")); },
  "close-drawer": () => closeDrawer(),
  "close-modal": (el) => closeModal(el.closest(".modal")),
  "open-task": (el) => openTask(+el.dataset.task),
  "dr-tab": (el) => { S.drawerTab = el.dataset.tab; renderDrawer(true); if (S.drawerTab === "log") loadLog(S.openTask); },
  "goal-filter": (el) => { S.goalFilter = el.dataset.goal ? +el.dataset.goal : null; renderGoals(); renderKanban(); },
  "goal-continue": (el) => prefill(`/continue m${el.dataset.goal} `),
  "task-continue": (el) => prefill(`/continue t${el.dataset.task} `),
  "grill-pick": (el) => { const q = S.state.grill.question; send("grill", { action: "answer", goal: S.state.grill.goal, text: q.options[+el.dataset.i] }); },
  "grill-skip": () => {
    const g = S.state.grill, q = g.question || {};
    send("grill", { action: "answer", goal: g.goal, text: q.rec ? t("grill_skip_rec", { v: q.rec }) : t("grill_skip_answer") });
  },
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
  "merge": (el) => { send("merge", { task: +el.dataset.task }); const m = el.closest(".modal"); if (m) closeModal(m); },
  "reject": (el) => { const m = el.closest(".modal"); if (m) closeModal(m); if (S.openTask !== +el.dataset.task) openTask(+el.dataset.task); S.rejecting = true; renderDrawer(true); },
  "reject-send": (el) => { send("reject", { task: +el.dataset.task, feedback: $("#reject-fb").value }); S.rejecting = false; renderDrawer(true); },
  "reject-cancel": () => { S.rejecting = false; renderDrawer(true); },
  "diff": (el) => DiffView.task(+el.dataset.task),
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
    else if (S.openTask != null) closeDrawer();
  }
});

/* đồng hồ: cập nhật thời gian chạy mỗi giây mà không vẽ lại */
setInterval(() => {
  const n = now();
  $$("[data-since]").forEach((el) => { el.textContent = dur(n - +el.dataset.since); });
}, 1000);

autosize();
connect();
