"""Tab ✅ To-do và 🗒 Ghi chú của TUI — cùng file với web (todos.py, notes.py, lưu ngoài repo).

To-do: danh sách nhóm theo hạn / tag / ưu tiên / thủ công, ô nhập hiểu "#tag !cao @mai 17:00", popup chi tiết
(`TodoEditScreen`), popup Quản lý tag (`TagScreen`). Ghi chú: danh sách bên trái, ô soạn markdown bên phải, tự lưu.
Nạp muộn từ `tui.py` (`from .tui_todo import …` trong compose) nên import ngược `tui` ở đây không vòng."""
from __future__ import annotations

import json
import time
from pathlib import Path

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, OptionList, Select, Static, TextArea
from textual.widgets.option_list import Option

from . import notes, projects, todos
from .i18n import tr
from .tui import (RESET, BaseModal, Btn, ChoiceScreen, ConfirmScreen, PromptScreen, TextAreaVN, TextInput,
                  set_static)

PRI_STYLE = {3: "bold red", 2: "bold yellow", 1: "dim", 0: ""}
DUE_STYLE = {"over": "red", "today": "cyan", "week": "yellow", "later": "dim", "": "dim"}
GROUPS = ("due", "tag", "pri", "manual")


def pri_name(p: int) -> str:
    return (tr("Không"), tr("Thấp"), tr("Vừa"), tr("Cao"))[p if p in todos.PRIORITIES else 0]


def group_name(g: str) -> str:
    return {"due": tr("Hạn"), "tag": tr("Tag"), "pri": tr("Ưu tiên"), "manual": tr("Thủ công")}[g]


def grouped(items: list, tags: list, mode: str, hide_done: bool = False) -> list:
    """[(tiêu đề, kiểu, [việc])] theo chế độ nhóm; việc đã xong gom cuối (trừ chế độ thủ công)."""
    if mode == "manual":
        return [(tr("Việc"), "", [x for x in items if not (hide_done and x.get("done"))])]
    open_ = [x for x in items if not x.get("done")]
    order = {id(x): i for i, x in enumerate(items)}

    def by_due(x):
        return (x.get("due") or "9999", -(x.get("priority") or 0), order[id(x)])
    out: list = []
    if mode == "due":
        names = {"over": "⚠ " + tr("Quá hạn"), "today": "◉ " + tr("Hôm nay"), "week": tr("Tuần này"),
                 "later": tr("Sau này"), "none": tr("Không có hạn")}
        for k in ("over", "today", "week", "later", "none"):
            out.append((names[k], k, sorted([x for x in open_ if todos.bucket(x) == k], key=by_due)))
    elif mode == "tag":
        ids = {t["id"] for t in tags}
        for t in tags:
            out.append(("#" + t["name"], t["color"], sorted([x for x in open_ if t["id"] in (x.get("tags") or [])],
                                                            key=by_due)))
        out.append((tr("Không có tag"), "", sorted([x for x in open_ if not set(x.get("tags") or []) & ids],
                                                   key=by_due)))
    else:
        for p in (3, 2, 1, 0):
            out.append((("!" * p + " " if p else "") + pri_name(p), PRI_STYLE[p],
                        sorted([x for x in open_ if (x.get("priority") or 0) == p], key=by_due)))
    out = [g for g in out if g[2]]
    done = sorted([x for x in items if x.get("done")], key=lambda x: -(x.get("done_at") or 0))
    if done and not hide_done:
        out.append(("✓ " + tr("Đã xong"), "done", done))
    return out


def todo_line(x: dict, tagmap: dict) -> Text:
    t = Text("☑ " if x.get("done") else "☐ ", "green" if x.get("done") else "")
    p = x.get("priority") or 0
    t.append(("!" * p).ljust(3) + " ", PRI_STYLE[p])
    t.append(x["text"], "strike dim" if x.get("done") else "")
    if x.get("desc"):
        t.append(" ≡", "dim")
    for i in x.get("tags") or []:
        if i in tagmap:
            t.append(" #" + tagmap[i]["name"], tagmap[i]["color"])
    label, b = todos.due_label(x)
    if label:
        t.append("  " + label, DUE_STYLE.get(b, "dim"))
    return t


