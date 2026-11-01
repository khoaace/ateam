"""Tab 🛰 API của TUI — bản rút gọn của trang API trên web, cùng file `.ateam/api/` (apiclient.py).

Bên trái: collection, môi trường, danh sách request, ＋ Request, ▶ Chạy hết. Bên phải: method + URL (Enter = Gửi),
tên, các tab Params / Headers / Body / Auth / Kiểm tra (bảng khoá–giá trị viết thành dòng chữ: "Khoá: giá trị" cho
header, "khoá=giá trị" cho params / form, "#" đầu dòng = tắt), response (JSON tô màu, assert) và 🛠 giao trưởng nhóm
sửa. Tự lưu ~0,8 giây sau phím cuối như web; web sửa cùng file thì đọc lại (khi ở đây chưa gõ gì).
Không có: ✨ quét code, nhập Postman/OpenAPI, popup biến/secret — dùng web hoặc `ateam api import`.
Nạp muộn từ `tui.py` (trong compose) nên import ngược `tui` ở đây không vòng."""
from __future__ import annotations

import json
from pathlib import Path

from rich.json import JSON
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, OptionList, Select, Static, TabbedContent, TabPane, TextArea
from textual.widgets.option_list import Option

from . import apiclient as A
from .i18n import tr
from .tui import Btn, ReflowLog, TextAreaVN, TextInput, set_static

METHOD_STYLE = {"GET": "green", "POST": "yellow", "PUT": "cyan", "PATCH": "cyan", "DELETE": "red"}


def rows_to_text(rows, sep: str) -> str:
    """[[k, v, bật], …] -> dòng "k<sep>v" ("# " đầu dòng = tắt)."""
    return "\n".join(("" if (len(r) < 3 or r[2]) else "# ") + f"{r[0]}{sep}{r[1]}" for r in rows or [])


def text_to_rows(text: str, sep: str) -> list:
    out = []
    for ln in text.splitlines():
        on = not ln.lstrip().startswith("#")
        ln = ln.lstrip().lstrip("#").strip() if not on else ln.strip()
        if not ln:
            continue
        k, _, v = ln.partition(sep)
        if k.strip():
            out.append([k.strip(), v.strip(), on])
    return out


class ApiList(OptionList):
    BINDINGS = [Binding("n", "new", tr("Request mới")), Binding("delete,d", "delete", tr("Xoá"))]

    def action_new(self) -> None:
        self.parent.parent.new_request()  # type: ignore[union-attr]

    def action_delete(self) -> None:
        self.parent.parent.delete_request()  # type: ignore[union-attr]


