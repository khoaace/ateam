"""Tab Code của giao diện web: cây thư mục, đọc/ghi file (`editor.read_source/save_source`).

Mọi đường dẫn là tương đối với gốc dự án; đường ra ngoài dự án (`..`, đường tuyệt đối, symlink trỏ ra ngoài)
và thư mục `.git` bị từ chối. Ghi file kèm mtime lúc mở để phát hiện file đã đổi trên đĩa (agent vừa sửa).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

from . import editor
from .i18n import tr

if TYPE_CHECKING:
    from .web import WebApp


def safe_path(root: Path, rel: str) -> Path | None:
    """Đường dẫn trong dự án, hoặc None nếu ra ngoài / vào .git."""
    rel = (rel or "").strip().lstrip("@").strip('"').strip("'")
    if not rel or "\0" in rel:
        return None
    root = root.resolve()
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        return None
    if ".git" in p.relative_to(root).parts:
        return None
    return p


def children(entries: list[str], d: str) -> list[dict]:
    """Con trực tiếp của thư mục d ("" = gốc) từ danh sách phẳng của FileIndex ("a/", "a/b.py"…):
    thư mục trước, rồi file, theo tên."""
    pre = d.rstrip("/") + "/" if d else ""
    dirs, files = [], []
    for e in entries:
        if not e.startswith(pre) or e == pre:
            continue
        rest = e[len(pre):]
        if rest.endswith("/") and "/" not in rest[:-1]:
            dirs.append({"name": rest[:-1], "path": e[:-1], "dir": True})
        elif "/" not in rest:
            files.append({"name": rest, "path": e, "dir": False})
    key = (lambda x: x["name"].lower())
    return sorted(dirs, key=key) + sorted(files, key=key)


class CodeWeb:
    def __init__(self, app: "WebApp"):
        self.app = app

    def routes(self) -> list:
        return [web.get("/api/tree", self.api_tree), web.get("/api/file", self.api_file),
                web.get("/api/file/stat", self.api_stat)]

    async def api_tree(self, r: web.Request) -> web.Response:
        idx = self.app.index
        if r.query.get("refresh") or idx.stale():
            await idx.refresh()
        return web.json_response(children(idx.entries, r.query.get("dir", "")))

    async def api_file(self, r: web.Request) -> web.Response:
        rel = r.query.get("path", "")
        p = safe_path(self.app.root, rel)
        if p is None:
            return web.json_response({"error": tr("Đường dẫn không hợp lệ (ngoài dự án): {path}", path=rel)})
        if p.is_dir():
            return web.json_response({"error": tr("{path} là thư mục", path=rel), "dir": True})
        sf = editor.read_source(p)
        if sf.error:
            return web.json_response({"error": sf.error})
        return web.json_response({
            "path": p.relative_to(self.app.root.resolve()).as_posix(), "text": sf.text, "mtime": sf.mtime,
            "newline": sf.newline, "read_only": sf.read_only, "note": sf.note, "size": sf.size,
            "new": not sf.mtime, "language": editor.language_name(p) if sf.mtime else ""})

    async def api_stat(self, r: web.Request) -> web.Response:
        p = safe_path(self.app.root, r.query.get("path", ""))
        return web.json_response({"mtime": editor.disk_mtime(p) if p else 0.0})

    def save(self, d: dict) -> tuple:
        """{"path", "text", "mtime" (lúc mở; 0 = file mới), "force"} → ghi; xung đột → ("…", "warn", {conflict})."""
        rel = str(d.get("path") or "")
        p = safe_path(self.app.root, rel)
        if p is None:
            return tr("Đường dẫn không hợp lệ (ngoài dự án): {path}", path=rel), "error"
        sf = editor.read_source(p)  # lấy kiểu xuống dòng / mã hoá hiện tại của file
        if sf.error:
            return sf.error, "error"
        force = bool(d.get("force"))
        if sf.read_only and not force:
            return tr("Chỉ đọc ({note}) — :w! để vẫn ghi", note=sf.note), "warn", {"save": {"path": rel,
                                                                                       "read_only": True}}
        sf.mtime = float(d.get("mtime") or 0)  # so với lúc trình duyệt mở file
        res = editor.save_source(sf, str(d.get("text") or ""), force=force)
        if res == "conflict":
            return tr("File đã đổi trên đĩa (có thể do agent sửa)"), "warn", {"save": {"path": rel, "conflict": True}}
        if res:
            return res, "error"
        n = str(d.get("text") or "").count("\n") + 1
        self.app.index.loaded_at = 0  # file mới hiện ngay trong cây
        return tr("Đã lưu {path} · {n} dòng", path=rel, n=n), "ok", {"save": {"path": rel, "mtime": sf.mtime}}
