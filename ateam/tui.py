"""Giao diện terminal (Textual): tab Bảng việc + tab Đội (log từng agent & timeline)."""

from __future__ import annotations

import asyncio
import difflib
import inspect
import json
import re
import shlex
import shutil
import time
import unicodedata
from collections import deque
from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (Button, Checkbox, DataTable, Footer, Header, Input, OptionList,
                             RichLog, Select, SelectionList, Static, TabbedContent, TabPane)
from textual.widgets.selection_list import Selection
from textual.widgets.option_list import Option

from . import clipboard, diffview, gitops, mentions, shell, update
from .config import (CATALOG, CUSTOM_FILE, INSTALL_HINTS, LEAD_ALIAS, NAME_RE, PROVIDERS, ROLES, TIERS,
                     WORKFLOW_TEMPLATES, AgentConfig, Config, TeamPlan, builtin_agent, default_cli,
                     full_access_supported, plan_team, provider_of, provider_template, save_onboard,
                     tier_preset,
                     Workflow, WorkflowStep, agent_from_dict, agent_templates, describe_models,
                     clear_agent_state, load_config, load_custom, load_state, mark_setup_done, needs_setup,
                     save_custom_item,
                     save_project_setting, workflow_to_dict)
from .db import ACTIVE, DB, GOAL_ENDED
from .orchestrator import SYSTEM, Orchestrator

# màu "đang chạy/đang xử lý": xanh dương (256 màu, Terminal.app không có truecolor); magenta trước đây
# bị Terminal.app vẽ gần như đỏ, dễ nhầm với lỗi
RUNNING = "dodger_blue1"
STATUS = {
    "draft": ("nháp", "yellow"),
    "queued": ("chờ", "cyan"),
    "running": ("đang chạy", f"bold {RUNNING}"),
    "done": ("xong", "green"),
    "failed": ("lỗi", "bold red"),
    "cancelled": ("đã huỷ", "dim"),
    "blocked": ("bị chặn", "red"),
    "conflict": ("xung đột", "bold yellow"),
    "review": ("chờ duyệt", "bold yellow"),
}
STATUS_ICON = {"draft": "✎", "queued": "◌", "done": "✓", "failed": "✗", "cancelled": "–",
               "blocked": "⊘", "conflict": "≠", "review": "◆"}  # running: dùng SPIN
BAR_STYLE = {"running": RUNNING, "done": "green", "failed": "red", "cancelled": "grey50",
             "blocked": "red", "conflict": "yellow", "review": "yellow"}
GOAL_STATUS = {
    "planning": ("đang lập kế hoạch", RUNNING),
    "awaiting": ("chờ duyệt (F2)", "yellow"),
    "grilling": ("đang hỏi bạn", "yellow"),
    "cancelled": ("đã bỏ", "dim"),
    "running": ("đang làm", "cyan"),
    "reviewing": ("đang review", RUNNING),
    "done": ("hoàn thành", "green"),
    "incomplete": ("chưa xong", "yellow"),
    "failed": ("lỗi", "red"),
}
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
NARROW_WIDTH = 110  # terminal hẹp hơn: bảng việc và log xếp dọc thay vì hai cột
# ô nhập đang ở "/continue <ref> …" (ref = m12 / t40), nhóm 1 = ref
CONTINUE_RE = re.compile(r"/(?:continue|tiep|c) (\S+) ")
SILENT_WARN = 60  # giây không có output -> cảnh báo "im lặng"
PANE_MODELS = 5   # số model gợi ý hiện trong ô agent (đủ xem bằng /models <agent>)
RESET = "\x00reset"  # lựa chọn "quay về mặc định" trong bảng chọn

HELP = """\
Gõ một câu bình thường  → giao MỤC TIÊU cho trưởng nhóm lập kế hoạch & chia việc
                          (hoặc chạy theo workflow mặc định nếu đã chọn trong /setup).

Giao việc:
  /task <agent> <nội dung>          giao tay (vd: /task codex viết test cho utils.py)
                                    agent nhận đúng nguyên văn bạn gõ (gõ /task rồi chọn agent)
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
  /continue <m12|t40> <yêu cầu>     tiếp tục mục tiêu (m) hoặc thread /task (t) đã xong: trưởng nhóm
                                    lập task bổ sung dựa trên việc đã làm / agent nhận kèm các lượt trước.
                                    F6 (Ctrl+O) với task đang chọn, hoặc bấm "↪ Tiếp tục" ở khung mục tiêu
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
  /usage                            thống kê lượt chạy, thời gian, token ước tính theo agent, rồi hỏi
                                    hạn mức thật từ từng CLI (claude/agy: /usage, opencode stats, codex)
  /update                           kiểm tra và cập nhật ateam lên bản mới nhất (mở lại app sau đó)
  /cooldown <agent> <phút>          cho agent tạm nghỉ (vd khi bạn biết nó sắp hết hạn mức)
  /cooldown <agent> off             cho agent làm việc lại ngay

Model & effort của từng agent (được lưu lại cho lần sau):
  /model <agent> <tên model>        vd: /model claude opus   ·   /model grok grok-4.7-build-fast
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
  /goal <mục tiêu>                  trưởng nhóm lập kế hoạch, kể cả khi đã đặt workflow mặc định
  /grill <mục tiêu>                 "grill me": trưởng nhóm hỏi bạn từng câu (phạm vi, luồng, dữ liệu, ca
                                    biên, tiêu chí xong…) kèm phương án gợi ý, tới khi đủ rõ thì chốt đặc tả
                                    rồi lập kế hoạch. Trả lời ở ô nhập; gõ số / bấm để chọn phương án
  /grill xong   /grill bỏ           chốt luôn với những gì đã trả lời / bỏ mục tiêu đang hỏi đáp

Khác:
  /pause  /resume                   tạm dừng / tiếp tục nhận task mới
  /clear                            dọn task & mục tiêu đã kết thúc khỏi bảng (nút 🗑 trên bảng)
  /compact [trọng tâm]              trưởng nhóm tóm tắt ghi chú, mục tiêu & log cho prompt sau gọn hơn
  /log <task>   /log sys            xem log 1 task / log hệ thống (Ctrl+L)
  /team  /board  /term  /git        chuyển tab Đội / Bảng việc / Terminal / Git (Ctrl+T xoay vòng)

Lệnh terminal (tab 💻 Terminal):
  !<lệnh>                           chạy lệnh trong thư mục dự án, vd !yarn dev, !make test
  !                                 gợi ý script package.json, target Makefile, lệnh gần đây (Enter chạy)
  /sh <lệnh>                        như !<lệnh>
  /stop [số]                        dừng lệnh đang chọn (nút ■ Dừng / ↻ Chạy lại / ✗ Xoá trong tab)

Git (tab 🌿 Git — Ctrl+T xoay tới, hoặc /git):
  /git                              mở tab Git: file thay đổi, commit, nhánh, lịch sử, stash, pull/push
                                    trong danh sách file: Space stage/bỏ stage · a stage tất cả · u bỏ stage
                                    tất cả · x bỏ thay đổi · Enter/d xem diff · c tới ô commit message
                                    trong lịch sử: Enter/d xem commit · r revert
  /git <lệnh>                       chạy git <lệnh> bất kỳ ở tab Terminal, vd /git tag v1.0,
                                    /git cherry-pick abc123, /git remote add origin <url>
  /commit <message>                 commit file đã stage (chưa stage gì thì commit mọi thay đổi)
  /commit --no-verify <message>     commit bỏ qua git hook (pre-commit, commit-msg); /commit -n cũng được.
                                    Trong tab Git: ô "Bỏ qua hook (--no-verify)" dưới nút Commit
  /commit                           trưởng nhóm đọc diff và viết commit message (nút ✨ trong tab Git)
  /push [-f]   /pull   /fetch       đồng bộ với remote (-f = --force-with-lease)
  /branch [tên]   /checkout <nhánh> tạo & chuyển nhánh / chuyển nhánh (trống: mở danh sách nhánh)
  /stash [message]   /stash pop     cất tạm / lấy lại thay đổi chưa commit (/stash list: danh sách)
                                    đổi nhánh, pull, stash bị chặn khi agent đang chạy task

Trợ giúp & thoát:
  /help                             trợ giúp này (F1)
  F2 = Ctrl+G, F5 = Ctrl+R, F6 = Ctrl+O   dùng F2/F5/F6 khi terminal chặn phím Ctrl (vd terminal trong VS Code/
                                    Cursor trên Mac: Ctrl+G là Go to Line, Ctrl+R là Run Recent).
                                    MacBook: giữ fn khi bấm F2/F5
  /quit                             thoát (Ctrl+Q) — agent đang chạy sẽ bị dừng"""

WELCOME = """\
👋 Chào mừng tới ateam — bắt đầu nhanh:
  • Gõ một mục tiêu (vd: Thêm trang đăng nhập) → trưởng nhóm lập kế hoạch, Enter (hoặc F2) để duyệt & chạy
  • /grill Thêm trang đăng nhập → trưởng nhóm hỏi kỹ từng câu cho rõ yêu cầu rồi mới lập kế hoạch
  • /task codex viết test cho utils.py → giao tay cho 1 agent
  • Gõ / để xem các lệnh · @ để nhắc file · Ctrl+V dán ảnh
  • !yarn dev → chạy lệnh terminal (gõ ! để xem gợi ý) · tab 💻 Terminal
  • /git → tab 🌿 Git: stage, commit (trưởng nhóm viết message), nhánh, pull/push, stash, lịch sử
  • F1 hoặc /help: toàn bộ lệnh & phím tắt · Ctrl+T: đổi tab (Bảng việc / Đội / Terminal / Git)"""

