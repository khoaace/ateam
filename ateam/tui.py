"""Giao diện terminal (Textual): tab Bảng việc + tab Đội (log từng agent & timeline)."""

from __future__ import annotations

import asyncio
import re
import shlex
import time
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (DataTable, Footer, Header, Input, RichLog, Static, TabbedContent,
                             TabPane)

from .config import Config, save_project_setting
from .db import DB
from .orchestrator import SYSTEM, Orchestrator

STATUS = {
    "draft": ("nháp", "yellow"),
    "queued": ("chờ", "cyan"),
    "running": ("đang chạy", "bold magenta"),
    "done": ("xong", "green"),
    "failed": ("lỗi", "bold red"),
    "cancelled": ("đã huỷ", "dim"),
    "blocked": ("bị chặn", "red"),
    "conflict": ("xung đột", "bold yellow"),
    "review": ("chờ duyệt", "bold yellow"),
}
BAR_STYLE = {"running": "magenta", "done": "green", "failed": "red", "cancelled": "grey50",
             "blocked": "red", "conflict": "yellow", "review": "yellow"}
GOAL_STATUS = {
    "planning": ("đang lập kế hoạch", "magenta"),
    "awaiting": ("chờ duyệt (/go)", "yellow"),
    "running": ("đang làm", "cyan"),
    "reviewing": ("đang review", "magenta"),
    "done": ("hoàn thành", "green"),
    "incomplete": ("chưa xong", "yellow"),
    "failed": ("lỗi", "red"),
}
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SILENT_WARN = 60  # giây không có output -> cảnh báo "im lặng"

HELP = """\
Gõ một câu bình thường  → giao MỤC TIÊU cho trưởng nhóm lập kế hoạch & chia việc.

Giao việc:
  /task <agent> <nội dung>          giao tay (vd: /task codex viết test cho utils.py)
  /task <agent>@<effort> <nội dung> giao kèm effort riêng (vd: /task codex@xhigh tìm lỗi deadlock)
  /task <agent>:<model>@<effort> …  giao kèm cả model riêng
  /go [mục tiêu]                    duyệt kế hoạch nháp và chạy (Ctrl+G)
  /assign <task> <agent>            đổi người làm 1 task
  /edit <task> <nội dung>           sửa nội dung task (khi chưa chạy)
  /set <task> effort|model <giá trị>  đổi effort/model riêng cho 1 task ('-' = theo agent)
  /retry <task>   /cancel <task>    chạy lại (Ctrl+R) / huỷ (Ctrl+K) task
  /review <mục tiêu>                bắt trưởng nhóm review ngay
  /note <nội dung>                  ghi chú chung cho cả đội

Kiểm tra & duyệt code:
  /verify <lệnh>                    lệnh kiểm tra sau mỗi task cho dự án này (vd: /verify npm test)
  /verify off   /verify             tắt / xem lệnh đang dùng
  /diff <task>                      xem thay đổi của task (Ctrl+D với task đang chọn)
  /merge <task>                     duyệt và merge task đang chờ (Ctrl+Y)
  /reject <task> [góp ý]            từ chối; có góp ý thì giao làm lại kèm góp ý đó

Hạn mức:
  /usage                            thống kê lượt chạy, thời gian, token ước tính theo agent
  /cooldown <agent> <phút>          cho agent tạm nghỉ (vd khi bạn biết nó sắp hết hạn mức)
  /cooldown <agent> off             cho agent làm việc lại ngay

Model & effort của từng agent (được lưu lại cho lần sau):
  /model <agent> <tên model>        vd: /model claude opus   ·   /model grok xai/grok-4.7
  /effort <agent> <mức>             vd: /effort codex xhigh  ·   /effort claude high
  /model <agent> -  /effort <agent> -   quay về mặc định trong config
  /agents                           xem model, effort, mức effort hợp lệ của từng agent

Khác:
  /pause  /resume                   tạm dừng / tiếp tục nhận task mới
  /log <task>   /log sys            xem log 1 task / log hệ thống (Ctrl+L)
  /team  /board                     chuyển tab Đội / Bảng việc (Ctrl+T)
  /quit                             thoát (Ctrl+Q) — agent đang chạy sẽ bị dừng"""


