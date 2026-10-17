"""Token & cost thật của một lượt chạy, đọc từ file phiên mà CLI tự ghi (không đổi cách chạy CLI):

- Claude Code: ~/.claude/projects/<thư mục làm việc, ký tự không phải chữ/số → "-">/<phiên>.jsonl — mỗi dòng
  `assistant` có `message.usage` (input/output/cache) và `message.model`; một tin nhắn có thể nằm ở nhiều dòng
  cùng `message.id` (mỗi khối nội dung một dòng) → chỉ tính một lần.
- Codex: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl — `session_meta.payload.cwd`, `turn_context.payload.model`,
  `event_msg` `token_count` có `info.total_token_usage` cộng dồn cả phiên (lấy cái cuối).

Lượt chạy được ghép với file phiên theo thư mục làm việc + khoảng thời gian, và đầu prompt (khi nhiều phiên cùng
chạy trong một thư mục). Agent khác (agy, grok, opencode…) hoặc không tìm thấy → None (bên gọi ước tính).
Cost = token × bảng giá công khai (USD / 1 triệu token), ghi đè bằng [prices."<model>"] trong config.toml."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SLACK = 5.0  # giây: đồng hồ CLI và ateam lệch nhau / CLI ghi file trễ


@dataclass
class Usage:
    in_tok: int = 0       # input không tính phần đọc từ cache
    out_tok: int = 0
    cache_read: int = 0
    cache_write: int = 0
    model: str = ""

    @property
    def total(self) -> int:
        return self.in_tok + self.out_tok + self.cache_read + self.cache_write


def claude_projects() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"


def codex_sessions() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"


def encode_dir(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def _ts(s) -> float:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _norm(s: str) -> str:
    return " ".join(str(s or "").split())[:160]


def _same_prompt(prompt: str, text: str) -> bool:
    a, b = _norm(prompt), _norm(text)
    if not a or not b:
        return False
    n = min(len(a), len(b), 120)
    return a[:n] == b[:n]


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
    return ""


def _lines(path: Path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def _dirs(cwd: str) -> list[str]:
    out = [cwd]
    try:
        real = str(Path(cwd).resolve())  # macOS: /tmp → /private/tmp
        if real != cwd:
            out.append(real)
    except OSError:
        pass
    return out


def claude_usage(cwd: str, started: float, finished: float, prompt: str,
                 session: str | None = None) -> Usage | None:
    root = claude_projects()
    files = []
    for d in {encode_dir(p) for p in _dirs(cwd)}:
        folder = root / d
        if folder.is_dir():
            files += [f for f in folder.glob("*.jsonl") if f.stat().st_mtime >= started - SLACK]
    if session and any(f.stem == session for f in files):
        files = [f for f in files if f.stem == session]  # biết id phiên (file <id>.jsonl): khỏi đoán theo prompt
    found: list[tuple[bool, Usage]] = []
    for f in files:
        first_user, msgs, model = None, {}, ""
        for d in _lines(f):
            ts = _ts(d.get("timestamp"))
            if d.get("type") == "user" and first_user is None:
                first_user = _text_of((d.get("message") or {}).get("content"))
            if d.get("type") != "assistant" or not (started - SLACK <= ts <= finished + SLACK):
                continue
            m = d.get("message") or {}
            u = m.get("usage") or {}
            if not u:
                continue
            msgs[m.get("id") or d.get("uuid")] = u  # nhiều dòng cùng message.id: dùng dòng cuối
            model = m.get("model") or model
        if not msgs:
            continue
        us = Usage(model=model)
        for u in msgs.values():
            us.in_tok += int(u.get("input_tokens") or 0)
            us.out_tok += int(u.get("output_tokens") or 0)
            us.cache_read += int(u.get("cache_read_input_tokens") or 0)
            us.cache_write += int(u.get("cache_creation_input_tokens") or 0)
        found.append((f.stem == session or _same_prompt(prompt, first_user or ""), us))
    return _pick(found)


def _pick(found: list) -> Usage | None:
    """Phiên khớp prompt; không phiên nào khớp mà chỉ có đúng một phiên trong khoảng thời gian thì lấy nó."""
    match = [u for ok, u in found if ok]
    if match:
        return match[0]
    return found[0][1] if len(found) == 1 else None


def codex_usage(cwd: str, started: float, finished: float, prompt: str,
                session: str | None = None) -> Usage | None:
    root = codex_sessions()
    days = {time.strftime("%Y/%m/%d", time.localtime(t)) for t in (started - 86400, started, finished)}
    days |= {time.strftime("%Y/%m/%d", time.gmtime(t)) for t in (started, finished)}
    dirs = set(_dirs(cwd))
    found: list[tuple[bool, Usage]] = []
    if session:  # biết id phiên: file rollout-<thời điểm>-<id>.jsonl, có thể ở ngày cũ (lượt --resume)
        files = list(root.glob(f"*/*/*/*{session}*.jsonl"))
    else:
        files = [f for day in days if (root / day).is_dir() for f in (root / day).glob("*.jsonl")]
    for f in files:
        try:
            if f.stat().st_mtime < started - SLACK:
                continue
        except OSError:
            continue
        us, total, before, user, ok_dir, t0 = Usage(), None, None, None, False, 0.0
        for d in _lines(f):
            p = d.get("payload") or {}
            kind = d.get("type")
            if kind == "session_meta":
                ok_dir = p.get("cwd") in dirs
                t0 = _ts(p.get("timestamp") or d.get("timestamp"))
                if not ok_dir:
                    break
            elif kind == "turn_context":
                us.model = p.get("model") or us.model
            elif kind == "event_msg" and p.get("type") == "user_message" and user is None:
                user = p.get("message") or ""
            elif kind == "event_msg" and p.get("type") == "token_count" and (p.get("info") or {}).get(
                    "total_token_usage"):
                if _ts(d.get("timestamp")) < started - SLACK:
                    before = p["info"]["total_token_usage"]  # cộng dồn của các lượt trước (phiên tiếp tục)
                else:
                    total = p["info"]["total_token_usage"]
        if not ok_dir or total is None or not (session or started - 60 <= t0 <= finished + SLACK):
            continue

        def n(key: str) -> int:
            return int(total.get(key) or 0) - int((before or {}).get(key) or 0)
        cached = n("cached_input_tokens")
        us.in_tok = max(0, n("input_tokens") - cached)
        us.cache_read = max(0, cached)
        us.out_tok = max(0, n("output_tokens"))
        found.append((bool(session) or _same_prompt(prompt, user or ""), us))
    return _pick(found)


def collect(binary: str, cwd: str, started: float, finished: float, prompt: str,
            session: str | None = None) -> Usage | None:
    """Token thật của một lượt chạy CLI `binary` trong thư mục `cwd`, hoặc None nếu không đọc được.
    session: id phiên (khi biết) — chọn đúng file phiên, cả khi lượt này tiếp tục phiên cũ (--resume)."""
    name = Path(binary or "").name
    try:
        if name == "claude":
            return claude_usage(cwd, started, finished, prompt, session)
        if name == "codex":
            return codex_usage(cwd, started, finished, prompt, session)
    except Exception:  # file phiên hỏng / định dạng đổi: coi như không có
        return None
    return None


# ------------------------------------------------------------------ bảng giá (USD / 1 triệu token)
# (chuỗi con của tên model, input, output, đọc cache, ghi cache) — khớp cái đầu tiên, nên để tên cụ thể trước.
# Ước tính theo bảng giá công khai; model không có trong bảng → không tính cost (hiện "—").
PRICES: list[tuple[str, float, float, float, float]] = [
    ("claude-3-opus", 15, 75, 1.5, 18.75), ("opus-4-1", 15, 75, 1.5, 18.75), ("opus-4-0", 15, 75, 1.5, 18.75),
    ("opus-4-2025", 15, 75, 1.5, 18.75), ("opus", 5, 25, 0.5, 6.25),
    ("sonnet", 3, 15, 0.3, 3.75),
    ("haiku-3-5", 0.8, 4, 0.08, 1), ("3-5-haiku", 0.8, 4, 0.08, 1), ("haiku", 1, 5, 0.1, 1.25),
    ("gpt-5-nano", 0.05, 0.4, 0.005, 0), ("gpt-5-mini", 0.25, 2, 0.025, 0), ("gpt-5", 1.25, 10, 0.125, 0),
    ("gpt-4.1-mini", 0.4, 1.6, 0.1, 0), ("gpt-4.1", 2, 8, 0.5, 0), ("o4-mini", 1.1, 4.4, 0.275, 0),
    ("o3", 2, 8, 0.5, 0),
]


def price_of(model: str, overrides: dict | None = None) -> tuple[float, float, float, float] | None:
    m = (model or "").lower()
    if not m:
        return None
    for key, p in (overrides or {}).items():  # [prices."<model>"] input/output/cache_read/cache_write
        if key.lower() in m and isinstance(p, dict) and "input" in p and "output" in p:
            i, o = float(p["input"]), float(p["output"])
            return i, o, float(p.get("cache_read", i * 0.1)), float(p.get("cache_write", i * 1.25))
    for key, i, o, cr, cw in PRICES:
        if key in m:
            return i, o, cr, cw
    return None


def cost_of(u: Usage, overrides: dict | None = None) -> float | None:
    p = price_of(u.model, overrides)
    if not p:
        return None
    i, o, cr, cw = p
    return (u.in_tok * i + u.out_tok * o + u.cache_read * cr + u.cache_write * cw) / 1e6
