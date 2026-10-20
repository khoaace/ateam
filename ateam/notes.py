"""Ghi chú theo dự án (tab 🗒 Ghi chú của TUI và web). Lưu như to-do: ~/.config/ateam/notes/<tên>-<băm đường
dẫn>.json, ngoài repo; tag dùng chung với to-do (todos.load_tags).

Mỗi ghi chú: {id, title, body (markdown), tags (id tag), pinned, created, updated}. Ảnh chụp web chỉ gửi bản rút gọn
(summaries); nội dung đầy đủ tải khi mở. Lưu kèm `base` = updated đã đọc: file có bản mới hơn (tab / máy khác vừa
sửa) thì Conflict, để người dùng chọn tải lại hay ghi đè."""
from __future__ import annotations

import re
import time
from pathlib import Path

from . import todos

MAX_TITLE = 200
MAX_BODY = 200_000
SNIP = 120
_sums: dict = {}  # đường dẫn -> (danh sách gốc, bản rút gọn)


class Conflict(Exception):
    def __init__(self, note: dict):
        super().__init__("conflict")
        self.note = note


def path_for(root: Path) -> Path:
    return todos.path_for(root, "notes")


def load(root: Path) -> list:
    return todos.read_list(path_for(root), lambda x: isinstance(x.get("id"), int))


def save(root: Path, items: list) -> None:
    todos.write_list(path_for(root), items)


def title_of(n: dict) -> str:
    """Tiêu đề, trống thì dòng đầu của nội dung (bỏ dấu # của heading)."""
    if str(n.get("title") or "").strip():
        return str(n["title"]).strip()
    for ln in str(n.get("body") or "").splitlines():
        ln = re.sub(r"^\s*#+\s*", "", ln).strip()
        if ln:
            return ln[:80]
    return ""


def snippet(n: dict) -> str:
    """Đoạn đầu của nội dung (bỏ dòng tiêu đề trùng title, dấu markdown đầu dòng) cho danh sách."""
    head, out = title_of(n), []
    for ln in str(n.get("body") or "").splitlines():
        ln = re.sub(r"^\s*(#+|[-*+]\s+(\[[ xX]\])?|>)\s*", "", ln).strip()
        if ln and not (not out and ln == head):
            out.append(ln)
        if sum(len(x) for x in out) > SNIP:
            break
    return " ".join(out)[:SNIP]


def summaries(root: Path) -> list:
    """Bản rút gọn cho ảnh chụp web / danh sách: ghim trước, rồi sửa gần nhất."""
    items = load(root)
    hit = _sums.get(path_for(root))
    if hit and hit[0] is items:
        return hit[1]
    out = [{"id": n["id"], "title": title_of(n), "snip": snippet(n), "tags": list(n.get("tags") or []),
            "pinned": bool(n.get("pinned")), "created": n.get("created"), "updated": n.get("updated"),
            "chars": len(str(n.get("body") or ""))} for n in items]
    out.sort(key=lambda x: (not x["pinned"], -(x["updated"] or 0)))
    _sums[path_for(root)] = (items, out)
    return out


def get(root: Path, nid) -> dict | None:
    return next((dict(n) for n in load(root) if n.get("id") == todos._int(nid, -1)), None)


def apply(root: Path, action: str, d: dict):
    """add (title, body, tags) -> ghi chú mới · get (id) · save (id, title, body, tags, base) -> ghi chú đã lưu,
    Conflict nếu file có bản mới hơn base (force bỏ qua) · pin (id, on) · delete (id) · to_todo (text, id: tạo việc
    mang tag của ghi chú) -> danh sách việc."""
    items = [dict(n) for n in load(root)]
    find = [n for n in items if n.get("id") == todos._int(d.get("id"), -1)]
    now = time.time()
    if action == "get":
        return dict(find[0]) if find else None
    if action == "to_todo":
        tags = list(find[0].get("tags") or []) if find else []
        return todos.apply(root, "add", {"text": str(d.get("text") or ""), "tags": tags})
    if action == "add":
        n = {"id": todos.next_id(items), "title": str(d.get("title") or "").strip()[:MAX_TITLE],
             "body": str(d.get("body") or "")[:MAX_BODY], "tags": todos.ensure_tags(root, d.get("tags") or []),
             "pinned": False, "created": now, "updated": now}
        items.append(n)
        save(root, items)
        return dict(n)
    if not find:
        return None
    n = find[0]
    if action == "save":
        base = d.get("base")
        if not d.get("force") and base is not None and (n.get("updated") or 0) > float(base) + 1e-6:
            raise Conflict(dict(n))
        if "title" in d:
            n["title"] = str(d.get("title") or "").strip()[:MAX_TITLE]
        if "body" in d:
            n["body"] = str(d.get("body") or "")[:MAX_BODY]
        if isinstance(d.get("tags"), list):
            n["tags"] = todos.ensure_tags(root, d["tags"])
        n["updated"] = max(now, (n.get("updated") or 0) + 1e-3)
    elif action == "pin":
        n["pinned"] = bool(d.get("on", not n.get("pinned")))
    elif action == "delete":
        items.remove(n)
    else:
        return None
    save(root, items)
    return dict(n)
