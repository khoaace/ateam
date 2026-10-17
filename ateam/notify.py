"""Thông báo khi có việc cần người dùng: kế hoạch chờ duyệt, task chờ duyệt diff, task lỗi/xung đột.

`Watcher` so trạng thái task/mục tiêu giữa hai lần đọc DB (TUI mỗi lượt vẽ, web mỗi lượt đẩy ảnh chụp) —
không chèn vào từng chỗ đổi trạng thái trong orchestrator. `desktop()` hiện thông báo của hệ điều hành.
Chế độ lưu ở state.json `notify`: all (mặc định) | app (chỉ trong app) | off."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from dataclasses import dataclass

from .config import load_state, save_state
from .db import ASKING, CONFLICT, FAILED, REVIEW
from .i18n import tr

MODES = ("all", "app", "off")


@dataclass
class Notice:
    kind: str  # failed | conflict | review | plan | ask
    title: str
    body: str
    task_id: int | None = None
    goal_id: int | None = None
    level: str = "info"  # info | warn

    def to_json(self) -> dict:
        return {"t": "notice", "kind": self.kind, "title": self.title, "body": self.body,
                "task": self.task_id, "goal": self.goal_id, "level": self.level}


def _short(s: str, n: int = 120) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


class Watcher:
    """Nhớ trạng thái lần đọc trước; lần đầu chỉ ghi nhận (mở app không báo lại việc cũ)."""

    def __init__(self) -> None:
        self.tasks: dict[int, str] | None = None
        self.goals: dict[int, str] = {}

    def diff(self, tasks: list, goals: list) -> list[Notice]:
        first = self.tasks is None
        old_t, old_g = self.tasks or {}, self.goals
        self.tasks = {t.id: t.status for t in tasks}
        self.goals = {g.id: g.status for g in goals}
        if first:
            return []
        out: list[Notice] = []
        for g in goals:
            if g.status == "awaiting" and old_g.get(g.id) != "awaiting":
                out.append(Notice("plan", tr("📝 Kế hoạch chờ duyệt"),
                                  tr("Mục tiêu #{gid}: {text}", gid=g.id, text=_short(g.text)), goal_id=g.id))
        for t in tasks:
            if t.status == old_t.get(t.id):
                continue
            head = f"#{t.id} {_short(t.title, 80)} · {t.agent}"
            if t.status == FAILED:
                out.append(Notice("failed", tr("✗ Task lỗi"), head + (" — " + _short(t.error, 100) if t.error else ""),
                                  task_id=t.id, goal_id=t.goal_id, level="warn"))
            elif t.status == CONFLICT:
                out.append(Notice("conflict", tr("⚠ Task bị xung đột khi merge"), head, task_id=t.id,
                                  goal_id=t.goal_id, level="warn"))
            elif t.status == REVIEW:
                out.append(Notice("review", tr("👀 Task chờ duyệt diff"), head, task_id=t.id, goal_id=t.goal_id))
            elif t.status == ASKING:
                q = t.question() if hasattr(t, "question") else None
                out.append(Notice("ask", tr("❓ Agent hỏi bạn"), head + (" — " + _short(q["q"], 140) if q else ""),
                                  task_id=t.id, goal_id=t.goal_id))
        return out


def mode() -> str:
    m = load_state().get("notify")
    return m if m in MODES else "all"


def set_mode(m: str) -> None:
    st = load_state()
    if m == "all":
        st.pop("notify", None)
    else:
        st["notify"] = m
    save_state(st)


def parse_mode(arg: str) -> str | None:
    """'/notify on|app|off' → chế độ; None nếu không hiểu."""
    arg = arg.lower()
    if arg in ("on", "all", "bật", "bat"):
        return "all"
    if arg in ("off", "tắt", "tat"):
        return "off"
    return "app" if arg == "app" else None


def mode_label(m: str) -> str:
    return {"all": tr("bật (trong app + thông báo hệ thống)"), "app": tr("chỉ trong app"),
            "off": tr("tắt")}[m]


def _osa(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


async def desktop(title: str, body: str) -> bool:
    """Thông báo của hệ điều hành (macOS: Notification Center; Linux: notify-send). Không có thì bỏ qua.
    ATEAM_DESKTOP_NOTIFY=0 tắt hẳn (test chạy agent giả lập không bật thông báo thật trên máy)."""
    if os.environ.get("ATEAM_DESKTOP_NOTIFY") == "0":
        return False
    if sys.platform == "darwin" and shutil.which("osascript"):
        argv = ["osascript", "-e", f"display notification {_osa(body)} with title {_osa(title)} subtitle \"ateam\""]
    elif shutil.which("notify-send"):
        argv = ["notify-send", "-a", "ateam", title, body]
    else:
        return False
    try:
        p = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.DEVNULL,
                                                 stdout=asyncio.subprocess.DEVNULL,
                                                 stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(p.wait(), 10)
        return p.returncode == 0
    except Exception:
        return False


def test_notice() -> Notice:
    return Notice("test", "🔔 ateam", tr("Thông báo thử — có kế hoạch/diff chờ duyệt hoặc task lỗi sẽ báo thế này."))


def command(rest: str) -> tuple[str, bool]:
    """/notify [on|app|off|test] — dùng chung TUI và web. Trả (lời nhắn, có gửi thông báo thử không).
    Tham số lạ → ValueError (bên gọi in cách dùng)."""
    arg = rest.strip().lower()
    if arg == "test":
        return tr("🔔 Đã gửi thông báo thử"), True
    if arg:
        m = parse_mode(arg)
        if not m:
            raise ValueError(arg)
        set_mode(m)
    return tr("Thông báo: {v} · /notify on|app|off|test", v=mode_label(mode())), False
