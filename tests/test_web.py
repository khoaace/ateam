"""`ateam web` (giao diện qua textual-serve) và khoá chỉ-1-phiên giao diện."""

from __future__ import annotations

import asyncio
import os
import shlex
import sys
import types

from ateam import cli, i18n


def test_web_tui_needs_textual_serve(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "textual_serve.server", None)  # import -> ImportError
    assert cli.main(["-C", str(tmp_path), "web", "--tui"]) == 1
    out = capsys.readouterr().out
    assert "textual-serve" in out and "pip install" in out


def test_web_needs_aiohttp(tmp_path, monkeypatch, capsys):
    import ateam
    monkeypatch.setitem(sys.modules, "ateam.web", None)  # như máy chưa cài aiohttp
    monkeypatch.delattr(ateam, "web", raising=False)  # đã import ở test khác: `from . import web` lấy thuộc tính
    assert cli.main(["-C", str(tmp_path), "web"]) == 1
    out = capsys.readouterr().out
    assert "aiohttp" in out and "pip install" in out


def test_web_serves_tui_on_localhost(tmp_path, monkeypatch):
    seen = {}

    class FakeServer:
        def __init__(self, command, host, port, title):
            seen.update(command=command, host=host, port=port, title=title)

        def serve(self):
            seen["served"] = True

    mod = types.ModuleType("textual_serve.server")
    mod.Server = FakeServer
    monkeypatch.setitem(sys.modules, "textual_serve", types.ModuleType("textual_serve"))
    monkeypatch.setitem(sys.modules, "textual_serve.server", mod)
    root = tmp_path / "dự án"
    root.mkdir()
    monkeypatch.setattr(i18n, "_lang", i18n.get_lang())  # --lang đổi ngôn ngữ toàn cục -> trả lại sau test
    monkeypatch.setenv("ATEAM_LANG", "vi")
    assert cli.main(["-C", str(root), "--lang", "en", "web", "--tui", "--port", "8123"]) == 0
    assert seen["served"] and seen["host"] == "127.0.0.1" and seen["port"] == 8123
    # --lang qua biến môi trường, không ghim vào lệnh (nút Restart chạy lại đúng lệnh này)
    assert shlex.split(seen["command"]) == [sys.executable, "-m", "ateam", "-C", str(root.resolve()), "tui"]
    assert os.environ["ATEAM_LANG"] == "en"


def test_lang_restart_skips_execv_under_web(tmp_path, monkeypatch):
    """/lang dưới `ateam web`: không execv (tiến trình mới sẽ mồ côi, giữ khoá) — để nút Restart của trình duyệt mở lại."""
    import ateam.tui

    class FakeApp:
        def __init__(self, *a, **kw):
            self.restart_requested = True

        def run(self):
            pass

    execs = []
    monkeypatch.setattr(ateam.tui, "TeamApp", FakeApp)
    monkeypatch.setattr(cli, "ensure_global_config", lambda: [])
    monkeypatch.setattr(cli, "needs_setup", lambda: False)
    monkeypatch.setattr(cli.os, "execv", lambda *a: execs.append(a))
    monkeypatch.setenv("TEXTUAL_DRIVER", "textual.drivers.web_driver:WebDriver")
    assert cli.main(["-C", str(tmp_path), "tui"]) == 0
    assert execs == []
    monkeypatch.delenv("TEXTUAL_DRIVER")
    assert cli.main(["-C", str(tmp_path), "tui"]) == 0
    assert len(execs) == 1  # trong terminal vẫn mở lại như cũ


def test_session_lock_allows_one(tmp_path):
    first = cli.acquire_session_lock(tmp_path)
    assert first is not None
    assert cli.acquire_session_lock(tmp_path) is None  # phiên thứ hai bị chặn
    first.close()  # phiên đầu thoát -> mở lại được
    again = cli.acquire_session_lock(tmp_path)
    assert again is not None
    again.close()


def test_busy_app_shows_message_and_quits():
    from textual.widgets import Static

    from ateam.tui import BusyApp

    async def main():
        app = BusyApp()
        async with app.run_test() as pilot:
            assert "phiên ateam khác" in str(app.query_one("#busy", Static).render())
            await pilot.press("ctrl+q")
            await pilot.pause()
        assert app.return_code == 0

    asyncio.run(main())


