"""Giao diện terminal (Textual): tab Bảng việc + tab Agents (log từng agent & timeline)."""

from __future__ import annotations

import asyncio
import contextlib
import difflib
import inspect
import json
import os
import re
import shlex
import shutil
import signal
import time
import unicodedata
from collections import deque
from functools import partial
from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.geometry import Size
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import (Button, Checkbox, DataTable, Footer, Header, Input, OptionList,
                             RichLog, Select, SelectionList, Static, TabbedContent, TabPane, TextArea)
from textual.widgets.selection_list import Selection
from textual.widgets.option_list import Option

from . import (clipboard, diffview, editor, gitops, mentions, notify, palette, projects, reports, rules, search,
               shell, theme, todos, update, wizard)
from .reports import fmt_dur, fmt_tokens, today_start  # noqa: F401 (test và code cũ import từ tui)
from .config import (CUSTOM_FILE, INSTALL_HINTS, LEAD_ALIAS, PROVIDERS, ROLES, TIERS,
                     WIZARD_FLOW, WORKFLOW_TEMPLATES, AgentConfig, Config, TeamPlan,
                     full_access_supported, plan_team, provider_of, provider_template, save_onboard,
                     tier_preset, agent_from_dict, agent_templates,
                     clear_agent_state, found_models, load_config, load_custom, load_state, mark_setup_done,
                     save_commit_agent, save_custom_item, save_state,
                     save_project_setting, workflow_to_dict)
from .db import ACTIVE, ASKING, DB, GOAL_ENDED
from .orchestrator import CHAT, SYSTEM, Orchestrator
from .grid import GridHub
from . import vterm
from .logtail import LOG_TAIL_BYTES, read_log_tail  # noqa: F401 (test import từ tui)
from .i18n import LANG_NAMES, LANGS, get_lang, normalize, save_lang, tr

# Màu trạng thái lấy từ theme đang dùng (apply_palette, gọi khi khởi động và khi đổi theme). Mặc định
# "đang chạy" là xanh dương: magenta trước đây bị Terminal.app (256 màu) vẽ gần như đỏ, dễ nhầm với lỗi.
# 16 màu ANSI chuẩn (green, yellow…) Textual tự đổi theo nền sáng/tối.
RUNNING = "dodger_blue1"
STATUS: dict[str, tuple[str, str]] = {}
BAR_STYLE: dict[str, str] = {}
GOAL_STATUS: dict[str, tuple[str, str]] = {}
STATUS_ICON = {"draft": "✎", "queued": "◌", "done": "✓", "failed": "✗", "cancelled": "–",
               "blocked": "⊘", "conflict": "≠", "review": "◆", "asking": "?"}  # running: dùng SPIN


PAL: dict[str, str] = {}  # màu ngữ nghĩa của theme hiện tại (theme.palette)


def apply_palette(pal: dict[str, str]) -> None:
    """Dựng lại bảng màu trạng thái theo theme (pal: running/ok/warn/err/info, xem theme.palette)."""
    global RUNNING
    RUNNING = pal["running"]
    PAL.clear()
    PAL.update(pal)
    ok, warn, err, info = pal["ok"], pal["warn"], pal["err"], pal["info"]
    STATUS.clear()
    STATUS.update({
        "draft": (tr("nháp"), warn),
        "queued": (tr("chờ"), info),
        "running": (tr("đang chạy"), f"bold {RUNNING}"),
        "done": (tr("xong"), ok),
        "failed": (tr("lỗi"), f"bold {err}"),
        "cancelled": (tr("đã huỷ"), "dim"),
        "blocked": (tr("bị chặn"), err),
        "conflict": (tr("xung đột"), f"bold {warn}"),
        "review": (tr("chờ duyệt"), f"bold {warn}"),
        "asking": (tr("đang hỏi bạn"), f"bold {warn}"),
    })
    BAR_STYLE.clear()
    BAR_STYLE.update({"running": RUNNING, "done": ok, "failed": err, "cancelled": "grey50",
                      "blocked": err, "conflict": warn, "review": warn, "asking": warn})
    GOAL_STATUS.clear()
    GOAL_STATUS.update({
        "planning": (tr("đang lập kế hoạch"), RUNNING),
        "awaiting": (tr("chờ duyệt (F2)"), warn),
        "grilling": (tr("đang hỏi bạn"), warn),
        "cancelled": (tr("đã bỏ"), "dim"),
        "running": (tr("đang làm"), info),
        "reviewing": (tr("đang review"), RUNNING),
        "done": (tr("hoàn thành"), ok),
        "incomplete": (tr("chưa xong"), warn),
        "failed": (tr("lỗi"), err),
    })


apply_palette(theme.palette(None))
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
NARROW_WIDTH = 110  # terminal hẹp hơn: bảng việc và log xếp dọc thay vì hai cột
# ô nhập đang ở "/continue <ref> …" (ref = m12 / t40), nhóm 1 = ref
CONTINUE_RE = re.compile(r"/(?:continue|tiep|c) (\S+) ")
SILENT_WARN = 60  # giây không có output -> cảnh báo "im lặng"
PANE_MODELS = 5   # số model gợi ý hiện trong ô agent (đủ xem bằng /models <agent>)
RESET = "\x00reset"  # lựa chọn "quay về mặc định" trong bảng chọn

HELP = tr("""\
Gõ một câu bình thường  → giao MỤC TIÊU cho trưởng nhóm lập kế hoạch & chia việc
                          (hoặc chạy theo workflow mặc định: F4 / nút bên trái ô nhập để chọn).

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
  /plan [mục tiêu]                  xem lại kế hoạch kể cả khi đã duyệt / xong (nút 📋 ở thẻ mục tiêu trên web)
  /continue <m12|t40> <yêu cầu>     tiếp tục mục tiêu (m) hoặc thread /task (t) đã xong: trưởng nhóm
                                    lập task bổ sung dựa trên việc đã làm / agent nhận kèm các lượt trước.
                                    F6 (Ctrl+O) với task đang chọn, hoặc bấm "↪ Tiếp tục" ở khung mục tiêu
  /note <nội dung>                  ghi chú chung cho cả đội
  /chat <agent> [tin]               chat trực tiếp với 1 agent, giữ phiên CLI (ô 💬 ở tab Agents; /new: cuộc
                                    mới · /term: mở CLI thật của agent tiếp tục phiên đó)
  F7   /focus [agent]               phóng to 1 agent (chat riêng, cả màn hình); F7 / Esc thu lại

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
  /model <agent>   /effort <agent>  mở bảng chọn từ danh sách agent hỗ trợ (hoặc bấm vào ô agent ở tab Agents)
  /model <agent> -                  quay về mặc định trong config (tương tự /effort <agent> -)
  /models [agent]                   xem model & effort mỗi agent hỗ trợ
  /models <agent> làm mới           hỏi CLI danh sách model thật (opencode models, agy models)
  /agents                           xem model, effort, mức effort hợp lệ của từng agent
  /setup                            mở lại màn hình thiết lập: bật/tắt agent, trưởng nhóm, model, effort
  /roles                            sửa nhanh vai trò · CLI · model · effort (không đi lại cả /setup)
  /theme [tên] [màu nhấn]           chọn theme màu (xem trước trực tiếp), vd /theme nord tím
  /lang en|vi                       đổi ngôn ngữ giao diện (app tự mở lại)
  /open [thư mục]                   mở folder / dự án khác: dự án gần đây, hoặc gõ đường dẫn (Tab gợi ý)
  /rules [rule mới]                 rule của dự án mọi agent phải tuân theo (ateam gửi kèm mọi prompt): thêm,
                                    sửa, bật/tắt, chỉ cho vài agent / vai trò; xem AGENTS.md, CLAUDE.md có sẵn

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
  /todo [việc cần làm]              tab ✅ To-do: việc riêng dự án, hiểu #tag !cao @mai 17:00 (lưu ngoài repo)
  /notes [tiêu đề]   /tags          tab 🗒 Ghi chú (markdown, tự lưu) / quản lý tag dùng chung
  /clear                            dọn task & mục tiêu đã kết thúc khỏi bảng (nút 🗑 trên bảng)
  /compact [trọng tâm]              trưởng nhóm tóm tắt ghi chú, mục tiêu & log cho prompt sau gọn hơn
  /init [trọng tâm]                 trưởng nhóm tìm hiểu dự án 1 lần, viết .ateam/project.md gửi kèm mọi kế
                                    hoạch & task để agent đỡ đọc lại code (gõ lại để cập nhật)
  /log <task>   /log sys            xem log 1 task / log hệ thống (Ctrl+L)
  /team  /board  /term  /git  /code chuyển tab Agents / Bảng việc / Terminal / Git / Code (Ctrl+T xoay vòng)
  /grid [agent]                     tab 🔲 Lưới: mỗi ô là CLI thật của một agent (F10 sắp xếp, kéo tiêu đề đổi chỗ)
  Alt+1 … Alt+9, Alt+0              tới thẳng tab theo thứ tự (Mac: bật "Use Option as Meta" trong terminal)

Lệnh terminal (tab 💻 Terminal):
  !<lệnh>                           chạy lệnh trong thư mục dự án, vd !yarn dev, !make test
  !                                 gợi ý script package.json, target Makefile, lệnh gần đây (Enter chạy)
  /sh <lệnh>                        như !<lệnh>
  /stop [số]                        dừng lệnh đang chọn (nút ■ Dừng / ↻ Chạy lại / ✗ Xoá trong tab)

Git (tab 🌿 Git — Ctrl+T xoay tới, hoặc /git):
  /git                              mở tab Git: file thay đổi, commit, nhánh, lịch sử, stash, pull/push
                                    trong danh sách file: Space stage/bỏ stage · a stage tất cả · u bỏ stage
                                    tất cả · x bỏ thay đổi · X bỏ tất cả · Enter/d xem diff · c tới ô commit
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

Xem & sửa code (tab 📝 Code — Ctrl+T xoay tới, hoặc /code):
  Ctrl+P                            command palette: mở nhanh file (file gần đây trước); gõ > lệnh,
                                    @ symbol (hàm, class, heading), :số tới dòng, /chữ tìm trong file.
                                    F8 = lệnh, F9 = symbol (web: ⌘⇧P, ⌘⇧O). Lệnh: lưu tất cả, file mới,
                                    đổi tên, xoá vào Thùng rác, xuống dòng mềm, xem diff git, mở VS Code,
                                    hỏi / giao task cho agent về file hoặc đoạn đang chọn
  /code [@file[:dòng]]              mở file trong editor (trống: mở tab, gõ để lọc file bên trái);
                                    /edit @file cũng được
                                    phím e ở tab Git (file đang chọn) / màn hình diff (đúng đoạn đang xem)
  /search [từ khoá]   F3             tìm & thay trong toàn dự án như VS Code: Aa / nguyên từ / regex, lọc file,
                                    xem trước chữ thay; Enter mở file đúng chỗ · r thay trong file · Ctrl+R thay tất cả
  phím vim                          i a I A o O sửa · Esc về normal · h j k l w b e 0 ^ $ gg G Ctrl+D/U
                                    x dd D dw cw cc yy p P J r u Ctrl+R · v V chọn · / ? n N * tìm
                                    :w lưu · :q đóng · :wq · :q! bỏ thay đổi · :e! nạp lại · :<số> tới dòng
                                    :bn :bp đổi file · :files ẩn/hiện danh sách · số đếm: 5j, 3dd, 2dw
  /vim off   /vim on                tắt phím vim (sửa như editor thường, Ctrl+S lưu) / bật lại
                                    file bị agent sửa trong lúc mở: tự nạp lại nếu bạn chưa sửa, không thì
                                    báo để :e! hoặc :w! (ghi đè); file > 2 MB tắt tô màu, > 5 MB chỉ đọc

Trợ giúp & thoát:
  /help                             trợ giúp này (F1)
  F2 = Ctrl+G, F5 = Ctrl+R, F6 = Ctrl+O   dùng F2/F5/F6 khi terminal chặn phím Ctrl (vd terminal trong VS Code/
                                    Cursor trên Mac: Ctrl+G là Go to Line, Ctrl+R là Run Recent).
                                    MacBook: giữ fn khi bấm F2/F5
  /quit                             thoát (Ctrl+Q) — agent đang chạy sẽ bị dừng""")

WELCOME = tr("""\
👋 Chào mừng tới ateam — bắt đầu nhanh:
  • Gõ một mục tiêu (vd: Thêm trang đăng nhập) → trưởng nhóm lập kế hoạch, Enter (hoặc F2) để duyệt & chạy
  • /grill Thêm trang đăng nhập → trưởng nhóm hỏi kỹ từng câu cho rõ yêu cầu rồi mới lập kế hoạch
  • /task codex viết test cho utils.py → giao tay cho 1 agent
  • Gõ / để xem các lệnh · @ để nhắc file · Ctrl+V dán ảnh
  • !yarn dev → chạy lệnh terminal (gõ ! để xem gợi ý) · tab 💻 Terminal
  • /git → tab 🌿 Git: stage, commit (trưởng nhóm viết message), nhánh, pull/push, stash, lịch sử
  • /code @file → tab 📝 Code: xem & sửa code với phím vim (:w lưu, /vim off để sửa kiểu thường)
  • F1 hoặc /help: toàn bộ lệnh & phím tắt · Ctrl+T: đổi tab (Bảng việc / Agents / Workflows / Code / Git / …)""")

# lệnh cho bảng gợi ý khi gõ "/" (tên, tham số, mô tả ngắn) — giữ khớp với TeamApp.run_command
COMMANDS = [
    ("task", tr("<agent> <nội dung>"), tr("giao tay cho 1 agent, gửi nguyên văn")),
    ("chat", tr("<agent> [tin nhắn]"), tr("chat trực tiếp với 1 agent như trong terminal (giữ phiên, ô 💬 ở tab Agents)")),
    ("focus", tr("[agent]"), tr("phóng to 1 agent cả màn hình để chat riêng (F7; gõ lại / Esc để thu)")),
    ("go", tr("[mục tiêu]"), tr("duyệt kế hoạch nháp và chạy")),
    ("drop", tr("[mục tiêu]"), tr("bỏ kế hoạch nháp (huỷ mọi task nháp của nó)")),
    ("goal", tr("<mục tiêu>"), tr("trưởng nhóm lập kế hoạch (bỏ qua workflow mặc định)")),
    ("grill", tr("<mục tiêu|xong|bỏ>"), tr("trưởng nhóm hỏi kỹ từng câu để làm rõ yêu cầu rồi mới "
                                            "lập kế hoạch")),
    ("sh", tr("<lệnh>"), tr("chạy lệnh terminal (như !lệnh), vd /sh yarn dev")),
    ("stop", tr("[số]"), tr("dừng lệnh terminal đang chọn (hoặc lệnh số đó)")),
    ("term", "", tr("mở tab Terminal (lệnh đang chạy)")),
    ("theme", tr("[tên] [màu nhấn]"), tr("chọn theme màu (xem trước trực tiếp)")),
    ("lang", "<en|vi>", tr("đổi ngôn ngữ giao diện (app tự mở lại)")),
    ("rules", tr("[rule mới]"), tr("rule của dự án mà mọi agent phải tuân theo; kèm nội dung thì thêm luôn")),
    ("open", tr("[thư mục]"), tr("mở folder / dự án khác (dự án gần đây, gõ đường dẫn — Tab gợi ý)")),
    ("code", tr("[@file[:dòng]]"), tr("mở tab 📝 Code: xem & sửa file với phím vim")),
    ("vim", tr("<on|off|file>"), tr("bật/tắt phím vim trong tab 📝 Code")),
    ("git", tr("[lệnh git]"), tr("mở tab Git; kèm lệnh thì chạy git <lệnh> ở tab Terminal")),
    ("commit", "[--no-verify] [message]", tr("commit (chưa stage gì thì commit tất cả); trống: "
                                             "trưởng nhóm viết message")),
    ("push", "[-f]", tr("push nhánh hiện tại (lần đầu tự tạo nhánh trên remote)")),
    ("pull", "", tr("pull nhánh hiện tại (fast-forward, không được thì merge)")),
    ("fetch", "", tr("fetch mọi remote")),
    ("branch", tr("[tên]"), tr("tạo & chuyển sang nhánh mới; trống: danh sách nhánh")),
    ("checkout", tr("<nhánh>"), tr("chuyển sang nhánh (nhánh remote → tạo nhánh local)")),
    ("stash", "[message|pop|apply|list]", tr("cất tạm / lấy lại thay đổi chưa commit")),
    ("flow", tr("<tên> <mục tiêu>"), tr("chạy mục tiêu theo workflow")),
    ("assign", "<task> [agent]", tr("đổi người làm 1 task (task lỗi/huỷ: chạy lại luôn); thiếu agent: bảng chọn")),
    ("edit", tr("<task> <nội dung>"), tr("sửa nội dung task chưa chạy")),
    ("set", tr("<task> effort|model <giá trị>"), tr("effort/model riêng cho 1 task")),
    ("retry", "<task>", tr("chạy lại task")),
    ("cancel", tr("<task|m<mục tiêu>>"), tr("huỷ task; m<số>: huỷ lượt lập kế hoạch đang chạy")),
    ("review", tr("<mục tiêu>"), tr("bắt trưởng nhóm review ngay")),
    ("search", tr("[từ khoá]"), tr("tìm & thay trong toàn dự án (F3), như VS Code")),
    ("plan", tr("[mục tiêu]"), tr("xem lại kế hoạch của mục tiêu, kể cả đã duyệt / đã xong")),
    ("todo", tr("[việc cần làm]"), tr("mở tab To-do (lưu ngoài repo); kèm nội dung thì thêm việc · hiểu #tag !cao @mai")),
    ("notes", tr("[tiêu đề]"), tr("mở tab 🗒 Ghi chú (lưu ngoài repo); kèm tiêu đề thì tạo ghi chú mới")),
    ("tags", "", tr("quản lý tag dùng chung cho To-do và Ghi chú")),
    ("grid", tr("[agent]"), tr("mở tab 🔲 Lưới: mỗi ô là CLI thật của một agent; kèm agent thì thêm ô")),
    ("continue", tr("<m12|t40> <yêu cầu>"), tr("tiếp tục mục tiêu / thread đã xong (F6)")),
    ("note", tr("<nội dung>"), tr("ghi chú chung cho cả đội")),
    ("diff", "<task>", tr("xem thay đổi của task")),
    ("merge", "<task>", tr("duyệt và merge task đang chờ")),
    ("reject", tr("<task> [góp ý]"), tr("từ chối, có góp ý thì giao làm lại")),
    ("verify", tr("[lệnh|off]"), tr("lệnh kiểm tra sau mỗi task")),
    ("notify", "[on|app|off|test]", tr("thông báo khi có kế hoạch/diff chờ duyệt hoặc task lỗi")),
    ("model", tr("<agent> [tên|-]"), tr("đổi model của agent")),
    ("effort", tr("<agent> [mức|-]"), tr("đổi effort của agent")),
    ("models", tr("[agent] [làm mới]"), tr("xem model & effort hỗ trợ")),
    ("agents", "", tr("cấu hình, lệnh chạy của từng agent")),
    ("setup", "", tr("màn hình thiết lập đội")),
    ("roles", "", tr("sửa nhanh vai trò · CLI · model · effort của đội")),
    ("custom", "", tr("tab Workflows (agent tuỳ chỉnh ở tab Agents)")),
    ("dash", "", tr("thống kê: token, cost, lịch sử mục tiêu")),
    ("flow-setup", "", tr("luồng mặc định: agent · model · effort từng bước")),
    ("usage", "", tr("thống kê lượt chạy + hạn mức còn lại báo bởi từng CLI")),
    ("update", "", tr("cập nhật ateam lên bản mới nhất")),
    ("cooldown", tr("<agent> <phút|off>"), tr("cho agent tạm nghỉ")),
    ("compact", tr("[trọng tâm]"), tr("tóm tắt ngữ cảnh chung cho prompt gọn lại")),
    ("init", tr("[trọng tâm]"), tr("trưởng nhóm tìm hiểu dự án 1 lần, viết bản tổng quan gửi kèm mọi kế hoạch "
                                    "& task")),
    ("clear", "", tr("dọn task & mục tiêu đã kết thúc khỏi bảng việc")),
    ("pause", "", tr("tạm dừng nhận task mới")),
    ("resume", "", tr("tiếp tục nhận task")),
    ("log", "[task|sys]", tr("xem log 1 task / log hệ thống")),
    ("team", "", tr("chuyển sang tab Agents")),
    ("board", "", tr("chuyển sang tab Bảng việc")),
    ("help", "", tr("toàn bộ lệnh & phím tắt")),
    ("quit", "", tr("thoát")),
]
COMMAND_ALIASES = {"tim": "search", "find": "search", "grep": "search", "vaitro": "roles", "role": "roles", "grill-me": "grill", "hoi": "grill", "h": "help", "?": "help", "t": "task", "tiep": "continue", "c": "continue", "flows": "flow", "workflow": "custom",
                   "workflows": "custom", "agent-moi": "team", "exit": "quit", "q": "quit"}


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
        return tr("Không hiểu lệnh /{cmd}", cmd=cmd)
    out = tr("Dùng: /{name} {args} — {desc}", name=name, args=spec[1], desc=spec[2]).replace("  ", " ")
    others = [n for n, _a, _d in COMMANDS if n != name and n.startswith(name)]
    if others:
        out += tr(" · hay ý bạn là ") + ", ".join("/" + n for n in others) + "?"
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


def plan_text(items: list, title: str = tr("📋 Kế hoạch")) -> Text:
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
        t.append(tr("🔎 Review: ✓ hoàn thành"), "bold green")
    else:
        t.append(tr("🔎 Review: cần làm thêm"), "bold yellow")
    if data.get("summary"):
        t.append("\n  ")
        t.append_text(md_text(str(data["summary"])))
    new = data.get("new_tasks") or []
    if new:
        t.append("\n")
        t.append_text(plan_text(new, tr("  ➕ Việc giao thêm")))
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
        self.after_json = out is not None and (tr("📋 Kế hoạch") in out.plain or "🔎 Review" in out.plain)
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
            t.append(tr("‹prompt ateam gửi agent — đã ẩn›"), "dim italic")
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
                return Text(tr("▸ prompt gửi agent (ẩn)"), "dim italic")
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
            return Text(tr("✗ Lỗi: ") + msg, "bold red")
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
            t.append(tr("✔ Tóm tắt:"), "bold green")
            t.append_text(md_text(s[len("SUMMARY:"):], "green"))
            return t
        if s.startswith("<<<NOTE>>>"):
            body = s[len("<<<NOTE>>>"):]
            if "<<<END>>>" in body:
                body = body.replace("<<<END>>>", "")
            else:
                self.block = "note"
            t = Text()
            t.append(tr("📝 Ghi chú: "), "bold yellow")
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
            t.append(tr("↪ Giao cho {to}", to=attrs.get('to', '?')), "bold magenta")
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
    """Một agent ở tab Agents: tiêu đề trạng thái (dòng trong danh sách) + log trực tiếp và ô chat (hiện khi phóng
    to — F7, /focus, bấm vào agent)."""

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
        yield TextInput(placeholder=tr("💬 Nhắn {agent}… (Enter gửi · /new: cuộc mới · /term: mở CLI thật · Esc: về danh sách)",
                                       agent=self.agent), classes="pane-chat")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        text = event.value.strip()
        event.input.value = ""
        if text:
            self.app.send_chat(self.agent, text)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape" and self.app.focus_agent == self.agent:  # Esc thu ô đang phóng to
            event.stop()
            self.app.set_focus_agent(None)

    @property
    def head(self) -> Static:
        return self.query_one(".pane-head", Static)

    @property
    def body(self) -> RichLog:
        return self.query_one(".pane-log", RichLog)

    def on_click(self, event) -> None:
        if event.style.meta.get("@click"):  # bấm vào chip model/effort: đã đổi ngay (choice_line)
            return
        if event.widget is self.head:  # danh sách: bấm vào agent -> chat riêng; đang chat: chọn model rồi effort
            if self.app.focus_agent == self.agent:
                self.app.open_picker(self.agent, "model", then_effort=True)
            else:
                self.app.set_focus_agent(self.agent)


def choice_line(label: str, items: list[str], current: str, limit: int = 0, agent: str = "") -> Text:
    """'model: [opus] sonnet haiku … +3' — mục đang dùng được tô đậm. Có `agent`: bấm vào một mục là đổi ngay
    (`app.set_agent_opt`), bấm "… +3" mở bảng chọn đủ."""
    def click(action: str) -> Style | None:
        return Style(meta={"@click": action}) if agent else None

    t = Text(f"{label}: ", "dim")
    if not items:
        t.append(tr("(để CLI tự chọn)") if label == "model" else tr("(không có)"), "dim")
        return t
    shown = items[:limit] if limit else items
    if current and current not in shown:
        shown = [current] + shown[:-1] if limit else [current] + shown
    for i, it in enumerate(shown):
        if i:
            t.append(" ")
        style = Style.parse("bold reverse cyan" if it == current else "cyan")
        act = click(f"app.set_agent_opt({agent!r}, {label!r}, {it!r})")
        t.append(it, style + act if act else style)
    if len(items) > len(shown):
        act = click(f"app.pick_agent_opt({agent!r}, {label!r})")
        t.append(f" … +{len(items) - len(shown)}", Style.parse("dim") + act if act else "dim")
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
            if not self._size_known:
                # ô chưa từng hiện (tab Agents chưa mở): RichLog sẽ hoãn vào hàng đợi không giới hạn rồi phát lại qua
                # write() (thành dòng đôi trong _items). Chỉ giữ ở _items (có giới hạn), vẽ một lần khi có kích thước.
                return self
        return super().write(content, *args, **kw)

    def clear(self):
        self._items.clear()
        return super().clear()

    def on_resize(self, event) -> None:
        first = not self._size_known
        super().on_resize(event)  # RichLog: ghi các dòng hoãn lại lúc chưa biết kích thước
        width = self.scrollable_content_region.width
        if first and self._size_known and self._items:
            self._reflow()  # các dòng ghi lúc ô còn ẩn
        elif self._width and width != self._width and self._items:
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

    BINDINGS = [Binding("escape", "request_close", tr("Đóng"))]
    DEFAULT_CSS = """
    BaseModal .m-titlebar { height: 1; }
    BaseModal .m-title { width: 1fr; text-style: bold; color: $primary; }
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
            self.notify(tr("Còn thay đổi chưa lưu — Esc lần nữa để bỏ, Ctrl+S để lưu"), severity="warning")
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
    #choice-box { width: 60; height: auto; max-height: 80%; border: round $primary 70%;
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
            yield Static(Text(tr("Enter: chọn · Esc: đóng · tên khác: /model <agent> <tên>"), "dim"))

    def on_mount(self) -> None:
        ol = self.query_one(OptionList)
        ol.highlighted = self.items.index(self.current) if self.current in self.items else len(self.items)
        ol.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        oid = event.option.id or ""
        self.dismiss(RESET if oid == "reset" else self.items[int(oid[1:])])

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class InputModeScreen(BaseModal):
    """Gõ mục tiêu (không kèm lệnh) sẽ đi đâu: trưởng nhóm lập kế hoạch hay một workflow (F4, nút cạnh ô nhập).
    Trả tên workflow ("" = trưởng nhóm), CONFIG (mở popup Luồng mặc định) hoặc None (Esc)."""

    CONFIG = "\x00config"
    DEFAULT_CSS = """
    InputModeScreen { align: center middle; }
    #mode-box { width: 76; max-width: 100%; height: auto; max-height: 80%; border: round $primary 70%;
                background: $surface; padding: 0 1; }
    #mode-list { height: auto; max-height: 24; }
    """

    def __init__(self, cfg: Config):
        super().__init__()
        self.modes = wizard.input_modes(cfg)
        self.current = cfg.default_workflow

    def compose(self) -> ComposeResult:
        opts = [Option(("● " if name == self.current else "  ") + label, id=f"m{n}")
                for n, (name, label) in enumerate(self.modes)]
        opts.append(Option(tr("  ⚙ Cấu hình luồng… (agent · model · effort từng bước, workflow mẫu)"), id="config"))
        with Vertical(id="mode-box"):
            yield self.title_bar(tr("Gõ mục tiêu sẽ chạy theo…"))
            yield OptionList(*opts, id="mode-list")
            yield Static(Text(tr("Enter: chọn · Esc: đóng · /goal luôn để trưởng nhóm lập kế hoạch · "
                                 "/flow <tên> chạy workflow khác một lần"), "dim"))

    def on_mount(self) -> None:
        ol = self.query_one(OptionList)
        ol.highlighted = next((n for n, (name, _l) in enumerate(self.modes) if name == self.current), 0)
        ol.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        oid = event.option.id or ""
        self.dismiss(self.CONFIG if oid == "config" else self.modes[int(oid[1:])][0])


class HelpScreen(BaseModal):
    """Toàn bộ lệnh & phím tắt trong một bảng nổi cuộn được (/help, F1)."""

    BINDINGS = [Binding("f1", "close", tr("Đóng"), priority=True)]
    DEFAULT_CSS = """
    HelpScreen { align: center middle; }
    #help-box { width: 124; max-width: 100%; height: 90%; border: round $primary 70%;
                background: $surface; padding: 0 1; }
    #help-body { height: 1fr; }
    #help-foot { height: 1; color: $text-muted; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield self.title_bar(tr("Trợ giúp ateam"))
            with VerticalScroll(id="help-body"):
                yield Static(help_text())
            yield Static(tr("↑↓ / PgUp PgDn cuộn · Esc hoặc F1 đóng"), id="help-foot")

    def on_mount(self) -> None:
        self.query_one("#help-body").focus()

    def action_close(self) -> None:
        self.close()


def role_row(prefix: str, role: str, label: str, desc: str, a, providers: list[str], cfg: Config,
             holder: str = "") -> Horizontal:
    """Một dòng bảng Vai trò: tên vai trò (+ agent đang giữ) · ô chọn CLI · model · effort · mô tả. Dùng chung cho
    wizard /setup, popup /roles (prefix "ob") và bảng ⚡ Vai trò ở tab Agents (prefix "rt")."""
    short = {"claude": "Claude", "grok": "Grok"}  # ô chọn hẹp: tên ngắn, không xuống dòng
    clis = [(short.get(p, PROVIDERS[p][0]), p) for p in providers]
    if role != "lead":
        clis.append((tr("(không dùng)"), RESET))
    p = a[0] if a else RESET
    models = wizard.models_of(cfg, p) if a else []
    if a and a[1] and a[1] not in models:
        models = [a[1]] + models
    effs = wizard.efforts_of(p) if a else []
    name = Text.assemble((label, "bold"), ((" · " if prefix == "rt" else "\n") + holder, "dim")) if holder else label
    return Horizontal(
        Static(name, classes="ob-role"),
        Select(clis, value=p if any(p == v for _l, v in clis) else clis[0][1], allow_blank=False,
               classes="ob-cli", id=f"{prefix}-cli-{role}"),
        Select([(m, m) for m in models] + [(tr("(mặc định)"), RESET)], value=(a[1] if a and a[1] else RESET),
               allow_blank=False, disabled=not a, classes="ob-model", id=f"{prefix}-model-{role}"),
        Select([(e, e) for e in effs] + [(tr("(mặc định)"), RESET)],
               value=(a[2] if a and a[2] in effs else RESET), allow_blank=False,
               disabled=not (a and effs), classes="ob-effort", id=f"{prefix}-effort-{role}"),
        Static(desc, classes="ob-desc"), classes="ob-row")


def refresh_role_row(owner, prefix: str, role: str, a, cfg: Config) -> None:
    """Đổi CLI của một dòng Vai trò: nạp lại ô chọn model/effort theo CLI mới."""
    p = a[0] if a else RESET
    msel = owner.query(f"#{prefix}-model-{role}")
    esel = owner.query(f"#{prefix}-effort-{role}")
    if not msel or not esel:
        return
    msel, esel = msel.first(Select), esel.first(Select)
    models = wizard.models_of(cfg, p) if a else []
    if a and a[1] and a[1] not in models:
        models = [a[1]] + models
    effs = wizard.efforts_of(p) if a else []
    msel.set_options([(m, m) for m in models] + [(tr("(mặc định)"), RESET)])
    msel.value = a[1] if a and a[1] in models else RESET
    esel.set_options([(e, e) for e in effs] + [(tr("(mặc định)"), RESET)])
    esel.value = a[2] if a and a[2] in effs else RESET
    msel.disabled, esel.disabled = not a, not (a and effs)


def read_role_rows(owner, prefix: str) -> dict:
    """Gán vai trò đang chọn trên các dòng: vai trò -> (CLI, model, effort) hoặc None (không dùng)."""
    out: dict = {}
    for k, _l, _d in ROLES:
        p = owner.query_one(f"#{prefix}-cli-{k}", Select).value
        if p == RESET:
            out[k] = None
            continue
        m = owner.query_one(f"#{prefix}-model-{k}", Select).value
        e = owner.query_one(f"#{prefix}-effort-{k}", Select).value
        out[k] = (p, "" if m == RESET else m, "" if e == RESET else e)
    return out


class OnboardScreen(BaseModal):
    """Wizard thiết lập đội (lần đầu mở app, /setup, `ateam setup`): hỏi từng bước — CLI đang dùng, kiểu làm
    việc, mức chi phí, gán CLI · model · effort cho từng vai trò, an toàn & duyệt code, lệnh kiểm tra — rồi
    xem lại và lưu. Mỗi lúc chỉ dựng widget của bước đang mở. Esc = quay lại bước trước.

    Trả về {"plan": TeamPlan, "settings": {...}} (xem config.save_onboard), hoặc None nếu đóng.

    only_roles (/roles): chỉ bước Vai trò · model · effort, mọi CLI đã cài; lưu ngay, các thiết lập khác giữ nguyên."""

    BINDINGS = [Binding("ctrl+s", "save", tr("Lưu"), priority=True)]
    DEFAULT_CSS = """
    OnboardScreen { align: center middle; }
    #ob-box { width: 116; max-width: 98%; height: auto; max-height: 95%; border: round $primary 70%;
              background: $surface; padding: 0 1; }
    #ob-steps { height: auto; color: $text-muted; margin-bottom: 1; }
    #ob-body { height: auto; max-height: 34; }
    #ob-body .ob-q { text-style: bold; margin-top: 1; }
    #ob-body .ob-hint { color: $text-muted; }
    #ob-body .ob-flow-row { height: auto; margin-top: 1; }
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
    STEPS, STYLES, TIER_HINTS, APPLY = wizard.STEPS, wizard.STYLES, wizard.TIER_HINTS, wizard.APPLY

    def __init__(self, root: Path, cfg: Config, orch: Orchestrator, timeout: float = 20, only_roles: bool = False):
        super().__init__()
        self.root, self.cfg, self.orch, self.timeout = root, cfg, orch, timeout
        self.only_roles = only_roles
        self.step = [k for k, _t, _s in self.STEPS].index("roles") if only_roles else 0
        init = wizard.initial(cfg, root)
        self.installed, self.providers = init["installed"], init["providers"]
        self.style, self.tier, self.assign = init["style"], init["tier"], init["assign"]
        # assign đang ứng với bộ CLI/mức nào; lần đầu thiết lập (None) thì bước Vai trò điền theo mức chi phí,
        # mở lại /setup thì giữ đội hiện tại cho tới khi đổi CLI hoặc mức
        self._assign_key = (tuple(self.providers), None if init["first"] else self.tier)
        if only_roles:  # sửa nhanh: chọn được mọi CLI đã cài, giữ nguyên gán hiện tại
            self.providers = wizard.quick_providers(init)
            self._assign_key = (tuple(self.providers), self.tier)
        self.access, self.apply, self.verify = init["access"], init["apply"], init["verify"]
        self.flow_name = cfg.default_workflow  # workflow chọn ở popup "Luồng mặc định" ("" = mẫu tinh-nang)
        self.git = (root / ".git").exists()
        self.discovering = True
        self._step_ready = asyncio.Event()
        self._esc_at = 0.0

    # ---------------------------------------------------------------- dữ liệu
    def models_of(self, provider: str) -> list[str]:
        return wizard.models_of(self.cfg, provider)

    def efforts_of(self, provider: str) -> list[str]:
        return wizard.efforts_of(provider)

    def _default(self, role: str) -> tuple[str, str, str] | None:
        return wizard.default_role(self.cfg, role, self.providers, self.tier)

    def plan(self) -> TeamPlan:
        return plan_team(self.assign)

    def settings(self) -> dict:
        return wizard.settings_of(self.style, self.access, self.apply, self.verify, self.flow_name)

    # ---------------------------------------------------------------- khung
    def compose(self) -> ComposeResult:
        with Vertical(id="ob-box"):
            yield self.title_bar(tr("Thiết lập đội AI"))
            yield Static(id="ob-steps")
            yield VerticalScroll(id="ob-body")
            with Horizontal(id="ob-buttons"):
                yield Btn(tr("Agent & workflow tuỳ chỉnh…"), id="ob-custom")
                yield Static(classes="ob-spacer")
                yield Btn(tr("← Quay lại"), id="ob-back")
                yield Btn(tr("Tiếp →"), id="ob-next", variant="primary")

    async def on_mount(self) -> None:
        await self.show_step(self.step)
        self.run_worker(self._discover(), exclusive=True)

    async def _discover(self) -> None:
        try:
            await self.orch.discover_all(timeout=self.timeout)
        except Exception as e:  # không bao giờ chặn wizard
            self.orch.log(tr("⚠ Không hỏi được danh sách model: {e}", e=e))
        while not self._step_ready.is_set():
            await self._step_ready.wait()
        self.discovering = False
        if self.STEPS[self.step][0] == "roles":
            # Giữ nguyên widget đang được nhập/chọn: dựng lại cả bước có thể huỷ Select
            # giữa lúc xử lý phím hoặc cập nhật value, đồng thời làm mất lựa chọn vừa sửa.
            self.collect()
            for role, _label, _desc in ROLES:
                self._refresh_role(role, self.assign.get(role))
            self.query_one("#ob-roles-hint", Static).update(self._roles_hint())

    async def show_step(self, i: int) -> None:
        self._step_ready.clear()
        self.step = i
        key, title, _short = self.STEPS[i]
        self.query_one(".m-title", Static).update(Text(
            tr("⚡ Vai trò · model · effort") if self.only_roles else
            tr("Thiết lập đội AI · Bước {v}/{v2} — {title}", v=i + 1, v2=len(self.STEPS), title=title), "bold"))
        t = Text()
        for n, (_k, _title, name) in enumerate(self.STEPS):
            if n:
                t.append("  ›  ", "dim")
            t.append(f"{n + 1}. {name}", "bold" if n == i else "dim" if n > i else "green")
        self.query_one("#ob-steps", Static).update(
            Text(tr("Lưu là có hiệu lực ngay; kiểu làm việc, quyền, lệnh kiểm tra giữ nguyên (đổi ở /setup)."), "dim")
            if self.only_roles else t)
        body = self.query_one("#ob-body", VerticalScroll)
        await body.remove_children()
        await body.mount_all(getattr(self, f"_step_{key}")())
        self.query_one("#ob-back", Button).disabled = i == 0
        self.query_one("#ob-back").display = not self.only_roles
        self.query_one("#ob-next", Button).label = (tr("Lưu (Ctrl+S)") if self.only_roles else
                                                    tr("Lưu & bắt đầu (Ctrl+S)") if key == "review" else tr("Tiếp →"))
        self.query_one("#ob-custom").display = key == "review"
        first = body.query("SelectionList, OptionList, Select, Input")
        (first.first() if first else self.query_one("#ob-next")).focus()
        self._step_ready.set()

    # ---------------------------------------------------------------- từng bước
    def _step_cli(self) -> list:
        items = []
        for p, (label, _agent) in PROVIDERS.items():
            ok = p in self.installed
            t = Text(f"{label:14}", "bold" if ok else "dim")
            t.append(tr("  ✓ đã cài ({p})", p=p) if ok else tr("  ✗ chưa cài — {v}", v=INSTALL_HINTS.get(p, p)),
                     "green" if ok else "dim")
            items.append(Selection(t, p, p in self.providers and ok, disabled=not ok))
        return [Static(tr("Bạn đang dùng những CLI nào? Đội chỉ gồm các CLI được chọn."), classes="ob-q"),
                SelectionList(*items, id="ob-cli"),
                Static(tr("Space: chọn/bỏ · Tab: sang nút Tiếp"), classes="ob-hint")]

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
        return [Static(tr("Bạn muốn đội làm việc thế nào?"), classes="ob-q"),
                self._choice("ob-style", self.STYLES, self.style),
                Static(tr("↑↓ chọn · Enter: chọn và sang bước tiếp"), classes="ob-hint"),
                Horizontal(Btn(tr("⚙ Cấu hình luồng cố định…"), id="ob-flow"),
                           Static(tr("  agent · model · effort cho từng bước của workflow '{name}'",
                                     name=self.flow_name or WIZARD_FLOW), classes="ob-hint"),
                           classes="ob-flow-row")]

    def _step_tier(self) -> list:
        items = [(k, label, self.TIER_HINTS[k]) for k, label in TIERS]
        return [Static(tr("Ưu tiên tiết kiệm hạn mức hay chất lượng?"), classes="ob-q"),
                self._choice("ob-tier", items, self.tier),
                Static(tr("Bước sau điền sẵn model & effort theo mức này — vẫn đổi được từng vai "
                          "trò."),
                       classes="ob-hint")]

    def _row(self, role: str, label: str, desc: str) -> Horizontal:
        return role_row("ob", role, label, desc, self.assign.get(role), self.providers, self.cfg)

    def _step_roles(self) -> list:
        key = (tuple(self.providers), self.tier)
        if self._assign_key != key:  # đổi CLI hoặc mức chi phí: gán lại theo mặc định mới
            self.assign = wizard.default_assign(self.cfg, self.providers, self.tier)
            self._assign_key = key
        out = [Static(tr("Giao từng vai trò cho CLI nào, dùng model và effort gì?"), classes="ob-q"),
               Static(self._roles_hint(), classes="ob-hint", id="ob-roles-hint")]
        out += [self._row(k, label, desc) for k, label, desc in ROLES]
        return out

    def _roles_hint(self) -> str:
        return tr("Cùng một CLI làm nhiều vai trò với model/effort khác nhau → ateam tự tạo "
                  "thêm agent (vd claude-review).") + (tr("  ⏳ đang hỏi danh sách model từ các CLI…")
                                                    if self.discovering else "")

    def _step_safety(self) -> list:
        access = wizard.ACCESS
        no_git = () if self.git else ("worktree-auto", "worktree-review")
        apply = [(k, label, hint if self.git else hint + tr(" — cần thư mục là git repo có commit"))
                 for k, label, hint in self.APPLY]
        return [Static(tr("Agent được làm gì?"), classes="ob-q"),
                self._choice("ob-access", access, self.access),
                Static(tr("Thay đổi của agent áp vào code thế nào?"), classes="ob-q"),
                self._choice("ob-apply", apply, self.apply, disabled=no_git)]

    def _step_verify(self) -> list:
        items = wizard.verify_choices(self.root, self.verify)
        cmds = [c for c, _l, _h in items]
        return [Static(tr("Lệnh kiểm tra tự chạy sau mỗi task (test, lint, build)?"), classes="ob-q"),
                self._choice("ob-verify", items, self.verify),
                TextInput(self.verify if self.verify not in cmds else "",
                          placeholder=tr("hoặc gõ lệnh khác, vd: npm run lint && npm test"), id="ob-verify-input")]

    def _step_review(self) -> list:
        plan, st = self.plan(), self.settings()
        t = Text()
        t.append(tr("Đội\n"), "bold")
        for name, a in plan.agents.items():
            t.append(f"  {'★ ' if name == plan.lead else '  '}{name:18}", "bold yellow" if name == plan.lead else "bold")
            t.append(f"{PROVIDERS[a['provider']][0]:13}", "cyan")
            label = (a["model"] or tr("mặc định")) + (f" · {a['effort']}" if a["effort"] else "")
            t.append(f"{label:30}")
            t.append(", ".join(dict((k, lbl) for k, lbl, _d in ROLES)[r].lstrip("★ ") for r in a["roles"]), "dim")
            if not a["builtin"]:
                t.append(tr("  (agent thêm)"), "green")
            t.append("\n")
        others = [n for n in self.cfg.custom_agents if n in self.cfg.agents and not load_custom()
                  .get("agents", {}).get(n, {}).get("wizard")]
        if others:
            t.append(tr("  Agent tuỳ chỉnh giữ nguyên: {v}\n", v=', '.join(others)), "dim")
        style = dict((k, label) for k, label, _h in self.STYLES)[self.style]
        apply = dict((k, label) for k, label, _h in self.APPLY)[self.apply]
        t.append(tr("\nCách làm việc\n"), "bold")
        for k, v in ((tr("Kiểu"), style), (tr("Mức"), dict(TIERS)[self.tier]),
                     (tr("Quyền"), tr("toàn quyền") if st["full_access"] else tr("chỉ sửa file")),
                     (tr("Áp thay đổi"), apply), (tr("Kiểm tra"), st["verify_command"] or tr("không"))):
            t.append(f"  {k:12}", "dim")
            t.append(v + "\n")
        if not plan.lead:
            t.append(tr("\n⚠ Chưa có trưởng nhóm — quay lại bước Vai trò."), "bold red")
        return [Static(t)]

    # ---------------------------------------------------------------- lưu lựa chọn của bước đang mở
    def collect(self) -> str | None:
        """Đọc giá trị của bước đang mở vào self.*; trả về lỗi (chuỗi) nếu chưa hợp lệ."""
        key = self.STEPS[self.step][0]
        if key == "cli":
            chosen = list(self.query_one("#ob-cli", SelectionList).selected)
            if not chosen:
                return tr("Chọn ít nhất một CLI")
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
            self.assign.update(read_role_rows(self, "ob"))
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
        self._refresh_role(role, self.assign[role])

    def _refresh_role(self, role: str, a) -> None:
        refresh_role_row(self, "ob", role, a, self.cfg)

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
            if self.STEPS[self.step][0] == "review" or self.only_roles:
                self.action_save()
            else:
                await self.go(1)
        elif bid == "ob-back":
            event.stop()
            await self.go(-1)
        elif bid == "ob-custom":
            event.stop()
            self.app.push_screen(CustomScreen(self.root, self.cfg), self._custom_done)
        elif bid == "ob-flow":
            event.stop()
            self.collect()
            self.app.push_screen(DefaultFlowScreen(self.cfg, in_setup=True, name=self.flow_name), self._flow_done)

    async def _flow_done(self, name) -> None:
        if not name:
            return
        self.flow_name, self.style = name, "flow"  # đã cấu hình luồng → chọn luôn kiểu "theo quy trình"
        await self.app.reload_custom()
        await self.show_step(self.step)

    async def _custom_done(self, changed) -> None:
        if changed:
            await self.app.reload_custom()
            await self.show_step(self.step)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "ob-verify-input":
            event.stop()
            await self.go(1)

    def action_request_close(self) -> None:
        if self.only_roles:
            self.close()
            return
        if self.step > 0:  # Esc = quay lại bước trước
            self.run_worker(self.go(-1), exclusive=True, group="ob-nav")
            return
        if time.time() - self._esc_at > 3:
            self._esc_at = time.time()
            self.notify(tr("Esc lần nữa để thoát thiết lập (giữ cấu hình hiện tại)"), severity="warning")
            return
        self.close()

    def action_save(self) -> None:
        if self.STEPS[self.step][0] != "review":
            self.collect()
        plan = self.plan()
        if not plan.lead:
            self.notify(tr("Chưa có trưởng nhóm — chọn CLI cho vai trò ★ Trưởng nhóm"), severity="error")
            return
        self.dismiss({"plan": plan, "settings": self.settings()})


class RolesTable(Vertical):
    """Bảng ⚡ Vai trò ở tab Agents (như trang Agents của web): đổi CLI · model · effort của từng vai trò ngay trên
    tab, có thay đổi thì hiện ✓ Lưu / Huỷ (lưu như /roles: chỉ vai trò, thiết lập khác giữ nguyên). Đang sửa dở
    thì không vẽ lại."""

    DEFAULT_CSS = """
    RolesTable { height: auto; padding: 0 1; margin-bottom: 1; }
    RolesTable #rt-head { height: 1; }
    RolesTable #rt-title { width: auto; text-style: bold; }
    RolesTable #rt-hint { width: 1fr; padding: 0 0 0 2; color: $text-muted; text-wrap: nowrap; text-overflow: ellipsis; }
    RolesTable #rt-head Button { margin-left: 1; }
    RolesTable #rt-rows { height: auto; }
    RolesTable #rt-rows { margin-top: 1; }
    RolesTable .ob-row { height: 1; }
    RolesTable .ob-role { width: 30; height: 1; text-wrap: nowrap; text-overflow: ellipsis; }
    RolesTable Select { height: 1; margin-right: 1; }
    RolesTable Select > SelectCurrent { border: none; height: 1; padding: 0 1; background: $boost; }
    RolesTable .ob-cli { width: 2fr; min-width: 16; }
    RolesTable .ob-model { width: 3fr; min-width: 20; }
    RolesTable .ob-effort { width: 2fr; min-width: 12; }
    RolesTable .ob-desc { width: 3fr; min-width: 0; color: $text-muted; text-wrap: nowrap; text-overflow: ellipsis; }
    """

    def __init__(self, root: Path, cfg: Config, **kw):
        super().__init__(**kw)
        self.root, self.cfg = root, cfg
        self.base: dict | None = None  # gán vai trò lúc vẽ (so để biết đã sửa chưa)
        self.dirty = False
        self._lock = asyncio.Lock()  # nạp lại chồng nhau (mở tab + /setup…): dựng lần lượt
        self._gen = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="rt-head"):
            yield Static(tr("⚡ Vai trò"), id="rt-title")
            yield Static(tr("CLI · model · effort của từng vai trò — đổi xong bấm ✓ Lưu"), id="rt-hint")
            yield Btn(tr("⚙ Thiết lập đầy đủ"), id="rt-setup")
            yield Btn(tr("Huỷ"), id="rt-cancel")
            yield Btn(tr("✓ Lưu"), id="rt-save", variant="success")
        yield Vertical(id="rt-rows")

    async def on_mount(self) -> None:
        await self.reload(force=True)

    async def reload(self, force: bool = False) -> None:
        async with self._lock:
            if self.dirty and not force:
                return
            self._gen += 1
            self.cfg = self.app.cfg
            init = wizard.initial(self.cfg, self.root)
            self.providers = wizard.quick_providers(init)
            holders = wizard.role_agents(self.cfg)
            rows = [role_row("rt", k, label, desc, init["assign"].get(k), self.providers, self.cfg,
                             holders.get(k, "")) for k, label, desc in ROLES]
            box = self.query_one("#rt-rows", Vertical)
            self.base = None  # Select.Changed lúc dựng không tính là sửa
            await box.remove_children()
            await box.mount_all(rows)
            self._mark_dirty(False)
            gen = self._gen
            self.call_after_refresh(lambda: self._ready(gen))

    def _ready(self, gen: int) -> None:
        if gen != self._gen or self._lock.locked():  # đã có lượt dựng mới hơn
            return
        try:
            self.base = read_role_rows(self, "rt")
        except Exception:  # đang dựng lại
            self.base = None

    def _mark_dirty(self, on: bool) -> None:
        self.dirty = on
        self.query_one("#rt-save").display = self.query_one("#rt-cancel").display = on

    def on_select_changed(self, event: Select.Changed) -> None:
        sid = event.select.id or ""
        if not sid.startswith("rt-"):
            return
        event.stop()
        if self.base is None:
            return
        if sid.startswith("rt-cli-"):  # đổi CLI: model/effort gợi ý theo CLI mới
            role = sid[len("rt-cli-"):]
            p = event.value
            cur = read_role_rows(self, "rt").get(role)
            if p == RESET:
                refresh_role_row(self, "rt", role, None, self.cfg)
            elif self.base.get(role) is None or self.base[role][0] != p:
                refresh_role_row(self, "rt", role, (p,) + tier_preset(
                    p, "balanced", role, wizard.models_of(self.cfg, p), wizard.efforts_of(p)), self.cfg)
            elif cur != self.base.get(role):
                refresh_role_row(self, "rt", role, self.base[role], self.cfg)
        self._mark_dirty(read_role_rows(self, "rt") != self.base)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if not bid.startswith("rt-"):
            return
        event.stop()
        if bid == "rt-setup":
            self.app.open_setup()
        elif bid == "rt-cancel":
            await self.reload(force=True)
        elif bid == "rt-save":
            plan = plan_team(read_role_rows(self, "rt"))
            if not plan.lead:
                self.notify(tr("Chưa có trưởng nhóm — chọn CLI cho vai trò ★ Trưởng nhóm"), severity="error")
                return
            self._mark_dirty(False)
            await self.app._setup_done({"plan": plan, "settings": wizard.current_settings(self.app.cfg, self.root)})
            await self.reload(force=True)
            self.notify(tr("⚡ Đã lưu vai trò"))


# --------------------------------------------------------------------------- agent & workflow tuỳ chỉnh
FORM_CSS = """
    #{box} { width: 120; max-width: 100%; height: auto; max-height: 95%; border: round $primary 70%;
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


ACCESS_CHOICES = [(tr("sửa file"), "safe"), (tr("toàn quyền"), "full")]
ACCESS_LONG = [(tr("Chỉ sửa file (an toàn)"), "safe"),
               (tr("Toàn quyền — chạy lệnh, mạng (build, git push…)"), "full")]


class AgentQuickScreen(BaseModal):
    """Thêm/sửa agent dựa trên một nhà cung cấp có sẵn (Claude Code, Codex, Antigravity, OpenCode):
    chỉ chọn model, effort, quyền — mọi cờ CLI lấy từ mẫu. "Nâng cao…" mở form đầy đủ (AgentEditScreen).
    Trả về (tên, thân TOML, tên cũ) hoặc None (Esc)."""

    BINDINGS = [Binding("ctrl+s", "save", tr("Lưu"), priority=True)]
    DEFAULT_CSS = "AgentQuickScreen { align: center middle; }" + FORM_CSS.replace("{box}", "quick-box") + """
    #quick-preview { height: auto; padding: 0 1; background: $boost; margin-top: 1; }
    """

    def __init__(self, cfg: Config, name: str | None = None, raw: dict | None = None):
        super().__init__()
        self.cfg, self.old_name, self.raw = cfg, name, dict(raw or {})
        self.provider = provider_of(self.raw.get("command")) or next(
            (p for p in PROVIDERS if shutil.which(p)), "claude")

    def compose(self) -> ComposeResult:
        provs = [(label + ("" if shutil.which(p) else tr("  (chưa cài)")), p) for p, (label, _t) in PROVIDERS.items()]
        with Vertical(id="quick-box"):
            yield self.title_bar(tr("Sửa agent ") + self.old_name if self.old_name else tr("Thêm agent"))
            yield Static(Text(tr("Chọn nhà cung cấp, model, effort và quyền — cờ CLI ateam tự "
                                 "điền. Ctrl+S lưu, Esc huỷ. CLI khác (Gemini, Aider, lệnh riêng): "
                                 "Nâng cao…"), "dim"))
            yield form_row(tr("Nhà cung cấp"), Select(provs, value=self.provider, allow_blank=False, id="q-provider",
                                                  classes="f-input"), tr("CLI chạy agent này"))
            yield form_row(tr("Tên"), TextInput(self.old_name or "", placeholder="vd: codex-nhanh",
                                            id="q-name", classes="f-input"), tr("chữ, số, - và _"))
            yield form_row("Model", Select([(tr("(mặc định)"), RESET)], value=RESET, allow_blank=False, id="q-model",
                                           classes="f-input"), tr("(mặc định) = để CLI tự chọn"))
            yield form_row("Effort", Select([(tr("(mặc định)"), RESET)], value=RESET, allow_blank=False,
                                            id="q-effort", classes="f-input"), tr("mức suy luận"))
            yield form_row(tr("Quyền"), Select(ACCESS_LONG, value="full" if self.raw.get("full_access") else "safe",
                                           allow_blank=False, id="q-access", classes="f-input"),
                           tr("toàn quyền khi agent cần chạy lệnh"))
            yield form_row(tr("Vai trò"), TextInput(str(self.raw.get("role", "")), placeholder=tr("trưởng nhóm chia việc dựa vào đây"), id="q-role", classes="f-input"), tr("tuỳ chọn"))
            yield Static(id="quick-preview")
            with Horizontal(classes="f-buttons"):
                yield Btn(tr("Nâng cao…"), id="q-advanced")
                yield Btn(tr("Huỷ"), id="q-cancel")
                yield Btn(tr("Lưu (Ctrl+S)"), id="q-save", variant="primary")

    def on_mount(self) -> None:
        self._fill_choices(keep_model=str(self.raw.get("model") or ""), keep_effort=str(self.raw.get("effort") or ""))
        if not self.old_name:
            self._auto_name()
        self.query_one("#q-provider", Select).focus()
        self.call_after_refresh(self.mark_clean)

    def _models(self) -> list[str]:
        return wizard.quick_models(self.cfg, self.provider)

    def _fill_choices(self, keep_model: str = "", keep_effort: str = "") -> None:
        models = self._models()
        if keep_model and keep_model not in models:
            models = [keep_model] + models
        msel = self.query_one("#q-model", Select)
        msel.set_options([(m, m) for m in models] + [(tr("(mặc định)"), RESET)])
        msel.value = keep_model or RESET
        efforts = provider_template(self.provider).get("efforts") or []
        esel = self.query_one("#q-effort", Select)
        esel.set_options([(e, e) for e in efforts] + [(tr("(mặc định)"), RESET)])
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
        self._auto = name.value = wizard.auto_name(self.cfg, PROVIDERS[self.provider][1])

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
        def val(wid: str) -> str:
            v = self.query_one(wid, Select).value
            return "" if v in (RESET, Select.BLANK, None) else str(v)
        return wizard.quick_body(self.cfg, self.provider, val("#q-model"), val("#q-effort"),
                                 self.query_one("#q-role", TextInput).value,
                                 self.query_one("#q-access", Select).value == "full")

    def update_preview(self) -> None:
        if not self.is_mounted:
            return
        name = self.query_one("#q-name", TextInput).value.strip() or "agent"
        a = agent_from_dict(name, self.body())
        t = Text()
        t.append(tr("Lệnh sẽ chạy: "), "bold")
        t.append(" ".join(a.argv("<prompt>")))
        t.append("\n")
        t.append(tr("✓ đã cài '{binary}'", binary=a.binary) if a.installed() else tr("✗ chưa cài '{binary}'", binary=a.binary),
                 "green" if a.installed() else "yellow")
        if a.full_access:
            t.append(tr("   ⚠ toàn quyền: agent chạy được mọi lệnh trên máy, chỉ dùng với repo tin "
                        "tưởng"), "yellow")
        self.query_one("#quick-preview", Static).update(t)

    def validate(self) -> tuple[str, dict]:
        name = self.query_one("#q-name", TextInput).value.strip()
        wizard.check_agent_name(self.cfg, name, self.old_name)
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

    BINDINGS = [Binding("ctrl+s", "save", tr("Lưu"), priority=True)]
    DEFAULT_CSS = "AgentEditScreen { align: center middle; }" + FORM_CSS.replace("{box}", "agent-box") + """
    #agent-preview { height: auto; padding: 0 1; background: $boost; margin-top: 1; }
    """
    FIELDS = wizard.AGENT_FIELDS

    def __init__(self, cfg: Config, name: str | None = None, raw: dict | None = None,
                 new_name: str | None = None):
        super().__init__()
        self.cfg, self.old_name, self.raw = cfg, name, dict(raw or {})
        self.new_name = new_name  # tên đã gõ ở form đơn giản (mở form này bằng "Nâng cao…")
        self.templates = agent_templates()

    def compose(self) -> ComposeResult:
        with Vertical(id="agent-box"):
            yield self.title_bar(tr("Sửa agent ") + self.old_name if self.old_name else tr("Thêm agent tuỳ chỉnh"))
            yield Static(Text(tr("Bất kỳ CLI nào có chế độ headless (nhận prompt, in kết quả rồi "
                                 "thoát). Chọn mẫu để điền sẵn, Ctrl+S lưu, Esc huỷ."), "dim"))
            with VerticalScroll(classes="f-scroll"):
                yield form_row(tr("Mẫu"), Select([(k, k) for k in self.templates], prompt=tr("(chọn để điền sẵn)"),
                                             id="ag-template", classes="f-input"),
                               tr("điền sẵn lệnh, cờ model/effort, cú pháp file"))
                yield form_row(tr("Tên"), TextInput(self.old_name or self.new_name or "",
                                                placeholder="vd: gemini, aider-fast",
                                            id="ag-name", classes="f-input"),
                               tr("chữ, số, - và _"))
                for fid, label, hint, _k, _t in self.FIELDS:
                    yield form_row(label, TextInput(id=f"ag-{fid}", classes="f-input"), hint)
                yield form_row(tr("Tuỳ chọn"), Horizontal(
                    Checkbox(tr("Chạy trong terminal giả (pty)"), id="ag-pty"),
                    Checkbox(tr("Chạy lệnh kiểm tra sau task"), True, id="ag-verify"),
                    Checkbox(tr("Toàn quyền"), id="ag-full"),
                    classes="f-input"), tr("pty cần cho CLI chỉ in khi có terminal (vd agy)"))
            yield Static(id="agent-preview")
            with Horizontal(classes="f-buttons"):
                yield Btn(tr("Huỷ"), id="ag-cancel")
                yield Btn(tr("Lưu (Ctrl+S)"), id="ag-save", variant="primary")

    def on_mount(self) -> None:
        self.fill(self.raw)
        self.query_one("#ag-name" if not self.old_name else "#ag-command", Input).focus()
        self.call_after_refresh(self.mark_clean)

    def fill(self, raw: dict) -> None:
        for fid, text in wizard.agent_fields_text(raw).items():
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
            name.value = wizard.auto_name(self.cfg, "my-agent" if base == "trống" else base)

    def on_input_changed(self, event: Input.Changed) -> None:
        self.update_preview()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        self.update_preview()

    def body(self) -> dict:
        """Đọc form thành dict như trong TOML (chỉ những khoá có điền). Lỗi -> ValueError."""
        return wizard.agent_body({fid: self.query_one(f"#ag-{fid}", Input).value for fid, *_r in self.FIELDS},
                                 pty=self.query_one("#ag-pty", Checkbox).value,
                                 verify=self.query_one("#ag-verify", Checkbox).value,
                                 full=self.query_one("#ag-full", Checkbox).value)

    def update_preview(self) -> None:
        t = Text()
        try:
            body = self.body()
            name = self.query_one("#ag-name", Input).value.strip() or "agent"
            a = agent_from_dict(name, body)
            if not a.command:
                t.append(tr("Nhập lệnh để xem trước."), "dim")
            else:
                t.append(tr("Lệnh sẽ chạy: "), "bold")
                t.append(" ".join(a.argv("<prompt>", model=a.model or None, effort=a.effort or None)))
                t.append("\n@file → ", "bold")
                t.append(mentions.describe(a.binary, a.file_ref, a.file_args, a.image_args))
                t.append("   ")
                t.append(tr("✓ đã cài '{binary}'", binary=a.binary) if a.installed() else tr("✗ chưa cài '{binary}'", binary=a.binary),
                         "green" if a.installed() else "yellow")
                if not any("{prompt}" in c for c in a.command):
                    t.append(tr("\n⚠ lệnh không có {prompt}: prompt sẽ được thêm vào cuối"), "yellow")
        except ValueError as e:
            t.append(f"⚠ {e}", "yellow")
        self.query_one("#agent-preview", Static).update(t)

    def validate(self) -> tuple[str, dict]:
        name = self.query_one("#ag-name", Input).value.strip()
        body = self.body()
        wizard.check_agent(self.cfg, name, self.old_name, body)
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

    BINDINGS = [Binding("ctrl+s", "save", tr("Lưu"), priority=True)]
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
    #wf-ai-row { width: 64; height: 3; }
    #wf-ai-desc { width: 1fr; }
    #wf-ai { margin-top: 1; }
    """

    def __init__(self, cfg: Config, name: str | None = None, raw: dict | None = None):
        super().__init__()
        self.cfg, self.old_name, self.raw = cfg, name, dict(raw or {})
        self.n = 0  # bộ đếm id hàng (không phải số thứ tự bước)

    def agent_options(self, extra: str = "") -> list[tuple[str, str]]:
        opts = [(tr("★ trưởng nhóm ({lead})", lead=self.cfg.lead), LEAD_ALIAS)] + [(n, n) for n in self.cfg.agents]
        if extra and extra not in (LEAD_ALIAS, *self.cfg.agents):
            opts.append((tr("{extra} (không có trong đội)", extra=extra), extra))
        return opts

    def compose(self) -> ComposeResult:
        with Vertical(id="flow-box"):
            yield self.title_bar(tr("Sửa workflow ") + self.old_name if self.old_name else tr("Thêm workflow"))
            yield Static(Text(tr("Chuỗi bước dựng sẵn, chạy bằng /flow <tên> <mục tiêu> — không "
                                 "cần trưởng nhóm lập kế hoạch. {goal} trong tiêu đề/prompt = mục "
                                 "tiêu bạn gõ. 'Sau bước': trống = sau bước liền trước, 0 = chạy "
                                 "ngay, 1,2 = sau bước 1 và 2."),
                              "dim"))
            with VerticalScroll(classes="f-scroll"):
                yield form_row(tr("✨ Gợi ý"), Horizontal(
                    TextInput(placeholder=tr("mô tả quy trình, vd: thiết kế → code → test → review"), id="wf-ai-desc"),
                    Btn(tr("Gợi ý"), id="wf-ai"), id="wf-ai-row"), tr("trưởng nhóm điền các bước"))
                yield form_row(tr("Mẫu"), Select([(f"{k} — {v['description']}", k)
                                              for k, v in WORKFLOW_TEMPLATES.items()],
                                             prompt=tr("(chọn để điền sẵn)"), id="wf-template",
                                             classes="f-input"), tr("thay toàn bộ các bước"))
                yield form_row(tr("Tên"), TextInput(self.old_name or "", placeholder=tr("vd: tinh-nang, sua-loi"),
                                            id="wf-name", classes="f-input"), tr("chữ, số, - và _"))
                yield form_row(tr("Mô tả"), TextInput(id="wf-desc", classes="f-input"), tr("hiện trong /flow"))
                yield form_row("Review", Checkbox(tr("Trưởng nhóm review khi xong"), id="wf-review"),
                               tr("review có thể giao thêm việc"))
                yield Horizontal(*[Static(label, classes=cls) for label, cls in (
                    ("", "step-no"), ("Agent", "step-agent"), (tr("Tiêu đề"), "step-title"),
                    ("Prompt", "step-prompt"), (tr("Sau bước"), "step-after"), ("Effort", "step-effort"),
                    ("", "step-del"))], id="flow-head")
                yield Vertical(id="flow-steps")
                yield Btn(tr("+ Thêm bước"), id="wf-add")
            with Horizontal(classes="f-buttons"):
                yield Btn(tr("Huỷ"), id="wf-cancel")
                yield Btn(tr("Lưu (Ctrl+S)"), id="wf-save", variant="primary")

    async def on_mount(self) -> None:
        await self.fill(self.raw)
        self.query_one("#wf-name" if not self.old_name else "#wf-desc", Input).focus()
        self.call_after_refresh(self.mark_clean)

    def step_row(self, st: dict) -> Horizontal:
        self.n += 1
        k = self.n
        agent = str(st.get("agent") or LEAD_ALIAS)
        after_text = wizard.after_text(st.get("after"))
        return Horizontal(
            Static("", classes="step-no"),
            Select(self.agent_options(agent), value=agent, allow_blank=False, classes="step-agent",
                   id=f"wf-agent-{k}"),
            TextInput(str(st.get("title") or ""), placeholder=tr("tiêu đề"), classes="step-title", id=f"wf-title-{k}"),
            TextInput(str(st.get("prompt") or ""), placeholder=tr("việc cần làm, có thể dùng {goal}"),
                  classes="step-prompt", id=f"wf-prompt-{k}"),
            TextInput(after_text, placeholder=tr("trước"), classes="step-after", id=f"wf-after-{k}"),
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
        await self.fill(wizard.workflow_template(self.cfg, str(event.value)))
        name = self.query_one("#wf-name", Input)
        if not name.value.strip():
            name.value = str(event.value)

    async def suggest(self) -> None:
        btn = self.query_one("#wf-ai", Button)
        if btn.disabled:
            return
        btn.disabled = True
        label = btn.label
        btn.label = tr("⏳ Đang thiết kế…")
        try:
            with self.app.busy(tr("✨ {lead} đang thiết kế workflow…", lead=self.cfg.lead)):
                ok, form = await self.app.orch.suggest_workflow(self.query_one("#wf-ai-desc", Input).value)
        finally:
            btn.disabled = False
            btn.label = label
        if not self.is_attached:  # đã đóng popup trong lúc chờ
            return
        if not ok:
            self.notify(str(form), severity="warning", timeout=8)
            return
        name = self.query_one("#wf-name", Input)
        if not name.value.strip():
            name.value = form["name"]
        await self.fill(form)
        self.notify(tr("✨ Đã điền {n} bước — xem lại rồi Ctrl+S để lưu", n=len(form["steps"])))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "wf-ai-desc":
            event.stop()
            self.run_worker(self.suggest(), exclusive=True, group="wf-ai")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "wf-ai":
            self.run_worker(self.suggest(), exclusive=True, group="wf-ai")
        elif bid == "wf-add":
            await self.query_one("#flow-steps", Vertical).mount(self.step_row({}))
            self.renumber()
        elif bid.startswith("wf-del-"):
            if len(self.query(".step-row")) <= 1:
                self.notify(tr("Workflow cần ít nhất 1 bước"), severity="warning")
                return
            await self.query_one(f"#wf-step-{bid[7:]}").remove()
            self.renumber()
        elif bid == "wf-save":
            self.action_save()
        elif bid == "wf-cancel":
            self.action_cancel()

    def validate(self) -> tuple[str, dict]:
        name = self.query_one("#wf-name", Input).value.strip()
        steps = []
        for row in self.query(".step-row"):
            k = (row.id or "")[len("wf-step-"):]
            steps.append({"agent": str(row.query_one(f"#wf-agent-{k}", Select).value),
                          "title": row.query_one(f"#wf-title-{k}", Input).value,
                          "prompt": row.query_one(f"#wf-prompt-{k}", Input).value,
                          "after": row.query_one(f"#wf-after-{k}", Input).value,
                          "effort": row.query_one(f"#wf-effort-{k}", Input).value})
        body = wizard.workflow_body(self.cfg, name, self.old_name, self.query_one("#wf-desc", Input).value,
                                    self.query_one("#wf-review", Checkbox).value, steps)
        return name, body

    def action_save(self) -> None:
        try:
            name, body = self.validate()
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        self.dismiss((name, body, self.old_name))

    def action_cancel(self) -> None:
        self.dismiss(None)


class DefaultFlowScreen(BaseModal):
    """Popup "Luồng mặc định": chọn workflow, rồi agent · model · effort cho từng bước (giữ tiêu đề/prompt),
    bật/tắt review cuối, đặt làm luồng chạy khi gõ mục tiêu. Lưu ngay vào custom.toml.
    in_setup: mở từ /setup — wizard tự đặt luồng mặc định khi lưu nên ẩn ô đó. Trả về tên workflow hoặc None."""

    BINDINGS = [Binding("ctrl+s", "save", tr("Lưu"), priority=True)]
    DEFAULT_CSS = "DefaultFlowScreen { align: center middle; }" + FORM_CSS.replace("{box}", "df-box") + """
    #df-steps { height: auto; }
    .df-row { height: 3; }
    .df-title { width: 28; padding: 1 0 0 1; text-style: bold; text-wrap: nowrap; text-overflow: ellipsis; }
    .df-agent { width: 30; }
    .df-model { width: 1fr; }
    .df-effort { width: 18; }
    #df-head { height: 1; color: $text-muted; text-style: bold; margin-top: 1; }
    #df-box Checkbox { height: auto; border: none; margin-right: 2; }
    #df-checks { height: auto; margin-top: 1; }
    """

    def __init__(self, cfg: Config, in_setup: bool = False, name: str = ""):
        super().__init__()
        self.cfg, self.in_setup = cfg, in_setup
        self.form = wizard.flow_form(cfg, name)
        self.n = 0  # bộ đếm id hàng (vẽ lại khi đổi workflow)

    def compose(self) -> ComposeResult:
        with Vertical(id="df-box"):
            yield self.title_bar(tr("⚙ Luồng mặc định"))
            yield Static(Text(tr("Gõ mục tiêu (không kèm /goal) là chạy workflow này: mỗi bước một task, bước sau "
                                 "chờ bước trước. Chọn agent, model, effort cho từng bước — sửa tiêu đề/prompt hay "
                                 "thêm bước ở tab 🔀 Workflows."), "dim"))
            yield form_row("Workflow", Select([(lbl, n) for n, lbl in wizard.flow_names(self.cfg)],
                                              value=self.form["name"], allow_blank=False, id="df-name",
                                              classes="f-input"))
            with Horizontal(id="df-head"):
                yield Static(tr("Bước"), classes="df-title")
                yield Static("Agent", classes="df-agent")
                yield Static("Model", classes="df-model")
                yield Static("Effort", classes="df-effort")
            with VerticalScroll(classes="f-scroll"):
                yield Vertical(id="df-steps")
            with Horizontal(id="df-checks"):
                yield Checkbox(tr("Trưởng nhóm review khi xong"), self.form["review"], id="df-review")
                yield Checkbox(tr("Chạy khi gõ mục tiêu (luồng mặc định)"), True, id="df-default")
            with Horizontal(classes="f-buttons"):
                yield Btn(tr("Huỷ"), id="df-cancel")
                yield Btn(tr("Lưu (Ctrl+S)"), id="df-save", variant="primary")

    async def on_mount(self) -> None:
        self.query_one("#df-default").display = not self.in_setup
        await self.fill()
        self.query_one("#df-name", Select).focus()

    def _choices(self, agent: str, model: str, effort: str) -> tuple[list, list]:
        models, efforts = wizard.flow_step_choices(self.cfg, agent)
        if model and model not in models:
            models = [model] + models
        mopts = [(tr("(mặc định của agent)"), RESET)] + [(m, m) for m in models]
        eopts = [(tr("(mặc định)"), RESET)] + [(e, e) for e in efforts]
        return mopts, eopts

    async def fill(self) -> None:
        rows = []
        self.n += 1
        agents = wizard.flow_agents(self.cfg)
        for i, st in enumerate(self.form["steps"], 1):
            k = f"{self.n}-{i}"
            agent = st["agent"] if any(v == st["agent"] for _l, v in agents) else LEAD_ALIAS
            mopts, eopts = self._choices(agent, st["model"], st["effort"])
            effort = st["effort"] if any(v == st["effort"] for _l, v in eopts) else RESET
            rows.append(Horizontal(
                Static(f"{i}. {st['title']}", classes="df-title"),
                Select(agents, value=agent, allow_blank=False, id=f"df-agent-{k}", classes="df-agent"),
                Select(mopts, value=st["model"] or RESET, allow_blank=False, id=f"df-model-{k}", classes="df-model"),
                Select(eopts, value=effort, allow_blank=False, id=f"df-effort-{k}", classes="df-effort"),
                classes="df-row"))
        box = self.query_one("#df-steps", Vertical)
        await box.remove_children()
        await box.mount_all(rows)
        self.query_one("#df-review", Checkbox).value = self.form["review"]

    async def on_select_changed(self, event: Select.Changed) -> None:
        sid = event.select.id or ""
        if sid == "df-name":
            event.stop()
            if event.value != self.form["name"]:
                self.form = wizard.flow_form(self.cfg, str(event.value))
                await self.fill()
        elif sid.startswith("df-agent-"):  # đổi agent: nạp lại model/effort của bước đó
            event.stop()
            k = sid[len("df-agent-"):]
            mopts, eopts = self._choices(str(event.value), "", "")
            msel, esel = self.query_one(f"#df-model-{k}", Select), self.query_one(f"#df-effort-{k}", Select)
            msel.set_options(mopts)
            esel.set_options(eopts)
            msel.value, esel.value = RESET, RESET

    def values(self) -> list[dict]:
        out = []
        for i in range(1, len(self.form["steps"]) + 1):
            k = f"{self.n}-{i}"

            def val(wid: str) -> str:
                v = self.query_one(wid, Select).value
                return "" if v in (RESET, Select.BLANK, None) else str(v)
            out.append({"agent": val(f"#df-agent-{k}") or LEAD_ALIAS, "model": val(f"#df-model-{k}"),
                        "effort": val(f"#df-effort-{k}")})
        return out

    def action_save(self) -> None:
        make_default = None if self.in_setup else self.query_one("#df-default", Checkbox).value
        try:
            msg = wizard.save_flow(self.cfg, self.form["name"], self.values(),
                                   self.query_one("#df-review", Checkbox).value, make_default)
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        self.notify(msg)
        self.dismiss(self.form["name"])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "df-save":
            event.stop()
            self.action_save()
        elif event.button.id == "df-cancel":
            event.stop()
            self.dismiss(None)


class CustomPanel(Vertical):
    """Danh sách agent & workflow tuỳ chỉnh + nút Thêm/Sửa/Xoá. `show`: "agents" (tab 🤖 Agents), "flows"
    (tab 🔀 Workflows), "all" (popup /custom). Mỗi lần lưu ghi ngay vào custom.toml rồi gửi `CustomPanel.Changed`
    (bên chứa nạp lại cấu hình)."""

    DEFAULT_CSS = """
    CustomPanel { height: auto; }
    CustomPanel .c-intro { height: auto; color: $text-muted; }
    CustomPanel .f-scroll { height: auto; max-height: 34; }
    CustomPanel .f-section { height: 1; margin-top: 1; color: $text-muted; text-style: bold; }
    CustomPanel .c-row { height: 3; }
    CustomPanel .c-name { width: 22; padding: 1 0 0 1; text-style: bold; }
    CustomPanel .c-info { width: 1fr; height: 3; padding: 1 0 0 1; color: $text-muted;
                          text-wrap: nowrap; text-overflow: ellipsis; }
    CustomPanel .c-row Button { margin: 1 0 0 1; }
    CustomPanel .c-empty { height: 1; padding: 0 1; color: $text-muted; }
    CustomPanel .c-off { opacity: 60%; }
    CustomPanel #custom-agents, CustomPanel #custom-flows { height: auto; }
    CustomPanel .c-adds { height: auto; }
    CustomPanel .c-adds Button { margin: 0 0 0 1; }
    """

    class Changed(Message):
        def __init__(self, panel: "CustomPanel"):
            super().__init__()
            self.panel = panel

        @property
        def control(self) -> "CustomPanel":
            return self.panel

    def __init__(self, root: Path, cfg: Config, show: str = "all", **kw):
        super().__init__(**kw)
        self.root, self.cfg, self.show = root, cfg, show
        self.ids: dict[str, tuple[str, str]] = {}  # id nút -> (hành động, tên)
        self.armed: str | None = None  # nút xoá đang chờ bấm lần 2
        self._n = 0

    def compose(self) -> ComposeResult:
        if self.show == "agents":
            intro = tr("Agent mới tham gia đội như agent có sẵn (trưởng nhóm phân việc theo vai trò, bật/tắt ở "
                       "/setup). Lưu ở {CUSTOM_FILE}", CUSTOM_FILE=CUSTOM_FILE)
        elif self.show == "flows":
            intro = tr("Workflow chạy bằng /flow <tên> <mục tiêu>, hoặc ★ Mặc định để gõ mục tiêu là chạy luôn. "
                       "Agent tuỳ chỉnh nằm ở tab 🤖 Agents. Lưu ở {CUSTOM_FILE}", CUSTOM_FILE=CUSTOM_FILE)
        else:
            intro = tr("Agent mới tham gia đội như agent có sẵn (trưởng nhóm phân việc "
                       "theo vai trò, bật/tắt ở /setup). Workflow chạy bằng /flow <tên> "
                       "<mục tiêu>, hoặc ★ Mặc định để gõ mục tiêu là chạy luôn. Lưu ở {CUSTOM_FILE}", CUSTOM_FILE=CUSTOM_FILE)
        yield Static(Text(intro, "dim"), classes="c-intro")
        with VerticalScroll(classes="f-scroll"):
            if self.show != "flows":
                yield Static(tr("Agent tuỳ chỉnh"), classes="f-section")
                yield Vertical(id="custom-agents")
                with Horizontal(classes="c-adds"):
                    yield Btn(tr("+ Thêm agent"), id="custom-add-agent")
            if self.show != "agents":
                yield Static("Workflow", classes="f-section")
                yield Vertical(id="custom-flows")
                with Horizontal(classes="c-adds"):
                    yield Btn(tr("+ Thêm workflow"), id="custom-add-flow")
                    yield Btn(tr("⚙ Luồng mặc định"), id="custom-default-flow")

    async def on_mount(self) -> None:
        await self.refill()

    async def refill(self) -> None:
        self.cfg = load_config(self.root)
        self.ids.clear()
        self.armed = None

        def btn(label: str, action: str, name: str, variant: str = "default") -> Button:
            self._n += 1  # id mới mỗi lần vẽ lại (id cũ có thể chưa kịp gỡ)
            bid = f"c-btn-{self._n}"
            self.ids[bid] = (action, name)
            return Btn(label, id=bid, variant=variant)

        rows = []
        for name in sorted(self.cfg.custom_agents):
            a = self.cfg.agents[name]
            if self.show == "agents" and a.enabled:
                continue  # tab Agents: agent đang bật đã có dòng riêng (nút Sửa/Xoá ở đó), ở đây chỉ agent chưa bật
            ok = "✓" if a.installed() else tr("✗ chưa cài")
            off = tr("○ chưa bật (bật ở /setup) · ") if not a.enabled else ""
            rows.append(Horizontal(Static(name, classes="c-name"),
                                   Static(f"{off}{ok} · {' '.join(a.argv('<prompt>'))}", classes="c-info"),
                                   btn(tr("Sửa"), "edit-agent", name), btn(tr("Xoá"), "del-agent", name, "error"),
                                   classes="c-row c-off" if not a.enabled else "c-row"))
        if not rows and self.show != "agents":
            rows = [Static(tr("Chưa có. Bấm '+ Thêm agent' để thêm CLI bất kỳ (Gemini, Aider, "
                              "script riêng…)."),
                           classes="c-empty")]
        for box in self.query("#custom-agents").results(Vertical):
            await box.remove_children()
            await box.mount_all(rows)

        rows = []
        for name, w in self.cfg.workflows.items():
            info = tr("{v} bước: {v2}", v=len(w.steps), v2=w.summary()) + (f" · {w.description}" if w.description else "")
            if name == self.cfg.default_workflow:
                info = tr("★ mặc định · ") + info
            star = tr("☆ Bỏ mặc định") if name == self.cfg.default_workflow else tr("★ Mặc định")
            rows.append(Horizontal(Static(name, classes="c-name"), Static(info, classes="c-info"),
                                   btn(star, "default-flow", name),
                                   btn(tr("Sửa"), "edit-flow", name), btn(tr("Xoá"), "del-flow", name, "error"),
                                   classes="c-row"))
        if not rows:
            rows = [Static(tr("Chưa có. Bấm '+ Thêm workflow' (có mẫu: tính năng mới, sửa lỗi, "
                              "review)."),
                           classes="c-empty")]
        for box in self.query("#custom-flows").results(Vertical):
            await box.remove_children()
            await box.mount_all(rows)

    async def edit_agent(self, name: str) -> None:
        raw = (load_custom().get("agents") or {}).get(name, {})
        form = AgentQuickScreen if provider_of(raw.get("command")) else AgentEditScreen
        self.app.push_screen(form(self.cfg, name, raw), lambda r: self._saved("agents", r))

    async def delete_agent(self, name: str) -> None:
        """Xoá agent tuỳ chỉnh (nút ✗ Xoá trên dòng agent ở tab Agents): hỏi lại trước khi xoá."""
        if name == self.cfg.lead:
            self.notify(tr("'{name}' đang là trưởng nhóm — đổi trưởng nhóm ở /setup trước.", name=name), severity="error")
            return
        if name not in (load_custom().get("agents") or {}):
            self.notify(tr("'{name}' nằm trong file cấu hình khác ({v}) — sửa file đó để xoá.", name=name,
                           v=', '.join(map(str, self.cfg.sources))), severity="warning")
            return

        async def done(yes) -> None:
            if yes:
                save_custom_item("agents", name, None)
                self.notify(tr("Đã xoá '{name}'", name=name))
                await self.changed()
        self.app.push_screen(ConfirmScreen(tr("✗ Xoá agent"), tr("Xoá agent tuỳ chỉnh '{name}'?", name=name), tr("Xoá")),
                             done)

    async def _saved(self, kind: str, result) -> None:
        if not result:
            return
        name, body, old = result
        save_custom_item(kind, name, body, old)
        if kind == "agents":  # giá trị vừa đặt trong form phải có hiệu lực, không để state.json cũ đè
            clear_agent_state(name)
            if old and old != name:
                clear_agent_state(old, keys=("enabled", "model", "effort", "role", "full_access"))
        self.notify(tr("Đã lưu {v} '{name}'", v='agent' if kind == 'agents' else 'workflow', name=name))
        await self.changed()

    async def changed(self) -> None:
        self.post_message(self.Changed(self))
        await self.refill()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "custom-add-agent":
            event.stop()
            self.app.push_screen(AgentQuickScreen(self.cfg), lambda r: self._saved("agents", r))
            return
        if bid == "custom-add-flow":
            event.stop()
            self.app.push_screen(WorkflowEditScreen(self.cfg), lambda r: self._saved("workflows", r))
            return
        if bid == "custom-default-flow":
            event.stop()
            self.app.open_default_flow(self.changed)
            return
        if bid not in self.ids:
            return
        event.stop()
        action, name = self.ids[bid]
        custom = load_custom()
        if action == "edit-agent":
            await self.edit_agent(name)
        elif action == "edit-flow":
            raw = (custom.get("workflows") or {}).get(name)
            old: str | None = name
            if raw is None:  # workflow ghi trong config.toml / file dự án: lưu thành bản sao
                raw, old = workflow_to_dict(self.cfg.workflows[name]), None
                self.notify(tr("'{name}' nằm trong file cấu hình — lưu sẽ tạo bản sao với tên mới.", name=name))
            self.app.push_screen(WorkflowEditScreen(self.cfg, old, raw),
                                 lambda r: self._saved("workflows", r))
        elif action == "default-flow":  # gõ mục tiêu chạy workflow này (bấm lại: về trưởng nhóm)
            self.notify(wizard.set_input_mode(self.cfg, "" if name == self.cfg.default_workflow else name))
            await self.changed()
        elif action in ("del-agent", "del-flow"):
            kind = "agents" if action == "del-agent" else "workflows"
            if kind == "agents" and name == self.cfg.lead:
                self.notify(tr("'{name}' đang là trưởng nhóm — đổi trưởng nhóm ở /setup trước.", name=name),
                            severity="error")
                return
            if name not in (custom.get(kind) or {}):
                self.notify(tr("'{name}' nằm trong file cấu hình khác ({v}) — sửa file đó để xoá.", name=name, v=', '.join(map(str, self.cfg.sources))), severity="warning")
                return
            if self.armed != bid:  # bấm lần 2 mới xoá
                self.armed = bid
                event.button.label = tr("Chắc chưa?")
                return
            save_custom_item(kind, name, None)
            self.notify(tr("Đã xoá '{name}'", name=name))
            await self.changed()


class CustomScreen(BaseModal):
    """Popup /custom (hoặc nút ở màn hình thiết lập): bọc `CustomPanel`. Trả về True nếu có thay đổi."""

    DEFAULT_CSS = "CustomScreen { align: center middle; }" + FORM_CSS.replace("{box}", "custom-box")

    def __init__(self, root: Path, cfg: Config):
        super().__init__()
        self.root, self.cfg = root, cfg
        self.changed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="custom-box"):
            yield self.title_bar(tr("Agent & workflow tuỳ chỉnh"))
            yield CustomPanel(self.root, self.cfg)
            with Horizontal(classes="f-buttons"):
                yield Btn("Xong (Esc)", id="custom-close", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#custom-add-agent", Button).focus()

    def on_custom_panel_changed(self, event: CustomPanel.Changed) -> None:
        event.stop()  # đóng popup mới nạp lại cấu hình (TeamApp.open_custom)
        self.changed = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "custom-close":
            self.action_close()

    def close(self) -> None:
        self.dismiss(self.changed)

    def action_close(self) -> None:
        self.close()


class MentionList(OptionList):
    """Danh sách gợi ý file/thư mục nổi phía trên ô nhập khi gõ @."""

    can_focus = False

    def on_mount(self) -> None:
        self.border_title = tr("@ file / thư mục")
        self.border_subtitle = tr("↑↓ chọn · Tab/Enter chèn · Esc đóng")


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
            self.app.notify(tr("Đã dán ảnh {v}", v=clipboard.shorten(path, self.root)), timeout=3)
        elif self.app.clipboard:
            self.action_paste()  # chữ đã copy trong app (Ctrl+C / Ctrl+X) như Ctrl+V cũ
        else:
            self.app.notify(tr("Không dán được ảnh: {why}. Dán chữ bằng Cmd+V.", why=why),
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
        self.popup.border_subtitle = tr("↑↓ chọn · Tab/Enter chèn · Esc đóng")
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
        # tham số đầu là tên agent: /task (sau đó :model @effort), /focus, /chat (rồi tới tin nhắn), /grid (+ :shell)
        a = re.fullmatch(r"/(task|t|focus|chat|grid) ([^\s:@]*|:\S*)", before)
        if a and self.cursor_position == len(self.value) and (a.group(1) == "grid" or not a.group(2).startswith(":")):
            self._mode, self._span = "agent", (a.start(2), self.cursor_position)
            self._fill_agents(a.group(2), a.group(1))
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
        popup.border_title = tr("/ lệnh")
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
        popup.border_title = tr("! lệnh terminal")
        popup.border_subtitle = tr("↑↓ chọn rồi Enter chạy · Tab chèn để sửa · Esc đóng")
        popup.display = True

    def _fill_agents(self, query: str, cmd: str = "task") -> None:
        from .grid import SHELL
        agents = self.app.cfg.active_agents()
        if cmd == "grid":  # ô lưới: agent có CLI tương tác + terminal trống
            names = [SHELL] + [n for n, a in agents.items() if a.interactive_argv() is not None]
        else:
            names = list(agents)
        info = {n: (tr("terminal"), tr("shell của bạn trong thư mục dự án")) if n == SHELL
                else (agents[n].label(), agents[n].role) for n in names}
        q = query.lower()
        found = [n for n in names if n.lower().startswith(q)]
        found += [n for n in names if q in n.lower() and n not in found]
        if not found or found == [query]:  # gõ đủ tên rồi: không che ô nhập nữa
            self.close_popup()
            return
        popup = self.popup
        popup.clear_options()
        width = max(len(n) for n in found) + 2
        label_w = max(len(info[n][0]) for n in found) + 3
        room = min(90, self.app.size.width - 1) - 8  # #mention rộng 90, trừ viền, lề và thanh cuộn
        for n in found:
            t = Text()
            t.append(n.ljust(width), "bold cyan")
            t.append(info[n][0].ljust(label_w), "dim")
            t.append(info[n][1])
            t.truncate(max(room, width), overflow="ellipsis")  # vai trò dài: cắt "…", không gãy dòng
            popup.add_option(Option(t, id=n))
        popup.highlighted = 0
        popup.border_title = {"focus": tr("/focus — phóng to agent để chat riêng"),
                              "chat": tr("/chat — chọn agent rồi gõ tin nhắn"),
                              "grid": tr("/grid — mở CLI thật trong một ô lưới")}.get(cmd, tr("/task — chọn agent"))
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
        popup.border_title = tr("/continue — chọn mục tiêu (m) hoặc thread /task (t) để tiếp tục")
        popup.display = True

    def _fill(self, query: str) -> None:
        popup = self.popup
        popup.border_title = tr("@ file / thư mục")
        found = mentions.search(self.index.entries, query)
        popup.clear_options()
        if found:
            popup.add_options([Option(Text("📁 " + e, "bold cyan") if e.endswith("/")
                                      else Text("   " + e), id=e) for e in found])
            popup.highlighted = 0
        else:
            msg = tr("đang đọc danh sách file…") if not self.index.loaded_at else tr("không có file nào khớp")
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
        tasks = [t for t in app.snap_tasks() if t.started and t.started > now - 3 * 3600]
        spans = [s for s in app.orch.lead_spans if s[0] > now - 3 * 3600]
        out = Text()
        out.append("⏱ Timeline", "bold")
        if not tasks and not spans:
            out.append(tr("  — chưa có hoạt động"), "dim")
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

        out.append(tr("   {v} → bây giờ ({v2})", v=time.strftime('%H:%M:%S', time.localtime(t0)), v2=fmt_dur(t1 - t0)), "dim")
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
        for label, st in ((tr("█ đang chạy"), RUNNING), (tr("█ xong"), "green"), (tr("█ lỗi"), "red"),
                          (tr("▒ trưởng nhóm lập kế hoạch/review"), "yellow")):
            out.append(label + "   ", st)
        return out


class ThemeScreen(BaseModal):
    """Chọn theme màu (/theme): danh sách theme bên trái, màu nhấn bên phải, xem trước trực tiếp khi di
    chuyển. Enter/Lưu ghi vào state.json; Esc trả lại theme cũ."""

    DEFAULT_CSS = """
    ThemeScreen { align: center middle; }
    #th-box { width: 96; max-width: 100%; height: auto; max-height: 90%; padding: 0 1;
              border: round $primary 70%; background: $surface; }
    #th-cols { height: auto; }
    #th-list { width: 1fr; height: auto; max-height: 24; border: none; }
    #th-accent { width: 30; height: auto; max-height: 24; border: none; margin-left: 2; }
    #th-sample { height: auto; margin-top: 1; padding: 0 1; background: $boost; }
    #th-hint { height: auto; color: $text-muted; margin-top: 1; }
    #th-buttons { height: auto; margin-top: 1; align: right middle; }
    #th-buttons Button { margin-left: 2; }
    """

    def __init__(self, base: str, accent: str):
        super().__init__()
        self.orig = (base, accent)
        self.base, self.accent = base, accent
        self.names = theme.theme_names()
        self.accents = [""] + list(theme.ACCENTS)

    def compose(self) -> ComposeResult:
        opts: list = []
        dark_done = False
        opts.append(Option(Text(tr("Tối"), "bold dim"), disabled=True))
        for n in self.names:
            if not theme.is_dark(n) and not dark_done:
                opts.append(Option(Text(tr("Sáng"), "bold dim"), disabled=True))
                dark_done = True
            opts.append(Option(n, id=f"t:{n}"))
        acc = []
        for k in self.accents:
            t = Text()
            t.append("■ ", theme.ACCENTS.get(k, "dim"))
            t.append(theme.accent_label(k))
            acc.append(Option(t, id=f"a:{k}"))
        with Vertical(id="th-box", classes="m-box"):
            yield self.title_bar(tr("🎨 Theme màu"))
            with Horizontal(id="th-cols"):
                yield OptionList(*opts, id="th-list")
                yield OptionList(*acc, id="th-accent")
            yield Static(id="th-sample")
            yield Static(tr("↑↓ xem trước · Tab sang cột màu nhấn · Enter lưu · Esc huỷ (trả theme cũ)"),
                         id="th-hint")
            with Horizontal(id="th-buttons", classes="m-buttons"):
                yield Btn(tr("Huỷ"), id="th-cancel")
                yield Btn(tr("✓ Lưu theme"), id="th-save", variant="success")

    def on_mount(self) -> None:
        tl = self.query_one("#th-list", OptionList)
        ids = [tl.get_option_at_index(i).id for i in range(tl.option_count)]
        if f"t:{self.base}" in ids:
            tl.highlighted = ids.index(f"t:{self.base}")
        al = self.query_one("#th-accent", OptionList)
        al.highlighted = self.accents.index(self.accent) if self.accent in self.accents else 0
        tl.focus()
        self.draw_sample()

    def draw_sample(self) -> None:
        t = Text()
        t.append(tr("Xem trước: "), "bold")
        for key in ("running", "done", "failed", "review", "queued"):
            label, style = STATUS[key]
            t.append(f" {STATUS_ICON.get(key, '●')} {label} ", style)
        t.append("\n")
        t.append(tr("Theme: "), "dim")
        t.append(theme.theme_id(self.base, self.accent), "bold")
        set_static(self.query_one("#th-sample", Static), t)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()
        oid = event.option.id or ""
        if oid.startswith("t:"):
            self.base = oid[2:]
        elif oid.startswith("a:"):
            self.accent = oid[2:]
        else:
            return
        self.app.apply_theme(self.base, self.accent)
        self.draw_sample()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.save()

    def save(self) -> None:
        self.app.apply_theme(self.base, self.accent, save=True)
        self.dismiss(theme.theme_id(self.base, self.accent))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "th-save":
            event.stop()
            self.save()
        elif event.button.id == "th-cancel":
            event.stop()
            self.close()

    def close(self) -> None:
        self.app.apply_theme(*self.orig)
        self.dismiss(None)


PLAN_SOURCES = [("plan", tr("Kế hoạch ban đầu")), ("workflow", tr("Theo workflow")),
                ("review", tr("Bổ sung khi review")), ("followup", tr("Tiếp tục / làm thêm")),
                ("delegate", tr("Giao việc chéo")), ("user", tr("Thêm tay"))]


class PlanViewScreen(BaseModal):
    """📋 Kế hoạch của một mục tiêu, xem lại cả khi đã duyệt / xong (/plan) — như popup 📋 của web, đọc từ trên
    xuống: đề bài → kế hoạch của trưởng nhóm (bảng các bước) → kết quả từng agent (markdown đầy đủ) → tổng kết.
    Phím p: hiện / ẩn prompt giao cho từng agent."""

    BINDINGS = [Binding("p", "toggle_prompts", tr("Prompt"))]
    DEFAULT_CSS = """
    PlanViewScreen { align: center middle; }
    #pv-box { width: 124; max-width: 100%; height: 92%; border: round $primary 70%; background: $surface; padding: 0 1; }
    #pv-body { height: 1fr; }
    #pv-foot { height: 1; color: $text-muted; }
    """

    def __init__(self, goal, tasks: list):
        super().__init__()
        self.goal, self.tasks, self.prompts = goal, tasks, False
        self.doc = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="pv-box"):
            yield self.title_bar(tr("📋 Kế hoạch mục tiêu #{id}", id=self.goal.id))
            with VerticalScroll(id="pv-body"):
                yield Static(id="pv-text")
            yield Static(tr("↑↓ / PgUp PgDn cuộn · p hiện/ẩn prompt · Esc đóng"), id="pv-foot")

    def build(self) -> str:
        """Cả popup dạng markdown (rich vẽ bảng, tiêu đề, code…)."""
        cell = (lambda v: str(v).replace("|", "\\|").replace("\n", " "))
        status = (lambda t: f"{STATUS_ICON.get(t.status, '●')} {STATUS.get(t.status, (t.status, ''))[0]}")
        out = [self.goal.text.strip(), ""]
        if not self.tasks:
            out.append(tr("Mục tiêu này chưa có task nào"))
        else:
            src = dict(PLAN_SOURCES)
            out += [f"## 📋 {tr('Kế hoạch của trưởng nhóm')}", "",
                    f"| # | Agent | {tr('Việc')} | {tr('Chạy sau')} | {tr('Trạng thái')} |", "|---|---|---|---|---|"]
            for t in self.tasks:
                k = (t.source or "plan").split(":")[0]
                note = f" _({src[k]}{' ← ' + t.source[9:] if t.source.startswith('delegate:') else ''})_" \
                    if k in src and k not in ("plan", "workflow") else ""
                out.append(f"| #{t.id} | {cell(t.agent)} | {cell(t.title)}{note} | "
                           f"{', '.join(f'#{d}' for d in t.depends_on)} | {status(t)} |")
            out += ["", f"## 🤖 {tr('Kết quả từng agent')}"]
            for t in self.tasks:
                meta = " · ".join(x for x in (t.model, t.effort) if x)
                dur = fmt_dur((t.finished or time.time()) - t.started) if t.started else ""
                out += ["", f"### #{t.id} · {t.agent} — {t.title}",
                        f"_{status(t)}{' · ' + dur if dur else ''}{' · ' + meta if meta else ''}_", "",
                        (t.result or t.error or tr("Chưa có kết quả.")).strip()]
                if self.prompts:
                    out += ["", "**Prompt:**", "", "\n".join("> " + ln for ln in (t.prompt or "").splitlines())]
        if self.goal.summary:
            out += ["", "---", "", f"## ✔ {tr('Tổng kết của trưởng nhóm')}", "", self.goal.summary.strip()]
        return "\n".join(out)

    def on_mount(self) -> None:
        self.render_doc()
        self.query_one("#pv-body").focus()

    def render_doc(self) -> None:
        from rich.markdown import Markdown
        self.doc = self.build()
        self.query_one("#pv-text", Static).update(Markdown(self.doc))

    def action_toggle_prompts(self) -> None:
        self.prompts = not self.prompts
        self.render_doc()


class SearchList(OptionList):
    BINDINGS = [Binding("r", "replace_file", tr("Thay trong file")), Binding("x", "hide_file", tr("Bỏ file")),
                Binding("tab", "app.focus_next", show=False)]

    def action_replace_file(self) -> None:
        self.screen.replace_current()  # type: ignore[attr-defined]

    def action_hide_file(self) -> None:
        self.screen.hide_current()  # type: ignore[attr-defined]


class SearchScreen(BaseModal):
    """🔍 Tìm & thay trong toàn dự án (F3, /search) — như ô Search của VS Code và mục 🔍 Tìm ở tab Code của web;
    logic ở search.py. Gõ là tìm; có chữ ở ô "Thay bằng" thì kết quả hiện chữ cũ → mới. Enter trên một dòng:
    đóng và mở file đúng chỗ đó ở tab 📝 Code. Trả về (đường dẫn, dòng, cột) hoặc None."""

    BINDINGS = [Binding("ctrl+r", "replace_all", tr("Thay tất cả"), priority=True)]
    DEFAULT_CSS = """
    SearchScreen { align: center middle; }
    #sr-box { width: 130; max-width: 100%; height: 92%; border: round $primary 70%; background: $surface; padding: 0 1; }
    #sr-box .sr-row { height: 3; }
    #sr-box #sr-q, #sr-box #sr-r { width: 1fr; }
    #sr-box Checkbox { width: auto; border: none; padding: 0 1; margin-top: 0; }
    #sr-box #sr-inc, #sr-box #sr-exc { width: 1fr; }
    #sr-sum { height: 1; color: $text-muted; margin-top: 1; }
    #sr-list { height: 1fr; border: none; }
    #sr-foot { height: 1; color: $text-muted; }
    """

    def __init__(self, state: dict):
        super().__init__()
        self.state = state  # app giữ lại giữa các lần mở: query, replace, case, word, regex, include, exclude
        self.res: dict | None = None
        self.hidden: set[str] = set()
        self._timer = None

    def compose(self) -> ComposeResult:
        st = self.state
        with Vertical(id="sr-box"):
            yield self.title_bar(tr("🔍 Tìm & thay trong dự án"))
            with Horizontal(classes="sr-row"):
                yield TextInput(st.get("query", ""), placeholder=tr("Tìm…"), id="sr-q")
                yield Checkbox("Aa", st.get("case", False), id="sr-case", tooltip=tr("Phân biệt hoa/thường"))
                yield Checkbox(tr("Nguyên từ"), st.get("word", False), id="sr-word")
                yield Checkbox("Regex", st.get("regex", False), id="sr-regex")
            with Horizontal(classes="sr-row"):
                yield TextInput(st.get("replace", ""), placeholder=tr("Thay bằng… (để trống: chỉ tìm)"), id="sr-r")
            with Horizontal(classes="sr-row"):
                yield TextInput(st.get("include", ""), placeholder=tr("File gồm — vd src, *.ts"), id="sr-inc")
                yield TextInput(st.get("exclude", ""), placeholder=tr("File bỏ qua — vd *.test.ts, dist"), id="sr-exc")
            yield Static(id="sr-sum")
            yield SearchList(id="sr-list")
            yield Static(tr("Enter mở file · Tab sang kết quả · r thay trong file · x bỏ file · Ctrl+R thay tất cả · "
                            "Esc đóng"), id="sr-foot")

    def on_mount(self) -> None:
        q = self.query_one("#sr-q", TextInput)
        q.focus()
        if q.value:
            self.run_search()

    # ---------------------------------------------------------------- tìm
    def opts(self) -> dict:
        return {k: self.query_one(f"#sr-{k}", Checkbox).value for k in ("case", "word", "regex")}

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        if self._timer:
            self._timer.stop()
        self._timer = self.set_timer(0.3, self.run_search)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        event.stop()
        self.run_search()

    def run_search(self) -> None:
        st = self.state
        st.update(query=self.query_one("#sr-q", Input).value, replace=self.query_one("#sr-r", Input).value,
                  include=self.query_one("#sr-inc", Input).value, exclude=self.query_one("#sr-exc", Input).value,
                  **self.opts())
        self.run_worker(self._search(), exclusive=True, group="sr")

    async def _search(self) -> None:
        st = self.state
        self.hidden.clear()
        if not st["query"]:
            self.res = None
            self.render_results()
            return
        self.query_one("#sr-sum", Static).update(Text(tr("Đang tìm…"), "dim"))
        files = await self.app.search_files()  # type: ignore[attr-defined]
        try:
            self.res = await asyncio.to_thread(
                search.search, self.app.root, files, st["query"], include=st["include"],  # type: ignore[attr-defined]
                exclude=st["exclude"], replace=st["replace"] or None, **self.opts())
        except ValueError as e:
            self.res = {"error": tr("Regex không hợp lệ: {e}", e=e)}
        self.render_results()

    def render_results(self) -> None:
        ol = self.query_one("#sr-list", SearchList)
        sum_ = self.query_one("#sr-sum", Static)
        ol.clear_options()
        r = self.res
        if not r:
            sum_.update("")
            return
        if r.get("error"):
            sum_.update(Text(r["error"], PAL.get("err", "red")))
            return
        files = [f for f in r["files"] if f["path"] not in self.hidden]
        n = sum(len(f["matches"]) for f in files)
        if not files:
            sum_.update(Text(tr("Không có kết quả"), "dim"))
            return
        t = Text(tr("{n} kết quả trong {f} file", n=n, f=len(files)))
        if r.get("truncated"):
            t.append(" · " + tr("quá nhiều, chỉ hiện phần đầu — thu hẹp tìm kiếm"), PAL.get("warn", "yellow"))
        sum_.update(t)
        rep = bool(self.state.get("replace"))
        opts: list = []
        for f in files:
            name = f["path"].rsplit("/", 1)[-1]
            head = Text(no_wrap=True, overflow="ellipsis")
            head.append(f"{name}  ", "bold")
            head.append(f["path"][:-len(name)].rstrip("/") + "  ", "dim")
            head.append(f"{len(f['matches'])}", "bold cyan")
            opts.append(Option(head, id="F" + f["path"]))
            for i, m in enumerate(f["matches"]):
                pre = m["text"][:m["s"]].lstrip()
                pre = "…" + pre[-30:] if len(pre) > 32 else pre
                line = Text(no_wrap=True, overflow="ellipsis")
                line.append(f"  {m['line']:>5}  ", "dim")
                line.append(pre)
                hit = m["text"][m["s"]:m["e"]]
                if rep:
                    line.append(hit, f"strike {PAL.get('err', 'red')}")
                    line.append(m.get("repl", ""), f"bold {PAL.get('ok', 'green')}")
                else:
                    line.append(hit, f"bold reverse {PAL.get('warn', 'yellow')}")
                line.append(m["text"][m["e"]:])
                opts.append(Option(line, id=f"M{i}:{f['path']}"))
        ol.add_options(opts)

    def _at(self) -> tuple[str, dict | None]:
        """(đường dẫn, chỗ khớp hoặc None nếu đang ở dòng tên file) của dòng đang chọn."""
        ol = self.query_one("#sr-list", SearchList)
        if ol.highlighted is None or not ol.option_count:
            return "", None
        oid = ol.get_option_at_index(ol.highlighted).id or ""
        if oid.startswith("F"):
            return oid[1:], None
        idx, _, path = oid[1:].partition(":")
        f = next((x for x in (self.res or {}).get("files", []) if x["path"] == path), None)
        return path, (f["matches"][int(idx)] if f else None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        path, m = self._at()
        if path:
            self.dismiss((path, m["line"] if m else 1, m["col"] if m else 0))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.query_one("#sr-list", SearchList).focus()

    # ---------------------------------------------------------------- thay
    def visible(self) -> list[str]:
        return [f["path"] for f in (self.res or {}).get("files", []) if f["path"] not in self.hidden]

    def hide_current(self) -> None:
        path, _m = self._at()
        if path:
            self.hidden.add(path)
            self.render_results()

    def replace_current(self) -> None:
        path, _m = self._at()
        if path:
            self.replace_files([path])

    def action_replace_all(self) -> None:
        self.replace_files(self.visible())

    def replace_files(self, paths: list[str]) -> None:
        st = self.state
        if not st.get("query") or not paths or self.res is None or self.res.get("error"):
            return
        if not st.get("replace"):
            self.notify(tr("Gõ chữ thay thế ở ô \"Thay bằng\" trước"), severity="warning")
            self.query_one("#sr-r", Input).focus()
            return
        dirty = set(self.app.code_unsaved())  # type: ignore[attr-defined]
        skip = [p for p in paths if p in dirty]
        if skip:
            self.notify(tr("Bỏ qua file đang sửa dở (chưa lưu): {v}", v=", ".join(skip)), severity="warning")
        paths = [p for p in paths if p not in dirty]
        if not paths:
            return
        n = sum(len(f["matches"]) for f in self.res["files"] if f["path"] in paths)

        async def go(ok) -> None:
            if not ok:
                return
            try:
                res = await asyncio.to_thread(search.replace_in, self.app.root,  # type: ignore[attr-defined]
                                              paths, st["query"], st["replace"], **self.opts())
            except (ValueError, OSError) as e:
                self.notify(str(e), severity="error")
                return
            self.notify(tr("Đã thay {n} kết quả trong {f} file", n=res["total"], f=len(res["files"])))
            await self.app.after_replace(list(res["files"]), st, res["total"])  # type: ignore[attr-defined]
            self.run_search()

        self.app.push_screen(ConfirmScreen(
            tr("Thay tất cả"), tr("Thay {n} kết quả trong {f} file bằng \"{r}\"? App không hoàn tác được — xem lại "
                                 "bằng git diff.", n=n, f=len(paths), r=st["replace"]), tr("Thay tất cả")), go)

    def close(self) -> None:
        self.dismiss(None)


class StatusBar(Static):
    """Thanh trạng thái phía trên Footer: nhánh git, số task theo trạng thái, agent đang nghỉ, theme,
    ngôn ngữ. Bấm vào theme / ngôn ngữ để đổi."""

    def build(self, app: "TeamApp") -> Text:
        t = Text()
        sep = ("  │  ", "dim")
        if app.busy_ops:  # đầu thanh cho dễ thấy; mất khi thao tác xong
            t.append(f"{SPIN[app._frame]} " + "  ·  ".join(app.busy_ops.values()), f"bold {RUNNING}")
            t.append(*sep)
        st = app.git_status
        if st is not None and st.is_repo:
            t.append("⎇ ", "bold")
            t.append(st.branch or (st.oid[:8] if st.oid else "—"), "bold")
            if st.ahead:
                t.append(f" ↑{st.ahead}", STATUS["review"][1])
            if st.behind:
                t.append(f" ↓{st.behind}", STATUS["queued"][1])
            if st.files:
                t.append(f" ±{len(st.files)}", "dim")
            t.append(*sep)
        tasks = app.snap_tasks()
        counts = {}
        for x in tasks:
            counts[x.status] = counts.get(x.status, 0) + 1
        shown = False
        for key in ("running", "queued", "asking", "review", "failed"):
            n = counts.get(key, 0)
            if n:
                icon = SPIN[app._frame] if key == "running" else STATUS_ICON.get(key, "·")
                label, style = STATUS[key]
                t.append(f"{icon} {n} {label}", style)
                t.append("  ")
                shown = True
        if not shown:
            t.append(tr("○ rảnh"), "dim")
            t.append("  ")
        if app.orch.paused:
            t.append(tr("⏸ tạm dừng"), STATUS["review"][1])
            t.append("  ")
        resting = [a for a in app.cfg.active_agents() if app.orch.in_cooldown(a)]
        if resting:
            t.append(tr("⏸ nghỉ: {v}", v=", ".join(resting)), STATUS["conflict"][1])
        t.append(*sep)
        t.append(f"🎨 {app.theme}", Style(meta={"@click": "app.open_theme"}))
        t.append("  ")
        t.append(f"🌐 {get_lang().upper()}", Style(bold=True, meta={"@click": "app.toggle_lang"}))
        return t


def hang(text: str, width: int, indent: int, first: int = 0) -> str:
    """Xuống hàng theo `width` cột, các dòng sau thụt `indent` khoảng trắng (thẳng với chữ dòng đầu,
    dòng đầu đã bắt đầu ở cột `first`)."""
    import textwrap
    lines = textwrap.wrap(text, width=max(20, width - indent), break_long_words=False,
                          initial_indent=" " * max(0, first - indent)) or [""]
    lines[0] = lines[0][max(0, first - indent):]
    return ("\n" + " " * indent).join(lines)


class GrillBar(Vertical):
    """Khung hỏi đáp (/grill): câu hỏi hiện tại của trưởng nhóm, các phương án gợi ý (bấm hoặc gõ số),
    nút chốt / để trưởng nhóm tự quyết / hỏi lại / bỏ. Câu trả lời gõ ở ô nhập chính.
    Cũng dùng cho câu hỏi agent gửi giữa task (<<<ASK>>>, task_id đặt) khi không có /grill nào đang chạy."""

    BINDINGS = [Binding("escape", "leave", show=False)]

    def __init__(self, **kw):
        super().__init__(**kw)
        self.goal_id: int | None = None
        self.task_id: int | None = None  # câu hỏi của agent trong task này (<<<ASK>>>)
        self.question: dict | None = None  # câu đang chờ trả lời (None: trưởng nhóm đang nghĩ / lỗi)
        self._sig: tuple = ()

    def compose(self) -> ComposeResult:
        yield Static(id="grill-head")
        yield Static(id="grill-q")
        with Horizontal(id="grill-buttons"):
            yield Btn(tr("✓ Đủ rồi — chốt & lập kế hoạch"), id="grill-done", variant="success")
            yield Btn(tr("⏭ Để trưởng nhóm tự quyết"), id="grill-skip")
            yield Btn(tr("↻ Hỏi tiếp"), id="grill-retry")
            yield Btn(tr("✗ Bỏ mục tiêu"), id="grill-cancel", variant="error")
            yield Btn(tr("⏭ Để agent tự quyết"), id="grill-askskip")
            yield Btn(tr("📜 Xem task"), id="grill-askview")
            yield Btn(tr("✗ Huỷ task"), id="grill-askcancel", variant="error")

    def _buttons(self, ask: bool) -> None:
        for b in ("grill-done", "grill-skip", "grill-retry", "grill-cancel"):
            self.query_one(f"#{b}", Button).display = not ask
        for b in ("grill-askskip", "grill-askview", "grill-askcancel"):
            self.query_one(f"#{b}", Button).display = ask

    def _question(self, q: dict, label: str, width: int) -> Text:
        # chữ thường trên nền mặc định: nền màu + chữ đen (bản trước) gần như không đọc được trên
        # Terminal.app 256 màu và loang cả khối khi dòng dài xuống hàng. Dòng dài thụt lề thẳng chữ.
        body = Text()
        body.append(label, "bold yellow")
        body.append(hang(q.get("q", ""), width, len(label) + 1, first=len(label) + 1), "bold")
        if q.get("why"):
            body.append("\n   ")
            body.append(hang(q["why"], width, 3, first=3), "italic dim")
        rec = q.get("rec")
        if q.get("options"):
            body.append("\n")  # dòng trống tách câu hỏi với các phương án
        for i, opt in enumerate(q.get("options") or [], 1):
            click = {"@click": f"app.grill_pick({i})"}
            body.append("\n   ")
            body.append(f"{i}. ", Style(color="green" if opt == rec else "cyan", bold=True))
            body.append(hang(opt, width, 6, first=6), Style(meta=click, bold=opt == rec))
            if opt == rec:
                body.append(tr("  ★ khuyên dùng"), "bold green")
        if rec and rec not in (q.get("options") or []):
            body.append("\n   ")
            body.append(tr("★ khuyên dùng: "), "bold green")
            body.append(hang(rec, width, 18, first=18))
        body.append(tr("\n   Gõ câu trả lời ở ô dưới rồi Enter · gõ số (1, 2…) hoặc bấm vào "
                       "phương án để chọn"),
                    "dim")
        return body

    def update_ask(self, v: dict) -> bool:
        """Câu hỏi của agent giữa task (<<<ASK>>>). True khi vừa có câu hỏi mới."""
        q = v["question"]
        is_new = self.task_id != v["task"] or self.question is None or self.question.get("q") != q.get("q")
        self.goal_id, self.task_id, self.question = None, v["task"], q
        self.display = True
        sig = ("ask", v["task"], q.get("q"), self.size.width)
        if sig == self._sig:
            return False
        self._sig = sig
        head = Text()
        head.append(tr("❓ {agent} hỏi · task #{tid} ", agent=v["agent"], tid=v["task"]), "bold")
        head.append(v["title"][:160])
        if v["others"] > 0:
            head.append(tr(" · còn {others} task khác đang hỏi", others=v["others"]), "dim")
        self.query_one("#grill-head", Static).update(head)
        width = max(40, (self.size.width or 120) - 4)
        self.query_one("#grill-q", Static).update(self._question(q, tr("❓ Câu {v}: ", v=v["n"]), width))
        self._buttons(True)
        return is_new

    def update_grill(self, app: "TeamApp") -> bool:
        """Vẽ lại theo DB (Orchestrator.waiting_view: câu /grill chờ trả lời > câu <<<ASK>>> > trạng thái /grill).
        Trả về True khi vừa có câu hỏi MỚI (để app báo và đưa con trỏ về ô nhập)."""
        v = app.orch.waiting_view(app.snap_goals(), app.snap_tasks())
        if not v:
            self.goal_id = self.task_id = self.question = None
            self._sig = ()
            self.display = False
            return False
        if v["kind"] == "ask":
            return self.update_ask(v)
        self.task_id = None
        self._buttons(False)
        busy, q, err = v["busy"], v["question"], v["error"]
        sig = (v["goal"], v["n"], q is None, err, busy, app._frame if busy else 0, self.size.width)
        is_new = q is not None and (self.question is None or self.goal_id != v["goal"]
                                    or self.question.get("q") != q.get("q"))
        self.goal_id, self.question = v["goal"], q
        self.display = True
        if sig == self._sig:
            return False
        self._sig = sig
        head = Text()
        head.append(f"🎯 #{v['goal']} ", "bold")
        head.append(v["text"].splitlines()[0][:160] if v["text"] else "")
        head.append(tr("   · đã trả lời {n_answered} câu", n_answered=v["answered"]), "dim")
        if v["others"] > 0:
            head.append(tr(" · còn {others} mục tiêu khác đang hỏi đáp (hiện sau khi xong mục tiêu "
                           "này)", others=v["others"]), "dim")
        self.query_one("#grill-head", Static).update(head)
        body = Text()
        if busy:
            body.append(tr("{v} {lead} đang nghĩ câu hỏi tiếp theo…", v=SPIN[app._frame], lead=app.cfg.lead), f"bold {RUNNING}")
        elif err:
            body.append(f"⚠ {err}", "bold red")
        elif q:
            body = self._question(q, tr("❓ Câu {v}: ", v=v["n"]), max(40, (self.size.width or 120) - 4))
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
            yield Btn(tr("▶ Duyệt & chạy  F2"), id="plan-approve", variant="success")
            yield Btn(tr("✎ Sửa task"), id="plan-edit")
            yield Btn(tr("⇄ Đổi agent"), id="plan-assign")
            yield Btn(tr("✗ Bỏ kế hoạch"), id="plan-discard", variant="error")
        yield Static(tr("↑↓ xem từng task · Enter: sửa nội dung · Tab: chuyển nút · Esc: về ô nhập"),
                     id="plan-hint")

    def update_plan(self, app: "TeamApp") -> bool:
        """Vẽ lại theo DB. Trả về True nếu vừa có kế hoạch MỚI cần duyệt (để app chuyển focus)."""
        waiting = [g for g in app.snap_goals() if g.status == "awaiting"]
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
        head.append(tr("📋 Kế hoạch chờ duyệt "), "bold yellow")
        head.append(f"#{g.id}", "bold")
        if g.round > 1:
            head.append(tr(" · vòng {round}", round=g.round), "yellow")
        head.append(f" · {len(tasks)} task", "yellow")
        if len(waiting) > 1:
            head.append(tr(" · còn {v} kế hoạch khác sau", v=len(waiting) - 1), "dim")
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
            box.update(Text(tr("(kế hoạch không có task nào)"), "dim"))
            return
        a = app.cfg.agents.get(t.agent)
        text = Text()
        text.append(f"#{t.id} ", "bold")
        text.append(t.agent, "bold cyan")
        if a:
            text.append(f"  {a.label(t.model, t.effort)}", "dim")
        if t.depends_on:
            text.append(tr("  ⟵ chạy sau #{v}", v=', #'.join(map(str, t.depends_on))), "dim")
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
        Binding("q", "close", tr("Đóng")),
        Binding("n,j", "move(1)", tr("File kế"), show=False),
        Binding("p,k", "move(-1)", tr("File trước"), show=False),
        Binding("right_square_bracket", "hunk(1)", tr("Đoạn kế"), show=False),
        Binding("left_square_bracket", "hunk(-1)", tr("Đoạn trước"), show=False),
        Binding("s", "toggle_split", tr("Đổi kiểu"), show=False),
        Binding("o", "open_code", "VS Code", show=False),
        Binding("e", "edit_file", tr("Sửa file"), show=False),
        Binding("pagedown,space", "page(1)", show=False),
        Binding("pageup", "page(-1)", show=False),
    ]
    DEFAULT_CSS = """
    DiffScreen { background: $background; }
    #diff-top { height: auto; background: $boost; }
    #diff-head { width: 1fr; height: auto; padding: 0 1; }
    #diff-main { height: 1fr; }
    #diff-files { width: 30%; min-width: 24; max-width: 60; border: none; border-right: solid $foreground 15%; }
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
            yield Btn(tr("✕ Đóng"), classes="m-close")
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
        keys = tr("↑↓ chọn file · ] [ đoạn kế/trước · s hai cột/một cột · PgUp/PgDn cuộn")
        keys += tr(" · o mở VS Code") if self.has_code else ""
        task = self.app.db.task(ds.tid)
        if task and task.status in ("review", "conflict"):
            keys += " · Ctrl+Y merge"
        head.append(tr("\n{keys} · Esc đóng", keys=keys), "dim")
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
        title.append("   " + (tr("hai cột") if self.is_split() else tr("một cột")), "dim")
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

    def action_edit_file(self) -> None:
        """Mở file đang xem trong tab 📝 Code, tại dòng của đoạn đổi đang ở đầu màn hình."""
        fd = self.current
        if fd is None or fd.status == "D":
            self.app.notify(tr("File đã bị xoá — không có gì để sửa"), severity="warning")
            return
        y = self.query_one("#diff-scroll", VerticalScroll).scroll_y
        idx = max([i for i, st in enumerate(self._starts) if st <= y + 0.5] or [0])
        line = None
        if fd.hunks:
            hunk = fd.hunks[min(idx, len(fd.hunks) - 1)]
            # dòng thêm/sửa đầu tiên của đoạn (không có thì dòng ngữ cảnh đầu)
            line = next((ln.new_no for ln in hunk.lines if ln.kind == "+" and ln.new_no), None) or \
                next((ln.new_no for ln in hunk.lines if ln.new_no), None)
        self.dismiss(None)
        self.app.open_code(fd.path, line)

    async def action_open_code(self) -> None:
        if not self.has_code:
            self.app.notify(tr("Không thấy lệnh 'code' — trong VS Code: Shell Command: Install "
                               "'code' command"),
                            severity="warning")
            return
        fd = self.current
        old, new = await self.app.orch.diff_versions(self.ds, fd)
        proc = await asyncio.create_subprocess_exec(
            "code", "--diff", str(old), str(new), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        self.app.notify(tr("Đang mở {path} trong VS Code…", path=fd.path), timeout=3)
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

    def __init__(self, title: str, body: str, yes: str = tr("Đồng ý")):
        super().__init__()
        self.title_text, self.body, self.yes = title, body, yes

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield self.title_bar(self.title_text)
            yield Static(self.body, id="confirm-body")
            with Horizontal(id="confirm-buttons"):
                yield Btn(tr("Huỷ (n)"), id="confirm-no")
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


class PromptScreen(BaseModal):
    """Hỏi một dòng chữ (tên file mới, câu hỏi cho agent…). Trả về chữ đã gõ (đã strip, khác rỗng) hoặc None."""

    DEFAULT_CSS = """
    PromptScreen { align: center middle; }
    #prompt-box { width: 90; max-width: 100%; height: auto; border: round $primary 70%; background: $surface;
                  padding: 0 1; }
    #prompt-hint { height: auto; color: $text-muted; margin-top: 1; }
    """

    def __init__(self, title: str, value: str = "", placeholder: str = "", hint: str = "", allow_empty: bool = False):
        super().__init__()
        self.title_text, self.value, self.placeholder, self.hint = title, value, placeholder, hint
        self.allow_empty = allow_empty  # True: Enter trên ô trống trả "" (vd. bỏ hạn / bỏ hết tag)

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-box"):
            yield self.title_bar(self.title_text)
            yield TextInput(self.value, placeholder=self.placeholder, id="prompt-in")
            yield Static(self.hint or tr("Enter xong · Esc huỷ"), id="prompt-hint")

    def on_mount(self) -> None:
        self.query_one("#prompt-in", TextInput).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        text = event.value.strip()
        if text or self.allow_empty:
            self.dismiss(text)


class TextAreaVN(TextArea):
    """Ô soạn nhiều dòng gõ tiếng Việt không lỗi dấu — cùng cách xử lý với TextInput: nuốt ký tự mồi U+202F của
    OpenKey cùng Backspace theo sau, Backspace xoá trọn chữ cùng dấu (xử lý ngay trong `_on_key`), gộp dòng đang
    sửa về dạng dựng sẵn (NFC)."""

    IME_PLACEHOLDER = TextInput.IME_PLACEHOLDER

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._ime_placeholders = 0

    async def _on_key(self, event: events.Key) -> None:
        if event.character == self.IME_PLACEHOLDER:
            self._ime_placeholders += 1
            event.stop()
            event.prevent_default()
            return
        if event.key == "backspace":
            event.stop()
            event.prevent_default()
            self.action_delete_left()
            return
        self._ime_placeholders = 0
        await super()._on_key(event)

    def action_delete_left(self) -> None:
        if self._ime_placeholders:
            self._ime_placeholders -= 1
            return
        row, col = self.cursor_location
        line = self.document.get_line(row)
        if self.selection.is_empty and col > 0:
            start = col - 1
            while start > 0 and unicodedata.combining(line[start]):
                start -= 1
            self.delete((row, start), (row, col))
        else:
            super().action_delete_left()

    def compose_nfc(self) -> None:
        row, col = self.cursor_location
        line = self.document.get_line(row)
        nfc = unicodedata.normalize("NFC", line)
        if nfc != line:
            self.replace(nfc, (row, 0), (row, len(line)), maintain_selection_offset=False)
            self.move_cursor((row, len(unicodedata.normalize("NFC", line[:col]))))

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.compose_nfc()


class RuleEditScreen(BaseModal):
    """Thêm / sửa một rule của dự án (/rules). Trả {title, text, targets, enabled} hoặc None (Esc)."""

    BINDINGS = [Binding("ctrl+s", "save", tr("Lưu"), priority=True)]
    DEFAULT_CSS = """
    RuleEditScreen { align: center middle; }
    #rule-box { width: 110; max-width: 100%; height: auto; max-height: 95%; border: round $primary 70%;
                background: $surface; padding: 0 1; }
    #rule-text { height: 12; }
    #rule-targets { height: auto; max-height: 9; }
    #rule-box .f-section { height: 1; margin-top: 1; color: $text-muted; text-style: bold; }
    #rule-buttons { height: auto; align: right middle; }
    #rule-buttons Button { margin-left: 2; }
    """

    def __init__(self, cfg: Config, rule: dict | None = None):
        super().__init__()
        self.cfg, self.rule = cfg, dict(rule or {})

    def compose(self) -> ComposeResult:
        chosen = set(self.rule.get("targets") or [])
        with Vertical(id="rule-box"):
            yield self.title_bar(tr("✎ Sửa rule") if self.rule else tr("+ Thêm rule"))
            yield Static(tr("Tiêu đề (không bắt buộc)"), classes="f-section")
            yield TextInput(self.rule.get("title", ""), placeholder=tr("vd: Commit message tiếng Việt"),
                            id="rule-title")
            yield Static(tr("Nội dung — agent nhận nguyên văn"), classes="f-section")
            yield TextAreaVN(self.rule.get("text", ""), id="rule-text", soft_wrap=True, show_line_numbers=False)
            yield Static(tr("Áp dụng cho (không chọn gì = mọi agent)"), classes="f-section")
            yield SelectionList(*[(label, v, v in chosen) for v, label in rules.target_choices(self.cfg)],
                                id="rule-targets")
            yield Checkbox(tr("Bật"), self.rule.get("enabled", True) is not False, id="rule-on")
            with Horizontal(id="rule-buttons"):
                yield Btn(tr("Huỷ"), id="rule-cancel")
                yield Btn(tr("Lưu (Ctrl+S)"), id="rule-save", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#rule-text" if self.rule else "#rule-title").focus()
        self.call_after_refresh(self.mark_clean)

    def form_values(self) -> tuple:
        return super().form_values() + (self.query_one("#rule-text", TextArea).text,
                                         tuple(self.query_one("#rule-targets", SelectionList).selected))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "rule-save":
            self.action_save()
        elif event.button.id == "rule-cancel":
            self.close()

    def action_save(self) -> None:
        text = self.query_one("#rule-text", TextArea).text.strip()
        if not text:
            self.notify(tr("Rule chưa có nội dung"), severity="warning")
            return
        self.dismiss({"title": self.query_one("#rule-title", Input).value.strip(), "text": text,
                      "targets": list(self.query_one("#rule-targets", SelectionList).selected),
                      "enabled": self.query_one("#rule-on", Checkbox).value})


class RulesScreen(BaseModal):
    """/rules: rule của dự án — ateam gửi kèm mọi prompt cho agent (rules.py). a thêm · Enter sửa · Space bật/tắt ·
    d xoá · Shift+↑↓ đổi thứ tự. Mục "File có sẵn" (AGENTS.md, CLAUDE.md…): Enter mở ở tab 📝 Code."""

    BINDINGS = [Binding("a", "add", tr("Thêm"), show=False), Binding("e", "edit", show=False),
                Binding("space", "toggle", show=False), Binding("d", "delete", show=False),
                Binding("shift+up", "move(-1)", show=False), Binding("shift+down", "move(1)", show=False)]
    DEFAULT_CSS = """
    RulesScreen { align: center middle; }
    #rules-box { width: 110; max-width: 100%; height: auto; max-height: 90%; border: round $primary 70%;
                 background: $surface; padding: 0 1; }
    #rules-list { height: auto; max-height: 26; margin-top: 1; }
    #rules-buttons { height: auto; align: right middle; }
    #rules-buttons Button { margin-left: 2; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="rules-box"):
            yield self.title_bar(tr("📏 Rule của dự án"))
            yield Static(Text(tr("Mọi agent phải tuân theo: ateam gửi kèm rule ở đầu mỗi prompt (task, chat, lập kế "
                                 "hoạch, review, commit message). Lưu riêng máy này: {v}",
                                 v=projects.shorten(rules.path_for(self.app.root))), "dim"))
            yield OptionList(id="rules-list")
            yield Static(Text(tr("a thêm · Enter sửa · Space bật/tắt · d xoá · Shift+↑↓ đổi thứ tự · Esc đóng"), "dim"))
            with Horizontal(id="rules-buttons"):
                yield Btn(tr("+ Thêm rule (a)"), id="rules-add", variant="primary")
                yield Btn(tr("Đóng"), id="rules-close")

    def on_mount(self) -> None:
        self.refill()
        self.query_one("#rules-list", OptionList).focus()

    def refill(self, keep: str | None = None) -> None:
        lst = self.query_one("#rules-list", OptionList)
        cur = keep or (lst.get_option_at_index(lst.highlighted).id if lst.highlighted is not None else None)
        lst.clear_options()
        items = rules.load(self.app.root)
        for r in items:
            t = Text()
            t.append("✓ " if r.get("enabled", True) else "○ ", "green" if r.get("enabled", True) else "dim")
            t.append(rules.name_of(r), "" if r.get("enabled", True) else "dim")
            t.append(f"  → {rules.targets_label(r)}", "dim")
            lst.add_option(Option(t, id=f"r{r['id']}"))
        if not items:
            lst.add_option(Option(Text(tr("Chưa có rule nào — bấm a để thêm"), "dim"), disabled=True))
        native = rules.native_files(self.app.root)
        if native:
            lst.add_option(Option(Text(tr("File rule có sẵn trong repo — CLI tự đọc, ateam không gửi kèm "
                                          "(Enter mở ở tab Code)"), "bold dim"), disabled=True))
            for f in native:
                t = Text("📄 " + f["path"])
                t.append("  " + tr("{v} tự đọc", v=f["readers"]), "dim")
                lst.add_option(Option(t, id="f" + f["path"]))
        ids = [lst.get_option_at_index(i).id for i in range(lst.option_count)]
        if cur and cur in ids:  # dòng tiêu đề / "chưa có rule" có id None
            lst.highlighted = ids.index(cur)
        else:
            lst.highlighted = next((i for i, x in enumerate(ids) if x), None)

    def current(self) -> str:
        lst = self.query_one("#rules-list", OptionList)
        return (lst.get_option_at_index(lst.highlighted).id or "") if lst.highlighted is not None else ""

    def rule(self) -> dict | None:
        oid = self.current()
        if not oid.startswith("r"):
            return None
        return next((r for r in rules.load(self.app.root) if r["id"] == int(oid[1:])), None)

    def run_op(self, action: str, data: dict, keep: str | None = None) -> None:
        err = rules.apply(self.app.root, action, data)
        if err:
            self.notify(err, severity="warning")
        self.refill(keep)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        oid = event.option.id or ""
        if oid.startswith("f"):
            self.dismiss(None)
            self.app.open_code(oid[1:])
        elif oid.startswith("r"):
            self.action_edit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rules-add":
            event.stop()
            self.action_add()
        elif event.button.id == "rules-close":
            event.stop()
            self.close()

    def action_add(self) -> None:
        def done(d) -> None:
            if d:
                n = len(rules.load(self.app.root))
                self.run_op("add", d)
                items = rules.load(self.app.root)
                if len(items) > n:
                    self.refill(f"r{items[-1]['id']}")
        self.app.push_screen(RuleEditScreen(self.app.cfg), done)

    def action_edit(self) -> None:
        r = self.rule()
        if r:
            self.app.push_screen(RuleEditScreen(self.app.cfg, r),
                                 lambda d: d and self.run_op("update", dict(d, id=r["id"])))

    def action_toggle(self) -> None:
        r = self.rule()
        if r:
            self.run_op("toggle", {"id": r["id"]})

    def action_move(self, by: int) -> None:
        r = self.rule()
        if r:
            self.run_op("move", {"id": r["id"], "by": by}, keep=f"r{r['id']}")

    def action_delete(self) -> None:
        r = self.rule()
        if r:
            self.app.push_screen(ConfirmScreen(tr("Xoá rule"), tr("Xoá rule \"{v}\"?", v=rules.name_of(r)), yes=tr("Xoá")),
                                 lambda ok: ok and self.run_op("delete", {"id": r["id"]}))


class PaletteScreen(BaseModal):
    """Command palette của tab 📝 Code, như VS Code: gõ để mở nhanh file (file mở gần đây đứng đầu), `>` lệnh,
    `@` symbol trong file, `:số` tới dòng, `/chữ` tìm trong file. Danh sách do `app.palette_items(chữ)` dựng;
    trả về giá trị của mục được chọn (vd ("file", đường dẫn), ("cmd", id), ("line", dòng)) hoặc None.
    `items`/`placeholder`/`foot`: dùng lại cho popup khác (Mở folder, /open); `complete`: Tab điền mục đang chọn
    vào ô gõ (đi vào thư mục con)."""

    DEFAULT_CSS = """
    PaletteScreen { align: center top; }
    #pal-box { width: 100; max-width: 100%; height: auto; max-height: 80%; margin-top: 2;
               border: round $primary 70%; background: $surface; padding: 0 1; }
    #pal-list { height: auto; max-height: 24; border: none; padding: 0; }
    #pal-foot { height: 1; color: $text-muted; }
    """
    BINDINGS = [Binding("up", "move(-1)", show=False, priority=True),
                Binding("down", "move(1)", show=False, priority=True),
                Binding("pageup", "move(-10)", show=False, priority=True),
                Binding("pagedown", "move(10)", show=False, priority=True),
                Binding("tab", "complete", show=False, priority=True)]

    def __init__(self, query: str = "", items=None, placeholder: str = "", foot: str = "", complete=None):
        super().__init__()
        self.query_text = query
        self.items, self.complete = items, complete
        self.placeholder = placeholder or tr("Tên file… · > lệnh · @ symbol · :dòng · /tìm trong file")
        self.foot = foot or tr("↑↓ chọn · Enter mở · > lệnh · @ symbol · : dòng · / tìm trong file · Esc đóng")
        self.values: list = []

    def compose(self) -> ComposeResult:
        with Vertical(id="pal-box"):
            yield TextInput(self.query_text, placeholder=self.placeholder, id="pal-q")
            yield OptionList(id="pal-list")
            yield Static(self.foot, id="pal-foot")

    def on_mount(self) -> None:
        q = self.query_one("#pal-q", TextInput)
        q.focus()
        q.cursor_position = len(q.value)
        self.refill(q.value)

    def refill(self, text: str) -> None:
        items = (self.items or self.app.palette_items)(text)
        self.values = [v for _label, v in items]
        lst = self.query_one("#pal-list", OptionList)
        lst.clear_options()
        lst.add_options([Option(label, disabled=v is None) for label, v in items])
        first = next((i for i, v in enumerate(self.values) if v is not None), None)
        if first is not None:
            lst.highlighted = first

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.refill(event.value)

    def action_move(self, delta: int) -> None:
        """↑↓ / PageUp PageDown từ ô gõ: dời mục đang chọn, bỏ qua dòng tiêu đề (giá trị None)."""
        lst = self.query_one("#pal-list", OptionList)
        i, step = (lst.highlighted if lst.highlighted is not None else -1), (1 if delta > 0 else -1)
        for _ in range(abs(delta)):
            j = i + step
            while 0 <= j < len(self.values) and self.values[j] is None:
                j += step
            if not 0 <= j < len(self.values):
                break
            i = j
        if 0 <= i < len(self.values):
            lst.highlighted = i

    def choose(self, index: int | None) -> None:
        if index is not None and 0 <= index < len(self.values) and self.values[index] is not None:
            self.dismiss(self.values[index])

    def action_complete(self) -> None:
        i = self.query_one("#pal-list", OptionList).highlighted
        if self.complete is None:
            self.focus_next()
        elif i is not None and 0 <= i < len(self.values) and self.values[i] is not None:
            q = self.query_one("#pal-q", TextInput)
            q.value = self.complete(self.values[i])
            q.cursor_position = len(q.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.choose(self.query_one("#pal-list", OptionList).highlighted)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.choose(event.option_index)


class GitFileList(OptionList):
    """Danh sách file thay đổi ở tab Git. Space stage/bỏ stage, a stage tất cả, u bỏ stage tất cả,
    x bỏ thay đổi, X bỏ tất cả, Enter/d xem diff; file xung đột: Enter/r giải quyết, g nhờ agent giải quyết mọi xung đột."""

    BINDINGS = [
        Binding("space", "app.git_toggle", tr("Stage/bỏ stage"), show=False),
        Binding("a", "app.git_stage_all", tr("Stage tất cả"), show=False),
        Binding("u", "app.git_unstage_all", tr("Bỏ stage tất cả"), show=False),
        Binding("x", "app.git_discard", tr("Bỏ thay đổi"), show=False),
        Binding("X", "app.git_discard_all", tr("Bỏ tất cả thay đổi"), show=False),
        Binding("d", "app.git_diff", tr("Xem diff"), show=False),
        Binding("c", "app.git_focus_msg", "Commit", show=False),
        Binding("e", "app.git_edit", tr("Sửa file"), show=False),
        Binding("r", "app.git_resolve", tr("Giải quyết xung đột"), show=False),
        Binding("g", "app.git_ai_resolve", tr("Nhờ agent giải quyết xung đột"), show=False),
        Binding("t", "app.git_tree", tr("Danh sách / cây thư mục"), show=False),
    ]


class GitLogList(OptionList):
    """Lịch sử commit ở tab Git. Enter xem diff của commit, r revert."""

    BINDINGS = [
        Binding("r", "app.git_revert", "Revert", show=False),
        Binding("d", "app.git_show_commit", tr("Xem commit"), show=False),
    ]


class ConflictScreen(BaseModal):
    """Giải quyết xung đột một file (như VS Code): mỗi khối <<<<<<< chọn giữ hiện tại / lấy bên đến / giữ cả hai;
    hết khối thì tự stage. Trả "edit" (mở ở tab Code), "ai" (nhờ agent) hoặc None."""

    DEFAULT_CSS = """
    ConflictScreen { align: center middle; }
    #cf-box { width: 120; max-width: 100%; height: 90%; border: round $warning; background: $surface; padding: 0 1; }
    #cf-note { height: auto; color: $warning; }
    #cf-list { height: 1fr; }
    #cf-hint { height: auto; color: $text-muted; }
    .cf-buttons { height: auto; }
    #cf-box .cf-buttons Button { margin-right: 1; }
    """
    BINDINGS = [
        Binding("o", "pick('ours')", tr("Giữ hiện tại"), show=False),
        Binding("t", "pick('theirs')", tr("Lấy bên đến"), show=False),
        Binding("b", "pick('both')", tr("Giữ cả hai"), show=False),
        Binding("O", "side('ours')", tr("Cả file: hiện tại"), show=False),
        Binding("T", "side('theirs')", tr("Cả file: bên đến"), show=False),
        Binding("m", "done", tr("Đánh dấu đã xong"), show=False),
        Binding("e", "dismiss_with('edit')", tr("Sửa trong Code"), show=False),
        Binding("g", "dismiss_with('ai')", tr("Nhờ agent"), show=False),
    ]

    def __init__(self, repo, path: str):
        super().__init__()
        self.repo, self.path = repo, path
        self.info: dict = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="cf-box"):
            yield self.title_bar(tr("⇄ Giải quyết xung đột · {path}", path=self.path))
            yield Static(id="cf-note")
            yield OptionList(id="cf-list")
            yield Static(Text(tr("Khối đang chọn: o giữ hiện tại · t lấy bên đến · b giữ cả hai  —  cả file: O hiện tại · "
                                 "T bên đến  —  e sửa · g nhờ agent · m đã xong · Esc đóng"), "dim"), id="cf-hint")
            with Horizontal(classes="cf-buttons"):
                yield Btn(tr("Giữ hiện tại"), id="cf-ours")
                yield Btn(tr("Lấy bên đến"), id="cf-theirs")
                yield Btn(tr("Giữ cả hai"), id="cf-both")
                yield Btn(tr("✎ Sửa trong Code"), id="cf-edit")
            with Horizontal(classes="cf-buttons"):
                yield Btn(tr("Cả file: hiện tại"), id="cf-take-ours")
                yield Btn(tr("Cả file: bên đến"), id="cf-take-theirs")
                yield Btn(tr("🤖 Nhờ agent"), id="cf-ai")
                yield Btn(tr("✓ Đánh dấu đã xong"), id="cf-done", variant="success")

    def on_mount(self) -> None:
        self.run_worker(self.load(), exclusive=True)

    async def load(self) -> None:
        self.info = info = await self.repo.conflict_info(self.path)
        if not info["conflicted"]:
            self.notify(tr("Đã giải quyết xong {path}", path=self.path))
            self.dismiss(None)
            return
        n = len(info["blocks"])
        notes = []
        if info["state"] == "rebase":
            notes.append(tr("Đang rebase: \"hiện tại\" là nhánh đích, \"bên đến\" là commit của bạn đang được áp lại."))
        if info["ours_deleted"]:
            notes.append(tr("Phía hiện tại đã xoá file này, bên đến sửa nó — O xoá, T giữ bản bên đến."))
        elif info["theirs_deleted"]:
            notes.append(tr("Bên đến đã xoá file này, phía hiện tại sửa nó — O giữ bản hiện tại, T xoá."))
        elif info["binary"]:
            notes.append(tr("File nhị phân hoặc không phải UTF-8 — chỉ chọn được nguyên bản một phía (O/T)."))
        elif not n:
            notes.append(tr("Không còn dấu xung đột trong file — xem lại rồi m (đánh dấu đã xong)."))
        self.query_one("#cf-note", Static).update("\n".join(notes))
        ol = self.query_one("#cf-list", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        for i, b in enumerate(info["blocks"]):
            t = Text()
            t.append(tr("Xung đột {i}/{n} · dòng {line}", i=i + 1, n=n, line=b["line"]) + "\n", "bold")
            for ln in b["before"]:
                t.append(f"  {ln}\n", "dim")
            for label, tag, body, style in ((tr("Hiện tại"), b["ours_label"], b["ours"], "green"),
                                            (tr("Bản gốc"), "", b["base"], "dim"),
                                            (tr("Bên đến"), b["theirs_label"], b["theirs"], "cyan")):
                if body is None:
                    continue
                t.append(f"▌ {label}" + (f" · {tag}" if tag else "") + "\n", f"bold {style}")
                for ln in body.splitlines() or [tr("(trống)")]:
                    t.append(f"▌ {ln}\n", style)
            for ln in b["after"]:
                t.append(f"  {ln}\n", "dim")
            t.rstrip()
            ol.add_option(Option(t, id=str(i)))
        if n:
            ol.highlighted = min(keep or 0, n - 1)
            ol.focus()

    def _run(self, make) -> None:
        async def go() -> None:
            ok, msg = await make()
            self.notify(msg, severity="information" if ok else "warning", timeout=4 if ok else 8)
            await self.load()
        self.run_worker(go(), exclusive=True)

    def action_pick(self, choice: str) -> None:
        ol = self.query_one("#cf-list", OptionList)
        if ol.highlighted is None or not self.info.get("blocks"):
            return
        idx = ol.highlighted
        self._run(lambda: self.repo.resolve_block(self.path, idx, choice))

    def action_side(self, side: str) -> None:
        self._run(lambda: self.repo.take_side([self.path], side))

    def action_done(self) -> None:
        self._run(lambda: self.repo.mark_resolved([self.path]))

    def action_dismiss_with(self, what: str) -> None:
        self.dismiss(what)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()  # Enter trên khối: không làm gì (chọn bằng o/t/b), tránh lan lên app

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        bid = event.button.id or ""
        if bid in ("cf-ours", "cf-theirs", "cf-both"):
            self.action_pick(bid[3:])
        elif bid in ("cf-take-ours", "cf-take-theirs"):
            self.action_side(bid[8:])
        elif bid == "cf-done":
            self.action_done()
        elif bid in ("cf-edit", "cf-ai"):
            self.dismiss(bid[3:])


class GitBranchScreen(BaseModal):
    """Danh sách nhánh local + remote. Trả về (hành động, nhánh, tên mới) hoặc None."""

    DEFAULT_CSS = """
    GitBranchScreen { align: center middle; }
    #gb-box { width: 100; max-width: 100%; height: auto; max-height: 90%; border: round $primary 70%;
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

    def options(self, q: str = "") -> list:
        """Option cho các nhánh khớp bộ lọc (chuỗi con, không phân biệt hoa thường); id = chỉ số trong branches."""
        opts = []
        for i, b in enumerate(self.branches):
            if q and q.lower() not in b.name.lower():
                continue
            t = Text()
            t.append("● " if b.current else "  ", "green")
            t.append(b.name, "bold green" if b.current else ("cyan" if b.remote else ""))
            if b.track:
                t.append(f" {b.track}", "yellow")
            elif b.upstream:
                t.append(f" → {b.upstream}", "dim")
            if b.name.startswith("ateam/"):
                t.append(tr("  nhánh task của ateam"), "dim")
            t.append(f"  {b.date}", "dim")
            if b.subject:
                t.append(f"  {b.subject[:60]}", "dim")
            opts.append(Option(t, id=str(i)))
        return opts

    def compose(self) -> ComposeResult:
        with Vertical(id="gb-box"):
            yield self.title_bar(tr("⎇ Nhánh — đang ở {v}", v=self.current or '(detached)'))
            yield TextInput(id="gb-filter", placeholder=tr("Lọc nhánh theo tên… (Enter: chuyển sang nhánh khớp "
                                                           "đầu tiên · ↓: xuống danh sách)"))
            yield OptionList(*self.options(), id="gb-list")
            yield Static(Text(tr("Enter: chuyển sang nhánh đang chọn (nhánh remote → tạo nhánh "
                                 "local theo dõi nó) · Esc: đóng"), "dim"), id="gb-hint")
            with Horizontal(classes="gb-buttons"):
                yield Btn(tr("⎇ Chuyển sang"), id="gb-checkout", variant="primary")
                yield Btn(tr("⤵ Merge vào nhánh hiện tại"), id="gb-merge")
                yield Btn(tr("✗ Xoá"), id="gb-delete", variant="error")
                yield Btn(tr("✗ Xoá hẳn"), id="gb-force", variant="error")
            yield TextInput(id="gb-name", placeholder=tr("Tên nhánh mới, vd feature/dang-nhap "
                                                         "(Enter để tạo từ nhánh hiện tại)"))
            with Horizontal(classes="gb-buttons"):
                yield Btn(tr("＋ Tạo & chuyển sang"), id="gb-create", variant="success")
                yield Btn(tr("✎ Đổi tên nhánh đang chọn"), id="gb-rename")

    def on_mount(self) -> None:
        ol = self.query_one("#gb-list", OptionList)
        if self.branches:
            ol.highlighted = 0
        self.query_one("#gb-filter", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "gb-filter":
            return
        event.stop()
        ol = self.query_one("#gb-list", OptionList)
        ol.clear_options()
        ol.add_options(self.options(event.value.strip()))
        if ol.option_count:
            ol.highlighted = 0

    def on_key(self, event) -> None:
        if event.key == "down" and self.focused is self.query_one("#gb-filter", Input):
            event.stop()
            self.query_one("#gb-list", OptionList).focus()

    def selected(self):
        ol = self.query_one("#gb-list", OptionList)
        if ol.highlighted is None or ol.highlighted >= ol.option_count:
            return None
        return self.branches[int(ol.get_option_at_index(ol.highlighted).id)]

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        b = self.selected()
        if b:
            self.dismiss(("checkout", b.name, ""))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if event.input.id == "gb-filter":  # chuyển sang nhánh khớp đầu tiên
            b = self.selected()
            if b and not b.current:
                self.dismiss(("checkout", b.name, ""))
            elif not b:
                self.notify(tr("Không có nhánh nào khớp"), severity="warning")
            return
        self._create()

    def _create(self) -> None:
        name = self.query_one("#gb-name", Input).value.strip()
        if not name:
            self.notify(tr("Gõ tên nhánh mới trước"), severity="warning")
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
            self.notify(tr("Chưa có nhánh nào"), severity="warning")
            return
        if bid == "gb-rename":
            new = self.query_one("#gb-name", Input).value.strip()
            if b.remote:
                self.notify(tr("Chỉ đổi tên được nhánh local"), severity="warning")
            elif not new:
                self.notify(tr("Gõ tên mới cho {name} vào ô bên dưới rồi bấm lại", name=b.name), severity="warning")
            else:
                self.dismiss(("rename", b.name, new))
            return
        if b.remote and bid not in ("gb-checkout", "gb-merge"):
            self.notify(tr("Không xoá nhánh remote từ đây (dùng /git push origin --delete <nhánh>)"),
                        severity="warning")
            return
        if b.current and bid in ("gb-merge", "gb-delete", "gb-force"):
            self.notify(tr("{name} là nhánh hiện tại", name=b.name), severity="warning")
            return
        action = {"gb-checkout": "checkout", "gb-merge": "merge", "gb-delete": "delete",
                  "gb-force": "force-delete"}[bid]
        self.dismiss((action, b.name, ""))


class GitStashScreen(BaseModal):
    """Các lần stash. Trả về (hành động, ref, message) hoặc None."""

    DEFAULT_CSS = """
    GitStashScreen { align: center middle; }
    #gs-box { width: 90; max-width: 100%; height: auto; max-height: 85%; border: round $primary 70%;
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
            yield self.title_bar(tr("📦 Stash — cất tạm thay đổi chưa commit"))
            yield OptionList(*opts, id="gs-list")
            yield Static(tr("Chưa có stash nào."), id="gs-empty")
            with Horizontal(classes="gs-buttons", id="gs-row-list"):
                yield Btn(tr("⤴ Lấy lại (pop)"), id="gs-pop", variant="primary")
                yield Btn(tr("Áp dụng, giữ stash"), id="gs-apply")
                yield Btn(tr("✗ Xoá"), id="gs-drop", variant="error")
            yield TextInput(id="gs-msg", placeholder=tr("Ghi chú cho lần cất (không bắt buộc) — Enter để cất"))
            with Horizontal(classes="gs-buttons"):
                yield Btn(tr("📦 Cất mọi thay đổi (kể cả file mới)"), id="gs-push", variant="success")

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
            self.notify(tr("Không có thay đổi nào để cất"), severity="warning")

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
def parse_code_target(arg: str) -> tuple[str, int | None]:
    """"@src/a.py:12" -> ("src/a.py", 12); bỏ @ và ngoặc kép của gợi ý @file."""
    t = arg.strip()
    if t.startswith("@"):
        t = t[1:]
    line = None
    m = re.match(r"^(.*?):(\d+)(?::\d+)?$", t)
    if m and m.group(1):
        t, line = m.group(1), int(m.group(2))
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1]
    return t, line


from textual.document._wrapped_document import WrappedDocument as _WrappedDocument  # noqa: E402


class _NoWrapDocument(_WrappedDocument):
    """WrappedDocument cho editor không xuống dòng mềm: mỗi dòng đúng 1 hàng nên height = số dòng (O(1))."""

    @property
    def height(self) -> int:
        return len(self._wrap_offsets)


class CodeEditor(TextArea):
    """Editor của tab 📝 Code: TextArea (chỉ vẽ dòng đang hiện) + phím vim (`editor.VimState`) + tô màu
    pygments chạy nền: mỗi lần sửa chỉ hẹn tô lại (debounce) trong thread, gõ liên tục không lexer lại
    từng phím; file lớn tắt tô màu."""

    DEFAULT_CSS = """
    CodeEditor { border: none; padding: 0; height: 1fr; }
    CodeEditor:focus { border: none; }
    """
    BINDINGS = [Binding("ctrl+s", "save", tr("Lưu"), show=False, priority=True)]
    HL_DELAY = 0.2
    HL_MARGIN = 200  # tô thêm bấy nhiêu dòng dưới màn hình

    def __init__(self, **kw):
        super().__init__("", soft_wrap=False, show_line_numbers=True, tab_behavior="indent",
                         theme="vscode_dark", **kw)
        self.vim = editor.VimState()
        self.vim_on = True
        self.buffer: editor.SourceFile | None = None
        self.lexer = None
        self.highlight_on = False
        self.hl_runs = 0  # số lượt tô màu đã chạy (test kiểm tra debounce)
        self._hl_timer = None
        self._hl_upto = 0
        self._gen = 0
        self._saved_gen = 0
        self._want_col = 0
        self.message = ""

    # ---- trạng thái
    @property
    def dirty(self) -> bool:
        return self.buffer is not None and self._gen != self._saved_gen

    def mark_saved(self) -> None:
        self._saved_gen = self._gen

    def load(self, sf: "editor.SourceFile", cursor: tuple = (0, 0), dirty_text: str | None = None) -> None:
        """Nạp file (hoặc nội dung buffer chưa lưu) vào editor."""
        self.buffer = sf
        self.lexer = editor.lexer_for(sf.path)
        text = sf.text if dirty_text is None else dirty_text
        self.highlight_on = self.lexer is not None and editor.can_highlight(text, sf.size)
        self._highlights.clear()
        self._hl_upto = 0
        self.read_only = sf.read_only
        self.load_text(text)
        self.mark_saved()
        if dirty_text is not None:
            self._saved_gen = -1
        self.vim = editor.VimState(shiftwidth=self.vim.shiftwidth)
        self.message = ""
        self.move_cursor(self.clamp_visitable(cursor), center=True)
        self._want_col = self.cursor_location[1]
        if self.highlight_on:
            self._schedule_hl(0)

    def _set_document(self, text: str, language: str | None) -> None:
        super()._set_document(text, language)
        # WrappedDocument.height của Textual cộng dồn trên mọi dòng mỗi lần vẽ 1 dòng (O(n) / dòng): file
        # 60 000 dòng mất hàng giây mỗi khung hình. Không xuống dòng mềm thì chiều cao = số dòng.
        if not self.soft_wrap:
            self.wrapped_document.__class__ = _NoWrapDocument
        self._max_width = None

    def set_wrap(self, on: bool) -> None:
        """Bật/tắt xuống dòng mềm (palette, `:set wrap`): bật thì dùng lại WrappedDocument gốc (chậm hơn với
        file rất dài nhưng đúng chiều cao khi dòng gãy)."""
        self.wrapped_document.__class__ = _WrappedDocument if on else _NoWrapDocument
        self.soft_wrap = on

    def _refresh_size(self) -> None:
        # Textual đo lại độ rộng mọi dòng sau mỗi lần sửa (O(n)): giữ độ rộng lớn nhất, chỉ đo các dòng vừa
        # sửa (độ rộng chỉ dùng cho thanh cuộn ngang — lớn hơn thật một chút sau khi xoá dòng dài không sao)
        if self.soft_wrap or not hasattr(self, "_max_width"):
            super()._refresh_size()
            return
        from rich.cells import cell_len
        lines = self.document.lines
        tab = self.indent_width
        if self._max_width is None:
            self._max_width = max((cell_len(ln.expandtabs(tab)) for ln in lines), default=0)
        else:
            r0, r1 = getattr(self, "_edit_rows", None) or (self.cursor_location[0],) * 2
            for ln in lines[max(0, r0):min(len(lines), r1 + 1, r0 + 5000)]:
                w = cell_len(ln.expandtabs(tab))
                if w > self._max_width:
                    self._max_width = w
        self.virtual_size = Size(self._max_width + self.gutter_width + 1, len(lines))
        self._refresh_scrollbars()

    def edit(self, edit):
        top = edit.top[0] if hasattr(edit, "top") else self.cursor_location[0]
        self._edit_rows = (top, top + getattr(edit, "text", "").count("\n"))
        result = super().edit(edit)
        self._edit_rows = None
        return result

    def undo(self) -> None:
        self._max_width = None
        super().undo()

    def redo(self) -> None:
        self._max_width = None
        super().redo()

    # ---- tô màu chạy nền
    def _build_highlight_map(self) -> None:
        # Textual gọi sau mỗi lần sửa / undo / nạp: chỉ đánh dấu và hẹn tô lại, không lexer ngay
        self._line_cache.clear()
        if not hasattr(self, "_gen"):
            return
        self._gen += 1
        if self.highlight_on:
            self._schedule_hl()

    def _schedule_hl(self, delay: float | None = None) -> None:
        if self._hl_timer is not None:
            self._hl_timer.stop()
        # set_timer(0) làm Timer của Textual chia cho 0
        self._hl_timer = self.set_timer(max(0.01, self.HL_DELAY if delay is None else delay), self._start_hl)

    def _start_hl(self) -> None:
        self._hl_timer = None
        if not self.highlight_on or self.lexer is None:
            return
        upto = int(self.scroll_y) + self.size.height + self.HL_MARGIN
        self.run_worker(partial(self._hl_job, self.text, self.lexer, upto, self._gen), thread=True,
                        exclusive=True, group="code-hl")

    def _hl_job(self, text: str, lexer, upto: int, gen: int) -> None:
        try:
            hl = editor.highlight_lines(text, lexer, upto)
        except Exception:
            return
        self.app.call_from_thread(self._hl_done, hl, upto, gen)

    def _hl_done(self, hl: dict, upto: int, gen: int) -> None:
        self.hl_runs += 1
        if gen != self._gen:  # đã sửa tiếp trong lúc tô: lượt mới đã được hẹn
            return
        self._highlights.clear()
        self._highlights.update(hl)
        self._hl_upto = upto
        self._line_cache.clear()
        self.refresh()

    def watch_scroll_y(self, old: float, new: float) -> None:
        super().watch_scroll_y(old, new)
        if self.highlight_on and new + self.size.height > self._hl_upto - 20 and self._hl_timer is None:
            self._schedule_hl(0.05)

    # ---- phím
    async def _on_key(self, event: events.Key) -> None:
        if not self.vim_on or self.buffer is None:
            await super()._on_key(event)
            return
        if self.vim.mode == "insert" and event.key not in ("escape", "ctrl+c", "ctrl+left_square_bracket"):
            if self.read_only:
                event.stop()
                event.prevent_default()
                return
            await super()._on_key(event)
            return
        event.stop()
        event.prevent_default()
        ops = self.vim.feed(event.key, event.character, self.document.lines, self.cursor_location,
                            max(1, self.size.height))
        self.apply(ops)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # ở normal/visual mọi phím (mũi tên, Backspace, Ctrl+D/U/K…) đi qua VimState, không qua binding sửa
        # chữ của TextArea (Ctrl+U xoá đầu dòng, Ctrl+D xoá ký tự…)
        if self.vim_on and self.buffer is not None and self.vim.mode != "insert" and action != "save":
            return False
        return True

    def check_consume_key(self, key: str, character: str | None = None) -> bool:
        # chỉ nhận ký tự in được (h j k : / …) — Ctrl+T, F1, Ctrl+Q của app vẫn phải chạy
        if self.vim_on and self.buffer is not None and self.vim.mode != "insert":
            return character is not None and character.isprintable()
        return super().check_consume_key(key, character)

    def apply(self, ops: list) -> None:
        from textual.widgets.text_area import Selection
        lines = self.document.lines
        for op in ops:
            kind = op[0]
            if kind == "edit":
                if self.read_only:
                    self.message = tr("Chỉ đọc: {v}", v=self.buffer.note if self.buffer else "")
                    continue
                self.replace(op[3], op[1], op[2], maintain_selection_offset=False)
                lines = self.document.lines
            elif kind in ("move", "move_v"):
                r, c = op[1]
                r = max(0, min(r, len(lines) - 1))
                if c is None:
                    c = editor.first_nonblank(lines[r])
                if kind == "move_v":
                    c = self._want_col
                else:
                    self._want_col = c
                if self.vim.mode not in ("insert",):
                    c = min(c, max(0, len(lines[r]) - 1))
                self.move_cursor((r, min(c, len(lines[r]))))
            elif kind == "select":
                self.selection = Selection(op[1], op[2])
            elif kind == "undo":
                for _ in range(op[1]):
                    self.undo()
                lines = self.document.lines
                self._clamp_normal()
            elif kind == "redo":
                for _ in range(op[1]):
                    self.redo()
                lines = self.document.lines
            elif kind == "mode":
                self.set_class(op[1] == "insert", "-insert")
                self.message = ""
            elif kind == "msg":
                self.message = op[1]
            elif kind == "ex":
                self.app.code_ex(op[1])
        self.post_message(self.StatusChanged(self))

    def _clamp_normal(self) -> None:
        r, c = self.cursor_location
        n = len(self.document[r])
        if c > max(0, n - 1):
            self.move_cursor((r, max(0, n - 1)))

    def action_save(self) -> None:
        self.app.code_ex("w")

    class StatusChanged(Message):
        def __init__(self, ed: "CodeEditor"):
            super().__init__()
            self.editor = ed


class CodeFileList(OptionList):
    """Danh sách file ở tab Code: buffer đang mở ở trên, dưới là cây thư mục (ô lọc trống) hoặc kết quả lọc.
    Enter/→ mở thư mục, Enter/← thu gọn, ← trên file nhảy về thư mục cha."""

    BINDINGS = [
        Binding("right", "app.code_fold(1)", tr("Mở thư mục"), show=False),
        Binding("l", "app.code_fold(1)", tr("Mở thư mục"), show=False),
        Binding("left", "app.code_fold(0)", tr("Thu gọn thư mục"), show=False),
        Binding("h", "app.code_fold(0)", tr("Thu gọn thư mục"), show=False),
    ]


class TaskTable(DataTable):
    """Bảng task ở tab Bảng việc. Chế độ nhóm (mặc định): dòng tiêu đề 📌 Ngoài kế hoạch rồi từng kế hoạch, Enter trên
    tiêu đề thu/mở nhóm. Phím một chữ đặt ở đây (không phải ở app) để không nuốt chữ gõ trong ô nhập."""
    BINDINGS = [
        Binding("n", "app.adhoc_task", tr("Giao task ngoài kế hoạch"), show=False),
        Binding("g", "app.toggle_task_groups", tr("Nhóm theo kế hoạch / bảng phẳng"), show=False),
        Binding("left_square_bracket", "app.task_group(-1)", tr("Nhóm trước"), show=False),
        Binding("right_square_bracket", "app.task_group(1)", tr("Nhóm sau"), show=False),
        Binding("c", "app.continue_group", tr("Tiếp tục kế hoạch"), show=False),
    ]


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
    #right { width: 1fr; border-left: solid $foreground 15%; }
    /* terminal hẹp: xếp dọc, không để cột phải chỉ còn vài ký tự (log thành chữ dọc) */
    #board.narrow { layout: vertical; }
    #board.narrow #left { width: 100%; min-width: 0; height: 45%; }
    #board.narrow #right { width: 100%; height: 1fr; border-left: none;
                           border-top: solid $foreground 15%; }
    #agents { height: auto; padding: 0 1; background: $boost; }
    #goals { height: auto; max-height: 7; padding: 0 1; border-bottom: solid $foreground 15%; }
    #tasks { height: 1fr; }
    #board-tools { height: 1; align: right top; display: none; }
    #term { height: 1fr; }
    #jobs-side { width: 34%; min-width: 30; max-width: 70; border-right: solid $foreground 15%; }
    #jobs { height: 1fr; border: none; }
    #jobs-empty { height: auto; padding: 1 2; color: $text-muted; }
    #scripts-title { height: 1; padding: 0 1; margin-top: 1; background: $panel; }
    #term-scripts { height: 1fr; border: none; }
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
    #git-side { width: 50%; min-width: 40; border-right: solid $foreground 15%; }
    #git-main.narrow #git-side { width: 100%; height: 55%; border-right: none;
                                 border-bottom: solid $foreground 15%; }
    #git-files { height: 1fr; border: none; }
    #git-empty { height: 1fr; padding: 1 2; }
    .git-row { height: auto; }
    .git-row Button { padding: 0; margin-right: 1; }
    #git-msg { margin: 0; }
    #git-ai-agent { width: 26; height: 1; }
    #git-ai-agent > SelectCurrent { border: none; height: 1; padding: 0 1; }
    #git-amend, #git-no-verify { height: auto; border: none; padding: 0; background: transparent;
                                 margin-right: 2; }
    #git-hist { width: 1fr; }
    #git-log-title { height: 1; padding: 0 1; background: $panel; }
    #git-log { height: 1fr; border: none; }
    #git-norepo { height: 1fr; padding: 1 2; }
    #tasks-empty { height: 1fr; padding: 1 2; color: $text-muted; }
    #code { height: 1fr; }
    #custom-tab { height: 1fr; padding: 0 1; }
    #dash { height: 1fr; padding: 0 1; }
    #dash-cards, #dash-chart, #dash-goal, #dash-note { height: auto; margin-top: 1; }
    #dash .dash-title { height: 1; margin-top: 1; color: $text-muted; text-style: bold; }
    #dash-agents { height: auto; max-height: 12; }
    #dash-goals { height: auto; max-height: 16; }
    #custom-tab .f-scroll { height: 1fr; max-height: 100%; }
    #code-side { width: 34; min-width: 22; border-right: solid $foreground 15%; }
    #code.narrow #code-side { width: 24; }
    #code.hide-side #code-side { display: none; }
    #code-filter { margin: 0; }
    #code-new { width: 100%; height: 1; min-width: 0; }
    #code-files { height: 1fr; border: none; }
    #code-main { width: 1fr; }
    #code-head { height: 1; padding: 0 1; background: $boost; overflow: hidden hidden; }
    #code-status { height: 1; padding: 0 1; background: $panel; overflow: hidden hidden; }
    /* cao cố định: chiều cao đổi theo từng task thì mỗi lần lướt bảng cả màn hình phải tính lại bố cục */
    #detail { height: 6; padding: 0 1; background: $boost; overflow: hidden hidden; }
    #log-tools { height: 1; align: right top; }
    #log-clear { margin: 0 1 0 0; }
    #log { height: 1fr; padding: 0 1; overflow-x: hidden; }
    /* tab Agents: danh sách gọn (chỉ phần đầu mỗi ô); chat = phóng to 1 ô (F7 / bấm vào agent) */
    #team-list { height: 1fr; }
    #team-hint { height: auto; padding: 0 1; margin-bottom: 1; }
    #team-grid { height: auto; }
    #agents-custom { margin-top: 1; padding: 0 1; }
    .agentpane { height: auto; margin-bottom: 1; border: none; border-left: tall $panel-lighten-2; }
    .agentpane.busy { border-left: tall $accent; }
    .agentpane.missing { border-left: tall $error 50%; }
    .agentpane.cooling { border-left: tall $warning; }
    .agentpane.failed { border-left: tall $error; }
    .agentpane .pane-log, .agentpane .pane-chat { display: none; }
    .pane-head { height: auto; padding: 0 1; background: $boost; }
    .pane-log { height: 1fr; padding: 0 1; overflow-x: hidden; }
    .pane-chat { height: 1; margin: 0; padding: 0 1; border: none; background: $boost; }
    .pane-chat:focus { border: none; background: $accent 25%; }
    /* F7 / /focus: chỉ còn 1 ô agent (có log + ô chat) chiếm cả tab Agents */
    #team.focused #team-list { overflow: hidden hidden; }
    #team.focused #team-hint, #team.focused #agents-custom, #team.focused #timeline { display: none; }
    #team-grid.focused { height: 1fr; }
    #team-grid.focused .agentpane.unfocused { display: none; }
    #team-grid.focused .agentpane { height: 1fr; margin: 0; border: round $accent; }
    #team-grid.focused .pane-log, #team-grid.focused .pane-chat { display: block; }
    #timeline { height: auto; max-height: 14; padding: 0 1; border-top: solid $foreground 15%; }
    #cmd-row { dock: bottom; height: 3; margin: 0 0 2 0; }
    #cmd-mode { width: auto; max-width: 30%; margin-top: 1; text-wrap: nowrap; text-overflow: ellipsis; }
    #cmd { width: 1fr; }
    /* Footer, thanh trạng thái, ô nhập cùng dock dưới: chồng nhau nên đẩy bằng margin */
    #statusbar { dock: bottom; height: 1; margin: 0 0 1 0; padding: 0 1; background: $boost;
                 overflow: hidden hidden; }
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
    /* phương án bấm được (meta @click): không tô kiểu link (gạch chân + đổi màu mọi dòng, cả khoảng thụt
       lề), chỉ gạch chân khi rê chuột */
    #grill-q { height: auto; margin-top: 1; link-style: none; link-color: $text; link-background: transparent;
               link-style-hover: underline; link-color-hover: $text; link-background-hover: $boost; }
    #grill-buttons { height: auto; margin-top: 1; }
    #grill-buttons Button { margin-right: 2; }
    #continue-hint { height: auto; display: none; padding: 0 1; background: $boost; }
    #mention { dock: bottom; layer: overlay; display: none; height: auto; max-height: 14;
               width: 90; max-width: 100%; margin: 0 0 5 1; border: round $panel-lighten-2;
               border-title-color: $accent; border-subtitle-color: $text-muted;
               background: $panel; }
    """
    # priority=True: phím tắt vẫn chạy khi con trỏ đang ở ô nhập (Input của Textual tự dùng
    # Ctrl+D, Ctrl+K... để sửa chữ, sẽ nuốt mất phím nếu không ưu tiên)
    BINDINGS = [
        Binding("f1", "help", tr("Trợ giúp"), priority=True),
        Binding("ctrl+q", "quit", tr("Thoát"), priority=True),
        Binding("ctrl+t", "toggle_tab", tr("Đổi tab"), priority=True),
        # F2/F5 đứng trước: Ctrl+G (Go to Line) và Ctrl+R (Run Recent Command) bị terminal tích hợp
        # của VS Code/Cursor trên macOS chặn — footer hiện phím đầu tiên, phím Ctrl vẫn dùng được
        Binding("f2,ctrl+g", "approve", tr("Duyệt & chạy"), priority=True),
        Binding("f5,ctrl+r", "retry", tr("Chạy lại"), priority=True),
        Binding("ctrl+k", "cancel_task", tr("Huỷ task"), priority=True),
        Binding("f6,ctrl+o", "continue", tr("Tiếp tục"), priority=True),
        Binding("ctrl+d", "diff", tr("Xem diff"), priority=True),
        Binding("ctrl+y", "merge", "Merge", priority=True),
        Binding("ctrl+l", "syslog", tr("Log hệ thống"), priority=True),
        Binding("f3", "search", tr("Tìm trong dự án"), priority=True),
        Binding("f4", "pick_mode", tr("Luồng"), priority=True),
        Binding("f7", "focus_agent", tr("Phóng to agent"), show=False, priority=True),
        # Command palette (tab 📝 Code) như VS Code; terminal thường không phân biệt Ctrl+Shift+P với Ctrl+P
        # nên lệnh / symbol có thêm F8 / F9
        Binding("ctrl+p", "palette('')", tr("Mở nhanh file"), show=False, priority=True),
        Binding("f8,ctrl+shift+p", "palette('>')", tr("Lệnh"), show=False, priority=True),
        Binding("f9,ctrl+shift+o", "palette('@')", tr("Symbol"), show=False, priority=True),
        Binding("f10", "grid_arrange", tr("Sắp xếp lưới"), show=False, priority=True),
        *[Binding(f"alt+{i + 1}", f"goto_tab({i})", show=False, priority=True) for i in range(9)],
        Binding("alt+0", "goto_tab(9)", show=False, priority=True),
    ]

    def __init__(self, root: Path, cfg: Config, db: DB, setup: bool = False):
        super().__init__()
        self.root, self.cfg, self.db = root, cfg, db
        self.focus_agent: str | None = None  # agent đang phóng to ở tab Agents (F7, /focus)
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
        self._grayed: set = set()  # theme đã đăng ký đè bản nền xám (theme.grayed)
        self.git_tree = bool(load_state().get("git_tree"))  # tab Git: danh sách file dạng cây thư mục (phím t)
        self._git_closed: set = set()  # thư mục đang thu gọn ở chế độ cây: "nhóm\0thư/mục/"
        self.busy_ops: dict[int, str] = {}  # thao tác chạy lâu (commit, push, AI viết…): hiện ⠋ ở thanh trạng thái
        self._busy_seq = 0
        self._git_ids: list = []
        self._git_log_ids: list = []
        self._git_body = ""  # phần thân commit message do trưởng nhóm viết (ô nhập chỉ một dòng)
        self._rows: dict[int, tuple] = {}
        # bảng task nhóm theo kế hoạch (phím g đổi sang bảng phẳng, nhớ trong state.json)
        self.task_groups = load_state().get("task_groups", True) is not False
        self._folded: dict[str, bool] = {}  # khoá nhóm ("g:adhoc", "g:<id>") -> thu gọn; vắng = mặc định
        self._gorder: list[str] = []
        self._gsig: dict[str, tuple] = {}
        self._loop_task: asyncio.Task | None = None
        self._frame = 0
        self._booted = False
        self.restart_requested = False  # /lang, /open: cli.cmd_tui mở lại app sau khi thoát
        self.restart_root: Path | None = None  # /open: mở lại ở thư mục này
        self.code_bufs: dict[str, dict] = {}  # tab 📝 Code: đường dẫn tuyệt đối -> buffer
        self.search_state: dict = {}  # popup 🔍 Tìm & thay (F3): giữ từ khoá, tuỳ chọn giữa các lần mở
        self.code_order: list[str] = []
        self.code_cur: str | None = None
        self.code_open: set[str] = set()  # cây thư mục tab Code: thư mục đang mở ("src/", "src/app/")
        self._code_tree: tuple = (None, {})  # (danh sách chỉ mục đã dựng, cây) — dựng lại khi chỉ mục đổi
        self._code_check_at = 0.0
        self._quit_ok = False
        self._goal_status: dict[int, str] = {}  # để báo khi mục tiêu vừa kết thúc
        self._log_cut: dict[int, int] = {}  # nút Xoá log: vị trí (byte) trong file log bắt đầu hiện
        self._snap: dict | None = None  # DB đọc 1 lần cho mỗi lượt refresh_view
        self.notices = notify.Watcher()  # báo khi task lỗi / chờ duyệt (so trạng thái giữa các lượt vẽ)
        self._refresh_pending = False
        self._row_timer = None  # hẹn nạp log của dòng đang chọn (lướt bảng)
        # tab 🔲 Lưới: CLI thật của agent trong từng ô (grid.GridHub dùng chung với web), màn hình vterm theo ô
        self.grid = GridHub(root, lambda: self.cfg, lambda a: self.orch.terminal_session(a))
        self.grid.listen(self._on_grid)
        self.grid_screens: dict[str, vterm.Screen] = {}
        self.grid_focused: str | None = None
        self.grid_zoom: str | None = None
        self.grid_arrange = False  # F10: phím mũi tên… sắp xếp ô thay vì gửi vào CLI
        self.grid_drag: str | None = None
        self._last_key = ""

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs", initial="tab-board"):
            with TabPane(tr("📋 Bảng việc"), id="tab-board"):
                with Horizontal(id="board"):
                    with Vertical(id="left"):
                        yield Static(id="agents")
                        yield Static(id="goals")
                        with Horizontal(id="board-tools"):
                            yield Btn(tr("🗑 Dọn task đã xong"), id="board-clear")
                        yield TaskTable(id="tasks", cursor_type="row", zebra_stripes=True)
                        yield Static(id="tasks-empty")
                    with Vertical(id="right"):
                        yield Static(id="detail")
                        with Horizontal(id="log-tools"):
                            yield Btn(tr("🗑 Xoá log"), id="log-clear")
                        yield ReflowLog(id="log", wrap=True, markup=False, highlight=False,
                                      max_lines=5000, min_width=1)
            with TabPane(tr("🔲 Lưới"), id="tab-grid"):
                from .tui_grid import GridPanel
                yield GridPanel(id="grid-panel")
            with TabPane(tr("🤖 Agents"), id="tab-team"):
                with Vertical(id="team"):
                    with VerticalScroll(id="team-list"):
                        yield RolesTable(self.root, self.cfg, id="roles-table")
                        yield Static(Text.assemble((tr("🤖 Agent"), "bold"), ("   " + tr(
                            "Bấm vào một agent (hoặc F7) để chat riêng · bấm model/effort để đổi ngay · Esc về danh sách"),
                            "dim")), id="team-hint")
                        with Vertical(id="team-grid"):
                            for name in self.pane_order():
                                yield AgentPane(name)
                        yield CustomPanel(self.root, self.cfg, show="agents", id="agents-custom")
                    yield Timeline(id="timeline")
            with TabPane(tr("🔀 Workflows"), id="tab-custom"):
                yield CustomPanel(self.root, self.cfg, show="flows", id="custom-tab")
            with TabPane("📝 Code", id="tab-code"):
                with Horizontal(id="code"):
                    with Vertical(id="code-side"):
                        yield TextInput(id="code-filter", placeholder=tr("Tìm file… (Enter mở)"))
                        yield Btn(tr("＋ File mới"), id="code-new")
                        yield CodeFileList(id="code-files")
                    with Vertical(id="code-main"):
                        yield Static(id="code-head")
                        yield CodeEditor(id="code-editor")
                        yield Static(id="code-status")
            with TabPane("🌿 Git", id="tab-git"):
                with Vertical(id="git"):
                    with Horizontal(id="git-top"):
                        yield Static(id="git-head")
                        with Horizontal(id="git-actions"):
                            yield Btn(tr("▶ Tiếp tục"), id="git-continue", variant="success")
                            yield Btn(tr("✗ Huỷ merge"), id="git-abort", variant="error")
                            yield Btn("⇣ Fetch", id="git-fetch")
                            yield Btn("⬇ Pull", id="git-pull")
                            yield Btn("⬆ Push", id="git-push", variant="primary")
                            yield Btn(tr("⎇ Nhánh"), id="git-branches")
                            yield Btn("📦 Stash", id="git-stash")
                            yield Btn("⟳", id="git-refresh")
                    with Horizontal(id="git-main"):
                        with Vertical(id="git-side"):
                            yield GitFileList(id="git-files")
                            yield Static(id="git-empty")
                            with Horizontal(classes="git-row"):
                                yield Btn("± Stage", id="git-stage")
                                yield Btn(tr("+ Tất cả"), id="git-stage-all")
                                yield Btn(tr("↺ Bỏ thay đổi"), id="git-discard", variant="error")
                                yield Btn("Δ Diff", id="git-diff")
                            with Horizontal(classes="git-row"):
                                yield Btn(tr("↺ Bỏ tất cả"), id="git-discard-all", variant="error")
                                yield Btn(self._git_tree_label(), id="git-tree")
                            with Horizontal(classes="git-row", id="git-cf-row"):
                                yield Btn(tr("⇄ Giải quyết"), id="git-resolve", variant="warning")
                                yield Btn(tr("🤖 Nhờ agent"), id="git-ai-resolve")
                            yield TextInput(id="git-msg", placeholder=tr("Commit message — Enter để commit"))
                            with Horizontal(classes="git-row"):
                                yield Btn("✓ Commit", id="git-commit", variant="success")
                                yield Btn(tr("✨ AI viết"), id="git-ai", variant="primary")
                                yield Select(self.commit_agent_options(), value=self.cfg.commit_agent,
                                             allow_blank=False, id="git-ai-agent")
                            with Horizontal(classes="git-row"):
                                yield Checkbox(tr("Sửa commit trước"), id="git-amend")
                                yield Checkbox(tr("Bỏ qua hook (--no-verify)"), id="git-no-verify")
                        with Vertical(id="git-hist"):
                            yield Static(id="git-log-title")
                            yield GitLogList(id="git-log")
                            with Horizontal(classes="git-row"):
                                yield Btn(tr("Δ Xem commit"), id="git-show")
                                yield Btn("↶ Revert", id="git-revert")
                                yield Btn(tr("⎌ Bỏ commit cuối"), id="git-undo", variant="warning")
                    with Vertical(id="git-norepo"):
                        yield Static(Text.assemble(
                            (tr("Thư mục này chưa là git repo.\n\n"), "bold"),
                            tr("Tạo repo để theo dõi thay đổi, commit, và dùng chế độ worktree "
                               "(mỗi task một nhánh riêng).\n")))
                        yield Btn(tr("＋ Tạo git repo (git init)"), id="git-init", variant="success")
            with TabPane("💻 Terminal", id="tab-term"):
                with Horizontal(id="term"):
                    with Vertical(id="jobs-side"):
                        yield OptionList(id="jobs")
                        yield Static(id="jobs-empty")
                        with Horizontal(id="jobs-buttons"):
                            yield Btn(tr("■ Dừng"), id="job-stop", variant="error")
                            yield Btn(tr("↻ Chạy lại"), id="job-restart")
                            yield Btn(tr("✗ Xoá"), id="job-remove")
                        yield Static(Text(tr("📜 Script dự án — Enter / bấm để chạy"), "bold"), id="scripts-title")
                        yield OptionList(id="term-scripts")
                    with Vertical(id="job-view"):
                        yield Static(id="job-head")
                        yield ReflowLog(id="job-log", wrap=True, markup=False, highlight=False,
                                      max_lines=5000, min_width=1)
            with TabPane(tr("✅ To-do"), id="tab-todo"):
                from .tui_todo import NotesPanel, TodoPanel
                yield TodoPanel(self.root, id="todo-tab")
            with TabPane(tr("🗒 Ghi chú"), id="tab-notes"):
                yield NotesPanel(self.root, id="notes-tab")
            with TabPane(tr("📊 Thống kê"), id="tab-dash"):
                with VerticalScroll(id="dash"):
                    yield Static(id="dash-cards")
                    yield Static(id="dash-chart")
                    yield Static(tr("Theo agent · model (30 ngày)"), classes="dash-title")
                    yield DataTable(id="dash-agents", cursor_type="row", zebra_stripes=True)
                    yield Static(tr("Lịch sử mục tiêu  ·  Enter: tiếp tục mục tiêu (/continue)"),
                                 classes="dash-title")
                    yield DataTable(id="dash-goals", cursor_type="row", zebra_stripes=True)
                    yield Static(id="dash-goal")
                    yield Static(id="dash-note")
        yield GrillBar(id="grill")
        yield PlanBar(id="plan")
        yield Static(id="continue-hint")
        yield MentionList(id="mention")
        with Horizontal(id="cmd-row"):
            # gõ mục tiêu đi đâu: trưởng nhóm hay workflow mặc định — bấm (hoặc F4) để đổi
            yield Btn(wizard.mode_label(self.cfg) + " ▾", id="cmd-mode")
            yield CommandInput(self.root, id="cmd",
                               placeholder=tr("Nhập mục tiêu cho trưởng nhóm, /help, hoặc @ để nhắc file"))
        yield StatusBar(id="statusbar")
        yield Footer()

    async def on_mount(self) -> None:
        self.sub_title = str(self.root)
        st = load_state()
        self.apply_theme(st.get("theme") or theme.DEFAULT_THEME, st.get("accent") or "")
        ed = self.query_one("#code-editor", CodeEditor)
        ed.vim_on = st.get("vim", True) is not False
        ed.read_only = True  # chưa mở file nào
        table = self.query_one("#tasks", DataTable)
        table.add_column("#", key="id", width=4)
        table.add_column("Agent", key="agent", width=13)
        table.add_column(tr("Trạng thái"), key="status", width=12)
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
        self.query_one("#code").set_class(w < 110, "narrow")
        self.query_one("#git-top").set_class(w < 140, "narrow")

    def _preload_panes(self) -> None:
        """Nạp phần cuối log của task gần nhất cho mỗi ô agent."""
        tasks = self.db.tasks()
        for pane in self.query(AgentPane):
            last = [t for t in tasks if t.agent == pane.agent and t.started]
            if not last:
                pane.body.write(Text(tr("chưa có việc nào"), "dim"))
                continue
            t = last[-1]
            p = self.orch.log_path(t.id)
            label, style = STATUS.get(t.status, (t.status, ""))
            pane.body.write(Text(f"── #{t.id} {t.title} [{label}] ──", style))
            if p.exists():  # chỉ đọc phần cuối: log cũ có thể vài MB, mỗi agent một file lúc mở app
                for line in styled_lines(read_log_tail(p, limit=32 * 1024), pane.styler)[-40:]:
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
                label, style = STATUS.get(st, STATUS["done"]) if st else STATUS["done"]
                p.body.write(Text(f"── ■ {label} sau {fmt_dur(time.time() - act['started'])} ──", style))
        elif kind == "changed":
            self.schedule_refresh()

    def clear_board(self) -> None:
        n_tasks, n_goals = self.orch.clear_finished()
        if not n_tasks and not n_goals:
            self.notify(tr("Không có task nào đã kết thúc để dọn"))
            return
        if self.view_task != SYSTEM and not self.db.task(abs(self.view_task)):
            self.show_task(SYSTEM)  # log đang xem thuộc task vừa bị dọn
        self.notify(tr("🗑 Đã dọn {n_tasks} task", n_tasks=n_tasks) + (tr(", {n_goals} mục tiêu", n_goals=n_goals) if n_goals else ""))
        self.refresh_view()

    # ------------------------------------------------------------------ lệnh terminal
    def run_shell(self, cmd: str) -> None:
        cmd = cmd.strip()
        if not cmd:
            self.notify(tr("Gõ lệnh sau dấu !, vd !yarn dev (gõ ! để xem gợi ý)"), severity="warning")
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
                    tr("── {v} (mã {rc}) sau {v2} ──", v=tr('✓ xong') if ok else tr('■ đã dừng') if job.status == 'stopped' else tr('✗ lỗi'), rc=job.rc, v2=fmt_dur(job.finished - job.started)),
                    "green" if ok else "dim" if job.status == "stopped" else "bold red"))
            if job.status == "failed":
                self.notify(tr("✗ Lệnh lỗi (mã {rc}): {cmd}", rc=job.rc, cmd=job.cmd), severity="warning", timeout=5)
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

    def load_scripts(self, force: bool = False) -> None:
        """Danh sách 📜 Script dự án ở tab Terminal (package.json, Makefile, lệnh gần đây) — đọc lại tối đa
        30 giây/lần, khi mở tab."""
        if not force and time.time() - getattr(self, "_scripts_at", 0) < 30:
            return
        self._scripts_at = time.time()
        items = shell.project_scripts(self.root)
        ol = self.query_one("#term-scripts", OptionList)
        ids = [c for c, _d in items]
        if ids == getattr(self, "_script_ids", None):
            return
        self._script_ids = ids
        width = min(30, max((len(c) for c in ids), default=0) + 2)
        ol.clear_options()
        for cmd, desc in items:
            t = Text(cmd.ljust(width), "bold cyan")
            t.append(desc, "dim")
            ol.add_option(Option(t, id=cmd))
        self.query_one("#scripts-title").display = ol.display = bool(items)

    def _refresh_jobs(self) -> None:
        jobs = list(self.shell.jobs.values())
        ol = self.query_one("#jobs", OptionList)
        empty = self.query_one("#jobs-empty", Static)
        ol.display, empty.display = bool(jobs), not jobs
        self.query_one("#jobs-buttons").display = bool(jobs)
        if not jobs:
            t = Text(tr("Chưa chạy lệnh nào.\n\n"), "bold")
            t.append(tr("Gõ "), "")
            t.append(tr("!lệnh"), "bold cyan")
            t.append(tr(" ở ô nhập, vd "))
            t.append("!yarn dev", "bold cyan")
            t.append(tr(".\nGõ "))
            t.append("!", "bold cyan")
            t.append(tr(" để xem gợi ý script của dự án (package.json, Makefile, lệnh gần đây).\n\n"))
            t.append(tr("Lệnh chạy trong thư mục dự án, nhiều lệnh song song được; thoát app "
                        "(Ctrl+Q) sẽ dừng mọi lệnh đang chạy."), "dim")
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
        label = {"running": (tr("đang chạy"), RUNNING), "done": (tr("xong"), "green"),
                 "failed": (tr("lỗi (mã {rc})", rc=job.rc), "bold red"), "stopped": (tr("đã dừng"), "dim")}[job.status]
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

    # ------------------------------------------------------------------ lưới (tab 🔲 Lưới)
    def grid_screen(self, cid: str) -> vterm.Screen:
        scr = self.grid_screens.get(cid)
        if scr is None:
            t = self.grid.terms.get(cid)

            def reply(b: bytes, cid=cid) -> None:  # trả lời truy vấn của CLI (vị trí con trỏ…)
                t2 = self.grid.terms.get(cid)
                if t2 and t2.alive:
                    t2.session.write(b)
            scr = self.grid_screens[cid] = vterm.Screen(24, 80, reply=reply)
            if t and t.buf:
                scr.feed(bytes(t.buf))
        return scr

    def _on_grid(self, cid: str, kind: str, payload) -> None:
        if kind == "data":
            if cid in self.grid_screens:
                self.grid_screens[cid].feed(payload)
            else:
                self.grid_screen(cid)  # màn hình mới nạp cả bộ đệm (đã gồm payload)
        elif kind == "layout":
            for k in [k for k in self.grid_screens if not self.grid.layout.find(k)]:
                del self.grid_screens[k]  # ô đã đóng

    def grid_tab_shown(self) -> None:
        from .tui_grid import GridCell, GridPanel
        panel = self.query_one("#grid-panel", GridPanel)
        cells = list(panel.query(GridCell))
        target = next((g for g in cells if g.cell_id == self.grid_focused), cells[0] if cells else None)
        if target:
            target.focus_term()

    def action_grid_arrange(self) -> None:
        from .tui_grid import GridPanel
        self.grid_arrange = not self.grid_arrange
        self.query_one("#grid-panel", GridPanel).set_hint("")
        if self.grid_arrange:
            self.grid_tab_shown()

    def grid_arrange_key(self, key: str) -> None:
        from .tui_grid import GridPanel
        self.query_one("#grid-panel", GridPanel).arrange_key(key)

    # ------------------------------------------------------------------ code (tab 📝 Code)
    CODE_LIMIT = 10  # số buffer giữ cùng lúc
    # phím tắt của app trùng phím vim (Ctrl+D/U/R…): nhường cho editor khi đang gõ trong đó
    CODE_YIELD = {"diff", "cancel_task", "retry", "approve", "continue", "merge", "syslog"}

    async def on_event(self, event) -> None:
        if isinstance(event, events.Key):
            self._last_key = event.key  # check_action: phím Ctrl khi đang gõ trong ô của tab Lưới là của CLI
        await super().on_event(event)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "grid_arrange":
            return self.query_one("#tabs", TabbedContent).active == "tab-grid" and not isinstance(
                self.screen, ModalScreen)
        if self._last_key.startswith("ctrl+") and action != "quit":
            from .tui_grid import TermView
            if isinstance(self.focused, TermView):
                return False  # Ctrl+R, Ctrl+T, Ctrl+O… trong CLI: nhường cho CLI
        if action == "palette" and isinstance(self.screen, ModalScreen):
            return False  # đang mở popup khác (kể cả chính palette): để phím cho popup đó
        if action == "retry" and isinstance(self.screen, SearchScreen):
            return False  # Ctrl+R trong popup 🔍 = thay tất cả
        if action in self.CODE_YIELD:
            f = self.focused
            if isinstance(f, CodeEditor) and f.buffer is not None:
                return False
        return True

    def code_editor(self) -> CodeEditor:
        return self.query_one("#code-editor", CodeEditor)

    def code_rel(self, key: str) -> str:
        try:
            return str(Path(key).relative_to(self.root))
        except ValueError:
            return key

    def code_unsaved(self) -> list[str]:
        self._stash_code()
        return [self.code_rel(k) for k in self.code_order if self.code_bufs[k].get("dirty")]

    def code_tab_shown(self) -> None:
        ed = self.code_editor()
        if ed.buffer is not None:
            ed.focus()
        else:
            self.query_one("#code-filter", Input).focus()
        idx = self.query_one("#cmd", CommandInput).index
        if idx.stale():
            async def load() -> None:
                await idx.refresh()
                self.refresh_code_files()
            self.run_worker(load(), exclusive=True, group="code-index")
        self.refresh_code_files()
        self._refresh_code_head()

    def refresh_code_files(self) -> None:
        """Danh sách bên trái: buffer đang mở, rồi cây thư mục (ô lọc trống) hoặc file khớp ô lọc (chỉ mục @file)."""
        ol = self.query_one("#code-files", CodeFileList)
        q = self.query_one("#code-filter", Input).value.strip()
        ed = self.code_editor()
        opts: list = []
        seen = set()
        cur = self.code_rel(self.code_cur) if self.code_cur else None
        if self.code_order:
            opts.append(Option(Text(tr("Đang mở"), "bold dim"), disabled=True))
            for key in self.code_order:
                rel = self.code_rel(key)
                if q and mentions.score(rel, q) is None:
                    continue
                dirty = ed.dirty if key == self.code_cur else self.code_bufs[key].get("dirty")
                t = Text(no_wrap=True, overflow="ellipsis")
                t.append("● " if dirty else "  ", PAL.get("warn", "yellow"))
                t.append(rel, "bold" if key == self.code_cur else "")
                opts.append(Option(t, id="f:" + rel))
                seen.add(rel)
        entries = self.query_one("#cmd", CommandInput).index.entries
        if not q:
            if self._code_tree[0] is not entries:
                self._code_tree = (entries, editor.build_tree([e for e in entries if not e.endswith("/")]))
            rows = editor.tree_rows(self._code_tree[1], self.code_open)
            if rows:
                opts.append(Option(Text(tr("Thư mục dự án"), "bold dim"), disabled=True))
            for guide, path, name, is_dir in rows:
                t = Text(guide, "dim", no_wrap=True, overflow="ellipsis")
                if is_dir:
                    t.append("▾ " if path in self.code_open else "▸ ", "dim")
                    t.append(name, f"bold {PAL.get('info', 'cyan')}")
                    opts.append(Option(t, id="d:" + path))
                else:
                    t.append("" if guide else "  ")
                    t.append(name, "bold" if path == cur else "")
                    opts.append(Option(t, id="t:" + path))
        else:
            files = [e for e in entries if not e.endswith("/")]
            found = [f for f in mentions.search(files, q, limit=300) if f not in seen]
            if found:
                opts.append(Option(Text(tr("File"), "bold dim"), disabled=True))
                opts += [Option(Text(f, no_wrap=True, overflow="ellipsis"), id="f:" + f) for f in found]
        key = [(o.id, o.prompt.plain) for o in opts]
        if key == getattr(ol, "_ids", None) and q == getattr(ol, "_q", None):
            return
        keep = ol.get_option_at_index(ol.highlighted).id if ol.highlighted is not None and ol.option_count else None
        same_q = q == getattr(ol, "_q", None)
        ol._ids, ol._q = key, q
        ol.clear_options()
        ol.add_options(opts)
        ids = [o.id for o in opts]
        if same_q and keep in ids:  # mở/thu gọn thư mục, lưu file…: con trỏ đứng yên chỗ cũ
            ol.highlighted = ids.index(keep)
            return
        first = next((i for i, o in enumerate(opts) if o.id and o.id[2:] not in seen), None)
        if q and first is not None:
            ol.highlighted = first

    def action_code_fold(self, expand: int) -> None:
        """→/l mở thư mục (đã mở thì xuống mục con đầu), ←/h thu gọn (trên file hoặc thư mục đã đóng: về thư mục cha)."""
        ol = self.query_one("#code-files", CodeFileList)
        if ol.highlighted is None:
            return
        oid = ol.get_option_at_index(ol.highlighted).id or ""
        kind, path = oid[:2], oid[2:]
        if expand:
            if kind != "d:":
                return
            if path in self.code_open:
                ol.action_cursor_down()
            else:
                self.code_fold(path)
            return
        if kind == "d:" and path in self.code_open:
            self.code_fold(path)
            return
        parent = path.rstrip("/").rpartition("/")[0]
        if parent and kind in ("d:", "t:"):
            ids = [ol.get_option_at_index(i).id for i in range(ol.option_count)]
            if "d:" + parent + "/" in ids:
                ol.highlighted = ids.index("d:" + parent + "/")

    def code_fold(self, path: str) -> None:
        """Mở / thu gọn một thư mục của cây (đóng thư mục cha thì thư mục con vẫn nhớ trạng thái mở)."""
        self.code_open.symmetric_difference_update({path})
        self.refresh_code_files()

    # ------------------------------------------------------------------ 🔍 tìm & thay trong dự án (F3, /search)
    def action_search(self, query: str | None = None) -> None:
        st = self.search_state
        ed = self.code_editor()
        sel = ed.selected_text if ed.buffer is not None else ""
        if query is None and sel and "\n" not in sel:
            query = sel  # đang chọn chữ trong editor: tìm luôn chữ đó
        if query is not None:
            st["query"] = query

        def done(r) -> None:
            if r:
                path, line, col = r
                self.open_code(path, line, col)
        self.push_screen(SearchScreen(st), done)

    async def search_files(self) -> list[str]:
        idx = self.query_one("#cmd", CommandInput).index
        if idx.stale():
            await idx.refresh()
        return list(idx.entries)

    async def after_replace(self, paths: list[str], st: dict, n: int) -> None:
        """Sau khi thay: file đang mở (đã chắc chắn không sửa dở) nạp lại; ghi vào log hệ thống."""
        self.orch.log(tr("🔍 Thay \"{q}\" → \"{r}\": {n} chỗ trong {f} file", q=st["query"], r=st["replace"], n=n,
                         f=len(paths)))
        changed = {str(Path(os.path.normpath(str(self.root / p)))) for p in paths}
        for key in changed & set(self.code_bufs):
            self.code_bufs[key].update(dirty=False, text=None)
        ed = self.code_editor()
        if ed.buffer is not None and str(ed.buffer.path) in changed:
            await self.code_reload(keep_message=True)

    def open_code(self, target: str = "", line: int | None = None, col: int = 0) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-code"
        if not target:
            self.code_tab_shown()
            return
        self.run_worker(self._open_code(target, line, col), exclusive=True, group="code-open")

    def _stash_code(self) -> None:
        """Ghi trạng thái buffer đang hiện (con trỏ, nội dung chưa lưu) trước khi đổi buffer."""
        ed = self.code_editor()
        if self.code_cur and self.code_cur in self.code_bufs and ed.buffer is not None:
            b = self.code_bufs[self.code_cur]
            b["cursor"] = ed.cursor_location
            b["dirty"] = ed.dirty
            b["text"] = ed.text if ed.dirty else None

    async def _open_code(self, target: str, line: int | None = None, col: int = 0) -> None:
        path = Path(target).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = Path(os.path.normpath(str(path)))
        key = str(path)
        ed = self.code_editor()
        if path.is_dir():
            rel = self.code_rel(key).rstrip("/") + "/"
            if rel.startswith("../") or Path(rel).is_absolute():  # ngoài dự án: không có trong cây, lọc như cũ
                self.query_one("#code-filter", Input).value = rel
                self.query_one("#code-filter", Input).focus()
                return
            if rel != "./":
                self.code_open.update(editor.parent_dirs(rel + "x") + [rel])  # mở cây tới thư mục đó
            self.query_one("#code-filter", Input).value = ""
            self.refresh_code_files()
            ol = self.query_one("#code-files", CodeFileList)
            ids = [ol.get_option_at_index(i).id for i in range(ol.option_count)]
            if "d:" + rel in ids:
                ol.highlighted = ids.index("d:" + rel)
            ol.focus()
            return
        self.code_open.update(editor.parent_dirs(self.code_rel(key)))  # cây thư mục mở tới file đang sửa
        self._stash_code()
        b = self.code_bufs.get(key)
        if b is not None and b.get("dirty"):
            sf, text = b["sf"], b["text"]
        else:
            sf = await asyncio.to_thread(editor.read_source, path)
            if sf.error:
                self.notify(f"{self.code_rel(key)}: {sf.error}", severity="warning")
                return
            text = None
        cursor = (line - 1, 0) if line else (b or {}).get("cursor", (0, 0))
        if key not in self.code_bufs:
            self.code_bufs[key] = {"sf": sf}
            self.code_order.append(key)
            self._trim_code_bufs(key)
        self.code_bufs[key].update(sf=sf, dirty=text is not None, text=text)
        self.code_cur = key
        ed.load(sf, cursor=cursor, dirty_text=text)
        if line:
            row = max(0, min(line - 1, ed.document.line_count - 1))
            ed.move_cursor((row, col or editor.first_nonblank(ed.document[row])), center=True)
        if not sf.mtime and not sf.text:
            ed.message = tr("File mới — :w để tạo")
        ed.focus()
        if sf.mtime:
            palette.touch_recent(self.root, self.code_rel(key))
        self._code_syms = (key, None)  # symbol cho thanh "đang ở đâu": tính lại khi cần
        self.refresh_code_files()
        self._refresh_code_head()

    def _trim_code_bufs(self, keep: str) -> None:
        while len(self.code_order) > self.CODE_LIMIT:
            old = next((k for k in self.code_order if k != keep and not self.code_bufs[k].get("dirty")), None)
            if old is None:
                break
            self.code_order.remove(old)
            self.code_bufs.pop(old, None)

    def code_close(self, force: bool = False) -> None:
        ed = self.code_editor()
        if not self.code_cur:
            return
        if ed.dirty and not force:
            ed.message = tr("Chưa lưu — :w để lưu, :q! để bỏ thay đổi")
            self._refresh_code_head()
            return
        key = self.code_cur
        self.code_order.remove(key)
        self.code_bufs.pop(key, None)
        self.code_cur = None
        if self.code_order:
            self.open_code(self.code_rel(self.code_order[-1]))
            return
        ed.buffer = None
        ed.highlight_on = False
        ed.load_text("")
        ed.read_only = True
        ed.vim = editor.VimState()
        ed.set_class(False, "-insert")
        self.refresh_code_files()
        self._refresh_code_head()
        self.query_one("#code-filter", Input).focus()

    def code_cycle(self, delta: int) -> None:
        if len(self.code_order) < 2 or self.code_cur not in self.code_order:
            return
        i = (self.code_order.index(self.code_cur) + delta) % len(self.code_order)
        self.open_code(self.code_rel(self.code_order[i]))

    # ---------------------------------------------------------------- command palette (tab 📝 Code)
    def action_palette(self, query: str = "") -> None:
        """Ctrl+P mở nhanh file · F8 (Ctrl+Shift+P) lệnh · F9 (Ctrl+Shift+O) symbol trong file đang mở."""
        ed = self.code_editor()
        sf = ed.buffer
        self._pal_syms = palette.symbols(sf.path, ed.text) if sf is not None and query.startswith("@") else None
        self.push_screen(PaletteScreen(query), self._palette_done)

    def palette_items(self, text: str) -> list[tuple[Text, object]]:
        """Các dòng của palette theo chữ đang gõ: (nhãn, giá trị) — giá trị None = dòng tiêu đề / gợi ý."""
        ed = self.code_editor()
        sf = ed.buffer
        dim = "dim"

        def head(msg: str) -> tuple[Text, None]:
            return Text(msg, dim), None

        if text.startswith(">"):
            out = []
            for cid, label, key, _web in palette.fuzzy(palette.CODE_COMMANDS, text[1:],
                                                         key=lambda c: c[1] + " " + palette.KEYWORDS.get(c[0], "")):
                if (cid in palette.NEEDS_FILE and sf is None) or cid in palette.TUI_SKIP:
                    continue
                t = Text(label)
                if key:
                    t.append(f"   {key}", dim)
                out.append((t, ("cmd", cid)))
            return out or [head(tr("Không có lệnh nào khớp"))]
        if sf is None and text[:1] in ("@", ":", "/"):
            return [head(tr("Chưa mở file nào — gõ tên file để mở"))]
        if text.startswith("@"):
            if getattr(self, "_pal_syms", None) is None:
                self._pal_syms = palette.symbols(sf.path, ed.text)
            icons = {"class": "◆", "type": "◇", "function": "ƒ", "method": "ƒ", "heading": "#"}
            out = []
            for sym in palette.fuzzy(self._pal_syms, text[1:], key=lambda x: x["name"]):
                t = Text("  " * sym["depth"] + icons.get(sym["kind"], "•") + " ", dim)
                t.append(sym["name"])
                t.append(f"  :{sym['line']}", dim)
                out.append((t, ("line", sym["line"], 0)))
            return out or [head(tr("Không thấy symbol (hàm, class, heading) nào"))]
        if text.startswith(":"):
            arg = text[1:].strip()
            n = ed.document.line_count
            if arg.isdigit() and 1 <= int(arg) <= n:
                return [(Text(tr("Tới dòng {v}", v=arg)), ("line", int(arg), 0))]
            return [head(tr("Gõ số dòng (1–{n})", n=n))]
        if text.startswith("/"):
            q = text[1:]
            if not q:
                return [head(tr("Gõ chữ cần tìm trong file"))]
            ql, out = q.lower(), []
            for i, line in enumerate(ed.document.lines, 1):
                col = line.lower().find(ql)
                if col >= 0:
                    t = Text(f"{i:>5}  ", dim)
                    t.append(line.strip()[:120])
                    out.append((t, ("line", i, col)))
                    if len(out) >= 300:
                        break
            return out or [head(tr("Không thấy \"{v}\" trong file", v=q))]
        # mở nhanh file: file gần đây trước, rồi khớp mờ trong cả dự án
        idx = self.query_one("#cmd", CommandInput).index
        if idx.stale():
            self.run_worker(idx.refresh(), group="mention-index")
        files = [e for e in idx.entries if not e.endswith("/")]
        known = set(files)
        recent = [f for f in palette.recent_files(self.root) if f in known or (self.root / f).is_file()]
        out = []
        if not text.strip():
            if recent:
                out.append(head(tr("Mở gần đây")))
                out += [(Text(f), ("file", f)) for f in recent]
            out.append(head(tr("Gõ tên file · > lệnh · @ symbol · :dòng · /tìm trong file")))
            return out
        hits = palette.fuzzy(recent, text, limit=8)
        out += [(Text("🕘 " + f), ("file", f)) for f in hits]
        seen = set(hits)
        out += [(Text(f), ("file", f)) for f in mentions.search(files, text, limit=80) if f not in seen]
        return out or [head(tr("Không có file nào khớp — > để xem lệnh"))]

    def _palette_done(self, value) -> None:
        if not value:
            return
        kind = value[0]
        if kind == "file":
            self.open_code(value[1])
        elif kind == "line":
            ed = self.code_editor()
            row = max(0, min(value[1] - 1, ed.document.line_count - 1))
            self.query_one("#tabs", TabbedContent).active = "tab-code"
            ed.move_cursor((row, value[2] if len(value) > 2 else 0), center=True)
            ed.focus()
        elif kind == "cmd":
            self.code_command(value[1])

    # ---------------------------------------------------------------- mở folder / dự án khác (/open)
    def action_open_project(self, query: str = "") -> None:
        """Popup chọn dự án: dự án gần đây, hoặc gõ đường dẫn (Tab đi vào thư mục con)."""
        self.push_screen(PaletteScreen(query, items=self.project_items,
                                       placeholder=tr("Tên dự án gần đây, hoặc đường dẫn: ~/code/app, ../app-khac"),
                                       foot=tr("↑↓ chọn · Tab đi vào thư mục · Enter mở · Esc đóng"),
                                       complete=lambda v: projects.shorten(v[1]) + "/"),
                         lambda v: v and self.open_project(v[1]))

    def project_items(self, text: str) -> list[tuple[Text, object]]:
        out: list[tuple[Text, object]] = []
        items = projects.candidates(text, self.root)
        if not text.strip() and items:
            out.append((Text(tr("Dự án gần đây"), "dim"), None))
        for it in items:
            t = Text(("🕘 " if it["kind"] == "recent" else "📁 ") + it["name"])
            t.append("  " + it["where"], "dim")
            if it["kind"] == "current":
                t.append("  " + tr("(đang mở)"), "dim")
            out.append((t, None if it["kind"] == "current" else ("project", it["path"])))
        if not out or all(v is None for _t, v in out):
            out.append((Text(tr("Gõ đường dẫn thư mục, vd ~/code/app") if not text.strip()
                             else tr("Không có thư mục nào khớp"), "dim"), None))
        return out

    def open_project(self, text: str) -> None:
        """Mở lại app ở thư mục khác (cli.cmd_tui chạy lại với -C): agent đang chạy thì hỏi trước."""
        if "WebDriver" in os.environ.get("TEXTUAL_DRIVER", ""):
            self.notify(tr("Trong trình duyệt (ateam web --tui) không đổi được dự án — chạy lại: "
                           "ateam web --tui -C {v}", v=text), severity="warning", timeout=10)
            return
        path, err = projects.check_target(text, self.root)
        if path is None:
            self.notify(err, severity="warning")
            return

        def go(ok) -> None:
            if ok:
                self.restart_root, self.restart_requested = path, True
                self.call_later(self.action_quit)
        busy = len(self.orch.runs) + len(self.orch.lead_busy)
        if busy:
            self.push_screen(ConfirmScreen(tr("Đang có agent chạy"),
                                           tr("{n} lượt agent đang chạy sẽ bị dừng (task dở thành lỗi — quay lại "
                                              "dự án này thì /retry).\nMở {v}?", n=busy, v=projects.shorten(path)),
                                           yes=tr("Dừng & mở")), go)
        else:
            go(True)

    def code_selection_ref(self) -> str:
        """"@đường/dẫn" kèm dòng đang chọn (hoặc dòng con trỏ) — để hỏi / giao việc cho agent."""
        ed = self.code_editor()
        rel = self.code_rel(str(ed.buffer.path))
        a, b = sorted((ed.selection.start[0], ed.selection.end[0]))
        if ed.selection.start == ed.selection.end:
            return f"@{rel}"
        return f"@{rel} " + (tr("(dòng {a})", a=a + 1) if a == b else tr("(dòng {a}–{b})", a=a + 1, b=b + 1))

    def code_command(self, cid: str) -> None:
        """Chạy một lệnh của palette (`palette.CODE_COMMANDS`)."""
        ed = self.code_editor()
        sf = ed.buffer
        rel = self.code_rel(str(sf.path)) if sf is not None else ""
        if cid in palette.NEEDS_FILE and sf is None:
            self.notify(tr("Chưa mở file nào"), severity="warning")
            return
        simple = {"save": "w", "close": "q", "next": "bn", "prev": "bp", "toggle_files": "files"}
        if cid in simple:
            self.code_ex(simple[cid])
        elif cid in ("quick_open", "goto_symbol", "goto_line", "find"):
            self.action_palette({"quick_open": "", "goto_symbol": "@", "goto_line": ":", "find": "/"}[cid])
        elif cid == "search_project":
            self.action_search()
        elif cid == "save_all":
            self.run_worker(self.code_save_all(), group="code-save")
        elif cid == "toggle_wrap":
            ed.set_wrap(not ed.soft_wrap)
            ed.message = tr("Xuống dòng mềm: bật") if ed.soft_wrap else tr("Xuống dòng mềm: tắt")
            self._refresh_code_head()
        elif cid == "toggle_numbers":
            ed.show_line_numbers = not ed.show_line_numbers
        elif cid == "toggle_vim":
            self.run_command("/vim " + ("off" if ed.vim_on else "on"))
        elif cid == "copy_path":
            ref = f"{rel}:{ed.cursor_location[0] + 1}"
            self.copy_to_clipboard(ref)
            self.notify(tr("Đã chép {v}", v=ref))
        elif cid == "open_vscode":
            self.run_worker(self._open_vscode(sf.path, ed.cursor_location[0] + 1), group="vscode")
        elif cid == "git_diff":
            self.run_worker(self._code_git_diff(rel), group="code-diff")
        elif cid == "new_file":
            base = (str(Path(rel).parent) + "/") if rel and Path(rel).parent != Path(".") else ""
            self.push_screen(PromptScreen(tr("📄 File mới"), base, tr("đường/dẫn/file.ext")), self._code_new_file)
        elif cid == "rename_file":
            self.push_screen(PromptScreen(tr("✎ Đổi tên / chuyển {v}", v=rel), rel), self._code_rename_file)
        elif cid == "delete_file":
            def done(ok) -> None:
                if ok:
                    self.run_worker(self._code_delete_file(rel), group="code-open")
            self.push_screen(ConfirmScreen(tr("Xoá file"), tr("Đưa {v} vào Thùng rác?", v=rel), yes=tr("Xoá")), done)
        elif cid in ("ask_agent", "task_agent"):
            self._code_ask_agent(cid == "task_agent")
        elif cid == "open_folder":
            self.action_open_project()

    async def code_save_all(self) -> None:
        """Lưu file đang mở và mọi buffer chưa lưu khác (bỏ qua file chỉ đọc / đổi trên đĩa — báo lại)."""
        self._stash_code()
        cur = self.code_cur
        problems = []
        for key in list(self.code_order):
            b = self.code_bufs.get(key) or {}
            if key == cur or not b.get("dirty") or b.get("text") is None:
                continue
            err = await asyncio.to_thread(editor.save_source, b["sf"], b["text"], False)
            if err:
                problems.append(f"{self.code_rel(key)}: {err}")
            else:
                b["sf"].text = b["text"]
                b.update(dirty=False, text=None)
        if self.code_editor().dirty:
            await self.code_save()
        self.refresh_code_files()
        if problems:
            self.notify("\n".join(problems), severity="warning", timeout=10)

    async def _open_vscode(self, path: Path, line: int) -> None:
        if not shutil.which("code"):
            self.notify(tr("Không thấy lệnh 'code' — trong VS Code: Shell Command: Install 'code' command"),
                        severity="warning")
            return
        proc = await asyncio.create_subprocess_exec("code", "-g", f"{path}:{line}", stdin=asyncio.subprocess.DEVNULL,
                                                    stdout=asyncio.subprocess.DEVNULL,
                                                    stderr=asyncio.subprocess.DEVNULL)
        self.notify(tr("Đang mở {path} trong VS Code…", path=self.code_rel(str(path))), timeout=3)
        await proc.wait()

    async def _code_git_diff(self, rel: str) -> None:
        ds = await self.git.changes_diffset(staged=False)
        idx = next((i for i, f in enumerate(ds.files) if f.path == rel), None)
        if idx is None:
            ds = await self.git.changes_diffset(staged=True)
            idx = next((i for i, f in enumerate(ds.files) if f.path == rel), None)
        if idx is None:
            self.notify(tr("{v}: không có thay đổi so với git", v=rel))
            return
        self.push_screen(DiffScreen(ds, has_code=bool(shutil.which("code")), start=idx))

    def _code_new_file(self, rel: str | None) -> None:
        if not rel:
            return
        err = palette.file_new(self.root, rel)
        if err:
            self.notify(err, severity="warning")
            return
        self.query_one("#cmd", CommandInput).index.loaded_at = 0  # Ctrl+P / @ thấy file mới ngay
        self.open_code(rel)

    def _code_rename_file(self, new: str | None) -> None:
        ed = self.code_editor()
        if not new or ed.buffer is None:
            return
        old_key = str(ed.buffer.path)
        old = self.code_rel(old_key)
        if new == old:
            return
        if ed.dirty:
            self.notify(tr("Lưu file trước khi đổi tên"), severity="warning")
            return
        err = palette.file_rename(self.root, old, new)
        if err:
            self.notify(err, severity="warning")
            return
        self.code_order.remove(old_key)
        self.code_bufs.pop(old_key, None)
        self.code_cur = None
        self.query_one("#cmd", CommandInput).index.loaded_at = 0
        self.notify(tr("Đã đổi {v} → {v2}", v=old, v2=new))
        self.open_code(new, ed.cursor_location[0] + 1)

    async def _code_delete_file(self, rel: str) -> None:
        err = await palette.file_trash(self.root, rel)
        if err:
            self.notify(err, severity="warning")
            return
        key = str(Path(os.path.normpath(str(self.root / rel))))
        if self.code_cur == key:
            self.code_close(force=True)
        elif key in self.code_bufs:
            self.code_order.remove(key)
            self.code_bufs.pop(key, None)
        self.notify(tr("Đã đưa {v} vào Thùng rác", v=rel))
        self.refresh_code_files()

    def _code_ask_agent(self, as_task: bool) -> None:
        """Hỏi (chat 💬) hoặc giao task cho một agent về file / đoạn đang chọn: chọn agent rồi gõ yêu cầu."""
        ref = self.code_selection_ref()
        agents = list(self.cfg.active_agents())

        def ask(agent) -> None:
            if agent is None:
                return
            agent = self.cfg.lead if agent == RESET else agent

            def send(text: str | None) -> None:
                if not text:
                    return
                msg = f"{ref}: {text}"
                if as_task:
                    self.orch.add_task(agent, msg)
                    self.notify(tr("Đã giao cho {agent}: {v}", agent=agent, v=msg[:80]))
                else:
                    self.send_chat(agent, msg)
                    self.notify(tr("Đã hỏi {agent} — xem trả lời ở tab 🤖 Agents", agent=agent))
            title = (tr("Giao task cho {agent} về {v}", agent=agent, v=ref) if as_task
                     else tr("Hỏi {agent} về {v}", agent=agent, v=ref))
            self.push_screen(PromptScreen(title, placeholder=tr("vd: giải thích đoạn này / viết test cho hàm này")),
                             send)
        self.push_screen(ChoiceScreen(tr("Chọn agent"), agents, "", tr("★ trưởng nhóm ({lead})", lead=self.cfg.lead)),
                         ask)

    def code_ex(self, cmd: str) -> None:
        """Lệnh `:` của editor (w, q, wq, e!, bn…)."""
        ed = self.code_editor()
        name, _, arg = cmd.strip().partition(" ")
        arg = arg.strip()
        if ed.buffer is None and name not in ("e", "edit", "files", "Ex", "Lex", "new", "enew"):
            ed.message = tr("Chưa mở file nào")
        elif name in ("w", "w!", "write", "update"):
            self.run_worker(self.code_save(force=name.endswith("!")), group="code-save")
        elif name in ("wq", "x", "wq!", "x!", "xit"):
            self.run_worker(self.code_save(force=name.endswith("!"), close=True), group="code-save")
        elif name in ("q", "quit", "bd", "bdelete", "close"):
            self.code_close()
        elif name in ("q!", "quit!", "bd!"):
            self.code_close(force=True)
        elif name in ("e!", "edit!"):
            self.run_worker(self.code_reload(), group="code-open")
        elif name in ("new", "enew"):  # :new [đường/dẫn] — trống thì hỏi tên (như nút ＋ File mới)
            if arg:
                self._code_new_file(arg)
            else:
                self.code_command("new_file")
        elif name in ("e", "edit") and arg:
            target, line = parse_code_target(arg)
            self.open_code(target, line)
        elif name in ("bn", "bnext"):
            self.code_cycle(1)
        elif name in ("bp", "bprevious", "bprev", "bN"):
            self.code_cycle(-1)
        elif name in ("files", "Ex", "Lex", "e", "edit"):
            box = self.query_one("#code")
            box.set_class(not box.has_class("hide-side"), "hide-side")
            if not box.has_class("hide-side"):
                self.query_one("#code-filter", Input).focus()
        elif name == "set" and arg in ("nu", "number", "nonu", "nonumber"):
            ed.show_line_numbers = arg in ("nu", "number")
        elif name == "set" and arg in ("wrap", "nowrap"):
            ed.set_wrap(arg == "wrap")
        elif name in ("noh", "nohlsearch"):
            pass
        else:
            ed.message = tr("Lệnh không hỗ trợ: :{cmd}", cmd=cmd)
        self._refresh_code_head()

    async def code_save(self, force: bool = False, close: bool = False) -> None:
        ed = self.code_editor()
        sf = ed.buffer
        if sf is None:
            return
        if sf.read_only and not force:
            ed.message = tr("Chỉ đọc ({v}) — :w! để vẫn ghi", v=sf.note)
            self._refresh_code_head()
            return
        gen, text = ed._gen, ed.text
        err = await asyncio.to_thread(editor.save_source, sf, text, force)
        if err == "conflict":
            def done(ok) -> None:
                if ok:
                    self.run_worker(self.code_save(force=True, close=close), group="code-save")
            self.push_screen(ConfirmScreen(
                tr("File đã đổi trên đĩa"),
                tr("{path} vừa bị sửa bên ngoài (có thể do agent) sau khi bạn mở.\nGhi đè bằng nội dung của "
                   "bạn? (Huỷ rồi :e! để nạp bản trên đĩa)", path=self.code_rel(str(sf.path))),
                yes=tr("Ghi đè")), done)
            return
        if err:
            ed.message = err
            self._refresh_code_head()
            return
        sf.text = text
        if ed.buffer is sf:
            ed._saved_gen = gen
        if str(sf.path) in self.code_bufs:
            self.code_bufs[str(sf.path)].update(dirty=False, text=None)
        ed.message = tr("Đã lưu {path} · {n} dòng", path=self.code_rel(str(sf.path)), n=text.count("\n") + 1)
        self._code_syms = (None, None)
        self.refresh_code_files()
        self._refresh_code_head()
        if close and ed.buffer is sf and not ed.dirty:
            self.code_close()

    async def code_reload(self, keep_message: bool = False) -> None:
        ed = self.code_editor()
        sf = ed.buffer
        if sf is None:
            return
        cursor = ed.cursor_location
        new = await asyncio.to_thread(editor.read_source, sf.path)
        if new.error:
            ed.message = new.error
            return
        self.code_bufs.setdefault(str(sf.path), {}).update(sf=new, dirty=False, text=None)
        ed.load(new, cursor=cursor)
        if not keep_message:
            ed.message = tr("Đã nạp lại từ đĩa")
        self.refresh_code_files()
        self._refresh_code_head()

    def _check_code_disk(self) -> None:
        """File đang mở bị sửa bên ngoài (agent): buffer sạch tự nạp lại, buffer đang sửa thì báo."""
        now = time.time()
        if now - self._code_check_at < 2:
            return
        self._code_check_at = now
        ed = self.code_editor()
        sf = ed.buffer
        if sf is None or not sf.mtime:
            return
        m = editor.disk_mtime(sf.path)
        if not m or m == sf.mtime:
            return
        if not ed.dirty:
            self.run_worker(self.code_reload(keep_message=True), group="code-open")
            ed.message = tr("File vừa đổi trên đĩa — đã nạp lại")
        elif getattr(sf, "_warned", 0) != m:
            sf._warned = m
            ed.message = tr("File đổi trên đĩa — :e! nạp lại (bỏ thay đổi của bạn) hoặc :w! ghi đè")
            self._refresh_code_head()

    def _refresh_code_head(self) -> None:
        ed = self.code_editor()
        head = Text()
        status = Text()
        sf = ed.buffer
        if sf is None:
            head.append(tr("📝 Chưa mở file"), "bold")
            status.append(tr("Chọn file bên trái (gõ để lọc, Enter mở) · /code @đường/dẫn[:dòng] · "
                             "phím e ở tab Git / màn hình diff"), "dim")
        else:
            head.append("📄 " + self.code_rel(str(sf.path)), "bold")
            if ed.dirty:
                head.append(" ●", PAL.get("warn", "yellow"))
            r, c = ed.cursor_location
            sym = palette.symbol_at(self.code_symbols(), r + 1)
            if sym:
                head.append(f" › {sym['name']}", PAL["info"])
            head.append(tr("  ·  {lang}  ·  dòng {r}/{n}, cột {c}", lang=editor.language_name(sf.path), r=r + 1,
                           n=ed.document.line_count, c=c + 1), "dim")
            if sf.newline != "\n":
                head.append("  ·  CRLF", "dim")
            if sf.read_only:
                head.append("  ·  " + tr("chỉ đọc") + (f" ({sf.note})" if sf.note else ""), PAL.get("warn", "yellow"))
            if not ed.highlight_on and ed.lexer is not None:
                head.append("  ·  " + tr("tắt tô màu (file lớn)"), "dim")
            if ed.vim_on:
                mode = ed.vim.status
                style = {"insert": f"bold {PAL.get('ok', 'green')}", "visual": f"bold {PAL.get('warn', 'yellow')}",
                         "vline": f"bold {PAL.get('warn', 'yellow')}"}.get(ed.vim.mode, "bold")
                status.append(mode or "NORMAL", style)
                if ed.message and ed.vim.mode not in ("command", "search"):
                    status.append("   " + ed.message)
                elif not mode and not ed.message:
                    status.append(tr("   i sửa · :w lưu · :q đóng · / tìm · u hoàn tác · /vim off tắt phím vim"),
                                  "dim")
            else:
                status.append(ed.message or tr("Ctrl+S lưu · /vim on bật phím vim"), "dim")
        set_static(self.query_one("#code-head", Static), head)
        set_static(self.query_one("#code-status", Static), status)

    def code_symbols(self) -> list[dict]:
        """Symbol của file đang mở cho thanh "đang ở đâu" (› tên hàm): tính khi mở / lưu file, không theo từng
        phím gõ (lexer cả file); file > 300KB thì bỏ."""
        ed = self.code_editor()
        key = str(ed.buffer.path) if ed.buffer is not None else None
        cached = getattr(self, "_code_syms", (None, None))
        if cached[0] != key or cached[1] is None:
            text = ed.text
            syms = palette.symbols(ed.buffer.path, text) if key and len(text) < 300_000 else []
            self._code_syms = (key, syms)
        return self._code_syms[1]

    def on_code_editor_status_changed(self, event: CodeEditor.StatusChanged) -> None:
        self._refresh_code_head()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "code-editor":
            was = getattr(self, "_code_was_dirty", False)
            now = self.code_editor().dirty
            self._refresh_code_head()
            if now != was:
                self._code_was_dirty = now
                self.refresh_code_files()

    def on_text_area_selection_changed(self, event: TextArea.SelectionChanged) -> None:
        if event.text_area.id == "code-editor":
            self._refresh_code_head()

    def action_git_edit(self) -> None:
        sel = self.git_selected()
        if not sel or sel[1].endswith("/"):
            self.notify(tr("Chọn 1 file trong danh sách trước"))
            return
        self.open_code(sel[1])

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
                self._git_badge(st)
                try:
                    self._render_git()
                except Exception as e:  # không để lỗi vẽ làm treo app
                    self.log.error(f"render git: {e!r}")
                if not self._git_again:
                    break
        finally:
            self._git_loading = False

    def _git_badge(self, st) -> None:
        """Số file thay đổi trên nhãn tab Git ("🌿 Git 3"); sạch thì chỉ "🌿 Git"."""
        n = len(st.files) if st.is_repo else 0
        label = f"🌿 Git {n}" if n else "🌿 Git"
        try:
            tab = self.query_one("#tabs", TabbedContent).get_tab("tab-git")
        except Exception:
            return
        if str(tab.label) != label:
            tab.label = label

    def _git_rows(self, st) -> list[tuple[str | None, Text]]:
        """(id, dòng) cho danh sách file: tiêu đề nhóm có id None (không chọn được)."""
        rows: list[tuple[str | None, Text]] = []

        def file_row(f, staged: bool, indent: str, name: str, d: str) -> Text:
            icon, color = gitops.file_icon(f, staged)
            t = Text(indent)
            t.append(f"{icon} ", f"bold {color}")
            t.append(name)
            if d:
                t.append(f"  {d}", "dim")
            if f.orig:
                t.append(f"  ← {f.orig}", "dim")
            return t

        def group(title: str, files, code: str, staged: bool, style: str) -> None:
            if not files:
                return
            rows.append((None, Text(f"{title} ({len(files)})", f"bold {style}")))
            if not self.git_tree:
                for f in files:
                    d, _, name = f.path.rpartition("/")
                    rows.append((f"{code}\0{f.path}", file_row(f, staged, "  ", name, d)))
                return
            by = {f.path: f for f in files}
            closed = [d for d in (k.partition("\0")[2] for k in self._git_closed if k.startswith(code + "\0"))]
            for depth, path, label, is_dir in gitops.tree_rows(list(by)):
                if any(path != d and path.startswith(d) for d in closed):
                    continue  # nằm trong thư mục đang thu gọn
                indent = "  " + "  " * depth
                if is_dir:
                    n = sum(p.startswith(path) for p in by)
                    t = Text(indent)
                    t.append("▸ " if path in closed else "▾ ", "dim")
                    t.append(f"📁 {label}", "bold")
                    t.append(f"  {n}", "dim")
                    rows.append((f"{code}\0{path}", t))
                else:
                    rows.append((f"{code}\0{path}", file_row(by[path], staged, indent, label, "")))

        group(tr("Xung đột — sửa xong thì stage"), st.conflicts, "c", False, "red")
        group(tr("Đã stage — sẽ vào commit"), st.staged, "s", True, "green")
        group(tr("Chưa stage"), st.unstaged + st.untracked, "w", False, "yellow")
        return rows

    def commit_agent_options(self) -> list[tuple[str, str]]:
        """Ô chọn agent viết commit message: trưởng nhóm (mặc định) + các agent đang bật."""
        c = self.cfg
        return [(tr("Trưởng nhóm ({lead})", lead=c.lead), "")] + [
            (n, n) for n in c.active_agents() if n != c.lead]

    def _render_git(self) -> None:
        st = self.git_status
        if st is None:
            return
        sel = self.query_one("#git-ai-agent", Select)
        opts = self.commit_agent_options()
        if opts != getattr(self, "_git_ai_opts", None):  # /setup, /custom đổi đội → cập nhật danh sách
            self._git_ai_opts = opts
            sel.set_options(opts)
            sel.value = self.cfg.commit_agent if any(v == self.cfg.commit_agent for _l, v in opts) else ""
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
        head.append(st.branch or (f"detached @ {st.oid[:8]}" if st.oid else tr("(chưa có commit)")), "bold green")
        if st.upstream:
            head.append(f"  → {st.upstream}", "dim")
            if st.ahead:
                head.append(tr("  ↑{ahead} chưa push", ahead=st.ahead), "bold yellow")
            if st.behind:
                head.append(tr("  ↓{behind} chưa pull", behind=st.behind), "bold cyan")
            if not st.ahead and not st.behind:
                head.append(tr("  ✓ đồng bộ"), "green")
        elif st.branch:
            head.append(tr("  chưa có trên remote (Push để tạo)"), "dim")
        if st.stashes:
            head.append(f"   📦 {st.stashes} stash", "cyan")
        if st.state:
            head.append(tr("   ⚠ đang {state} dở", state=st.state), "bold red")
        self.query_one("#git-head", Static).update(head)
        self.query_one("#git-abort").display = bool(st.state)
        cont = self.query_one("#git-continue", Button)
        cont.display = bool(st.state) and not st.conflicts
        cont.label = tr("▶ Tiếp tục {state}", state=st.state)
        self.query_one("#git-cf-row").display = bool(st.conflicts)

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
            empty.update(Text(tr("✓ Không có thay đổi nào chưa commit."), "green"))
        n_staged = len(st.staged)
        amend = self.query_one("#git-amend", Checkbox).value
        skip = tr(" (bỏ qua hook)") if self.query_one("#git-no-verify", Checkbox).value else ""
        self.query_one("#git-msg", Input).placeholder = (
            tr("Message mới cho commit trước — Enter để sửa commit{skip}", skip=skip) if amend else
            tr("Commit message cho {n_staged} file đã stage — Enter để commit{skip}", n_staged=n_staged, skip=skip) if n_staged else
            tr("Commit message (chưa stage gì: commit mọi thay đổi) — Enter để commit{skip}", skip=skip))

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
            Text(tr("📜 Lịch sử ({v} commit gần nhất)", v=len(self.git_commits)), "bold") if self.git_commits
            else Text(tr("📜 Chưa có commit nào"), "bold"))

    def git_selected(self) -> tuple[str, str] | None:
        """(nhóm, đường dẫn) của file đang chọn: nhóm s = đã stage, w = chưa stage, c = xung đột. Chế độ cây:
        hàng thư mục có đường dẫn kết thúc bằng "/"."""
        ol = self.query_one("#git-files", GitFileList)
        if ol.highlighted is None or ol.highlighted >= ol.option_count:
            return None
        oid = ol.get_option_at_index(ol.highlighted).id
        if not oid:
            return None
        code, _, path = oid.partition("\0")
        return code, path

    def git_group_paths(self, code: str, path: str) -> list[str]:
        """File của nhóm `code` ứng với dòng đang chọn: chính file đó, hoặc mọi file trong thư mục (chế độ cây)."""
        st = self.git_status
        if not path.endswith("/") or st is None:
            return [path]
        files = {"c": st.conflicts, "s": st.staged}.get(code) or (st.unstaged + st.untracked)
        return [f.path for f in files if f.path.startswith(path)]

    def action_git_tree(self) -> None:
        """t / nút 📁: đổi danh sách file giữa phẳng và cây thư mục (nhớ trong state.json)."""
        self.git_tree = not self.git_tree
        st = load_state()
        st["git_tree"] = self.git_tree
        save_state(st)
        self.query_one("#git-tree", Button).label = self._git_tree_label()
        self._git_ids = []
        self._render_git()

    def _git_tree_label(self) -> str:
        return tr("≡ Danh sách") if self.git_tree else tr("📁 Thư mục")

    def git_fold(self, oid: str) -> None:
        """Thu gọn / mở thư mục ở chế độ cây."""
        self._git_closed.symmetric_difference_update({oid})
        self._render_git()

    def git_commit_selected(self):
        log = self.query_one("#git-log", GitLogList)
        if log.highlighted is None or not self.git_commits:
            return None
        return self.git_commits[min(log.highlighted, len(self.git_commits) - 1)]

    def git_do(self, make, busy_check: bool = False, then=None, label: str = "") -> None:
        """Chạy một thao tác git (make() trả coroutine → (ok, lời nhắn)), báo kết quả, vẽ lại tab Git.
        busy_check: thao tác đổi nhánh/HEAD — từ chối khi agent đang chạy (chúng đang sửa hoặc sắp merge
        vào nhánh hiện tại). label: thao tác có thể lâu (commit, push…) — hiện "đang chạy" tới khi xong."""
        if busy_check and self.orch.runs:
            self.notify(tr("Đang có {v} task chạy — đợi xong (hoặc Ctrl+K huỷ) rồi hẵng đổi "
                           "nhánh/pull/stash", v=len(self.orch.runs)), severity="warning", timeout=6)
            return

        async def go() -> None:
            with self.busy(label) if label else contextlib.nullcontext():
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
        paths = self.git_group_paths(code, path)
        self.git_do(lambda: self.git.unstage(paths) if code == "s" else self.git.stage(paths))

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
            self.notify(tr("Chỉ bỏ được thay đổi chưa stage — bỏ stage file trước (Space)"), severity="warning")
            return
        paths = self.git_group_paths(code, path)
        if path.endswith("/"):
            what = tr("bỏ mọi thay đổi chưa stage (file chưa theo dõi bị XOÁ) của {n} file trong", n=len(paths))
        else:
            f = next((f for f in self.git_status.files if f.path == path), None) if self.git_status else None
            what = tr("XOÁ file chưa theo dõi") if f and f.untracked else tr("bỏ mọi thay đổi chưa stage của")

        def done(yes) -> None:
            if yes:
                self.git_do(lambda: self.git.discard(paths))
        self.push_screen(ConfirmScreen(tr("↺ Bỏ thay đổi"), tr("{v} {path}?\nKhông thể hoàn tác.", v=what.capitalize(), path=path), tr("Bỏ thay đổi")), done)

    def action_git_discard_all(self) -> None:
        """↺ Bỏ tất cả: đã stage, chưa stage, file mới — thư mục về đúng commit cuối (GitRepo.discard_all)."""
        st = self.git_status
        if not st or not st.files:
            self.notify(tr("Không có thay đổi nào để bỏ"))
            return
        u = len([f for f in st.files if f.untracked])

        def done(yes) -> None:
            if yes:  # reset --hard + clean: agent đang chạy task (chế độ shared) sẽ mất phần đang sửa
                self.git_do(self.git.discard_all, busy_check=True)
        self.push_screen(ConfirmScreen(
            tr("↺ Bỏ tất cả thay đổi"),
            tr("Bỏ MỌI thay đổi ({s} file đã stage, {w} file chưa stage) và XOÁ {u} file chưa theo dõi? Thư mục "
               "về đúng commit cuối — không thể hoàn tác.", s=len(st.staged), w=len(st.unstaged), u=u),
            tr("Bỏ tất cả")), done)

    async def action_git_diff(self) -> None:
        sel = self.git_selected()
        if not sel:
            self.notify(tr("Chọn 1 file trong danh sách trước"))
            return
        code, path = sel
        path = self.git_group_paths(code, path)[0] if path.endswith("/") else path  # thư mục: file đầu tiên
        if code == "c":
            ds = diffview.DiffSet(0, tr("Xung đột · {path}", path=path),
                                  diffview.parse_unified(await self.git.diff_text("HEAD", "--", path)), "HEAD", None)
        else:
            ds = await self.git.changes_diffset(staged=code == "s")
        if not ds.files:
            self.notify(tr("Không có diff để xem"), severity="warning")
            return
        idx = next((i for i, f in enumerate(ds.files) if f.path == path), 0)
        self.push_screen(DiffScreen(ds, has_code=bool(shutil.which("code")), start=idx))

    async def action_git_show_commit(self) -> None:
        c = self.git_commit_selected()
        if not c:
            return
        ds = await self.git.commit_diffset(c)
        if not ds.files:
            self.notify(tr("Commit {short} không đổi file nào (vd commit merge)", short=c.short))
            return
        self.push_screen(DiffScreen(ds, has_code=bool(shutil.which("code"))))

    def action_git_revert(self) -> None:
        c = self.git_commit_selected()
        if not c:
            return

        def done(yes) -> None:
            if yes:
                self.git_do(lambda: self.git.revert(c.sha), busy_check=True)
        self.push_screen(ConfirmScreen("↶ Revert", tr("Tạo commit mới đảo ngược {short} · {subject}?", short=c.short, subject=c.subject),
                                       "Revert"), done)

    def action_git_resolve(self) -> None:
        """Mở màn hình giải quyết xung đột cho file đang chọn (không chọn file xung đột: file xung đột đầu tiên)."""
        st = self.git_status
        sel = self.git_selected()
        path = self.git_group_paths(*sel)[0] if sel and sel[0] == "c" else (st.conflicts[0].path if st and st.conflicts else "")
        if not path:
            self.notify(tr("Không có file nào đang xung đột"))
            return

        def done(res) -> None:
            if res == "edit":
                self.open_code(path)
            elif res == "ai":
                self.action_git_ai_resolve([path])
            self.run_worker(self.refresh_git(), exclusive=False)
        self.push_screen(ConflictScreen(self.git, path), done)

    def action_git_ai_resolve(self, paths: list[str] | None = None) -> None:
        async def go() -> None:
            with self.busy(tr("🤖 AI đang giải xung đột…")):
                ok, msg = await self.orch.resolve_conflicts(paths)
            self.notify(msg, severity="information" if ok else "warning", timeout=8)
        self.run_worker(go(), exclusive=False)

    def action_git_focus_msg(self) -> None:
        self.query_one("#git-msg", Input).focus()

    def git_commit(self, message: str | None = None, no_verify: bool | None = None) -> None:
        box = self.query_one("#git-msg", Input)
        msg = (box.value if message is None else message).strip()
        amend = self.query_one("#git-amend", Checkbox).value
        skip = self.query_one("#git-no-verify", Checkbox).value if no_verify is None else no_verify
        if not msg and not amend:
            self.notify(tr("Gõ commit message trước (hoặc bấm ✨ để trưởng nhóm viết)"), severity="warning")
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
                    then=clear, label=tr("⏳ Đang commit… (hook có thể chạy lâu)"))

    async def git_ai_message(self) -> None:
        btn = self.query_one("#git-ai", Button)
        if btn.disabled:
            return
        btn.disabled = True
        label = btn.label
        btn.label = tr("⏳ Đang viết…")
        try:
            with self.busy(tr("✨ {lead} đang viết commit message…", lead=self.orch.commit_agent())):
                ok, msg = await self.orch.commit_message()
        finally:
            btn.disabled = False
            btn.label = label
        if not ok:
            self.notify(msg, severity="warning", timeout=8)
            return
        box = self.query_one("#git-msg", Input)
        # ô nhập một dòng: dòng tiêu đề + phần thân nối bằng " | " sẽ khó đọc → giữ tiêu đề, thân lưu riêng
        subject, _, body = msg.partition("\n")
        self._git_body = body.strip()
        box.value = subject.strip()
        box.focus()
        self.notify(tr("✨ Đã điền commit message — sửa nếu cần rồi Enter để commit")
                    + (tr(" (kèm phần mô tả trưởng nhóm viết)") if self._git_body else ""))

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
            self.git_do(lambda: self.git.checkout(name), busy_check=True, label=tr("⏳ Đang chuyển nhánh…"))
        elif action == "create":
            self.git_do(lambda: self.git.create_branch(name), busy_check=True)
        elif action == "merge":
            self.git_do(lambda: self.git.merge(name), busy_check=True, label=tr("⏳ Đang merge…"))
        elif action == "rename":
            self.git_do(lambda: self.git.rename_branch(name, new))
        elif action == "delete":
            self.git_do(lambda: self.git.delete_branch(name))
        elif action == "force-delete":
            def done(yes) -> None:
                if yes:
                    self.git_do(lambda: self.git.delete_branch(name, force=True))
            self.push_screen(ConfirmScreen(tr("✗ Xoá hẳn nhánh"), tr("Xoá nhánh {name} kể cả "
                                                                       "commit chưa merge?\n"
                                                                       "Các commit đó sẽ mất.", name=name), tr("Xoá hẳn")), done)

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
            self.push_screen(ConfirmScreen(tr("✗ Xoá stash"), tr("Xoá {ref}? Thay đổi trong đó sẽ mất.", ref=ref), tr("Xoá")), done)

    def git_button(self, bid: str) -> None:
        g = self.git
        if bid == "git-refresh":
            self.run_worker(self.refresh_git(), exclusive=False)
        elif bid == "git-fetch":
            self.git_do(g.fetch, label=tr("⇣ Đang fetch…"))
        elif bid == "git-pull":
            self.git_do(g.pull, busy_check=True, label=tr("⬇ Đang pull…"))
        elif bid == "git-push":
            self.git_do(g.push, label=tr("⬆ Đang push…"))
        elif bid == "git-branches":
            self.git_branches()
        elif bid == "git-stash":
            self.git_stash()
        elif bid == "git-abort":
            self.git_do(g.abort)
        elif bid == "git-continue":
            self.git_do(g.continue_op, busy_check=True, label=tr("⏳ Đang tiếp tục…"))
        elif bid == "git-resolve":
            self.action_git_resolve()
        elif bid == "git-ai-resolve":
            self.action_git_ai_resolve()
        elif bid == "git-init":
            self.git_do(g.init)
        elif bid == "git-stage":
            self.action_git_toggle()
        elif bid == "git-stage-all":
            self.action_git_stage_all()
        elif bid == "git-discard":
            self.action_git_discard()
        elif bid == "git-discard-all":
            self.action_git_discard_all()
        elif bid == "git-tree":
            self.action_git_tree()

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
            self.push_screen(ConfirmScreen(tr("⎌ Bỏ commit cuối"), tr("Bỏ commit cuối cùng, giữ "
                                                                        "nguyên thay đổi của nó (ở "
                                                                        "trạng thái đã stage) để "
                                                                        "sửa rồi commit lại?"), tr("Bỏ commit")), done)

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
                self.notify(tr("Dùng: /commit [--no-verify] <message>"), severity="warning")
                return
            self.git_commit(msg, no_verify=True if skip else None)
        elif cmd == "push":
            self.git_do(lambda: g.push(force=rest in ("-f", "--force", "force")), label=tr("⬆ Đang push…"))
        elif cmd == "pull":
            self.git_do(g.pull, busy_check=True, label=tr("⬇ Đang pull…"))
        elif cmd == "fetch":
            self.git_do(g.fetch, label=tr("⇣ Đang fetch…"))
        elif cmd == "branch":
            if rest:
                self.git_do(lambda: g.create_branch(rest), busy_check=True)
            else:
                self.git_branches()
        elif cmd == "checkout":
            self.git_do(lambda: g.checkout(rest), busy_check=True, label=tr("⏳ Đang chuyển nhánh…"))
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
        tabs = self.screen_stack[0].query("#tabs") if self.screen_stack else None
        if not tabs:  # app đang đóng (đổi theme lúc thoát vẫn gọi lại refresh)
            return
        self._snap = {"tasks": self.db.tasks(), "goals": self.db.goals()}
        self.show_notices(self.notices.diff(self._snap["tasks"], self._snap["goals"]))
        tab = tabs.first(TabbedContent).active
        fns = [self._refresh_goals, self._refresh_plan, self._refresh_grill]
        if tab == "tab-board":
            fns += [self._refresh_agents, self._refresh_table, self._refresh_detail]
        elif tab == "tab-team":
            fns += [self._refresh_panes, self._refresh_timeline]
        elif tab == "tab-term":
            fns += [self._refresh_jobs]
        elif tab == "tab-code":
            fns += [self._check_code_disk]
        elif tab == "tab-dash":
            fns += [self._refresh_dash]
        elif tab == "tab-todo":
            fns += [self.query_one("#todo-tab").reload]  # web sửa cùng file: đọc lại theo mtime
        elif tab == "tab-notes":
            fns += [self.query_one("#notes-tab").reload]
        if tab == "tab-git" and time.time() - self._git_at > 3 and not self._git_loading:
            # thay đổi do agent/editor bên ngoài: đọc lại git status định kỳ khi đang xem tab
            self.run_worker(self.refresh_git(), exclusive=False)
        elif tab != "tab-git" and time.time() - self._git_at > 10 and not self._git_loading:
            # thanh trạng thái hiện nhánh git: ngoài tab Git đọc lại thưa hơn
            self.run_worker(self.refresh_git(), exclusive=False)
        fns.append(self._refresh_statusbar)
        try:
            for fn in fns:
                try:
                    fn()
                except Exception as e:  # không để lỗi vẽ làm treo app
                    self.log.error(f"refresh {fn.__name__}: {e!r}")
        finally:
            self._snap = None

    def show_notices(self, notes: list, force: bool = False) -> None:
        """Toast + chuông, và thông báo hệ điều hành khi chế độ là 'all' (/notify)."""
        m = notify.mode() if notes else "off"
        if force and notes and m == "off":  # /notify test lúc đang tắt: vẫn cho thấy trong app
            m = "app"
        if m == "off":
            return
        for n in notes[:4]:
            self.notify(n.body, title=n.title, severity="warning" if n.level == "warn" else "information",
                        timeout=10)
        self.bell()
        if m == "all":
            for n in notes[:3]:
                self.run_worker(notify.desktop(n.title, n.body), exclusive=False)

    # ------------------------------------------------------------------ tab 📊 Thống kê
    def _refresh_dash(self, force: bool = False) -> None:
        """Số liệu dùng chung với web (reports.dashboard / goal_history); vẽ lại tối đa 2 giây một lần."""
        if not force and time.time() - getattr(self, "_dash_at", 0) < 2:
            return
        self._dash_at = time.time()
        # không đổi gì (cùng phút — "hôm nay"/"x phút trước" vẫn đúng) thì không dựng lại hai bảng
        sig = (self.db.change_sig(), int(time.time() // 60))
        if not force and sig == getattr(self, "_dash_sig", None):
            return
        self._dash_sig = sig
        d = reports.dashboard(self.db)
        self._dash_hist = reports.goal_history(self.db)
        t = Text()
        for label, b in ((tr("Hôm nay"), d["today"]), (tr("7 ngày"), d["week"]), (tr("30 ngày"), d["month"])):
            t.append(f" {label:<9}", "bold")
            t.append(f" {reports.fmt_tokens(b['tokens']):>7} token", "bold cyan")
            t.append(f"  (in {reports.fmt_tokens(b['in_tok'])} · out {reports.fmt_tokens(b['out_tok'])} · "
                     f"cache {reports.fmt_tokens(b['cache'])})", "dim")
            t.append(f"   {reports.fmt_cost(b['cost']):>8}", "bold green")
            t.append(tr("   {n} lượt · {v}", n=b["runs"], v=reports.fmt_dur(b["secs"])))
            if b["failed"] or b["ratelimits"]:
                t.append(tr("  · {f} lỗi · {r} hết hạn mức", f=b["failed"], r=b["ratelimits"]), "yellow")
            t.append("\n")
        set_static(self.query_one("#dash-cards", Static), t)
        days = d["per_day"]
        top = max((x["tokens"] for x in days), default=0)
        bars = " ▁▂▃▄▅▆▇█"
        c = Text(tr(" Token 14 ngày (cao nhất {v}/ngày)\n ", v=reports.fmt_tokens(top)), "dim")
        for x in days:
            lvl = 0 if not x["tokens"] else max(1, round(x["tokens"] / top * 8)) if top else 0
            c.append(bars[lvl] * 3 + " ", "cyan")
        c.append("\n ")
        for x in days:
            c.append(x["day"][8:] + "  ", "dim")
        set_static(self.query_one("#dash-chart", Static), c)

        table = self.query_one("#dash-agents", DataTable)
        if not table.columns:
            for col in ("Agent / model", tr("Lượt"), tr("Thời gian"), "Token", "Cost", tr("Lỗi"), tr("Số thật")):
                table.add_column(col)
        table.clear()
        for kind, data in (("agent", d["by_agent"]), ("model", d["by_model"])):
            for name, b in sorted(data.items(), key=lambda kv: -kv[1]["tokens"]):
                label = tr("(mặc định của agent)") if name == "—" else name
                table.add_row(("👤 " if kind == "agent" else "🧠 ") + label, str(b["runs"]), reports.fmt_dur(b["secs"]),
                              reports.fmt_tokens(b["tokens"]), reports.fmt_cost(b["cost"]), str(b["failed"]),
                              f"{b['real']}/{b['runs']}")
        gt = self.query_one("#dash-goals", DataTable)
        cur = gt.cursor_row
        if not gt.columns:
            for col in ("#", tr("Mục tiêu"), tr("Trạng thái"), "Task", "Agent", tr("Bắt đầu"), "Token", "Cost"):
                gt.add_column(col)
        gt.clear()
        for g in self._dash_hist:
            label, style = GOAL_STATUS.get(g["status"], (g["status"], ""))
            gt.add_row(str(g["id"]), " ".join(g["text"].split())[:60], Text(label, style),
                       f"{g['done']}/{g['tasks']}" + (f" ✗{g['failed']}" if g["failed"] else ""),
                       ", ".join(g["agents"]), time.strftime("%d/%m %H:%M", time.localtime(g["created"] or 0)),
                       reports.fmt_tokens(g["tokens"]), reports.fmt_cost(g["cost"]), key=f"g{g['id']}")
        if self._dash_hist:
            gt.move_cursor(row=min(cur, len(self._dash_hist) - 1))
        self.query_one("#dash-goals").display = bool(self._dash_hist)
        set_static(self.query_one("#dash-note", Static), Text(d["note"], "dim"))
        self._show_dash_goal()

    def dash_goal(self) -> dict | None:
        hist = getattr(self, "_dash_hist", None) or []
        row = self.query_one("#dash-goals", DataTable).cursor_row
        return hist[row] if 0 <= row < len(hist) else None

    def _show_dash_goal(self) -> None:
        g = self.dash_goal()
        box = self.query_one("#dash-goal", Static)
        if not g:
            set_static(box, Text(tr("Chưa có mục tiêu nào. Gõ mục tiêu ở ô dưới để bắt đầu."), "dim"))
            return
        t = Text()
        t.append(tr("Mục tiêu #{gid}", gid=g["id"]), "bold")
        t.append(f" · {GOAL_STATUS.get(g['status'], (g['status'],))[0]}"
                 + (f" · workflow {g['workflow']}" if g["workflow"] else ""), "dim")
        t.append("\n" + g["text"].strip()[:600] + "\n")
        if g["summary"]:
            t.append(tr("Kết quả: "), "bold")
            t.append(g["summary"].strip()[:800] + "\n")
        t.append(tr("{n} lượt chạy · {v} · {tok} token ({real}/{n} số thật) · {cost}", n=g["runs"],
                    v=reports.fmt_dur(g["secs"]), tok=reports.fmt_tokens(g["tokens"]), real=g["real"],
                    cost=reports.fmt_cost(g["cost"])), "dim")
        set_static(box, t)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "tasks":
            key = str(event.row_key.value or "")
            if key.startswith("g:"):  # Enter / bấm tiêu đề nhóm: thu / mở
                self._toggle_group(key)
            return
        if event.data_table.id != "dash-goals":
            return
        g = self.dash_goal()
        if g:  # Enter: điền /continue m<id> như F6
            box = self.query_one("#cmd", Input)
            box.value = f"/continue m{g['id']} "
            box.cursor_position = len(box.value)
            box.focus()

    def _refresh_statusbar(self) -> None:
        bar = self.query_one("#statusbar", StatusBar)
        set_static(bar, bar.build(self))

    @contextlib.contextmanager
    def busy(self, label: str):
        """Đánh dấu một thao tác đang chạy (thanh trạng thái hiện spinner + nhãn) tới khi khối with kết thúc."""
        self._busy_seq += 1
        key = self._busy_seq
        self.busy_ops[key] = label
        self._busy_redraw()
        try:
            yield
        finally:
            self.busy_ops.pop(key, None)
            self._busy_redraw()

    def _busy_redraw(self) -> None:
        bars = self.screen_stack[0].query("#statusbar") if self.screen_stack else []
        for bar in bars:  # popup đang mở: vẫn vẽ thanh ở màn hình chính
            set_static(bar, bar.build(self))

    # ------------------------------------------------------------------ theme / ngôn ngữ
    def theme_choice(self) -> tuple:
        """(theme gốc, màu nhấn) đang dùng."""
        base, _, accent = (self.theme or theme.DEFAULT_THEME).partition("+")
        return base, accent

    def apply_theme(self, base: str, accent: str = "", save: bool = False) -> bool:
        """Đổi theme (+ màu nhấn): CSS theo theme Textual, chữ Rich theo bảng màu ngữ nghĩa, diff theo nền
        sáng/tối. save=True ghi vào state.json. False nếu tên theme không có."""
        if base not in self.available_themes:
            return False
        accent = accent if accent in theme.ACCENTS else ""
        name = theme.theme_id(base, accent)
        if name not in self._grayed:  # theme tối: nền xám thay nền ngả xanh (đăng ký đè, giữ tên)
            t = theme.make_theme(base, accent) or self.available_themes.get(name)
            if t is None:
                return False
            self.register_theme(theme.grayed(t))
            self._grayed.add(name)
            if self.theme == name:  # đăng ký đè theme đang dùng: gán lại không kích hoạt watcher
                self._watch_theme(name)
        self.theme = name
        cur = self.current_theme
        apply_palette(theme.palette(cur))
        diffview.set_light(not cur.dark)
        for ed in self.query(CodeEditor):
            ed.theme = "vscode_dark" if cur.dark else "github_light"
        self._git_ids, self._git_log_ids = [], []  # vẽ lại danh sách git với màu mới
        if save:
            st = load_state()
            st["theme"], st["accent"] = base, accent
            save_state(st)
        if self._booted:
            self.refresh_view()
            if self.git_status is not None:
                try:
                    self._render_git()
                except Exception as e:
                    self.log.error(f"render git: {e!r}")
        return True

    def action_open_theme(self) -> None:
        self.push_screen(ThemeScreen(*self.theme_choice()))

    def action_toggle_lang(self) -> None:
        self.run_command("/lang " + ("vi" if get_lang() == "en" else "en"))

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
            elif event.pane.id == "tab-dash":
                self._refresh_dash(force=True)
            elif event.pane.id == "tab-custom":
                self.run_worker(self.query_one("#custom-tab", CustomPanel).refill(), exclusive=False)
            elif event.pane.id == "tab-team":
                self.run_worker(self.query_one("#agents-custom", CustomPanel).refill(), exclusive=False)
            elif event.pane.id == "tab-code":
                self.code_tab_shown()
            elif event.pane.id == "tab-term":
                self.load_scripts()
            elif event.pane.id == "tab-grid":
                self.grid_tab_shown()
            elif event.pane.id == "tab-todo":
                panel = self.query_one("#todo-tab")
                panel.reload()
                panel.query_one("#todo-list" if panel.items() else "#todo-input").focus()
            elif event.pane.id == "tab-notes":
                self.query_one("#notes-tab").shown()

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
            chunks.append(Text(tr("  ⏸ TẠM DỪNG (/resume)"), "bold yellow"))
        jobs = self.shell.running()
        if jobs:
            ports = sorted({p for j in jobs for p in j.ports})
            chunks.append(Text(tr("  💻 {v} lệnh đang chạy", v=len(jobs)) + (
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
                self.notify(tr("🏁 Mục tiêu #{id} {v} — F6 hoặc bấm ↪ Tiếp tục để giao thêm việc", id=g.id, v=GOAL_STATUS.get(g.status, (g.status,))[0]), timeout=6)
        t = Text()
        if not goals:
            t.append(tr("Chưa có mục tiêu. Gõ yêu cầu ở ô dưới cùng."), "dim")
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
            t.append(tr(" · vòng {round}]", round=g.round) if g.round > 1 else "]", style)
            t.append(f" {g.text.splitlines()[0][:80] if g.text else ''}")
            if g.followups:
                t.append(tr("\n   ↪ lần tiếp {v}: {v2}", v=len(g.followups), v2=g.followups[-1].splitlines()[0][:120]),
                         "cyan")
            ended = g.status in GOAL_ENDED
            if ended:  # nút bấm đầu dòng riêng: không bị gãy dòng như khi nằm cuối tiêu đề dài
                t.append("\n   ")
                t.append(tr(" ↪ Tiếp tục "), Style(color="black", bgcolor="cyan", bold=True,
                                              meta={"@click": f"app.continue_goal({g.id})"}))
            if g.summary and g.status in ("done", "incomplete", "failed", "awaiting"):
                t.append(f" {g.summary[:160]}" if ended else f"\n   ↳ {g.summary[:160]}", "dim")
            if g.status == "planning":
                t.append("\n   ")
                t.append(tr(" ✕ Huỷ lập kế hoạch "), Style(color="black", bgcolor="red", bold=True,
                                                         meta={"@click": f"app.cancel_planning({g.id})"}))
            if g.status == "awaiting":
                t.append(tr("\n   ↳ xem khung Duyệt kế hoạch phía dưới · F2 duyệt & chạy"), "yellow")
            if g.status == "grilling":
                t.append(tr("\n   ↳ trả lời câu hỏi ở khung Hỏi đáp phía dưới"), "yellow")
            elif g.spec and g.status not in GOAL_ENDED:
                t.append(tr("\n   📝 đã chốt yêu cầu sau {v} câu hỏi", v=len((g.grill or {}).get('qa') or [])), "dim")
        if self.query_one("#tabs", TabbedContent).active == "tab-board":
            set_static(self.query_one("#goals", Static), t)

    def _refresh_table(self) -> None:
        table = self.query_one("#tasks", DataTable)
        now = time.time()
        tasks = [t for t in self.snap_tasks() if t.source != CHAT]  # lượt chat hiện ở ô agent (tab Agents)
        empty = self.query_one("#tasks-empty", Static)
        table.display, empty.display = bool(tasks), not tasks
        alive = {t.id for t in tasks}
        for tid in [i for i in self._rows if i not in alive and not self.task_groups]:  # đã dọn (/clear, nút Dọn)
            table.remove_row(str(tid))
            del self._rows[tid]
        tids, gids = self.orch.finished_ids(tasks, self.snap_goals())
        tools = self.query_one("#board-tools")
        tools.display = bool(tids or gids)
        if tids or gids:
            self.query_one("#board-clear", Button).label = tr("🗑 Dọn {v} task đã xong", v=len(tids))
        if not tasks:
            t = Text()
            t.append(tr("Chưa có task nào.\n\n"), "bold")
            first = (tr("chạy theo workflow '{default_workflow}' (/goal: trưởng nhóm)", default_workflow=self.cfg.default_workflow)
                     if self.cfg.default_workflow else tr("trưởng nhóm lập kế hoạch & chia việc"))
            for keys, what in ((tr("Gõ một mục tiêu"), first),
                               (tr("/grill <mục tiêu>"), tr("trưởng nhóm hỏi kỹ cho rõ rồi mới lập kế hoạch")),
                               (tr("/task <agent> <nội dung>"), tr("giao tay cho 1 agent")),
                               (tr("/flow <tên> <mục tiêu>"), tr("chạy theo workflow dựng sẵn")),
                               ("F1", tr("xem mọi lệnh & phím tắt"))):
                t.append(f"  {keys:27}", "bold cyan")
                t.append(what + "\n")
            set_static(empty, t)
        if self.task_groups:
            self._refresh_grouped(table, tasks, now)
            return
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
                table.add_row(Text(row[0]), Text(row[1]), Text(row[2], style), Text(row[3], "dim", justify="right"),
                              Text(row[4]), key=key)
                self._rows[task.id] = row
            elif self._rows[task.id] != row:
                table.update_cell(key, "agent", Text(row[1]))
                table.update_cell(key, "status", Text(row[2], style))
                table.update_cell(key, "time", Text(row[3], "dim", justify="right"))
                table.update_cell(key, "title", Text(row[4]))
                self._rows[task.id] = row

    def _group_folded(self, key: str, ended: bool) -> bool:
        return self._folded.get(key, ended)

    def _task_cells(self, task, now: float, tree: str) -> tuple:
        label, style = STATUS.get(task.status, (task.status, ""))
        icon = SPIN[self._frame] if task.status == "running" else STATUS_ICON.get(task.status, "·")
        deps = f" ⟵{','.join(map(str, task.depends_on))}" if task.depends_on else ""
        dur = fmt_dur((task.finished or now) - task.started) if task.started else ""
        title = Text(tree, "dim")
        title.append(("↳ " if task.parent_id else "") + task.title, "dim" if task.status in ("done", "cancelled") else "")
        title.append(deps, "dim")
        if task.error and task.status in ("failed", "blocked", "conflict"):
            title.append("  " + task.error.splitlines()[0][:80], PAL.get("err", "red"))
        agent = task.agent + (f"@{task.effort}" if task.effort else "")
        return (Text(str(task.id)), Text(agent), Text(f"{icon} {label}", style),
                Text(dur, "dim", justify="right"), title)

    def _group_counts(self, ts: list, t: Text) -> None:
        for st in ("running", "review", "queued", "failed", "done"):
            n = sum(1 for x in ts if x.status == st)
            if n:
                label, style = STATUS.get(st, (st, ""))
                t.append(f"  {STATUS_ICON.get(st, '•')}{n}", style)

    def _refresh_grouped(self, table: DataTable, tasks: list, now: float) -> None:
        """Bảng task nhóm theo kế hoạch: 📌 Ngoài kế hoạch (task giao tay, không thuộc mục tiêu nào) luôn ở trên cùng,
        rồi từng kế hoạch mới nhất trước; kế hoạch đã kết thúc mặc định thu gọn. Thứ tự dòng không đổi thì chỉ sửa ô
        đổi (như bảng phẳng), đổi thì dựng lại và giữ con trỏ theo khoá dòng."""
        tasks = [t for t in tasks if t.status != "draft"]  # task nháp ở khung Duyệt kế hoạch
        if not tasks:  # bảng trống: hiện hướng dẫn (#tasks-empty), không để lại dòng tiêu đề
            if self._gorder:
                table.clear()
            self._gorder, self._gsig = [], {}
            return
        goals = {g.id: g for g in self.snap_goals()}
        adhoc = [t for t in tasks if t.goal_id is None]
        by: dict[int, list] = {}
        for t in tasks:
            if t.goal_id is not None:
                by.setdefault(t.goal_id, []).append(t)
        gids = set(by) | {g.id for g in goals.values() if g.status not in GOAL_ENDED}
        rows: list[tuple[str, tuple]] = []
        blank = (Text(""), Text(""), Text(""))

        def body(ts: list) -> None:
            for i, x in enumerate(ts):
                rows.append((str(x.id), self._task_cells(x, now, "  └ " if i == len(ts) - 1 else "  ├ ")))

        fold = self._group_folded("g:adhoc", False)
        h = Text(tr("📌 Ngoài kế hoạch"), f"bold {PAL.get('warn', 'yellow')}")
        h.append(f"  {len(adhoc)}", "dim")
        if fold:
            self._group_counts(adhoc, h)
        h.append(tr("  · n: giao task cho agent"), "dim")
        rows.append(("g:adhoc", (Text("▸" if fold else "▾", "bold"),) + blank + (h,)))
        if not fold:
            body(adhoc)
        for gid in sorted(gids, reverse=True):
            g, ts = goals.get(gid), by.get(gid, [])
            ended = g is None or g.status in GOAL_ENDED
            key = f"g:{gid}"
            fold = self._group_folded(key, ended)
            h = Text(f"🎯 #{gid} ", "bold")
            if g:
                busy = g.status in ("planning", "reviewing") or gid in self.orch.lead_busy
                label, style = GOAL_STATUS.get(g.status, (g.status, ""))
                if busy:
                    h.append(f"{SPIN[self._frame]} ", f"bold {RUNNING}")
                h.append(f"[{label}] ", style)
            if ts:  # tiến độ trước tiêu đề: cột Task hẹp thì phần bị cắt là tiêu đề, không phải số liệu
                n, d = len(ts), sum(1 for x in ts if x.status == "done")
                r = sum(1 for x in ts if x.status in ("running", "review"))
                w = 6
                dw, rw = round(d / n * w), round(r / n * w)
                h.append("━" * dw, PAL.get("ok", "green"))
                h.append("━" * rw, RUNNING)
                h.append("─" * max(0, w - dw - rw), "dim")
                h.append(f" {d}/{n} ", "dim")
            if fold:
                self._group_counts(ts, h)
                if ended and g:
                    h.append(tr("  · c: tiếp tục"), "dim")
                h.append("  ")
            if g:
                if g.workflow:
                    h.append(f"⚙{g.workflow} ", "cyan")
                h.append(g.text.splitlines()[0][:80] if g.text else "", "bold")
            rows.append((key, (Text("▸" if fold else "▾", "bold"),) + blank + (h,)))
            if not fold:
                body(ts)
        order = [k for k, _ in rows]
        sig = {k: tuple((c.plain, str(c.style), tuple((s.start, s.end, str(s.style)) for s in c.spans)) for c in cells)
               for k, cells in rows}
        if order != self._gorder:
            cur = self._cursor_key(table)
            table.clear()
            for k, cells in rows:
                table.add_row(*cells, key=k)
            self._gorder = order
            if cur in order:
                table.move_cursor(row=order.index(cur))
        else:
            for k, cells in rows:
                if self._gsig.get(k) != sig[k]:
                    for col, cell in zip(("id", "agent", "status", "time", "title"), cells):
                        table.update_cell(k, col, cell)
        self._gsig = sig

    @staticmethod
    def _cursor_key(table: DataTable) -> str | None:
        if not table.row_count:
            return None
        try:
            return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        except Exception:  # noqa: BLE001 — con trỏ ngoài bảng sau khi xoá dòng
            return None

    def action_toggle_task_groups(self) -> None:
        """g (bảng task đang chọn): đổi giữa nhóm theo kế hoạch và bảng phẳng theo id (nhớ trong state.json)."""
        self.task_groups = not self.task_groups
        st = load_state()
        st["task_groups"] = self.task_groups
        save_state(st)
        self.query_one("#tasks", DataTable).clear()
        self._rows, self._gorder, self._gsig = {}, [], {}
        self._refresh_table()
        self.notify(tr("Bảng task: nhóm theo kế hoạch") if self.task_groups else tr("Bảng task: bảng phẳng theo id"))

    def action_task_group(self, delta: int) -> None:
        """[ / ]: nhảy tới tiêu đề nhóm trước / sau."""
        table = self.query_one("#tasks", DataTable)
        if not self.task_groups or not self._gorder:
            return
        heads = [i for i, k in enumerate(self._gorder) if k.startswith("g:")]
        row = table.cursor_row
        nxt = [i for i in heads if i > row] if delta > 0 else [i for i in heads if i < row]
        if nxt:
            table.move_cursor(row=nxt[0] if delta > 0 else nxt[-1])

    def action_adhoc_task(self) -> None:
        """n: điền sẵn /task để giao việc cho một agent, ngoài mọi kế hoạch."""
        box = self.query_one("#cmd", Input)
        box.value = "/task "
        box.cursor_position = len(box.value)
        box.focus()

    def action_continue_group(self) -> None:
        """c trên bảng task: tiếp tục kế hoạch của dòng đang chọn (tiêu đề nhóm hoặc task trong nhóm)."""
        key = self._cursor_key(self.query_one("#tasks", DataTable)) or ""
        if key.startswith("g:") and key[2:].isdigit():
            self.prefill_continue(f"m{key[2:]}")
        elif not key.startswith("g:"):
            self.action_continue()

    def _toggle_group(self, key: str) -> None:
        goal = self.db.goal(int(key[2:])) if key[2:].isdigit() else None
        ended = key != "g:adhoc" and (goal is None or goal.status in GOAL_ENDED)
        self._folded[key] = not self._group_folded(key, ended)
        self._refresh_table()

    def _refresh_detail(self) -> None:
        d = self.query_one("#detail", Static)
        if self.view_task == SYSTEM:
            t = Text(tr("📜 Log hệ thống"), "bold")
            t.append(tr("  ·  chọn 1 task trong bảng để xem log riêng · Ctrl+T: tab Agents"), "dim")
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
            t.append(tr("  (được {v} giao)", v=task.source.split(':', 1)[1]), "dim")
        t.append("\n" + task.prompt[:300].replace("\n", " "), "dim")
        if task.attempts:
            t.append(tr("  · đã sửa lỗi test {attempts} lần", attempts=task.attempts), "yellow")
        if task.status == "review":
            t.append(tr("\n👀 Chờ duyệt — Ctrl+D xem diff, Ctrl+Y merge, /reject <task> [góp ý]"), "yellow")
        if task.error:
            t.append(f"\n⚠ {task.error}", "red")
        elif task.result and task.status != "running":
            t.append(f"\n↳ {task.result[:240].replace(chr(10), ' ')}", "green")
        if task.status in ("failed", "cancelled", "blocked"):
            t.append("\n")
            t.append(tr(" ⇄ Đổi agent "), Style(color="black", bgcolor="cyan", bold=True,
                                               meta={"@click": f"app.reassign_task({task.id})"}))
            t.append(tr("  F5: chạy lại với {agent}", agent=task.agent), "dim")
        if task.status not in ACTIVE:
            g = self.db.goal(task.goal_id) if task.goal_id else None
            if g is None or g.status in GOAL_ENDED:
                what = tr("mục tiêu #{id}", id=g.id) if g else tr("hỏi tiếp {agent} trong thread này", agent=task.agent)
                t.append(tr("\n↪ F6: tiếp tục {what}", what=what), "dim")
        set_static(d, t)

    def _refresh_panes(self) -> None:
        now = time.time()
        tasks = self.snap_tasks()
        # tổng hợp cả bảng runs: đọc lại tối đa 5 giây một lần (ô agent vẽ lại mỗi 0,5 giây)
        if time.time() - getattr(self, "_usage_at", 0) > 5:
            self._usage_at, self._usage = time.time(), self.db.usage(today_start())
        usage = self._usage
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
            if name in self.cfg.custom_agents:
                t.append(tr(" [tuỳ chỉnh]"), PAL["info"])
            t.append(f"  {a.label()}", PAL["info"])
            # nhãn trạng thái như web: chưa cài / nghỉ đến … / đang chạy N / rảnh
            if not a.installed():
                badge, color = tr("chưa cài"), PAL["err"]
            elif self.orch.in_cooldown(name) and not acts:
                badge, color = tr("nghỉ đến {v}", v=self.orch.cooldown_label(name)), PAL["warn"]
            elif acts:
                badge, color = tr("đang chạy {n}", n=len(acts)), PAL["running"]
            else:
                badge, color = tr("rảnh"), PAL["ok"]
            t.append("  ")
            t.append(f" {badge} ", f"bold reverse {color}")
            for what, label in (("chat", tr("💬 Chat")), ("term", "⌨ Terminal")) + (
                    (("edit", tr("✎ Sửa")), ("del", tr("✗ Xoá"))) if name in self.cfg.custom_agents else ()):
                t.append("  ")
                t.append(f"[{label}]", Style.parse("bold") + Style(meta={"@click": f"app.agent_btn({name!r}, {what!r})"}))
            role = self.role_label(name)
            if role or a.role:
                t.append(f"\n{role}" if role else "\n", "bold")
                t.append(("  · " if role and a.role else "") + (a.role[:80] if a.role else ""), "dim")
            t.append("\n")
            t.append_text(choice_line("model", a.model_choices(), a.model, PANE_MODELS, agent=name))
            t.append("\n")
            t.append_text(choice_line("effort", a.efforts_for(), a.current_effort(), agent=name))
            if not a.installed():
                t.append(tr("\n✗ chưa cài lệnh '{binary}'", binary=a.binary), "red")
            elif self.orch.in_cooldown(name) and not acts:
                t.append(tr("\n⏸ hết hạn mức — nghỉ đến {v}", v=self.orch.cooldown_label(name)), "bold yellow")
                fb = self.orch.pick_fallback(name)
                t.append(tr("  · task mới chuyển cho {fb}", fb=fb) if fb else tr("  · task của nó chờ hồi hạn mức"),
                         "yellow")
            elif acts:
                for act in acts:
                    head = f"#{act['task_id']} {act['title']}" if act["task_id"] else act["title"]
                    t.append(f"\n{SPIN[self._frame]} ", f"bold {RUNNING}")
                    t.append(head[:60], "bold")
                    t.append(f"  [{act['label']}]", "cyan")
                    t.append(f"  ⏱ {fmt_dur(now - act['started'])}", RUNNING)
                    t.append(tr("  · {v} dòng", v=act['lines']), "dim")
                    quiet = now - act["last_at"]
                    if quiet > SILENT_WARN:
                        t.append(tr("  · im lặng {v}", v=fmt_dur(quiet)), "yellow")
                    if act["last_line"]:
                        t.append(f"\n  › {act['last_line'][:90]}", "dim")
            last_done = next((x for x in reversed(mine) if x.finished), None)
            t.append(f"\n✓{n_done}", PAL["ok"])
            t.append(f" ✗{n_fail}", PAL["err"] if n_fail else "dim")
            t.append(f" ⏳{n_wait}", PAL["info"] if n_wait else "dim")
            u = usage.get(name)
            if u:
                t.append(tr("   hôm nay {v} lượt · {v2}", v=u['runs'], v2=fmt_dur(u['secs'])), "dim")  # token: /usage
            if not acts and last_done:  # rảnh: task gần nhất
                label, style = STATUS.get(last_done.status, (last_done.status, ""))
                t.append(tr("  · gần nhất #{id} ", id=last_done.id), "dim")
                t.append(label, style)
            set_static(pane.head, t)
            pane.set_class(bool(acts), "busy")
            pane.set_class(not a.installed(), "missing")
            pane.set_class(not acts and self.orch.in_cooldown(name), "cooling")
            pane.set_class(not acts and last_done is not None
                           and last_done.status in ("failed", "blocked", "conflict"), "failed")

    def _refresh_grill(self) -> None:
        bar = self.query_one("#grill", GrillBar)
        was = bar.question is not None
        new = bar.update_grill(self)
        bar.border_title = (tr("❓ Agent hỏi giữa task") if bar.task_id is not None
                            else tr("🔎 Trưởng nhóm hỏi để hiểu rõ yêu cầu"))
        waiting = bar.question is not None
        if waiting != was or new:
            self._show_input_mode()
        if new:
            box = self.query_one("#cmd", Input)
            if self.screen is self.screen_stack[0]:
                box.focus()
            if bar.task_id is None:  # câu hỏi của agent đã có thông báo riêng (notify.Watcher)
                self.notify(tr("❓ Trưởng nhóm hỏi — trả lời ở ô nhập (hoặc gõ số phương án)"), timeout=5)

    def answer_grill(self, text: str | None) -> None:
        """Trả lời câu đang hiện ở khung hỏi đáp (số 1…n = chọn phương án; None = để trưởng nhóm tự quyết)."""
        bar = self.query_one("#grill", GrillBar)
        if bar.task_id is not None:
            self.notify(self.orch.answer_task(bar.task_id, text))
        else:
            self.notify(self.orch.answer_grill(bar.goal_id, text))
        self.refresh_view()

    def action_grill_pick(self, i: int) -> None:
        self.answer_grill(str(i))

    def _refresh_plan(self) -> None:
        bar = self.query_one("#plan", PlanBar)
        if not bar.update_plan(self):
            return
        bar.border_title = tr("Duyệt kế hoạch")
        # kế hoạch mới: đưa con trỏ vào nút "Duyệt & chạy" (Enter là chạy) — trừ khi người dùng
        # đang gõ dở trong ô nhập hoặc đang mở màn hình khác
        box = self.query_one("#cmd", Input)
        if self.screen is self.screen_stack[0] and not box.value:
            self.query_one("#plan-approve", Button).focus()
        self.notify(tr("📋 Kế hoạch #{goal_id} sẵn sàng — Enter hoặc F2 để duyệt & chạy", goal_id=bar.goal_id),
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
        if bid == "cmd-mode":
            event.stop()
            self.action_pick_mode()
            return
        if bid.startswith("git-"):
            event.stop()
            self.git_button(bid)
            return
        if bid == "code-new":
            event.stop()
            self.code_command("new_file")
            return
        if bid.startswith("grill-"):
            event.stop()
            bar = self.query_one("#grill", GrillBar)
            o = self.orch
            if bid == "grill-done":
                self.notify(o.finish_grill(bar.goal_id))
            elif bid == "grill-skip":
                self.answer_grill(None)
            elif bid == "grill-retry":
                self.notify(o.retry_grill(bar.goal_id))
            elif bid == "grill-cancel":
                self.notify(o.cancel_grill(bar.goal_id))
            elif bid == "grill-askskip" and bar.task_id is not None:
                self.notify(o.answer_task(bar.task_id, None))
            elif bid == "grill-askcancel" and bar.task_id is not None:
                self.notify(o.cancel(bar.task_id))
            elif bid == "grill-askview" and bar.task_id is not None:
                self.show_task(bar.task_id)
            self.refresh_view()
            return
        if bid.startswith("job-"):
            event.stop()
            job = self.selected_job()
            if job is None:
                return
            if bid == "job-stop" and not self.shell.stop(job):
                self.notify(tr("Lệnh này đã dừng"))
            elif bid == "job-restart":
                self.show_job(self.shell.restart(job).id)
            elif bid == "job-remove" and not self.shell.remove(job):
                self.notify(tr("Đang chạy — Dừng trước rồi mới xoá"), severity="warning")
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
                self.notify(tr("Đã bỏ kế hoạch #{goal_id} ({n} task nháp)", goal_id=bar.goal_id, n=n))
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
        if event.option_list.id == "term-scripts":
            event.stop()
            if event.option.id:
                self.run_shell(event.option.id)
                self._scripts_at = 0  # lệnh vừa chạy lên đầu "gần đây"
                self.load_scripts()
            return
        if event.option_list.id == "code-files":
            event.stop()
            oid = event.option.id or ""
            if oid.startswith("d:"):  # thư mục của cây: Enter/bấm = mở / thu gọn
                self.code_fold(oid[2:])
            elif oid:
                self.open_code(oid[2:])
            return
        if event.option_list.id == "git-files":
            event.stop()
            sel = self.git_selected()
            if sel and sel[1].endswith("/"):  # chế độ cây: Enter/bấm vào thư mục = thu gọn / mở
                self.git_fold(event.option.id)
            elif sel and sel[0] == "c":
                self.action_git_resolve()
            else:
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
            self.notify(tr("Kế hoạch không còn task nào"))
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
                log.write(Text(tr("🗑 Đã xoá log cũ — chỉ hiện dòng mới"), "dim italic"))
            for line in styled_lines(text, self.log_styler)[-LOG_SHOW_LINES:]:
                log.write(line)
        elif tid != SYSTEM:
            log.write(tr("(task chưa chạy — chưa có log)"))
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
        if event.data_table.id == "dash-goals":
            self._show_dash_goal()
            return
        if event.data_table.id != "tasks":
            return
        # giữ ↑↓ để lướt bảng: chỉ nạp log của dòng dừng lại (đọc + tô màu log mỗi dòng lướt qua rất chậm)
        if event.row_key and str(event.row_key.value or "").isdigit():  # bỏ qua tiêu đề nhóm ("g:…")
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

    def open_plan(self, gid: int | None) -> None:
        """/plan [mục tiêu]: trống = mục tiêu của task đang chọn, không có thì mục tiêu mới nhất."""
        if gid is None:
            t = self.db.task(self.selected_task()) if self.selected_task() else None
            gid = t.goal_id if t and t.goal_id else next((g.id for g in reversed(self.db.goals())), None)
        g = self.db.goal(gid) if gid else None
        if not g:
            self.notify(tr("Không thấy mục tiêu #{id}", id=gid or "?"), severity="warning")
            return
        self.push_screen(PlanViewScreen(g, self.db.tasks(goal_id=g.id)))

    TAB_ORDER = ["tab-board", "tab-grid", "tab-team", "tab-custom", "tab-code", "tab-git", "tab-term", "tab-todo", "tab-notes",
                 "tab-dash"]

    def action_toggle_tab(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        order = self.TAB_ORDER
        tabs.active = order[(order.index(tabs.active) + 1) % len(order)] if tabs.active in order else order[0]
        self.refresh_view()

    def action_goto_tab(self, i: int) -> None:
        """Alt+1…9, Alt+0 (tab thứ 10): tới thẳng tab theo thứ tự trên thanh tab."""
        if 0 <= i < len(self.TAB_ORDER):
            self.query_one("#tabs", TabbedContent).active = self.TAB_ORDER[i]
            self.refresh_view()

    def action_approve(self) -> None:
        bar = self.query_one("#plan", PlanBar)
        gid = bar.goal_id if bar.display else None
        n = self.orch.approve(gid)
        if not n:
            self.notify(tr("Không có task nháp nào cần duyệt"))
            return
        self.notify(tr("▶ Đã duyệt {n} task", n=n) + (tr(" của kế hoạch #{gid}", gid=gid) if gid else ""))
        self.refresh_view()
        if not bar.display:
            self.query_one("#cmd", Input).focus()

    def action_retry(self) -> None:
        tid = self.selected_task()
        self.notify(self.orch.retry(tid) if tid else tr("Chọn 1 task trong bảng trước"))

    def action_cancel_task(self) -> None:
        tid = self.selected_task()
        self.notify(self.orch.cancel(tid) if tid else tr("Chọn 1 task trong bảng trước"))

    async def action_diff(self) -> None:
        if isinstance(self.screen, DiffScreen):  # Ctrl+D lần nữa = đóng
            self.screen.dismiss(None)
            return
        tid = self.selected_task()
        if not tid:
            self.notify(tr("Chọn 1 task trong bảng trước"))
            return
        await self.show_diff(tid)

    async def action_merge(self) -> None:
        tid = self.selected_task()
        if not tid:
            self.notify(tr("Chọn 1 task trong bảng trước"))
            return
        self.notify(await self.orch.merge(tid))
        if isinstance(self.screen, DiffScreen):  # duyệt xong từ màn hình diff
            self.screen.dismiss(None)
        self.refresh_view()

    def action_syslog(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-board"
        self.show_task(SYSTEM)

    async def action_quit(self) -> None:
        unsaved = self.code_unsaved()
        if unsaved and not self._quit_ok:
            def done(ok) -> None:
                if ok:
                    self._quit_ok = True
                    self.call_later(self.action_quit)
                else:
                    self.restart_requested = False
            self.push_screen(ConfirmScreen(tr("Còn file chưa lưu"),
                                           tr("Tab 📝 Code còn {n} file chưa lưu: {v}\nThoát và bỏ các thay đổi này?",
                                              n=len(unsaved), v=", ".join(unsaved)),
                                           yes=tr("Thoát, bỏ thay đổi")), done)
            return
        self.shell.stop_all()  # không để lại dev server mồ côi sau khi thoát
        self.grid.shutdown()  # CLI trong các ô của tab 🔲 Lưới
        for run in self.orch.all_runs():  # cả lượt trưởng nhóm (lập kế hoạch, /init…): không để CLI chạy mồ côi
            run.cancel()
        if self._loop_task:
            self._loop_task.cancel()
        self.exit()

    # ------------------------------------------------------------------ ô lệnh
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "code-filter":
            event.stop()
            self.refresh_code_files()
            return
        if isinstance(event.input, CommandInput):
            event.input.update_mention()
            self._update_continue_hint(event.value)

    # ------------------------------------------------------------------ tiếp tục mục tiêu / thread
    def continue_candidates(self) -> list[tuple[str, Text]]:
        """(ref, dòng hiển thị) cho gợi ý /continue: mục tiêu đã kết thúc rồi thread /task đã xong."""
        out: list[tuple[str, Text]] = []
        for c in reports.continue_candidates(self.db):
            t = Text()
            t.append("🎯 " if c["kind"] == "goal" else "💬 ")
            t.append(c["ref"].ljust(6), "bold cyan")
            if c["kind"] == "goal":
                label, style = GOAL_STATUS.get(c["status"], (c["status"], ""))
                t.append(f"{label:11}", style)
                t.append(c["title"])
                if c["summary"]:
                    t.append(f" — {c['summary']}", "dim")
            else:
                _label, style = STATUS.get(c["status"], (c["status"], ""))
                t.append(f"{c['agent']} ", "cyan")
                t.append(f"{STATUS_ICON.get(c['status'], '·')} ", style)
                t.append(c["title"])
            out.append((c["ref"], t))
        return out

    def continue_hint(self, ref: str) -> Text:
        """Dòng giải thích /continue <ref> sẽ làm gì (hoặc vì sao chưa được)."""
        ok, msg = reports.continue_hint(self.db, self.orch, ref)
        if not ok:
            return Text(msg if msg.startswith("⚠") else f"⚠ {msg}", "yellow")
        t = Text(msg, "bold")
        t.append(tr("  (gõ yêu cầu mới rồi Enter, Esc huỷ)"), "dim")
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
                self.notify(tr("Chưa có mục tiêu nào đã xong để tiếp tục — chọn 1 task trong bảng"),
                            severity="warning")
                return
            ref = f"m{ended[-1].id}"
        self.prefill_continue(ref)

    def action_continue_goal(self, gid: int) -> None:
        """Nút "↪ Tiếp tục" trong khung mục tiêu."""
        self.prefill_continue(f"m{gid}")

    def action_cancel_planning(self, gid: int) -> None:
        """Nút "✕ Huỷ" của mục tiêu đang lập kế hoạch."""
        self.notify(self.orch.cancel_planning(gid))
        self.refresh_view()

    def action_reassign_task(self, tid: int) -> None:
        """Nút "⇄ Đổi agent" ở chi tiết task lỗi / bị huỷ."""
        self.reassign_task(tid)

    def reassign_task(self, tid: int) -> None:
        """Bảng chọn agent cho task rồi chạy lại ngay (task lỗi / bị huỷ / bị chặn) — /assign <task>."""
        t = self.db.task(tid)
        if not t:
            self.notify(tr("Không có task #{tid}", tid=tid), severity="warning")
            return
        agents = [n for n, a in self.cfg.active_agents().items() if a.installed()]

        def done(agent: str | None) -> None:
            if agent and agent != RESET:
                self.notify(self.orch.assign(tid, agent, rerun=True))
                self.refresh_view()
        self.push_screen(ChoiceScreen(tr("Đổi agent cho task #{tid}", tid=tid), agents, t.agent,
                                      tr("Thôi (giữ {agent})", agent=t.agent)), done)

    def start_goal(self, text: str, workflow: str = "") -> None:
        """Mục tiêu mới: theo workflow (nếu có) hoặc để trưởng nhóm lập kế hoạch."""
        if workflow:
            res = self.orch.run_workflow(workflow, text)
            if isinstance(res, str):
                self.notify(res, severity="warning")
                return
        else:
            if not self.cfg.agents.get(self.cfg.lead):
                self.notify(tr("Không có trưởng nhóm '{lead}' trong cấu hình", lead=self.cfg.lead), severity="error")
                return
            self.orch.new_goal(text)
        self.show_task(SYSTEM)

    def _show_input_mode(self) -> None:
        """Ô nhập cho biết gõ mục tiêu sẽ đi đâu: workflow mặc định hay trưởng nhóm."""
        wf = self.cfg.default_workflow
        mode = self.query_one("#cmd-mode", Button)
        mode.label = Btn.wrap(wizard.mode_label(self.cfg) + " ▾")
        mode.refresh(layout=True)  # width auto: tính lại theo nhãn mới
        bar = self.query_one("#grill", GrillBar)
        if bar.question is not None:
            self.query_one("#cmd", Input).placeholder = (
                tr("Trả lời câu hỏi của agent (Enter) · gõ số để chọn phương án") if bar.task_id is not None
                else tr("Trả lời câu hỏi của trưởng nhóm (Enter) · gõ số để chọn phương án · /grill "
                        "xong để chốt"))
            return
        self.query_one("#cmd", Input).placeholder = (
            tr("Nhập mục tiêu (chạy theo workflow '{wf}') · /goal: trưởng nhóm lập kế hoạch · "
               "/help · @ nhắc file", wf=wf)
            if wf else tr("Nhập mục tiêu cho trưởng nhóm, /help, hoặc @ để nhắc file"))

    def action_pick_mode(self) -> None:
        """F4 / nút cạnh ô nhập: gõ mục tiêu → trưởng nhóm lập kế hoạch hay chạy một workflow."""
        if isinstance(self.screen, InputModeScreen):
            return

        def done(name) -> None:
            if name is None:
                return
            if name == InputModeScreen.CONFIG:
                self.open_default_flow()
                return
            self.notify(wizard.set_input_mode(self.cfg, name))
            self._show_input_mode()
            self.query_one("#cmd", Input).focus()
        self.push_screen(InputModeScreen(self.cfg), done)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "git-ai-agent" or event.value is Select.BLANK:
            return
        event.stop()
        name = str(event.value or "")
        if name != self.cfg.commit_agent:
            self.cfg.commit_agent = name
            save_commit_agent(name)

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
        if event.input.id == "code-filter":
            event.stop()
            ol = self.query_one("#code-files", CodeFileList)
            idx = ol.highlighted if ol.highlighted is not None else 0
            for i in range(idx, ol.option_count):
                oid = ol.get_option_at_index(i).id
                if oid and not oid.startswith("d:"):
                    self.open_code(oid[2:])
                    break
            return
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
            self.notify(tr("Lỗi: {e}", e=e), severity="error")

    def usage_text(self) -> str:
        return reports.usage_text(self.cfg, self.db, self.orch)

    async def _cli_usage(self) -> None:
        """Hỏi song song hạn mức của từng agent bằng chính CLI của nó, in vào log hệ thống khi xong."""
        names = reports.usage_agents(self.cfg)  # đủ claude, codex, agy, grok (kể cả agent đang tắt)
        self.write_sys(tr("\nĐang hỏi hạn mức từ CLI của {v}…", v=', '.join(names)))

        def done(name: str, cmd: str, lines: list[str]) -> None:
            note = reports.agent_note(self.cfg, name)
            self.write_sys(f"\n📊 {name}" + (f"  ({cmd})" if cmd else "") + (f"  · {note}" if note else "") + "\n"
                           + "\n".join("  " + ln for ln in lines))
        with self.busy(tr("📊 Đang hỏi hạn mức…")):
            await self.orch.usage_all(names, on_done=done)

    async def _self_update(self) -> None:
        self.notify(tr("Đang kiểm tra bản mới…"), timeout=3)
        ok, msg = await update.run_update(lambda line: self.orch.log("  " + line))
        self.orch.log(("✓ " if ok else "ℹ ") + msg)
        self.notify(msg, severity="information" if ok else "warning", timeout=12)
        self.show_task(SYSTEM)

    def models_text(self, only: str | None = None) -> str:
        return reports.models_text(self.cfg, only)

    def action_set_agent_opt(self, agent: str, key: str, value: str) -> None:
        """Bấm chip model/effort trên ô agent (tab Agents): đổi ngay, không mở bảng chọn."""
        a = self.cfg.agents.get(agent)
        if a and value != (a.model if key == "model" else a.current_effort()):
            self.notify(self.orch.set_agent_option(agent, key, value))
            self.refresh_view()

    def action_pick_agent_opt(self, agent: str, key: str) -> None:
        self.open_picker(agent, key)

    def open_picker(self, agent: str, key: str, then_effort: bool = False) -> None:
        a: AgentConfig | None = self.cfg.agents.get(agent)
        if not a:
            return
        items = a.model_choices() if key == "model" else list(a.efforts_for())
        current = a.model if key == "model" else a.current_effort()
        title = tr("Chọn {key} cho {agent}  (đang dùng: {v})", key=key, agent=agent, v=current or tr('mặc định'))

        def done(value) -> None:
            if value is not None:
                self.notify(self.orch.set_agent_option(agent, key, None if value == RESET else value))
                self.refresh_view()
            if then_effort and key == "model" and value is not None and a.efforts_for():
                self.open_picker(agent, "effort")

        self.push_screen(ChoiceScreen(title, items, current, tr("mặc định trong config / CLI")), done)

    async def _discover_missing_models(self) -> None:
        """Hỏi (song song) các CLI có lệnh liệt kê model mà chưa từng hỏi (opencode models, agy models)."""
        found = found_models(load_state())
        await self.orch.discover_all([n for n in self.cfg.active_agents() if n not in found],
                                     on_done=lambda _n, msg: self.orch.log("⚙ " + msg))

    def open_setup(self) -> None:
        self.push_screen(OnboardScreen(self.root, self.cfg, self.orch), self._setup_done)

    async def _setup_done(self, result) -> None:
        if result is None:
            mark_setup_done()
            self.orch.log(tr("ℹ Bỏ qua thiết lập. Mở lại bất cứ lúc nào bằng /setup (hoặc `ateam "
                             "setup`)."))
            return
        save_onboard(self.root, result["plan"], **result["settings"])
        await self.reload_custom()  # agent thêm (vd claude-review) và workflow mới
        c = self.cfg
        if wizard.apply_live(c, load_config(self.root)):
            await self.orch.apply_isolation()
        await self._rebuild_panes()
        self._show_input_mode()
        on = [f"{n} ({a.label()})" for n, a in c.active_agents().items()]
        flow = (tr(" Gõ mục tiêu → workflow '{default_workflow}' (/goal: trưởng nhóm lập kế hoạch).", default_workflow=c.default_workflow)
                if c.default_workflow else "")
        self.orch.log(tr("⚙ Đã lưu thiết lập. Trưởng nhóm: {lead}. Đội: {v}.{flow} Đổi lại: "
                         "/setup, /model, /effort.", lead=c.lead, v=', '.join(on), flow=flow))
        self.refresh_view()

    def open_roles(self) -> None:
        """/roles: sửa nhanh bảng Vai trò · model · effort của /setup, giữ nguyên các thiết lập khác."""
        async def done(result) -> None:
            if result:
                await self._setup_done(result)
        self.push_screen(OnboardScreen(self.root, self.cfg, self.orch, only_roles=True), done)

    def open_custom(self) -> None:
        async def done(changed) -> None:
            if changed:
                await self.reload_custom()
        self.push_screen(CustomScreen(self.root, self.cfg), done)

    async def on_custom_panel_changed(self, event: CustomPanel.Changed) -> None:
        await self.reload_custom()  # sửa ở tab Agents / Workflows: có hiệu lực ngay
        for panel in self.screen.query(CustomPanel):  # tab còn lại cũng thấy thay đổi
            if panel is not event.control:
                self.run_worker(panel.refill(), exclusive=False)

    def open_default_flow(self, after=None) -> None:
        """Popup "Luồng mặc định" (/flow-setup, nút ở tab 🔀 Workflows)."""
        async def done(name) -> None:
            if not name:
                return
            await self.reload_custom()
            if after:
                await after()
        self.push_screen(DefaultFlowScreen(self.cfg), done)

    async def reload_custom(self) -> None:
        """Đọc lại custom.toml: thêm/bớt/sửa agent tuỳ chỉnh và workflow ngay, không cần mở lại app."""
        added, removed = wizard.reload_custom(self.cfg, load_config(self.root))
        self._show_input_mode()
        await self._rebuild_panes()
        msg = (tr("⚙ Đã cập nhật agent/workflow tuỳ chỉnh. Agent: {v}", v=', '.join(self.cfg.agents))
               + (tr(" (mới: {v})", v=', '.join(sorted(added))) if added else "")
               + (tr(" (đã xoá: {v})", v=', '.join(sorted(removed))) if removed else "")
               + f". Workflow: {', '.join(self.cfg.workflows) or tr('(chưa có)')}.")
        self.orch.log(msg)
        self.refresh_view()

    def flows_text(self) -> str:
        return reports.flows_text(self.cfg)

    async def _rebuild_panes(self) -> None:
        grid = self.query_one("#team-grid", Vertical)
        self.set_focus_agent(None)
        await grid.remove_children()
        await grid.mount_all([AgentPane(n) for n in self.pane_order()])
        self._preload_panes()
        # truyền hàm (không phải coroutine): worker bị huỷ trước khi chạy (thoát app) không để lại coroutine treo
        self.run_worker(self.query_one("#roles-table", RolesTable).reload, exclusive=False)
        self.run_worker(self.query_one("#agents-custom", CustomPanel).refill, exclusive=False)

    def _check_effort(self, agent: str, effort: str | None) -> None:
        a = self.cfg.agents[agent]
        if effort and effort != "-" and a.efforts_for() and effort not in a.efforts_for():
            self.notify(tr("'{effort}' không có trong danh sách của {agent}: {v} — vẫn dùng, nhưng "
                           "CLI có thể báo lỗi", effort=effort, agent=agent, v=', '.join(a.efforts_for())), severity="warning")

    def open_agent_terminal(self, agent: str) -> None:
        self.run_worker(self._agent_terminal(agent), exclusive=True, group="agent-term")

    async def _agent_terminal(self, agent: str) -> None:
        """Nhường terminal cho CLI thật của agent (tiếp tục phiên chat), thoát CLI thì quay lại ateam. Vòng lặp vẫn
        chạy (task khác vẫn chạy, chỉ không vẽ màn hình) nên dùng tiến trình con async, không subprocess.run."""
        a = self.cfg.agents.get(agent)
        argv = a.interactive_argv(self.orch.terminal_session(agent)) if a else None
        if not argv:
            self.notify(tr("Không biết cách mở {agent} ở chế độ tương tác (agent tuỳ chỉnh) — tự mở trong terminal khác",
                           agent=agent), severity="warning")
            return
        cmd = " ".join(shlex.quote(x) for x in argv)
        loop = asyncio.get_running_loop()
        try:
            with self.suspend():
                print(tr("\n── {agent}: {cmd} — thoát CLI để quay lại ateam ──\n", agent=agent, cmd=cmd), flush=True)
                # Ctrl+C lọt ra ngoài CLI (lúc nó chưa vào raw mode) không được giết luôn ateam; handler (không phải
                # SIG_IGN) để tiến trình con vẫn nhận Ctrl+C bình thường sau exec
                loop.add_signal_handler(signal.SIGINT, lambda: None)
                try:
                    proc = await asyncio.create_subprocess_exec(*argv, cwd=str(self.root))
                    await proc.wait()
                finally:
                    loop.remove_signal_handler(signal.SIGINT)
        except SuspendNotSupported:
            self.copy_to_clipboard(cmd)
            self.notify(tr("Giao diện này không nhường terminal được — chạy trong terminal khác (đã chép): {cmd}",
                           cmd=cmd), timeout=12)
        except OSError as e:
            self.notify(tr("Không chạy được {cmd}: {e}", cmd=cmd, e=e), severity="error")
        self.refresh_view()

    def pane_order(self) -> list[str]:
        """Agent đang bật theo thứ tự ở tab Agents (như web): agent giữ vai trò theo thứ tự vai trò, rồi agent khác."""
        on = [n for n, a in self.cfg.agents.items() if a.enabled]
        holders = wizard.role_agents(self.cfg)
        first = [holders[k] for k, _l, _d in ROLES if holders.get(k) in on]
        first = list(dict.fromkeys(first))
        return first + [n for n in on if n not in first]

    def role_label(self, agent: str) -> str:
        """Tên vai trò agent đang giữ (★ Trưởng nhóm, Code…) — "" nếu không giữ vai trò nào."""
        holders = wizard.role_agents(self.cfg)
        return ", ".join(label for k, label, _d in ROLES if holders.get(k) == agent)

    def action_agent_btn(self, agent: str, what: str) -> None:
        """Nút trên dòng agent ở tab Agents: chat (phóng to), term (CLI thật), edit/del (agent tuỳ chỉnh)."""
        if what == "chat":
            self.set_focus_agent(agent)
        elif what == "term":
            self.open_agent_terminal(agent)
        elif what in ("edit", "del"):
            panel = self.query_one("#agents-custom", CustomPanel)
            self.run_worker(panel.edit_agent(agent) if what == "edit" else panel.delete_agent(agent), exclusive=False)

    def set_focus_agent(self, agent: str | None) -> None:
        """Phóng to ô của `agent` cả tab Agents (log + ô chat, ẩn danh sách và Timeline), None = về danh sách."""
        self.focus_agent = agent if agent and self.pane(agent) else None
        self.query_one("#team-grid", Vertical).set_class(self.focus_agent is not None, "focused")
        self.query_one("#team", Vertical).set_class(self.focus_agent is not None, "focused")
        for p in self.query(AgentPane):
            p.set_class(self.focus_agent is not None and p.agent != self.focus_agent, "unfocused")
        if self.focus_agent:
            self.query_one("#tabs", TabbedContent).active = "tab-team"
            self.pane(self.focus_agent).query_one(".pane-chat", Input).focus()

    def action_focus_agent(self, agent: str | None = None) -> None:
        """F7: phóng to ô agent đang chứa con trỏ (không có thì trưởng nhóm); đang phóng to thì thu lại."""
        if self.focus_agent and (agent is None or agent == self.focus_agent):
            self.set_focus_agent(None)
            return
        if agent is None:
            node = self.focused
            while node is not None and not isinstance(node, AgentPane):
                node = node.parent
            agent = node.agent if node is not None else self.cfg.lead
            if not self.pane(agent):
                agent = next((p.agent for p in self.query(AgentPane)), None)
        self.set_focus_agent(agent)

    def send_chat(self, agent: str, text: str) -> None:
        """Ô 💬 của ô agent (tab Agents) và /chat: mỗi tin là một lượt chạy tiếp phiên CLI của agent."""
        pane = self.pane(agent)
        if text in ("/term", "/terminal"):
            self.open_agent_terminal(agent)
            return
        if text == "/focus":
            self.action_focus_agent(agent)
            return
        new = text == "/new" or text.startswith("/new ")
        if new:
            text = text[4:].strip()
            if pane:
                pane.body.write(Text(tr("── cuộc trò chuyện mới ──"), "dim"))
            if not text:
                self.orch.chat_reset(agent)
                return
        res = self.orch.chat(agent, text, new=new)
        if isinstance(res, str):
            self.notify(res, severity="warning")
            return
        if pane:
            pane.body.write(Text(tr("› bạn: {text}", text=text), "bold"))

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
                self.notify(tr("Dùng: /task <agent>[:model][@effort] <nội dung>  — agent: {v}", v=', '.join(agents)), severity="warning")
                return
            agent, model, effort = m.group(1), m.group(2), m.group(3)
            self._check_effort(agent, effort)
            o.add_task(agent, prompt.strip(), model=model, effort=effort)
        elif cmd == "chat":
            agent, _, msg = rest.partition(" ")
            if agent not in agents:
                self.notify(tr("Dùng: /chat <agent> <tin nhắn>  — agent: {v}", v=", ".join(agents)), severity="warning")
                return
            self.query_one("#tabs", TabbedContent).active = "tab-team"
            if self.focus_agent != agent:
                self.set_focus_agent(agent)  # tab Agents là danh sách: chat = phóng to ô của agent
            if msg.strip():
                self.send_chat(agent, msg.strip())
        elif cmd == "rules":
            if rest:
                err = rules.apply(self.root, "add", {"text": rest})
                self.notify(err or tr("📏 Đã thêm rule — mọi agent nhận từ lượt sau"), severity="warning" if err else "information")
            else:
                self.push_screen(RulesScreen())
        elif cmd == "open":
            if rest:
                self.open_project(rest)
            else:
                self.action_open_project()
        elif cmd == "focus":
            if rest and rest not in agents:
                self.notify(tr("Dùng: /focus [agent]  — agent: {v}", v=", ".join(agents)), severity="warning")
                return
            self.action_focus_agent(rest or None)
        elif cmd in ("model", "effort"):
            parts = rest.split(maxsplit=1)
            if not parts or parts[0] not in self.cfg.agents:
                self.notify(tr("Dùng: /{cmd} <agent> <giá trị|->  — agent: {v}", cmd=cmd, v=', '.join(self.cfg.agents)),
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
                self.notify(tr("Dùng: /models [agent] [làm mới] — agent: {v}", v=', '.join(self.cfg.agents)),
                            severity="warning")
                return
            if len(parts) > 1:
                async def _d(agent=parts[0]):
                    self.notify(tr("Đang hỏi {agent} danh sách model…", agent=agent))
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
                self.notify(tr("Dùng: /set <task> model|effort <giá trị|->"), severity="warning")
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
                self.notify(tr("Lệnh kiểm tra: {v} · sửa tối đa {max_fix_attempts} lần", v=v.command or tr('(tắt)'), max_fix_attempts=v.max_fix_attempts)
                            + (tr(" · người sửa: {fix_agent}", fix_agent=v.fix_agent) if v.fix_agent else ""))
                return
            if rest.lower() in ("off", "-", "tắt"):
                save_project_setting(self.root, "verify_command", None)
                v.command = ""
                o.log(tr("⚙ Tắt kiểm tra sau mỗi task cho dự án này."))
            else:
                save_project_setting(self.root, "verify_command", rest)
                v.command = rest
                o.log(tr("⚙ Kiểm tra sau mỗi task: `{rest}` (sửa tối đa {max_fix_attempts} lần)", rest=rest, max_fix_attempts=v.max_fix_attempts))
        elif cmd == "usage":
            self.write_sys(self.usage_text())
            self.run_worker(self._cli_usage(), exclusive=True, group="cli-usage")
        elif cmd == "update":
            self.run_worker(self._self_update(), exclusive=True, group="self-update")
        elif cmd == "cooldown":
            parts = rest.split()
            if not parts:
                self.notify(tr("Dùng: /cooldown <agent> <phút|off>"), severity="warning")
                return
            mins = None if len(parts) < 2 or parts[1].lower() in ("off", "0", "-") else int(parts[1])
            self.notify(o.set_cooldown_manual(parts[0], mins))
        elif cmd == "go":
            n = o.approve(num(rest) if rest else None)
            self.notify(tr("Đã duyệt {n} task", n=n) if n else tr("Không có task nháp"))
        elif cmd == "clear":
            self.clear_board()
        elif cmd == "drop":
            bar = self.query_one("#plan", PlanBar)
            gid = num(rest) if rest else bar.goal_id
            g = o.db.goal(gid) if gid is not None else None
            if not g or g.status != "awaiting":
                self.notify(tr("Không có kế hoạch nháp nào để bỏ"), severity="warning")
                return
            self.notify(tr("Đã bỏ kế hoạch #{gid} ({v} task nháp)", gid=gid, v=o.discard_plan(gid)))
        elif cmd == "assign":
            tid, *agent = shlex.split(rest)[:2]
            if agent:
                self.notify(o.assign(num(tid), agent[0], rerun=True))
            else:
                self.reassign_task(num(tid))
        elif cmd == "edit" and not re.match(r"^#?\d+(\s|$)", rest.strip()):
            target, line = parse_code_target(rest)  # /edit @file: mở file trong tab 📝 Code
            self.open_code(target, line)
        elif cmd == "edit":
            tid, _, prompt = rest.partition(" ")
            self.notify(o.edit(num(tid), prompt.strip()))
        elif cmd == "retry":
            self.notify(o.retry(num(rest)))
        elif cmd == "cancel":
            self.notify(o.cancel_command(rest))
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
        elif cmd == "init":
            async def _i(focus=rest):
                ok, msg = await o.init_overview(focus)
                self.notify(msg, severity="information" if ok else "warning")
                self.refresh_view()
            self.run_worker(_i(), exclusive=False)
        elif cmd == "pause":
            o.paused = True
            o.log(tr("⏸ Tạm dừng: không bắt đầu task mới (task đang chạy vẫn tiếp tục)."))
        elif cmd == "resume":
            o.paused = False
            o.log(tr("▶ Tiếp tục."))
        elif cmd == "log":
            self.query_one("#tabs", TabbedContent).active = "tab-board"
            self.show_task(SYSTEM if rest in ("", "sys", "0") else num(rest))
        elif cmd in ("team", "agent-moi"):
            self.query_one("#tabs", TabbedContent).active = "tab-team"
        elif cmd == "board":
            self.query_one("#tabs", TabbedContent).active = "tab-board"
        elif cmd == "agents":
            self.write_sys(reports.agents_text(self.cfg))
        elif cmd == "setup":
            self.open_setup()
            return
        elif cmd == "roles":
            self.open_roles()
            return
        elif cmd == "dash":
            self.query_one("#tabs", TabbedContent).active = "tab-dash"
        elif cmd == "search":
            self.action_search(rest or None)
            return
        elif cmd == "plan":
            self.open_plan(int(rest.lstrip("#mM")) if rest else None)
            return
        elif cmd == "todo":
            if rest.strip():
                try:
                    todos.apply(self.root, "add", {"text": rest})
                    self.notify(tr("✅ Đã thêm vào To-do"))
                except ValueError:
                    self.notify(tr("Nhập nội dung việc cần làm"), severity="warning")
            self.query_one("#tabs", TabbedContent).active = "tab-todo"
            return
        elif cmd == "notes":
            self.query_one("#tabs", TabbedContent).active = "tab-notes"
            if rest.strip():
                self.query_one("#notes-tab").new_note(rest.strip())
            return
        elif cmd == "tags":
            from .tui_todo import TagScreen
            self.query_one("#tabs", TabbedContent).active = "tab-todo"
            self.push_screen(TagScreen(self.root), lambda _r: self.query_one("#todo-tab").reload(force=True))
            return
        elif cmd == "grid":
            self.query_one("#tabs", TabbedContent).active = "tab-grid"
            agent = rest.strip()
            if agent:
                from .tui_grid import GridPanel
                panel = self.query_one("#grid-panel", GridPanel)
                self.run_worker(panel._add({"agent": agent, "resume": True}), group="grid-add")
            return
        elif cmd == "flow-setup":
            self.open_default_flow()
            return
        elif cmd in ("custom", "workflow", "workflows"):
            self.query_one("#tabs", TabbedContent).active = "tab-custom"  # popup vẫn mở từ /setup
            return
        elif cmd == "goal":
            self.start_goal(rest.strip())
        elif cmd in ("theme", "giaodien", "mau"):
            args = rest.split()
            if not args:
                self.action_open_theme()
                return
            name = args[0].lower()
            if name not in self.available_themes or "+" in name:
                self.notify(tr("Không có theme {name} — có: {v}", name=name, v=", ".join(theme.theme_names())),
                            severity="warning", timeout=8)
                return
            accent = ""
            if len(args) > 1:
                acc = theme.normalize_accent(" ".join(args[1:]))
                if acc is None:
                    acc = theme.normalize_accent("-".join(args[1:]))
                if acc is None:
                    self.notify(tr("Không có màu nhấn {name} — có: {v}", name=" ".join(args[1:]),
                                   v=", ".join(theme.ACCENTS)), severity="warning", timeout=8)
                    return
                accent = acc
            self.apply_theme(name, accent, save=True)
            self.notify(tr("Theme: {v}", v=theme.theme_id(name, accent)))
            return
        elif cmd in ("lang", "language", "ngonngu"):
            code = normalize(rest)
            if not code:
                self.notify(tr("Ngôn ngữ: {v} · đổi bằng /lang en hoặc /lang vi", v=LANG_NAMES[get_lang()]),
                            severity="warning")
                return
            if code == get_lang():
                self.notify(tr("Đang dùng {v} rồi", v=LANG_NAMES[code]))
                return
            save_lang(code)
            if o.runs or o.lead_busy:
                self.notify(tr("Đã lưu {v} — áp dụng khi mở lại app (đang có agent chạy, không tự mở "
                               "lại)", v=LANG_NAMES[code]), timeout=8)
                return
            self.restart_requested = True
            self.call_later(self.action_quit)
            return
        elif cmd in ("grill", "grill-me", "hoi"):
            msg = o.grill_command(rest)
            if msg is not None:
                self.notify(msg)
            elif not self.cfg.agents.get(self.cfg.lead):
                self.notify(tr("Không có trưởng nhóm '{lead}' trong cấu hình", lead=self.cfg.lead), severity="error")
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
                self.notify(tr("↪ Trưởng nhóm đang lập kế hoạch tiếp cho mục tiêu #{i}", i=i))
                self.show_task(SYSTEM)
            else:
                self.notify(tr("↪ Task #{i}: hỏi tiếp {agent}", i=i, agent=self.db.task(i).agent))
                self.show_task(i)
        elif cmd == "sh":
            self.run_shell(rest)
        elif cmd == "stop":
            job = self.shell.jobs.get(num(rest)) if rest.strip() else self.selected_job()
            if not job or not self.shell.stop(job):
                self.notify(tr("Không có lệnh nào đang chạy để dừng"), severity="warning")
            else:
                self.notify(tr("■ Đã dừng: {cmd}", cmd=job.cmd))
        elif cmd == "term":
            self.query_one("#tabs", TabbedContent).active = "tab-term"
            self.refresh_view()
        elif cmd in ("code", "open", "vi"):
            target, line = parse_code_target(rest)
            self.open_code(target, line)
        elif cmd == "notify":
            try:
                msg, test = notify.command(rest)
            except ValueError:
                self.notify(command_usage(cmd), severity="warning")
                return
            self.notify(msg)
            if test:
                self.show_notices([notify.test_notice()], force=True)
        elif cmd == "vim":
            arg = rest.strip().lower()
            if arg in ("on", "off", "bật", "bat", "tắt", "tat"):
                on = arg in ("on", "bật", "bat")
                st = load_state()
                st["vim"] = on
                save_state(st)
                ed = self.query_one("#code-editor", CodeEditor)
                ed.vim_on = on
                ed.vim = editor.VimState()
                ed.set_class(False, "-insert")
                self._refresh_code_head()
                self.notify(tr("Phím vim trong tab 📝 Code: bật") if on else
                            tr("Phím vim trong tab 📝 Code: tắt (Ctrl+S lưu)"))
            elif arg:
                target, line = parse_code_target(rest)
                self.open_code(target, line)
            else:
                self.notify(tr("Phím vim: {v} · /vim on|off · /vim <file> mở file",
                               v=tr("bật") if self.query_one("#code-editor", CodeEditor).vim_on else tr("tắt")))
        elif cmd in ("git", "commit", "push", "pull", "fetch", "branch", "checkout", "stash"):
            self.git_command(cmd, rest)
        elif cmd in ("flow", "flows"):
            name, _, goal = rest.partition(" ")
            if not name or not goal.strip():
                if name and name not in self.cfg.workflows:
                    self.notify(tr("Không có workflow '{name}'", name=name), severity="warning")
                self.write_sys(self.flows_text())
                return
            res = o.run_workflow(name, goal.strip())
            if isinstance(res, str):
                self.notify(res, severity="warning")
        elif cmd in ("quit", "exit", "q"):
            self.call_later(self.action_quit)
        else:
            near = suggest_command(cmd)
            self.notify(tr("Không hiểu lệnh /{cmd}", cmd=cmd) + (tr(" — có phải /{near}?", near=near) if near else "")
                        + tr(" · gõ / để xem danh sách, F1 trợ giúp"), severity="warning")
        self.refresh_view()


class BusyApp(App):
    """Hiện khi dự án đã có phiên giao diện khác giữ khoá (xem cli.acquire_session_lock)."""

    BINDINGS = [Binding("ctrl+q", "quit", tr("Thoát"), priority=True)]
    CSS = "Screen { align: center middle; } #busy { width: 70; height: auto; padding: 1 2; border: round $warning; }"

    def compose(self) -> ComposeResult:
        yield Static(tr("Dự án này đang mở ở một phiên ateam khác (terminal hoặc tab web).\n"
                        "Đóng phiên đó rồi mở lại.  ·  Ctrl+Q để thoát"), id="busy")
