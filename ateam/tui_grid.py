"""Tab 🔲 Lưới của TUI: mỗi ô là CLI thật của một agent (pty + `vterm.Screen`), gõ trực tiếp được.

Bố cục, CLI và lưu trữ nằm ở `grid.GridHub` (dùng chung với web). Ở đây chỉ có widget: `TermView` vẽ màn hình và
gửi phím vào pty, `GridCell` (tiêu đề + terminal), `GridPanel` (thanh công cụ + các cột), `GridAddScreen` (popup
Thêm agent). Nạp muộn từ `tui.py` (`from .tui_grid import …` trong compose) nên import ngược `tui` ở đây không vòng.

Phím: khi đang gõ trong ô, phím Ctrl của ateam nhường cho CLI (TeamApp.check_action), trừ Ctrl+Q và các phím F.
F10 bật chế độ sắp xếp (`GRID_KEYS`); kéo tiêu đề ô thả lên ô khác để đổi chỗ / đặt cạnh."""

from __future__ import annotations

from functools import lru_cache

from rich.color import Color
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Button, Checkbox, OptionList, Select, Static
from textual.widgets.option_list import Option

from . import vterm
from .grid import SHELL, GridHub, preset_names, shell_argv
from .i18n import tr
from .tui import BaseModal, Btn

RESIZE_STEP = 0.05
EDGE = 0.25  # thả trong 25% sát cạnh ô = đặt bên cạnh, còn lại = đổi chỗ


def grid_help() -> str:
    return tr("Sắp xếp: ←↑→↓ chọn ô · Shift+←↑→↓ đổi chỗ · +/- rộng · [/] cao · a thêm · x đóng · z phóng to · "
              "r mở lại · 1-5 bố cục · b gửi tất cả · Esc xong")


@lru_cache(maxsize=4096)
def _style(attr: tuple, cursor: bool = False) -> Style:
    fg, bg, bold, dim, italic, under, rev, strike, hidden = attr

    def col(c):
        if c is None:
            return None
        if isinstance(c, int):
            return Color.from_ansi(c)
        try:
            return Color.parse(c)
        except Exception:
            return None
    return Style(color=col(fg), bgcolor=col(bg), bold=bold or None, dim=dim or None, italic=italic or None,
                 underline=under or None, strike=strike or None, reverse=(rev != cursor) or None,
                 conceal=hidden or None)