# ---------------------------------------------------------------------------- giao diện web (ateam/web.py)
def _free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_web_ui_end_to_end(env, project, monkeypatch):
    """Server thật + agent giả lập: trang, chặn Host/Origin lạ, WebSocket giao mục tiêu → duyệt → chạy xong,
    lệnh terminal, lệnh chưa có trên web."""
    pytest = __import__("pytest")
    pytest.importorskip("aiohttp")
    import importlib

    import aiohttp
    from aiohttp.test_utils import TestClient, TestServer

    from conftest import git_init

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    import ateam.config
    importlib.reload(ateam.config)  # đọc XDG_CONFIG_HOME của test
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.web import WebApp

    async def main():
        ensure_global_config()
        port = _free_port()
        wa = WebApp(project, load_config(project), DB(project / ".ateam/team.db"), port)
        client = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=port))
        await client.start_server()
        try:
            r = await client.get("/")
            assert r.status == 200 and "/static/app.js" in await r.text()
            assert (await client.get("/static/app.css")).status == 200
            # DNS rebinding / trang web lạ: chặn
            assert (await client.get("/", headers={"Host": "evil.example"})).status == 403
            try:
                await client.ws_connect("/ws", headers={"Origin": "http://evil.example"})
                raise AssertionError("WebSocket từ origin lạ phải bị chặn")
            except aiohttp.WSServerHandshakeError as e:
                assert e.status == 403

            ws = await client.ws_connect("/ws", headers={"Origin": f"http://127.0.0.1:{port}"})
            hello = await ws.receive_json(timeout=10)
            assert hello["t"] == "hello" and hello["T"]["board"] and hello["project"] == project.name
            from ateam.tui import COMMANDS
            assert {c["name"] for c in hello["commands"]} == {c[0] for c in COMMANDS}  # đủ lệnh như TUI
            a0 = hello["agents"][0]  # dữ liệu gợi ý /task agent:model@effort
            assert {"name", "models", "efforts", "model", "effort"} <= set(a0)
            state = await ws.receive_json(timeout=10)
            assert state["t"] == "state" and state["goals"] == []

            async def until(cond, timeout=90):
                loop = asyncio.get_running_loop()
                end = loop.time() + timeout
                while loop.time() < end:
                    m = await ws.receive_json(timeout=max(0.1, end - loop.time()))
                    if cond(m):
                        return m
                raise AssertionError("hết giờ chờ")

            def state_with(pred):
                return lambda m: m["t"] == "state" and pred(m)

            await ws.send_json({"op": "submit", "text": "Tạo vài file"})
            st = await until(state_with(lambda m: any(g["status"] == "awaiting" for g in m["goals"])))
            gid = next(g["id"] for g in st["goals"] if g["status"] == "awaiting")
            assert any(t["status"] == "draft" and t["goal"] == gid for t in st["tasks"])
            await ws.send_json({"op": "approve", "goal": gid})
            toast = await until(lambda m: m["t"] == "toast")
            assert toast["level"] == "ok"
            await until(state_with(lambda m: all(t["status"] not in ("draft", "queued", "running")
                                                 for t in m["tasks"] if t["goal"] == gid)
                                   and any(t["status"] == "done" for t in m["tasks"])))
            tid = next(t.id for t in wa.db.tasks() if t.status == "done")
            log = await (await client.get(f"/api/log/{tid}")).json()
            assert log["lines"], "log của task phải đọc được qua /api/log"

            await ws.send_json({"op": "submit", "text": "!echo xin-chao-web"})
            opened = await until(lambda m: m["t"] == "toast" and "open" in m)
            jid = opened["open"]["job"]
            await until(lambda m: m["t"] == "job" and m["id"] == jid and "xin-chao-web" in m["line"])

            await ws.send_json({"op": "submit", "text": "/khonglenhnay"})
            warn = await until(lambda m: m["t"] == "toast" and m["text"])
            assert warn["level"] == "warn" and "/khonglenhnay" in warn["text"]
            await ws.send_json({"op": "submit", "text": "/git", "ref": 7})  # lệnh mở tab: trả "open"
            opened = await until(lambda m: m["t"] == "toast" and m.get("ref") == 7)
            assert opened["open"] == {"view": "git"}
            await ws.close()
        finally:
            await client.close()

    asyncio.run(main())


