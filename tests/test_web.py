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
    port = _free_port()
    assert cli.main(["-C", str(root), "--lang", "en", "web", "--tui", "--port", str(port)]) == 0
    assert seen["served"] and seen["host"] == "127.0.0.1" and seen["port"] == port
    # --lang qua biến môi trường, không ghim vào lệnh (nút Restart chạy lại đúng lệnh này)
    assert shlex.split(seen["command"]) == [sys.executable, "-m", "ateam", "-C", str(root.resolve()), "tui"]
    assert os.environ["ATEAM_LANG"] == "en"
    # cổng bận (dự án khác đang mở web) -> cổng kế tiếp
    import socket
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        assert cli.main(["-C", str(root), "web", "--tui", "--port", str(port)]) == 0
    assert seen["port"] > port


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
    monkeypatch.setattr("ateam.projects.touch_project", lambda root: None)  # không ghi state.json thật
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


def test_web_port_from_session_lock(tmp_path):
    """`ateam web` ghi cổng vào tui.lock: cửa sổ web khác mở dự án này thì dùng lại server; TUI / chưa mở → None."""
    assert cli.web_port(tmp_path) is None
    lock = cli.acquire_session_lock(tmp_path)
    assert cli.web_port(tmp_path) is None  # TUI giữ khoá, không ghi cổng
    lock.write("web 8123\n")
    lock.flush()
    assert cli.web_port(tmp_path) == 8123
    assert cli.acquire_session_lock(tmp_path) is None and cli.web_port(tmp_path) == 8123  # thử khoá không xoá cổng
    lock.close()
    assert cli.web_port(tmp_path) is None  # file còn chữ nhưng không ai giữ khoá


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
            # ảnh chụp bảng việc không mang prompt/kết quả (có thể rất dài); ngăn chi tiết lấy qua /api/task
            draft = next(t for t in st["tasks"] if t["status"] == "draft")
            assert "prompt" in draft  # task nháp giữ prompt: khung duyệt kế hoạch hiện nó
            snap = wa.snapshot()
            assert all("result" not in t for t in snap["tasks"])
            assert all("prompt" not in t for t in snap["tasks"] if t["status"] != "draft")
            full = await (await client.get(f"/api/task/{tid}")).json()
            assert full["id"] == tid and full["prompt"] and full["result"]

            await ws.send_json({"op": "submit", "text": "!echo xin-chao-web"})
            opened = await until(lambda m: m["t"] == "toast" and "open" in m)
            jid = opened["open"]["job"]
            await until(lambda m: m["t"] == "lines" and any(  # dòng output gom theo lô
                x["k"] == "job" and x["id"] == jid and "xin-chao-web" in x["line"] for x in m["items"]))

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
            (project / "base.txt").write_text("base\nsửa hai\n")
            assert (await wa.handle({"op": "git", "action": "stash_push", "message": "hai"}))[1] == "ok"
            # tên stash ở khoá "stash" — "ref" là mã chờ trả lời của trình duyệt (trùng thì toast "đang chạy" treo)
            assert (await wa.handle({"op": "git", "action": "stash_pop", "stash": "stash@{1}", "ref": 7}))[1] == "ok"
            assert "sửa tạm" in (project / "base.txt").read_text()
            left = await (await client.get("/api/git/stashes")).json()
            assert len(left) == 1 and "hai" in left[0]["subject"]
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
            (project / "base.txt").write_text("base\nđang sửa\n")  # bỏ mọi thay đổi: xoá luôn phần agent đang sửa
            assert (await wa.handle({"op": "git", "action": "discard_all"}))[1] == "warn"
            assert "đang sửa" in (project / "base.txt").read_text()
            wa.orch.runs.clear()
            assert (await wa.handle({"op": "git", "action": "discard_all"}))[1] == "ok"
            r = await wa.command("/commit --no-verify")
            assert r[1] == "warn"  # thiếu message
        finally:
            await client.close()

    asyncio.run(main())


def test_web_quota_bars(env, project, monkeypatch):
    """Hạn mức 5h/tuần: tab mở là nhận tin "quota" (không chờ vòng 60 giây); /api/quota?refresh=1 hỏi lại.
    claude/agy giả lập in /usage, codex chưa có phiên → báo lỗi; grok không có."""
    import pytest
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer
    wa = _web_app(env, project, monkeypatch)

    async def main():
        client = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=wa.port))
        await client.start_server()
        try:
            ws = await client.ws_connect("/ws", headers={"Origin": f"http://127.0.0.1:{wa.port}"})
            while True:
                m = await ws.receive_json(timeout=30)
                if m.get("t") == "quota":
                    break
            by = {i["cli"]: i for i in m["items"]}
            assert set(by) == {"claude", "codex", "agy"}, by
            assert [(w["kind"], w["used"]) for w in by["claude"]["windows"]] == [("5h", 41), ("week", 26)]
            assert [(w["kind"], w["used"]) for w in by["agy"]["windows"]] == [("week", 71), ("5h", 20)]
            assert not by["codex"]["windows"] and "codex" in by["codex"]["error"]
            r = await (await client.get("/api/quota?refresh=1")).json()
            assert r["t"] == "quota" and r["at"] >= m["at"] and len(r["items"]) == 3
            await ws.close()
        finally:
            await client.close()

    asyncio.run(main())


