"""Nhắc file/thư mục bằng @: tìm gợi ý cho TUI và đổi @đường-dẫn sang cú pháp của từng agent CLI.

Trong prompt, ateam dùng một dạng chung: `@đường/dẫn` (có dấu cách thì `@"đường dẫn"`). Ngay trước khi
chạy agent, `render()` đổi mỗi lần nhắc (chỉ khi đường dẫn có thật) theo `file_ref` của agent, và
trả về cờ đính kèm file (`file_args`) cho CLI nào đính file bằng cờ thay vì cú pháp trong prompt.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path

from .clipboard import is_image
from .i18n import tr

# Cú pháp mặc định theo tên lệnh (command[0]). Ghi đè từng agent bằng file_ref / file_args trong config.
#   file_ref   cách viết đường dẫn trong prompt; {path} được thay
#   file_args  cờ thêm vào lệnh cho mỗi file/thư mục được nhắc (trước prompt)
SYNTAX: dict[str, tuple[str, list[str]]] = {
    "claude": ("@{path}", []),             # Claude Code đọc @file ngay trong prompt
    "agy": ("@{path}", []),                # Antigravity: @file như Gemini CLI
    "grok": ("@{path}", []),               # Grok Build: @file trong prompt
    "gemini": ("@{path}", []),
    "codex": ("{path}", []),               # codex exec không có @ (chỉ TUI có) -> đường dẫn thường
    "opencode": ("{path}", ["-f", "{path}"]),  # opencode run đính file bằng -f/--file
}
DEFAULT_SYNTAX = ("{path}", [])

# Ảnh (png, jpg… — xem clipboard.IMAGE_EXTS): CLI nào đính ảnh bằng cờ riêng thì dùng cờ này thay cho
# file_args; đường dẫn trong prompt vẫn viết theo file_ref. Ghi đè bằng image_args trong config.
# codex: `-i/--image` nhận nhiều giá trị, dạng `--image=…` để nó không nuốt luôn prompt phía sau.
IMAGE_ARGS: dict[str, list[str]] = {
    "codex": ["--image={path}"],
}

IGNORE_DIRS = {".git", ".ateam", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache",
               ".pytest_cache", ".ruff_cache", ".tox", ".idea", ".next", ".cache", "dist", "build",
               "target", ".DS_Store"}
MAX_ENTRIES = 50000

# @ đứng đầu chuỗi hoặc sau khoảng trắng / dấu mở ngoặc (không bắt email, a@b, codex@xhigh)
MENTION_RE = re.compile(r'(?<![^\s(\[{"\'`])@(?:"([^"\n]+)"|([^\s"\'`<>|]+))')
TRAILING = ".,:;!?)]}'\""


def syntax_for(binary: str, file_ref: str | None = None,
               file_args: list[str] | None = None) -> tuple[str, list[str]]:
    ref, args = SYNTAX.get(os.path.basename(binary or ""), DEFAULT_SYNTAX)
    return (file_ref if file_ref else ref), (list(file_args) if file_args is not None else list(args))


def image_args_for(binary: str, file_args: list[str] | None = None,
                   image_args: list[str] | None = None) -> list[str]:
    if image_args is not None:
        return list(image_args)
    own = IMAGE_ARGS.get(os.path.basename(binary or ""))
    return list(own) if own is not None else syntax_for(binary, None, file_args)[1]


def describe(binary: str, file_ref: str | None = None, file_args: list[str] | None = None,
             image_args: list[str] | None = None) -> str:
    """Mô tả ngắn cú pháp nhắc file của agent, vd "@src/app.py" hoặc "src/app.py + -f src/app.py"."""
    ref, args = syntax_for(binary, file_ref, file_args)
    out = ref.replace("{path}", "src/app.py")
    if args:
        out += " + " + " ".join(a.replace("{path}", "src/app.py") for a in args)
    img = image_args_for(binary, file_args, image_args)
    if img != args:
        out += tr(" · ảnh: ") + ref.replace("{path}", "a.png")
        if img:
            out += " + " + " ".join(a.replace("{path}", "a.png") for a in img)
    return out


def quote(path: str) -> str:
    """Dạng chung ateam chèn vào ô nhập."""
    return f'@"{path}"' if any(c.isspace() for c in path) else f"@{path}"


def _exists(path: str, roots: list[Path]) -> bool:
    p = Path(os.path.expanduser(path))
    if p.is_absolute():
        return p.exists()
    return any((r / p).exists() for r in roots)


def find(prompt: str, roots: list[Path]) -> list[tuple[int, int, str, str]]:
    """Các lần nhắc có thật trong prompt: (đầu, cuối, đường dẫn, phần đuôi bị cắt ra)."""
    out = []
    for m in MENTION_RE.finditer(prompt):
        if m.group(1) is not None:
            if _exists(m.group(1), roots):
                out.append((m.start(), m.end(), m.group(1), ""))
            continue
        path, tail = m.group(2), ""
        while path and not _exists(path, roots) and path[-1] in TRAILING:
            path, tail = path[:-1], path[-1] + tail
        if path and _exists(path, roots):
            out.append((m.start(), m.end(), path, tail))
    return out


def _located(path: str, roots: list[Path]) -> str:
    """Đường dẫn tương đối không có trong thư mục làm việc (roots[0], vd worktree) nhưng có ở thư mục
    dự án (vd ảnh dán ở .ateam/images, bị git bỏ qua) -> đổi sang đường dẫn tuyệt đối để agent mở được."""
    p = Path(os.path.expanduser(path))
    if p.is_absolute() or not roots or (roots[0] / p).exists():
        return path
    for r in roots[1:]:
        if (r / p).exists():
            return str(r / p)
    return path


def render(prompt: str, binary: str, roots: list[Path], *, file_ref: str | None = None,
           file_args: list[str] | None = None,
           image_args: list[str] | None = None) -> tuple[str, list[str]]:
    """Đổi @đường-dẫn sang cú pháp của agent. Trả (prompt mới, cờ đính kèm file/ảnh)."""
    ref, args = syntax_for(binary, file_ref, file_args)
    img_args = image_args_for(binary, file_args, image_args)
    found = find(prompt, roots)
    if not found:
        return prompt, []
    parts, extra, seen, last = [], [], set(), 0
    for start, end, path, tail in found:
        path = _located(path, roots)
        spaced = any(c.isspace() for c in path)
        shown = f'"{path}"' if spaced and ref.startswith("@") else path
        parts.append(prompt[last:start] + ref.replace("{path}", shown) + tail)
        last = end
        flags = img_args if is_image(path) else args
        if flags and path not in seen:
            seen.add(path)
            extra += [a.replace("{path}", path) for a in flags]
    parts.append(prompt[last:])
    return "".join(parts), extra


def insert_args(argv: list[str], prompt: str, extra: list[str],
                prompt_flags: tuple[str, ...] = ("-p", "--print", "--prompt")) -> list[str]:
    """Chèn cờ ngay trước prompt (và trước -p nếu prompt đi sau cờ đó)."""
    if not extra:
        return argv
    idx = next((i for i in range(len(argv) - 1, -1, -1) if argv[i] == prompt), len(argv))
    if 0 < idx < len(argv) and argv[idx - 1] in prompt_flags:
        idx -= 1
    elif idx == len(argv) - 1 and not extra[-1].startswith("-"):
        # prompt là đối số vị trí cuối, ngay sau giá trị của cờ: cờ nhận nhiều giá trị (opencode -f là
        # mảng yargs, kể cả dạng --file=) sẽ nuốt luôn prompt thành "file" -> "File not found: <prompt>".
        # "--" chấm dứt phần cờ.
        extra = list(extra) + ["--"]
    return argv[:idx] + list(extra) + argv[idx:]


# ---------------------------------------------------------------- gợi ý trong TUI
def walk(root: Path, limit: int = MAX_ENTRIES) -> list[str]:
    """Liệt kê file + thư mục (thư mục có '/' ở cuối), bỏ thư mục rác. Dùng khi không có git."""
    out: list[str] = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in IGNORE_DIRS)
        rel = os.path.relpath(d, root)
        pre = "" if rel == "." else rel.replace(os.sep, "/") + "/"
        out += [pre + x + "/" for x in dirs]
        out += [pre + f for f in sorted(files) if f not in IGNORE_DIRS]
        if len(out) >= limit:
            break
    return out[:limit]


def with_dirs(files: list[str]) -> list[str]:
    """Thêm các thư mục cha (có '/') vào danh sách file của git."""
    dirs: set[str] = set()
    for f in files:
        parts = f.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]) + "/")
    return sorted(dirs) + files


def score(entry: str, query: str) -> int | None:
    """Điểm khớp (cao hơn = tốt hơn); None nếu không khớp."""
    e, q = entry.lower(), query.lower()
    if not q:
        return 100 - entry.rstrip("/").count("/") * 10 + (5 if entry.endswith("/") else 0)
    base = e.rstrip("/").rsplit("/", 1)[-1]
    depth = e.rstrip("/").count("/")
    if e.startswith(q):
        if "/" in q.rstrip("/") or q.endswith("/"):
            # đang đi sâu vào thư mục: ưu tiên con trực tiếp
            rest = e[len(q):].rstrip("/")
            return 1000 - rest.count("/") * 50 + (5 if e.endswith("/") else 0)
        return 900 - depth * 20 - len(e)
    if base.startswith(q):
        return 800 - depth * 10 - len(base)
    i = base.find(q)
    if i >= 0:
        return 600 - i - depth * 10
    i = e.find(q)
    if i >= 0:
        return 400 - i - depth * 5
    # khớp rải rác (fuzzy): các ký tự của q xuất hiện theo thứ tự
    pos, gaps = -1, 0
    for ch in q:
        nxt = e.find(ch, pos + 1)
        if nxt < 0:
            return None
        gaps += nxt - pos - 1
        pos = nxt
    return 200 - gaps - depth * 5


def search(entries: list[str], query: str, limit: int = 12) -> list[str]:
    if not query:
        top = [e for e in entries if "/" not in e.rstrip("/")]
        return sorted(top, key=lambda e: (not e.endswith("/"), e.lower()))[:limit]
    ranked = []
    q = query.lower()
    for e in entries:
        if q.endswith("/") and e.lower() == q:
            continue  # đang ở trong thư mục này rồi
        s = score(e, query)
        if s is not None:
            ranked.append((-s, e.lower(), e))
    ranked.sort()
    return [e for _, _, e in ranked[:limit]]


class FileIndex:
    """Danh sách file/thư mục của dự án cho gợi ý @, làm mới tối đa mỗi `ttl` giây."""

    def __init__(self, root: Path, ttl: float = 20.0):
        self.root = root
        self.ttl = ttl
        self.entries: list[str] = []
        self.loaded_at = 0.0
        self._task: asyncio.Task | None = None

    def stale(self) -> bool:
        return time.time() - self.loaded_at > self.ttl

    async def refresh(self) -> list[str]:
        if self._task and not self._task.done():
            return await self._task
        self._task = asyncio.ensure_future(self._load())
        return await self._task

    async def _load(self) -> list[str]:
        entries = await self._git_files()
        if entries is None:
            entries = await asyncio.get_running_loop().run_in_executor(None, walk, self.root)
        self.entries = entries
        self.loaded_at = time.time()
        return entries

    async def _git_files(self) -> list[str] | None:
        """File theo git (tôn trọng .gitignore, gồm cả file chưa add). None nếu không phải repo git."""
        if not (self.root / ".git").exists():
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "ls-files", "-co", "--exclude-standard", "-z", cwd=str(self.root),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await proc.communicate()
        except Exception:
            return None
        if proc.returncode != 0:
            return None
        files = [f for f in out.decode("utf-8", "replace").split("\0") if f]
        files = [f for f in files if not any(p in IGNORE_DIRS for p in f.split("/")[:-1])]
        return with_dirs(files[:MAX_ENTRIES])
