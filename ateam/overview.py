"""Bản tổng quan dự án (/init): trưởng nhóm tìm hiểu dự án một lần, viết bản đồ gọn (mục đích, lệnh, thư mục →
trách nhiệm, quy ước…) vào .ateam/project.md; ateam gửi kèm prompt lập kế hoạch, /grill và mỗi task để agent khỏi
đọc lại code mỗi kế hoạch. Dòng đầu là meta `<!-- ateam:init commit=<sha> date=<ngày> -->` (commit lúc viết, để
biết file nào đã đổi từ đó); phần còn lại là markdown người dùng sửa được."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

MAX_CHARS = 12000  # phần gửi kèm prompt
MAX_CHANGED = 40  # số file đã đổi kể từ /init liệt kê trong prompt
MAX_CHANGED_INIT = 200  # … và trong prompt cập nhật của /init
MAX_STATUS = 50  # số dòng `git status` gửi khi cập nhật — prompt đi qua argv (Linux: tối đa 128 KB một đối số)
SEEN = "PROJECT OVERVIEW: unchanged since you received it earlier in this conversation."
STALE_COMMITS = 20  # từ chừng này commit mới thì nhắc chạy lại /init
META_RE = re.compile(r"^<!--\s*ateam:init\s+(.*?)\s*-->\s*\n?")


def path_for(root: Path) -> Path:
    return Path(root) / ".ateam" / "project.md"


def load(root: Path) -> tuple[str, dict]:
    """(nội dung không kèm dòng meta, {"commit", "date"}); chưa có file → ("", {})."""
    try:
        text = path_for(root).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "", {}
    meta = {}
    m = META_RE.match(text)
    if m:
        meta = dict(kv.split("=", 1) for kv in m.group(1).split() if "=" in kv)
        text = text[m.end():]
    return text.strip(), meta


def save(root: Path, text: str, commit: str = "") -> None:
    p = path_for(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(f"<!-- ateam:init commit={commit} date={time.strftime('%Y-%m-%d')} -->\n{text.strip()}\n",
                   encoding="utf-8")
    tmp.replace(p)


def _listed(items: list[str], limit: int, sep: str) -> str:
    more = f"{sep}… (+{len(items) - limit} more)" if len(items) > limit else ""
    return sep.join(items[:limit]) + more


def changes_text(commits: int | None, changed: list[str], status: str) -> str:
    """Thay đổi kể từ lần /init trước (file đã đổi qua các commit, `git status --short`) cho prompt cập nhật."""
    parts = []
    if changed:
        parts.append(f"{commits} commits; files changed: " + _listed(changed, MAX_CHANGED_INIT, ", "))
    if status.strip():
        parts.append("Uncommitted changes:\n" + _listed(status.strip().splitlines(), MAX_STATUS, "\n"))
    return "\n".join(parts)


def digest(block_text: str) -> str:
    return hashlib.sha1(block_text.encode()).hexdigest()[:12]


def block(text: str, meta: dict, changed: list[str] | None = None, commits: int | None = 0) -> str:
    """Khối PROJECT OVERVIEW đặt vào prompt (tiếng Anh như mọi prompt). Rỗng nếu chưa có bản tổng quan."""
    if not text:
        return ""
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rstrip() + "\n[… overview truncated]"
    when = f" on {meta['date']}" if meta.get("date") else ""
    out = (f"PROJECT OVERVIEW (written by the team lead with /init{when}; it may be outdated — when it disagrees "
           f"with the code, trust the code):\n{text}")
    if changed:
        out += (f"\nFiles changed since this overview was written ({commits} commits): "
                + _listed(changed, MAX_CHANGED, ", "))
    return out
