"""Báo cáo dạng chữ dùng chung cho TUI và giao diện web: /usage, /agents, /flow, /models, gợi ý /continue.

Không phụ thuộc Textual — trả chuỗi thường hoặc dữ liệu thô; mỗi giao diện tự tô màu.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from . import mentions
from .config import Config, describe_models
from .db import ACTIVE, DB, GOAL_ENDED
from .i18n import tr

if TYPE_CHECKING:
    from .orchestrator import Orchestrator


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


def usage_text(cfg: Config, db: DB, orch: "Orchestrator") -> str:
    now = time.time()
    out = []
    for label, since in ((tr("Hôm nay"), today_start()), (tr("7 ngày"), now - 7 * 86400)):
        u = db.usage(since)
        out.append(f"{label}:")
        out.append(f"  {'agent':12} {tr('lượt'):>5} {tr('thời gian'):>10} {'~token':>8} {tr('lỗi'):>4} "
                   f"{tr('hết HM'):>6}")
        for name in cfg.agents:
            r = u.get(name)
            if not r:
                continue
            tok = (r["prompt_chars"] + r["output_chars"]) // 4
            out.append(f"  {name:12} {r['runs']:>5} {fmt_dur(r['secs']):>10} {fmt_tokens(tok):>8} "
                       f"{r['failed']:>4} {r['ratelimits']:>6}")
    cds = [tr("{a} đến {v}", a=a, v=orch.cooldown_label(a)) for a in cfg.agents if orch.in_cooldown(a)]
    out.append(tr("Đang tạm nghỉ: ") + (", ".join(cds) if cds else tr("không")))
    out.append(tr("(~token = ước tính từ độ dài prompt và output, chưa gồm file agent tự đọc)"))
    return "\n".join(out)


def agents_text(cfg: Config) -> str:
    lines = []
    for n, a in cfg.agents.items():
        st = "✓" if a.installed() else tr("✗ chưa cài")
        lead = tr(" ★ trưởng nhóm") if n == cfg.lead else ""
        lead += tr(" · tuỳ chỉnh (/custom)") if n in cfg.custom_agents else ""
        lines.append(f"{n:12} {st}{lead}\n   model/effort: {a.label()}"
                     + (tr("   (effort hợp lệ: {v})", v=', '.join(a.efforts)) if a.efforts else "")
                     + tr("\n   lệnh: {v}", v=' '.join(a.argv('<prompt>')))
                     + f"\n   @file → {mentions.describe(a.binary, a.file_ref, a.file_args, a.image_args)}"
                     + tr("\n   vai trò: {role}", role=a.role))
    return "\n".join(lines)


def flows_text(cfg: Config) -> str:
    if not cfg.workflows:
        return tr("Chưa có workflow nào. Tạo bằng /custom → '+ Thêm workflow' (có mẫu sẵn).")
    lines = []
    for n, w in cfg.workflows.items():
        lines.append(f"⚙ {n}  ({w.summary()})" + (f" — {w.description}" if w.description else ""))
        for i, st in enumerate(w.steps, 1):
            lines.append(f"   {i}. [{st.agent}{('@' + st.effort) if st.effort else ''}] "
                         f"{st.title or st.prompt[:50]}")
    lines.append(tr("Chạy: /flow <tên> <mục tiêu>   ·   sửa: /custom"))
    return "\n".join(lines)


def models_text(cfg: Config, only: str | None = None) -> str:
    return (describe_models(cfg, only) + tr("\n"
                                            "Chọn: /model <agent>, /effort <agent> hoặc "
                                            "bấm vào ô agent ở tab Đội. Model ngoài danh "
                                            "sách vẫn đặt được: /model <agent> <tên>."))


def continue_candidates(db: DB) -> list[dict]:
    """Gợi ý /continue: mục tiêu đã kết thúc (mới nhất trước, tối đa 10) rồi thread /task đã xong (tối đa 10).
    Mỗi mục: {ref, kind: goal|task, status, title, summary, agent}."""
    out: list[dict] = []
    for g in reversed(db.goals()):
        if g.status not in GOAL_ENDED:
            continue
        out.append({"ref": f"m{g.id}", "kind": "goal", "status": g.status,
                    "title": g.text.splitlines()[0] if g.text else "",
                    "summary": (g.summary or "").splitlines()[0] if g.summary else "", "agent": ""})
        if len(out) >= 10:
            break
    tasks = db.tasks()
    has_next = {t.parent_id for t in tasks if t.source == "followup" and t.goal_id is None}
    n = 0
    for task in reversed(tasks):
        if task.goal_id is not None or task.status in ACTIVE or task.id in has_next:
            continue
        out.append({"ref": f"t{task.id}", "kind": "task", "status": task.status, "title": task.title,
                    "summary": "", "agent": task.agent})
        n += 1
        if n >= 10:
            break
    return out


def continue_hint(db: DB, orch: "Orchestrator", ref: str) -> tuple[bool, str]:
    """(được không, câu giải thích) cho /continue <ref>."""
    r = orch.continue_ref(ref)
    if isinstance(r, str):
        return False, r
    kind, i = r
    if kind == "goal":
        g = db.goal(i)
        if g.status not in GOAL_ENDED:
            return False, tr("⚠ Mục tiêu #{i} chưa kết thúc — đợi xong rồi tiếp tục", i=i)
        n = len(db.tasks(goal_id=i))
        return True, (tr("↪ Tiếp tục mục tiêu #{i} ", i=i) + f"«{g.text.splitlines()[0][:60]}»"
                      + tr(" — trưởng nhóm lập task bổ sung dựa trên {n} task đã làm", n=n))
    task = db.task(i)
    if task.status in ACTIVE:
        return False, tr("⚠ Task #{i} chưa xong (hoặc đang chờ duyệt) — đợi xong rồi tiếp tục", i=i)
    turns = len(orch.thread_of(task)) + 1
    return True, (tr("↪ Hỏi tiếp {agent} ", agent=task.agent) + f"«{task.title[:60]}»"
                  + tr(" — kèm {turns} lượt trước của thread", turns=turns))
