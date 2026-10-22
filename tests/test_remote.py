"""`ateam web` từ xa: mã QR thuần Python, token + cookie, chặn origin lạ, khoá khi sai nhiều, --readonly, --tunnel."""

from __future__ import annotations

import asyncio
import importlib
import os
import stat

import pytest

from conftest import ateam

from ateam import qr


# ---------------------------------------------------------------------------- mã QR
def _syndromes_zero(block: list[int], ec: list[int]) -> bool:
    """Codeword Reed-Solomon đúng ⇔ đa thức (dữ liệu + sửa lỗi) bằng 0 tại α^0…α^(n-1)."""
    word = block + ec
    a = 1
    for _ in range(len(ec)):
        s = 0
        for c in word:
            s = qr._gf_mul(s, a) ^ c
        if s:
            return False
        a = qr._gf_mul(a, 2)
    return True


def test_qr_structure_and_reed_solomon():
    for text, version in (("hi", 1), ("https://abc.trycloudflare.com/?t=" + "x" * 43, 5), ("q" * 200, 10)):
        v, blocks, ecs, words = qr.codewords(text.encode())
        assert v == version and all(_syndromes_zero(b, e) for b, e in zip(blocks, ecs))
        q = qr.QR(text)
        assert q.size == 4 * v + 17
        n = q.size
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):  # 3 ô định vị: tâm 3x3 tối, vòng sáng, viền tối
            assert q.m[cy][cx] and not q.m[cy - 2][cx] and q.m[cy - 3][cx]
        assert q.m[n - 8][8]  # module tối cố định
        # format info (hàng 8, cột 0..5) giải ra đúng mức M + mask đã chọn
        bits = sum(q.m[i][8] << i for i in range(6)) | q.m[7][8] << 6 | q.m[8][8] << 7 | q.m[8][7] << 8
        bits |= sum(q.m[8][14 - i] << i for i in range(9, 15))
        assert ((bits ^ 0x5412) >> 10) == q.mask  # 2 bit đầu = 00 (M)
    assert "\x1b[" in qr.QR("x").to_text() and qr.QR("x").to_svg().startswith("<svg")
    with pytest.raises(ValueError):
        qr.codewords(b"z" * 300)


# ---------------------------------------------------------------------------- server từ xa
def _app(env, project, monkeypatch, **remote):
    pytest.importorskip("aiohttp")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.web import WebApp
    from ateam.web_auth import Remote
    ensure_global_config()
    r = Remote(project / ".ateam", port=8123, **remote)
    return WebApp(project, load_config(project), DB(project / ".ateam/team.db"), 8123, r)


def test_token_cookie_origin_and_lockout(env, project, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer
    wa = _app(env, project, monkeypatch, public_url="https://ateam.example.com")
    tok = wa.remote.token
    path = project / ".ateam/web_token"
    assert len(tok) >= 40 and stat.S_IMODE(os.stat(path).st_mode) == 0o600

    async def main():
        c = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=0))
        await c.start_server()
        try:
            r = await c.get("/")  # chưa có token: trang đăng nhập (kể cả từ 127.0.0.1 — tunnel nối từ localhost)
            assert r.status == 401 and 'action="/login"' in await r.text()
            assert r.headers["X-Frame-Options"] == "DENY"
            assert (await c.get("/api/goals")).status == 401
            assert (await c.get("/static/app.css")).status == 200
            assert (await c.get("/?t=sai")).status == 401
            # QR: /?t=TOKEN → cookie HttpOnly + về "/" (token không ở lại trên URL)
            r = await c.get(f"/?t={tok}", allow_redirects=False, headers={"Host": "ateam.example.com",
                                                                           "X-Forwarded-Proto": "https"})
            assert r.status == 302 and r.headers["Location"] == "/"
            ck = r.headers["Set-Cookie"]
            assert "HttpOnly" in ck and "SameSite=Strict" in ck and "Secure" in ck
            c.session.cookie_jar.update_cookies({"ateam_auth": tok})
            r = await c.get("/", headers={"Host": "ateam.example.com"})
            assert r.status == 200 and "/static/app.js" in await r.text()
            rem = await (await c.get("/api/remote")).json()
            assert rem["enabled"] and any(u["url"] == f"https://ateam.example.com/?t={tok}" for u in rem["urls"])
            assert rem["urls"][0]["svg"].startswith("<svg")
            # WebSocket: Origin phải trùng Host
            ws = await c.ws_connect("/ws", headers={"Origin": f"http://{c.host}:{c.port}"})
            hello = await ws.receive_json(timeout=10)
            assert hello["remote"] and not hello["readonly"]
            await ws.close()
            with pytest.raises(Exception):
                await c.ws_connect("/ws", headers={"Origin": "https://evil.example"})
            c.session.cookie_jar.clear()
            # form đăng nhập
            r = await c.post("/login", data={"token": tok}, allow_redirects=False)
            assert r.status == 302 and "ateam_auth" in r.headers["Set-Cookie"]
            c.session.cookie_jar.clear()
            assert (await c.get("/api/goals", headers={"Authorization": f"Bearer {tok}"})).status == 200
            # sai quá nhiều: khoá tạm, kể cả token đúng
            for _ in range(20):
                await c.get("/?t=doan-mo")
            assert (await c.get(f"/?t={tok}")).status == 429
            # người đã đăng nhập không bị khoá theo
            assert (await c.get("/api/goals", headers={"Authorization": f"Bearer {tok}"})).status == 200
        finally:
            await c.close()
    asyncio.run(main())
    # giữ token qua lần chạy; --new-token đổi
    from ateam.web_auth import load_token
    assert load_token(project / ".ateam") == tok and load_token(project / ".ateam", new=True) != tok


