"""Tab Code của giao diện web: cây thư mục, đọc/ghi file (`editor.read_source/save_source`).

Mọi đường dẫn là tương đối với gốc dự án; đường ra ngoài dự án (`..`, đường tuyệt đối, symlink trỏ ra ngoài)
và thư mục `.git` bị từ chối. Ghi file kèm mtime lúc mở để phát hiện file đã đổi trên đĩa (agent vừa sửa).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

from . import editor, palette, search
from .i18n import tr
from .palette import safe_path

if TYPE_CHECKING:
    from .web import WebApp


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
                web.get("/api/file/stat", self.api_stat), web.get("/api/symbols", self.api_symbols),
                web.get("/api/recent", self.api_recent)]

    async def api_tree(self, r: web.Request) -> web.Response:
        """?refresh=1: quét lại ngay (⟳); ?age=5: quét lại nếu danh sách cũ hơn 5 giây (tab Code hỏi định kỳ để
        thấy file agent vừa tạo — nhanh hơn TTL mặc định của FileIndex)."""
        idx = self.app.index
        try:
            age = float(r.query.get("age") or idx.ttl)
        except ValueError:
            age = idx.ttl
        if r.query.get("refresh") or idx.stale() or time.time() - idx.loaded_at > max(age, 2.0):
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
        rel = p.relative_to(self.app.root.resolve()).as_posix()
        if sf.mtime and not r.query.get("quiet"):  # mở file (không phải nạp lại): vào danh sách gần đây
            palette.touch_recent(self.app.root, rel)
        return web.json_response({
            "path": rel, "text": sf.text, "mtime": sf.mtime,
            "newline": sf.newline, "read_only": sf.read_only, "note": sf.note, "size": sf.size,
            "new": not sf.mtime, "language": editor.language_name(p) if sf.mtime else ""})

    async def api_symbols(self, r: web.Request) -> web.Response:
        """Hàm / class / heading của file (palette `@`, thanh "đang ở đâu")."""
        p = safe_path(self.app.root, r.query.get("path", ""))
        if p is None or not p.is_file():
            return web.json_response([])
        sf = await asyncio.to_thread(editor.read_source, p)
        return web.json_response([] if sf.error else await asyncio.to_thread(palette.symbols, p, sf.text))

    async def api_recent(self, r: web.Request) -> web.Response:
        root = self.app.root
        return web.json_response([f for f in palette.recent_files(root) if (root / f).is_file()])

    async def file_op(self, op: str, d: dict) -> tuple | None:
        """Thao tác file của palette: file_new {path}, file_rename {path, to}, file_delete {path}, open_vscode
        {path, line}."""
        root, path = self.app.root, str(d.get("path") or "")
        if op == "file_new":
            err = palette.file_new(root, path)
        elif op == "file_rename":
            err = palette.file_rename(root, path, str(d.get("to") or ""))
        elif op == "file_delete":
            err = await palette.file_trash(root, path)
        else:  # open_vscode: chỉ khi dùng trên chính máy này (từ xa thì VS Code mở ở máy chủ, vô nghĩa)
            p = safe_path(root, path)
            if self.app.remote.enabled or p is None:
                return tr("Chỉ mở VS Code được khi dùng ateam web trên chính máy này"), "warn"
            import shutil
            if not shutil.which("code"):
                return tr("Không thấy lệnh 'code' — trong VS Code: Shell Command: Install 'code' command"), "warn"
            await asyncio.create_subprocess_exec("code", "-g", f"{p}:{int(d.get('line') or 1)}",
                                                 stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                                                 stderr=asyncio.subprocess.DEVNULL)
            return None
        if err:
            return err, "warn"
        self.app.index.loaded_at = 0  # cây file / Ctrl+P thấy ngay file mới / tên mới
        return "", "ok", {"ok": True}

    async def api_stat(self, r: web.Request) -> web.Response:
        """?path=a → {"mtime"}; ?p=a&p=b (mọi tab đang mở) → {"mtimes": {a: …, b: …}} (0 = không còn file)."""
        many = r.query.getall("p", [])
        if many:
            out = {}
            for rel in many[:50]:
                p = safe_path(self.app.root, rel)
                out[rel] = editor.disk_mtime(p) if p else 0.0
            return web.json_response({"mtimes": out})
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
