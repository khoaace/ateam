"""Chạy một agent CLI headless, stream output từng dòng, hỗ trợ pty, timeout và huỷ."""

from __future__ import annotations

import asyncio
import codecs
import os
import re
import signal
from typing import Callable

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")


def clean_line(s: str) -> str:
    s = ANSI_RE.sub("", s)
    if "\r" in s:  # spinner/progress: giữ phần sau dấu \r cuối cùng có nội dung
        parts = [p for p in s.split("\r") if p.strip()]
        s = parts[-1] if parts else ""
    return "".join(ch for ch in s if ch == "\t" or ch >= " " or ch == "\n").rstrip()


def build_argv(command: list[str], prompt: str) -> list[str]:
    if any("{prompt}" in c for c in command):
        return [c.replace("{prompt}", prompt) for c in command]
    return [*command, prompt]


class Run:
    """Một lần chạy agent. Gọi `await run.start()`; `run.cancel()` để dừng."""

    def __init__(self, argv: list[str], cwd: str, env: dict[str, str], *, use_pty: bool,
                 timeout: float, on_line: Callable[[str], None]):
        self.argv, self.cwd, self.env = argv, cwd, env
        self.use_pty, self.timeout, self.on_line = use_pty, timeout, on_line
        self.proc: asyncio.subprocess.Process | None = None
        self.lines: list[str] = []
        self.cancelled = False
        self.timed_out = False

    def _emit_text(self, buf: list[str], text: str, final: bool = False) -> None:
        buf[0] += text.replace("\r\n", "\n")
        while "\n" in buf[0]:
            line, buf[0] = buf[0].split("\n", 1)
            self._emit(line)
        if final and buf[0]:
            self._emit(buf[0])
            buf[0] = ""

    def _emit(self, raw: str) -> None:
        line = clean_line(raw)
        self.lines.append(line)
        try:
            self.on_line(line)
        except Exception:
            pass

    async def start(self) -> int:
        try:
            return await asyncio.wait_for(self._run(), timeout=self.timeout)
        except asyncio.TimeoutError:
            self.timed_out = True
            self._kill()
            if self.proc:
                try:
                    await asyncio.wait_for(self.proc.wait(), 10)
                except Exception:
                    pass
            return 124

    async def _run(self) -> int:
        if self.use_pty:
            return await self._run_pty()
        self.proc = await asyncio.create_subprocess_exec(
            *self.argv, cwd=self.cwd, env=self.env, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            start_new_session=True)
        dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        buf = [""]
        assert self.proc.stdout
        while True:
            chunk = await self.proc.stdout.read(4096)
            if not chunk:
                break
            self._emit_text(buf, dec.decode(chunk))
        self._emit_text(buf, dec.decode(b"", final=True), final=True)
        return await self.proc.wait()

    async def _run_pty(self) -> int:
        import fcntl
        import pty
        import struct
        import termios

        master, slave = pty.openpty()
        try:  # terminal rộng để agent không ngắt dòng
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 220, 0, 0))
        except OSError:
            pass
        env = dict(self.env)
        env.setdefault("TERM", "xterm-256color")
        self.proc = await asyncio.create_subprocess_exec(
            *self.argv, cwd=self.cwd, env=env, stdin=slave, stdout=slave, stderr=slave,
            start_new_session=True)
        os.close(slave)
        loop = asyncio.get_running_loop()
        q: asyncio.Queue[bytes | None] = asyncio.Queue()

        def readable() -> None:
            try:
                data = os.read(master, 4096)
            except OSError:
                data = b""
            if not data:
                loop.remove_reader(master)
                q.put_nowait(None)
            else:
                q.put_nowait(data)

        loop.add_reader(master, readable)
        dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        buf = [""]
        wait_task = asyncio.ensure_future(self.proc.wait())
        try:
            while True:
                get = asyncio.ensure_future(q.get())
                done, _ = await asyncio.wait({get, wait_task}, return_when=asyncio.FIRST_COMPLETED)
                if get in done:
                    data = get.result()
                    if data is None:
                        break
                    self._emit_text(buf, dec.decode(data))
                else:
                    get.cancel()
                    # tiến trình đã thoát: đọc nốt phần còn lại tối đa 1 giây
                    try:
                        while True:
                            data = await asyncio.wait_for(q.get(), 1.0)
                            if data is None:
                                break
                            self._emit_text(buf, dec.decode(data))
                    except asyncio.TimeoutError:
                        pass
                    break
        finally:
            try:
                loop.remove_reader(master)
            except Exception:
                pass
            os.close(master)
        self._emit_text(buf, dec.decode(b"", final=True), final=True)
        return await wait_task

    def _kill(self) -> None:
        if self.proc and self.proc.returncode is None:
            for sig in (signal.SIGTERM,):
                try:
                    os.killpg(self.proc.pid, sig)
                except (ProcessLookupError, PermissionError):
                    pass

            async def hard_kill(p=self.proc):
                await asyncio.sleep(5)
                if p.returncode is None:
                    try:
                        os.killpg(p.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
            try:
                asyncio.get_running_loop().create_task(hard_kill())
            except RuntimeError:
                pass

    def cancel(self) -> None:
        self.cancelled = True
        self._kill()

    @property
    def output(self) -> str:
        return "\n".join(self.lines)
