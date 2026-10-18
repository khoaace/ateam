"""Mở folder / dự án khác (/open): dự án gần đây (state.json chung), gợi ý thư mục khi gõ đường dẫn, kiểm tra
thư mục đích; TUI mở lại app với -C, web dừng server rồi cli.cmd_web chạy lại ở dự án mới."""

from __future__ import annotations

import asyncio
from pathlib import Path

from test_editor import _app

from ateam import cli


def _dirs(tmp_path) -> tuple[Path, Path]:
    other = tmp_path / "code" / "app-khac"
    for d in ("src", "docs", ".hidden"):
        (other / d).mkdir(parents=True)
    (other / "README.md").write_text("x")
    return other, tmp_path / "code"


def test_recent_candidates_and_check(env, project, monkeypatch, tmp_path):
    _app(env, project, monkeypatch)  # XDG của test
    from ateam import projects
    other, code = _dirs(tmp_path)
    for p in (other, project, other):
        projects.touch_project(p)
    assert projects.recent_projects() == [str(other.resolve()), str(project.resolve())]
    # chữ thường: lọc dự án gần đây; dự án đang mở được đánh dấu (không chọn được)
    assert [c["kind"] for c in projects.candidates("", project)] == ["recent", "current"]
    assert [c["path"] for c in projects.candidates("khac", project)] == [str(other.resolve())]
    # đường dẫn: thư mục con khớp tiền tố, bỏ thư mục ẩn (trừ khi gõ ".")
    base = str(other) + "/"
    assert [Path(c["path"]).name for c in projects.candidates(base, project)] == ["docs", "src"]
    assert [Path(c["path"]).name for c in projects.candidates(base + "s", project)] == ["src"]
    assert [Path(c["path"]).name for c in projects.candidates(base + ".h", project)] == [".hidden"]
    assert projects.candidates(str(other), project)[0]["path"] == str(other.resolve())  # chính nó đứng đầu
    assert projects.candidates("/khong/co/", project) == []
    # đường dẫn tương đối: tính từ thư mục cha của dự án đang mở (dự án nằm cạnh)
    assert projects.expand("proj", project) == project
    assert projects.shorten(Path.home() / "code") == "~/code"
    # kiểm tra thư mục đích
    assert projects.check_target(str(other), project) == (other.resolve(), "")
    assert projects.check_target("../" + project.name, project)[0] is None  # chính dự án đang mở
    assert "Không có" in projects.check_target(str(tmp_path / "nope"), project)[1]
    assert "không phải thư mục" in projects.check_target(str(other / "README.md"), project)[1]
    lock = cli.acquire_session_lock(other)  # phiên ateam khác đang mở dự án đó
    try:
        assert "phiên ateam khác" in projects.check_target(str(other), project)[1]
    finally:
        lock.close()


def test_with_root_replaces_dir():
    assert cli.with_root(["-C", "/a", "tui"], Path("/b")) == ["-C", "/b", "tui"]
    assert cli.with_root(["--dir=/a", "web", "--port", "9"], Path("/b")) == ["-C", "/b", "web", "--port", "9"]
    assert cli.with_root(["-C/a"], Path("/b")) == ["-C", "/b"]
    assert cli.with_root([], Path("/b")) == ["-C", "/b"]