def test_readonly_blocks_actions(env, project, monkeypatch):
    wa = _app(env, project, monkeypatch, host="0.0.0.0", readonly=True)
    assert wa.remote.enabled and wa.remote.urls()[-1][1].startswith("http://127.0.0.1:8123/?t=")
    r = asyncio.run(wa.handle({"op": "submit", "text": "!rm -rf x"}))
    assert r[1] == "warn" and "chỉ xem" in r[0]
    assert asyncio.run(wa.handle({"op": "save", "path": "a.txt", "text": "x"}))[1] == "warn"
    assert not (project / "a.txt").exists() and not wa.shell.jobs
    assert wa.hello()["readonly"]


def test_local_mode_unchanged_without_token(env, project, monkeypatch):
    wa = _app(env, project, monkeypatch)
    assert not wa.remote.enabled and not wa.remote.token and not (project / ".ateam/web_token").exists()


def test_restart_into_remote_from_phone_popup(env, project, monkeypatch):
    """📱 ↻ Chạy lại: server dừng rồi cli.cmd_web chạy lại cùng cổng với --host 0.0.0.0 / --tunnel; trình duyệt nhận
    token (server mới đọc lại đúng token đó) để vào lại."""
    from ateam.web_auth import load_token
    wa = _app(env, project, monkeypatch)
    stopped = []
    wa.stop_server = lambda: stopped.append(1)

    async def main():
        assert (await wa.handle({"op": "remote_restart", "mode": "x"}))[1] == "warn"
        wa.orch.runs[999] = None  # agent đang chạy: trình duyệt hỏi lại rồi gửi force
        r = await wa.handle({"op": "remote_restart", "mode": "lan"})
        assert r[2] == {"busy": 1} and wa.next_root is None
        r = await wa.handle({"op": "remote_restart", "mode": "lan", "force": True})
        wa.orch.runs.clear()
        assert r[2]["restarting"] and wa.next_root == wa.root and wa.next_args == ["--host", "0.0.0.0"]
        assert r[2]["token"] == load_token(project / ".ateam")
        await asyncio.sleep(0.4)
        assert stopped == [1]
        r = await wa.handle({"op": "remote_restart", "mode": "tunnel"})  # fakebin có cloudflared
        assert r[2]["restarting"] and wa.next_args == ["--tunnel"]
        monkeypatch.setattr("ateam.web.shutil.which", lambda _n: None)
        wa.next_args = []
        r = await wa.handle({"op": "remote_restart", "mode": "tunnel"})
        assert r[1] == "warn" and "brew install cloudflared" in r[0] and not wa.next_args
        wa.remote.enabled = True
        assert (await wa.handle({"op": "remote_restart", "mode": "lan"}))[1] == "warn"
    asyncio.run(main())


def test_api_remote_pending_until_tunnel_url(env, project, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer
    wa = _app(env, project, monkeypatch, tunnel=True)
    wa._startup = wa._shutdown = lambda _app: asyncio.sleep(0)  # không chạy cloudflared / bộ lập lịch

    async def main():
        c = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=0))
        await c.start_server()
        try:
            h = {"Authorization": f"Bearer {wa.remote.token}"}
            assert (await (await c.get("/api/remote", headers=h)).json())["pending"]
            wa.remote.tunnel_url = "https://x.trycloudflare.com"
            assert not (await (await c.get("/api/remote", headers=h)).json())["pending"]
        finally:
            await c.close()
    asyncio.run(main())


def test_tunnel_learns_public_url(env, project, monkeypatch, capsys):
    wa = _app(env, project, monkeypatch, tunnel=True)

    async def main():
        seen = []
        task = asyncio.ensure_future(wa.remote.start_tunnel(seen.append))
        for _ in range(50):
            if seen:
                break
            await asyncio.sleep(0.1)
        await wa.remote.stop_tunnel()
        task.cancel()
        return seen
    assert asyncio.run(main()) == ["https://fake-tunnel-abc.trycloudflare.com"]
    assert wa.remote.urls()[0] == ("Cloudflare Tunnel",
                                   f"https://fake-tunnel-abc.trycloudflare.com/?t={wa.remote.token}")
    from ateam.web import print_remote
    print_remote(wa.remote, only=wa.remote.tunnel_url)
    assert "\x1b[" in capsys.readouterr().out  # mã QR in ra terminal


def test_cli_rejects_bad_combinations(env, project):
    r = ateam(env, project, "web", "--tui", "--host", "0.0.0.0", check=False)
    assert r.returncode == 1 and "--tui" in r.stderr
    r = ateam(env, project, "web", "--public-url", "ateam.example.com", check=False)
    assert r.returncode == 1 and "https://" in r.stderr
    env = dict(env, PATH="/usr/bin:/bin")
    import sys
    r = ateam(dict(env, PATH=os.path.dirname(sys.executable) + ":/usr/bin:/bin"), project, "web", "--tunnel",
              check=False)
    assert r.returncode == 1 and "brew install cloudflared" in r.stderr