def test_web_tells_new_version(env, project, monkeypatch):
    """Mở `ateam web`: có bản mới thì tab đang mở nhận tin "update", tab mở sau thấy trong hello (⬆ + nút Cập nhật)."""
    import pytest
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer

    from ateam import update
    wa = _web_app(env, project, monkeypatch)
    monkeypatch.setattr(update, "editable_source", lambda: None)

    async def main():
        gate = asyncio.Event()  # tạo trong vòng lặp: Python 3.9 gắn Event vào get_event_loop() lúc tạo

        async def check_new():
            await gate.wait()  # tab đầu kết nối trước khi kiểm tra xong
            return "99.0.0"
        monkeypatch.setattr(update, "check_new", check_new)
        client = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=wa.port))
        await client.start_server()
        try:
            hdr = {"Origin": f"http://127.0.0.1:{wa.port}"}
            ws = await client.ws_connect("/ws", headers=hdr)
            m = await ws.receive_json(timeout=30)
            assert m["t"] == "hello" and "latest" not in m
            gate.set()
            while m.get("t") != "update":
                m = await ws.receive_json(timeout=30)
            assert m["latest"] == "99.0.0" and "gõ /update" in m["update_text"] and not m["update_src"]
            ws2 = await client.ws_connect("/ws", headers=hdr)
            h = await ws2.receive_json(timeout=30)
            assert h["t"] == "hello" and h["latest"] == "99.0.0"
            await ws.close()
            await ws2.close()
        finally:
            await client.close()

    asyncio.run(main())


