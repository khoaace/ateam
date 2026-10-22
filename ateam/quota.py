"""Hạn mức 5 giờ / tuần của từng CLI dạng số (thanh tiến độ ở giao diện web) — bóc từ cùng nguồn với /usage:
`claude -p /usage`, `agy -p /usage`, ảnh chụp rate_limits trong file phiên codex. Grok không có lệnh headless nào in
hạn mức nên không có ở đây."""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from . import limits
from .i18n import tr

if TYPE_CHECKING:
    from .orchestrator import Orchestrator

QUOTA_CLIS = ("claude", "codex", "agy")
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"), 1)}
# "Current session: 13% used · resets Oct 22 at 12:09pm (Asia/Saigon)", "Current week (all models): 3% used · …"
CLAUDE_RE = re.compile(r"Current (session|week)(?:\s*\(([^)]*)\))?:\s*(\d+(?:\.\d+)?)%\s*used(?:.*?resets\s+(.+))?",
                       re.I)
CLAUDE_AT_RE = re.compile(r"(?:([a-z]{3})[a-z]*\.?\s+(\d{1,2})(?:,?\s+at)?\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)"
                          r"(?:\s*\(([^)]+)\))?", re.I)
# "Gemini Models  Weekly Limit Remaining  11%  2026-10-24 09:03 +07" — số in ra là phần CÒN LẠI
AGY_RE = re.compile(r"^\s*(.+?)\s{2,}(Weekly|Five Hour) Limit Remaining\s+(\d+(?:\.\d+)?)%"
                    r"(?:\s+(\d{4}-\d\d-\d\d \d\d:\d\d)\s*([+-]\d\d):?(\d\d)?)?", re.I)


def window(kind: str, used: float, resets_at: float | None, group: str = "") -> dict:
    return {"kind": kind, "label": "5h" if kind == "5h" else tr("tuần") if kind == "week" else kind,
            "group": group, "used": max(0.0, min(100.0, float(used))), "resets_at": resets_at}


def _claude_reset(text: str, now: float) -> float | None:
    """"Oct 22 at 12:09pm (Asia/Saigon)", "Oct 20 at 6am", "7pm" → epoch (múi giờ trong ngoặc nếu có)."""
    m = CLAUDE_AT_RE.search(text or "")
    if not m:
        return None
    mon, day, h, mi, ap, tzname = m.groups()
    tz = None
    if tzname:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tzname.strip())
        except Exception:  # tên múi giờ lạ / máy thiếu tzdata: dùng giờ máy
            tz = None
    base = dt.datetime.fromtimestamp(now, tz)
    hour = int(h) % 12 + (12 if ap.lower() == "pm" else 0)
    try:
        if mon:
            if mon.lower() not in MONTHS:
                return None
            cand = base.replace(month=MONTHS[mon.lower()], day=int(day), hour=hour, minute=int(mi or 0), second=0,
                                microsecond=0)
            if cand.timestamp() < now - 180 * 86400:  # "Jan 2" in vào cuối tháng 12 → năm sau
                cand = cand.replace(year=cand.year + 1)
        else:
            cand = base.replace(hour=hour, minute=int(mi or 0), second=0, microsecond=0)
            if cand.timestamp() <= now:
                cand += dt.timedelta(days=1)
    except ValueError:
        return None
    return cand.timestamp()


def parse_claude(lines: list[str], now: float | None = None) -> list[dict]:
    now = now or time.time()
    out = []
    for ln in lines:
        m = CLAUDE_RE.search(ln)
        if not m:
            continue
        kind, group, used, reset = m.groups()
        group = "" if not group or group.strip().lower() == "all models" else group.strip()
        out.append(window("5h" if kind.lower() == "session" else "week", float(used), _claude_reset(reset, now),
                          group))
    return out


def parse_agy(lines: list[str]) -> list[dict]:
    out = []
    for ln in lines:
        for part in ln.split("\r"):
            m = AGY_RE.search(part)
            if not m:
                continue
            group, kind, left, at, tzh, tzm = m.groups()
            reset = None
            if at:
                off = dt.timedelta(hours=int(tzh), minutes=int(tzm or 0) * (-1 if tzh.startswith("-") else 1))
                reset = dt.datetime.strptime(at, "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone(off)).timestamp()
            out.append(window("week" if kind.lower() == "weekly" else "5h", 100 - float(left), reset, group.strip()))
    return out


def codex_quota(home=None, now: float | None = None) -> tuple[list[dict], float | None]:
    """Khung hạn mức codex + lúc chụp. Khung theo window_minutes (gói Plus có khi chỉ có `primary` = tuần);
    khung đã qua giờ hồi từ lúc chụp thì coi như đã dùng 0%."""
    now = now or time.time()
    snap, when = limits.codex_snapshot(home)
    if not snap:
        return [], None
    out = []
    for key in ("primary", "secondary"):
        w = snap.get(key)
        if not isinstance(w, dict) or not isinstance(w.get("used_percent"), (int, float)):
            continue
        mins = w.get("window_minutes")
        kind = "5h" if mins == 300 else "week" if mins == 10080 else limits._window(mins)
        reset = float(w["resets_at"]) if w.get("resets_at") else None
        if reset and reset <= now:
            out.append(window(kind, 0, None))
        else:
            out.append(window(kind, w["used_percent"], reset))
    at = None
    if when:
        try:
            at = dt.datetime.fromisoformat(str(when).replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return out, at


async def collect(orch: "Orchestrator") -> list[dict]:
    """Hạn mức của các CLI đã cài trong QUOTA_CLIS (song song). Hạn mức là của tài khoản CLI: hỏi qua agent đầu
    tiên dùng CLI đó (ưu tiên agent đang bật), kể cả khi mọi agent của nó đang tắt."""
    cfg = orch.cfg

    async def one(cli: str) -> dict | None:
        names = [n for n, a in cfg.agents.items() if Path(a.binary).name == cli]
        name = next((n for n in names if cfg.agents[n].enabled), names[0] if names else None)
        if not name or not cfg.agents[name].installed():
            return None
        item = {"cli": cli, "agent": name, "windows": [], "at": time.time(), "error": ""}
        if cli == "codex":
            item["windows"], at = codex_quota()
            item["at"] = at or item["at"]
            if not item["windows"]:
                item["error"] = tr("Chưa có phiên codex nào ghi hạn mức — chạy 1 task codex trước.")
            return item
        _cmd, lines = await orch.agent_usage(name)
        item["windows"] = parse_claude(lines) if cli == "claude" else parse_agy(lines)
        if not item["windows"]:
            item["error"] = next((ln.strip() for ln in lines if ln.strip()), "")[:160]
        return item
    return [i for i in await asyncio.gather(*(one(c) for c in QUOTA_CLIS)) if i]
