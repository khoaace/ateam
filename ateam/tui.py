"""Giao diện terminal (Textual): tab Bảng việc + tab Đội (log từng agent & timeline)."""

from __future__ import annotations

import asyncio
import difflib
import inspect
import re
import shlex
import time
import unicodedata
from pathlib import Path

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (Button, Checkbox, DataTable, Footer, Header, Input, OptionList,
                             RichLog, Select, Static, TabbedContent, TabPane)
from textual.widgets.option_list import Option

from . import clipboard, mentions
from .config import (CUSTOM_FILE, LEAD_ALIAS, NAME_RE, WORKFLOW_TEMPLATES, AgentConfig, Config,
                     Workflow, WorkflowStep, agent_from_dict, agent_templates, describe_models,
                     load_config, load_custom, load_state, mark_setup_done, save_custom_item,
                     save_project_setting, save_setup, workflow_to_dict)
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
STATUS_ICON = {"draft": "✎", "queued": "◌", "done": "✓", "failed": "✗", "cancelled": "–",
               "blocked": "⊘", "conflict": "≠", "review": "◆"}  # running: dùng SPIN
BAR_STYLE = {"running": "magenta", "done": "green", "failed": "red", "cancelled": "grey50",
             "blocked": "red", "conflict": "yellow", "review": "yellow"}
GOAL_STATUS = {
    "planning": ("đang lập kế hoạch", "magenta"),
    "awaiting": ("chờ duyệt (F2)", "yellow"),
    "cancelled": ("đã bỏ", "dim"),
    "running": ("đang làm", "cyan"),
    "reviewing": ("đang review", "magenta"),
    "done": ("hoàn thành", "green"),
    "incomplete": ("chưa xong", "yellow"),
    "failed": ("lỗi", "red"),
}
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SILENT_WARN = 60  # giây không có output -> cảnh báo "im lặng"
PANE_MODELS = 5   # số model gợi ý hiện trong ô agent (đủ xem bằng /models <agent>)
RESET = "\x00reset"  # lựa chọn "quay về mặc định" trong bảng chọn

HELP = """\
Gõ một câu bình thường  → giao MỤC TIÊU cho trưởng nhóm lập kế hoạch & chia việc.

Giao việc:
  /task <agent> <nội dung>          giao tay (vd: /task codex viết test cho utils.py)
  /task <agent>@<effort> <nội dung> giao kèm effort riêng (vd: /task codex@xhigh tìm lỗi deadlock)
  /task <agent>:<model>@<effort> …  giao kèm cả model riêng
  /go [mục tiêu]                    duyệt kế hoạch nháp và chạy (F2 hoặc Ctrl+G, hoặc nút trong khung
                                    "Duyệt kế hoạch" hiện phía trên ô nhập khi có kế hoạch chờ)
  /drop [mục tiêu]                  bỏ kế hoạch nháp (huỷ mọi task nháp của nó)
  /assign <task> <agent>            đổi người làm 1 task
  /edit <task> <nội dung>           sửa nội dung task (khi chưa chạy)
  /set <task> effort|model <giá trị>
                                    đổi effort/model riêng cho 1 task ('-' = theo agent)
  /retry <task>   /cancel <task>    chạy lại (F5 hoặc Ctrl+R) / huỷ (Ctrl+K) task
  /review <mục tiêu>                bắt trưởng nhóm review ngay
  /note <nội dung>                  ghi chú chung cho cả đội

Lệnh, file, ảnh trong ô nhập:
  gõ / ở đầu ô nhập                 hiện danh sách lệnh kèm mô tả, gõ tiếp để lọc
  gõ @ trong ô nhập                 hiện danh sách file/thư mục của dự án, gõ tiếp để lọc
                                    ↑↓ chọn · Tab/Enter chèn · Esc đóng (chọn thư mục để đi vào trong)
                                    khi chạy, @đường-dẫn được đổi sang cú pháp của từng agent (xem /agents)
  Ctrl+V trong ô nhập               dán ảnh từ clipboard (lưu vào .ateam/images, chèn @ảnh);
                                    kéo-thả file ảnh vào terminal cũng thành @ảnh. Mỗi agent nhận ảnh
                                    theo cách CLI đó hỗ trợ (codex: --image, opencode: -f)

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
  /model <agent>   /effort <agent>  mở bảng chọn từ danh sách agent hỗ trợ (hoặc bấm vào ô agent ở tab Đội)
  /model <agent> -                  quay về mặc định trong config (tương tự /effort <agent> -)
  /models [agent]                   xem model & effort mỗi agent hỗ trợ
  /models <agent> làm mới           hỏi CLI danh sách model thật (opencode models, agy models)
  /agents                           xem model, effort, mức effort hợp lệ của từng agent
  /setup                            mở lại màn hình thiết lập: bật/tắt agent, trưởng nhóm, model, effort

Agent & workflow tuỳ chỉnh:
  /custom                           thêm/sửa/xoá agent riêng (CLI bất kỳ) và workflow (chuỗi bước dựng sẵn)
  /flow <tên> <mục tiêu>            chạy mục tiêu theo workflow — các bước thành task ngay, không cần lập kế hoạch
  /flow                             xem các workflow đang có

Khác:
  /pause  /resume                   tạm dừng / tiếp tục nhận task mới
  /compact [trọng tâm]              trưởng nhóm tóm tắt ghi chú, mục tiêu & log cho prompt sau gọn hơn
  /log <task>   /log sys            xem log 1 task / log hệ thống (Ctrl+L)
  /team  /board                     chuyển tab Đội / Bảng việc (Ctrl+T)
  /help                             trợ giúp này (F1)
  F2 = Ctrl+G, F5 = Ctrl+R          dùng F2/F5 khi terminal chặn phím Ctrl (vd terminal trong VS Code/
                                    Cursor trên Mac: Ctrl+G là Go to Line, Ctrl+R là Run Recent).
                                    MacBook: giữ fn khi bấm F2/F5
  /quit                             thoát (Ctrl+Q) — agent đang chạy sẽ bị dừng"""

WELCOME = """\
👋 Chào mừng tới ateam — bắt đầu nhanh:
  • Gõ một mục tiêu (vd: Thêm trang đăng nhập) → trưởng nhóm lập kế hoạch, Enter (hoặc F2) để duyệt & chạy
  • /task codex viết test cho utils.py → giao tay cho 1 agent
  • Gõ / để xem các lệnh · @ để nhắc file · Ctrl+V dán ảnh
  • F1 hoặc /help: toàn bộ lệnh & phím tắt · Ctrl+T: xem cả đội làm việc"""

# lệnh cho bảng gợi ý khi gõ "/" (tên, tham số, mô tả ngắn) — giữ khớp với TeamApp.run_command
COMMANDS = [
    ("task", "<agent> <nội dung>", "giao tay cho 1 agent"),
    ("go", "[mục tiêu]", "duyệt kế hoạch nháp và chạy"),
    ("drop", "[mục tiêu]", "bỏ kế hoạch nháp (huỷ mọi task nháp của nó)"),
    ("flow", "<tên> <mục tiêu>", "chạy mục tiêu theo workflow"),
    ("assign", "<task> <agent>", "đổi người làm 1 task"),
    ("edit", "<task> <nội dung>", "sửa nội dung task chưa chạy"),
    ("set", "<task> effort|model <giá trị>", "effort/model riêng cho 1 task"),
    ("retry", "<task>", "chạy lại task"),
    ("cancel", "<task>", "huỷ task"),
    ("review", "<mục tiêu>", "bắt trưởng nhóm review ngay"),
    ("note", "<nội dung>", "ghi chú chung cho cả đội"),
    ("diff", "<task>", "xem thay đổi của task"),
    ("merge", "<task>", "duyệt và merge task đang chờ"),
    ("reject", "<task> [góp ý]", "từ chối, có góp ý thì giao làm lại"),
    ("verify", "[lệnh|off]", "lệnh kiểm tra sau mỗi task"),
    ("model", "<agent> [tên|-]", "đổi model của agent"),
    ("effort", "<agent> [mức|-]", "đổi effort của agent"),
    ("models", "[agent] [làm mới]", "xem model & effort hỗ trợ"),
    ("agents", "", "cấu hình, lệnh chạy của từng agent"),
    ("setup", "", "màn hình thiết lập đội"),
    ("custom", "", "agent & workflow tuỳ chỉnh"),
    ("usage", "", "thống kê lượt chạy, thời gian, token"),
    ("cooldown", "<agent> <phút|off>", "cho agent tạm nghỉ"),
    ("compact", "[trọng tâm]", "tóm tắt ngữ cảnh chung cho prompt gọn lại"),
    ("pause", "", "tạm dừng nhận task mới"),
    ("resume", "", "tiếp tục nhận task"),
    ("log", "[task|sys]", "xem log 1 task / log hệ thống"),
    ("team", "", "chuyển sang tab Đội"),
    ("board", "", "chuyển sang tab Bảng việc"),
    ("help", "", "toàn bộ lệnh & phím tắt"),
    ("quit", "", "thoát"),
]
COMMAND_ALIASES = {"h": "help", "?": "help", "t": "task", "flows": "flow", "workflow": "custom",
                   "workflows": "custom", "agent-moi": "custom", "exit": "quit", "q": "quit"}


def suggest_command(cmd: str) -> str | None:
    """Lệnh gần giống nhất với lệnh gõ sai (vd 'stup' -> 'setup'), hoặc None."""
    names = [c[0] for c in COMMANDS]
    pre = [n for n in names if n.startswith(cmd)] if cmd else []
    if len(pre) == 1:
        return pre[0]
    close = difflib.get_close_matches(cmd, names + list(COMMAND_ALIASES), n=1, cutoff=0.6)
    return COMMAND_ALIASES.get(close[0], close[0]) if close else None


def command_usage(cmd: str) -> str:
    """'Dùng: /lệnh <tham số> — mô tả', kèm gợi ý lệnh khác bắt đầu bằng cùng tên (/set -> /setup)."""
    name = COMMAND_ALIASES.get(cmd, cmd)
    spec = next((c for c in COMMANDS if c[0] == name), None)
    if not spec:
        return f"Không hiểu lệnh /{cmd}"
    out = f"Dùng: /{name} {spec[1]} — {spec[2]}".replace("  ", " ")
    others = [n for n, _a, _d in COMMANDS if n != name and n.startswith(name)]
    if others:
        out += " · hay ý bạn là " + ", ".join("/" + n for n in others) + "?"
    return out