def test_web_slow_op_does_not_block_tab(env, project, monkeypatch):
    """AI viết commit message (chạy lâu) chạy riêng: tab vẫn nhận trả lời cho thao tác khác; trả lời đúng ref khi xong."""
    import pytest
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer
    wa = _web_app(env, project, monkeypatch)

    async def main():
        gate = asyncio.Event()

        async def slow_message():
            await gate.wait()
            return True, "feat: chậm mà chắc"
        monkeypatch.setattr(wa.orch, "commit_message", slow_message)
        client = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=wa.port))
        await client.start_server()
        try:
            ws = await client.ws_connect("/ws", headers={"Origin": f"http://127.0.0.1:{wa.port}"})

            async def reply(ref):
                while True:
                    m = await ws.receive_json(timeout=10)
                    if m.get("t") == "toast" and m.get("ref") == ref:
                        return m
            await ws.send_json({"op": "git", "action": "ai_message", "ref": 1})
            await ws.send_json({"op": "git", "action": "commit_agent", "name": "", "ref": 2})
            assert (await reply(2))["level"] == ""  # không phải chờ AI viết xong
            gate.set()
            assert (await reply(1))["git_msg"] == "feat: chậm mà chắc"
            assert wa.slow_op({"op": "submit", "text": "/push"}) and not wa.slow_op({"op": "submit", "text": "Làm X"})
            # gọi trưởng nhóm vài phút: không được chặn các thao tác khác của tab
            assert wa.slow_op({"op": "submit", "text": "/init"}) and wa.slow_op({"op": "submit", "text": "/compact x"})
            assert wa.slow_op({"op": "submit", "text": "/models opencode làm mới"})
            assert not wa.slow_op({"op": "git", "action": "stage"})
            await ws.close()
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
            # mọi tab đang mở hỏi mtime một lần (agent sửa file ở tab khác); file không còn / ngoài dự án → 0
            st = await (await client.get("/api/file/stat?p=src/app.py&p=khong-co.txt&p=../ngoai.txt")).json()
            assert st["mtimes"] == {"src/app.py": r[2]["save"]["mtime"], "khong-co.txt": 0.0, "../ngoai.txt": 0.0}
            assert (await (await client.get("/api/file/stat?path=src/app.py")).json())["mtime"] == r[2]["save"]["mtime"]
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
            # dấu git ở lề: nội dung ở HEAD; chưa theo dõi / bị .gitignore / ngoài dự án
            import subprocess
            git = lambda *a: subprocess.run(("git",) + a, cwd=project, check=True, capture_output=True)
            if not (project / ".git").exists():
                git("init", "-q")
            (project / ".gitignore").write_text("*.log\n")
            git("add", "src/app.py", ".gitignore")
            git("-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "base")
            (project / "src" / "app.py").write_text("changed\n")
            (project / "moi.txt").write_text("x\n")
            (project / "x.log").write_text("x\n")
            base = await (await client.get("/api/file/base?path=src/app.py")).json()
            assert base == {"repo": True, "tracked": True, "ignored": False, "text": "x\n"}  # CRLF → \n
            assert (await (await client.get("/api/file/base?path=moi.txt")).json())["tracked"] is False
            assert (await (await client.get("/api/file/base?path=x.log")).json())["ignored"] is True
            assert "error" in await (await client.get("/api/file/base?path=../ngoai.txt")).json()
            # diff hai cột của tab Code (Source Control): ?ref=index = bản đã stage, HEAD giữ nguyên
            git("add", "src/app.py")
            (project / "src" / "app.py").write_text("changed again\n")
            idx = await (await client.get("/api/file/base?ref=index&path=src/app.py")).json()
            assert idx["tracked"] and idx["text"] == "changed\n"
            assert (await (await client.get("/api/file/base?path=src/app.py")).json())["text"] == "x\n"
            assert (await (await client.get("/api/file/base?ref=index&path=moi.txt")).json())["tracked"] is False
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

            # ⚡ /roles: chỉ đổi vai trò — kiểu làm việc, lệnh kiểm tra, quyền giữ nguyên
            assert (await wa.command("/roles"))[2]["open"]["modal"] == "roles"
            st = await (await client.get("/api/setup")).json()
            assert set(st["quick_providers"]) >= {"claude", "codex", "agy"}  # mọi CLI đã cài, không chỉ đội
            assert st["init"]["assign"]["lead"][0] == "codex"  # mở lại: đúng đội vừa lưu
            quick = dict(st["init"]["assign"], lead=["codex", "", "high"])
            r = await wa.handle({"op": "roles_save", "assign": quick})
            assert r[1] == "ok" and r[2]["setup_saved"]
            assert wa.cfg.lead == "codex" and wa.cfg.agents["codex"].effort == "high"
            assert not wa.cfg.approve_plan and wa.cfg.verify.command == "make test"  # từ setup_save ở trên
            # bảng vai trò trên trang Agents: mỗi vai trò kèm agent đang giữ (để hiện trạng thái + chat)
            roles = {r["key"]: r["agent"] for r in (await (await client.get("/api/setup")).json())["roles"]}
            assert roles["lead"] == "codex" and all(n in wa.cfg.agents for n in roles.values() if n)
            assert (await wa.handle({"op": "roles_save", "assign": dict(quick, lead=None)}))[1] == "error"

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
                                                            {"agent": "claude", "prompt": "test", "after": "1",
                                                             "model": "opus", "effort": "high"}]})
            assert r[1] == "ok" and "nhanh" in wa.cfg.workflows
            st2 = wa.cfg.workflows["nhanh"].steps[1]
            assert (st2.model, st2.effort) == ("opus", "high")  # form workflow: agent → model → effort
            cu = await (await client.get("/api/custom")).json()
            assert cu["step_agents"][0]["value"] == "lead" and "efforts" in cu["step_choices"]["claude"]
            r = await wa.handle({"op": "custom_save", "kind": "workflows", "name": "hong", "steps": [
                {"agent": "lead", "title": "a", "after": "2"}]})
            assert r[1] == "error"
            assert (await wa.handle({"op": "custom_delete", "kind": "agents", "name": "claude-nhanh"}))[1] == "ok"
            assert "claude-nhanh" not in wa.cfg.agents
            # mục 🧩 Tuỳ chỉnh + popup "Luồng mặc định" (như DefaultFlowScreen)
            assert (await wa.command("/custom"))[2]["open"] == {"view": "custom"}
            assert (await wa.command("/flow-setup"))[2]["open"] == {"modal": "flow"}
            df = await (await client.get("/api/default_flow")).json()  # chưa đặt workflow: ★ trưởng nhóm
            assert df["form"]["lead"] and df["names"][0]["name"] == "*lead"
            assert [q["key"] for q in df["quality"]] == ["fast", "auto", "strict"]
            assert (await wa.handle({"op": "default_flow_save", "name": "*lead", "quality": "rat-nhanh"}))[1] == "error"
            r = await wa.handle({"op": "default_flow_save", "name": "*lead", "quality": "fast"})
            assert r[1] == "ok" and wa.cfg.quality == "fast" and wa.cfg.default_workflow == ""
            sdf = await (await client.get("/api/default_flow?setup=1")).json()  # từ /setup: chỉ workflow
            assert sdf["form"]["name"] == "tinh-nang" and all(n["name"] != "*lead" for n in sdf["names"])
            df = await (await client.get("/api/default_flow?name=tinh-nang")).json()
            assert df["form"]["name"] == "tinh-nang" and not df["form"]["exists"]
            assert df["form"]["steps"][2]["type"] == "review"
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
            wa.cfg.agents["grok"].enabled = False  # agent đang tắt: /usage vẫn có mục của CLI đó
            r = await wa.command("/usage")
            body = r[2]["open"]["text"]["body"]
            for name in ("claude", "codex", "antigravity", "grok"):  # đủ 4 CLI, cả khi chưa chạy lượt nào
                assert f"  {name} " in body and f"📊 {name}" in body, body
            assert "Current session: 41% used" in body and "Weekly Limit Remaining" in body  # hạn mức ngay trong khung
            assert "📊 grok  (grok usage)  · đang tắt" in body and "(đang tắt)" in body
            assert wa.slow_op({"op": "submit", "text": "/usage"})
            wa.cfg.agents["grok"].enabled = True
            assert "codex" in (await wa.command("/agents"))[2]["open"]["text"]["body"]
            r = await wa.command("/model codex")
            assert r[2]["open"]["picker"]["agent"] == "codex"
        finally:
            await client.close()

    asyncio.run(main())


def test_web_suggest_workflow(env, project, monkeypatch):
    """✨ Gợi ý ở form workflow: trưởng nhóm thiết kế bước theo mô tả → điền form (chuẩn hoá), lưu được."""
    import pytest
    pytest.importorskip("aiohttp")
    wa = _web_app(env, project, monkeypatch)

    async def main():
        assert (await wa.handle({"op": "workflow_suggest", "description": "  "}))[1] == "warn"
        r = await wa.handle({"op": "workflow_suggest", "description": "thiết kế, code rồi kiểm tra giao diện"})
        f = r[2]["wf_suggest"]
        assert r[1] == "ok" and f["name"] == "tinh-nang-ui" and f["review"] is False
        assert [st["agent"] for st in f["steps"]] == ["lead", "codex", "lead"]  # 'ghost' không có trong đội
        assert [st["after"] for st in f["steps"]] == ["0", "", ""]  # [1, 9] sai -> sau bước trước
        assert f["steps"][1]["effort"] == "" and "{goal}" in f["steps"][0]["title"]
        r = await wa.handle({"op": "custom_save", "kind": "workflows", "name": f["name"],
                             "description": f["description"], "review": f["review"], "steps": f["steps"]})
        assert r[1] == "ok" and len(wa.cfg.workflows["tinh-nang-ui"].steps) == 3
        again = await wa.handle({"op": "workflow_suggest", "description": "như trên"})
        assert again[2]["wf_suggest"]["name"] == "tinh-nang-ui-2"  # không trùng workflow đã có
        assert "===== Gợi ý workflow — claude" in (project / ".ateam/logs/lead.log").read_text()
    asyncio.run(main())