def fmt_dur(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def today_start() -> float:
    lt = time.localtime()
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def safe_id(name: str) -> str:
    return "pane-" + re.sub(r"[^A-Za-z0-9_-]", "_", name)


# ============================================================================ widgets
class AgentPane(Vertical):
    """Một ô trong tab Đội: tiêu đề trạng thái + log trực tiếp của 1 agent."""

    def __init__(self, agent: str):
        super().__init__(id=safe_id(agent), classes="agentpane")
        self.agent = agent

    def compose(self) -> ComposeResult:
        yield Static(classes="pane-head")
        yield RichLog(classes="pane-log", wrap=True, markup=False, highlight=False, max_lines=3000)

    @property
    def head(self) -> Static:
        return self.query_one(".pane-head", Static)

    @property
    def body(self) -> RichLog:
        return self.query_one(".pane-log", RichLog)


class Timeline(Static):
    """Biểu đồ Gantt: mỗi agent một hàng, mỗi task một đoạn màu."""

    def build(self, app: "TeamApp") -> Text:
        now = time.time()
        agents = [n for n, a in app.cfg.agents.items() if a.enabled]
        tasks = [t for t in app.db.tasks() if t.started and t.started > now - 3 * 3600]
        spans = [s for s in app.orch.lead_spans if s[0] > now - 3 * 3600]
        out = Text()
        out.append("⏱ Timeline", "bold")
        if not tasks and not spans:
            out.append("  — chưa có hoạt động", "dim")
            return out
        t0 = min([t.started for t in tasks] + [s[0] for s in spans])
        t1 = now
        if t1 - t0 < 60:
            t0 = t1 - 60
        label_w = max(len(n) for n in agents) + 3
        width = max(20, (self.size.width or 110) - label_w - 2)
        scale = width / (t1 - t0)

        def col(ts: float) -> int:
            return min(width - 1, max(0, int((ts - t0) * scale)))

        out.append(f"   {time.strftime('%H:%M:%S', time.localtime(t0))} → bây giờ "
                   f"({fmt_dur(t1 - t0)})", "dim")
        for name in agents:
            cells: list[tuple[str, str]] = [("·", "grey30")] * width
            if name == app.cfg.lead:
                for s, e, _label in spans:
                    for c in range(col(s), col(e or now) + 1):
                        cells[c] = ("▒", "yellow")
            for t in tasks:
                if t.agent != name:
                    continue
                end = t.finished or now
                c0, c1 = col(t.started), col(end)
                style = BAR_STYLE.get(t.status, "white")
                for c in range(c0, c1 + 1):
                    cells[c] = ("█", style)
                tag = f"#{t.id}"
                if c1 - c0 + 1 >= len(tag) + 1:
                    for i, ch in enumerate(tag):
                        cells[c0 + 1 + i if c0 + 1 + i <= c1 else c0 + i] = (ch, f"bold black on {style}")
            out.append("\n")
            star = "★" if name == app.cfg.lead else " "
            out.append(f"{star}{name:<{label_w - 1}}", "bold" if name in app.busy_agents() else "")
            for ch, st in cells:
                out.append(ch, st)
        out.append("\n")
        out.append(" " * label_w)
        for label, st in (("█ đang chạy", "magenta"), ("█ xong", "green"), ("█ lỗi", "red"),
                          ("▒ trưởng nhóm lập kế hoạch/review", "yellow")):
            out.append(label + "   ", st)
        return out


# ============================================================================ app
class TeamApp(App):
    TITLE = "AI Team"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    #tabs { height: 1fr; }
    TabPane { padding: 0; }
    #board { height: 1fr; }
    #left { width: 46%; min-width: 40; }
    #right { width: 1fr; border-left: solid $primary-darken-2; }
    #agents { height: auto; padding: 0 1; background: $boost; }
    #goals { height: auto; max-height: 7; padding: 0 1; border-bottom: solid $primary-darken-3; }
    #tasks { height: 1fr; }
    #detail { height: auto; max-height: 9; padding: 0 1; background: $boost; }
    #log { height: 1fr; padding: 0 1; }
    #team-grid { layout: grid; grid-size: 2; grid-gutter: 0 1; height: 1fr; }
    .agentpane { border: round $panel-lighten-2; height: 1fr; }
    .agentpane.busy { border: heavy $accent; }
    .agentpane.missing { border: round $error 50%; }
    .pane-head { height: auto; padding: 0 1; background: $boost; }
    .pane-log { height: 1fr; padding: 0 1; }
    #timeline { height: auto; max-height: 14; padding: 0 1; border-top: solid $primary-darken-2; }
    #cmd { dock: bottom; margin: 0 0 1 0; }
    """
    BINDINGS = [
        Binding("ctrl+q", "quit", "Thoát"),
        Binding("ctrl+t", "toggle_tab", "Bảng việc ⇄ Đội"),
        Binding("ctrl+g", "approve", "Duyệt & chạy"),
        Binding("ctrl+r", "retry", "Chạy lại"),
        Binding("ctrl+k", "cancel_task", "Huỷ task"),
        Binding("ctrl+d", "diff", "Xem diff"),
        Binding("ctrl+y", "merge", "Merge"),
        Binding("ctrl+l", "syslog", "Log hệ thống"),
    ]

    def __init__(self, root: Path, cfg: Config, db: DB):
        super().__init__()
        self.root, self.cfg, self.db = root, cfg, db
        self.orch = Orchestrator(root, cfg, db, on_event=self.on_orch_event)
        self.view_task = SYSTEM
        self._rows: dict[int, tuple] = {}
        self._loop_task: asyncio.Task | None = None
        self._frame = 0
        self._booted = False

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs", initial="tab-board"):
            with TabPane("📋 Bảng việc", id="tab-board"):
                with Horizontal(id="board"):
                    with Vertical(id="left"):
                        yield Static(id="agents")
                        yield Static(id="goals")
                        yield DataTable(id="tasks", cursor_type="row", zebra_stripes=True)
                    with Vertical(id="right"):
                        yield Static(id="detail")
                        yield RichLog(id="log", wrap=True, markup=False, highlight=False,
                                      max_lines=5000)
            with TabPane("👥 Đội", id="tab-team"):
                with Vertical(id="team"):
                    with Vertical(id="team-grid"):
                        for name, a in self.cfg.agents.items():
                            if a.enabled:
                                yield AgentPane(name)
                    yield Timeline(id="timeline")
        yield Input(id="cmd", placeholder="Nhập mục tiêu cho trưởng nhóm, hoặc /help")
        yield Footer()

    async def on_mount(self) -> None:
        self.sub_title = str(self.root)
        table = self.query_one("#tasks", DataTable)
        table.add_column("#", key="id", width=4)
        table.add_column("Agent", key="agent", width=16)
        table.add_column("Trạng thái", key="status", width=10)
        table.add_column("⏱", key="time", width=7)
        table.add_column("Task", key="title")
        self.show_task(SYSTEM)
        self._preload_panes()
        await self.orch.setup()
        for n in self.cfg.notices:
            self.orch.log("ℹ " + n)
        self._booted = True
        self._loop_task = asyncio.get_running_loop().create_task(self.orch.run_forever())
        self.set_interval(0.5, self.refresh_view)
        self.refresh_view()
        self.query_one("#cmd", Input).focus()
        if not self.db.tasks():
            self.write_sys(HELP)

    def _preload_panes(self) -> None:
        """Nạp phần cuối log của task gần nhất cho mỗi ô agent."""
        tasks = self.db.tasks()
        for pane in self.query(AgentPane):
            last = [t for t in tasks if t.agent == pane.agent and t.started]
            if not last:
                pane.body.write(Text("chưa có việc nào", "dim"))
                continue
            t = last[-1]
            p = self.orch.log_path(t.id)
            label, style = STATUS.get(t.status, (t.status, ""))
            pane.body.write(Text(f"── #{t.id} {t.title} [{label}] ──", style))
            if p.exists():
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]:
                    pane.body.write(line)

    def pane(self, agent: str) -> AgentPane | None:
        try:
            return self.query_one(f"#{safe_id(agent)}", AgentPane)
        except Exception:
            return None

    # ------------------------------------------------------------------ sự kiện từ điều phối
    def on_orch_event(self, kind: str, data: dict) -> None:
        if kind == "log":
            if data.get("task_id") == self.view_task:
                self.query_one("#log", RichLog).write(data["line"])
            agent = data.get("agent")
            if agent and (p := self.pane(agent)):
                p.body.write(data.get("raw", data["line"]))
        elif kind == "activity":
            p = self.pane(data["agent"])
            if not p:
                return
            if "start" in data:
                act = data["start"]
                if act["task_id"] and act["task_id"] == self.view_task:
                    self.show_task(act["task_id"])  # bỏ dòng "chưa chạy" cũ
                head = f"#{act['task_id']} {act['title']}" if act["task_id"] else act["title"]
                p.body.write(Text(f"\n── ▶ {time.strftime('%H:%M:%S')}  {head}  [{act['label']}] ──",
                                 "bold cyan"))
            else:
                act = data["end"]
                st = act.get("status")
                label, style = STATUS.get(st, ("xong", "green")) if st else ("xong", "green")
                p.body.write(Text(f"── ■ {label} sau {fmt_dur(time.time() - act['started'])} ──", style))
        elif kind == "changed":
            self.refresh_view()

    def write_sys(self, text: str) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-board"
        if self.view_task != SYSTEM:
            self.show_task(SYSTEM)
        log = self.query_one("#log", RichLog)
        for line in text.splitlines():
            log.write(line)

    # ------------------------------------------------------------------ vẽ lại
    def busy_agents(self) -> set[str]:
        return {a for a, acts in self.orch.activity.items() if acts}

    def refresh_view(self) -> None:
        if not self._booted:
            return
        self._frame = (self._frame + 1) % len(SPIN)
        for fn in (self._refresh_agents, self._refresh_goals, self._refresh_table,
                   self._refresh_detail, self._refresh_panes, self._refresh_timeline):
            try:
                fn()
            except Exception as e:  # không để lỗi vẽ làm treo app
                self.log.error(f"refresh {fn.__name__}: {e!r}")

    def _refresh_agents(self) -> None:
        t = Text()
        busy = self.busy_agents()
        for name, a in self.cfg.agents.items():
            if not a.enabled:
                continue
            if name == self.cfg.lead:
                t.append(" ★", "yellow")
            if not a.installed():
                t.append(f" ✗ {name}", "red")
            elif self.orch.in_cooldown(name):
                t.append(f" ⏸ {name}", "yellow")
            elif name in busy:
                t.append(f" {SPIN[self._frame]} {name}", "bold magenta")
            else:
                t.append(f" ○ {name}", "green")
            t.append(f" ({a.label()}) ", "dim")
        if self.orch.paused:
            t.append("  ⏸ TẠM DỪNG", "bold yellow")
        self.query_one("#agents", Static).update(t)

    def _refresh_goals(self) -> None:
        goals = self.db.goals()[-4:]
        t = Text()
        if not goals:
            t.append("Chưa có mục tiêu. Gõ yêu cầu ở ô dưới cùng.", "dim")
        for i, g in enumerate(goals):
            label, style = GOAL_STATUS.get(g.status, (g.status, ""))
            if i:
                t.append("\n")
            t.append(f"🎯 #{g.id} ", "bold")
            t.append(f"[{label}", style)
            t.append(f" · vòng {g.round}]" if g.round > 1 else "]", style)
            t.append(f" {g.text[:80]}")
            if g.summary and g.status in ("done", "incomplete", "failed", "awaiting"):
                t.append(f"\n   ↳ {g.summary[:160]}", "dim")
        self.query_one("#goals", Static).update(t)

    def _refresh_table(self) -> None:
        table = self.query_one("#tasks", DataTable)
        now = time.time()
        for task in self.db.tasks():
            label, style = STATUS.get(task.status, (task.status, ""))
            prefix = "↳ " if task.parent_id else ""
            deps = f" ⟵{','.join(map(str, task.depends_on))}" if task.depends_on else ""
            agent = task.agent + (f"@{task.effort}" if task.effort else "")
            dur = fmt_dur((task.finished or now) - task.started) if task.started else ""
            row = (str(task.id), agent, label, dur, f"{prefix}{task.title}{deps}", style)
            key = str(task.id)
            if task.id not in self._rows:
                table.add_row(Text(row[0]), Text(row[1]), Text(row[2], style), Text(row[3], "dim"),
                              Text(row[4]), key=key)
                self._rows[task.id] = row
            elif self._rows[task.id] != row:
                table.update_cell(key, "agent", Text(row[1]))
                table.update_cell(key, "status", Text(row[2], style))
                table.update_cell(key, "time", Text(row[3], "dim"))
                table.update_cell(key, "title", Text(row[4]))
                self._rows[task.id] = row

    def _refresh_detail(self) -> None:
        d = self.query_one("#detail", Static)
        if self.view_task < 0:
            task = self.db.task(-self.view_task)
            if task:
                label, style = STATUS.get(task.status, (task.status, ""))
                t = Text()
                t.append(f"Δ Diff #{task.id} ", "bold")
                t.append(f"{task.agent} ", "bold cyan")
                t.append(f"[{label}] ", style)
                t.append(task.title, "bold")
                if task.status in ("review", "conflict"):
                    t.append("\nCtrl+Y / /merge để merge · /reject <task> [góp ý] để từ chối", "yellow")
                d.update(t)
            return
        if self.view_task == SYSTEM:
            d.update(Text("📜 Log hệ thống — chọn 1 task trong bảng để xem log của nó · "
                          "Ctrl+T để xem cả đội", "bold"))
            return
        task = self.db.task(self.view_task)
        if not task:
            return
        label, style = STATUS.get(task.status, (task.status, ""))
        a = self.cfg.agents.get(task.agent)
        t = Text()
        t.append(f"#{task.id} ", "bold")
        t.append(f"{task.agent} ", "bold cyan")
        if a:
            t.append(f"({a.label(task.model, task.effort)}) ", "dim")
        t.append(f"[{label}] ", style)
        t.append(task.title, "bold")
        if task.source and task.source.startswith("delegate:"):
            t.append(f"  (được {task.source.split(':', 1)[1]} giao)", "dim")
        t.append("\n" + task.prompt[:300].replace("\n", " "), "dim")
        if task.attempts:
            t.append(f"  · đã sửa lỗi test {task.attempts} lần", "yellow")
        if task.status == "review":
            t.append("\n👀 Chờ duyệt — Ctrl+D xem diff, Ctrl+Y merge, /reject <task> [góp ý]", "yellow")
        if task.error:
            t.append(f"\n⚠ {task.error}", "red")
        elif task.result and task.status != "running":
            t.append(f"\n↳ {task.result[:240].replace(chr(10), ' ')}", "green")
        d.update(t)

    def _refresh_panes(self) -> None:
        now = time.time()
        tasks = self.db.tasks()
        usage = self.db.usage(today_start())
        for pane in self.query(AgentPane):
            name = pane.agent
            a = self.cfg.agents[name]
            acts = self.orch.current_activities(name)
            mine = [t for t in tasks if t.agent == name]
            n_done = sum(t.status == "done" for t in mine)
            n_fail = sum(t.status in ("failed", "blocked", "conflict") for t in mine)
            n_wait = sum(t.status in ("queued", "draft", "review") for t in mine)
            t = Text()
            if name == self.cfg.lead:
                t.append("★ ", "yellow")
            t.append(name, "bold")
            t.append(f"  {a.label()}", "cyan")
            t.append(f"   ✓{n_done}", "green")
            t.append(f" ✗{n_fail}", "red" if n_fail else "dim")
            t.append(f" ⏳{n_wait}", "cyan" if n_wait else "dim")
            u = usage.get(name)
            if u:
                t.append(f"   hôm nay {u['runs']} lượt · {fmt_dur(u['secs'])} · "
                         f"~{(u['prompt_chars'] + u['output_chars']) // 4 // 1000}k token", "dim")
            if not a.installed():
                t.append(f"\n✗ chưa cài lệnh '{a.binary}'", "red")
            elif self.orch.in_cooldown(name) and not acts:
                t.append(f"\n⏸ hết hạn mức — nghỉ đến {self.orch.cooldown_label(name)}", "bold yellow")
                fb = self.orch.pick_fallback(name)
                t.append(f"  · task mới chuyển cho {fb}" if fb else "  · task của nó chờ hồi hạn mức",
                         "yellow")
            elif acts:
                for act in acts:
                    head = f"#{act['task_id']} {act['title']}" if act["task_id"] else act["title"]
                    t.append(f"\n{SPIN[self._frame]} ", "bold magenta")
                    t.append(head[:60], "bold")
                    t.append(f"  [{act['label']}]", "cyan")
                    t.append(f"  ⏱ {fmt_dur(now - act['started'])}", "magenta")
                    t.append(f"  · {act['lines']} dòng", "dim")
                    quiet = now - act["last_at"]
                    if quiet > SILENT_WARN:
                        t.append(f"  · im lặng {fmt_dur(quiet)}", "yellow")
                    if act["last_line"]:
                        t.append(f"\n  › {act['last_line'][:90]}", "dim")
            else:
                last = next((x for x in reversed(mine) if x.finished), None)
                t.append("\n○ rảnh", "green")
                if last:
                    label, style = STATUS.get(last.status, (last.status, ""))
                    t.append(f"  · gần nhất #{last.id} ", "dim")
                    t.append(label, style)
            pane.head.update(t)
            pane.set_class(bool(acts), "busy")
            pane.set_class(not a.installed(), "missing")

    def _refresh_timeline(self) -> None:
        tl = self.query_one("#timeline", Timeline)
        tl.update(tl.build(self))

    def show_task(self, tid: int) -> None:
        self.view_task = tid
        log = self.query_one("#log", RichLog)
        log.clear()
        path = (self.orch.logs / "system.log") if tid == SYSTEM else self.orch.log_path(tid)
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]:
                log.write(line)
        elif tid != SYSTEM:
            log.write("(task chưa chạy — chưa có log)")
        if self._booted:
            self._refresh_detail()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key and event.row_key.value:
            tid = int(event.row_key.value)
            if tid != self.view_task:
                self.show_task(tid)

    def selected_task(self) -> int | None:
        if self.view_task == SYSTEM:
            return None
        return abs(self.view_task)

    async def show_diff(self, tid: int) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-board"
        text = await self.orch.diff(tid)
        self.view_task = -tid
        log = self.query_one("#log", RichLog)
        log.clear()
        for line in text.splitlines()[:4000]:
            if line.startswith("+") and not line.startswith("+++"):
                st = "green"
            elif line.startswith("-") and not line.startswith("---"):
                st = "red"
            elif line.startswith("@@"):
                st = "cyan"
            elif line.startswith(("diff --git", "+++", "---", "Diff #")):
                st = "bold"
            else:
                st = ""
            log.write(Text(line, st))
        self._refresh_detail()

    # ------------------------------------------------------------------ phím tắt
    def action_toggle_tab(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = "tab-team" if tabs.active == "tab-board" else "tab-board"
        self.refresh_view()

    def action_approve(self) -> None:
        n = self.orch.approve()
        if not n:
            self.notify("Không có task nháp nào cần duyệt")

    def action_retry(self) -> None:
        tid = self.selected_task()
        self.notify(self.orch.retry(tid) if tid else "Chọn 1 task trong bảng trước")

    def action_cancel_task(self) -> None:
        tid = self.selected_task()
        self.notify(self.orch.cancel(tid) if tid else "Chọn 1 task trong bảng trước")

    async def action_diff(self) -> None:
        tid = self.selected_task()
        if not tid:
            self.notify("Chọn 1 task trong bảng trước")
            return
        await self.show_diff(tid)

    async def action_merge(self) -> None:
        tid = self.selected_task()
        if not tid:
            self.notify("Chọn 1 task trong bảng trước")
            return
        self.notify(await self.orch.merge(tid))
        self.refresh_view()

    def action_syslog(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-board"
        self.show_task(SYSTEM)

    async def action_quit(self) -> None:
        for run in list(self.orch.runs.values()):
            if run is not None:
                run.cancel()
        if self._loop_task:
            self._loop_task.cancel()
        self.exit()

    # ------------------------------------------------------------------ ô lệnh
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        if not text.startswith("/"):
            if not self.cfg.agents.get(self.cfg.lead):
                self.notify(f"Không có trưởng nhóm '{self.cfg.lead}' trong cấu hình", severity="error")
                return
            self.orch.new_goal(text)
            self.show_task(SYSTEM)
            return
        try:
            self.run_command(text)
        except Exception as e:
            self.notify(f"Lỗi: {e}", severity="error")

    def usage_text(self) -> str:
        now = time.time()
        out = []
        for label, since in (("Hôm nay", today_start()), ("7 ngày", now - 7 * 86400)):
            u = self.db.usage(since)
            out.append(f"{label}:")
            out.append(f"  {'agent':12} {'lượt':>5} {'thời gian':>10} {'~token':>8} {'lỗi':>4} {'hết HM':>6}")
            for name in self.cfg.agents:
                r = u.get(name)
                if not r:
                    continue
                tok = (r["prompt_chars"] + r["output_chars"]) // 4
                out.append(f"  {name:12} {r['runs']:>5} {fmt_dur(r['secs']):>10} {tok // 1000:>7}k "
                           f"{r['failed']:>4} {r['ratelimits']:>6}")
        cds = [f"{a} đến {self.orch.cooldown_label(a)}" for a in self.cfg.agents if self.orch.in_cooldown(a)]
        out.append("Đang tạm nghỉ: " + (", ".join(cds) if cds else "không"))
        out.append("(~token = ước tính từ độ dài prompt và output, chưa gồm file agent tự đọc)")
        return "\n".join(out)

    def _check_effort(self, agent: str, effort: str | None) -> None:
        a = self.cfg.agents[agent]
        if effort and effort != "-" and a.efforts and effort not in a.efforts:
            self.notify(f"'{effort}' không có trong danh sách của {agent}: {', '.join(a.efforts)} "
                        f"— vẫn dùng, nhưng CLI có thể báo lỗi", severity="warning")

    def run_command(self, text: str) -> None:
        cmd, _, rest = text[1:].partition(" ")
        cmd, rest = cmd.lower(), rest.strip()
        o = self.orch
        agents = self.cfg.active_agents()

        def num(s: str) -> int:
            return int(s.lstrip("#"))

        if cmd in ("help", "h", "?"):
            self.write_sys(HELP)
        elif cmd in ("task", "t"):
            spec, _, prompt = rest.partition(" ")
            m = re.fullmatch(r"([^:@]+)(?::([^@]+))?(?:@(.+))?", spec)
            if not m or m.group(1) not in agents or not prompt.strip():
                self.notify(f"Dùng: /task <agent>[:model][@effort] <nội dung>  — agent: "
                            f"{', '.join(agents)}", severity="warning")
                return
            agent, model, effort = m.group(1), m.group(2), m.group(3)
            self._check_effort(agent, effort)
            o.add_task(agent, prompt.strip(), model=model, effort=effort)
        elif cmd in ("model", "effort"):
            parts = rest.split(maxsplit=1)
            if not parts or parts[0] not in self.cfg.agents:
                self.notify(f"Dùng: /{cmd} <agent> <giá trị|->  — agent: {', '.join(self.cfg.agents)}",
                            severity="warning")
                return
            if len(parts) == 1:
                a = self.cfg.agents[parts[0]]
                hint = f" · effort hợp lệ: {', '.join(a.efforts)}" if a.efforts else ""
                self.notify(f"{a.name}: {a.label()}{hint}")
                return
            if cmd == "effort":
                self._check_effort(parts[0], parts[1].strip())
            self.notify(o.set_agent_option(parts[0], cmd, parts[1].strip()))
        elif cmd == "set":
            tid, key, *val = rest.split(maxsplit=2)
            if key not in ("model", "effort"):
                self.notify("Dùng: /set <task> model|effort <giá trị|->", severity="warning")
                return
            task = o.db.task(num(tid))
            if task and key == "effort" and val:
                self._check_effort(task.agent, val[0])
            self.notify(o.set_task_option(num(tid), key, val[0] if val else None))
        elif cmd == "diff":
            self.run_worker(self.show_diff(num(rest)), exclusive=False)
        elif cmd == "merge":
            async def _m(tid=num(rest)):
                self.notify(await o.merge(tid))
                self.refresh_view()
            self.run_worker(_m(), exclusive=False)
        elif cmd == "reject":
            tid, _, fb = rest.partition(" ")
            async def _r(tid=num(tid), fb=fb.strip() or None):
                self.notify(await o.reject(tid, fb))
                self.refresh_view()
            self.run_worker(_r(), exclusive=False)
        elif cmd == "verify":
            v = self.cfg.verify
            if not rest:
                self.notify(f"Lệnh kiểm tra: {v.command or '(tắt)'} · sửa tối đa {v.max_fix_attempts} lần"
                            + (f" · người sửa: {v.fix_agent}" if v.fix_agent else ""))
                return
            if rest.lower() in ("off", "-", "tắt"):
                save_project_setting(self.root, "verify_command", None)
                v.command = ""
                o.log("⚙ Tắt kiểm tra sau mỗi task cho dự án này.")
            else:
                save_project_setting(self.root, "verify_command", rest)
                v.command = rest
                o.log(f"⚙ Kiểm tra sau mỗi task: `{rest}` (sửa tối đa {v.max_fix_attempts} lần)")
        elif cmd == "usage":
            self.write_sys(self.usage_text())
        elif cmd == "cooldown":
            parts = rest.split()
            if not parts:
                self.notify("Dùng: /cooldown <agent> <phút|off>", severity="warning")
                return
            mins = None if len(parts) < 2 or parts[1].lower() in ("off", "0", "-") else int(parts[1])
            self.notify(o.set_cooldown_manual(parts[0], mins))
        elif cmd == "go":
            n = o.approve(num(rest) if rest else None)
            self.notify(f"Đã duyệt {n} task" if n else "Không có task nháp")
        elif cmd == "assign":
            tid, agent = shlex.split(rest)[:2]
            self.notify(o.assign(num(tid), agent))
        elif cmd == "edit":
            tid, _, prompt = rest.partition(" ")
            self.notify(o.edit(num(tid), prompt.strip()))
        elif cmd == "retry":
            self.notify(o.retry(num(rest)))
        elif cmd == "cancel":
            self.notify(o.cancel(num(rest)))
        elif cmd == "review":
            self.notify(o.force_review(num(rest)))
        elif cmd == "note":
            o.note(rest)
        elif cmd == "pause":
            o.paused = True
            o.log("⏸ Tạm dừng: không bắt đầu task mới (task đang chạy vẫn tiếp tục).")
        elif cmd == "resume":
            o.paused = False
            o.log("▶ Tiếp tục.")
        elif cmd == "log":
            self.query_one("#tabs", TabbedContent).active = "tab-board"
            self.show_task(SYSTEM if rest in ("", "sys", "0") else num(rest))
        elif cmd == "team":
            self.query_one("#tabs", TabbedContent).active = "tab-team"
        elif cmd == "board":
            self.query_one("#tabs", TabbedContent).active = "tab-board"
        elif cmd == "agents":
            lines = []
            for n, a in self.cfg.agents.items():
                st = "✓" if a.installed() else "✗ chưa cài"
                lead = " ★ trưởng nhóm" if n == self.cfg.lead else ""
                lines.append(f"{n:12} {st}{lead}\n   model/effort: {a.label()}"
                             + (f"   (effort hợp lệ: {', '.join(a.efforts)})" if a.efforts else "")
                             + f"\n   lệnh: {' '.join(a.argv('<prompt>'))}\n   vai trò: {a.role}")
            self.write_sys("\n".join(lines))
        elif cmd in ("quit", "exit", "q"):
            self.call_later(self.action_quit)
        else:
            self.notify(f"Không hiểu lệnh /{cmd} — gõ /help", severity="warning")
        self.refresh_view()
