/* Tab Git — như tab 🌿 Git của TUI (tui.py: refresh_git, git_button…): trạng thái, stage/unstage, bỏ thay đổi,
   commit (amend, --no-verify, trưởng nhóm viết message), lịch sử (xem, revert, bỏ commit cuối), nhánh, stash,
   fetch/pull/push. Gọi server: GET /api/git/*, WS {op: "git", action}. */
"use strict";

window.GitView = (() => {
  const G = { st: null, log: [], sel: null, timer: null, ops: new Set(), amend: false, noVerify: false,  // ops: thao tác đang chạy
    tree: false, closed: new Set() };  // tree: danh sách dạng cây thư mục (nhớ theo trình duyệt); closed: "nhóm\0thư/mục/" đang thu
  try { G.tree = localStorage.getItem("ateam.gitTree") === "1"; } catch (e) { /* chế độ riêng tư */ }
  const box = () => $("#git");

  async function refresh() {
    try {
      const [st, log] = await Promise.all([fetch("/api/git/status").then((r) => r.json()), fetch("/api/git/log?n=80").then((r) => r.json())]);
      const sig = JSON.stringify([st, log]);
      if (sig === G.sig) return;  // không đổi: không vẽ lại (đang gõ message / cuộn danh sách)
      G.sig = sig; G.st = st; G.log = log;
      render();
    } catch (e) { /* server đang khởi động lại */ }
  }
  // toast "đang chạy…" (chỉ hiện nếu quá 300ms) cho từng thao tác; còn lại dùng chữ chung
  const BUSY = { commit: "git_committing", fetch: "git_fetching", pull: "git_pulling", push: "git_pushing",
    ai_resolve: "git_ai_resolving", merge: "git_merging", checkout: "git_checking_out", continue: "git_continuing" };
  const BTN = { ai_message: "ai", commit: "commit_now" };  // thao tác → nút (data-gact) hiện spinner
  async function act(action, data = {}) {
    G.sig = "";
    G.ops.add(action); markBusy();
    const r = await request("git", Object.assign({ action }, data), t(BUSY[action] || "git_working"));
    G.ops.delete(action);
    S.branches = null;  // gợi ý /checkout đọc lại
    G.sig = "";
    await refresh();
    markBusy();
    return r;
  }
  function markBusy() {  // nút của thao tác đang chạy: khoá + spinner (gọi lại sau mỗi lần vẽ)
    $$("[data-gact].busy", box()).forEach((b) => { b.classList.remove("busy"); b.disabled = false; });
    for (const op of G.ops) {
      const b = $(`[data-gact="${BTN[op] || op}"]`, box());
      if (b) { b.classList.add("busy"); b.disabled = true; }
    }
  }

  function groups() {
    const g = (G.st && G.st.groups) || { c: [], s: [], w: [] };
    return [["c", t("git_conflicts"), g.c], ["s", t("git_staged"), g.s], ["w", t("git_changes"), g.w]].filter((x) => x[2].length);
  }
  function fileRow(code, f, depth) {  // depth: chế độ cây (thụt lề, không hiện thư mục cạnh tên)
    const sel = G.sel && G.sel.code === code && G.sel.path === f.path;
    const name = f.path.split("/").pop(), dir = depth == null && f.path.includes("/") ? f.path.slice(0, f.path.lastIndexOf("/")) : "";
    const icon = { M: "review", A: "done", U: "done", D: "failed", R: "draft", C: "draft", "!": "failed" }[f.icon] || "queued";
    return `<div class="gfile${sel ? " sel" : ""}" data-gact="sel" data-code="${code}" data-path="${esc(f.path)}" tabindex="-1"${depth ? ` style="padding-left:${8 + depth * 14}px"` : ""}>
      <span class="fstat s-${icon}">${esc(f.icon)}</span><span class="gname">${esc(name)}</span><span class="gdir">${esc(dir)}${f.orig ? " ← " + esc(f.orig) : ""}</span>
      <span class="grow-acts">
        <button class="mini" data-gact="diff" title="d">Δ</button>
        <button class="mini" data-gact="edit" title="e">✎</button>
        ${code === "c" ? `<button class="mini" data-gact="resolve" title="Enter">⇄</button>` : ""}
        ${code === "w" ? `<button class="mini danger" data-gact="discard" title="x">↺</button>` : ""}
        ${code !== "c" ? `<button class="mini" data-gact="toggle" title="space">${code === "s" ? "−" : "+"}</button>` : ""}
      </span></div>`;
  }

  function dirRow(code, depth, path, label, n) {  // hàng thư mục ở chế độ cây: bấm = thu/mở, +/− stage cả thư mục
    const sel = G.sel && G.sel.code === code && G.sel.path === path, shut = G.closed.has(code + "\0" + path);
    return `<div class="gfile gdirrow${sel ? " sel" : ""}" data-gact="sel" data-code="${code}" data-path="${esc(path)}" tabindex="-1" style="padding-left:${8 + depth * 14}px">
      <span class="gfold">${shut ? "▸" : "▾"}</span><span class="gname">📁 ${esc(label)}</span><span class="gdir">${n}</span>
      <span class="grow-acts">
        ${code === "w" ? `<button class="mini danger" data-gact="discard" title="x">↺</button>` : ""}
        ${code !== "c" ? `<button class="mini" data-gact="toggle" title="space">${code === "s" ? "−" : "+"}</button>` : ""}
      </span></div>`;
  }
  function groupRows(code, list) {
    if (!G.tree || !G.st.trees) return list.map((f) => fileRow(code, f)).join("");
    const by = new Map(list.map((f) => [f.path, f]));
    const shut = [...G.closed].filter((k) => k.startsWith(code + "\0")).map((k) => k.slice(2));
    return G.st.trees[code].filter(([, path]) => !shut.some((d) => path !== d && path.startsWith(d)))
      .map(([depth, path, label, isDir]) => isDir ? dirRow(code, depth, path, label, list.filter((f) => f.path.startsWith(path)).length)
        : fileRow(code, by.get(path), depth)).join("");
  }
  // file của nhóm ứng với dòng đang chọn: chính file đó, hoặc mọi file trong thư mục (chế độ cây)
  function groupPaths(sel) {
    if (!sel.path.endsWith("/")) return [sel.path];
    return ((G.st && G.st.groups[sel.code]) || []).map((f) => f.path).filter((p) => p.startsWith(sel.path));
  }
  function fold(sel) { const k = sel.code + "\0" + sel.path; if (!G.closed.delete(k)) G.closed.add(k); render(); }
  function setTree(on) {
    G.tree = on;
    try { localStorage.setItem("ateam.gitTree", on ? "1" : "0"); } catch (e) { /* chế độ riêng tư */ }
    render();
  }

  function commitAgent() {
    const s = S.state || {};
    return s.commit_agent && (s.agents || []).some((a) => a.name === s.commit_agent) ? s.commit_agent : "";
  }
  function aiAgents() {  // trưởng nhóm (mặc định) + các agent đang bật — như ô chọn ở TUI
    const s = S.state || {}, cur = commitAgent();
    return `<option value="">${esc(t("git_ai_lead", { lead: s.lead || "" }))}</option>`
      + (s.agents || []).filter((a) => a.name !== s.lead).map((a) => `<option value="${esc(a.name)}"${a.name === cur ? " selected" : ""}>${esc(a.name)}</option>`).join("");
  }
  function render() {
    const st = G.st, el = box();
    if (!st || !el) return;
    if (!st.is_repo) {
      el.innerHTML = `<div class="empty"><div class="empty-ico"><svg viewBox="0 0 24 24"><circle cx="6" cy="6" r="2.4"/><circle cx="6" cy="18" r="2.4"/><circle cx="18" cy="9" r="2.4"/><path d="M6 8.4v7.2M18 11.4c0 3-3 3.6-6 4.2"/></svg></div>
        <div class="big">${esc(t("git_norepo"))}</div><div>${esc(t("git_norepo_hint"))}</div>
        <button class="btn primary" data-gact="init">git init</button></div>`;
      return;
    }
    const sync = st.upstream ? [st.ahead ? `↑${st.ahead}` : "", st.behind ? `↓${st.behind}` : ""].filter(Boolean).join(" ") || "✓ " + t("git_synced") : t("git_no_remote");
    const head = st.branch || (st.oid ? "detached @" + st.oid.slice(0, 8) : t("git_no_commit"));
    const files = groups().map(([code, title, list]) => `<div class="ggroup"><div class="ghead">${esc(title)} <span class="n">${list.length}</span>
        ${code === "s" ? `<button class="mini" data-gact="unstage_all" title="u">${esc(t("git_unstage_all"))}</button>` : code === "w" ? `<button class="mini" data-gact="stage_all" title="a">${esc(t("git_stage_all"))}</button>` : code === "c" ? `<button class="mini" data-gact="ai_resolve">🤖 ${esc(t("cf_ai_all"))}</button>` : ""}
        ${code !== "c" && st.oid && !st.state && !st.groups.c.length ? `<button class="mini danger" data-gact="discard_all" title="X">${esc(t("git_discard_all"))}</button>` : ""}</div>
        ${groupRows(code, list)}</div>`).join("") || `<div class="gclean">✓ ${esc(t("git_clean"))}</div>`;
    const nStaged = st.groups.s.length;
    const ph = G.amend ? t("git_msg_amend") : nStaged ? t("git_msg_staged", { n: nStaged }) : t("git_msg_all");
    const log = G.log.map((c, i) => `<div class="gcommit${G.selCommit === c.sha ? " sel" : ""}" data-gact="commit" data-sha="${esc(c.sha)}">
        <span class="sha">${esc(c.short)}</span>${c.refs ? `<span class="refs">${esc(c.refs)}</span>` : ""}<span class="subj">${esc(c.subject)}</span>
        <span class="who">${esc(c.author)} · ${esc(c.date)}</span>
        <span class="grow-acts"><button class="mini" data-gact="show" title="d">Δ</button><button class="mini" data-gact="revert" title="r">↶</button>
        ${i === 0 ? `<button class="mini" data-gact="undo" title="${esc(t("git_undo"))}">⎌</button>` : ""}</span></div>`).join("")
      || `<div class="gclean muted">${esc(t("git_no_commit"))}</div>`;
    const keepMsg = $("#git-msg") ? $("#git-msg").value : "";
    const focused = document.activeElement && document.activeElement.id === "git-msg";
    el.innerHTML = `
      <div class="ghdr panel">
        <div class="gbranch"><svg viewBox="0 0 24 24"><circle cx="6" cy="6" r="2.4"/><circle cx="6" cy="18" r="2.4"/><circle cx="18" cy="9" r="2.4"/><path d="M6 8.4v7.2M18 11.4c0 3-3 3.6-6 4.2-2 .4-4 1-5.6 2.4"/></svg>
          <b>${esc(head)}</b>${st.upstream ? `<span class="muted">→ ${esc(st.upstream)}</span>` : ""}<span class="chip">${esc(sync)}</span>
          ${st.stashes ? `<span class="chip">📦 ${st.stashes} stash</span>` : ""}
          ${st.state ? `<span class="chip warn">⚠ ${esc(t("git_state", { v: st.state }))}</span>${st.groups.c.length ? "" : `<button class="btn sm primary" data-gact="continue">▶ ${esc(t("git_continue", { v: st.state }))}</button>`}<button class="btn sm danger" data-gact="abort">${esc(t("git_abort"))}</button>` : ""}</div>
        <div class="panel-actions">
          <button class="btn sm ghost" data-gact="fetch">⇣ Fetch</button>
          <button class="btn sm ghost" data-gact="pull">⬇ Pull</button>
          <button class="btn sm" data-gact="push">⬆ Push</button>
          <button class="btn sm ghost" data-gact="branches">⎇ ${esc(t("git_branches"))}</button>
          <button class="btn sm ghost" data-gact="stash">📦 Stash</button>
          <button class="icon-btn" data-gact="refresh" title="${esc(t("refresh"))}"><svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 11-2.3-5.6M20 4v5h-5"/></svg></button>
        </div>
      </div>
      <div class="gmain">
        <div class="gleft panel">
          <div class="gfiles-bar"><button class="btn sm ghost" data-gact="tree" title="${esc(t("git_tree_hint"))}">${esc(t(G.tree ? "git_list" : "git_tree"))}</button></div>
          <div class="gfiles" id="git-files">${files}</div>
          <div class="gcommitbox">
            <textarea id="git-msg" class="field" rows="3" placeholder="${esc(ph)}">${esc(keepMsg)}</textarea>
            <div class="row-actions">
              <label class="chk"><input type="checkbox" id="git-amend" ${G.amend ? "checked" : ""}> ${esc(t("git_amend"))}</label>
              <label class="chk"><input type="checkbox" id="git-noverify" ${G.noVerify ? "checked" : ""}> ${esc(t("git_noverify"))}</label>
              <span style="flex:1"></span>
              <select class="agent-select" id="git-ai-agent" title="${esc(t("git_ai_agent"))}">${aiAgents()}</select>
              <button class="btn sm" data-gact="ai">✨ ${esc(t("git_ai"))}</button>
              <button class="btn sm primary" data-gact="commit_now">✓ Commit <kbd>⌘↵</kbd></button>
            </div>
          </div>
        </div>
        <div class="gright panel"><div class="ghead">${esc(t("git_history"))}</div><div class="glog">${log}</div></div>
      </div>`;
    if (focused) { const m = $("#git-msg"); m.focus(); m.setSelectionRange(m.value.length, m.value.length); }
    markBusy();
  }

  function selPath(el) {
    const row = el.closest(".gfile");
    return row ? { code: row.dataset.code, path: row.dataset.path } : G.sel;
  }
  async function toggle(sel) {
    if (!sel || sel.code === "c") return;
    await act(sel.code === "s" ? "unstage" : "stage", { paths: groupPaths(sel) });
  }
  async function discard(sel) {
    if (!sel || sel.code !== "w") return;
    if (sel.path.endsWith("/")) {
      const paths = groupPaths(sel);
      if (paths.length && await confirmBox(t("git_discard_title"), t("git_discard_dir", { n: paths.length, path: sel.path }), t("git_discard_yes"))) await act("discard", { paths });
      return;
    }
    const f = G.st.groups.w.find((x) => x.path === sel.path);
    const untracked = f && f.icon === "U";
    if (await confirmBox(t("git_discard_title"), untracked ? t("git_discard_new", { path: sel.path }) : t("git_discard_q", { path: sel.path }), t("git_discard_yes"))) await act("discard", { path: sel.path });
  }
  async function discardAll() {  // ↺ Bỏ tất cả: đã stage + chưa stage + file mới, về đúng commit cuối
    const g = G.st && G.st.groups;
    if (!g || !(g.s.length || g.w.length)) return;
    const u = g.w.filter((f) => f.icon === "U").length;
    if (await confirmBox(t("git_discard_all_title"), t("git_discard_all_q", { s: g.s.length, w: g.w.length - u, u }), t("git_discard_all_yes"))) await act("discard_all");
  }
  function diff(sel) {
    if (!sel) return;
    const path = groupPaths(sel)[0];  // thư mục: file đầu tiên
    if (path) DiffView.git({ kind: sel.code === "s" ? "staged" : sel.code === "c" ? "conflict" : "unstaged", path });
  }
  async function commit() {
    if (G.ops.has("commit")) return;
    const box = $("#git-msg"), msg = box.value.trim();
    if (!msg && !G.amend) { toast(t("git_need_msg"), "warn"); box.focus(); return; }
    const r = await act("commit", { message: msg, amend: G.amend, no_verify: G.noVerify });
    // act() đã vẽ lại tab (ô nhập là phần tử mới, còn giữ message cũ) → xoá trên phần tử hiện tại
    if (r.committed) { $("#git-msg").value = ""; G.amend = false; render(); }
  }
  async function aiMessage() {
    if (G.ops.has("ai_message")) return;
    G.ops.add("ai_message"); markBusy();
    const r = await request("git", { action: "ai_message" }, t("git_ai_wait", { lead: commitAgent() || (S.state && S.state.lead) || "lead" }));
    G.ops.delete("ai_message");
    markBusy();
    if (r.git_msg) { $("#git-msg").value = r.git_msg; $("#git-msg").focus(); }
  }
  async function onClick(e) {
    const b = e.target.closest("[data-gact]");
    if (!b) return;
    const a = b.dataset.gact;
    if (a === "sel") {  // bấm vào file = mở diff (xung đột: giải quyết) như Enter ở TUI; thư mục = thu/mở
      G.sel = selPath(b); $$(".gfile", box()).forEach((r) => r.classList.toggle("sel", r === b));
      if (G.sel.path.endsWith("/")) return fold(G.sel);
      return G.sel.code === "c" ? resolve(G.sel.path) : diff(G.sel);
    }
    const sel = selPath(b);
    if (b.closest(".gfile")) G.sel = sel;
    const sha = b.closest(".gcommit") && b.closest(".gcommit").dataset.sha;
    switch (a) {
      case "toggle": return toggle(sel);
      case "discard": return discard(sel);
      case "discard_all": return discardAll();
      case "diff": return diff(sel);
      case "resolve": return resolve(sel.path);
      case "ai_resolve": return act("ai_resolve");
      case "continue": return act("continue");
      case "edit": setView("code"); return CodeView.open(sel.path);
      case "tree": return setTree(!G.tree);
      case "stage_all": case "unstage_all": case "init": case "abort": return act(a);
      case "fetch": case "pull": case "push":
        if (G.ops.has(a)) return;
        return act(a);
      case "refresh": G.sig = ""; return refresh();
      case "branches": return branches();
      case "stash": return stash();
      case "ai": return aiMessage();
      case "commit_now": return commit();
      case "commit": G.selCommit = sha; $$(".gcommit", box()).forEach((r) => r.classList.toggle("sel", r.dataset.sha === sha)); return;
      case "show": return DiffView.git({ commit: sha });
      case "revert": {
        const c = G.log.find((x) => x.sha === sha);
        if (await confirmBox("↶ Revert", t("git_revert_q", { v: `${c.short} ${c.subject}` }), "Revert")) await act("revert", { sha });
        return;
      }
      case "undo":
        if (await confirmBox(t("git_undo"), t("git_undo_q"), t("git_undo_yes"))) await act("undo");
        return;
    }
  }
  async function onChange(e) {
    if (e.target.id === "git-noverify") { G.noVerify = e.target.checked; render(); }
    if (e.target.id === "git-ai-agent") {
      if (S.state) S.state.commit_agent = e.target.value;
      await request("git", { action: "commit_agent", name: e.target.value });
    }
    if (e.target.id === "git-amend") {
      G.amend = e.target.checked;
      const msg = $("#git-msg");
      if (G.amend && !msg.value.trim()) { const r = await request("git", { action: "last_message" }); if (r.git_msg) msg.value = r.git_msg; }
      render();
    }
  }
  function onKey(e) {
    if (S.view !== "git") return;
    if (e.target.id === "git-msg") {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); commit(); }
      return;
    }
    if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || topModal() || e.metaKey || e.ctrlKey) return;
    const k = e.key;
    const rows = $$(".gfile", box());
    if (k === "ArrowDown" || k === "ArrowUp" || k === "j" || k === "k") {
      const i = rows.findIndex((r) => r.classList.contains("sel"));
      const n = rows[Math.max(0, Math.min(rows.length - 1, i + (k === "ArrowDown" || k === "j" ? 1 : -1)))];
      if (n) { G.sel = { code: n.dataset.code, path: n.dataset.path }; rows.forEach((r) => r.classList.toggle("sel", r === n)); n.scrollIntoView({ block: "nearest" }); }
    } else if (k === " ") toggle(G.sel);
    else if (k === "a") act("stage_all");
    else if (k === "u") act("unstage_all");
    else if (k === "x") discard(G.sel);
    else if (k === "X") discardAll();
    else if (k === "t") setTree(!G.tree);
    else if (k === "Enter" && G.sel && G.sel.path.endsWith("/")) fold(G.sel);
    else if ((k === "r" || k === "Enter") && G.sel && G.sel.code === "c") resolve(G.sel.path);
    else if (k === "g" && G.st && G.st.groups.c.length) act("ai_resolve");
    else if (k === "d" || k === "Enter") diff(G.sel);
    else if (k === "c") $("#git-msg").focus();
    else if (k === "e" && G.sel && !G.sel.path.endsWith("/")) { setView("code"); CodeView.open(G.sel.path); }
    else return;
    e.preventDefault();
  }

  /* ---------------------------------------------------------------- giải quyết xung đột */
  // Như VS Code: mỗi khối <<<<<<< có nút Giữ hiện tại / Lấy bên đến / Giữ cả hai; hết khối thì server tự stage.
  async function resolve(path) {
    if (!path) return;
    const m = openModal(`${modalHead("⇄ " + esc(t("cf_title")) + ` <span class="muted mono">· ${esc(path)}</span>`)}
      <div class="modal-pad cf-body"></div>`, { box: "lg" });
    const side = (cls, label, tag, text) => `<div class="cf-side ${cls}"><div class="cf-label">${esc(label)}${tag ? ` <span class="muted">· ${esc(tag)}</span>` : ""}</div>
      <pre class="mono">${esc(text) || `<span class="muted">${esc(t("cf_empty"))}</span>`}</pre></div>`;
    const ctx = (lines) => lines.length ? `<pre class="mono cf-ctx">${esc(lines.join("\n"))}</pre>` : "";
    async function load() {
      const info = await (await fetch("/api/git/conflict?path=" + encodeURIComponent(path))).json();
      if (!info.conflicted) { closeModal(m); toast(t("cf_resolved", { path }), "ok"); return; }
      const n = info.blocks.length;
      const note = info.ours_deleted ? t("cf_ours_deleted") : info.theirs_deleted ? t("cf_theirs_deleted")
        : info.binary ? t("cf_binary") : n ? "" : t("cf_none");
      const blocks = info.blocks.map((b, i) => `<div class="cf-block" data-i="${i}">
          <div class="cf-head"><b>${esc(t("cf_block", { i: i + 1, n, line: b.line }))}</b><span style="flex:1"></span>
            <button class="btn sm" data-cf="ours">${esc(t("cf_keep_current"))}</button>
            <button class="btn sm" data-cf="theirs">${esc(t("cf_keep_incoming"))}</button>
            <button class="btn sm ghost" data-cf="both">${esc(t("cf_keep_both"))}</button></div>
          ${ctx(b.before)}${side("cur", t("cf_current"), b.ours_label, b.ours)}
          ${b.base !== null ? side("base", t("cf_base"), "", b.base) : ""}
          ${side("inc", t("cf_incoming"), b.theirs_label, b.theirs)}${ctx(b.after)}</div>`).join("");
      $(".cf-body", m).innerHTML = `
        ${info.state === "rebase" ? `<div class="muted small">${esc(t("cf_rebase"))}</div>` : ""}
        ${note ? `<div class="cf-note">${esc(note)}</div>` : ""}
        <div class="row-actions">
          <button class="btn sm" data-cf="take_ours">${esc(t("cf_all_current"))}</button>
          <button class="btn sm" data-cf="take_theirs">${esc(t("cf_all_incoming"))}</button>
          <button class="btn sm ghost" data-cf="ai">🤖 ${esc(t("cf_ai"))}</button>
          <button class="btn sm ghost" data-cf="edit">✎ ${esc(t("cf_edit"))}</button>
          <span style="flex:1"></span>
          <button class="btn sm primary" data-cf="done">✓ ${esc(t("cf_done"))}</button></div>
        <div class="cf-list">${blocks}</div>`;
    }
    m.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-cf]");
      if (!b) return;
      const a = b.dataset.cf, blk = b.closest(".cf-block");
      if (a === "edit") { closeModal(m); setView("code"); return CodeView.open(path); }
      if (a === "ai") { closeModal(m); return act("ai_resolve", { path }); }
      const r = blk ? await act("resolve_block", { path, index: +blk.dataset.i, choice: a })
        : await act(a === "done" ? "mark_resolved" : a, { path });
      if (r.level !== "warn") await load();
    });
    await load();
  }

  /* ---------------------------------------------------------------- nhánh */
  async function branches() {
    const list = await (await fetch("/api/git/branches")).json();
    const cur = G.st && G.st.branch;
    const row = (b) => `<div class="brow${b.current ? " cur" : ""}" data-name="${esc(b.name)}" data-remote="${b.remote ? 1 : 0}">
        <span class="bdot">${b.current ? "●" : ""}</span><b>${esc(b.name)}</b>${b.name.startsWith("ateam/") ? `<span class="chip">task</span>` : ""}
        <span class="muted">${esc(b.track || (b.upstream ? "→ " + b.upstream : ""))}</span><span class="muted bsub">${esc(b.date)} · ${esc(b.subject)}</span>
        <span class="grow-acts">
          ${b.current ? "" : `<button class="btn sm" data-bact="checkout">${esc(t("git_checkout"))}</button>`}
          ${b.current || b.remote ? "" : `<button class="btn sm ghost" data-bact="merge">Merge</button>`}
          ${b.remote ? "" : `<button class="btn sm ghost" data-bact="rename">${esc(t("git_rename"))}</button>`}
          ${b.current || b.remote ? "" : `<button class="btn sm danger" data-bact="delete">${esc(t("remove"))}</button>`}
        </span></div>`;
    const group = (key, items) => items.length ? `<div class="bgroup" data-group="${key}"><div class="ghead">${esc(t(key))} <span class="n">${items.length}</span></div>${items.map(row).join("")}</div>` : "";
    const m = openModal(`${modalHead("⎇ " + esc(t("git_branches")) + (cur ? ` <span class="muted">· ${esc(cur)}</span>` : ""))}
      <div class="modal-pad"><input class="field one" id="gb-filter" placeholder="${esc(t("git_filter_branch"))}" autofocus>
      <div class="blist">${group("git_local", list.filter((b) => !b.remote))}${group("git_remote", list.filter((b) => b.remote))}
        <div class="gclean muted" id="gb-none" hidden>${esc(t("git_no_match"))}</div></div>
      <div class="row-actions"><input class="field one" id="gb-name" placeholder="${esc(t("git_new_branch"))}">
      <button class="btn primary" data-bact="create">+ ${esc(t("git_create_branch"))}</button></div></div>`, { box: "md" });
    const filter = () => {
      const q = $("#gb-filter", m).value.trim().toLowerCase();
      let shown = 0;
      $$(".bgroup", m).forEach((g) => {
        let n = 0;
        $$(".brow", g).forEach((r) => { const ok = !q || r.dataset.name.toLowerCase().includes(q); r.hidden = !ok; n += ok; });
        g.hidden = !n; $(".n", g).textContent = n; shown += n;
      });
      $("#gb-none", m).hidden = !!shown;
    };
    $("#gb-filter", m).addEventListener("input", filter);
    $("#gb-filter", m).addEventListener("keydown", (e) => {
      if (e.key === "Escape" && e.target.value) { e.preventDefault(); e.stopPropagation(); e.target.value = ""; filter(); }
      if (e.key === "Enter") {  // chuyển sang nhánh khớp đầu tiên
        const r = $$(".brow", m).find((x) => !x.hidden && !x.classList.contains("cur"));
        if (r) { closeModal(m); act("checkout", { name: r.dataset.name }); }
      }
    });
    m.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-bact]");
      if (!b) return;
      const row = b.closest(".brow"), name = row ? row.dataset.name : "";
      const a = b.dataset.bact;
      if (a === "create") {
        const n = $("#gb-name", m).value.trim();
        if (!n) return;
        closeModal(m); return act("create_branch", { name: n });
      }
      if (a === "checkout") { closeModal(m); return act("checkout", { name }); }
      if (a === "merge") { if (await confirmBox("Merge", t("git_merge_q", { name, cur }), "Merge", false)) { closeModal(m); return act("merge", { name }); } return; }
      if (a === "rename") {
        const nn = await inputBox(t("git_rename"), t("git_rename_q", { name }), name);
        if (nn && nn !== name) { closeModal(m); return act("rename_branch", { name, new: nn }); }
        return;
      }
      if (a === "delete") {
        const r = await act("delete_branch", { name });
        if (r.level === "warn" && /merged|merge/.test(r.text || "") && await confirmBox(t("git_force_delete"), t("git_force_delete_q", { name }), t("git_force_delete"))) await act("delete_branch", { name, force: true });
        closeModal(m); branches();
      }
    });
    $("#gb-name", m).addEventListener("keydown", (e) => { if (e.key === "Enter") m.querySelector("[data-bact=create]").click(); });
  }

  /* ---------------------------------------------------------------- stash */
  async function stash() {
    const list = await (await fetch("/api/git/stashes")).json();
    const dirty = G.st && !G.st.clean;
    const rows = list.map((s) => `<div class="brow" data-ref="${esc(s.ref)}"><b>${esc(s.ref)}</b><span class="bsub">${esc(s.subject)}</span><span class="muted">${esc(s.date)}</span>
        <span class="grow-acts"><button class="btn sm" data-sact="pop">Pop</button><button class="btn sm ghost" data-sact="apply">Apply</button>
        <button class="btn sm danger" data-sact="drop">${esc(t("remove"))}</button></span></div>`).join("") || `<div class="gclean muted">${esc(t("git_no_stash"))}</div>`;
    const m = openModal(`${modalHead("📦 Stash")}<div class="modal-pad">
      <div class="row-actions"><input class="field one" id="gs-msg" placeholder="${esc(t("git_stash_msg"))}" ${dirty ? "autofocus" : "disabled"}>
      <button class="btn primary" data-sact="push" ${dirty ? "" : "disabled"}>${esc(t("git_stash_push"))}</button></div>
      <div class="blist">${rows}</div></div>`, { box: "md" });
    m.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-sact]");
      if (!b) return;
      const ref = b.closest(".brow") && b.closest(".brow").dataset.ref, a = b.dataset.sact;
      if (a === "push") { closeModal(m); return act("stash_push", { message: $("#gs-msg", m).value.trim() }); }
      if (a === "drop") { if (await confirmBox(t("git_stash_drop"), t("git_stash_drop_q", { ref }), t("remove"))) { closeModal(m); await act("stash_drop", { stash: ref }); stash(); } return; }
      closeModal(m); return act(a === "pop" ? "stash_pop" : "stash_apply", { stash: ref });
    });
    $("#gs-msg", m).addEventListener("keydown", (e) => { if (e.key === "Enter") m.querySelector("[data-sact=push]").click(); });
  }

  document.addEventListener("click", (e) => { if (e.target.closest("#git")) onClick(e); });
  document.addEventListener("change", (e) => { if (e.target.closest("#git")) onChange(e); });
  document.addEventListener("keydown", onKey);

  return {
    show() { refresh(); clearInterval(G.timer); G.timer = setInterval(() => { if (!document.hidden && !topModal()) refresh(); }, 3000); },
    hide() { clearInterval(G.timer); G.timer = null; },
    aiMessage() { setTimeout(aiMessage, 300); },
    branches, stash, resolve,
  };
})();