def command_needs_args(cmd: str) -> bool:
    name = COMMAND_ALIASES.get(cmd, cmd)
    return next((a for n, a, _d in COMMANDS if n == name), "").startswith("<")


def match_commands(query: str) -> list[tuple[str, str, str]]:
    """Lệnh khớp chữ đang gõ sau '/': bắt đầu bằng query trước, rồi chứa query."""
    q = query.lower()
    first = [c for c in COMMANDS if c[0].startswith(q)]
    if len(q) < 2:  # 1 chữ: chỉ lệnh bắt đầu bằng chữ đó, đỡ nhiễu
        return first
    return first + [c for c in COMMANDS if q in c[0] and c not in first]


def help_text() -> Text:
    """HELP có màu: tiêu đề mục đậm, lệnh màu cyan, mô tả thường."""
    t = Text()
    for i, line in enumerate(HELP.splitlines()):
        if i:
            t.append("\n")
        if not line.startswith(" "):
            t.append(line, "bold" if line.endswith(":") else "")
        elif line[2:3] != " ":  # "  /lệnh …   mô tả"
            t.append(line[:36], "bold cyan")
            t.append(line[36:])
        else:  # dòng mô tả nối tiếp
            t.append(line)
    return t


def flow_chunks(chunks: list[Text], width: int) -> Text:
    """Ghép các mảnh thành nhiều dòng, chỉ xuống dòng *giữa* các mảnh (không cắt đôi 1 mảnh)."""
    out, used = Text(), 0
    for ch in chunks:
        w = ch.cell_len
        if used and width and used + w > width:
            out.append("\n")
            used = 0
        out.append_text(ch)
        used += w
    return out


def fmt_dur(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_tokens(n: int) -> str:
    """850 · 1.2k · 37k — số token ước tính, không làm tròn mọi thứ nhỏ thành '0k'."""
    if n < 1000:
        return str(n)
    return f"{n / 1000:.1f}k" if n < 10000 else f"{n // 1000}k"


def today_start() -> float:
    lt = time.localtime()
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def safe_id(name: str, prefix: str = "pane-") -> str:
    return prefix + re.sub(r"[^A-Za-z0-9_-]", "_", name)


# ============================================================================ widgets
class TextInput(Input):
    """Ô nhập gõ tiếng Việt không lỗi dấu.

    Bộ gõ (OpenKey/EVKey… để "Unicode tổ hợp", hoặc gửi dấu thành ký tự riêng) có thể đưa vào
    chữ dạng tách rời "e" + dấu mũ U+0302 + dấu nặng U+0323. Terminal vẽ dấu rời lệch khỏi chữ
    ("lỗi font"), còn Backspace của Input chỉ xoá một code point nên khi bộ gõ xoá chữ cũ để thay
    chữ mới thì dấu sót lại. Vì vậy sau mỗi lần sửa ta gộp về dạng dựng sẵn (NFC), và Backspace/Delete
    xoá trọn một chữ cùng các dấu đi kèm.
    """

    def _compose_nfc(self) -> None:
        value, cur = self.value, self.cursor_position
        before = unicodedata.normalize("NFC", value[:cur])
        after = unicodedata.normalize("NFC", value[cur:])
        if before + after != value:
            self.value = before + after
            self.cursor_position = len(before)

    def replace(self, text: str, start: int, end: int) -> None:
        super().replace(text, start, end)
        self._compose_nfc()

    def insert_text_at_cursor(self, text: str) -> None:
        super().insert_text_at_cursor(text)
        self._compose_nfc()

    def _no_selection(self) -> bool:
        sel = getattr(self, "selection", None)  # Textual cũ chưa có chọn vùng trong Input
        return sel is None or sel.is_empty

    def action_delete_left(self) -> None:
        cur = self.cursor_position
        if self._no_selection() and cur > 0:
            start = cur - 1
            while start > 0 and unicodedata.combining(self.value[start]):
                start -= 1
            self.delete(start, cur)
        else:
            super().action_delete_left()

    def action_delete_right(self) -> None:
        cur, value = self.cursor_position, self.value
        if self._no_selection() and cur < len(value):
            end = cur + 1
            while end < len(value) and unicodedata.combining(value[end]):
                end += 1
            self.delete(cur, end)
        else:
            super().action_delete_right()


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

    def on_click(self, event) -> None:
        if event.widget is self.head:  # bấm vào tiêu đề ô -> chọn model rồi effort
            self.app.open_picker(self.agent, "model", then_effort=True)


def choice_line(label: str, items: list[str], current: str, limit: int = 0) -> Text:
    """'model: [opus] sonnet haiku … +3' — mục đang dùng được tô đậm."""
    t = Text(f"{label}: ", "dim")
    if not items:
        t.append("(để CLI tự chọn)" if label == "model" else "(không có)", "dim")
        return t
    shown = items[:limit] if limit else items
    if current and current not in shown:
        shown = [current] + shown[:-1] if limit else [current] + shown
    for i, it in enumerate(shown):
        if i:
            t.append(" ")
        t.append(it, "bold reverse cyan" if it == current else "cyan")
    if len(items) > len(shown):
        t.append(f" … +{len(items) - len(shown)}", "dim")
    return t


class ChoiceScreen(ModalScreen):
    """Bảng chọn model/effort cho 1 agent. Trả về giá trị chọn, RESET, hoặc None (Esc)."""

    BINDINGS = [Binding("escape", "dismiss_none", "Đóng", priority=True)]
    DEFAULT_CSS = """
    ChoiceScreen { align: center middle; }
    #choice-box { width: 60; height: auto; max-height: 80%; border: thick $accent;
                  background: $surface; padding: 0 1; }
    #choice-list { height: auto; max-height: 30; }
    """

    def __init__(self, title: str, items: list[str], current: str, default_label: str):
        super().__init__()
        self.title_text, self.items, self.current = title, items, current
        self.default_label = default_label

    def compose(self) -> ComposeResult:
        opts = [Option(("● " if it == self.current else "  ") + it, id=f"i{n}")
                for n, it in enumerate(self.items)]
        opts.append(Option(("● " if not self.current else "  ") + self.default_label, id="reset"))
        with Vertical(id="choice-box"):
            yield Static(Text(self.title_text, "bold"))
            yield OptionList(*opts, id="choice-list")
            yield Static(Text("Enter: chọn · Esc: đóng · tên khác: /model <agent> <tên>", "dim"))

    def on_mount(self) -> None:
        ol = self.query_one(OptionList)
        ol.highlighted = self.items.index(self.current) if self.current in self.items else len(self.items)
        ol.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        oid = event.option.id or ""
        self.dismiss(RESET if oid == "reset" else self.items[int(oid[1:])])

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen):
    """Toàn bộ lệnh & phím tắt trong một bảng nổi cuộn được (/help, F1)."""

    BINDINGS = [Binding("escape", "close", "Đóng", priority=True),
                Binding("f1", "close", "Đóng", priority=True)]
    DEFAULT_CSS = """
    HelpScreen { align: center middle; }
    #help-box { width: 124; max-width: 100%; height: 90%; border: thick $accent;
                background: $surface; padding: 0 1; }
    #help-body { height: 1fr; }
    #help-foot { height: 1; color: $text-muted; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static(Text("Trợ giúp ateam", "bold"))
            with VerticalScroll(id="help-body"):
                yield Static(help_text())
            yield Static("↑↓ / PgUp PgDn cuộn · Esc hoặc F1 đóng", id="help-foot")

    def on_mount(self) -> None:
        self.query_one("#help-body").focus()

    def action_close(self) -> None:
        self.dismiss(None)


class SetupScreen(ModalScreen):
    """Thiết lập lần đầu (hoặc /setup): bật agent nào, trưởng nhóm, model và effort từng agent.

    Trước khi hiện form, hỏi song song các CLI có lệnh liệt kê model (opencode models, agy models)
    để bảng chọn có sẵn model thật; CLI khác dùng danh mục có sẵn. Trả về dict lựa chọn, hoặc
    None nếu bỏ qua (Esc)."""

    BINDINGS = [Binding("escape", "skip", "Bỏ qua", priority=True),
                Binding("ctrl+s", "save", "Lưu", priority=True)]
    DEFAULT_CSS = """
    SetupScreen { align: center middle; }
    #setup-box { width: 110; max-width: 100%; height: auto; max-height: 95%; border: thick $accent;
                 background: $surface; padding: 0 1; }
    #setup-rows { height: auto; max-height: 32; }
    .setup-row, #setup-lead-row { height: 3; }
    .setup-row Checkbox { width: 22; }
    .setup-model { width: 42; }
    .setup-effort { width: 18; }
    .setup-note { width: 1fr; height: 3; padding: 1 0 0 1; color: $text-muted;
                  text-wrap: nowrap; text-overflow: ellipsis; }
    #setup-head { height: 1; color: $text-muted; text-style: bold; margin-top: 1; }
    #setup-lead-row > Static { width: 22; padding: 1 0 0 1; }
    #setup-lead { width: 42; }
    #setup-buttons { height: auto; align: right middle; }
    #setup-buttons Button { margin-left: 2; }
    """

    def __init__(self, cfg: Config, orch: Orchestrator, timeout: float = 20):
        super().__init__()
        self.cfg, self.orch, self.timeout = cfg, orch, timeout
        self.fetch: dict[str, str] = {}
        self.ready = False

    def compose(self) -> ComposeResult:
        with Vertical(id="setup-box"):
            yield Static(Text("Thiết lập đội AI", "bold"))
            yield Static(id="setup-status")
            yield Vertical(id="setup-rows")
            with Horizontal(id="setup-buttons"):
                yield Button("Agent & workflow tuỳ chỉnh…", id="setup-custom")
                yield Button("Bỏ qua (Esc)", id="setup-skip")
                yield Button("Lưu & bắt đầu (Ctrl+S)", id="setup-save", variant="primary",
                             disabled=True)

    def on_mount(self) -> None:
        for n, a in self.cfg.agents.items():
            if a.models_command and a.installed():
                self.fetch[n] = "đang hỏi…"
            elif not a.installed():
                self.fetch[n] = f"chưa cài '{a.binary}'"
            else:
                self.fetch[n] = f"danh mục có sẵn ({len(a.models)} model)" if a.models else "CLI tự chọn"
        self._show_status()
        self.run_worker(self._prefetch(), exclusive=True)

    def _show_status(self) -> None:
        t = Text("Đang lấy danh sách model từ các CLI…\n" if not self.ready else
                 "Chọn agent tham gia, model và effort. Tab/↑↓ để di chuyển, Enter để mở bảng chọn.\n",
                 "yellow" if not self.ready else "dim")
        for n, msg in self.fetch.items():
            t.append(f"  {n}: ", "bold")
            t.append(msg + "\n", "dim")
        self.query_one("#setup-status", Static).update(t)

    async def _prefetch(self) -> None:
        def done(n: str, msg: str) -> None:
            a = self.cfg.agents[n]
            ok = msg.startswith(f"{n}: tìm thấy")
            self.fetch[n] = (f"{len(a.models)} model" + (" (hỏi từ CLI)" if ok else "")
                             + ("" if ok else f" — {msg.split(': ', 1)[-1]}, dùng danh mục có sẵn"))
            self._show_status()
        try:
            await self.orch.discover_all(timeout=self.timeout, on_done=done)
        except Exception as e:  # không bao giờ chặn màn hình thiết lập
            self.orch.log(f"⚠ Không hỏi được danh sách model: {e}")
        await self._build_form()

    async def _build_form(self) -> None:
        rows = self.query_one("#setup-rows", Vertical)
        installed = [n for n, a in self.cfg.agents.items() if a.installed()]
        lead = self.cfg.lead if self.cfg.lead in installed else (installed[0] if installed else self.cfg.lead)
        lead_opts = [(n + ("" if n in installed else "  (chưa cài)"), n) for n in self.cfg.agents]
        widgets = [Horizontal(Static("★ Trưởng nhóm"),
                              Select(lead_opts, value=lead, allow_blank=False, id="setup-lead"),
                              Static("lập kế hoạch & review", classes="setup-note"),
                              id="setup-lead-row"),
                   Static(f"{'  Agent (bật/tắt)':22}{'Model':42}{'Effort':18}Vai trò", id="setup-head")]
        for n, a in self.cfg.agents.items():
            ok = a.installed()
            box = Checkbox(n, value=ok and (a.enabled or n == lead), disabled=not ok,
                           id=safe_id(n, "setup-on-"))
            models = [(m, m) for m in a.model_choices()] + [("(mặc định)", RESET)]
            model = Select(models, value=a.model if a.model else RESET, allow_blank=False,
                           disabled=not ok, classes="setup-model", id=safe_id(n, "setup-model-"))
            row = [box, model]
            if a.efforts:
                extra = [a.effort] if a.effort and a.effort not in a.efforts else []  # giữ mức tự đặt
                effs = [(e, e) for e in extra + a.efforts] + [("(mặc định)", RESET)]
                row.append(Select(effs, value=a.effort or RESET,
                                  allow_blank=False, disabled=not ok, classes="setup-effort",
                                  id=safe_id(n, "setup-effort-")))
            else:
                row.append(Static("effort: (không có)", classes="setup-effort setup-note"))
            row.append(Static(a.role if ok else f"✗ chưa cài lệnh '{a.binary}'", classes="setup-note"))
            widgets.append(Horizontal(*row, classes="setup-row"))
        await rows.mount_all(widgets)
        self.query_one("#setup-save", Button).disabled = False
        self.ready = True
        self._show_status()
        self.query_one("#setup-lead", Select).focus()

    def choices(self) -> dict:
        out: dict = {"lead": self.query_one("#setup-lead", Select).value, "agents": {}}
        for n, a in self.cfg.agents.items():
            m = self.query_one("#" + safe_id(n, "setup-model-"), Select).value
            ch = {"enabled": self.query_one("#" + safe_id(n, "setup-on-"), Checkbox).value,
                  "model": None if m == RESET else m}
            effs = self.query("#" + safe_id(n, "setup-effort-"))
            if effs and isinstance(effs.first(), Select):
                e = effs.first().value
                ch["effort"] = None if e == RESET else e
            if not a.installed():
                ch = {"enabled": a.enabled}  # không đụng tới agent chưa cài
            out["agents"][n] = ch
        return out

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "setup-save":
            self.action_save()
        elif event.button.id == "setup-skip":
            self.action_skip()
        elif event.button.id == "setup-custom" and self.ready:
            keep = self.choices()
            self.app.push_screen(CustomScreen(self.orch.root, self.cfg),
                                 lambda changed: self._custom_done(changed, keep))

    async def _custom_done(self, changed: bool, keep: dict) -> None:
        """Quay lại từ màn hình tuỳ chỉnh: nạp lại đội rồi dựng lại form, giữ lựa chọn đang dở."""
        if not changed:
            return
        await self.app.reload_custom()
        for n, a in self.cfg.agents.items():
            if a.models_command and a.installed() and n not in self.fetch:
                self.fetch[n] = "chưa hỏi danh sách model (/models " + n + " làm mới)"
            elif not a.installed():
                self.fetch[n] = f"chưa cài '{a.binary}'"
            elif n not in self.fetch:
                self.fetch[n] = f"danh mục có sẵn ({len(a.models)} model)" if a.models else "CLI tự chọn"
        for n in [n for n in self.fetch if n not in self.cfg.agents]:
            del self.fetch[n]
        self.ready = False
        await self.query_one("#setup-rows", Vertical).remove_children()
        await self._build_form()
        if keep["lead"] in self.cfg.agents:
            self.query_one("#setup-lead", Select).value = keep["lead"]
        for n, ch in keep["agents"].items():
            if n not in self.cfg.agents or not self.cfg.agents[n].installed():
                continue
            self.query_one("#" + safe_id(n, "setup-on-"), Checkbox).value = bool(ch.get("enabled"))
            for key in ("model", "effort"):
                w = self.query("#" + safe_id(n, f"setup-{key}-"))
                if key in ch and w and isinstance(w.first(), Select):
                    v = ch[key] or RESET
                    if any(v == val for _, val in w.first()._options):
                        w.first().value = v

    def action_save(self) -> None:
        if not self.ready:
            return
        ch = self.choices()
        lead = self.cfg.agents.get(ch["lead"])
        if not lead or not lead.installed() or not ch["agents"][ch["lead"]].get("enabled"):
            self.notify(f"Trưởng nhóm '{ch['lead']}' phải được bật (và đã cài).", severity="error")
            return
        self.dismiss(ch)

    def action_skip(self) -> None:
        self.dismiss(None)


# --------------------------------------------------------------------------- agent & workflow tuỳ chỉnh
FORM_CSS = """
    #{box} { width: 120; max-width: 100%; height: auto; max-height: 95%; border: thick $accent;
             background: $surface; padding: 0 1; }
    #{box} .f-scroll { height: auto; max-height: 34; }
    #{box} .f-row { height: 3; }
    #{box} .f-label { width: 20; padding: 1 0 0 1; text-style: bold; }
    #{box} .f-input { width: 54; }
    #{box} .f-hint { width: 1fr; height: 3; padding: 1 0 0 1; color: $text-muted;
                     text-wrap: nowrap; text-overflow: ellipsis; }
    #{box} .f-section { height: 1; margin-top: 1; color: $text-muted; text-style: bold; }
    #{box} .f-buttons { height: auto; align: right middle; }
    #{box} .f-buttons Button { margin-left: 2; }