def test_web_js_uses_only_translated_strings():
    """Chữ hiển thị trên web phải qua ui_strings() (có bản dịch) — JS/HTML không viết thẳng tiếng Việt,
    và mọi khoá t("…")/data-t JS dùng đều có trong ui_strings()."""
    import re
    from pathlib import Path

    import pytest
    pytest.importorskip("aiohttp")
    from ateam.web import STATIC, ui_strings

    VI = re.compile(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.I)
    keys = set(ui_strings())
    files = sorted(f.name for f in STATIC.iterdir() if f.suffix in (".js", ".html"))  # vendor/ (CodeMirror) bỏ qua
    assert {"app.js", "git.js", "code.js", "diff.js", "setup.js", "dash.js", "index.html"} <= set(files)
    for f in files:
        text = Path(STATIC / f).read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/|(?<![:\"'])//[^\n]*|<!--.*?-->", "", text, flags=re.S)  # bỏ chú thích
        assert not VI.search(code), f"{f} có chữ tiếng Việt viết thẳng: {VI.search(code).group()!r}"
        used = set(re.findall(r'\bt\("([a-z_]+)"', text)) | set(re.findall(r'data-t="([a-z_]+)"', text))
        prefixes = {k for k in used if k.endswith("_")}  # khoá ghép: t("col_" + cột), t("g_" + trạng thái)…
        assert used - prefixes <= keys, f"{f} dùng khoá chưa có trong ui_strings(): {sorted(used - prefixes - keys)}"
        for pre in prefixes:
            assert any(k.startswith(pre) for k in keys), f"không có khoá nào bắt đầu bằng {pre!r}"
    for st in ("planning", "awaiting", "running", "reviewing", "done", "incomplete", "failed", "cancelled", "grilling"):
        assert "g_" + st in keys  # mọi trạng thái mục tiêu (db.Goal) có nhãn



def test_web_handles_every_tui_command():
    """Mọi lệnh trong tui.COMMANDS phải có nhánh xử lý trong WebApp._command — giữ hai giao diện đồng bộ."""
    import inspect
    import re

    import pytest
    pytest.importorskip("aiohttp")
    from ateam.tui import COMMANDS
    from ateam.web import WebApp

    src = inspect.getsource(WebApp._command)
    handled = set()
    for m in re.finditer(r"cmd (?:==|in) (\([^)]*\)|\"[^\"]+\")", src):
        handled |= set(re.findall(r'"([^"]+)"', m.group(1)))
    missing = sorted({c[0] for c in COMMANDS} - handled)
    assert not missing, f"Lệnh TUI chưa có ở web (thêm vào WebApp._command): {missing}"


def _web_app(env, project, monkeypatch):
    import importlib

    from conftest import git_init
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.web import WebApp
    ensure_global_config()
    return WebApp(project, load_config(project), DB(project / ".ateam/team.db"), _free_port())


def test_web_git_ops_and_diff(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer
    wa = _web_app(env, project, monkeypatch)

    async def main():
        client = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=wa.port))
        await client.start_server()
        try:
            (project / "base.txt").write_text("base\ndòng mới\n")
            (project / "new.py").write_text("def add(a, b):\n    return a + b\n")
            st = await (await client.get("/api/git/status")).json()
            assert st["is_repo"] and {f["path"] for f in st["groups"]["w"]} == {"base.txt", "new.py"}
            # diff chưa stage: kèm file mới, cột đôi + token tô màu
            d = await (await client.get("/api/git/diff?kind=unstaged&path=new.py")).json()
            assert d["files"][d["start"]]["path"] == "new.py"
            f = next(x for x in d["files"] if x["path"] == "base.txt")
            assert f["hunks"][0]["rows"] and any(ln["k"] == "+" for ln in f["hunks"][0]["lines"])
            py = next(x for x in d["files"] if x["path"] == "new.py")
            assert ["k", "def"] in py["hunks"][0]["lines"][0]["t"]  # pygments: từ khoá
            r = await wa.handle({"op": "git", "action": "stage", "path": "new.py"})
            assert r[1] == "ok"
            st = await (await client.get("/api/git/status")).json()
            assert [f["path"] for f in st["groups"]["s"]] == ["new.py"]
            r = await wa.handle({"op": "git", "action": "commit", "message": "thêm add"})
            assert r[1] == "ok" and r[2]["committed"]
            log = await (await client.get("/api/git/log")).json()
            assert log[0]["subject"] == "thêm add"
            cd = await (await client.get(f"/api/git/diff?commit={log[0]['sha']}")).json()
            assert [x["path"] for x in cd["files"]] == ["new.py"]
            # amend giữ message khi trống
            r = await wa.handle({"op": "git", "action": "commit", "message": "", "amend": True})
            assert r[1] == "ok"
            # nhánh + stash
            assert (await wa.handle({"op": "git", "action": "create_branch", "name": "thu-nghiem"}))[1] == "ok"
            br = await (await client.get("/api/git/branches")).json()
            assert next(b for b in br if b["current"])["name"] == "thu-nghiem"
            (project / "base.txt").write_text("base\nsửa tạm\n")  # amend lúc chưa stage gì đã commit hết (như TUI)
            assert (await wa.handle({"op": "git", "action": "stash_push", "message": "tạm"}))[1] == "ok"
            assert (await client.get("/api/git/stashes")).status == 200
            assert len(await (await client.get("/api/git/stashes")).json()) == 1
            assert (await wa.handle({"op": "git", "action": "stash_pop"}))[1] == "ok"
            assert (await wa.handle({"op": "git", "action": "discard", "path": "base.txt"}))[1] == "ok"
            assert "sửa tạm" not in (project / "base.txt").read_text()
            # chọn agent viết commit message (mặc định trưởng nhóm) — lưu state.json, dùng chung TUI
            from ateam.config import load_state
            (project / "base.txt").write_text("base\nlần nữa\n")
            assert (await wa.handle({"op": "git", "action": "commit_agent", "name": "khong-co"}))[1] == "warn"
            assert (await wa.handle({"op": "git", "action": "commit_agent", "name": "codex"}))[1] == ""
            assert wa.snapshot()["commit_agent"] == "codex" and load_state()["commit_agent"] == "codex"
            r = await wa.handle({"op": "git", "action": "ai_message"})
            assert r[2]["git_msg"] == "Codex viết message này"
            await wa.handle({"op": "git", "action": "commit_agent", "name": ""})
            assert "commit_agent" not in load_state()
            r = await wa.handle({"op": "git", "action": "ai_message"})
            assert r[2]["git_msg"].startswith("Thêm file mới cho bản demo")
            assert (await wa.handle({"op": "git", "action": "discard", "path": "base.txt"}))[1] == "ok"
            # đổi nhánh khi agent đang chạy: từ chối như TUI
            wa.orch.runs[999] = None
            r = await wa.handle({"op": "git", "action": "checkout", "name": "master"})
            assert r[1] == "warn"
            wa.orch.runs.clear()
            r = await wa.command("/commit --no-verify")
            assert r[1] == "warn"  # thiếu message
        finally:
            await client.close()

    asyncio.run(main())


