"""⏰ Hẹn giờ chạy mục tiêu (`/schedule`, `ateam schedule`): lúc HH:MM, sau một khoảng (+30m), hằng ngày, hoặc khi
một agent hồi hạn mức. Lịch nằm trong bảng `schedules` của `.ateam/team.db`; chỉ chạy khi một phiên ateam đang mở
(TUI, `ateam web`, `ateam run`) — `Orchestrator.tick` gọi `Orchestrator.check_schedules`."""

from __future__ import annotations

import datetime as dt
import re
import time
from pathlib import Path

from .i18n import tr

AT, DAILY, QUOTA = "at", "daily", "quota"
DAILY_WORDS = ("daily", "hangngay", "moingay", "everyday")
QUOTA_WORDS = ("quota", "hoi", "khihoi", "when")
REMOVE_WORDS = ("rm", "xoa", "huy", "cancel", "del", "delete")
# hạn mức 5 giờ dùng từ mức này trở lên coi như cạn: lịch "khi hồi" chờ tới giờ hồi
QUOTA_FULL = 95.0
CHECK_EVERY = 10.0  # giây giữa hai lần xem lịch (tick chạy ~0,7 giây/lần)
HHMM_RE = re.compile(r"(\d{1,2})[:hg](\d{2})?$", re.I)
DUR_RE = re.compile(r"\+(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?$", re.I)

USAGE = tr("Dùng: /schedule <khi> <mục tiêu> — khi: 22:30 · +45m · +2h · daily 08:00 · quota claude "
           "(chạy khi claude còn / hồi hạn mức). Mục tiêu bắt đầu bằng /flow <tên> thì chạy workflow đó. "
           "/schedule: xem lịch · /schedule rm <số>: huỷ")


def next_hhmm(hhmm: str, now: float | None = None) -> float:
    """Lần tới của giờ HH:MM theo giờ máy (đã qua hôm nay thì ngày mai)."""
    h, m = (int(x) for x in hhmm.split(":"))
    base = dt.datetime.fromtimestamp(now if now is not None else time.time())
    cand = base.replace(hour=h, minute=m, second=0, microsecond=0)
    if cand.timestamp() <= base.timestamp():
        cand += dt.timedelta(days=1)
    return cand.timestamp()


def _hhmm(word: str) -> str | None:
    m = HHMM_RE.match(word.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None


def parse(spec: str, agents: list[str], now: float | None = None) -> dict | str:
    """"22:30 viết test" / "+45m …" / "daily 08:00 …" / "quota claude …" → {"kind", "at", "daily", "agent",
    "text", "flow"}; sai cú pháp → chuỗi lỗi."""
    now = time.time() if now is None else now
    words = spec.split()
    if not words:
        return USAGE
    first, rest = words[0].lower(), words[1:]
    out: dict = {"kind": AT, "at": None, "daily": None, "agent": None}
    for sep in ("@", "="):  # daily@08:00, quota@claude
        if sep in first and first.split(sep, 1)[0] in DAILY_WORDS + QUOTA_WORDS:
            head, tail = first.split(sep, 1)
            first, rest = head, [tail] + rest
    if first in DAILY_WORDS:
        hhmm = _hhmm(rest[0]) if rest else None
        if not hhmm:
            return tr("Thiếu giờ — vd /schedule daily 08:00 <mục tiêu>")
        out.update(kind=DAILY, daily=hhmm, at=next_hhmm(hhmm, now))
        rest = rest[1:]
    elif first in QUOTA_WORDS:
        if not rest or rest[0] not in agents:
            return tr("Thiếu agent — vd /schedule quota claude <mục tiêu> · agent: {v}", v=", ".join(agents))
        out.update(kind=QUOTA, agent=rest[0])
        rest = rest[1:]
    elif DUR_RE.match(first) and first != "+":
        d, h, m = (int(x or 0) for x in DUR_RE.match(first).groups())
        secs = d * 86400 + h * 3600 + m * 60
        if not secs:
            return USAGE
        out["at"] = now + secs
    elif _hhmm(first):
        out["at"] = next_hhmm(_hhmm(first), now)
    else:
        return USAGE
    text = " ".join(rest).strip()
    flow = None
    m = re.match(r"/flow\s+(\S+)\s+(.+)", text, re.S)
    if m:
        flow, text = m.group(1), m.group(2).strip()
    if not text:
        return tr("Thiếu mục tiêu sau giờ hẹn")
    out.update(text=text, flow=flow)
    return out


def when_label(s: dict, now: float | None = None) -> str:
    """"22:30 26/10" / "hằng ngày 08:00 (lần tới 08:00 27/10)" / "khi claude hồi hạn mức"."""
    if s["kind"] == QUOTA:
        return tr("khi {agent} còn hạn mức", agent=s["agent"])
    at = time.strftime("%H:%M %d/%m", time.localtime(s["at"])) if s.get("at") else "-"
    if s["kind"] == DAILY:
        return tr("hằng ngày {hhmm} (lần tới {at})", hhmm=s["daily"], at=at)
    return at


def list_text(rows: list[dict]) -> str:
    waiting = [s for s in rows if s["status"] == "waiting"]
    if not waiting:
        return tr("Chưa có lịch nào — {usage}", usage=USAGE)
    lines = [tr("⏰ Lịch chạy (chỉ chạy khi ateam đang mở):")]
    for s in waiting:
        flow = f" [workflow {s['flow']}]" if s.get("flow") else ""
        last = tr(" · lần trước → mục tiêu #{gid}", gid=s["goal_id"]) if s.get("goal_id") else ""
        lines.append(f"  #{s['id']}  {when_label(s)}{flow}: {s['text']}{last}")
    lines.append(tr("Huỷ: /schedule rm <số>"))
    return "\n".join(lines)


def quota_blocked(items: list[dict] | None, binary: str, now: float | None = None) -> float | None:
    """Giờ hồi (epoch) nếu hạn mức 5 giờ của CLI `binary` đang cạn theo số liệu quota.py gần nhất; None = còn dùng
    được / không biết."""
    now = time.time() if now is None else now
    for item in items or []:
        if item.get("cli") != Path(binary).name:
            continue
        for w in item.get("windows") or []:
            if w.get("used", 0) >= QUOTA_FULL and w.get("resets_at") and w["resets_at"] > now:
                return float(w["resets_at"])
    return None
