"""Một tiến trình tương tác trong pty, nối hai chiều với trình duyệt (xterm.js): "Mở trong terminal" ở `ateam web`
chạy CLI thật của agent (`claude --resume <phiên>`…). Khác `runner.Run` (đọc từng dòng, bỏ mã ANSI, không có
input): ở đây byte thô đi ra nguyên vẹn, phím gõ đi vào, đổi kích thước báo SIGWINCH như terminal thật."""

from __future__ import annotations

import asyncio
import fcntl
import os
import signal
import struct
import termios
from typing import Callable


def _set_size(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", max(2, rows), max(10, cols), 0, 0))


class PtySession:
    """on_data(bytes) mỗi khi tiến trình in ra; on_exit(mã thoát) khi nó thoát. Gọi `await start()` rồi
    `write()`, `resize()`, `close()`."""

    def __init__(self, argv: list[str], cwd: str, env: dict[str, str], *, on_data: Callable[[bytes], None],
                 on_exit: Callable[[int], None], rows: int = 30, cols: int = 100):
        self.argv, self.cwd, self.env = argv, cwd, env
        self.on_data, self.on_exit = on_data, on_exit
        self.rows, self.cols = rows, cols
        self.proc: asyncio.subprocess.Process | None = None
        self.master: int | None = None
        self.rc: int | None = None
        self._waiter: asyncio.Task | None = None

    async def start(self) -> None:
        import pty
        master, slave = pty.openpty()
        try:
            _set_size(slave, self.rows, self.cols)
            env = dict(self.env)
            env.setdefault("TERM", "xterm-256color")
            env.setdefault("COLORTERM", "truecolor")

            def ctty() -> None:  # sau setsid: nhận pty làm terminal điều khiển (Ctrl+C, SIGWINCH, job control)
                fcntl.ioctl(0, termios.TIOCSCTTY, 0)

            self.proc = await asyncio.create_subprocess_exec(
                *self.argv, cwd=self.cwd, env=env, stdin=slave, stdout=slave, stderr=slave,
                start_new_session=True, preexec_fn=ctty)
        except BaseException:
            os.close(master)
            raise
        finally:
            os.close(slave)  # tiến trình con giữ bản của nó; khi nó thoát, đọc master báo EOF/EIO
        self.master = master
        os.set_blocking(master, False)
        asyncio.get_running_loop().add_reader(master, self._readable)
        self._waiter = asyncio.ensure_future(self._wait())

    def _readable(self) -> None:
        try:
            data = os.read(self.master, 65536)
        except BlockingIOError:
            return
        except OSError:  # EIO: phía slave đã đóng hết
            data = b""
        if not data:
            asyncio.get_running_loop().remove_reader(self.master)
            return
        try:
            self.on_data(data)
        except Exception:
            pass

    async def _wait(self) -> None:
        rc = await self.proc.wait()
        await asyncio.sleep(0.1)  # để phần output cuối kịp đọc
        self._close_fd()
        self.rc = rc
        try:
            self.on_exit(rc)
        except Exception:
            pass

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    def write(self, data: bytes) -> None:
        if self.master is None or not self.alive:
            return
        view = memoryview(data)
        while view:  # master không chặn: phím gõ / dán đoạn ngắn, ghi ngay
            try:
                n = os.write(self.master, view)
            except BlockingIOError:
                break
            except OSError:
                return
            view = view[n:]

    def resize(self, rows: int, cols: int) -> None:
        self.rows, self.cols = rows, cols
        if self.master is not None:
            try:
                _set_size(self.master, rows, cols)  # nhân hệ điều hành báo SIGWINCH cho tiến trình
            except OSError:
                pass

    def close(self) -> None:
        """Đóng như đóng cửa sổ terminal: SIGHUP cả nhóm tiến trình, còn sống sau 3 giây thì SIGKILL."""
        if not self.alive:
            self._close_fd()
            return
        pid = self.proc.pid
        for sig in (signal.SIGHUP, signal.SIGTERM):
            try:
                os.killpg(pid, sig)
            except (ProcessLookupError, PermissionError):
                return

        async def hard_kill(p=self.proc) -> None:
            await asyncio.sleep(3)
            if p.returncode is None:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        asyncio.get_running_loop().create_task(hard_kill())

    def kill_now(self) -> None:
        if self.alive:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def _close_fd(self) -> None:
        if self.master is not None:
            try:
                asyncio.get_running_loop().remove_reader(self.master)
            except Exception:
                pass
            try:
                os.close(self.master)
            except OSError:
                pass
            self.master = None
