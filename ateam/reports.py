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
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M" if n < 10_000_000 else f"{n // 1_000_000}M"
    return f"{n / 1000:.1f}k" if n < 10000 else f"{n // 1000}k"


def fmt_cost(usd: float | None) -> str:
    if usd is None:
        return "—"
    return f"${usd:.2f}" if usd >= 0.01 or usd == 0 else "<$0.01"


def today_start() -> float:
    lt = time.localtime()
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def usage_text(cfg: Config, db: DB, orch: "Orchestrator") -> str:
    now = time.time()
    out = []
    for label, since in ((tr("Hôm nay"), today_start()), (tr("7 ngày"), now - 7 * 86400)):
        by = summarize(db.runs_since(since), "agent")
        out.append(f"{label}:")
        out.append(f"  {'agent':12} {tr('lượt'):>5} {tr('thời gian'):>10} {'token':>8} {'cost':>8} {tr('lỗi'):>4} "
                   f"{tr('hết HM'):>6}")
        for name in cfg.agents:
            r = by.get(name)
            if not r:
                continue
            tok = fmt_tokens(r["tokens"]) + ("" if r["real"] == r["runs"] else "~")
            out.append(f"  {name:12} {r['runs']:>5} {fmt_dur(r['secs']):>10} {tok:>8} {fmt_cost(r['cost']):>8} "
                       f"{r['failed']:>4} {r['ratelimits']:>6}")
    cds = [tr("{a} đến {v}", a=a, v=orch.cooldown_label(a)) for a in cfg.agents if orch.in_cooldown(a)]
    out.append(tr("Đang tạm nghỉ: ") + (", ".join(cds) if cds else tr("không")))
    out.append(TOKEN_NOTE)
    out.append(tr("Xem thêm: /dash (biểu đồ theo ngày, theo model, lịch sử mục tiêu)"))
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


def continue_candidates(db: DB, tasks: list | None = None, goals: list | None = None) -> list[dict]:
    """Gợi ý /continue: mục tiêu đã kết thúc (mới nhất trước, tối đa 10) rồi thread /task đã xong (tối đa 10).
    Mỗi mục: {ref, kind: goal|task, status, title, summary, agent}. tasks/goals: danh sách đã đọc sẵn."""
    out: list[dict] = []
    for g in reversed(db.goals() if goals is None else goals):
        if g.status not in GOAL_ENDED:
            continue
        out.append({"ref": f"m{g.id}", "kind": "goal", "status": g.status,
                    "title": g.text.splitlines()[0] if g.text else "",
                    "summary": (g.summary or "").splitlines()[0] if g.summary else "", "agent": ""})
        if len(out) >= 10:
            break
    tasks = db.tasks() if tasks is None else tasks
    has_next = {t.parent_id for t in tasks if t.source == "followup" and t.goal_id is None}
    n = 0
    for task in reversed(tasks):
        if task.goal_id is not None or task.status in ACTIVE or task.id in has_next or task.source == "chat":
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


# ------------------------------------------------------------------ dashboard (/dash, tab 📊 Thống kê, web)
TOKEN_NOTE = tr("token: Claude Code & Codex đọc từ log phiên của CLI; agent khác ước tính ~4 ký tự/token (dấu ~). "
                "cost: ước tính theo bảng giá công khai — sửa bằng [prices.\"<model>\"] trong config.toml.")


def _bucket() -> dict:
    return {"runs": 0, "secs": 0.0, "tokens": 0, "in_tok": 0, "out_tok": 0, "cache": 0, "cost": None,
            "failed": 0, "ratelimits": 0, "real": 0}


def _add(b: dict, r: dict) -> None:
    b["runs"] += 1
    b["secs"] += max(0.0, (r.get("finished") or r["started"]) - r["started"])
    b["tokens"] += int(r.get("tokens") or 0)
    if r.get("in_tok") is not None:
        b["in_tok"] += int(r["in_tok"] or 0)
        b["out_tok"] += int(r["out_tok"] or 0)
        b["cache"] += int(r.get("cache_read") or 0) + int(r.get("cache_write") or 0)
    else:  # lượt cũ (trước khi có cột token): ước tính
        b["in_tok"] += int(r.get("prompt_chars") or 0) // 4
        b["out_tok"] += int(r.get("output_chars") or 0) // 4
    if r.get("cost") is not None:
        b["cost"] = (b["cost"] or 0.0) + float(r["cost"])
    b["failed"] += r.get("status") in ("failed", "timeout")
    b["ratelimits"] += r.get("status") == "ratelimit"
    b["real"] += r.get("tok_src") == "cli"


def summarize(runs: list[dict], key: str | None = None) -> dict:
    """Cộng dồn lượt chạy: một bucket (key None) hoặc {giá trị cột key: bucket}."""
    if key is None:
        b = _bucket()
        for r in runs:
            _add(b, r)
        return b
    out: dict = {}
    for r in runs:
        _add(out.setdefault(r.get(key) or "—", _bucket()), r)
    return out


def dashboard(db: DB, days: int = 14) -> dict:
    """Số liệu cho dashboard: tổng hôm nay / 7 / 30 ngày, theo agent, theo model (30 ngày) và theo ngày."""
    today = today_start()
    runs = db.runs_since(today - 29 * 86400)
    week = [r for r in runs if r["started"] >= today - 6 * 86400]
    per_day = []
    for i in range(days - 1, -1, -1):
        start = time.mktime(time.localtime(today - i * 86400)[:3] + (0, 0, 0, 0, 0, -1))
        b = summarize([r for r in runs if start <= r["started"] < start + 86400])
        b["day"] = time.strftime("%Y-%m-%d", time.localtime(start))
        per_day.append(b)
    return {"today": summarize([r for r in runs if r["started"] >= today]), "week": summarize(week),
            "month": summarize(runs), "by_agent": summarize(runs, "agent"), "by_model": summarize(runs, "model"),
            "per_day": per_day, "note": TOKEN_NOTE}


def goal_history(db: DB, limit: int = 50) -> list[dict]:
    """Lịch sử mục tiêu (mới nhất trước): trạng thái, số task, agent tham gia, thời gian, token, cost."""
    goals = db.goals()[-limit:][::-1]
    tasks = db.tasks()
    by_goal: dict[int, list] = {}
    for t in tasks:
        if t.goal_id is not None:
            by_goal.setdefault(t.goal_id, []).append(t)
    runs = summarize(db.runs_since(0), "gid")
    out = []
    for g in goals:
        ts = by_goal.get(g.id, [])
        ends = [t.finished for t in ts if t.finished]
        u = runs.get(g.id) or _bucket()
        out.append({"id": g.id, "text": g.text, "status": g.status, "workflow": g.workflow or "",
                    "summary": g.summary or "", "created": g.created, "finished": max(ends) if ends else None,
                    "tasks": len(ts), "done": sum(t.status == "done" for t in ts),
                    "failed": sum(t.status in ("failed", "blocked", "conflict") for t in ts),
                    "agents": sorted({t.agent for t in ts}), "tokens": u["tokens"], "cost": u["cost"],
                    "runs": u["runs"], "secs": u["secs"], "real": u["real"]})
    return out