"""


def form_row(label: str, widget, hint: str = "") -> Horizontal:
    return Horizontal(Static(label, classes="f-label"), widget, Static(hint, classes="f-hint"),
                      classes="f-row")


def _csv(text: str) -> list[str]:
    return [x.strip() for x in text.replace(";", ",").split(",") if x.strip()]


def _argv_text(v) -> str:
    """argv -> chuỗi để sửa trong ô nhập; chỉ đặt trong nháy khi cần ({prompt} giữ nguyên cho dễ đọc)."""
    if not isinstance(v, list):
        return str(v or "")
    return " ".join(x if x and not re.search(r"[\s'\"\\]", x) else shlex.quote(x) for x in map(str, v))


class AgentEditScreen(ModalScreen):
    """Form thêm/sửa 1 agent tuỳ chỉnh. Trả về (tên, thân TOML, tên cũ) hoặc None (Esc)."""

    BINDINGS = [Binding("escape", "cancel", "Huỷ", priority=True),
                Binding("ctrl+s", "save", "Lưu", priority=True)]
    DEFAULT_CSS = "AgentEditScreen { align: center middle; }" + FORM_CSS.replace("{box}", "agent-box") + """
    #agent-preview { height: auto; padding: 0 1; background: $boost; margin-top: 1; }
    """
    FIELDS = [  # (id, nhãn, gợi ý, khoá TOML, kiểu: argv | csv | text | int)
        ("command", "Lệnh", "bắt buộc; {prompt} = nội dung task", "command", "argv"),
        ("role", "Vai trò", "trưởng nhóm phân việc dựa vào đây", "role", "text"),
        ("model", "Model mặc định", "trống = để CLI tự chọn", "model", "text"),
        ("models", "Model gợi ý", "cách nhau dấu phẩy", "models", "csv"),
        ("model-args", "Cờ model", "vd: --model {model}", "model_args", "argv"),
        ("efforts", "Mức effort", "vd: low, medium, high · '-' = không có", "efforts", "csv"),
        ("effort", "Effort mặc định", "trống = để CLI tự chọn", "effort", "text"),
        ("effort-args", "Cờ effort", "vd: --effort {effort}", "effort_args", "argv"),
        ("models-command", "Lệnh liệt kê model", "vd: mycli models (tuỳ chọn)", "models_command", "argv"),
        ("file-ref", "Nhắc file @", "vd: @{path} hoặc {path} · trống = theo lệnh", "file_ref", "text"),
        ("file-args", "Cờ đính file", "vd: -f {path} · trống = theo lệnh · '-' = tắt", "file_args", "argv"),
        ("image-args", "Cờ đính ảnh", "vd: --image={path} · trống = theo lệnh · '-' = tắt", "image_args", "argv"),
        ("fallback", "Dự phòng", "agent thay khi hết hạn mức, cách nhau dấu phẩy", "fallback", "csv"),
        ("timeout", "Timeout (giây)", "mặc định 1800", "timeout", "int"),
        ("max-concurrent", "Số task cùng lúc", "mặc định 1", "max_concurrent", "int"),
    ]

    def __init__(self, cfg: Config, name: str | None = None, raw: dict | None = None):
        super().__init__()
        self.cfg, self.old_name, self.raw = cfg, name, dict(raw or {})
        self.templates = agent_templates()

    def compose(self) -> ComposeResult:
        with Vertical(id="agent-box"):
            yield Static(Text("Sửa agent " + self.old_name if self.old_name else "Thêm agent tuỳ chỉnh",
                              "bold"))
            yield Static(Text("Bất kỳ CLI nào có chế độ headless (nhận prompt, in kết quả rồi thoát). "
                              "Chọn mẫu để điền sẵn, Ctrl+S lưu, Esc huỷ.", "dim"))
            with VerticalScroll(classes="f-scroll"):
                yield form_row("Mẫu", Select([(k, k) for k in self.templates], prompt="(chọn để điền sẵn)",
                                             id="ag-template", classes="f-input"),
                               "điền sẵn lệnh, cờ model/effort, cú pháp file")
                yield form_row("Tên", TextInput(self.old_name or "", placeholder="vd: gemini, aider-fast",
                                            id="ag-name", classes="f-input"),
                               "chữ, số, - và _")
                for fid, label, hint, _k, _t in self.FIELDS:
                    yield form_row(label, TextInput(id=f"ag-{fid}", classes="f-input"), hint)
                yield form_row("Tuỳ chọn", Horizontal(
                    Checkbox("Chạy trong terminal giả (pty)", id="ag-pty"),
                    Checkbox("Chạy lệnh kiểm tra sau task", True, id="ag-verify"),
                    classes="f-input"), "pty cần cho CLI chỉ in khi có terminal (vd agy)")
            yield Static(id="agent-preview")
            with Horizontal(classes="f-buttons"):
                yield Button("Huỷ (Esc)", id="ag-cancel")
                yield Button("Lưu (Ctrl+S)", id="ag-save", variant="primary")

    def on_mount(self) -> None:
        self.fill(self.raw)
        self.query_one("#ag-name" if not self.old_name else "#ag-command", Input).focus()

    def fill(self, raw: dict) -> None:
        for fid, _l, _h, key, kind in self.FIELDS:
            v = raw.get(key)
            if v is None:
                text = ""
            elif kind == "argv":
                text = "-" if key in ("file_args", "image_args") and v == [] else _argv_text(v)
            elif kind == "csv":
                text = "-" if v == [] else ", ".join(map(str, v if isinstance(v, list) else [v]))
            else:
                text = str(v)
            self.query_one(f"#ag-{fid}", Input).value = text
        self.query_one("#ag-pty", Checkbox).value = bool(raw.get("pty", False))
        self.query_one("#ag-verify", Checkbox).value = bool(raw.get("verify", True))
        self.update_preview()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "ag-template" or event.value not in self.templates:
            return
        self.fill(self.templates[event.value])
        name = self.query_one("#ag-name", Input)
        if not name.value.strip():
            base = str(event.value).split()[0]
            base = "my-agent" if base == "trống" else base
            n, i = base, 2
            while n in self.cfg.agents:
                n, i = f"{base}-{i}", i + 1
            name.value = n

    def on_input_changed(self, event: Input.Changed) -> None:
        self.update_preview()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        self.update_preview()

    def body(self) -> dict:
        """Đọc form thành dict như trong TOML (chỉ những khoá có điền). Lỗi -> ValueError."""
        out: dict = {}
        for fid, label, _h, key, kind in self.FIELDS:
            text = self.query_one(f"#ag-{fid}", Input).value.strip()
            if not text:
                continue
            if kind == "argv":
                if key in ("file_args", "image_args") and text == "-":
                    out[key] = []
                    continue
                try:
                    out[key] = shlex.split(text)
                except ValueError:
                    raise ValueError(f"{label}: thiếu dấu nháy đóng")
            elif kind == "csv":
                out[key] = [] if text == "-" else _csv(text)
            elif kind == "int":
                if not text.isdigit() or int(text) < 1:
                    raise ValueError(f"{label}: phải là số nguyên dương")
                out[key] = int(text)
            else:
                out[key] = text
        if self.query_one("#ag-pty", Checkbox).value:
            out["pty"] = True
        if not self.query_one("#ag-verify", Checkbox).value:
            out["verify"] = False
        return out

    def update_preview(self) -> None:
        t = Text()
        try:
            body = self.body()
            name = self.query_one("#ag-name", Input).value.strip() or "agent"
            a = agent_from_dict(name, body)
            if not a.command:
                t.append("Nhập lệnh để xem trước.", "dim")
            else:
                t.append("Lệnh sẽ chạy: ", "bold")
                t.append(" ".join(a.argv("<prompt>", model=a.model or None, effort=a.effort or None)))
                t.append("\n@file → ", "bold")
                t.append(mentions.describe(a.binary, a.file_ref, a.file_args, a.image_args))
                t.append("   ")
                t.append(f"✓ đã cài '{a.binary}'" if a.installed() else f"✗ chưa cài '{a.binary}'",
                         "green" if a.installed() else "yellow")
                if not any("{prompt}" in c for c in a.command):
                    t.append("\n⚠ lệnh không có {prompt}: prompt sẽ được thêm vào cuối", "yellow")
        except ValueError as e:
            t.append(f"⚠ {e}", "yellow")
        self.query_one("#agent-preview", Static).update(t)

    def validate(self) -> tuple[str, dict]:
        name = self.query_one("#ag-name", Input).value.strip()
        if not NAME_RE.match(name) or name == LEAD_ALIAS:
            raise ValueError("Tên chỉ gồm chữ, số, - và _ (không dùng 'lead')")
        if name in self.cfg.agents and name != self.old_name:
            raise ValueError(f"Đã có agent '{name}' — chọn tên khác")
        body = self.body()
        if not body.get("command"):
            raise ValueError("Cần nhập lệnh chạy agent")
        bad = [f for f in body.get("fallback", []) if f not in self.cfg.agents or f == name]
        if bad:
            raise ValueError(f"Dự phòng không có trong đội: {', '.join(bad)}")
        return name, body

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ag-save":
            self.action_save()
        elif event.button.id == "ag-cancel":
            self.action_cancel()

    def action_save(self) -> None:
        try:
            name, body = self.validate()
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        self.dismiss((name, body, self.old_name))

    def action_cancel(self) -> None:
        self.dismiss(None)


class WorkflowEditScreen(ModalScreen):
    """Form thêm/sửa 1 workflow: danh sách bước (agent, tiêu đề, prompt, chạy sau bước nào, effort).
    Trả về (tên, thân TOML, tên cũ) hoặc None (Esc)."""

    BINDINGS = [Binding("escape", "cancel", "Huỷ", priority=True),
                Binding("ctrl+s", "save", "Lưu", priority=True)]
    DEFAULT_CSS = "WorkflowEditScreen { align: center middle; }" + FORM_CSS.replace("{box}", "flow-box") + """
    #flow-steps { height: auto; }
    #flow-box .f-input { width: 64; }
    .step-row { height: 3; }
    .step-no { width: 4; padding: 1 0 0 1; text-style: bold; }
    .step-agent { width: 32; }
    .step-title { width: 22; }
    .step-prompt { width: 1fr; }
    .step-after { width: 12; }
    .step-effort { width: 12; }
    .step-del { width: 5; min-width: 5; }
    #flow-head { height: 1; color: $text-muted; text-style: bold; margin-top: 1; }
    #flow-head Static { padding: 0 0 0 1; }
    #flow-add { margin-left: 4; }
    """

    def __init__(self, cfg: Config, name: str | None = None, raw: dict | None = None):
        super().__init__()
        self.cfg, self.old_name, self.raw = cfg, name, dict(raw or {})
        self.n = 0  # bộ đếm id hàng (không phải số thứ tự bước)

    def agent_options(self, extra: str = "") -> list[tuple[str, str]]:
        opts = [(f"★ trưởng nhóm ({self.cfg.lead})", LEAD_ALIAS)] + [(n, n) for n in self.cfg.agents]
        if extra and extra not in (LEAD_ALIAS, *self.cfg.agents):
            opts.append((f"{extra} (không có trong đội)", extra))
        return opts

    def compose(self) -> ComposeResult:
        with Vertical(id="flow-box"):
            yield Static(Text("Sửa workflow " + self.old_name if self.old_name else "Thêm workflow", "bold"))
            yield Static(Text("Chuỗi bước dựng sẵn, chạy bằng /flow <tên> <mục tiêu> — không cần trưởng "
                              "nhóm lập kế hoạch. {goal} trong tiêu đề/prompt = mục tiêu bạn gõ. "
                              "'Sau bước': trống = sau bước liền trước, 0 = chạy ngay, 1,2 = sau bước 1 và 2.",
                              "dim"))
            with VerticalScroll(classes="f-scroll"):
                yield form_row("Mẫu", Select([(f"{k} — {v['description']}", k)
                                              for k, v in WORKFLOW_TEMPLATES.items()],
                                             prompt="(chọn để điền sẵn)", id="wf-template",
                                             classes="f-input"), "thay toàn bộ các bước")
                yield form_row("Tên", TextInput(self.old_name or "", placeholder="vd: tinh-nang, sua-loi",
                                            id="wf-name", classes="f-input"), "chữ, số, - và _")
                yield form_row("Mô tả", TextInput(id="wf-desc", classes="f-input"), "hiện trong /flow")
                yield form_row("Review", Checkbox("Trưởng nhóm review khi xong", id="wf-review"),
                               "review có thể giao thêm việc")
                yield Horizontal(*[Static(label, classes=cls) for label, cls in (
                    ("", "step-no"), ("Agent", "step-agent"), ("Tiêu đề", "step-title"),
                    ("Prompt", "step-prompt"), ("Sau bước", "step-after"), ("Effort", "step-effort"),
                    ("", "step-del"))], id="flow-head")
                yield Vertical(id="flow-steps")
                yield Button("+ Thêm bước", id="wf-add")
            with Horizontal(classes="f-buttons"):
                yield Button("Huỷ (Esc)", id="wf-cancel")
                yield Button("Lưu (Ctrl+S)", id="wf-save", variant="primary")

    async def on_mount(self) -> None:
        await self.fill(self.raw)
        self.query_one("#wf-name" if not self.old_name else "#wf-desc", Input).focus()

    def step_row(self, st: dict) -> Horizontal:
        self.n += 1
        k = self.n
        agent = str(st.get("agent") or LEAD_ALIAS)
        after = st.get("after")
        after_text = "" if after is None else ("0" if after == [] else
                                               ",".join(map(str, after if isinstance(after, list) else [after])))
        return Horizontal(
            Static("", classes="step-no"),
            Select(self.agent_options(agent), value=agent, allow_blank=False, classes="step-agent",
                   id=f"wf-agent-{k}"),
            TextInput(str(st.get("title") or ""), placeholder="tiêu đề", classes="step-title", id=f"wf-title-{k}"),
            TextInput(str(st.get("prompt") or ""), placeholder="việc cần làm, có thể dùng {goal}",
                  classes="step-prompt", id=f"wf-prompt-{k}"),
            TextInput(after_text, placeholder="trước", classes="step-after", id=f"wf-after-{k}"),
            TextInput(str(st.get("effort") or ""), placeholder="effort", classes="step-effort",
                  id=f"wf-effort-{k}"),
            Button("✕", classes="step-del", id=f"wf-del-{k}"),
            classes="step-row", id=f"wf-step-{k}")

    def renumber(self) -> None:
        for i, row in enumerate(self.query(".step-row"), 1):
            row.query_one(".step-no", Static).update(f"{i}.")

    async def fill(self, raw: dict) -> None:
        self.query_one("#wf-desc", Input).value = str(raw.get("description") or "")
        rv = raw.get("review")
        self.query_one("#wf-review", Checkbox).value = self.cfg.auto_review if rv is None else bool(rv)
        box = self.query_one("#flow-steps", Vertical)
        await box.remove_children()
        steps = raw.get("steps") or [{"agent": LEAD_ALIAS}]
        await box.mount_all([self.step_row(st) for st in steps])
        self.renumber()

    async def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "wf-template" or event.value not in WORKFLOW_TEMPLATES:
            return
        tpl = WORKFLOW_TEMPLATES[event.value]
        member = next((n for n in self.cfg.active_agents() if n != self.cfg.lead), LEAD_ALIAS)
        raw = dict(tpl, steps=[dict(st, agent=member if st["agent"] == "*" else st["agent"])
                               for st in tpl["steps"]])
        await self.fill(raw)
        name = self.query_one("#wf-name", Input)
        if not name.value.strip():
            name.value = str(event.value)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "wf-add":
            await self.query_one("#flow-steps", Vertical).mount(self.step_row({}))
            self.renumber()
        elif bid.startswith("wf-del-"):
            if len(self.query(".step-row")) <= 1:
                self.notify("Workflow cần ít nhất 1 bước", severity="warning")
                return
            await self.query_one(f"#wf-step-{bid[7:]}").remove()
            self.renumber()
        elif bid == "wf-save":
            self.action_save()
        elif bid == "wf-cancel":
            self.action_cancel()

    def validate(self) -> tuple[str, dict]:
        name = self.query_one("#wf-name", Input).value.strip()
        if not NAME_RE.match(name):
            raise ValueError("Tên chỉ gồm chữ, số, - và _")
        if name in self.cfg.workflows and name != self.old_name:
            raise ValueError(f"Đã có workflow '{name}' — chọn tên khác")
        steps = []
        for i, row in enumerate(self.query(".step-row"), 1):
            k = (row.id or "")[len("wf-step-"):]
            agent = str(row.query_one(f"#wf-agent-{k}", Select).value)
            title = row.query_one(f"#wf-title-{k}", Input).value.strip()
            prompt = row.query_one(f"#wf-prompt-{k}", Input).value.strip()
            if not (title or prompt):
                raise ValueError(f"Bước {i}: cần tiêu đề hoặc prompt")
            after_text = row.query_one(f"#wf-after-{k}", Input).value.strip()
            after: list[int] | None = None
            if after_text in ("0", "-"):
                after = []
            elif after_text:
                parts = _csv(after_text)
                if not all(p.isdigit() and 0 < int(p) < i for p in parts):
                    raise ValueError(f"Bước {i}: 'Sau bước' phải là số bước đứng trước (1…{i - 1})")
                after = [int(p) for p in parts]
            effort = row.query_one(f"#wf-effort-{k}", Input).value.strip().lower()
            steps.append(WorkflowStep(agent=agent, title=title, prompt=prompt, after=after, effort=effort))
        if not steps:
            raise ValueError("Workflow cần ít nhất 1 bước")
        wf = Workflow(name=name, description=self.query_one("#wf-desc", Input).value.strip(),
                      steps=steps, review=self.query_one("#wf-review", Checkbox).value)
        return name, workflow_to_dict(wf)

    def action_save(self) -> None:
        try:
            name, body = self.validate()
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        self.dismiss((name, body, self.old_name))

    def action_cancel(self) -> None:
        self.dismiss(None)


class CustomScreen(ModalScreen):
    """Quản lý agent và workflow tuỳ chỉnh (/custom, hoặc nút ở màn hình thiết lập).
    Mỗi lần lưu ghi ngay vào custom.toml. Trả về True nếu có thay đổi."""

    BINDINGS = [Binding("escape", "close", "Đóng", priority=True)]
    DEFAULT_CSS = "CustomScreen { align: center middle; }" + FORM_CSS.replace("{box}", "custom-box") + """
    .c-row { height: 3; }
    .c-name { width: 22; padding: 1 0 0 1; text-style: bold; }
    .c-info { width: 1fr; height: 3; padding: 1 0 0 1; color: $text-muted;
              text-wrap: nowrap; text-overflow: ellipsis; }
    .c-row Button { min-width: 8; margin-left: 1; }
    .c-empty { height: 1; padding: 0 1; color: $text-muted; }
    #custom-agents, #custom-flows { height: auto; }
    #custom-box Button.c-add { margin: 0 0 0 1; }
    """

    def __init__(self, root: Path, cfg: Config):
        super().__init__()
        self.root, self.cfg = root, cfg
        self.changed = False
        self.ids: dict[str, tuple[str, str]] = {}  # id nút -> (hành động, tên)
        self.armed: str | None = None  # nút xoá đang chờ bấm lần 2

    def compose(self) -> ComposeResult:
        with Vertical(id="custom-box"):
            yield Static(Text("Agent & workflow tuỳ chỉnh", "bold"))
            yield Static(Text("Agent mới tham gia đội như agent có sẵn (trưởng nhóm phân việc theo vai "
                              "trò, bật/tắt ở /setup). Workflow chạy bằng /flow <tên> <mục tiêu>. "
                              f"Lưu ở {CUSTOM_FILE}", "dim"))
            with VerticalScroll(classes="f-scroll"):
                yield Static("Agent tuỳ chỉnh", classes="f-section")
                yield Vertical(id="custom-agents")
                yield Button("+ Thêm agent", id="custom-add-agent", classes="c-add")
                yield Static("Workflow", classes="f-section")
                yield Vertical(id="custom-flows")
                yield Button("+ Thêm workflow", id="custom-add-flow", classes="c-add")
            with Horizontal(classes="f-buttons"):
                yield Button("Xong (Esc)", id="custom-close", variant="primary")

    async def on_mount(self) -> None:
        await self.refill()
        self.query_one("#custom-add-agent", Button).focus()

    async def refill(self) -> None:
        self.cfg = load_config(self.root)
        self.ids.clear()
        self.armed = None
        n = 0

        def btn(label: str, action: str, name: str, variant: str = "default") -> Button:
            nonlocal n
            n += 1
            bid = f"c-btn-{n}"
            self.ids[bid] = (action, name)
            return Button(label, id=bid, variant=variant)

        rows = []
        for name in sorted(self.cfg.custom_agents):
            a = self.cfg.agents[name]
            ok = "✓" if a.installed() else "✗ chưa cài"
            rows.append(Horizontal(Static(name, classes="c-name"),
                                   Static(f"{ok} · {' '.join(a.argv('<prompt>'))}", classes="c-info"),
                                   btn("Sửa", "edit-agent", name), btn("Xoá", "del-agent", name, "error"),
                                   classes="c-row"))
        if not rows:
            rows = [Static("Chưa có. Bấm '+ Thêm agent' để thêm CLI bất kỳ (Gemini, Aider, script riêng…).",
                           classes="c-empty")]
        box = self.query_one("#custom-agents", Vertical)
        await box.remove_children()
        await box.mount_all(rows)

        rows = []
        for name, w in self.cfg.workflows.items():
            info = f"{len(w.steps)} bước: {w.summary()}" + (f" · {w.description}" if w.description else "")
            rows.append(Horizontal(Static(name, classes="c-name"), Static(info, classes="c-info"),
                                   btn("Sửa", "edit-flow", name), btn("Xoá", "del-flow", name, "error"),
                                   classes="c-row"))
        if not rows:
            rows = [Static("Chưa có. Bấm '+ Thêm workflow' (có mẫu: tính năng mới, sửa lỗi, review).",
                           classes="c-empty")]
        box = self.query_one("#custom-flows", Vertical)
        await box.remove_children()
        await box.mount_all(rows)

    async def _saved(self, kind: str, result) -> None:
        if not result:
            return
        name, body, old = result
        save_custom_item(kind, name, body, old)
        self.changed = True
        self.notify(f"Đã lưu {'agent' if kind == 'agents' else 'workflow'} '{name}'")
        await self.refill()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "custom-close":
            self.action_close()
            return
        if bid == "custom-add-agent":
            self.app.push_screen(AgentEditScreen(self.cfg), lambda r: self._saved("agents", r))
            return
        if bid == "custom-add-flow":
            self.app.push_screen(WorkflowEditScreen(self.cfg), lambda r: self._saved("workflows", r))
            return
        action, name = self.ids.get(bid, ("", ""))
        custom = load_custom()
        if action == "edit-agent":
            raw = (custom.get("agents") or {}).get(name, {})
            self.app.push_screen(AgentEditScreen(self.cfg, name, raw), lambda r: self._saved("agents", r))
        elif action == "edit-flow":
            raw = (custom.get("workflows") or {}).get(name)
            old: str | None = name
            if raw is None:  # workflow ghi trong config.toml / file dự án: lưu thành bản sao
                raw, old = workflow_to_dict(self.cfg.workflows[name]), None
                self.notify(f"'{name}' nằm trong file cấu hình — lưu sẽ tạo bản sao với tên mới.")
            self.app.push_screen(WorkflowEditScreen(self.cfg, old, raw),
                                 lambda r: self._saved("workflows", r))
        elif action in ("del-agent", "del-flow"):
            kind = "agents" if action == "del-agent" else "workflows"
            if kind == "agents" and name == self.cfg.lead:
                self.notify(f"'{name}' đang là trưởng nhóm — đổi trưởng nhóm ở /setup trước.",
                            severity="error")
                return
            if name not in (custom.get(kind) or {}):
                self.notify(f"'{name}' nằm trong file cấu hình khác ({', '.join(map(str, self.cfg.sources))})"
                            " — sửa file đó để xoá.", severity="warning")
                return
            if self.armed != bid:  # bấm lần 2 mới xoá
                self.armed = bid
                event.button.label = "Chắc chưa?"
                return
            save_custom_item(kind, name, None)
            self.changed = True
            self.notify(f"Đã xoá '{name}'")
            await self.refill()

    def action_close(self) -> None:
        self.dismiss(self.changed)


class MentionList(OptionList):
    """Danh sách gợi ý file/thư mục nổi phía trên ô nhập khi gõ @."""

    can_focus = False

    def on_mount(self) -> None:
        self.border_title = "@ file / thư mục"
        self.border_subtitle = "↑↓ chọn · Tab/Enter chèn · Esc đóng"


# @ ở đầu ô nhập hoặc sau khoảng trắng / mở ngoặc, tới con trỏ: @abc hoặc @"có dấu cách
MENTION_AT_CURSOR = re.compile(r'(?:^|(?<=[\s(\[{\'`]))@(?:"([^"]*)|([^\s"\'`]*))$')


class CommandInput(TextInput):
    """Ô nhập lệnh, có gợi ý file/thư mục khi gõ @ và dán ảnh bằng Ctrl+V."""

    BINDINGS = [
        Binding("up", "mention_move(-1)", show=False),
        Binding("down", "mention_move(1)", show=False),
        Binding("tab", "mention_accept", show=False),
        Binding("enter", "mention_enter", show=False),
        Binding("escape", "mention_close", show=False),
        Binding("ctrl+v", "paste_image", show=False),
    ]

    def __init__(self, root: Path, **kw):
        super().__init__(**kw)
        self.root = root
        self.index = mentions.FileIndex(root)
        self._span: tuple[int, int] | None = None  # vị trí "@…" (hoặc "/…") đang gõ trong value
        self._mode = "file"  # "file": gợi ý @file · "cmd": gợi ý lệnh khi gõ / ở đầu ô

    # ------------------------------------------------------------ ảnh
    def insert_mentions(self, paths: list[str]) -> None:
        """Chèn `@ảnh` tại con trỏ (có dấu cách ngăn với chữ đứng trước/sau)."""
        before = self.value[:self.cursor_position]
        text = " ".join(mentions.quote(clipboard.shorten(Path(p), self.root)) for p in paths) + " "
        if before and not before[-1].isspace():
            text = " " + text
        self.insert_text_at_cursor(text)
        self.close_popup()

    def action_paste_image(self) -> None:
        self.run_worker(self._paste_image(), exclusive=True, group="paste-image")

    async def _paste_image(self) -> None:
        path, why = await clipboard.grab_image(self.root / ".ateam" / "images")
        if path:
            self.insert_mentions([str(path)])
            self.app.notify(f"Đã dán ảnh {clipboard.shorten(path, self.root)}", timeout=3)
        elif self.app.clipboard:
            self.action_paste()  # chữ đã copy trong app (Ctrl+C / Ctrl+X) như Ctrl+V cũ
        else:
            self.app.notify(f"Không dán được ảnh: {why}. Dán chữ bằng Cmd+V.",
                            severity="warning", timeout=4)

    async def _on_paste(self, event: events.Paste) -> None:
        # kéo-thả ảnh vào terminal = dán đường dẫn của nó -> đổi thành @ảnh để agent nhận được ảnh
        found = clipboard.dropped_images(event.text)
        if found:
            event.prevent_default()
            event.stop()
            self.insert_mentions(found)

    @property
    def popup(self) -> MentionList:
        return self.app.query_one("#mention", MentionList)

    @property
    def popup_open(self) -> bool:
        return self.popup.display

    def close_popup(self) -> None:
        self.popup.display = False
        self._span = None

    def update_mention(self) -> None:
        """Gọi khi nội dung đổi: mở/lọc/đóng danh sách gợi ý theo chữ trước con trỏ."""
        before = self.value[:self.cursor_position]
        c = re.fullmatch(r"/(\S*)", before)
        if c and self.cursor_position == len(self.value):
            self._mode, self._span = "cmd", (0, self.cursor_position)
            self._fill_commands(c.group(1))
            return
        m = MENTION_AT_CURSOR.search(before)
        if not m:
            self.close_popup()
            return
        self._mode = "file"
        self._span = (m.start(), self.cursor_position)
        query = m.group(1) if m.group(1) is not None else m.group(2)
        if self.index.stale():
            self.run_worker(self._reload(), exclusive=True, group="mention-index")
        self._fill(query)

    async def _reload(self) -> None:
        await self.index.refresh()
        if self._span is not None:
            self.update_mention()

    def _fill_commands(self, query: str) -> None:
        popup = self.popup
        found = match_commands(query)
        if not found:
            self.close_popup()
            return
        popup.clear_options()
        width = max(len(n) + len(a) for n, a, _d in COMMANDS) + 4
        for name, args, desc in found:
            t = Text()
            t.append("/" + name, "bold cyan")
            t.append(f" {args}".ljust(width - len(name)), "cyan")
            t.append(desc, "dim")
            popup.add_option(Option(t, id=name))
        popup.highlighted = 0
        popup.border_title = "/ lệnh"
        popup.display = True

    def _fill(self, query: str) -> None:
        popup = self.popup
        popup.border_title = "@ file / thư mục"
        found = mentions.search(self.index.entries, query)
        popup.clear_options()
        if found:
            popup.add_options([Option(Text("📁 " + e, "bold cyan") if e.endswith("/")
                                      else Text("   " + e), id=e) for e in found])
            popup.highlighted = 0
        else:
            msg = "đang đọc danh sách file…" if not self.index.loaded_at else "không có file nào khớp"
            popup.add_option(Option(Text(msg, "dim"), disabled=True))
        popup.display = True

    def accept(self) -> bool:
        """Chèn mục đang chọn. Thư mục: giữ danh sách mở để đi vào trong."""
        popup = self.popup
        if self._span is None or popup.highlighted is None:
            return False
        opt = popup.get_option_at_index(popup.highlighted)
        if opt.disabled or not opt.id:
            return False
        start, end = self._span
        if self._mode == "cmd":
            args = next((a for n, a, _d in COMMANDS if n == opt.id), "")
            self.value = f"/{opt.id} " if args else f"/{opt.id}"
            self.cursor_position = len(self.value)
            self.close_popup()
            return True
        path = opt.id
        text = mentions.quote(path)
        if path.endswith("/") and text.endswith('"'):
            text = text[:-1]  # @"thư mục có dấu cách/ — để gõ tiếp vào trong
        if not path.endswith("/"):
            text += " "
        self.value = self.value[:start] + text + self.value[end:]
        self.cursor_position = start + len(text)
        self.update_mention()
        return True

    def action_mention_move(self, delta: int) -> None:
        if self.popup_open:
            if delta < 0:
                self.popup.action_cursor_up()
            else:
                self.popup.action_cursor_down()

    def action_mention_accept(self) -> None:
        if not (self.popup_open and self.accept()):
            self.screen.focus_next()

    async def action_mention_enter(self) -> None:
        if self.popup_open and self._mode == "cmd":
            typed = self.value[1:].lower()
            known = {n for n, _a, _d in COMMANDS} | set(COMMAND_ALIASES)
            # gõ đủ tên lệnh rồi Enter -> chạy luôn (lệnh bắt buộc tham số thì chèn dấu cách, chờ gõ
            # tiếp); chưa đủ -> chèn lệnh đang chọn, lệnh không cần tham số thì chạy luôn
            if typed in known and command_needs_args(typed):
                self.value = f"/{typed} "
                self.cursor_position = len(self.value)
                self.close_popup()
                return
            if typed not in known and self.accept() and self.value.endswith(" "):
                return
        elif self.popup_open and self.accept():
            return
        self.close_popup()
        res = self.action_submit()
        if inspect.isawaitable(res):
            await res

    def action_mention_close(self) -> None:
        self.close_popup()


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


class PlanBar(Vertical):
    """Khung duyệt kế hoạch: hiện ở cả hai tab khi trưởng nhóm (hoặc workflow) có kế hoạch nháp.
    Liệt kê task nháp (agent, tiêu đề, phụ thuộc) kèm nút duyệt / sửa / đổi agent / bỏ."""

    BINDINGS = [Binding("escape", "leave", show=False)]

    def __init__(self, **kw):
        super().__init__(**kw)
        self.goal_id: int | None = None
        self._sig: tuple = ()

    def compose(self) -> ComposeResult:
        yield Static(id="plan-head")
        yield OptionList(id="plan-tasks")
        with Horizontal(id="plan-buttons"):
            yield Button("▶ Duyệt & chạy  F2", id="plan-approve", variant="success")
            yield Button("✎ Sửa task", id="plan-edit")
            yield Button("⇄ Đổi agent", id="plan-assign")
            yield Button("✗ Bỏ kế hoạch", id="plan-discard", variant="error")
        yield Static("Enter trên 1 task: sửa nội dung · Tab: chuyển nút · Esc: về ô nhập",
                     id="plan-hint")

    def update_plan(self, app: "TeamApp") -> bool:
        """Vẽ lại theo DB. Trả về True nếu vừa có kế hoạch MỚI cần duyệt (để app chuyển focus)."""
        waiting = [g for g in app.db.goals() if g.status == "awaiting"]
        if not waiting:
            self.goal_id, self._sig = None, ()
            self.display = False
            return False
        g = waiting[0]
        tasks = app.db.tasks(goal_id=g.id, status="draft")
        sig = (g.id, g.round, len(waiting),
               tuple((t.id, t.agent, t.effort, t.title, tuple(t.depends_on), t.prompt) for t in tasks))
        is_new = g.id != self.goal_id
        self.goal_id = g.id
        self.display = True
        if sig == self._sig:
            return False
        self._sig = sig
        head = Text()
        head.append("📋 Kế hoạch chờ duyệt ", "bold yellow")
        head.append(f"#{g.id}", "bold")
        if g.round > 1:
            head.append(f" · vòng {g.round}", "yellow")
        head.append(f" · {len(tasks)} task", "yellow")
        if len(waiting) > 1:
            head.append(f" · còn {len(waiting) - 1} kế hoạch khác sau", "dim")
        head.append(f"\n🎯 {g.text[:150]}", "")
        self.query_one("#plan-head", Static).update(head)
        ol = self.query_one("#plan-tasks", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        w = max((len(t.agent) + (len(t.effort) + 1 if t.effort else 0) for t in tasks), default=6)
        for t in tasks:
            line = Text()
            line.append(f"#{t.id:<4}", "bold")
            agent = t.agent + (f"@{t.effort}" if t.effort else "")
            line.append(f"{agent:<{w}}  ", "bold cyan")
            line.append(t.title)
            if t.depends_on:
                line.append(f"  ⟵ sau #{', #'.join(map(str, t.depends_on))}", "dim")
            ol.add_option(Option(line, id=str(t.id)))
        if tasks:
            ol.highlighted = min(keep, len(tasks) - 1) if keep is not None and not is_new else 0
        return is_new

    def selected_task(self) -> int | None:
        ol = self.query_one("#plan-tasks", OptionList)
        if ol.highlighted is None or not ol.option_count:
            return None
        return int(ol.get_option_at_index(ol.highlighted).id)

    def action_leave(self) -> None:
        self.app.query_one("#cmd", Input).focus()


# ============================================================================ app
class TeamApp(App):
    TITLE = "AI Team"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { layers: base overlay; }
    #tabs { height: 1fr; }
    TabPane { padding: 0; }
    #board { height: 1fr; }
    #left { width: 46%; min-width: 40; }
    #right { width: 1fr; border-left: solid $primary-darken-2; }
    #agents { height: auto; padding: 0 1; background: $boost; }
    #goals { height: auto; max-height: 7; padding: 0 1; border-bottom: solid $primary-darken-3; }
    #tasks { height: 1fr; }
    #tasks-empty { height: 1fr; padding: 1 2; color: $text-muted; }
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
    #plan { height: auto; max-height: 20; display: none; border: heavy $warning;
            border-title-color: $warning; padding: 0 1; background: $boost; }
    #plan:focus-within { border: heavy $success; }
    #plan-tasks { height: auto; max-height: 10; border: none; padding: 0; background: $boost; }
    #plan-buttons { height: auto; margin-top: 1; }
    #plan-buttons Button { margin-right: 1; min-width: 14; }
    #plan-hint { color: $text-muted; }
    #mention { dock: bottom; layer: overlay; display: none; height: auto; max-height: 14;
               width: 90; max-width: 100%; margin: 0 0 4 1; border: round $accent;
               background: $panel; }
    """
    # priority=True: phím tắt vẫn chạy khi con trỏ đang ở ô nhập (Input của Textual tự dùng
    # Ctrl+D, Ctrl+K... để sửa chữ, sẽ nuốt mất phím nếu không ưu tiên)
    BINDINGS = [
        Binding("f1", "help", "Trợ giúp", priority=True),
        Binding("ctrl+q", "quit", "Thoát", priority=True),
        Binding("ctrl+t", "toggle_tab", "Bảng việc ⇄ Đội", priority=True),
        # F2/F5 đứng trước: Ctrl+G (Go to Line) và Ctrl+R (Run Recent Command) bị terminal tích hợp
        # của VS Code/Cursor trên macOS chặn — footer hiện phím đầu tiên, phím Ctrl vẫn dùng được
        Binding("f2,ctrl+g", "approve", "Duyệt & chạy", priority=True),
        Binding("f5,ctrl+r", "retry", "Chạy lại", priority=True),
        Binding("ctrl+k", "cancel_task", "Huỷ task", priority=True),
        Binding("ctrl+d", "diff", "Xem diff", priority=True),
        Binding("ctrl+y", "merge", "Merge", priority=True),
        Binding("ctrl+l", "syslog", "Log hệ thống", priority=True),
    ]

    def __init__(self, root: Path, cfg: Config, db: DB, setup: bool = False):
        super().__init__()
        self.root, self.cfg, self.db = root, cfg, db
        self.start_setup = setup
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
                        yield Static(id="tasks-empty")
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
        yield PlanBar(id="plan")
        yield MentionList(id="mention")
        yield CommandInput(self.root, id="cmd",
                           placeholder="Nhập mục tiêu cho trưởng nhóm, /help, hoặc @ để nhắc file")
        yield Footer()

    async def on_mount(self) -> None:
        self.sub_title = str(self.root)
        table = self.query_one("#tasks", DataTable)
        table.add_column("#", key="id", width=4)
        table.add_column("Agent", key="agent", width=13)
        table.add_column("Trạng thái", key="status", width=12)
        table.add_column("⏱", key="time", width=6)
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
            self.write_sys(WELCOME)
        if self.start_setup:
            self.open_setup()
        else:
            self.run_worker(self._discover_missing_models(), exclusive=False)

    def on_resize(self, event: events.Resize) -> None:
        # terminal hẹp: nới cột bảng việc để cột "Task" (quan trọng nhất) không bị đẩy mất
        self.query_one("#left").styles.width = "46%" if event.size.width >= 140 else "58%"

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
                   self._refresh_detail, self._refresh_panes, self._refresh_timeline,
                   self._refresh_plan):
            try:
                fn()
            except Exception as e:  # không để lỗi vẽ làm treo app
                self.log.error(f"refresh {fn.__name__}: {e!r}")

    def _refresh_agents(self) -> None:
        chunks: list[Text] = []
        busy = self.busy_agents()
        for name, a in self.cfg.agents.items():
            if not a.enabled:
                continue
            t = Text()
            chunks.append(t)
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
            chunks.append(Text("  ⏸ TẠM DỪNG (/resume)", "bold yellow"))
        w = self.query_one("#agents", Static)
        w.update(flow_chunks(chunks, w.content_region.width))

    def _refresh_goals(self) -> None:
        goals = self.db.goals()[-4:]
        t = Text()
        if not goals:
            t.append("Chưa có mục tiêu. Gõ yêu cầu ở ô dưới cùng.", "dim")
        for i, g in enumerate(goals):
            label, style = GOAL_STATUS.get(g.status, (g.status, ""))
            if i:
                t.append("\n")
            busy = g.status in ("planning", "reviewing")
            t.append(f"{SPIN[self._frame]} " if busy else "🎯 ", "bold magenta" if busy else "")
            t.append(f"#{g.id} ", "bold")
            if g.workflow:
                t.append(f"⚙{g.workflow} ", "cyan")
            t.append(f"[{label}", style)
            t.append(f" · vòng {g.round}]" if g.round > 1 else "]", style)
            t.append(f" {g.text[:80]}")
            if g.summary and g.status in ("done", "incomplete", "failed", "awaiting"):
                t.append(f"\n   ↳ {g.summary[:160]}", "dim")
            if g.status == "awaiting":
                t.append("\n   ↳ xem khung Duyệt kế hoạch phía dưới · F2 duyệt & chạy", "yellow")
        self.query_one("#goals", Static).update(t)

    def _refresh_table(self) -> None:
        table = self.query_one("#tasks", DataTable)
        now = time.time()
        tasks = self.db.tasks()
        empty = self.query_one("#tasks-empty", Static)
        table.display, empty.display = bool(tasks), not tasks
        if not tasks:
            t = Text()
            t.append("Chưa có task nào.\n\n", "bold")
            for keys, what in (("Gõ một mục tiêu", "trưởng nhóm lập kế hoạch & chia việc"),
                               ("/task <agent> <nội dung>", "giao tay cho 1 agent"),
                               ("/flow <tên> <mục tiêu>", "chạy theo workflow dựng sẵn"),
                               ("F1", "xem mọi lệnh & phím tắt")):
                t.append(f"  {keys:27}", "bold cyan")
                t.append(what + "\n")
            empty.update(t)
        for task in tasks:
            label, style = STATUS.get(task.status, (task.status, ""))
            icon = SPIN[self._frame] if task.status == "running" else STATUS_ICON.get(task.status, "·")
            label = f"{icon} {label}"
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
            t = Text("📜 Log hệ thống", "bold")
            t.append("  ·  chọn 1 task trong bảng để xem log riêng · Ctrl+T: tab Đội", "dim")
            d.update(t)
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
                t.append(f"   hôm nay {u['runs']} lượt · {fmt_dur(u['secs'])}", "dim")  # token: /usage
            t.append("\n")
            t.append_text(choice_line("model", a.model_choices(), a.model, PANE_MODELS))
            t.append("\n")
            t.append_text(choice_line("effort", a.efforts, a.effort))
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

    def _refresh_plan(self) -> None:
        bar = self.query_one("#plan", PlanBar)
        if not bar.update_plan(self):
            return
        bar.border_title = "Duyệt kế hoạch"
        # kế hoạch mới: đưa con trỏ vào nút "Duyệt & chạy" (Enter là chạy) — trừ khi người dùng
        # đang gõ dở trong ô nhập hoặc đang mở màn hình khác
        box = self.query_one("#cmd", Input)
        if self.screen is self.screen_stack[0] and not box.value:
            self.query_one("#plan-approve", Button).focus()
        self.notify(f"📋 Kế hoạch #{bar.goal_id} sẵn sàng — Enter hoặc F2 để duyệt & chạy",
                    timeout=6)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if not bid.startswith("plan-"):
            return
        event.stop()
        bar = self.query_one("#plan", PlanBar)
        if bid == "plan-approve":
            self.action_approve()
        elif bid == "plan-discard":
            if bar.goal_id is not None:
                n = self.orch.discard_plan(bar.goal_id)
                self.notify(f"Đã bỏ kế hoạch #{bar.goal_id} ({n} task nháp)")
        elif bid in ("plan-edit", "plan-assign"):
            self.prefill_plan_command(bid[5:], bar.selected_task())
        self.refresh_view()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "plan-tasks" and event.option.id:
            event.stop()
            self.prefill_plan_command("edit", int(event.option.id))

    def prefill_plan_command(self, kind: str, tid: int | None) -> None:
        """Điền sẵn /edit hoặc /assign cho task nháp vào ô nhập để người dùng sửa rồi Enter."""
        if tid is None:
            self.notify("Kế hoạch không còn task nào")
            return
        task = self.db.task(tid)
        if not task:
            return
        box = self.query_one("#cmd", Input)
        if kind == "edit":
            box.value = f"/edit {tid} " + " ".join(task.prompt.split())
        else:
            box.value = f"/assign {tid} "
            self.notify("Agent: " + ", ".join(self.cfg.active_agents()))
        box.focus()
        box.cursor_position = len(box.value)

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
    def action_help(self) -> None:
        if isinstance(self.screen, HelpScreen):  # F1 lần nữa = đóng
            self.screen.dismiss(None)
        else:
            self.push_screen(HelpScreen())

    def action_toggle_tab(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = "tab-team" if tabs.active == "tab-board" else "tab-board"
        self.refresh_view()

    def action_approve(self) -> None:
        bar = self.query_one("#plan", PlanBar)
        gid = bar.goal_id if bar.display else None
        n = self.orch.approve(gid)
        if not n:
            self.notify("Không có task nháp nào cần duyệt")
            return
        self.notify(f"▶ Đã duyệt {n} task" + (f" của kế hoạch #{gid}" if gid else ""))
        self.refresh_view()
        if not bar.display:
            self.query_one("#cmd", Input).focus()

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
    def on_input_changed(self, event: Input.Changed) -> None:
        if isinstance(event.input, CommandInput):
            event.input.update_mention()

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
        except (ValueError, IndexError):  # thiếu/sai tham số (vd /set không có task) -> chỉ cách dùng
            self.notify(command_usage(text[1:].split(" ", 1)[0].lower()), severity="warning")
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
                out.append(f"  {name:12} {r['runs']:>5} {fmt_dur(r['secs']):>10} {fmt_tokens(tok):>8} "
                           f"{r['failed']:>4} {r['ratelimits']:>6}")
        cds = [f"{a} đến {self.orch.cooldown_label(a)}" for a in self.cfg.agents if self.orch.in_cooldown(a)]
        out.append("Đang tạm nghỉ: " + (", ".join(cds) if cds else "không"))
        out.append("(~token = ước tính từ độ dài prompt và output, chưa gồm file agent tự đọc)")
        return "\n".join(out)

    def models_text(self, only: str | None = None) -> str:
        return (describe_models(self.cfg, only) + "\nChọn: /model <agent>, /effort <agent> hoặc bấm vào "
                "ô agent ở tab Đội. Model ngoài danh sách vẫn đặt được: /model <agent> <tên>.")

    def open_picker(self, agent: str, key: str, then_effort: bool = False) -> None:
        a: AgentConfig | None = self.cfg.agents.get(agent)
        if not a:
            return
        items = a.model_choices() if key == "model" else list(a.efforts)
        current = a.model if key == "model" else a.effort
        title = f"Chọn {key} cho {agent}  (đang dùng: {current or 'mặc định'})"

        def done(value) -> None:
            if value is not None:
                self.notify(self.orch.set_agent_option(agent, key, None if value == RESET else value))
                self.refresh_view()
            if then_effort and key == "model" and value is not None and a.efforts:
                self.open_picker(agent, "effort")

        self.push_screen(ChoiceScreen(title, items, current, "mặc định trong config / CLI"), done)

    async def _discover_missing_models(self) -> None:
        """Hỏi (song song) các CLI có lệnh liệt kê model mà chưa từng hỏi (opencode models, agy models)."""
        found = load_state().get("models_found", {})
        await self.orch.discover_all([n for n in self.cfg.active_agents() if n not in found],
                                     on_done=lambda _n, msg: self.orch.log("⚙ " + msg))

    def open_setup(self) -> None:
        self.push_screen(SetupScreen(self.cfg, self.orch), self._setup_done)

    async def _setup_done(self, result) -> None:
        if result is None:
            mark_setup_done()
            self.orch.log("ℹ Bỏ qua thiết lập. Mở lại bất cứ lúc nào bằng /setup (hoặc `ateam setup`).")
            return
        save_setup(self.root, result["lead"], result["agents"])
        fresh = load_config(self.root)
        self.cfg.lead = fresh.lead
        for n, a in self.cfg.agents.items():
            f = fresh.agents.get(n)
            if f:
                a.enabled, a.model, a.effort = f.enabled, f.model, f.effort
        await self._rebuild_panes()
        on = [f"{n} ({a.label()})" for n, a in self.cfg.active_agents().items()]
        self.orch.log(f"⚙ Đã lưu thiết lập. Trưởng nhóm: {self.cfg.lead}. Đội: {', '.join(on)}. "
                      "Đổi lại: /setup, /model, /effort.")
        self.refresh_view()

    def open_custom(self) -> None:
        async def done(changed) -> None:
            if changed:
                await self.reload_custom()
        self.push_screen(CustomScreen(self.root, self.cfg), done)

    async def reload_custom(self) -> None:
        """Đọc lại custom.toml: thêm/bớt/sửa agent tuỳ chỉnh và workflow ngay, không cần mở lại app."""
        fresh = load_config(self.root)
        before = set(self.cfg.agents)
        for n in [n for n in self.cfg.agents if n not in fresh.agents]:
            del self.cfg.agents[n]
        for n, a in fresh.agents.items():
            if n not in self.cfg.agents or n in self.cfg.custom_agents or n in fresh.custom_agents:
                self.cfg.agents[n] = a  # agent có sẵn giữ nguyên đối tượng (model/effort đang dùng)
        self.cfg.custom_agents = fresh.custom_agents
        self.cfg.workflows = fresh.workflows
        if self.cfg.lead not in self.cfg.agents:
            self.cfg.lead = fresh.lead
        await self._rebuild_panes()
        added, removed = set(self.cfg.agents) - before, before - set(self.cfg.agents)
        msg = (f"⚙ Đã cập nhật agent/workflow tuỳ chỉnh. Agent: {', '.join(self.cfg.agents)}"
               + (f" (mới: {', '.join(sorted(added))})" if added else "")
               + (f" (đã xoá: {', '.join(sorted(removed))})" if removed else "")
               + f". Workflow: {', '.join(self.cfg.workflows) or '(chưa có)'}.")
        self.orch.log(msg)
        self.refresh_view()

    def flows_text(self) -> str:
        if not self.cfg.workflows:
            return "Chưa có workflow nào. Tạo bằng /custom → '+ Thêm workflow' (có mẫu sẵn)."
        lines = []
        for n, w in self.cfg.workflows.items():
            lines.append(f"⚙ {n}  ({w.summary()})" + (f" — {w.description}" if w.description else ""))
            for i, st in enumerate(w.steps, 1):
                lines.append(f"   {i}. [{st.agent}{('@' + st.effort) if st.effort else ''}] "
                             f"{st.title or st.prompt[:50]}")
        lines.append("Chạy: /flow <tên> <mục tiêu>   ·   sửa: /custom")
        return "\n".join(lines)

    async def _rebuild_panes(self) -> None:
        grid = self.query_one("#team-grid", Vertical)
        await grid.remove_children()
        await grid.mount_all([AgentPane(n) for n, a in self.cfg.agents.items() if a.enabled])
        self._preload_panes()

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
            self.action_help()
            return
        if not rest and command_needs_args(cmd) and cmd not in ("flow", "model", "effort"):
            self.notify(command_usage(cmd), severity="warning")
            return
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
                self.open_picker(parts[0], cmd)
                return
            if cmd == "effort":
                self._check_effort(parts[0], parts[1].strip())
            self.notify(o.set_agent_option(parts[0], cmd, parts[1].strip()))
        elif cmd == "models":
            parts = rest.split()
            if parts and parts[0] not in self.cfg.agents:
                self.notify(f"Dùng: /models [agent] [làm mới] — agent: {', '.join(self.cfg.agents)}",
                            severity="warning")
                return
            if len(parts) > 1:
                async def _d(agent=parts[0]):
                    self.notify(f"Đang hỏi {agent} danh sách model…")
                    msg = await o.discover_models(agent)
                    o.log("⚙ " + msg)
                    self.write_sys(self.models_text(agent))
                    self.refresh_view()
                self.run_worker(_d(), exclusive=False)
                return
            self.write_sys(self.models_text(parts[0] if parts else None))
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
        elif cmd == "drop":
            bar = self.query_one("#plan", PlanBar)
            gid = num(rest) if rest else bar.goal_id
            g = o.db.goal(gid) if gid is not None else None
            if not g or g.status != "awaiting":
                self.notify("Không có kế hoạch nháp nào để bỏ", severity="warning")
                return
            self.notify(f"Đã bỏ kế hoạch #{gid} ({o.discard_plan(gid)} task nháp)")
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
        elif cmd == "compact":
            async def _c(focus=rest):
                ok, msg = await o.compact(focus)
                self.notify(msg, severity="information" if ok else "warning")
                self.refresh_view()
            self.run_worker(_c(), exclusive=False)
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
                lead += " · tuỳ chỉnh (/custom)" if n in self.cfg.custom_agents else ""
                lines.append(f"{n:12} {st}{lead}\n   model/effort: {a.label()}"
                             + (f"   (effort hợp lệ: {', '.join(a.efforts)})" if a.efforts else "")
                             + f"\n   lệnh: {' '.join(a.argv('<prompt>'))}"
                             + f"\n   @file → {mentions.describe(a.binary, a.file_ref, a.file_args, a.image_args)}"
                             + f"\n   vai trò: {a.role}")
            self.write_sys("\n".join(lines))
        elif cmd == "setup":
            self.open_setup()
            return
        elif cmd in ("custom", "agent-moi", "workflow", "workflows"):
            self.open_custom()
            return
        elif cmd in ("flow", "flows"):
            name, _, goal = rest.partition(" ")
            if not name or not goal.strip():
                if name and name not in self.cfg.workflows:
                    self.notify(f"Không có workflow '{name}'", severity="warning")
                self.write_sys(self.flows_text())
                return
            res = o.run_workflow(name, goal.strip())
            if isinstance(res, str):
                self.notify(res, severity="warning")
        elif cmd in ("quit", "exit", "q"):
            self.call_later(self.action_quit)
        else:
            near = suggest_command(cmd)
            self.notify(f"Không hiểu lệnh /{cmd}" + (f" — có phải /{near}?" if near else "")
                        + " · gõ / để xem danh sách, F1 trợ giúp", severity="warning")
        self.refresh_view()