def test_web_markdown_renderer(tmp_path):
    """Log/kết quả của agent hiện markdown dễ đọc: tiêu đề, danh sách, ```, bảng, khối NOTE, SUMMARY (app.js)."""
    import json
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("không có node")
    from ateam.web import STATIC
    src = (STATIC / "app.js").read_text(encoding="utf-8")
    code = src[src.index("const TS_RE"):src.index("function appendLines")]
    lines = ["#### 3. Dung lượng", "- **Đã giữ:** `node_modules` (214M)", "  ```text", "$ du -sh", "  ```",
             "14. `a` (191M)", "<<<NOTE>>>[Gemini_flash] Task #41 hoàn tất <<<END>>>",
             '<<<DELEGATE to="codex" title="Viết test">>>', "làm *X*", "<<<END>>>", "SUMMARY: xong <b>",
             "[12:00:01] ✓ ok", "2 * 3 * 4 và snake_case_name"]
    js = ("const esc = (s) => String(s).replace(/[&<>\"']/g, (c) => `&#${c.charCodeAt(0)};`);\n"
          "const t = (k) => k;\n" + code +
          f"const st = {{}}; console.log(JSON.stringify({json.dumps(lines)}.map((s) => lineHtml(s, st))));"
          "console.log(JSON.stringify(mdHtml('| a | b |\\n|---|---|\\n| `x` | y |')));")
    (tmp_path / "t.js").write_text(js, encoding="utf-8")
    out = subprocess.run([node, str(tmp_path / "t.js")], capture_output=True, text=True, check=True).stdout.splitlines()
    h = json.loads(out[0])
    assert 'md-h4">3. Dung lượng<' in h[0]
    assert "md-li" in h[1] and "<b>Đã giữ:</b>" in h[1] and '<code class="md-c">node_modules</code>' in h[1]
    assert "md-pre-start" in h[2] and 'md-lang">text<' in h[2]
    assert 'class="l md-pre"' in h[3] and "$ du -sh" in h[3]  # trong ``` vẫn là code, không phải dòng lệnh ateam
    assert "md-pre-end" in h[4] and "md-ol" in h[5] and ">14.<" in h[5]
    assert "md-note md-start md-end" in h[6] and 'md-who">Gemini_flash<' in h[6] and "&#60;&#60;&#60;" not in h[6]
    assert "md-del md-start" in h[7] and "codex" in h[7] and "Viết test" in h[7]
    assert "md-del" in h[8] and "<i>X</i>" in h[8] and "md-end" in h[9]
    assert "md-sum" in h[10] and "md_summary" in h[10] and "&#60;b&#62;" in h[10]  # HTML của agent bị escape
    assert "l-ok" in h[11] and 'class="ts"' in h[11]
    assert "<i>" not in h[12] and "snake_case_name" in h[12]
    table = json.loads(out[1])
    assert "<th>a</th>" in table and '<td><code class="md-c">x</code></td>' in table


def test_web_need_you_hides_failed_tasks_of_done_goals(tmp_path):
    """Cột "Cần bạn": task lỗi trong kế hoạch trưởng nhóm đã chốt hoàn thành không còn chờ bạn (app.js needYou)."""
    import json
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("không có node")
    from ateam.web import STATIC
    src = (STATIC / "app.js").read_text(encoding="utf-8")
    code = src[src.index("const NEED_YOU"):src.index("function loadBoardPrefs")]
    tasks = [{"id": 15, "goal": 5, "status": "failed"}, {"id": 16, "goal": 5, "status": "done"},
             {"id": 20, "goal": 5, "status": "review"}, {"id": 21, "goal": 6, "status": "failed"},
             {"id": 22, "goal": 7, "status": "blocked"}, {"id": 23, "goal": None, "status": "failed"}]
    goals = [{"id": 5, "status": "done"}, {"id": 6, "status": "incomplete"}, {"id": 7, "status": "done"}]
    js = code + f"console.log(JSON.stringify(needYou({json.dumps(tasks)}, {json.dumps(goals)}).map((x) => x.id)));"
    (tmp_path / "t.js").write_text(js, encoding="utf-8")
    out = subprocess.run([node, str(tmp_path / "t.js")], capture_output=True, text=True, check=True).stdout
    # diff chờ duyệt vẫn hiện; lỗi ở kế hoạch chưa xong và task ngoài kế hoạch vẫn hiện
    assert json.loads(out) == [23, 21, 20]

