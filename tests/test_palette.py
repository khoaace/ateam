"""Command palette của tab 📝 Code: mở nhanh file (file gần đây trước), `>` lệnh, `@` symbol, `:dòng`, `/tìm`,
thao tác file (tạo / đổi tên / xoá vào Thùng rác) và hỏi agent về đoạn đang chọn."""

from __future__ import annotations

import asyncio
from pathlib import Path

from test_editor import _app

from ateam import palette


def test_symbols_python_js_markdown():
    py = "import os\n\nclass Foo:\n    def bar(self):\n        return len('a')\n\ndef baz():\n    pass\n"
    assert [(s["name"], s["kind"], s["line"]) for s in palette.symbols(Path("a.py"), py)] == [
        ("Foo", "class", 3), ("bar", "function", 4), ("baz", "function", 7)]
    js = ("export function hello(a) {}\nclass Box extends Base {\n  render() {\n    if (x) {\n    }\n  }\n}\n"
          "const add = (a, b) => a + b\nexport const App: FC<P> = async () => {}\ninterface Props { x: number }\n")
    assert [s["name"] for s in palette.symbols(Path("a.tsx"), js)] == ["hello", "Box", "render", "add", "App", "Props"]
    md = "# Tiêu đề\ntext\n## Mục con\n```\n# không phải heading\n```\n"
    assert [(s["name"], s["depth"]) for s in palette.symbols(Path("r.md"), md)] == [("Tiêu đề", 0), ("Mục con", 1)]
    syms = palette.symbols(Path("a.py"), py)
    assert palette.symbol_at(syms, 5)["name"] == "bar" and palette.symbol_at(syms, 1) is None


def test_fuzzy_and_recent(tmp_path):
    assert palette.fuzzy(["src/app.py", "README.md", "src/apple/x.py"], "apppy")[0] == "src/app.py"
    assert palette.fuzzy(["Lưu file", "Bật/tắt xuống dòng mềm"], "zzz") == []
    (tmp_path / ".ateam").mkdir()
    for f in ("a.py", "b.py", "a.py"):
        palette.touch_recent(tmp_path, f)
    assert palette.recent_files(tmp_path) == ["a.py", "b.py"]
    palette.forget_recent(tmp_path, "a.py", "c.py")
    assert palette.recent_files(tmp_path) == ["c.py", "b.py"]


def test_file_ops_stay_in_project(tmp_path, monkeypatch):
    monkeypatch.setenv("ATEAM_TRASH_DIR", str(tmp_path / "trash"))
    root = tmp_path / "p"
    (root / ".ateam").mkdir(parents=True)
    assert palette.file_new(root, "src/new.py") == "" and (root / "src/new.py").is_file()
    assert palette.file_new(root, "src/new.py")  # đã có
    assert palette.file_new(root, "../ngoai.py") and not (tmp_path / "ngoai.py").exists()
    assert palette.file_new(root, ".git/config")
    assert palette.file_rename(root, "src/new.py", "lib/moved.py") == "" and (root / "lib/moved.py").is_file()
    assert palette.file_rename(root, "lib/moved.py", "../ra-ngoai.py")
    assert asyncio.run(palette.file_trash(root, "lib/moved.py")) == ""
    assert not (root / "lib/moved.py").exists() and (tmp_path / "trash/moved.py").is_file()
    assert asyncio.run(palette.file_trash(root, "lib"))  # thư mục: không xoá


def test_tui_palette(env, project, monkeypatch):
    monkeypatch.setenv("ATEAM_TRASH_DIR", str(project.parent / "trash"))
    tui, app = _app(env, project, monkeypatch)
    (project / "src").mkdir()
    (project / "src/app.py").write_text("import os\n\nclass Foo:\n    def bar(self):\n        return 1\n\n\n"
                                        "def helper_func():\n    return Foo().bar()\n")
    (project / "README.md").write_text("# Demo\n")

    async def main():
        async def wait(cond, n=80):
            for _ in range(n):
                await pilot.pause(0.05)
                if cond():
                    return True
            return False

        async with app.run_test(size=(150, 45)) as pilot:
            assert await wait(lambda: app._booted)
            # Ctrl+P: gõ rải rác tên file, Enter mở
            await pilot.press("ctrl+p")
            assert await wait(lambda: isinstance(app.screen, tui.PaletteScreen))
            await pilot.press(*"apppy")
            await pilot.pause(0.1)
            await pilot.press("enter")
            assert await wait(lambda: (app.code_cur or "").endswith("src/app.py"))
            assert palette.recent_files(project)[0] == "src/app.py"
            # F9 / @: tới hàm; thanh trên hiện "› tên hàm"
            await pilot.press("f9")
            await pilot.press(*"helper")
            await pilot.pause(0.1)
            await pilot.press("enter")
            assert await wait(lambda: app.code_editor().cursor_location[0] == 7)
            assert "› helper_func" in str(app.query_one("#code-head").render())
            # :dòng và /tìm trong file
            await pilot.press("ctrl+p")
            await pilot.press(*":4", "enter")
            assert await wait(lambda: app.code_editor().cursor_location[0] == 3)
            await pilot.press("ctrl+p")
            await pilot.press(*"/foo()", "enter")
            assert await wait(lambda: app.code_editor().cursor_location == (8, 11))
            # Ctrl+P trống: "Mở gần đây" đứng đầu
            await pilot.press("ctrl+p")
            await pilot.pause(0.1)
            opts = [str(o.prompt) for o in app.screen.query_one("#pal-list").options]
            assert opts[:2] == ["Mở gần đây", "src/app.py"], opts
            await pilot.press("escape")
            # F8 / >: lệnh, gõ từ khoá tiếng Anh như VS Code
            await pilot.press("f8")
            await pilot.press(*"wrap", "enter")
            assert await wait(lambda: app.code_editor().soft_wrap)
            app.code_command("toggle_wrap")
            assert not app.code_editor().soft_wrap
            # hỏi agent về đoạn đang chọn: chọn agent rồi gõ câu hỏi -> lượt chat có @file (dòng)
            ed = app.code_editor()
            from textual.widgets.text_area import Selection
            ed.selection = Selection((2, 0), (4, 0))
            app.code_command("ask_agent")
            assert await wait(lambda: isinstance(app.screen, tui.ChoiceScreen))
            app.screen.dismiss("codex")
            assert await wait(lambda: isinstance(app.screen, tui.PromptScreen))
            await pilot.press(*"giai thich", "enter")
            assert await wait(lambda: any(t.source == "chat" for t in app.db.tasks()))
            t = next(t for t in app.db.tasks() if t.source == "chat")
            assert t.agent == "codex" and t.prompt == "@src/app.py (dòng 3–5): giai thich", t.prompt
            # đổi tên rồi xoá (vào Thùng rác)
            app.code_command("rename_file")
            assert await wait(lambda: isinstance(app.screen, tui.PromptScreen))
            app.screen.query_one("#prompt-in").value = "src/main.py"
            await pilot.press("enter")
            assert await wait(lambda: (app.code_cur or "").endswith("src/main.py"))
            assert (project / "src/main.py").exists() and not (project / "src/app.py").exists()
            assert palette.recent_files(project)[0] == "src/main.py"
            app.code_command("delete_file")
            assert await wait(lambda: isinstance(app.screen, tui.ConfirmScreen))
            await pilot.press("y")
            assert await wait(lambda: not (project / "src/main.py").exists())
            assert (project.parent / "trash/main.py").exists() and app.code_cur is None
            # file mới
            app.code_command("new_file")
            assert await wait(lambda: isinstance(app.screen, tui.PromptScreen))
            app.screen.query_one("#prompt-in").value = "docs/ghi-chu.md"
            await pilot.press("enter")
            assert await wait(lambda: (app.code_cur or "").endswith("docs/ghi-chu.md"))
            await pilot.press("ctrl+q")
    asyncio.run(main())


