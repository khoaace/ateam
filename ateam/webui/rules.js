/* 📏 Rule của dự án (/rules, nút 📏 trên thanh trên): điều mọi agent phải tuân theo — server lưu ngoài repo
   (ateam/rules.py) và gửi kèm ở đầu mỗi prompt. Bật/tắt, chỉ cho vài agent / vai trò, đổi thứ tự; mục cuối liệt kê
   file rule CLI tự đọc có sẵn trong repo (AGENTS.md, CLAUDE.md…) — bấm để mở ở tab Code. */
"use strict";

window.RulesView = (() => {
  let R = { rules: [], native: [], targets: [], file: "" }, m = null;

  const tlabel = (r) => {
    if (!r.targets || !r.targets.length) return t("rules_all");
    const lab = Object.fromEntries(R.targets.map((x) => [x.v, x.label.replace(/^[^:]+:\s*/, "")]));
    return r.targets.map((v) => lab[v] || v.split(":").pop()).join(", ");
  };
  const name = (r) => r.title || String(r.text || "").trim().split("\n")[0].slice(0, 60);

  async function op(action, data) {
    const r = await request(action ? "rules" : "rules_list", Object.assign({ action }, data || {}));
    if (r.rules) { R = r; render(); }
    return r;
  }

  function render() {
    if (!m || !document.body.contains(m)) return;
    const rows = R.rules.map((r) => `
      <div class="rule-row${r.enabled ? "" : " off"}" data-id="${r.id}">
        <label class="chk" title="${esc(t("rules_toggle"))}"><input type="checkbox" data-act="toggle" ${r.enabled ? "checked" : ""}></label>
        <button class="rule-main" data-act="edit"><span class="rule-name">${esc(name(r))}</span>
          <span class="muted small">→ ${esc(tlabel(r))}</span></button>
        <button class="icon-btn sm" data-act="up" title="${esc(t("rules_up"))}">↑</button>
        <button class="icon-btn sm" data-act="down" title="${esc(t("rules_down"))}">↓</button>
        <button class="icon-btn sm" data-act="del" title="${esc(t("rules_del"))}">✕</button>
      </div>`).join("") || `<div class="muted small rule-empty">${esc(t("rules_empty"))}</div>`;
    const native = R.native.length ? `<div class="sec-title" style="margin-top:16px">${esc(t("rules_native"))}</div>`
      + R.native.map((f) => `<div class="rule-row"><button class="rule-main" data-file="${esc(f.path)}">
          <span class="mono">📄 ${esc(f.path)}</span><span class="muted small">${esc(t("rules_reads", { v: f.readers }))}</span></button>
          <button class="btn sm ghost" data-file="${esc(f.path)}">${esc(t("rules_open"))}</button></div>`).join("") : "";
    $(".rules-body", m).innerHTML = `<div class="rule-list">${rows}</div>${native}`;
  }

  function form(r) {
    const chosen = new Set((r && r.targets) || []);
    const fm = openModal(`${modalHead(esc(t(r ? "rules_edit" : "rules_new")))}<div class="modal-pad rule-form">
      <div class="sec-title">${esc(t("rules_f_title"))}</div>
      <input class="field one" id="rf-title" maxlength="120" placeholder="${esc(t("rules_f_title_ph"))}" value="${esc((r && r.title) || "")}">
      <div class="sec-title">${esc(t("rules_f_text"))}</div>
      <textarea class="field" id="rf-text" rows="9" maxlength="8000">${esc((r && r.text) || "")}</textarea>
      <div class="sec-title">${esc(t("rules_f_targets"))}</div>
      <div class="chips-pick">${R.targets.map((x) => `<label class="chk pick-chip"><input type="checkbox" value="${esc(x.v)}" ${chosen.has(x.v) ? "checked" : ""}> ${esc(x.label)}</label>`).join("")}</div>
      <label class="chk" style="margin-top:10px"><input type="checkbox" id="rf-on" ${!r || r.enabled ? "checked" : ""}> ${esc(t("rules_f_on"))}</label>
      <div class="row-actions end"><button class="btn ghost" data-act="no">${esc(t("cancel_edit"))}</button>
        <button class="btn primary" data-act="save">${esc(t("rules_save"))}</button></div></div>`, { box: "md" });
    setTimeout(() => $(r ? "#rf-text" : "#rf-title", fm).focus(), 40);
    fm.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      if (b.dataset.act === "no") { closeModal(fm); return; }
      const data = { title: $("#rf-title", fm).value, text: $("#rf-text", fm).value, enabled: $("#rf-on", fm).checked,
        targets: $$(".chips-pick input:checked", fm).map((i) => i.value) };
      if (!data.text.trim()) { toast(t("rules_f_text"), "warn"); return; }
      const res = await op(r ? "update" : "add", r ? Object.assign(data, { id: r.id }) : data);
      if (res.level !== "warn") closeModal(fm);
    });
  }

  async function open() {
    if (m && document.body.contains(m)) closeModal(m);
    m = openModal(`${modalHead(esc(t("rules_title")))}<div class="modal-pad">
      <div class="muted small rules-hint"></div>
      <div class="rules-body"></div>
      <div class="row-actions end"><button class="btn primary" data-act="add">${esc(t("rules_add"))}</button></div></div>`, { box: "md" });
    m.addEventListener("click", async (e) => {
      const f = e.target.closest("[data-file]");
      if (f) { closeModal(m); setView("code"); CodeView.open(f.dataset.file); return; }
      const b = e.target.closest("[data-act]");
      if (!b) return;
      if (b.dataset.act === "add") return form(null);
      const row = b.closest("[data-id]"), id = row && +row.dataset.id, r = R.rules.find((x) => x.id === id);
      if (!r) return;
      if (b.dataset.act === "toggle") op("toggle", { id });
      else if (b.dataset.act === "edit") form(r);
      else if (b.dataset.act === "up" || b.dataset.act === "down") op("move", { id, by: b.dataset.act === "up" ? -1 : 1 });
      else if (b.dataset.act === "del" && await confirmBox(t("rules_del"), t("rules_del_q", { v: name(r) }), t("rules_del"))) op("delete", { id });
    });
    await op("", {});
    $(".rules-hint", m).textContent = t("rules_hint", { v: R.file });
  }

  return { open };
})();
