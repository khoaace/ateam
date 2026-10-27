"""`ateam web` từ xa (điện thoại, Cloudflare Tunnel): token, đăng nhập bằng cookie, chặn trang lạ, tunnel.

Cục bộ (mặc định, chỉ nghe 127.0.0.1): như cũ — không cần token, chỉ nhận Host/Origin là máy này.
Từ xa (`--host` không phải loopback, `--tunnel`, `--public-url`): MỌI request cần token (kể cả từ 127.0.0.1,
vì cloudflared nối vào từ localhost), trừ /login và /static. Vào bằng `/?t=TOKEN` (mã QR) → cookie HttpOnly,
SameSite=Strict rồi chuyển về `/` (token không nằm lại trên thanh địa chỉ / lịch sử). Origin phải trùng Host
(trang khác không mở được WebSocket hay gửi form). Giao diện chạy được lệnh shell, sửa file, git push — token
là toàn quyền, `--readonly` chỉ cho xem."""

from __future__ import annotations

import asyncio
import hmac
import html
import ipaddress
import os
import re
import secrets
import socket
import time
from pathlib import Path

from aiohttp import web

from .i18n import tr
from .tunnel import TUNNEL_RE, quick_tunnel, terminate  # noqa: F401 (TUNNEL_RE: code cũ import từ đây)

COOKIE = "ateam_auth"
COOKIE_AGE = 30 * 86400
MAX_FAILS = 20       # sai token quá chừng này lần trong FAIL_WINDOW giây → khoá tạm
FAIL_WINDOW = 600


def is_loopback(host: str) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def lan_ip() -> str | None:
    """IP của máy trong mạng LAN (UDP connect không gửi gói nào)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None
    finally:
        s.close()


def load_token(state: Path, new: bool = False) -> str:
    """Token lưu ở .ateam/web_token (chmod 600) — giữ qua các lần chạy để cookie trên điện thoại còn dùng
    được; new=True tạo token mới (mọi thiết bị cũ phải quét lại)."""
    path = state / "web_token"
    if not new:
        try:
            tok = path.read_text(encoding="utf-8").strip()
            if len(tok) >= 32:
                return tok
        except OSError:
            pass
    tok = secrets.token_urlsafe(32)
    state.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(tok + "\n")
    os.chmod(path, 0o600)
    return tok


class Remote:
    """Cấu hình truy cập từ xa của một server `ateam web`."""

    def __init__(self, state: Path, *, host: str = "127.0.0.1", port: int = 8000, public_url: str = "",
                 tunnel: bool = False, readonly: bool = False, new_token: bool = False):
        self.host, self.port, self.tunnel, self.readonly = host, port, tunnel, readonly
        self.public_url = public_url.rstrip("/")
        self.tunnel_url = ""  # học được khi cloudflared in ra
        self.enabled = bool(tunnel or self.public_url or not is_loopback(host))
        self.token = load_token(state, new_token) if self.enabled else ""
        self.fails: list[float] = []
        self.proc: asyncio.subprocess.Process | None = None

    def check(self, value: str | None) -> bool:
        return bool(value) and bool(self.token) and hmac.compare_digest(value.encode(), self.token.encode())

    def locked(self) -> bool:
        now = time.time()
        self.fails = [t for t in self.fails if now - t < FAIL_WINDOW]
        return len(self.fails) >= MAX_FAILS

    def urls(self) -> list[tuple[str, str]]:
        """(nhãn, URL kèm token) để in / hiện mã QR."""
        q = f"/?t={self.token}"
        out = []
        if self.tunnel_url:
            out.append((tr("Cloudflare Tunnel"), self.tunnel_url + q))
        if self.public_url:
            out.append((tr("Địa chỉ công khai"), self.public_url + q))
        if not is_loopback(self.host):
            ip = lan_ip() if self.host in ("0.0.0.0", "::") else self.host
            if ip:
                out.append((tr("Mạng LAN"), f"http://{ip}:{self.port}{q}"))
        out.append((tr("Máy này"), f"http://127.0.0.1:{self.port}{q}"))
        return out

    # ------------------------------------------------------------------ cloudflared
    async def start_tunnel(self, on_url) -> None:
        """Quick tunnel (không cần tài khoản): cloudflared in URL https://*.trycloudflare.com ra stderr."""
        def got(url: str) -> None:
            self.tunnel_url = url
            on_url(url)

        def proc(p) -> None:
            self.proc = p
        await quick_tunnel(f"http://127.0.0.1:{self.port}", got, proc)

    async def stop_tunnel(self) -> None:
        await terminate(self.proc)


