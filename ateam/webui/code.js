/* Tab Code — như tab 📝 Code của TUI: cây thư mục + lọc file, nhiều file mở (tối đa 10), editor CodeMirror 6
   (vendor/codemirror.js, nạp khi mở tab lần đầu) với phím vim (bật/tắt dùng chung TUI: /vim on|off), :w :q :wq
   :x :q! :e! :e <file> :bn :bp, Ctrl/⌘+S lưu. File đổi trên đĩa (agent sửa): chưa sửa → tự nạp lại, đang sửa → cảnh
   báo; lưu khi file đã đổi → hỏi ghi đè. File .md: Sửa / Chia đôi / Xem trước (mdHtml của app.js, Ctrl/⌘+Shift+V đổi
   chế độ, nhớ trong localStorage "ateam-md"). 🔍 Tìm & thay trong toàn dự án (⌘⇧F, như VS Code) ở sidebar — logic
   ở ateam/search.py. */
"use strict";

window.CodeView = (() => {
  const LIMIT = 10;
  const C = { view: null, bufs: new Map(), order: [], cur: null, open: new Set([""]), tree: {}, filter: "",
    loading: null, comp: null, warned: {}, timer: null, mode: "normal" };
  const el = () => $("#code");

  /* ---------------------------------------------------------------- nạp CodeMirror */
  function loadCM() {
    if (window.CM) return Promise.resolve();
    if (C.loading) return C.loading;
    C.loading = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "/static/vendor/codemirror.js";
      s.onload = () => { defineEx(); resolve(); };
      s.onerror = reject;
      document.head.appendChild(s);
    });
    return C.loading;
  }
  function comps() {
    if (!C.comp) C.comp = { vim: new CM.Compartment(), theme: new CM.Compartment(), lang: new CM.Compartment(), ro: new CM.Compartment() };
    return C.comp;
  }
  const vimOn = () => S.prefs.vim !== false;
  const MD_MODES = ["edit", "split", "view"];
  C.md = (() => { try { return localStorage.getItem("ateam-md") || "edit"; } catch (e) { return "edit"; } })();

  function extensions(buf) {
    const c = comps();
    return [
      c.vim.of(vimOn() ? CM.vim() : []),  // vim trước các keymap khác
      CM.basicSetup,
      CM.keymap.of([CM.indentWithTab, { key: "Mod-s", run: () => { save(); return true; } }]),
      c.theme.of(isDark() ? CM.oneDark : []),
      c.lang.of(buf.lang ? buf.lang.support : []),
      c.ro.of(CM.EditorState.readOnly.of(!!buf.ro)),
      CM.EditorView.updateListener.of((u) => {
        if (u.docChanged) { buf.dirty = u.state.doc.toString() !== buf.saved; renderTabs(); schedulePreview(); }
        if (u.docChanged || u.selectionSet) renderStatus();
      }),
    ];
  }

  /* ---------------------------------------------------------------- lệnh vim (:w :q …) */
  function defineEx() {
    const V = CM.Vim;
    const bang = (p) => /!/.test((p.input || "").split(/\s/)[0]);
    V.defineEx("write", "w", (_cm, p) => save(bang(p)));
    V.defineEx("update", "up", () => save());
    V.defineEx("wq", "wq", async (_cm, p) => { if (await save(bang(p))) close(C.cur); });
    V.defineEx("xit", "x", async (_cm, p) => { if (await save(bang(p))) close(C.cur); });
    V.defineEx("quit", "q", (_cm, p) => close(C.cur, bang(p)));
    V.defineEx("bdelete", "bd", (_cm, p) => close(C.cur, bang(p)));
    V.defineEx("close", "clo", (_cm, p) => close(C.cur, bang(p)));
    V.defineEx("edit", "e", (_cm, p) => {
      const arg = (p.args || []).join(" ").trim();
      if (arg) open(arg);
      else if (bang(p)) reload(true);
      else el().classList.toggle("no-side");
    });
    V.defineEx("bnext", "bn", () => cycle(1));
    V.defineEx("bprevious", "bp", () => cycle(-1));
    V.defineEx("files", "files", () => el().classList.toggle("no-side"));
    V.defineEx("Explore", "Ex", () => el().classList.toggle("no-side"));
  }

  /* ---------------------------------------------------------------- khung */
  function layout() {
    if ($("#code-editor")) return;
    el().innerHTML = `
      <aside class="code-side">
        <div class="side-tabs">
          <button class="side-tab on" data-side="files" title="${esc(t("sr_files"))}"><svg viewBox="0 0 24 24"><path d="M4 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2z"/></svg>${esc(t("sr_files"))}</button>
          <button class="side-tab" data-side="search" title="${esc(t("sr_search"))} (⌘⇧F)"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/></svg>${esc(t("sr_search"))}</button>
        </div>
        <div class="side-pane" id="side-files">
          <input class="field one" id="code-filter" placeholder="${esc(t("code_filter"))}" autocomplete="off" spellcheck="false">
          <div class="tree" id="code-tree"></div>
        </div>
        <div class="side-pane hidden" id="side-search">${searchPane()}</div>
      </aside>
      <section class="code-main">
        <div class="code-tabs" id="code-tabs"></div>
        <div class="code-body" data-md="edit">
          <div class="code-host" id="code-editor"></div>
          <div class="code-preview md" id="code-preview"></div>
        </div>
        <div class="code-status" id="code-status"></div>
      </section>`;
    bindSearch();
    $("#code-filter").addEventListener("input", (e) => { C.filter = e.target.value; renderTree(); });
    $("#code-filter").addEventListener("keydown", (e) => {
      if (e.key === "Enter") { const f = $("#code-tree .tnode.file"); if (f) open(f.dataset.path); }
      if (e.key === "Escape" && C.filter) { e.target.value = C.filter = ""; renderTree(); e.stopPropagation(); }
    });
  }

  /* ---------------------------------------------------------------- cây thư mục */
  async function loadDir(dir, force) {
    if (C.tree[dir] && !force) return C.tree[dir];
    try { C.tree[dir] = await (await fetch(`/api/tree?dir=${encodeURIComponent(dir)}${force ? "&refresh=1" : ""}`)).json(); }
    catch (e) { C.tree[dir] = []; }
    return C.tree[dir];
  }
  function icon(n) {
    if (n.dir) return C.open.has(n.path) ? "▾" : "▸";
    const ext = n.name.includes(".") ? n.name.split(".").pop().toLowerCase() : "";
    return `<i class="fic e-${esc(ext)}">${esc(ext.slice(0, 3) || "·")}</i>`;
  }
  function nodes(dir, depth) {
    return (C.tree[dir] || []).map((n) => {
      const cls = (n.dir ? "dir" : "file") + (n.path === C.cur ? " on" : "") + (C.bufs.get(n.path) && C.bufs.get(n.path).dirty ? " dirty" : "");
      const row = `<div class="tnode ${cls}" data-path="${esc(n.path)}" data-dir="${n.dir ? 1 : 0}" style="padding-left:${10 + depth * 14}px">
        <span class="ticon">${icon(n)}</span><span class="tname">${esc(n.name)}</span></div>`;
      return row + (n.dir && C.open.has(n.path) ? nodes(n.path, depth + 1) : "");
    }).join("");
  }
  let filterSeq = 0;
  async function renderTree() {
    const box = $("#code-tree");
    if (!box) return;
    if (C.filter.trim()) {
      const seq = ++filterSeq;
      const files = await (await fetch(`/api/files?n=80&q=${encodeURIComponent(C.filter.trim())}`)).json();
      if (seq !== filterSeq) return;
      box.innerHTML = files.map((f) => {
        const dir = f.endsWith("/");
        return `<div class="tnode ${dir ? "dir" : "file"}${f === C.cur ? " on" : ""}" data-path="${esc(dir ? f.slice(0, -1) : f)}" data-dir="${dir ? 1 : 0}" data-flat="1">
          <span class="ticon">${dir ? "▸" : icon({ name: f })}</span><span class="tname">${esc(f)}</span></div>`;
      }).join("") || `<div class="muted small pad">${esc(t("code_nofile"))}</div>`;
      return;
    }
    await loadDir("");
    box.innerHTML = nodes("", 0) || `<div class="muted small pad">${esc(t("code_nofile"))}</div>`;
  }
  async function onTree(e) {
    const n = e.target.closest(".tnode");
    if (!n) return;
    const path = n.dataset.path;
    if (n.dataset.dir === "1") {
      if (n.dataset.flat) { C.filter = path + "/"; $("#code-filter").value = C.filter; return renderTree(); }
      if (C.open.has(path)) C.open.delete(path); else { C.open.add(path); await loadDir(path); }
      return renderTree();
    }
    open(path);
  }
  function revealInTree(path) {  // mở các thư mục cha của file đang xem
    const parts = path.split("/");
    let acc = "";
    for (const p of parts.slice(0, -1)) { acc = acc ? acc + "/" + p : p; C.open.add(acc); }
    return Promise.all([...C.open].map((d) => loadDir(d))).then(renderTree);
  }

  /* ---------------------------------------------------------------- file đang mở */
  function renderTabs() {
    const box = $("#code-tabs");
    if (!box) return;
    box.innerHTML = C.order.map((p) => {
      const b = C.bufs.get(p);
      return `<div class="ctab${p === C.cur ? " on" : ""}" data-path="${esc(p)}" title="${esc(p)}">
        <span class="tname">${esc(p.split("/").pop())}</span>${b.dirty ? `<span class="dot-dirty">●</span>` : ""}
        <button class="ctab-x" data-close="${esc(p)}">×</button></div>`;
    }).join("") || `<div class="muted small pad">${esc(t("code_hint"))}</div>`;
    $$("#code-tree .tnode.file").forEach((n) => n.classList.toggle("dirty", !!(C.bufs.get(n.dataset.path) || {}).dirty));
  }
  function renderStatus() {
    const box = $("#code-status");
    if (!box) return;
    const b = C.cur && C.bufs.get(C.cur);
    if (!b) { box.innerHTML = `<span>${esc(vimOn() ? t("code_vim_hint") : t("code_novim_hint"))}</span>`; return; }
    const st = C.view.state, pos = st.selection.main.head, line = st.doc.lineAt(pos);
    const mode = vimOn() ? `<span class="vmode m-${esc(C.mode)}">${esc(C.mode.toUpperCase())}</span>` : "";
    box.innerHTML = `${mode}<span class="mono">${esc(b.path)}</span>${b.dirty ? `<span class="dot-dirty">●</span>` : ""}
      <span style="flex:1"></span>${b.ro ? `<span class="chip warn">${esc(t("code_readonly", { v: b.note }))}</span>` : ""}
      ${b.newline === "\r\n" ? `<span class="chip">CRLF</span>` : ""}<span>${esc((b.lang && b.lang.name) || b.language || t("code_plain"))}</span>
      <span class="mono">${esc(t("code_pos", { r: line.number, n: st.doc.lines, c: pos - line.from + 1 }))}</span>
      ${isMd(b) ? `<span class="seg" title="${esc(t("code_md_title"))}">${MD_MODES.map((m) =>
        `<button class="mini${m === C.md ? " on" : ""}" data-cact="md" data-md="${m}">${esc(t("code_md_" + m))}</button>`).join("")}</span>` : ""}
      <button class="mini" data-cact="vim" title="/vim on|off">vim ${vimOn() ? "✓" : "✗"}</button>`;
  }

  /* ---------------------------------------------------------------- xem trước markdown */
  const isMd = (b) => !!b && /\.(md|markdown|mdx)$/i.test(b.path);
  function mdMode() { return isMd(C.cur && C.bufs.get(C.cur)) ? C.md : "edit"; }
  let pvTimer = null;
  function renderPreview() {
    const box = $("#code-preview");
    if (!box) return;
    const mode = mdMode();
    box.parentElement.dataset.md = mode;
    box.innerHTML = mode === "edit" || !C.view ? "" : mdHtml(C.view.state.doc.toString());
  }
  function schedulePreview() {
    if (mdMode() === "edit") return;
    clearTimeout(pvTimer);
    pvTimer = setTimeout(renderPreview, 150);
  }
  function setMd(mode) {
    C.md = mode;
    try { localStorage.setItem("ateam-md", mode); } catch (e) { /* chặn lưu */ }
    renderPreview(); renderStatus();
    if (C.view) { C.view.requestMeasure(); if (mode !== "view") C.view.focus(); }
  }
  function syncScroll() {  // chia đôi: preview cuộn theo editor (theo tỉ lệ)
    const src = C.view && C.view.scrollDOM, box = $("#code-preview");
    if (!src || !box || mdMode() !== "split") return;
    const r = src.scrollTop / Math.max(1, src.scrollHeight - src.clientHeight);
    box.scrollTop = r * (box.scrollHeight - box.clientHeight);
  }
  function newView(state) {
    C.view = new CM.EditorView({ state, parent: $("#code-editor") });
    C.view.scrollDOM.addEventListener("scroll", syncScroll);
  }

  function stash() {
    const b = C.cur && C.bufs.get(C.cur);
    if (b && C.view) b.state = C.view.state;
  }
  function activate(path, line, col, len) {
    const b = C.bufs.get(path);
    if (!b) return;
    stash();
    C.cur = path;
    if (!b.state) b.state = CM.EditorState.create({ doc: b.saved, extensions: extensions(b) });
    if (!C.view) {
      newView(b.state);
      watchVim();
    } else C.view.setState(b.state);
    refreshConfig();
    if (line) {
      const ln = C.view.state.doc.line(Math.max(1, Math.min(line, C.view.state.doc.lines)));
      const from = Math.min(ln.from + (col || 0), ln.to);
      const to = vimOn() ? from : Math.min(from + (len || 0), C.view.state.doc.length);  // vim: chỉ đặt con trỏ, không vào VISUAL
      C.view.dispatch({ selection: { anchor: from, head: to }, effects: CM.EditorView.scrollIntoView(from, { y: "center" }) });
    }
    C.view.focus();
    renderTabs(); renderStatus(); renderPreview();
    revealInTree(path);
  }
  function watchVim() {
    try {
      const cm = CM.getCM(C.view);
      if (cm) cm.on("vim-mode-change", (e) => { C.mode = e.mode + (e.subMode ? "-" + e.subMode : ""); renderStatus(); });
    } catch (e) { /* vim tắt */ }
  }
  function refreshConfig() {  // vim / sáng-tối đổi sau khi buffer được tạo
    if (!C.view) return;
    const c = comps();
    C.view.dispatch({ effects: [c.vim.reconfigure(vimOn() ? CM.vim() : []), c.theme.reconfigure(isDark() ? CM.oneDark : [])] });
    watchVim();
  }

  async function open(path, line, col, len) {
    path = String(path || "").replace(/^@/, "").replace(/^"(.*)"$/, "$1").replace(/\/$/, "");
    await show();
    if (!path) return;
    if (C.bufs.has(path)) { activate(path, line, col, len); return; }
    const r = await (await fetch("/api/file?path=" + encodeURIComponent(path))).json();
    if (r.dir) { C.filter = path + "/"; $("#code-filter").value = C.filter; renderTree(); return; }
    if (r.error) { toast(r.error, "warn"); return; }
    const lang = CM.languageFor(r.path);
    const b = { path: r.path, saved: r.text, mtime: r.mtime, ro: r.read_only, note: r.note, newline: r.newline, lang,
      language: r.language, dirty: false, state: null };
    C.bufs.set(r.path, b);
    C.order.push(r.path);
    while (C.order.length > LIMIT) {  // bỏ file cũ nhất chưa sửa
      const old = C.order.find((p) => !C.bufs.get(p).dirty && p !== r.path);
      if (!old) break;
      C.order.splice(C.order.indexOf(old), 1); C.bufs.delete(old);
    }
    activate(r.path, line, col, len);
    if (r.new) toast(t("code_new_file"), "info");
  }
  async function close(path, force) {
    const b = path && C.bufs.get(path);
    if (!b) return;
    if (path === C.cur) stash();
    if (b.dirty && !force) {
      if (!await confirmBox(t("code_unsaved"), t("code_unsaved_q", { path }), t("code_discard"))) return;
    }
    C.bufs.delete(path);
    const i = C.order.indexOf(path);
    C.order.splice(i, 1);
    if (path === C.cur) {
      C.cur = null;
      const next = C.order[Math.min(i, C.order.length - 1)];
      if (next) activate(next);
      else { C.view.setState(CM.EditorState.create({ doc: "", extensions: [CM.EditorState.readOnly.of(true), comps().theme.of(isDark() ? CM.oneDark : [])] })); renderStatus(); renderPreview(); }
    }
    renderTabs();
  }
  function cycle(d) {
    if (!C.order.length) return;
    const i = (C.order.indexOf(C.cur) + d + C.order.length) % C.order.length;
    activate(C.order[i]);
  }
  async function save(force = false) {
    const b = C.cur && C.bufs.get(C.cur);
    if (!b) return false;
    const text = C.view.state.doc.toString();
    const r = await request("save", { path: b.path, text, mtime: b.mtime, force });
    const sv = r.save || {};
    if (sv.conflict) {
      if (await confirmBox(t("code_conflict"), t("code_conflict_q", { path: b.path }), t("code_overwrite"))) return save(true);
      return false;
    }
    if (sv.read_only) {
      if (await confirmBox(t("code_readonly_title"), t("code_readonly_q", { v: b.note }), t("code_write_anyway"))) return save(true);
      return false;
    }
    if (sv.mtime) {
      b.saved = text; b.mtime = sv.mtime; b.dirty = false; C.warned[b.path] = 0;
      renderTabs(); renderStatus();
      return true;
    }
    return false;
  }
  async function reload(quiet, path) {
    const b = C.bufs.get(path || C.cur);
    if (!b) return;
    if (b.path !== C.cur) {  // file mở ở tab khác (vd vừa thay thế): nạp lại khi chuyển tới
      const r = await (await fetch("/api/file?path=" + encodeURIComponent(b.path))).json();
      if (!r.error) { b.saved = r.text; b.mtime = r.mtime; b.dirty = false; b.state = null; renderTabs(); }
      return;
    }
    const r = await (await fetch("/api/file?path=" + encodeURIComponent(b.path))).json();
    if (r.error) { toast(r.error, "warn"); return; }
    const head = C.view.state.selection.main.head;
    b.saved = r.text; b.mtime = r.mtime; b.dirty = false; b.ro = r.read_only; b.note = r.note;
    b.state = CM.EditorState.create({ doc: r.text, extensions: extensions(b), selection: { anchor: Math.min(head, r.text.length) } });
    C.view.setState(b.state);
    refreshConfig();
    renderTabs(); renderStatus(); renderPreview();
    toast(quiet === "disk" ? t("code_reloaded_disk") : t("code_reloaded"), "info");
  }
  async function checkDisk() {  // agent sửa file đang mở
    const b = C.cur && C.bufs.get(C.cur);
    if (!b || S.view !== "code" || document.hidden) return;
    try {
      const r = await (await fetch("/api/file/stat?path=" + encodeURIComponent(b.path))).json();
      if (!r.mtime || r.mtime === b.mtime || C.cur !== b.path) return;
      if (!b.dirty) reload("disk");
      else if (C.warned[b.path] !== r.mtime) { C.warned[b.path] = r.mtime; toast(t("code_changed_dirty"), "warn"); }
    } catch (e) { /* bỏ qua */ }
  }

  /* ---------------------------------------------------------------- 🔍 tìm & thay trong dự án */
  const SR = { query: "", replace: "", showRep: false, more: false, case: false, word: false, regex: false,
    include: "", exclude: "", res: null, hidden: new Set(), closed: new Set(), seq: 0, timer: null };
  function searchPane() {
    const opt = (k, label, title) => `<button class="sr-opt" data-opt="${k}" title="${esc(title)}">${label}</button>`;
    return `<div class="sr-form">
        <button class="sr-twist" data-sr="toggle-rep" title="${esc(t("sr_toggle_replace"))}">›</button>
        <div class="sr-fields">
          <div class="sr-box"><input class="field one" id="sr-q" placeholder="${esc(t("sr_search"))}" autocomplete="off" spellcheck="false">
            ${opt("case", "Aa", t("sr_case"))}${opt("word", "<u>ab</u>", t("sr_word"))}${opt("regex", ".*", t("sr_regex"))}</div>
          <div class="sr-box hidden" id="sr-rep-row"><input class="field one" id="sr-r" placeholder="${esc(t("sr_replace_ph"))}" autocomplete="off" spellcheck="false">
            <button class="sr-opt" data-sr="replace-all" title="${esc(t("sr_replace_all"))} (⌘⏎)">⇄</button></div>
        </div>
      </div>
      <button class="sr-more" data-sr="more">⋯ ${esc(t("sr_more"))}</button>
      <div class="sr-filters hidden" id="sr-filters">
        <input class="field one" id="sr-inc" placeholder="${esc(t("sr_include"))}" autocomplete="off" spellcheck="false">
        <input class="field one" id="sr-exc" placeholder="${esc(t("sr_exclude"))}" autocomplete="off" spellcheck="false">
      </div>
      <div class="sr-sum muted small" id="sr-sum"></div>
      <div class="sr-results" id="sr-results"></div>`;
  }
  function bindSearch() {
    const side = $(".code-side");
    side.addEventListener("click", (e) => {
      const tab = e.target.closest("[data-side]");
      if (tab) return sidePane(tab.dataset.side);
      const o = e.target.closest("[data-opt]");
      if (o) { SR[o.dataset.opt] = !SR[o.dataset.opt]; o.classList.toggle("on", SR[o.dataset.opt]); return runSearch(); }
      const b = e.target.closest("[data-sr]");
      if (b) {
        const a = b.dataset.sr;
        if (a === "toggle-rep") { SR.showRep = !SR.showRep; b.classList.toggle("open", SR.showRep); $("#sr-rep-row").classList.toggle("hidden", !SR.showRep); if (SR.showRep) $("#sr-r").focus(); return runSearch(); }
        if (a === "more") { SR.more = !SR.more; $("#sr-filters").classList.toggle("hidden", !SR.more); return; }
        if (a === "replace-all") return replaceFiles(visibleFiles());
        const path = b.closest("[data-file]") && b.closest("[data-file]").dataset.file;
        if (a === "file-replace") { e.stopPropagation(); return replaceFiles([path]); }
        if (a === "file-hide") { e.stopPropagation(); SR.hidden.add(path); return renderResults(); }
      }
      const head = e.target.closest(".sr-file-head");
      if (head) { const f = head.parentElement.dataset.file; SR.closed.has(f) ? SR.closed.delete(f) : SR.closed.add(f); return renderResults(); }
      const m = e.target.closest("[data-line]");
      if (m) open(m.closest("[data-file]").dataset.file, +m.dataset.line, +m.dataset.col, +m.dataset.len);
    });
    const input = (id, key) => $(id).addEventListener("input", (e) => { SR[key] = e.target.value; clearTimeout(SR.timer); SR.timer = setTimeout(runSearch, 250); });
    input("#sr-q", "query"); input("#sr-r", "replace"); input("#sr-inc", "include"); input("#sr-exc", "exclude");
    side.addEventListener("keydown", (e) => {
      if (!e.target.closest("#side-search")) return;
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && SR.showRep) { e.preventDefault(); replaceFiles(visibleFiles()); }
      else if (e.key === "Enter") { e.preventDefault(); clearTimeout(SR.timer); runSearch(); }
    });
  }
  function sidePane(which, prefill) {
    $$(".side-tab").forEach((b) => b.classList.toggle("on", b.dataset.side === which));
    $("#side-files").classList.toggle("hidden", which !== "files");
    $("#side-search").classList.toggle("hidden", which !== "search");
    el().classList.toggle("searching", which === "search");
    if (which === "search") {
      const q = $("#sr-q");
      if (prefill && !prefill.includes("\n")) { q.value = SR.query = prefill; runSearch(); }
      q.focus(); q.select();
    } else $("#code-filter").focus();
  }
  async function runSearch() {
    const seq = ++SR.seq;
    SR.hidden.clear();
    if (!SR.query) { SR.res = null; return renderResults(); }
    $("#sr-sum").textContent = t("sr_searching");
    const r = await request("code_search", { query: SR.query, case: SR.case, word: SR.word, regex: SR.regex,
      include: SR.include, exclude: SR.exclude, replace: SR.showRep ? SR.replace : null });
    if (seq !== SR.seq) return;  // đã gõ tiếp
    SR.res = r.search || { files: [], total: 0 };
    renderResults();
  }
  const visibleFiles = () => (SR.res && SR.res.files || []).map((f) => f.path).filter((p) => !SR.hidden.has(p));
  function renderResults() {
    const box = $("#sr-results"), sum = $("#sr-sum");
    if (!box) return;
    const r = SR.res;
    if (!r) { box.innerHTML = ""; sum.textContent = ""; return; }
    if (r.error) { box.innerHTML = ""; sum.innerHTML = `<span class="err-text">${esc(r.error)}</span>`; return; }
    const files = r.files.filter((f) => !SR.hidden.has(f.path));
    const n = files.reduce((a, f) => a + f.matches.length, 0);
    sum.textContent = !files.length ? t("sr_none") : t("sr_summary", { n, f: files.length }) + (r.truncated ? " · " + t("sr_truncated") : "");
    const rep = SR.showRep;
    box.innerHTML = files.map((f) => {
      const name = f.path.split("/").pop(), dir = f.path.slice(0, -name.length).replace(/\/$/, "");
      const rows = SR.closed.has(f.path) ? "" : f.matches.map((m) => {
        const hit = esc(m.text.slice(m.s, m.e));
        const pre = m.text.slice(0, m.s).trimStart();  // sidebar hẹp: giữ ít chữ trước chỗ khớp để thấy phần thay
        const before = pre.length > 14 ? "…" + pre.slice(-12) : pre;
        const mid = rep ? `<del>${hit}</del><ins>${esc(m.repl || "")}</ins>` : `<mark>${hit}</mark>`;
        return `<div class="sr-match" data-line="${m.line}" data-col="${m.col}" data-len="${m.len}" title="${m.line}:${m.col + 1}">
          ${esc(before)}${mid}${esc(m.text.slice(m.e))}</div>`;
      }).join("");
      return `<div class="sr-file" data-file="${esc(f.path)}">
        <div class="sr-file-head"><span class="sr-chev">${SR.closed.has(f.path) ? "▸" : "▾"}</span>${icon({ name })}
          <b class="tname">${esc(name)}</b><span class="muted small sr-dir">${esc(dir)}</span><span class="sr-n">${f.matches.length}</span>
          ${rep ? `<button class="sr-act" data-sr="file-replace" title="${esc(t("sr_replace_file"))}">⇄</button>` : ""}
          <button class="sr-act" data-sr="file-hide" title="${esc(t("sr_dismiss"))}">×</button></div>${rows}</div>`;
    }).join("");
  }
  async function replaceFiles(paths) {
    paths = (paths || []).filter(Boolean);
    if (!SR.query || !paths.length) return;
    const dirty = paths.filter((p) => (C.bufs.get(p) || {}).dirty || (p === C.cur && C.view && C.view.state.doc.toString() !== C.bufs.get(p).saved));
    if (dirty.length) toast(t("sr_dirty", { v: dirty.join(", ") }), "warn");
    paths = paths.filter((p) => !dirty.includes(p));
    if (!paths.length) return;
    const n = SR.res.files.filter((f) => paths.includes(f.path)).reduce((a, f) => a + f.matches.length, 0);
    if (!await confirmBox(t("sr_replace_all"), t("sr_confirm_q", { n, f: paths.length, r: SR.replace }), t("sr_replace_all"), false)) return;
    const r = await request("code_replace", { query: SR.query, replacement: SR.replace, case: SR.case, word: SR.word,
      regex: SR.regex, files: paths });
    const done = (r.replaced || {}).files || {};
    for (const p of Object.keys(done)) if (C.bufs.has(p)) await reload("disk", p);
    runSearch();
  }

  async function show() {
    layout();
    if (!C.timer) C.timer = setInterval(checkDisk, 2000);
    renderTree(); renderTabs(); renderStatus();
    try { await loadCM(); } catch (e) { toast(t("code_load_fail"), "error"); return; }
    if (!C.view) {
      newView(CM.EditorState.create({ doc: "", extensions: [CM.EditorState.readOnly.of(true), comps().theme.of(isDark() ? CM.oneDark : [])] }));
    }
    if (C.cur) C.view.focus(); else $("#code-filter").focus();
  }

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#code")) return;
    if (e.target.closest("#code-tree")) return onTree(e);
    const x = e.target.closest("[data-close]");
    if (x) { e.stopPropagation(); return close(x.dataset.close); }
    const tab = e.target.closest(".ctab");
    if (tab) return activate(tab.dataset.path);
    if (e.target.closest("[data-cact=vim]")) request("prefs", { vim: !vimOn() });
    const md = e.target.closest("[data-cact=md]");
    if (md) setMd(md.dataset.md);
  });
  document.addEventListener("keydown", (e) => {  // ⌘⇧F ở mọi tab: sang tab Code, mở ô tìm (lấy chữ đang chọn)
    if (!((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "f")) return;
    e.preventDefault(); e.stopPropagation();
    const sel = C.view ? C.view.state.sliceDoc(C.view.state.selection.main.from, C.view.state.selection.main.to) : "";
    (S.view === "code" ? Promise.resolve() : (setView("code"), show())).then(() => sidePane("search", sel));
  }, true);
  document.addEventListener("keydown", (e) => {
    if (S.view !== "code") return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "v" && isMd(C.cur && C.bufs.get(C.cur))) {
      e.preventDefault(); setMd(MD_MODES[(MD_MODES.indexOf(C.md) + 1) % MD_MODES.length]);
    }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "p") { e.preventDefault(); $("#code-filter").focus(); $("#code-filter").select(); }
  });
  window.addEventListener("beforeunload", (e) => {
    if ([...C.bufs.values()].some((b) => b.dirty || (b.path === C.cur && C.view && C.view.state.doc.toString() !== b.saved))) { e.preventDefault(); e.returnValue = ""; }
  });

  return {
    show, open, search: (q) => show().then(() => sidePane("search", q || "")),
    prefsChanged() { if (window.CM && C.view) { refreshConfig(); renderStatus(); } },
    unsaved: () => [...C.bufs.values()].filter((b) => b.dirty).map((b) => b.path),
  };
})();