def test_web_palette_api(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer
    from test_web import _web_app
    monkeypatch.setenv("ATEAM_TRASH_DIR", str(project.parent / "trash"))
    wa = _web_app(env, project, monkeypatch)
    (project / "src").mkdir()
    (project / "src/app.py").write_text("class Foo:\n    def bar(self):\n        pass\n")
    assert any(c["id"] == "ask_agent" and c["kw"] for c in wa.hello()["code_commands"])
    assert not any(c["id"] == "toggle_numbers" for c in wa.hello()["code_commands"])  # CodeMirror luôn có số dòng

    async def main():
        client = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=wa.port))
        await client.start_server()
        try:
            syms = await (await client.get("/api/symbols?path=src/app.py")).json()
            assert [(s["name"], s["line"]) for s in syms] == [("Foo", 1), ("bar", 2)]
            assert await (await client.get("/api/symbols?path=../x.py")).json() == []
            await client.get("/api/file?path=src/app.py")  # mở -> vào danh sách gần đây (dùng chung với TUI)
            await client.get("/api/file?path=README.md&quiet=1")  # nạp lại -> không tính
            assert await (await client.get("/api/recent")).json() == ["src/app.py"]
            r = await wa.handle({"op": "file_new", "path": "src/new.py"})
            assert r[2]["ok"] and (project / "src/new.py").exists()
            assert (await wa.handle({"op": "file_new", "path": "../ngoai.py"}))[1] == "warn"
            r = await wa.handle({"op": "file_rename", "path": "src/app.py", "to": "src/main.py"})
            assert r[2]["ok"] and (project / "src/main.py").exists()
            assert await (await client.get("/api/recent")).json() == ["src/main.py"]
            # diff của đúng một file (palette "Xem thay đổi git"): chưa có thay đổi so với git -> báo lỗi
            d = await (await client.get("/api/git/diff?kind=file&path=src/main.py")).json()
            assert "error" in d or d["files"][d.get("start", 0)]["path"] == "src/main.py"
            assert (await wa.handle({"op": "file_delete", "path": "src/main.py"}))[2]["ok"]
            assert not (project / "src/main.py").exists() and (project.parent / "trash/main.py").exists()
        finally:
            await client.close()
    asyncio.run(main())
    # --readonly: thao tác file bị chặn
    wa.remote.readonly = True
    assert asyncio.run(wa.handle({"op": "file_delete", "path": "src/new.py"}))[1] == "warn"
    assert (project / "src/new.py").exists()


def test_tui_new_file_button_and_ex(env, project, monkeypatch):
    """Nút ＋ File mới ở cột file (tab Code) và `:new đường/dẫn` — không cần biết palette."""
    tui, app = _app(env, project, monkeypatch)

    async def main():
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause(0.3)
            app.query_one("#tabs").active = "tab-code"
            await pilot.pause(0.2)
            await pilot.click("#code-new")
            await pilot.pause(0.2)
            assert isinstance(app.screen, tui.PromptScreen)
            app.screen.query_one("#prompt-in").value = "src/moi.py"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert (project / "src/moi.py").is_file() and (app.code_cur or "").endswith("src/moi.py")
            app.code_ex("new notes/ghi-chu.md")
            await pilot.pause(0.3)
            assert (project / "notes/ghi-chu.md").is_file() and (app.code_cur or "").endswith("notes/ghi-chu.md")
            await pilot.press("ctrl+q")
    asyncio.run(main())
