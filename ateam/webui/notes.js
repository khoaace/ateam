/* Mục 🗒 Ghi chú — ghi chú markdown của riêng dự án, lưu như to-do (ateam/notes.py, ngoài repo), tag dùng chung với
   To-do (TD ở todo.js). Ảnh chụp trạng thái chỉ có bản rút gọn (S.state.notes); mở ghi chú thì tải nội dung đầy đủ
   (op note/get). Gõ là tự lưu (~0,8 giây sau phím cuối) kèm `base` = updated đã đọc: tab / máy khác vừa sửa thì
   server trả note_conflict, ta hỏi Tải lại / Ghi đè. */
"use strict";

window.NotesView = (() => {
  const LS = "ateam-notes-view";
  let P = { mode: "split", tag: null };
  try { Object.assign(P, JSON.parse(localStorage.getItem(LS) || "{}")); } catch (e) { /* chặn lưu */ }
  const keep = () => { try { localStorage.setItem(LS, JSON.stringify(P)); } catch (e) { /* chặn lưu */ } };
  let cur = null, dirty = false, saving = false, timer = null, conflict = null, q = "", listSig = "", savedAt = 0, wantOpen = null;
  const list = () => (S.state && S.state.notes) || [];

  function layout() {
    if ($("#notes-list")) return;
    $("#notes").innerHTML = `
      <div class="nview">
        <div class="nlist">
          <div class="nlh"><div class="top"><span class="fsearch"><input class="field one" id="notes-q" placeholder="${esc(t("n_search"))}" autocomplete="off"><kbd>/</kbd></span>
            <button class="btn sm primary" id="notes-new">${esc(t("n_new"))}</button></div>
            <div class="trtags wrap" id="notes-tags"></div></div>
          <div class="nitems" id="notes-list"></div>
        </div>
        <div class="ned" id="notes-ed"></div>
      </div>`;
    $("#notes-new").addEventListener("click", () => newNote());
    $("#notes-q").addEventListener("input", (e) => { q = e.target.value; listSig = ""; renderList(); });
    $("#notes-q").addEventListener("keydown", (e) => { if (e.key === "Escape" && q) { e.stopPropagation(); e.target.value = q = ""; listSig = ""; renderList(); } });
    $("#notes-tags").addEventListener("click", (e) => {
      const c = e.target.closest("[data-tag]");
      if (!c) return;
      P.tag = c.dataset.tag === "" || +c.dataset.tag === P.tag ? null : +c.dataset.tag;
      keep(); listSig = ""; renderList();
    });
    $("#notes-list").addEventListener("click", (e) => { const r = e.target.closest("[data-nid]"); if (r) open(+r.dataset.nid); });
    const ed = $("#notes-ed");
    ed.addEventListener("input", (e) => {
      if (!cur) return;
      if (e.target.id === "note-title") cur.title = e.target.value;
      else if (e.target.id === "note-body") { cur.body = e.target.value; preview(); }
      else return;
      touch();
    });
    ed.addEventListener("click", edClick);
    ed.addEventListener("mouseup", selBar);
    ed.addEventListener("keyup", (e) => { if (e.target.id === "note-body" && e.shiftKey) selBar(e); });
    ed.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); flush(); }
      if (e.target.id === "note-title" && e.key === "Enter" && !e.isComposing) { e.preventDefault(); const b = $("#note-body"); if (b) b.focus(); }
    });
    ed.addEventListener("scroll", hideSel, true);
  }

  /* ---------------------------------------------------------------- danh sách bên trái */
  const tagRow = (ids) => TD.tagRowHtml(ids).replace(esc(t("add_tag")), esc(t("n_tag_add")));
  function title(n) { return n.title || t("n_untitled"); }
  function filtered() {
    const s = q.trim().toLowerCase();
    return list().filter((n) => (P.tag == null || (n.tags || []).includes(P.tag))
      && (!s || [n.title, n.snip, ...(n.tags || []).map((i) => (TD.tagById(i) || {}).name || "")].join(" ").toLowerCase().includes(s)));
  }
  function renderList() {
    const s = JSON.stringify([list(), TD.tags(), P.tag, q, cur && cur.id]);
    if (s === listSig) return;
    listSig = s;
    if (P.tag != null && !TD.tagById(P.tag)) P.tag = null;
    const used = new Set(list().flatMap((n) => n.tags || []));
    $("#notes-tags").innerHTML = `<span class="ttag all${P.tag == null ? " on" : ""}" data-tag="">${esc(t("tag_all"))} ${list().length}</span>`
      + TD.tags().filter((g) => used.has(g.id)).map((g) => TD.chip(g, { on: g.id === P.tag })).join("");
    const items = filtered(), pinned = items.filter((n) => n.pinned), rest = items.filter((n) => !n.pinned);
    const row = (n) => `<div class="ni${cur && cur.id === n.id ? " sel" : ""}" data-nid="${n.id}">
      <div class="nt">${n.pinned ? "<span>📌</span>" : ""}<span class="nn">${esc(title(n))}</span><span class="tm">${esc(TD.when(n.updated))}</span></div>
      ${n.snip ? `<div class="ns">${esc(n.snip)}</div>` : ""}${(n.tags || []).length ? `<div class="trtags">${n.tags.map((i) => TD.chip(i)).join("")}</div>` : ""}</div>`;
    $("#notes-list").innerHTML = !list().length ? `<div class="col-empty nempty">${esc(t("n_empty"))}</div>`
      : !items.length ? `<div class="col-empty nempty">${esc(t("n_nomatch"))}</div>`
        : (pinned.length ? `<div class="nsec">${esc(t("n_pinned"))}</div>${pinned.map(row).join("")}` : "")
          + (rest.length ? `${pinned.length ? `<div class="nsec">${esc(t("n_recent"))}</div>` : ""}${rest.map(row).join("")}` : "");
  }

  /* ---------------------------------------------------------------- trình soạn bên phải */
  function renderEd() {
    const ed = $("#notes-ed");
    hideSel();
    if (!cur) { ed.innerHTML = `<div class="nnone muted">${esc(t(list().length ? "n_none" : "n_empty"))}<button class="btn sm primary" data-ne="new">${esc(t("n_new"))}</button></div>`; return; }
    const m = P.mode;
    ed.innerHTML = `
      ${conflict ? `<div class="nconf">${esc(t("n_conflict"))}<span class="tsp"></span><button class="btn sm" data-ne="reload">${esc(t("n_reload"))}</button><button class="btn sm danger" data-ne="force">${esc(t("n_overwrite"))}</button></div>` : ""}
      <div class="neh"><div class="t"><input class="ntitle" id="note-title" value="${esc(cur.title || "")}" placeholder="${esc(t("n_title_ph"))}" maxlength="200">
        <button class="btn ghost sm" data-ne="pin">${esc(t(cur.pinned ? "n_unpin" : "n_pin"))}</button></div>
        <div class="bar"><span class="trtags wrap" id="note-tags">${tagRow(cur.tags || [])}</span><span class="tsp"></span>
          <span class="tseg">${["edit", "split", "view"].map((k) => `<button data-mode="${k}" class="${k === m ? "on" : ""}">${esc(t("md_" + k))}</button>`).join("")}</span></div></div>
      <div class="nsplit m-${m}">
        <textarea class="nsrc" id="note-body" placeholder="${esc(t("n_body_ph"))}" spellcheck="false">${esc(cur.body || "")}</textarea>
        <div class="nprev md" id="note-prev"></div></div>
      <div class="nfoot"><span id="note-state"></span><span>${esc(t("n_autosave"))}</span><span>·</span><span id="note-chars"></span><span class="tsp"></span>
        <span class="path">${esc(t("created_at", { t: TD.when(cur.created) }))} · ${esc(S.meta.notes_file || "")}</span>
        <button class="btn ghost sm danger" data-ne="del">${esc(t("todo_del"))}</button></div>`;
    TD.bindTagRow($("#note-tags"), () => cur.tags || [], (ids) => { cur.tags = ids; $("#note-tags").innerHTML = tagRow(ids); touch(true); });
    preview();
    state();
  }
  function preview() {
    const p = $("#note-prev");
    if (p && P.mode !== "edit") p.innerHTML = cur.body ? mdHtml(cur.body) : `<span class="muted">${esc(t("n_body_ph"))}</span>`;
    const c = $("#note-chars");
    if (c) c.textContent = t("n_chars", { n: (cur.body || "").length });
  }
  function state() {
    const s = $("#note-state");
    if (!s) return;
    s.className = dirty ? "unsaved" : "saved";
    s.textContent = saving ? t("n_saving") : dirty ? t("n_unsaved") : t("n_saved", { t: TD.when(savedAt || cur.updated) });
  }
  function edClick(e) {
    const b = e.target.closest("[data-ne], [data-mode], [data-sel]");
    if (!b) return;
    if (b.dataset.mode) { P.mode = b.dataset.mode; keep(); renderEd(); const x = $("#note-body"); if (x && P.mode !== "view") x.focus(); return; }
    if (b.dataset.sel) { selAction(b.dataset.sel); return; }
    const a = b.dataset.ne;
    if (a === "new") newNote();
    if (!cur) return;
    if (a === "pin") { send("note", { action: "pin", id: cur.id, on: !cur.pinned }); cur.pinned = !cur.pinned; renderEd(); }
    if (a === "del") {
      const n = cur;
      confirmBox(t("todo_del"), t("n_del_q", { v: title(n) }), t("todo_del")).then((ok) => {
        if (!ok) return;
        clearTimeout(timer); dirty = false;
        send("note", { action: "delete", id: n.id });
        if (cur && cur.id === n.id) { cur = null; renderEd(); }
      });
    }
    if (a === "reload") { conflict = null; dirty = false; load(cur.id); }
    if (a === "force") { conflict = null; save(true); }
  }

  /* ---------------------------------------------------------------- lưu: debounce, base, xung đột */
  function touch(now) {
    dirty = true;
    state();
    clearTimeout(timer);
    timer = setTimeout(() => save(false), now ? 0 : 800);
  }
  function save(force) {
    clearTimeout(timer);
    if (!cur || !dirty || conflict) return Promise.resolve();
    const n = cur, body = { action: "save", id: n.id, title: n.title || "", body: n.body || "", tags: n.tags || [], base: n.updated };
    if (force) body.force = true;
    saving = true; state();
    return request("note", body).then((r) => {
      saving = false;
      if (r.note_conflict) { conflict = r.note_conflict; renderEd(); return; }
      if (r.note && cur && cur.id === r.note.id) {
        cur.updated = r.note.updated; cur.tags = r.note.tags;
        savedAt = r.note.updated;
        // gõ tiếp trong lúc chờ: còn dirty nếu nội dung đã khác bản vừa lưu
        dirty = cur.title !== (r.note.title || "") || cur.body !== (r.note.body || "");
        if (dirty) touch();
        const tg = $("#note-tags");
        if (tg && !tg.contains(document.activeElement)) { tg.innerHTML = tagRow(cur.tags); }
      }
      state();
    });
  }
  function flush() { return dirty ? save(false) : Promise.resolve(); }
  function load(id) {
    return request("note", { action: "get", id }).then((r) => {
      if (!r.note) return;
      cur = r.note; dirty = false; conflict = null; savedAt = cur.updated;
      listSig = ""; renderList(); renderEd();
    });
  }
  async function open(id) {
    if (cur && cur.id === id) return;
    await flush();
    await load(id);
  }
  async function newNote(fields) {
    await flush();
    const r = await request("note", Object.assign({ action: "add", tags: P.tag != null ? [P.tag] : [] }, fields || {}));
    if (!r.note) return;
    cur = r.note; dirty = false; conflict = null; savedAt = cur.updated;
    if (P.mode === "view") { P.mode = "split"; keep(); }
    listSig = ""; renderList(); renderEd();
    const tt = $("#note-title");
    if (tt) tt.focus();
  }

  /* ---------------------------------------------------------------- bôi đen → to-do / giao trưởng nhóm */
  function selected() {
    const ta = $("#note-body");
    return ta && ta.selectionEnd > ta.selectionStart ? ta.value.slice(ta.selectionStart, ta.selectionEnd) : "";
  }
  function selBar(e) {
    const s = selected();
    hideSel();
    if (!s.trim() || !e || e.target.id !== "note-body") return;
    const ed = $("#notes-ed"), r = ed.getBoundingClientRect();
    const x = (e.clientX || r.left + 40) - r.left, y = (e.clientY || r.top + 120) - r.top;
    ed.insertAdjacentHTML("beforeend", `<div class="nselbar" style="left:${Math.max(8, Math.min(x - 40, r.width - 380))}px;top:${y + 14}px">
      <button class="btn sm primary" data-sel="todo">${esc(t("n_to_todo"))}</button><button class="btn sm ghost" data-sel="lead">${esc(t("to_lead"))}</button></div>`);
  }
  function hideSel() { const b = $(".nselbar"); if (b) b.remove(); }
  function selAction(kind) {
    const s = selected();
    hideSel();
    if (!s.trim() || !cur) return;
    if (kind === "lead") { send("submit", { text: s.trim() }); setView("board"); return; }
    const lines = s.split("\n").map((l) => l.replace(/^\s*([-*+]\s+(\[[ xX]\]\s+)?|\d+[.)]\s+|#+\s+)/, "").trim()).filter(Boolean).slice(0, 30);
    for (const l of lines) send("note", { action: "to_todo", id: cur.id, text: l });
  }

  function navCount() { const c = $("#count-notes"); if (c) c.textContent = list().length || ""; }
  function render() {
    navCount();
    if (S.view !== "notes") return;
    layout();
    renderList();
    if (wantOpen != null) { const id = wantOpen; wantOpen = null; open(id); return; }
    if (!cur && $("#notes-ed").childElementCount === 0) renderEd();
    if (cur) {
      // tab khác sửa ghi chú đang mở (không có thay đổi chưa lưu ở đây): tải lại bản mới
      const s = list().find((n) => n.id === cur.id);
      if (!s) { cur = null; renderEd(); return; }
      if (!dirty && !saving && !conflict && (s.updated || 0) > (cur.updated || 0) + 1e-6) load(cur.id);
      else if (s.pinned !== !!cur.pinned) { cur.pinned = s.pinned; const b = $('#notes-ed [data-ne="pin"]'); if (b) b.textContent = t(cur.pinned ? "n_unpin" : "n_pin"); }
    }
  }
  function escape() {
    if (TD.closePop()) return true;
    if ($(".nselbar")) { hideSel(); return true; }
    return false;
  }
  document.addEventListener("keydown", (e) => {
    if (S.view !== "notes" || topModal()) return;
    if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) && !e.metaKey && !e.ctrlKey) { e.preventDefault(); $("#notes-q").focus(); }
  });
  window.addEventListener("beforeunload", () => { if (dirty) save(false); });

  return {
    render, escape,
    show() { listSig = ""; render(); },
    hide() { flush(); },
    openNote(id) { wantOpen = id; if (S.view === "notes") render(); },
  };
})();
