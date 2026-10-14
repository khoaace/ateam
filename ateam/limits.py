"""Phát hiện agent hết hạn mức (rate limit / usage limit) và đoán lúc hạn mức hồi lại."""

from __future__ import annotations

import datetime as dt
import re
import time

from .config import load_state, save_state

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