class TermView(Widget, can_focus=True):
    """Một terminal: vẽ `vterm.Screen` của ô `cell_id`, phím gõ đi vào pty qua GridHub."""

    DEFAULT_CSS = """
    TermView { height: 1fr; width: 1fr; background: $background; }
    """

    def __init__(self, cell_id: str, **kw):
        super().__init__(**kw)
        self.cell_id = cell_id
        self.scroll_off = 0  # số dòng đang cuộn lên xem lịch sử (màn hình chính)
        self._seen = -1

    @property
    def hub(self) -> GridHub:
        return self.app.grid

    @property
    def term(self) -> vterm.Screen:
        return self.app.grid_screen(self.cell_id)

    def on_mount(self) -> None:
        self.set_interval(1 / 30, self._tick)

    def _tick(self) -> None:
        v = self.term.version
        if v != self._seen:
            self._seen = v
            self.refresh()

    def on_resize(self, event: events.Resize) -> None:
        w, h = self.size.width, self.size.height
        if w > 1 and h > 0:
            self.term.resize(h, w)
            self.hub.resize(self.cell_id, h, w)
            self.refresh()

    def on_focus(self) -> None:
        if self.hub.layout.find(self.cell_id):  # ⌨ shell của tab Terminal không thuộc Lưới
            self.app.grid_focused = self.cell_id
        self.refresh()
        panel = self._panel()
        if panel:
            panel.refresh_heads()

    def on_blur(self) -> None:
        self.refresh()

    def _panel(self):
        for a in self.ancestors:
            if isinstance(a, GridPanel):
                return a
        return None

    # ---- vẽ
    def render_line(self, y: int) -> Strip:
        width = self.size.width
        scr = self.term
        status = self.hub.status(self.cell_id)
        if status != "run" and y == self.size.height - 1:
            t = self.hub.terms.get(self.cell_id)
            msg = (tr(" CLI đã thoát (mã {rc}) — Enter: mở lại ", rc=t.rc) if status == "exit" and t
                   else tr(" CLI chưa chạy — Enter: mở (tiếp tục phiên) "))
            return Strip([Segment(msg[:width], Style(reverse=True, bold=True))]).extend_cell_length(width)
        hist = scr.history if not scr.in_alt else []
        off = min(self.scroll_off, len(hist))
        if off:
            idx = len(hist) - off + y
            row = hist[idx] if idx < len(hist) else scr.lines[idx - len(hist)]
        else:
            row = scr.lines[y] if y < len(scr.lines) else []
        cur_x = scr.x if (self.has_focus and scr.cursor_visible and not off and y == scr.y and status == "run") else -1
        segs: list = []
        buf, last = [], None
        for x, (ch, attr) in enumerate(row[:width]):
            if ch == "":
                continue
            key = (attr, x == cur_x)
            if key != last and buf:
                segs.append(Segment("".join(buf), _style(*last)))
                buf = []
            last = key
            buf.append(ch)
        if buf:
            segs.append(Segment("".join(buf), _style(*last)))
        if off and y == 0:
            segs = [Segment(tr(" ↑ lịch sử ({n} dòng) — gõ phím để về cuối ", n=off), Style(reverse=True))]
        return Strip(segs).crop_extend(0, width, None)

    # ---- phím
    async def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        app = self.app
        if app.grid_arrange:
            app.grid_arrange_key(event.key)
            return
        if self.hub.status(self.cell_id) != "run":
            if event.key == "enter":
                await self.hub.start(self.cell_id, self.size.height or 24, self.size.width or 80)
            return
        data = vterm.encode(event.key, event.character, self.term.app_cursor)
        if data:
            self.scroll_off = 0
            self.hub.write(self.cell_id, data)

    def on_paste(self, event: events.Paste) -> None:
        event.stop()
        text = event.text.replace("\r\n", "\r").replace("\n", "\r")
        if self.term.bracketed_paste:
            text = "\x1b[200~" + text + "\x1b[201~"
        self.hub.write(self.cell_id, text.encode())

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        if not self.term.in_alt:
            self.scroll_off = min(len(self.term.history), self.scroll_off + 3)
            self.refresh()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        self.scroll_off = max(0, self.scroll_off - 3)
        self.refresh()


class GridHead(Static):
    """Tiêu đề ô: bấm giữ rồi thả lên ô khác để di chuyển ô này."""

    def __init__(self, cell_id: str, **kw):
        super().__init__(**kw)
        self.cell_id = cell_id
        self._down = False

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._down = True
        self.capture_mouse()
        self.app.grid_drag = self.cell_id

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._down:
            panel = self.app.query_one("#grid-panel", GridPanel)
            panel.set_hint(tr("Thả lên ô khác: giữa = đổi chỗ, sát cạnh = đặt bên đó · thả tại chỗ = huỷ"))

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if not self._down:
            return
        self._down = False
        self.release_mouse()
        self.app.grid_drag = None
        panel = self.app.query_one("#grid-panel", GridPanel)
        panel.set_hint("")
        try:
            widget, _ = self.app.screen.get_widget_at(event.screen_x, event.screen_y)
        except Exception:
            widget = None
        target = widget if isinstance(widget, GridCell) else next(
            (a for a in (widget.ancestors if widget else []) if isinstance(a, GridCell)), None)
        if target is None or target.cell_id == self.cell_id:
            self.query_ancestor(GridCell).focus_term()
            return
        r = target.region
        fx = (event.screen_x - r.x) / max(1, r.width)
        fy = (event.screen_y - r.y) / max(1, r.height)
        where = ("left" if fx < EDGE else "right" if fx > 1 - EDGE else
                 "top" if fy < EDGE else "bottom" if fy > 1 - EDGE else "center")
        panel.move(self.cell_id, target.cell_id, where)