def test_web_code_files(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer
    wa = _web_app(env, project, monkeypatch)
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("print('hi')\r\n")
    (project / "blob.bin").write_bytes(b"\0\1\2")

    async def main():
        client = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=wa.port))
        await client.start_server()
        try:
            root = await (await client.get("/api/tree?dir=&refresh=1")).json()
            names = [n["name"] for n in root]
            assert names[0] == "src" and root[0]["dir"] and ".git" not in names and ".ateam" not in names
            sub = await (await client.get("/api/tree?dir=src")).json()
            assert [n["path"] for n in sub] == ["src/app.py"]
            f = await (await client.get("/api/file?path=src/app.py")).json()
            assert f["text"] == "print('hi')\n" and f["newline"] == "\r\n" and f["language"] == "Python"
            r = wa.code.save({"path": "src/app.py", "text": "print('xin chào')\n", "mtime": f["mtime"]})
            assert r[1] == "ok" and r[2]["save"]["mtime"]
            assert (project / "src" / "app.py").read_bytes() == "print('xin chào')\r\n".encode()  # giữ CRLF
            # agent sửa file trong lúc đang mở -> xung đột, ghi đè khi force
            r = wa.code.save({"path": "src/app.py", "text": "x\n", "mtime": f["mtime"]})
            assert r[2]["save"]["conflict"]
            assert wa.code.save({"path": "src/app.py", "text": "x\n", "mtime": f["mtime"], "force": True})[1] == "ok"
            # file mới
            assert wa.code.save({"path": "docs/moi.md", "text": "# mới\n", "mtime": 0})[1] == "ok"
            assert (project / "docs" / "moi.md").exists()
            # ngoài dự án / .git / nhị phân: từ chối
            for bad in ("../ngoai.txt", "/etc/passwd", ".git/config", "src/../../x"):
                assert "error" in await (await client.get("/api/file?path=" + bad)).json()
                assert wa.code.save({"path": bad, "text": "x", "mtime": 0})[1] == "error"
            assert not (project.parent / "ngoai.txt").exists()
            assert "error" in await (await client.get("/api/file?path=blob.bin")).json()
            r = await wa.command("/code @src/app.py:3")
            assert r[2]["open"]["code"] == {"path": "src/app.py", "line": 3}
        finally:
            await client.close()

    asyncio.run(main())


