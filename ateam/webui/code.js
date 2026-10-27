/* Tab Code — như tab 📝 Code của TUI: cây thư mục + lọc file, nhiều file mở (tối đa 10), editor CodeMirror 6
   (vendor/codemirror.js, nạp khi mở tab lần đầu) với phím vim (bật/tắt dùng chung TUI: /vim on|off), :w :q :wq
   :x :q! :e! :e <file> :bn :bp, Ctrl/⌘+S lưu. File đổi trên đĩa (agent sửa): chưa sửa → tự nạp lại, đang sửa → cảnh
   báo; lưu khi file đã đổi → hỏi ghi đè. File .md: Sửa / Chia đôi / Xem trước (mdHtml của app.js, Ctrl/⌘+Shift+V đổi
   chế độ, nhớ trong localStorage "ateam-md"). 🔍 Tìm & thay trong toàn dự án (⌘⇧F, như VS Code) ở sidebar — logic
   ở ateam/search.py. Chia đôi hai khung (⌘\\, mỗi file ở một khung), ảnh / PDF xem tại chỗ, ⌥Tab đổi file vừa dùng,
   Outline, palette # (symbol cả dự án), F12 / ⌘+click đi tới định nghĩa, ⇧⌥F format (ruff, prettier…), tự lưu.
   ✨ ⌘I: agent viết lại đoạn đang chọn → diff ngay trong editor (chấp nhận / bỏ từng đoạn); ⌘⇧E giải thích đoạn chọn.
   Tab Thay đổi (Source Control): file thay đổi theo git, bấm → diff hai cột (MergeView), sửa bên phải rồi ⌘S lưu. */
"use strict";