def test_web_image_paths_in_task_text(tmp_path):
    """Xem task / kế hoạch: bóc ảnh nội dung nhắc tới — @ảnh dán, @"có dấu cách", đường dẫn trần (app.js imagePaths)."""
    import json
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("không có node")
    from ateam.web import STATIC
    src = (STATIC / "app.js").read_text(encoding="utf-8")
    code = src[src.index("const IMG_EXT"):src.index("function imagesHtml")]
    texts = ["@.ateam/images/paste-1.png làm nền giống @.ateam/images/paste-2.PNG cho tôi",
             "ảnh mẫu .ateam/images/a.png (ảnh hiện tại: .ateam/images/b.jpg), lại .ateam/images/a.png.",
             '@"my shots/x 1.png" và `public/logo.svg` và ./img/c.webp',
             "https://cdn.example/a.png, functions/api/speech.js, ảnh.png.bak, email@x.png"]
    js = code + f"console.log(JSON.stringify({json.dumps(texts)}.map(imagePaths)));"
    (tmp_path / "t.js").write_text(js, encoding="utf-8")
    out = json.loads(subprocess.run([node, str(tmp_path / "t.js")], capture_output=True, text=True, check=True).stdout)
    assert out[0] == [".ateam/images/paste-1.png", ".ateam/images/paste-2.PNG"]
    assert out[1] == [".ateam/images/a.png", ".ateam/images/b.jpg"]  # trùng chỉ hiện một lần
    assert out[2] == ["my shots/x 1.png", "public/logo.svg", "img/c.webp"]
    assert out[3] == []  # link ngoài, file không phải ảnh, chữ dính @ giữa từ

def test_web_lofi_links(tmp_path):
    """Nhạc lofi (lofi.js): nhận link YouTube các dạng → id, link http(s) khác → stream, còn lại từ chối."""
    import json
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("không có node")
    from ateam.web import STATIC
    js = ("const window = { addEventListener() {} }; const localStorage = { getItem: () => null };\n"
          + (STATIC / "lofi.js").read_text(encoding="utf-8") +
          "\nconst P = window.Lofi.parse; console.log(JSON.stringify([P('https://www.youtube.com/watch?v=7NOSDKb0HlU&t=1'),"
          " P('https://youtu.be/5yx6BWlEVcY'), P('https://www.youtube.com/live/4xDzrJKXOOY?si=x'),"
          " P('https://radio.example/lofi.mp3'), P('lofi'), P(''), window.Lofi.STATIONS.length]))")
    (tmp_path / "t.js").write_text(js, encoding="utf-8")
    out = json.loads(subprocess.run([node, str(tmp_path / "t.js")], capture_output=True, text=True, check=True).stdout)
    assert out[:3] == [{"yt": "7NOSDKb0HlU"}, {"yt": "5yx6BWlEVcY"}, {"yt": "4xDzrJKXOOY"}]
    assert out[3] == {"audio": "https://radio.example/lofi.mp3"} and out[4] is None and out[5] is None
    assert out[6] >= 3


def test_web_todos_outside_repo(env, project, monkeypatch):
    """✅ To-do: lưu theo dự án ở ~/.config/ateam/todos (không trong repo), thêm/sửa/đánh dấu/đổi thứ tự/xoá."""
    import pytest
    pytest.importorskip("aiohttp")
    from pathlib import Path

    from ateam import todos
    wa = _web_app(env, project, monkeypatch)

    async def main():
        assert (await wa.handle({"op": "todo", "action": "add", "text": "  "}))[1] == "warn"
        for s in ("viết test", "sửa `README`", "deploy"):
            assert await wa.handle({"op": "todo", "action": "add", "text": s}) is None
        ids = [x["id"] for x in wa.snapshot()["todos"]]
        await wa.handle({"op": "todo", "action": "toggle", "id": ids[0]})
        await wa.handle({"op": "todo", "action": "edit", "id": ids[2], "text": "deploy lên prod"})
        await wa.handle({"op": "todo", "action": "move", "id": ids[2], "to": 0})
        st = wa.snapshot()["todos"]
        assert [x["text"] for x in st] == ["deploy lên prod", "viết test", "sửa `README`"]
        assert [x["done"] for x in st] == [False, True, False]
        await wa.handle({"op": "todo", "action": "clear"})
        await wa.handle({"op": "todo", "action": "delete", "id": ids[1]})
        assert [x["text"] for x in wa.snapshot()["todos"]] == ["deploy lên prod"]

    asyncio.run(main())
    f = todos.path_for(project)
    assert f.exists() and Path(env["XDG_CONFIG_HOME"]) in f.parents and project not in f.parents
    assert "todo" not in "".join(p.name for p in project.rglob("*") if ".git" not in p.parts)
    other = project.parent / "khac"
    other.mkdir()
    assert todos.load(other) == [] and todos.path_for(other) != f  # mỗi thư mục một danh sách
    assert wa.hello()["todo_file"].endswith(f.name)

    async def cmds():
        r = await wa.command("/todo hỏi team")
        assert r[2]["open"]["view"] == "todo" and todos.load(project)[-1]["text"] == "hỏi team"
        assert (await wa.command("/plan"))[1] == "warn"  # chưa có mục tiêu
        gid = wa.db.add_goal("x")
        assert (await wa.command("/plan"))[2]["open"]["plan"] == gid
        assert (await wa.command(f"/plan m{gid}"))[2]["open"]["plan"] == gid

    asyncio.run(cmds())