class TodoList(OptionList):
    BINDINGS = [Binding("space", "toggle", tr("Xong/chưa")), Binding("e", "edit", tr("Sửa")),
                Binding("delete,backspace,d", "delete", tr("Xoá")), Binding("shift+up,K", "move(-1)", tr("Lên")),
                Binding("shift+down,J", "move(1)", tr("Xuống")), Binding("c", "clear", tr("Dọn việc đã xong")),
                Binding("t", "tags", tr("Tag")), Binding("u", "due", tr("Hạn")), Binding("p", "priority", tr("Ưu tiên")),
                Binding("g", "group", tr("Nhóm")), Binding("f", "filter", tr("Lọc tag")),
                Binding("h", "hide_done", tr("Ẩn việc xong")), Binding("T", "manage_tags", tr("Quản lý tag"))]

    def _panel(self) -> "TodoPanel":
        return self.parent  # type: ignore[return-value]

    def action_toggle(self) -> None:
        self._panel().act("toggle")

    def action_edit(self) -> None:
        self._panel().start_edit()

    def action_delete(self) -> None:
        self._panel().act("delete")

    def action_move(self, d: int) -> None:
        self._panel().act("move", d)

    def action_clear(self) -> None:
        self._panel().act("clear")

    def action_tags(self) -> None:
        self._panel().ask_tags()

    def action_due(self) -> None:
        self._panel().ask_due()

    def action_priority(self) -> None:
        self._panel().cycle_priority()

    def action_group(self) -> None:
        self._panel().cycle_group()

    def action_filter(self) -> None:
        self._panel().pick_filter()

    def action_hide_done(self) -> None:
        self._panel().toggle_hide_done()

    def action_manage_tags(self) -> None:
        self.app.push_screen(TagScreen(self._panel().root), lambda _r: self._panel().reload(force=True))


