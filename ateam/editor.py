"""Tab 📝 Code: phần không phụ thuộc giao diện — đọc/ghi file nguồn an toàn, tô màu cú pháp bằng pygments
(không cần tree-sitter), và bộ xử lý phím kiểu vim (`VimState`) trả về danh sách thao tác để widget
(`CodeEditor` ở tui.py) áp dụng. Tách ra để test được không cần dựng app."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import tr

MAX_EDIT_BYTES = 5 * 1024 * 1024  # lớn hơn: mở chỉ đọc
MAX_HL_BYTES = 2 * 1024 * 1024  # lớn hơn: không tô màu
MAX_HL_LINES = 20000
BINARY_SNIFF = 8192


# ---------------------------------------------------------------------------------------------- đọc / ghi
@dataclass
class SourceFile:
    path: Path
    text: str = ""
    newline: str = "\n"
    encoding: str = "utf-8"
    mtime: float = 0.0
    size: int = 0
    read_only: bool = False
    error: str = ""  # khác rỗng: không mở được (nhị phân, không đọc được…)
    note: str = ""  # ghi chú hiện trên thanh editor (chỉ đọc vì…)


def read_source(path: Path) -> SourceFile:
    """Đọc file nguồn (gọi trong thread). Không ném lỗi: lỗi nằm ở `.error`."""
    sf = SourceFile(path=path)
    try:
        st = path.stat()
        sf.mtime, sf.size = st.st_mtime, st.st_size
        raw = path.read_bytes()
    except FileNotFoundError:
        return sf  # file mới: lưu sẽ tạo
    except OSError as e:
        sf.error = tr("Không đọc được: {e}", e=e.strerror or e)
        return sf
    if b"\0" in raw[:BINARY_SNIFF]:
        sf.error = tr("File nhị phân — không mở trong editor")
        return sf
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
        sf.encoding, sf.read_only = "latin-1", True
        sf.note = tr("không phải UTF-8 — chỉ đọc")
    if text.startswith("﻿"):
        text = text[1:]
        sf.encoding = "utf-8-sig"
    if "\r\n" in text:
        sf.newline = "\r\n"
        text = text.replace("\r\n", "\n")
    if sf.size > MAX_EDIT_BYTES:
        sf.read_only = True
        sf.note = tr("file lớn — chỉ đọc")
    sf.text = text
    return sf


def disk_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def save_source(sf: SourceFile, text: str, force: bool = False) -> str:
    """Ghi `text` ra file (gọi trong thread). Trả "" nếu xong, "conflict" nếu file trên đĩa đã đổi từ lúc
    mở (agent vừa sửa) và không `force`, hoặc thông báo lỗi. Ghi qua file tạm + os.replace để không làm
    hỏng file khi lỗi giữa chừng."""
    if not force and sf.mtime and disk_mtime(sf.path) not in (0.0, sf.mtime):
        return "conflict"
    data = text.replace("\n", sf.newline) if sf.newline != "\n" else text
    enc = "utf-8" if sf.encoding == "latin-1" else sf.encoding
    try:
        sf.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".ateam-", dir=str(sf.path.parent))
        try:
            with os.fdopen(fd, "w", encoding=enc, newline="") as f:
                f.write(data)
            if sf.path.exists():
                os.chmod(tmp, sf.path.stat().st_mode & 0o7777)
            os.replace(tmp, sf.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as e:
        return tr("Không lưu được: {e}", e=e.strerror or e)
    st = sf.path.stat()
    sf.mtime, sf.size = st.st_mtime, st.st_size
    return ""


# ---------------------------------------------------------------------------------------------- tô màu
_LEXERS: dict = {}


# Format bằng công cụ của dự án (tab Code web: ⇧⌥F, format khi lưu): theo đuôi file, công cụ nào có trước thì dùng.
# Tham số "{path}" = đường dẫn file (để công cụ đọc đúng cấu hình / ngôn ngữ). Đọc chữ từ stdin, in ra stdout.
_PRETTIER = [("prettier", ["--stdin-filepath", "{path}"])]
FORMATTERS: list[tuple[set, list]] = [
    ({".py", ".pyi"}, [("ruff", ["format", "--stdin-filename", "{path}", "-"]),
                       ("black", ["-q", "--stdin-filename", "{path}", "-"])]),
    ({".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".css", ".scss", ".less", ".json", ".jsonc",
      ".md", ".markdown", ".mdx", ".html", ".vue", ".svelte", ".yaml", ".yml", ".graphql"}, _PRETTIER),
    ({".go"}, [("gofmt", [])]),
    ({".rs"}, [("rustfmt", ["--emit", "stdout", "--edition", "2021"])]),
    ({".sh", ".bash"}, [("shfmt", ["-filename", "{path}"])]),
]


def _find_tool(name: str, root: Path) -> str | None:
    """Ưu tiên bản cài trong dự án (node_modules/.bin, .venv) rồi mới tới PATH."""
    for d in (root / "node_modules" / ".bin", root / ".venv" / "bin", root / "venv" / "bin"):
        p = d / name
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return shutil.which(name)


def formatter_for(path: Path, root: Path) -> list[str] | None:
    """Lệnh format file này (argv), None nếu máy không có công cụ nào hợp."""
    ext = path.suffix.lower()
    for exts, tools in FORMATTERS:
        if ext in exts:
            for name, args in tools:
                exe = _find_tool(name, root)
                if exe:
                    return [exe] + [a.replace("{path}", str(path)) for a in args]
    return None


async def format_text(argv: list[str], text: str, cwd: Path, timeout: float = 20.0) -> tuple[bool, str]:
    """Chạy công cụ format: (True, chữ đã format) hoặc (False, lời báo lỗi)."""
    import asyncio
    try:
        proc = await asyncio.create_subprocess_exec(*argv, cwd=str(cwd), stdin=asyncio.subprocess.PIPE,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except OSError as e:
        return False, str(e)
    try:
        out, err = await asyncio.wait_for(proc.communicate(text.encode("utf-8")), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return False, tr("{v} quá {n} giây — đã dừng", v=Path(argv[0]).name, n=int(timeout))
    if proc.returncode:
        msg = (err or out).decode("utf-8", "replace").strip()
        return False, msg[-600:] or tr("thoát với mã {code}", code=proc.returncode)
    return True, out.decode("utf-8", "replace").replace("\r\n", "\n")


def lexer_for(path: Path, sample: str = ""):
    """Lexer pygments theo tên file (cache theo đuôi); None nếu không nhận ra."""
    key = path.suffix.lower() or path.name.lower()
    if key in _LEXERS:
        return _LEXERS[key]
    lexer = None
    try:
        from pygments.lexers import get_lexer_for_filename
        from pygments.util import ClassNotFound
        try:
            lexer = get_lexer_for_filename(path.name, stripnl=False, ensurenl=False)
        except ClassNotFound:
            lexer = None
    except Exception:
        lexer = None
    if lexer is not None and lexer.name.lower() in ("text only", "text"):
        lexer = None
    _LEXERS[key] = lexer
    return lexer


def language_name(path: Path) -> str:
    lx = lexer_for(path)
    return lx.name if lx is not None else tr("văn bản")


def _style_name(ttype) -> str | None:
    from pygments import token as T
    if ttype in T.Comment:
        return "comment"
    if ttype in T.String.Doc:
        return "string.documentation"
    if ttype in T.String:
        return "string"
    if ttype in T.Number:
        return "number"
    if ttype in T.Keyword.Constant:
        return "boolean"
    if ttype in T.Keyword.Type:
        return "type.builtin"
    if ttype in T.Keyword:
        return "keyword"
    if ttype in T.Operator.Word:
        return "keyword.operator"
    if ttype in T.Operator:
        return "operator"
    if ttype in T.Name.Function:
        return "function"
    if ttype in T.Name.Class:
        return "type.class"
    if ttype in T.Name.Decorator:
        return "function"
    if ttype in T.Name.Builtin:
        return "constant.builtin"
    if ttype in T.Name.Tag:
        return "tag"
    if ttype in T.Name.Attribute:
        return "css.property"
    if ttype in T.Name.Exception:
        return "exception"
    if ttype in T.Generic.Heading or ttype in T.Generic.Subheading:
        return "heading"
    if ttype in T.Punctuation:
        return "punctuation.bracket"
    return None


def highlight_lines(text: str, lexer, end_line: int | None = None) -> dict[int, list[tuple[int, int, str]]]:
    """{dòng: [(byte_đầu, byte_cuối, tên style TextAreaTheme)]} cho các dòng < end_line (None = cả file).
    Offset tính theo byte UTF-8 vì TextArea._render_line đọc highlight theo byte."""
    out: dict[int, list[tuple[int, int, str]]] = {}
    if lexer is None or not text:
        return out
    if end_line is not None:
        cut = -1
        for _ in range(end_line):
            cut = text.find("\n", cut + 1)
            if cut < 0:
                break
        if cut >= 0:
            text = text[:cut]
    row, bcol = 0, 0
    for _, ttype, value in lexer.get_tokens_unprocessed(text):
        name = _style_name(ttype)
        parts = value.split("\n")
        for i, part in enumerate(parts):
            if i:
                row += 1
                bcol = 0
            if not part:
                continue
            blen = len(part.encode("utf-8"))
            if name:
                out.setdefault(row, []).append((bcol, bcol + blen, name))
            bcol += blen
    return out


def can_highlight(text: str, size: int) -> bool:
    return size <= MAX_HL_BYTES and text.count("\n") < MAX_HL_LINES


# ---------------------------------------------------------------------------------------------- vim
Loc = tuple  # (dòng, cột) theo ký tự, như TextArea


def _cls(ch: str) -> int:
    """Lớp ký tự cho chuyển động theo từ: 0 khoảng trắng, 1 chữ/số/_, 2 dấu câu."""
    if ch.isspace():
        return 0
    if ch.isalnum() or ch == "_":
        return 1
    return 2


def first_nonblank(line: str) -> int:
    return len(line) - len(line.lstrip(" \t")) if line.strip() else 0


@dataclass
class VimState:
    """Máy trạng thái phím vim. `feed(key, char, lines, cursor, height)` trả danh sách thao tác:

    ("move", loc) · ("edit", start, end, text) thay đoạn [start, end) bằng text · ("select", a, b) vùng chọn
    (b loại trừ) · ("undo", n) · ("redo", n) · ("mode", tên) · ("ex", lệnh) lệnh `:` widget tự làm (w, q…)
    · ("msg", chữ) · ("bell",)
    """

    mode: str = "normal"  # normal | insert | visual | vline | command | search
    count: str = ""
    op: str = ""  # d c y > < đang chờ chuyển động
    op_count: int = 1
    prefix: str = ""  # g hoặc r đang chờ phím thứ hai
    anchor: Loc = (0, 0)  # điểm đầu vùng chọn (visual)
    cmdline: str = ""
    register: str = ""
    reg_linewise: bool = False
    last_search: str = ""
    search_forward: bool = True
    shiftwidth: int = 4
    _lines: list = field(default_factory=list, repr=False)
    _had_count = False

    # ---- tiện ích
    @property
    def status(self) -> str:
        if self.mode == "command":
            return ":" + self.cmdline
        if self.mode == "search":
            return ("/" if self.search_forward else "?") + self.cmdline
        return {"insert": "-- INSERT --", "visual": "-- VISUAL --", "vline": "-- VISUAL LINE --"}.get(
            self.mode, (str(self.op_count) if self.op and self.op_count > 1 else "") + self.count + self.op
            + self.prefix)

    def _n(self) -> int:
        n = int(self.count) if self.count else 1
        self.count = ""
        return max(1, n)

    def _reset(self) -> None:
        self.count, self.op, self.prefix, self.op_count = "", "", "", 1

    def _clamp(self, loc: Loc, insert: bool = False) -> Loc:
        lines = self._lines
        r = max(0, min(loc[0], len(lines) - 1))
        n = len(lines[r])
        c = max(0, min(loc[1], n if insert else max(0, n - 1)))
        return (r, c)

    # ---- chuyển động: (đích, theo dòng, bao gồm ký tự cuối)
    def _word_fwd(self, loc: Loc) -> Loc:
        lines = self._lines
        r, c = loc
        line = lines[r]
        if c < len(line):
            k = _cls(line[c])
            while c < len(line) and _cls(line[c]) == k and k != 0:
                c += 1
        while True:
            while c < len(line) and line[c].isspace():
                c += 1
            if c < len(line):
                return (r, c)
            if r + 1 >= len(lines):
                return (r, len(line))
            r, c, line = r + 1, 0, lines[r + 1]
            if not line:
                return (r, 0)

    def _word_end(self, loc: Loc) -> Loc:
        lines = self._lines
        r, c = loc
        c += 1
        line = lines[r]
        while True:
            while c < len(line) and line[c].isspace():
                c += 1
            if c < len(line):
                break
            if r + 1 >= len(lines):
                return (r, max(0, len(line) - 1))
            r, c, line = r + 1, 0, lines[r + 1]
        k = _cls(line[c])
        while c + 1 < len(line) and _cls(line[c + 1]) == k:
            c += 1
        return (r, c)

    def _word_back(self, loc: Loc) -> Loc:
        lines = self._lines
        r, c = loc
        line = lines[r]
        c -= 1
        while True:
            while c >= 0 and line[c].isspace():
                c -= 1
            if c >= 0:
                break
            if r == 0:
                return (0, 0)
            r -= 1
            line = lines[r]
            c = len(line) - 1
            if not line:
                return (r, 0)
        k = _cls(line[c])
        while c > 0 and _cls(line[c - 1]) == k:
            c -= 1
        return (r, c)

    def _motion(self, k: str, cur: Loc, n: int, height: int):
        lines = self._lines
        r, c = cur
        last = len(lines) - 1
        if k in ("h", "left", "backspace"):
            return (r, max(0, c - n)), False, False
        if k in ("l", "right", " "):
            return (r, min(len(lines[r]), c + n)), False, False
        if k in ("j", "down", "enter", "+"):
            t = min(last, r + n)
            return (t, c if k in ("j", "down") else first_nonblank(lines[t])), True, True
        if k in ("k", "up", "-"):
            t = max(0, r - n)
            return (t, c if k in ("k", "up") else first_nonblank(lines[t])), True, True
        if k in ("0", "home"):
            return (r, 0), False, False
        if k == "^":
            return (r, first_nonblank(lines[r])), False, False
        if k in ("$", "end"):
            t = min(last, r + n - 1)
            return (t, max(0, len(lines[t]) - 1)), False, True
        if k == "w":
            loc = cur
            for _ in range(n):
                loc = self._word_fwd(loc)
            return loc, False, False
        if k == "e":
            loc = cur
            for _ in range(n):
                loc = self._word_end(loc)
            return loc, False, True
        if k == "b":
            loc = cur
            for _ in range(n):
                loc = self._word_back(loc)
            return loc, False, False
        if k == "G":
            t = min(last, n - 1) if self._had_count else last
            return (t, first_nonblank(lines[t])), True, True
        if k == "gg":
            t = min(last, n - 1)
            return (t, first_nonblank(lines[t])), True, True
        if k == "ctrl+d":
            return (min(last, r + max(1, height // 2) * n), c), True, True
        if k == "ctrl+u":
            return (max(0, r - max(1, height // 2) * n), c), True, True
        if k in ("ctrl+f", "pagedown"):
            return (min(last, r + max(1, height - 2) * n), c), True, True
        if k in ("ctrl+b", "pageup"):
            return (max(0, r - max(1, height - 2) * n), c), True, True
        return None

    # ---- thao tác trên đoạn
    def _linewise_range(self, r1: int, r2: int):
        """(start, end) xoá trọn dòng r1..r2 kể cả xuống dòng."""
        lines = self._lines
        last = len(lines) - 1
        if r2 < last:
            return (r1, 0), (r2 + 1, 0)
        if r1 > 0:
            return (r1 - 1, len(lines[r1 - 1])), (r2, len(lines[r2]))
        return (0, 0), (r2, len(lines[r2]))

    def _text(self, a: Loc, b: Loc) -> str:
        lines = self._lines
        if a[0] == b[0]:
            return lines[a[0]][a[1]:b[1]]
        parts = [lines[a[0]][a[1]:]] + list(lines[a[0] + 1:b[0]]) + [lines[b[0]][:b[1]]]
        return "\n".join(parts)

    def _apply_op(self, op: str, a: Loc, b: Loc, linewise: bool, out: list) -> None:
        """Áp toán tử op trên đoạn a..b (b loại trừ nếu không theo dòng)."""
        lines = self._lines
        if linewise:
            r1, r2 = sorted((a[0], b[0]))
            if op in (">", "<"):
                for r in range(r1, r2 + 1):
                    line = lines[r]
                    if op == ">":
                        if line:
                            out.append(("edit", (r, 0), (r, 0), " " * self.shiftwidth))
                    else:
                        strip = min(self.shiftwidth, len(line) - len(line.lstrip(" ")))
                        if strip:
                            out.append(("edit", (r, 0), (r, strip), ""))
                out.append(("move", (r1, first_nonblank(lines[r1]) + (self.shiftwidth if op == ">" else 0))))
                return
            self.register = "\n".join(lines[r1:r2 + 1]) + "\n"
            self.reg_linewise = True
            if op == "y":
                out.append(("move", (r1, a[1] if a[0] == r1 else b[1])))
                out.append(("msg", tr("đã chép {n} dòng", n=r2 - r1 + 1)))
                return
            if op == "c":
                indent = lines[r1][:first_nonblank(lines[r1])]
                out.append(("edit", (r1, 0), (r2, len(lines[r2])), indent))
                out.append(("move", (r1, len(indent))))
                out.append(("mode", "insert"))
                self.mode = "insert"
                return
            s, e = self._linewise_range(r1, r2)
            out.append(("edit", s, e, ""))
            nr = min(r1, len(lines) - 1 - (r2 - r1 + 1)) if len(lines) > r2 - r1 + 1 else 0
            out.append(("move", (max(0, nr), None)))  # None: cột = ký tự đầu không trắng sau khi sửa
            return
        a, b = sorted((a, b))
        self.register = self._text(a, b)
        self.reg_linewise = False
        if op == "y":
            out.append(("move", a))
            return
        if op in (">", "<"):
            self._apply_op(op, a, b, True, out)
            return
        out.append(("edit", a, b, ""))
        out.append(("move", a))
        if op == "c":
            out.append(("mode", "insert"))
            self.mode = "insert"

    def _paste(self, after: bool, cur: Loc, n: int, out: list) -> None:
        if not self.register:
            out.append(("bell",))
            return
        lines = self._lines
        r, c = cur
        if self.reg_linewise:
            body = self.register[:-1] if self.register.endswith("\n") else self.register
            body = "\n".join([body] * n)
            if after:
                out.append(("edit", (r, len(lines[r])), (r, len(lines[r])), "\n" + body))
                out.append(("move", (r + 1, None)))
            else:
                out.append(("edit", (r, 0), (r, 0), body + "\n"))
                out.append(("move", (r, None)))
            return
        text = self.register * n
        col = min(len(lines[r]), c + 1) if after and lines[r] else c
        out.append(("edit", (r, col), (r, col), text))
        tail = text.split("\n")
        end = (r + len(tail) - 1, (col if len(tail) == 1 else 0) + len(tail[-1]) - 1)
        out.append(("move", (end[0], max(0, end[1]))))

    def _search(self, pattern: str, cur: Loc, forward: bool, n: int, out: list) -> None:
        lines = self._lines
        try:
            rx = re.compile(pattern)
        except re.error:
            rx = re.compile(re.escape(pattern))
        r, c = cur
        total = len(lines)
        loc = None
        for _ in range(n):
            found = None
            if forward:
                m = rx.search(lines[r], c + 1)
                if m:
                    found = (r, m.start())
                else:
                    for i in range(1, total + 1):
                        rr = (r + i) % total
                        m = rx.search(lines[rr])
                        if m:
                            found = (rr, m.start())
                            break
            else:
                ms = [m for m in rx.finditer(lines[r]) if m.start() < c]
                if ms:
                    found = (r, ms[-1].start())
                else:
                    for i in range(1, total + 1):
                        rr = (r - i) % total
                        ms = list(rx.finditer(lines[rr]))
                        if ms:
                            found = (rr, ms[-1].start())
                            break
            if found is None:
                break
            loc = found
            r, c = found
        if loc is None:
            out.append(("msg", tr("Không tìm thấy: {p}", p=pattern)))
            out.append(("bell",))
        else:
            out.append(("move", loc))

    def _word_under(self, cur: Loc) -> str:
        line = self._lines[cur[0]]
        c = cur[1]
        if not line:
            return ""
        c = min(c, len(line) - 1)
        while c < len(line) and _cls(line[c]) != 1:
            c += 1
        if c >= len(line):
            return ""
        s = e = c
        while s > 0 and _cls(line[s - 1]) == 1:
            s -= 1
        while e < len(line) and _cls(line[e]) == 1:
            e += 1
        return line[s:e]

    # ---- vào
    def feed(self, key: str, char: str | None, lines, cursor: Loc, height: int = 20) -> list:
        """Một phím. `key` là tên phím Textual (escape, ctrl+d, left…), `char` ký tự in được (hoặc None)."""
        self._lines = lines if lines else [""]
        k = char if char and len(char) == 1 and char.isprintable() else key
        out: list = []
        if self.mode in ("command", "search"):
            return self._feed_cmdline(k, key, cursor, out)
        if self.mode == "insert":
            if key in ("escape", "ctrl+left_square_bracket", "ctrl+c"):
                self.mode = "normal"
                out.append(("mode", "normal"))
                out.append(("move", self._clamp((cursor[0], cursor[1] - 1))))
            return out
        visual = self.mode in ("visual", "vline")
        if key in ("escape", "ctrl+c", "ctrl+left_square_bracket"):
            if visual:
                self.mode = "normal"
                out.append(("mode", "normal"))
                out.append(("move", self._clamp(cursor)))
            self._reset()
            return out

        # phím thứ hai của g / r
        if self.prefix == "r":
            self.prefix = ""
            n = self._n()
            line = lines[cursor[0]]
            if k and len(k) == 1 and cursor[1] + n <= len(line):
                out.append(("edit", cursor, (cursor[0], cursor[1] + n), k * n))
                out.append(("move", (cursor[0], cursor[1] + n - 1)))
            else:
                out.append(("bell",))
            self._reset()
            return out
        if self.prefix == "g":
            self.prefix = ""
            if k == "g":
                k = "gg"
            elif k == "J":
                k = "gJ"
            else:
                self._reset()
                return [("bell",)]

        if k.isdigit() and len(k) == 1 and (k != "0" or self.count):
            self.count += k
            return out
        if k == "g":
            self.prefix = "g"
            return out

        self._had_count = bool(self.count)
        n = self._n()

        # ----- visual
        if visual:
            return self._feed_visual(k, cursor, n, height, out)

        # ----- toán tử đang chờ chuyển động
        if self.op:
            op, n = self.op, n * self.op_count
            self.op, self.op_count = "", 1
            if k == op or (op == "c" and k == "c"):
                r2 = min(len(lines) - 1, cursor[0] + n - 1)
                self._apply_op(op, cursor, (r2, 0), True, out)
                return out
            if op == "c" and k == "w":
                k = "e"  # cw = ce (vim)
                line = lines[cursor[0]]
                if cursor[1] < len(line) and line[cursor[1]].isspace():
                    k = "w"
            mv = self._motion(k, cursor, n, height)
            if mv is None:
                return [("bell",)]
            target, linewise, inclusive = mv
            if k == "w" and op in ("d", "y", "c") and target[0] > cursor[0]:
                target = (cursor[0], len(lines[cursor[0]]))  # dw ở cuối dòng không nuốt dòng sau
            if linewise:
                self._apply_op(op, cursor, target, True, out)
                return out
            a, b = sorted((cursor, target))
            if inclusive:
                b = (b[0], min(len(lines[b[0]]), b[1] + 1))
            self._apply_op(op, a, b, False, out)
            return out

        # ----- chuyển động thường
        mv = self._motion(k, cursor, n, height)
        if mv is not None:
            target = mv[0]
            if k in ("j", "k", "down", "up", "ctrl+d", "ctrl+u", "ctrl+f", "ctrl+b", "pagedown", "pageup"):
                out.append(("move_v", target))  # giữ cột mong muốn
            else:
                out.append(("move", self._clamp(target)))
            return out

        r, c = cursor
        line = lines[r]
        if k in ("d", "c", "y", ">", "<"):
            self.op, self.op_count = k, n
            return out
        if k == "i":
            return self._insert(out, cursor)
        if k == "a":
            return self._insert(out, (r, min(len(line), c + 1)))
        if k == "I":
            return self._insert(out, (r, first_nonblank(line)))
        if k == "A":
            return self._insert(out, (r, len(line)))
        if k == "o":
            indent = line[:first_nonblank(line)]
            out.append(("edit", (r, len(line)), (r, len(line)), "\n" + indent))
            return self._insert(out, (r + 1, len(indent)))
        if k == "O":
            indent = line[:first_nonblank(line)]
            out.append(("edit", (r, 0), (r, 0), indent + "\n"))
            return self._insert(out, (r, len(indent)))
        if k in ("x", "delete"):
            if not line:
                return [("bell",)]
            gone = min(len(line), c + n) - c
            self._apply_op("d", cursor, (r, c + gone), False, out)
            out.append(("move", (r, max(0, min(c, len(line) - gone - 1)))))
            return out
        if k == "X":
            if c == 0:
                return [("bell",)]
            self._apply_op("d", (r, max(0, c - n)), cursor, False, out)
            return out
        if k == "s":
            self._apply_op("c", cursor, (r, min(len(line), c + n)), False, out)
            return out
        if k == "S":
            self._apply_op("c", cursor, (min(len(lines) - 1, r + n - 1), 0), True, out)
            return out
        if k in ("D", "C"):
            r2 = min(len(lines) - 1, r + n - 1)
            self._apply_op("d" if k == "D" else "c", cursor, (r2, len(lines[r2])), False, out)
            if k == "D":
                out.append(("move", (r, max(0, c - 1))))
            return out
        if k == "Y":
            self._apply_op("y", cursor, (min(len(lines) - 1, r + n - 1), 0), True, out)
            return out
        if k in ("p", "P"):
            self._paste(k == "p", cursor, n, out)
            return out
        if k in ("J", "gJ"):
            m = min(len(lines) - 1, r + max(1, n - 1))
            if m == r:
                return [("bell",)]
            joined = lines[r]
            col = 0
            for nxt in lines[r + 1:m + 1]:
                body = nxt if k == "gJ" else nxt.lstrip()
                sep = "" if k == "gJ" or not body or joined.endswith(" ") or not joined else " "
                col = len(joined)
                joined += sep + body
            out.append(("edit", (r, 0), (m, len(lines[m])), joined))
            out.append(("move", (r, col)))
            return out
        if k == "r":
            self.prefix = "r"
            self.count = str(n) if n > 1 else ""
            return out
        if k == "u":
            return [("undo", n)]
        if k == "ctrl+r":
            return [("redo", n)]
        if k == "v":
            self.mode, self.anchor = "visual", cursor
            out.append(("mode", "visual"))
            out.append(("select", cursor, (r, c + 1)))
            return out
        if k == "V":
            self.mode, self.anchor = "vline", cursor
            out.append(("mode", "vline"))
            out.append(("select", (r, 0), (r, len(line))))
            return out
        if k in (":", "/", "?"):
            self.mode = "command" if k == ":" else "search"
            self.search_forward = k != "?"
            self.cmdline = ""
            out.append(("mode", self.mode))
            return out
        if k in ("n", "N"):
            if not self.last_search:
                return [("bell",)]
            self._search(self.last_search, cursor, self.search_forward == (k == "n"), n, out)
            return out
        if k in ("*", "#"):
            w = self._word_under(cursor)
            if not w:
                return [("bell",)]
            self.last_search, self.search_forward = r"\b" + re.escape(w) + r"\b", k == "*"
            self._search(self.last_search, cursor, k == "*", n, out)
            return out
        if k == "ctrl+s":
            return [("ex", "w")]
        return [("bell",)] if len(k) == 1 else []

    def _insert(self, out: list, loc: Loc) -> list:
        self.mode = "insert"
        out.append(("move", loc))
        out.append(("mode", "insert"))
        return out

    def _feed_visual(self, k: str, cursor: Loc, n: int, height: int, out: list) -> list:
        lines = self._lines
        line_mode = self.mode == "vline"
        if k in ("v", "V"):
            want = "vline" if k == "V" else "visual"
            if self.mode == want:
                self.mode = "normal"
                out.append(("mode", "normal"))
                out.append(("move", self._clamp(cursor)))
                return out
            self.mode = want
            line_mode = want == "vline"
            out.append(("mode", want))
            out.extend(self._visual_sel(cursor, line_mode))
            return out
        mv = self._motion(k, cursor, n, height)
        if mv is not None:
            target = self._clamp(mv[0])
            out.append(("move", target))
            out.extend(self._visual_sel(target, line_mode))
            return out
        if k in ("d", "x", "y", "c", ">", "<", "delete", "D", "X", "Y", "C", "S", "R"):
            op = {"x": "d", "delete": "d", "D": "d", "X": "d", "Y": "y", "C": "c", "S": "c", "R": "c"}.get(k, k)
            linewise = line_mode or k in ("D", "X", "Y", "C", "S", "R")
            a, b = sorted((self.anchor, cursor))
            self.mode = "normal"
            out.append(("mode", "normal"))
            if linewise:
                self._apply_op(op, a, b, True, out)
            else:
                b = (b[0], min(len(lines[b[0]]), b[1] + 1))
                self._apply_op(op, a, b, False, out)
            if self.mode == "insert":
                pass
            return out
        if k in ("p", "P"):
            a, b = sorted((self.anchor, cursor))
            reg, lw = self.register, self.reg_linewise
            self.mode = "normal"
            out.append(("mode", "normal"))
            if line_mode:
                s, e = (a[0], 0), (b[0], len(lines[b[0]]))
            else:
                s, e = a, (b[0], min(len(lines[b[0]]), b[1] + 1))
            text = reg[:-1] if lw and reg.endswith("\n") else reg
            out.append(("edit", s, e, text))
            out.append(("move", s))
            return out
        if k == ":":
            self.mode, self.cmdline = "command", ""
            out.append(("mode", "command"))
            return out
        return [("bell",)]

    def _visual_sel(self, cursor: Loc, line_mode: bool) -> list:
        lines = self._lines
        a = self.anchor
        if line_mode:
            r1, r2 = sorted((a[0], cursor[0]))
            if cursor[0] >= a[0]:
                return [("select", (r1, 0), (r2, len(lines[r2])))]
            return [("select", (r2, len(lines[r2])), (r1, 0))]
        if cursor >= a:
            return [("select", a, (cursor[0], min(len(lines[cursor[0]]), cursor[1] + 1)))]
        return [("select", (a[0], min(len(lines[a[0]]), a[1] + 1)), cursor)]

    def _feed_cmdline(self, k: str, key: str, cursor: Loc, out: list) -> list:
        was_search = self.mode == "search"
        if key in ("escape", "ctrl+c"):
            self.mode, self.cmdline = "normal", ""
            out.append(("mode", "normal"))
            return out
        if key == "backspace":
            if not self.cmdline:
                self.mode = "normal"
                out.append(("mode", "normal"))
            else:
                self.cmdline = self.cmdline[:-1]
                out.append(("mode", self.mode))
            return out
        if key == "enter":
            cmd = self.cmdline.strip()
            self.mode, self.cmdline = "normal", ""
            out.append(("mode", "normal"))
            if was_search:
                if cmd:
                    self.last_search = cmd
                if self.last_search:
                    self._search(self.last_search, cursor, self.search_forward, 1, out)
                return out
            if not cmd:
                return out
            if cmd.isdigit():
                t = max(0, min(len(self._lines) - 1, int(cmd) - 1))
                out.append(("move", (t, first_nonblank(self._lines[t]))))
                return out
            if cmd == "$":
                t = len(self._lines) - 1
                out.append(("move", (t, first_nonblank(self._lines[t]))))
                return out
            out.append(("ex", cmd))
            return out
        if len(k) == 1:
            self.cmdline += k
            out.append(("mode", self.mode))
        return out


def apply_ops(lines: list[str], cursor: Loc, ops: list) -> tuple[list[str], Loc]:
    """Áp danh sách thao tác lên danh sách dòng (dùng cho test; widget dùng API của TextArea)."""
    text = "\n".join(lines)
    for op in ops:
        if op[0] == "edit":
            _, a, b, s = op
            cur = text.split("\n")

            def off(loc):
                return sum(len(x) + 1 for x in cur[:loc[0]]) + loc[1]
            text = text[:off(a)] + s + text[off(b):]
        elif op[0] in ("move", "move_v"):
            loc = op[1]
            cur = text.split("\n")
            r = max(0, min(loc[0], len(cur) - 1))
            c = first_nonblank(cur[r]) if loc[1] is None else min(loc[1], len(cur[r]))
            cursor = (r, c)
    return text.split("\n"), cursor