def test_web_tags_and_notes(env, project, monkeypatch):
    """Quản lý tag (op tag) và 🗒 Ghi chú (op note): ảnh chụp gửi tag + bản rút gọn ghi chú, lưu xung đột trả bản mới
    cho tab đó tự hỏi, /notes và /tags mở đúng chỗ."""
    import pytest
    pytest.importorskip("aiohttp")
    from ateam import notes, todos
    wa = _web_app(env, project, monkeypatch)

    async def main():
        await wa.handle({"op": "todo", "action": "add", "text": "sửa login #bug !cao @mai"})
        snap = wa.snapshot()
        assert [t["name"] for t in snap["tags"]] == ["bug"] and snap["todos"][0]["priority"] == 3
        bug = snap["tags"][0]["id"]
        assert (await wa.handle({"op": "tag", "action": "add", "name": " "}))[1] == "warn"
        assert await wa.handle({"op": "tag", "action": "add", "name": "UI"}) is None
        r = await wa.handle({"op": "tag", "action": "rename", "id": bug, "name": "ui"})
        assert r[1] == "warn" and "ui" in r[0]
        r = await wa.handle({"op": "note", "action": "add", "title": "Họp", "tags": ["bug"]})
        n = r[2]["note"]
        assert n["tags"] == [bug] and wa.snapshot()["notes"][0]["title"] == "Họp"
        r = await wa.handle({"op": "note", "action": "save", "id": n["id"], "body": "- [ ] a", "base": n["updated"]})
        assert r[2]["note"]["body"] == "- [ ] a"
        r = await wa.handle({"op": "note", "action": "save", "id": n["id"], "body": "cũ", "base": n["updated"]})
        assert r[2]["note_conflict"]["body"] == "- [ ] a"
        assert (await wa.handle({"op": "note", "action": "get", "id": 999}))[1] == "warn"
        assert (await wa.handle({"op": "note", "action": "to_todo", "id": n["id"], "text": "a"}))[1] == "ok"
        assert todos.load(project)[-1]["tags"] == [bug]
        await wa.handle({"op": "tag", "action": "delete", "id": bug})
        assert notes.get(project, n["id"])["tags"] == [] and [t["name"] for t in wa.snapshot()["tags"]] == ["ui"]
        r = await wa.command("/notes Ý tưởng")
        assert r[2]["open"]["view"] == "notes" and notes.get(project, r[2]["open"]["note"])["title"] == "Ý tưởng"
        assert (await wa.command("/tags"))[2]["open"] == {"view": "todo", "modal": "tags"}
        assert wa.hello()["notes_file"].endswith(notes.path_for(project).name)

    asyncio.run(main())


def test_web_continue_does_not_open_drawer(env, project, monkeypatch):
    """/continue t<id> …: báo bằng toast có nút "Xem" (open.task_link) — không tự bật ngăn chi tiết che bảng việc."""
    import pytest
    pytest.importorskip("aiohttp")
    wa = _web_app(env, project, monkeypatch)

    async def main():
        tid = wa.db.add_task("codex", "x", "x")
        wa.db.update_task(tid, status="done")
        r = await wa.command(f"/continue t{tid} làm tiếp")
        assert r[1] == "ok" and "task" not in r[2]["open"]
        assert r[2]["open"]["task_link"] > tid
        assert (await wa.command(f"/continue t{tid}"))[2]["open"] == {"prefill": f"/continue t{tid} "}
        assert (await wa.command(f"/log {tid}"))[2]["open"] == {"task": tid}  # lệnh xem tường minh vẫn mở

    asyncio.run(main())
    assert {"view_task", "side_collapse", "side_expand"} <= set(wa.hello()["T"])


def test_web_grill_answer_skip_and_finish(env, project, monkeypatch):
    """/grill trên web: gõ số ở ô nhập = phương án, nút "tự quyết" (op grill skip) do server soạn câu trả lời,
    /grill xong chốt và lập kế hoạch; ảnh chụp trạng thái mang câu hỏi đang chờ."""
    import pytest
    pytest.importorskip("aiohttp")
    from ateam import prompts as P
    wa = _web_app(env, project, monkeypatch)
    o = wa.orch

    async def idle():
        for _ in range(200):
            await asyncio.sleep(0.05)
            if not o.lead_busy:
                return

    async def main():
        assert await wa.command("/grill Thêm trang đăng nhập") is None
        await idle()
        st = wa.snapshot()
        gid = st["grill"]["goal"]
        assert st["grill"]["question"]["q"] == "Câu hỏi số 1?" and st["ask"] is None
        assert "Đã trả lời" in (await wa.submit("2"))[0]  # gõ số = chọn phương án, không thành mục tiêu mới
        await idle()
        assert o.db.goal(gid).answered()[0]["a"] == "Phương án B" and len(o.db.goals()) == 1
        await wa.handle({"op": "grill", "action": "skip", "goal": gid})
        await idle()
        assert o.db.goal(gid).answered()[1]["a"] == P.skip_answer("Phương án A")
        gid2 = o.start_grill("Thêm trang hồ sơ")
        await idle()
        assert "đang chốt" in (await wa.command("/grill xong"))[0]
        await idle()
        assert o.db.goal(gid2).status in ("awaiting", "running")

    asyncio.run(main())


def test_web_goal_plan_after_run(env, project, monkeypatch):
    """📋 Xem lại kế hoạch sau khi đã duyệt: mọi task của mục tiêu, kèm nguồn, prompt, phụ thuộc."""
    import pytest
    pytest.importorskip("aiohttp")
    wa = _web_app(env, project, monkeypatch)
    db = wa.db
    gid = db.add_goal("làm a và b")
    t1 = db.add_task("codex", "Tạo a", "tạo file a", goal_id=gid, source="plan")
    db.add_task("claude", "Tạo b", "tạo file b", goal_id=gid, source="review", depends_on=[t1])
    db.add_task("grok", "Phụ", "giúp", goal_id=gid, source="delegate:codex")
    db.add_task("codex", "Khác", "x", source="user")

    async def main():
        r = await wa.handle({"op": "goal_plan", "goal": gid})
        p = r[2]["goal_plan"]
        assert p["goal"]["id"] == gid and p["goal"]["text"] == "làm a và b"
        assert [(x["title"], x["source"]) for x in p["tasks"]] == [("Tạo a", "plan"), ("Tạo b", "review"),
                                                                    ("Phụ", "delegate:codex")]
        assert p["tasks"][1]["deps"] == [t1] and p["tasks"][0]["prompt"] == "tạo file a"
        db.update_task(t1, result="## Xong\n- tạo **a**")
        p = (await wa.handle({"op": "goal_plan", "goal": gid}))[2]["goal_plan"]
        assert p["tasks"][0]["result"] == "## Xong\n- tạo **a**"  # popup hiện kết quả đầy đủ của từng task
        assert (await wa.handle({"op": "goal_plan", "goal": 999}))[1] == "warn"

    asyncio.run(main())