# lệnh cho bảng gợi ý khi gõ "/" (tên, tham số, mô tả ngắn) — giữ khớp với TeamApp.run_command
COMMANDS = [
    ("task", "<agent> <nội dung>", "giao tay cho 1 agent, gửi nguyên văn"),
    ("go", "[mục tiêu]", "duyệt kế hoạch nháp và chạy"),
    ("drop", "[mục tiêu]", "bỏ kế hoạch nháp (huỷ mọi task nháp của nó)"),
    ("goal", "<mục tiêu>", "trưởng nhóm lập kế hoạch (bỏ qua workflow mặc định)"),
    ("grill", "<mục tiêu|xong|bỏ>", "trưởng nhóm hỏi kỹ từng câu để làm rõ yêu cầu rồi mới lập kế hoạch"),
    ("sh", "<lệnh>", "chạy lệnh terminal (như !lệnh), vd /sh yarn dev"),
    ("stop", "[số]", "dừng lệnh terminal đang chọn (hoặc lệnh số đó)"),
    ("term", "", "mở tab Terminal (lệnh đang chạy)"),
    ("git", "[lệnh git]", "mở tab Git; kèm lệnh thì chạy git <lệnh> ở tab Terminal"),
    ("commit", "[--no-verify] [message]", "commit (chưa stage gì thì commit tất cả); trống: trưởng nhóm viết message"),
    ("push", "[-f]", "push nhánh hiện tại (lần đầu tự tạo nhánh trên remote)"),
    ("pull", "", "pull nhánh hiện tại (fast-forward, không được thì merge)"),
    ("fetch", "", "fetch mọi remote"),
    ("branch", "[tên]", "tạo & chuyển sang nhánh mới; trống: danh sách nhánh"),
    ("checkout", "<nhánh>", "chuyển sang nhánh (nhánh remote → tạo nhánh local)"),
    ("stash", "[message|pop|apply|list]", "cất tạm / lấy lại thay đổi chưa commit"),
    ("flow", "<tên> <mục tiêu>", "chạy mục tiêu theo workflow"),
    ("assign", "<task> <agent>", "đổi người làm 1 task"),
    ("edit", "<task> <nội dung>", "sửa nội dung task chưa chạy"),
    ("set", "<task> effort|model <giá trị>", "effort/model riêng cho 1 task"),
    ("retry", "<task>", "chạy lại task"),
    ("cancel", "<task>", "huỷ task"),
    ("review", "<mục tiêu>", "bắt trưởng nhóm review ngay"),
    ("continue", "<m12|t40> <yêu cầu>", "tiếp tục mục tiêu / thread đã xong (F6)"),
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
    ("usage", "", "thống kê lượt chạy + hạn mức còn lại báo bởi từng CLI"),
    ("update", "", "cập nhật ateam lên bản mới nhất"),
    ("cooldown", "<agent> <phút|off>", "cho agent tạm nghỉ"),
    ("compact", "[trọng tâm]", "tóm tắt ngữ cảnh chung cho prompt gọn lại"),
    ("clear", "", "dọn task & mục tiêu đã kết thúc khỏi bảng việc"),
    ("pause", "", "tạm dừng nhận task mới"),
    ("resume", "", "tiếp tục nhận task"),
    ("log", "[task|sys]", "xem log 1 task / log hệ thống"),
    ("team", "", "chuyển sang tab Đội"),
    ("board", "", "chuyển sang tab Bảng việc"),
    ("help", "", "toàn bộ lệnh & phím tắt"),
    ("quit", "", "thoát"),
]
COMMAND_ALIASES = {"grill-me": "grill", "hoi": "grill", "h": "help", "?": "help", "t": "task", "tiep": "continue", "c": "continue", "flows": "flow", "workflow": "custom",
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


# ============================================================================ tô màu log
LOG_TIME_RE = re.compile(r"^\[(\d\d:\d\d:\d\d)\] (.*)$")
LOG_PREFIX_RE = re.compile(r"^(\s*\[[\w.:-]+\] )(.*)$")  # "[test] …", "  [claude] …" (trưởng nhóm)
LOG_ICON_STYLE = {"✓": "green", "✗": "bold red", "▶": "cyan", "■": "cyan", "➕": "blue",
                  "⚠": "yellow", "⚙": "dim", "↪": "magenta", "📝": "yellow"}
CODEX_HEAD_RE = re.compile(
    r"^(OpenAI Codex v|Reading (additional input|prompt) from stdin|-{4,}$|"
    r"(workdir|model|provider|approval|sandbox|reasoning effort|reasoning summaries|session id): )")
CODEX_MARKS = ("codex", "thinking", "exec", "tokens used", "user")
# prompt ateam gửi thành viên (prompts.task_prompt) bị CLI in lại, vd opencode "File not found: <prompt>":
# dòng đầu chứa PROMPT_START, dòng cuối (luật SUMMARY) chứa PROMPT_END -> gập lại cho log dễ đọc
PROMPT_START = ", a member of an AI agent team"
PROMPT_END = "anything teammates need to know."
PROMPT_FOLD_MAX = 400  # không thấy dòng cuối sau ngần này dòng thì thôi gập (prompt bị cắt)
RUST_LOG_RE = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z\s+(ERROR|WARN|INFO|DEBUG|TRACE)\s+(.*)$")
DELEGATE_OPEN_RE = re.compile(r"^\s*<<<DELEGATE\b(.*?)>>>\s*(.*)$")
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
MD_INLINE_RE = re.compile(r"\*\*(.+?)\*\*|`([^`]+)`")


def md_text(s: str, style: str = "") -> Text:
    """Markdown trong một dòng: **đậm**, `code`, # tiêu đề, - gạch đầu dòng."""
    h = re.match(r"^(#{1,6})\s+(.*)$", s)
    if h:
        s, style = h.group(2), (style + " bold").strip()
    b = re.match(r"^(\s*)[-*] (.*)$", s)
    if b:
        s = f"{b.group(1)}• {b.group(2)}"
    t = Text(style=style)
    pos = 0
    for m in MD_INLINE_RE.finditer(s):
        t.append(s[pos:m.start()])
        if m.group(1) is not None:
            t.append(m.group(1), "bold")
        else:
            t.append(m.group(2), "cyan")
        pos = m.end()
    t.append(s[pos:])
    return t


def plan_text(items: list, title: str = "📋 Kế hoạch") -> Text:
    """Kế hoạch JSON của trưởng nhóm -> danh sách task dễ đọc (id, agent@effort, tiêu đề, phụ thuộc,
    đoạn đầu nội dung)."""
    t = Text()
    t.append(f"{title}: {len(items)} task", "bold yellow")
    for it in items:
        agent = str(it.get("agent", "?")) + (f"@{it['effort']}" if it.get("effort") else "")
        t.append(f"\n  #{it.get('id', '?')}  ", "bold")
        t.append(agent, "bold cyan")
        t.append("  " + str(it.get("title", "")), "bold")
        deps = it.get("depends_on") or []
        if deps:
            t.append(f"  ⟵ sau #{', #'.join(map(str, deps))}", "dim")
        prompt = " ".join(str(it.get("prompt", "")).split())
        if prompt:
            t.append("\n      " + (prompt if len(prompt) <= 240 else prompt[:239] + "…"), "dim")
    return t


def review_text(data: dict) -> Text:
    t = Text()
    if data.get("done"):
        t.append("🔎 Review: ✓ hoàn thành", "bold green")
    else:
        t.append("🔎 Review: cần làm thêm", "bold yellow")
    if data.get("summary"):
        t.append("\n  ")
        t.append_text(md_text(str(data["summary"])))
    new = data.get("new_tasks") or []
    if new:
        t.append("\n")
        t.append_text(plan_text(new, "  ➕ Việc giao thêm"))
    return t


def json_text(raw: str) -> Text | None:
    """Kế hoạch (mảng task) hoặc kết quả review (object có done/summary) -> Text; còn lại None."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if isinstance(data, list) and data and all(isinstance(x, dict) and "agent" in x for x in data):
        return plan_text(data)
    if isinstance(data, dict) and "done" in data and ("summary" in data or "new_tasks" in data):
        return review_text(data)
    return None


def set_static(widget: Static, content) -> None:
    """Static.update chỉ khi nội dung thật sự đổi: update luôn bắt widget vẽ (và có thể tính lại bố cục),
    mà vòng làm mới chạy mỗi 0,5 giây với nội dung thường y nguyên."""
    sig = (content.plain, tuple(content.spans), str(content.style)) if isinstance(content, Text) else content
    if getattr(widget, "_ateam_sig", None) != sig:
        widget._ateam_sig = sig
        widget.update(content)


LOG_SHOW_LINES = 300  # số dòng cuối hiện khi mở log 1 task (cuộn lên xem thêm: /log hoặc file .ateam/logs)
LOG_TAIL_BYTES = 192 * 1024  # mở log 1 task: chỉ đọc chừng này byte cuối (file vài MB đọc + tô màu rất chậm)


def read_log_tail(path: Path, start: int = 0, limit: int = LOG_TAIL_BYTES) -> str:
    """Phần cuối file log từ byte `start` (bỏ dòng bị cắt dở ở đầu nếu phải bỏ bớt)."""
    with open(path, "rb") as f:
        size = f.seek(0, 2)
        if start > size:  # file bị ghi lại từ đầu (task chạy lại)
            start = 0
        begin = max(start, size - limit)
        f.seek(begin)
        data = f.read()
    if begin > start:
        nl = data.find(b"\n")
        data = data[nl + 1:] if nl >= 0 else b""
    return data.decode("utf-8", errors="replace")


def styled_lines(text: str, styler: "LogStyler") -> list[Text]:
    """Tô cả file từ đầu (để biết đang ở khối nào), rồi bên gọi lấy phần cuối."""
    return [t for t in map(styler.style, text.splitlines()) if t is not None]


class LogStyler:
    """Tô màu từng dòng log khi hiển thị (file log trên đĩa giữ nguyên chữ thô).

    Có trạng thái vì vài khối kéo dài nhiều dòng: prompt mà codex in lại (ẩn đi), khối NOTE/DELEGATE.
    `style(line)` trả None nghĩa là bỏ dòng đó."""

    def __init__(self, task_headers: bool = True) -> None:
        self.task_headers = task_headers  # dòng "$ agent · task · …" của ateam (tắt cho log lệnh terminal)
        self.codex = False      # đang ở header của codex
        self.echo = False       # đang ở đoạn codex in lại prompt
        self.block = ""         # "note" | "delegate" khi đang trong khối nhiều dòng
        self.folded = -1        # >= 0: đang ẩn prompt ateam bị CLI in lại (số dòng đã ẩn)
        self.last_error = ""
        self.json_buf: list[str] = []  # JSON nhiều dòng của trưởng nhóm đang gom
        self.after_json = False         # dòng trước vừa vẽ xong một khối JSON

    def style(self, line: str) -> Text | None:
        out = self._style(line)
        self.after_json = out is not None and ("📋 Kế hoạch" in out.plain or "🔎 Review" in out.plain)
        return out

    def _style(self, line: str) -> Text | None:
        s = line.rstrip()
        if self.after_json and LOG_PREFIX_RE.sub(r"\2", s).strip() == "```":
            return None  # rào đóng của khối JSON vừa vẽ
        if self.json_buf:  # đang gom JSON nhiều dòng: đủ thì vẽ, quá dài/không phải JSON thì trả lại thô
            p = LOG_PREFIX_RE.match(s)  # dòng của trưởng nhóm trong log hệ thống: "  [claude] …"
            self.json_buf.append(p.group(2) if p else s)
            raw = "\n".join(self.json_buf)
            done = json_text(raw)
            if done is not None:
                self.json_buf = []
                return done
            if len(self.json_buf) < 400 and not self.json_buf[-1].startswith("```"):
                return None
            lines, self.json_buf = self.json_buf, []
            return Text("\n").join(md_text(x) for x in lines)
        if s.strip() == "```json":  # rào mở khối JSON của trưởng nhóm: bỏ cho gọn
            return None
        if self.echo:
            if s not in CODEX_MARKS and not s.startswith(("warning:", "ERROR", "error:")) \
                    and not RUST_LOG_RE.match(s):
                return None
            self.echo = False
        if self.task_headers and s.startswith("$ "):  # tiêu đề lượt chạy: "$ agent · task · model · effort · thư mục"
            self.codex, self.block, self.folded = False, "", -1
            parts = s[2:].split(" · ")
            t = Text()
            t.append("▍" + (" · ".join(parts[:-1]) if len(parts) > 1 else s[2:]), "bold cyan")
            if len(parts) > 1:
                t.append("  " + parts[-1], "dim")
            return t
        if self.folded >= 0:
            self.folded += 1
            if PROMPT_END in s or self.folded > PROMPT_FOLD_MAX:
                self.folded = -1
            return None
        start = s.find('You are "')
        if start >= 0 and PROMPT_START in s[start:]:
            t = Text()
            pre = s[:start].rstrip()
            if pre:  # vd "Error: File not found:"
                head = self._style(pre) or Text(pre)
                t.append_text(head)
                t.stylize(head.style, 0, len(head))  # append_text bỏ style gốc của Text
                t.append(" ")
            t.append("‹prompt ateam gửi agent — đã ẩn›", "dim italic")
            self.folded = -1 if PROMPT_END in s else 0  # đặt sau khi tô `pre` (gọi lại _style)
            return t
        if self.block:
            if "<<<END>>>" in s:
                rest = s.replace("<<<END>>>", "").strip()
                kind, self.block = self.block, ""
                return Text("   " + rest, "yellow" if kind == "note" else "magenta") if rest else None
            return Text("   " + s, "yellow" if self.block == "note" else "dim")
        m = LOG_TIME_RE.match(s)
        if m:
            t = Text()
            t.append(m.group(1) + " ", "dim")
            body = m.group(2)
            icon = body[:1] if body[:1] in LOG_ICON_STYLE else body[:2] if body[:2] in LOG_ICON_STYLE else ""
            if icon:
                t.append(icon, LOG_ICON_STYLE[icon])
                # lỗi/cảnh báo tô cả dòng cho dễ thấy; ⚙ (thông tin cấu hình) để mờ
                t.append(body[len(icon):], {"✗": "red", "⚠": "yellow", "⚙": "dim"}.get(icon, ""))
            else:
                t.append_text(self._style(body) or Text())
            return t
        m = LOG_PREFIX_RE.match(s)
        if m:
            inner = self._style(m.group(2))
            if inner is None:
                return None
            t = Text()
            t.append(m.group(1), "dim")
            t.append_text(inner)
            return t
        if s.startswith(("OpenAI Codex v", "Reading additional input from stdin")):
            self.codex = True
        if self.codex:
            if s == "user":
                self.codex, self.echo = False, True
                return Text("▸ prompt gửi agent (ẩn)", "dim italic")
            if CODEX_HEAD_RE.match(s):
                return Text(s, "dim")
            self.codex = False
        if s in CODEX_MARKS:
            return Text("▸ " + s, "dim italic")
        if s.startswith("ERROR:"):
            body = s[len("ERROR:"):].strip()
            msg = body
            try:
                data = json.loads(body)
                err = data.get("error") if isinstance(data, dict) else None
                msg = (err.get("message") if isinstance(err, dict) else None) or data.get("message") or body
            except (ValueError, AttributeError):
                pass
            if msg == self.last_error:  # codex in cùng một lỗi nhiều lần
                return None
            self.last_error = msg
            return Text("✗ Lỗi: " + msg, "bold red")
        r = RUST_LOG_RE.match(s)
        if r:
            lvl = r.group(1)
            return Text(f"{lvl.lower()}: {r.group(2)}",
                        "red" if lvl == "ERROR" else "yellow" if lvl == "WARN" else "dim")
        if s.lower().startswith(("warning:", "warn:")):
            return Text(s, "yellow")
        if s.lower().startswith("error:"):
            return Text(s, "bold red")
        if s.startswith("> "):  # "> build · grok-4.7" của opencode
            return Text(s, "dim")
        if s.startswith("SUMMARY:"):
            t = Text()
            t.append("✔ Tóm tắt:", "bold green")
            t.append_text(md_text(s[len("SUMMARY:"):], "green"))
            return t
        if s.startswith("<<<NOTE>>>"):
            body = s[len("<<<NOTE>>>"):]
            if "<<<END>>>" in body:
                body = body.replace("<<<END>>>", "")
            else:
                self.block = "note"
            t = Text()
            t.append("📝 Ghi chú: ", "bold yellow")
            t.append(body.strip(), "yellow")
            return t
        stripped = s.strip()
        if stripped.startswith(("[", "{")):
            done = json_text(stripped)
            if done is not None:
                return done
            if stripped in ("[", "{") or stripped.startswith(("[{", '{"')):
                self.json_buf = [stripped]  # có thể là JSON trải nhiều dòng: gom tiếp
                return None
        d = DELEGATE_OPEN_RE.match(s)
        if d:
            attrs = dict(ATTR_RE.findall(d.group(1)))
            if "<<<END>>>" not in d.group(2):
                self.block = "delegate"
            t = Text()
            t.append(f"↪ Giao cho {attrs.get('to', '?')}", "bold magenta")
            if attrs.get("title"):
                t.append(": " + attrs["title"], "magenta")
            return t
        return md_text(s)


# ============================================================================ widgets
class TextInput(Input):
    """Ô nhập gõ tiếng Việt không lỗi dấu.

    Bộ gõ (OpenKey/EVKey… để "Unicode tổ hợp", hoặc gửi dấu thành ký tự riêng) có thể đưa vào
    chữ dạng tách rời "e" + dấu mũ U+0302 + dấu nặng U+0323. Terminal vẽ dấu rời lệch khỏi chữ
    ("lỗi font"), còn Backspace của Input chỉ xoá một code point nên khi bộ gõ xoá chữ cũ để thay
    chữ mới thì dấu sót lại. Vì vậy sau mỗi lần sửa ta gộp về dạng dựng sẵn (NFC), và Backspace/Delete
    xoá trọn một chữ cùng các dấu đi kèm.

    OpenKey gửi thêm ký tự mồi U+202F trước khi xoá chữ cũ và tính nó vào số Backspace. Terminal chèn
    U+202F nên shell không sao, nhưng Textual coi nó là ký tự không in được và bỏ qua -> Backspace thừa
    xoá mất một chữ thật ("chào" thành "cà"). Ta ghi nhận ký tự mồi và nuốt đúng một Backspace theo sau.

    Backspace/Delete cũng được xử lý ngay trong `_on_key`: nếu để binding của Input lo, phím xoá đi vòng
    qua app nên chạy *sau* các chữ tới cùng lượt, mà bộ gõ thì bắn Backspace + chữ mới liền nhau -> chữ
    mới bị chính Backspace xoá ("tôi" thành "to"), chỉ xảy ra khi các phím tới dồn (lúc bị lúc không).
    """

    IME_PLACEHOLDER = "\u202f"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._ime_placeholders = 0  # số ký tự mồi đã nhận mà chưa có Backspace tương ứng

    async def _on_key(self, event: events.Key) -> None:
        if event.character == self.IME_PLACEHOLDER:
            self._ime_placeholders += 1
            event.stop()
            event.prevent_default()
            return
        if event.key in ("backspace", "delete"):
            event.stop()
            event.prevent_default()
            if event.key == "backspace":
                self.action_delete_left()
            else:
                self.action_delete_right()
            return
        self._ime_placeholders = 0
        await super()._on_key(event)

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
        if self._ime_placeholders:  # Backspace này xoá ký tự mồi của OpenKey, vốn không được chèn
            self._ime_placeholders -= 1
            return
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
        self.styler = LogStyler()

    def compose(self) -> ComposeResult:
        yield Static(classes="pane-head")
        # min_width=1: RichLog mặc định vẽ mỗi dòng rộng ít nhất 78 cột; ô agent hẹp hơn thì
        # sinh thanh cuộn ngang, chữ bị cắt và vuốt trackpad làm log trôi sang ngang
        yield ReflowLog(classes="pane-log", wrap=True, markup=False, highlight=False,
                      max_lines=3000, min_width=1)

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


class Btn(Button):
    """Nút chỉ có chữ (không nền, không viền — màu chữ theo variant, xem TeamApp.CSS): nhãn bọc
    "[ … ]" để vẫn nhận ra là nút."""

    def __init__(self, label=None, *args, **kw):
        super().__init__(self.wrap(label), *args, **kw)

    @staticmethod
    def wrap(label):
        if isinstance(label, str):
            label = Text(label)  # chữ thường, không bóc markup (nhãn có "[" / "]")
        if isinstance(label, Text) and not label.plain.startswith("[ "):
            label = Text.assemble("[ ", label, " ]")
        return label

    def validate_label(self, label):
        return super().validate_label(self.wrap(label))


class ReflowLog(RichLog):
    """RichLog vẽ mỗi dòng theo bề rộng lúc ghi; đổi bề rộng (kéo cửa sổ, terminal hẹp rồi rộng lại)
    thì dòng cũ vẫn giữ bề rộng cũ — có khi chỉ 1–2 ký tự, thành chữ dọc. Lớp này giữ lại nội dung đã ghi
    và vẽ lại khi bề rộng đổi."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self._items: deque = deque(maxlen=self.max_lines or 5000)
        self._width = 0
        self._reflowing = False

    def write(self, content, *args, **kw):
        if not self._reflowing:
            self._items.append(content)
        return super().write(content, *args, **kw)

    def clear(self):
        self._items.clear()
        return super().clear()

    def on_resize(self, event) -> None:
        super().on_resize(event)  # RichLog: ghi các dòng hoãn lại lúc chưa biết kích thước
        width = self.scrollable_content_region.width
        if self._width and width != self._width and self._items:
            self.set_timer(0.15, self._reflow, name="reflow")
        self._width = width

    def _reflow(self) -> None:
        at_end = self.is_vertical_scroll_end
        self._reflowing = True
        try:
            RichLog.clear(self)
            for item in self._items:
                super().write(item, scroll_end=False)
        finally:
            self._reflowing = False
        if at_end:
            self.scroll_end(animate=False)


class BaseModal(ModalScreen):
    """Popup chung: dòng tiêu đề có nút ✕; Esc đóng *một* lớp — không dùng priority, nên dropdown (Select)
    hay danh sách đang mở nhận Esc trước và chỉ đóng chính nó. Form có thay đổi chưa lưu (dirty) cần Esc
    hai lần (trong 3 giây) mới đóng."""

    BINDINGS = [Binding("escape", "request_close", "Đóng")]
    DEFAULT_CSS = """
    BaseModal .m-titlebar { height: 1; }
    BaseModal .m-title { width: 1fr; text-style: bold; }
    """
    _initial = None
    _esc_at = 0.0

    def title_bar(self, title: str) -> Horizontal:
        return Horizontal(Static(Text(title, "bold"), classes="m-title"),
                          Btn("✕", classes="m-close"), classes="m-titlebar")

    def form_values(self) -> tuple:
        return tuple((w.id, w.value) for w in self.query("Input, Select, Checkbox"))

    def mark_clean(self) -> None:
        """Gọi khi form vừa điền xong giá trị ban đầu."""
        self._initial = self.form_values()

    def dirty(self) -> bool:
        return self._initial is not None and self.form_values() != self._initial

    def close(self) -> None:
        self.dismiss(None)

    def action_request_close(self) -> None:
        if self.dirty() and time.time() - self._esc_at > 3:
            self._esc_at = time.time()
            self.notify("Còn thay đổi chưa lưu — Esc lần nữa để bỏ, Ctrl+S để lưu", severity="warning")
            return
        self.close()

    @on(Button.Pressed, ".m-close")
    def _close_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.close()


class ChoiceScreen(BaseModal):
    """Bảng chọn model/effort cho 1 agent. Trả về giá trị chọn, RESET, hoặc None (Esc)."""

    DEFAULT_CSS = """
    ChoiceScreen { align: center middle; }
    #choice-box { width: 60; height: auto; max-height: 80%; border: round $panel-lighten-2;
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
            yield self.title_bar(self.title_text)
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


class HelpScreen(BaseModal):
    """Toàn bộ lệnh & phím tắt trong một bảng nổi cuộn được (/help, F1)."""

    BINDINGS = [Binding("f1", "close", "Đóng", priority=True)]
    DEFAULT_CSS = """
    HelpScreen { align: center middle; }
    #help-box { width: 124; max-width: 100%; height: 90%; border: round $panel-lighten-2;
                background: $surface; padding: 0 1; }
    #help-body { height: 1fr; }
    #help-foot { height: 1; color: $text-muted; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield self.title_bar("Trợ giúp ateam")
            with VerticalScroll(id="help-body"):
                yield Static(help_text())
            yield Static("↑↓ / PgUp PgDn cuộn · Esc hoặc F1 đóng", id="help-foot")

    def on_mount(self) -> None:
        self.query_one("#help-body").focus()

    def action_close(self) -> None:
        self.close()