class TodoPanel(Vertical):
    """Tab ✅ To-do: việc cần làm của riêng dự án, lưu ngoài repo (todos.py) — dùng chung file với web."""

    DEFAULT_CSS = """
    TodoPanel { padding: 0 1; }
    #todo-input { margin-bottom: 0; }
    #todo-bar { height: 1; color: $text-muted; margin-bottom: 1; }
    #todo-list { height: 1fr; border: none; }
    #todo-foot { height: auto; color: $text-muted; }
    """

    def __init__(self, root: Path, **kw):
        super().__init__(**kw)
        self.root, self.editing, self._sig = root, None, None
        self.group, self.tag_filter, self.hide_done = "due", None, False

    def compose(self) -> ComposeResult:
        yield TextInput(id="todo-input", placeholder=tr("Thêm việc…  #tag  !cao  @mai 17:00  — Enter"))
        yield Static(id="todo-bar")
        yield TodoList(id="todo-list")
        yield Static(id="todo-foot")

    def items(self) -> list:
        return todos.load(self.root)

    def current(self) -> dict | None:
        ol = self.query_one(TodoList)
        o = ol.get_option_at_index(ol.highlighted) if ol.highlighted is not None and ol.option_count else None
        return next((x for x in self.items() if o and o.id and o.id == f"t{x.get('id')}"), None)

    def reload(self, focus_id: int | None = None, force: bool = False) -> None:
        items, tags = self.items(), todos.load_tags(self.root)
        tagmap = {t["id"]: t for t in tags}
        if self.tag_filter is not None and self.tag_filter not in tagmap:
            self.tag_filter = None
        shown = [x for x in items if self.tag_filter is None or self.tag_filter in (x.get("tags") or [])]
        ol = self.query_one(TodoList)
        # nhãn hạn đổi theo giờ (quá hạn, hôm nay): vẽ lại mỗi phút dù dữ liệu không đổi
        sig = json.dumps([items, tags, self.group, self.tag_filter, self.hide_done, time.strftime("%H:%M")],
                         ensure_ascii=False)
        if sig != self._sig or force:
            self._sig = sig
            keep = focus_id if focus_id is not None else (self.current() or {}).get("id")
            ol.clear_options()
            for title, kind, rows in grouped(shown, tags, self.group, self.hide_done):
                head = Text(f"{title}  ", "bold " + (DUE_STYLE.get(kind) if kind in ("over", "today") else
                                                    kind if kind.startswith("#") or " " in kind else ""))
                head.append(str(len(rows)), "dim")
                ol.add_option(Option(head, disabled=True))
                for x in rows:
                    ol.add_option(Option(todo_line(x, tagmap), id=f"t{x['id']}"))
            if not shown:
                ol.add_option(Option(Text(tr("Chưa có việc nào") if not items else tr("Không có việc nào khớp bộ lọc"),
                                          "dim"), disabled=True))
            ids = [ol.get_option_at_index(i).id for i in range(ol.option_count)]
            want = f"t{keep}" if keep is not None else None
            first = next((i for i, v in enumerate(ids) if v), None)  # bỏ qua tiêu đề nhóm (id None)
            ol.highlighted = ids.index(want) if want and want in ids else first
        bar = Text(tr("Nhóm theo: {g}", g=group_name(self.group)), "")
        if self.tag_filter is not None:
            bar.append("  ·  " + tr("Lọc tag:") + " ", "dim")
            bar.append("#" + tagmap[self.tag_filter]["name"], tagmap[self.tag_filter]["color"])
        if self.hide_done:
            bar.append("  ·  " + tr("Ẩn việc đã xong"), "dim")
        over = sum(1 for x in items if todos.bucket(x) == "over")
        if over:
            bar.append("  ·  " + tr("{n} việc quá hạn", n=over), "red")
        set_static(self.query_one("#todo-bar", Static), bar)
        left = sum(1 for x in items if not x.get("done"))
        foot = Text(tr("{n} việc chưa xong", n=left) + "  ·  ", "bold" if left else "")
        foot.append(tr("Enter chi tiết · Space xong · e sửa · t tag · u hạn · p ưu tiên · g nhóm · f lọc tag · h ẩn "
                       "việc xong · T quản lý tag · d xoá · Shift+↑↓ đổi thứ tự · c dọn việc xong"), "dim")
        path = str(todos.path_for(self.root)).replace(str(Path.home()), "~", 1)
        foot.append("\n" + tr("Lưu riêng cho dự án này ở {path} — ngoài thư mục dự án, dùng chung tag với Ghi chú.",
                               path=path), "dim")
        set_static(self.query_one("#todo-foot", Static), foot)

    def run_op(self, action: str, data: dict) -> None:
        try:
            todos.apply(self.root, action, data)
        except ValueError:
            self.app.notify(tr("Nhập nội dung việc cần làm"), severity="warning")
        self.reload(focus_id=data.get("id") if action != "delete" else None)

    def act(self, action: str, d: int = 0) -> None:
        x = self.current()
        if action != "clear" and not x:
            return
        data: dict = {"id": x and x["id"]}
        if action == "move":
            items = self.items()
            data["to"] = max(0, items.index(x) + d)
        self.run_op(action, data)

    def ask_tags(self) -> None:
        x = self.current()
        if not x:
            return
        cur = ", ".join(todos.tag_names(self.root, x.get("tags")))
        names = ", ".join(t["name"] for t in todos.load_tags(self.root))

        def done(v) -> None:
            if v is not None:
                self.run_op("edit", {"id": x["id"], "tags": [s for s in v.replace("#", " ").replace(",", " ").split()]})
        self.app.push_screen(PromptScreen(tr("Tag của việc"), cur, placeholder="bug, ui",
                                          hint=tr("Cách nhau bằng dấu phẩy · tag chưa có thì tạo mới · trống = bỏ hết "
                                                  "tag · có sẵn: {v}", v=names or "—"), allow_empty=True), done)

    def ask_due(self) -> None:
        x = self.current()
        if not x:
            return

        def done(v) -> None:
            if v is None:
                return
            due = todos.parse_due(v)
            if due is None:
                self.app.notify(tr("Không hiểu hạn “{v}” — ví dụ: mai, t6, 24/10 17:00", v=v), severity="warning")
                return
            self.run_op("edit", {"id": x["id"], "due": due})
        self.app.push_screen(PromptScreen(tr("Hạn của việc"), (x.get("due") or "").replace("T", " "),
                                          placeholder=tr("mai 17:00"),
                                          hint=tr("hôm nay · mai · t2…cn · tuần sau · 24/10 · 24/10 17:00 · 17h — "
                                                  "trống = bỏ hạn"), allow_empty=True), done)

    def cycle_priority(self) -> None:
        x = self.current()
        if x:
            self.run_op("edit", {"id": x["id"], "priority": ((x.get("priority") or 0) + 1) % 4})

    def cycle_group(self) -> None:
        self.group = GROUPS[(GROUPS.index(self.group) + 1) % len(GROUPS)]
        self.reload(force=True)

    def toggle_hide_done(self) -> None:
        self.hide_done = not self.hide_done
        self.reload(force=True)

    def pick_filter(self) -> None:
        tags = todos.load_tags(self.root)
        if not tags:
            self.app.notify(tr("Chưa có tag nào — gõ #tag khi thêm việc"))
            return
        cur = next((t["name"] for t in tags if t["id"] == self.tag_filter), "")

        def done(v) -> None:
            if v is None:
                return
            self.tag_filter = None if v == RESET else next((t["id"] for t in tags if t["name"] == v), None)
            self.reload(force=True)
        self.app.push_screen(ChoiceScreen(tr("Lọc theo tag"), [t["name"] for t in tags], cur, tr("tất cả")), done)

    def start_edit(self) -> None:
        x = self.current()
        if not x:
            return
        self.editing = x["id"]
        inp = self.query_one("#todo-input", TextInput)
        inp.value = x["text"]
        inp.placeholder = tr("Sửa việc — Enter lưu, Esc huỷ")
        inp.focus()

    def stop_edit(self) -> None:
        self.editing = None
        inp = self.query_one("#todo-input", TextInput)
        inp.value = ""
        inp.placeholder = tr("Thêm việc…  #tag  !cao  @mai 17:00  — Enter")

    def open_detail(self) -> None:
        x = self.current()
        if not x:
            return

        def done(d) -> None:
            if not d:
                return
            if d.pop("lead", False):
                self.app.start_goal(x["text"] + ("\n\n" + d["desc"] if d.get("desc") else ""))
            self.run_op("edit", dict(d, id=x["id"]))
        self.app.push_screen(TodoEditScreen(self.root, x), done)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        text = event.value.strip()
        if self.editing is not None:
            if text:
                todos.apply(self.root, "edit", {"id": self.editing, "text": text})
            gid = self.editing
            self.stop_edit()
            self.reload(focus_id=gid)
            self.query_one(TodoList).focus()
            return
        if text:
            try:
                todos.apply(self.root, "add", {"text": text})
            except ValueError:
                self.app.notify(tr("Nhập nội dung việc cần làm"), severity="warning")
                return
            event.input.value = ""
            self.reload(focus_id=max(x["id"] for x in self.items()))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.open_detail()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape" and self.editing is not None:
            event.stop()
            self.stop_edit()
            self.query_one(TodoList).focus()


