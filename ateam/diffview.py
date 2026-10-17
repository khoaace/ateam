"""Xem diff kiểu VS Code: bóc output `git diff`, ghép dòng hai cột, tô màu cú pháp và chữ đổi trong dòng.

Không phụ thuộc Textual (chỉ rich + pygments, vốn đi kèm Textual) để test được riêng.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.style import Style
from rich.syntax import Syntax
from rich.text import Span, Text
from .i18n import tr

MAX_ROWS = 4000  # mỗi file; dài hơn thì cắt, mở bằng VS Code (phím o) để xem đủ
# Dòng rất dài (file sinh tự động: tsconfig.tsbuildinfo, *.min.js, lock một dòng — có thể hàng trăm nghìn ký tự)
# chỉ hiện phần đầu như VS Code, và không so từng chữ: difflib chạy theo bình phương số token, một dòng như vậy
# làm treo cả app (vòng lặp sự kiện của web / TUI đứng hàng giờ).
MAX_LINE_CHARS = 2000
MAX_WORD_TOKENS = 600

# màu nền giống VS Code (Dark+); Textual tự hạ xuống 256 màu nếu terminal không có truecolor.
# Theme sáng (set_light) dùng màu kiểu GitHub light.
ADD_BG, DEL_BG = "on #1e3a29", "on #4b1818"
ADD_WORD, DEL_WORD = "on #2f6f45", "on #8b2c2c"
EMPTY_BG = "on #262626"
HUNK_STYLE = "#6a9fb5 on #1b2633"
NUM_STYLE = "#6e7681"
SYNTAX_THEME = "monokai"
_DARK = dict(ADD_BG=ADD_BG, DEL_BG=DEL_BG, ADD_WORD=ADD_WORD, DEL_WORD=DEL_WORD, EMPTY_BG=EMPTY_BG,
             HUNK_STYLE=HUNK_STYLE, NUM_STYLE=NUM_STYLE, SYNTAX_THEME=SYNTAX_THEME)
_LIGHT = dict(ADD_BG="on #dafbe1", DEL_BG="on #ffebe9", ADD_WORD="on #aceebb", DEL_WORD="on #ffcecb",
              EMPTY_BG="on #f6f8fa", HUNK_STYLE="#0550ae on #ddf4ff", NUM_STYLE="#8c959f",
              SYNTAX_THEME="friendly")


def set_light(light: bool) -> None:
    """Đổi bảng màu diff theo theme sáng/tối của app."""
    globals().update(_LIGHT if light else _DARK)
STATUS_STYLE = {"M": "yellow", "A": "green", "D": "red", "R": "magenta"}

TOKEN_RE = re.compile(r"\w+|\s+|[^\w\s]")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
DIFF_GIT_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")


@dataclass
class DiffLine:
    kind: str                 # " " giữ nguyên · "-" xoá · "+" thêm
    old_no: Optional[int]
    new_no: Optional[int]
    text: str


@dataclass
class Hunk:
    header: str
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    path: str
    old_path: str = ""
    status: str = "M"         # M sửa · A thêm · D xoá · R đổi tên
    binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def added(self) -> int:
        return sum(ln.kind == "+" for h in self.hunks for ln in h.lines)

    @property
    def removed(self) -> int:
        return sum(ln.kind == "-" for h in self.hunks for ln in h.lines)


@dataclass
class DiffSet:
    """Mọi file đổi của một task. head None = thư mục làm việc (chế độ shared)."""
    tid: int
    title: str
    files: list[FileDiff]
    base: str
    head: Optional[str]

    @property
    def added(self) -> int:
        return sum(f.added for f in self.files)

    @property
    def removed(self) -> int:
        return sum(f.removed for f in self.files)


def _unquote(p: str) -> str:
    # git đặt đường dẫn có ký tự đặc biệt trong ngoặc kép (đã tắt core.quotePath nên chữ Việt giữ nguyên)
    if len(p) >= 2 and p[0] == p[-1] == '"':
        p = p[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return p


def clip(text: str) -> str:
    """Dòng hiển thị trong diff: quá MAX_LINE_CHARS thì cắt, ghi số ký tự bị ẩn."""
    if len(text) <= MAX_LINE_CHARS:
        return text
    return text[:MAX_LINE_CHARS] + tr(" … (+{n} ký tự — dòng quá dài, mở file để xem đủ)", n=len(text) - MAX_LINE_CHARS)


def parse_unified(text: str) -> list[FileDiff]:
    """Bóc output `git diff -M --no-color` thành danh sách file."""
    files: list[FileDiff] = []
    fd: FileDiff | None = None
    hunk: Hunk | None = None
    old_no = new_no = 0
    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            m = DIFF_GIT_RE.match(raw)
            path = _unquote(m.group(2)) if m else raw[len("diff --git "):]
            fd = FileDiff(path=path, old_path=_unquote(m.group(1)) if m else path)
            files.append(fd)
            hunk = None
            continue
        if fd is None:
            continue
        if hunk is not None and raw[:1] in (" ", "-", "+", "\\", ""):
            if raw.startswith("\\"):  # "\ No newline at end of file"
                continue
            kind, body = (raw[0], clip(raw[1:])) if raw else (" ", "")
            if kind == "-":
                hunk.lines.append(DiffLine("-", old_no, None, body))
                old_no += 1
            elif kind == "+":
                hunk.lines.append(DiffLine("+", None, new_no, body))
                new_no += 1
            else:
                hunk.lines.append(DiffLine(" ", old_no, new_no, body))
                old_no += 1
                new_no += 1
            continue
        m = HUNK_RE.match(raw)
        if m:
            old_no, new_no = int(m.group(1)), int(m.group(3))
            hunk = Hunk(raw)
            fd.hunks.append(hunk)
        elif raw.startswith("new file mode"):
            fd.status = "A"
        elif raw.startswith("deleted file mode"):
            fd.status = "D"
        elif raw.startswith("rename from "):
            fd.old_path, fd.status = _unquote(raw[len("rename from "):]), "R"
        elif raw.startswith("rename to "):
            fd.path = _unquote(raw[len("rename to "):])
        elif raw.startswith("Binary files ") or raw.startswith("GIT binary patch"):
            fd.binary = True
        elif raw.startswith("--- ") and raw[4:] != "/dev/null":
            fd.old_path = _unquote(raw[4:])[2:] if raw[4:].lstrip('"').startswith("a/") else fd.old_path
        elif raw.startswith("+++ ") and raw[4:] != "/dev/null":
            fd.path = _unquote(raw[4:])[2:] if raw[4:].lstrip('"').startswith("b/") else fd.path
    return files


def added_file(path: str, text: str | None) -> FileDiff:
    """File mới chưa track (chế độ shared): mọi dòng là dòng thêm. text None = file nhị phân."""
    fd = FileDiff(path=path, old_path=path, status="A", binary=text is None)
    if text:
        lines = text.splitlines()
        fd.hunks.append(Hunk(f"@@ -0,0 +1,{len(lines)} @@",
                             [DiffLine("+", None, i + 1, clip(ln)) for i, ln in enumerate(lines)]))
    return fd


# ---------------------------------------------------------------- tô màu
def _lexer(path: str) -> str:
    from pygments.lexers import get_lexer_for_filename
    from pygments.util import ClassNotFound
    try:
        lx = get_lexer_for_filename(path, stripnl=False)
        return lx.aliases[0] if lx.aliases else "text"
    except ClassNotFound:
        return "text"


def highlight_lines(lines: list[str], lexer: str) -> list[Text]:
    """Tô cả khối một lần (chuỗi/comment nhiều dòng vẫn đúng) rồi tách lại theo dòng."""
    if not lines:
        return []
    code = "\n".join(ln.expandtabs(4) for ln in lines)
    if lexer == "text":
        parts = [Text(ln) for ln in code.split("\n")]
    else:
        hl = Syntax(code, lexer, theme=SYNTAX_THEME, background_color="default").highlight(code)
        hl.style = ""
        # bỏ màu nền của theme khỏi từng token, để nền dòng thêm/xoá phủ kín cả chữ
        hl.spans[:] = [Span(sp.start, sp.end, _fg_only(sp.style)) for sp in hl.spans]
        parts = hl.split("\n", allow_blank=True)
    parts = parts[:len(lines)]
    while len(parts) < len(lines):
        parts.append(Text())
    return parts


def _fg_only(style) -> Style:
    st = Style.parse(style) if isinstance(style, str) else style
    return Style(color=st.color, bold=st.bold, italic=st.italic, underline=st.underline)


def word_spans(a: str, b: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Đoạn khác nhau giữa dòng cũ a và dòng mới b, so theo từ như VS Code (không vụn từng ký tự).
    Hai dòng khác hẳn nhau thì không tô gì (cả dòng đã có nền)."""
    ta, tb = TOKEN_RE.findall(a), TOKEN_RE.findall(b)
    if len(ta) > MAX_WORD_TOKENS or len(tb) > MAX_WORD_TOKENS:
        return [], []  # quá dài để so từng chữ (difflib bình phương): chỉ tô nền cả dòng
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    # độ giống tính trên chữ (bỏ khoảng trắng, vốn trùng nhau ở hầu hết mọi cặp dòng)
    same = sum(len(t) for blk in sm.get_matching_blocks() for t in ta[blk.a:blk.a + blk.size] if not t.isspace())
    total = sum(len(t) for t in ta + tb if not t.isspace())
    if not total or 2 * same / total < 0.3:
        return [], []
    pa = [0]
    for tok in ta:
        pa.append(pa[-1] + len(tok))
    pb = [0]
    for tok in tb:
        pb.append(pb[-1] + len(tok))
    old, new = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if i2 > i1:
            old.append((pa[i1], pa[i2]))
        if j2 > j1:
            new.append((pb[j1], pb[j2]))
    return old, new


