/* Tab ✅ To-do — việc cần làm của riêng dự án này. Server lưu ngoài repo (ateam/todos.py) và gửi danh sách trong
   ảnh chụp trạng thái (S.state.todos), nên mọi tab trình duyệt thấy cùng một danh sách. Bấm đúp để sửa, kéo để
   đổi thứ tự. */
"use strict";

window.TodoView = (() => {
  let editing = null, dragId = null, sig = "";
  const el = () => $("#todo");
  const items = () => (S.state && S.state.todos) || [];
  const op = (action, data) => send("todo", Object.assign({ action }, data || {}));

  function layout() {
    if ($("#todo-add")) return;
    el().innerHTML = `
      <div class="todo-box">
        <input class="field one" id="todo-add" placeholder="${esc(t("todo_ph"))}" autocomplete="off" maxlength="500">
        <div class="todo-list" id="todo-list"></div>
        <div class="todo-foot"><span id="todo-left"></span><span style="flex:1"></span>
          <button class="btn sm ghost" id="todo-clear">${esc(t("todo_clear"))}</button></div>
        <div class="muted small">${esc(t("todo_where", { path: S.meta.todo_file || "" }))}</div>
      </div>`;
    $("#todo-add").addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.isComposing || !e.target.value.trim()) return;
      op("add", { text: e.target.value });
      e.target.value = "";
    });
    $("#todo-clear").addEventListener("click", () => op("clear"));
    const list = $("#todo-list");
    list.addEventListener("click", (e) => {
      const row = e.target.closest("[data-id]");
      if (!row) return;
      if (e.target.closest("[data-del]")) op("delete", { id: +row.dataset.id });
      else if (e.target.closest("input[type=checkbox]")) op("toggle", { id: +row.dataset.id });
    });
    list.addEventListener("dblclick", (e) => {
      const row = e.target.closest("[data-id]");
      if (row && e.target.closest(".todo-text")) startEdit(+row.dataset.id);
    });
    list.addEventListener("dragstart", (e) => { const r = e.target.closest("[data-id]"); dragId = r ? +r.dataset.id : null; });
    list.addEventListener("dragover", (e) => { if (dragId != null) e.preventDefault(); });
    list.addEventListener("drop", (e) => {
      const r = e.target.closest("[data-id]");
      if (dragId == null || !r) return;
      e.preventDefault();
      const to = items().findIndex((x) => x.id === +r.dataset.id);
      if (+r.dataset.id !== dragId && to >= 0) op("move", { id: dragId, to });
      dragId = null;
    });
  }

  function startEdit(id) {
    const x = items().find((y) => y.id === id), row = $(`#todo-list [data-id="${id}"]`);
    if (!x || !row) return;
    editing = id;
    const span = $(".todo-text", row);
    span.innerHTML = `<input class="field one todo-edit" value="${esc(x.text)}" maxlength="500">`;
    const inp = $("input", span);
    inp.focus(); inp.select();
    const done = (keep) => {
      if (editing !== id) return;
      editing = null;
      if (keep && inp.value.trim() && inp.value.trim() !== x.text) op("edit", { id, text: inp.value });
      sig = ""; render();
    };
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing) done(true);
      if (e.key === "Escape") { e.stopPropagation(); done(false); }
    });
    inp.addEventListener("blur", () => done(true));
  }

  function render() {
    const nav = $("#count-todo"), left = items().filter((x) => !x.done).length;
    if (nav) nav.textContent = left || "";
    if (S.view !== "todo" || editing != null) return;
    layout();
    const s = JSON.stringify(items());
    if (s === sig) return;
    sig = s;
    $("#todo-list").innerHTML = items().map((x) => `
      <div class="todo-item${x.done ? " done" : ""}" data-id="${x.id}" draggable="true">
        <span class="todo-grip" aria-hidden="true">⋮⋮</span>
        <input type="checkbox" ${x.done ? "checked" : ""}>
        <span class="todo-text" title="${esc(t("todo_edit"))}">${mdInline(x.text)}</span>
        <button class="icon-btn todo-x" data-del title="${esc(t("todo_del"))}"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
      </div>`).join("") || `<div class="col-empty">${esc(t("todo_empty"))}</div>`;
    $("#todo-left").textContent = t("todo_left", { n: left });
    $("#todo-clear").disabled = !items().some((x) => x.done);
  }

  return { render, show() { sig = ""; render(); const a = $("#todo-add"); if (a) a.focus(); } };
})();