class ApiPanel(Horizontal):
    BINDINGS = [Binding("ctrl+s", "save", tr("Lưu"), show=False, priority=True)]
    DEFAULT_CSS = """
    ApiPanel { padding: 0 1; }
    #api-side { width: 40; height: 1fr; margin-right: 1; }
    #api-side Select { margin-bottom: 0; }
    #api-list { height: 1fr; border: none; }
    #api-side-btns, #api-urlrow, #api-resp-head { height: auto; }
    #api-foot { height: auto; color: $text-muted; }
    #api-main { width: 1fr; height: 1fr; }
    #api-method { width: 14; }
    #api-urlrow Button { margin-top: 1; }
    #api-url { width: 1fr; }
    #api-tabs { height: 14; }
    #api-tabs TextArea { height: 1fr; }
    #api-asserts, #api-extract { border: round $panel-lighten-2; border-title-color: $text-muted; }
    #api-tabs Select { width: 30; }
    #api-status { width: 1fr; padding: 0 1; }
    #api-resp { height: 1fr; border: none; }
    """

    def __init__(self, root: Path, **kw):
        super().__init__(**kw)
        self.root = root
        self.coll: dict | None = None
        self.coll_name, self.env, self.cur_id = "", "", None
        self.results: dict = {}
        self.dirty, self._loading, self._timer, self._mtime = False, False, None, None
        self._quiet_sel = False  # đang đặt lại ô chọn collection / môi trường (vòng làm mới) — không phải người dùng chọn

    def compose(self) -> ComposeResult:
        with Vertical(id="api-side"):
            yield Select([], id="api-coll", prompt=tr("(chưa có collection)"))
            yield Select([], id="api-env", prompt=tr("(không dùng môi trường)"))
            yield ApiList(id="api-list")
            with Horizontal(id="api-side-btns"):
                yield Btn(tr("＋ Request"), id="api-new", variant="primary")
                yield Btn(tr("▶ Chạy hết"), id="api-run")
            yield Static(id="api-foot")
        with Vertical(id="api-main"):
            with Horizontal(id="api-urlrow"):
                yield Select([(m, m) for m in A.METHODS], id="api-method", allow_blank=False, value="GET")
                yield TextInput(id="api-url", placeholder=tr("https://… hoặc /đường-dẫn (nối sau {{base_url}}) · Enter gửi"))
                yield Btn(tr("Gửi"), id="api-send", variant="primary")
            yield TextInput(id="api-name", placeholder=tr("Tên request"))
            with TabbedContent(id="api-tabs"):
                with TabPane("Params", id="api-t-query"):
                    yield TextAreaVN("", id="api-query", soft_wrap=True, show_line_numbers=False,
                                     placeholder=tr("khoá=giá trị mỗi dòng · # đầu dòng = tắt"))
                with TabPane("Headers", id="api-t-headers"):
                    yield TextAreaVN("", id="api-headers", soft_wrap=True, show_line_numbers=False,
                                     placeholder=tr("Khoá: giá trị mỗi dòng · # đầu dòng = tắt"))
                with TabPane("Body", id="api-t-body"):
                    yield Select([(tr("Không có"), "none"), ("JSON", "json"), ("Form", "form"), ("Raw", "raw")],
                                 id="api-btype", allow_blank=False, value="none")
                    yield TextAreaVN("", id="api-body", soft_wrap=True, show_line_numbers=False,
                                     placeholder=tr("JSON / chữ thô · Form: khoá=giá trị mỗi dòng"))
                with TabPane("Auth", id="api-t-auth"):
                    yield Select([(tr("Không"), "none"), ("Bearer token", "bearer"), ("Basic", "basic")],
                                 id="api-atype", allow_blank=False, value="none")
                    yield TextInput(id="api-auth", placeholder=tr("Bearer: {{token}} · Basic: tài khoản:mật khẩu"))
                with TabPane(tr("Kiểm tra"), id="api-t-tests"):
                    yield TextAreaVN("", id="api-asserts", soft_wrap=True, show_line_numbers=False,
                                     placeholder="status == 200\njson $.data.id exists\ntime < 500")
                    yield TextAreaVN("", id="api-extract", soft_wrap=True, show_line_numbers=False,
                                     placeholder="token = json $.data.token")
            with Horizontal(id="api-resp-head"):
                yield Static(id="api-status")
                yield Btn(tr("🛠 Giao trưởng nhóm sửa"), id="api-fix")
            yield ReflowLog(id="api-resp", wrap=True, markup=False, highlight=False, min_width=1)

    def on_mount(self) -> None:
        self.query_one("#api-fix").display = False
        self.query_one("#api-asserts").border_title = tr("Assert — mỗi dòng một điều kiện")
        self.query_one("#api-extract").border_title = tr("Lấy biến từ response (lưu thành secret)")
        self.show_editor(False)

    def show_editor(self, on: bool) -> None:
        for wid in ("#api-urlrow", "#api-name", "#api-tabs", "#api-resp-head", "#api-resp"):
            self.query_one(wid).display = on

    # ---------------------------------------------------------------- tải / danh sách
    def shown(self) -> None:
        self.reload(force=True)
        self.query_one("#api-list" if self.coll and self.coll["requests"] else "#api-new").focus()

    def reload(self, force: bool = False) -> None:
        """Đọc lại danh sách collection / môi trường, và collection đang mở nếu file đổi (web vừa sửa) mà ở đây
        chưa gõ gì. Gọi mỗi lần làm mới khi đang xem tab."""
        names = A.list_collections(self.root)
        if self.coll_name not in names:
            self.coll_name = names[0] if names else ""
            force = True
        path = A.api_dir(self.root) / f"{self.coll_name}.json"
        try:
            mtime = path.stat().st_mtime if self.coll_name else None
        except OSError:
            mtime = None
        envs = A.list_envs(self.root)
        if self.env not in envs:
            self.env = ""
        # chỉ chặn sự kiện của ô chọn, không đụng _loading: người dùng đang gõ thì thay đổi vẫn được tự lưu
        self._quiet_sel = True
        try:
            self._set_select("#api-coll", [(n, n) for n in names], self.coll_name)
            self._set_select("#api-env", [(n, n) for n in envs], self.env)
        finally:
            self.call_after_refresh(self._sel_done)
        if (force or mtime != self._mtime) and not self.dirty:
            self._mtime = mtime
            self.coll = A.load_collection(self.root, self.coll_name) if self.coll_name else None
            if self.coll and not self.current():
                self.cur_id = self.coll["requests"][0]["id"] if self.coll["requests"] else None
            self.render_list()
            self.open_request(self.cur_id)
        self.foot()

    def _set_select(self, wid: str, options: list, value: str) -> None:
        sel = self.query_one(wid, Select)
        sig = (tuple(options), value)
        if getattr(sel, "_ateam_sig", None) == sig:
            return
        sel._ateam_sig = sig
        sel.set_options(options)
        if value:
            sel.value = value
        else:
            sel.clear()

    def _loaded(self) -> None:
        self._loading = False

    def _sel_done(self) -> None:
        self._quiet_sel = False

    def current(self) -> dict | None:
        return next((r for r in (self.coll or {}).get("requests") or [] if r.get("id") == self.cur_id), None)

    def render_list(self) -> None:
        lst = self.query_one(ApiList)
        lst.clear_options()
        reqs = (self.coll or {}).get("requests") or []
        folder = None
        for r in sorted(reqs, key=lambda x: x.get("folder") or ""):
            if (r.get("folder") or "") != folder:
                folder = r.get("folder") or ""
                if folder:
                    lst.add_option(Option(Text(folder.upper(), "dim bold"), disabled=True))
            m = r.get("method") or "GET"
            t = Text()
            t.append(f"{m:<7}", METHOD_STYLE.get(m, "dim"))
            t.append(r.get("name") or r.get("url") or tr("Request không tên"))
            res = self.results.get(r.get("id"))
            if res:
                st = res["response"].get("status") or "✗"
                t.append(f"  {st}", "green" if res["ok"] else "red")
            lst.add_option(Option(t, id=f"r{r['id']}"))
        if not reqs:
            lst.add_option(Option(Text(tr("Chưa có request — bấm n hoặc ＋ Request") if self.coll else
                                       tr("Chưa có collection — bấm ＋ Request để tạo"), "dim"), disabled=True))
        ids = [o.id for o in lst.options]
        key = f"r{self.cur_id}"
        if key in ids:
            lst.highlighted = ids.index(key)

    def foot(self) -> None:
        text = Text(f".ateam/api/{self.coll_name}.json" if self.coll_name else ".ateam/api/", "dim")
        if self.coll:
            text.append("  ● " + tr("chưa lưu") if self.dirty else "  ✓ " + tr("đã lưu"),
                        "yellow" if self.dirty else "green")
        set_static(self.query_one("#api-foot", Static), text)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()
        oid = event.option.id or ""
        if oid.startswith("r") and int(oid[1:]) != self.cur_id:
            self.open_request(int(oid[1:]))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.query_one("#api-url").focus()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        event.stop()  # tab con: không để TeamApp tưởng là đổi tab chính

    # ---------------------------------------------------------------- soạn
    def open_request(self, rid) -> None:
        if self.dirty:
            self.action_save()
        self.cur_id = rid
        r = self.current()
        self.show_editor(bool(r))
        if not r:
            return
        self._loading = True
        try:
            self.query_one("#api-method", Select).value = r.get("method") or "GET"
            self.query_one("#api-url", Input).value = r.get("url") or ""
            self.query_one("#api-name", Input).value = r.get("name") or ""
            self.query_one("#api-query", TextArea).load_text(rows_to_text(r.get("query"), "="))
            self.query_one("#api-headers", TextArea).load_text(rows_to_text(r.get("headers"), ": "))
            b = r.get("body") or {}
            self.query_one("#api-btype", Select).value = b.get("type") or "none"
            self.query_one("#api-body", TextArea).load_text(rows_to_text(b.get("form"), "=") if b.get("type") == "form"
                                                            else b.get("text") or "")
            a = r.get("auth") or {}
            self.query_one("#api-atype", Select).value = a.get("type") or "none"
            self.query_one("#api-auth", Input).value = (a.get("token") or "") if a.get("type") == "bearer" else \
                (f"{a.get('user') or ''}:{a.get('password') or ''}" if a.get("type") == "basic" else "")
            self.query_one("#api-asserts", TextArea).load_text("\n".join(r.get("asserts") or []))
            self.query_one("#api-extract", TextArea).load_text("\n".join(r.get("extract") or []))
        finally:
            self.call_after_refresh(self._loaded)
        self.show_result()

    def collect(self) -> None:
        """Ô soạn -> request đang mở (giữ nguyên khoá không có ô sửa ở đây, vd timeout)."""
        r = self.current()
        if not r:
            return
        r["method"] = str(self.query_one("#api-method", Select).value or "GET")
        r["url"] = self.query_one("#api-url", Input).value.strip()
        r["name"] = self.query_one("#api-name", Input).value.strip()
        r["query"] = text_to_rows(self.query_one("#api-query", TextArea).text, "=")
        r["headers"] = text_to_rows(self.query_one("#api-headers", TextArea).text, ":")
        kind = str(self.query_one("#api-btype", Select).value or "none")
        body = self.query_one("#api-body", TextArea).text
        r["body"] = {"type": "form", "form": text_to_rows(body, "=")} if kind == "form" else {"type": kind, "text": body}
        atype = str(self.query_one("#api-atype", Select).value or "none")
        val = self.query_one("#api-auth", Input).value.strip()
        user, _, pw = val.partition(":")
        r["auth"] = {"type": "bearer", "token": val} if atype == "bearer" else \
            {"type": "basic", "user": user, "password": pw} if atype == "basic" else {"type": "none"}
        lines = lambda wid: [x.strip() for x in self.query_one(wid, TextArea).text.splitlines() if x.strip()]  # noqa: E731
        r["asserts"], r["extract"] = lines("#api-asserts"), lines("#api-extract")

    def changed(self) -> None:
        if self._loading or not self.current():
            return
        self.dirty = True
        self.foot()
        if self._timer:
            self._timer.stop()
        self._timer = self.set_timer(0.8, self.action_save)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in ("api-url", "api-name", "api-auth"):
            event.stop()
            self.changed()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        event.stop()
        self.changed()

    def on_select_changed(self, event: Select.Changed) -> None:
        event.stop()
        wid = event.select.id
        if self._loading or (self._quiet_sel and wid in ("api-coll", "api-env")):
            return
        if wid == "api-coll" and event.value != Select.BLANK and event.value != self.coll_name:
            self.action_save()
            self.coll_name, self.cur_id, self.results = str(event.value), None, {}
            self.reload(force=True)
        elif wid == "api-env":
            self.env = "" if event.value == Select.BLANK else str(event.value)
        elif wid in ("api-method", "api-btype", "api-atype"):
            self.changed()

    def action_save(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None
        if not self.dirty or not self.coll:
            return
        self.collect()
        A.save_collection(self.root, self.coll, self.coll_name)
        self.dirty = False
        try:
            self._mtime = (A.api_dir(self.root) / f"{self.coll_name}.json").stat().st_mtime
        except OSError:
            pass
        keep = self.cur_id
        self.render_list()
        self.cur_id = keep
        self.foot()

    def new_request(self) -> None:
        if not self.coll:
            self.coll_name = A.unique_name(self.root, "api")
            ports = A.dev_ports(self.app.shell) if hasattr(self.app, "shell") else []
            self.coll = {"name": self.coll_name, "vars": {"base_url": f"http://localhost:{ports[0]}"} if ports else {},
                         "requests": []}
        rid = max([r.get("id", 0) for r in self.coll["requests"]] + [0]) + 1
        self.coll["requests"].append({"id": rid, "name": "", "method": "GET", "url": "/", "query": [], "headers": [],
                                      "body": {"type": "none"}, "auth": {"type": "none"}, "asserts": ["status == 200"]})
        self.dirty = True
        self.action_save()
        self.reload(force=True)
        self.open_request(rid)
        self.render_list()
        url = self.query_one("#api-url", Input)
        url.focus()

    def delete_request(self) -> None:
        r = self.current()
        if not r:
            return
        from .tui import ConfirmScreen

        def done(ok) -> None:
            if ok:
                self.coll["requests"] = [x for x in self.coll["requests"] if x is not r]
                self.cur_id = self.coll["requests"][0]["id"] if self.coll["requests"] else None
                self.dirty, self._loading = True, True  # không để collect() ghi ô soạn của request vừa xoá
                A.save_collection(self.root, self.coll, self.coll_name)
                self.dirty, self._loading = False, False
                self.reload(force=True)
        self.app.push_screen(ConfirmScreen(tr("Xoá request"), tr("Xoá request “{v}”?", v=r.get("name") or r.get("url")),
                                           tr("Xoá")), done)

    # ---------------------------------------------------------------- gửi / chạy
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "api-url":
            event.stop()
            self.send()

    def on_button_pressed(self, event) -> None:
        bid = event.button.id
        if bid in ("api-send", "api-new", "api-run", "api-fix"):
            event.stop()
        if bid == "api-send":
            self.send()
        elif bid == "api-new":
            self.new_request()
        elif bid == "api-run":
            self.run_worker(self.run_all(), exclusive=True, group="api-run")
        elif bid == "api-fix":
            self.fix()

    def send(self) -> None:
        if self.current():
            self.action_save()
            self.collect()
            self.run_worker(self._send(dict(self.current())), exclusive=True, group="api-send")

    async def _send(self, req: dict) -> None:
        set_static(self.query_one("#api-status", Static), Text(tr("Đang gửi…"), "dim"))
        res = await A.run_request(self.root, self.coll, req, self.env)
        res["response"]["body"] = A.mask(res["response"].get("body") or "", A.load_secrets(self.root))
        self.results[req["id"]] = res
        if req["id"] == self.cur_id:
            self.show_result()
        self.render_list()

    def show_result(self) -> None:
        log = self.query_one("#api-resp", ReflowLog)
        log.clear()
        res = self.results.get(self.cur_id)
        fix = self.query_one("#api-fix")
        if not res:
            set_static(self.query_one("#api-status", Static), Text(tr("Gửi request để xem response · Enter ở ô URL"), "dim"))
            fix.display = False
            return
        rp = res["response"]
        fails = [a for a in res["asserts"] if not a["ok"]]
        fix.display = bool(rp.get("error")) or (rp.get("status") or 0) >= 400 or bool(fails)
        if rp.get("error"):
            set_static(self.query_one("#api-status", Static), Text(tr("✗ Lỗi mạng · {ms} ms", ms=rp["ms"]), "bold red"))
            log.write(Text(rp["error"], "red"))
            return
        st = rp["status"]
        head = Text(f"{st} {rp.get('reason') or ''}", "bold " + ("green" if st < 300 else "yellow" if st < 400 else "red"))
        head.append(f"  {rp['ms']} ms · {rp['size']} B", "dim")
        if res["asserts"]:
            head.append(f"  {'✗' if fails else '✓'} {len(res['asserts']) - len(fails)}/{len(res['asserts'])}",
                        "red" if fails else "green")
        if res.get("extracted"):
            head.append("  " + tr("Đã lưu biến: {v}", v=", ".join(res["extracted"])), "dim")
        set_static(self.query_one("#api-status", Static), head)
        for a in res["asserts"]:
            log.write(Text(("✓ " if a["ok"] else "✗ ") + a["msg"], "green" if a["ok"] else "red"))
        body = rp.get("body") or ""
        try:
            json.loads(body)
            log.write(JSON(body[:300000]))
        except ValueError:
            log.write(Text(body[:300000] or tr("(body trống)"), "" if body else "dim"))

    async def run_all(self) -> None:
        self.action_save()
        if not self.coll:
            return
        text, ok = await A.run_report(self.root, self.coll_name + (" " + self.env if self.env else ""))
        self.app.write_sys(text)  # type: ignore[attr-defined]
        self.app.notify(text.splitlines()[-1], severity="information" if ok else "warning")

    def fix(self) -> None:
        r, res = self.current(), self.results.get(self.cur_id)
        if not r or not res:
            return
        orch = self.app.orch  # type: ignore[attr-defined]
        title, prompt = A.fix_task(self.root, {"collection": self.coll_name, "env": self.env, "request": r, "result": res},
                                   A.dev_log(self.app.shell) if hasattr(self.app, "shell") else "")
        tid = orch.add_task(orch.cfg.lead, prompt, title)
        self.app.notify(tr("🛠 Đã giao {agent} sửa (task #{tid})", agent=orch.cfg.lead, tid=tid))