def _styled_hunk(hunk: Hunk, lexer: str) -> dict[int, Text]:
    """Text đã tô (cú pháp + chữ đổi) cho từng dòng của hunk, theo chỉ số dòng."""
    old_idx = [i for i, ln in enumerate(hunk.lines) if ln.kind != "+"]
    new_idx = [i for i, ln in enumerate(hunk.lines) if ln.kind != "-"]
    out: dict[int, Text] = {}
    for idx, txt in zip(old_idx, highlight_lines([hunk.lines[i].text for i in old_idx], lexer)):
        out[idx] = txt
    for idx, txt in zip(new_idx, highlight_lines([hunk.lines[i].text for i in new_idx], lexer)):
        if hunk.lines[idx].kind == "+":
            out[idx] = txt
    for dels, adds in _change_blocks(hunk):
        for d, a in zip(dels, adds):
            o, n = word_spans(hunk.lines[d].text.expandtabs(4), hunk.lines[a].text.expandtabs(4))
            for s, e in o:
                out[d].stylize(DEL_WORD, s, e)
            for s, e in n:
                out[a].stylize(ADD_WORD, s, e)
    return out


def _change_blocks(hunk: Hunk) -> list[tuple[list[int], list[int]]]:
    """Các khối thay đổi liên tiếp: (chỉ số dòng xoá, chỉ số dòng thêm)."""
    blocks, dels, adds = [], [], []
    for i, ln in enumerate(hunk.lines + [DiffLine(" ", None, None, "")]):
        if ln.kind == "-":
            if adds:  # "-" sau "+": khối mới
                blocks.append((dels, adds))
                dels, adds = [], []
            dels.append(i)
        elif ln.kind == "+":
            adds.append(i)
        elif dels or adds:
            blocks.append((dels, adds))
            dels, adds = [], []
    return blocks


