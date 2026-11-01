/* Mục 🛰 API — gọi thử HTTP kiểu Postman (ateam/web_api.py + ateam/apiclient.py). Collection lưu ở .ateam/api/<tên>.json
   (commit được); sửa là tự lưu (~0,8 giây sau phím cuối). Request đang soạn gửi thẳng lên server (op http send) nên
   không cần lưu trước khi gửi. Secret (token, mật khẩu, biến lấy từ response) ở ngoài repo, server chỉ trả tên. */
"use strict";

window.ApiView = (() => {
  const LS = "ateam-api-view";
  let P = { coll: "", env: "", req: null, tab: "params", rtab: "body" };
  try { Object.assign(P, JSON.parse(localStorage.getItem(LS) || "{}")); } catch (e) { /* chặn lưu */ }
  const keep = () => { try { localStorage.setItem(LS, JSON.stringify(P)); } catch (e) { /* chặn lưu */ } };
  let st = { collections: [], envs: [], secrets: [], ports: [] }, coll = null, results = {}, q = "", timer = null, dirty = false;
  const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];
  const cur = () => (coll && coll.requests.find((r) => r.id === P.req)) || null;

  async function call(action, data = {}, busy = "") {
    const m = await request("http", Object.assign({ action }, data), busy);
    if (m.http && m.http.collections) st = m.http;
    return m.http ? m : (m.text && toast(m.text, m.level || "warn"), null);
  }

  /* ---------------------------------------------------------------- khung */
  function layout() {
    if ($("#api-items")) return;
    $("#api").innerHTML = `
      <div class="aview">
        <div class="alist">
          <div class="alh">
            <div class="row"><select class="field one sm" id="api-coll"></select>
              <button class="btn sm ghost" data-a="coll-new" title="${esc(t("ap_new_coll"))}">＋</button>
              <button class="btn sm ghost danger" data-a="coll-del" title="${esc(t("ap_del"))}">✕</button></div>
            <div class="row"><select class="field one sm" id="api-env"></select>
              <button class="btn sm ghost" data-a="vars">${esc(t("ap_vars"))}</button></div>
            <div class="row"><button class="btn sm primary" data-a="req-new">${esc(t("ap_new_req"))}</button>
              <button class="btn sm" data-a="curl">${esc(t("ap_curl"))}</button>
              <button class="btn sm" data-a="run">${esc(t("ap_run_all"))}</button></div>
            <input class="field one sm" id="api-q" placeholder="${esc(t("ap_search"))}" autocomplete="off">
          </div>
          <div class="aitems" id="api-items"></div>
          <div class="afoot"><button class="btn sm ghost" data-a="history">${esc(t("ap_history"))}</button>
            <span class="path" id="api-path"></span><span id="api-saved"></span></div>
        </div>
        <div class="aed" id="api-ed"></div>
      </div>`;
    const root = $("#api");
    root.addEventListener("click", onClick);
    root.addEventListener("input", onInput);
    root.addEventListener("change", onChange);
    root.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); sendCur(); }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); flush(); }
    });
    $("#api-q").addEventListener("input", (e) => { q = e.target.value.toLowerCase(); renderList(); });
  }

  function renderSide() {
    const sel = $("#api-coll");
    sel.innerHTML = st.collections.length
      ? st.collections.map((c) => `<option value="${esc(c.name)}"${c.name === P.coll ? " selected" : ""}>${esc(c.name)} (${c.count})</option>`).join("")
      : `<option value="">${esc(t("ap_no_coll"))}</option>`;
    $("#api-env").innerHTML = `<option value="">${esc(t("ap_no_env"))}</option>` +
      st.envs.map((n) => `<option value="${esc(n)}"${n === P.env ? " selected" : ""}>${esc(n)}</option>`).join("");
    $("#api-path").textContent = coll ? `${st.dir || ".ateam/api/"}${P.coll}.json` : st.dir || "";
    savedMark();
  }
  function savedMark() {
    const s = $("#api-saved");
    if (!s) return;
    s.className = dirty ? "unsaved" : "saved";
    s.textContent = coll ? (dirty ? "● " + t("ap_unsaved") : "✓ " + t("ap_saved")) : "";
  }

  function renderList() {
    const box = $("#api-items");
    if (!coll) { box.innerHTML = `<div class="nempty muted">${esc(t("ap_empty"))}</div>`; return; }
    const rs = coll.requests.filter((r) => !q || `${r.name} ${r.url} ${r.folder || ""}`.toLowerCase().includes(q));
    if (!rs.length) { box.innerHTML = `<div class="nempty muted">${esc(t(q ? "ap_no_match" : "ap_empty"))}</div>`; return; }
    const groups = {};
    for (const r of rs) (groups[r.folder || ""] = groups[r.folder || ""] || []).push(r);
    box.innerHTML = Object.keys(groups).sort().map((f) => (f ? `<div class="nsec">${esc(f)}</div>` : "") + groups[f].map((r) => {
      const res = results[r.id], code = res && res.response ? res.response.status : null;
      const mark = res ? `<span class="ast ${res.ok ? "ok" : "bad"}">${res.response.error ? "✗" : code}</span>` : "";
      return `<div class="ai${r.id === P.req ? " sel" : ""}" data-rid="${r.id}"><span class="am m-${esc(r.method || "GET")}">${esc(r.method || "GET")}</span>
        <span class="an">${esc(r.name || r.url || t("ap_untitled"))}</span>${mark}</div>`;
    }).join("")).join("");
  }

  /* ---------------------------------------------------------------- soạn request */
  const kvRows = (rows) => (rows || []).concat([["", "", true]]);
  function kvHtml(field, rows) {
    return `<div class="akv" data-kv="${field}">` + kvRows(rows).map((r, i, all) => `<div class="kvr">
      <input type="checkbox" data-i="${i}" data-f="on"${r[2] === false ? "" : " checked"}${i === all.length - 1 ? " disabled" : ""}>
      <input class="field one sm" data-i="${i}" data-f="k" value="${esc(r[0])}" placeholder="${esc(t("ap_key"))}">
      <input class="field one sm" data-i="${i}" data-f="v" value="${esc(r[1])}" placeholder="${esc(t("ap_value"))}">
      <button class="icon-btn sm" data-a="kv-del" data-i="${i}"${i === all.length - 1 ? " hidden" : ""}>✕</button></div>`).join("") + "</div>";
  }
  /* sửa một ô của bảng khoá–giá trị; gõ vào dòng trống cuối thì vẽ lại bảng (thêm dòng trống mới), giữ con trỏ */
  function kvEdit(el, rows) {
    const kv = el.closest("[data-kv]"), field = kv.dataset.kv, i = +el.dataset.i, f = el.dataset.f;
    if (!rows[i]) rows[i] = ["", "", true];
    if (f === "k") rows[i][0] = el.value; else if (f === "v") rows[i][1] = el.value; else rows[i][2] = el.checked;
    if (f !== "on" && !kv.querySelector(`[data-i="${i + 1}"]`)) {
      const pos = el.selectionStart, box = kv.parentNode;
      kv.outerHTML = kvHtml(field, rows);
      const again = $(`[data-kv="${field}"] [data-i="${i}"][data-f="${f}"]`, box);
      if (again) { again.focus(); again.setSelectionRange(pos, pos); }
    }
  }
  function tabBody(r) {
    if (P.tab === "params") return kvHtml("query", r.query);
    if (P.tab === "headers") return kvHtml("headers", r.headers);
    if (P.tab === "body") {
      const b = r.body || { type: "none" };
      const seg = ["none", "json", "form", "raw"].map((k) => `<button class="mini btn sm${(b.type || "none") === k ? " on" : ""}" data-a="body-type" data-v="${k}">${esc(t("ap_b_" + k))}</button>`).join("");
      const inner = b.type === "form" ? kvHtml("form", b.form)
        : b.type === "json" || b.type === "raw"
          ? `<textarea class="asrc" data-f="body-text" spellcheck="false">${esc(b.text || "")}</textarea>` : "";
      const fmt = b.type === "json" ? `<button class="btn sm ghost" data-a="fmt">${esc(t("ap_format"))}</button>` : "";
      return `<div class="abar"><span class="seg">${seg}</span>${fmt}</div>${inner}`;
    }
    if (P.tab === "auth") {
      const a = r.auth || { type: "none" };
      const opt = (k, l) => `<option value="${k}"${(a.type || "none") === k ? " selected" : ""}>${esc(t(l))}</option>`;
      const inp = (f, l, type = "text") => `<label class="af"><span>${esc(t(l))}</span><input class="field one sm" type="${type}" data-f="auth-${f}" value="${esc(a[f] || "")}" placeholder="{{token}}"></label>`;
      return `<div class="aform"><label class="af"><span>${esc(t("ap_auth"))}</span><select class="field one sm" data-f="auth-type">
        ${opt("none", "ap_auth_none")}${opt("bearer", "ap_bearer")}${opt("basic", "ap_basic")}</select></label>
        ${a.type === "bearer" ? inp("token", "ap_token") : ""}
        ${a.type === "basic" ? inp("user", "ap_user") + inp("password", "ap_pass", "password") : ""}
        <div class="muted small">${esc(t("ap_auth_hint"))}</div></div>`;
    }
    return `<div class="aform"><div class="muted small">${esc(t("ap_asserts"))}</div>
      <textarea class="asrc short" data-f="asserts" spellcheck="false" placeholder="${esc(t("ap_asserts_ph"))}">${esc((r.asserts || []).join("\n"))}</textarea>
      <div class="muted small">${esc(t("ap_extract"))}</div>
      <textarea class="asrc short" data-f="extract" spellcheck="false" placeholder="${esc(t("ap_extract_ph"))}">${esc((r.extract || []).join("\n"))}</textarea></div>`;
  }
  function count(r, tab) {
    const n = tab === "params" ? (r.query || []).length : tab === "headers" ? (r.headers || []).length
      : tab === "tests" ? (r.asserts || []).length : 0;
    return n ? ` <span class="nav-count">${n}</span>` : "";
  }
  function renderEd() {
    const ed = $("#api-ed"), r = cur();
    if (!r) { ed.innerHTML = `<div class="nnone muted">${esc(t(coll ? "ap_none" : "ap_empty"))}</div>`; return; }
    const tabs = ["params", "headers", "body", "auth", "tests"].map((k) =>
      `<button class="tab${P.tab === k ? " on" : ""}" data-a="tab" data-v="${k}">${esc(t("ap_" + k))}${count(r, k)}</button>`).join("");
    ed.innerHTML = `
      <div class="aeh">
        <div class="row"><input class="ntitle" data-f="name" value="${esc(r.name || "")}" placeholder="${esc(t("ap_name_ph"))}">
          <input class="field one sm afold" data-f="folder" value="${esc(r.folder || "")}" placeholder="${esc(t("ap_folder_ph"))}">
          <button class="btn sm ghost" data-a="copy-curl">${esc(t("ap_copy_curl"))}</button>
          <button class="btn sm ghost" data-a="dup">${esc(t("ap_dup"))}</button>
          <button class="btn sm ghost danger" data-a="req-del">${esc(t("ap_del"))}</button></div>
        <div class="row aurl"><select class="field one sm am-sel" data-f="method">${METHODS.map((m) => `<option${(r.method || "GET") === m ? " selected" : ""}>${m}</option>`).join("")}</select>
          <input class="field one mono" data-f="url" value="${esc(r.url || "")}" placeholder="${esc(t("ap_url_ph"))}" spellcheck="false">
          <button class="btn primary" data-a="send" id="api-send">${esc(t("ap_send"))} <kbd>⌘↵</kbd></button></div>
      </div>
      <div class="tabs">${tabs}</div>
      <div class="atab" id="api-tab">${tabBody(r)}</div>
      <div class="aresp" id="api-resp"></div>`;
    renderResp();
  }

  /* ---------------------------------------------------------------- response */
  function prettyJson(text) {
    let v;
    try { v = JSON.parse(text); } catch (e) { return null; }
    const s = JSON.stringify(v, null, 2);
    return esc(s).replace(/(&quot;(?:\\.|[^&\\]|&(?!quot;))*?&quot;)(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
      (m, str, colon, kw, num) => str ? `<span class="${colon ? "tk-f" : "tk-s"}">${str}</span>${colon || ""}`
        : kw ? `<span class="tk-k">${kw}</span>` : `<span class="tk-n">${num}</span>`);
  }
  const size = (n) => n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(1) + " KB" : (n / 1048576).toFixed(1) + " MB";
  function renderResp() {
    const box = $("#api-resp"), r = cur();
    if (!box || !r) return;
    const res = results[r.id];
    if (!res) { box.innerHTML = `<div class="nnone muted">${esc(t("ap_no_resp"))}</div>`; return; }
    const rp = res.response;
    if (rp.error) {
      box.innerHTML = `<div class="arh"><span class="chip" style="color:var(--failed)">${esc(t("ap_net_err"))}</span><span class="muted">${rp.ms} ms</span></div>
        <pre class="abody err">${esc(rp.error)}</pre>`;
      return;
    }
    const cls = rp.status < 300 ? "done" : rp.status < 400 ? "review" : "failed";
    const fails = res.asserts.filter((a) => !a.ok).length;
    const tabs = ["body", "headers", "tests"].map((k) => `<button class="tab${P.rtab === k ? " on" : ""}" data-a="rtab" data-v="${k}">${esc(t("ap_r_" + k))}${
      k === "tests" && res.asserts.length ? ` <span class="ast ${fails ? "bad" : "ok"}">${res.asserts.length - fails}/${res.asserts.length}</span>` : ""}</button>`).join("");
    let body;
    if (P.rtab === "headers") body = `<div class="ahdrs">${rp.headers.map(([k, v]) => `<div><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join("")}</div>`;
    else if (P.rtab === "tests") body = res.asserts.length ? `<div class="aasserts">${res.asserts.map((a) => `<div class="${a.ok ? "ok" : "bad"}">${a.ok ? "✓" : "✗"} ${esc(a.msg)}</div>`).join("")}</div>`
      : `<div class="muted pad">${esc(t("ap_no_asserts"))}</div>`;
    else {
      const text = rp.body.length > 300000 ? rp.body.slice(0, 300000) : rp.body;
      body = `<pre class="abody">${prettyJson(text) || esc(text) || `<span class="muted">${esc(t("ap_empty_body"))}</span>`}</pre>`;
    }
    const ext = res.extracted && res.extracted.length ? `<span class="muted">${esc(t("ap_extracted", { v: res.extracted.join(", ") }))}</span>` : "";
    box.innerHTML = `<div class="arh"><span class="chip" style="color:var(--${cls})"><span class="dot"></span>${rp.status} ${esc(rp.reason || "")}</span>
      <span class="muted">${rp.ms} ms · ${size(rp.size)}${rp.truncated ? " · " + esc(t("ap_truncated")) : ""}</span>${ext}
      <span class="sp"></span><button class="btn sm ghost" data-a="copy-body">${esc(t("ap_copy_body"))}</button></div>
      <div class="tabs">${tabs}</div><div class="arb">${body}</div>`;
  }

  /* ---------------------------------------------------------------- sự kiện */
  function setField(r, f, v) {
    if (f === "body-text") { r.body = Object.assign({ type: "json" }, r.body, { text: v }); }
    else if (f === "asserts" || f === "extract") r[f] = v.split("\n").map((s) => s.trimEnd()).filter((s) => s.trim());
    else if (f.startsWith("auth-")) {
      r.auth = Object.assign({ type: "none" }, r.auth, { [f.slice(5)]: v });
      if (f === "auth-type") renderTabOnly();
    } else r[f] = v;
  }
  function onInput(e) {
    const el = e.target, r = cur();
    if (!r || !el.dataset) return;
    const kv = el.closest("[data-kv]");
    if (kv) {
      const field = kv.dataset.kv;
      kvEdit(el, field === "form" ? ((r.body = r.body || { type: "form" }).form = r.body.form || []) : (r[field] = r[field] || []));
      touch();
      return;
    }
    if (!el.dataset.f) return;
    setField(r, el.dataset.f, el.value);
    touch();
    if (["name", "url", "method"].includes(el.dataset.f)) renderList();
  }
  function onChange(e) {  // select/checkbox phát cả input lẫn change: phần soạn request đã xử lý ở onInput
    const el = e.target;
    if (el.id === "api-coll") { flush(); P.coll = el.value; P.req = null; keep(); loadColl(); }
    else if (el.id === "api-env") { P.env = el.value; keep(); }
  }
  function renderTabOnly() { const r = cur(), b = $("#api-tab"); if (r && b) b.innerHTML = tabBody(r); }
  function onClick(e) {
    const it = e.target.closest("[data-rid]");
    if (it) { P.req = +it.dataset.rid; keep(); renderList(); renderEd(); return; }
    const b = e.target.closest("[data-a]");
    if (!b) return;
    const a = b.dataset.a, r = cur();
    const acts = {
      "coll-new": newColl, "coll-del": delColl, "vars": varsModal, "req-new": () => newReq(),
      "curl": importCurl, "run": runAll, "history": historyModal, "send": sendCur, "dup": dupReq, "req-del": delReq,
      "copy-curl": copyCurl,
      "copy-body": () => { const x = r && results[r.id]; if (x) copy(x.response.body || ""); },
      "tab": () => { P.tab = b.dataset.v; keep(); renderEd(); },
      "rtab": () => { P.rtab = b.dataset.v; keep(); renderResp(); },
      "body-type": () => { r.body = Object.assign({}, r.body, { type: b.dataset.v }); touch(); renderTabOnly(); },
      "fmt": () => {
        try { r.body.text = JSON.stringify(JSON.parse(r.body.text || ""), null, 2); touch(); renderTabOnly(); }
        catch (err) { toast(t("ap_bad_json", { v: err.message }), "warn"); }
      },
      "kv-del": () => {
        const kv = b.closest("[data-kv]"), field = kv.dataset.kv;
        const rows = field === "form" ? r.body.form : r[field];
        rows.splice(+b.dataset.i, 1); touch(); kv.outerHTML = kvHtml(field, rows);
      },
    };
    if (acts[a]) acts[a]();
  }
  function copy(text) {
    navigator.clipboard.writeText(text).then(() => toast(t("copied"), "ok"), () => textModal("curl", text));
  }

  /* ---------------------------------------------------------------- lưu / tải */
  function touch() { dirty = true; savedMark(); clearTimeout(timer); timer = setTimeout(flush, 800); }
  async function flush() {
    clearTimeout(timer);
    if (!dirty || !coll) return;
    dirty = false;
    const m = await call("save", { collection: P.coll, data: coll });
    if (!m) { dirty = true; }
    savedMark();
    const c = st.collections.find((x) => x.name === P.coll);
    if (c && c.count !== coll.requests.length) { c.count = coll.requests.length; renderSide(); }
  }
  async function loadState() { await call("state"); }
  async function loadColl() {
    if (!st.collections.some((c) => c.name === P.coll)) P.coll = st.collections.length ? st.collections[0].name : "";
    coll = null;
    if (P.coll) {
      const m = await call("get", { collection: P.coll });
      coll = m ? m.http.collection : null;
    }
    if (coll && !cur()) P.req = coll.requests.length ? coll.requests[0].id : null;
    keep(); renderSide(); renderList(); renderEd();
  }
  async function ensureColl() {
    if (coll) return true;
    const m = await call("new", { name: "api" });
    if (!m) return false;
    P.coll = m.http.created; await loadColl();
    return !!coll;
  }
  function nextId() { return Math.max(0, ...coll.requests.map((r) => r.id || 0)) + 1; }
  async function newReq(base) {
    if (!(await ensureColl())) return;
    const r = Object.assign({ name: "", method: "GET", url: "/", query: [], headers: [], body: { type: "none" }, auth: { type: "none" }, asserts: ["status == 200"] },
      base || {}, { id: nextId() });
    coll.requests.push(r); P.req = r.id; keep(); touch(); renderList(); renderEd();
    const u = $('#api-ed [data-f="url"]'); if (u && !base) { u.focus(); u.select(); }
  }
  function dupReq() {
    const r = cur();
    if (r) newReq(Object.assign(JSON.parse(JSON.stringify(r)), { name: (r.name || "") + " (copy)" }));
  }
  async function delReq() {
    const r = cur();
    if (!r || !(await confirmBox(t("ap_del"), t("ap_del_req_q", { v: r.name || r.url }), t("ap_del")))) return;
    coll.requests = coll.requests.filter((x) => x !== r);
    P.req = coll.requests.length ? coll.requests[0].id : null; keep(); touch(); renderList(); renderEd();
  }
  async function newColl() {
    const name = await inputBox(t("ap_new_coll"), t("ap_coll_name"), "");
    if (!name) return;
    await flush();
    const m = await call("new", { name });
    if (m) { P.coll = m.http.created; P.req = null; await loadColl(); }
  }
  async function delColl() {
    if (!coll || !(await confirmBox(t("ap_del"), t("ap_del_coll_q", { v: P.coll }), t("ap_del")))) return;
    clearTimeout(timer); dirty = false;
    await call("delete", { collection: P.coll });
    P.coll = ""; await loadColl();
  }

  /* ---------------------------------------------------------------- gửi / chạy */
  async function sendCur() {
    const r = cur();
    if (!r) return;
    const m = await busyBtn($("#api-send"), call("send", { collection: P.coll, env: P.env, request: r }));
    if (!m) return;
    results[r.id] = m.http.result; st.secrets = m.http.secrets;
    if (P.rtab === "tests" && !m.http.result.asserts.length) P.rtab = "body";
    renderResp(); renderList();
  }
  async function copyCurl() {
    const r = cur();
    if (!r) return;
    const m = await call("curl", { collection: P.coll, env: P.env, request: r });
    if (m) copy(m.http.curl);
  }
  async function runAll() {
    if (!coll || !coll.requests.length) return;
    await flush();
    const m = await call("run", { collection: P.coll, env: P.env }, t("ap_running"));
    if (!m) return;
    const rows = m.http.run;
    openModal(`${modalHead(esc(t("ap_run_title", { v: P.coll })))}<div class="modal-body plain"><div class="arun">${rows.map((x) => `
      <div class="arr ${x.ok ? "ok" : "bad"}" data-rid="${x.id}"><b>${x.ok ? "✓" : "✗"} ${esc(x.name || "#" + x.id)}</b>
        <span class="muted">${x.error ? esc(x.error) : `${x.status} · ${x.ms} ms`}</span>
        ${x.asserts.filter((a) => !a.ok).map((a) => `<div class="bad small">✗ ${esc(a.msg)}</div>`).join("")}</div>`).join("")}
      </div><div class="muted small pad">${esc(m.text || "")} · <code>ateam api run ${esc(P.coll)}${P.env ? " --env " + esc(P.env) : ""}</code></div></div>`, { box: "md" });
  }
  async function importCurl() {
    const m0 = openModal(`${modalHead(esc(t("ap_curl")))}<div class="modal-pad"><div class="confirm-text">${esc(t("ap_curl_q"))}</div>
      <textarea class="field asrc" id="api-curl" spellcheck="false" autofocus placeholder="curl https://…"></textarea>
      <div class="row-actions end"><button class="btn primary" id="api-curl-go">${esc(t("ap_import"))}</button></div></div>`, { box: "md" });
    $("#api-curl-go", m0).addEventListener("click", async () => {
      const m = await call("import_curl", { text: $("#api-curl", m0).value });
      if (!m) return;
      closeModal(m0); newReq(m.http.request);
    });
  }
  async function historyModal() {
    const m = await call("history");
    if (!m) return;
    const h = m.http.history;
    const box = openModal(`${modalHead(esc(t("ap_history")))}<div class="modal-body plain"><div class="arun">${h.length ? h.map((x, i) => `
      <div class="arr hist" data-h="${i}"><b><span class="am m-${esc(x.request.method || "GET")}">${esc(x.request.method || "GET")}</span> ${esc(x.request.url || "")}</b>
        <span class="muted">${x.error ? esc(x.error) : x.status} · ${x.ms} ms · ${esc(new Date(x.at * 1000).toLocaleString())}${x.collection ? " · " + esc(x.collection) : ""}</span></div>`).join("")
      : `<div class="muted pad">${esc(t("ap_hist_empty"))}</div>`}</div></div>`, { box: "md" });
    box.addEventListener("click", (e) => {
      const row = e.target.closest("[data-h]");
      if (!row) return;
      const x = h[+row.dataset.h];
      closeModal(box); newReq(Object.assign({}, x.request, { name: x.name || "" }));
    });
  }

  /* ---------------------------------------------------------------- biến */
  async function varsModal() {
    await flush();
    const env = P.env, ev = env ? ((await call("env_get", { env })) || { http: { values: {} } }).http.values : {};
    const pairs = (o) => Object.entries(o || {}).map(([k, v]) => [k, v, true]);
    const ports = st.ports.length ? `<div class="muted small">${esc(t("ap_port_hint", { v: st.ports.map((p) => "http://localhost:" + p).join(", ") }))}</div>` : "";
    const m = openModal(`${modalHead(esc(t("ap_vars")))}<div class="modal-pad avars">
      ${coll ? `<div class="panel-title small">${esc(t("ap_coll_vars"))}</div>${kvHtml("cvars", pairs(coll.vars))}` : ""}
      <div class="panel-title small">${esc(env ? t("ap_env_vars", { v: env }) : t("ap_env"))}</div>
      ${env ? kvHtml("evars", pairs(ev)) : `<div class="muted small">${esc(t("ap_env_none"))}</div>`}
      <button class="btn sm ghost" data-v="env-new">${esc(t("ap_env_new"))}</button>${ports}
      <div class="panel-title small">${esc(t("ap_secrets"))}</div>
      <div class="asec">${st.secrets.map((k) => `<div class="kvr"><code>{{${esc(k)}}}</code><input class="field one sm" type="password" data-sk="${esc(k)}" placeholder="••••••">
        <button class="btn sm ghost" data-v="sec-set" data-k="${esc(k)}">${esc(t("ap_secret_set"))}</button><button class="icon-btn sm" data-v="sec-del" data-k="${esc(k)}">✕</button></div>`).join("")}
        <div class="kvr"><input class="field one sm" id="sec-k" placeholder="${esc(t("ap_key"))}"><input class="field one sm" type="password" id="sec-v" placeholder="${esc(t("ap_value"))}">
        <button class="btn sm ghost" data-v="sec-add">＋</button></div></div>
      <div class="muted small">${esc(t("ap_secret_hint"))}</div>
      <div class="row-actions end"><button class="btn primary" data-v="save">${esc(t("ap_save"))}</button></div></div>`, { box: "md" });
    const rows = { cvars: pairs(coll && coll.vars), evars: pairs(ev) };
    m.addEventListener("input", (e) => { const kv = e.target.closest("[data-kv]"); if (kv) kvEdit(e.target, rows[kv.dataset.kv]); });
    const obj = (list) => Object.fromEntries(list.filter((r) => r[0].trim() && r[2] !== false).map((r) => [r[0].trim(), r[1]]));
    m.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-v],[data-a='kv-del']");
      if (!b) return;
      if (b.dataset.a === "kv-del") { const kv = b.closest("[data-kv]"); rows[kv.dataset.kv].splice(+b.dataset.i, 1); kv.outerHTML = kvHtml(kv.dataset.kv, rows[kv.dataset.kv]); return; }
      const v = b.dataset.v;
      if (v === "save") {
        if (coll) { coll.vars = obj(rows.cvars); dirty = true; await flush(); }
        if (env) await call("env_save", { env, values: obj(rows.evars) });
        closeModal(m);
      } else if (v === "env-new") {
        const name = await inputBox(t("ap_env_new"), t("ap_env_name"), "local");
        if (!name) return;
        const base = st.ports.length ? { base_url: "http://localhost:" + st.ports[0] } : {};
        if (await call("env_save", { env: name, values: base })) { P.env = st.envs.find((n) => n === name) || name; keep(); renderSide(); closeModal(m); varsModal(); }
      } else if (v === "sec-set" || v === "sec-add") {
        const k = v === "sec-add" ? $("#sec-k", m).value.trim() : b.dataset.k;
        const val = v === "sec-add" ? $("#sec-v", m).value : $(`[data-sk="${CSS.escape(k)}"]`, m).value;
        if (await call("secret_set", { key: k, value: val })) { toast(t("ap_secret_saved", { v: k }), "ok"); if (v === "sec-add") { closeModal(m); varsModal(); } }
      } else if (v === "sec-del") {
        if (await call("secret_delete", { key: b.dataset.k })) { closeModal(m); varsModal(); }
      }
    });
  }

  /* ---------------------------------------------------------------- công khai */
  return {
    async show() {
      layout();
      await loadState();
      await loadColl();
    },
    hide() { flush(); },
    escape() { return false; },
  };
})();
