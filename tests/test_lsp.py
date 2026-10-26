"""Tab 📝 Code: F12 đi tới định nghĩa / Shift+F12 tìm chỗ dùng qua language server (`lsp.py`, server giả lập
`tests/fakebin/pyright-langserver`) và git blame dòng hiện tại (`gitops.blame_line`)."""

from __future__ import annotations

import asyncio
import subprocess

from conftest import git_init, wait_for
from test_editor import _app

from ateam import gitops, lsp

SRC = "class Foo:\n    def bar(self):\n        return 1\n\n\ndef helper():\n    return Foo().bar()\n"


def _write(project):
    (project / "pkg").mkdir()
    (project / "pkg/mod.py").write_text(SRC)
    (project / "use.py").write_text("from pkg.mod import Foo\n\nx = 'ồ'; y = Foo()\n")


def test_utf16_columns():
    s = "a = '𝄞'; b"
    assert lsp.utf16_col(s, s.index("b")) == s.index("b") + 1  # 𝄞 = 2 đơn vị UTF-16
    assert lsp.py_col(s, lsp.utf16_col(s, s.index("b"))) == s.index("b")
    assert lsp.language_id("ts", lsp.Path("a.tsx")) == "typescriptreact"


def test_hub_definition_references_and_dead_server(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    _write(project)
    hub = lsp.Hub(project)

    async def main():
        text = (project / "use.py").read_text()
        col = text.split("\n")[2].index("Foo")  # sau ký tự 'ồ': cột Python ≠ UTF-16 khi có emoji, ở đây bằng nhau
        res = await hub.query("definition", "use.py", text, 3, col)
        assert res["server"] == "pyright-langserver"
        assert [(x["path"], x["line"], x["col"], x["inside"]) for x in res["items"]] == [("pkg/mod.py", 1, 6, True)]
        res = await hub.query("references", "pkg/mod.py", SRC, 7, SRC.split("\n")[6].index("Foo"))
        assert {(x["path"], x["line"]) for x in res["items"]} == {("pkg/mod.py", 7), ("use.py", 1), ("use.py", 3)}
        # sửa chưa lưu: server đọc nội dung đang sửa (didChange), không đọc đĩa
        edited = "\n\n" + text
        res = await hub.query("definition", "use.py", edited, 5, col)
        assert res["items"][0]["path"] == "pkg/mod.py"
        assert (await hub.query("definition", "README.md", "# x", 1, 0)) == {"unavailable": True}
        await hub.close()
        assert hub.clients == {}

    asyncio.run(main())
    monkeypatch.setenv("ATEAM_FAKE_LSP_DEAD", "1")
    dead = lsp.Hub(project)

    async def broken():
        res = await dead.query("definition", "use.py", "Foo", 1, 0)
        assert res.get("error")
        again = await dead.query("definition", "use.py", "Foo", 1, 0)  # hỏng rồi: không khởi động lại liên tục
        assert again.get("unavailable") or again.get("error")
        await dead.close()

    asyncio.run(broken())


def test_blame_line_and_ago(project):
    git_init(project)
    assert gitops.ago(1000, 1000 + 7200) == "2 giờ trước" and gitops.ago(1000, 1010) == "vừa xong"

    async def main():
        res = await gitops.blame_line(project, "base.txt", 1)
        assert res["author"] == "t" and res["summary"] == "init" and not res["uncommitted"] and len(res["short"]) == 8
        res = await gitops.blame_line(project, "base.txt", 2, "base\ndòng mới\n")  # chưa lưu
        assert res["uncommitted"] and res["summary"] == ""
        (project / "moi.txt").write_text("x\n")
        assert isinstance(await gitops.blame_line(project, "moi.txt", 1), str)

    asyncio.run(main())


def test_web_code_lsp_and_blame(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    from test_web import _web_app
    git_init(project)
    _write(project)
    wa = _web_app(env, project, monkeypatch)
    assert wa.slow_op({"op": "code_lsp"}) and wa.slow_op({"op": "code_blame"})

    async def main():
        text = (project / "use.py").read_text()
        r = await wa.handle({"op": "code_lsp", "kind": "definition", "path": "use.py", "text": text, "line": 1,
                             "ch": text.index("Foo")})
        assert r[2]["lsp"]["items"][0]["path"] == "pkg/mod.py"
        r = await wa.handle({"op": "code_lsp", "path": "../x.py", "text": "", "line": 1, "ch": 0})
        assert r[2]["lsp"]["error"]
        r = await wa.handle({"op": "code_blame", "path": "base.txt", "line": 1})
        assert r[2]["blame"]["summary"] == "init"
        await wa.lsp.close()

    asyncio.run(main())


def test_tui_f12_and_blame(env, project, monkeypatch):
    tui, app = _app(env, project, monkeypatch)  # đã git init
    _write(project)
    subprocess.run(["git", "add", "."], cwd=project, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "thêm mod"], cwd=project,
                   check=True)

    async def main():
        async with app.run_test(size=(150, 45)) as pilot:
            assert await wait_for(pilot, lambda: app._booted)
            app.open_code("use.py", 3, 15)
            assert await wait_for(pilot, lambda: (app.code_cur or "").endswith("use.py"))
            ed = app.code_editor()
            ed.cursor_location = (2, 15)  # con trỏ trên Foo
            await pilot.press("f12")  # một định nghĩa: mở thẳng
            assert await wait_for(pilot, lambda: (app.code_cur or "").endswith("pkg/mod.py"))
            assert await wait_for(pilot, lambda: app.code_editor().cursor_location == (0, 6))
            await pilot.press("shift+f12")  # chỗ dùng: danh sách để chọn
            assert await wait_for(pilot, lambda: isinstance(app.screen, tui.PaletteScreen))
            assert len(app.screen.values) == 3
            await pilot.press("escape")
            notes = []
            monkeypatch.setattr(app, "notify", lambda msg, **kw: notes.append((msg, kw.get("title"))))
            app.code_command("blame_line")
            assert await wait_for(pilot, lambda: notes)
            assert "thêm mod" in notes[0][0] and "1" in notes[0][1]
            await pilot.press("ctrl+q")

    asyncio.run(main())