def test_web_help_columns(tmp_path):
    """Popup Trợ giúp (helpRows của app.js): tách lệnh / mô tả theo cột của HELP, dòng thụt sâu là phần tiếp của
    lệnh trên — kể cả lệnh dài lấn cột và lệnh không có mô tả trên cùng dòng (vi lẫn en)."""
    import json
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("không có node")
    from ateam.locales.en import EN
    from ateam.tui import HELP  # test chạy tiếng Việt: HELP là bản gốc, EN[HELP] là bản dịch
    from ateam.web import STATIC
    src = (STATIC / "app.js").read_text(encoding="utf-8")
    code = src[src.index("function helpRows"):src.index("function helpModal")]
    (tmp_path / "t.js").write_text(code + f"console.log(JSON.stringify({json.dumps([HELP, EN[HELP]])}.map(helpRows)));",
                                   encoding="utf-8")
    out = json.loads(subprocess.run([node, str(tmp_path / "t.js")], capture_output=True, text=True, check=True).stdout)
    for rows in out:
        cmds = [r for r in rows if "cmd" in r]
        assert cmds and all(r["cmd"] and len(r["cmd"]) <= 40 for r in cmds)  # không dòng mô tả nào mồ côi
    vi = out[0]
    by = {r["cmd"]: r["desc"] for r in vi if "cmd" in r}
    assert by["/set <task> effort|model <giá trị>"] == ["đổi effort/model riêng cho 1 task ('-' = theo agent)"]
    assert by["/retry <task>   /cancel <task>"][0].startswith("chạy lại")
    assert len(by["/continue <m12|t40> <yêu cầu>"]) == 3
    assert by["F2 = Ctrl+G, F5 = Ctrl+R, F6 = Ctrl+O"][-1] == "MacBook: giữ fn khi bấm F2/F5"
    assert {"head": "Giao việc:"} in vi


def test_web_paste_image(env, project, monkeypatch):
    """Dán / kéo-thả ảnh vào ô nhập web: POST /api/image lưu .ateam/images (đúng đuôi), trả @đường/dẫn để chèn."""
    import pytest
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer
    wa = _web_app(env, project, monkeypatch)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 32

    async def main():
        client = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=wa.port))
        await client.start_server()
        try:
            r = await (await client.post("/api/image", data=png)).json()
            assert r["path"].startswith(".ateam/images/paste-") and r["path"].endswith(".png")
            assert r["mention"] == "@" + r["path"] and (project / r["path"]).read_bytes() == png
            r2 = await (await client.post("/api/image", data=jpg)).json()
            assert r2["path"].endswith(".jpg") and r2["path"] != r["path"]
            assert "error" in await (await client.post("/api/image", data=b"hello")).json()
            wa.remote.readonly = True
            assert "error" in await (await client.post("/api/image", data=png)).json()
        finally:
            await client.close()

    asyncio.run(main())


def test_web_code_ai_edit_and_explain(env, project, monkeypatch):
    """⌘I tab Code: agent viết lại đoạn đang chọn (trả code, không sửa file) hoặc giải thích; chạy nền như AI viết commit."""
    import pytest
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer
    wa = _web_app(env, project, monkeypatch)
    (project / "app.py").write_text("import os\n\ndef hi():\n    return 1\n")
    text = (project / "app.py").read_text()
    start, end = text.index("def hi"), len(text) - 1
    assert wa.slow_op({"op": "code_ai"})

    async def main():
        r = await wa.handle({"op": "code_ai", "mode": "edit", "path": "app.py", "text": text, "from": start, "to": end,
                             "instruction": "viết hoa", "agent": "claude"})
        assert r[2] == {"code": "DEF HI():\n    RETURN 1"}
        assert (project / "app.py").read_text() == text  # agent không sửa file
        # codex in lại prompt (có khối <<<CODE>>> mẫu) và bọc ``` — vẫn lấy đúng đoạn trả lời
        r = await wa.handle({"op": "code_ai", "mode": "edit", "path": "app.py", "text": text, "from": start, "to": end,
                             "instruction": "x", "agent": "codex"})
        assert r[2] == {"code": "codex_sua = True"}
        assert (await wa.handle({"op": "code_ai", "mode": "edit", "path": "app.py", "text": text, "from": 0, "to": 3,
                                 "instruction": "  "}))[1] == "warn"
        r = await wa.handle({"op": "code_ai", "mode": "explain", "path": "app.py", "text": text, "from": start, "to": end})
        assert r[2]["answer"].startswith("**Đoạn này** trả về lời chào.") and "`hello(name)`" in r[2]["answer"]

        # chạy nền: trong lúc agent đang sửa (CHAM_SUA: chậm 2 giây) tab vẫn nhận trả lời thao tác khác
        client = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=wa.port))
        await client.start_server()
        try:
            ws = await client.ws_connect("/ws", headers={"Origin": f"http://127.0.0.1:{wa.port}"})

            async def reply(ref):
                while True:
                    m = await ws.receive_json(timeout=15)
                    if m.get("t") == "toast" and m.get("ref") == ref:
                        return m
            await ws.send_json({"op": "code_ai", "mode": "edit", "path": "app.py", "text": text, "from": start,
                                "to": end, "instruction": "CHAM_SUA", "agent": "claude", "ref": 1})
            await ws.send_json({"op": "prefs", "autosave": False, "ref": 2})
            first = await reply(2)
            assert "code" not in first
            assert (await reply(1))["code"] == "DEF HI():\n    RETURN 1"
            await ws.close()
        finally:
            await client.close()
    asyncio.run(main())


