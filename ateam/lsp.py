"""Language server cho tab 📝 Code (TUI + web): đi tới định nghĩa / tìm chỗ dùng chính xác bằng LSP khi máy có sẵn
server của ngôn ngữ (pyright, typescript-language-server, gopls, rust-analyzer, clangd…). Không có server thì giao diện
dùng cách cũ: tìm symbol theo tên (palette.workspace_symbols). Mỗi server một tiến trình con cho cả dự án, mở khi cần
lần đầu, chạy qua asyncio (không treo vòng lặp), tắt khi đóng app."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from .i18n import tr

# (khoá, đuôi file, languageId theo đuôi, các lệnh thử lần lượt)
SERVERS: list[tuple[str, tuple[str, ...], dict[str, str], list[list[str]]]] = [
    ("python", (".py", ".pyi"), {}, [["pyright-langserver", "--stdio"], ["basedpyright-langserver", "--stdio"],
                                      ["pylsp"], ["jedi-language-server"]]),
    ("ts", (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"),
     {".ts": "typescript", ".mts": "typescript", ".cts": "typescript", ".tsx": "typescriptreact",
      ".jsx": "javascriptreact"}, [["typescript-language-server", "--stdio"]]),
    ("go", (".go",), {}, [["gopls"]]),
    ("rust", (".rs",), {}, [["rust-analyzer"]]),
    ("c", (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh"), {".c": "c", ".h": "c"}, [["clangd"]]),
]
LANG_IDS = {"python": "python", "ts": "javascript", "go": "go", "rust": "rust", "c": "cpp"}
START_TIMEOUT = 30.0  # initialize (pyright đọc cấu hình, tsserver nạp dự án)
REQUEST_TIMEOUT = 20.0
MAX_RESULTS = 500


def server_for(root: Path, path: Path) -> tuple[str, list[str]] | None:
    """(khoá, argv) của server cho file, None nếu máy không có server nào cho ngôn ngữ đó. Ưu tiên bản cài trong dự án
    (node_modules/.bin, .venv/bin) rồi PATH."""
    ext = path.suffix.lower()
    for key, exts, _ids, cands in SERVERS:
        if ext not in exts:
            continue
        for argv in cands:
            for d in (root / "node_modules" / ".bin", root / ".venv" / "bin", root / "venv" / "bin"):
                local = d / argv[0]
                if local.is_file() and os.access(local, os.X_OK):
                    return key, [str(local)] + argv[1:]
            exe = shutil.which(argv[0])
            if exe:
                return key, [exe] + argv[1:]
        return None
    return None


def tsserver_path(root: Path, argv: list[str]) -> str | None:
    """tsserver.js cho typescript-language-server khi dự án không cài typescript: bản cài toàn cục cạnh server hoặc
    cạnh `tsc` trên PATH (server không tự tìm bản toàn cục)."""
    if (root / "node_modules" / "typescript" / "lib" / "tsserver.js").is_file():
        return None
    cands = []
    real = Path(os.path.realpath(argv[0]))
    for parent in real.parents:
        if parent.name == "node_modules":
            cands.append(parent / "typescript" / "lib" / "tsserver.js")
            break
    tsc = shutil.which("tsc")
    if tsc:
        cands.append(Path(os.path.realpath(tsc)).parent.parent / "lib" / "tsserver.js")
    return next((str(c) for c in cands if c.is_file()), None)


def language_id(key: str, path: Path) -> str:
    for k, _exts, ids, _c in SERVERS:
        if k == key:
            return ids.get(path.suffix.lower(), LANG_IDS[key])
    return key


def utf16_col(line: str, col: int) -> int:
    """Cột theo ký tự Python → cột UTF-16 (đơn vị LSP mặc định; emoji = 2)."""
    return len(line[:col].encode("utf-16-le")) // 2


def py_col(line: str, col16: int) -> int:
    """Ngược lại utf16_col."""
    b = line.encode("utf-16-le")[:col16 * 2]
    return len(b.decode("utf-16-le", "ignore"))


def uri_to_path(uri: str) -> Path | None:
    u = urlparse(uri)
    return Path(unquote(u.path)) if u.scheme == "file" else None


class LspError(Exception):
    pass


class Client:
    """Một language server (JSON-RPC qua stdin/stdout)."""

    def __init__(self, root: Path, key: str, argv: list[str]):
        self.root, self.key, self.argv = root, key, argv
        self.proc: asyncio.subprocess.Process | None = None
        self._seq = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._docs: dict[str, tuple[int, str]] = {}  # uri -> (version, text) đã gửi
        self._reader: asyncio.Task | None = None
        self._ready: asyncio.Future | None = None
        self.error = ""

    async def start(self) -> None:
        if self._ready is None:
            self._ready = asyncio.get_running_loop().create_future()
            asyncio.get_running_loop().create_task(self._start())
        await asyncio.wait_for(asyncio.shield(self._ready), START_TIMEOUT)
        if self.error:
            raise LspError(self.error)

    async def _start(self) -> None:
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *self.argv, cwd=str(self.root), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, start_new_session=True)
            self._reader = asyncio.get_running_loop().create_task(self._read())
            await self._request("initialize", {
                "processId": os.getpid(), "rootUri": self.root.as_uri(), "rootPath": str(self.root),
                "workspaceFolders": [{"uri": self.root.as_uri(), "name": self.root.name}],
                "capabilities": {"textDocument": {"definition": {"linkSupport": True}, "references": {},
                                                  "synchronization": {"didSave": False}},
                                 "workspace": {"configuration": True, "workspaceFolders": True}},
                "clientInfo": {"name": "ateam"}, **self._init_options()}, START_TIMEOUT)
            self._notify("initialized", {})
        except Exception as e:  # không chạy được / không trả lời: ghi lỗi, lần sau giao diện dùng cách cũ
            self.error = tr("{v} không khởi động được: {e}", v=Path(self.argv[0]).name, e=e or type(e).__name__)
            await self.close()
        if self._ready and not self._ready.done():
            self._ready.set_result(None)

    def _init_options(self) -> dict:
        if self.key == "ts":
            ts = tsserver_path(self.root, self.argv)
            if ts:
                return {"initializationOptions": {"tsserver": {"path": ts}}}
        return {}

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None and not self.error

    def _send(self, msg: dict) -> None:
        if not self.proc or not self.proc.stdin or self.proc.stdin.is_closing():
            raise LspError(tr("language server đã dừng"))
        body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)

    def _notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _request(self, method: str, params: dict, timeout: float = REQUEST_TIMEOUT):
        self._seq += 1
        rid = self._seq
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            raise LspError(tr("{v} không trả lời sau {n} giây", v=Path(self.argv[0]).name, n=int(timeout)))
        finally:
            self._pending.pop(rid, None)

    async def _read(self) -> None:
        out = self.proc.stdout
        try:
            while True:
                head = await out.readuntil(b"\r\n\r\n")
                n = next((int(ln.split(b":", 1)[1]) for ln in head.split(b"\r\n")
                          if ln.lower().startswith(b"content-length:")), 0)
                msg = json.loads(await out.readexactly(n)) if n else {}
                if "method" in msg and "id" in msg:  # server hỏi client: trả lời rỗng cho đủ giao thức
                    res = None
                    if msg["method"] == "workspace/configuration":
                        res = [None] * len((msg.get("params") or {}).get("items") or [])
                    elif msg["method"] == "workspace/workspaceFolders":
                        res = [{"uri": self.root.as_uri(), "name": self.root.name}]
                    self._send({"jsonrpc": "2.0", "id": msg["id"], "result": res})
                elif "id" in msg and msg["id"] in self._pending:
                    fut = self._pending[msg["id"]]
                    if not fut.done():
                        if "error" in msg:
                            fut.set_exception(LspError(str((msg["error"] or {}).get("message") or msg["error"])))
                        else:
                            fut.set_result(msg.get("result"))
        except (asyncio.IncompleteReadError, ConnectionError, ValueError, LspError, asyncio.LimitOverrunError):
            pass
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(LspError(tr("language server đã dừng")))

    def _sync(self, path: Path, text: str) -> str:
        uri = path.as_uri()
        cur = self._docs.get(uri)
        if cur is None:
            self._notify("textDocument/didOpen", {"textDocument": {
                "uri": uri, "languageId": language_id(self.key, path), "version": 1, "text": text}})
            self._docs[uri] = (1, text)
        elif cur[1] != text:
            v = cur[0] + 1
            self._notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": v},
                                                    "contentChanges": [{"text": text}]})
            self._docs[uri] = (v, text)
        return uri

    async def locations(self, method: str, path: Path, text: str, line: int, col16: int) -> list[dict]:
        """definition / references tại (dòng từ 0, cột UTF-16) → [{"path": Path, "line" (từ 0), "col16"}]."""
        await self.start()
        uri = self._sync(path, text)
        params: dict = {"textDocument": {"uri": uri}, "position": {"line": line, "character": col16}}
        if method == "textDocument/references":
            params["context"] = {"includeDeclaration": False}
        res = await self._request(method, params)
        items = res if isinstance(res, list) else [res] if res else []
        out = []
        for it in items[:MAX_RESULTS]:
            u = it.get("targetUri") or it.get("uri")
            rng = it.get("targetSelectionRange") or it.get("range") or {}
            p = uri_to_path(u or "")
            if p is None:
                continue
            start = rng.get("start") or {}
            out.append({"path": p, "line": int(start.get("line", 0)), "col16": int(start.get("character", 0))})
        return out

    async def close(self) -> None:
        p = self.proc
        if p and p.returncode is None:
            try:
                if not self.error:
                    await asyncio.wait_for(self._request("shutdown", {}, 3), 3)
                    self._notify("exit", {})
            except Exception:
                pass
            try:
                p.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(p.wait(), 3)
            except asyncio.TimeoutError:
                pass
        if self._reader:
            self._reader.cancel()


class Hub:
    """Các language server của một dự án (theo khoá ngôn ngữ), dùng chung cho mọi tab web / TUI."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.clients: dict[str, Client] = {}

    def available(self, path: Path) -> bool:
        return server_for(self.root, path) is not None

    async def query(self, kind: str, rel: str, text: str, line: int, col: int, utf16: bool = False) -> dict:
        """kind "definition" | "references"; line từ 1, col từ 0 (ký tự Python, hoặc UTF-16 nếu utf16=True — web).
        Trả {"items": [{"path" (tương đối, hoặc tuyệt đối nếu ngoài dự án), "line" (từ 1), "col", "text", "inside"}],
        "server"} hoặc {"error"} / {"unavailable": True} (không có server → dùng cách tìm theo tên)."""
        path = (self.root / rel).resolve()
        found = server_for(self.root, path)
        if not found:
            return {"unavailable": True}
        key, argv = found
        c = self.clients.get(key)
        if c is None or (c.proc is not None and c.proc.returncode is not None) or c.error:
            if c is not None and c.error and c.argv == argv:
                return {"unavailable": True, "error": c.error}  # đã hỏng trong phiên này: không thử lại liên tục
            c = self.clients[key] = Client(self.root, key, argv)
        lines = text.split("\n")
        src = lines[line - 1] if 0 < line <= len(lines) else ""
        col16 = col if utf16 else utf16_col(src, col)
        method = "textDocument/definition" if kind == "definition" else "textDocument/references"
        try:
            locs = await c.locations(method, path, text, line - 1, col16)
        except (LspError, asyncio.TimeoutError, OSError) as e:
            return {"error": str(e) or tr("language server không trả lời"), "server": Path(argv[0]).name}
        root = self.root.resolve()
        items, cache = [], {}
        for loc in locs:
            p = loc["path"]
            inside = p == root or root in p.parents
            if p not in cache:
                try:
                    cache[p] = text.split("\n") if p == path else p.read_text(encoding="utf-8", errors="replace").split("\n")
                except OSError:
                    cache[p] = []
            ln = cache[p][loc["line"]] if loc["line"] < len(cache[p]) else ""
            items.append({"path": str(p.relative_to(root)) if inside else str(p), "line": loc["line"] + 1,
                          "col": loc["col16"] if utf16 else py_col(ln, loc["col16"]), "text": ln.strip()[:200],
                          "inside": inside})
        return {"items": items, "server": Path(argv[0]).name}

    async def close(self) -> None:
        await asyncio.gather(*(c.close() for c in self.clients.values()), return_exceptions=True)
        self.clients.clear()