def split_rows(hunk: Hunk) -> list[tuple[Optional[int], Optional[int]]]:
    """Ghép dòng cho kiểu hai cột: (chỉ số dòng bên trái, chỉ số dòng bên phải). Trong mỗi khối thay đổi,
    dòng xoá đối diện dòng thêm; phía ngắn hơn để trống (None)."""
    rows: list[tuple[Optional[int], Optional[int]]] = []
    blocks = {b[0][0] if b[0] else b[1][0]: b for b in _change_blocks(hunk)}
    i = 0
    while i < len(hunk.lines):
        if hunk.lines[i].kind == " ":
            rows.append((i, i))
            i += 1
            continue
        dels, adds = blocks[i]
        for k in range(max(len(dels), len(adds))):
            rows.append((dels[k] if k < len(dels) else None, adds[k] if k < len(adds) else None))
        i = max(dels + adds) + 1
    return rows


# ---------------------------------------------------------------- vẽ
def _cell(t: Text | None, width: int, bg: str) -> Text:
    if t is None:
        return Text(" " * width, EMPTY_BG)
    c = t.copy()
    c.truncate(width, overflow="ellipsis", pad=True)
    c.style = bg  # nền dòng là style gốc: màu cú pháp và nền chữ đổi (span) nằm đè lên
    return c


