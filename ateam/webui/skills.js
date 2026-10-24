/* 🧩 Skills (trang Skills, /skills): skill theo chuẩn Agent Skills (thư mục có SKILL.md) gom từ mọi CLI, dự án và thư
   viện ateam (ateam/skills.py, web_skills.py). Bật/tắt theo dự án = trưởng nhóm có thấy skill khi lập kế hoạch không
   ($tên dùng được mọi skill). Xem, tạo / sửa / nhập / xoá skill trong thư viện, ✨ AI viết skill, cài từ GitHub.
   Chip 🧩 trên task gọi SkillsView.view(tên). */
"use strict";

window.SkillsView = (() => {
  let R = { skills: [], library: "", agents: [], lead: "" }, q = "";
  const NAME_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
  const KIND_ORDER = { project: 0, library: 1, cli: 2 };
  const box = () => $("#skills");

  async function load(op, data) {
    const r = await request(op || "skills_list", data || {});
    if (r.skills) { R = r; render(); }
    return r;
  }
  const act = (action, data) => load("skills", Object.assign({ action }, data));

  function rowHtml(s) {
    const lib = s.kind === "library";
    const warn = s.problems.length ? `<span class="chip warn" title="${esc(s.problems.join("\n"))}">⚠ ${s.problems.length}</span>` : "";
    const more = s.others.length ? `<span class="chip" title="${esc(s.others.join("\n"))}">${esc(t("sk_others", { n: s.others.length }))}</span>` : "";
    const script = s.scripts ? `<span class="chip" title="${esc(t("sk_scripts_hint"))}">⚙ ${esc(t("sk_scripts"))}</span>` : "";
    return `<div class="rule-row sk-row${s.on ? "" : " off"}" data-name="${esc(s.name)}">
      <label class="chk" title="${esc(t("sk_toggle"))}"><input type="checkbox" data-act="toggle" ${s.on ? "checked" : ""} ${s.usable && s.description ? "" : "disabled"}></label>
      <button class="rule-main" data-act="view"><span class="rule-name mono">${esc(s.name)}</span>
        <span class="muted small">${esc(s.description || t("sk_no_desc"))}</span></button>
      ${warn}${script}${more}
      <button class="icon-btn sm" data-act="copy" title="${esc(t("sk_copy"))}">$</button>
      ${lib ? `<button class="icon-btn sm" data-act="edit" title="${esc(t("sk_edit"))}">✎</button>
        <button class="icon-btn sm" data-act="del" title="${esc(t("sk_del"))}">✕</button>`
        : `<button class="icon-btn sm" data-act="import" title="${esc(t("sk_import"))}">⇩</button>`}
    </div>`;
  }

  const readersOf = (items) => (items.find((x) => x.readers) || {}).readers || "";  // file .md nằm phẳng: không ai đọc

  function render() {
    const b = box();
    if (!b || !b._built) return;
    const ql = q.trim().toLowerCase();
    const list = R.skills.filter((s) => !ql || (s.name + " " + s.description).toLowerCase().includes(ql));
    const groups = new Map();
    for (const s of list.slice().sort((a, c) => KIND_ORDER[a.kind] - KIND_ORDER[c.kind])) {
      if (!groups.has(s.source)) groups.set(s.source, []);
      groups.get(s.source).push(s);
    }
    const on = R.skills.filter((s) => s.on).length;
    $(".sk-count", b).textContent = t("sk_count", { on, n: R.skills.length });
    $(".sk-hint", b).textContent = t("sk_hint", { v: R.library });
    $(".sk-groups", b).innerHTML = [...groups.entries()].map(([src, items]) => `
      <div class="sk-group"><div class="sec-title">${esc(src)}${readersOf(items) ? ` <span class="muted small">· ${esc(t("rules_reads", { v: readersOf(items) }))}</span>` : ""}</div>
        <div class="rule-list">${items.map(rowHtml).join("")}</div></div>`).join("")
      || `<div class="empty"><div class="big">${esc(t("sk_empty"))}</div><div>${esc(t("sk_empty_hint"))}</div></div>`;
  }

  function show() {
    const b = box();
    if (!b._built) {
      b._built = true;
      b.innerHTML = `<div class="sk-top"><input class="field one sk-q" placeholder="${esc(t("sk_search"))}">
          <span class="muted small sk-count"></span><span class="sp"></span>
          <button class="btn sm" data-act="github">⬇ ${esc(t("sk_github"))}</button>
          <button class="btn sm" data-act="ai">✨ ${esc(t("sk_ai"))}</button>
          <button class="btn sm primary" data-act="new">+ ${esc(t("sk_new"))}</button></div>
        <div class="muted small sk-hint"></div><div class="sk-groups"></div>`;
      $(".sk-q", b).addEventListener("input", (e) => { q = e.target.value; render(); });
      b.addEventListener("click", onClick);
    }
    load();
  }

  async function onClick(e) {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    const a = b.dataset.act;
    if (a === "new") return form(null);
    if (a === "ai") return aiModal(null);
    if (a === "github") return githubModal();
    const row = b.closest("[data-name]"), name = row && row.dataset.name, s = R.skills.find((x) => x.name === name);
    if (!s) return;
    if (a === "toggle") act("toggle", { name, on: b.checked });
    else if (a === "view") view(name);
    else if (a === "copy") copyName(name);
    else if (a === "edit") edit(name);
    else if (a === "import") importSkill(s);
    else if (a === "del" && await confirmBox(t("sk_del"), t("sk_del_q", { v: name }), t("sk_del"))) act("delete", { name });
  }

  function copyName(name) {
    navigator.clipboard.writeText("$" + name).then(() => toast(t("sk_copied", { v: "$" + name }), "ok"));
  }

  async function importSkill(s) {
    const exists = R.skills.some((x) => x.kind === "library" && x.name === s.name) || s.others.some((o) => o.includes("/ateam/skills/"));
    if (exists && !await confirmBox(t("sk_import"), t("sk_overwrite_q", { v: s.name }), t("sk_import"))) return;
    act("import", { name: s.name, overwrite: exists });
  }

  async function view(name) {
    const r = await request("skill_view", { name });
    const s = r.skill_view;
    if (!s) return;
    const chips = [`<span class="chip">${esc(s.source)}</span>`]
      .concat(s.readers ? [`<span class="chip">${esc(t("rules_reads", { v: s.readers }))}</span>`] : [])
      .concat(s.scripts ? [`<span class="chip" title="${esc(t("sk_scripts_hint"))}">⚙ ${esc(t("sk_scripts"))}</span>`] : []).join("");
    const probs = s.problems.length ? `<div class="error-box">${s.problems.map(esc).join("<br>")}</div>` : "";
    const files = s.files.length > 1 ? `<div class="sec-title">${esc(t("sk_files"))}</div><div class="mono small sk-files">${s.files.map(esc).join("<br>")}</div>` : "";
    const lib = s.kind === "library";
    const m = openModal(`${modalHead("🧩 " + esc(s.name))}<div class="modal-pad">
      <div class="sk-chips">${chips}</div>${probs}
      <div class="muted small mono sk-path">${esc(s.path)}</div>
      ${s.description ? `<div class="sk-desc">${esc(s.description)}</div>` : ""}
      <div class="prompt-box md" style="max-height:55vh">${mdHtml(s.text.replace(/^\uFEFF?---\r?\n[\s\S]*?\r?\n---[ \t]*(\r?\n|$)/, ""))}</div>${files}
      <div class="row-actions end">
        <button class="btn ghost" data-act="copy">$ ${esc(t("sk_copy"))}</button>
        ${lib ? `<button class="btn" data-act="edit">✎ ${esc(t("sk_edit"))}</button>` : `<button class="btn" data-act="import">⇩ ${esc(t("sk_import"))}</button>`}
      </div></div>`, { box: "lg" });
    m.addEventListener("click", (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      if (b.dataset.act === "copy") copyName(s.name);
      else if (b.dataset.act === "edit") { closeModal(m); edit(s.name); }
      else if (b.dataset.act === "import") { closeModal(m); importSkill(s); }
    });
  }

  /* tạo (3 ô, server sinh SKILL.md đúng chuẩn) — cũng là form duyệt bản ✨ AI viết */
  function form(draft) {
    const d = draft || { name: "", description: "", body: "" };
    const fm = openModal(`${modalHead(esc(t(draft ? "sk_review" : "sk_new")))}<div class="modal-pad rule-form">
      <div class="sec-title">${esc(t("sk_f_name"))}</div>
      <input class="field one mono" id="sk-name" maxlength="64" placeholder="release-checklist" value="${esc(d.name)}">
      <div class="muted small sk-name-err"></div>
      <div class="sec-title">${esc(t("sk_f_desc"))}</div>
      <textarea class="field" id="sk-desc" rows="3" maxlength="1024" placeholder="${esc(t("sk_f_desc_ph"))}">${esc(d.description)}</textarea>
      <div class="sec-title">${esc(t("sk_f_body"))}</div>
      <textarea class="field mono" id="sk-body" rows="16">${esc(d.body)}</textarea>
      <div class="row-actions end"><button class="btn ghost" data-act="no">${esc(t("cancel_edit"))}</button>
        <button class="btn primary" data-act="save">${esc(t("rules_save"))}</button></div></div>`, { box: "lg" });
    const nameIn = $("#sk-name", fm), err = $(".sk-name-err", fm);
    const check = () => {
      const v = nameIn.value.trim(), exists = R.skills.some((x) => x.kind === "library" && x.name === v);
      err.textContent = v && !NAME_RE.test(v) ? t("sk_bad_name") : exists ? t("sk_exists", { v }) : "";
    };
    nameIn.addEventListener("input", check);
    check();
    setTimeout(() => nameIn.focus(), 40);
    fm.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      if (b.dataset.act === "no") { closeModal(fm); return; }
      const name = nameIn.value.trim();
      const exists = R.skills.some((x) => x.kind === "library" && x.name === name);
      if (exists && !await confirmBox(t("sk_new"), t("sk_overwrite_q", { v: name }), t("rules_save"))) return;
      const r = await load("skills", { action: "create", name, description: $("#sk-desc", fm).value, body: $("#sk-body", fm).value, overwrite: exists });
      if (r.level !== "warn") closeModal(fm);
    });
  }

  /* sửa skill trong thư viện: cả SKILL.md (giữ license / metadata…) */
  async function edit(name) {
    const r = await request("skill_view", { name });
    const s = r.skill_view;
    if (!s) return;
    const fm = openModal(`${modalHead("✎ " + esc(name))}<div class="modal-pad rule-form">
      <div class="muted small mono">${esc(s.path)}</div>
      <textarea class="field mono" id="sk-text" rows="24">${esc(s.text)}</textarea>
      <div class="row-actions end"><button class="btn ghost" data-act="no">${esc(t("cancel_edit"))}</button>
        <button class="btn primary" data-act="save">${esc(t("rules_save"))}</button></div></div>`, { box: "lg" });
    fm.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      if (b.dataset.act === "no") { closeModal(fm); return; }
      const res = await load("skills", { action: "update", name, text: $("#sk-text", fm).value });
      if (res.level !== "warn") closeModal(fm);
    });
  }

  const agentOpts = () => R.agents.map((n) => `<option value="${esc(n)}"${n === R.lead ? " selected" : ""}>${esc(n)}${n === R.lead ? " ★" : ""}</option>`).join("");

  /* ✨ AI viết skill: theo mô tả (gid null) hoặc rút từ mục tiêu đã xong (💾 Lưu thành skill) → form duyệt */
  async function aiModal(gid) {
    if (!R.agents.length) await load();
    const fm = openModal(`${modalHead("✨ " + esc(t(gid == null ? "sk_ai" : "sk_from_goal")))}<div class="modal-pad rule-form">
      <div class="muted small">${esc(gid == null ? t("sk_ai_hint") : t("sk_from_goal_hint", { id: gid }))}</div>
      <textarea class="field" id="sk-ai-text" rows="${gid == null ? 6 : 3}" placeholder="${esc(t(gid == null ? "sk_ai_ph" : "sk_focus_ph"))}"></textarea>
      <div class="sec-title">${esc(t("sk_ai_agent"))}</div><select class="agent-select" id="sk-ai-agent">${agentOpts()}</select>
      <div class="row-actions end"><button class="btn ghost" data-act="no">${esc(t("cancel_edit"))}</button>
        <button class="btn primary" data-act="go">✨ ${esc(t("sk_ai_go"))}</button></div></div>`, { box: "md" });
    setTimeout(() => $("#sk-ai-text", fm).focus(), 40);
    fm.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      if (b.dataset.act === "no") { closeModal(fm); return; }
      const text = $("#sk-ai-text", fm).value, agent = $("#sk-ai-agent", fm).value;
      if (gid == null && !text.trim()) { toast(t("sk_ai_ph"), "warn"); return; }
      const data = gid == null ? { description: text, agent } : { goal: gid, focus: text, agent };
      const r = await busyBtn(b, request("skill_ai", data, t("sk_ai_busy")));
      if (r.skill_draft) { closeModal(fm); form(r.skill_draft); }
    });
  }

  /* ⬇ cài từ GitHub: link → server clone vào thư mục tạm → chọn skill → chép vào thư viện */
  function githubModal() {
    let token = "", found = [];
    const fm = openModal(`${modalHead("⬇ " + esc(t("sk_github")))}<div class="modal-pad rule-form">
      <div class="muted small">${esc(t("sk_gh_hint"))}</div>
      <div class="sk-gh-row"><input class="field one mono" id="sk-gh-url" placeholder="anthropics/skills">
        <button class="btn" data-act="fetch">${esc(t("sk_gh_fetch"))}</button></div>
      <div class="sk-gh-list"></div>
      <div class="row-actions end"><button class="btn ghost" data-act="no">${esc(t("cancel_edit"))}</button>
        <button class="btn primary" data-act="install" disabled>${esc(t("sk_gh_install"))}</button></div></div>`,
    { box: "lg", onClose: () => { if (token) send("skill_discard", { token }); } });
    const list = $(".sk-gh-list", fm), inst = $('[data-act="install"]', fm);
    setTimeout(() => $("#sk-gh-url", fm).focus(), 40);
    $("#sk-gh-url", fm).addEventListener("keydown", (e) => { if (e.key === "Enter") $('[data-act="fetch"]', fm).click(); });
    fm.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      if (b.dataset.act === "no") { closeModal(fm); return; }
      if (b.dataset.act === "fetch") {
        if (token) { send("skill_discard", { token }); token = ""; }
        const r = await busyBtn(b, request("skill_fetch", { url: $("#sk-gh-url", fm).value }, t("sk_gh_busy")));
        if (!r.skill_fetch) return;
        token = r.skill_fetch.token; found = r.skill_fetch.skills;
        list.innerHTML = `<div class="rule-list">${found.map((s, i) => `<label class="rule-row sk-row">
            <input type="checkbox" data-i="${i}" ${s.usable && !s.exists ? "checked" : ""} ${s.usable ? "" : "disabled"}>
            <span class="rule-main"><span class="rule-name mono">${esc(s.name)}</span><span class="muted small">${esc(s.description || t("sk_no_desc"))}</span>
              <span class="muted small mono">${esc(s.path)} · ${esc(t("sk_n_files", { n: s.files }))}</span></span>
            ${s.scripts ? `<span class="chip warn" title="${esc(t("sk_scripts_hint"))}">⚙ ${esc(t("sk_scripts"))}</span>` : ""}
            ${s.exists ? `<span class="chip warn">${esc(t("sk_in_lib"))}</span>` : ""}
            ${s.problems.length ? `<span class="chip warn" title="${esc(s.problems.join("\n"))}">⚠ ${s.problems.length}</span>` : ""}
          </label>`).join("")}</div>
          ${found.some((s) => s.exists) ? `<label class="chk"><input type="checkbox" id="sk-gh-over"> ${esc(t("sk_gh_overwrite"))}</label>` : ""}
          <div class="muted small">${esc(t("sk_gh_trust"))}</div>`;
        inst.disabled = false;
      }
      if (b.dataset.act === "install") {
        const names = $$("input[data-i]:checked", list).map((x) => found[+x.dataset.i].name);
        if (!names.length) { toast(t("sk_gh_pick"), "warn"); return; }
        const over = $("#sk-gh-over", fm);
        const r = await busyBtn(b, load("skill_install", { token, names, overwrite: !!(over && over.checked) }));
        token = "";
        if (r.skill_installed) closeModal(fm);
      }
    });
  }

  /* chip 🧩 trên task / kế hoạch */
  function chips(names) {
    return (names || []).map((n) => `<span class="chip sk-chip" data-action="skill-view" data-name="${esc(n)}" title="${esc(t("sk_view"))}">🧩 ${esc(n)}</span>`).join("");
  }

  return { show, view, chips, fromGoal: (gid) => aiModal(gid) };
})();