class OnboardScreen(BaseModal):
    """Wizard thiết lập đội (lần đầu mở app, /setup, `ateam setup`): hỏi từng bước — CLI đang dùng, kiểu làm
    việc, mức chi phí, gán CLI · model · effort cho từng vai trò, an toàn & duyệt code, lệnh kiểm tra — rồi
    xem lại và lưu. Mỗi lúc chỉ dựng widget của bước đang mở. Esc = quay lại bước trước.

    Trả về {"plan": TeamPlan, "settings": {...}} (xem config.save_onboard), hoặc None nếu đóng."""

    BINDINGS = [Binding("ctrl+s", "save", "Lưu", priority=True)]
    DEFAULT_CSS = """
    OnboardScreen { align: center middle; }
    #ob-box { width: 116; max-width: 98%; height: auto; max-height: 95%; border: round $panel-lighten-2;
              background: $surface; padding: 0 1; }
    #ob-steps { height: auto; color: $text-muted; margin-bottom: 1; }
    #ob-body { height: auto; max-height: 34; }
    #ob-body .ob-q { text-style: bold; margin-top: 1; }
    #ob-body .ob-hint { color: $text-muted; }
    #ob-body OptionList, #ob-body SelectionList { height: auto; max-height: 12; border: none;
                                                  padding: 0; background: $surface; }
    #ob-body .ob-row { height: 3; }
    /* cột co giãn theo bề rộng: terminal hẹp vẫn thấy đủ CLI / model / effort, mô tả co lại trước */
    #ob-body .ob-role { width: 17; padding: 1 0 0 0; text-style: bold; }
    #ob-body .ob-cli { width: 2fr; min-width: 17; }
    #ob-body .ob-model { width: 3fr; min-width: 21; }
    #ob-body .ob-effort { width: 2fr; min-width: 13; }
    #ob-body .ob-desc { width: 3fr; min-width: 0; padding: 1 0 0 1; color: $text-muted; text-wrap: nowrap;
                        text-overflow: ellipsis; }
    #ob-body #ob-verify-input { margin-top: 1; }
    #ob-buttons { height: auto; margin-top: 1; }
    #ob-buttons .ob-spacer { width: 1fr; }
    #ob-buttons Button { margin-left: 2; }
    """
    # (khoá, tiêu đề, tên ngắn trên thanh tiến trình)
    STEPS = [("cli", "CLI bạn đang dùng", "CLI"), ("style", "Kiểu làm việc", "Kiểu"),
             ("tier", "Mức chi phí", "Mức"), ("roles", "Vai trò · model · effort", "Vai trò"),
             ("safety", "An toàn & duyệt code", "An toàn"), ("verify", "Lệnh kiểm tra", "Kiểm tra"),
             ("review", "Xem lại & lưu", "Xem lại")]
    STYLES = [("approve", "Trưởng nhóm lập kế hoạch, tôi duyệt rồi mới chạy",
               "kế hoạch hiện ở khung Duyệt kế hoạch, Enter/F2 để chạy — an toàn, dễ kiểm soát"),
              ("auto", "Trưởng nhóm lập kế hoạch và chạy luôn", "nhanh nhất, không cần duyệt"),
              ("flow", "Theo quy trình cố định: thiết kế → code → test",
               "gõ mục tiêu là chạy workflow 'tinh-nang'; /goal vẫn để trưởng nhóm lập kế hoạch"),
              ("manual", "Chủ yếu tôi tự giao từng việc (/task)",
               "tắt trưởng nhóm tự review và giao thêm việc")]
    TIER_HINTS = {"eco": "model nhỏ/nhanh, effort thấp — tốn ít hạn mức nhất",
                  "balanced": "model mạnh vừa, effort trung bình; trưởng nhóm và review cao hơn 1 bậc",
                  "max": "model mạnh nhất, effort cao — chất lượng tốt nhất, tốn hạn mức nhất"}
    APPLY = [("shared", "Sửa thẳng vào thư mục dự án", "đơn giản; các agent làm chung một chỗ"),
             ("worktree-auto", "Mỗi task một nhánh git riêng, xong thì tự merge",
              "an toàn khi nhiều agent chạy song song"),
             ("worktree-review", "Mỗi task một nhánh git riêng, tôi xem diff rồi mới merge",
              "Ctrl+D xem diff kiểu VS Code, Ctrl+Y merge")]

    def __init__(self, root: Path, cfg: Config, orch: Orchestrator, timeout: float = 20):
        super().__init__()
        self.root, self.cfg, self.orch, self.timeout = root, cfg, orch, timeout
        self.step = 0
        self.installed = [p for p in PROVIDERS if shutil.which(p)]
        team = {provider_of(a.command) for a in cfg.active_agents().values()}
        self.providers = [p for p in self.installed if p in team] or list(self.installed)
        self.style = ("flow" if cfg.default_workflow else "manual" if not cfg.auto_review
                      else "approve" if cfg.approve_plan else "auto")
        self.tier = "balanced"
        self.assign: dict[str, tuple[str, str, str] | None] = self._current_assign()
        # assign đang ứng với bộ CLI/mức nào; lần đầu thiết lập (None) thì bước Vai trò điền theo mức chi phí,
        # mở lại /setup thì giữ đội hiện tại cho tới khi đổi CLI hoặc mức
        self._assign_key = (tuple(self.providers), None if needs_setup() else self.tier)
        self.access = "full" if any(a.full_access for a in cfg.active_agents().values()) else "safe"
        self.apply = ("shared" if cfg.isolation != "worktree" else
                      "worktree-review" if cfg.merge == "review" else "worktree-auto")
        self.verify = cfg.verify.command
        self.git = (root / ".git").exists()
        self.discovering = True
        self._esc_at = 0.0

    # ---------------------------------------------------------------- dữ liệu
    def models_of(self, provider: str) -> list[str]:
        a = self.cfg.agents.get(builtin_agent(provider))
        if a is None or provider_of(a.command) != provider:
            a = next((x for x in self.cfg.agents.values() if provider_of(x.command) == provider), None)
        return a.model_choices() if a else list(CATALOG.get(provider, {}).get("models", []))

    def efforts_of(self, provider: str) -> list[str]:
        return [str(e) for e in provider_template(provider).get("efforts") or []] if provider in PROVIDERS else []

    def _current_assign(self) -> dict:
        """Gán vai trò theo đội hiện tại (mở lại /setup): vai trò mà role của agent có nhắc tới; còn lại
        theo mặc định."""
        out: dict = {}
        agents = {n: a for n, a in self.cfg.active_agents().items() if provider_of(a.command)}
        for key, _label, desc in ROLES:
            a = agents.get(self.cfg.lead) if key == "lead" else next(
                (x for x in agents.values() if desc in x.role), None)
            if a and provider_of(a.command) in self.providers:
                out[key] = (provider_of(a.command), a.model, a.effort)
            else:
                out[key] = self._default(key)
        return out

    def _default(self, role: str) -> tuple[str, str, str] | None:
        p = default_cli(role, self.providers)
        if not p:
            return None
        return (p,) + tier_preset(p, self.tier, role, self.models_of(p), self.efforts_of(p))

    def plan(self) -> TeamPlan:
        return plan_team(self.assign)

    def settings(self) -> dict:
        return {"full_access": self.access == "full", "approve_plan": self.style != "auto",
                "auto_review": self.style != "manual", "flow": self.style == "flow",
                "isolation": "worktree" if self.apply.startswith("worktree") else "shared",
                "merge": "review" if self.apply == "worktree-review" else "auto",
                "verify_command": self.verify.strip()}

    # ---------------------------------------------------------------- khung
    def compose(self) -> ComposeResult:
        with Vertical(id="ob-box"):
            yield self.title_bar("Thiết lập đội AI")
            yield Static(id="ob-steps")
            yield VerticalScroll(id="ob-body")
            with Horizontal(id="ob-buttons"):
                yield Btn("Agent & workflow tuỳ chỉnh…", id="ob-custom")
                yield Static(classes="ob-spacer")
                yield Btn("← Quay lại", id="ob-back")
                yield Btn("Tiếp →", id="ob-next", variant="primary")

    async def on_mount(self) -> None:
        self.run_worker(self._discover(), exclusive=True)
        await self.show_step(0)

    async def _discover(self) -> None:
        try:
            await self.orch.discover_all(timeout=self.timeout)
        except Exception as e:  # không bao giờ chặn wizard
            self.orch.log(f"⚠ Không hỏi được danh sách model: {e}")
        self.discovering = False
        if self.STEPS[self.step][0] == "roles":
            await self.show_step(self.step)  # nạp lại model vừa hỏi được

    async def show_step(self, i: int) -> None:
        self.step = i
        key, title, _short = self.STEPS[i]
        self.query_one(".m-title", Static).update(Text(f"Thiết lập đội AI · Bước {i + 1}/{len(self.STEPS)} — {title}",
                                                       "bold"))
        t = Text()
        for n, (_k, _title, name) in enumerate(self.STEPS):
            if n:
                t.append("  ›  ", "dim")
            t.append(f"{n + 1}. {name}", "bold" if n == i else "dim" if n > i else "green")
        self.query_one("#ob-steps", Static).update(t)
        body = self.query_one("#ob-body", VerticalScroll)
        await body.remove_children()
        await body.mount_all(getattr(self, f"_step_{key}")())
        self.query_one("#ob-back", Button).disabled = i == 0
        self.query_one("#ob-next", Button).label = "Lưu & bắt đầu (Ctrl+S)" if key == "review" else "Tiếp →"
        self.query_one("#ob-custom").display = key == "review"
        first = body.query("SelectionList, OptionList, Select, Input")
        (first.first() if first else self.query_one("#ob-next")).focus()

    # ---------------------------------------------------------------- từng bước
    def _step_cli(self) -> list:
        items = []
        for p, (label, _agent) in PROVIDERS.items():
            ok = p in self.installed
            t = Text(f"{label:14}", "bold" if ok else "dim")
            t.append(f"  ✓ đã cài ({p})" if ok else f"  ✗ chưa cài — {INSTALL_HINTS.get(p, p)}",
                     "green" if ok else "dim")
            items.append(Selection(t, p, p in self.providers and ok, disabled=not ok))
        return [Static("Bạn đang dùng những CLI nào? Đội chỉ gồm các CLI được chọn.", classes="ob-q"),
                SelectionList(*items, id="ob-cli"),
                Static("Space: chọn/bỏ · Tab: sang nút Tiếp", classes="ob-hint")]

    def _choice(self, oid: str, items: list[tuple[str, str, str]], current: str, disabled=()) -> OptionList:
        opts = []
        for k, label, hint in items:
            t = Text()  # Text(chữ, style) sẽ tô cả dòng — chỉ tô riêng dấu ●
            t.append("● " if k == current else "○ ", "bold green" if k == current else "dim")
            t.append(label, "bold")
            t.append(f"\n   {hint}", "grey62")  # không dùng dim: trên nền dòng đang chọn sẽ chìm mất
            opts.append(Option(t, id=k, disabled=k in disabled))
        ol = OptionList(*opts, id=oid)
        ol.highlighted = next((n for n, (k, _l, _h) in enumerate(items) if k == current), 0)
        return ol

    def _step_style(self) -> list:
        return [Static("Bạn muốn đội làm việc thế nào?", classes="ob-q"),
                self._choice("ob-style", self.STYLES, self.style),
                Static("↑↓ chọn · Enter: chọn và sang bước tiếp", classes="ob-hint")]

    def _step_tier(self) -> list:
        items = [(k, label, self.TIER_HINTS[k]) for k, label in TIERS]
        return [Static("Ưu tiên tiết kiệm hạn mức hay chất lượng?", classes="ob-q"),
                self._choice("ob-tier", items, self.tier),
                Static("Bước sau điền sẵn model & effort theo mức này — vẫn đổi được từng vai trò.",
                       classes="ob-hint")]

    def _row(self, role: str, label: str, desc: str) -> Horizontal:
        a = self.assign.get(role)
        short = {"claude": "Claude", "grok": "Grok"}  # ô chọn hẹp: tên ngắn, không xuống dòng
        clis = [(short.get(p, PROVIDERS[p][0]), p) for p in self.providers]
        if role != "lead":
            clis.append(("(không dùng)", RESET))
        p = a[0] if a else RESET
        models = self.models_of(p) if a else []
        if a and a[1] and a[1] not in models:
            models = [a[1]] + models
        effs = self.efforts_of(p) if a else []
        return Horizontal(
            Static(label, classes="ob-role"),
            Select(clis, value=p if any(p == v for _l, v in clis) else clis[0][1], allow_blank=False,
                   classes="ob-cli", id=f"ob-cli-{role}"),
            Select([(m, m) for m in models] + [("(mặc định)", RESET)], value=(a[1] if a and a[1] else RESET),
                   allow_blank=False, disabled=not a, classes="ob-model", id=f"ob-model-{role}"),
            Select([(e, e) for e in effs] + [("(mặc định)", RESET)],
                   value=(a[2] if a and a[2] in effs else RESET), allow_blank=False,
                   disabled=not (a and effs), classes="ob-effort", id=f"ob-effort-{role}"),
            Static(desc, classes="ob-desc"), classes="ob-row")

    def _step_roles(self) -> list:
        key = (tuple(self.providers), self.tier)
        if self._assign_key != key:  # đổi CLI hoặc mức chi phí: gán lại theo mặc định mới
            self.assign = {k: self._default(k) for k, _l, _d in ROLES}
            self._assign_key = key
        out = [Static("Giao từng vai trò cho CLI nào, dùng model và effort gì?", classes="ob-q"),
               Static("Cùng một CLI làm nhiều vai trò với model/effort khác nhau → ateam tự tạo thêm agent "
                      "(vd claude-review)." + ("  ⏳ đang hỏi danh sách model từ các CLI…" if self.discovering
                                               else ""), classes="ob-hint")]
        out += [self._row(k, label, desc) for k, label, desc in ROLES]
        return out

    def _step_safety(self) -> list:
        access = [("safe", "Chỉ sửa file (an toàn)", "agent không chạy lệnh shell / mạng"),
                  ("full", "Toàn quyền — chạy lệnh, mạng (lint, build, git push…)",
                   "chỉ dùng cho repo bạn tin tưởng; agent tuỳ chỉnh đổi riêng ở /custom")]
        no_git = () if self.git else ("worktree-auto", "worktree-review")
        apply = [(k, label, hint if self.git else hint + " — cần thư mục là git repo có commit")
                 for k, label, hint in self.APPLY]
        return [Static("Agent được làm gì?", classes="ob-q"),
                self._choice("ob-access", access, self.access),
                Static("Thay đổi của agent áp vào code thế nào?", classes="ob-q"),
                self._choice("ob-apply", apply, self.apply, disabled=no_git)]

    def _step_verify(self) -> list:
        words = ("test", "lint", "check", "build", "typecheck", "tsc", "vitest", "jest", "pytest")
        cmds = [c for c, _d in shell.project_scripts(self.root, recent=[])
                if any(w in c.lower() for w in words)][:8]
        items = [(c, c, "chạy sau mỗi task có sửa code; lỗi thì giao agent sửa") for c in cmds]
        if self.verify and self.verify not in cmds:
            items.insert(0, (self.verify, self.verify, "đang dùng"))
        items.append(("", "Không chạy lệnh kiểm tra", "bật sau bằng /verify <lệnh>"))
        return [Static("Lệnh kiểm tra tự chạy sau mỗi task (test, lint, build)?", classes="ob-q"),
                self._choice("ob-verify", items, self.verify),
                TextInput(self.verify if self.verify not in cmds else "",
                          placeholder="hoặc gõ lệnh khác, vd: npm run lint && npm test", id="ob-verify-input")]

    def _step_review(self) -> list:
        plan, st = self.plan(), self.settings()
        t = Text()
        t.append("Đội\n", "bold")
        for name, a in plan.agents.items():
            t.append(f"  {'★ ' if name == plan.lead else '  '}{name:18}", "bold yellow" if name == plan.lead else "bold")
            t.append(f"{PROVIDERS[a['provider']][0]:13}", "cyan")
            label = (a["model"] or "mặc định") + (f" · {a['effort']}" if a["effort"] else "")
            t.append(f"{label:30}")
            t.append(", ".join(dict((k, lbl) for k, lbl, _d in ROLES)[r].lstrip("★ ") for r in a["roles"]), "dim")
            if not a["builtin"]:
                t.append("  (agent thêm)", "green")
            t.append("\n")
        others = [n for n in self.cfg.custom_agents if n in self.cfg.agents and not load_custom()
                  .get("agents", {}).get(n, {}).get("wizard")]
        if others:
            t.append(f"  Agent tuỳ chỉnh giữ nguyên: {', '.join(others)}\n", "dim")
        style = dict((k, label) for k, label, _h in self.STYLES)[self.style]
        apply = dict((k, label) for k, label, _h in self.APPLY)[self.apply]
        t.append("\nCách làm việc\n", "bold")
        for k, v in (("Kiểu", style), ("Mức", dict(TIERS)[self.tier]),
                     ("Quyền", "toàn quyền" if st["full_access"] else "chỉ sửa file"),
                     ("Áp thay đổi", apply), ("Kiểm tra", st["verify_command"] or "không")):
            t.append(f"  {k:12}", "dim")
            t.append(v + "\n")
        if not plan.lead:
            t.append("\n⚠ Chưa có trưởng nhóm — quay lại bước Vai trò.", "bold red")
        return [Static(t)]

    # ---------------------------------------------------------------- lưu lựa chọn của bước đang mở
    def collect(self) -> str | None:
        """Đọc giá trị của bước đang mở vào self.*; trả về lỗi (chuỗi) nếu chưa hợp lệ."""
        key = self.STEPS[self.step][0]
        if key == "cli":
            chosen = list(self.query_one("#ob-cli", SelectionList).selected)
            if not chosen:
                return "Chọn ít nhất một CLI"
            self.providers = [p for p in PROVIDERS if p in chosen]
        elif key in ("style", "tier", "safety"):
            for oid, attr in (("ob-style", "style"), ("ob-tier", "tier"), ("ob-access", "access"),
                              ("ob-apply", "apply")):
                for ol in self.query(f"#{oid}"):
                    if ol.highlighted is not None:
                        opt = ol.get_option_at_index(ol.highlighted)
                        if not opt.disabled:
                            setattr(self, attr, opt.id)
        elif key == "roles":
            for k, _l, _d in ROLES:
                p = self.query_one(f"#ob-cli-{k}", Select).value
                if p == RESET:
                    self.assign[k] = None
                    continue
                m = self.query_one(f"#ob-model-{k}", Select).value
                e = self.query_one(f"#ob-effort-{k}", Select).value
                self.assign[k] = (p, "" if m == RESET else m, "" if e == RESET else e)
        elif key == "verify":
            typed = self.query_one("#ob-verify-input", Input).value.strip()
            ol = self.query_one("#ob-verify", OptionList)
            self.verify = typed or (ol.get_option_at_index(ol.highlighted).id or ""
                                    if ol.highlighted is not None else "")
        return None

    async def go(self, delta: int) -> None:
        if delta > 0:
            err = self.collect()
            if err:
                self.notify(err, severity="warning")
                return
        else:
            self.collect()
        await self.show_step(max(0, min(len(self.STEPS) - 1, self.step + delta)))

    # ---------------------------------------------------------------- sự kiện
    def on_select_changed(self, event: Select.Changed) -> None:
        """Đổi CLI của một vai trò: nạp lại model/effort của dòng đó (gợi ý theo mức chi phí)."""
        sid = event.select.id or ""
        if not sid.startswith("ob-cli-"):
            return
        role = sid[len("ob-cli-"):]
        p = event.value
        cur = self.assign.get(role)
        if p == RESET:
            self.assign[role] = None
        elif not cur or cur[0] != p:
            self.assign[role] = (p,) + tier_preset(p, self.tier, role, self.models_of(p), self.efforts_of(p))
        else:
            return
        a = self.assign[role]
        msel = self.query(f"#ob-model-{role}")
        esel = self.query(f"#ob-effort-{role}")
        if not msel or not esel:
            return
        msel, esel = msel.first(Select), esel.first(Select)
        models = self.models_of(p) if a else []
        effs = self.efforts_of(p) if a else []
        msel.set_options([(m, m) for m in models] + [("(mặc định)", RESET)])
        msel.value = a[1] if a and a[1] in models else RESET
        esel.set_options([(e, e) for e in effs] + [("(mặc định)", RESET)])
        esel.value = a[2] if a and a[2] in effs else RESET
        msel.disabled, esel.disabled = not a, not (a and effs)

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        oid = event.option_list.id
        if oid == "ob-access":  # câu hỏi thứ 2 cùng bước
            self.query_one("#ob-apply", OptionList).focus()
            return
        await self.go(1)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "ob-next":
            event.stop()
            if self.STEPS[self.step][0] == "review":
                self.action_save()
            else:
                await self.go(1)
        elif bid == "ob-back":
            event.stop()
            await self.go(-1)
        elif bid == "ob-custom":
            event.stop()
            self.app.push_screen(CustomScreen(self.root, self.cfg), self._custom_done)

    async def _custom_done(self, changed) -> None:
        if changed:
            await self.app.reload_custom()
            await self.show_step(self.step)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "ob-verify-input":
            event.stop()
            await self.go(1)

    def action_request_close(self) -> None:
        if self.step > 0:  # Esc = quay lại bước trước
            self.run_worker(self.go(-1), exclusive=True, group="ob-nav")
            return
        if time.time() - self._esc_at > 3:
            self._esc_at = time.time()
            self.notify("Esc lần nữa để thoát thiết lập (giữ cấu hình hiện tại)", severity="warning")
            return
        self.close()

    def action_save(self) -> None:
        if self.STEPS[self.step][0] != "review":
            self.collect()
        plan = self.plan()
        if not plan.lead:
            self.notify("Chưa có trưởng nhóm — chọn CLI cho vai trò ★ Trưởng nhóm", severity="error")
            return
        self.dismiss({"plan": plan, "settings": self.settings()})


