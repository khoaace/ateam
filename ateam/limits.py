"""Phát hiện agent hết hạn mức (rate limit / usage limit) và đoán lúc hạn mức hồi lại."""

from __future__ import annotations

import datetime as dt
import re
import time

from .config import load_state, save_state
from .i18n import tr

LIMIT_RE = re.compile(
    r"rate[ _-]?limit|usage[ _-]?limit|quota|too many requests|\b429\b|limit (?:reached|exceeded)"
    r"|resource[_ ]exhausted|out of (?:credits|usage)|hit (?:your|the) (?:usage )?limit"
    r"|(?:have|'ve) reached (?:your|the)|credit balance is too low|weekly limit|session limit",
    re.I)
IN_RE = re.compile(r"(?:try again|retry|resets?|available again)\s+in\s+(?:about\s+)?(\d+)\s*"
                   r"(s|sec|second|m|min|minute|h|hr|hour)s?\b", re.I)
AT_RE = re.compile(r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I)
EPOCH_RE = re.compile(r"\|(\d{10})\b")


def looks_rate_limited(output: str, rc: int) -> bool:
    """Chỉ xét khi agent thất bại hoặc in rất ít — tránh nhầm với code có chữ 'rate limit'."""
    lines = [l for l in output.splitlines() if l.strip()]
    if rc == 0 and len(lines) > 15:
        return False
    return bool(LIMIT_RE.search("\n".join(lines[-30:])))


def reset_time(output: str, default_minutes: int, now: float | None = None) -> float:
    now = now or time.time()
    tail = "\n".join(output.splitlines()[-30:])
    m = EPOCH_RE.search(tail)
    if m and now < int(m.group(1)) < now + 8 * 86400:
        return float(m.group(1))
    m = IN_RE.search(tail)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        mult = 1 if unit.startswith("s") else 3600 if unit.startswith("h") else 60
        return now + n * mult + 30
    m = AT_RE.search(tail)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        if 0 <= h < 24 and 0 <= mi < 60:
            base = dt.datetime.fromtimestamp(now)
            cand = base.replace(hour=h, minute=mi, second=0, microsecond=0)
            if cand.timestamp() <= now:
                cand += dt.timedelta(days=1)
            return cand.timestamp() + 30
    return now + default_minutes * 60


# ---------------------------------------------------------------- lưu trạng thái tạm nghỉ (chung mọi dự án)
def load_cooldowns() -> dict[str, float]:
    now = time.time()
    return {a: float(t) for a, t in (load_state().get("cooldown") or {}).items() if float(t) > now}


def save_cooldown(agent: str, until: float | None) -> None:
    st = load_state()
    cd = {a: t for a, t in (st.get("cooldown") or {}).items() if float(t) > time.time()}
    if until is None:
        cd.pop(agent, None)
    else:
        cd[agent] = until
    st["cooldown"] = cd
    save_state(st)


def _window(minutes) -> str:
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        return "?"
    if m % 10080 == 0:
        return tr("{v} tuần", v=m // 10080) if m > 10080 else tr("tuần")
    if m % 1440 == 0:
        return tr("{v} ngày", v=m // 1440)
    if m % 60 == 0:
        return tr("{v} giờ", v=m // 60)
    return tr("{m} phút", m=m)


def codex_rate_limits(home=None, max_files: int = 30) -> list[str] | None:
    """Hạn mức Codex lấy từ ảnh chụp `rate_limits` mà codex ghi vào file phiên (sự kiện token_count) —
    codex không có lệnh headless nào in hạn mức mà không gọi model. None nếu chưa có phiên nào."""
    import json
    import os
    from pathlib import Path
    root = Path(home or os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
    try:
        files = sorted(root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]
    except OSError:
        return None
    for f in files:
        snap, when = None, None
        try:
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if '"rate_limits"' not in line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                rl = (ev.get("payload") or {}).get("rate_limits")
                if isinstance(rl, dict):
                    snap, when = rl, ev.get("timestamp")
        except OSError:
            continue
        if not snap:
            continue
        out = []
        if snap.get("plan_type"):
            out.append(tr("Gói: {v}", v=snap['plan_type']))
        for key, label in (("primary", tr("Hạn mức chính")), ("secondary", tr("Hạn mức phụ"))):
            w = snap.get(key)
            if not isinstance(w, dict):
                continue
            used = w.get("used_percent")
            line = tr("{label} ({v}): đã dùng {used:g}%", label=label, v=_window(w.get('window_minutes')), used=used) if isinstance(
                used, (int, float)) else f"{label}: ?"
            if w.get("resets_at"):
                line += tr(" · hồi lúc ") + time.strftime("%H:%M %d/%m", time.localtime(int(w["resets_at"])))
            out.append(line)
        cr = snap.get("credits")
        if isinstance(cr, dict) and (cr.get("has_credits") or cr.get("unlimited")):
            out.append("Credits: " + (tr("không giới hạn") if cr.get("unlimited") else str(cr.get("balance"))))
        if snap.get("rate_limit_reached_type"):
            out.append(tr("⚠ Đang chạm hạn mức: {v}", v=snap['rate_limit_reached_type']))
        if when:
            try:
                t = dt.datetime.fromisoformat(str(when).replace("Z", "+00:00")).timestamp()
                out.append(tr("(số liệu lúc ") + time.strftime("%H:%M %d/%m", time.localtime(t))
                           + tr(" — lần chạy codex gần nhất)"))
            except ValueError:
                pass
        return out
    return None
