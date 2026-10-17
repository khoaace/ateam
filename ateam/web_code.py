"""Tab Code của giao diện web: cây thư mục, đọc/ghi file (`editor.read_source/save_source`).

Mọi đường dẫn là tương đối với gốc dự án; đường ra ngoài dự án (`..`, đường tuyệt đối, symlink trỏ ra ngoài)
và thư mục `.git` bị từ chối. Ghi file kèm mtime lúc mở để phát hiện file đã đổi trên đĩa (agent vừa sửa).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

from . import editor, search
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

    @staticmethod
    def _opts(d: dict) -> dict:
        return {"regex": bool(d.get("regex")), "case": bool(d.get("case")), "word": bool(d.get("word"))}

    async def search(self, d: dict) -> tuple:
        """🔍 Tìm trong toàn dự án (⌘⇧F): {"query", "regex", "case", "word", "include", "exclude", "replace"?}."""
        q = str(d.get("query") or "")
        if not q:
            return "", "", {"search": {"files": [], "total": 0, "truncated": False}}
        idx = self.app.index
        if idx.stale():
            await idx.refresh()
        rep = d.get("replace")
        try:
            res = await asyncio.get_running_loop().run_in_executor(None, lambda: search.search(
                self.app.root, list(idx.entries), q, include=str(d.get("include") or ""),
                exclude=str(d.get("exclude") or ""), replace=None if rep is None else str(rep), **self._opts(d)))
        except ValueError as e:
            return "", "", {"search": {"error": tr("Regex không hợp lệ: {e}", e=e)}}
        return "", "", {"search": res}

    async def replace(self, d: dict) -> tuple:
        """Thay trong các file đang hiện ở kết quả (trình duyệt gửi danh sách, đã bỏ file đang sửa dở)."""
        q = str(d.get("query") or "")
        files = [str(f) for f in d.get("files") or []]
        if not q or not files:
            return tr("Không có gì để thay"), "warn"
        root = self.app.root.resolve()
        rels = [p.relative_to(root).as_posix() for p in (safe_path(self.app.root, f) for f in files) if p and p.is_file()]
        try:
            res = await asyncio.get_running_loop().run_in_executor(None, lambda: search.replace_in(
                root, rels, q, str(d.get("replacement") or ""), **self._opts(d)))
        except ValueError as e:
            return tr("Regex không hợp lệ: {e}", e=e), "error"
        except OSError as e:
            return tr("Không ghi được file: {e}", e=e), "error"
        self.app.orch.log(tr("🔍 Thay \"{q}\" → \"{r}\": {n} chỗ trong {f} file", q=q, r=d.get("replacement") or "",
                             n=res["total"], f=len(res["files"])))
        return (tr("Đã thay {n} kết quả trong {f} file", n=res["total"], f=len(res["files"])), "ok",
                {"replaced": res})

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
