/* Xem diff kiểu VS Code — dùng chung cho diff của task (/api/diff/<task>) và tab Git (/api/git/diff…).
   Dữ liệu từ web_git.diffset_json: file → hunk → dòng {k, o, n, t: [[lớp, chữ]], w: [[đầu, cuối]]} + rows (2 cột). */
"use strict";

window.DiffView = (() => {
  let D = null;   // {ds, file, split, modal, task}

  function wide() { return window.innerWidth >= 1100; }

  /* token tô cú pháp + đoạn chữ đổi (w) → HTML */
  function lineHtml(toks, spans) {
    let pos = 0, out = "";
    const marks = spans || [];
    for (const [cls, text] of toks) {
      let i = 0;
      while (i < text.length) {
        const abs = pos + i;
        const inSpan = marks.find(([a, b]) => abs >= a && abs < b);
        const nextEdge = Math.min(...marks.flatMap(([a, b]) => [a, b]).filter((e) => e > abs), pos + text.length);
        const piece = text.slice(i, nextEdge - pos);
        const h = esc(piece);
        out += cls ? `<span class="tk-${cls}">${inSpan ? `<mark>${h}</mark>` : h}</span>` : inSpan ? `<mark>${h}</mark>` : h;
        i += piece.length || 1;
      }
      pos += text.length;
    }
    return out || "&nbsp;";
  }
  const kindCls = (k) => (k === "+" ? "add" : k === "-" ? "del" : "ctx");

  function fileBody(f) {
    if (f.binary) return `<div class="d-note">${esc(t("diff_binary"))}</div>`;
    if (!f.hunks.length) return `<div class="d-note">${esc(f.status === "R" ? t("diff_renamed") : t("diff_empty"))}</div>`;
    const parts = [];
    f.hunks.forEach((h, hi) => {
      parts.push(`<div class="d-hunk" data-hunk="${hi}">${esc(h.header)}</div>`);
      if (D.split) {
        for (const [l, r] of h.rows) {
          const L = l == null ? null : h.lines[l], R = r == null ? null : h.lines[r];
          const cell = (x, side) => x == null
            ? `<span class="dn"></span><span class="dc blank"></span>`
            : `<span class="dn">${(side === "l" ? x.o : x.n) ?? ""}</span><span class="dc ${x.k === " " ? "ctx" : kindCls(x.k)}">${lineHtml(x.t, x.w)}</span>`;
          parts.push(`<div class="drow split" data-new="${R && R.n != null ? R.n : ""}">${cell(L, "l")}${cell(R, "r")}</div>`);
        }
      } else {
        for (const x of h.lines) {
          parts.push(`<div class="drow uni ${kindCls(x.k)}" data-new="${x.n ?? ""}"><span class="dn">${x.o ?? ""}</span><span class="dn">${x.n ?? ""}</span>
            <span class="dsign">${x.k === " " ? "" : x.k}</span><span class="dc">${lineHtml(x.t, x.w)}</span></div>`);
        }
      }
    });
    if (f.truncated) parts.push(`<div class="d-note">${esc(t("diff_truncated"))}</div>`);
    return parts.join("");
  }

  function statusBadge(st) {
    const c = { A: "done", D: "failed", R: "draft", M: "review" }[st] || "queued";
    return `<span class="fstat s-${c}">${esc(st)}</span>`;
  }

  function render() {
    const ds = D.ds, f = ds.files[D.file];
    const list = ds.files.map((x, i) => `<button class="dfile${i === D.file ? " on" : ""}" data-i="${i}">
      ${statusBadge(x.status)}<span class="dpath"><b>${esc(x.path.split("/").pop())}</b><i>${esc(x.path.includes("/") ? x.path.slice(0, x.path.lastIndexOf("/")) : "")}</i></span>
      <span class="dstat"><em class="a">+${x.added}</em><em class="r">−${x.removed}</em></span></button>`).join("");
    const title = f.old_path && f.old_path !== f.path && f.status === "R" ? `${esc(f.old_path)} → ${esc(f.path)}` : esc(f.path);
    $(".d-files", D.modal).innerHTML = list;
    $(".d-title", D.modal).innerHTML = `${statusBadge(f.status)} ${title} <span class="dstat"><em class="a">+${f.added}</em><em class="r">−${f.removed}</em></span>`;
    $(".d-body", D.modal).innerHTML = `<div class="diff2${D.split ? " is-split" : ""}">${fileBody(f)}</div>`;
    $(".d-body", D.modal).scrollTop = 0;
    $("[data-dact=split]", D.modal).classList.toggle("on", D.split);
  }

  function show(ds, opts = {}) {
    if (ds.error) { toast(ds.error, "warn"); return; }
    D = { ds, file: Math.min(ds.start || 0, ds.files.length - 1), split: wide(), task: opts.task || null };
    const x = D.task && S.state && S.state.tasks.find((y) => y.id === D.task);
    const review = x && ["review", "conflict"].includes(x.status);
    D.modal = openModal(`${modalHead(`Δ ${esc(ds.title)} <span class="dstat big"><em class="a">+${ds.added}</em><em class="r">−${ds.removed}</em></span>`,
      `<span class="d-tools">
        <button class="btn sm ghost" data-dact="prev" title="[">⇡ ${esc(t("hunk_prev"))}</button>
        <button class="btn sm ghost" data-dact="next" title="]">⇣ ${esc(t("hunk_next"))}</button>
        <button class="btn sm ghost" data-dact="split" title="s">⫴ ${esc(t("split_view"))}</button>
        <button class="btn sm ghost" data-dact="code" title="e">✎ ${esc(t("open_in_code"))}</button>
        ${review ? `<button class="btn sm danger" data-action="reject" data-task="${D.task}">✗ ${esc(t("reject"))}</button>
          <button class="btn sm success" data-action="merge" data-task="${D.task}">✓ ${esc(t("merge"))} <kbd>Ctrl+Y</kbd></button>` : ""}
      </span>`)}
      <div class="d-layout"><div class="d-files"></div><div class="d-main"><div class="d-title"></div><div class="d-body"></div></div></div>
      <div class="d-keys">${esc(t("diff_keys"))}</div>`, { box: "xl", onClose: () => { D = null; } });
    D.modal.addEventListener("click", onClick);
    render();
  }

  function hunkTop(dir) {
    const body = $(".d-body", D.modal);
    const hs = $$(".d-hunk", body);
    const cur = body.scrollTop + 4;
    const target = dir > 0 ? hs.find((h) => h.offsetTop > cur) : hs.reverse().find((h) => h.offsetTop < cur - 8);
    if (target) body.scrollTop = target.offsetTop - 2;
  }
  function openInCode() {
    const f = D.ds.files[D.file];
    const body = $(".d-body", D.modal);
    const row = $$(".drow", body).find((r) => r.offsetTop >= body.scrollTop && r.dataset.new);
    const line = row ? +row.dataset.new : null;
    closeModal(D.modal);
    setView("code");
    CodeView.open(f.path, line);
  }
  function onClick(e) {
    const fb = e.target.closest(".dfile");
    if (fb) { D.file = +fb.dataset.i; render(); return; }
    const b = e.target.closest("[data-dact]");
    if (!b) return;
    const a = b.dataset.dact;
    if (a === "split") { D.split = !D.split; render(); }
    if (a === "next") hunkTop(1);
    if (a === "prev") hunkTop(-1);
    if (a === "code") openInCode();
  }
  document.addEventListener("keydown", (e) => {
    if (!D || topModal() !== D.modal || /INPUT|TEXTAREA/.test(e.target.tagName)) return;
    const k = e.key;
    if (k === "n" || k === "j") { D.file = Math.min(D.ds.files.length - 1, D.file + 1); render(); }
    else if (k === "p" || k === "k") { D.file = Math.max(0, D.file - 1); render(); }
    else if (k === "]") hunkTop(1);
    else if (k === "[") hunkTop(-1);
    else if (k === "s") { D.split = !D.split; render(); }
    else if (k === "e") openInCode();
    else if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "y" && D.task) { e.preventDefault(); send("merge", { task: D.task }); closeModal(D.modal); }
    else return;
    e.preventDefault();
  });

  async function load(url, opts) {
    try { show(await (await fetch(url)).json(), opts); } catch (e) { toast(String(e), "error"); }
  }
  return {
    task: (tid) => load(`/api/diff/${tid}`, { task: tid }),
    git: (params) => load("/api/git/diff?" + new URLSearchParams(params)),
    show,
  };
})();