def test_web_setup_and_custom(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer
    wa = _web_app(env, project, monkeypatch)

    async def main():
        client = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=wa.port))
        await client.start_server()
        try:
            st = await (await client.get("/api/setup")).json()
            assert [s["key"] for s in st["steps"]] == ["cli", "style", "tier", "roles", "safety", "verify", "review"]
            assert "claude" in st["init"]["installed"]  # CLI giả lập trong PATH
            assign = await (await client.get("/api/setup/assign?providers=claude,codex&tier=eco")).json()
            assert assign["lead"][0] in ("claude", "codex")
            assign["lead"] = ["codex", "", ""]
            plan = await (await client.get("/api/setup/plan?assign=" + __import__("json").dumps(assign))).json()
            assert plan["lead"] == "codex"
            r = await wa.handle({"op": "setup_save", "providers": ["claude", "codex"], "style": "auto", "tier": "eco",
                                 "assign": assign, "access": "safe", "apply": "shared", "verify": "make test"})
            assert r[1] == "ok"
            assert wa.cfg.lead == "codex" and not wa.cfg.approve_plan and wa.cfg.verify.command == "make test"
            from ateam.config import load_state
            assert load_state()["lead"] == "codex"
            # chưa có trưởng nhóm -> lỗi, không lưu
            bad = dict(assign, lead=None)
            assert (await wa.handle({"op": "setup_save", "assign": bad}))[1] == "error"

            # /custom: agent nhanh, sửa sai tên, xoá
            q = await (await client.get("/api/custom/quick?provider=claude")).json()
            assert q["name"].startswith("claude")
            r = await wa.handle({"op": "custom_save", "kind": "agents", "mode": "quick", "provider": "claude",
                                 "name": "claude-nhanh", "model": "", "effort": "", "role": "Viết test", "full": False})
            assert r[1] == "ok" and "claude-nhanh" in wa.cfg.agents
            assert any(a["name"] == "claude-nhanh" for a in (await (await client.get("/api/custom")).json())["agents"])
            r = await wa.handle({"op": "custom_save", "kind": "agents", "mode": "quick", "provider": "claude",
                                 "name": "lead"})
            assert r[1] == "error"
            r = await wa.handle({"op": "custom_save", "kind": "agents", "mode": "advanced", "name": "mycli2",
                                 "fields": {"command": "mycli {prompt}", "timeout": "abc"}})
            assert r[1] == "error"  # timeout không phải số
            prev = (await wa.handle({"op": "custom_preview", "mode": "advanced", "name": "x",
                                     "fields": {"command": "mycli -p {prompt}"}}))[2]["preview"]
            assert prev["argv"].startswith("mycli -p") and not prev["no_prompt"]
            r = await wa.handle({"op": "custom_save", "kind": "workflows", "name": "nhanh", "description": "thử",
                                 "review": False, "steps": [{"agent": "lead", "title": "Làm {goal}"},
                                                            {"agent": "claude", "prompt": "test", "after": "1"}]})
            assert r[1] == "ok" and "nhanh" in wa.cfg.workflows
            r = await wa.handle({"op": "custom_save", "kind": "workflows", "name": "hong", "steps": [
                {"agent": "lead", "title": "a", "after": "2"}]})
            assert r[1] == "error"
            assert (await wa.handle({"op": "custom_delete", "kind": "agents", "name": "claude-nhanh"}))[1] == "ok"
            assert "claude-nhanh" not in wa.cfg.agents
            # mục 🧩 Tuỳ chỉnh + popup "Luồng mặc định" (như DefaultFlowScreen)
            assert (await wa.command("/custom"))[2]["open"] == {"view": "custom"}
            assert (await wa.command("/flow-setup"))[2]["open"] == {"modal": "flow"}
            df = await (await client.get("/api/default_flow")).json()
            assert df["form"]["name"] == "tinh-nang" and not df["form"]["exists"]
            assert {"value": "lead", "label": "★ Trưởng nhóm (codex)"} in df["agents"]
            assert "high" in df["choices"]["claude"]["efforts"]
            steps = [dict(st) for st in df["form"]["steps"]]
            steps[1].update(agent="claude", effort="high")
            bad = [dict(st) for st in steps]
            bad[2].update(agent="claude", effort="sieu-cao")
            assert (await wa.handle({"op": "default_flow_save", "name": "tinh-nang", "steps": bad,
                                     "review": True, "make_default": True}))[1] == "error"
            r = await wa.handle({"op": "default_flow_save", "name": "tinh-nang", "steps": steps, "review": True,
                                 "make_default": True})
            assert r[1] == "ok" and r[2]["flow_saved"] == "tinh-nang"
            assert wa.cfg.default_workflow == "tinh-nang"
            assert [st.agent for st in wa.cfg.workflows["tinh-nang"].steps][1] == "claude"
            assert wa.cfg.workflows["tinh-nang"].steps[1].effort == "high"
            cu = await (await client.get("/api/custom")).json()
            assert cu["default_workflow"] == "tinh-nang"
            df = await (await client.get("/api/default_flow?name=nhanh")).json()
            assert df["form"]["name"] == "nhanh" and df["form"]["exists"] and not df["form"]["is_default"]
            assert "error" in await (await client.get("/api/default_flow?name=khong-co")).json()
            # wizard /setup dùng luồng đã chọn ở popup
            r = await wa.handle({"op": "setup_save", "providers": ["claude", "codex"], "style": "flow", "tier": "eco",
                                 "assign": assign, "access": "safe", "apply": "shared", "verify": "",
                                 "flow_name": "nhanh"})
            assert r[1] == "ok" and wa.cfg.default_workflow == "nhanh"
            # dashboard: cùng số liệu với tab 📊 Thống kê
            assert (await wa.command("/dash"))[2]["open"] == {"view": "dash"}
            wa.db.update_goal(wa.db.add_goal("Thử dashboard"), status="done")  # không để bộ lập lịch chạy nó
            rid = wa.db.add_run(None, "claude", "lead", 400, goal_id=1)
            wa.db.finish_run(rid, 0, "ok", 400)
            wa.db.set_run_usage(rid, model="claude-sonnet-4-6", in_tok=10, out_tok=20, cache_read=0, cache_write=0,
                                cost=0.5, src="cli")
            dash = await (await client.get("/api/dashboard")).json()
            assert dash["today"]["tokens"] == 30 and dash["today"]["cost"] == 0.5 and len(dash["per_day"]) == 14
            assert dash["by_model"]["claude-sonnet-4-6"]["real"] == 1
            goals = await (await client.get("/api/goals")).json()
            assert goals[0]["text"] == "Thử dashboard" and goals[0]["tokens"] == 30
            # tuỳ chọn dùng chung với TUI
            assert (await wa.handle({"op": "prefs", "vim": False}))[1] == "ok"
            assert (await wa.handle({"op": "prefs", "accent": "tím"}))[1] == "ok"
            assert load_state()["vim"] is False and load_state()["accent"] == "purple"
            r = await wa.command("/usage")
            assert r[2]["open"]["text"]["body"]
            assert "codex" in (await wa.command("/agents"))[2]["open"]["text"]["body"]
            r = await wa.command("/model codex")
            assert r[2]["open"]["picker"]["agent"] == "codex"
        finally:
            await client.close()

    asyncio.run(main())
