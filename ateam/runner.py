"""Chạy một agent CLI headless, stream output từng dòng, hỗ trợ pty, timeout và huỷ."""

from __future__ import annotations

import asyncio
import codecs
import os
import re
import signal
from collections import deque
from typing import Callable

from . import agystream

MAX_PARTIAL = 64 * 1024  # dòng chưa có \n dài hơn thế (spinner chỉ dùng \r, JSON một dòng…) thì cắt/đẩy ra

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")


def clean_line(s: str) -> str:
    s = ANSI_RE.sub("", s)
    if "\r" in s:  # spinner/progress: giữ phần sau dấu \r cuối cùng có nội dung
        parts = [p for p in s.split("\r") if p.strip()]
        s = parts[-1] if parts else ""
    # bỏ cả DEL và ký tự điều khiển C1 (U+0080–U+009F): nhiều terminal hiểu U+0085/U+008D
    # là xuống dòng/cuộn ngược, in thẳng ra sẽ làm cả màn hình TUI bị đẩy lệch
    return "".join(ch for ch in s
                   if ch == "\t" or ch == "\n" or (ch >= " " and not "\x7f" <= ch <= "\x9f")).rstrip()


class Run:
    """Một lần chạy agent. Gọi `await run.start()`; `run.cancel()` để dừng."""

    def __init__(self, argv: list[str], cwd: str, env: dict[str, str], *, use_pty: bool,
                 timeout: float, on_line: Callable[[str], None], keep_lines: int | None = None,
                 max_partial: int | None = MAX_PARTIAL):
        """timeout: giây tối đa, <= 0 = không giới hạn (task của agent: chạy tới khi xong hoặc bị huỷ).
        keep_lines: chỉ giữ N dòng cuối trong bộ nhớ (lệnh chạy rất lâu như dev server).
        max_partial=None: không cắt dòng dài (output là JSON một dòng cần bóc nguyên vẹn, vd `codex debug models`)."""
        # PWD theo cwd: env chép từ os.environ mang PWD của nơi chạy ateam (thư mục gốc khi task ở worktree, dự án
        # cũ sau /open) — CLI/shell đọc $PWD sẽ tưởng đang ở đó
        self.argv, self.cwd, self.env = argv, cwd, dict(env, PWD=os.path.abspath(cwd))
        self.use_pty, self.timeout, self.on_line = use_pty, timeout, on_line
        self.proc: asyncio.subprocess.Process | None = None
        self.lines: list[str] | deque[str] = deque(maxlen=keep_lines) if keep_lines else []
        self._output: str | None = None
        self.cancelled = False
        self.timed_out = False
        self.max_partial = max_partial
        # agy --output-format stream-json: sự kiện JSON -> dòng dễ đọc; tool chỉ hiện, không vào output
        self.stream = agystream.AgyStream() if agystream.wants(argv) else None
        self.meta: list[str] = []      # dòng chỉ để bắt id phiên (không vào output)
        self.session_lost = False      # CLI báo không còn phiên --resume/--conversation: đã dừng sớm

    def _emit_text(self, buf: list[str], text: str, final: bool = False) -> None:
        text = text.replace("\r\n", "\n")
        if "\n" in text:  # chỉ tách khi đoạn mới có \n: không quét lại cả dòng dài mỗi lần đọc
            *lines, buf[0] = (buf[0] + text).split("\n")
            for line in lines:
                self._emit(line)
        else:
            buf[0] += text
        if self.max_partial is not None and len(buf[0]) > self.max_partial:
            # spinner/progress chỉ ghi đè bằng \r: giữ từ dấu \r áp chót (clean_line lấy đoạn cuối có chữ)
            cut = buf[0].rfind("\r", 0, len(buf[0]) - 1)
            if cut > 0:
                buf[0] = buf[0][cut:]
            if len(buf[0]) > self.max_partial:
                self._emit(buf[0])
                buf[0] = ""
        if final and buf[0]:
            self._emit(buf[0])
            buf[0] = ""

    def _emit(self, raw: str) -> None:
        line = clean_line(raw)
        if self.stream is None:
            self._show(line, True)
            return
        for text, kind in self.stream.feed(line):
            if kind == agystream.META:
                self.meta.append(text)
            self._show(text, kind == agystream.OUT)
        if self.stream.lost and not self.session_lost:  # chạy tiếp là làm việc trong phiên mới thiếu ngữ cảnh
            self.session_lost = True
            self._kill()

    def _show(self, line: str, keep: bool) -> None:
        if keep:
            self.lines.append(line)
            self._output = None
        try:
            self.on_line(line)
        except Exception:
            pass

    @property
    def usage(self):
        """Token thật CLI tự báo trong output (agy stream-json), None = không có."""
        return self.stream.usage if self.stream else None

    async def start(self) -> int:
        try:
            return await asyncio.wait_for(self._run(), timeout=self.timeout if self.timeout > 0 else None)
        except asyncio.CancelledError:  # app thoát / Ctrl+C / task bị huỷ: tiến trình ở session riêng nên phải tự dừng
            self.cancelled = True
            self._kill()
            raise
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
        stdout = self.proc.stdout
        while True:
            try:
                chunk = await asyncio.wait_for(stdout.read(4096), 0.5)
            except asyncio.TimeoutError:
                # proc.wait() của asyncio chờ cả pipe đóng: tiến trình con chạy nền (vd `npm run dev &`) giữ stdout
                # thì sẽ chờ tới timeout. Tiến trình chính đã thoát và im lặng 0,5s -> coi như xong.
                if self.proc.returncode is not None:
                    break
                continue
            if not chunk:
                break
            self._emit_text(buf, dec.decode(chunk))
        self._emit_text(buf, dec.decode(b"", final=True), final=True)
        if self.proc.returncode is not None:
            return self.proc.returncode
        return await self.proc.wait()

    async def _run_pty(self) -> int:
        import fcntl
        import pty
        import struct
        import termios

        master, slave = pty.openpty()
        try:
            try:  # terminal rộng để agent không ngắt dòng
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 220, 0, 0))
            except OSError:
                pass
            env = dict(self.env)
            env.setdefault("TERM", "xterm-256color")
            self.proc = await asyncio.create_subprocess_exec(
                *self.argv, cwd=self.cwd, env=env, stdin=slave, stdout=slave, stderr=slave,
                start_new_session=True)
        except BaseException:  # không chạy được (hoặc bị huỷ lúc đang mở): không rò 2 fd
            os.close(slave)
            os.close(master)
            raise
        # Giữ slave mở tới khi tiến trình thoát: trên macOS, đóng hết phía slave làm mất phần
        # output còn nằm trong pty chưa kịp đọc (agent in nhanh rồi thoát -> mất sạch output).
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
                    # tiến trình đã thoát: lấy phần đã đọc trong hàng đợi, rồi đọc thẳng
                    # những gì còn trong pty (slave vẫn mở nên dữ liệu chưa bị bỏ)
                    loop.remove_reader(master)
                    while not q.empty():
                        data = q.get_nowait()
                        if data:
                            self._emit_text(buf, dec.decode(data))
                    os.set_blocking(master, False)
                    for _ in range(10000):  # chặn trên phòng tiến trình con còn ghi liên tục
                        try:
                            data = os.read(master, 4096)
                        except OSError:  # BlockingIOError = hết dữ liệu; EIO = đã đóng
                            break
                        if not data:
                            break
                        self._emit_text(buf, dec.decode(data))
                    break
        finally:
            try:
                loop.remove_reader(master)
            except Exception:
                pass
            os.close(slave)
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

    def kill_now(self) -> None:
        """SIGKILL cả nhóm tiến trình ngay — lúc thoát app, hẹn giờ SIGKILL của _kill không kịp chạy."""
        if self.proc and self.proc.returncode is None:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def cancel(self) -> None:
        self.cancelled = True
        self._kill()

    @property
    def output(self) -> str:
        if self._output is None:  # được đọc nhiều lần sau mỗi lượt (_classify, session_of, parse_ask…)
            self._output = "\n".join(self.lines)
        return self._output