def test_web_todo_fab_wired():
    """Nút nổi ✅ góc dưới phải (todo.js TodoPop): có chữ riêng, vẽ lại cùng TodoView, Esc đóng popover."""
    from ateam.web import STATIC, ui_strings
    s = ui_strings()
    assert {"todo_pop_open", "todo_pop_none"} <= set(s)
    js = (STATIC / "todo.js").read_text(encoding="utf-8")
    assert "window.TodoPop" in js and "if (window.TodoPop) TodoPop.render();" in js
    assert "TodoPop.close()" in (STATIC / "app.js").read_text(encoding="utf-8")
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert ".tdfab {" in css
    # icon nét SVG thay emoji; tên việc hiện đủ, xuống hàng, ưu tiên/tag/hạn ở dòng dưới
    assert '">✅<span' not in js and "tdp-meta" in js
    assert ".tdp-body {" in css and "overflow-wrap: anywhere" in css
    # nút nhạc: nốt nhạc thay tai nghe (cả nút nổi lẫn mục nav)
    for f in ("lofi.js", "index.html"):
        html = (STATIC / f).read_text(encoding="utf-8")
        assert "M4 15v-3a8 8" not in html and "M9 17.5V5.5l11-2v12" in html


def test_web_row_actions_buttons_spaced():
    """Thanh nút cuối popup (.row-actions): HTML hay viết nút liền nhau (Thôi|Lưu ở Thêm workflow, Thêm agent, Luồng
    mặc định) nên khe phải đến từ CSS — flex + gap, và `.end` mới đẩy được nút sang phải."""
    import re

    from ateam.web import STATIC
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    rule = re.search(r"^\.row-actions \{([^}]*)\}", css, re.M)
    assert rule and "display: flex" in rule.group(1) and re.search(r"gap: [1-9]", rule.group(1))
    js = (STATIC / "setup.js").read_text(encoding="utf-8")
    assert 'data-wf="cancel"' in js  # popup trong ảnh lỗi vẫn dùng .row-actions
    assert re.search(r"^\.wf-btns \{[^}]*gap: [4-9]px", css, re.M)


def test_web_workflow_from_goal(env, project, monkeypatch, tmp_path):
    """🔀 Lưu mục tiêu thành workflow: chỉ mục tiêu đã xong; trưởng nhóm nhận các task (agent, loại, chờ bước nào) →
    form điền sẵn, tick 'Chỉ dự án này'."""
    import pytest
    pytest.importorskip("aiohttp")
    env["ATEAM_FAKE_FULL_LOG"] = str(tmp_path / "full.log")
    wa = _web_app(env, project, monkeypatch)

    async def main():
        gid = wa.db.add_goal("Thêm trang đăng nhập")
        a = wa.db.add_task("codex", "Viết API", "viết API /login", goal_id=gid, status="done")
        b = wa.db.add_task("claude", "Review", "review API", goal_id=gid, status="done", kind="review")
        wa.db.update_task(b, depends_on=[a])
        wa.db.add_task("grok", "Bỏ", "x", goal_id=gid, status="cancelled")
        assert (await wa.handle({"op": "workflow_from_goal", "goal": gid}))[1] == "warn"  # chưa xong
        wa.db.update_goal(gid, status="done")
        assert wa.slow_op({"op": "workflow_from_goal", "goal": gid})
        r = await wa.handle({"op": "workflow_from_goal", "goal": gid})
        f = r[2]["wf_from_goal"]
        assert r[1] == "ok" and f["name"] == "tu-muc-tieu" and f["project"] is True and len(f["steps"]) == 3
        log = (tmp_path / "full.log").read_text()
        assert "FINISHED GOAL" in log and "1. [codex, code] Viết API — waits for: none" in log
        assert "2. [lead, review] Review — waits for: 1" in log and "Bỏ" not in log  # task huỷ không gửi
    asyncio.run(main())


def test_codemirror_bundle_has_merge_view():
    """Diff hai cột của tab Code (code.js) cần MergeView + nhảy đoạn trong gói CodeMirror (scripts/editor/entry.js)."""
    from pathlib import Path

    import pytest
    pytest.importorskip("aiohttp")
    from ateam.web import STATIC
    bundle = (Path(STATIC) / "vendor" / "codemirror.js").read_text(encoding="utf-8")
    for name in ("MergeView", "goToNextChunk", "goToPreviousChunk", "unifiedMergeView"):
        assert name in bundle
    used = set(__import__("re").findall(r"\bCM\.(\w+)", (Path(STATIC) / "code.js").read_text(encoding="utf-8")))
    entry = (Path(__file__).parent.parent / "scripts" / "editor" / "entry.js").read_text(encoding="utf-8")
    assert all(n in entry for n in used), sorted(n for n in used if n not in entry)
