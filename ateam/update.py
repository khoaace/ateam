"""Tự cập nhật ateam từ trong app (/update) hoặc dòng lệnh (`ateam update`).

So phiên bản đang chạy với version.txt trên trang docs; có bản mới thì chạy đúng lệnh cài một dòng
(scripts/get.sh). Bản cài từ mã nguồn (`pip install -e`) không tự cập nhật — get.sh sẽ thay mất bản
liên kết — mà chỉ dẫn `git pull`.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from importlib import metadata
from pathlib import Path
from typing import Callable, Optional

from . import __version__
from .i18n import tr

VERSION_URL = "https://ateam.khoaace.workers.dev/version.txt"
GET_SH = "https://raw.githubusercontent.com/khoaace/ateam/main/scripts/get.sh"
UPDATE_CMD = ["bash", "-c", f"curl -fsSL {GET_SH} | bash"]


def editable_source() -> Optional[Path]:
    """Thư mục mã nguồn nếu ateam được cài bằng `pip install -e`, ngược lại None."""
    # duyệt mọi bản metadata tên ateam: chạy trong thư mục mã nguồn thì ateam.egg-info đứng trước
    for dist in metadata.distributions(name="ateam"):
        try:
            info = json.loads(dist.read_text("direct_url.json") or "{}")
        except ValueError:
            continue
        url = str(info.get("url", ""))
        if (info.get("dir_info") or {}).get("editable") and url.startswith("file://"):
            return Path(url[len("file://"):])
    return None


def parse_version(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


async def latest_version(timeout: float = 15) -> Optional[str]:
    """Phiên bản mới nhất trên trang docs, hoặc None nếu không lấy được (mất mạng, chưa có curl…)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl", "-fsSL", "--max-time", str(int(timeout)), VERSION_URL,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout + 5)
    except (OSError, asyncio.TimeoutError):
        return None
    v = out.decode("utf-8", "replace").strip()
    return v if proc.returncode == 0 and re.fullmatch(r"\d+\.\d+\.\d+\S*", v) else None


async def run_update(on_line: Callable[[str], None], force: bool = False) -> tuple[bool, str]:
    """Kiểm tra và cập nhật. Trả (đã cài bản mới?, thông báo cuối cho người dùng)."""
    src = editable_source()
    latest = await latest_version()
    if latest is None:
        return False, tr("Không kiểm tra được phiên bản mới (mất mạng?). Thử lại sau.")
    if not force and parse_version(latest) <= parse_version(__version__):
        return False, tr("Đang dùng bản mới nhất ({version}).", version=__version__)
    if src is not None:
        return False, (tr("Có bản {latest} (đang chạy {version}), nhưng ateam được cài từ mã nguồn "
                          "ở {src}: cập nhật bằng `git -C {src} pull`, rồi mở lại app.", latest=latest, version=__version__, src=src))
    on_line(tr("→ Cập nhật ateam {version} → {latest}", version=__version__, latest=latest))
    from .runner import Run
    run = Run(list(UPDATE_CMD), str(Path.home()), dict(os.environ), use_pty=False,
              timeout=600, on_line=on_line)
    code = await run.start()
    if code != 0:
        return False, tr("Cập nhật thất bại (mã thoát {code}) — xem log ở trên, hoặc chạy tay: "
                         "curl -fsSL {GET_SH} | bash", code=code, GET_SH=GET_SH)
    return True, tr("Đã cập nhật lên {latest}. Thoát (Ctrl+Q) rồi mở lại ateam để dùng bản mới.", latest=latest)


async def check_new() -> Optional[str]:
    """Kiểm tra lúc mở app: phiên bản mới hơn bản đang chạy, hoặc None (đã mới nhất, mất mạng, hoặc tắt bằng biến
    môi trường ATEAM_NO_UPDATE_CHECK)."""
    if os.environ.get("ATEAM_NO_UPDATE_CHECK"):
        return None
    latest = await latest_version()
    return latest if latest and parse_version(latest) > parse_version(__version__) else None


def new_version_text(latest: str) -> str:
    src = editable_source()
    if src is not None:
        return tr("⬆ Có bản ateam {latest} (đang dùng {version}) — cập nhật bằng `git -C {src} pull`",
                  latest=latest, version=__version__, src=src)
    return tr("⬆ Có bản ateam {latest} (đang dùng {version}) — gõ /update để cập nhật",
              latest=latest, version=__version__)
