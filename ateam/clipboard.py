"""Dán ảnh từ clipboard hệ thống vào ô nhập (Ctrl+V) và nhận ảnh kéo-thả vào terminal.

Terminal không truyền ảnh qua thao tác dán thường (Cmd+V chỉ gửi chữ), nên khi bấm Ctrl+V ateam tự
đọc clipboard bằng công cụ của hệ điều hành, lưu ảnh vào `.ateam/images/` rồi chèn `@đường/dẫn` vào
ô nhập. Từ đó ảnh đi theo đúng đường của `@file` (xem `mentions.render`): mỗi agent nhận ảnh theo
cú pháp CLI của nó (Claude/agy: `@ảnh` trong prompt, Codex: cờ `--image=…`, OpenCode: `-f ảnh`).

  macOS  : `pngpaste` nếu có, không thì `osascript` (có sẵn). Clipboard chứa file ảnh copy từ
           Finder thì dùng thẳng file đó.
  Linux  : `wl-paste` (Wayland) hoặc `xclip` (X11).
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import sys
import time
from pathlib import Path
from .i18n import tr

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic"}
KEEP_DAYS = 7  # ảnh dán cũ hơn chừng này ngày bị xoá khi dán ảnh mới

# osascript: ghi ảnh PNG trong clipboard ra file; nếu clipboard là file (copy trong Finder) thì
# trả đường dẫn của nó. In "OK", "FILE:<đường dẫn>" hoặc "NONE".
OSASCRIPT = """\
on run argv
  set outPath to item 1 of argv
  try
    set img to the clipboard as «class PNGf»
  on error
    try
      set f to the clipboard as «class furl»
      return "FILE:" & POSIX path of f
    on error
      return "NONE"
    end try
  end try
  set fh to open for access (POSIX file outPath) with write permission
  set eof fh to 0
  write img to fh
  close access fh
  return "OK"
end run"""


def is_image(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def looks_like_image(data: bytes) -> bool:
    return (data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8\xff")
            or data[:6] in (b"GIF87a", b"GIF89a") or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
            or data[:2] == b"BM" or data[:4] in (b"II*\x00", b"MM\x00*"))


def new_path(folder: Path, ext: str = ".png") -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    p = folder / f"paste-{stamp}{ext}"
    i = 2
    while p.exists():
        p = folder / f"paste-{stamp}-{i}{ext}"
        i += 1
    return p


def image_ext(data: bytes) -> str:
    """Đuôi file theo nội dung ảnh (dán từ trình duyệt có thể là JPEG/GIF/WebP, không chỉ PNG)."""
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:2] == b"BM":
        return ".bmp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return ".tiff"
    return ".png"


def save_image(data: bytes, folder: Path) -> Path:
    """Lưu ảnh dán từ trình duyệt (tab web) vào `.ateam/images/` như Ctrl+V của TUI. ValueError nếu không phải ảnh."""
    if not looks_like_image(data):
        raise ValueError("not an image")
    folder.mkdir(parents=True, exist_ok=True)
    prune(folder)
    p = new_path(folder, image_ext(data))
    p.write_bytes(data)
    return p


def prune(folder: Path, days: int = KEEP_DAYS) -> None:
    cutoff = time.time() - days * 86400
    for p in folder.glob("paste-*"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


def methods() -> list[str]:
    """Cách đọc clipboard dùng được trên máy này, theo thứ tự thử."""
    out = []
    if sys.platform == "darwin":
        if shutil.which("pngpaste"):
            out.append("pngpaste")
        if shutil.which("osascript"):
            out.append("osascript")
    else:
        if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
            out.append("wl-paste")
        if shutil.which("xclip"):
            out.append("xclip")
    return out


async def _run(argv: list[str], timeout: float = 5.0) -> tuple[int, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
    except OSError:
        return 127, b""
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, b""
    return proc.returncode or 0, out


def _saved(dest: Path) -> bool:
    try:
        with open(dest, "rb") as f:
            ok = looks_like_image(f.read(16))
    except OSError:
        return False
    if not ok:
        dest.unlink()
    return ok


async def _try(method: str, dest: Path) -> Path | None:
    if method == "pngpaste":
        code, _ = await _run(["pngpaste", str(dest)])
        return dest if code == 0 and _saved(dest) else None
    if method == "osascript":
        code, out = await _run(["osascript", "-e", OSASCRIPT, str(dest)])
        res = out.decode("utf-8", "replace").strip()
        if code == 0 and res == "OK" and _saved(dest):
            return dest
        if code == 0 and res.startswith("FILE:") and is_image(res[5:]) and Path(res[5:]).is_file():
            return Path(res[5:])
        return None
    if method == "wl-paste":
        code, types = await _run(["wl-paste", "--list-types"])
        argv = ["wl-paste", "--no-newline", "--type"]
    else:
        code, types = await _run(["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"])
        argv = ["xclip", "-selection", "clipboard", "-o", "-t"]
    names = types.decode("utf-8", "replace").split()
    mime = next((m for m in ("image/png", "image/jpeg", "image/webp", "image/gif") if m in names), None)
    if code != 0 or not mime:
        return None
    code, data = await _run(argv + [mime])
    if code != 0 or not looks_like_image(data):
        return None
    if mime != "image/png":
        dest = dest.with_suffix("." + mime.split("/")[1].replace("jpeg", "jpg"))
    dest.write_bytes(data)
    return dest


async def grab_image(folder: Path) -> tuple[Path | None, str]:
    """Lưu ảnh đang có trong clipboard vào `folder`. Trả (đường dẫn ảnh, lý do nếu không có)."""
    tried = methods()
    if not tried:
        if sys.platform == "darwin":
            return None, tr("không tìm thấy osascript để đọc clipboard")
        return None, tr("cần cài wl-paste (Wayland) hoặc xclip (X11) để dán ảnh")
    folder.mkdir(parents=True, exist_ok=True)
    prune(folder)
    dest = new_path(folder)
    for m in tried:
        got = await _try(m, dest)
        if got:
            return got, ""
    return None, tr("clipboard không có ảnh")


def dropped_images(text: str) -> list[str] | None:
    """Chữ dán vào là (các) đường dẫn file ảnh có thật — kiểu kéo-thả ảnh từ Finder vào terminal,
    vd `/Users/a/Desktop/Ảnh\\ chụp.png` hoặc `'/tmp/a b.png'`. Trả danh sách đường dẫn, không thì None."""
    text = text.strip()
    if not text or "\n" in text:
        return None
    try:
        parts = shlex.split(text)
    except ValueError:
        return None
    if not parts:
        return None
    out = []
    for p in parts:
        if p.startswith("file://"):
            from urllib.parse import unquote
            p = unquote(p[7:])
        p = os.path.expanduser(p)
        if not (os.path.isabs(p) and is_image(p) and os.path.isfile(p)):
            return None
        out.append(p)
    return out


def shorten(path: Path, root: Path) -> str:
    """Đường dẫn tương đối với dự án nếu nằm trong dự án, không thì giữ tuyệt đối."""
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)
