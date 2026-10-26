"""⌨ Shell tương tác ở tab Terminal: shell rời của GridHub (không thuộc bố cục Lưới), web (grid_shell, /term),
TUI (tự mở khi vào tab, ⌨ Trong shell, /term) và shell ở worktree của task (merge gồm phần sửa tay)."""

from __future__ import annotations

import asyncio
import base64
import importlib
import re
import subprocess

from conftest import ateam, git_init, write_project_config


async def _until(pred, timeout=10):
    for _ in range(int(timeout / 0.05)):
        if pred():
            return True
        await asyncio.sleep(0.05)
    return False


def _env(env, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config
    ensure_global_config()


def test_hub_loose_shells(env, project, monkeypatch):
    _env(env, monkeypatch)
    from ateam.config import load_config
    from ateam.grid import GridHub, load_layout
    cfg = load_config(project)
    sub = project / "sub"
    sub.mkdir()

    async def main():
        hub = GridHub(project, lambda: cfg, lambda a: None)
        events = []
        hub.listen(lambda cid, kind, p: events.append((cid, kind)))

        def out(cid):
            return re.sub(rb"\x1b\[[0-9;?]*[a-zA-Z]", b"", bytes(hub.terms[cid].buf))
        a, err = await hub.add_shell()
        assert a and not err and hub.status(a) == "run"
        hub.write(a, b"echo xin-$((1+1))\r")
        assert await _until(lambda: b"xin-2" in out(a))
        # lệnh gõ sẵn chạy ngay; thư mục riêng (worktree của task)
        b, _ = await hub.add_shell(str(sub), task=7, cmd="pwd")
        assert await _until(lambda: str(sub).encode() in out(b))
        sh = hub.shells()
        assert [x["title"] for x in sh] == ["sh #1", "sh #2"] and sh[1]["task"] == 7 and sh[0]["status"] == "run"
        assert sh[0]["cwd"] == "" and sh[1]["cwd"] == "sub"
        # không thuộc Lưới: bố cục và grid.json không đổi
        assert hub.state()["cols"] == [] and not load_layout(project).cells()
        assert not (project / ".ateam" / "grid.json").exists()
        hub.close_task_shells(7)
        assert b not in hub.loose and b not in hub.terms and (b, "layout") in events
        hub.write(a, b"exit\r")
        assert await _until(lambda: hub.status(a) == "exit")
        assert hub.shells()[0]["status"] == "exit"
        assert await hub.start(a) == "" and hub.status(a) == "run"  # mở lại, giữ output cũ
        assert b"xin-2" in out(a)
        c, _ = await hub.add_shell()
        assert hub.shells()[-1]["title"] == "sh #2"
        hub.shutdown()
    asyncio.run(main())


def test_web_shell_ops(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    _env(env, monkeypatch)
    from aiohttp.test_utils import TestClient, TestServer
    from ateam.config import load_config
    from ateam.db import DB
    from ateam.web import WebApp
    from test_web import _free_port
    port = _free_port()
    wa = WebApp(project, load_config(project), DB(project / ".ateam/team.db"), port)

    async def recv_until(ws, pred, n=400):
        for _ in range(n):
            m = await ws.receive_json(timeout=10)
            if pred(m):
                return m
        raise AssertionError("không nhận được tin mong đợi")

    def has(m, cid, text):
        return m["t"] == "gpty" and m["id"] == cid and text in base64.b64decode(m["data"])

    async def main():
        c = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=port))
        await c.start_server()
        try:
            hdr = {"Origin": f"http://127.0.0.1:{port}"}
            ws = await c.ws_connect("/ws", headers=hdr)
            await ws.send_json({"op": "grid_attach"})
            await ws.send_json({"op": "grid_shell", "rows": 20, "cols": 70, "ref": 1})
            cid = (await recv_until(ws, lambda m: m["t"] == "toast" and m.get("ref") == 1))["open"]["term"]
            await ws.send_json({"op": "grid_in", "id": cid, "data": "echo hi-$((2+3))\r"})
            await recv_until(ws, lambda m: has(m, cid, b"hi-5"))
            st = await recv_until(ws, lambda m: m["t"] == "state" and m["shells"])
            assert [x["id"] for x in st["shells"]] == [cid] and wa.grid.state()["cols"] == []
            # /term <lệnh>: shell mới chạy lệnh; /term trống: tới shell đang có
            await ws.send_json({"op": "submit", "text": "/term echo tu-lenh", "ref": 2})
            cid2 = (await recv_until(ws, lambda m: m["t"] == "toast" and m.get("ref") == 2))["open"]["term"]
            await recv_until(ws, lambda m: has(m, cid2, b"tu-lenh\r\n"))
            await ws.send_json({"op": "submit", "text": "/term", "ref": 3})
            assert (await recv_until(ws, lambda m: m.get("ref") == 3))["open"] == {"term": "focus"}
            await ws.send_json({"op": "submit", "text": "/term #99", "ref": 4})
            r = await recv_until(ws, lambda m: m.get("ref") == 4)
            assert r["level"] == "warn" and "#99" in r["text"]
            # tab mở sau nhận lại output của shell
            ws2 = await c.ws_connect("/ws", headers=hdr)
            await ws2.send_json({"op": "grid_attach"})
            rep = await recv_until(ws2, lambda m: m["t"] == "gpty" and m.get("replay") and m["id"] == cid)
            assert b"hi-5" in base64.b64decode(rep["data"])
            await ws2.close()
            # ■ Dừng trên dòng shell: dừng tiến trình nhưng giữ shell trong danh sách (↻ Mở lại chạy tiếp)
            await ws.send_json({"op": "grid_stop", "id": cid2})
            st = await recv_until(ws, lambda m: m["t"] == "state"
                                  and any(x["id"] == cid2 and x["status"] == "exit" for x in m["shells"]))
            assert {x["id"] for x in st["shells"]} == {cid, cid2}
            await ws.send_json({"op": "grid_close", "id": cid2})
            assert await _until(lambda: list(wa.grid.loose) == [cid] and cid2 not in wa.grid.terms)
            await ws.close()
            wa.remote.readonly = True  # --readonly: không mở shell được
            r = await wa.grid_op(None, {"op": "grid_shell"})
            assert r[1] == "warn" and len(wa.grid.loose) == 1
        finally:
            wa.grid.shutdown()
            await c.close()
    asyncio.run(main())


