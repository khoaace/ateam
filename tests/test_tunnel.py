"""🌐 /share: public cổng local qua Cloudflare quick tunnel — cú pháp, TunnelManager với cloudflared giả lập,
lệnh /share ở web (hỏi lại lần đầu, ảnh chụp trạng thái) và TUI (nút ở tab Terminal), `ateam share`."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys

import pytest

from conftest import ateam

from ateam import tunnel


def test_parse_port_and_command():
    assert tunnel.parse_port("3000") == 3000
    assert tunnel.parse_port(":5173") == 5173
    assert tunnel.parse_port("localhost:8080") == 8080
    assert tunnel.parse_port("http://127.0.0.1:4000/") == 4000
    assert tunnel.parse_port("70000") is None and tunnel.parse_port("abc") is None
    assert tunnel.parse_command("") == ("list", None, False)
    assert tunnel.parse_command("3000") == ("start", 3000, False)
    assert tunnel.parse_command("3000 --yes") == ("start", 3000, True)
    assert tunnel.parse_command("stop 3000") == ("stop", 3000, False)
    assert tunnel.parse_command("off") == ("stop", None, False)
    for bad in ("abc", "3000 4000", "stop x"):
        with pytest.raises(ValueError):
            tunnel.parse_command(bad)


async def _server():
    """Một 'dev server' nghe 127.0.0.1 ở cổng ngẫu nhiên."""
    async def handle(_r, w):
        w.close()
    srv = await asyncio.start_server(handle, "127.0.0.1", 0)
    return srv, srv.sockets[0].getsockname()[1]


async def _wait(cond, n=100):
    for _ in range(n):
        if cond():
            return True
        await asyncio.sleep(0.1)
    return False


def test_manager_starts_and_stops_tunnel(env, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    seen = []

    async def main():
        srv, port = await _server()
        mgr = tunnel.TunnelManager(lambda t: seen.append((t.port, t.status, t.url)), reserved=(1,))
        with pytest.raises(ValueError, match="ateam web"):
            await mgr.start(1)
        t = await mgr.start(port)
        assert await _wait(lambda: t.url)
        assert t.url == "https://fake-tunnel-abc.trycloudflare.com" and t.status == "up"
        assert await mgr.start(port) is t  # mở lại cùng cổng: dùng tunnel cũ
        assert f"{port} →" in mgr.summary()
        proc = t.proc
        assert await mgr.stop(port) and not mgr.active()
        assert proc.returncode is not None  # cloudflared đã dừng thật
        assert not await mgr.stop(port)
        srv.close()
        # không có gì nghe ở cổng → không mở tunnel
        with pytest.raises(ValueError, match="Không có gì đang chạy"):
            await mgr.start(port)
    asyncio.run(main())
    assert (seen[0][1], seen[-1][1]) == ("starting", "stopped")
    assert any(s == "up" for _p, s, _u in seen)
    log = open(env["ATEAM_FAKE_ARGS_LOG"]).read()
    assert "cloudflared tunnel --no-autoupdate --url http://localhost:" in log


def test_manager_without_cloudflared(env, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PATH", os.path.dirname(sys.executable) + ":/usr/bin:/bin")
    mgr = tunnel.TunnelManager()
    assert "brew install cloudflared" in mgr.check(3000)
    with pytest.raises(ValueError, match="brew install cloudflared"):
        asyncio.run(mgr.start(3000))


def _web(env, project, monkeypatch):
    pytest.importorskip("aiohttp")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.web import WebApp
    ensure_global_config()
    return WebApp(project, load_config(project), DB(project / ".ateam/team.db"), 8123)


def test_web_share_command_confirms_then_shares(env, project, monkeypatch):
    wa = _web(env, project, monkeypatch)

    async def main():
        srv, port = await _server()
        r = await wa.command("/share 8123")  # chính server ateam web
        assert r[1] == "warn" and "📱" in r[0]
        r = await wa.command(f"/share {port}")
        assert r[2]["open"]["confirm"]["cmd"] == f"/share {port} --yes"  # lần đầu: hỏi lại
        assert "ai có link" in r[2]["open"]["confirm"]["text"] and not wa.tunnels.active()
        r = await wa.command(f"/share {port} --yes")
        assert r[1] == "info"
        assert await _wait(lambda: wa.tunnels.get(port) and wa.tunnels.get(port).url)
        snap = wa.snapshot(wa.db.tasks(), wa.db.goals())
        tn = snap["tunnels"][0]
        assert tn["port"] == port and tn["url"].endswith("trycloudflare.com") and tn["svg"].startswith("<svg")
        assert "🌐" in (await wa.command("/share"))[2]["open"]["text"]["body"]
        srv2, port2 = await _server()
        r = await wa.command(f"/share {port2}")  # đã xác nhận trong phiên: không hỏi lại
        assert r[1] == "info" and wa.tunnels.get(port2)
        assert (await wa.command(f"/share stop {port}"))[1] == "info" and not wa.tunnels.get(port)
        assert (await wa.command(f"/share stop {port}"))[1] == "warn"
        assert "1" in (await wa.command("/share stop"))[0] and not wa.tunnels.active()
        assert (await wa.command("/share abc"))[1] == "warn"  # sai cú pháp → cách dùng
        srv.close()
        srv2.close()
    asyncio.run(main())


def test_tui_share_button_and_quit_stops_tunnels(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import ConfirmScreen, TeamApp
    ensure_global_config()
    app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))

    async def main():
        srv, port = await _server()
        async with app.run_test(size=(160, 48)) as pilot:
            async def wait(cond, n=200):
                for _ in range(n):
                    await pilot.pause(0.1)
                    if cond():
                        return True
                return False
            assert await wait(lambda: app._booted)
            # lệnh nền in ra cổng → nút 🌐 Public :cổng ở tab Terminal
            app.run_shell(f"echo 'Local: http://localhost:{port}/'; sleep 30")
            assert await wait(lambda: any(port in j.ports for j in app.shell.jobs.values()))
            app.refresh_view()
            await pilot.pause(0.2)
            from textual.widgets import Button, Static
            btn = app.query_one("#job-share", Button)
            assert await wait(lambda: str(btn.label) == "🌐 Public" and not btn.disabled)
            btn.press()
            assert await wait(lambda: isinstance(app.screen, ConfirmScreen))  # lần đầu: cảnh báo link công khai
            app.screen.dismiss(True)
            assert await wait(lambda: app.tunnels.get(port) is not None and bool(app.tunnels.get(port).url))
            app.refresh_view()
            assert await wait(lambda: str(btn.label) == "🌐 Tắt")
            info = app.query_one("#tunnels-info", Static)
            assert info.display and "trycloudflare.com" in str(info.render())
            proc = app.tunnels.get(port).proc
            await app.action_quit()
        assert proc.returncode is not None  # thoát app: tunnel tắt theo
        srv.close()
    asyncio.run(main())


def test_cli_share_errors(env, project):
    r = ateam(env, project, "share", "abc", check=False)
    assert r.returncode == 1 and "3000" in r.stderr
    r = ateam(env, project, "share", "1", check=False)  # không có gì nghe ở cổng 1
    assert r.returncode == 1 and "Không có gì đang chạy" in r.stderr
    r = ateam(dict(env, PATH=os.path.dirname(sys.executable) + ":/usr/bin:/bin"), project, "share", "3000",
              check=False)
    assert r.returncode == 1 and "brew install cloudflared" in r.stderr
