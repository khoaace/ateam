"""Command palette của tab 📝 Code (TUI và web dùng chung): bảng lệnh, file mở gần đây, symbol trong file
(hàm, class, heading — bóc bằng token pygments, không cần LSP), lọc mờ."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import time
from pathlib import Path

from .config import load_project_state, save_project_setting
from .i18n import tr

RECENT_MAX = 30
SYMBOL_MAX_BYTES = 2 * 1024 * 1024  # file lớn hơn: không bóc symbol (lexer chậm)

# (id, nhãn, phím tắt TUI, phím tắt web) — thứ tự hiện trong palette khi chưa gõ gì sau ">"
CODE_COMMANDS: list[tuple[str, str, str, str]] = [
    ("quick_open", tr("Mở nhanh file…"), "Ctrl+P", "Ctrl/⌘+P"),
    ("goto_symbol", tr("Tới symbol trong file… (@)"), "F9", "Ctrl/⌘+Shift+O"),
    ("workspace_symbol", tr("Tìm symbol trong cả dự án… (#)"), "", ""),
    ("goto_definition", tr("Đi tới định nghĩa"), "", "F12 · ⌘+click"),
    ("recent_buffer", tr("Đổi sang file vừa dùng"), "", "⌥Tab"),
    ("goto_line", tr("Tới dòng… (:)"), "", ""),
    ("find", tr("Tìm trong file… (/)"), "", ""),
    ("search_project", tr("Tìm & thay trong dự án"), "F3", "Ctrl/⌘+Shift+F"),
    ("ai_edit", tr("✨ Sửa đoạn đang chọn bằng AI…"), "", "Ctrl/⌘+I"),
    ("ai_explain", tr("✨ Giải thích đoạn đang chọn"), "", "Ctrl/⌘+Shift+E"),
    ("ask_agent", tr("Hỏi agent về file / đoạn đang chọn…"), "", ""),
    ("task_agent", tr("Giao task cho agent với file / đoạn đang chọn…"), "", ""),
    ("save", tr("Lưu file"), "Ctrl+S", "Ctrl/⌘+S"),
    ("save_all", tr("Lưu tất cả"), "", ""),
    ("close", tr("Đóng file"), ":q", ":q"),
    ("next", tr("File kế tiếp"), ":bn", ":bn"),
    ("prev", tr("File trước"), ":bp", ":bp"),
    ("new_file", tr("File mới…"), "", ""),
    ("rename_file", tr("Đổi tên / chuyển file…"), "", ""),
    ("delete_file", tr("Xoá file (vào Thùng rác)"), "", ""),
    ("copy_path", tr("Chép đường dẫn (kèm dòng)"), "", ""),
    ("git_diff", tr("Xem thay đổi git của file"), "", ""),
    ("open_vscode", tr("Mở trong VS Code"), "", ""),
    ("format", tr("Format file (ruff, prettier…)"), "", "Shift+⌥+F"),
    ("toggle_fmt_save", tr("Bật/tắt format khi lưu"), "", ""),
    ("toggle_autosave", tr("Bật/tắt tự lưu"), "", ""),
    ("toggle_split", tr("Chia đôi / gộp khung editor"), "", "Ctrl/⌘+\\"),
    ("outline", tr("Xem outline (symbol của file)"), "", ""),
    ("toggle_wrap", tr("Bật/tắt xuống dòng mềm"), "", ""),
    ("toggle_numbers", tr("Bật/tắt số dòng"), "", ""),
    ("toggle_vim", tr("Bật/tắt phím vim"), "", ""),
    ("toggle_files", tr("Ẩn/hiện danh sách file"), ":files", ":files"),
    ("open_folder", tr("Mở folder / dự án khác…"), "/open", "/open"),
]
# từ khoá tiếng Anh để gõ kiểu VS Code (vd ">wrap", ">rename") vẫn khớp nhãn tiếng Việt
KEYWORDS: dict[str, str] = {'quick_open': 'open file', 'goto_symbol': 'symbol outline', 'goto_line': 'goto line', 'find': 'find search', 'search_project': 'search replace', 'ask_agent': 'ask chat agent', 'task_agent': 'task agent', 'save': 'save write', 'save_all': 'save all', 'close': 'close', 'next': 'next buffer', 'prev': 'previous buffer', 'new_file': 'new file create', 'rename_file': 'rename move', 'delete_file': 'delete remove trash', 'copy_path': 'copy path', 'git_diff': 'git diff changes', 'open_vscode': 'vscode code editor', 'toggle_wrap': 'word wrap', 'toggle_numbers': 'line numbers', 'toggle_vim': 'vim', 'toggle_files': 'sidebar files explorer',
            'open_folder': 'open folder project recent workspace switch', 'workspace_symbol': 'workspace symbol project',
            'goto_definition': 'go to definition declaration', 'recent_buffer': 'recent buffer switch mru',
            'format': 'format document prettier ruff black', 'toggle_fmt_save': 'format on save',
            'toggle_autosave': 'auto save autosave', 'toggle_split': 'split editor right', 'outline': 'outline symbols',
            'ai_edit': 'ai edit inline rewrite refactor', 'ai_explain': 'ai explain'}
# lệnh cần file đang mở
NEEDS_FILE = {"goto_symbol", "goto_line", "find", "save", "save_all", "close", "next", "prev", "rename_file",
              "delete_file", "copy_path", "git_diff", "open_vscode", "goto_definition", "format", "outline", "ai_edit", "ai_explain"}


WEB_SKIP = {"toggle_numbers"}  # CodeMirror của web luôn có số dòng
TUI_SKIP = {"workspace_symbol", "goto_definition", "recent_buffer", "format", "toggle_fmt_save", "toggle_autosave",
            "toggle_split", "outline", "ai_edit", "ai_explain"}  # mới có ở web
WS_SYMBOL_MAX_BYTES = 512 * 1024  # symbol toàn dự án: bỏ qua file lớn hơn
WS_SYMBOL_FILES = 4000
WS_SYMBOL_SECONDS = 4.0  # lần quét đầu (chưa có cache) dừng sau bấy nhiêu giây, trả phần đã có


def commands_json() -> list[dict]:
    """Bảng lệnh cho web (`hello()`)."""
    return [{"id": i, "label": label, "key": web, "kw": KEYWORDS.get(i, ""), "file": i in NEEDS_FILE}
            for i, label, _tui, web in CODE_COMMANDS if i not in WEB_SKIP]


# ------------------------------------------------------------------------------------------- file gần đây
def recent_files(root: Path) -> list[str]:
    files = load_project_state(root).get("recent_files") or []
    return [f for f in files if isinstance(f, str)][:RECENT_MAX]


def touch_recent(root: Path, rel: str) -> None:
    """Ghi file vừa mở lên đầu danh sách gần đây (.ateam/state.json, chung TUI và web)."""
    files = [f for f in recent_files(root) if f != rel]
    save_project_setting(root, "recent_files", [rel] + files[:RECENT_MAX - 1])


def forget_recent(root: Path, rel: str, new: str | None = None) -> None:
    """File bị xoá (new=None) hoặc đổi tên: bỏ / thay trong danh sách gần đây."""
    files = recent_files(root)
    if rel in files:
        files = [new if f == rel else f for f in files if new or f != rel]
        save_project_setting(root, "recent_files", files)


# ------------------------------------------------------------------------------------------------ lọc mờ
def fuzzy_score(text: str, query: str) -> int | None:
    """Điểm khớp rải rác (các chữ của query lần lượt có trong text); cao hơn = tốt hơn; None = không khớp."""
    t, q = text.lower(), query.lower().strip()
    if not q:
        return 0
    if q in t:
        # khớp ở đầu một từ ("ask" trong "ask agent") hơn khớp giữa từ ("ask" trong "task")
        word = re.search(r"(?:^|[^\w])" + re.escape(q), t)
        at = word.start() + (word.group(0)[0] != q[0]) if word else t.index(q)
        return 1000 - at - len(t) // 4 + (300 if word else 0) + (200 if t.startswith(q) else 0)
    pos, gaps = -1, 0
    for ch in q:
        nxt = t.find(ch, pos + 1)
        if nxt < 0:
            return None
        gaps += nxt - pos - 1
        pos = nxt
    return 500 - gaps - len(t) // 4


def fuzzy(items: list, query: str, key=lambda x: x, limit: int = 200) -> list:
    if not query.strip():
        return items[:limit]
    scored = [(s, i, it) for i, it in enumerate(items) if (s := fuzzy_score(key(it), query)) is not None]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [it for _s, _i, it in scored[:limit]]


# -------------------------------------------------------------------------------------------------- symbol
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
JS_EXT = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte"}
_KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "return", "with", "else", "do", "new", "typeof"}
# (regex, kind): nhóm cuối có tên = tên symbol. JS/TS: lexer pygments gọi hầu hết tên là Name.Other
_JS_RULES = [
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\*?\s+(?P<n>[\w$]+)"), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(?P<n>[\w$]+)"), "class"),
    (re.compile(r"^\s*(?:export\s+)?(?:declare\s+)?(?:interface|type|enum)\s+(?P<n>[\w$]+)"), "type"),
    (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<n>[\w$]+)\s*(?::[^=]+)?=\s*(?:async\s*)?"
                r"(?:function\b|\([^)]*\)\s*(?::[^=]+)?=>|[\w$]+\s*=>)"), "function"),
    (re.compile(r"^\s+(?:public\s+|private\s+|protected\s+|static\s+|async\s+|get\s+|set\s+)*"
                r"(?P<n>[\w$]+)\s*\([^)]*\)\s*(?::\s*[^{]+)?\{\s*$"), "method"),
]
# dự phòng cho ngôn ngữ khác khi lexer không gắn Name.Function/Name.Class
_GENERIC_RULES = [
    (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:def|fn|func|function|sub|proc)\s+"
                r"(?:\([^)]*\)\s*)?(?P<n>[\w$]+)"), "function"),
    (re.compile(r"^\s*(?:pub\s+)?(?:class|struct|trait|interface|enum|module|impl)\s+(?P<n>[\w$]+)"), "class"),
]


def _by_rules(text: str, rules) -> list[dict]:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        for rx, kind in rules:
            m = rx.match(line)
            if m and m.group("n") not in _KEYWORDS:
                indent = len(line) - len(line.lstrip())
                out.append({"name": m.group("n"), "kind": kind, "line": i, "depth": min(indent // 2, 6)})
                break
    return out


def symbols(path: Path, text: str) -> list[dict]:
    """Hàm / class / heading trong file: [{"name", "kind", "line" (từ 1), "depth"}] theo thứ tự trong file."""
    if len(text) > SYMBOL_MAX_BYTES:
        return []
    if path.suffix.lower() in (".md", ".markdown", ".mdx"):
        out, fence = [], False
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("```", "~~~")):
                fence = not fence
            m = None if fence else _MD_HEADING.match(line)
            if m:
                out.append({"name": m.group(2), "kind": "heading", "line": i, "depth": len(m.group(1)) - 1})
        return out
    if path.suffix.lower() in JS_EXT:
        return _by_rules(text, _JS_RULES)
    from . import editor
    lexer = editor.lexer_for(path, text[:2000])
    if lexer is None:
        return _by_rules(text, _GENERIC_RULES)
    from pygments.token import Name
    out, line, seen = [], 1, set()
    try:
        tokens = lexer.get_tokens_unprocessed(text)
        for _pos, ttype, value in tokens:
            if ttype in Name.Class:
                kind = "class"
            elif ttype in Name.Function:
                kind = "function"
            else:
                kind = ""
            if kind and value.strip() and (line, value) not in seen:
                seen.add((line, value))
                col = text.rfind("\n", 0, _pos)
                indent = len(text[col + 1:_pos]) - len(text[col + 1:_pos].lstrip())
                out.append({"name": value.strip(), "kind": kind, "line": line, "depth": min(indent // 2, 6)})
            line += value.count("\n")
    except Exception:
        pass
    return out or _by_rules(text, _GENERIC_RULES)


def _symbol_file(path: Path) -> bool:
    """File có thể bóc symbol: markdown, JS/TS, hoặc pygments nhận ra ngôn ngữ."""
    from . import editor
    ext = path.suffix.lower()
    return ext in (".md", ".markdown", ".mdx") or ext in JS_EXT or editor.lexer_for(path) is not None


def workspace_symbols(root: Path, entries: list[str], query: str, cache: dict, exact: bool = False,
                      limit: int = 200) -> dict:
    """Symbol của mọi file trong dự án (palette `#`, F12 đi tới định nghĩa): {"items": [{"name", "kind", "line",
    "path"}], "partial"}. cache {rel: (mtime, [symbol])} giữ giữa các lần hỏi — chỉ bóc lại file đã đổi.
    exact: đúng tên (bỏ heading markdown) — để tìm định nghĩa."""
    from . import editor
    out, partial, deadline = [], False, time.monotonic() + WS_SYMBOL_SECONDS
    files = [e for e in entries if not e.endswith("/")][:WS_SYMBOL_FILES]
    for rel in files:
        p = root / rel
        try:
            st = p.stat()
        except OSError:
            continue
        hit = cache.get(rel)
        if hit is None or hit[0] != st.st_mtime:
            if st.st_size > WS_SYMBOL_MAX_BYTES or not _symbol_file(p):
                cache[rel] = (st.st_mtime, [])
                continue
            if time.monotonic() > deadline:
                partial = True
                continue
            sf = editor.read_source(p)
            hit = cache[rel] = (st.st_mtime, [] if sf.error else symbols(p, sf.text))
        out.extend(dict(s, path=rel) for s in hit[1])
    for gone in set(cache) - set(files):
        cache.pop(gone, None)
    if exact:
        items = [s for s in out if s["name"] == query and s["kind"] != "heading"][:limit]
    else:
        items = fuzzy(out, query, key=lambda s: s["name"], limit=limit)
    return {"items": [{"name": s["name"], "kind": s["kind"], "line": s["line"], "path": s["path"]} for s in items],
            "partial": partial}


def symbol_at(syms: list[dict], line: int) -> dict | None:
    """Symbol gần nhất phía trên dòng `line` (từ 1) — cho thanh "đang ở đâu" (breadcrumb)."""
    best = None
    for s in syms:
        if s["line"] > line:
            break
        best = s
    return best


# ------------------------------------------------------------------------------------- tạo / đổi tên / xoá file
def safe_path(root: Path, rel: str) -> Path | None:
    """Đường dẫn trong dự án, hoặc None nếu ra ngoài / vào .git."""
    rel = (rel or "").strip().lstrip("@").strip('"').strip("'")
    if not rel or "\0" in rel:
        return None
    root = root.resolve()
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        return None
    if ".git" in (x.lower() for x in p.relative_to(root).parts):  # macOS: .GIT cũng là .git
        return None
    return p


def file_new(root: Path, rel: str) -> str:
    """Tạo file rỗng (kèm thư mục cha). "" nếu xong, không thì lời báo lỗi."""
    p = safe_path(root, rel)
    if p is None or p == root.resolve():
        return tr("Đường dẫn không hợp lệ: {v}", v=rel)
    if p.exists():
        return tr("Đã có {v}", v=rel)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    except OSError as e:
        return str(e)
    return ""


def file_rename(root: Path, old: str, new: str) -> str:
    src, dst = safe_path(root, old), safe_path(root, new)
    if src is None or dst is None or root.resolve() in (src, dst):
        return tr("Đường dẫn không hợp lệ: {v}", v=new)
    if not src.exists():
        return tr("Không còn file {v}", v=old)
    if dst.exists():
        return tr("Đã có {v}", v=new)
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.rename(src, dst)
    except OSError as e:
        return str(e)
    forget_recent(root, old, new)
    return ""


async def file_trash(root: Path, rel: str) -> str:
    """Xoá file vào Thùng rác (macOS: Finder, để còn khôi phục được; Linux: ~/.local/share/Trash).
    ATEAM_TRASH_DIR: chuyển vào thư mục này (test)."""
    p = safe_path(root, rel)
    if p is None or p == root.resolve() or not p.exists():
        return tr("Không còn file {v}", v=rel)
    if p.is_dir():
        return tr("{v} là thư mục — chỉ xoá file", v=rel)
    target = os.environ.get("ATEAM_TRASH_DIR")
    if not target and sys.platform == "darwin" and shutil.which("osascript"):
        script = 'on run argv\ntell application "Finder" to delete (POSIX file (item 1 of argv))\nend run'
        proc = await asyncio.create_subprocess_exec("osascript", "-e", script, str(p),
                                                    stdout=asyncio.subprocess.DEVNULL,
                                                    stderr=asyncio.subprocess.PIPE)
        _out, err = await proc.communicate()
        if proc.returncode:
            return tr("Không đưa được vào Thùng rác: {e}", e=err.decode(errors="replace").strip())
    else:
        d = Path(target) if target else Path.home() / ".local/share/Trash/files"
        try:
            d.mkdir(parents=True, exist_ok=True)
            dest = d / p.name
            if dest.exists():
                dest = d / f"{p.stem} {time.strftime('%Y%m%d-%H%M%S')}{p.suffix}"
            await asyncio.to_thread(shutil.move, str(p), str(dest))
        except OSError as e:
            return str(e)
    forget_recent(root, rel)
    return ""