def test_tui_terminal_shell(env, project, monkeypatch):
    _env(env, monkeypatch)
    from ateam.config import load_config
    from ateam.db import DB
    from ateam.tui import TeamApp
    from ateam.tui_grid import TermView
    app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))

    async def main():
        async with app.run_test(size=(160, 48)) as pilot:
            async def wait(cond, n=200):
                for _ in range(n):
                    await pilot.pause(0.1)
                    if cond():
                        return True
                return False

            def screen_text(cid):
                return "\n".join("".join(ch for ch, _a in row) for row in app.grid_screen(cid).lines)
            # !lệnh đưa tới tab Terminal nhưng không tự mở shell
            app.run_shell("echo nen")
            assert await wait(lambda: app.query_one("#tabs").active == "tab-term" and app.shell.jobs)
            await pilot.pause(0.3)
            assert not app.grid.loose and app.view_shell is None
            # s ở danh sách lệnh !: chạy lại lệnh đó trong shell tương tác
            app.query_one("#jobs").focus()
            await pilot.press("s")
            assert await wait(lambda: len(app.grid.loose) == 1 and isinstance(app.focused, TermView))
            cid = app.view_shell
            assert await wait(lambda: "nen" in screen_text(cid))
            assert not app.query_one("#job-log").display and app.query_one("#sh-view").display
            # gõ phím trong khung: vào pty
            await pilot.press(*"echo go-$((3+4))", "enter")
            assert await wait(lambda: "go-7" in screen_text(cid))
            # /term <lệnh>: shell thứ hai; danh sách bên trái có cả hai
            app.run_command("/term echo hai")
            assert await wait(lambda: len(app.grid.loose) == 2 and app.view_shell != cid)
            assert await wait(lambda: app.query_one("#shells").option_count == 2)
            # ✕ Đóng: về shell còn lại
            app.query_one("#sh-close").press()
            assert await wait(lambda: len(app.grid.loose) == 1 and app.view_shell == cid)
            # chọn lệnh ! ở danh sách: khung phải về output
            app.query_one("#jobs").focus()
            await pilot.press("enter")
            assert await wait(lambda: app.view_shell is None and app.query_one("#job-log").display)
            app.run_command("/term")
            assert await wait(lambda: app.view_shell == cid and isinstance(app.focused, TermView))
            assert not app.grid.layout.cells()
            await pilot.press("ctrl+q")
    asyncio.run(main())


def test_task_shell_worktree_merge_and_reject(env, project, monkeypatch):
    git_init(project)
    write_project_config(project, 'isolation = "worktree"\nmerge = "review"\n')
    ateam(env, project, "add", "--to", "grok", "tạo b")
    ateam(env, project, "add", "--to", "codex", "tạo a")
    ateam(env, project, "run", "-q")
    _env(env, monkeypatch)
    from ateam.config import load_config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    o = Orchestrator(project, load_config(project), DB(project / ".ateam/team.db"))
    released = []
    o.on_shell_release = released.append

    def branches():
        return subprocess.run(["git", "branch", "--list", "ateam/*"], cwd=project, capture_output=True,
                              text=True).stdout

    async def main():
        await o.setup()
        path, err = await o.task_shell_dir(1)
        assert not err and path == project / ".ateam" / "worktrees" / "sh-t1" and (path / "b.txt").exists()
        assert (await o.task_shell_dir(1))[0] == path  # mở lại: dùng lại worktree
        (path / "sua-tay.txt").write_text("sửa trong shell\n")
        assert "Đã merge #1" in await o.merge(1)
        assert (project / "b.txt").exists() and (project / "sua-tay.txt").exists()
        assert not path.exists() and released == [1] and "ateam/t1" not in branches()
        path2, _ = await o.task_shell_dir(2)
        (path2 / "bo.txt").write_text("x")
        await o.reject(2, None)
        assert not path2.exists() and released == [1, 2] and "ateam/t2" not in branches()
        assert not (project / "bo.txt").exists()
        assert (await o.task_shell_dir(2))[0] is None  # không còn nhánh
    asyncio.run(main())