# --------------------------------------------------------------------------- agent & workflow tuỳ chỉnh
FORM_CSS = """
    #{box} { width: 120; max-width: 100%; height: auto; max-height: 95%; border: round $panel-lighten-2;
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


ACCESS_CHOICES = [("sửa file", "safe"), ("toàn quyền", "full")]
ACCESS_LONG = [("Chỉ sửa file (an toàn)", "safe"),
               ("Toàn quyền — chạy lệnh, mạng (build, git push…)", "full")]


class AgentQuickScreen(BaseModal):
    """Thêm/sửa agent dựa trên một nhà cung cấp có sẵn (Claude Code, Codex, Antigravity, OpenCode):
    chỉ chọn model, effort, quyền — mọi cờ CLI lấy từ mẫu. "Nâng cao…" mở form đầy đủ (AgentEditScreen).
    Trả về (tên, thân TOML, tên cũ) hoặc None (Esc)."""

    BINDINGS = [Binding("ctrl+s", "save", "Lưu", priority=True)]
    DEFAULT_CSS = "AgentQuickScreen { align: center middle; }" + FORM_CSS.replace("{box}", "quick-box") + """
    #quick-preview { height: auto; padding: 0 1; background: $boost; margin-top: 1; }
    """

    def __init__(self, cfg: Config, name: str | None = None, raw: dict | None = None):
        super().__init__()
        self.cfg, self.old_name, self.raw = cfg, name, dict(raw or {})
        self.provider = provider_of(self.raw.get("command")) or next(
            (p for p in PROVIDERS if shutil.which(p)), "claude")

    def compose(self) -> ComposeResult:
        provs = [(label + ("" if shutil.which(p) else "  (chưa cài)"), p) for p, (label, _t) in PROVIDERS.items()]
        with Vertical(id="quick-box"):
            yield self.title_bar("Sửa agent " + self.old_name if self.old_name else "Thêm agent")
            yield Static(Text("Chọn nhà cung cấp, model, effort và quyền — cờ CLI ateam tự điền. "
                              "Ctrl+S lưu, Esc huỷ. CLI khác (Gemini, Aider, lệnh riêng): Nâng cao…", "dim"))
            yield form_row("Nhà cung cấp", Select(provs, value=self.provider, allow_blank=False, id="q-provider",
                                                  classes="f-input"), "CLI chạy agent này")
            yield form_row("Tên", TextInput(self.old_name or "", placeholder="vd: codex-nhanh",
                                            id="q-name", classes="f-input"), "chữ, số, - và _")
            yield form_row("Model", Select([("(mặc định)", RESET)], value=RESET, allow_blank=False, id="q-model",
                                           classes="f-input"), "(mặc định) = để CLI tự chọn")
            yield form_row("Effort", Select([("(mặc định)", RESET)], value=RESET, allow_blank=False,
                                            id="q-effort", classes="f-input"), "mức suy luận")
            yield form_row("Quyền", Select(ACCESS_LONG, value="full" if self.raw.get("full_access") else "safe",
                                           allow_blank=False, id="q-access", classes="f-input"),
                           "toàn quyền khi agent cần chạy lệnh")
            yield form_row("Vai trò", TextInput(str(self.raw.get("role", "")), placeholder="trưởng nhóm chia việc "
                                                "dựa vào đây", id="q-role", classes="f-input"), "tuỳ chọn")
            yield Static(id="quick-preview")
            with Horizontal(classes="f-buttons"):
                yield Btn("Nâng cao…", id="q-advanced")
                yield Btn("Huỷ", id="q-cancel")
                yield Btn("Lưu (Ctrl+S)", id="q-save", variant="primary")

    def on_mount(self) -> None:
        self._fill_choices(keep_model=str(self.raw.get("model") or ""), keep_effort=str(self.raw.get("effort") or ""))
        if not self.old_name:
            self._auto_name()
        self.query_one("#q-provider", Select).focus()
        self.call_after_refresh(self.mark_clean)

    def _models(self) -> list[str]:
        # model hỏi được từ CLI nằm ở agent có sẵn cùng lệnh; không có thì danh mục có sẵn
        same = [a for n, a in self.cfg.agents.items()
                if provider_of(a.command) == self.provider and n not in self.cfg.custom_agents]
        if same:
            return same[0].model_choices()
        return list(CATALOG.get(self.provider, {}).get("models", []))

    def _fill_choices(self, keep_model: str = "", keep_effort: str = "") -> None:
        models = self._models()
        if keep_model and keep_model not in models:
            models = [keep_model] + models
        msel = self.query_one("#q-model", Select)
        msel.set_options([(m, m) for m in models] + [("(mặc định)", RESET)])
        msel.value = keep_model or RESET
        efforts = provider_template(self.provider).get("efforts") or []
        esel = self.query_one("#q-effort", Select)
        esel.set_options([(e, e) for e in efforts] + [("(mặc định)", RESET)])
        esel.value = keep_effort if keep_effort in efforts else RESET
        esel.disabled = not efforts
        role = self.query_one("#q-role", TextInput)
        if not role.value.strip() or role.value == getattr(self, "_auto_role", None):
            self._auto_role = str(provider_template(self.provider).get("role", ""))
            role.value = self._auto_role
        self.update_preview()

    def _auto_name(self) -> None:
        name = self.query_one("#q-name", TextInput)
        if name.value.strip() and name.value != getattr(self, "_auto", None):
            return
        base = PROVIDERS[self.provider][1]
        n, i = base, 2
        while n in self.cfg.agents:
            n, i = f"{base}-{i}", i + 1
        self._auto = name.value = n

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "q-provider" and event.value in PROVIDERS and event.value != self.provider:
            self.provider = str(event.value)
            self._fill_choices()
            if not self.old_name:
                self._auto_name()
        self.update_preview()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.update_preview()

    def body(self) -> dict:
        body = provider_template(self.provider)
        for key, wid in (("model", "#q-model"), ("effort", "#q-effort")):
            v = self.query_one(wid, Select).value
            body.pop(key, None)
            if v not in (RESET, Select.BLANK, None, ""):
                body[key] = v
        role = self.query_one("#q-role", TextInput).value.strip()
        body["role"] = role
        if self.query_one("#q-access", Select).value == "full":
            body["full_access"] = True
        # dự phòng của mẫu có thể trỏ tới agent đã bị tắt/xoá: chỉ giữ agent đang có
        body["fallback"] = [f for f in body.get("fallback", []) if f in self.cfg.agents]
        return body

    def update_preview(self) -> None:
        if not self.is_mounted:
            return
        name = self.query_one("#q-name", TextInput).value.strip() or "agent"
        a = agent_from_dict(name, self.body())
        t = Text()
        t.append("Lệnh sẽ chạy: ", "bold")
        t.append(" ".join(a.argv("<prompt>")))
        t.append("\n")
        t.append(f"✓ đã cài '{a.binary}'" if a.installed() else f"✗ chưa cài '{a.binary}'",
                 "green" if a.installed() else "yellow")
        if a.full_access:
            t.append("   ⚠ toàn quyền: agent chạy được mọi lệnh trên máy, chỉ dùng với repo tin tưởng", "yellow")
        self.query_one("#quick-preview", Static).update(t)

    def validate(self) -> tuple[str, dict]:
        name = self.query_one("#q-name", TextInput).value.strip()
        if not NAME_RE.match(name) or name == LEAD_ALIAS:
            raise ValueError("Tên chỉ gồm chữ, số, - và _ (không dùng 'lead')")
        if name in self.cfg.agents and name != self.old_name:
            raise ValueError(f"Đã có agent '{name}' — chọn tên khác")
        return name, self.body()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "q-save":
            self.action_save()
        elif bid == "q-cancel":
            self.action_cancel()
        elif bid == "q-advanced":
            name = self.query_one("#q-name", TextInput).value.strip() or None

            def back(result) -> None:  # lưu ở form nâng cao = xong luôn form này
                if result:
                    self.dismiss(result)
            self.app.push_screen(AgentEditScreen(self.cfg, self.old_name, self.body(), new_name=name), back)

    def action_save(self) -> None:
        try:
            name, body = self.validate()
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        self.dismiss((name, body, self.old_name))

    def action_cancel(self) -> None:
        self.dismiss(None)


class AgentEditScreen(BaseModal):
    """Form thêm/sửa 1 agent tuỳ chỉnh. Trả về (tên, thân TOML, tên cũ) hoặc None (Esc)."""

    BINDINGS = [Binding("ctrl+s", "save", "Lưu", priority=True)]
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

    def __init__(self, cfg: Config, name: str | None = None, raw: dict | None = None,
                 new_name: str | None = None):
        super().__init__()
        self.cfg, self.old_name, self.raw = cfg, name, dict(raw or {})
        self.new_name = new_name  # tên đã gõ ở form đơn giản (mở form này bằng "Nâng cao…")
        self.templates = agent_templates()

    def compose(self) -> ComposeResult:
        with Vertical(id="agent-box"):
            yield self.title_bar("Sửa agent " + self.old_name if self.old_name else "Thêm agent tuỳ chỉnh")
            yield Static(Text("Bất kỳ CLI nào có chế độ headless (nhận prompt, in kết quả rồi thoát). "
                              "Chọn mẫu để điền sẵn, Ctrl+S lưu, Esc huỷ.", "dim"))
            with VerticalScroll(classes="f-scroll"):
                yield form_row("Mẫu", Select([(k, k) for k in self.templates], prompt="(chọn để điền sẵn)",
                                             id="ag-template", classes="f-input"),
                               "điền sẵn lệnh, cờ model/effort, cú pháp file")
                yield form_row("Tên", TextInput(self.old_name or self.new_name or "",
                                                placeholder="vd: gemini, aider-fast",
                                            id="ag-name", classes="f-input"),
                               "chữ, số, - và _")
                for fid, label, hint, _k, _t in self.FIELDS:
                    yield form_row(label, TextInput(id=f"ag-{fid}", classes="f-input"), hint)
                yield form_row("Tuỳ chọn", Horizontal(
                    Checkbox("Chạy trong terminal giả (pty)", id="ag-pty"),
                    Checkbox("Chạy lệnh kiểm tra sau task", True, id="ag-verify"),
                    Checkbox("Toàn quyền", id="ag-full"),
                    classes="f-input"), "pty cần cho CLI chỉ in khi có terminal (vd agy)")
            yield Static(id="agent-preview")
            with Horizontal(classes="f-buttons"):
                yield Btn("Huỷ", id="ag-cancel")
                yield Btn("Lưu (Ctrl+S)", id="ag-save", variant="primary")

    def on_mount(self) -> None:
        self.fill(self.raw)
        self.query_one("#ag-name" if not self.old_name else "#ag-command", Input).focus()
        self.call_after_refresh(self.mark_clean)

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
        self.query_one("#ag-full", Checkbox).value = bool(raw.get("full_access", False))
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
        if self.query_one("#ag-full", Checkbox).value:
            out["full_access"] = True
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


class WorkflowEditScreen(BaseModal):
    """Form thêm/sửa 1 workflow: danh sách bước (agent, tiêu đề, prompt, chạy sau bước nào, effort).
    Trả về (tên, thân TOML, tên cũ) hoặc None (Esc)."""

    BINDINGS = [Binding("ctrl+s", "save", "Lưu", priority=True)]
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
            yield self.title_bar("Sửa workflow " + self.old_name if self.old_name else "Thêm workflow")
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
                yield Btn("+ Thêm bước", id="wf-add")
            with Horizontal(classes="f-buttons"):
                yield Btn("Huỷ", id="wf-cancel")
                yield Btn("Lưu (Ctrl+S)", id="wf-save", variant="primary")

    async def on_mount(self) -> None:
        await self.fill(self.raw)
        self.query_one("#wf-name" if not self.old_name else "#wf-desc", Input).focus()
        self.call_after_refresh(self.mark_clean)

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
            Btn("✕", classes="step-del", id=f"wf-del-{k}"),
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


class CustomScreen(BaseModal):
    """Quản lý agent và workflow tuỳ chỉnh (/custom, hoặc nút ở màn hình thiết lập).
    Mỗi lần lưu ghi ngay vào custom.toml. Trả về True nếu có thay đổi."""

    DEFAULT_CSS = "CustomScreen { align: center middle; }" + FORM_CSS.replace("{box}", "custom-box") + """
    .c-row { height: 3; }
    .c-name { width: 22; padding: 1 0 0 1; text-style: bold; }
    .c-info { width: 1fr; height: 3; padding: 1 0 0 1; color: $text-muted;
              text-wrap: nowrap; text-overflow: ellipsis; }
    .c-row Button { margin: 1 0 0 1; }
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
            yield self.title_bar("Agent & workflow tuỳ chỉnh")
            yield Static(Text("Agent mới tham gia đội như agent có sẵn (trưởng nhóm phân việc theo vai "
                              "trò, bật/tắt ở /setup). Workflow chạy bằng /flow <tên> <mục tiêu>. "
                              f"Lưu ở {CUSTOM_FILE}", "dim"))
            with VerticalScroll(classes="f-scroll"):
                yield Static("Agent tuỳ chỉnh", classes="f-section")
                yield Vertical(id="custom-agents")
                yield Btn("+ Thêm agent", id="custom-add-agent", classes="c-add")
                yield Static("Workflow", classes="f-section")
                yield Vertical(id="custom-flows")
                yield Btn("+ Thêm workflow", id="custom-add-flow", classes="c-add")
            with Horizontal(classes="f-buttons"):
                yield Btn("Xong (Esc)", id="custom-close", variant="primary")

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
            return Btn(label, id=bid, variant=variant)

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
        if kind == "agents":  # giá trị vừa đặt trong form phải có hiệu lực, không để state.json cũ đè
            clear_agent_state(name)
            if old and old != name:
                clear_agent_state(old, keys=("enabled", "model", "effort", "role", "full_access"))
        self.changed = True
        self.notify(f"Đã lưu {'agent' if kind == 'agents' else 'workflow'} '{name}'")
        await self.refill()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "custom-close":
            self.action_close()
            return
        if bid == "custom-add-agent":
            self.app.push_screen(AgentQuickScreen(self.cfg), lambda r: self._saved("agents", r))
            return
        if bid == "custom-add-flow":
            self.app.push_screen(WorkflowEditScreen(self.cfg), lambda r: self._saved("workflows", r))
            return
        action, name = self.ids.get(bid, ("", ""))
        custom = load_custom()
        if action == "edit-agent":
            raw = (custom.get("agents") or {}).get(name, {})
            form = AgentQuickScreen if provider_of(raw.get("command")) else AgentEditScreen
            self.app.push_screen(form(self.cfg, name, raw), lambda r: self._saved("agents", r))
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

    def close(self) -> None:
        self.dismiss(self.changed)

    def action_close(self) -> None:
        self.close()


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
        self._mode = "file"  # "file": gợi ý @file · "cmd": gợi ý lệnh khi gõ / ở đầu ô · "agent": /task <agent>
        self._picked = False  # đã dùng ↑↓ chọn trong danh sách kể từ lần gõ cuối

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
        self.popup.border_subtitle = "↑↓ chọn · Tab/Enter chèn · Esc đóng"
        self._span = None

    def update_mention(self) -> None:
        """Gọi khi nội dung đổi: mở/lọc/đóng danh sách gợi ý theo chữ trước con trỏ."""
        self._picked = False
        before = self.value[:self.cursor_position]
        c = re.fullmatch(r"/(\S*)", before)
        if c and self.cursor_position == len(self.value):
            self._mode, self._span = "cmd", (0, self.cursor_position)
            self._fill_commands(c.group(1))
            return
        sh = re.fullmatch(r"!(.*)", before)
        if sh and self.cursor_position == len(self.value):
            self._mode, self._span = "shell", (0, self.cursor_position)
            self._fill_shell(sh.group(1))
            return
        cont = re.fullmatch(r"/(?:continue|tiep|c) (\S*)", before)
        if cont and self.cursor_position == len(self.value):
            self._mode, self._span = "continue", (cont.start(1), self.cursor_position)
            self._fill_continue(cont.group(1))
            return
        a = re.fullmatch(r"/(?:task|t) ([^\s:@]*)", before)
        if a and self.cursor_position == len(self.value):
            self._mode, self._span = "agent", (a.start(1), self.cursor_position)
            self._fill_agents(a.group(1))
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

    def _fill_shell(self, query: str) -> None:
        """Gợi ý cho !: lệnh gần đây, script package.json, target Makefile."""
        items = shell.project_scripts(self.root)
        q = query.strip().lower()
        found = [it for it in items if it[0].lower().startswith(q)]
        found += [it for it in items if it not in found and (q in it[0].lower() or q in it[1].lower())]
        if not found or (len(found) == 1 and found[0][0] == query.strip()):
            self.close_popup()
            return
        popup = self.popup
        popup.clear_options()
        width = min(36, max(len(c) for c, _d in found[:30]) + 2)
        room = min(90, self.app.size.width - 1) - 8
        for cmd, desc in found[:30]:
            t = Text()
            t.append(cmd.ljust(width), "bold cyan")
            t.append(desc, "dim")
            t.truncate(max(room, width), overflow="ellipsis")
            popup.add_option(Option(t, id=cmd))
        popup.highlighted = 0
        popup.border_title = "! lệnh terminal"
        popup.border_subtitle = "↑↓ chọn rồi Enter chạy · Tab chèn để sửa · Esc đóng"
        popup.display = True

    def _fill_agents(self, query: str) -> None:
        agents = self.app.cfg.active_agents()
        q = query.lower()
        found = [n for n in agents if n.lower().startswith(q)]
        found += [n for n in agents if q in n.lower() and n not in found]
        if not found or found == [query]:  # gõ đủ tên rồi: không che ô nhập nữa
            self.close_popup()
            return
        popup = self.popup
        popup.clear_options()
        width = max(len(n) for n in found) + 2
        label_w = max(len(agents[n].label()) for n in found) + 3
        room = min(90, self.app.size.width - 1) - 8  # #mention rộng 90, trừ viền, lề và thanh cuộn
        for n in found:
            a = agents[n]
            t = Text()
            t.append(n.ljust(width), "bold cyan")
            t.append(a.label().ljust(label_w), "dim")
            t.append(a.role)
            t.truncate(max(room, width), overflow="ellipsis")  # vai trò dài: cắt "…", không gãy dòng
            popup.add_option(Option(t, id=n))
        popup.highlighted = 0
        popup.border_title = "/task — chọn agent"
        popup.display = True

    def _fill_continue(self, query: str) -> None:
        """Gợi ý cho /continue: mục tiêu và thread /task đã kết thúc, mới nhất trước."""
        q = query.lower().lstrip("#")
        items = self.app.continue_candidates()
        found = [(ref, t) for ref, t in items if not q or q in ref or q in t.plain.lower()]
        if not found or [r for r, _t in found] == [q]:  # gõ đủ ref rồi: không che ô nhập nữa
            self.close_popup()
            return
        popup = self.popup
        popup.clear_options()
        room = min(90, self.app.size.width - 1) - 8
        for ref, t in found:
            t = t.copy()
            t.truncate(room, overflow="ellipsis")
            popup.add_option(Option(t, id=ref))
        popup.highlighted = 0
        popup.border_title = "/continue — chọn mục tiêu (m) hoặc thread /task (t) để tiếp tục"
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
        if self._mode == "shell":
            self.value = "!" + opt.id
            self.cursor_position = len(self.value)
            self.close_popup()
            return True
        if self._mode in ("agent", "continue"):
            self.value = self.value[:start] + opt.id + " " + self.value[end:]
            self.cursor_position = start + len(opt.id) + 1
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
            self._picked = True  # người dùng tự chọn gợi ý: Enter ở chế độ ! chạy gợi ý đó
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
        elif self.popup_open and self._mode == "shell":
            # Enter chạy đúng lệnh đã gõ; chỉ khi ô còn trống ("!") hoặc đã ↑↓ chọn thì chạy gợi ý
            if self._picked or not self.value[1:].strip():
                self.accept()
        elif self.popup_open and self.accept():
            return
        self.close_popup()
        res = self.action_submit()
        if inspect.isawaitable(res):
            await res

    def action_mention_close(self) -> None:
        if not self.popup_open and CONTINUE_RE.match(self.value):  # Esc huỷ /continue đang soạn
            self.value = ""
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
        for label, st in (("█ đang chạy", RUNNING), ("█ xong", "green"), ("█ lỗi", "red"),
                          ("▒ trưởng nhóm lập kế hoạch/review", "yellow")):
            out.append(label + "   ", st)
        return out


