"""To-do list theo dự án (tab ✅ To-do của web). Lưu ngoài repo — ~/.config/ateam/todos/<tên>-<băm đường dẫn>.json —
để không phải thêm gì vào .gitignore và không lẫn vào commit. Mỗi việc: {id, text, done, created}."""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from . import config

MAX_TEXT = 500
_cache: dict = {}  # đường dẫn file -> (mtime, danh sách): ảnh chụp web đọc mỗi 0,5 giây


def path_for(root: Path) -> Path:
    root = Path(root).resolve()
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", root.name).strip("-") or "root"
    return config.GLOBAL_DIR / "todos" / f"{slug}-{hashlib.sha1(str(root).encode()).hexdigest()[:10]}.json"


def load(root: Path) -> list:
    p = path_for(root)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return []
    hit = _cache.get(p)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        items = [x for x in json.loads(p.read_text(encoding="utf-8")) if isinstance(x, dict) and x.get("text")]
    except (OSError, ValueError, TypeError):
        items = []
    _cache[p] = (mtime, items)
    return items


def save(root: Path, items: list) -> None:
    p = path_for(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    _cache.pop(p, None)


def apply(root: Path, action: str, d: dict) -> list:
    """Một thao tác: add (text) · toggle/edit (id, text) · delete (id) · clear (bỏ việc đã xong) · move (id, to)."""
    items = [dict(x) for x in load(root)]
    text = str(d.get("text") or "").strip()[:MAX_TEXT]
    find = [x for x in items if x.get("id") == d.get("id")]
    if action == "add":
        if not text:
            raise ValueError("empty")
        items.append({"id": max([x.get("id", 0) for x in items] + [0]) + 1, "text": text, "done": False,
                      "created": time.time()})
    elif action == "toggle" and find:
        find[0]["done"] = not find[0].get("done")
    elif action == "edit" and find and text:
        find[0]["text"] = text
    elif action == "delete" and find:
        items.remove(find[0])
    elif action == "clear":
        items = [x for x in items if not x.get("done")]
    elif action == "move" and find:
        items.remove(find[0])
        to = max(0, min(int(d.get("to") or 0), len(items)))
        items.insert(to, find[0])
    else:
        return items
    save(root, items)
    return items