def _num(n: Optional[int], w: int) -> Text:
    return Text((str(n) if n is not None else "").rjust(w) + " ", NUM_STYLE)


def _notice(fd: FileDiff) -> Text | None:
    if fd.binary:
        return Text(tr("  (file nhị phân — không hiện nội dung; nhấn o để mở bằng VS Code)"), "dim italic")
    if not fd.hunks:
        what = {"R": tr("chỉ đổi tên, nội dung giữ nguyên"), "A": tr("file rỗng"), "D": tr("file rỗng bị xoá")}
        return Text(f"  ({what.get(fd.status, tr('chỉ đổi quyền file'))})", "dim italic")
    return None


def render(fd: FileDiff, width: int, split: bool) -> tuple[Text, list[int]]:
    """Vẽ một file: trả (Text nhiều dòng, chỉ số dòng bắt đầu mỗi hunk — cho phím nhảy hunk)."""
    note = _notice(fd)
    if note is not None:
        return note, []
    lexer = _lexer(fd.path)
    numw = max(3, len(str(max((ln.old_no or ln.new_no or 0) for h in fd.hunks for ln in h.lines))))
    lines: list[Text] = []
    starts: list[int] = []
    for h in fd.hunks:
        if len(lines) >= MAX_ROWS:
            break
        starts.append(len(lines))
        head = Text(f" ⋯ {h.header}")
        head.truncate(width, overflow="ellipsis", pad=True)
        head.stylize(HUNK_STYLE)
        lines.append(head)
        styled = _styled_hunk(h, lexer)
        if split:
            side = max(8, (width - 2 * (numw + 1) - 1) // 2)
            for li, ri in split_rows(h):
                if len(lines) >= MAX_ROWS:
                    break
                row = Text()
                lt = None if li is None else styled[li]
                rt = None if ri is None else styled[ri]
                lk = None if li is None else h.lines[li].kind
                rk = None if ri is None else h.lines[ri].kind
                row.append_text(_num(None if li is None else h.lines[li].old_no, numw))
                row.append_text(_cell(lt, side, DEL_BG if lk == "-" else ""))
                row.append("│", NUM_STYLE)
                row.append_text(_num(None if ri is None else h.lines[ri].new_no, numw))
                row.append_text(_cell(rt, side, ADD_BG if rk == "+" else ""))
                lines.append(row)
        else:
            body = max(8, width - 2 * (numw + 1) - 2)
            for i, ln in enumerate(h.lines):
                if len(lines) >= MAX_ROWS:
                    break
                bg = {"-": DEL_BG, "+": ADD_BG}.get(ln.kind, "")
                row = Text()
                row.append_text(_num(ln.old_no if ln.kind != "+" else None, numw))
                row.append_text(_num(ln.new_no if ln.kind != "-" else None, numw))
                sign = Text(ln.kind if ln.kind != " " else " ", "bold green" if ln.kind == "+" else
                            "bold red" if ln.kind == "-" else "")
                sign.append(" ")
                if bg:
                    sign.stylize(bg)
                row.append_text(sign)
                row.append_text(_cell(styled[i], body, bg))
                lines.append(row)
    if len(lines) >= MAX_ROWS:
        lines.append(Text(tr("  … còn nữa — file quá dài, nhấn o để xem đủ bằng VS Code"), "yellow"))
    return Text("\n").join(lines), starts


def file_label(fd: FileDiff, width: int = 40) -> Text:
    """Một dòng trong danh sách file: trạng thái, tên file (đậm) + thư mục (mờ), +a −r."""
    t = Text()
    t.append(fd.status + " ", "bold " + STATUS_STYLE.get(fd.status, ""))
    p = Path(fd.path)
    parent = "" if str(p.parent) == "." else str(p.parent) + "/"
    t.append(p.name, "bold")
    if parent:
        t.append(" " + parent, "dim")
    stats = Text()
    if fd.added:
        stats.append(f" +{fd.added}", "green")
    if fd.removed:
        stats.append(f" −{fd.removed}", "red")
    if fd.binary:
        stats.append(" bin", "dim")
    room = max(4, width - stats.cell_len)
    t.truncate(room, overflow="ellipsis", pad=True)
    t.append_text(stats)
    return t