class GrillBar(Vertical):
    """Khung hỏi đáp (/grill): câu hỏi hiện tại của trưởng nhóm, các phương án gợi ý (bấm hoặc gõ số),
    nút chốt / để trưởng nhóm tự quyết / hỏi lại / bỏ. Câu trả lời gõ ở ô nhập chính."""

    BINDINGS = [Binding("escape", "leave", show=False)]

    def __init__(self, **kw):
        super().__init__(**kw)
        self.goal_id: int | None = None
        self.question: dict | None = None  # câu đang chờ trả lời (None: trưởng nhóm đang nghĩ / lỗi)
        self._sig: tuple = ()

    def compose(self) -> ComposeResult:
        yield Static(id="grill-head")
        yield Static(id="grill-q")
        with Horizontal(id="grill-buttons"):
            yield Btn("✓ Đủ rồi — chốt & lập kế hoạch", id="grill-done", variant="success")
            yield Btn("⏭ Để trưởng nhóm tự quyết", id="grill-skip")
            yield Btn("↻ Hỏi tiếp", id="grill-retry")
            yield Btn("✗ Bỏ mục tiêu", id="grill-cancel", variant="error")

    def update_grill(self, app: "TeamApp") -> bool:
        """Vẽ lại theo DB. Trả về True khi vừa có câu hỏi MỚI (để app báo và đưa con trỏ về ô nhập)."""
        g = app.orch.grill_active()
        if not g:
            self.goal_id, self.question, self._sig = None, None, ()
            self.display = False
            return False
        busy = g.id in app.orch.lead_busy
        q = None if busy else app.orch.grill_question(g)
        data = g.grill or {}
        qa = data.get("qa") or []
        err = "" if busy else str(data.get("error") or "")
        sig = (g.id, len(qa), q is None, err, busy, app._frame if busy else 0)
        is_new = q is not None and (self.question is None or self.goal_id != g.id
                                    or self.question.get("q") != q.get("q"))
        self.goal_id, self.question = g.id, q
        self.display = True
        if sig == self._sig:
            return False
        self._sig = sig
        n_answered = sum(1 for x in qa if x.get("a") is not None)
        head = Text()
        head.append(f"🎯 #{g.id} ", "bold")
        head.append(g.text.splitlines()[0][:160] if g.text else "")
        head.append(f"   · đã trả lời {n_answered} câu", "dim")
        others = sum(1 for x in app.db.goals() if x.status == "grilling") - 1
        if others > 0:
            head.append(f" · còn {others} mục tiêu khác đang hỏi đáp (hiện sau khi xong mục tiêu này)", "dim")
        self.query_one("#grill-head", Static).update(head)
        body = Text()
        if busy:
            body.append(f"{SPIN[app._frame]} {app.cfg.lead} đang nghĩ câu hỏi tiếp theo…", f"bold {RUNNING}")
        elif err:
            body.append(f"⚠ {err}", "bold red")
        elif q:
            body.append(f"❓ Câu {len(qa)}: ", "bold yellow")
            body.append(q.get("q", ""), "bold")
            if q.get("why"):
                body.append(f"\n   {q['why']}", "dim")
            for i, opt in enumerate(q.get("options") or [], 1):
                body.append("\n   ")
                body.append(f" {i}. {opt} ", Style(color="black", bgcolor="cyan" if opt != q.get("rec")
                                                   else "green", bold=True,
                                                   meta={"@click": f"app.grill_pick({i})"}))
                if opt == q.get("rec"):
                    body.append(" ★ khuyên dùng", "green")
            if q.get("rec") and q["rec"] not in (q.get("options") or []):
                body.append(f"\n   ★ khuyên dùng: {q['rec']}", "green")
            body.append("\n   Gõ câu trả lời ở ô dưới rồi Enter · gõ số (1, 2…) hoặc bấm để chọn phương án", "dim")
        self.query_one("#grill-q", Static).update(body)
        self.query_one("#grill-done", Button).disabled = busy
        self.query_one("#grill-skip", Button).display = q is not None
        self.query_one("#grill-retry", Button).display = not busy and q is None
        return is_new

    def action_leave(self) -> None:
        self.app.query_one("#cmd", Input).focus()


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
        with VerticalScroll(id="plan-detail-box"):
            yield Static(id="plan-detail")
        with Horizontal(id="plan-buttons"):
            yield Btn("▶ Duyệt & chạy  F2", id="plan-approve", variant="success")
            yield Btn("✎ Sửa task", id="plan-edit")
            yield Btn("⇄ Đổi agent", id="plan-assign")
            yield Btn("✗ Bỏ kế hoạch", id="plan-discard", variant="error")
        yield Static("↑↓ xem từng task · Enter: sửa nội dung · Tab: chuyển nút · Esc: về ô nhập",
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
        head.append("\n🎯 ", "")
        head.append(g.text if len(g.text) <= 300 else g.text[:299] + "…")
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
        self.show_detail(app)
        return is_new

    def show_detail(self, app: "TeamApp") -> None:
        """Ô dưới danh sách: toàn bộ nội dung task đang chọn, để duyệt mà không phải mở /edit."""
        box = self.query_one("#plan-detail", Static)
        tid = self.selected_task()
        t = app.db.task(tid) if tid is not None else None
        if not t:
            box.update(Text("(kế hoạch không có task nào)", "dim"))
            return
        a = app.cfg.agents.get(t.agent)
        text = Text()
        text.append(f"#{t.id} ", "bold")
        text.append(t.agent, "bold cyan")
        if a:
            text.append(f"  {a.label(t.model, t.effort)}", "dim")
        if t.depends_on:
            text.append(f"  ⟵ chạy sau #{', #'.join(map(str, t.depends_on))}", "dim")
        text.append("\n")
        text.append(t.title, "bold")
        for line in t.prompt.splitlines() or [""]:
            text.append("\n")
            text.append_text(md_text(line))
        box.update(text)
        self.query_one("#plan-detail-box", VerticalScroll).scroll_home(animate=False)

    def selected_task(self) -> int | None:
        ol = self.query_one("#plan-tasks", OptionList)
        if ol.highlighted is None or not ol.option_count:
            return None
        return int(ol.get_option_at_index(ol.highlighted).id)

    def action_leave(self) -> None:
        self.app.query_one("#cmd", Input).focus()


class DiffScreen(BaseModal):
    """Xem diff kiểu VS Code: danh sách file bên trái, diff của file đang chọn bên phải (hai cột hoặc
    một cột), tô màu cú pháp và chữ đổi trong dòng. Phím o mở file trong `code --diff`."""

    BINDINGS = [
        Binding("q", "close", "Đóng"),
        Binding("n,j", "move(1)", "File kế", show=False),
        Binding("p,k", "move(-1)", "File trước", show=False),
        Binding("right_square_bracket", "hunk(1)", "Đoạn kế", show=False),
        Binding("left_square_bracket", "hunk(-1)", "Đoạn trước", show=False),
        Binding("s", "toggle_split", "Đổi kiểu", show=False),
        Binding("o", "open_code", "VS Code", show=False),
        Binding("pagedown,space", "page(1)", show=False),
        Binding("pageup", "page(-1)", show=False),
    ]
    DEFAULT_CSS = """
    DiffScreen { background: $background; }
    #diff-top { height: auto; background: $boost; }
    #diff-head { width: 1fr; height: auto; padding: 0 1; }
    #diff-main { height: 1fr; }
    #diff-files { width: 30%; min-width: 24; max-width: 60; border: none; border-right: solid $primary-darken-2; }
    #diff-right { width: 1fr; }
    #diff-title { height: 1; padding: 0 1; background: $panel; }
    #diff-scroll { height: 1fr; }
    #diff-body { width: auto; min-width: 100%; }
    """

    def __init__(self, ds, has_code: bool, start: int = 0):
        super().__init__()
        self.ds = ds
        self.has_code = has_code
        self.start = start  # file chọn sẵn (mở từ một file ở tab Git)
        self.split: bool | None = None  # None = tự chọn theo bề rộng
        self._starts: list[int] = []
        self._width = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="diff-top"):
            yield Static(id="diff-head")
            yield Btn("✕ Đóng", classes="m-close")
        with Horizontal(id="diff-main"):
            yield OptionList(id="diff-files")
            with Vertical(id="diff-right"):
                yield Static(id="diff-title")
                with VerticalScroll(id="diff-scroll"):
                    yield Static(id="diff-body")

    def on_mount(self) -> None:
        ds = self.ds
        head = Text()
        head.append(f"Δ {ds.title}", "bold")
        head.append(f"   {len(ds.files)} file  ", "")
        head.append(f"+{ds.added}", "green")
        head.append(" ")
        head.append(f"−{ds.removed}", "red")
        keys = "↑↓ chọn file · ] [ đoạn kế/trước · s hai cột/một cột · PgUp/PgDn cuộn"
        keys += " · o mở VS Code" if self.has_code else ""
        task = self.app.db.task(ds.tid)
        if task and task.status in ("review", "conflict"):
            keys += " · Ctrl+Y merge"
        head.append(f"\n{keys} · Esc đóng", "dim")
        self.query_one("#diff-head", Static).update(head)
        ol = self.query_one("#diff-files", OptionList)
        for i, fd in enumerate(ds.files):
            ol.add_option(Option(diffview.file_label(fd, 40), id=str(i)))
        ol.highlighted = min(self.start, max(0, len(ds.files) - 1))
        ol.focus()
        self.call_after_refresh(self.redraw)

    @property
    def current(self):
        ol = self.query_one("#diff-files", OptionList)
        return self.ds.files[ol.highlighted or 0] if self.ds.files else None

    def is_split(self) -> bool:
        return self.split if self.split is not None else self.size.width >= 120

    def redraw(self) -> None:
        fd = self.current
        if fd is None:
            return
        scroll = self.query_one("#diff-scroll", VerticalScroll)
        width = max(40, scroll.size.width - 2)
        self._width = width
        title = Text()
        title.append(fd.status + " ", "bold " + diffview.STATUS_STYLE.get(fd.status, ""))
        if fd.status == "R" and fd.old_path != fd.path:
            title.append(f"{fd.old_path} → ", "dim")
        title.append(fd.path, "bold")
        title.append(f"   +{fd.added}", "green")
        title.append(f" −{fd.removed}", "red")
        title.append("   " + ("hai cột" if self.is_split() else "một cột"), "dim")
        self.query_one("#diff-title", Static).update(title)
        body, self._starts = diffview.render(fd, width, self.is_split())
        self.query_one("#diff-body", Static).update(body)
        scroll.scroll_home(animate=False)

    def on_resize(self, event) -> None:
        self.call_after_refresh(self.redraw)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "diff-files":
            event.stop()
            self.redraw()

    def action_close(self) -> None:
        self.dismiss(None)

    def action_move(self, delta: int) -> None:
        ol = self.query_one("#diff-files", OptionList)
        if ol.option_count:
            ol.highlighted = ((ol.highlighted or 0) + delta) % ol.option_count

    def action_toggle_split(self) -> None:
        self.split = not self.is_split()
        self.redraw()

    def action_page(self, delta: int) -> None:
        scroll = self.query_one("#diff-scroll", VerticalScroll)
        (scroll.scroll_page_down if delta > 0 else scroll.scroll_page_up)(animate=False)

    def action_hunk(self, delta: int) -> None:
        scroll = self.query_one("#diff-scroll", VerticalScroll)
        y = scroll.scroll_y
        if delta > 0:
            nxt = [s for s in self._starts if s > y + 0.5]
        else:
            nxt = [s for s in self._starts if s < y - 0.5][-1:]
        if nxt:
            scroll.scroll_to(y=nxt[0], animate=False)

    async def action_open_code(self) -> None:
        if not self.has_code:
            self.app.notify("Không thấy lệnh 'code' — trong VS Code: Shell Command: Install 'code' command",
                            severity="warning")
            return
        fd = self.current
        old, new = await self.app.orch.diff_versions(self.ds, fd)
        proc = await asyncio.create_subprocess_exec(
            "code", "--diff", str(old), str(new), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        self.app.notify(f"Đang mở {fd.path} trong VS Code…", timeout=3)
        await proc.wait()


class ConfirmScreen(BaseModal):
    """Hỏi lại trước thao tác không hoàn tác được. Trả về True (đồng ý) hoặc None."""

    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    #confirm-box { width: 70; max-width: 100%; height: auto; border: round $warning;
                   background: $surface; padding: 0 1; }
    #confirm-body { height: auto; margin: 1 0; }
    #confirm-buttons { height: auto; align: right middle; }
    #confirm-buttons Button { margin-left: 2; }
    """
    BINDINGS = [Binding("y", "yes", show=False), Binding("n", "close", show=False)]

    def __init__(self, title: str, body: str, yes: str = "Đồng ý"):
        super().__init__()
        self.title_text, self.body, self.yes = title, body, yes

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield self.title_bar(self.title_text)
            yield Static(self.body, id="confirm-body")
            with Horizontal(id="confirm-buttons"):
                yield Btn("Huỷ (n)", id="confirm-no")
                yield Btn(f"{self.yes} (y)", id="confirm-yes", variant="error")

    def on_mount(self) -> None:
        self.query_one("#confirm-no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "confirm-yes":
            self.dismiss(True)
        else:
            self.close()

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_close(self) -> None:
        self.close()


class GitFileList(OptionList):
    """Danh sách file thay đổi ở tab Git. Space stage/bỏ stage, a stage tất cả, u bỏ stage tất cả,
    x bỏ thay đổi, Enter/d xem diff."""

    BINDINGS = [
        Binding("space", "app.git_toggle", "Stage/bỏ stage", show=False),
        Binding("a", "app.git_stage_all", "Stage tất cả", show=False),
        Binding("u", "app.git_unstage_all", "Bỏ stage tất cả", show=False),
        Binding("x", "app.git_discard", "Bỏ thay đổi", show=False),
        Binding("d", "app.git_diff", "Xem diff", show=False),
        Binding("c", "app.git_focus_msg", "Commit", show=False),
    ]


class GitLogList(OptionList):
    """Lịch sử commit ở tab Git. Enter xem diff của commit, r revert."""

    BINDINGS = [
        Binding("r", "app.git_revert", "Revert", show=False),
        Binding("d", "app.git_show_commit", "Xem commit", show=False),
    ]


class GitBranchScreen(BaseModal):
    """Danh sách nhánh local + remote. Trả về (hành động, nhánh, tên mới) hoặc None."""

    DEFAULT_CSS = """
    GitBranchScreen { align: center middle; }
    #gb-box { width: 100; max-width: 100%; height: auto; max-height: 90%; border: round $panel-lighten-2;
              background: $surface; padding: 0 1; }
    #gb-list { height: auto; max-height: 20; }
    #gb-hint { height: auto; color: $text-muted; }
    #gb-name { margin-top: 1; }
    .gb-buttons { height: auto; margin-top: 1; }
    .gb-buttons Button { margin-right: 2; }
    """

    def __init__(self, branches: list, current: str):
        super().__init__()
        self.branches, self.current = branches, current

    def compose(self) -> ComposeResult:
        opts = []
        for i, b in enumerate(self.branches):
            t = Text()
            t.append("● " if b.current else "  ", "green")
            t.append(b.name, "bold green" if b.current else ("cyan" if b.remote else ""))
            if b.track:
                t.append(f" {b.track}", "yellow")
            elif b.upstream:
                t.append(f" → {b.upstream}", "dim")
            if b.name.startswith("ateam/"):
                t.append("  nhánh task của ateam", "dim")
            t.append(f"  {b.date}", "dim")
            if b.subject:
                t.append(f"  {b.subject[:60]}", "dim")
            opts.append(Option(t, id=str(i)))
        with Vertical(id="gb-box"):
            yield self.title_bar(f"⎇ Nhánh — đang ở {self.current or '(detached)'}")
            yield OptionList(*opts, id="gb-list")
            yield Static(Text("Enter: chuyển sang nhánh đang chọn (nhánh remote → tạo nhánh local theo dõi nó)"
                              " · Esc: đóng", "dim"), id="gb-hint")
            with Horizontal(classes="gb-buttons"):
                yield Btn("⎇ Chuyển sang", id="gb-checkout", variant="primary")
                yield Btn("⤵ Merge vào nhánh hiện tại", id="gb-merge")
                yield Btn("✗ Xoá", id="gb-delete", variant="error")
                yield Btn("✗ Xoá hẳn", id="gb-force", variant="error")
            yield TextInput(id="gb-name", placeholder="Tên nhánh mới, vd feature/dang-nhap (Enter để tạo từ "
                                                      "nhánh hiện tại)")
            with Horizontal(classes="gb-buttons"):
                yield Btn("＋ Tạo & chuyển sang", id="gb-create", variant="success")
                yield Btn("✎ Đổi tên nhánh đang chọn", id="gb-rename")

    def on_mount(self) -> None:
        ol = self.query_one("#gb-list", OptionList)
        if self.branches:
            ol.highlighted = 0
        ol.focus()

    def selected(self):
        ol = self.query_one("#gb-list", OptionList)
        if ol.highlighted is None or not self.branches:
            return None
        return self.branches[ol.highlighted]

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        b = self.selected()
        if b:
            self.dismiss(("checkout", b.name, ""))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._create()

    def _create(self) -> None:
        name = self.query_one("#gb-name", Input).value.strip()
        if not name:
            self.notify("Gõ tên nhánh mới trước", severity="warning")
            return
        self.dismiss(("create", name, ""))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if not bid.startswith("gb-"):
            return
        event.stop()
        if bid == "gb-create":
            self._create()
            return
        b = self.selected()
        if not b:
            self.notify("Chưa có nhánh nào", severity="warning")
            return
        if bid == "gb-rename":
            new = self.query_one("#gb-name", Input).value.strip()
            if b.remote:
                self.notify("Chỉ đổi tên được nhánh local", severity="warning")
            elif not new:
                self.notify(f"Gõ tên mới cho {b.name} vào ô bên dưới rồi bấm lại", severity="warning")
            else:
                self.dismiss(("rename", b.name, new))
            return
        if b.remote and bid not in ("gb-checkout", "gb-merge"):
            self.notify("Không xoá nhánh remote từ đây (dùng /git push origin --delete <nhánh>)",
                        severity="warning")
            return
        if b.current and bid in ("gb-merge", "gb-delete", "gb-force"):
            self.notify(f"{b.name} là nhánh hiện tại", severity="warning")
            return
        action = {"gb-checkout": "checkout", "gb-merge": "merge", "gb-delete": "delete",
                  "gb-force": "force-delete"}[bid]
        self.dismiss((action, b.name, ""))


class GitStashScreen(BaseModal):
    """Các lần stash. Trả về (hành động, ref, message) hoặc None."""

    DEFAULT_CSS = """
    GitStashScreen { align: center middle; }
    #gs-box { width: 90; max-width: 100%; height: auto; max-height: 85%; border: round $panel-lighten-2;
              background: $surface; padding: 0 1; }
    #gs-list { height: auto; max-height: 20; }
    #gs-empty { height: auto; color: $text-muted; margin: 1 0; }
    #gs-msg { margin-top: 1; }
    .gs-buttons { height: auto; margin-top: 1; }
    .gs-buttons Button { margin-right: 2; }
    """

    def __init__(self, stashes: list, dirty: bool):
        super().__init__()
        self.stashes, self.dirty_tree = stashes, dirty

    def compose(self) -> ComposeResult:
        opts = []
        for i, s in enumerate(self.stashes):
            t = Text()
            t.append(f"{s.ref}  ", "bold cyan")
            t.append(s.subject)
            t.append(f"  {s.date}", "dim")
            opts.append(Option(t, id=str(i)))
        with Vertical(id="gs-box"):
            yield self.title_bar("📦 Stash — cất tạm thay đổi chưa commit")
            yield OptionList(*opts, id="gs-list")
            yield Static("Chưa có stash nào.", id="gs-empty")
            with Horizontal(classes="gs-buttons", id="gs-row-list"):
                yield Btn("⤴ Lấy lại (pop)", id="gs-pop", variant="primary")
                yield Btn("Áp dụng, giữ stash", id="gs-apply")
                yield Btn("✗ Xoá", id="gs-drop", variant="error")
            yield TextInput(id="gs-msg", placeholder="Ghi chú cho lần cất (không bắt buộc) — Enter để cất")
            with Horizontal(classes="gs-buttons"):
                yield Btn("📦 Cất mọi thay đổi (kể cả file mới)", id="gs-push", variant="success")

    def on_mount(self) -> None:
        has = bool(self.stashes)
        self.query_one("#gs-list").display = has
        self.query_one("#gs-row-list").display = has
        self.query_one("#gs-empty").display = not has
        self.query_one("#gs-push", Button).disabled = not self.dirty_tree
        if has:
            ol = self.query_one("#gs-list", OptionList)
            ol.highlighted = 0
            ol.focus()
        else:
            self.query_one("#gs-msg", Input).focus()

    def selected(self):
        ol = self.query_one("#gs-list", OptionList)
        return self.stashes[ol.highlighted] if self.stashes and ol.highlighted is not None else None

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        s = self.selected()
        if s:
            self.dismiss(("pop", s.ref, ""))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if self.dirty_tree:
            self.dismiss(("push", "", event.value.strip()))
        else:
            self.notify("Không có thay đổi nào để cất", severity="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if not bid.startswith("gs-"):
            return
        event.stop()
        if bid == "gs-push":
            self.dismiss(("push", "", self.query_one("#gs-msg", Input).value.strip()))
            return
        s = self.selected()
        if s:
            self.dismiss((bid[3:], s.ref, ""))


# ============================================================================ app
class TeamApp(App):
    TITLE = "AI Team"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { layers: base overlay; overflow: hidden hidden; }
    /* Nút chỉ có chữ: không nền, không viền; variant phân biệt bằng màu chữ (xem Btn) */
    Button, Button:hover, Button:focus, Button.-active {
        height: 1; min-width: 0; border: none; padding: 0 1; background: transparent; tint: transparent;
        text-style: bold; color: $text; }
    Button:hover { text-style: bold underline; }
    Button:focus { text-style: bold underline; }
    Button.-primary { color: $accent; }
    Button.-success { color: $success; }
    Button.-warning { color: $warning; }
    Button.-error { color: $error; }
    Button:disabled { color: $text-disabled; text-style: none; }
    Footer { overflow: hidden hidden; }
    /* dòng đang chọn trong danh sách (wizard, gợi ý / @ !, dropdown): nền xám trung tính thay cho xanh dương
       đậm — chữ màu (xanh lá, cyan) đè lên xanh dương gần như không đọc được */
    OptionList > .option-list--option-highlighted,
    OptionList:focus > .option-list--option-highlighted {
        background: $panel-lighten-2; color: $text; text-style: bold; }
    SelectionList > .selection-list--button-highlighted,
    SelectionList:focus > .selection-list--button-highlighted { background: $panel-lighten-2; }
    #tabs { height: 1fr; }
    #tabs > ContentSwitcher { height: 1fr; }
    TabPane { padding: 0; height: 1fr; }
    #team { height: 1fr; overflow: hidden hidden; }
    #board { height: 1fr; }
    #left { width: 46%; min-width: 40; }
    #board.mid #left { width: 58%; }
    #right { width: 1fr; border-left: solid $primary-darken-2; }
    /* terminal hẹp: xếp dọc, không để cột phải chỉ còn vài ký tự (log thành chữ dọc) */
    #board.narrow { layout: vertical; }
    #board.narrow #left { width: 100%; min-width: 0; height: 45%; }
    #board.narrow #right { width: 100%; height: 1fr; border-left: none;
                           border-top: solid $primary-darken-2; }
    #agents { height: auto; padding: 0 1; background: $boost; }
    #goals { height: auto; max-height: 7; padding: 0 1; border-bottom: solid $primary-darken-3; }
    #tasks { height: 1fr; }
    #board-tools { height: 1; align: right top; display: none; }
    #term { height: 1fr; }
    #jobs-side { width: 34%; min-width: 30; max-width: 70; border-right: solid $primary-darken-2; }
    #jobs { height: 1fr; border: none; }
    #jobs-empty { height: 1fr; padding: 1 2; color: $text-muted; }
    #jobs-buttons { height: auto; }
    #jobs-buttons Button { margin-right: 1; }
    #job-view { width: 1fr; }
    #job-head { height: auto; padding: 0 1; background: $boost; }
    #job-log { height: 1fr; }
    #board-clear { margin: 0 1 0 0; }
    #git-top { height: auto; background: $boost; }
    #git-top.narrow { layout: vertical; }
    #git-top.narrow #git-head { width: 100%; }
    #git-head { width: 1fr; height: auto; padding: 0 1; }
    #git-actions { width: auto; height: auto; }
    #git-actions Button { margin-left: 1; }
    #git-main { height: 1fr; }
    #git-main.narrow { layout: vertical; }
    #git-side { width: 50%; min-width: 40; border-right: solid $primary-darken-2; }
    #git-main.narrow #git-side { width: 100%; height: 55%; border-right: none;
                                 border-bottom: solid $primary-darken-2; }
    #git-files { height: 1fr; border: none; }
    #git-empty { height: 1fr; padding: 1 2; }
    .git-row { height: auto; }
    .git-row Button { padding: 0; margin-right: 1; }
    #git-msg { margin: 0; }
    #git-amend, #git-no-verify { height: auto; border: none; padding: 0; background: transparent;
                                 margin-right: 2; }
    #git-hist { width: 1fr; }
    #git-log-title { height: 1; padding: 0 1; background: $panel; }
    #git-log { height: 1fr; border: none; }
    #git-norepo { height: 1fr; padding: 1 2; }
    #tasks-empty { height: 1fr; padding: 1 2; color: $text-muted; }
    /* cao cố định: chiều cao đổi theo từng task thì mỗi lần lướt bảng cả màn hình phải tính lại bố cục */
    #detail { height: 6; padding: 0 1; background: $boost; overflow: hidden hidden; }
    #log-tools { height: 1; align: right top; }
    #log-clear { margin: 0 1 0 0; }
    #log { height: 1fr; padding: 0 1; overflow-x: hidden; }
    #team-grid { layout: grid; grid-size: 2; grid-gutter: 0 1; height: 1fr; }
    .agentpane { border: round $panel-lighten-2; height: 1fr; }
    .agentpane.busy { border: heavy $accent; }
    .agentpane.missing { border: round $error 50%; }
    .pane-head { height: auto; padding: 0 1; background: $boost; }
    .pane-log { height: 1fr; padding: 0 1; overflow-x: hidden; }
    #timeline { height: auto; max-height: 14; padding: 0 1; border-top: solid $primary-darken-2; }
    #cmd { dock: bottom; margin: 0 0 1 0; }
    #plan { height: auto; max-height: 75%; display: none; border: round $panel-lighten-2;
            border-title-color: $warning; border-title-style: bold; padding: 0 1; background: $boost; }
    #plan:focus-within { border-title-color: $success; }
    #plan-tasks { height: auto; max-height: 10; border: none; padding: 0; background: $boost; }
    #plan-detail-box { height: auto; max-height: 10; margin-top: 1; padding: 0 1; background: $panel; }
    #plan-detail { height: auto; }
    #plan-buttons { height: auto; margin-top: 1; }
    #plan-buttons Button { margin-right: 2; }
    #plan-hint { color: $text-muted; }
    #grill { height: auto; max-height: 60%; display: none; border: round $warning;
             border-title-color: $warning; border-title-style: bold; padding: 0 1; background: $boost; }
    #grill-q { height: auto; margin-top: 1; }
    #grill-buttons { height: auto; margin-top: 1; }
    #grill-buttons Button { margin-right: 2; }
    #continue-hint { height: auto; display: none; padding: 0 1; background: $boost; }
    #mention { dock: bottom; layer: overlay; display: none; height: auto; max-height: 14;
               width: 90; max-width: 100%; margin: 0 0 4 1; border: round $panel-lighten-2;
               border-title-color: $accent; border-subtitle-color: $text-muted;
               background: $panel; }
    """
    # priority=True: phím tắt vẫn chạy khi con trỏ đang ở ô nhập (Input của Textual tự dùng
    # Ctrl+D, Ctrl+K... để sửa chữ, sẽ nuốt mất phím nếu không ưu tiên)
    BINDINGS = [
        Binding("f1", "help", "Trợ giúp", priority=True),
        Binding("ctrl+q", "quit", "Thoát", priority=True),
        Binding("ctrl+t", "toggle_tab", "Đổi tab", priority=True),
        # F2/F5 đứng trước: Ctrl+G (Go to Line) và Ctrl+R (Run Recent Command) bị terminal tích hợp
        # của VS Code/Cursor trên macOS chặn — footer hiện phím đầu tiên, phím Ctrl vẫn dùng được
        Binding("f2,ctrl+g", "approve", "Duyệt & chạy", priority=True),
        Binding("f5,ctrl+r", "retry", "Chạy lại", priority=True),
        Binding("ctrl+k", "cancel_task", "Huỷ task", priority=True),
        Binding("f6,ctrl+o", "continue", "Tiếp tục", priority=True),
        Binding("ctrl+d", "diff", "Xem diff", priority=True),
        Binding("ctrl+y", "merge", "Merge", priority=True),
        Binding("ctrl+l", "syslog", "Log hệ thống", priority=True),
    ]

    def __init__(self, root: Path, cfg: Config, db: DB, setup: bool = False):
        super().__init__()
        self.root, self.cfg, self.db = root, cfg, db
        self.start_setup = setup
        # tắt hiệu ứng chuyển động (gạch chân tab trượt, cuộn mượt): mỗi lần đổi tab/cuộn phải vẽ lại nhiều
        # khung hình — trên terminal là giật, lag
        self.animation_level = "none"
        self.orch = Orchestrator(root, cfg, db, on_event=self.on_orch_event)
        self.view_task = SYSTEM
        self.log_styler = LogStyler()  # trạng thái tô màu của log đang xem (#log)
        self.shell = shell.ShellManager(root, on_event=self.on_shell_event)  # lệnh terminal (!lệnh)
        self.view_job: int | None = None
        self.job_styler = LogStyler(task_headers=False)
        self.git = gitops.GitRepo(root)  # tab 🌿 Git
        self.git_status: gitops.RepoStatus | None = None
        self.git_commits: list = []
        self._git_loading = self._git_again = False
        self._git_at = 0.0
        self._git_ids: list = []
        self._git_log_ids: list = []
        self._git_body = ""  # phần thân commit message do trưởng nhóm viết (ô nhập chỉ một dòng)
        self._rows: dict[int, tuple] = {}
        self._loop_task: asyncio.Task | None = None
        self._frame = 0
        self._booted = False
        self._goal_status: dict[int, str] = {}  # để báo khi mục tiêu vừa kết thúc
        self._log_cut: dict[int, int] = {}  # nút Xoá log: vị trí (byte) trong file log bắt đầu hiện
        self._snap: dict | None = None  # DB đọc 1 lần cho mỗi lượt refresh_view
        self._refresh_pending = False
        self._row_timer = None  # hẹn nạp log của dòng đang chọn (lướt bảng)

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs", initial="tab-board"):
            with TabPane("📋 Bảng việc", id="tab-board"):
                with Horizontal(id="board"):
                    with Vertical(id="left"):
                        yield Static(id="agents")
                        yield Static(id="goals")
                        with Horizontal(id="board-tools"):
                            yield Btn("🗑 Dọn task đã xong", id="board-clear")
                        yield DataTable(id="tasks", cursor_type="row", zebra_stripes=True)
                        yield Static(id="tasks-empty")
                    with Vertical(id="right"):
                        yield Static(id="detail")
                        with Horizontal(id="log-tools"):
                            yield Btn("🗑 Xoá log", id="log-clear")
                        yield ReflowLog(id="log", wrap=True, markup=False, highlight=False,
                                      max_lines=5000, min_width=1)
            with TabPane("👥 Đội", id="tab-team"):
                with Vertical(id="team"):
                    with Vertical(id="team-grid"):
                        for name, a in self.cfg.agents.items():
                            if a.enabled:
                                yield AgentPane(name)
                    yield Timeline(id="timeline")
            with TabPane("💻 Terminal", id="tab-term"):
                with Horizontal(id="term"):
                    with Vertical(id="jobs-side"):
                        yield OptionList(id="jobs")
                        yield Static(id="jobs-empty")
                        with Horizontal(id="jobs-buttons"):
                            yield Btn("■ Dừng", id="job-stop", variant="error")
                            yield Btn("↻ Chạy lại", id="job-restart")
                            yield Btn("✗ Xoá", id="job-remove")
                    with Vertical(id="job-view"):
                        yield Static(id="job-head")
                        yield ReflowLog(id="job-log", wrap=True, markup=False, highlight=False,
                                      max_lines=5000, min_width=1)
            with TabPane("🌿 Git", id="tab-git"):
                with Vertical(id="git"):
                    with Horizontal(id="git-top"):
                        yield Static(id="git-head")
                        with Horizontal(id="git-actions"):
                            yield Btn("✗ Huỷ merge", id="git-abort", variant="error")
                            yield Btn("⇣ Fetch", id="git-fetch")
                            yield Btn("⬇ Pull", id="git-pull")
                            yield Btn("⬆ Push", id="git-push", variant="primary")
                            yield Btn("⎇ Nhánh", id="git-branches")
                            yield Btn("📦 Stash", id="git-stash")
                            yield Btn("⟳", id="git-refresh")
                    with Horizontal(id="git-main"):
                        with Vertical(id="git-side"):
                            yield GitFileList(id="git-files")
                            yield Static(id="git-empty")
                            with Horizontal(classes="git-row"):
                                yield Btn("± Stage", id="git-stage")
                                yield Btn("+ Tất cả", id="git-stage-all")
                                yield Btn("↺ Bỏ thay đổi", id="git-discard", variant="error")
                                yield Btn("Δ Diff", id="git-diff")
                            yield TextInput(id="git-msg", placeholder="Commit message — Enter để commit")
                            with Horizontal(classes="git-row"):
                                yield Btn("✓ Commit", id="git-commit", variant="success")
                                yield Btn("✨ Trưởng nhóm viết", id="git-ai", variant="primary")
                            with Horizontal(classes="git-row"):
                                yield Checkbox("Sửa commit trước", id="git-amend")
                                yield Checkbox("Bỏ qua hook (--no-verify)", id="git-no-verify")
                        with Vertical(id="git-hist"):
                            yield Static(id="git-log-title")
                            yield GitLogList(id="git-log")
                            with Horizontal(classes="git-row"):
                                yield Btn("Δ Xem commit", id="git-show")
                                yield Btn("↶ Revert", id="git-revert")
                                yield Btn("⎌ Bỏ commit cuối", id="git-undo", variant="warning")
                    with Vertical(id="git-norepo"):
                        yield Static(Text.assemble(
                            ("Thư mục này chưa là git repo.\n\n", "bold"),
                            "Tạo repo để theo dõi thay đổi, commit, và dùng chế độ worktree "
                            "(mỗi task một nhánh riêng).\n"))
                        yield Btn("＋ Tạo git repo (git init)", id="git-init", variant="success")
        yield GrillBar(id="grill")
        yield PlanBar(id="plan")
        yield Static(id="continue-hint")
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
        self._show_input_mode()
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
        # vừa: nới cột bảng việc để cột "Task" (quan trọng nhất) không bị đẩy mất; hẹp: xếp dọc
        board, w = self.query_one("#board"), event.size.width
        board.set_class(w < NARROW_WIDTH, "narrow")
        board.set_class(NARROW_WIDTH <= w < 140, "mid")
        self.query_one("#git-main").set_class(w < NARROW_WIDTH, "narrow")
        self.query_one("#git-top").set_class(w < 140, "narrow")

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
                for line in styled_lines(p.read_text(encoding="utf-8", errors="replace"), pane.styler)[-40:]:
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
                line = self.log_styler.style(data["line"])
                if line is not None:
                    self.query_one("#log", RichLog).write(line)
            agent = data.get("agent")
            if agent and (p := self.pane(agent)):
                line = p.styler.style(data.get("raw", data["line"]))
                if line is not None:
                    p.body.write(line)
        elif kind == "activity":
            p = self.pane(data["agent"])
            if not p:
                return
            if "start" in data:
                act = data["start"]
                p.styler = LogStyler()  # lượt chạy mới: bỏ trạng thái khối của lượt trước
                if act["task_id"]:
                    self._log_cut.pop(act["task_id"], None)  # task chạy lại: file log ghi từ đầu
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
            self.schedule_refresh()

    def clear_board(self) -> None:
        n_tasks, n_goals = self.orch.clear_finished()
        if not n_tasks and not n_goals:
            self.notify("Không có task nào đã kết thúc để dọn")
            return
        if self.view_task != SYSTEM and not self.db.task(abs(self.view_task)):
            self.show_task(SYSTEM)  # log đang xem thuộc task vừa bị dọn
        self.notify(f"🗑 Đã dọn {n_tasks} task" + (f", {n_goals} mục tiêu" if n_goals else ""))
        self.refresh_view()

    # ------------------------------------------------------------------ lệnh terminal
    def run_shell(self, cmd: str) -> None:
        cmd = cmd.strip()
        if not cmd:
            self.notify("Gõ lệnh sau dấu !, vd !yarn dev (gõ ! để xem gợi ý)", severity="warning")
            return
        job = self.shell.start(cmd)
        self.query_one("#tabs", TabbedContent).active = "tab-term"
        self.show_job(job.id)
        self.refresh_view()

    def selected_job(self) -> "shell.ShellJob | None":
        return self.shell.jobs.get(self.view_job) if self.view_job is not None else None

    def show_job(self, jid: int) -> None:
        self.view_job = jid
        log = self.query_one("#job-log", RichLog)
        log.clear()
        self.job_styler = LogStyler(task_headers=False)
        job = self.shell.jobs.get(jid)
        if job:
            for line in styled_lines("\n".join(job.lines), self.job_styler):
                log.write(line)
        self._refresh_jobs()

    def on_shell_event(self, kind: str, job, line: str) -> None:
        if kind == "line" and job.id == self.view_job:
            styled = self.job_styler.style(line)
            if styled is not None:
                self.query_one("#job-log", RichLog).write(styled)
        elif kind == "exit":
            if job.id == self.view_job:
                ok = job.status == "done"
                self.query_one("#job-log", RichLog).write(Text(
                    f"── {'✓ xong' if ok else '■ đã dừng' if job.status == 'stopped' else '✗ lỗi'}"
                    f" (mã {job.rc}) sau {fmt_dur(job.finished - job.started)} ──",
                    "green" if ok else "dim" if job.status == "stopped" else "bold red"))
            if job.status == "failed":
                self.notify(f"✗ Lệnh lỗi (mã {job.rc}): {job.cmd}", severity="warning", timeout=5)
        if kind != "line":
            self.refresh_view()

    def _job_label(self, job) -> Text:
        icon, style = {"running": (SPIN[self._frame], f"bold {RUNNING}"), "done": ("✓", "green"),
                       "failed": ("✗", "bold red"), "stopped": ("■", "dim")}[job.status]
        t = Text()
        t.append(f"{icon} ", style)
        t.append(f"#{job.id} ", "dim")
        t.append(job.cmd, "bold" if job.alive else "")
        if job.ports:
            t.append("  " + " ".join(f":{p}" for p in job.ports), "cyan")
        t.append(f"  {fmt_dur((job.finished or time.time()) - job.started)}", "dim")
        return t

    def _refresh_jobs(self) -> None:
        jobs = list(self.shell.jobs.values())
        ol = self.query_one("#jobs", OptionList)
        empty = self.query_one("#jobs-empty", Static)
        ol.display, empty.display = bool(jobs), not jobs
        self.query_one("#jobs-buttons").display = bool(jobs)
        if not jobs:
            t = Text("Chưa chạy lệnh nào.\n\n", "bold")
            t.append("Gõ ", "")
            t.append("!lệnh", "bold cyan")
            t.append(" ở ô nhập, vd ")
            t.append("!yarn dev", "bold cyan")
            t.append(".\nGõ ")
            t.append("!", "bold cyan")
            t.append(" để xem gợi ý script của dự án (package.json, Makefile, lệnh gần đây).\n\n")
            t.append("Lệnh chạy trong thư mục dự án, nhiều lệnh song song được; thoát app (Ctrl+Q) "
                     "sẽ dừng mọi lệnh đang chạy.", "dim")
            empty.update(t)
            self.query_one("#job-head", Static).update(Text("💻 Terminal", "bold"))
            return
        if self.view_job not in self.shell.jobs:
            self.view_job = jobs[-1].id
            self.show_job(self.view_job)
            return
        ids = [str(j.id) for j in jobs]
        current = [o.id for o in (ol.get_option_at_index(i) for i in range(ol.option_count))]
        if current != ids:
            ol.clear_options()
            ol.add_options([Option(self._job_label(j), id=str(j.id)) for j in jobs])
        else:
            for i, j in enumerate(jobs):
                ol.replace_option_prompt_at_index(i, self._job_label(j))
        idx = ids.index(str(self.view_job))
        if ol.highlighted != idx:
            ol.highlighted = idx
        job = self.shell.jobs[self.view_job]
        head = Text()
        head.append(f"$ {job.cmd}", "bold")
        label = {"running": ("đang chạy", RUNNING), "done": ("xong", "green"),
                 "failed": (f"lỗi (mã {job.rc})", "bold red"), "stopped": ("đã dừng", "dim")}[job.status]
        head.append(f"   {label[0]}", label[1])
        head.append(f" · {fmt_dur((job.finished or time.time()) - job.started)}", "dim")
        for p in job.ports:
            head.append("   ")
            head.append(f"http://localhost:{p}", "underline cyan")
        self.query_one("#job-head", Static).update(head)
        self.query_one("#job-stop", Button).disabled = not job.alive

    def write_sys(self, text: str) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-board"
        if self.view_task != SYSTEM:
            self.show_task(SYSTEM)
        log = self.query_one("#log", RichLog)
        for line in text.splitlines():
            log.write(line)

    # ------------------------------------------------------------------ git (tab 🌿 Git)
    def open_git_tab(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-git"
        self.run_worker(self.refresh_git(), exclusive=False)

    async def refresh_git(self) -> None:
        """Đọc lại trạng thái + lịch sử git rồi vẽ tab Git. Gọi chồng nhau thì chỉ chạy thêm 1 lượt."""
        if self._git_loading:
            self._git_again = True
            return
        self._git_loading = True
        try:
            while True:
                self._git_again = False
                st = await self.git.status()
                commits = await self.git.log(80) if st.is_repo and st.oid else []
                self.git_status, self.git_commits = st, commits
                self._git_at = time.time()
                try:
                    self._render_git()
                except Exception as e:  # không để lỗi vẽ làm treo app
                    self.log.error(f"render git: {e!r}")
                if not self._git_again:
                    break
        finally:
            self._git_loading = False

    def _git_rows(self, st) -> list[tuple[str | None, Text]]:
        """(id, dòng) cho danh sách file: tiêu đề nhóm có id None (không chọn được)."""
        rows: list[tuple[str | None, Text]] = []

        def group(title: str, files, code: str, staged: bool, style: str) -> None:
            if not files:
                return
            rows.append((None, Text(f"{title} ({len(files)})", f"bold {style}")))
            for f in files:
                icon, color = gitops.file_icon(f, staged)
                t = Text("  ")
                t.append(f"{icon} ", f"bold {color}")
                d, _, name = f.path.rpartition("/")
                t.append(name)
                if d:
                    t.append(f"  {d}", "dim")
                if f.orig:
                    t.append(f"  ← {f.orig}", "dim")
                rows.append((f"{code}\0{f.path}", t))

        group("Xung đột — sửa xong thì stage", st.conflicts, "c", False, "red")
        group("Đã stage — sẽ vào commit", st.staged, "s", True, "green")
        group("Chưa stage", st.unstaged + st.untracked, "w", False, "yellow")
        return rows

    def _render_git(self) -> None:
        st = self.git_status
        if st is None:
            return
        head = Text()
        ol = self.query_one("#git-files", GitFileList)
        empty = self.query_one("#git-empty", Static)
        self.query_one("#git-main").display = st.is_repo
        self.query_one("#git-norepo").display = not st.is_repo
        if not st.is_repo:
            head.append("🌿 Git", "bold")
            self.query_one("#git-head", Static).update(head)
            return
        head.append("⎇ ", "bold green")
        head.append(st.branch or (f"detached @ {st.oid[:8]}" if st.oid else "(chưa có commit)"), "bold green")
        if st.upstream:
            head.append(f"  → {st.upstream}", "dim")
            if st.ahead:
                head.append(f"  ↑{st.ahead} chưa push", "bold yellow")
            if st.behind:
                head.append(f"  ↓{st.behind} chưa pull", "bold cyan")
            if not st.ahead and not st.behind:
                head.append("  ✓ đồng bộ", "green")
        elif st.branch:
            head.append("  chưa có trên remote (Push để tạo)", "dim")
        if st.stashes:
            head.append(f"   📦 {st.stashes} stash", "cyan")
        if st.state:
            head.append(f"   ⚠ đang {st.state} dở", "bold red")
        self.query_one("#git-head", Static).update(head)
        self.query_one("#git-abort").display = bool(st.state)

        rows = self._git_rows(st)
        ids = [r[0] for r in rows]
        keep = None
        if ol.highlighted is not None and ol.highlighted < ol.option_count:
            keep = ol.get_option_at_index(ol.highlighted).id
        if ids != self._git_ids:
            ol.clear_options()
            ol.add_options([Option(t, id=i, disabled=i is None) for i, t in rows])
            self._git_ids = ids
            paths = [i.partition("\0")[2] if i else None for i in ids]
            if keep is not None and keep in ids:
                target = ids.index(keep)
            elif keep and keep.partition("\0")[2] in paths:
                # file vừa chuyển nhóm (stage/bỏ stage): giữ con trỏ trên chính file đó
                target = paths.index(keep.partition("\0")[2])
            else:
                target = next((n for n, i in enumerate(ids) if i is not None), None)
            if target is not None:
                ol.highlighted = target
        ol.display = bool(rows)
        empty.display = not rows
        if not rows:
            empty.update(Text("✓ Không có thay đổi nào chưa commit.", "green"))
        n_staged = len(st.staged)
        amend = self.query_one("#git-amend", Checkbox).value
        skip = " (bỏ qua hook)" if self.query_one("#git-no-verify", Checkbox).value else ""
        self.query_one("#git-msg", Input).placeholder = (
            f"Message mới cho commit trước — Enter để sửa commit{skip}" if amend else
            f"Commit message cho {n_staged} file đã stage — Enter để commit{skip}" if n_staged else
            f"Commit message (chưa stage gì: commit mọi thay đổi) — Enter để commit{skip}")

        log = self.query_one("#git-log", GitLogList)
        sigs = [c.sha for c in self.git_commits]
        if sigs != self._git_log_ids:
            keep = log.highlighted
            log.clear_options()
            for c in self.git_commits:
                t = Text()
                t.append(f"{c.short} ", "yellow")
                if c.refs:
                    t.append(f"({c.refs}) ", "bold cyan")
                t.append(c.subject)
                t.append(f"  {c.author} · {c.date}", "dim")
                log.add_option(Option(t, id=c.sha))
            self._git_log_ids = sigs
            if self.git_commits:
                log.highlighted = min(keep or 0, len(self.git_commits) - 1)
        self.query_one("#git-log-title", Static).update(
            Text(f"📜 Lịch sử ({len(self.git_commits)} commit gần nhất)", "bold") if self.git_commits
            else Text("📜 Chưa có commit nào", "bold"))

    def git_selected(self) -> tuple[str, str] | None:
        """(nhóm, đường dẫn) của file đang chọn: nhóm s = đã stage, w = chưa stage, c = xung đột."""
        ol = self.query_one("#git-files", GitFileList)
        if ol.highlighted is None or ol.highlighted >= ol.option_count:
            return None
        oid = ol.get_option_at_index(ol.highlighted).id
        if not oid:
            return None
        code, _, path = oid.partition("\0")
        return code, path

    def git_commit_selected(self):
        log = self.query_one("#git-log", GitLogList)
        if log.highlighted is None or not self.git_commits:
            return None
        return self.git_commits[min(log.highlighted, len(self.git_commits) - 1)]

    def git_do(self, make, busy_check: bool = False, then=None) -> None:
        """Chạy một thao tác git (make() trả coroutine → (ok, lời nhắn)), báo kết quả, vẽ lại tab Git.
        busy_check: thao tác đổi nhánh/HEAD — từ chối khi agent đang chạy (chúng đang sửa hoặc sắp merge
        vào nhánh hiện tại)."""
        if busy_check and self.orch.runs:
            self.notify(f"Đang có {len(self.orch.runs)} task chạy — đợi xong (hoặc Ctrl+K huỷ) rồi hẵng "
                        f"đổi nhánh/pull/stash", severity="warning", timeout=6)
            return

        async def go() -> None:
            ok, msg = await make()
            self.notify(msg, severity="information" if ok else "warning", timeout=4 if ok else 10)
            if ok and then:
                then()
            await self.refresh_git()
        self.run_worker(go(), exclusive=False)

    def action_git_toggle(self) -> None:
        sel = self.git_selected()
        if not sel:
            return
        code, path = sel
        self.git_do(lambda: self.git.unstage([path]) if code == "s" else self.git.stage([path]))

    def action_git_stage_all(self) -> None:
        self.git_do(self.git.stage_all)

    def action_git_unstage_all(self) -> None:
        self.git_do(lambda: self.git.unstage())

    def action_git_discard(self) -> None:
        sel = self.git_selected()
        if not sel:
            return
        code, path = sel
        if code != "w":
            self.notify("Chỉ bỏ được thay đổi chưa stage — bỏ stage file trước (Space)", severity="warning")
            return
        f = next((f for f in self.git_status.files if f.path == path), None) if self.git_status else None
        what = "XOÁ file chưa theo dõi" if f and f.untracked else "bỏ mọi thay đổi chưa stage của"

        def done(yes) -> None:
            if yes:
                self.git_do(lambda: self.git.discard([path]))
        self.push_screen(ConfirmScreen("↺ Bỏ thay đổi", f"{what.capitalize()} {path}?\n"
                                       "Không thể hoàn tác.", "Bỏ thay đổi"), done)

    async def action_git_diff(self) -> None:
        sel = self.git_selected()
        if not sel:
            self.notify("Chọn 1 file trong danh sách trước")
            return
        code, path = sel
        if code == "c":
            ds = diffview.DiffSet(0, f"Xung đột · {path}",
                                  diffview.parse_unified(await self.git.diff_text("HEAD", "--", path)), "HEAD", None)
        else:
            ds = await self.git.changes_diffset(staged=code == "s")
        if not ds.files:
            self.notify("Không có diff để xem", severity="warning")
            return
        idx = next((i for i, f in enumerate(ds.files) if f.path == path), 0)
        self.push_screen(DiffScreen(ds, has_code=bool(shutil.which("code")), start=idx))

    async def action_git_show_commit(self) -> None:
        c = self.git_commit_selected()
        if not c:
            return
        ds = await self.git.commit_diffset(c)
        if not ds.files:
            self.notify(f"Commit {c.short} không đổi file nào (vd commit merge)")
            return
        self.push_screen(DiffScreen(ds, has_code=bool(shutil.which("code"))))

    def action_git_revert(self) -> None:
        c = self.git_commit_selected()
        if not c:
            return

        def done(yes) -> None:
            if yes:
                self.git_do(lambda: self.git.revert(c.sha), busy_check=True)
        self.push_screen(ConfirmScreen("↶ Revert", f"Tạo commit mới đảo ngược {c.short} · {c.subject}?",
                                       "Revert"), done)

    def action_git_focus_msg(self) -> None:
        self.query_one("#git-msg", Input).focus()

    def git_commit(self, message: str | None = None, no_verify: bool | None = None) -> None:
        box = self.query_one("#git-msg", Input)
        msg = (box.value if message is None else message).strip()
        amend = self.query_one("#git-amend", Checkbox).value
        skip = self.query_one("#git-no-verify", Checkbox).value if no_verify is None else no_verify
        if not msg and not amend:
            self.notify("Gõ commit message trước (hoặc bấm ✨ để trưởng nhóm viết)", severity="warning")
            box.focus()
            return
        st = self.git_status
        all_changes = not (st and st.staged)

        def clear() -> None:
            box.value = ""
            self._git_body = ""
            self.query_one("#git-amend", Checkbox).value = False
        # ô "Bỏ qua hook" giữ nguyên sau khi commit (hook hỏng thường hỏng cho nhiều lần commit liền)
        self.git_do(lambda: self.git.commit(msg, amend=amend, all_changes=all_changes, no_verify=skip),
                    then=clear)

    async def git_ai_message(self) -> None:
        btn = self.query_one("#git-ai", Button)
        if btn.disabled:
            return
        btn.disabled = True
        self.notify(f"✨ {self.cfg.lead} đang viết commit message…")
        try:
            ok, msg = await self.orch.commit_message()
        finally:
            btn.disabled = False
        if not ok:
            self.notify(msg, severity="warning", timeout=8)
            return
        box = self.query_one("#git-msg", Input)
        # ô nhập một dòng: dòng tiêu đề + phần thân nối bằng " | " sẽ khó đọc → giữ tiêu đề, thân lưu riêng
        subject, _, body = msg.partition("\n")
        self._git_body = body.strip()
        box.value = subject.strip()
        box.focus()
        self.notify("✨ Đã điền commit message — sửa nếu cần rồi Enter để commit"
                    + (" (kèm phần mô tả trưởng nhóm viết)" if self._git_body else ""))

    def git_branches(self) -> None:
        async def go() -> None:
            branches = await self.git.branches()
            st = self.git_status or await self.git.status()
            self.push_screen(GitBranchScreen(branches, st.branch), self._git_branch_done)
        self.run_worker(go(), exclusive=False)

    def _git_branch_done(self, res) -> None:
        if not res:
            return
        action, name, new = res
        if action == "checkout":
            self.git_do(lambda: self.git.checkout(name), busy_check=True)
        elif action == "create":
            self.git_do(lambda: self.git.create_branch(name), busy_check=True)
        elif action == "merge":
            self.git_do(lambda: self.git.merge(name), busy_check=True)
        elif action == "rename":
            self.git_do(lambda: self.git.rename_branch(name, new))
        elif action == "delete":
            self.git_do(lambda: self.git.delete_branch(name))
        elif action == "force-delete":
            def done(yes) -> None:
                if yes:
                    self.git_do(lambda: self.git.delete_branch(name, force=True))
            self.push_screen(ConfirmScreen("✗ Xoá hẳn nhánh", f"Xoá nhánh {name} kể cả commit chưa merge?\n"
                                           "Các commit đó sẽ mất.", "Xoá hẳn"), done)

    def git_stash(self) -> None:
        async def go() -> None:
            stashes = await self.git.stashes()
            st = self.git_status or await self.git.status()
            self.push_screen(GitStashScreen(stashes, not st.clean), self._git_stash_done)
        self.run_worker(go(), exclusive=False)

    def _git_stash_done(self, res) -> None:
        if not res:
            return
        action, ref, msg = res
        if action == "push":
            self.git_do(lambda: self.git.stash_push(msg), busy_check=True)
        elif action in ("pop", "apply"):
            self.git_do(lambda: self.git.stash_apply(ref, pop=action == "pop"), busy_check=True)
        elif action == "drop":
            def done(yes) -> None:
                if yes:
                    self.git_do(lambda: self.git.stash_drop(ref))
            self.push_screen(ConfirmScreen("✗ Xoá stash", f"Xoá {ref}? Thay đổi trong đó sẽ mất.", "Xoá"), done)

    def git_button(self, bid: str) -> None:
        g = self.git
        if bid == "git-refresh":
            self.run_worker(self.refresh_git(), exclusive=False)
        elif bid == "git-fetch":
            self.notify("⇣ Đang fetch…", timeout=2)
            self.git_do(g.fetch)
        elif bid == "git-pull":
            self.notify("⬇ Đang pull…", timeout=2)
            self.git_do(g.pull, busy_check=True)
        elif bid == "git-push":
            self.notify("⬆ Đang push…", timeout=2)
            self.git_do(g.push)
        elif bid == "git-branches":
            self.git_branches()
        elif bid == "git-stash":
            self.git_stash()
        elif bid == "git-abort":
            self.git_do(g.abort)
        elif bid == "git-init":
            self.git_do(g.init)
        elif bid == "git-stage":
            self.action_git_toggle()
        elif bid == "git-stage-all":
            self.action_git_stage_all()
        elif bid == "git-discard":
            self.action_git_discard()
        elif bid == "git-diff":
            self.run_worker(self.action_git_diff(), exclusive=False)
        elif bid == "git-commit":
            msg = self.query_one("#git-msg", Input).value.strip()
            self.git_commit(msg + ("\n\n" + self._git_body if self._git_body and msg else ""))
        elif bid == "git-ai":
            self.run_worker(self.git_ai_message(), exclusive=False)
        elif bid == "git-show":
            self.run_worker(self.action_git_show_commit(), exclusive=False)
        elif bid == "git-revert":
            self.action_git_revert()
        elif bid == "git-undo":
            def done(yes) -> None:
                if yes:
                    self.git_do(g.reset_soft, busy_check=True)
            self.push_screen(ConfirmScreen("⎌ Bỏ commit cuối", "Bỏ commit cuối cùng, giữ nguyên thay đổi của "
                                           "nó (ở trạng thái đã stage) để sửa rồi commit lại?", "Bỏ commit"), done)

    def git_command(self, cmd: str, rest: str) -> None:
        """/git, /commit, /push, /pull, /fetch, /branch, /checkout, /stash."""
        g = self.git
        if cmd == "git":
            if not rest:
                self.open_git_tab()
                return
            # lệnh git bất kỳ (rebase, tag, cherry-pick…): chạy ở tab Terminal, xong thì đọc lại trạng thái
            self.run_shell("git " + rest)
            return
        if cmd == "commit":
            if not rest:
                self.open_git_tab()
                self.run_worker(self.git_ai_message(), exclusive=False)
                return
            self._git_body = ""
            words = rest.split()
            skip = any(w in ("--no-verify", "-n") for w in words[:1])
            msg = " ".join(words[1:]) if skip else rest
            if not msg:
                self.notify("Dùng: /commit [--no-verify] <message>", severity="warning")
                return
            self.git_commit(msg, no_verify=True if skip else None)
        elif cmd == "push":
            self.git_do(lambda: g.push(force=rest in ("-f", "--force", "force")))
        elif cmd == "pull":
            self.git_do(g.pull, busy_check=True)
        elif cmd == "fetch":
            self.git_do(g.fetch)
        elif cmd == "branch":
            if rest:
                self.git_do(lambda: g.create_branch(rest), busy_check=True)
            else:
                self.git_branches()
        elif cmd == "checkout":
            self.git_do(lambda: g.checkout(rest), busy_check=True)
        elif cmd == "stash":
            if rest in ("pop", "apply"):
                self.git_do(lambda: g.stash_apply(pop=rest == "pop"), busy_check=True)
            elif rest in ("list", "ls"):
                self.git_stash()
            else:
                self.git_do(lambda: g.stash_push(rest), busy_check=True)

    # ------------------------------------------------------------------ vẽ lại
    def busy_agents(self) -> set[str]:
        return {a for a, acts in self.orch.activity.items() if acts}

    def refresh_view(self) -> None:
        if not self._booted:
            return
        self._refresh_pending = False
        self._frame = (self._frame + 1) % len(SPIN)
        # một lần đọc DB cho cả lượt vẽ; tab đang ẩn thì không vẽ (vẽ ngay khi chuyển sang — on_tabbed…)
        self._snap = {"tasks": self.db.tasks(), "goals": self.db.goals()}
        tab = self.query_one("#tabs", TabbedContent).active
        fns = [self._refresh_goals, self._refresh_plan, self._refresh_grill]
        if tab == "tab-board":
            fns += [self._refresh_agents, self._refresh_table, self._refresh_detail]
        elif tab == "tab-team":
            fns += [self._refresh_panes, self._refresh_timeline]
        elif tab == "tab-term":
            fns += [self._refresh_jobs]
        elif tab == "tab-git" and time.time() - self._git_at > 3 and not self._git_loading:
            # thay đổi do agent/editor bên ngoài: đọc lại git status định kỳ khi đang xem tab
            self.run_worker(self.refresh_git(), exclusive=False)
        try:
            for fn in fns:
                try:
                    fn()
                except Exception as e:  # không để lỗi vẽ làm treo app
                    self.log.error(f"refresh {fn.__name__}: {e!r}")
        finally:
            self._snap = None

    def schedule_refresh(self, delay: float = 0.15) -> None:
        """Gộp nhiều sự kiện "changed" liền nhau thành một lần vẽ."""
        if not self._refresh_pending:
            self._refresh_pending = True
            self.set_timer(delay, self.refresh_view)

    def snap_tasks(self) -> list:
        return self._snap["tasks"] if self._snap else self.db.tasks()

    def snap_goals(self) -> list:
        return self._snap["goals"] if self._snap else self.db.goals()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.tabbed_content.id == "tabs":
            self.refresh_view()
            if event.pane.id == "tab-git":
                self.run_worker(self.refresh_git(), exclusive=False)

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
                t.append(f" {SPIN[self._frame]} {name}", f"bold {RUNNING}")
            else:
                t.append(f" ○ {name}", "green")
            t.append(f" ({a.label()}) ", "dim")
        if self.orch.paused:
            chunks.append(Text("  ⏸ TẠM DỪNG (/resume)", "bold yellow"))
        jobs = self.shell.running()
        if jobs:
            ports = sorted({p for j in jobs for p in j.ports})
            chunks.append(Text(f"  💻 {len(jobs)} lệnh đang chạy" + (
                " (" + ", ".join(f":{p}" for p in ports) + ")" if ports else "") + " · Ctrl+T", RUNNING))
        w = self.query_one("#agents", Static)
        set_static(w, flow_chunks(chunks, w.content_region.width))

    def _refresh_goals(self) -> None:
        all_goals = self.snap_goals()
        # 4 mục tiêu mới nhất + mọi mục tiêu chưa xong (mục tiêu cũ vừa "tiếp tục" vẫn hiện)
        keep = {g.id for g in all_goals[-4:]} | {g.id for g in all_goals if g.status not in GOAL_ENDED}
        goals = [g for g in all_goals if g.id in keep]
        prev, self._goal_status = self._goal_status, {g.id: g.status for g in all_goals}
        for g in all_goals:
            if g.status in GOAL_ENDED and prev.get(g.id, g.status) not in GOAL_ENDED:
                self.notify(f"🏁 Mục tiêu #{g.id} {GOAL_STATUS.get(g.status, (g.status,))[0]} — "
                            f"F6 hoặc bấm ↪ Tiếp tục để giao thêm việc", timeout=6)
        t = Text()
        if not goals:
            t.append("Chưa có mục tiêu. Gõ yêu cầu ở ô dưới cùng.", "dim")
        for i, g in enumerate(goals):
            label, style = GOAL_STATUS.get(g.status, (g.status, ""))
            if i:
                t.append("\n")
            busy = g.status in ("planning", "reviewing") or g.id in self.orch.lead_busy
            t.append(f"{SPIN[self._frame]} " if busy else "🎯 ", f"bold {RUNNING}" if busy else "")
            t.append(f"#{g.id} ", "bold")
            if g.workflow:
                t.append(f"⚙{g.workflow} ", "cyan")
            t.append(f"[{label}", style)
            t.append(f" · vòng {g.round}]" if g.round > 1 else "]", style)
            t.append(f" {g.text.splitlines()[0][:80] if g.text else ''}")
            if g.followups:
                t.append(f"\n   ↪ lần tiếp {len(g.followups)}: {g.followups[-1].splitlines()[0][:120]}",
                         "cyan")
            ended = g.status in GOAL_ENDED
            if ended:  # nút bấm đầu dòng riêng: không bị gãy dòng như khi nằm cuối tiêu đề dài
                t.append("\n   ")
                t.append(" ↪ Tiếp tục ", Style(color="black", bgcolor="cyan", bold=True,
                                              meta={"@click": f"app.continue_goal({g.id})"}))
            if g.summary and g.status in ("done", "incomplete", "failed", "awaiting"):
                t.append(f" {g.summary[:160]}" if ended else f"\n   ↳ {g.summary[:160]}", "dim")
            if g.status == "awaiting":
                t.append("\n   ↳ xem khung Duyệt kế hoạch phía dưới · F2 duyệt & chạy", "yellow")
            if g.status == "grilling":
                t.append("\n   ↳ trả lời câu hỏi ở khung Hỏi đáp phía dưới", "yellow")
            elif g.spec and g.status not in GOAL_ENDED:
                t.append(f"\n   📝 đã chốt yêu cầu sau {len((g.grill or {}).get('qa') or [])} câu hỏi", "dim")
        if self.query_one("#tabs", TabbedContent).active == "tab-board":
            set_static(self.query_one("#goals", Static), t)

    def _refresh_table(self) -> None:
        table = self.query_one("#tasks", DataTable)
        now = time.time()
        tasks = self.snap_tasks()
        empty = self.query_one("#tasks-empty", Static)
        table.display, empty.display = bool(tasks), not tasks
        alive = {t.id for t in tasks}
        for tid in [i for i in self._rows if i not in alive]:  # đã dọn (/clear, nút Dọn)
            table.remove_row(str(tid))
            del self._rows[tid]
        tids, gids = self.orch.finished_ids(tasks, self.snap_goals())
        tools = self.query_one("#board-tools")
        tools.display = bool(tids or gids)
        if tids or gids:
            self.query_one("#board-clear", Button).label = f"🗑 Dọn {len(tids)} task đã xong"
        if not tasks:
            t = Text()
            t.append("Chưa có task nào.\n\n", "bold")
            first = (f"chạy theo workflow '{self.cfg.default_workflow}' (/goal: trưởng nhóm)"
                     if self.cfg.default_workflow else "trưởng nhóm lập kế hoạch & chia việc")
            for keys, what in (("Gõ một mục tiêu", first),
                               ("/grill <mục tiêu>", "trưởng nhóm hỏi kỹ cho rõ rồi mới lập kế hoạch"),
                               ("/task <agent> <nội dung>", "giao tay cho 1 agent"),
                               ("/flow <tên> <mục tiêu>", "chạy theo workflow dựng sẵn"),
                               ("F1", "xem mọi lệnh & phím tắt")):
                t.append(f"  {keys:27}", "bold cyan")
                t.append(what + "\n")
            set_static(empty, t)
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
        if self.view_task == SYSTEM:
            t = Text("📜 Log hệ thống", "bold")
            t.append("  ·  chọn 1 task trong bảng để xem log riêng · Ctrl+T: tab Đội", "dim")
            set_static(d, t)
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
        if task.status not in ACTIVE:
            g = self.db.goal(task.goal_id) if task.goal_id else None
            if g is None or g.status in GOAL_ENDED:
                what = f"mục tiêu #{g.id}" if g else f"hỏi tiếp {task.agent} trong thread này"
                t.append(f"\n↪ F6: tiếp tục {what}", "dim")
        set_static(d, t)

    def _refresh_panes(self) -> None:
        now = time.time()
        tasks = self.snap_tasks()
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
                    t.append(f"\n{SPIN[self._frame]} ", f"bold {RUNNING}")
                    t.append(head[:60], "bold")
                    t.append(f"  [{act['label']}]", "cyan")
                    t.append(f"  ⏱ {fmt_dur(now - act['started'])}", RUNNING)
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
            set_static(pane.head, t)
            pane.set_class(bool(acts), "busy")
            pane.set_class(not a.installed(), "missing")

    def _refresh_grill(self) -> None:
        bar = self.query_one("#grill", GrillBar)
        was = bar.question is not None
        new = bar.update_grill(self)
        bar.border_title = "🔎 Trưởng nhóm hỏi để hiểu rõ yêu cầu"
        waiting = bar.question is not None
        if waiting != was:
            self._show_input_mode()
        if new:
            box = self.query_one("#cmd", Input)
            if self.screen is self.screen_stack[0]:
                box.focus()
            self.notify("❓ Trưởng nhóm hỏi — trả lời ở ô nhập (hoặc gõ số phương án)", timeout=5)

    def answer_grill(self, text: str) -> None:
        bar = self.query_one("#grill", GrillBar)
        q = bar.question
        opts = (q or {}).get("options") or []
        if text.strip().isdigit() and 1 <= int(text.strip()) <= len(opts):
            text = opts[int(text.strip()) - 1]  # gõ số = chọn phương án đó
        self.notify(self.orch.answer_grill(bar.goal_id, text))
        self.refresh_view()

    def action_grill_pick(self, i: int) -> None:
        self.answer_grill(str(i))

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
        if bid == "board-clear":
            event.stop()
            self.clear_board()
            return
        if bid == "log-clear":
            event.stop()
            self.clear_log()
            return
        if bid.startswith("git-"):
            event.stop()
            self.git_button(bid)
            return
        if bid.startswith("grill-"):
            event.stop()
            bar = self.query_one("#grill", GrillBar)
            o = self.orch
            if bid == "grill-done":
                self.notify(o.finish_grill(bar.goal_id))
            elif bid == "grill-skip":
                q = bar.question or {}
                self.answer_grill("(Tôi không chắc — bạn tự quyết"
                                  + (f", theo khuyến nghị: {q['rec']})" if q.get("rec") else ")"))
            elif bid == "grill-retry":
                self.notify(o.retry_grill(bar.goal_id))
            elif bid == "grill-cancel":
                self.notify(o.cancel_grill(bar.goal_id))
            self.refresh_view()
            return
        if bid.startswith("job-"):
            event.stop()
            job = self.selected_job()
            if job is None:
                return
            if bid == "job-stop" and not self.shell.stop(job):
                self.notify("Lệnh này đã dừng")
            elif bid == "job-restart":
                self.show_job(self.shell.restart(job).id)
            elif bid == "job-remove" and not self.shell.remove(job):
                self.notify("Đang chạy — Dừng trước rồi mới xoá", severity="warning")
            self.refresh_view()
            return
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

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "jobs" and event.option.id:
            event.stop()
            ol = event.option_list
            # dựng lại danh sách sinh sự kiện "chọn dòng 0" đến trễ: bỏ qua nếu không còn là dòng đang chọn
            if ol.highlighted is None or ol.get_option_at_index(ol.highlighted).id != event.option.id:
                return
            if int(event.option.id) != self.view_job:
                self.show_job(int(event.option.id))
            return
        if event.option_list.id == "plan-tasks":
            event.stop()
            self.query_one("#plan", PlanBar).show_detail(self)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "git-files":
            event.stop()
            self.run_worker(self.action_git_diff(), exclusive=False)
            return
        if event.option_list.id == "git-log":
            event.stop()
            self.run_worker(self.action_git_show_commit(), exclusive=False)
            return
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
        set_static(tl, tl.build(self))

    def show_task(self, tid: int) -> None:
        self.view_task = tid
        log = self.query_one("#log", RichLog)
        log.clear()
        self.log_styler = LogStyler()
        path = self._log_file(tid)
        if path.exists():
            cut = self._log_cut.get(tid, 0)
            text = read_log_tail(path, cut)
            if cut:
                log.write(Text("🗑 Đã xoá log cũ — chỉ hiện dòng mới", "dim italic"))
            for line in styled_lines(text, self.log_styler)[-LOG_SHOW_LINES:]:
                log.write(line)
        elif tid != SYSTEM:
            log.write("(task chưa chạy — chưa có log)")
        if self._booted:
            self._refresh_detail()

    def _log_file(self, tid: int) -> Path:
        return (self.orch.logs / "system.log") if tid == SYSTEM else self.orch.log_path(tid)

    def clear_log(self) -> None:
        """Nút 🗑 Xoá log: ẩn log đang xem (chỉ hiện dòng mới). File log trên đĩa giữ nguyên, vì task
        đang chạy vẫn ghi vào nó và /retry, review cần đọc lại."""
        path = self._log_file(self.view_task)
        self._log_cut[self.view_task] = path.stat().st_size if path.exists() else 0
        self.show_task(self.view_task)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        # giữ ↑↓ để lướt bảng: chỉ nạp log của dòng dừng lại (đọc + tô màu log mỗi dòng lướt qua rất chậm)
        if event.row_key and event.row_key.value:
            tid = int(event.row_key.value)
            if tid != self.view_task:
                self.view_task = tid  # phím tắt (F5, Ctrl+D, F6…) dùng ngay dòng đang chọn
                self._refresh_detail()
                if self._row_timer is not None:
                    self._row_timer.stop()
                self._row_timer = self.set_timer(0.12, lambda: self._show_selected(tid))

    def _show_selected(self, tid: int) -> None:
        self._row_timer = None
        if self.view_task == tid:
            self.show_task(tid)

    def selected_task(self) -> int | None:
        if self.view_task == SYSTEM:
            return None
        return abs(self.view_task)

    async def show_diff(self, tid: int) -> None:
        """Mở màn hình xem diff của task (Ctrl+D, /diff N)."""
        ds = await self.orch.diff_files(tid)
        if isinstance(ds, str):
            self.notify(ds, severity="warning")
            return
        self.query_one("#tabs", TabbedContent).active = "tab-board"
        if self.view_task != tid:
            self.show_task(tid)  # task đang chọn = task đang xem diff (Ctrl+Y merge đúng task)
        self.push_screen(DiffScreen(ds, has_code=bool(shutil.which("code"))))

    # ------------------------------------------------------------------ phím tắt
    def action_help(self) -> None:
        if isinstance(self.screen, HelpScreen):  # F1 lần nữa = đóng
            self.screen.dismiss(None)
        else:
            self.push_screen(HelpScreen())

    def action_toggle_tab(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        order = ["tab-board", "tab-team", "tab-term", "tab-git"]
        tabs.active = order[(order.index(tabs.active) + 1) % len(order)] if tabs.active in order else order[0]
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
        if isinstance(self.screen, DiffScreen):  # Ctrl+D lần nữa = đóng
            self.screen.dismiss(None)
            return
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
        if isinstance(self.screen, DiffScreen):  # duyệt xong từ màn hình diff
            self.screen.dismiss(None)
        self.refresh_view()

    def action_syslog(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-board"
        self.show_task(SYSTEM)

    async def action_quit(self) -> None:
        self.shell.stop_all()  # không để lại dev server mồ côi sau khi thoát
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
            self._update_continue_hint(event.value)

    # ------------------------------------------------------------------ tiếp tục mục tiêu / thread
    def continue_candidates(self) -> list[tuple[str, Text]]:
        """(ref, dòng hiển thị) cho gợi ý /continue: mục tiêu đã kết thúc rồi thread /task đã xong."""
        out: list[tuple[str, Text]] = []
        for g in reversed(self.db.goals()):
            if g.status not in GOAL_ENDED:
                continue
            label, style = GOAL_STATUS.get(g.status, (g.status, ""))
            t = Text()
            t.append("🎯 ")
            t.append(f"m{g.id}".ljust(6), "bold cyan")
            t.append(f"{label:11}", style)
            t.append(g.text.splitlines()[0] if g.text else "")
            if g.summary:
                t.append(f" — {g.summary.splitlines()[0]}", "dim")
            out.append((f"m{g.id}", t))
            if len(out) >= 10:
                break
        tasks = self.db.tasks()
        has_next = {t.parent_id for t in tasks if t.source == "followup" and t.goal_id is None}
        n = 0
        for task in reversed(tasks):
            if task.goal_id is not None or task.status in ACTIVE or task.id in has_next:
                continue
            label, style = STATUS.get(task.status, (task.status, ""))
            t = Text()
            t.append("💬 ")
            t.append(f"t{task.id}".ljust(6), "bold cyan")
            t.append(f"{task.agent} ", "cyan")
            t.append(f"{STATUS_ICON.get(task.status, '·')} ", style)
            t.append(task.title)
            out.append((f"t{task.id}", t))
            n += 1
            if n >= 10:
                break
        return out

    def continue_hint(self, ref: str) -> Text:
        """Dòng giải thích /continue <ref> sẽ làm gì (hoặc vì sao chưa được)."""
        r = self.orch.continue_ref(ref)
        if isinstance(r, str):
            return Text(f"⚠ {r}", "yellow")
        kind, i = r
        t = Text()
        if kind == "goal":
            g = self.db.goal(i)
            if g.status not in GOAL_ENDED:
                return Text(f"⚠ Mục tiêu #{i} chưa kết thúc — đợi xong rồi tiếp tục", "yellow")
            n = len(self.db.tasks(goal_id=i))
            t.append(f"↪ Tiếp tục mục tiêu #{i} ", "bold")
            t.append(f"«{g.text.splitlines()[0][:60]}»", "cyan")
            t.append(f" — trưởng nhóm lập task bổ sung dựa trên {n} task đã làm", "")
        else:
            task = self.db.task(i)
            if task.status in ACTIVE:
                return Text(f"⚠ Task #{i} chưa xong (hoặc đang chờ duyệt) — đợi xong rồi tiếp tục",
                            "yellow")
            turns = len(self.orch.thread_of(task)) + 1
            t.append(f"↪ Hỏi tiếp {task.agent} ", "bold")
            t.append(f"«{task.title[:60]}»", "cyan")
            t.append(f" — kèm {turns} lượt trước của thread", "")
        t.append("  (gõ yêu cầu mới rồi Enter, Esc huỷ)", "dim")
        return t

    def _update_continue_hint(self, value: str) -> None:
        hint = self.query_one("#continue-hint", Static)
        m = CONTINUE_RE.match(value)
        hint.display = bool(m)
        if m:
            hint.update(self.continue_hint(m.group(1)))

    def prefill_continue(self, ref: str) -> None:
        """Điền '/continue <ref> ' vào ô nhập để người dùng gõ tiếp yêu cầu mới."""
        self.query_one("#tabs", TabbedContent).active = "tab-board"
        inp = self.query_one("#cmd", CommandInput)
        inp.value = f"/continue {ref} "
        inp.cursor_position = len(inp.value)
        inp.close_popup()
        inp.focus()

    def action_continue(self) -> None:
        """F6: tiếp tục mục tiêu của task đang chọn / thread /task đó / mục tiêu xong gần nhất."""
        tid = self.selected_task()
        task = self.db.task(tid) if tid else None
        if task:
            ref = f"m{task.goal_id}" if task.goal_id and self.db.goal(task.goal_id) else f"t{task.id}"
        else:
            ended = [g for g in self.db.goals() if g.status in GOAL_ENDED]
            if not ended:
                self.notify("Chưa có mục tiêu nào đã xong để tiếp tục — chọn 1 task trong bảng",
                            severity="warning")
                return
            ref = f"m{ended[-1].id}"
        self.prefill_continue(ref)

    def action_continue_goal(self, gid: int) -> None:
        """Nút "↪ Tiếp tục" trong khung mục tiêu."""
        self.prefill_continue(f"m{gid}")

    def start_goal(self, text: str, workflow: str = "") -> None:
        """Mục tiêu mới: theo workflow (nếu có) hoặc để trưởng nhóm lập kế hoạch."""
        if workflow:
            res = self.orch.run_workflow(workflow, text)
            if isinstance(res, str):
                self.notify(res, severity="warning")
                return
        else:
            if not self.cfg.agents.get(self.cfg.lead):
                self.notify(f"Không có trưởng nhóm '{self.cfg.lead}' trong cấu hình", severity="error")
                return
            self.orch.new_goal(text)
        self.show_task(SYSTEM)

    def _show_input_mode(self) -> None:
        """Ô nhập cho biết gõ mục tiêu sẽ đi đâu: workflow mặc định hay trưởng nhóm."""
        wf = self.cfg.default_workflow
        if self.query_one("#grill", GrillBar).question is not None:
            self.query_one("#cmd", Input).placeholder = (
                "Trả lời câu hỏi của trưởng nhóm (Enter) · gõ số để chọn phương án · /grill xong để chốt")
            return
        self.query_one("#cmd", Input).placeholder = (
            f"Nhập mục tiêu (chạy theo workflow '{wf}') · /goal: trưởng nhóm lập kế hoạch · /help · @ nhắc file"
            if wf else "Nhập mục tiêu cho trưởng nhóm, /help, hoặc @ để nhắc file")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "git-no-verify":
            event.stop()
            self._render_git()
            return
        if event.checkbox.id != "git-amend":
            return
        event.stop()
        if event.value:
            async def fill() -> None:
                box = self.query_one("#git-msg", Input)
                if not box.value.strip():
                    subject, _, body = (await self.git.last_message()).partition("\n")
                    box.value, self._git_body = subject.strip(), body.strip()
            self.run_worker(fill(), exclusive=False)
        self._render_git()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "git-msg":
            event.stop()
            self.git_button("git-commit")
            return
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        if text.startswith("!"):  # lệnh terminal: !yarn dev
            self.run_shell(text[1:])
            return
        if not text.startswith("/") and self.query_one("#grill", GrillBar).question is not None:
            self.answer_grill(text)  # đang hỏi đáp: câu gõ vào là câu trả lời
            return
        if not text.startswith("/"):
            self.start_goal(text, self.cfg.default_workflow)
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

    async def _cli_usage(self) -> None:
        """Hỏi song song hạn mức của từng agent bằng chính CLI của nó, in vào log hệ thống khi xong."""
        names = list(self.cfg.active_agents())
        self.write_sys(f"\nĐang hỏi hạn mức từ CLI của {', '.join(names)}…")

        def done(name: str, cmd: str, lines: list[str]) -> None:
            self.write_sys(f"\n📊 {name}" + (f"  ({cmd})" if cmd else "") + "\n"
                           + "\n".join("  " + ln for ln in lines))
        await self.orch.usage_all(names, on_done=done)

    async def _self_update(self) -> None:
        self.notify("Đang kiểm tra bản mới…", timeout=3)
        ok, msg = await update.run_update(lambda line: self.orch.log("  " + line))
        self.orch.log(("✓ " if ok else "ℹ ") + msg)
        self.notify(msg, severity="information" if ok else "warning", timeout=12)
        self.show_task(SYSTEM)

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
        self.push_screen(OnboardScreen(self.root, self.cfg, self.orch), self._setup_done)

    async def _setup_done(self, result) -> None:
        if result is None:
            mark_setup_done()
            self.orch.log("ℹ Bỏ qua thiết lập. Mở lại bất cứ lúc nào bằng /setup (hoặc `ateam setup`).")
            return
        save_onboard(self.root, result["plan"], **result["settings"])
        await self.reload_custom()  # agent thêm (vd claude-review) và workflow mới
        fresh = load_config(self.root)
        c = self.cfg
        c.lead, c.default_workflow = fresh.lead, fresh.default_workflow
        c.approve_plan, c.auto_review, c.merge = fresh.approve_plan, fresh.auto_review, fresh.merge
        c.verify.command = fresh.verify.command
        for n, a in c.agents.items():
            f = fresh.agents.get(n)
            if f:
                a.enabled, a.model, a.effort, a.role = f.enabled, f.model, f.effort, f.role
                a.full_access = f.full_access
        if c.isolation != fresh.isolation:
            c.isolation = fresh.isolation
            await self.orch.apply_isolation()
        await self._rebuild_panes()
        self._show_input_mode()
        on = [f"{n} ({a.label()})" for n, a in c.active_agents().items()]
        flow = (f" Gõ mục tiêu → workflow '{c.default_workflow}' (/goal: trưởng nhóm lập kế hoạch)."
                if c.default_workflow else "")
        self.orch.log(f"⚙ Đã lưu thiết lập. Trưởng nhóm: {c.lead}. Đội: {', '.join(on)}.{flow} "
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
        self.cfg.default_workflow = fresh.default_workflow  # workflow mặc định vừa bị xoá -> bỏ
        self._show_input_mode()
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
            self.run_worker(self._cli_usage(), exclusive=True, group="cli-usage")
        elif cmd == "update":
            self.run_worker(self._self_update(), exclusive=True, group="self-update")
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
        elif cmd == "clear":
            self.clear_board()
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
        elif cmd == "goal":
            self.start_goal(rest.strip())
        elif cmd in ("grill", "grill-me", "hoi"):
            sub = rest.strip().lower()
            if sub in ("xong", "done", "chot", "chốt"):
                self.notify(o.finish_grill(None))
            elif sub in ("bỏ", "bo", "huỷ", "huy", "cancel"):
                self.notify(o.cancel_grill(None))
            elif sub in ("tiếp", "tiep", "retry"):
                self.notify(o.retry_grill(None))
            elif not self.cfg.agents.get(self.cfg.lead):
                self.notify(f"Không có trưởng nhóm '{self.cfg.lead}' trong cấu hình", severity="error")
                return
            else:
                o.start_grill(rest.strip())
                self.show_task(SYSTEM)
        elif cmd in ("continue", "tiep", "c"):
            ref, _, req = rest.partition(" ")
            if not req.strip():  # mới có ref: điền sẵn để gõ tiếp yêu cầu
                self.prefill_continue(ref)
                return
            res = o.continue_any(ref, req)
            if isinstance(res, str):
                self.notify(res, severity="warning")
                return
            kind, i = res
            if kind == "goal":
                self.notify(f"↪ Trưởng nhóm đang lập kế hoạch tiếp cho mục tiêu #{i}")
                self.show_task(SYSTEM)
            else:
                self.notify(f"↪ Task #{i}: hỏi tiếp {self.db.task(i).agent}")
                self.show_task(i)
        elif cmd == "sh":
            self.run_shell(rest)
        elif cmd == "stop":
            job = self.shell.jobs.get(num(rest)) if rest.strip() else self.selected_job()
            if not job or not self.shell.stop(job):
                self.notify("Không có lệnh nào đang chạy để dừng", severity="warning")
            else:
                self.notify(f"■ Đã dừng: {job.cmd}")
        elif cmd == "term":
            self.query_one("#tabs", TabbedContent).active = "tab-term"
            self.refresh_view()
        elif cmd in ("git", "commit", "push", "pull", "fetch", "branch", "checkout", "stash"):
            self.git_command(cmd, rest)
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
