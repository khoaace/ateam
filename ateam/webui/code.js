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
    loading: null, comp: null, warned: {}, timer: null, mode: "normal", wrap: false };
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
    if (!C.comp) C.comp = { vim: new CM.Compartment(), theme: new CM.Compartment(), lang: new CM.Compartment(), ro: new CM.Compartment(), wrap: new CM.Compartment() };
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
      c.wrap.of(C.wrap ? CM.EditorView.lineWrapping : []),
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
          <div class="code-filter-row"><input class="field one" id="code-filter" placeholder="${esc(t("code_filter"))}" autocomplete="off" spellcheck="false">
            <button class="icon-btn" id="code-new" title="${esc(t("pal_new"))}" aria-label="${esc(t("pal_new"))}">＋</button></div>
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
    $("#code-new").addEventListener("click", () => runCmd("new_file"));
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
    const sym = symAt(b.syms, line.number);
    box.innerHTML = `${mode}<span class="mono">${esc(b.path)}</span>${b.dirty ? `<span class="dot-dirty">●</span>` : ""}
      ${sym ? `<span class="mono crumb">› ${esc(sym.name)}</span>` : ""}
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
    if (!b.syms) loadSyms(b);
  }
  /* symbol (hàm, class, heading) của file: thanh "› đang ở đâu" và palette @ — tính lại khi mở / lưu */
  async function loadSyms(b) {
    try { b.syms = await (await fetch("/api/symbols?path=" + encodeURIComponent(b.path))).json(); } catch (e) { b.syms = []; }
    if (b.path === C.cur) renderStatus();
    return b.syms;
  }
  function symAt(syms, line) {
    let best = null;
    for (const s of syms || []) { if (s.line > line) break; best = s; }
    return best;
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
    C.view.dispatch({ effects: [c.vim.reconfigure(vimOn() ? CM.vim() : []), c.theme.reconfigure(isDark() ? CM.oneDark : []),
      c.wrap.reconfigure(C.wrap ? CM.EditorView.lineWrapping : [])] });
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
      renderTabs(); renderStatus(); loadSyms(b);
      return true;
    }
    return false;
  }
  async function reload(quiet, path) {
    const b = C.bufs.get(path || C.cur);
    if (!b) return;
    if (b.path !== C.cur) {  // file mở ở tab khác (vd vừa thay thế): nạp lại khi chuyển tới
      const r = await (await fetch("/api/file?quiet=1&path=" + encodeURIComponent(b.path))).json();
      if (!r.error) { b.saved = r.text; b.mtime = r.mtime; b.dirty = false; b.state = null; renderTabs(); }
      return;
    }
    const r = await (await fetch("/api/file?quiet=1&path=" + encodeURIComponent(b.path))).json();
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
      regex: SR.regex, files: paths }, t("busy_replacing"));
    const done = (r.replaced || {}).files || {};
    for (const p of Object.keys(done)) if (C.bufs.has(p)) await reload("disk", p);
    runSearch();
  }

  /* ---------------------------------------------------------------- command palette (như VS Code, palette.py) */
  const P = { m: null, vals: [], sel: -1, recent: [], seq: 0 };
  function fuzzyScore(text, q) {  // như palette.fuzzy_score
    const s = text.toLowerCase(); q = q.toLowerCase().trim();
    if (!q) return 0;
    const at = s.indexOf(q);
    if (at >= 0) {  // khớp ở đầu một từ ("ask" trong "ask agent") hơn khớp giữa từ ("ask" trong "task")
      let w = -1;
      for (let i = at; i >= 0; i = s.indexOf(q, i + 1)) if (i === 0 || !/[\p{L}\p{N}_]/u.test(s[i - 1])) { w = i; break; }
      const pos = w >= 0 ? w : at;
      return 1000 - pos - (s.length >> 2) + (w >= 0 ? 300 : 0) + (pos === 0 ? 200 : 0);
    }
    let pos = -1, gaps = 0;
    for (const ch of q) { const n = s.indexOf(ch, pos + 1); if (n < 0) return null; gaps += n - pos - 1; pos = n; }
    return 500 - gaps - (s.length >> 2);
  }
  function fuzzy(items, q, key, limit = 200) {
    if (!q.trim()) return items.slice(0, limit);
    return items.map((it, i) => [fuzzyScore(key(it), q), i, it]).filter((x) => x[0] != null)
      .sort((a, b) => b[0] - a[0] || a[1] - b[1]).slice(0, limit).map((x) => x[2]);
  }
  async function palette(prefix = "") {
    await show();
    if (P.m && document.body.contains(P.m)) closeModal(P.m);
    const m = P.m = openModal(`<div class="pal"><input class="field one pal-q" autocomplete="off" spellcheck="false" placeholder="${esc(t("pal_ph"))}">
      <div class="pal-list" role="listbox"></div><div class="pal-foot">${esc(t("pal_foot"))}</div></div>`, { box: "md", cls: "palette" });
    const q = $(".pal-q", m);
    q.value = prefix;
    try { P.recent = await (await fetch("/api/recent")).json(); } catch (e) { P.recent = []; }
    q.addEventListener("input", () => refill(q.value));
    q.addEventListener("keydown", (e) => {
      const d = { ArrowDown: 1, ArrowUp: -1, PageDown: 10, PageUp: -10 }[e.key];
      if (d) { e.preventDefault(); move(d); }
      else if (e.key === "Enter") { e.preventDefault(); choose(P.sel); }
    });
    $(".pal-list", m).addEventListener("click", (e) => { const r = e.target.closest("[data-i]"); if (r) choose(+r.dataset.i); });
    refill(prefix);
    setTimeout(() => { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 40);
  }
  async function palItems(text) {
    const b = C.cur && C.bufs.get(C.cur), head = (s) => ({ head: s });
    if (text.startsWith(">")) {
      const out = fuzzy((S.meta.code_commands || []).filter((c) => !c.file || b), text.slice(1), (c) => c.label + " " + c.kw)
        .map((c) => ({ html: `${esc(c.label)}${c.key ? `<span class="pal-key">${esc(c.key)}</span>` : ""}`, val: ["cmd", c.id] }));
      return out.length ? out : [head(t("pal_nocmd"))];
    }
    if (!b && /^[@:/]/.test(text)) return [head(t("pal_noopen"))];
    if (text.startsWith("@")) {
      const syms = b.syms || await loadSyms(b);
      const icon = { class: "◆", type: "◇", function: "ƒ", method: "ƒ", heading: "#" };
      const out = fuzzy(syms, text.slice(1), (s) => s.name).map((s) => ({
        html: `<span class="pal-dim">${"&nbsp;&nbsp;".repeat(s.depth)}${icon[s.kind] || "•"}</span> ${esc(s.name)}<span class="pal-key">:${s.line}</span>`,
        val: ["line", s.line, 0] }));
      return out.length ? out : [head(t("pal_nosym"))];
    }
    const doc = C.view && C.view.state.doc;
    if (text.startsWith(":")) {
      const n = parseInt(text.slice(1).trim(), 10);
      return n >= 1 && n <= doc.lines ? [{ html: esc(t("pal_line", { v: n })), val: ["line", n, 0] }] : [head(t("pal_line_hint", { n: doc.lines }))];
    }
    if (text.startsWith("/")) {
      const q = text.slice(1).toLowerCase(), out = [];
      if (!q) return [head(t("pal_find_hint"))];
      for (let i = 1; i <= doc.lines && out.length < 300; i++) {
        const ln = doc.line(i).text, col = ln.toLowerCase().indexOf(q);
        if (col >= 0) out.push({ html: `<span class="pal-dim">${String(i).padStart(5, " ")}</span>  ${esc(ln.trim().slice(0, 140))}`, val: ["line", i, col] });
      }
      return out.length ? out : [head(t("pal_nofind", { v: text.slice(1) }))];
    }
    if (!text.trim()) {
      return (P.recent.length ? [head(t("pal_recent"))].concat(P.recent.map((f) => ({ html: esc(f), val: ["file", f] }))) : [])
        .concat([head(t("pal_hint"))]);
    }
    const hits = fuzzy(P.recent, text, (f) => f, 8);
    let files = [];
    try { files = await (await fetch(`/api/files?n=80&q=${encodeURIComponent(text.trim())}`)).json(); } catch (e) { /* mất kết nối */ }
    const out = hits.map((f) => ({ html: "🕘 " + esc(f), val: ["file", f] }))
      .concat(files.filter((f) => !f.endsWith("/") && !hits.includes(f)).map((f) => ({ html: esc(f), val: ["file", f] })));
    return out.length ? out : [head(t("pal_nofile"))];
  }
  async function refill(text) {
    const seq = ++P.seq, items = await palItems(text);
    if (seq !== P.seq || !P.m) return;
    P.vals = items.map((x) => x.val || null);
    P.sel = P.vals.findIndex((v) => v);
    $(".pal-list", P.m).innerHTML = items.map((x, i) => x.head ? `<div class="pal-head">${esc(x.head)}</div>`
      : `<div class="pal-item${i === P.sel ? " on" : ""}" data-i="${i}" role="option">${x.html}</div>`).join("");
  }
  function move(d) {
    let i = P.sel;
    const step = d > 0 ? 1 : -1;
    for (let k = 0; k < Math.abs(d); k++) {
      let j = i + step;
      while (j >= 0 && j < P.vals.length && !P.vals[j]) j += step;
      if (j < 0 || j >= P.vals.length) break;
      i = j;
    }
    if (i < 0 || !P.vals[i]) return;
    P.sel = i;
    $$(".pal-item", P.m).forEach((r) => r.classList.toggle("on", +r.dataset.i === i));
    const on = $(".pal-item.on", P.m);
    if (on) on.scrollIntoView({ block: "nearest" });
  }
  function choose(i) {
    const v = P.vals[i];
    if (!v) return;
    closeModal(P.m); P.m = null;
    if (v[0] === "file") open(v[1]);
    else if (v[0] === "line") activate(C.cur, v[1], v[2]);
    else if (v[0] === "cmd") runCmd(v[1]);
  }
  function selRef() {  // "@đường/dẫn (dòng a–b)" của đoạn đang chọn — để hỏi / giao việc cho agent
    const st = C.view.state, s = st.selection.main;
    if (s.empty) return "@" + C.cur;
    const a = st.doc.lineAt(s.from).number, b = st.doc.lineAt(s.to).number;
    return `@${C.cur} ` + (a === b ? t("pal_line1", { a }) : t("pal_lines", { a, b }));
  }
  function pickAgent() {
    return new Promise((resolve) => {
      let done = false;
      const names = (S.state ? S.state.agents : []).map((a) => a.name);
      const m = openModal(`${modalHead(esc(t("pal_choose_agent")))}<div class="modal-pad"><div class="picks">${names.map((n) =>
        `<button class="pick" data-v="${esc(n)}">${esc(n)}</button>`).join("")}</div></div>`,
        { box: "sm", onClose: () => { if (!done) { done = true; resolve(null); } } });
      m.addEventListener("click", (e) => { const b = e.target.closest(".pick"); if (b) { done = true; resolve(b.dataset.v); m.remove(); } });
    });
  }
  async function saveAll() {
    stash();
    for (const b of C.bufs.values()) {
      if (b.path === C.cur || !b.state) continue;
      const text = b.state.doc.toString();
      if (text === b.saved) continue;
      const r = await request("save", { path: b.path, text, mtime: b.mtime });
      if ((r.save || {}).mtime) { b.saved = text; b.mtime = r.save.mtime; b.dirty = false; }
    }
    if (C.cur) await save();
    renderTabs();
  }
  async function runCmd(id) {
    const b = C.cur && C.bufs.get(C.cur);
    const line = b && C.view ? C.view.state.doc.lineAt(C.view.state.selection.main.head).number : 1;
    const go = { quick_open: "", goto_symbol: "@", goto_line: ":", find: "/" };
    if (id in go) return palette(go[id]);
    switch (id) {
      case "search_project": return sidePane("search", b ? C.view.state.sliceDoc(C.view.state.selection.main.from, C.view.state.selection.main.to) : "");
      case "save": return save();
      case "save_all": return saveAll();
      case "close": return close(C.cur);
      case "next": return cycle(1);
      case "prev": return cycle(-1);
      case "toggle_files": return el().classList.toggle("no-side");
      case "toggle_vim": return request("prefs", { vim: !vimOn() });
      case "open_folder": return projectModal();
      case "toggle_wrap":
        C.wrap = !C.wrap; refreshConfig(); toast(t(C.wrap ? "pal_wrap_on" : "pal_wrap_off"), "info"); return;
      case "copy_path": {
        const v = `${C.cur}:${line}`;
        try { await navigator.clipboard.writeText(v); toast(t("pal_copied", { v }), "info"); } catch (e) { toast(v, "info"); }
        return;
      }
      case "git_diff": return DiffView.git({ kind: "file", path: C.cur });
      case "open_vscode": return send("open_vscode", { path: C.cur, line });
      case "new_file": {
        const dir = b && C.cur.includes("/") ? C.cur.slice(0, C.cur.lastIndexOf("/") + 1) : "";
        const p = await inputBox(t("pal_new"), t("pal_path"), dir);
        if (p && (await request("file_new", { path: p })).ok) { C.tree = {}; await open(p); }
        return;
      }
      case "rename_file": {
        if (b.dirty) { toast(t("pal_save_first"), "warn"); return; }
        const to = await inputBox(t("pal_rename", { v: C.cur }), t("pal_path"), C.cur);
        if (!to || to === C.cur) return;
        const old = C.cur;
        if ((await request("file_rename", { path: old, to })).ok) { await close(old, true); C.tree = {}; await open(to, line); }
        return;
      }
      case "delete_file": {
        const p = C.cur;
        if (!await confirmBox(t("pal_delete"), t("pal_delete_q", { v: p }), t("pal_delete_yes"))) return;
        if ((await request("file_delete", { path: p })).ok) { await close(p, true); C.tree = {}; renderTree(); }
        return;
      }
      case "ask_agent": case "task_agent": {
        const ref = selRef(), agent = await pickAgent();
        if (!agent) return;
        const q = await inputBox(t(id === "ask_agent" ? "pal_ask" : "pal_task", { agent, v: ref }), t("pal_ask_ph"));
        if (!q) return;
        const msg = `${ref}: ${q}`;
        if (id === "ask_agent") { if (send("chat", { agent, text: msg })) toast(t("pal_asked", { agent }), "info"); }
        else if (send("submit", { text: `/task ${agent} ${msg}` })) toast(t("pal_assigned", { agent, v: msg.slice(0, 80) }), "info");
        return;
      }
    }
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
  });
  document.addEventListener("keydown", (e) => {  // ⌘P mở nhanh file · ⌘⇧P lệnh · ⌘⇧O symbol — ở mọi tab, như VS Code
    if (!(e.metaKey || e.ctrlKey) || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k !== "p" && !(k === "o" && e.shiftKey)) return;
    if (e.target.closest && e.target.closest(".xterm")) return;
    const top = topModal();
    if (top && top !== P.m) return;  // popup khác đang mở
    e.preventDefault(); e.stopPropagation();
    if (S.view !== "code") setView("code");
    palette(k === "o" ? "@" : e.shiftKey ? ">" : "");
  }, true);
  window.addEventListener("beforeunload", (e) => {
    if (S.switching) return;  // đổi dự án (/open): đã hỏi bỏ thay đổi
    if ([...C.bufs.values()].some((b) => b.dirty || (b.path === C.cur && C.view && C.view.state.doc.toString() !== b.saved))) { e.preventDefault(); e.returnValue = ""; }
  });

  return {
    show, open, palette, search: (q) => show().then(() => sidePane("search", q || "")),
    prefsChanged() { if (window.CM && C.view) { refreshConfig(); renderStatus(); } },
    unsaved: () => [...C.bufs.values()].filter((b) => b.dirty).map((b) => b.path),
  };
})();
