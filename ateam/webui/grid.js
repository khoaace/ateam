/* Mục 🔲 Lưới — mỗi ô là CLI thật của một agent (pty ở server, xterm.js ở đây). Server giữ bố cục + CLI
   (ateam/grid.py, WebApp.grid_op): đóng tab không dừng CLI; mở lại tab thì grid_attach nhận bố cục và output gần
   nhất của từng ô. Kéo ⠿ tiêu đề ô thả lên ô khác (trên/dưới/trái/phải/giữa = đổi chỗ), kéo khe để đổi kích thước,
   đúp-click khe để chia đều. */
"use strict";

window.GridView = (() => {
  const G = { state: null, terms: {}, holders: {}, fits: {}, attached: false, focus: null, zoom: null, drag: null, sig: "", pending: {} };
  const EDGE = 0.25;
  const el = () => $("#grid");
  const cells = () => (G.state ? G.state.cols.flatMap((c) => c.cells) : []);
  const cellById = (id) => cells().find((c) => c.id === id);
  const PRESET_ICONS = {
    stack: '<rect x="2" y="2.5" width="12" height="11" rx="1"/><path d="M2 8h12"/>',
    cols2: '<rect x="2" y="2.5" width="12" height="11" rx="1"/><path d="M8 2.5v11"/>',
    auto: '<rect x="2" y="2.5" width="12" height="11" rx="1"/><path d="M8 2.5v11M2 8h12"/>',
    lead: '<rect x="2" y="2.5" width="12" height="11" rx="1"/><path d="M7 2.5v11M7 8h7M10.5 2.5v5.5"/>',
    row: '<rect x="2" y="2.5" width="12" height="11" rx="1"/><path d="M5.5 2.5v11M9 2.5v11M12 2.5v11"/>',
  };

  /* ---------------------------------------------------------------- kết nối */
  async function show() {
    layout();
    if (!G.attached) {
      try { await loadTerm(); } catch (e) { toast(t("disconnected"), "error"); return; }
      if (send("grid_attach")) G.attached = true;
    } else render();
    setTimeout(() => focusCell(G.focus), 30);
  }
  function reset() {  // mất kết nối: lần mở sau gắn lại (server phát lại output)
    G.attached = false;
    if (S.view === "grid") show();
  }
  function onState(m) {
    G.state = m;
    const ids = new Set(cells().map((c) => c.id));
    for (const id of Object.keys(G.terms)) if (!ids.has(id)) dropTerm(id);
    if (G.focus && !ids.has(G.focus)) G.focus = null;
    if (G.zoom && !ids.has(G.zoom)) G.zoom = null;
    const n = $("#count-grid");
    if (n) n.textContent = ids.size || "";
    if (S.view === "grid") render();
  }
  function bytes(b64) {
    const bin = atob(b64), out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
  function onData(m) {
    const term = G.terms[m.id];
    if (!term) { (G.pending[m.id] = G.pending[m.id] || []).push(m); return; }
    if (m.replay) term.reset();
    term.write(bytes(m.data));
  }
  function onExit(m) {
    const term = G.terms[m.id];
    if (term) term.write(`\r\n\x1b[2m[${t("g_exit_msg", { rc: m.rc })}]\x1b[0m\r\n`);
  }

  /* ---------------------------------------------------------------- terminal */
  function termFor(id) {
    if (G.terms[id]) return G.holders[id];
    const holder = document.createElement("div");
    holder.className = "gterm";
    const cs = getComputedStyle(document.documentElement);
    const term = new Terminal(Object.assign({ cursorBlink: true, fontSize: 12.5, scrollback: 5000, allowProposedApi: true,
      fontFamily: cs.getPropertyValue("--mono").trim() || "monospace" }, termOptions()));
    const fit = new FitAddon.FitAddon();
    term.loadAddon(fit);
    G.terms[id] = term; G.holders[id] = holder; G.fits[id] = fit;
    term.onData((data) => send("grid_in", { id, data }));
    term.onResize(({ rows, cols }) => send("grid_size", { id, rows, cols }));
    term.textarea && term.textarea.addEventListener("focus", () => setFocus(id));
    holder.addEventListener("mousedown", () => setFocus(id));
    new ResizeObserver(() => refit(id)).observe(holder);
    holder._opened = false;
    return holder;
  }
  function refit(id) {
    const f = G.fits[id], h = G.holders[id];
    if (!f || !h || !h.isConnected || !h.offsetWidth) return;
    try { f.fit(); } catch (e) { /* đang đóng */ }
  }
  function openTerm(id) {
    const h = G.holders[id], term = G.terms[id];
    if (h._opened || !h.isConnected) return;
    h._opened = true;
    term.open(h);
    refit(id);
    send("grid_size", { id, rows: term.rows, cols: term.cols });
    for (const m of G.pending[id] || []) onData(m);
    delete G.pending[id];
  }
  function dropTerm(id) {
    if (G.terms[id]) G.terms[id].dispose();
    delete G.terms[id]; delete G.holders[id]; delete G.fits[id]; delete G.pending[id];
  }
  function setFocus(id) {
    if (G.focus === id) return;
    G.focus = id;
    $$(".gcell", el()).forEach((c) => c.classList.toggle("focus", c.dataset.id === id));
  }
  function focusCell(id) {
    const c = id && cellById(id) ? id : (cells()[0] || {}).id;
    if (!c) return;
    setFocus(c);
    if (G.terms[c]) G.terms[c].focus();
  }

  /* ---------------------------------------------------------------- vẽ */
  function layout() {
    if ($(".gview", el())) return;
    const presets = S.meta.grid_presets || {};
    el().innerHTML = `<div class="gview">
      <div class="gbar">
        <button class="btn primary sm" data-g="add">${esc(t("g_add"))}</button>
        <button class="btn sm" data-g="shell" title="${esc(t("g_shell_s"))}">${esc(t("g_shell"))}</button>
        <span class="gsep"></span><span class="glbl">${esc(t("g_layout"))}</span>
        <span class="gseg">${Object.keys(presets).map((k) => `<button data-g="preset" data-preset="${k}" title="${esc(presets[k])}"><svg viewBox="0 0 16 16">${PRESET_ICONS[k] || ""}</svg></button>`).join("")}</span>
        <span class="glayout-name" id="g-layout-name"></span>
        <span style="flex:1"></span>
        <span class="glbl">${esc(t("g_to"))}</span>
        <button class="btn sm" data-g="bcast" id="g-bcast"></button>
        <button class="btn ghost sm" data-g="full" id="g-full">${esc(t("g_full"))}</button>
      </div>
      <div class="ghint">${esc(t("g_hint"))}</div>
      <div class="ggrid" id="ggrid"></div>
    </div>`;
    el().addEventListener("click", onClick);
    el().addEventListener("dblclick", onDblClick);
    el().addEventListener("mousedown", onGutterDown);
    el().addEventListener("dragstart", onDragStart);
    el().addEventListener("dragend", onDragEnd);
    el().addEventListener("dragover", onDragOver);
    el().addEventListener("drop", onDrop);
  }
  function signature() {
    if (!G.state) return "";
    const zoom = G.zoom && cellById(G.zoom) ? G.zoom : "";
    return zoom + "|" + G.state.cols.map((c) => c.cells.map((x) => x.id).join(",")).join("/");
  }
  function render() {
    layout();
    if (!G.state) return;
    const presets = S.meta.grid_presets || {};
    $$("[data-preset]", el()).forEach((b) => b.classList.toggle("on", b.dataset.preset === G.state.preset));
    $("#g-layout-name").textContent = presets[G.state.preset] || "";
    const n = cells().filter((c) => c.bcast).length;
    const bc = $("#g-bcast");
    bc.textContent = G.state.bcast ? t("g_all", { n }) : t("g_one");
    bc.classList.toggle("bcast-on", !!G.state.bcast);
    $("#g-full").classList.toggle("on", document.documentElement.classList.contains("grid-full"));
    const sig = signature();
    if (sig !== G.sig) { G.sig = sig; build(); }
    applySizes();
    for (const c of cells()) paintHead(c);
  }
  function build() {
    const grid = $("#ggrid");
    for (const h of Object.values(G.holders)) if (h.parentNode) h.parentNode.removeChild(h);  // giữ terminal, gắn lại sau
    if (!cells().length) {
      grid.innerHTML = `<div class="gempty">${emptyHtml()}</div>`;
      return;
    }
    const zoom = G.zoom && cellById(G.zoom);
    const cols = zoom ? [{ w: 1, cells: [zoom] }] : G.state.cols;
    grid.innerHTML = cols.map((col, i) => `${i ? `<div class="ggutter v" data-col="${i - 1}"></div>` : ""}
      <div class="gcol" data-col="${i}">${col.cells.map((c, j) => `${j ? `<div class="ggutter h" data-col="${i}" data-cell="${j - 1}"></div>` : ""}
        <div class="gcell" data-id="${esc(c.id)}">
          <div class="ghead" draggable="true">
            <span class="ggrip">⠿</span>${headName(c)}<span class="gmeta"></span><span class="gst"></span>
            <button class="gbtn" data-g="restart" title="${esc(t("g_restart"))}">⟲</button>
            <button class="gbtn" data-g="zoom" title="${esc(t("g_zoom"))}">⤢</button>
            <button class="gbtn" data-g="menu" title="${esc(t("g_more"))}">⋯</button>
            <button class="gbtn" data-g="close" title="${esc(t("g_close"))}">✕</button>
          </div>
          <div class="gbody"><div class="goff" data-g="start"></div></div>
          <div class="gfoot"></div>
          <div class="gdrop"></div>
        </div>`).join("")}</div>`).join("");
    for (const c of zoom ? [zoom] : cells()) {
      const body = $(`.gcell[data-id="${CSS.escape(c.id)}"] .gbody`, grid);
      body.insertBefore(termFor(c.id), body.firstChild);
      openTerm(c.id);
      setTimeout(() => refit(c.id), 0);
    }
    $$(".gcell", grid).forEach((x) => x.classList.toggle("focus", x.dataset.id === G.focus));
  }
  function emptyHtml() {
    const agents = (S.meta.agents || []).filter((a) => a.tty);
    return `<div class="gplus">＋</div><div class="gempty-t">${esc(t("g_empty_t"))}</div>
      <div class="gempty-s">${esc(t("g_empty_s"))}</div>
      <div class="gquick">${agents.map((a) => `<button class="chip" data-g="quick" data-agent="${esc(a.name)}">${esc(a.name)}</button>`).join("")}
        <button class="chip" data-g="shell" title="${esc(t("g_shell_s"))}">${esc(t("g_shell"))}</button></div>`;
  }
  const SHELL = ":shell";  // ô terminal trống (grid.SHELL): shell của người dùng, không phải agent
  const shellHtml = () => `<span class="agent"><span class="av">⌨</span>${esc(t("terminal"))}</span>`;
  const headName = (c) => c.shell ? shellHtml() : agentHtml(c.agent);
  function applySizes() {
    if (G.zoom) return;
    $$(".gcol", el()).forEach((colEl, i) => {
      const col = G.state.cols[i];
      if (!col) return;
      colEl.style.flexGrow = col.w;
      $$(":scope > .gcell", colEl).forEach((cEl, j) => { if (col.cells[j]) cEl.style.flexGrow = col.cells[j].h; });
    });
  }
  function paintHead(c) {
    const cEl = $(`.gcell[data-id="${CSS.escape(c.id)}"]`, el());
    if (!cEl) return;
    const st = c.status === "run" ? [t("g_run"), "run"] : c.status === "exit" ? [t("g_exit", { rc: c.rc }), "exit"] : [t("g_off"), "off"];
    $(".gmeta", cEl).textContent = (c.lead ? "★ " : "") + (c.label || "");
    $(".gst", cEl).innerHTML = `<i></i>${esc(st[0])}`;
    $(".gst", cEl).className = "gst " + st[1];
    $("[data-g=restart]", cEl).hidden = c.status === "run";
    const off = $(".goff", cEl);
    off.hidden = c.status === "run";
    off.textContent = c.status === "exit" ? t("g_exit_msg", { rc: c.rc }) : t("g_off_msg");
    off.classList.toggle("exited", c.status === "exit");
    cEl.classList.toggle("bc", !!(G.state.bcast && c.bcast));
    $(".gfoot", cEl).textContent = c.cmd || "";
  }

  /* ---------------------------------------------------------------- bấm */
  function onClick(e) {
    const b = e.target.closest("[data-g]");
    if (!b) return;
    const cEl = b.closest(".gcell"), id = cEl && cEl.dataset.id;
    const act = b.dataset.g;
    if (act === "add") addModal();
    else if (act === "quick") request("grid_add", { agent: b.dataset.agent, resume: true }, t("busy_opening", { v: b.dataset.agent })).then(focusNew);
    else if (act === "shell") request("grid_add", { agent: SHELL }, t("busy_opening", { v: "Terminal" })).then(focusNew);
    else if (act === "preset") { G.zoom = null; send("grid_preset", { preset: b.dataset.preset }); }
    else if (act === "bcast") send("grid_bcast", { on: !G.state.bcast });
    else if (act === "full") { document.documentElement.classList.toggle("grid-full"); render(); setTimeout(() => cells().forEach((c) => refit(c.id)), 50); }
    else if (act === "zoom") { G.zoom = G.zoom === id ? null : id; G.focus = id; render(); setTimeout(() => focusCell(id), 30); }
    else if (act === "restart" || act === "start") {
      const term = G.terms[id];
      send("grid_start", { id, rows: term ? term.rows : 24, cols: term ? term.cols : 80 });
      setTimeout(() => focusCell(id), 30);
    } else if (act === "close") closeCell(id);
    else if (act === "menu") cellMenu(id, b);
  }
  function focusNew(r) {
    if (r && r.grid_cell) { G.focus = r.grid_cell; setTimeout(() => focusCell(r.grid_cell), 120); }
  }
  async function closeCell(id) {
    const c = cellById(id);
    if (!c) return;
    if (c.status === "run" && !(await confirmBox(t("g_close"), t("g_close_q", { agent: c.shell ? t("terminal") : c.agent }), t("g_close_yes")))) return;
    send("grid_close", { id });
  }
  function cellMenu(id, btn) {
    const c = cellById(id);
    $$(".gmenu").forEach((m) => m.remove());
    const m = document.createElement("div");
    m.className = "gmenu";
    m.innerHTML = `<div class="mh">${c.shell ? esc(t("terminal")) : `${esc(c.agent)} · ${esc(c.label || "")}`}</div>
      <div class="mi" data-m="right">${esc(t("g_split_r"))}</div>
      <div class="mi" data-m="bottom">${esc(t("g_split_b"))}</div>
      <div class="ms"></div>
      <label class="mi"><input type="checkbox" data-m="bcast" ${c.bcast ? "checked" : ""}> ${esc(t("g_bcast_in"))}</label>
      <div class="ms"></div>
      <div class="mi danger" data-m="close">✕ ${esc(t("g_close"))}</div>`;
    document.body.appendChild(m);
    const r = btn.getBoundingClientRect();
    m.style.top = (r.bottom + 4) + "px";
    m.style.left = Math.max(8, Math.min(window.innerWidth - m.offsetWidth - 8, r.right - m.offsetWidth)) + "px";
    const gone = (e) => { if (!m.contains(e.target)) { m.remove(); document.removeEventListener("mousedown", gone, true); } };
    setTimeout(() => document.addEventListener("mousedown", gone, true), 0);
    m.addEventListener("click", (e) => {
      const it = e.target.closest("[data-m]");
      if (!it) return;
      const k = it.dataset.m;
      if (k === "bcast") { send("grid_cell", { id, bcast: it.checked }); return; }
      m.remove();
      if (k === "close") closeCell(id);
      else addModal({ near: id, where: k });
    });
  }

  /* ---------------------------------------------------------------- kéo thả ô */
  function onDragStart(e) {
    const head = e.target.closest && e.target.closest(".ghead");
    if (!head) return;
    G.drag = head.closest(".gcell").dataset.id;
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", G.drag); } catch (err) { /* Safari cũ */ }
    $("#ggrid").classList.add("dragging");
    head.closest(".gcell").classList.add("lifted");
  }
  function onDragEnd() {
    G.drag = null;
    const grid = $("#ggrid");
    if (!grid) return;
    grid.classList.remove("dragging");
    $$(".gcell", grid).forEach((c) => { c.classList.remove("lifted"); $(".gdrop", c).className = "gdrop"; $(".gdrop", c).textContent = ""; });
  }
  function zoneOf(cEl, e) {
    const r = cEl.getBoundingClientRect();
    const fx = (e.clientX - r.left) / r.width, fy = (e.clientY - r.top) / r.height;
    return fx < EDGE ? "left" : fx > 1 - EDGE ? "right" : fy < EDGE ? "top" : fy > 1 - EDGE ? "bottom" : "center";
  }
  function onDragOver(e) {
    if (!G.drag) return;
    const cEl = e.target.closest && e.target.closest(".gcell");
    $$(".gcell", el()).forEach((c) => { if (c !== cEl) { $(".gdrop", c).className = "gdrop"; $(".gdrop", c).textContent = ""; } });
    if (!cEl || cEl.dataset.id === G.drag) return;
    e.preventDefault();
    const z = zoneOf(cEl, e), d = $(".gdrop", cEl);
    d.className = "gdrop on z-" + z;
    d.textContent = t("g_drop_" + z);
  }
  function onDrop(e) {
    const cEl = e.target.closest && e.target.closest(".gcell");
    if (!G.drag || !cEl || cEl.dataset.id === G.drag) { onDragEnd(); return; }
    e.preventDefault();
    send("grid_move", { src: G.drag, dst: cEl.dataset.id, where: zoneOf(cEl, e) });
    G.focus = G.drag;
    onDragEnd();
  }

  /* ---------------------------------------------------------------- kéo khe đổi kích thước */
  function onGutterDown(e) {
    const g = e.target.closest(".ggutter");
    if (!g || e.button !== 0) return;
    e.preventDefault();
    const vertical = g.classList.contains("v");
    const a = g.previousElementSibling, b = g.nextElementSibling;
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    const total = vertical ? ra.width + rb.width : ra.height + rb.height;
    const grow = (+a.style.flexGrow || 1) + (+b.style.flexGrow || 1);
    const start = vertical ? e.clientX : e.clientY, sizeA = vertical ? ra.width : ra.height;
    g.classList.add("hot");
    document.body.classList.add(vertical ? "g-resizing-x" : "g-resizing-y");
    const move = (ev) => {
      const pos = vertical ? ev.clientX : ev.clientY;
      const fa = Math.min(0.85, Math.max(0.15, (sizeA + pos - start) / total));
      a.style.flexGrow = grow * fa; b.style.flexGrow = grow * (1 - fa);
    };
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      g.classList.remove("hot");
      document.body.classList.remove("g-resizing-x", "g-resizing-y");
      saveSizes();
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  }
  function onDblClick(e) {
    const g = e.target.closest(".ggutter");
    if (!g) return;
    const a = g.previousElementSibling, b = g.nextElementSibling;
    const avg = ((+a.style.flexGrow || 1) + (+b.style.flexGrow || 1)) / 2;
    a.style.flexGrow = avg; b.style.flexGrow = avg;
    saveSizes();
  }
  function saveSizes() {
    if (G.zoom) return;
    const widths = $$(".gcol", el()).map((c) => +c.style.flexGrow || 1);
    const heights = {};
    $$(".gcell", el()).forEach((c) => { heights[c.dataset.id] = +c.style.flexGrow || 1; });
    send("grid_sizes", { widths, heights });
  }

  /* ---------------------------------------------------------------- popup Thêm agent */
  function addModal(opts = {}) {
    const agents = (S.meta.agents || []).filter((a) => a.tty);
    const open = {};
    for (const c of cells()) open[c.agent] = (open[c.agent] || 0) + 1;
    const shell = { name: SHELL, models: [], efforts: [], model: "", effort: "" };
    let pick = agents.find((a) => !open[a.name]) || agents[0] || shell;
    const near = opts.near || (G.focus && cellById(G.focus) ? G.focus : "");
    const m = openModal(`${modalHead(esc(t("g_add_title")))}
      <div class="modal-pad gadd">
        <div><div class="gfl">1 · ${esc(t("g_cli"))}</div><div class="gclis"><button class="gcli" data-agent="${SHELL}">${shellHtml()}
            <span class="gcli-s">${esc(t("g_shell_s"))}</span><span class="gcli-n">${open[SHELL] ? "×" + open[SHELL] : ""}</span></button>${agents.map((a) => `
          <button class="gcli" data-agent="${esc(a.name)}">${agentHtml(a.name)}
            <span class="gcli-s">${esc(a.bin)} · ${esc(a.installed ? t("g_installed") : t("g_missing"))}</span>
            <span class="gcli-n">${open[a.name] ? "×" + open[a.name] : ""}</span></button>`).join("")}</div></div>
        <div class="grow2">
          <div><div class="gfl">2 · ${esc(t("g_model"))}</div>
            <select class="field one" id="ga-model"></select><select class="field one" id="ga-effort" style="margin-top:6px"></select></div>
          <div><div class="gfl">3 · ${esc(t("g_session"))}</div>
            <label class="gopt"><input type="radio" name="ga-sess" value="resume" checked><span><b>${esc(t("g_resume"))}</b><small>${esc(t("g_resume_s"))}</small></span></label>
            <label class="gopt"><input type="radio" name="ga-sess" value="new"><span><b>${esc(t("g_new"))}</b><small>${esc(t("g_new_s"))}</small></span></label></div>
        </div>
        <div><div class="gfl">4 · ${esc(t("g_place"))}</div><div class="gplace">
          <label class="gopt"><input type="radio" name="ga-where" value="" ${opts.where ? "" : "checked"}><span><b>${esc(t("g_place_auto"))}</b></span></label>
          <label class="gopt"><input type="radio" name="ga-where" value="right" ${opts.where === "right" ? "checked" : ""} ${near ? "" : "disabled"}><span><b>${esc(t("g_place_right"))}</b></span></label>
          <label class="gopt"><input type="radio" name="ga-where" value="bottom" ${opts.where === "bottom" ? "checked" : ""} ${near ? "" : "disabled"}><span><b>${esc(t("g_place_bottom"))}</b></span></label>
        </div></div>
        <div class="row-actions end"><button class="btn ghost" data-action="close-modal">${esc(t("cancel_edit"))}</button>
          <button class="btn primary" id="ga-ok">${esc(t("g_open"))}</button></div>
      </div>`, { box: "md" });
    const fill = () => {
      $$(".gcli", m).forEach((b) => b.classList.toggle("on", b.dataset.agent === pick.name));
      $("#ga-model", m).innerHTML = `<option value="">${esc(t("g_default"))}${pick.model ? " (" + esc(pick.model) + ")" : ""}</option>`
        + pick.models.map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join("");
      fillEffort();
      $$("#ga-model, #ga-effort, input[name=ga-sess]", m).forEach((x) => { x.disabled = pick === shell; });
    };
    const fillEffort = () => {
      $("#ga-effort", m).innerHTML = `<option value="">effort: ${esc(t("g_default"))}${pick.effort ? " (" + esc(pick.effort) + ")" : ""}</option>`
        + pick.efforts.map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join("");
    };
    fill();
    m.addEventListener("click", (e) => {
      const b = e.target.closest(".gcli");
      if (b) { pick = b.dataset.agent === SHELL ? shell : agents.find((a) => a.name === b.dataset.agent) || pick; fill(); }
    });
    const go = () => {
      const where = ($("input[name=ga-where]:checked", m) || {}).value || "";
      request("grid_add", { agent: pick.name, model: $("#ga-model", m).value, effort: $("#ga-effort", m).value,
        resume: ($("input[name=ga-sess]:checked", m) || {}).value !== "new", near: where ? near : "", where },
        t("busy_opening", { v: pick === shell ? "Terminal" : pick.name }))
        .then(focusNew);
      closeModal(m);
    };
    $("#ga-ok", m).addEventListener("click", go);
    m.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.target.closest("select")) { e.preventDefault(); go(); } });
    setTimeout(() => $("#ga-ok", m).focus(), 40);
  }

  /* /grid <agent> từ ô nhập: server đã thêm ô, chỉ cần mở mục Lưới */
  return { show, reset, onState, onData, onExit, render, addModal, focusCell, focused: () => G.focus,
    terms: () => Object.values(G.terms) };
})();