window.CodeView = (() => {
  const LIMIT = 10;
  const C = { panes: [{ view: null, cur: null }], act: 0, bufs: new Map(), order: [], mru: [], open: new Set([""]), tree: {}, filter: "",
    loading: null, comp: null, warned: {}, timer: null, ticks: 0, mode: "normal", wrap: false, restored: false,
    git: {}, gitDirs: new Set(), gitKey: "", head: undefined, runKey: "", side: "files", outKey: null };
  // C.view / C.cur = editor và file của khung đang dùng (chia đôi: 2 khung, mỗi khung một EditorView)
  for (const k of ["view", "cur"]) Object.defineProperty(C, k, { get: () => C.panes[C.act][k], set: (v) => { C.panes[C.act][k] = v; } });
  const HOSTS = ["#code-editor", "#code-editor2"];
  const paneOf = (path) => C.panes.findIndex((p) => p.cur === path);
  function liveState(b) {  // trạng thái mới nhất của buffer: đang hiện ở khung nào thì lấy từ editor đó
    const i = paneOf(b.path);
    return i >= 0 && C.panes[i].view && !b.media ? C.panes[i].view.state : b.state;
  }
  const liveText = (b) => { const st = liveState(b); return st ? st.doc.toString() : b.saved; };
  const KIND_ICON = { class: "◆", type: "◇", function: "ƒ", method: "ƒ", heading: "#" };
  const el = () => $("#code");
  async function getJSON(url) {  // mất kết nối / server lỗi → {error} thay vì lỗi không ai bắt
    try { return await (await fetch(url)).json(); } catch (e) { return { error: t("code_net_fail") }; }
  }

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
    if (!C.comp) C.comp = { vim: new CM.Compartment(), theme: new CM.Compartment(), lang: new CM.Compartment(), ro: new CM.Compartment(), wrap: new CM.Compartment(), merge: new CM.Compartment() };
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
      CM.keymap.of([CM.indentWithTab, { key: "Mod-s", run: () => { save(); return true; } },
        { key: "F12", run: (v) => { gotoDef(v); return true; } }, { key: "Shift-F12", run: (v) => { findRefs(v); return true; } }]),  // ⇧⌥F, ⌘\\: bắt ở document (vim nuốt phím ⌥)
      CM.EditorView.domEventHandlers({ mousedown: (e, v) => {  // ⌘+click (Ctrl+click): đi tới định nghĩa
        if (!(e.metaKey || e.ctrlKey) || e.button !== 0) return false;
        const pos = v.posAtCoords({ x: e.clientX, y: e.clientY });
        if (pos == null) return false;
        e.preventDefault(); gotoDef(v, pos);
        return true;
      } }),
      c.theme.of(isDark() ? CM.oneDark : []),
      c.lang.of(buf.lang ? buf.lang.support : []),
      c.ro.of(CM.EditorState.readOnly.of(!!buf.ro)),
      c.wrap.of(C.wrap ? CM.EditorView.lineWrapping : []),
      gitExt(),
      c.merge.of([]),  // ⌘I: unifiedMergeView so với trước khi AI sửa
      CM.EditorView.updateListener.of((u) => {
        if (AI.review && AI.review.view === u.view && u.transactions.length) {  // duyệt hết từng đoạn (nút ✓/✗ của merge) → xong
          const ch = CM.getChunks(u.state);
          if (ch && !ch.chunks.length) setTimeout(() => aiFinish(true), 0);
        }
        if (u.docChanged) { buf.dirty = u.state.doc.toString() !== buf.saved; renderTabs(); schedulePreview(); scheduleGit(); scheduleAutosave(buf); }
        if (u.docChanged || u.selectionSet) { renderStatus(); markOutline(); }
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
          <button class="side-tab on" data-side="files" title="${esc(t("sr_files"))}"><svg viewBox="0 0 24 24"><path d="M4 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2z"/></svg><span class="slbl">${esc(t("sr_files"))}</span></button>
          <button class="side-tab" data-side="search" title="${esc(t("sr_search"))} (⌘⇧F)"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/></svg><span class="slbl">${esc(t("sr_search"))}</span></button>
          <button class="side-tab" data-side="scm" title="${esc(t("scm_title"))}"><svg viewBox="0 0 24 24"><circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="8" r="2"/><path d="M6 8v8M18 10c0 4-6 3-11.5 6.5"/></svg><span class="slbl">${esc(t("scm_tab"))}</span><span class="scm-n" id="scm-n"></span></button>
          <button class="side-tab" data-side="outline" title="${esc(t("sr_outline"))}"><svg viewBox="0 0 24 24"><path d="M5 6h14M8 12h11M11 18h8"/></svg><span class="slbl">${esc(t("sr_outline"))}</span></button>
        </div>
        <div class="side-pane" id="side-files">
          <div class="code-filter-row"><input class="field one" id="code-filter" placeholder="${esc(t("code_filter"))}" autocomplete="off" spellcheck="false">
            <button class="icon-btn" id="code-new" title="${esc(t("pal_new"))}" aria-label="${esc(t("pal_new"))}">＋</button>
            <button class="icon-btn" id="code-new-dir" title="${esc(t("pal_new_dir"))}" aria-label="${esc(t("pal_new_dir"))}"><svg viewBox="0 0 24 24"><path d="M4 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2zM12 10v6M9 13h6"/></svg></button>
            <button class="icon-btn" id="code-refresh" title="${esc(t("code_refresh"))}" aria-label="${esc(t("code_refresh"))}">⟳</button></div>
          <div class="tree" id="code-tree"></div>
        </div>
        <div class="side-pane hidden" id="side-search">${searchPane()}</div>
        <div class="side-pane hidden" id="side-scm">${scmPane()}</div>
        <div class="side-pane hidden" id="side-outline"><div class="outline" id="code-outline"></div></div>
        <div class="code-resizer" id="code-resizer" role="separator" aria-orientation="vertical" tabindex="0" title="${esc(t("code_side_resize"))}"></div>
      </aside>
      <section class="code-main">
        <div class="code-tabs" id="code-tabs"></div>
        <nav class="code-crumbs hidden" id="code-crumbs"></nav>
        <div class="code-body" data-md="edit">
          <div class="code-host" id="code-editor"><div class="code-media"></div></div>
          <div class="code-host hidden" id="code-editor2"><div class="code-media"></div></div>
          <div class="code-preview md" id="code-preview"></div>
          <aside class="code-ai hidden" id="code-ai"></aside>
          <div class="code-diff" id="code-diff"><div class="diff-bar"></div><div class="diff-mv"></div></div>
        </div>
        <div class="code-status" id="code-status"></div>
      </section>`;
    bindSearch();
    $("#side-scm").addEventListener("click", scmClick);
    $("#side-scm").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && e.target.id === "scm-msg") { e.preventDefault(); scmCommit(); }
    });
    $("#code-diff").addEventListener("click", diffClick);
    $("#code-filter").addEventListener("input", (e) => { C.filter = e.target.value; renderTree(); });
    $("#code-new").addEventListener("click", () => runCmd("new_file"));
    $("#code-new-dir").addEventListener("click", () => runCmd("new_folder"));
    bindResizer();
    $("#code-refresh").addEventListener("click", () => refreshTree(true));
    $("#code-filter").addEventListener("keydown", (e) => {
      if (e.key === "Enter") { const f = $("#code-tree .tnode.file"); if (f) open(f.dataset.path); }
      if (e.key === "Escape" && C.filter) { e.target.value = C.filter = ""; renderTree(); e.stopPropagation(); }
    });
  }

  /* kéo mép phải cột bên để đổi độ rộng (nhớ theo trình duyệt); bấm đúp: về mặc định; ←/→ khi đang chọn mép */
  const SIDE_KEY = "ateam-code-side-w";
  function sideWidth(w) {
    if (w) w = Math.round(Math.min(Math.max(w, 160), Math.max(200, el().clientWidth - 320)));
    if (w) el().style.setProperty("--code-side-w", w + "px");
    else el().style.removeProperty("--code-side-w");
    try { if (w) localStorage.setItem(SIDE_KEY, String(w)); else localStorage.removeItem(SIDE_KEY); } catch (e) { /* trình duyệt chặn */ }
  }
  function bindResizer() {
    try { const w = +localStorage.getItem(SIDE_KEY); if (w) el().style.setProperty("--code-side-w", w + "px"); } catch (e) { /* trình duyệt chặn */ }
    const bar = $("#code-resizer"), side = $(".code-side");
    bar.addEventListener("pointerdown", (e) => {
      if (e.button) return;
      e.preventDefault();
      bar.setPointerCapture(e.pointerId);
      el().classList.add("resizing");
      const move = (ev) => sideWidth(ev.clientX - side.getBoundingClientRect().left);
      const up = () => {
        el().classList.remove("resizing");
        bar.removeEventListener("pointermove", move);
        bar.removeEventListener("pointerup", up);
        bar.removeEventListener("pointercancel", up);
      };
      bar.addEventListener("pointermove", move);
      bar.addEventListener("pointerup", up);
      bar.addEventListener("pointercancel", up);
    });
    bar.addEventListener("dblclick", () => sideWidth(0));
    bar.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      sideWidth(side.getBoundingClientRect().width + (e.key === "ArrowRight" ? 20 : -20));
    });
  }

  /* ---------------------------------------------------------------- cây thư mục */
  async function loadDir(dir, force) {
    if (C.tree[dir] && !force) return C.tree[dir];
    const r = await getJSON(`/api/tree?dir=${encodeURIComponent(dir)}${force ? "&refresh=1" : ""}`);
    C.tree[dir] = Array.isArray(r) ? r : C.tree[dir] || [];
    return C.tree[dir];
  }
  /* agent tạo / xoá file: tải lại các thư mục đang mở (vài giây một lần, ⟳ thì ngay), chỉ vẽ lại khi có đổi */
  async function refreshTree(force) {
    if (!force && (S.view !== "code" || document.hidden)) return;
    const dirs = [""].concat([...C.open].filter((d) => d && C.tree[d]));
    for (const d of Object.keys(C.tree)) if (!dirs.includes(d)) delete C.tree[d];  // thư mục đang đóng: nạp lại khi mở
    let changed = await loadGit();
    for (const [i, d] of dirs.entries()) {
      const r = await getJSON(`/api/tree?dir=${encodeURIComponent(d)}${i ? "" : force ? "&refresh=1" : "&age=5"}`);
      if (Array.isArray(r) && JSON.stringify(r) !== JSON.stringify(C.tree[d])) { C.tree[d] = r; changed = true; }
    }
    if (changed || force) renderTree();
  }
  function icon(n) {
    if (n.dir) return C.open.has(n.path) ? "▾" : "▸";
    const ext = n.name.includes(".") ? n.name.split(".").pop().toLowerCase() : "";
    return `<i class="fic e-${esc(ext)}">${esc(ext.slice(0, 3) || "·")}</i>`;
  }
  function gitTag(path, dir) {  // chữ trạng thái git bên phải tên (M sửa · U mới · A đã stage · C xung đột), thư mục: chấm
    if (dir) return C.gitDirs.has(path) ? [" g-dir", `<span class="gst">●</span>`] : ["", ""];
    const g = C.git[path];
    return g ? [" g-" + g, `<span class="gst" title="${esc(t("git_st_" + g))}">${esc(g)}</span>`] : ["", ""];
  }
  function nodes(dir, depth) {
    return (C.tree[dir] || []).map((n) => {
      const [gcls, gst] = gitTag(n.path, n.dir);
      const cls = (n.dir ? "dir" : "file") + (n.path === C.cur ? " on" : "") + (C.bufs.get(n.path) && C.bufs.get(n.path).dirty ? " dirty" : "") + gcls;
      const row = `<div class="tnode ${cls}" data-path="${esc(n.path)}" data-dir="${n.dir ? 1 : 0}" style="padding-left:${10 + depth * 14}px">
        <span class="ticon">${icon(n)}</span><span class="tname">${esc(n.name)}</span>${gst}</div>`;
      return row + (n.dir && C.open.has(n.path) ? nodes(n.path, depth + 1) : "");
    }).join("");
  }
  let filterSeq = 0;
  async function renderTree() {
    const box = $("#code-tree");
    if (!box) return;
    if (C.filter.trim()) {
      const seq = ++filterSeq;
      const r = await getJSON(`/api/files?n=80&q=${encodeURIComponent(C.filter.trim())}`);
      const files = Array.isArray(r) ? r : [];
      if (seq !== filterSeq) return;
      box.innerHTML = files.map((f) => {
        const dir = f.endsWith("/"), [gcls, gst] = gitTag(dir ? f.slice(0, -1) : f, dir);
        return `<div class="tnode ${dir ? "dir" : "file"}${f === C.cur ? " on" : ""}${gcls}" data-path="${esc(dir ? f.slice(0, -1) : f)}" data-dir="${dir ? 1 : 0}" data-flat="1">
          <span class="ticon">${dir ? "▸" : icon({ name: f })}</span><span class="tname">${esc(f)}</span>${gst}</div>`;
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

  /* ---------------------------------------------------------------- git: trạng thái file + dấu ở lề */
  async function loadGit() {  // true nếu trạng thái đổi (cần vẽ lại cây)
    const r = await getJSON("/api/git/status");
    if (r.is_repo === false) { C.gitRepo = false; C.gitGroups = null; renderScm(); }
    if (!r.groups) return false;
    C.gitRepo = r.is_repo !== false;
    const gk = JSON.stringify(r.groups);
    if (gk !== SC.key) { SC.key = gk; C.gitGroups = r.groups; renderScm(); }
    const st = {}, dirs = new Set(), g = r.groups;
    const put = (rows, fn) => (rows || []).forEach((f) => { if (!st[f.path]) st[f.path] = fn(f.icon); });
    put(g.c, () => "C"); put(g.w, (i) => i); put(g.s, (i) => i);
    for (const p of Object.keys(st)) for (let i = p.lastIndexOf("/"); i > 0; i = p.lastIndexOf("/", i - 1)) dirs.add(p.slice(0, i));
    const key = JSON.stringify(st), changed = key !== C.gitKey;
    C.git = st; C.gitDirs = dirs; C.gitKey = key;
    if (r.oid !== C.head) {  // commit mới (tab Git, agent): so lại với HEAD mới
      const first = C.head === undefined;
      C.head = r.oid;
      if (!first && window.CM) for (const p of C.panes) { const b = p.cur && C.bufs.get(p.cur); if (b && !b.media) loadBase(b); }
    }
    return changed;
  }
  let GIT = null;  // gutter + StateField dùng chung mọi buffer (tạo khi CodeMirror đã nạp)
  function gitExt() {
    if (!GIT) {
      const set = CM.StateEffect.define();
      class Mark extends CM.GutterMarker {
        constructor(kind) { super(); this.kind = kind; }
        eq(o) { return o.kind === this.kind; }
        toDOM() { const d = document.createElement("div"); d.className = "cm-git-" + this.kind; return d; }
      }
      const field = CM.StateField.define({
        create: () => CM.RangeSet.empty,
        update(v, tr) {
          for (const e of tr.effects) if (e.is(set)) return e.value;
          return tr.docChanged ? v.map(tr.changes) : v;
        },
      });
      const g = CM.gutter({
        class: "cm-git-gutter",
        markers: (view) => view.state.field(field),
        domEventHandlers: { mousedown: (view, line, ev) => hunkPop(view, line, ev) },
      });
      GIT = { set, marks: { add: new Mark("add"), mod: new Mark("mod"), del: new Mark("del") }, ext: [field, g] };
    }
    return GIT.ext;
  }
  function gitMarks(b, doc) {
    b.chunks = b.base ? CM.Chunk.build(b.base, doc) : [];
    const out = [];
    for (const ch of b.chunks) {
      if (ch.fromB === ch.toB) { out.push(GIT.marks.del.range(doc.lineAt(Math.min(ch.fromB, doc.length)).from)); continue; }
      const kind = ch.fromA === ch.toA ? "add" : "mod";
      for (let ln = doc.lineAt(ch.fromB).number, end = doc.lineAt(ch.endB).number; ln <= end; ln++) out.push(GIT.marks[kind].range(doc.line(ln).from));
    }
    return CM.RangeSet.of(out, true);
  }
  function applyGit(pi = C.act) {
    const p = C.panes[pi], b = p && p.cur && C.bufs.get(p.cur);
    if (b && !b.media && p.view && GIT) p.view.dispatch({ effects: GIT.set.of(gitMarks(b, p.view.state.doc)) });
  }
  let gitTimer = null;
  function scheduleGit() { clearTimeout(gitTimer); gitTimer = setTimeout(applyGit, 300); }
  async function loadBase(b) {  // nội dung ở HEAD; không phải repo / file bị .gitignore → không có dấu
    const r = await getJSON("/api/file/base?path=" + encodeURIComponent(b.path));
    if (r.error) return;
    b.base = r.repo && !r.ignored ? CM.Text.of(String(r.text || "").split("\n")) : null;
    if (paneOf(b.path) >= 0) applyGit(paneOf(b.path));
  }
  function hunkPop(view, line, ev) {  // bấm dấu ở lề: xem đoạn cũ, hoàn tác đoạn này
    const pane = C.panes.find((p) => p.view === view), b = pane && C.bufs.get(pane.cur), doc = view.state.doc;
    const ch = b && (b.chunks || []).find((c) => c.fromB === c.toB ? doc.lineAt(Math.min(c.fromB, doc.length)).from === line.from
      : line.from >= c.fromB && line.from <= c.endB);
    if (!ch) return false;
    const kind = ch.fromA === ch.toA ? "add" : ch.fromB === ch.toB ? "del" : "mod";
    const m = floating(ev.clientX + 12, ev.clientY - 8, "hunk-pop", `<div class="hunk-head"><span>${esc(t("git_hunk_" + kind))}</span>
        <button class="ctx-item" data-h="revert">↶ ${esc(t("git_hunk_revert"))}</button></div>
      ${kind === "add" ? "" : `<pre class="hunk-old">${esc(b.base.sliceString(ch.fromA, ch.endA))}</pre>`}`);
    m.addEventListener("click", (e) => {
      if (!e.target.closest("[data-h=revert]")) return;
      closeCtx();
      const d = view.state.doc;
      view.dispatch({ changes: { from: ch.fromB, to: Math.min(ch.toB, d.length), insert: b.base.sliceString(ch.fromA, Math.min(ch.toA, b.base.length)) } });
      view.focus();
    });
    return true;
  }

  /* ---------------------------------------------------------------- agent đang chạy (chế độ shared: sửa thẳng thư mục) */
  function runningAgents() {
    if ((S.meta.isolation || "shared") !== "shared" || !S.state) return [];
    return [...new Set(S.state.tasks.filter((x) => x.status === "running").map((x) => x.agent))];
  }
  function runChip() {
    const run = runningAgents();
    return run.length ? `<span class="chip run" title="${esc(t("code_running_tip"))}">⚙ ${esc(t("code_running", { v: run.join(", ") }))}</span>` : "";
  }

  /* ---------------------------------------------------------------- file đang mở */
  function renderTabs() {
    const box = $("#code-tabs");
    if (!box) return;
    box.innerHTML = C.order.map((p) => {
      const b = C.bufs.get(p);
      return `<div class="ctab${p === C.cur && !diffOn() ? " on" : C.panes[1] && paneOf(p) >= 0 ? " other" : ""}" data-path="${esc(p)}" title="${esc(p)}">
        <span class="tname">${esc(p.split("/").pop())}</span>${b.dirty ? `<span class="dot-dirty">●</span>` : ""}
        <button class="ctab-x" data-close="${esc(p)}">×</button></div>`;
    }).join("") + (C.diff ? `<div class="ctab diff${diffOn() ? " on" : ""}" data-diff="1" title="${esc(C.diff.path)}">
        <span class="tname">Δ ${esc(C.diff.path.split("/").pop())}</span><span class="tsub">${esc(t(C.diff.code === "s" ? "diff_tab_index" : "diff_tab_work"))}</span>
        ${C.diff.dirty ? `<span class="dot-dirty">●</span>` : ""}<button class="ctab-x" data-close-diff="1">×</button></div>` : "")
      || `<div class="muted small pad">${esc(t("code_hint"))}</div>`;
    $$("#code-tree .tnode.file").forEach((n) => n.classList.toggle("dirty", !!(C.bufs.get(n.dataset.path) || {}).dirty));
  }
  /* git blame dòng đang đứng (gitops.blame_line): bật ở palette → thanh trạng thái hiện "✎ tác giả, khi nào · commit" */
  C.blame = (() => { try { return localStorage.getItem("ateam-blame") === "1"; } catch (e) { return false; } })();
  const fmtBlame = (x) => typeof x === "string" ? { label: x, title: x }
    : x.uncommitted ? { label: "✎ " + x.author, title: x.author }
    : { label: `✎ ${x.author}, ${x.when}${x.summary ? " · " + x.summary.slice(0, 48) : ""}`, title: `${x.short} · ${x.author} · ${x.when}\n${x.summary}` };
  async function fetchBlame(b, line) {
    const text = liveText(b);
    const r = await request("code_blame", { path: b.path, line, text: text !== b.saved ? text : null });
    return r && r.blame != null ? fmtBlame(r.blame) : null;
  }
  async function blameNow(line) {
    const b = C.cur && C.bufs.get(C.cur);
    if (!b || b.media) return;
    const x = await fetchBlame(b, line);
    if (x) toast(x.title.replace("\n", " — "), "info");
  }
  function blameChip(b, line) {
    if (!C.blame || !b || b.media) return "";
    const k = `${b.path}:${line}:${b.dirty ? 1 : 0}`;
    if (C.blameKey !== k) {  // dừng con trỏ ~0,35 giây mới hỏi git
      C.blameKey = k; C.blameInfo = null; clearTimeout(C.blameTimer);
      C.blameTimer = setTimeout(async () => {
        const x = await fetchBlame(b, line);
        if (C.blameKey === k) { C.blameInfo = x; renderStatus(); }
      }, 350);
    }
    const x = C.blameInfo;
    return x ? `<span class="blame" title="${esc(x.title)}">${esc(x.label)}</span>` : "";
  }

  function renderStatus() {
    renderCrumbs();
    const box = $("#code-status");
    if (!box) return;
    const b = C.cur && C.bufs.get(C.cur);
    if (diffOn()) {
      const lang = CM.languageFor(C.diff.path);
      box.innerHTML = `<span>${esc(t(C.diff.ro ? "diff_ro_hint" : "diff_edit_hint"))}</span><span style="flex:1"></span>${runChip()}<span>${esc((lang && lang.name) || t("code_plain"))}</span>`;
      return;
    }
    if (!b) { box.innerHTML = `<span>${esc(vimOn() ? t("code_vim_hint") : t("code_novim_hint"))}</span>`; return; }
    if (b.media) {
      box.innerHTML = `<span style="flex:1"></span>${runChip()}
        <span>${esc(b.language || "")}</span><span class="mono">${esc(fmtSize(b.size))}</span>`;
      return;
    }
    const st = C.view.state, pos = st.selection.main.head, line = st.doc.lineAt(pos);
    const mode = vimOn() ? `<span class="vmode m-${esc(C.mode)}">${esc(C.mode.toUpperCase())}</span>` : "";
    box.innerHTML = `${mode}${b.dirty ? `<span class="dot-dirty">●</span>` : ""}${blameChip(b, line.number)}<span style="flex:1"></span>${runChip()}${S.prefs.autosave ? `<span class="chip" title="${esc(t("code_autosave_tip"))}">${esc(t("code_autosave_chip"))}</span>` : ""}${b.ro ? `<span class="chip warn">${esc(t("code_readonly", { v: b.note }))}</span>` : ""}
      ${b.newline === "\r\n" ? `<span class="chip">CRLF</span>` : ""}<span>${esc((b.lang && b.lang.name) || b.language || t("code_plain"))}</span>
      <span class="mono">${esc(t("code_pos", { r: line.number, n: st.doc.lines, c: pos - line.from + 1 }))}</span>
      ${isMd(b) && !C.panes[1] ? `<span class="seg" title="${esc(t("code_md_title"))}">${MD_MODES.map((m) =>
        `<button class="mini${m === C.md ? " on" : ""}" data-cact="md" data-md="${m}">${esc(t("code_md_" + m))}</button>`).join("")}</span>` : ""}
      ${C.git[b.path] && C.git[b.path] !== "C" ? `<button class="mini" data-cact="diff" title="${esc(t("scm_open_changes"))}">Δ ${esc(t("scm_changes_btn"))}</button>` : ""}
      <button class="mini" data-cact="vim" title="/vim on|off">vim ${vimOn() ? "✓" : "✗"}</button>`;
  }

  /* ---------------------------------------------------------------- breadcrumb kiểu VS Code: thư mục › file › symbol;
     bấm một đoạn → xổ danh sách cùng cấp (thư mục mở rộng tại chỗ, file thì mở), đoạn symbol → danh sách symbol */
  function symChain(syms, s) {  // symbol đang đứng + các symbol chứa nó (theo depth), ngoài cùng trước
    const out = s ? [s] : [];
    for (let k = s ? syms.indexOf(s) - 1 : -1; k >= 0 && out[0].depth > 0; k--) if (syms[k].depth < out[0].depth) out.unshift(syms[k]);
    return out;
  }
  function renderCrumbs() {
    const box = $("#code-crumbs");
    if (!box) return;
    const b = C.cur && C.bufs.get(C.cur);
    const chain = b && !b.media && C.view ? symChain(b.syms || [], symAt(b.syms, C.view.state.doc.lineAt(C.view.state.selection.main.head).number)) : [];
    const key = b ? b.path + "\n" + chain.map((s) => s.line).join(",") : "";
    if (key === C.crumbKey) return;  // gọi ở mỗi lần di con trỏ: chỉ vẽ lại khi đổi
    C.crumbKey = key;
    box.classList.toggle("hidden", !b);
    if (!b) { box.innerHTML = ""; return; }
    const parts = b.path.split("/"), sep = `<span class="bc-sep">›</span>`;
    box.innerHTML = parts.map((p, i) => `<button class="bc${i === parts.length - 1 ? " file" : ""}" data-bc="${i}" title="${esc(parts.slice(0, i + 1).join("/"))}">
        ${i === parts.length - 1 ? icon({ name: p }) : ""}<span>${esc(p)}</span></button>`).join(sep)
      + chain.map((s) => sep + `<button class="bc sym" data-bc="sym" data-line="${s.line}" title="${esc(t("pal_goto_symbol"))}">
        <span class="okind k-${esc(s.kind)}">${KIND_ICON[s.kind] || "•"}</span><span>${esc(s.name)}</span></button>`).join("");
  }
  async function crumbRows(dir, depth, on, exp) {
    let h = "";
    for (const n of await loadDir(dir)) {
      h += `<button class="ctx-item bc-item${n.path === on ? " on" : ""}" data-path="${esc(n.path)}" data-dir="${n.dir ? 1 : 0}" data-up="${esc(dir)}" style="padding-left:${8 + depth * 14}px">
        <span class="bc-ic">${n.dir ? (exp.has(n.path) ? "▾" : "▸") : icon(n)}</span><span class="tname">${esc(n.name)}</span></button>`;
      if (n.dir && exp.has(n.path)) h += await crumbRows(n.path, depth + 1, on, exp);
    }
    return h || `<div class="muted small pad">${esc(t("code_empty_dir"))}</div>`;
  }
  async function crumbPop(btn) {
    const which = btn.dataset.bc + ":" + (btn.dataset.line || "");
    if (C.crumbSkip === which) { C.crumbSkip = null; return; }  // bấm lại đoạn đang xổ: chỉ đóng
    const b = C.cur && C.bufs.get(C.cur);
    if (!b) return;
    const r = btn.getBoundingClientRect();
    if (btn.dataset.bc === "sym") {
      const syms = b.syms || [];
      const m = floating(r.left, r.bottom + 2, "ctx-menu bc-pop", syms.map((s) => `<button class="ctx-item bc-item${s.line === +btn.dataset.line ? " on" : ""}" data-line="${s.line}" style="padding-left:${8 + s.depth * 14}px">
          <span class="okind k-${esc(s.kind)}">${KIND_ICON[s.kind] || "•"}</span><span class="tname">${esc(s.name)}</span><span class="oline">${s.line}</span></button>`).join("")
        || `<div class="muted small pad">${esc(t("outline_empty"))}</div>`);
      m.dataset.bc = which;
      m.addEventListener("click", (e) => { const it = e.target.closest("[data-line]"); if (it) { closeCtx(); activate(C.cur, +it.dataset.line); } });
      focusOn(m);
      return;
    }
    const parts = b.path.split("/"), i = +btn.dataset.bc, on = parts.slice(0, i + 1).join("/"), dir = parts.slice(0, i).join("/");
    const exp = new Set();
    const m = floating(r.left, r.bottom + 2, "ctx-menu bc-pop", await crumbRows(dir, 0, on, exp));
    m.dataset.bc = which;
    const redraw = async (path) => {
      m.innerHTML = await crumbRows(dir, 0, on, exp);
      const it = $$(".bc-item", m).find((x) => x.dataset.path === path);
      if (it) it.focus();
    };
    const toggle = (it, want) => {
      const p = it.dataset.path;
      if (want === exp.has(p)) return;
      if (exp.has(p)) exp.delete(p); else exp.add(p);
      redraw(p);
    };
    m.addEventListener("click", (e) => {
      const it = e.target.closest(".bc-item");
      if (!it) return;
      if (it.dataset.dir === "1") return toggle(it, !exp.has(it.dataset.path));
      closeCtx();
      open(it.dataset.path);
    });
    m.addEventListener("keydown", (e) => {  // → mở thư mục, ← đóng thư mục (hoặc về thư mục cha)
      const it = e.target.closest(".bc-item");
      if (!it || (e.key !== "ArrowRight" && e.key !== "ArrowLeft")) return;
      e.preventDefault();
      if (e.key === "ArrowRight") { if (it.dataset.dir === "1") toggle(it, true); return; }
      if (it.dataset.dir === "1" && exp.has(it.dataset.path)) return toggle(it, false);
      if (exp.has(it.dataset.up)) { exp.delete(it.dataset.up); redraw(it.dataset.up); }
    });
    focusOn(m);
  }
  function focusOn(m) {  // focus mục đang chọn (không phải mục đầu như menu thường)
    const on = $(".bc-item.on", m);
    if (on) { on.focus(); on.scrollIntoView({ block: "center" }); }
  }
  document.addEventListener("mousedown", (e) => {  // đăng ký trước floating(): biết popup nào đang mở trước khi nó bị đóng
    const bc = e.target.closest && e.target.closest("#code-crumbs .bc");
    C.crumbSkip = bc && CTX && CTX.m.dataset.bc === bc.dataset.bc + ":" + (bc.dataset.line || "") ? CTX.m.dataset.bc : null;
  }, true);

  function fmtSize(n) { return n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : n >= 1024 ? Math.round(n / 1024) + " KB" : (n || 0) + " B"; }
  function showMedia(pi, b) {  // ảnh / PDF thay cho editor của khung pi
    const host = $(HOSTS[pi]), box = $(".code-media", host), src = `/api/raw?path=${encodeURIComponent(b.path)}&v=${b.mtime}`;
    host.classList.add("media");
    if (box.dataset.src === src) return;
    box.dataset.src = src;
    box.innerHTML = b.media === "pdf" ? `<iframe src="${esc(src)}" title="${esc(b.path)}"></iframe>` : `<img src="${esc(src)}" alt="${esc(b.path)}">`;
  }

  /* ---------------------------------------------------------------- xem trước markdown */
  const isMd = (b) => !!b && /\.(md|markdown|mdx)$/i.test(b.path);
  function mdMode() { return !C.panes[1] && isMd(C.cur && C.bufs.get(C.cur)) ? C.md : "edit"; }  // chia đôi editor: không xem trước
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
    const i = C.act;
    C.view = new CM.EditorView({ state, parent: $(HOSTS[i]) });
    C.view.scrollDOM.addEventListener("scroll", syncScroll);
    C.view.dom.addEventListener("focusin", () => setActive(i));
  }
  const blankState = () => CM.EditorState.create({ doc: "", extensions: [CM.EditorState.readOnly.of(true), comps().theme.of(isDark() ? CM.oneDark : [])] });
  function setActive(i) {  // chia đôi: khung đang dùng (bấm / focus vào khung)
    if (i === C.act || !C.panes[i]) return;
    C.act = i;
    HOSTS.forEach((h, k) => { const e = $(h); if (e) e.classList.toggle("act", k === i && !!C.panes[1]); });
    renderTabs(); renderStatus(); renderOutline();
    $$("#code-tree .tnode").forEach((n) => n.classList.toggle("on", n.dataset.path === C.cur));
  }

  function stash() {
    const b = C.cur && C.bufs.get(C.cur);
    if (b && C.view && !b.media) b.state = C.view.state;
  }
  function touchMru(p) { C.mru = [p].concat(C.mru.filter((x) => x !== p && C.bufs.has(x))); }
  function activate(path, line, col, len) {
    const b = C.bufs.get(path);
    if (!b) return;
    hideDiff();  // tab diff đang hiện: về editor
    const other = paneOf(path);
    if (other >= 0 && other !== C.act) setActive(other);  // mỗi file ở một khung: đang hiện ở khung kia thì sang đó
    if (AI.review && AI.review.view === C.view && C.cur !== path) aiFinish(true);  // rời file đang duyệt diff: giữ phần AI sửa
    stash();
    C.cur = path;
    touchMru(path);
    $(HOSTS[C.act]).classList.toggle("media", !!b.media);
    if (b.media) {
      showMedia(C.act, b);
      renderTabs(); renderStatus(); renderPreview(); renderOutline();
      revealInTree(path);
      persist();
      return;
    }
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
    renderTabs(); renderStatus(); renderPreview(); renderOutline();
    revealInTree(path);
    if (!b.syms) loadSyms(b);
    loadBase(b);
    persist();
  }
  /* chia đôi: khung phải (#code-editor2) có EditorView riêng; path = file mở ở khung phải (mặc định: file vừa dùng khác) */
  function split(path) {
    if (!window.CM || !C.view) return;
    if (C.panes[1]) {  // đã chia: sang khung kia (mở file ở đó nếu có)
      setActive(C.act ? 0 : 1);
      if (path) open(path); else if (C.view) C.view.focus();
      return;
    }
    const target = path || C.mru.find((p) => p !== C.cur && C.bufs.has(p));
    if (!target) { toast(t("split_need"), "info"); return; }
    if (target === C.panes[0].cur) {  // chuyển file đang xem sang phải, bên trái hiện file vừa dùng khác
      stash();
      C.panes[0].cur = null;
      const left = C.mru.find((p) => p !== target && C.bufs.has(p));
      if (left) activate(left); else { C.view.setState(blankState()); $(HOSTS[0]).classList.remove("media"); }
    }
    C.panes.push({ view: null, cur: null });
    $(HOSTS[1]).classList.remove("hidden");
    $(".code-body", el()).classList.add("split2");
    C.act = 1;
    newView(blankState());
    HOSTS.forEach((h, k) => $(h).classList.toggle("act", k === 1));
    if (C.bufs.has(target)) activate(target); else open(target);
    renderPreview();
  }
  function unsplit(keep = C.act) {  // gộp lại một khung, giữ file của khung `keep`
    if (!C.panes[1]) return;
    for (const p of C.panes) { const b = p.cur && C.bufs.get(p.cur); if (b && !b.media && p.view) b.state = p.view.state; }
    const keepPath = C.panes[keep].cur;
    C.panes[1].view.destroy();
    C.panes = [C.panes[0]];
    C.act = 0;
    const h2 = $(HOSTS[1]);
    h2.classList.add("hidden"); h2.classList.remove("media", "act");
    const m2 = $(".code-media", h2); m2.innerHTML = ""; delete m2.dataset.src;
    $(HOSTS[0]).classList.remove("act");
    $(".code-body", el()).classList.remove("split2");
    if (keep === 1) {
      C.panes[0].cur = null;
      if (keepPath) activate(keepPath); else { C.view.setState(blankState()); $(HOSTS[0]).classList.remove("media"); }
    }
    renderTabs(); renderStatus(); renderPreview(); renderOutline();
    if (C.view) C.view.focus();
    persist();
  }
  /* symbol (hàm, class, heading) của file: thanh "› đang ở đâu" và palette @ — tính lại khi mở / lưu */
  async function loadSyms(b) {
    const r = await getJSON("/api/symbols?path=" + encodeURIComponent(b.path));
    b.syms = Array.isArray(r) ? r : [];
    if (b.path === C.cur) { renderStatus(); renderOutline(); }
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
    const r = await getJSON("/api/file?path=" + encodeURIComponent(path));
    if (r.dir) { C.filter = path + "/"; $("#code-filter").value = C.filter; renderTree(); return; }
    if (r.error) { toast(r.error, "warn"); return; }
    addBuf(r);
    activate(r.path, line, col, len);
    if (r.new) toast(t("code_new_file"), "info");
  }
  function addBuf(r) {  // r: trả lời của /api/file
    const lang = r.media ? null : CM.languageFor(r.path);
    const b = r.media ? { path: r.path, media: r.media, size: r.size, mtime: r.mtime, language: r.language, saved: "", dirty: false, state: null, syms: [] } : { path: r.path, saved: r.text, mtime: r.mtime, ro: r.read_only, note: r.note, newline: r.newline, lang,
      language: r.language, dirty: false, state: null };
    C.bufs.set(r.path, b);
    C.order.push(r.path);
    while (C.order.length > LIMIT) {  // bỏ file cũ nhất chưa sửa
      const old = C.order.find((p) => !C.bufs.get(p).dirty && p !== r.path);
      if (!old) break;
      C.order.splice(C.order.indexOf(old), 1); C.bufs.delete(old);
    }
    return b;
  }
  /* nhớ file đang mở + vị trí con trỏ theo dự án (tải lại trang thì mở lại) */
  const sessKey = () => "ateam-code:" + (S.meta.root || "");
  function persist() {
    const pos = {};
    for (const p of C.order) {
      const st = liveState(C.bufs.get(p));
      if (st) pos[p] = st.selection.main.head;
    }
    const right = C.panes[1] ? C.panes[1].cur : null;
    try { localStorage.setItem(sessKey(), JSON.stringify({ order: C.order, cur: C.panes[0].cur, right, pos })); } catch (e) { /* chặn lưu */ }
  }
  async function restore() {
    let s = null;
    try { s = JSON.parse(localStorage.getItem(sessKey()) || "null"); } catch (e) { /* chặn đọc */ }
    if (!s || !Array.isArray(s.order)) return;
    const pos = s.pos || {};
    for (const p of s.order.slice(0, LIMIT)) {
      if (C.bufs.has(p)) continue;
      const r = await getJSON("/api/file?quiet=1&path=" + encodeURIComponent(p));
      if (r.error || r.dir || r.new) continue;  // file không còn
      const b = addBuf(r);
      if (!b.media) b.state = CM.EditorState.create({ doc: b.saved, extensions: extensions(b), selection: { anchor: Math.min(pos[p] || 0, b.saved.length) } });
    }
    const cur = C.bufs.has(s.cur) ? s.cur : C.order[0];
    if (!cur) return;
    activate(cur);
    const center = () => { if (!C.bufs.get(C.cur).media) C.view.dispatch({ effects: CM.EditorView.scrollIntoView(C.view.state.selection.main.head, { y: "center" }) }); };
    center();
    if (s.right && s.right !== cur && C.bufs.has(s.right)) { split(s.right); center(); setActive(0); }
  }
  async function close(path, force) {
    const b = path && C.bufs.get(path);
    if (!b) return;
    if (b.dirty && !force) {
      if (!await confirmBox(t("code_unsaved"), t("code_unsaved_q", { path }), t("code_discard"))) return;
    }
    const pi = paneOf(path);
    if (AI.review && AI.review.path === path) aiFinish(true);
    clearTimeout(b.asTimer);
    C.bufs.delete(path);
    C.mru = C.mru.filter((p) => p !== path);
    const i = C.order.indexOf(path);
    C.order.splice(i, 1);
    if (pi >= 0) {  // đang hiện ở khung pi: thay bằng file khác chưa hiện ở khung nào, hết thì gộp khung / để trống
      C.panes[pi].cur = null;
      const shown = C.panes.map((p) => p.cur);
      const next = C.mru.concat(C.order).find((p) => C.bufs.has(p) && !shown.includes(p));
      $(HOSTS[pi]).classList.remove("media");
      if (next) { C.act = pi; activate(next); }
      else if (C.panes[1]) unsplit(pi ? 0 : 1);
      else { C.view.setState(blankState()); renderStatus(); renderPreview(); renderOutline(); }
    }
    renderTabs();
    persist();
  }
  function cycle(d) {
    if (!C.order.length) return;
    const i = (C.order.indexOf(C.cur) + d + C.order.length) % C.order.length;
    activate(C.order[i]);
  }
  let saving = null;  // ⌘S / :w liên tiếp: chờ lần lưu đang chạy, không gửi hai lần (lần sau sẽ báo xung đột giả)
  function save(force = false) {
    if (!saving) saving = doSave(force).finally(() => { saving = null; });
    return saving;
  }
  async function doSave(force) {
    if (diffOn()) return saveDiff(force);
    const b = C.cur && C.bufs.get(C.cur);
    if (!b || b.media) return false;
    if (AI.review && AI.review.path === b.path) aiFinish(true);  // lưu = chấp nhận phần AI sửa
    if (S.prefs.fmt_save && !b.ro) await formatDoc(true);  // format khi lưu (không có công cụ: bỏ qua, im lặng)
    const ok = await saveBuf(b, liveText(b), force);
    renderTabs(); renderStatus();
    return ok;
  }
  /* ghi một buffer (đang xem hoặc ở tab khác); file đã đổi trên đĩa / chỉ đọc → hỏi ghi đè.
     auto (tự lưu): không toast, gặp xung đột thì tạm tắt tự lưu cho file này thay vì hỏi */
  async function saveBuf(b, text, force = false, auto = false) {
    b.saving = true;
    let r;
    try { r = await request("save", { path: b.path, text, mtime: b.mtime, force, quiet: auto }); } finally { b.saving = false; }
    const sv = r.save || {};
    if (auto && (sv.conflict || sv.read_only)) { b.noAuto = true; toast(t("code_autosave_off", { path: b.path }), "warn"); return false; }
    if (sv.conflict) {
      return await confirmBox(t("code_conflict"), t("code_conflict_q", { path: b.path }), t("code_overwrite")) && saveBuf(b, text, true);
    }
    if (sv.read_only) {
      return await confirmBox(t("code_readonly_title"), t("code_readonly_q", { v: b.note }), t("code_write_anyway")) && saveBuf(b, text, true);
    }
    if (!sv.mtime) return false;
    const st = liveState(b);
    b.saved = text; b.mtime = sv.mtime; b.dirty = !!st && st.doc.toString() !== text; C.warned[b.path] = 0;
    if (!auto) b.noAuto = false;
    loadSyms(b);
    loadGit().then((ch) => { if (ch) renderTree(); });
    return true;
  }
  async function reload(quiet, path) {
    const b = C.bufs.get(path || C.cur);
    if (!b) return;
    const r = await getJSON("/api/file?quiet=1&path=" + encodeURIComponent(b.path));
    const pi = paneOf(b.path);
    if (b.media) {  // ảnh / PDF đổi trên đĩa: hiện lại
      if (r.error) return;
      b.mtime = r.mtime; b.size = r.size;
      if (pi >= 0) { showMedia(pi, b); if (pi === C.act) renderStatus(); }
      return;
    }
    if (pi < 0) {  // file mở ở tab khác (vd vừa thay thế, agent sửa): nạp lại khi chuyển tới
      if (r.error) return;
      const head = b.state ? Math.min(b.state.selection.main.head, r.text.length) : 0;  // giữ chỗ con trỏ
      b.saved = r.text; b.mtime = r.mtime; b.dirty = false; b.syms = null;
      b.state = CM.EditorState.create({ doc: r.text, extensions: extensions(b), selection: { anchor: head } });
      renderTabs();
      return;
    }
    if (r.error) { toast(r.error, "warn"); return; }
    const v = C.panes[pi].view, head = v.state.selection.main.head;
    b.saved = r.text; b.mtime = r.mtime; b.dirty = false; b.ro = r.read_only; b.note = r.note; b.noAuto = false;
    b.state = CM.EditorState.create({ doc: r.text, extensions: extensions(b), selection: { anchor: Math.min(head, r.text.length) } });
    v.setState(b.state);
    if (pi === C.act) refreshConfig();
    applyGit(pi);
    renderTabs(); renderStatus(); renderPreview();
    const run = runningAgents();
    toast(quiet !== "disk" ? t("code_reloaded") : run.length ? t("code_reloaded_by", { v: run.join(", ") }) : t("code_reloaded_disk"), "info");
  }
  async function checkDisk() {  // agent sửa file đang mở (mọi tab, không chỉ file đang xem)
    if (S.view !== "code" || document.hidden || !C.order.length) return;
    const r = await getJSON("/api/file/stat?" + C.order.map((p) => "p=" + encodeURIComponent(p)).join("&"));
    for (const [path, mtime] of Object.entries(r.mtimes || {})) {
      const b = C.bufs.get(path);
      if (!b || !mtime || mtime === b.mtime || b.saving) continue;
      const cur = path === C.cur;
      const dirty = b.dirty || (!b.media && liveText(b) !== b.saved);
      if (!dirty) reload("disk", path);
      else if (C.warned[path] !== mtime) {
        C.warned[path] = mtime;
        toast(cur ? t("code_changed_dirty") : t("code_changed_tab", { path }), "warn");
      }
    }
  }
  function tick() {
    checkDisk();
    if (S.view === "code" && !document.hidden) checkDiff();
    if (++C.ticks % 3 === 0) refreshTree();
  }

  /* ---------------------------------------------------------------- Source Control: file thay đổi (sidebar) + diff hai cột
     Như VS Code: bấm file ở nhóm "Thay đổi" → so index ↔ thư mục làm việc, bên phải sửa được rồi ⌘S lưu; nhóm "Đã stage"
     → HEAD ↔ index (chỉ đọc). Diff là một tab riêng ở thanh tab (C.diff), thay chỗ editor khi đang xem. */
  const SC = { key: "", tree: (() => { try { return localStorage.getItem("ateam-scm-tree") === "1"; } catch (e) { return false; } })(),
    fold: new Set(), sel: null };
  const GROUPS = [["c", "git_conflicts"], ["s", "git_staged"], ["w", "git_changes"]];
  const scmCount = () => { const g = C.gitGroups || {}; return ["c", "s", "w"].reduce((n, k) => n + (g[k] || []).length, 0); };
  function scmPane() {
    return `<div class="scm-commit">
        <textarea class="field" id="scm-msg" rows="2" placeholder="${esc(t("scm_msg"))}" spellcheck="false"></textarea>
        <div class="scm-commit-row"><button class="btn sm primary" data-scm="commit" title="⌘Enter">✓ ${esc(t("scm_commit"))}</button>
          <button class="btn sm ghost" data-scm="ai" title="${esc(t("git_ai_agent"))}">✨ ${esc(t("git_ai"))}</button>
          <span style="flex:1"></span>
          <button class="icon-btn" data-scm="tree" title="${esc(t("git_tree_hint"))}" aria-label="${esc(t("git_tree_hint"))}">≡</button>
          <button class="icon-btn" data-scm="refresh" title="${esc(t("code_refresh"))}" aria-label="${esc(t("code_refresh"))}">⟳</button></div>
      </div>
      <div class="scm-list" id="scm-list"></div>`;
  }
  function scmRow(code, f, depth, label) {
    const name = label || f.path.split("/").pop(), dir = depth == null && f.path.includes("/") ? f.path.slice(0, f.path.lastIndexOf("/")) : "";
    const st = code === "c" ? "C" : f.icon, on = SC.sel && SC.sel.code === code && SC.sel.path === f.path;
    return `<div class="tnode file snode g-${esc(st)}${on ? " on" : ""}" data-code="${code}" data-path="${esc(f.path)}" title="${esc(f.path)}${f.orig ? " ← " + esc(f.orig) : ""}"
        style="padding-left:${10 + (depth || 0) * 14}px"><span class="ticon">${icon({ name })}</span><span class="tname${st === "D" ? " gone" : ""}">${esc(name)}</span>
      <span class="sdir">${esc(dir)}</span><span class="sacts">
        <button class="mini" data-sact="open" title="${esc(t("scm_open_file"))}">✎</button>
        ${code === "w" ? `<button class="mini" data-sact="discard" title="${esc(t("git_discard_title"))}">↺</button>` : ""}
        ${code !== "c" ? `<button class="mini" data-sact="${code === "s" ? "unstage" : "stage"}" title="${esc(t(code === "s" ? "scm_unstage" : "scm_stage"))}">${code === "s" ? "−" : "+"}</button>` : ""}
      </span><span class="gst" title="${esc(t("git_st_" + st))}">${esc(st)}</span></div>`;
  }
  function scmTree(code, files) {  // cây thư mục, chuỗi thư mục chỉ có một thư mục con gộp lại ("src/app")
    const root = { dirs: {}, files: [] };
    for (const f of files) {
      let n = root;
      for (const part of f.path.split("/").slice(0, -1)) n = n.dirs[part] || (n.dirs[part] = { dirs: {}, files: [] });
      n.files.push(f);
    }
    const out = [];
    const walk = (n, prefix, depth) => {
      for (const name of Object.keys(n.dirs).sort()) {
        let child = n.dirs[name], label = name, path = prefix + name;
        while (!child.files.length && Object.keys(child.dirs).length === 1) {
          const k = Object.keys(child.dirs)[0];
          label += "/" + k; path += "/" + k; child = child.dirs[k];
        }
        const fk = code + ":" + path;
        out.push(`<div class="tnode dir snode" data-code="${code}" data-dir="${esc(path)}" style="padding-left:${10 + depth * 14}px">
          <span class="ticon">${SC.fold.has(fk) ? "▸" : "▾"}</span><span class="tname">${esc(label)}</span><span class="sdir"></span><span class="sacts">
          ${code !== "c" ? `<button class="mini" data-sact="${code === "s" ? "unstage" : "stage"}" title="${esc(t(code === "s" ? "scm_unstage" : "scm_stage"))}">${code === "s" ? "−" : "+"}</button>` : ""}
          </span><span class="gst">●</span></div>`);
        if (!SC.fold.has(fk)) walk(child, path + "/", depth + 1);
      }
      for (const f of n.files.sort((a, b) => a.path.localeCompare(b.path))) out.push(scmRow(code, f, depth));
    };
    walk(root, "", 1);
    return out.join("");
  }
  function renderScm() {
    const n = scmCount(), badge = $("#scm-n");
    if (badge) badge.textContent = n ? String(n) : "";
    const box = $("#scm-list");
    if (!box || C.side !== "scm") return;
    $("[data-scm=tree]", el()).textContent = SC.tree ? "≡" : "▤";
    if (C.gitRepo === false) { box.innerHTML = `<div class="muted small pad">${esc(t("git_norepo"))}</div>`; return; }
    const g = C.gitGroups || {};
    box.innerHTML = GROUPS.filter(([k]) => (g[k] || []).length).map(([k, label]) => {
      const fold = SC.fold.has(k), list = g[k];
      return `<div class="scm-group" data-code="${k}"><span class="ticon">${fold ? "▸" : "▾"}</span><span class="tname">${esc(t(label))}</span>
          <span class="sacts">${k === "s" ? `<button class="mini" data-sact="unstage_all" title="${esc(t("git_unstage_all"))}">−</button>`
            : k === "w" ? `<button class="mini" data-sact="stage_all" title="${esc(t("git_stage_all"))}">+</button>` : ""}</span>
          <span class="scm-count">${list.length}</span></div>`
        + (fold ? "" : SC.tree ? scmTree(k, list) : list.map((f) => scmRow(k, f)).join(""));
    }).join("") || `<div class="muted small pad">✓ ${esc(t("git_clean"))}</div>`;
  }
  async function scmAct(action, data = {}) {
    const r = await request("git", Object.assign({ action }, data), t("git_working"));
    if (await loadGit()) renderTree();
    renderScm();
    return r;
  }
  async function scmCommit() {
    const box = $("#scm-msg"), msg = box.value.trim();
    if (!msg) { toast(t("git_need_msg"), "warn"); box.focus(); return; }
    const r = await scmAct("commit", { message: msg });
    if (r.committed) box.value = "";
  }
  async function scmClick(e) {
    const b = e.target.closest("[data-scm]");
    if (b) {
      const a = b.dataset.scm;
      if (a === "commit") return scmCommit();
      if (a === "refresh") return refreshTree(true).then(renderScm);
      if (a === "tree") {
        SC.tree = !SC.tree;
        try { localStorage.setItem("ateam-scm-tree", SC.tree ? "1" : "0"); } catch (err) { /* chặn lưu */ }
        return renderScm();
      }
      if (a === "ai") {
        const r = await request("git", { action: "ai_message" }, t("git_ai_wait", { lead: (S.state && S.state.lead) || "lead" }));
        if (r.git_msg) { $("#scm-msg").value = r.git_msg; $("#scm-msg").focus(); }
      }
      return;
    }
    const grp = e.target.closest(".scm-group"), row = e.target.closest(".snode"), act = e.target.closest("[data-sact]");
    const code = (grp || row || {}).dataset ? (grp || row).dataset.code : null;
    if (!code) return;
    const g = C.gitGroups || {};
    const paths = row && row.dataset.dir != null ? (g[code] || []).map((f) => f.path).filter((p) => p.startsWith(row.dataset.dir + "/"))
      : row ? [row.dataset.path] : (g[code] || []).map((f) => f.path);
    if (act) {
      e.stopPropagation();
      const a = act.dataset.sact;
      if (a === "open") return open(row.dataset.path);
      if (a === "stage" || a === "unstage") return scmAct(a, { paths });
      if (a === "stage_all") return scmAct("stage_all");
      if (a === "unstage_all") return scmAct("unstage_all");
      if (a === "discard") {
        const f = (g.w || []).find((x) => x.path === row.dataset.path);
        const q = f && f.icon === "U" ? t("git_discard_new", { path: f.path }) : t("git_discard_q", { path: row.dataset.path });
        if (!await confirmBox(t("git_discard_title"), q, t("git_discard_yes"))) return;
        await scmAct("discard", { path: row.dataset.path });
        if (C.diff && C.diff.path === row.dataset.path && !C.diff.dirty) reloadDiff();
        const ob = C.bufs.get(row.dataset.path);
        if (ob && !ob.dirty) reload(true, ob.path);
      }
      return;
    }
    if (grp) { if (SC.fold.has(code)) SC.fold.delete(code); else SC.fold.add(code); return renderScm(); }
    if (row.dataset.dir != null) {
      const fk = code + ":" + row.dataset.dir;
      if (SC.fold.has(fk)) SC.fold.delete(fk); else SC.fold.add(fk);
      return renderScm();
    }
    openDiff(row.dataset.path, code);
  }

  /* ---------------------------------------------------------------- diff hai cột (MergeView), bên phải sửa được */
  const diffOn = () => !!(C.diff && C.diff.on);
  const narrow = () => window.innerWidth < 800;  // điện thoại: diff một cột (unifiedMergeView)
  function groupOf(path) {  // nhóm của file trong Source Control: ưu tiên chưa stage (như mở từ cây / palette)
    const g = C.gitGroups || {};
    for (const k of ["c", "w", "s"]) { const f = (g[k] || []).find((x) => x.path === path); if (f) return [k, f]; }
    return [null, null];
  }
  function openChanges(path) {  // menu cây / palette "Xem thay đổi git": file có thay đổi → diff hai cột
    const [code] = groupOf(path);
    if (code === "w" || code === "s") return openDiff(path, code);
    DiffView.git({ kind: "file", path });
  }
  async function diffSides(path, code) {  // {left, right, saved, mtime, ro, label} hoặc {error}
    const f = ((C.gitGroups || {})[code] || []).find((x) => x.path === path);
    const gone = f && f.icon === "D";
    const base = await getJSON(`/api/file/base?path=${encodeURIComponent(path)}${code === "w" ? "&ref=index" : ""}`);
    if (base.error) return base;
    const left = String(base.text || "");
    if (code === "s") {
      const idx = gone ? { text: "" } : await getJSON(`/api/file/base?ref=index&path=${encodeURIComponent(path)}`);
      return { left, right: String(idx.text || ""), saved: null, mtime: 0, ro: true };
    }
    if (gone) return { left, right: "", saved: "", mtime: 0, ro: true };
    const b = C.bufs.get(path);
    if (b && !b.media) return { left, right: liveText(b), saved: b.saved, mtime: b.mtime, ro: false, roNote: b.ro ? b.note : "" };
    const r = await getJSON("/api/file?quiet=1&path=" + encodeURIComponent(path));
    if (r.error || r.media || r.dir) return { error: r.error || t("diff_binary") };
    return { left, right: r.text, saved: r.text, mtime: r.mtime, ro: false, roNote: r.read_only ? r.note : "" };
  }
  async function openDiff(path, code) {
    if (code === "c") return open(path);  // xung đột: sửa thẳng file (có <<<<<<< ===== >>>>>>>)
    await show();
    if (C.diff && C.diff.path === path && C.diff.code === code) { SC.sel = { code, path }; renderScm(); return showDiff(); }
    if (C.diff && C.diff.dirty
      && !await confirmBox(t("code_unsaved"), t("code_unsaved_q", { path: C.diff.path }), t("code_discard"))) return;
    const sides = await diffSides(path, code);
    if (sides.error) { toast(sides.error, "warn"); DiffView.git({ kind: code === "s" ? "staged" : "unstaged", path }); return; }
    SC.sel = { code, path };
    renderScm();
    dropDiff();
    C.diff = Object.assign({ path, code, on: true, dirty: false, inline: narrow(), collapse: false }, sides);
    buildDiff(sides.right);
    showDiff();
  }
  async function reloadDiff() {  // file / index đổi (agent sửa, stage…) khi diff chưa sửa dở: lấy lại hai bên
    const D = C.diff;
    if (!D || D.dirty) return;
    const sides = await diffSides(D.path, D.code);
    if (sides.error || C.diff !== D || D.dirty) return;
    Object.assign(D, sides);
    buildDiff(sides.right);
  }
  function diffExt(ro) {
    const D = C.diff, lang = CM.languageFor(D.path);
    return [
      ro ? [] : vimOn() ? CM.vim() : [],
      CM.basicSetup,
      isDark() ? CM.oneDark : [],
      lang ? lang.support : [],
      C.wrap ? CM.EditorView.lineWrapping : [],
      CM.EditorState.readOnly.of(ro),
      ro ? CM.EditorView.editable.of(false) : [],
    ];
  }
  const diffCfg = () => `${vimOn()}|${isDark()}|${C.wrap}`;
  function buildDiff(text) {  // dựng lại editor diff (mở, nạp lại, đổi một cột / hai cột, đổi sáng-tối)
    const D = C.diff;
    D.cfg = diffCfg();
    const host = $("#code-diff .diff-mv"), keep = D.mv ? D.mv.dom.scrollTop : D.edit ? D.edit.scrollDOM.scrollTop : 0;
    if (D.mv) D.mv.destroy(); else if (D.edit) D.edit.destroy();
    D.mv = D.edit = null;
    host.innerHTML = "";
    const ro = D.ro || !!D.roNote;
    const own = [
      CM.keymap.of([{ key: "Mod-s", run: () => { save(); return true; } },
        { key: "F7", run: (v) => CM.goToNextChunk(v) }, { key: "Shift-F7", run: (v) => CM.goToPreviousChunk(v) }]),
      CM.EditorView.updateListener.of((u) => { if (u.docChanged) { D.dirty = D.saved != null && u.state.doc.toString() !== D.saved; renderTabs(); renderDiffBar(); } }),
    ];
    const collapse = D.collapse ? { margin: 3, minSize: 6 } : undefined;
    if (D.inline) {
      D.edit = new CM.EditorView({ parent: host, state: CM.EditorState.create({ doc: text, extensions: [diffExt(D.ro), own,
        CM.unifiedMergeView({ original: D.left, mergeControls: false, highlightChanges: true, gutter: true, syntaxHighlightDeletions: true, collapseUnchanged: collapse })] }) });
    } else {
      D.mv = new CM.MergeView({
        a: { doc: D.left, extensions: diffExt(true) },
        b: { doc: text, extensions: [diffExt(D.ro), own] },
        parent: host, highlightChanges: true, gutter: true, collapseUnchanged: collapse,
        revertControls: D.ro ? undefined : "a-to-b",
        renderRevertControl: () => { const btn = document.createElement("button"); btn.textContent = "→"; btn.title = t("diff_revert_chunk"); return btn; },
      });
      D.edit = D.mv.b;
    }
    (D.mv ? D.mv.dom : D.edit.scrollDOM).scrollTop = keep;
    D.dirty = D.saved != null && text !== D.saved;
    renderDiffBar(); renderTabs();
  }
  function renderDiffBar() {
    const D = C.diff, bar = $("#code-diff .diff-bar");
    if (!D || !bar) return;
    const [, f] = groupOf(D.path), st = f ? f.icon : D.code === "s" ? "A" : "M";
    const ch = D.edit && CM.getChunks(D.edit.state), n = ch ? ch.chunks.length : 0;
    const dir = D.path.includes("/") ? D.path.slice(0, D.path.lastIndexOf("/")) : "";
    const lbl = (k) => `<span class="diff-side">${esc(t(k))}</span>`;
    bar.innerHTML = `<div class="diff-title"><span class="fstat s-${{ A: "done", U: "done", D: "failed", R: "draft" }[st] || "review"}">${esc(st)}</span>
        <b>${esc(D.path.split("/").pop())}</b><span class="muted small">${esc(dir)}</span>${D.dirty ? `<span class="dot-dirty">●</span>` : ""}
        <span class="muted small">${esc(n ? t("diff_n_changes", { n }) : t("diff_no_changes"))}</span>
        ${D.roNote ? `<span class="chip warn">${esc(t("code_readonly", { v: D.roNote }))}</span>` : ""}
        <span style="flex:1"></span>
        <button class="mini" data-dfa="prev" title="${esc(t("hunk_prev"))} (⇧F7)">↑</button>
        <button class="mini" data-dfa="next" title="${esc(t("hunk_next"))} (F7)">↓</button>
        <button class="mini${D.collapse ? " on" : ""}" data-dfa="collapse" title="${esc(t("diff_collapse"))}">⇕</button>
        <button class="mini${D.inline ? "" : " on"}" data-dfa="split" title="${esc(t("split_view"))}">⫴</button>
        ${D.code === "w" ? `<button class="mini" data-dfa="stage" title="${esc(t("scm_stage"))}">+</button>` : `<button class="mini" data-dfa="unstage" title="${esc(t("scm_unstage"))}">−</button>`}
        <button class="mini" data-dfa="open" title="${esc(t("scm_open_file"))}">✎</button>
        ${D.ro ? "" : `<button class="btn sm${D.dirty ? " primary" : " ghost"}" data-dfa="save" title="⌘S">${esc(t("diff_save"))}</button>`}</div>
      ${D.inline ? "" : `<div class="diff-heads">${lbl(D.code === "s" ? "diff_l_head" : "diff_l_index")}${lbl(D.code === "s" ? "diff_r_index" : "diff_r_work")}</div>`}`;
  }
  function showDiff() {
    if (!C.diff) return;
    stash();
    C.diff.on = true;
    el().classList.add("diffing");
    renderTabs(); renderStatus();
    if (C.diff.edit) { C.diff.edit.requestMeasure(); C.diff.edit.focus(); }
  }
  function hideDiff() {
    if (!diffOn()) return;
    C.diff.on = false;
    el().classList.remove("diffing");
    C.crumbKey = null;
    renderTabs(); renderStatus();
  }
  function dropDiff() {
    if (!C.diff) return;
    if (C.diff.mv) C.diff.mv.destroy(); else if (C.diff.edit) C.diff.edit.destroy();
    C.diff = null;
  }
  async function closeDiff(force) {
    const D = C.diff;
    if (!D) return;
    if (D.dirty && !force && !await confirmBox(t("code_unsaved"), t("code_unsaved_q", { path: D.path }), t("code_discard"))) return;
    const was = D.on;
    hideDiff(); dropDiff();
    SC.sel = null;
    renderScm(); renderTabs();
    if (was && C.view) C.view.focus();
  }
  async function diffOpenFile() {  // đang sửa dở: chữ chuyển sang editor (bỏ tab diff), không thì giữ tab diff
    const D = C.diff, line = D.edit ? D.edit.state.doc.lineAt(D.edit.state.selection.main.head).number : 1;
    const text = D.dirty ? D.edit.state.doc.toString() : null;
    await open(D.path, line);
    if (text == null || C.diff !== D) return;
    syncBuf(D.path, text, D.mtime, D.saved);
    dropDiff(); SC.sel = null; renderScm(); renderTabs();
  }
  async function saveDiff(force = false) {
    const D = C.diff;
    if (!D || D.ro) return false;
    const text = D.edit.state.doc.toString();
    const r = await request("save", { path: D.path, text, mtime: D.mtime, force });
    const sv = r.save || {};
    if (sv.conflict) return await confirmBox(t("code_conflict"), t("code_conflict_q", { path: D.path }), t("code_overwrite")) && saveDiff(true);
    if (sv.read_only) return await confirmBox(t("code_readonly_title"), t("code_readonly_q", { v: D.roNote }), t("code_write_anyway")) && saveDiff(true);
    if (!sv.mtime || C.diff !== D) return false;
    D.saved = text; D.mtime = sv.mtime; D.roNote = "";
    D.dirty = D.edit.state.doc.toString() !== text;
    syncBuf(D.path, text, sv.mtime);
    renderTabs(); renderDiffBar();
    loadGit().then((ch) => { if (ch) renderTree(); renderScm(); });
    return true;
  }
  /* file đang mở ở tab thường: theo nội dung vừa lưu ở diff (saved = bản trên đĩa nếu chữ chưa lưu) */
  function syncBuf(path, text, mtime, saved = text) {
    const b = C.bufs.get(path);
    if (!b || b.media) return;
    const pi = paneOf(path), st = liveState(b);
    b.saved = saved; b.mtime = mtime; b.syms = null; b.dirty = text !== saved; C.warned[path] = 0;
    b.state = CM.EditorState.create({ doc: text, extensions: extensions(b), selection: { anchor: Math.min(st ? st.selection.main.head : 0, text.length) } });
    if (pi >= 0) { C.panes[pi].view.setState(b.state); if (pi === C.act) refreshConfig(); applyGit(pi); }
    renderTabs();
  }
  async function checkDiff() {  // agent sửa file đang so: chưa sửa dở → nạp lại, đang sửa → cảnh báo một lần
    const D = C.diff;
    if (!D || D.ro || !D.mtime) return;
    const r = await getJSON("/api/file/stat?path=" + encodeURIComponent(D.path));
    if (!r.mtime || r.mtime === D.mtime || C.diff !== D) return;
    if (!D.dirty) { const b = C.bufs.get(D.path); if (b && !b.dirty) await reload(true, D.path); reloadDiff(); }
    else if (D.warned !== r.mtime) { D.warned = r.mtime; toast(t("code_changed_tab", { path: D.path }), "warn"); }
  }
  function diffClick(e) {
    const b = e.target.closest("[data-dfa]");
    if (!b || !C.diff) return;
    const D = C.diff, a = b.dataset.dfa;
    if (a === "next" || a === "prev") { (a === "next" ? CM.goToNextChunk : CM.goToPreviousChunk)(D.edit); D.edit.focus(); }
    if (a === "collapse") { D.collapse = !D.collapse; buildDiff(D.edit.state.doc.toString()); }
    if (a === "split") { D.inline = !D.inline; buildDiff(D.edit.state.doc.toString()); }
    if (a === "save") save();
    if (a === "open") diffOpenFile();
    if (a === "stage" || a === "unstage") {
      if (D.dirty) { toast(t("diff_save_first"), "warn"); return; }
      scmAct(a, { paths: [D.path] }).then(() => { const [code] = groupOf(D.path); if (code && code !== D.code && C.diff === D) openDiff(D.path, code); });
    }
  }

  /* ---------------------------------------------------------------- outline: symbol của file đang xem (sidebar) */
  function renderOutline() {
    const box = $("#code-outline");
    if (!box || C.side !== "outline") return;
    const b = C.cur && C.bufs.get(C.cur), syms = b && !b.media ? b.syms || [] : [];
    box.innerHTML = syms.length ? syms.map((s, k) => `<div class="onode" data-k="${k}" data-line="${s.line}" style="padding-left:${10 + s.depth * 12}px">
        <span class="okind k-${esc(s.kind)}">${KIND_ICON[s.kind] || "•"}</span><span class="tname">${esc(s.name)}</span><span class="oline">${s.line}</span></div>`).join("")
      : `<div class="muted small pad">${esc(b ? t("outline_empty") : t("pal_noopen"))}</div>`;
    C.outKey = null;
    markOutline();
  }
  function markOutline() {  // tô symbol đang đứng
    if (C.side !== "outline" || !C.view) return;
    const b = C.cur && C.bufs.get(C.cur);
    if (!b || b.media || !b.syms) return;
    const s = symAt(b.syms, C.view.state.doc.lineAt(C.view.state.selection.main.head).number), k = s ? b.syms.indexOf(s) : -1;
    if (k === C.outKey) return;
    C.outKey = k;
    $$("#code-outline .onode").forEach((n) => n.classList.toggle("on", +n.dataset.k === k));
    const on = $("#code-outline .onode.on");
    if (on) on.scrollIntoView({ block: "nearest" });
  }

  /* ---------------------------------------------------------------- ⌥Tab: đổi file theo thứ tự dùng gần nhất */
  const SW = { m: null, i: 0, list: [] };
  function switcher(step) {
    if (!SW.m) {
      SW.list = C.mru.filter((p) => C.bufs.has(p));
      if (SW.list.length < 2) return false;
      SW.i = 0;
      SW.m = document.createElement("div");
      SW.m.className = "mru-pop";
      SW.m.addEventListener("mousedown", (e) => { const r = e.target.closest("[data-k]"); if (r) { e.preventDefault(); SW.i = +r.dataset.k; switcherDone(true); } });
      document.body.appendChild(SW.m);
    }
    SW.i = (SW.i + step + SW.list.length) % SW.list.length;
    SW.m.innerHTML = `<div class="pal-head">${esc(t("mru_title"))}</div>` + SW.list.map((p, k) =>
      `<div class="pal-item${k === SW.i ? " on" : ""}" data-k="${k}">${icon({ name: p })} ${esc(p.split("/").pop())}<span class="pal-where">${esc(p)}</span></div>`).join("");
    return true;
  }
  function switcherDone(ok) {
    if (!SW.m) return;
    const p = SW.list[SW.i];
    SW.m.remove(); SW.m = null;
    if (ok && p) activate(p);
  }

  /* ---------------------------------------------------------------- đi tới định nghĩa (F12, ⌘+click) */
  /* language server (lsp.py) khi máy có pyright, typescript-language-server, gopls…: chính xác theo ngữ nghĩa;
     không có thì tìm theo tên như cũ. Kết quả và lỗi nằm trong payload (không toast mỗi lần bấm) */
  async function lspQuery(kind, view, pos) {
    const b = C.cur && C.bufs.get(C.cur), line = view.state.doc.lineAt(pos);
    const r = await request("code_lsp", { kind, path: b.path, text: view.state.doc.toString(), line: line.number, ch: pos - line.from },
      t("lsp_busy"));
    return (r && r.lsp) || { unavailable: true };
  }
  function locList(title, items) {  // nhiều kết quả: danh sách đường dẫn:dòng + dòng code, bấm để mở
    const m = openModal(`${modalHead(esc(title))}<div class="pal-list refs">${items.map((x, i) =>
      `<div class="pal-item${x.inside ? "" : " off"}" data-i="${i}" role="option"><span class="mono">${esc(x.path)}:${x.line}</span><span class="pal-desc">${esc(x.text)}</span></div>`).join("")}</div>`,
      { box: "md", cls: "palette" });
    m.addEventListener("click", (e) => {
      const r = e.target.closest("[data-i]"), x = r && items[+r.dataset.i];
      if (!x) return;
      if (!x.inside) { toast(t("lsp_outside", { v: `${x.path}:${x.line}` }), "info"); return; }
      closeModal(m); open(x.path, x.line);
    });
  }
  function wordAtPos(view, pos) {
    const w = view.state.wordAt(pos), word = w ? view.state.sliceDoc(w.from, w.to) : "";
    return /^[\p{L}_$][\p{L}\p{N}_$]*$/u.test(word) ? word : "";
  }
  async function findRefs(view = C.view, pos) {
    const b = C.cur && C.bufs.get(C.cur);
    if (!view || !b || b.media) return;
    if (pos == null) pos = view.state.selection.main.head;
    const word = wordAtPos(view, pos);
    if (!word) { toast(t("def_noword"), "info"); return; }
    const r = await lspQuery("references", view, pos);
    if (r.items && r.items.length) return locList(t("refs_title", { v: word, n: r.items.length }), r.items);
    if (r.items) { toast(t("refs_none", { v: word }), "info"); return; }
    if (r.error) toast(r.error, "warn");
    sidePane("search", word);  // không có language server: tìm chữ trong cả dự án
  }
  async function gotoDef(view = C.view, pos) {
    const b = C.cur && C.bufs.get(C.cur);
    if (!view || !b || b.media) return;
    if (pos == null) pos = view.state.selection.main.head;
    const word = wordAtPos(view, pos);
    if (!word) { toast(t("def_noword"), "info"); return; }
    const lsp = await lspQuery("definition", view, pos);
    if (lsp.items && lsp.items.length) {
      const inside = lsp.items.filter((x) => x.inside);
      if (inside.length === 1) return open(inside[0].path, inside[0].line);
      if (!inside.length) { toast(t("lsp_outside", { v: `${lsp.items[0].path}:${lsp.items[0].line}` }), "info"); return; }
      return locList(t("defs_title", { v: word }), lsp.items);
    }
    if (lsp.error && !lsp.unavailable) toast(lsp.error, "warn");
    const r = await getJSON("/api/wsymbols?exact=1&q=" + encodeURIComponent(word));
    const items = r.items || [], here = items.filter((x) => x.path === b.path);
    const hit = items.length === 1 ? items[0] : here.length === 1 ? here[0] : null;
    if (hit) return open(hit.path, hit.line);
    if (items.length) return palette("#" + word);
    toast(r.error || t("def_none", { v: word }), "info");
  }

  /* ---------------------------------------------------------------- format (công cụ của dự án) + tự lưu */
  async function formatDoc(quiet) {
    const b = C.cur && C.bufs.get(C.cur), view = C.view;
    if (!b || b.media || !view) return false;
    if (b.ro) { if (!quiet) toast(t("code_readonly", { v: b.note }), "warn"); return false; }
    const text = view.state.doc.toString();
    const r = await request("code_format", { path: b.path, text, quiet: !!quiet }, quiet ? "" : t("busy_formatting"));
    if (r.formatted == null || view.state.doc.toString() !== text) return false;  // lỗi (đã báo) / gõ tiếp trong lúc chờ
    const f = r.formatted;
    if (f === text) { if (!quiet) toast(t("fmt_same", { v: r.tool }), "info"); return true; }
    let a = 0, z = 0;  // chỉ thay đoạn khác nhau: con trỏ / cuộn giữ nguyên chỗ
    const n = Math.min(text.length, f.length);
    while (a < n && text[a] === f[a]) a++;
    while (z < n - a && text[text.length - 1 - z] === f[f.length - 1 - z]) z++;
    view.dispatch({ changes: { from: a, to: text.length - z, insert: f.slice(a, f.length - z) }, userEvent: "input.format" });
    if (!quiet) toast(t("fmt_done", { v: r.tool }), "ok");
    return true;
  }
  function scheduleAutosave(b) {
    if (!S.prefs.autosave || b.ro || b.noAuto || b.media) return;
    clearTimeout(b.asTimer);
    b.asTimer = setTimeout(async () => {
      if (!C.bufs.has(b.path) || b.saving) return;
      const text = liveText(b);
      if (text === b.saved) return;
      await saveBuf(b, text, false, true);
      renderTabs();
      if (b.path === C.cur) renderStatus();
    }, 1500);
  }

  /* ---------------------------------------------------------------- ✨ AI trong editor: ⌘I sửa inline, ⌘⇧E giải thích */
  const AI = { review: null, pending: false };
  function aiAgent() {  // agent lần trước chọn (nhớ trong trình duyệt), mặc định: agent viết commit / trưởng nhóm
    const names = (S.state ? S.state.agents : []).map((a) => a.name);
    let v = "";
    try { v = localStorage.getItem("ateam-ai-agent") || ""; } catch (e) { /* chặn đọc */ }
    return names.includes(v) ? v : (S.state && (names.includes(S.state.commit_agent) ? S.state.commit_agent : S.state.lead)) || names[0] || "";
  }
  function aiRange(view) {  // cả dòng của đoạn đang chọn (chưa chọn: dòng hiện tại)
    const st = view.state, s = st.selection.main;
    const end = !s.empty && s.to > s.from && st.doc.lineAt(s.to).from === s.to ? s.to - 1 : s.to;  // chọn tới đầu dòng sau: bỏ dòng đó
    const a = st.doc.lineAt(s.from), b = st.doc.lineAt(Math.max(s.from, end));
    return { from: a.from, to: b.to, label: a.number === b.number ? t("pal_line1", { a: a.number }) : t("pal_lines", { a: a.number, b: b.number }) };
  }
  function aiEdit() {
    const b = C.cur && C.bufs.get(C.cur), view = C.view;
    if (!b || b.media || !view) { toast(t("pal_noopen"), "info"); return; }
    if (b.ro) { toast(t("code_readonly", { v: b.note }), "warn"); return; }
    if (AI.pending) { toast(t("ai_wait"), "info"); return; }
    if (AI.review) aiFinish(true);
    const rg = aiRange(view), at = view.coordsAtPos(rg.from) || { left: 200, bottom: 200 };
    const agents = (S.state ? S.state.agents : []).map((a) => a.name), cur = aiAgent();
    const m = floating(at.left, at.bottom + 4, "ai-pop", `<div class="ai-head">✨ ${esc(t("ai_edit_title", { v: rg.label }))}</div>
      <textarea class="field ai-q" rows="2" placeholder="${esc(t("ai_edit_ph"))}" spellcheck="false"></textarea>
      <div class="ai-row"><select class="field ai-agent">${agents.map((n) => `<option${n === cur ? " selected" : ""}>${esc(n)}</option>`).join("")}</select>
        <span class="muted small">${esc(t("ai_hint"))}</span><button class="btn primary" data-ai="go">${esc(t("ai_go"))}</button></div>`);
    const q = $(".ai-q", m);
    const go = () => {
      const instruction = q.value.trim();
      if (!instruction) { q.focus(); return; }
      const agent = $(".ai-agent", m).value;
      try { localStorage.setItem("ateam-ai-agent", agent); } catch (e) { /* chặn lưu */ }
      closeCtx();
      aiRun(view, b, rg, instruction, agent);
    };
    q.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(); } });
    m.addEventListener("click", (e) => { if (e.target.closest("[data-ai=go]")) go(); });
    setTimeout(() => q.focus(), 0);
  }
  async function aiRun(view, b, rg, instruction, agent) {
    const text = view.state.doc.toString();
    AI.pending = true;
    let r;
    try {
      r = await request("code_ai", { mode: "edit", path: b.path, text, from: rg.from, to: rg.to, instruction, agent },
        t("ai_busy_edit", { agent }));
    } finally { AI.pending = false; }
    if (r.code == null) return;  // lỗi: server đã báo
    const pane = C.panes.find((p) => p.view === view);
    if (!pane || pane.cur !== b.path || view.state.doc.toString() !== text) { toast(t("ai_stale"), "warn"); return; }
    if (r.code === text.slice(rg.from, rg.to)) { toast(t("ai_same", { agent }), "info"); return; }
    const original = view.state.doc;
    view.dispatch({
      changes: { from: rg.from, to: rg.to, insert: r.code },
      effects: comps().merge.reconfigure(CM.unifiedMergeView({ original, mergeControls: chunkButton, highlightChanges: true, gutter: true, syntaxHighlightDeletions: true })),
      selection: { anchor: rg.from },  // bỏ vùng chọn: vim về normal mode, Esc là "Bỏ"
      scrollIntoView: true,
    });
    AI.review = { view, path: b.path, original, agent };
    const host = view.dom.parentElement, bar = document.createElement("div");
    bar.className = "ai-bar";
    bar.innerHTML = `<span>✨ ${esc(t("ai_review", { agent }))}</span>
      <button class="btn primary" data-ai="accept">${esc(t("ai_accept"))} <kbd>⌘⏎</kbd></button>
      <button class="btn ghost" data-ai="reject">${esc(t("ai_reject"))} <kbd>Esc</kbd></button>`;
    bar.addEventListener("click", (e) => { const a = e.target.closest("[data-ai]"); if (a) aiFinish(a.dataset.ai === "accept"); });
    host.appendChild(bar);
    AI.review.bar = bar;
    view.focus();
  }
  function chunkButton(type, action) {  // nút ✓ / ✗ của từng đoạn (chữ đã dịch thay cho Accept / Reject của CodeMirror)
    const b = document.createElement("button");
    b.name = type;
    b.textContent = t(type === "accept" ? "ai_accept" : "ai_reject");
    b.onmousedown = (e) => { e.preventDefault(); action(e); };
    return b;
  }
  function aiFinish(accept) {  // chấp nhận: giữ chữ mới (chưa lưu); bỏ: về như trước khi AI sửa
    const r = AI.review;
    if (!r) return;
    AI.review = null;
    r.bar.remove();
    const fx = comps().merge.reconfigure([]);
    if (accept) r.view.dispatch({ effects: fx });
    else r.view.dispatch({ changes: { from: 0, to: r.view.state.doc.length, insert: r.original }, effects: fx });
    if (!accept) toast(t("ai_rejected"), "info");
  }
  async function aiExplain() {
    const b = C.cur && C.bufs.get(C.cur), view = C.view;
    if (!b || b.media || !view) { toast(t("pal_noopen"), "info"); return; }
    let rg = aiRange(view);
    if (view.state.selection.main.empty) {  // chưa chọn: cả hàm / class đang đứng (tới symbol kế tiếp cùng cấp)
      const syms = b.syms || [], ln = view.state.doc.lineAt(view.state.selection.main.head).number, s = symAt(syms, ln);
      if (s) {
        const next = syms.find((x) => x.line > s.line && x.depth <= s.depth), doc = view.state.doc;
        const last = next ? next.line - 1 : doc.lines;
        rg = { from: doc.line(s.line).from, to: doc.line(Math.max(s.line, last)).to, label: s.name };
      }
    }
    const agent = aiAgent();
    const r = await request("code_ai", { mode: "explain", path: b.path, text: view.state.doc.toString(), from: rg.from, to: rg.to, agent },
      t("ai_busy_explain", { agent }));
    if (r.answer == null) return;
    const box = $("#code-ai");
    box.innerHTML = `<div class="ai-ph"><b>✨ ${esc(t("ai_explain_title", { agent, v: `${b.path.split("/").pop()} ${rg.label}` }))}</b>
      <button class="icon-btn" data-ai="copy" title="${esc(t("ai_copy"))}">⧉</button>
      <button class="icon-btn" data-ai="close" title="${esc(t("close"))}">×</button></div><div class="md ai-body">${mdHtml(r.answer)}</div>`;
    box._text = r.answer;
    box.classList.remove("hidden");
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
    C.side = which;
    $$(".side-tab").forEach((b) => b.classList.toggle("on", b.dataset.side === which));
    for (const k of ["files", "search", "scm", "outline"]) $("#side-" + k).classList.toggle("hidden", which !== k);
    el().classList.toggle("searching", which === "search");
    el().classList.remove("no-side");
    if (which === "outline") {
      const b = C.cur && C.bufs.get(C.cur);
      if (b && !b.syms) loadSyms(b);
      renderOutline();
      if (C.view) C.view.focus();
    } else if (which === "scm") {
      renderScm();
      loadGit().then((ch) => { if (ch) renderTree(); });
    } else if (which === "search") {
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
    const dirty = paths.filter((p) => (C.bufs.get(p) || {}).dirty || (C.bufs.has(p) && liveText(C.bufs.get(p)) !== C.bufs.get(p).saved));
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
  async function palette(prefix = "", stay = false) {  // stay: lệnh của app từ tab khác — không chuyển sang tab Code
    if (!stay) await show();
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
      const inCode = S.view === "code";
      const code = fuzzy((S.meta.code_commands || []).filter((c) => !c.file || (b && inCode)), text.slice(1), (c) => c.label + " " + c.kw)
        .map((c) => ({ html: `${esc(c.label)}${c.key ? `<span class="pal-key">${esc(c.key)}</span>` : ""}`, val: ["cmd", c.id] }));
      // lệnh /… của cả app (như gợi ý khi gõ "/"): chạy ngay, cần tham số thì điền vào ô nhập
      const app = fuzzy(S.meta.commands || [], text.slice(1), (c) => `/${c.name} ${c.desc}`)
        .map((c) => ({ html: `<b>/${esc(c.name)}</b>${c.args ? ` <span class="pal-dim">${esc(c.args)}</span>` : ""}<span class="pal-desc">${esc(c.desc)}</span>`,
          val: ["app", c.name, c.args.startsWith("<")] }));
      const out = inCode ? code.concat(app) : app.concat(code);
      return out.length ? out : [head(t("pal_nocmd"))];
    }
    if (text.startsWith("#")) {  // symbol trong cả dự án
      const q = text.slice(1).trim();
      if (!q) return [head(t("pal_ws_hint"))];
      const r = await getJSON("/api/wsymbols?q=" + encodeURIComponent(q));
      const out = (r.items || []).map((x) => ({
        html: `<span class="pal-dim">${KIND_ICON[x.kind] || "•"}</span> ${esc(x.name)}<span class="pal-where">${esc(x.path)}:${x.line}</span>`,
        val: ["sym", x.path, x.line] }));
      if (r.partial) out.push(head(t("pal_ws_partial")));
      return out.length ? out : [head(r.error || t("pal_ws_none"))];
    }
    if (!b && /^[@:/]/.test(text)) return [head(t("pal_noopen"))];
    if (b && b.media && /^[@:/]/.test(text)) return [head(t("pal_media"))];
    if (text.startsWith("@")) {
      const syms = b.syms || await loadSyms(b);
      const out = fuzzy(syms, text.slice(1), (s) => s.name).map((s) => ({
        html: `<span class="pal-dim">${"&nbsp;&nbsp;".repeat(s.depth)}${KIND_ICON[s.kind] || "•"}</span> ${esc(s.name)}<span class="pal-key">:${s.line}</span>`,
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
    else if (v[0] === "sym") open(v[1], v[2]);
    else if (v[0] === "cmd") { if (S.view !== "code") setView("code"); runCmd(v[1]); }
    else if (v[0] === "app") {  // lệnh /… của app: cần tham số → điền ô nhập; không thì chạy ngay
      if (v[2] || ["task", "chat", "handoff", "continue", "schedule"].includes(v[1])) { setView(S.view === "code" ? "board" : S.view); prefill(`/${v[1]} `); updateSuggest(); }
      else request("submit", { text: "/" + v[1] }, t("busy_cmd", { v: "/" + v[1] }));
    }
  }
  function selRef() {  // "@đường/dẫn (dòng a–b)" của đoạn đang chọn — để hỏi / giao việc cho agent
    const st = C.view.state, s = st.selection.main;
    if (s.empty || C.bufs.get(C.cur).media) return "@" + C.cur;
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
    let n = 0;
    const skipped = [];
    for (const b of C.bufs.values()) {
      const st = liveState(b);
      if (!st || b.media) continue;
      const text = st.doc.toString();
      if (text === b.saved) continue;
      if (await saveBuf(b, text)) n++; else skipped.push(b.path);
    }
    renderTabs(); renderStatus();
    if (skipped.length) toast(t("code_saved_some", { n, v: skipped.join(", ") }), "warn");
    else if (n > 1) toast(t("code_saved_all", { n }), "ok");
  }
  /* thao tác file — dùng chung cho palette (file đang mở) và menu chuột phải trên cây */
  async function copyText(v) {
    try { await navigator.clipboard.writeText(v); toast(t("pal_copied", { v }), "info"); } catch (e) { toast(v, "info"); }
  }
  async function newFile(dir) {
    const p = await inputBox(t("pal_new"), t("pal_path"), dir);
    if (p && (await request("file_new", { path: p })).ok) { C.tree = {}; await open(p); }
  }
  async function newFolder(dir) {
    const p = ((await inputBox(t("pal_new_dir"), t("pal_dir_path"), dir)) || "").replace(/\/+$/, "");
    if (!p || !(await request("dir_new", { path: p })).ok) return;
    C.tree = {};
    if (C.filter) { C.filter = ""; $("#code-filter").value = ""; }
    sidePane("files");
    await revealInTree(p + "/");
    const n = $(`#code-tree .tnode[data-path="${CSS.escape(p)}"]`);
    if (n) { n.classList.add("on"); n.scrollIntoView({ block: "nearest" }); }
  }
  const under = (path) => [...C.bufs.keys()].filter((p) => p === path || p.startsWith(path + "/"));
  async function renameFile(path, line) {
    const open_ = under(path);
    if (open_.some((p) => C.bufs.get(p).dirty)) { toast(t("pal_save_first"), "warn"); return; }
    const to = (await inputBox(t("pal_rename", { v: path }), t("pal_path"), path) || "").replace(/\/$/, "");
    if (!to || to === path) return;
    if (!(await request("file_rename", { path, to })).ok) return;
    const was = open_.includes(C.cur) ? C.cur : null;
    for (const p of open_) await close(p, true);
    C.tree = {};
    if (was) await open(to + was.slice(path.length), line); else renderTree();
  }
  async function deleteFile(path) {
    if (!await confirmBox(t("pal_delete"), t("pal_delete_q", { v: path }), t("pal_delete_yes"))) return;
    if ((await request("file_delete", { path })).ok) { if (C.bufs.has(path)) await close(path, true); C.tree = {}; renderTree(); }
  }
  function searchIn(dir) {  // 🔍 chỉ trong thư mục này
    sidePane("search");
    SR.include = dir; SR.more = true;
    $("#sr-inc").value = dir; $("#sr-filters").classList.remove("hidden");
    if (SR.query) runSearch();
  }

  /* khung nổi (menu chuột phải, đoạn thay đổi git): đóng khi bấm ra ngoài / Esc; ↑↓ đổi mục */
  let CTX = null;
  function closeCtx() {
    if (!CTX) return;
    CTX.m.remove();
    document.removeEventListener("mousedown", CTX.off, true);
    document.removeEventListener("keydown", CTX.off, true);
    CTX = null;
  }
  function floating(x, y, cls, html) {
    closeCtx();
    const m = document.createElement("div");
    m.className = cls;
    m.innerHTML = html;
    document.body.appendChild(m);
    const r = m.getBoundingClientRect();
    m.style.left = Math.max(4, Math.min(x, innerWidth - r.width - 4)) + "px";
    m.style.top = Math.max(4, Math.min(y, innerHeight - r.height - 4)) + "px";
    const off = (ev) => {
      if (ev.type === "mousedown") { if (!m.contains(ev.target)) closeCtx(); return; }
      const btns = $$(".ctx-item", m), i = btns.indexOf(document.activeElement);
      if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closeCtx(); }
      else if ((ev.key === "ArrowDown" || ev.key === "ArrowUp") && btns.length) {
        ev.preventDefault(); ev.stopPropagation();
        btns[(i + (ev.key === "ArrowDown" ? 1 : -1) + btns.length) % btns.length].focus();
      }
    };
    CTX = { m, off };
    document.addEventListener("mousedown", off, true);
    document.addEventListener("keydown", off, true);
    const first = $(".ctx-item", m);
    if (first) first.focus();
    return m;
  }
  /* menu chuột phải: items = [{label, run, key?, danger?} | "-"] */
  function ctxMenu(e, items) {
    e.preventDefault();
    const m = floating(e.clientX, e.clientY, "ctx-menu", items.map((it, i) => it === "-" ? `<div class="ctx-sep"></div>` :
      `<button class="ctx-item${it.danger ? " danger" : ""}" data-i="${i}" role="menuitem">${esc(it.label)}${it.key ? `<span class="pal-key">${esc(it.key)}</span>` : ""}</button>`).join(""));
    m.setAttribute("role", "menu");
    m.addEventListener("click", (ev) => { const b = ev.target.closest("[data-i]"); if (b) { closeCtx(); items[+b.dataset.i].run(); } });
  }
  function treeMenu(e, n) {
    const path = n.dataset.path;
    if (n.dataset.dir === "1") {
      return ctxMenu(e, [
        { label: t("ctx_new_here"), run: () => newFile(path + "/") },
        { label: t("ctx_new_dir_here"), run: () => newFolder(path + "/") },
        { label: t("ctx_search_in"), run: () => searchIn(path) },
        "-",
        { label: t("ctx_rename"), run: () => renameFile(path) },
        { label: t("ctx_copy_path"), run: () => copyText(path) },
      ]);
    }
    const dir = path.includes("/") ? path.slice(0, path.lastIndexOf("/") + 1) : "";
    ctxMenu(e, [
      { label: t("ctx_open"), run: () => open(path) },
      { label: t("ctx_open_right"), run: () => (C.bufs.has(path) ? split(path) : open(path).then(() => split(path))), key: "⌘\\" },
      { label: t("ctx_new_here"), run: () => newFile(dir) },
      { label: t("ctx_new_dir_here"), run: () => newFolder(dir) },
      "-",
      { label: t("ctx_rename"), run: () => renameFile(path) },
      { label: t("ctx_delete"), run: () => deleteFile(path), danger: true },
      "-",
      { label: t("ctx_copy_path"), run: () => copyText(path) },
      { label: t("ctx_git_diff"), run: () => openChanges(path) },
    ]);
  }

  async function runCmd(id) {
    const b = C.cur && C.bufs.get(C.cur);
    const line = b && !b.media && C.view ? C.view.state.doc.lineAt(C.view.state.selection.main.head).number : 1;
    const go = { quick_open: "", goto_symbol: "@", goto_line: ":", find: "/", workspace_symbol: "#" };
    if (id in go) return palette(go[id]);
    switch (id) {
      case "search_project": return sidePane("search", b && !b.media ? C.view.state.sliceDoc(C.view.state.selection.main.from, C.view.state.selection.main.to) : "");
      case "goto_definition": return gotoDef();
      case "find_references": return findRefs();
      case "blame_line": return blameNow(line);
      case "toggle_blame":
        C.blame = !C.blame; C.blameKey = "";
        try { localStorage.setItem("ateam-blame", C.blame ? "1" : "0"); } catch (e) { /* trình duyệt chặn */ }
        renderStatus(); return;
      case "recent_buffer": if (!switcher(1)) toast(t("mru_none"), "info"); return;
      case "format": return formatDoc(false);
      case "toggle_fmt_save": return request("prefs", { fmt_save: !S.prefs.fmt_save });
      case "toggle_autosave": return request("prefs", { autosave: !S.prefs.autosave });
      case "toggle_split": return C.panes[1] ? unsplit() : split();
      case "outline": return sidePane("outline");
      case "ai_edit": return aiEdit();
      case "ai_explain": return aiExplain();
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
      case "copy_path": return copyText(`${C.cur}:${line}`);
      case "git_diff": return openChanges(C.cur);
      case "open_vscode": return send("open_vscode", { path: C.cur, line });
      case "new_file": return newFile(b && C.cur.includes("/") ? C.cur.slice(0, C.cur.lastIndexOf("/") + 1) : "");
      case "new_folder": return newFolder(b && C.cur.includes("/") ? C.cur.slice(0, C.cur.lastIndexOf("/") + 1) : "");
      case "rename_file": return renameFile(C.cur, line);
      case "delete_file": return deleteFile(C.cur);
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
    if (!C.timer) C.timer = setInterval(tick, 2000);
    renderTree(); renderTabs(); renderStatus();
    loadGit().then((ch) => { if (ch) renderTree(); });
    try { await loadCM(); } catch (e) { toast(t("code_load_fail"), "error"); return; }
    if (!C.view) newView(blankState());
    if (!C.restored) { C.restored = true; await restore(); }
    if (C.cur && !C.bufs.get(C.cur).media) C.view.focus(); else if (!C.cur) $("#code-filter").focus();
  }

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#code")) return;
    if (e.target.closest("#code-tree")) return onTree(e);
    const on = e.target.closest("#code-outline .onode");
    if (on) return activate(C.cur, +on.dataset.line);
    const media = e.target.closest(".code-host");
    if (media && C.panes[1]) setActive(HOSTS.indexOf("#" + media.id));
    const bc = e.target.closest("#code-crumbs .bc");
    if (bc) return crumbPop(bc);
    const ai = e.target.closest("#code-ai [data-ai]");
    if (ai && ai.dataset.ai === "close") $("#code-ai").classList.add("hidden");
    if (ai && ai.dataset.ai === "copy") copyText($("#code-ai")._text || "");
    if (e.target.closest("[data-close-diff]")) { e.stopPropagation(); return closeDiff(); }
    if (e.target.closest(".ctab[data-diff]")) return showDiff();
    if (e.target.closest("[data-cact=diff]")) return openChanges(C.cur);
    const x = e.target.closest("[data-close]");
    if (x) { e.stopPropagation(); return close(x.dataset.close); }
    const tab = e.target.closest(".ctab");
    if (tab) return activate(tab.dataset.path);
    if (e.target.closest("[data-cact=vim]")) request("prefs", { vim: !vimOn() });
    const md = e.target.closest("[data-cact=md]");
    if (md) setMd(md.dataset.md);
  });
  document.addEventListener("contextmenu", (e) => {
    const n = e.target.closest && e.target.closest("#code-tree .tnode");
    if (n) treeMenu(e, n);
  });
  document.addEventListener("keydown", (e) => {  // ⌥Tab (giữ ⌥, Tab nữa để đổi, thả ⌥ để mở) — trình duyệt giữ Ctrl+Tab
    if (SW.m) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); switcherDone(false); return; }
      if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); switcherDone(true); return; }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); e.stopPropagation(); switcher(e.key === "ArrowDown" ? 1 : -1); return; }
    }
    if (S.view !== "code" || !e.altKey || e.key !== "Tab" || e.metaKey || e.ctrlKey) return;
    e.preventDefault(); e.stopPropagation();
    if (!switcher(e.shiftKey ? -1 : 1) && !SW.m) toast(t("mru_none"), "info");
  }, true);
  document.addEventListener("keyup", (e) => { if (SW.m && e.key === "Alt") switcherDone(true); }, true);
  document.addEventListener("keydown", (e) => {  // ⌘⇧F ở mọi tab: sang tab Code, mở ô tìm (lấy chữ đang chọn)
    if (!((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "f")) return;
    e.preventDefault(); e.stopPropagation();
    const sel = C.view ? C.view.state.sliceDoc(C.view.state.selection.main.from, C.view.state.selection.main.to) : "";
    (S.view === "code" ? Promise.resolve() : (setView("code"), show())).then(() => sidePane("search", sel));
  }, true);
  document.addEventListener("keydown", (e) => {  // ⇧⌥F format · ⌘\\ chia đôi — trước vim (vim nuốt phím ⌥ ở normal mode)
    if (S.view !== "code" || topModal()) return;
    const mod = (e.metaKey || e.ctrlKey) && !e.altKey;
    if (AI.review && mod && e.key === "Enter") { e.preventDefault(); e.stopPropagation(); aiFinish(true); return; }
    if (AI.review && e.key === "Escape" && !CTX && !(vimOn() && !/^normal/.test(C.mode))) {  // vim: Esc ra insert mode trước
      e.preventDefault(); e.stopPropagation(); aiFinish(false); return;
    }
    if (mod && !e.shiftKey && e.code === "KeyI") { e.preventDefault(); e.stopPropagation(); aiEdit(); return; }
    if (mod && e.shiftKey && e.code === "KeyE") { e.preventDefault(); e.stopPropagation(); aiExplain(); return; }
    if (e.altKey && e.shiftKey && !e.metaKey && !e.ctrlKey && e.code === "KeyF") { e.preventDefault(); e.stopPropagation(); formatDoc(false); }
    else if ((e.metaKey || e.ctrlKey) && !e.altKey && e.code === "Backslash") { e.preventDefault(); e.stopPropagation(); runCmd("toggle_split"); }
  }, true);
  document.addEventListener("keydown", (e) => {
    if (S.view !== "code") return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }  // cùng lúc với Mod-s của CodeMirror: save() chỉ chạy một lần
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "v" && isMd(C.cur && C.bufs.get(C.cur))) {
      e.preventDefault(); setMd(MD_MODES[(MD_MODES.indexOf(C.md) + 1) % MD_MODES.length]);
    }
  });
  document.addEventListener("keydown", (e) => {  // ⌘P mở nhanh file · ⌘⇧P / ⌘K lệnh · ⌘⇧O symbol — ở mọi tab, như VS Code
    if (!(e.metaKey || e.ctrlKey) || e.altKey) return;
    const k = e.key.toLowerCase();
    const cmds = (k === "p" && e.shiftKey) || (k === "k" && !e.shiftKey);
    if (k !== "p" && !(k === "o" && e.shiftKey) && !cmds) return;
    if (e.target.closest && e.target.closest(".xterm, .cm-editor") && k === "k") return;  // ⌘K của editor / terminal
    if (e.target.closest && e.target.closest(".xterm")) return;
    const top = topModal();
    if (top && top !== P.m) return;  // popup khác đang mở
    e.preventDefault(); e.stopPropagation();
    if (cmds) return palette(">", S.view !== "code");  // lệnh của cả app: mở ngay tại tab đang xem
    if (S.view !== "code") setView("code");
    palette(k === "o" ? "@" : "");
  }, true);
  window.addEventListener("beforeunload", (e) => {
    if (C.restored) persist();
    if (S.switching) return;  // đổi dự án (/open): đã hỏi bỏ thay đổi
    if ([...C.bufs.values()].some((b) => b.dirty || (!b.media && liveText(b) !== b.saved)) || (C.diff && C.diff.dirty)) { e.preventDefault(); e.returnValue = ""; }
  });

  return {
    show, open, palette, search: (q) => show().then(() => sidePane("search", q || "")),
    prefsChanged() {
      if (window.CM && C.view) { refreshConfig(); renderStatus(); }
      if (C.diff && C.diff.edit && C.diff.cfg !== diffCfg()) buildDiff(C.diff.edit.state.doc.toString());  // vim / sáng-tối đổi
    },
    stateChanged() {  // ảnh chụp trạng thái mới: chip "agent đang chạy"
      const k = runningAgents().join(",");
      if (k !== C.runKey) { C.runKey = k; renderStatus(); }
    },
    unsaved: () => [...C.bufs.values()].filter((b) => b.dirty).map((b) => b.path).concat(C.diff && C.diff.dirty ? [C.diff.path] : []),
  };
})();
