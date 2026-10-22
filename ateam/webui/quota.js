/* Hạn mức 5 giờ / tuần của claude, codex, agy: tin "quota" qua WebSocket (server hỏi lại mỗi 60 giây — quota.py),
   nút ⟳ gọi GET /api/quota?refresh=1. Khối nhỏ ở chân thanh bên (mỗi khung lấy nhóm model dùng nhiều nhất — giới
   hạn chạm trước) + chi tiết ở đầu trang Thống kê. Đếm ngược giờ hồi tính ở trình duyệt, vẽ lại mỗi 30 giây. */
"use strict";

window.QuotaView = (() => {
  const Q = { items: null, at: 0, busy: false };
  const NAMES = { agy: "antigravity" };
  const KINDS = ["5h", "week"];

  const pct = (v) => Math.round(v);
  const level = (v) => (v >= 90 ? "q-hi" : v >= 70 ? "q-mid" : "q-lo");
  function left(ts) {
    const s = ts - now();
    if (s <= 0) return t("quota_reset_past");
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    return t("quota_reset_in", { v: d ? `${d}d ${h}h` : h ? `${h}h ${String(m).padStart(2, "0")}m` : `${Math.max(1, m)}m` });
  }
  const when = (ts) => new Date(ts * 1000).toLocaleString([], { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  const reset = (w) => (w.resets_at ? `${left(w.resets_at)} · ${when(w.resets_at)}` : "");
  const tip = (w) => [w.group, t("quota_used", { v: pct(w.used) }), reset(w)].filter(Boolean).join(" · ");
  const bar = (w, big) => `<div class="qbar${big ? " big" : ""} ${level(w.used)}"><i style="width:${w.used}%"></i></div>`;
  const refreshBtn = () => `<button class="q-refresh${Q.busy ? " busy" : ""}" type="button" data-action="quota-refresh" title="${esc(t("quota_refresh"))}">⟳</button>`;

  function worst(item) {
    const by = {};
    for (const w of item.windows) if (!by[w.kind] || w.used > by[w.kind].used) by[w.kind] = w;
    return Object.values(by).sort((a, b) => (KINDS.indexOf(a.kind) + 1 || 9) - (KINDS.indexOf(b.kind) + 1 || 9));
  }

  function side() {
    const el = $("#quota");
    if (!el) return;
    const items = (Q.items || []).filter((i) => i.windows.length);
    el.innerHTML = !items.length ? "" : `<div class="q-head"><span>${esc(t("quota"))}</span>${refreshBtn()}</div>` + items.map((i) => {
      const ws = worst(i), top = Math.max(...ws.map((w) => w.used)), name = NAMES[i.cli] || i.cli;
      return `<div class="q-cli" data-action="quota-open" title="${esc(name + " · " + ws.map((w) => `${w.label} ${pct(w.used)}%`).join(" · "))}">
        <div class="q-name"><span class="q-dot ${level(top)}"></span><span class="q-n">${esc(name)}</span></div>
        ${ws.map((w) => `<div class="q-row" title="${esc(tip(w))}"><span>${esc(w.label)}</span>${bar(w)}<span class="q-v">${pct(w.used)}%</span></div>`).join("")}</div>`;
    }).join("");
  }

  function card(i) {
    const rows = i.windows.map((w) => `<div class="q-big">
        <div class="q-line"><b>${esc(w.label)}</b><span class="muted small">${esc(w.group)}</span><span class="q-pct">${esc(t("quota_used", { v: pct(w.used) }))}</span></div>
        ${bar(w, true)}<div class="muted small">${esc(reset(w))}</div></div>`).join("");
    return `<div class="qcard"><div><b>${esc(NAMES[i.cli] || i.cli)}</b><div class="muted small">${esc(t("quota_at", { v: when(i.at) }))}</div></div>
      ${rows || `<div class="muted small">${esc(i.error)}</div>`}</div>`;
  }
  function detail() {
    const el = $("#dash-quota");
    if (!el) return;
    const body = Q.items == null ? `<div class="muted small">${esc(t("quota_loading"))}</div>`
      : !Q.items.length ? `<div class="muted small">${esc(t("quota_none"))}</div>`
      : `<div class="qcards">${Q.items.map(card).join("")}</div>`;
    el.innerHTML = `<div class="panel"><div class="ghead">${esc(t("quota_title"))}<span class="mini">${refreshBtn()}</span></div>${body}</div>`;
  }

  function render() { side(); detail(); }
  function onState(m) { Q.items = m.items; Q.at = m.at; Q.busy = false; render(); }
  async function refresh() {
    if (Q.busy) return;
    Q.busy = true; render();
    try { onState(await fetch("/api/quota?refresh=1").then((r) => r.json())); } catch (e) { Q.busy = false; render(); }
  }
  setInterval(() => { if (Q.items) render(); }, 30000);
  return { onState, refresh, render };
})();
