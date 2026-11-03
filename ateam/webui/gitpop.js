/* Nút nổi Git góc dưới phải (ngay trên nút ✅ To-do), mọi tab trừ 🌿 Git. Bấm (hoặc Alt+G) mở popover:
   nhánh + fetch/pull/push, danh sách file tick để stage, commit nhanh (✨ AI viết, amend, --no-verify, menu ▾:
   commit & push, stage tất cả rồi commit…), màn chuyển / tạo nhánh. Điện thoại: bottom sheet.
   Số trên nút lấy từ ảnh chụp trạng thái (git_changes, git_info); popover mở thì đọc /api/git/status mỗi 3 giây.
   Thao tác đi qua WS {op: "git", action} như tab Git (web_git.GitWeb.op). */
"use strict";

window.GitPop = (() => {
  const P = { open: false, view: "main", st: null, ns: null, sig: "", timer: null, busy: new Set(), sel: null,
    amend: false, noVerify: false, branches: [], bq: "", bsel: 0, dirty: "carry" };
  try { P.dirty = localStorage.getItem("ateam.gitpopDirty") === "stash" ? "stash" : "carry"; } catch (e) { /* chế độ riêng tư */ }
  const box = () => $("#git-fab");
  const info = () => (S.state && S.state.git_info) || { repo: false };
  const GIT = '<svg viewBox="0 0 24 24"><circle cx="6" cy="6" r="2.4"/><circle cx="6" cy="18" r="2.4"/><circle cx="18" cy="9" r="2.4"/><path d="M6 8.4v7.2M18 11.4c0 3-3 3.6-6 4.2-2 .4-4 1-5.6 2.4"/></svg>';
  const IC = {
    fetch: '<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M18 3v4h-4M6 21v-4h4"/></svg>',
    pull: '<svg viewBox="0 0 24 24"><path d="M12 4v12M6 11l6 6 6-6M5 20h14"/></svg>',
    push: '<svg viewBox="0 0 24 24"><path d="M12 20V8M6 13l6-6 6 6M5 4h14"/></svg>',
    open: '<svg viewBox="0 0 24 24"><path d="M14 5h5v5M19 5l-8 8M18 14v5H5V6h5"/></svg>',
    x: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    back: '<svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7"/></svg>',
    check: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  };
  const BUSY = { commit: "git_committing", fetch: "git_fetching", pull: "git_pulling", push: "git_pushing", checkout: "git_checking_out" };

  /* ---------------------------------------------------------------- dữ liệu */
  async function refresh(force) {
    try {
      const st = await fetch("/api/git/status?numstat=1").then((r) => r.json());
      const sig = JSON.stringify(st);
      if (!force && sig === P.sig) return;
      P.sig = sig; P.st = st; P.ns = st.numstat || { s: {}, w: {} };
      drawMain();
    } catch (e) { /* server đang khởi động lại */ }
  }
  async function act(action, data = {}) {
    P.busy.add(action); drawFab(); drawHead();
    const r = await request("git", Object.assign({ action }, data), t(BUSY[action] || "git_working"));
    P.busy.delete(action);
    S.branches = null;  // gợi ý /checkout đọc lại
    await refresh(true);
    drawFab();
    return r;
  }

  /* ---------------------------------------------------------------- khung */
  function mount() {
    if (box()) return;
    const d = document.createElement("div");
    d.className = "gfab";
    d.id = "git-fab";
    d.innerHTML = `<div class="gp-bd" data-gp="close"></div>
      <div class="gp" role="dialog" aria-label="Git">
        <div class="gp-view" id="gp-main">
          <div class="gp-head" id="gp-head"></div>
          <div class="gp-sync" id="gp-sync"></div>
          <div class="gp-files" id="gp-files"></div>
          <div class="gp-cbx">
            <div class="gp-msgw"><textarea class="gp-msg" id="gp-msg" rows="2" spellcheck="false" placeholder="${esc(t("gp_msg_ph"))}"></textarea>
              <button class="gp-ai" data-gp="ai" title="${esc(t("git_ai"))}">✨</button></div>
            <div class="gp-opts">
              <button class="gp-tg" data-gp="amend"><i></i>amend</button>
              <button class="gp-tg warn" data-gp="noverify" title="${esc(t("git_noverify"))}"><i></i>--no-verify</button>
              <select class="agent-select" id="gp-agent" title="${esc(t("git_ai_agent"))}"></select>
            </div>
            <div class="gp-row"><span class="gp-hint" id="gp-hint"></span>
              <span class="gp-split"><button class="btn sm primary" data-gp="commit" id="gp-commit">✓ Commit</button><button class="btn sm primary dd" data-gp="menu" aria-haspopup="menu" title="${esc(t("gp_more"))}">▾</button></span></div>
          </div>
          <div class="gp-menu" id="gp-menu" role="menu" hidden>
            <button class="gp-mi" data-gp="c_plain"><span class="ic">✓</span><span>Commit</span><span class="k">⌘Enter</span></button>
            <button class="gp-mi" data-gp="c_push"><span class="ic">⇡</span><span>Commit &amp; Push<span class="sub">${esc(t("gp_push_sub"))}</span></span><span class="k">⌘⇧Enter</span></button>
            <button class="gp-mi" data-gp="c_noverify"><span class="ic">⚡</span><span>Commit --no-verify<span class="sub">${esc(t("gp_noverify_sub"))}</span></span><span class="k">⌥Enter</span></button>
            <button class="gp-mi" data-gp="c_amend"><span class="ic">✎</span><span>${esc(t("git_amend"))}</span></button>
            <div class="gp-msep"></div>
            <button class="gp-mi" data-gp="c_all"><span class="ic">＋</span><span>${esc(t("gp_stage_all_commit"))}</span></button>
            <button class="gp-mi" data-gp="c_ai"><span class="ic">✨</span><span>${esc(t("gp_ai_commit"))}</span></button>
          </div>
          <div class="gp-foot">${foot([["Space", "stage"], ["d", "diff"], ["b", t("gp_k_branch")], ["⌘Enter", "commit"], ["Esc", t("close")]])}</div>
        </div>
        <div class="gp-view" id="gp-branch" hidden>
          <div class="gp-head"><button class="gp-ib b" data-gp="back" title="${esc(t("gp_back"))}">${IC.back}</button><b>${esc(t("gp_branch_title"))}</b>
            <button class="gp-ib" data-gp="close" title="${esc(t("close"))}">${IC.x}</button></div>
          <input class="field one gp-in" id="gp-q" placeholder="${esc(t("gp_branch_ph"))}" autocomplete="off" spellcheck="false">
          <div class="gp-new" id="gp-new" data-gp="create" hidden>
            <div class="t"><span class="plus">+</span>${esc(t("git_create_branch"))} <span class="nm" id="gp-new-name"></span><span class="k">⌘Enter</span></div>
            <div class="o">${esc(t("gp_from"))} <select id="gp-start"></select></div>
          </div>
          <div class="gp-blist" id="gp-blist"></div>
          <div class="gp-dirty" id="gp-dirty" hidden><span id="gp-dirty-t"></span>
            <span class="gp-seg"><button data-gp="d_carry">${esc(t("gp_carry"))}</button><button data-gp="d_stash">${esc(t("gp_stash_switch"))}</button></span></div>
          <div class="gp-foot">${foot([["↑↓", t("gp_k_pick")], ["Enter", "checkout"], ["⌘Enter", t("gp_k_create")], ["Esc", t("gp_back")]])}</div>
        </div>
      </div>
      <button class="gfab-btn" data-gp="fab" aria-label="Git" aria-expanded="false">${GIT}<span class="gfab-n" id="gfab-n"></span><span class="gfab-ab" id="gfab-ab"></span></button>`;
    document.body.appendChild(d);
    d.addEventListener("click", onClick);
    d.addEventListener("change", onChange);
    d.addEventListener("keydown", onKey);
    $("#gp-q", d).addEventListener("input", () => { P.bq = $("#gp-q").value.trim(); P.bsel = 0; drawBranches(); });
  }
  function foot(items) { return items.map(([k, v]) => `<b>${esc(k)}</b> ${esc(v)}`).join(" · "); }

  /* ---------------------------------------------------------------- vẽ */
  function render() {  // gọi mỗi lần có ảnh chụp trạng thái
    mount();
    const b = box(), g = info();
    const hide = !g.repo || S.view === "git";
    b.classList.toggle("hidden", hide);
    if (hide && P.open) setOpen(false);
    drawFab();
  }
  function drawFab() {
    const b = box(), g = info();
    if (!b) return;
    const n = S.state ? S.state.git_changes || 0 : 0, conflict = g.conflicts || g.state;
    const badge = $("#gfab-n", b);
    badge.textContent = conflict ? "!" : n || "";
    badge.classList.toggle("warn", !!conflict);
    $("#gfab-ab", b).textContent = [g.ahead ? "↑" + g.ahead : "", g.behind ? "↓" + g.behind : ""].filter(Boolean).join(" ");
    const fab = $(".gfab-btn", b);
    fab.classList.toggle("busy", P.busy.size > 0);
    fab.setAttribute("aria-expanded", P.open ? "true" : "false");
    const sync = [g.ahead ? "↑" + g.ahead : "", g.behind ? "↓" + g.behind : ""].filter(Boolean).join(" ");
    fab.title = [g.branch || t("gp_detached"), t("gp_n_changes", { n }), sync, g.state ? t("git_state", { v: g.state }) : ""]
      .filter(Boolean).join(" · ") + "  (Alt+G)";
    b.classList.toggle("pop", P.open);
    document.body.classList.toggle("gitpop-open", P.open);
  }
  function drawHead() {
    const st = P.st, h = $("#gp-head");
    if (!h || !st) return;
    const name = st.branch || (st.oid ? st.oid.slice(0, 8) + " · " + t("gp_detached") : t("git_no_commit"));
    const busy = (a) => P.busy.has(a) ? " busy" : "";
    h.innerHTML = `<span class="gi">${GIT}</span>
      <button class="gp-br" data-gp="branches" title="${esc(t("gp_branch_title"))} (b)"><span>${esc(name)}</span></button>
      <button class="gp-ib b${busy("fetch")}" data-gp="fetch" title="Fetch">${IC.fetch}</button>
      <button class="gp-ib b${busy("pull")}" data-gp="pull" title="Pull">${IC.pull}<span class="c dn">${st.behind || ""}</span></button>
      <button class="gp-ib b${st.ahead ? " hl" : ""}${busy("push")}" data-gp="push" title="Push">${IC.push}<span class="c">${st.ahead || ""}</span></button>
      <button class="gp-ib" data-gp="tab" title="${esc(t("gp_open_tab"))}">${IC.open}</button>
      <button class="gp-ib" data-gp="close" title="${esc(t("close"))} (Esc)">${IC.x}</button>`;
  }
  function drawMain() {
    const st = P.st;
    if (!st || !box()) return;
    if (!st.is_repo) { setOpen(false); return; }
    drawHead();
    const sync = $("#gp-sync");
    const parts = [];
    if (st.state) parts.push(`<span class="warn">⚠ ${esc(t("git_state", { v: st.state }))}</span>`);
    if (st.upstream) {
      parts.push(`<span class="up">↑${st.ahead}${st.ahead ? " " + esc(t("gp_unpushed")) : ""}</span><span class="dn">↓${st.behind}</span>`,
        `<span class="up-name">→ ${esc(st.upstream)}</span>`);
    } else if (st.branch) parts.push(`<span>${esc(t("git_no_remote"))}</span>`);
    if (st.stashes) parts.push(`<span class="sp"></span><span class="ago">📦 ${st.stashes} stash</span>`);
    sync.innerHTML = parts.join("");
    sync.hidden = !parts.length;
    const g = st.groups, ns = P.ns || { s: {}, w: {} };
    const keyOk = P.sel && (g[P.sel.code] || []).some((f) => f.path === P.sel.path);
    if (!keyOk) P.sel = null;
    const row = (code, f) => {
      const name = f.path.split("/").pop(), dir = f.path.includes("/") ? f.path.slice(0, f.path.lastIndexOf("/")) : "";
      const n = (code === "s" ? ns.s : ns.w)[f.path];
      const sel = P.sel && P.sel.code === code && P.sel.path === f.path;
      const cb = code === "c" ? `<span class="gp-st C">!</span>` : `<button class="gp-cb${code === "s" ? " on" : ""}" data-gp="toggle" title="${esc(t(code === "s" ? "gp_unstage" : "gp_stage"))} (Space)">${IC.check}</button>`;
      return `<div class="gp-f${sel ? " sel" : ""}" data-code="${code}" data-path="${esc(f.path)}" title="${esc(f.path)}">${cb}
        <span class="gp-st ${esc(f.icon)}">${esc(f.icon)}</span><span class="gp-fn">${esc(name)}</span><span class="gp-fd">${esc(dir)}${f.orig ? " ← " + esc(f.orig) : ""}</span>
        ${n ? `<span class="gp-ns"><span class="a">+${n[0]}</span> <span class="d">−${n[1]}</span></span>` : ""}
        <span class="gp-ra">${code === "c" ? `<button data-gp="resolve" title="${esc(t("cf_resolve"))}">⇄</button>` : `<button data-gp="diff" title="${esc(t("gp_diff"))} (d)">Δ</button>`}
          ${code === "w" ? `<button data-gp="discard" title="${esc(t("git_discard_title"))}">↶</button>` : ""}
          <button data-gp="edit" title="${esc(t("gp_edit"))}">↗</button></span></div>`;
    };
    const group = (code, title, list, actBtn) => list.length ? `<div class="gp-gh${code === "c" ? " cf" : ""}">${esc(title)} <span class="n">${list.length}</span>${actBtn}</div>${list.map((f) => row(code, f)).join("")}` : "";
    const html = group("c", t("git_conflicts"), g.c, "")
      + group("s", t("git_staged"), g.s, `<button class="act" data-gp="unstage_all">− ${esc(t("git_unstage_all"))}</button>`)
      + group("w", t("git_changes"), g.w, `<button class="act" data-gp="stage_all">+ ${esc(t("git_stage_all"))}</button>`);
    $("#gp-files").innerHTML = html || `<div class="gp-clean">✓ ${esc(t("git_clean"))}</div>`;
    drawCommit();
  }
  function drawCommit() {
    const st = P.st, b = box();
    if (!st || !b) return;
    const nS = st.groups.s.length, nAll = st.groups.s.length + st.groups.w.length;
    $("[data-gp=amend]", b).classList.toggle("on", P.amend);
    $("[data-gp=noverify]", b).classList.toggle("on", P.noVerify);
    const btn = $("#gp-commit", b);
    btn.textContent = "✓ " + (P.amend ? "Amend" : nS ? t("gp_commit_n", { n: nS }) : nAll ? t("gp_commit_all", { n: nAll }) : "Commit");
    $$(".gp-split .btn", b).forEach((x) => x.classList.toggle("warn", P.noVerify));
    const hint = $("#gp-hint", b);
    hint.classList.toggle("warn", P.noVerify);
    hint.textContent = P.noVerify ? "⚠ " + t("gp_noverify_on") : nAll ? t("gp_counts", { s: nS, w: st.groups.w.length }) : "";
    const sel = $("#gp-agent", b);
    if (window.GitView && GitView.aiAgents && document.activeElement !== sel) {
      const opts = GitView.aiAgents();
      if (sel.dataset.sig !== opts) { sel.innerHTML = opts; sel.dataset.sig = opts; }
    }
    $("#gp-msg", b).placeholder = P.amend ? t("git_msg_amend") : nS ? t("git_msg_staged", { n: nS }) : t("git_msg_all");
  }

  /* ---------------------------------------------------------------- mở / đóng */
  function setOpen(on) {
    if (on === P.open) return;
    P.open = on;
    clearInterval(P.timer); P.timer = null;
    if (on) {
      if (window.TodoPop && TodoPop.isOpen()) TodoPop.close();
      if (window.Lofi && Lofi.popOpen()) Lofi.hidePop();
      showView("main");
      P.sig = "";
      // điện thoại: không tự focus ô message (bàn phím ảo che mất danh sách file)
      refresh(true).then(() => { if (P.open && !matchMedia("(max-width: 480px)").matches) $("#gp-msg").focus(); });
      P.timer = setInterval(() => { if (!document.hidden && !topModal() && P.view === "main") refresh(); }, 3000);
    } else {
      menu(false);
      const f = document.activeElement;
      if (f && box() && box().contains(f)) f.blur();
    }
    drawFab();
  }
  function showView(v) {
    P.view = v;
    $("#gp-main").hidden = v !== "main";
    $("#gp-branch").hidden = v !== "branch";
    menu(false);
    if (v === "branch") openBranches();
  }
  function menu(on) { const m = $("#gp-menu"); if (m) m.hidden = !on; }

  /* ---------------------------------------------------------------- file */
  function rowOf(el) { const r = el && el.closest(".gp-f"); return r ? { code: r.dataset.code, path: r.dataset.path } : null; }
  function select(sel) {
    P.sel = sel;
    $$(".gp-f", box()).forEach((r) => r.classList.toggle("sel", !!sel && r.dataset.code === sel.code && r.dataset.path === sel.path));
  }
  async function toggle(sel) {
    if (!sel || sel.code === "c") return;
    await act(sel.code === "s" ? "unstage" : "stage", { paths: [sel.path] });
  }
  function diff(sel) {
    if (!sel) return;
    if (sel.code === "c") { if (window.GitView) GitView.resolve(sel.path); return; }
    DiffView.git({ kind: sel.code === "s" ? "staged" : "unstaged", path: sel.path });
  }
  async function discard(sel) {
    if (!sel || sel.code !== "w") return;
    const f = P.st.groups.w.find((x) => x.path === sel.path);
    const q = f && f.icon === "U" ? t("git_discard_new", { path: sel.path }) : t("git_discard_q", { path: sel.path });
    if (await confirmBox(t("git_discard_title"), q, t("git_discard_yes"))) await act("discard", { path: sel.path });
  }

  /* ---------------------------------------------------------------- commit */
  async function aiMessage() {
    if (P.busy.has("ai_message")) return "";
    const b = $("[data-gp=ai]");
    P.busy.add("ai_message"); b.classList.add("busy"); drawFab();
    const lead = (window.GitView && GitView.commitAgent && GitView.commitAgent()) || (S.state && S.state.lead) || "lead";
    const r = await request("git", { action: "ai_message" }, t("git_ai_wait", { lead }));
    P.busy.delete("ai_message"); b.classList.remove("busy"); drawFab();
    if (r.git_msg) { const m = $("#gp-msg"); m.value = r.git_msg; m.focus(); }
    return r.git_msg || "";
  }
  /* mode: "" (theo công tắc), push (commit rồi push), noverify, amend, all (stage tất cả trước), ai (AI viết rồi commit) */
  async function commit(mode = "") {
    if (P.busy.has("commit") || !P.st) return;
    menu(false);
    const m = $("#gp-msg");
    if (mode === "amend" && !P.amend) await setAmend(true);
    if (mode === "ai" && !(await aiMessage())) return;
    const msg = m.value.trim(), amend = P.amend;
    if (!msg && !amend) { toast(t("git_need_msg"), "warn"); m.focus(); return; }
    if (mode === "all" && P.st.groups.w.length) await act("stage_all");
    const r = await act("commit", { message: msg, amend, no_verify: P.noVerify || mode === "noverify" });
    if (!r.committed) return;
    m.value = ""; P.amend = false; P.noVerify = false;  // --no-verify không được nhớ sang lần sau
    drawCommit();
    if (mode === "push") await act("push");
  }
  async function setAmend(on) {
    P.amend = on;
    const m = $("#gp-msg");
    if (on && !m.value.trim()) { const r = await request("git", { action: "last_message" }); if (r.git_msg) m.value = r.git_msg; }
    drawCommit();
  }

  /* ---------------------------------------------------------------- nhánh */
  async function openBranches() {
    P.bq = ""; P.bsel = 0;
    const q = $("#gp-q"); q.value = ""; q.focus();
    try { P.branches = await (await fetch("/api/git/branches")).json(); } catch (e) { P.branches = []; }
    const cur = P.st && P.st.branch;
    $("#gp-start").innerHTML = (cur ? [cur] : ["HEAD"]).concat(P.branches.filter((b) => b.name !== cur).map((b) => b.name))
      .map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
    drawBranches();
  }
  function validName(n) {  // như gitops.valid_branch_name (đủ để báo sớm; server kiểm lại)
    return !!n && !/[\s~^:?*[\\]|\.\.|@\{|^[-/.]|[/.]$|\.lock$|\/\//.test(n);
  }
  function branchRows() {
    const q = P.bq.toLowerCase(), m = (b) => !q || b.name.toLowerCase().includes(q);
    return { local: P.branches.filter((b) => !b.remote && m(b)), remote: P.branches.filter((b) => b.remote && m(b)) };
  }
  function drawBranches() {
    const { local, remote } = branchRows(), q = P.bq;
    const exists = P.branches.some((b) => !b.remote && b.name === q);
    const canNew = !!q && !exists;
    const nb = $("#gp-new");
    nb.hidden = !canNew;
    $("#gp-new-name").textContent = q;
    nb.classList.toggle("sel", canNew && P.bsel === -1);
    const hl = (name) => {
      if (!q) return esc(name);
      const i = name.toLowerCase().indexOf(q.toLowerCase());
      return i < 0 ? esc(name) : esc(name.slice(0, i)) + "<mark>" + esc(name.slice(i, i + q.length)) + "</mark>" + esc(name.slice(i + q.length));
    };
    const track = (b) => {
      const a = /ahead (\d+)/.exec(b.track || ""), d = /behind (\d+)/.exec(b.track || "");
      return (a ? `<span style="color:var(--running)">↑${a[1]}</span> ` : "") + (d ? `<span style="color:var(--review)">↓${d[1]}</span>` : "")
        + (/gone/.test(b.track || "") ? esc(t("gp_gone")) : "");
    };
    let i = 0;
    const row = (b) => {
      const idx = b.current ? null : i++;
      return `<div class="gp-b${b.current ? " cur" : ""}${b.remote ? " rem" : ""}${idx === P.bsel ? " sel" : ""}" data-gp="checkout" data-name="${esc(b.name)}"${idx == null ? "" : ` data-i="${idx}"`} title="${esc(b.subject || "")}">
        <span class="mk">${b.current ? IC.check : ""}</span><span class="bn">${hl(b.name)}</span>${b.current ? `<span class="curt">${esc(t("gp_current"))}</span>` : ""}
        <span class="ab">${track(b)}</span><span class="tm">${esc(b.date || "")}</span></div>`;
    };
    const grp = (title, list) => list.length ? `<div class="gp-gh">${esc(title)} <span class="n">${list.length}</span></div>${list.map(row).join("")}` : "";
    const html = grp(t("git_local"), local) + grp(t("git_remote"), remote);
    $("#gp-blist").innerHTML = html || `<div class="gp-none">${esc(t(canNew ? "gp_no_match_new" : "git_no_match"))}</div>`;
    if (canNew && !validName(q)) $("#gp-new-name").innerHTML = `${esc(q)} <span class="bad">· ${esc(t("gp_bad_name"))}</span>`;
    // thay đổi chưa commit: chọn mang theo / stash rồi chuyển
    const st = P.st, n = st ? st.groups.s.length + st.groups.w.length + st.groups.c.length : 0;
    $("#gp-dirty").hidden = !n;
    if (n) {
      $("#gp-dirty-t").innerHTML = t("gp_dirty", { n: `<b>${n}</b>`, b: esc(st.branch || "HEAD") });
      $$("#gp-dirty [data-gp]").forEach((x) => x.classList.toggle("on", x.dataset.gp === "d_" + P.dirty));
    }
    const s = $("#gp-blist .gp-b.sel");
    if (s) s.scrollIntoView({ block: "nearest" });
  }
  function moveSel(d) {
    const n = $$("#gp-blist .gp-b[data-i]").length, canNew = !$("#gp-new").hidden;
    let i = P.bsel + d;
    const lo = canNew ? -1 : 0;
    if (i < lo) i = lo;
    if (i > n - 1) i = n - 1;
    P.bsel = i; drawBranches();
  }
  async function checkout(name) {
    if (!name) return;
    const stash = P.dirty === "stash";
    let r = await act("checkout", { name, stash });
    if (r.need_stash && !stash && await confirmBox(t("gp_branch_title"), t("gp_need_stash", { name }), t("gp_stash_switch"), false)) {
      r = await act("checkout", { name, stash: true });
    }
    if (r.level !== "warn") showView("main");
  }
  async function create() {
    const name = P.bq;
    if (!name || !validName(name)) { toast(t("gp_bad_name"), "warn"); return; }
    const start = $("#gp-start").value;
    const r = await act("create_branch", { name, start: start === (P.st && P.st.branch) ? "" : start });
    if (r.level !== "warn") showView("main");
  }

  /* ---------------------------------------------------------------- sự kiện */
  async function onClick(e) {
    const b = e.target.closest("[data-gp]"), row = e.target.closest(".gp-f");
    const a = b ? b.dataset.gp : "";
    if (a !== "menu" && !e.target.closest("#gp-menu")) menu(false);
    if (!b && row) { const s = rowOf(row); select(s); diff(s); return; }  // bấm vào file: xem diff
    if (!b) return;
    if (row) select(rowOf(row));
    switch (a) {
      case "fab": return setOpen(!P.open);
      case "close": return setOpen(false);
      case "tab": setOpen(false); return setView("git");
      case "branches": return showView("branch");
      case "back": return showView("main");
      case "fetch": case "pull": case "push": case "stage_all": case "unstage_all":
        if (!P.busy.has(a)) await act(a);
        return;
      case "toggle": return toggle(rowOf(b));
      case "diff": case "resolve": return diff(rowOf(b));
      case "discard": return discard(rowOf(b));
      case "edit": { const s = rowOf(b); setOpen(false); setView("code"); return CodeView.open(s.path); }
      case "ai": return aiMessage();
      case "amend": return setAmend(!P.amend);
      case "noverify": P.noVerify = !P.noVerify; return drawCommit();
      case "commit": return commit();
      case "menu": { const m = $("#gp-menu"); m.hidden = !m.hidden; if (!m.hidden) $(".gp-mi", m).focus(); return; }
      case "c_plain": return commit("");
      case "c_push": return commit("push");
      case "c_noverify": return commit("noverify");
      case "c_amend": return commit("amend");
      case "c_all": return commit("all");
      case "c_ai": return commit("ai");
      case "checkout": if (!b.classList.contains("cur")) return checkout(b.dataset.name); return;
      case "create": if (!e.target.closest("select")) return create(); return;
      case "d_carry": case "d_stash":
        P.dirty = a.slice(2);
        try { localStorage.setItem("ateam.gitpopDirty", P.dirty); } catch (err) { /* chế độ riêng tư */ }
        return drawBranches();
    }
  }
  async function onChange(e) {
    if (e.target.id === "gp-agent") {
      if (S.state) S.state.commit_agent = e.target.value;
      await request("git", { action: "commit_agent", name: e.target.value });
    }
  }
  function onKey(e) {
    if (!P.open) return;
    const k = e.key, mod = e.metaKey || e.ctrlKey;
    if (k === "Escape") {
      e.preventDefault(); e.stopPropagation();
      if (!$("#gp-menu").hidden) { menu(false); $("#gp-commit").focus(); return; }
      if (P.view === "branch") { showView("main"); return; }
      setOpen(false); return;
    }
    if (P.view === "branch") {
      if (e.target.tagName === "SELECT") return;
      if (k === "ArrowDown" || k === "ArrowUp") { e.preventDefault(); moveSel(k === "ArrowDown" ? 1 : -1); return; }
      if (k === "Enter" && !e.isComposing) {
        e.preventDefault();
        if (mod || P.bsel === -1) return create();
        const r = $(`#gp-blist .gp-b[data-i="${P.bsel}"]`);
        if (r) return checkout(r.dataset.name);
        if (!$("#gp-new").hidden) return create();
      }
      return;
    }
    if (k === "Enter" && !e.isComposing && (mod || e.altKey)) {
      e.preventDefault();
      return commit(e.altKey ? "noverify" : e.shiftKey ? "push" : "");
    }
    if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || mod || e.altKey) return;
    const rows = $$(".gp-f", box());
    if (k === "ArrowDown" || k === "ArrowUp" || k === "j" || k === "k") {
      const i = rows.findIndex((r) => r.classList.contains("sel"));
      const n = rows[Math.max(0, Math.min(rows.length - 1, i + (k === "ArrowDown" || k === "j" ? 1 : -1)))];
      if (n) { select(rowOf(n)); n.scrollIntoView({ block: "nearest" }); }
    } else if (k === " " && P.sel) toggle(P.sel);
    else if (k === "d" || (k === "Enter" && P.sel)) diff(P.sel);
    else if (k === "x") discard(P.sel);
    else if (k === "b") showView("branch");
    else if (k === "c") $("#gp-msg").focus();
    else return;
    e.preventDefault();
  }
  /* bấm ra ngoài → đóng; bỏ qua popup chung (diff, xác nhận…) mở từ popover */
  window.addEventListener("pointerdown", (e) => {
    if (!P.open || !box() || box().contains(e.target) || e.target.closest(".modal, .toasts")) return;
    setOpen(false);
  });

  return { render, isOpen: () => P.open, close: () => setOpen(false), toggle: () => { render(); if (!box().classList.contains("hidden")) setOpen(!P.open); } };
})();