def test_cmd_tui_and_web_relaunch_in_new_root(tmp_path, monkeypatch):
    import ateam.tui
    import ateam.web
    other = tmp_path / "other"
    other.mkdir()

    class FakeApp:
        def __init__(self, *a, **kw):
            self.restart_requested, self.restart_root = True, other

        def run(self):
            pass

    execs = []
    monkeypatch.setattr(ateam.tui, "TeamApp", FakeApp)
    monkeypatch.setattr(cli, "ensure_global_config", lambda: [])
    monkeypatch.setattr(cli, "needs_setup", lambda: False)
    monkeypatch.setattr("ateam.projects.touch_project", lambda root: None)
    monkeypatch.setattr(cli.os, "execv", lambda *a: execs.append(a[1]))
    monkeypatch.setattr(cli.sys, "argv", ["ateam", "-C", str(tmp_path), "tui"])
    assert cli.main(["-C", str(tmp_path), "tui"]) == 0
    assert execs[-1][-3:] == ["-C", str(other), "tui"]
    # web: serve() trả thư mục mới (/open) -> chạy lại cùng cổng, bỏ --open
    monkeypatch.setattr(ateam.web, "serve", lambda *a, **kw: other)
    monkeypatch.setattr(cli.sys, "argv", ["ateam", "-C", str(tmp_path), "web", "--port", "8123", "--open"])
    monkeypatch.setattr("webbrowser.open", lambda url: None)
    assert cli.main(["-C", str(tmp_path), "web", "--port", "8123", "--open"]) == 0
    assert execs[-1][-5:] == ["-C", str(other), "web", "--port", "8123"]


def test_tui_open_project(env, project, monkeypatch, tmp_path):
    tui, app = _app(env, project, monkeypatch)
    from ateam import projects
    other, _code = _dirs(tmp_path)
    projects.touch_project(other)

    async def main():
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.2)
            app.run_command("/open " + str(tmp_path / "nope"))
            assert not app.restart_requested
            # /open: popup dự án gần đây; Tab đi vào thư mục, Enter mở
            app.run_command("/open")
            await pilot.pause(0.1)
            assert isinstance(app.screen, tui.PaletteScreen)
            opts = [str(o.prompt) for o in app.screen.query_one("#pal-list").options]
            assert opts[0] == "Dự án gần đây" and opts[1].startswith("🕘 app-khac  ")
            await pilot.press("tab")
            await pilot.pause(0.1)
            assert app.screen.query_one("#pal-q").value == projects.shorten(other) + "/"
            app.orch.runs[999] = None  # agent đang chạy: hỏi trước
            await pilot.press("s", "enter")  # -> app-khac/src
            await pilot.pause(0.1)
            assert isinstance(app.screen, tui.ConfirmScreen)
            await pilot.press("n")
            assert not app.restart_requested
            app.orch.runs.clear()
            app.run_command("/open " + str(other))
            await pilot.pause(0.3)
        assert app.restart_requested and app.restart_root == other.resolve()
    asyncio.run(main())


def test_web_open_project(env, project, monkeypatch, tmp_path):
    import pytest
    pytest.importorskip("aiohttp")
    from test_web import _web_app
    wa = _web_app(env, project, monkeypatch)
    other, _code = _dirs(tmp_path)
    stopped = []
    wa.stop_server = lambda: stopped.append(1)

    async def main():
        r = await wa.handle({"op": "submit", "text": "/open"})
        assert r[2]["open"] == {"project": ""}
        r = await wa.handle({"op": "projects", "q": str(other) + "/"})
        assert [Path(i["path"]).name for i in r[2]["items"]] == ["docs", "src"]
        assert (await wa.handle({"op": "open_project", "path": str(tmp_path / "nope")}))[1] == "warn"
        wa.orch.runs[999] = None  # agent đang chạy: trình duyệt hỏi lại rồi gửi force
        r = await wa.handle({"op": "open_project", "path": str(other)})
        assert r[2]["busy"] == 1 and wa.next_root is None
        r = await wa.handle({"op": "open_project", "path": str(other), "force": True})
        wa.orch.runs.clear()
        assert r[2]["switching"] and wa.next_root == other.resolve()
        await asyncio.sleep(0.4)
        assert stopped == [1]
    asyncio.run(main())
    # web từ xa: token chỉ cấp cho dự án này -> không đổi được
    wa.next_root, wa.remote.enabled = None, True
    assert asyncio.run(wa.handle({"op": "open_project", "path": str(other)}))[1] == "warn"
    assert asyncio.run(wa.handle({"op": "submit", "text": "/open"}))[1] == "warn"
    assert wa.next_root is None