class GridCell(Vertical):
    DEFAULT_CSS = """
    GridCell { border: round $panel-lighten-2; height: 1fr; width: 1fr; }
    GridCell.focus { border: round $accent; }
    GridCell.bcast { border: round $warning; }
    GridCell .gc-head-row { height: 1; }
    GridCell GridHead { width: 1fr; height: 1; }
    GridCell .gc-btn { margin-left: 1; }
    """

    def __init__(self, cell_id: str, **kw):
        super().__init__(**kw)
        self.cell_id = cell_id

    def compose(self) -> ComposeResult:
        with Horizontal(classes="gc-head-row"):
            yield GridHead(self.cell_id, classes="gc-head")
            yield Btn("⟲", classes="gc-btn gc-restart")
            yield Btn("⤢", classes="gc-btn gc-zoom")
            yield Btn("✕", classes="gc-btn gc-close", variant="error")
        yield TermView(self.cell_id)

    def focus_term(self) -> None:
        self.query_one(TermView).focus()

    def head_text(self) -> Text:
        app = self.app
        hub: GridHub = app.grid
        cell = hub.layout.cell(self.cell_id)
        if not cell:
            return Text("")
        a = app.cfg.agents.get(cell.agent)
        st = hub.status(self.cell_id)
        st_txt = {"run": (tr("● đang chạy"), "cyan"), "exit": (tr("■ đã thoát"), "red"),
                  "off": (tr("○ chưa mở"), "grey50")}[st]
        t = Text.assemble(("⠿ ", "grey50"), (tr("Terminal") if cell.agent == SHELL else cell.agent, "bold"))
        if cell.agent == app.cfg.lead:
            t.append(" ★", "yellow")
        if a:
            t.append("  " + a.label(cell.model or None, cell.effort or None), "grey62")
        t.append("  ")
        t.append(*st_txt)
        if hub.bcast and cell.bcast:
            t.append(tr("  ⇉ gửi tất cả"), "yellow")
        return t

    def refresh_head(self) -> None:
        self.query_one(GridHead).update(self.head_text())
        hub: GridHub = self.app.grid
        cell = hub.layout.cell(self.cell_id)
        self.set_class(self.app.grid_focused == self.cell_id, "focus")
        self.set_class(bool(hub.bcast and cell and cell.bcast), "bcast")

    @on(Button.Pressed, ".gc-btn")
    def _btn(self, event: Button.Pressed) -> None:
        event.stop()
        panel = self.app.query_one("#grid-panel", GridPanel)
        if event.button.has_class("gc-close"):
            panel.close_cell(self.cell_id)
        elif event.button.has_class("gc-zoom"):
            panel.toggle_zoom(self.cell_id)
        elif event.button.has_class("gc-restart"):
            panel.restart(self.cell_id)