def _secure(request: web.Request) -> bool:
    return request.secure or request.headers.get("X-Forwarded-Proto", "").lower() == "https"


def _logged_in(request: web.Request, token: str, to: str = "/") -> web.Response:
    r = web.Response(status=302, headers={"Location": to, "Cache-Control": "no-store"})
    r.set_cookie(COOKIE, token, max_age=COOKIE_AGE, httponly=True, samesite="Strict",
                 secure=_secure(request), path="/")
    return r


def login_page(error: str = "") -> web.Response:
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    body = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ateam</title>
<style>:root{{color-scheme:dark}}body{{font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
display:grid;place-items:center;min-height:100vh;margin:0;padding:16px;box-sizing:border-box;
background:#10110e;color:#e8e6dc}}form{{max-width:420px;width:100%;border:1px solid #35372f;padding:16px 16px 18px}}
h2{{margin:0 0 8px;font-size:15px;font-weight:650}}h2::before{{content:"❯ ";color:#8b5cf6}}
p{{margin:0;color:#8d897c;font-size:12px}}
input,button{{font:inherit;width:100%;box-sizing:border-box;padding:8px 10px;margin-top:8px;border-radius:2px}}
input{{background:#0c0d0b;color:#e8e6dc;border:1px solid #484b40}}
button{{background:#8b5cf6;color:#fff;border:1px solid #8b5cf6;cursor:pointer}}
.err{{color:#f07178}}
@media (prefers-color-scheme:light){{body{{background:#f3efe6;color:#1c1914}}
form{{border-color:#d5ccba}}p{{color:#6f675c}}
input{{background:#faf7f0;color:#1c1914;border-color:#c2b7a2}}}}</style></head><body><form method="post" action="/login">
<h2>ateam</h2><p>{html.escape(tr("Quét mã QR trong terminal đang chạy `ateam web`, hoặc dán token (file .ateam/web_token) vào đây."))}</p>
{err}<input name="token" type="password" autocomplete="current-password" placeholder="token" autofocus>
<button type="submit">{html.escape(tr("Vào"))}</button></form></body></html>"""
    return web.Response(status=401, text=body, content_type="text/html", headers={"Cache-Control": "no-store"})


def local_hosts(port: int) -> set[str]:
    return {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}


def auth_middleware(remote: Remote, port: int):
    """Cục bộ: chỉ Host/Origin là máy này (chặn DNS rebinding, trang lạ mở WebSocket). Từ xa: cần token."""
    hosts = local_hosts(port)

    @web.middleware
    async def guard(request: web.Request, handler):
        origin = request.headers.get("Origin")
        if not remote.enabled:
            if request.host not in hosts:
                return web.Response(status=403, text="forbidden host")
            if origin and re.sub(r"^https?://", "", origin) not in hosts:
                return web.Response(status=403, text="forbidden origin")
            return await handler(request)
        # từ xa: Host nào cũng được (tunnel, domain, IP LAN) vì cookie chỉ gửi cho đúng host đã đăng nhập —
        # DNS rebinding không mang theo cookie; trang khác không được gửi Origin của nó tới đây
        if origin and re.sub(r"^https?://", "", origin) != request.host:
            return web.Response(status=403, text="forbidden origin")
        if request.path.startswith("/static/"):
            return await handler(request)
        auth = request.headers.get("Authorization", "")
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else None
        q = request.query.get("t")
        # đã đăng nhập: không bị khoá vì người lạ đoán token sai nhiều lần (khoá chỉ chặn đăng nhập mới)
        if q is None and (remote.check(request.cookies.get(COOKIE)) or remote.check(bearer)):
            return await handler(request)
        if remote.locked():
            return web.Response(status=429, text=tr("Sai token quá nhiều lần — thử lại sau ít phút"))
        if request.path == "/login" and request.method == "POST":
            form = await request.post()
            if remote.check(str(form.get("token") or "").strip()):
                return _logged_in(request, remote.token)
            remote.fails.append(time.time())
            return login_page(tr("Token không đúng"))
        if q is not None:
            if remote.check(q):
                return _logged_in(request, remote.token, request.path if request.path != "/login" else "/")
            remote.fails.append(time.time())
            return login_page(tr("Token không đúng"))
        if bearer is not None:
            remote.fails.append(time.time())
        if request.path in ("/", "/login") and request.method == "GET":
            return login_page()
        return web.Response(status=401, text="unauthorized")
    return guard


async def security_headers(request: web.Request, response: web.StreamResponse) -> None:
    if request.path.startswith("/api/"):  # dữ liệu của dự án đang mở: không dùng lại bản cũ (sau /open cùng cổng)
        response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
