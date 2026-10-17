/* Dashboard — như tab 📊 Thống kê của TUI: token, cost, lượt chạy (hôm nay / 7 / 30 ngày), biểu đồ theo ngày,
   theo agent / model, lịch sử mục tiêu. Số liệu: GET /api/dashboard, /api/goals (reports.dashboard, goal_history). */
"use strict";

window.DashView = (() => {
  const D = { data: null, goals: [], open: null, timer: null, sig: "" };

  function tok(n) {
    n = n || 0;
    if (n < 1000) return String(n);
    if (n >= 1e6) return (n < 1e7 ? (n / 1e6).toFixed(1) : Math.floor(n / 1e6)) + "M";
    return (n < 1e4 ? (n / 1000).toFixed(1) : Math.floor(n / 1000)) + "k";
  }
  function cost(v) { return v == null ? "—" : v >= 0.01 || v === 0 ? "$" + v.toFixed(2) : "<$0.01"; }

  async function load() {
    try {
      const [data, goals] = await Promise.all([fetch("/api/dashboard").then((r) => r.json()), fetch("/api/goals").then((r) => r.json())]);
      const sig = JSON.stringify([data, goals]);
      if (sig === D.sig) return;
      D.sig = sig; D.data = data; D.goals = goals;
      render();
    } catch (e) { /* server đang khởi động lại */ }
  }
  function show() {
    load();
    clearInterval(D.timer);
    D.timer = setInterval(() => { if (S.view === "dash") load(); else clearInterval(D.timer); }, 5000);
  }

  function card(label, b) {
    return `<div class="panel dcard"><div class="dlabel">${esc(label)}</div>
      <div class="dbig">${tok(b.tokens)} <small>token</small></div>
      <div class="muted small">in ${tok(b.in_tok)} · out ${tok(b.out_tok)} · cache ${tok(b.cache)}</div>
      <div class="drow"><b class="dcost">${cost(b.cost)}</b><span class="muted small">${esc(t("dash_runs", { n: b.runs }))} · ${dur(b.secs)}</span></div>
      ${b.failed || b.ratelimits ? `<div class="small warn-text">${esc(t("dash_failed", { f: b.failed, r: b.ratelimits }))}</div>` : ""}</div>`;
  }
  function chart(days) {
    const top = Math.max(1, ...days.map((d) => d.tokens)), W = 640, H = 150, bw = W / days.length;
    const bars = days.map((d, i) => {
      const h = d.tokens ? Math.max(3, (d.tokens / top) * (H - 26)) : 0;
      return `<g><title>${esc(d.day)}: ${tok(d.tokens)} token · ${cost(d.cost)} · ${esc(t("dash_runs", { n: d.runs }))}</title>
        <rect x="${i * bw + 4}" y="${H - 18 - h}" width="${bw - 8}" height="${h}" rx="4" class="dbar"/>
        <text x="${i * bw + bw / 2}" y="${H - 4}" text-anchor="middle" class="dtick">${esc(d.day.slice(8))}</text></g>`;
    }).join("");
    return `<svg viewBox="0 0 ${W} ${H}" class="dchart" role="img" aria-label="${esc(t("dash_chart"))}">${bars}</svg>`;
  }
  function table(title, rows, head) {
    const list = Object.entries(rows).sort((a, b) => b[1].tokens - a[1].tokens);
    if (!list.length) return "";
    return `<div class="panel dtable"><div class="ghead">${esc(title)}</div><table class="ob-table">
      <tr class="muted">${[head, t("dash_col_runs"), t("dash_col_time"), "Token", "Cost", t("dash_col_failed"), t("dash_col_real")].map((h) => `<td>${esc(h)}</td>`).join("")}</tr>
      ${list.map(([k, b]) => `<tr><td><b>${esc(k === "—" ? t("df_agent_default") : k)}</b></td><td>${b.runs}</td><td>${dur(b.secs)}</td><td>${tok(b.tokens)}</td><td>${cost(b.cost)}</td><td>${b.failed}</td><td class="muted">${b.real}/${b.runs}</td></tr>`).join("")}</table></div>`;
  }
  function goalRow(g) {
    const open = D.open === g.id;
    const when = g.created ? new Date(g.created * 1000).toLocaleString([], { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
    return `<div class="dgoal${open ? " open" : ""}" data-dg="${g.id}">
      <div class="dgoal-head"><span class="muted mono">#${g.id}</span><b class="dgoal-text">${esc(g.text.split("\n")[0])}</b>
        <span class="chip s-${esc(g.status)}">${esc(t("g_" + g.status))}</span>
        <span class="muted small">${g.done}/${g.tasks} task${g.failed ? ` · ✗${g.failed}` : ""}</span>
        <span class="muted small">${esc(g.agents.join(", "))}</span><span class="muted small">${esc(when)}</span>
        <span class="small">${tok(g.tokens)}</span><b class="small">${cost(g.cost)}</b></div>
      ${open ? `<div class="dgoal-body"><div class="pre">${esc(g.text)}</div>
        ${g.summary ? `<div><b>${esc(t("dash_result"))}</b> ${esc(g.summary)}</div>` : ""}
        <div class="muted small">${esc(t("dash_goal_stats", { n: g.runs, v: dur(g.secs), tok: tok(g.tokens), real: g.real, cost: cost(g.cost) }))}${g.workflow ? " · workflow " + esc(g.workflow) : ""}</div>
        <div class="row-actions"><button class="btn sm primary" data-dga="continue" data-id="${g.id}">↪ ${esc(t("dash_continue"))}</button>
          <button class="btn sm ghost" data-dga="board">${esc(t("board"))}</button></div></div>` : ""}</div>`;
  }
  function render() {
    const el = $("#dash"), d = D.data;
    if (!el || !d) return;
    el.innerHTML = `<div class="dcards">${card(t("dash_today"), d.today)}${card(t("dash_week"), d.week)}${card(t("dash_month"), d.month)}</div>
      <div class="panel"><div class="ghead">${esc(t("dash_chart"))}</div>${chart(d.per_day)}</div>
      <div class="dtables">${table(t("dash_by_agent"), d.by_agent, "Agent")}${table(t("dash_by_model"), d.by_model, "Model")}</div>
      <div class="panel"><div class="ghead">${esc(t("dash_history"))}</div>
        ${D.goals.map(goalRow).join("") || `<div class="muted small pad">${esc(t("dash_no_goals"))}</div>`}</div>
      <div class="muted small">${esc(d.note)}</div>`;
  }
  document.addEventListener("click", (e) => {
    if (S.view !== "dash") return;
    const a = e.target.closest("[data-dga]");
    if (a) {
      if (a.dataset.dga === "continue") prefill(`/continue m${a.dataset.id} `);
      if (a.dataset.dga === "board") setView("board");
      return;
    }
    const g = e.target.closest(".dgoal-head");
    if (g) { const id = +g.parentElement.dataset.dg; D.open = D.open === id ? null : id; render(); }
  });
  return { show, load };
})();