class GridPanel(Vertical):
    DEFAULT_CSS = """
    GridPanel { height: 1fr; }
    #grid-tools { height: 1; }
    #grid-tools Button { margin-right: 1; }
    #grid-hint { height: 1; color: $text-muted; padding: 0 1; }
    #grid-hint.arrange { color: $warning; text-style: bold; }
    #grid-body { height: 1fr; }
    #grid-body > Vertical { height: 1fr; }
    #grid-empty { height: 1fr; content-align: center middle; color: $text-muted; }
    #grid-quick { height: auto; align: center top; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="grid-tools"):
            yield Btn(tr("＋ Thêm agent"), id="grid-add", variant="primary")
            yield Btn(tr("⌨ Terminal"), id="grid-shell")
            for key, name in preset_names().items():
                yield Btn(name, id=f"grid-preset-{key}", classes="grid-preset")
            yield Btn(tr("⇉ Gửi tất cả"), id="grid-bcast")
            yield Btn(tr("⚙ Sắp xếp (F10)"), id="grid-arrange")
        yield Static(id="grid-hint")
        yield Horizontal(id="grid-body")

    def on_mount(self) -> None:
        self._sig = None
        self.app.grid.listen(self._on_hub)
        self.rebuild()

    def on_unmount(self) -> None:
        self.app.grid.unlisten(self._on_hub)

    def _on_hub(self, cid: str, kind: str, payload) -> None:
        if kind == "layout":
            self.rebuild()

    def signature(self) -> tuple:
        lay = self.app.grid.layout
        zoom = self.app.grid_zoom if lay.find(self.app.grid_zoom or "") else None
        return (zoom, tuple((round(c.w, 3), tuple((x.id, round(x.h, 3)) for x in c.cells)) for c in lay.cols))

    def rebuild(self) -> None:
        sig = self.signature()
        if sig == self._sig:
            self.refresh_heads()
            return
        self._sig = sig
        self.run_worker(self._rebuild(sig), exclusive=True, group="grid-rebuild")

    async def _rebuild(self, sig) -> None:
        app = self.app
        hub: GridHub = app.grid
        body = self.query_one("#grid-body", Horizontal)
        await body.remove_children()
        zoom = sig[0]
        if not hub.layout.cols:
            box = Vertical(Static(tr("Chưa có agent nào trong lưới.\n\nBấm ＋ Thêm agent hoặc chọn nhanh một agent "
                                     "dưới đây — mỗi ô là CLI thật, gõ trực tiếp được."), id="grid-empty"),
                           Horizontal(*[Btn(n, classes="grid-quick-btn", name=n)
                                        for n in app.cfg.active_agents()],
                                      Btn(tr("⌨ Terminal"), classes="grid-quick-btn", name=SHELL), id="grid-quick"))
            await body.mount(box)
            self.refresh_tools()
            return
        cols = [[hub.layout.cell(zoom)]] if zoom else [c.cells for c in hub.layout.cols]
        widths = [1.0] if zoom else [c.w for c in hub.layout.cols]
        for cells, w in zip(cols, widths):
            col = Vertical()
            col.styles.width = f"{max(w, 0.05):.3f}fr"
            await body.mount(col)
            for c in cells:
                gc = GridCell(c.id)
                gc.styles.height = f"{max(c.h, 0.05):.3f}fr"
                await col.mount(gc)
        self.refresh_heads()
        self.refresh_tools()
        focus = app.grid_focused if hub.layout.find(app.grid_focused or "") else None
        target = self._cell_widget(focus) if focus else next(iter(self.query(GridCell)), None)
        if target and app.query_one("#tabs").active == "tab-grid":
            target.focus_term()

    def _cell_widget(self, cid: str | None) -> GridCell | None:
        return next((g for g in self.query(GridCell) if g.cell_id == cid), None)

    def refresh_heads(self) -> None:
        for g in self.query(GridCell):
            try:
                g.refresh_head()
            except Exception:
                pass

    def refresh_tools(self) -> None:
        hub: GridHub = self.app.grid
        for key in preset_names():
            b = self.query_one(f"#grid-preset-{key}", Button)
            b.variant = "primary" if hub.layout.preset == key else "default"
        bc = self.query_one("#grid-bcast", Button)
        bc.label = Btn.wrap(tr("⇉ Gửi tất cả: bật") if hub.bcast else tr("⇉ Gửi tất cả"))
        bc.variant = "warning" if hub.bcast else "default"
        self.set_hint("")

    def set_hint(self, text: str) -> None:
        hint = self.query_one("#grid-hint", Static)
        arrange = self.app.grid_arrange
        hint.set_class(arrange, "arrange")
        hint.update(Text(text or (grid_help() if arrange else tr(
            "Bấm vào ô để gõ thẳng vào CLI · phím Ctrl thuộc về CLI (Ctrl+Q vẫn thoát ateam) · F10: sắp xếp · "
            "kéo tiêu đề ô để đổi chỗ"))))

    # ---- thao tác
    def add_agent(self, near: str | None = None, where: str = "") -> None:
        def done(r) -> None:
            if r:
                self.app.run_worker(self._add(r, near, where), group="grid-add")
        self.app.push_screen(GridAddScreen(self.app.cfg), done)

    async def _add(self, r: dict, near: str | None = None, where: str = "") -> None:
        app = self.app
        size = self.query_one("#grid-body").size
        cid, err = await app.grid.add(r["agent"], model=r.get("model", ""), effort=r.get("effort", ""),
                                      resume=r.get("resume", True), near=near, where=where,
                                      rows=max(5, size.height // 2), cols=max(20, size.width // 2))
        if err:
            app.notify(err, severity="warning")
        if cid:
            app.grid_focused = cid
            self.rebuild()

    def move(self, src: str, dst: str, where: str) -> None:
        if self.app.grid.layout.move(src, dst, where):
            self.app.grid_focused = src
            self.app.grid.changed()

    def close_cell(self, cid: str) -> None:
        app = self.app
        hub: GridHub = app.grid
        cell = hub.layout.cell(cid)
        if not cell:
            return

        def done(ok) -> None:
            if ok:
                if app.grid_zoom == cid:
                    app.grid_zoom = None
                nxt = hub.layout.neighbor(cid, "left") or hub.layout.neighbor(cid, "up") or \
                    hub.layout.neighbor(cid, "right") or hub.layout.neighbor(cid, "down")
                app.grid_focused = nxt
                hub.close(cid)
        if hub.status(cid) == "run":
            from .tui import ConfirmScreen
            app.push_screen(ConfirmScreen(tr("Đóng terminal"), tr("Dừng CLI {agent} trong ô này và bỏ ô khỏi lưới?",
                                                                    agent=cell.agent), yes=tr("Đóng")), done)
        else:
            done(True)

    def toggle_zoom(self, cid: str) -> None:
        app = self.app
        app.grid_zoom = None if app.grid_zoom == cid else cid
        app.grid_focused = cid
        self.rebuild()

    def restart(self, cid: str) -> None:
        app = self.app
        hub: GridHub = app.grid
        if hub.status(cid) == "run":
            app.notify(tr("CLI đang chạy — đóng nó (hoặc ✕) trước khi mở lại"), severity="warning")
            return
        g = self._cell_widget(cid)
        size = g.query_one(TermView).size if g else None

        async def go() -> None:
            err = await hub.start(cid, (size.height if size else 0) or 24, (size.width if size else 0) or 80)
            if err:
                app.notify(err, severity="error")
            if g:
                g.focus_term()
        app.run_worker(go(), group="grid-start")

    def preset(self, key: str) -> None:
        app = self.app
        app.grid_zoom = None
        app.grid.layout.apply(key)
        app.grid.changed()

    def toggle_bcast(self) -> None:
        hub: GridHub = self.app.grid
        hub.bcast = not hub.bcast
        self.refresh_tools()
        self.refresh_heads()

    def arrange_key(self, key: str) -> None:
        """Phím ở chế độ sắp xếp (F10)."""
        app = self.app
        hub: GridHub = app.grid
        cid = app.grid_focused if hub.layout.find(app.grid_focused or "") else None
        dirs = {"left": "left", "right": "right", "up": "up", "down": "down"}
        if key in ("escape", "enter", "f10"):
            app.grid_arrange = False
            self.set_hint("")
            return
        if key == "a":
            self.add_agent()
            return
        if key == "b":
            self.toggle_bcast()
            return
        if key in ("1", "2", "3", "4", "5"):
            self.preset(list(preset_names())[int(key) - 1])
            return
        if not cid:
            return
        pos = hub.layout.find(cid)
        if key in dirs:
            nxt = hub.layout.neighbor(cid, dirs[key])
            if nxt:
                app.grid_focused = nxt
                g = self._cell_widget(nxt)
                if g:
                    g.focus_term()
        elif key.startswith("shift+") and key[6:] in dirs:
            if hub.layout.shift(cid, dirs[key[6:]]):
                hub.changed()
        elif key in ("plus", "equals_sign", "+", "="):
            hub.layout.resize_col(pos[0], RESIZE_STEP)
            hub.changed()
        elif key in ("minus", "-"):
            hub.layout.resize_col(pos[0], -RESIZE_STEP)
            hub.changed()
        elif key in ("right_square_bracket", "]"):
            hub.layout.resize_cell(cid, RESIZE_STEP)
            hub.changed()
        elif key in ("left_square_bracket", "["):
            hub.layout.resize_cell(cid, -RESIZE_STEP)
            hub.changed()
        elif key == "x":
            self.close_cell(cid)
        elif key == "z":
            self.toggle_zoom(cid)
        elif key == "r":
            self.restart(cid)

    @on(Button.Pressed, "#grid-tools Button")
    def _tool(self, event: Button.Pressed) -> None:
        event.stop()
        bid = event.button.id or ""
        if bid == "grid-add":
            self.add_agent()
        elif bid == "grid-shell":  # ô terminal trống: shell của người dùng (như nút shell ở web)
            self.app.run_worker(self._add({"agent": SHELL}), group="grid-add")
        elif bid.startswith("grid-preset-"):
            self.preset(bid[len("grid-preset-"):])
        elif bid == "grid-bcast":
            self.toggle_bcast()
        elif bid == "grid-arrange":
            self.app.action_grid_arrange()

    @on(Button.Pressed, ".grid-quick-btn")
    def _quick(self, event: Button.Pressed) -> None:
        event.stop()
        self.app.run_worker(self._add({"agent": event.button.name, "resume": True}), group="grid-add")


class GridAddScreen(BaseModal):
    """Popup Thêm agent vào lưới. Trả {agent, model, effort, resume} hoặc None. Mục đầu "⌨ Terminal" (agent SHELL)
    là shell của người dùng: không có model / effort / --resume."""

    DEFAULT_CSS = """
    GridAddScreen { align: center middle; }
    #ga-box { width: 84; max-width: 100%; height: auto; max-height: 90%; border: round $accent;
              background: $surface; padding: 0 1; }
    #ga-agents { height: auto; max-height: 10; margin: 1 0 0 0; }
    .ga-row { height: auto; margin-top: 1; }
    .ga-row Select { width: 1fr; }
    .ga-label { width: 10; padding-top: 1; color: $text-muted; }
    #ga-cmd { height: auto; margin-top: 1; color: $text-muted; }
    #ga-buttons { height: auto; align: right middle; margin-top: 1; }
    #ga-buttons Button { margin-left: 2; }
    """

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.names = [SHELL] + [n for n, a in cfg.active_agents().items() if a.interactive_argv() is not None]

    def compose(self) -> ComposeResult:
        with Vertical(id="ga-box"):
            yield self.title_bar(tr("Thêm agent vào lưới · mở CLI thật trong một ô mới"))
            opts = [Option(Text.assemble((tr("⌨ Terminal"), "bold"), ("  " + shell_argv()[0], "grey62"),
                                         (tr("  shell của bạn trong thư mục dự án"), "grey62")), id=SHELL)]
            for n in self.names[1:]:
                a = self.cfg.agents[n]
                t = Text.assemble((n, "bold"), ("  " + " ".join(a.command[:1]), "grey62"),
                                  ("  ✓" if a.installed() else tr("  ✗ chưa cài"), "green" if a.installed() else "red"))
                opts.append(Option(t, id=n))
            yield OptionList(*opts, id="ga-agents")
            with Horizontal(classes="ga-row"):
                yield Static("model", classes="ga-label")
                yield Select([(tr("mặc định"), "")], allow_blank=False, id="ga-model")
            with Horizontal(classes="ga-row"):
                yield Static("effort", classes="ga-label")
                yield Select([(tr("mặc định"), "")], allow_blank=False, id="ga-effort")
            yield Checkbox(tr("Tiếp tục phiên gần nhất của agent (--resume)"), value=True, id="ga-resume")
            yield Static(id="ga-cmd")
            with Horizontal(id="ga-buttons"):
                yield Btn(tr("Huỷ"), id="ga-cancel")
                yield Btn(tr("▶ Mở terminal"), id="ga-ok", variant="primary")

    def on_mount(self) -> None:
        ol = self.query_one("#ga-agents", OptionList)
        ol.highlighted = 1 if len(self.names) > 1 else 0  # mặc định: agent đầu tiên
        self._fill(self.names[ol.highlighted])
        ol.focus()

    def agent(self) -> str | None:
        ol = self.query_one("#ga-agents", OptionList)
        i = ol.highlighted
        return self.names[i] if i is not None and 0 <= i < len(self.names) else None

    def _fill(self, name: str) -> None:
        shell_cell = name == SHELL
        for wid in ("#ga-model", "#ga-effort", "#ga-resume"):
            self.query_one(wid).disabled = shell_cell
        if shell_cell:
            self.query_one("#ga-model", Select).set_options([(tr("mặc định"), "")])
            self.query_one("#ga-effort", Select).set_options([(tr("mặc định"), "")])
            self._preview()
            return
        a = self.cfg.agents[name]
        models = [(tr("mặc định ({m})", m=a.model or tr("CLI tự chọn")), "")] + [(m, m) for m in a.model_choices()]
        self.query_one("#ga-model", Select).set_options(models)
        self.query_one("#ga-model", Select).value = ""
        self._fill_effort(name, "")

    def _fill_effort(self, name: str, model: str) -> None:
        if name == SHELL:
            return
        a = self.cfg.agents[name]
        efs = [(tr("mặc định"), "")] + [(e, e) for e in a.efforts_for(model or None)]
        sel = self.query_one("#ga-effort", Select)
        sel.set_options(efs)
        sel.value = ""
        self._preview()

    def _preview(self) -> None:
        r = self.result()
        if not r:
            return
        if r["agent"] == SHELL:
            self.query_one("#ga-cmd", Static).update(Text("$ " + " ".join(shell_argv())))
            return
        a = self.cfg.agents[r["agent"]]
        argv = a.interactive_argv("<session>" if r["resume"] else None, model=r["model"] or None,
                                  effort=r["effort"] or None) or []
        self.query_one("#ga-cmd", Static).update(Text("$ " + " ".join(argv)))

    def result(self) -> dict | None:
        name = self.agent()
        if not name:
            return None
        m = self.query_one("#ga-model", Select).value
        e = self.query_one("#ga-effort", Select).value
        if name == SHELL:
            return {"agent": SHELL, "model": "", "effort": "", "resume": False}
        return {"agent": name, "model": m if isinstance(m, str) else "", "effort": e if isinstance(e, str) else "",
                "resume": self.query_one("#ga-resume", Checkbox).value}

    @on(OptionList.OptionHighlighted, "#ga-agents")
    def _agent_changed(self, event) -> None:
        name = self.agent()
        if name:
            self._fill(name)

    @on(OptionList.OptionSelected, "#ga-agents")
    def _agent_chosen(self, event) -> None:
        self.query_one("#ga-ok", Button).focus()

    @on(Select.Changed, "#ga-model")
    def _model_changed(self, event: Select.Changed) -> None:
        name = self.agent()
        if name and name != SHELL:
            self._fill_effort(name, event.value if isinstance(event.value, str) else "")

    @on(Select.Changed, "#ga-effort")
    def _effort_changed(self, event) -> None:
        self._preview()

    @on(Checkbox.Changed, "#ga-resume")
    def _resume_changed(self, event) -> None:
        self._preview()

    @on(Button.Pressed, "#ga-buttons Button")
    def _buttons(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "ga-ok":
            r = self.result()
            if r:
                self.dismiss(r)
        else:
            self.close()
