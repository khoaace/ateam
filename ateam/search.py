"""Tìm & thay trong toàn dự án (tab Code của web, ⌘⇧F) — như ô Search của VS Code.

Chạy trên danh sách file của `mentions.FileIndex` (git ls-files: tôn trọng .gitignore), bỏ file nhị phân, quá lớn
hoặc không phải UTF-8. Tuỳ chọn: phân biệt hoa/thường, nguyên từ, regex (cú pháp Python `re`), lọc file gồm / bỏ
qua (danh sách cách nhau dấu phẩy: `src`, `*.ts`, `src/**/*.tsx`). Chuỗi thay thế ở chế độ regex hiểu `$1`, `$&`,
`$$`, `\\n`, `\\t` như VS Code. Ghi lại giữ nguyên kiểu xuống dòng, BOM và quyền của file.
"""

from __future__ import annotations

import bisect
import os
import re
import tempfile
from fnmatch import fnmatch
from pathlib import Path

MAX_FILE = 2 * 1024 * 1024  # file lớn hơn: bỏ qua
MAX_MATCHES = 3000          # dừng khi đủ chừng này kết quả (báo truncated)
PREVIEW = 140               # độ dài dòng xem trước quanh chỗ khớp


def compile_query(query: str, regex: bool = False, case: bool = False, word: bool = False) -> re.Pattern:
    """Mẫu tìm; ValueError (kèm lỗi của re) nếu regex sai."""
    src = query if regex else re.escape(query)
    if word:
        src = rf"\b(?:{src})\b"
    try:
        return re.compile(src, (0 if case else re.IGNORECASE) | re.MULTILINE)
    except re.error as e:
        raise ValueError(str(e)) from e


def _patterns(text: str) -> list[str]:
    return [p.strip().strip("/") for p in (text or "").split(",") if p.strip().strip("/")]


def path_matches(path: str, pat: str) -> bool:
    """`src` = thư mục/file tên src ở bất kỳ đâu; có * ? [ thì so glob với cả đường dẫn lẫn tên file."""
    base = path.rsplit("/", 1)[-1]
    if not any(c in pat for c in "*?["):
        return path == pat or path.startswith(pat + "/") or f"/{pat}/" in f"/{path}" or base == pat
    pat = pat.replace("**/", "*")
    return fnmatch(path, pat) or fnmatch(base, pat)


def wanted(path: str, include: str = "", exclude: str = "") -> bool:
    inc, exc = _patterns(include), _patterns(exclude)
    if inc and not any(path_matches(path, p) for p in inc):
        return False
    return not any(path_matches(path, p) for p in exc)


def expand(template: str, m: re.Match, regex: bool) -> str:
    """Chuỗi thay cho một chỗ khớp. Không phải regex: nguyên văn."""
    if not regex:
        return template
    out, i, n = [], 0, len(template)
    while i < n:
        c = template[i]
        nxt = template[i + 1] if i + 1 < n else ""
        if c == "$" and nxt == "$":
            out.append("$")
            i += 2
        elif c == "$" and nxt == "&":
            out.append(m.group(0))
            i += 2
        elif c == "$" and nxt.isdigit():  # $1…$99: lấy 2 chữ số nếu có nhóm đó, không thì 1
            two = template[i + 1:i + 3]
            if len(two) == 2 and two.isdigit() and 10 <= int(two) <= m.re.groups:
                k, width = int(two), 2
            elif int(nxt) <= m.re.groups:
                k, width = int(nxt), 1
            else:
                out.append(c)
                i += 1
                continue
            out.append(m.group(k) or "")
            i += 1 + width
        elif c == "\\" and nxt in ("n", "t", "\\"):
            out.append({"n": "\n", "t": "\t", "\\": "\\"}[nxt])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def read_text(path: Path) -> tuple[str, str] | None:
    """(nội dung, mã hoá) của file chữ UTF-8; None nếu nhị phân / quá lớn / không đọc được."""
    try:
        if path.stat().st_size > MAX_FILE:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    enc = "utf-8-sig" if data.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        return data.decode(enc), enc
    except UnicodeDecodeError:
        return None


def _preview(line: str, start: int, end: int) -> tuple[str, int, int]:
    """Cắt dòng dài quanh chỗ khớp; trả (đoạn, vị trí bắt đầu / kết thúc chỗ khớp trong đoạn)."""
    end = min(end, len(line))
    if len(line) <= PREVIEW:
        return line, start, end
    left = max(0, start - 30)
    right = min(len(line), max(end, left + PREVIEW))
    pre = "…" if left else ""
    return pre + line[left:right] + ("…" if right < len(line) else ""), start - left + len(pre), end - left + len(pre)


def search(root: Path, files: list[str], query: str, *, regex: bool = False, case: bool = False,
           word: bool = False, include: str = "", exclude: str = "", replace: str | None = None,
           limit: int = MAX_MATCHES) -> dict:
    """{"files": [{"path", "matches": [{"line", "col", "len", "text", "s", "e", "repl"?}]}], "total", "truncated"}.
    line từ 1, col tính theo ký tự; s/e là vị trí chỗ khớp trong text (dòng xem trước)."""
    pat = compile_query(query, regex, case, word)
    out, total, truncated = [], 0, False
    for rel in files:
        if rel.endswith("/") or not wanted(rel, include, exclude):
            continue
        got = read_text(root / rel)
        if not got:
            continue
        text = got[0]
        starts: list[int] = []
        matches = []
        for m in pat.finditer(text):
            if m.end() == m.start():
                continue  # regex khớp rỗng (vd ^): bỏ
            if not starts:
                starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]
            ln = bisect.bisect_right(starts, m.start()) - 1
            ls = starts[ln]
            le = text.find("\n", ls)
            line = text[ls:le if le >= 0 else len(text)].rstrip("\r")
            col = m.start() - ls
            prev, s, e = _preview(line, col, col + (m.end() - m.start()))
            item = {"line": ln + 1, "col": col, "len": m.end() - m.start(), "text": prev, "s": s, "e": e}
            if replace is not None:
                item["repl"] = expand(replace, m, regex)
            matches.append(item)
            total += 1
            if total >= limit:
                truncated = True
                break
        if matches:
            out.append({"path": rel, "matches": matches})
        if truncated:
            break
    return {"files": out, "total": total, "truncated": truncated}


def write_text(path: Path, text: str, enc: str) -> None:
    """Ghi nguyên tử, giữ quyền file (chmod) — nội dung giữ nguyên \\r\\n vì không chuẩn hoá xuống dòng."""
    mode = path.stat().st_mode
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".ateam-replace-")
    try:
        with os.fdopen(fd, "w", encoding=enc, newline="") as f:
            f.write(text)
        os.chmod(tmp, mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def replace_in(root: Path, files: list[str], query: str, replacement: str, *, regex: bool = False,
               case: bool = False, word: bool = False) -> dict:
    """Thay mọi chỗ khớp trong các file (đường dẫn tương đối, bên gọi đã kiểm tra nằm trong dự án).
    Trả {"files": {đường dẫn: số chỗ đã thay}, "total"}."""
    pat = compile_query(query, regex, case, word)
    done: dict[str, int] = {}
    for rel in files:
        p = root / rel
        got = read_text(p)
        if not got:
            continue
        text, enc = got
        new, n = pat.subn(lambda m: expand(replacement, m, regex) if m.end() > m.start() else m.group(0), text)
        if n and new != text:
            write_text(p, new, enc)
            done[rel] = sum(1 for m in pat.finditer(text) if m.end() > m.start())
    return {"files": done, "total": sum(done.values())}
