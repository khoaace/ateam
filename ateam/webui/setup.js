/* /setup — wizard thiết lập đội 7 bước (như OnboardScreen của TUI) và /custom — agent & workflow tuỳ chỉnh
   (như CustomScreen / AgentQuickScreen / AgentEditScreen / WorkflowEditScreen). Logic kiểm tra/lưu ở server
   (ateam/wizard.py, dùng chung với TUI); trang chỉ thu thập lựa chọn. */
"use strict";

window.Setup = (() => {
  let W = null;  // trạng thái wizard
  let R = null;  // bảng vai trò trên trang Agents

  /* ================================================================ wizard /setup */
  async function open(first) {
    const data = await (await fetch("/api/setup")).json();
    const i = data.init;
    W = { data, first, step: 0, providers: i.providers.slice(), style: i.style, tier: i.tier, assign: i.assign,
      access: i.access, apply: i.apply, verify: i.verify, flowName: i.flow_name || "", assignKey: JSON.stringify([i.providers, i.first ? null : i.tier]),
      discovering: true, saved: false };
    W.modal = openModal(`${modalHead(`<span id="ob-title"></span>`)}<div class="ob-steps" id="ob-steps"></div>
      <div class="modal-pad ob-body" id="ob-body"></div>
      <div class="ob-foot"><button class="btn ghost" data-ob="custom">${esc(t("ob_custom"))}</button><span style="flex:1"></span>
        <button class="btn ghost" data-ob="back">← ${esc(t("ob_back"))}</button><button class="btn primary" data-ob="next"></button></div>`,
    { box: "lg", sticky: true, onClose: () => { if (W && W.first && !W.saved) send("setup_skip"); W = null; } });
    W.modal.addEventListener("click", onClick);
    W.modal.addEventListener("change", onChange);
    send("setup_discover");  // hỏi model mới từ các CLI (chạy nền, xong thì "discovered")
    step(0);
  }
  async function discovered() {
    if (!W) return;
    const data = await (await fetch("/api/setup")).json();
    W.data.models = data.models;
    W.discovering = false;
    if (W.data.steps[W.step].key === "roles") step(W.step);
  }

  const optCard = (name, k, label, hint, on, disabled) => `<label class="opt-card${on ? " on" : ""}${disabled ? " disabled" : ""}">
    <input type="radio" name="${name}" value="${esc(k)}" ${on ? "checked" : ""} ${disabled ? "disabled" : ""}>
    <span class="radio"></span><span><b>${esc(label)}</b><small>${esc(hint)}</small></span></label>`;

  async function step(i) {
    W.step = i;
    const d = W.data, s = d.steps[i];
    $("#ob-title", W.modal).textContent = t("ob_title", { v: i + 1, n: d.steps.length, title: s.title });
    $("#ob-steps", W.modal).innerHTML = d.steps.map((x, n) => `<span class="ob-step${n === i ? " on" : n < i ? " done" : ""}">${n < i ? "✓" : n + 1}. ${esc(x.short)}</span>`).join("");
    const body = $("#ob-body", W.modal);
    if (s.key === "cli") {
      body.innerHTML = `<div class="ob-q">${esc(t("ob_q_cli"))}</div>` + d.providers.map((p) => `
        <label class="opt-card${W.providers.includes(p.key) ? " on" : ""}${p.installed ? "" : " disabled"}">
        <input type="checkbox" name="cli" value="${p.key}" ${W.providers.includes(p.key) && p.installed ? "checked" : ""} ${p.installed ? "" : "disabled"}>
        <span class="check"></span><span><b>${esc(p.label)}</b><small>${p.installed ? "✓ " + esc(t("ob_installed", { p: p.key })) : "✗ " + esc(t("ob_not_installed", { v: p.hint }))}</small></span></label>`).join("");
    } else if (s.key === "style") {
      body.innerHTML = `<div class="ob-q">${esc(t("ob_q_style"))}</div>` + d.styles.map((x) => optCard("style", x.key, x.label, x.hint, W.style === x.key)).join("")
        + `<div class="row-actions"><button class="btn sm" data-ob="flow">⚙ ${esc(t("ob_flow"))}</button><span class="muted small">${esc(t("ob_flow_hint", { name: W.flowName || "tinh-nang" }))}</span></div>`;
    } else if (s.key === "tier") {
      body.innerHTML = `<div class="ob-q">${esc(t("ob_q_tier"))}</div>` + d.tiers.map((x) => optCard("tier", x.key, x.label, x.hint, W.tier === x.key)).join("")
        + `<div class="muted small">${esc(t("ob_tier_hint"))}</div>`;
    } else if (s.key === "roles") {
      const key = JSON.stringify([W.providers, W.tier]);
      if (W.assignKey !== key) {  // đổi CLI hoặc mức: gán lại theo mặc định mới
        W.assign = await (await fetch(`/api/setup/assign?providers=${W.providers.join(",")}&tier=${W.tier}`)).json();
        W.assignKey = key;
      }
      body.innerHTML = `<div class="ob-q">${esc(t("ob_q_roles"))}</div><div class="muted small">${esc(t("ob_roles_hint"))}${W.discovering ? " ⏳ " + esc(t("ob_discovering")) : ""}</div>
        <div class="roles">${d.roles.map((r) => roleRow(r, W)).join("")}</div>`;
    } else if (s.key === "safety") {
      body.innerHTML = `<div class="ob-q">${esc(t("ob_q_access"))}</div>` + d.access.map((x) => optCard("access", x.key, x.label, x.hint, W.access === x.key)).join("")
        + `<div class="ob-q">${esc(t("ob_q_apply"))}</div>` + d.apply.map((x) => optCard("apply", x.key, x.label,
          x.hint + (d.init.git || x.key === "shared" ? "" : t("ob_need_git")), W.apply === x.key, !d.init.git && x.key !== "shared")).join("");
    } else if (s.key === "verify") {
      const keys = d.verify.map((x) => x.key);
      body.innerHTML = `<div class="ob-q">${esc(t("ob_q_verify"))}</div>` + d.verify.map((x) => optCard("verify", x.key, x.label, x.hint, W.verify === x.key)).join("")
        + `<input class="field one" id="ob-verify-input" placeholder="${esc(t("ob_verify_ph"))}" value="${esc(keys.includes(W.verify) ? "" : W.verify)}">`;
    } else if (s.key === "review") {
      const plan = await (await fetch("/api/setup/plan?assign=" + encodeURIComponent(JSON.stringify(W.assign)))).json();
      const lbl = (list, k) => (list.find((x) => x.key === k) || {}).label || k;
      body.innerHTML = `<div class="ob-q">${esc(t("ob_team"))}</div><table class="ob-table">${plan.agents.map((a) => `<tr>
          <td>${a.name === plan.lead ? "★ " : ""}<b>${esc(a.name)}</b>${a.builtin ? "" : ` <span class="chip">${esc(t("ob_added"))}</span>`}</td>
          <td>${esc(a.provider_label)}</td><td class="mono">${esc((a.model || t("default_value")) + (a.effort ? " · " + a.effort : ""))}</td>
          <td class="muted">${esc(a.roles.map((r) => r.replace(/^★ /, "")).join(", "))}</td></tr>`).join("")}</table>
        ${d.custom_others.length ? `<div class="muted small">${esc(t("ob_custom_kept", { v: d.custom_others.join(", ") }))}</div>` : ""}
        <div class="ob-q">${esc(t("ob_how"))}</div><table class="ob-table kv">
          <tr><td>${esc(t("ob_style"))}</td><td>${esc(lbl(d.styles, W.style))}</td></tr>
          <tr><td>${esc(t("ob_tier"))}</td><td>${esc(lbl(d.tiers, W.tier))}</td></tr>
          <tr><td>${esc(t("ob_access"))}</td><td>${esc(lbl(d.access, W.access))}</td></tr>
          <tr><td>${esc(t("ob_apply"))}</td><td>${esc(lbl(d.apply, W.apply))}</td></tr>
          <tr><td>${esc(t("ob_verify"))}</td><td class="mono">${esc(W.verify || t("ob_none"))}</td></tr></table>
        ${plan.lead ? "" : `<div class="err-text">⚠ ${esc(t("ob_no_lead"))}</div>`}`;
    }
    $("[data-ob=back]", W.modal).disabled = i === 0;
    $("[data-ob=next]", W.modal).innerHTML = s.key === "review" ? `✓ ${esc(t("ob_save"))}` : `${esc(t("ob_next"))} →`;
    $("[data-ob=custom]", W.modal).classList.toggle("hidden", s.key !== "review");
  }
  function roleRow(r, st) {  // st: W (wizard, popup /roles) hoặc R (bảng trên trang Agents)
    const a = st.assign[r.key], d = st.data;
    const p = a ? a[0] : "";
    const clis = d.providers.filter((x) => st.providers.includes(x.key)).map((x) => `<option value="${x.key}"${x.key === p ? " selected" : ""}>${esc(x.label)}</option>`).join("")
      + (r.key !== "lead" ? `<option value=""${p ? "" : " selected"}>${esc(t("ob_unused"))}</option>` : "");
    let models = a ? (d.models[p] || []).slice() : [];
    if (a && a[1] && !models.includes(a[1])) models = [a[1]].concat(models);
    const effs = a ? d.efforts[p] || [] : [];
    const opt = (v, cur) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(v)}</option>`;
    const selects = `<select class="agent-select" data-rf="cli">${clis}</select>
      <select class="agent-select" data-rf="model" ${a ? "" : "disabled"}>${models.map((m) => opt(m, a && a[1])).join("")}<option value=""${a && a[1] ? "" : " selected"}>${esc(t("default_value"))}</option></select>
      <select class="agent-select" data-rf="effort" ${a && effs.length ? "" : "disabled"}>${effs.map((e) => opt(e, a && a[2])).join("")}<option value=""${a && a[2] && effs.includes(a[2]) ? "" : " selected"}>${esc(t("default_value"))}</option></select>`;
    if (st === R) {  // ô trạng thái + nút của agent giữ vai trò do app.js điền (fillRoles), đổi CLI xong mới đổi agent
      return `<div class="ag-row role-row" data-role="${r.key}" data-agent="${esc(r.agent)}">
        <span class="av lg" style="--h:${hue(r.agent || r.key)}">${esc((r.agent || "–")[0])}</span><div class="ag-main"><div class="agent-name">${esc(r.label)}</div><div class="ag-role mono">${esc(r.agent || "—")}</div></div>
        ${selects}<div class="ag-act" data-desc="${esc(r.desc)}"></div><div class="role-live"></div></div>`;
    }
    return `<div class="role-row" data-role="${r.key}"><b class="rlabel">${esc(r.label)}</b>${selects}
      <span class="muted small rdesc" title="${esc(r.desc)}">${esc(r.desc)}</span></div>`;
  }
  function collect() {
    const key = W.data.steps[W.step].key, m = W.modal;
    const radio = (n) => { const x = $(`input[name=${n}]:checked`, m); return x ? x.value : null; };
    if (key === "cli") {
      const chosen = $$("input[name=cli]:checked", m).map((x) => x.value);
      if (!chosen.length) return t("ob_pick_cli");
      W.providers = W.data.providers.map((p) => p.key).filter((p) => chosen.includes(p));
    }
    if (key === "style") W.style = radio("style") || W.style;
    if (key === "tier") W.tier = radio("tier") || W.tier;
    if (key === "safety") { W.access = radio("access") || W.access; W.apply = radio("apply") || W.apply; }
    if (key === "verify") { const typed = $("#ob-verify-input", m).value.trim(); W.verify = typed || (radio("verify") ?? W.verify); }
    if (key === "roles") readRoles(m, W);
    return null;
  }
  async function save(btn) {
    if (btn && btn.disabled) return;
    collect();
    const r = await busyBtn(btn, request("setup_save", { providers: W.providers, style: W.style, tier: W.tier, assign: W.assign, access: W.access, apply: W.apply, verify: W.verify, flow_name: W.flowName }, t("busy_saving")));
    if (r.setup_saved) { W.saved = true; closeModal(W.modal); }
  }
  async function onClick(e) {
    const b = e.target.closest("[data-ob]");
    const card = e.target.closest(".opt-card");
    if (card && !card.classList.contains("disabled")) {
      setTimeout(() => { $$(`.opt-card`, card.parentElement).forEach((c) => { const inp = $("input", c); c.classList.toggle("on", inp.checked); }); }, 0);
    }
    if (!b) return;
    const a = b.dataset.ob;
    if (a === "back") { collect(); step(Math.max(0, W.step - 1)); }
    if (a === "next") {
      if (W.data.steps[W.step].key === "review") return save(b);
      const err = collect();
      if (err) { toast(err, "warn"); return; }
      step(W.step + 1);
    }
    if (a === "custom") custom(() => { if (W) { open(W.first); } });
    if (a === "flow") {  // đã cấu hình luồng → chọn luôn kiểu "theo quy trình cố định"
      collect();
      flowModal({ inSetup: true, name: W.flowName, onSaved: (name) => { if (!W) return; W.flowName = name; W.style = "flow"; step(W.step); } });
    }
  }
  async function onChange(e) { await changeCli(e, W); }
  async function changeCli(e, st) {
    const sel = e.target.closest("[data-rf=cli]");
    if (!sel) return false;
    const row = sel.closest(".role-row"), role = row.dataset.role, p = sel.value;
    st.assign[role] = p ? await (await fetch(`/api/setup/assign?role=${role}&provider=${p}&tier=${st.tier}`)).json() : null;
    row.outerHTML = roleRow(st.data.roles.find((r) => r.key === role), st);
    return true;
  }
  const readRoles = (box, st) => $$(".role-row", box).forEach((row) => {
    const v = (f) => $(`[data-rf=${f}]`, row).value;
    st.assign[row.dataset.role] = v("cli") ? [v("cli"), v("model"), v("effort")] : null;
  });

  /* ---------------------------------------------------------------- ⚡ sửa nhanh vai trò (/roles) — chỉ bước Vai trò của
     wizard, chọn được mọi CLI đã cài; lưu ngay (server giữ nguyên kiểu làm việc, quyền, worktree, lệnh kiểm tra) */
  async function rolesModal() {
    const data = await (await fetch("/api/setup")).json();
    const i = data.init;
    W = { data, quick: true, step: data.steps.findIndex((s) => s.key === "roles"), providers: data.quick_providers,
      tier: i.tier, assign: i.assign, discovering: false };
    const m = openModal(`${modalHead("⚡ " + esc(t("roles_title")))}<div class="modal-pad ob-body">
      <div class="muted small">${esc(t("roles_hint"))}</div>
      <div class="roles">${data.roles.map((r) => roleRow(r, W)).join("")}</div></div>
      <div class="ob-foot"><button class="btn ghost" data-rq="setup">${esc(t("roles_full"))}</button><span style="flex:1"></span>
        <button class="btn ghost" data-rq="cancel">${esc(t("cancel_edit"))}</button>
        <button class="btn primary" data-rq="save">✓ ${esc(t("save"))}</button></div>`,
    { box: "lg", onClose: () => { if (W && W.quick) W = null; } });
    W.modal = m;
    m.addEventListener("change", onChange);
    m.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-rq]");
      if (!b) return;
      if (b.dataset.rq === "cancel") return closeModal(m);
      if (b.dataset.rq === "setup") { closeModal(m); return open(false); }
      if (b.disabled) return;
      collect();
      const r = await busyBtn(b, request("roles_save", { assign: W.assign }, t("busy_saving")));
      if (r.setup_saved) closeModal(m);
    });
  }

  /* ---------------------------------------------------------------- ⚡ bảng vai trò ngay trên trang Agents: như popup /roles,
     đổi gì là hiện nút Lưu; chưa lưu thì không vẽ lại (giữ lựa chọn đang sửa) */
  async function rolesPanel(head, box, onDraw, force) {
    if (R && R.dirty && !force) return;
    const data = await (await fetch("/api/setup")).json();
    R = { data, providers: data.quick_providers, tier: data.init.tier, assign: data.init.assign, dirty: false };
    head.innerHTML = `<span class="sec-title">⚡ ${esc(t("roles_title"))}</span><span class="muted small">${esc(t("roles_hint"))}</span><span style="flex:1"></span>
      <button class="btn sm ghost" data-rp="setup">${esc(t("roles_full"))}</button>
      <button class="btn sm ghost hidden" data-rp="cancel">${esc(t("cancel_edit"))}</button>
      <button class="btn sm primary hidden" data-rp="save">✓ ${esc(t("save"))}</button>`;
    box.innerHTML = data.roles.map((r) => roleRow(r, R)).join("");
    const dirty = () => { R.dirty = true; $$("[data-rp=cancel], [data-rp=save]", head).forEach((b) => b.classList.remove("hidden")); };
    box.onchange = async (e) => {
      dirty();
      if (await changeCli(e, R)) onDraw();
    };
    head.onclick = async (e) => {
      const b = e.target.closest("[data-rp]");
      if (!b) return;
      if (b.dataset.rp === "setup") return open(false);
      if (b.dataset.rp === "cancel") return rolesPanel(head, box, onDraw, true);
      if (b.disabled) return;
      readRoles(box, R);
      const r = await busyBtn(b, request("roles_save", { assign: R.assign }, t("busy_saving")));
      if (r.setup_saved) rolesPanel(head, box, onDraw, true);
    };
    onDraw();
  }

  /* ================================================================ /custom — trang Workflows + popup (agent tuỳ chỉnh ở trang Agents) */
  function customHtml(d, flowsOnly) {
    const agentRows = d.agents.map((a) => `<div class="c-row"><b>${esc(a.name)}</b>
        <span class="muted mono small c-info">${a.installed ? "✓" : "✗ " + esc(t("not_installed"))} · ${esc(a.argv)}</span>
        <button class="btn sm" data-cu="edit-agent" data-name="${esc(a.name)}">${esc(t("edit"))}</button>
        <button class="btn sm danger" data-cu="del-agent" data-name="${esc(a.name)}">${esc(t("remove"))}</button></div>`).join("")
      || `<div class="muted small pad">${esc(t("cu_no_agents"))}</div>`;
    const flowRows = d.workflows.map((w) => `<div class="c-row"><b>${esc(w.name)}</b>
        <span class="muted small c-info">${w.name === d.default_workflow ? `<span class="chip">★ ${esc(t("cu_default"))}</span> ` : ""}${esc(t("cu_steps", { n: w.steps, v: w.summary }))}${w.description ? " · " + esc(w.description) : ""}</span>
        <button class="btn sm" data-cu="${w.name === d.default_workflow ? "unset-default" : "set-default"}" data-name="${esc(w.name)}" title="${esc(t("mode_pick_title"))}">${esc(t(w.name === d.default_workflow ? "cu_unset_default" : "cu_make_default"))}</button>
        <button class="btn sm" data-cu="edit-flow" data-name="${esc(w.name)}">${esc(t("edit"))}</button>
        <button class="btn sm danger" data-cu="del-flow" data-name="${esc(w.name)}">${esc(t("remove"))}</button></div>`).join("")
      || `<div class="muted small pad">${esc(t("cu_no_flows"))}</div>`;
    const agents = flowsOnly ? "" : `<div class="sec-title" style="margin-top:14px">${esc(t("cu_agents"))}</div>${agentRows}
      <button class="btn sm" data-cu="add-agent">+ ${esc(t("cu_add_agent"))}</button>`;
    return `<div class="muted small">${esc(t(flowsOnly ? "wf_hint" : "cu_hint"))}</div>${agents}
      <div class="sec-title" style="margin-top:18px">Workflow</div>${flowRows}
      <div class="row-actions"><button class="btn sm" data-cu="add-flow">+ ${esc(t("cu_add_flow"))}</button>
        <button class="btn sm" data-cu="default-flow">⚙ ${esc(t("df_title"))}</button>
        <button class="btn sm" data-cu="roles">⚡ ${esc(t("roles_title"))}</button></div>`;
  }
  function customClick(d, reopen) {
    return async (e) => {
      const b = e.target.closest("[data-cu]");
      if (!b) return;
      const name = b.dataset.name;
      if (b.dataset.cu === "add-agent") agentForm(d, null, reopen);
      if (b.dataset.cu === "add-flow") flowForm(d, null, reopen);
      if (b.dataset.cu === "default-flow") flowModal({ onSaved: reopen });
      if (b.dataset.cu === "set-default" || b.dataset.cu === "unset-default") {  // gõ mục tiêu chạy workflow này
        const r = await request("input_mode", { name: b.dataset.cu === "set-default" ? name : "" });
        if (r.mode_saved) reopen();
      }
      if (b.dataset.cu === "roles") rolesModal();
      if (b.dataset.cu === "edit-agent") agentForm(d, d.agents.find((a) => a.name === name), reopen);
      if (b.dataset.cu === "edit-flow") flowForm(d, d.workflows.find((w) => w.name === name), reopen);
      if (b.dataset.cu === "del-agent" || b.dataset.cu === "del-flow") {
        const kind = b.dataset.cu === "del-agent" ? "agents" : "workflows";
        if (await confirmBox(t("remove"), t("cu_del_q", { name }), t("remove"))) {
          const r = await request("custom_delete", { kind, name });
          if (r.custom_saved) reopen();
        }
      }
    };
  }
  async function custom(onDone) {  // popup (mở từ /setup)
    const d = await (await fetch("/api/custom")).json();
    const m = openModal(`${modalHead(esc(t("cu_title")))}<div class="modal-pad">${customHtml(d)}</div>`,
      { box: "lg", onClose: () => { if (onDone) setTimeout(onDone, 0); } });
    const reopen = () => { onDone = null; closeModal(m); custom(); if (S.view === "custom") showCustom(); };
    m.addEventListener("click", customClick(d, reopen));
  }
  async function showCustom() {  // trang Workflows ở sidebar
    const el = $("#custom");
    if (!el) return;
    const d = await (await fetch("/api/custom")).json();
    el.innerHTML = `<div class="panel custom-page">${customHtml(d, true)}</div>`;
    el.onclick = customClick(d, showCustom);  // gán (không addEventListener) để vẽ lại không gắn trùng
  }
  /* agent tuỳ chỉnh từ trang Agents: thêm / sửa / xoá (cùng form với popup /custom) */
  const customData = async () => (await fetch("/api/custom")).json();
  async function addAgent(done) { agentForm(await customData(), null, done); }
  async function editAgent(name, done) {
    const d = await customData(), a = d.agents.find((x) => x.name === name);
    if (a) agentForm(d, a, done);
  }
  async function deleteAgent(name, done) {
    if (!(await confirmBox(t("remove"), t("cu_del_q", { name }), t("remove")))) return;
    const r = await request("custom_delete", { kind: "agents", name });
    if (r.custom_saved) done();
  }

  /* ---------------------------------------------------------------- popup "Luồng mặc định" (DefaultFlowScreen) */
  async function flowModal(opts = {}) {
    let d = await (await fetch("/api/default_flow?name=" + encodeURIComponent(opts.name || ""))).json();
    if (d.error) { toast(d.error, "warn"); return; }
    const opt = (v, label, cur) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(label)}</option>`;
    const choiceOpts = (agent, model, effort) => {
      const c = d.choices[agent] || { models: [], efforts: [] };
      const models = model && !c.models.includes(model) ? [model].concat(c.models) : c.models;
      return [opt("", t("df_agent_default"), model) + models.map((x) => opt(x, x, model)).join(""),
        opt("", t("default_value"), effort) + c.efforts.map((x) => opt(x, x, effort)).join("")];
    };
    const row = (st, i) => {
      const agent = d.agents.some((a) => a.value === st.agent) ? st.agent : "lead";
      const [mo, eo] = choiceOpts(agent, st.model, st.effort);
      return `<div class="df-row" data-i="${i}"><b class="df-step">${i + 1}. ${esc(st.title)}</b>
        <select class="agent-select" data-df="agent">${d.agents.map((a) => opt(a.value, a.label, agent)).join("")}</select>
        <select class="agent-select" data-df="model">${mo}</select>
        <select class="agent-select" data-df="effort">${eo}</select></div>`;
    };
    const body = () => `<label>Workflow<select class="field one" id="df-name">${d.names.map((n) => opt(n.name, n.label, d.form.name)).join("")}</select></label>
      <div class="df-head"><span>${esc(t("df_step"))}</span><span>Agent</span><span>Model</span><span>Effort</span></div>
      <div id="df-steps">${d.form.steps.map(row).join("")}</div>
      <label class="chk"><input type="checkbox" id="df-review" ${d.form.review ? "checked" : ""}> ${esc(t("df_review"))}</label>
      ${opts.inSetup ? "" : `<label class="chk"><input type="checkbox" id="df-default" checked> ${esc(t("df_default"))}</label>`}`;
    const m = openModal(`${modalHead("⚙ " + esc(t("df_title")))}<div class="modal-pad form">
      <div class="muted small">${esc(t("df_hint"))}</div><div id="df-body">${body()}</div>
      <div class="row-actions end"><button class="btn ghost" data-dfa="cancel">${esc(t("cancel_edit"))}</button><button class="btn primary" data-dfa="save">${esc(t("save"))}</button></div></div>`, { box: "lg" });
    m.addEventListener("change", async (e) => {
      if (e.target.id === "df-name") {
        d = await (await fetch("/api/default_flow?name=" + encodeURIComponent(e.target.value))).json();
        if (d.error) { toast(d.error, "warn"); return; }
        $("#df-body", m).innerHTML = body();
      } else if (e.target.dataset.df === "agent") {  // đổi agent: nạp lại model/effort của bước
        const r = e.target.closest(".df-row"), [mo, eo] = choiceOpts(e.target.value, "", "");
        $("[data-df=model]", r).innerHTML = mo;
        $("[data-df=effort]", r).innerHTML = eo;
      }
    });
    m.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-dfa]");
      if (!b) return;
      if (b.dataset.dfa === "cancel") { closeModal(m); return; }
      const steps = $$(".df-row", m).map((r) => ({ agent: $("[data-df=agent]", r).value, model: $("[data-df=model]", r).value, effort: $("[data-df=effort]", r).value }));
      const def = $("#df-default", m);
      if (b.disabled) return;
      const r = await busyBtn(b, request("default_flow_save", { name: d.form.name, steps, review: $("#df-review", m).checked, make_default: def ? def.checked : null }, t("busy_saving")));
      if (r.flow_saved) { closeModal(m); if (opts.onSaved) opts.onSaved(r.flow_saved); }
    });
  }

  /* ---------------------------------------------------------------- agent: form nhanh + nâng cao */
  async function agentForm(d, a, done, advanced) {
    const quick = !advanced && (!a || a.quick);
    if (!quick) return advancedForm(d, a, done);
    const raw = (a && a.raw) || {};
    let provider = (a && a.provider) || (d.providers.find((p) => p.installed) || d.providers[0]).key;
    const m = openModal(`${modalHead(esc(a ? t("cu_edit_agent", { name: a.name }) : t("cu_add_agent")))}<div class="modal-pad form">
      <div class="muted small">${esc(t("cu_quick_hint"))}</div>
      <label>${esc(t("cu_provider"))}<select class="field one" id="q-provider">${d.providers.map((p) => `<option value="${p.key}"${p.key === provider ? " selected" : ""}>${esc(p.label)}${p.installed ? "" : " (" + esc(t("not_installed")) + ")"}</option>`).join("")}</select></label>
      <label>${esc(t("cu_name"))}<input class="field one" id="q-name" value="${esc(a ? a.name : "")}" placeholder="vd: codex-nhanh"></label>
      <label>Model<select class="field one" id="q-model"></select></label>
      <label>Effort<select class="field one" id="q-effort"></select></label>
      <label>${esc(t("cu_access"))}<select class="field one" id="q-access"><option value="safe">${esc(t("cu_safe"))}</option><option value="full"${raw.full_access ? " selected" : ""}>${esc(t("cu_full"))}</option></select></label>
      <label>${esc(t("cu_role"))}<input class="field one" id="q-role" value="${esc(raw.role || "")}" placeholder="${esc(t("cu_role_ph"))}"></label>
      <div class="preview" id="q-preview"></div>
      <div class="row-actions end"><button class="btn ghost" data-q="advanced">${esc(t("cu_advanced"))}</button><span style="flex:1"></span>
        <button class="btn ghost" data-q="cancel">${esc(t("cancel_edit"))}</button><button class="btn primary" data-q="save">${esc(t("save"))}</button></div></div>`, { box: "md" });
    let autoName = "", autoRole = "";
    const fill = async (keepModel, keepEffort) => {
      const q = await (await fetch("/api/custom/quick?provider=" + provider)).json();
      let models = q.models;
      if (keepModel && !models.includes(keepModel)) models = [keepModel].concat(models);
      $("#q-model", m).innerHTML = models.map((x) => `<option${x === keepModel ? " selected" : ""}>${esc(x)}</option>`).join("") + `<option value=""${keepModel ? "" : " selected"}>${esc(t("default_value"))}</option>`;
      $("#q-effort", m).innerHTML = q.efforts.map((x) => `<option${x === keepEffort ? " selected" : ""}>${esc(x)}</option>`).join("") + `<option value=""${keepEffort && q.efforts.includes(keepEffort) ? "" : " selected"}>${esc(t("default_value"))}</option>`;
      $("#q-effort", m).disabled = !q.efforts.length;
      const role = $("#q-role", m), name = $("#q-name", m);
      if (!role.value.trim() || role.value === autoRole) { autoRole = role.value = q.role; }
      if (!a && (!name.value.trim() || name.value === autoName)) { autoName = name.value = q.name; }
      preview();
    };
    const body = () => ({ mode: "quick", provider, name: $("#q-name", m).value, model: $("#q-model", m).value, effort: $("#q-effort", m).value,
      role: $("#q-role", m).value, full: $("#q-access", m).value === "full", old: a ? a.name : null, kind: "agents" });
    let pt = null;
    const preview = () => { clearTimeout(pt); pt = setTimeout(async () => showPreview($("#q-preview", m), (await request("custom_preview", body())).preview), 150); };
    m.addEventListener("input", preview);
    m.addEventListener("change", (e) => { if (e.target.id === "q-provider") { provider = e.target.value; fill(); } else preview(); });
    m.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-q]");
      if (!b) return;
      if (b.dataset.q === "cancel") closeModal(m);
      if (b.dataset.q === "save" && !b.disabled) { const r = await busyBtn(b, request("custom_save", body(), t("busy_saving"))); if (r.custom_saved) { closeModal(m); done(); } }
      if (b.dataset.q === "advanced") {
        const r = await request("custom_preview", body());
        closeModal(m);
        advancedForm(d, a, done, { name: $("#q-name", m).value, raw: r.preview && r.preview.body });
      }
    });
    fill(raw.model || "", raw.effort || "");
  }
  function showPreview(box, p) {
    if (!p) return;
    if (p.error) { box.innerHTML = `<span class="warn-text">⚠ ${esc(p.error)}</span>`; return; }
    box.innerHTML = p.argv ? `<b>${esc(t("cu_will_run"))}</b> <code>${esc(p.argv)}</code><br>
      ${p.file ? `<b>@file →</b> ${esc(p.file)} · ` : ""}<span class="${p.installed ? "ok-text" : "warn-text"}">${p.installed ? "✓" : "✗"} ${esc(t(p.installed ? "cu_installed" : "cu_missing", { v: p.binary }))}</span>
      ${p.full ? `<br><span class="warn-text">⚠ ${esc(t("cu_full_warn"))}</span>` : ""}${p.no_prompt ? `<br><span class="warn-text">⚠ ${esc(t("cu_no_prompt"))}</span>` : ""}`
      : `<span class="muted">${esc(t("cu_type_cmd"))}</span>`;
  }
  async function advancedForm(d, a, done, from) {
    const fields = (a && a.fields) || {};
    const raw = (from && from.raw) || (a && a.raw) || {};
    const fromFields = from && from.raw ? await fieldsOf(from.raw) : null;
    const val = (id) => (fromFields || fields)[id] || "";
    const m = openModal(`${modalHead(esc(a ? t("cu_edit_agent", { name: a.name }) : t("cu_add_custom_agent")))}<div class="modal-pad form">
      <div class="muted small">${esc(t("cu_adv_hint"))}</div>
      <label>${esc(t("cu_template"))}<select class="field one" id="ag-template"><option value="">${esc(t("cu_pick_template"))}</option>${d.agent_templates.map((k) => `<option>${esc(k)}</option>`).join("")}</select></label>
      <label>${esc(t("cu_name"))}<input class="field one" id="ag-name" value="${esc((from && from.name) || (a ? a.name : ""))}"></label>
      ${d.fields.map((f) => `<label title="${esc(f.hint)}">${esc(f.label)}<input class="field one mono" data-fid="${f.id}" value="${esc(val(f.id))}" placeholder="${esc(f.hint)}"></label>`).join("")}
      <div class="row-actions"><label class="chk"><input type="checkbox" id="ag-pty" ${raw.pty ? "checked" : ""}> ${esc(t("cu_pty"))}</label>
        <label class="chk"><input type="checkbox" id="ag-verify" ${raw.verify === false ? "" : "checked"}> ${esc(t("cu_verify"))}</label>
        <label class="chk"><input type="checkbox" id="ag-full" ${raw.full_access ? "checked" : ""}> ${esc(t("cu_full"))}</label></div>
      <div class="preview" id="ag-preview"></div>
      <div class="row-actions end"><button class="btn ghost" data-q="cancel">${esc(t("cancel_edit"))}</button><button class="btn primary" data-q="save">${esc(t("save"))}</button></div></div>`, { box: "md" });
    const body = () => ({ mode: "advanced", kind: "agents", name: $("#ag-name", m).value, old: a ? a.name : null,
      fields: Object.fromEntries($$("[data-fid]", m).map((x) => [x.dataset.fid, x.value])),
      pty: $("#ag-pty", m).checked, verify: $("#ag-verify", m).checked, full: $("#ag-full", m).checked });
    let pt = null;
    const preview = () => { clearTimeout(pt); pt = setTimeout(async () => showPreview($("#ag-preview", m), (await request("custom_preview", body())).preview), 150); };
    m.addEventListener("input", preview);
    m.addEventListener("change", async (e) => {
      if (e.target.id === "ag-template" && e.target.value) {
        const tp = await (await fetch("/api/custom/template?key=" + encodeURIComponent(e.target.value))).json();
        $$("[data-fid]", m).forEach((x) => { x.value = tp.fields[x.dataset.fid] || ""; });
        $("#ag-pty", m).checked = !!tp.raw.pty; $("#ag-verify", m).checked = tp.raw.verify !== false; $("#ag-full", m).checked = !!tp.raw.full_access;
        if (!$("#ag-name", m).value.trim()) $("#ag-name", m).value = tp.name;
      }
      preview();
    });
    m.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-q]");
      if (!b) return;
      if (b.dataset.q === "cancel") closeModal(m);
      if (b.dataset.q === "save" && !b.disabled) { const r = await busyBtn(b, request("custom_save", body(), t("busy_saving"))); if (r.custom_saved) { closeModal(m); done(); } }
    });
    preview();
  }
  async function fieldsOf(raw) {
    const r = await request("custom_preview", { mode: "fields", raw });
    return (r.preview && r.preview.fields) || {};
  }

  /* ---------------------------------------------------------------- workflow */
  function flowForm(d, w, done) {
    const raw = (w && w.raw) || {};
    // mỗi bước: agent → model → effort (gợi ý theo CLI của agent, như popup Luồng mặc định), rồi tiêu đề + prompt
    const opt = (v, label, cur) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(label)}</option>`;
    const agentOpts = (cur) => d.step_agents.map((a) => opt(a.value, a.label, cur)).join("")
      + (d.step_agents.some((a) => a.value === cur) ? "" : opt(cur, t("cu_not_in_team", { v: cur }), cur));
    const modelOpts = (agent, model) => {
      const c = d.step_choices[agent] || { models: [] };
      return opt("", t("df_agent_default"), model) + (model && !c.models.includes(model) ? [model] : []).concat(c.models).map((x) => opt(x, x, model)).join("");
    };
    const effortOpts = (agent, effort) => {
      const effs = (d.step_choices[agent] || { efforts: [] }).efforts;
      return opt("", t("default_value"), effort) + (effort && !effs.includes(effort) ? [effort] : []).concat(effs).map((x) => opt(x, x, effort)).join("");
    };
    const hasEfforts = (agent, effort) => !!(effort || (d.step_choices[agent] || { efforts: [] }).efforts.length);
    const stepRow = (st) => {
      const agent = st.agent || "lead";
      return `<div class="wf-step"><span class="wf-no"></span>
      <select class="agent-select" data-sf="agent">${agentOpts(agent)}</select>
      <select class="agent-select" data-sf="model">${modelOpts(agent, st.model || "")}</select>
      <select class="agent-select" data-sf="effort"${hasEfforts(agent, st.effort) ? "" : " disabled"}>${effortOpts(agent, st.effort || "")}</select>
      <input class="field one" data-sf="after" value="${esc(st.after || "")}" placeholder="${esc(t("cu_step_after"))}">
      <button class="mini danger" data-wf="del">✕</button>
      <input class="field one wf-title" data-sf="title" value="${esc(st.title || "")}" placeholder="${esc(t("cu_step_title"))}">
      <input class="field one wf-prompt" data-sf="prompt" value="${esc(st.prompt || "")}" placeholder="${esc(t("cu_step_prompt"))}"></div>`;
    };
    const steps = (w && w.step_rows) || [{ agent: "lead" }];
    const m = openModal(`${modalHead(esc(w && w.in_file ? t("cu_edit_flow", { name: w.name }) : t("cu_add_flow")))}<div class="modal-pad form">
      <div class="muted small">${esc(t("cu_flow_hint"))}</div>
      ${w && !w.in_file ? `<div class="warn-text small">${esc(t("cu_flow_copy", { name: w.name }))}</div>` : ""}
      <label>${esc(t("cu_ai"))}<span class="wf-ai"><input class="field one" id="wf-ai-desc" placeholder="${esc(t("cu_ai_ph"))}"><button class="btn sm" data-wf="ai">${esc(t("cu_ai_btn"))}</button></span><span class="muted small">${esc(t("cu_ai_hint"))}</span></label>
      <label>${esc(t("cu_template"))}<select class="field one" id="wf-template"><option value="">${esc(t("cu_pick_template"))}</option>${d.workflow_templates.map((x) => `<option value="${esc(x.key)}">${esc(x.key)} — ${esc(x.description)}</option>`).join("")}</select></label>
      <label>${esc(t("cu_name"))}<input class="field one" id="wf-name" value="${esc(w && w.in_file ? w.name : "")}"></label>
      <label>${esc(t("cu_desc"))}<input class="field one" id="wf-desc" value="${esc(raw.description || "")}"></label>
      <label class="chk"><input type="checkbox" id="wf-review" ${(raw.review ?? d.auto_review) ? "checked" : ""}> ${esc(t("cu_review"))}</label>
      <div class="wf-head"><span></span><span>Agent</span><span>Model</span><span>Effort</span><span>${esc(t("cu_step_after"))}</span><span></span></div>
      <div id="wf-steps">${steps.map(stepRow).join("")}</div>
      <button class="btn sm" data-wf="add">+ ${esc(t("cu_add_step"))}</button>
      <div class="row-actions end"><button class="btn ghost" data-wf="cancel">${esc(t("cancel_edit"))}</button><button class="btn primary" data-wf="save">${esc(t("save"))}</button></div></div>`, { box: "lg" });
    const renumber = () => $$(".wf-no", m).forEach((x, i) => { x.textContent = i + 1 + "."; });
    renumber();
    m.addEventListener("change", async (e) => {
      if (e.target.dataset.sf === "agent") {  // đổi agent: nạp lại model/effort gợi ý của bước
        const r = e.target.closest(".wf-step"), eff = $("[data-sf=effort]", r);
        $("[data-sf=model]", r).innerHTML = modelOpts(e.target.value, "");
        eff.innerHTML = effortOpts(e.target.value, "");
        eff.disabled = !hasEfforts(e.target.value, "");
        return;
      }
      if (e.target.id !== "wf-template" || !e.target.value) return;
      const tp = await (await fetch("/api/custom/template?kind=workflow&key=" + encodeURIComponent(e.target.value))).json();
      $("#wf-desc", m).value = tp.description || "";
      if (tp.review != null) $("#wf-review", m).checked = !!tp.review;
      $("#wf-steps", m).innerHTML = tp.step_rows.map(stepRow).join("");
      if (!$("#wf-name", m).value.trim()) $("#wf-name", m).value = e.target.value;
      renumber();
    });
    const suggest = async () => {
      const b = $('[data-wf="ai"]', m);
      if (b.disabled) return;
      const r = await busyBtn(b, request("workflow_suggest", { description: $("#wf-ai-desc", m).value }, t("cu_ai_wait", { lead: d.lead })));
      const f = r.wf_suggest;
      if (!f) return;
      $("#wf-desc", m).value = f.description;
      $("#wf-review", m).checked = f.review;
      $("#wf-steps", m).innerHTML = f.steps.map(stepRow).join("");
      if (!$("#wf-name", m).value.trim()) $("#wf-name", m).value = f.name;
      renumber();
    };
    $("#wf-ai-desc", m).addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); suggest(); } });
    m.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-wf]");
      if (!b) return;
      const a = b.dataset.wf;
      if (a === "ai") { e.preventDefault(); suggest(); }
      if (a === "add") { $("#wf-steps", m).insertAdjacentHTML("beforeend", stepRow({ agent: "lead" })); renumber(); }
      if (a === "del") { if ($$(".wf-step", m).length > 1) { b.closest(".wf-step").remove(); renumber(); } else toast(t("cu_one_step"), "warn"); }
      if (a === "cancel") closeModal(m);
      if (a === "save" && !b.disabled) {
        const stepsOut = $$(".wf-step", m).map((row) => Object.fromEntries($$("[data-sf]", row).map((x) => [x.dataset.sf, x.value])));
        const r = await busyBtn(b, request("custom_save", { kind: "workflows", name: $("#wf-name", m).value, old: w && w.in_file ? w.name : null,
          description: $("#wf-desc", m).value, review: $("#wf-review", m).checked, steps: stepsOut }, t("busy_saving")));
        if (r.custom_saved) { closeModal(m); done(); }
      }
    });
  }

  return { open, discovered, custom, showCustom, flowModal, rolesModal, rolesPanel, addAgent, editAgent, deleteAgent };
})();