class TodoEditScreen(BaseModal):
    """Chi tiết một việc: tiêu đề, ưu tiên, hạn (gõ được "mai 17h"), tag, mô tả markdown. Trả dict các khoá đổi
    (kèm lead=True khi bấm Giao cho trưởng nhóm) hoặc None."""

    BINDINGS = [Binding("ctrl+s", "save", tr("Lưu"), priority=True)]
    DEFAULT_CSS = """
    TodoEditScreen { align: center middle; }
    #td-box { width: 110; max-width: 100%; height: auto; max-height: 95%; border: round $primary 70%;
              background: $surface; padding: 0 1; }
    #td-box .f-section { height: 1; margin-top: 1; color: $text-muted; text-style: bold; }
    #td-row { height: auto; }
    #td-row > Vertical { width: 1fr; height: auto; margin-right: 1; }
    #td-desc { height: 12; }
    #td-buttons { height: auto; align: right middle; margin-top: 1; }
    #td-buttons Button { margin-left: 2; }
    """

    def __init__(self, root: Path, item: dict):
        super().__init__()
        self.root, self.item = root, dict(item)

    def compose(self) -> ComposeResult:
        x = self.item
        with Vertical(id="td-box"):
            yield self.title_bar(tr("Việc #{id}", id=x["id"]))
            yield Static(tr("Tiêu đề"), classes="f-section")
            yield TextInput(x["text"], id="td-text")
            with Horizontal(id="td-row"):
                with Vertical():
                    yield Static(tr("Ưu tiên"), classes="f-section")
                    yield Select([(("!" * p + " " if p else "") + pri_name(p), p) for p in (0, 1, 2, 3)],
                                 value=x.get("priority") or 0, allow_blank=False, id="td-pri")
                with Vertical():
                    yield Static(tr("Hạn — trống = không hạn"), classes="f-section")
                    yield TextInput((x.get("due") or "").replace("T", " "), placeholder=tr("mai 17:00"), id="td-due")
                with Vertical():
                    yield Static(tr("Tag — cách nhau bằng dấu phẩy"), classes="f-section")
                    yield TextInput(", ".join(todos.tag_names(self.root, x.get("tags"))), placeholder="bug, ui",
                                    id="td-tags")
            yield Static(tr("Mô tả (markdown)"), classes="f-section")
            yield TextAreaVN(x.get("desc") or "", id="td-desc", soft_wrap=True, show_line_numbers=False)
            with Horizontal(id="td-buttons"):
                yield Btn(tr("▶ Giao cho trưởng nhóm"), id="td-lead")
                yield Btn(tr("Huỷ"), id="td-cancel")
                yield Btn(tr("Lưu (Ctrl+S)"), id="td-save", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#td-text").focus()
        self.call_after_refresh(self.mark_clean)

    def form_values(self) -> tuple:
        return super().form_values() + (self.query_one("#td-desc", TextArea).text,)

    def values(self) -> dict | None:
        text = self.query_one("#td-text", Input).value.strip()
        if not text:
            self.notify(tr("Nhập nội dung việc cần làm"), severity="warning")
            return None
        raw = self.query_one("#td-due", Input).value.strip()
        due = todos.parse_due(raw)
        if due is None:
            self.notify(tr("Không hiểu hạn “{v}” — ví dụ: mai, t6, 24/10 17:00", v=raw), severity="warning")
            return None
        tags = self.query_one("#td-tags", Input).value.replace("#", " ").replace(",", " ").split()
        return {"text": text, "priority": self.query_one("#td-pri", Select).value, "due": due, "tags": tags,
                "desc": self.query_one("#td-desc", TextArea).text}

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_save()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "td-save":
            self.action_save()
        elif event.button.id == "td-lead":
            v = self.values()
            if v:
                self.dismiss(dict(v, lead=True))
        elif event.button.id == "td-cancel":
            self.close()

    def action_save(self) -> None:
        v = self.values()
        if v:
            self.dismiss(v)


class TagScreen(BaseModal):
    """Quản lý tag (dùng chung To-do và Ghi chú): a thêm · r đổi tên · c đổi màu · m gộp vào tag khác · d xoá ·
    Shift+↑↓ đổi thứ tự."""

    BINDINGS = [Binding("a", "add", tr("Thêm"), show=False), Binding("r", "rename", show=False),
                Binding("c", "recolor", show=False), Binding("m", "merge", show=False),
                Binding("d,delete", "delete", show=False), Binding("shift+up", "move(-1)", show=False),
                Binding("shift+down", "move(1)", show=False)]
    DEFAULT_CSS = """
    TagScreen { align: center middle; }
    #tags-box { width: 96; max-width: 100%; height: auto; max-height: 90%; border: round $primary 70%;
                background: $surface; padding: 0 1; }
    #tags-list { height: auto; max-height: 24; margin-top: 1; }
    """

    def __init__(self, root: Path):
        super().__init__()
        self.root = root

    def compose(self) -> ComposeResult:
        with Vertical(id="tags-box"):
            yield self.title_bar(tr("Quản lý tag"))
            yield Static(Text(tr("Dùng chung cho To-do và Ghi chú của dự án này. Xoá tag chỉ gỡ tag khỏi việc và ghi "
                                 "chú, không xoá chúng."), "dim"))
            yield OptionList(id="tags-list")
            yield Static(Text(tr("a thêm · r đổi tên · c đổi màu · m gộp vào tag khác · d xoá · Shift+↑↓ đổi thứ tự "
                                 "· Esc đóng"), "dim"))

    def on_mount(self) -> None:
        self.refill()
        self.query_one("#tags-list", OptionList).focus()

    def refill(self, keep: int | None = None) -> None:
        lst = self.query_one("#tags-list", OptionList)
        cur = keep if keep is not None else (self.tag() or {}).get("id")
        lst.clear_options()
        counts = todos.tag_counts(self.root)
        tags = todos.load_tags(self.root)
        for t in tags:
            c = counts.get(t["id"], {})
            row = Text("■ ", t["color"])
            row.append(t["name"].ljust(24), t["color"])
            row.append(tr("{a} việc · {b} ghi chú · {c} chưa xong", a=c.get("todos", 0), b=c.get("notes", 0),
                          c=c.get("open", 0)), "dim")
            lst.add_option(Option(row, id=f"g{t['id']}"))
        if not tags:
            lst.add_option(Option(Text(tr("Chưa có tag nào — bấm a để thêm"), "dim"), disabled=True))
        ids = [f"g{t['id']}" for t in tags]
        lst.highlighted = ids.index(f"g{cur}") if f"g{cur}" in ids else (0 if ids else None)

    def tag(self) -> dict | None:
        lst = self.query_one("#tags-list", OptionList)
        if lst.highlighted is None or not lst.option_count:
            return None
        oid = lst.get_option_at_index(lst.highlighted).id or ""
        return next((t for t in todos.load_tags(self.root) if f"g{t['id']}" == oid), None)

    def run_op(self, action: str, data: dict, keep: int | None = None) -> None:
        try:
            todos.apply_tag(self.root, action, data)
        except ValueError as e:
            self.notify(tr("Đã có tag “{name}”", name=todos.norm_tag(data.get("name"))) if str(e) == "exists"
                        else tr("Nhập tên tag"), severity="warning")
        self.refill(keep)

    def action_add(self) -> None:
        def done(v) -> None:
            if v:
                self.run_op("add", {"name": v})
                t = next((t for t in todos.load_tags(self.root) if t["name"] == todos.norm_tag(v)), None)
                self.refill(t and t["id"])
        self.app.push_screen(PromptScreen(tr("Thêm tag"), placeholder="hotfix"), done)

    def action_rename(self) -> None:
        t = self.tag()
        if t:
            self.app.push_screen(PromptScreen(tr("Đổi tên tag"), t["name"]),
                                 lambda v: v and self.run_op("rename", {"id": t["id"], "name": v}, keep=t["id"]))

    def action_recolor(self) -> None:
        t = self.tag()
        if t:
            pal = todos.PALETTE
            nxt = pal[(pal.index(t["color"]) + 1) % len(pal)] if t["color"] in pal else pal[0]
            self.run_op("recolor", {"id": t["id"], "color": nxt}, keep=t["id"])

    def action_merge(self) -> None:
        t = self.tag()
        others = [x for x in todos.load_tags(self.root) if t and x["id"] != t["id"]]
        if not t or not others:
            return

        def done(v) -> None:
            into = next((x["id"] for x in others if x["name"] == v), None)
            if into:
                self.run_op("merge", {"id": t["id"], "into": into}, keep=into)
        self.app.push_screen(ChoiceScreen(tr("Gộp “{a}” vào", a=t["name"]), [x["name"] for x in others], "",
                                          tr("(huỷ)")), done)

    def action_delete(self) -> None:
        t = self.tag()
        if t:
            self.app.push_screen(ConfirmScreen(tr("Xoá tag"), tr("Xoá tag “{v}”? Việc và ghi chú vẫn còn, chỉ gỡ tag.",
                                                                 v=t["name"]), yes=tr("Xoá")),
                                 lambda ok: ok and self.run_op("delete", {"id": t["id"]}))

    def action_move(self, by: int) -> None:
        t = self.tag()
        if t:
            tags = todos.load_tags(self.root)
            i = next(n for n, x in enumerate(tags) if x["id"] == t["id"])
            self.run_op("move", {"id": t["id"], "to": max(0, i + by)}, keep=t["id"])


class NoteList(OptionList):
    BINDINGS = [Binding("n", "new", tr("Ghi chú mới")), Binding("p", "pin", tr("Ghim")),
                Binding("delete,d", "delete", tr("Xoá"))]

    def action_new(self) -> None:
        self.parent.parent.new_note()  # type: ignore[union-attr]

    def action_pin(self) -> None:
        self.parent.parent.pin()  # type: ignore[union-attr]

    def action_delete(self) -> None:
        self.parent.parent.delete()  # type: ignore[union-attr]


class NotesPanel(Horizontal):
    """Tab 🗒 Ghi chú: danh sách (lọc theo chữ hoặc #tag) + ô soạn markdown, tự lưu ~1 giây sau phím cuối, Ctrl+S lưu
    ngay. Lưu kèm base như web: bản trên đĩa mới hơn (web vừa sửa) thì hỏi ghi đè hay tải lại."""

    BINDINGS = [Binding("ctrl+s", "save", tr("Lưu"), show=False, priority=True),
                Binding("ctrl+n", "new", tr("Ghi chú mới"), show=False),
                Binding("alt+t", "to_todo", tr("Tạo to-do từ dòng"), show=False)]
    DEFAULT_CSS = """
    NotesPanel { padding: 0 1; }
    #notes-side { width: 44; height: 1fr; margin-right: 1; }
    #notes-filter { margin-bottom: 0; }
    #notes-list { height: 1fr; border: none; }
    #notes-main { width: 1fr; height: 1fr; }
    #note-title { text-style: bold; }
    #note-body { height: 1fr; }
    #note-foot { height: auto; color: $text-muted; }
    """

    def __init__(self, root: Path, **kw):
        super().__init__(**kw)
        self.root = root
        self.cur: dict | None = None
        self.dirty, self._sig, self._loading = False, None, False
        self._timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="notes-side"):
            yield TextInput(id="notes-filter", placeholder=tr("Tìm… (#tag để lọc)"))
            yield NoteList(id="notes-list")
        with Vertical(id="notes-main"):
            yield TextInput(id="note-title", placeholder=tr("Tiêu đề"))
            yield TextInput(id="note-tags", placeholder=tr("Tag — cách nhau bằng dấu phẩy"))
            yield TextAreaVN("", id="note-body", soft_wrap=True, show_line_numbers=False)
            yield Static(id="note-foot")

    def on_mount(self) -> None:
        self.show_editor(False)

    def shown(self) -> None:
        """Vừa mở tab: đọc lại, focus ô soạn nếu đang mở một ghi chú, không thì danh sách / ô tìm."""
        self.reload()
        if self.cur is not None:
            self.query_one("#note-body").focus()
        else:
            self.query_one("#notes-list" if notes.load(self.root) else "#notes-filter").focus()

    def show_editor(self, on: bool) -> None:
        for wid in ("#note-title", "#note-tags", "#note-body"):
            self.query_one(wid).display = on

    # ---------------------------------------------------------------- danh sách
    def reload(self, force: bool = False) -> None:
        items, tags = notes.summaries(self.root), todos.load_tags(self.root)
        tagmap = {t["id"]: t for t in tags}
        q = self.query_one("#notes-filter", Input).value.strip().lower()
        sig = json.dumps([items, tags, q], ensure_ascii=False)
        lst = self.query_one(NoteList)
        if sig != self._sig or force:
            self._sig = sig
            keep = (self.current_id() or (self.cur or {}).get("id"))
            words = q.split()
            shown = [n for n in items if all(
                (w[1:] in [tagmap[i]["name"] for i in n["tags"] if i in tagmap]) if w.startswith("#") and len(w) > 1
                else w in (n["title"] + " " + n["snip"]).lower() for w in words)]
            lst.clear_options()
            for n in shown:
                t = Text("📌 " if n["pinned"] else "", "")
                t.append(n["title"] or tr("Ghi chú không tên"), "bold")
                for i in n["tags"]:
                    if i in tagmap:
                        t.append(" #" + tagmap[i]["name"], tagmap[i]["color"])
                if n["snip"]:
                    t.append("\n" + n["snip"][:80], "dim")
                lst.add_option(Option(t, id=f"n{n['id']}"))
            if not shown:
                lst.add_option(Option(Text(tr("Chưa có ghi chú nào — bấm n để tạo") if not items
                                           else tr("Không có ghi chú khớp"), "dim"), disabled=True))
            ids = [f"n{n['id']}" for n in shown]
            lst.highlighted = ids.index(f"n{keep}") if f"n{keep}" in ids else (0 if ids else None)
        # web vừa sửa ghi chú đang mở mà ở đây chưa gõ gì: nạp lại bản mới
        if self.cur and not self.dirty:
            s = next((n for n in items if n["id"] == self.cur["id"]), None)
            if s is None:
                self.open_note(None)
            elif (s["updated"] or 0) > (self.cur.get("updated") or 0) + 1e-6:
                self.open_note(self.cur["id"])
        self.foot()

    def current_id(self) -> int | None:
        lst = self.query_one(NoteList)
        if lst.highlighted is None or not lst.option_count:
            return None
        oid = lst.get_option_at_index(lst.highlighted).id or ""
        return int(oid[1:]) if oid.startswith("n") else None

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()
        nid = self.current_id()
        if nid is not None and (not self.cur or self.cur["id"] != nid):
            self.open_note(nid)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.query_one("#note-body").focus()

    # ---------------------------------------------------------------- soạn + lưu
    def open_note(self, nid: int | None) -> None:
        if self.dirty:
            self.action_save()
        n = notes.get(self.root, nid) if nid is not None else None
        self.cur = n
        self.dirty = False
        self._loading = True
        try:
            self.show_editor(bool(n))
            if n:
                self.query_one("#note-title", Input).value = n.get("title") or ""
                self.query_one("#note-tags", Input).value = ", ".join(todos.tag_names(self.root, n.get("tags")))
                self.query_one("#note-body", TextArea).load_text(n.get("body") or "")
        finally:
            self.call_after_refresh(self._loaded)
        self.foot()

    def _loaded(self) -> None:
        self._loading = False

    def changed(self) -> None:
        if self._loading or not self.cur:
            return
        self.dirty = True
        self.foot()
        if self._timer:
            self._timer.stop()
        self._timer = self.set_timer(1.0, self.action_save)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "notes-filter":
            event.stop()
            self.reload(force=True)
        elif event.input.id in ("note-title", "note-tags"):
            event.stop()
            self.changed()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "note-body":
            self.changed()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if event.input.id == "notes-filter":
            self.query_one(NoteList).focus()
        elif event.input.id == "note-title":
            self.query_one("#note-tags").focus()
        elif event.input.id == "note-tags":
            self.action_save()
            self.query_one("#note-body").focus()

    def action_save(self, force: bool = False) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None
        if not self.cur or not (self.dirty or force):
            return
        tags = self.query_one("#note-tags", Input).value.replace("#", " ").replace(",", " ").split()
        data = {"id": self.cur["id"], "title": self.query_one("#note-title", Input).value,
                "body": self.query_one("#note-body", TextArea).text, "tags": tags, "base": self.cur.get("updated"),
                "force": force}
        try:
            n = notes.apply(self.root, "save", data)
        except notes.Conflict:
            self.dirty = False  # đừng tự lưu lại trong lúc hỏi
            nid = self.cur["id"]

            def done(ok) -> None:
                if ok:
                    self.dirty = True
                    self.action_save(force=True)
                else:
                    self.open_note(nid)
            self.app.push_screen(ConfirmScreen(tr("Ghi chú vừa được sửa ở nơi khác"),
                                               tr("Bản trên máy mới hơn bản đang sửa ở đây. Ghi đè bằng bản ở đây? "
                                                  "(Huỷ = tải lại bản mới)"), yes=tr("Ghi đè")), done)
            return
        if n:
            self.cur = n
        self.dirty = False
        self.reload()
        self.foot()

    def foot(self) -> None:
        f = Text()
        if self.cur:
            f.append(tr("● Chưa lưu") if self.dirty else tr("● Đã lưu {t}", t=time.strftime(
                "%H:%M", time.localtime(self.cur.get("updated") or time.time()))), "yellow" if self.dirty else "green")
            f.append("  ·  " + tr("{n} ký tự", n=len(self.query_one("#note-body", TextArea).text)), "dim")
            f.append("  ·  ", "dim")
        f.append(tr("n mới · p ghim · d xoá · Enter soạn · Ctrl+S lưu · Alt+T tạo to-do từ dòng đang chọn · tự lưu khi "
                    "gõ"), "dim")
        f.append("\n" + projects.shorten(notes.path_for(self.root)), "dim")
        set_static(self.query_one("#note-foot", Static), f)

    def action_new(self) -> None:
        self.new_note()

    def new_note(self, title: str = "") -> None:
        if self.dirty:
            self.action_save()
        n = notes.apply(self.root, "add", {"title": title})
        self.query_one("#notes-filter", Input).value = ""
        self.reload(force=True)
        lst = self.query_one(NoteList)
        ids = [lst.get_option_at_index(i).id for i in range(lst.option_count)]
        if f"n{n['id']}" in ids:
            lst.highlighted = ids.index(f"n{n['id']}")
        self.open_note(n["id"])
        self.query_one("#note-title" if not title else "#note-body").focus()

    def pin(self) -> None:
        nid = self.current_id()
        if nid is not None:
            notes.apply(self.root, "pin", {"id": nid})
            self.reload(force=True)

    def delete(self) -> None:
        nid = self.current_id()
        n = notes.get(self.root, nid) if nid is not None else None
        if not n:
            return

        def done(ok) -> None:
            if ok:
                if self.cur and self.cur["id"] == nid:
                    self.dirty = False
                    self.open_note(None)
                notes.apply(self.root, "delete", {"id": nid})
                self.reload(force=True)
        self.app.push_screen(ConfirmScreen(tr("Xoá ghi chú"), tr("Xoá ghi chú “{v}”?",
                                                                 v=notes.title_of(n) or tr("Ghi chú không tên")),
                                           yes=tr("Xoá")), done)

    def action_to_todo(self) -> None:
        """Dòng đang chọn (hoặc dòng có con trỏ) thành việc mới, mang tag của ghi chú."""
        if not self.cur:
            return
        body = self.query_one("#note-body", TextArea)
        text = body.selected_text or body.document.get_line(body.cursor_location[0])
        import re
        lines = [re.sub(r"^\s*([-*+]\s+(\[[ xX]\]\s+)?|\d+[.)]\s+|#+\s+)", "", ln).strip() for ln in text.splitlines()]
        lines = [ln for ln in lines if ln][:30]
        for ln in lines:
            notes.apply(self.root, "to_todo", {"id": self.cur["id"], "text": ln})
        if lines:
            self.app.notify(tr("✅ Đã thêm {n} việc vào To-do", n=len(lines)))
