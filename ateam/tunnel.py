"""🌐 Public một cổng local ra internet bằng Cloudflare quick tunnel (`/share 3000`, nút 🌐 ở tab Terminal,
`ateam share 3000`). Không cần tài khoản: `cloudflared tunnel --url http://localhost:PORT` in ra một địa chỉ
https://*.trycloudflare.com — đổi mỗi lần chạy, ai có link đều vào được (không có token như `ateam web --tunnel`).
Không phụ thuộc Textual — TUI và web chỉ hiển thị; `web_auth.Remote` dùng chung `quick_tunnel`.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .i18n import tr

TUNNEL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
STOP_WAIT = 5  # giây chờ cloudflared tự thoát trước khi kill


def available() -> bool:
    return shutil.which("cloudflared") is not None


def install_hint() -> str:
    return tr("Chưa cài cloudflared — cài bằng `brew install cloudflared` (macOS) rồi thử lại.")


async def quick_tunnel(target: str, on_url: Callable[[str], None],
                       on_proc: Callable[[asyncio.subprocess.Process], None] | None = None) -> int:
    """Chạy quick tunnel tới `target` (vd http://localhost:3000) tới khi cloudflared thoát; gọi on_url một lần
    khi cloudflared in URL công khai ra stderr. Trả mã thoát."""
    proc = await asyncio.create_subprocess_exec(
        "cloudflared", "tunnel", "--no-autoupdate", "--url", target,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    if on_proc:
        on_proc(proc)
    assert proc.stderr is not None
    seen = False
    async for raw in proc.stderr:
        m = TUNNEL_RE.search(raw.decode("utf-8", "replace"))
        if m and not seen:
            seen = True
            on_url(m.group(0))
    return await proc.wait()


async def terminate(proc: asyncio.subprocess.Process | None) -> None:
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), STOP_WAIT)
    except ProcessLookupError:
        pass
    except asyncio.TimeoutError:
        proc.kill()


async def listening_host(port: int, timeout: float = 1.0) -> str | None:
    """Host local đang nghe ở cổng này ("127.0.0.1" hoặc "::1" — Vite/Node mới hay chỉ nghe ::1), None nếu
    không có gì."""
    for host in ("127.0.0.1", "::1"):
        try:
            _r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        except (OSError, asyncio.TimeoutError):
            continue
        w.close()
        try:
            await w.wait_closed()
        except OSError:
            pass
        return host
    return None


def parse_port(text: str) -> int | None:
    """"3000", ":3000", "localhost:3000", "http://localhost:3000/" → 3000."""
    m = re.fullmatch(r"(?:https?://)?(?:(?:localhost|127\.0\.0\.1|\[::1\])?:)?(\d{1,5})/?", text.strip())
    if not m:
        return None
    p = int(m.group(1))
    return p if 1 <= p <= 65535 else None


@dataclass
class Tunnel:
    port: int
    target: str = ""
    url: str = ""
    status: str = "starting"           # starting · up · failed · stopped
    error: str = ""
    started: float = field(default_factory=time.time)
    proc: Optional[asyncio.subprocess.Process] = None
    task: Optional[asyncio.Task] = None

    @property
    def alive(self) -> bool:
        return self.status in ("starting", "up")

    def to_json(self) -> dict:
        return {"port": self.port, "url": self.url, "status": self.status, "error": self.error,
                "started": self.started}


class TunnelManager:
    """Các tunnel đang mở, mỗi cổng một tunnel. on_change(tunnel) khi có URL / dừng / lỗi.
    reserved: cổng không được public theo cách này (chính server `ateam web` — dùng 📱 / --tunnel, có token)."""

    def __init__(self, on_change: Callable[[Tunnel], None] | None = None, reserved: tuple[int, ...] = ()):
        self.on_change = on_change or (lambda _t: None)
        self.reserved = set(reserved)
        self.tunnels: dict[int, Tunnel] = {}

    def active(self) -> list[Tunnel]:
        return [t for t in self.tunnels.values() if t.alive]

    def get(self, port: int) -> Tunnel | None:
        t = self.tunnels.get(port)
        return t if t and t.alive else None

    def check(self, port: int) -> str | None:
        """Lý do không public được cổng này (None = được)."""
        if port in self.reserved:
            return tr("Cổng {port} là chính giao diện ateam web — mở từ xa bằng nút 📱 hoặc `ateam web --tunnel` "
                      "(có token).", port=port)
        if not available():
            return install_hint()
        return None

    async def start(self, port: int) -> Tunnel:
        """Mở tunnel cho cổng (đã mở thì trả tunnel cũ). ValueError(lý do) khi không mở được."""
        old = self.get(port)
        if old:
            return old
        why = self.check(port)
        if why:
            raise ValueError(why)
        host = await listening_host(port)
        if host is None:
            raise ValueError(tr("Không có gì đang chạy ở cổng {port} trên máy này — chạy dev server trước rồi "
                                "public.", port=port))
        t = Tunnel(port, f"http://{'[::1]' if host == '::1' else 'localhost'}:{port}")
        self.tunnels[port] = t

        def got_url(url: str) -> None:
            t.url, t.status = url, "up"
            self.on_change(t)

        def got_proc(proc) -> None:
            t.proc = proc

        async def go() -> None:
            try:
                rc = await quick_tunnel(t.target, got_url, got_proc)
            except OSError as e:
                t.status, t.error = "failed", tr("Không chạy được cloudflared: {e}", e=e)
            except asyncio.CancelledError:
                await terminate(t.proc)
                t.status = "stopped"
                raise
            else:
                if t.status != "stopped":
                    t.status = "failed"
                    t.error = tr("cloudflared đã dừng (mã {rc})", rc=rc)
            self.on_change(t)

        t.task = asyncio.get_running_loop().create_task(go())
        self.on_change(t)
        return t

    async def stop(self, port: int) -> bool:
        t = self.get(port)
        if t is None:
            return False
        t.status = "stopped"
        if t.proc is None and t.task:  # cloudflared chưa kịp chạy
            t.task.cancel()
        await terminate(t.proc)
        self.tunnels.pop(port, None)
        self.on_change(t)
        return True

    async def stop_all(self) -> int:
        ports = [t.port for t in self.active()]
        for p in ports:
            await self.stop(p)
        return len(ports)

    def summary(self) -> str:
        """Dòng liệt kê cho `/share` không tham số."""
        ts = self.active()
        if not ts:
            return tr("Chưa public cổng nào. Gõ /share <cổng>, vd /share 3000.")
        return "\n".join(f"🌐 :{t.port} → {t.url or tr('đang mở…')}" for t in ts)


def parse_command(rest: str) -> tuple[str, int | None, bool]:
    """`/share` → ("list", None) · `/share 3000 [--yes]` → ("start", 3000) · `/share stop 3000` → ("stop", 3000)
    · `/share stop` / `/share off` → ("stop", None) = dừng hết. Sai cú pháp → ValueError."""
    parts = rest.split()
    yes = "--yes" in parts
    parts = [p for p in parts if p != "--yes"]
    if not parts:
        return "list", None, yes
    if parts[0].lower() in ("stop", "off", "dung", "dừng"):
        if len(parts) == 1:
            return "stop", None, yes
        port = parse_port(parts[1])
        if port is None or len(parts) > 2:
            raise ValueError(rest)
        return "stop", port, yes
    port = parse_port(parts[0])
    if port is None or len(parts) > 1:
        raise ValueError(rest)
    return "start", port, yes


def warning_text(port: int) -> str:
    return tr("Cổng {port} sẽ có một địa chỉ https://…trycloudflare.com công khai: ai có link đều vào được, "
              "không cần mật khẩu hay token. Chỉ public dev server / trang demo, đừng public thứ có dữ liệu "
              "thật hoặc trang quản trị. Tunnel tự tắt khi bạn đóng ateam.", port=port)
