"""Chạy lệnh terminal của người dùng trong ateam (`!yarn dev`, `/sh make test`): nhiều lệnh song song,
stream output, dừng / chạy lại, gợi ý script của dự án. Không phụ thuộc Textual — tab Terminal ở tui.py
chỉ hiển thị.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .config import load_project_state, save_project_setting
from .runner import Run

MAX_LINES = 5000           # giữ trong bộ nhớ cho mỗi lệnh (file log có đủ)
RECENT_MAX = 20
FOREVER = 10 * 86400       # dev server chạy tới khi người dùng dừng
PORT_RE = re.compile(r"(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::\]|\[::1\]):(\d{2,5})\b|\bport\s+(\d{2,5})\b", re.I)


@dataclass
class ShellJob:
    id: int
    cmd: str
    cwd: Path
    started: float = field(default_factory=time.time)
    finished: Optional[float] = None
    rc: Optional[int] = None
    status: str = "running"            # running · done · failed · stopped
    lines: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    run: Optional[Run] = None
    task: Optional[asyncio.Task] = None

    @property
    def alive(self) -> bool:
        return self.status == "running"


def find_ports(line: str) -> list[int]:
    out = []
    for m in PORT_RE.finditer(line):
        p = int(m.group(1) or m.group(2))
        if 1 <= p <= 65535 and p not in out:
            out.append(p)
    return out


def package_manager(root: Path) -> str:
    for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"),
                     ("bun.lock", "bun")):
        if (root / lock).exists():
            return pm
    return "npm"


def project_scripts(root: Path, recent: list[str] | None = None) -> list[tuple[str, str]]:
    """Gợi ý cho `!`: (lệnh, mô tả) — lệnh gần đây, script package.json (đúng trình quản lý gói theo
    lockfile), target Makefile. Không trùng lệnh."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(cmd: str, desc: str) -> None:
        if cmd not in seen:
            seen.add(cmd)
            out.append((cmd, desc))

    for cmd in recent if recent is not None else recent_commands(root):
        add(cmd, "chạy gần đây")
    try:
        scripts = json.loads((root / "package.json").read_text(encoding="utf-8")).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        scripts = {}
    pm = package_manager(root)
    for name, body in scripts.items():
        cmd = f"{pm} {name}" if pm in ("yarn", "pnpm") else f"{pm} run {name}"
        add(cmd, str(body))
    for mk in ("Makefile", "makefile", "GNUmakefile"):
        try:
            text = (root / mk).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.finditer(r"^([A-Za-z0-9_][\w.-]*)\s*:(?!=)", text, re.M):
            add(f"make {m.group(1)}", "Makefile")
        break
    return out


def recent_commands(root: Path) -> list[str]:
    rec = load_project_state(root).get("recent_commands") or []
    return [str(c) for c in rec if isinstance(c, str)]


def remember(root: Path, cmd: str) -> None:
    rec = [cmd] + [c for c in recent_commands(root) if c != cmd]
    save_project_setting(root, "recent_commands", rec[:RECENT_MAX])


class ShellManager:
    """Các lệnh người dùng chạy. on_event(kind, job, line) với kind = "line" | "exit" | "changed"."""

    def __init__(self, root: Path, on_event: Callable[[str, ShellJob, str], None] | None = None):
        self.root = Path(root)
        self.on_event = on_event or (lambda *_a: None)
        self.jobs: dict[int, ShellJob] = {}
        self._next = 1
        self.logs = self.root / ".ateam" / "logs"

    def log_path(self, job: ShellJob) -> Path:
        return self.logs / f"sh{job.id}.log"

    def running(self) -> list[ShellJob]:
        return [j for j in self.jobs.values() if j.alive]

    def start(self, cmd: str) -> ShellJob:
        cmd = cmd.strip()
        job = ShellJob(self._next, cmd, self.root)
        self._next += 1
        self.jobs[job.id] = job
        remember(self.root, cmd)
        self.logs.mkdir(parents=True, exist_ok=True)
        shell = os.environ.get("SHELL") or "/bin/sh"
        log = open(self.log_path(job), "w", encoding="utf-8")
        log.write(f"$ {cmd}\n")

        def on_line(line: str) -> None:
            log.write(line + "\n")
            log.flush()
            job.lines.append(line)
            if len(job.lines) > MAX_LINES:
                del job.lines[:len(job.lines) - MAX_LINES]
            for p in find_ports(line):
                if p not in job.ports:
                    job.ports.append(p)
            self.on_event("line", job, line)

        # -l: nạp profile như mở terminal (PATH của nvm/volta/bun…); pty: lệnh in như trong terminal thật
        job.run = Run([shell, "-lc", cmd], str(self.root), dict(os.environ), use_pty=True,
                      timeout=FOREVER, on_line=on_line)

        async def go() -> None:
            try:
                rc = await job.run.start()
            except Exception as e:  # không chạy được shell
                on_line(f"✗ Không chạy được: {e}")
                rc = 127
            job.rc, job.finished = rc, time.time()
            if job.status == "running":
                job.status = "done" if rc == 0 else "failed"
            log.write(f"\n[thoát với mã {rc}]\n")
            log.close()
            self.on_event("exit", job, "")

        job.task = asyncio.get_running_loop().create_task(go())
        self.on_event("changed", job, "")
        return job

    def stop(self, job: ShellJob) -> bool:
        if not job.alive or not job.run:
            return False
        job.status = "stopped"
        job.run.cancel()
        self.on_event("changed", job, "")
        return True

    def restart(self, job: ShellJob) -> ShellJob:
        self.stop(job)
        return self.start(job.cmd)

    def remove(self, job: ShellJob) -> bool:
        if job.alive:
            return False
        self.jobs.pop(job.id, None)
        self.on_event("changed", job, "")
        return True

    def stop_all(self) -> int:
        return sum(self.stop(j) for j in list(self.jobs.values()))
