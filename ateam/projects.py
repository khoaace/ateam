"""Mở folder (dự án) khác, như File › Open Folder / Open Recent của VS Code: danh sách dự án gần đây (lưu ở
state.json chung, ngoài repo), gợi ý thư mục khi gõ đường dẫn, kiểm tra thư mục đích. TUI và web mở lại chính
ateam với `-C <thư mục>` (xem cli.with_root) — mọi thứ (bảng việc, khoá phiên, cấu hình) nạp lại từ đầu."""

from __future__ import annotations

import os
from pathlib import Path

from .config import load_state, save_state
from .i18n import tr

RECENT_MAX = 20
DIRS_MAX = 50


def recent_projects() -> list[str]:
    items = load_state().get("recent_projects") or []
    return [p for p in items if isinstance(p, str)][:RECENT_MAX]


def touch_project(root: Path) -> None:
    """Dự án vừa mở lên đầu danh sách gần đây."""
    p = str(Path(root).resolve())
    state = load_state()
    state["recent_projects"] = [p] + [x for x in recent_projects() if x != p][:RECENT_MAX - 1]
    save_state(state)


def shorten(path) -> str:
    """/Users/x/code/app -> ~/code/app"""
    p, home = str(path), str(Path.home())
    return "~" + p[len(home):] if p == home or p.startswith(home + os.sep) else p


def expand(text: str, base: Path) -> Path:
    """Chữ gõ -> đường dẫn tuyệt đối (~ là thư mục nhà, đường dẫn tương đối tính từ thư mục cha của dự án
    đang mở: gõ `app-khac` là dự án nằm cạnh)."""
    p = Path(os.path.expanduser(text.strip()))
    return p if p.is_absolute() else Path(base).parent / p


def is_path(text: str) -> bool:
    return text.startswith(("/", "~", "."))


def candidates(text: str, current: Path) -> list[dict]:
    """Gợi ý cho ô "Mở folder": {"path", "label", "kind": "recent" | "dir" | "current"}.
    Gõ đường dẫn (/, ~, .) thì liệt kê thư mục con khớp; gõ chữ thường thì lọc dự án gần đây."""
    from .palette import fuzzy
    cur = str(Path(current).resolve())

    def item(p: str, kind: str) -> dict:  # name: tên thư mục, where: thư mục cha (đường dẫn dài vẫn thấy tên)
        return {"path": p, "label": shorten(p), "name": Path(p).name or p, "where": shorten(Path(p).parent),
                "kind": "current" if p == cur else kind}

    text = text.strip()
    if is_path(text):
        full = expand(text, current)
        parent, prefix = (full, "") if text.endswith(("/", os.sep)) or text in ("~", ".", "..") else \
            (full.parent, full.name)
        out = [item(str(full.resolve()), "dir")] if prefix and full.is_dir() else []
        try:
            names = sorted(e.name for e in os.scandir(parent) if e.is_dir()
                           and (not e.name.startswith(".") or prefix.startswith("."))
                           and e.name.lower().startswith(prefix.lower()) and e.name != prefix)
        except OSError:
            names = []
        return out + [item(str((parent / n).resolve()), "dir") for n in names[:DIRS_MAX]]
    recent = [p for p in recent_projects() if Path(p).is_dir()]
    if not text:
        return [item(p, "recent") for p in recent]
    # khớp mờ theo tên thư mục (khớp mờ cả đường dẫn dài thì gần như gì cũng khớp), thêm khớp liền trong đường dẫn
    hits = fuzzy(recent, text, key=lambda p: Path(p).name)
    hits += [p for p in recent if p not in hits and text.lower() in shorten(p).lower()]
    return [item(p, "recent") for p in hits]


def check_target(text: str, current: Path) -> tuple[Path | None, str]:
    """Thư mục định mở: (đường dẫn, "") hoặc (None, lý do không mở được)."""
    if not text.strip():
        return None, tr("Gõ đường dẫn thư mục, vd ~/code/app")
    p = expand(text, current)
    if not p.exists():
        return None, tr("Không có thư mục {v}", v=shorten(p))
    if not p.is_dir():
        return None, tr("{v} không phải thư mục", v=shorten(p))
    p = p.resolve()
    if p == Path(current).resolve():
        return None, tr("Đang mở dự án này rồi")
    if not os.access(p, os.W_OK):
        return None, tr("Không ghi được vào {v} (ateam cần tạo .ateam/ ở đó)", v=shorten(p))
    from .cli import ui_session_running
    if ui_session_running(p):
        return None, tr("Dự án {v} đang mở ở một phiên ateam khác", v=shorten(p))
    return p, ""
