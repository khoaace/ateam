"""Tương thích model/effort của OpenCode 1 và 2, không gọi model để dò phiên bản/catalog."""

from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import AgentConfig, parse_models, parse_opencode_catalog
from .i18n import tr
from .runner import Run

ATTACHMENT_MAX = 10 * 1024 ** 2


def catalog_argv(binary: str, root: Path) -> list[str]:
    return [binary, "api", "model.list", "--param", f"location[directory]={root}"]


def major_version(output: str) -> int | None:
    m = re.search(r"\b(?:opencode\s+)?v?(\d+)\.\d+\.\d+\b", output, re.I)
    return int(m.group(1)) if m else None


def standard_models(a: AgentConfig) -> bool:
    """Chỉ đổi hai mẫu lệnh có sẵn; không đụng lệnh liệt kê riêng của người dùng."""
    cmd = a.models_command
    return (Path(a.binary).name == "opencode" and bool(cmd)
            and (shutil.which(cmd[0]) or cmd[0]) == (shutil.which(a.binary) or a.binary)
            and cmd[1:] in (["models"], ["models", "--verbose"]))


@dataclass
class Catalog:
    models: list[str] = field(default_factory=list)
    efforts: dict[str, list[str]] = field(default_factory=dict)
    warning: str = ""
    error: str = ""


class OpenCode:
    """Cache theo binary trong một phiên ateam; các alias dùng chung lần dò/catalog đang chạy."""

    def __init__(self, root: Path, env: Callable[[], dict], warn: Callable[[str], None]):
        self.root, self.env, self.warn = root, env, warn
        self._versions: dict[str, asyncio.Task] = {}
        self._catalogs: dict[str, asyncio.Task] = {}
        self._waiters: dict[asyncio.Task, int] = {}

    async def _shared(self, job: asyncio.Task):
        """Huỷ một người chờ không huỷ truy vấn của alias khác; hết người chờ thì dọn truy vấn."""
        self._waiters[job] = self._waiters.get(job, 0) + 1
        try:
            return await asyncio.shield(job)
        finally:
            remaining = self._waiters[job] - 1
            if remaining:
                self._waiters[job] = remaining
            else:
                del self._waiters[job]
                if not job.done():
                    job.cancel()
                    try:
                        await job
                    except asyncio.CancelledError:
                        pass

    async def _run(self, argv: list[str], timeout: float) -> tuple[Run, int]:
        run = Run(argv, str(self.root), self.env(), use_pty=False, timeout=timeout,
                  on_line=lambda _line: None, max_partial=None)
        try:
            code = await run.start()
        except asyncio.CancelledError:
            run.kill_now()
            if run.proc:
                await run.proc.wait()
            raise
        except OSError:
            code = 1
        return run, code

    async def _version(self, binary: str, timeout: float) -> int | None:
        run, code = await self._run([binary, "--version"], min(timeout, 10))
        version = major_version(run.output) if code == 0 else None
        if version is None:
            self.warn(tr("⚠ Không nhận diện được phiên bản OpenCode ({binary}); giữ cú pháp cấu hình hiện tại.",
                         binary=binary))
        return version

    async def prepare(self, a: AgentConfig, timeout: float = 10) -> None:
        if Path(a.binary).name != "opencode" or not a.installed():
            return
        key = shutil.which(a.binary) or a.binary
        job = self._versions.get(key)
        if job is None or job.cancelled():
            job = self._versions[key] = asyncio.create_task(self._version(a.binary, timeout))
        a.opencode_major = await self._shared(job)

    async def catalog(self, a: AgentConfig, timeout: float = 20, *, refresh: bool = False) -> Catalog:
        key = shutil.which(a.binary) or a.binary
        job = self._catalogs.get(key)
        if job is None or job.cancelled() or (refresh and job.done()):
            job = self._catalogs[key] = asyncio.create_task(self._catalog(a.binary, timeout))
        return await self._shared(job)

    async def _catalog(self, binary: str, timeout: float) -> Catalog:
        # Query lồng nhau phải dùng dấu []: location.directory bị API lờ đi; chuỗi JSON thì HTTP 400.
        run, code = await self._run(catalog_argv(binary, self.root), timeout)
        catalog = parse_opencode_catalog(run.output) if code == 0 else None
        if catalog:
            return Catalog([name for name, _ in catalog], dict(catalog))
        # Không log output API: metadata có thể chứa settings/headers của provider.
        run, code = await self._run([binary, "models"], timeout)
        names = [m for m in parse_models(run.output) if "/" in m] if code == 0 else []
        if names:
            return Catalog(names, warning=tr("⚠ OpenCode: đã lấy danh sách model nhưng thiếu metadata effort; "
                                              "tạm dùng effort mặc định của CLI."))
        why = (tr("hết thời gian") if run.timed_out else tr("mã thoát {code}", code=code)
               if code else tr("không thấy model nào"))
        return Catalog(error=tr("OpenCode: không lấy được catalog model ({why}); giữ danh sách đã lưu.", why=why))
