"""Chat trực tiếp với agent (ô 💬 tab Đội, /chat): mỗi tin là một lượt nối đúng phiên CLI, chạy ở thư mục gốc,
không verify / worktree / giao việc chéo, không hiện trên bảng việc; "Mở trong terminal" mở CLI thật."""

from __future__ import annotations

import asyncio
import importlib
import sys

from conftest import ateam, git_init, write_project_config

from ateam.config import AgentConfig


def _orch(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import load_config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    return Orchestrator(project, load_config(project), DB(project / ".ateam/team.db"))


def test_chat_turns_resume_same_session(env, project, monkeypatch, tmp_path):
    git_init(project)
    write_project_config(project, 'isolation = "worktree"\n')
    ateam(env, project, "verify", "exit 1")  # chat không chạy lệnh kiểm tra
    o = _orch(env, project, monkeypatch)
    args = tmp_path / "args.log"

    async def main():
        await o.setup()
        t1 = o.chat("claude", "xin chào")
        assert isinstance(t1, int)
        assert "đang trả lời" in o.chat("claude", "tin thứ hai")  # một lượt một lúc
        await o.run_until_idle()
        a = o.db.task(t1)
        assert a.status == "done" and a.source == "chat" and a.session and not a.branch  # không worktree
        t2 = o.chat("claude", "tiếp nhé")
        await o.run_until_idle()
        b = o.db.task(t2)
        assert b.status == "done" and b.parent_id == t1 and b.session == a.session
        t3 = o.chat("claude", "chuyện khác", new=True)
        await o.run_until_idle()
        c = o.db.task(t3)
        assert c.parent_id is None and c.session != a.session
        assert o.finished_ids()[0] == []  # /clear không dọn mất cuộc chat
        assert o.terminal_session("claude") == c.session
        return a, b
    a, b = asyncio.run(main())
    calls = [ln for ln in args.read_text().splitlines() if ln.startswith("claude")]
    assert f"--session-id {a.session}" in calls[0] and f"--resume {a.session}" in calls[1]


def test_chat_rejects_unknown_agent_and_empty(env, project, monkeypatch):
    o = _orch(env, project, monkeypatch)
    assert "Không có agent" in o.chat("khong-co", "x")
    assert "Gõ nội dung" in o.chat("claude", "  ")


def test_interactive_argv():
    assert AgentConfig("claude", ["claude", "-p", "{prompt}"]).interactive_argv("s1") == ["claude", "--resume", "s1"]
    assert AgentConfig("codex", ["codex", "exec", "{prompt}"]).interactive_argv("s1") == ["codex", "resume", "s1"]
    assert AgentConfig("codex", ["codex", "exec", "{prompt}"]).interactive_argv(None) == ["codex"]
    assert AgentConfig("opencode", ["opencode", "run", "{prompt}"]).interactive_argv("s1") == ["opencode"]
    assert AgentConfig("x", ["bash", "-c", "…", "_"]).interactive_argv("s1") is None


def test_tui_chat_box(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import AgentPane, TeamApp, TextInput

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            app.run_command("/chat codex")
            await pilot.pause(0.3)
            pane = app.pane("codex")
            assert app.focused is pane.query_one(".pane-chat")
            await pilot.press(*"lam gi vay")
            await pilot.press("enter")
            for _ in range(60):
                await pilot.pause(0.25)
                ts = app.db.tasks()
                if ts and ts[0].status == "done":
                    break
            t = app.db.tasks()[0]
            assert t.source == "chat" and t.status == "done" and t.prompt == "lam gi vay"
            assert not app.query_one("#tasks").row_count  # không hiện ở bảng việc
            assert any("bạn: lam gi vay" in ln.text for ln in pane.body.lines)
            assert isinstance(pane, AgentPane)
            # ô chat là TextInput: bộ gõ gửi dấu tách rời (e + ^ + .) vẫn ghép thành chữ dựng sẵn
            chat = pane.query_one(".pane-chat")
            assert isinstance(chat, TextInput)
            chat.insert_text_at_cursor("tie\u0302\u0301ng vie\u0302\u0323t")
            assert chat.value == "tiếng việt"
            chat.value = ""
            # /chat phóng to ô của agent (log + ô chat), các ô khác, danh sách và Timeline ẩn; Esc / F7 thu lại
            assert app.focus_agent == "codex"
            assert app.pane("claude").has_class("unfocused") and not pane.has_class("unfocused")
            assert pane.region.width > 120 and app.query_one("#timeline").region.height == 0
            await pilot.press("escape")
            await pilot.pause(0.1)
            assert app.focus_agent is None and not app.pane("claude").has_class("unfocused")
            await pilot.press("f7")  # F7 ở danh sách: phóng to trưởng nhóm
            await pilot.pause(0.1)
            assert app.focus_agent == "claude"
            await pilot.press("f7")
            await pilot.pause(0.1)
            assert app.focus_agent is None
            app.run_command("/focus claude")
            await pilot.pause(0.1)
            assert app.focus_agent == "claude" and app.focused is app.pane("claude").query_one(".pane-chat")
            app.run_command("/focus")
            assert app.focus_agent is None
            app.query_one("#cmd").focus()
            # tab Agents ở dạng danh sách: chỉ còn dòng tiêu đề mỗi agent, log + ô chat ẩn tới khi phóng to
            assert not app.pane("claude").body.display and app.pane("claude").head.region.height > 0
            await pilot.press("alt+6")  # Alt+số: tới thẳng tab (1 Bảng việc, 2 Agents, 3 Workflows, 4 Code, 5 Git, 6 Terminal…)
            await pilot.pause(0.1)
            assert app.query_one("#tabs").active == "tab-term"
            await pilot.press("alt+1")
            await pilot.pause(0.1)
            assert app.query_one("#tabs").active == "tab-board"
            await pilot.press("ctrl+q")
    asyncio.run(main())


def test_pty_session_echo_resize_close():
    from ateam.pty_session import PtySession
    out, done = bytearray(), []

    async def until(pred, timeout=10):
        for _ in range(int(timeout / 0.05)):
            if pred():
                return True
            await asyncio.sleep(0.05)
        return False

    async def main():
        code = ("import os, signal, sys, termios\n"
                "a = termios.tcgetattr(0); a[3] &= ~termios.ECHO; termios.tcsetattr(0, termios.TCSANOW, a)\n"
                "signal.signal(signal.SIGWINCH, lambda *_: print(*os.get_terminal_size()[::-1], flush=True))\n"
                "for line in sys.stdin: print(line.strip(), flush=True)\n")
        s = PtySession([sys.executable, "-c", code], ".", {"PATH": "/usr/bin:/bin"},
                       on_data=out.extend, on_exit=done.append, rows=20, cols=80)
        await s.start()
        await asyncio.sleep(0.3)
        s.write(b"xin chao\n")
        assert await until(lambda: b"xin chao" in out)
        s.resize(33, 111)  # terminal điều khiển là pty: tiến trình nhận SIGWINCH
        assert await until(lambda: b"33 111" in out)
        s.close()
        assert await until(lambda: done)
    asyncio.run(main())


def test_web_pty_open_runs_agent_cli(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from aiohttp.test_utils import TestClient, TestServer
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.web import WebApp
    ensure_global_config()
    from test_web import _free_port
    port = _free_port()
    wa = WebApp(project, load_config(project), DB(project / ".ateam/team.db"), port)

    async def main():
        c = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=port))
        await c.start_server()
        try:
            ws = await c.ws_connect("/ws", headers={"Origin": f"http://127.0.0.1:{port}"})
            await ws.send_json({"op": "pty_open", "agent": "claude", "rows": 24, "cols": 80, "ref": 1})
            got = {}
            for _ in range(200):
                m = await ws.receive_json(timeout=10)
                if m["t"] == "toast" and m.get("ref") == 1:
                    got["open"] = m["open"]
                elif m["t"] == "pty":
                    if not got.get("data"):  # claude giả lập ở chế độ tương tác: gõ exit để thoát
                        await ws.send_json({"op": "pty_in", "id": m["id"], "data": "exit\r"})
                    got.setdefault("data", True)
                elif m["t"] == "pty_exit":
                    got["exit"] = m
                    break
            assert got["open"]["pty"] and "claude" in got["open"]["title"] and got.get("data")
            assert not wa.ptys  # thoát thì được dọn
            await ws.send_json({"op": "pty_open", "agent": "khong-co", "ref": 2})
            while True:
                m = await ws.receive_json(timeout=10)
                if m["t"] == "toast" and m.get("ref") == 2:
                    assert m["level"] == "warn"
                    break
            await ws.close()
        finally:
            await c.close()
    asyncio.run(main())


def test_web_focus_command(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.web import WebApp
    ensure_global_config()
    wa = WebApp(project, load_config(project), DB(project / ".ateam/team.db"), 8124)
    r = asyncio.run(wa.handle({"op": "submit", "text": "/focus codex"}))
    assert r[2]["open"] == {"view": "team", "focus": "codex"}
    assert asyncio.run(wa.handle({"op": "submit", "text": "/focus"}))[2]["open"]["focus"] == ""
    assert asyncio.run(wa.handle({"op": "submit", "text": "/focus khong-co"}))[1] == "warn"
