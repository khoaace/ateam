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
        async def wait(cond, n=600):  # CI chạy song song có thể chậm: chờ tới ~30 giây, xong sớm thì thoát sớm
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


def test_workspace_symbols_cache_and_exact(tmp_path):
    (tmp_path / "a.py").write_text("def hello():\n    pass\n\nclass Greeter:\n    pass\n")
    (tmp_path / "b.ts").write_text("export function helloWorld() {}\n")
    (tmp_path / "r.md").write_text("# hello\n")
    (tmp_path / "big.py").write_text("def huge():\n    pass\n" + "#" * palette.WS_SYMBOL_MAX_BYTES)
    (tmp_path / "data.bin").write_bytes(b"\0\1")
    cache: dict = {}
    entries = ["a.py", "b.ts", "r.md", "big.py", "data.bin", "sub/"]
    res = palette.workspace_symbols(tmp_path, entries, "hello", cache)
    assert [(s["name"], s["path"]) for s in res["items"]][:2] == [("hello", "a.py"), ("hello", "r.md")]
    assert ("helloWorld", "b.ts") in [(s["name"], s["path"]) for s in res["items"]]
    assert not res["partial"] and "huge" not in [s["name"] for s in res["items"]]  # file lớn: bỏ qua
    # đúng tên, bỏ heading markdown: F12 đi tới định nghĩa
    exact = palette.workspace_symbols(tmp_path, entries, "hello", cache, exact=True)["items"]
    assert exact == [{"name": "hello", "kind": "function", "line": 1, "path": "a.py"}]
    # cache: file không đổi thì không đọc lại; file đổi thì bóc lại; file mất thì bỏ khỏi cache
    cache["b.ts"] = (cache["b.ts"][0], [{"name": "fromCache", "kind": "function", "line": 9, "depth": 0}])
    assert palette.workspace_symbols(tmp_path, entries, "fromCache", cache, exact=True)["items"][0]["line"] == 9
    import os
    os.utime(tmp_path / "b.ts", (1, 1))
    assert not palette.workspace_symbols(tmp_path, entries, "fromCache", cache, exact=True)["items"]
    palette.workspace_symbols(tmp_path, ["a.py"], "", cache)
    assert set(cache) == {"a.py"}


def test_formatter_for_prefers_project_tools(tmp_path, monkeypatch):
    from ateam import editor
    monkeypatch.setenv("PATH", str(Path(__file__).parent / "fakebin") + ":/usr/bin:/bin")  # ruff giả, không prettier
    argv = editor.formatter_for(tmp_path / "x.py", tmp_path)
    assert Path(argv[0]).name == "ruff" and argv[1:] == ["format", "--stdin-filename", str(tmp_path / "x.py"), "-"]
    assert editor.formatter_for(tmp_path / "x.unknownext", tmp_path) is None
    assert editor.formatter_for(tmp_path / "x.ts", tmp_path) is None  # không có prettier
    bin_ = tmp_path / "node_modules/.bin"
    bin_.mkdir(parents=True)
    (bin_ / "prettier").write_text("#!/bin/sh\ncat\n")
    (bin_ / "prettier").chmod(0o755)
    assert editor.formatter_for(tmp_path / "x.ts", tmp_path)[0] == str(bin_ / "prettier")  # bản trong dự án
    ok, out = asyncio.run(editor.format_text(editor.formatter_for(tmp_path / "x.py", tmp_path), "x = 'a'  \n", tmp_path))
    assert ok and out == 'x = "a"\n'
    ok, err = asyncio.run(editor.format_text(editor.formatter_for(tmp_path / "x.py", tmp_path), "SYNTAX ERROR", tmp_path))
    assert not ok and "Failed to parse" in err


def test_web_code_navigation_format_media(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer
    from test_web import _web_app
    wa = _web_app(env, project, monkeypatch)
    (project / "src").mkdir()
    (project / "src/app.py").write_text("def hello():\n    pass\n")
    (project / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 8)
    (project / "x.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>")
    (project / "doc.pdf").write_bytes(b"%PDF-1.4\n")
    hello = wa.hello()
    assert not hello["prefs"]["fmt_save"] and not hello["prefs"]["autosave"]
    ids = [c["id"] for c in hello["code_commands"]]
    assert {"workspace_symbol", "goto_definition", "format", "toggle_split", "outline"} <= set(ids)

    async def main():
        client = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=wa.port))
        await client.start_server()
        try:
            res = await (await client.get("/api/wsymbols?q=hello&exact=1")).json()
            assert res["items"] == [{"name": "hello", "kind": "function", "line": 1, "path": "src/app.py"}]
            # format bằng ruff (giả lập) — chạy nền như AI viết (không chặn tab)
            assert wa.slow_op({"op": "code_format"})
            r = await wa.handle({"op": "code_format", "path": "src/app.py", "text": "x = 'a'   \n"})
            assert r[2] == {"formatted": 'x = "a"\n', "tool": "ruff"}
            r = await wa.handle({"op": "code_format", "path": "src/app.py", "text": "SYNTAX ERROR"})
            assert r[1] == "warn" and "ruff" in r[0] and r[2]["formatted"] is None
            r = await wa.handle({"op": "code_format", "path": "a.unknownext", "text": "x"})
            assert r[1] == "warn" and r[2]["formatted"] is None
            assert (await wa.handle({"op": "code_format", "path": "a.unknownext", "text": "x", "quiet": True}))[1] == ""
            # tự lưu: không toast
            f = await (await client.get("/api/file?path=src/app.py")).json()
            r = wa.code.save({"path": "src/app.py", "text": "y = 1\n", "mtime": f["mtime"], "quiet": True})
            assert r[:2] == ("", "") and r[2]["save"]["mtime"]
            # tuỳ chọn format khi lưu / tự lưu
            assert (await wa.handle({"op": "prefs", "fmt_save": True}))[1] == "ok"
            assert wa.hello()["prefs"]["fmt_save"] is True
            # ảnh / PDF: /api/file báo media, byte lấy qua /api/raw
            m = await (await client.get("/api/file?path=logo.png")).json()
            assert m["media"] == "image" and m["size"] == 16 and "text" not in m
            assert (await (await client.get("/api/file?path=doc.pdf")).json())["media"] == "pdf"
            raw = await client.get("/api/raw?path=logo.png")
            assert raw.status == 200 and raw.content_type == "image/png" and (await raw.read()).startswith(b"\x89PNG")
            svg = await client.get("/api/raw?path=x.svg")
            assert "sandbox" in svg.headers["Content-Security-Policy"]
            for bad in ("src/app.py", "../ngoai.png", "khong-co.png"):
                assert (await client.get("/api/raw?path=" + bad)).status == 404
        finally:
            await client.close()
    asyncio.run(main())


def test_tui_palette_runs_app_commands_from_any_tab(env, project, monkeypatch):
    """F8 / Ctrl+Shift+P ở mọi tab: lệnh /… của cả app — chạy ngay, hoặc điền ô nhập nếu cần tham số. Kèm /schedule,
    /handoff và /undo (hỏi lại) chạy từ TUI."""
    tui, app = _app(env, project, monkeypatch)

    async def main():
        async def wait(cond, n=600):
            for _ in range(n):
                await pilot.pause(0.05)
                if cond():
                    return True
            return False

        async with app.run_test(size=(150, 45)) as pilot:
            assert await wait(lambda: app._booted)
            assert app.query_one("#tabs").active == "tab-board"
            await pilot.press("f8")
            assert await wait(lambda: isinstance(app.screen, tui.PaletteScreen))
            await pilot.press(*"dash")
            await pilot.pause(0.1)
            assert app.screen.values[0] == ("app", "dash", False)  # ngoài tab Code: lệnh của app đứng trước
            await pilot.press("enter")
            assert await wait(lambda: app.query_one("#tabs").active == "tab-dash")
            await pilot.press("f8")
            assert await wait(lambda: isinstance(app.screen, tui.PaletteScreen))
            await pilot.press(*"schedule", "enter")  # cần tham số: điền vào ô nhập
            assert await wait(lambda: app.query_one("#cmd").value == "/schedule ")
            app.query_one("#cmd").value = ""
            app.run_command("/schedule +30m viết README")
            assert app.db.schedules()[0]["text"] == "viết README"
            app.run_command("/handoff claude codex")
            await pilot.pause(0.1)
            assert not app.orch.chat_last("codex")  # chưa chat với claude: chỉ báo
            app.run_command("/undo m9")  # không có điểm khôi phục: báo, không hỏi lại
            await pilot.pause(0.5)
            assert not isinstance(app.screen, tui.ConfirmScreen)
            await pilot.press("ctrl+q")
    asyncio.run(main())


def test_dir_new_and_index_keeps_empty_dir(tmp_path):
    """Thư mục mới (📁) — trong dự án, không trùng; chỉ mục git vẫn giữ thư mục rỗng sau các lần quét lại."""
    import subprocess
    from ateam import mentions
    root = tmp_path / "p"
    root.mkdir()
    assert palette.dir_new(root, "src/components/") == "" and (root / "src/components").is_dir()
    assert palette.dir_new(root, "src/components")  # đã có
    assert palette.dir_new(root, "../ngoai") and not (tmp_path / "ngoai").exists()
    assert palette.dir_new(root, ".git/hooks2") and palette.dir_new(root, "")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "a.py").write_text("x\n")
    (root / "empty/inner").mkdir(parents=True)
    (root / "node_modules/x").mkdir(parents=True)
    idx = mentions.FileIndex(root)
    asyncio.run(idx.refresh())
    # thư mục rỗng (git không theo dõi) vẫn có trong chỉ mục, kể cả thư mục con; thư mục rác thì không
    assert {"src/", "src/components/", "empty/", "empty/inner/", "a.py"} <= set(idx.entries)
    assert not any(e.startswith("node_modules") for e in idx.entries)
    idx.entries = ["a.py"]
    (root / "lib/new").mkdir(parents=True)
    idx.add_dir("lib/new")  # hiện ngay, chưa cần quét lại
    assert {"lib/", "lib/new/"} <= set(idx.entries)
    (root / "src/components").rmdir()
    (root / "lib/new").rmdir()
    asyncio.run(idx.refresh())
    assert "src/components/" not in idx.entries and "src/" in idx.entries
    assert "lib/new/" not in idx.entries and not idx.made_dirs


def test_web_dir_new(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer
    from test_web import _web_app
    wa = _web_app(env, project, monkeypatch)
    assert any(c["id"] == "new_folder" for c in wa.hello()["code_commands"])

    async def main():
        client = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=wa.port))
        await client.start_server()
        try:
            r = await wa.handle({"op": "dir_new", "path": "lib/util/"})
            assert r[2]["ok"] and (project / "lib/util").is_dir()
            assert (await wa.handle({"op": "dir_new", "path": "lib/util"}))[1] == "warn"
            assert (await wa.handle({"op": "dir_new", "path": "../ngoai"}))[1] == "warn"
            tree = await (await client.get("/api/tree?dir=lib")).json()
            assert {"name": "util", "path": "lib/util", "dir": True} in tree
        finally:
            await client.close()
    asyncio.run(main())
    wa.remote.readonly = True
    assert asyncio.run(wa.handle({"op": "dir_new", "path": "khac"}))[1] == "warn"
    assert not (project / "khac").exists()


def test_tui_new_folder_and_side_width(env, project, monkeypatch):
    """Nút ＋ Thư mục: tạo rồi mở cây tới thư mục mới (kể cả rỗng). Cột file đổi độ rộng bằng :files N, < / >,
    kéo mép — nhớ trong state.json."""
    from ateam.config import load_state
    tui, app = _app(env, project, monkeypatch)

    async def main():
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause(0.3)
            app.query_one("#tabs").active = "tab-code"
            await pilot.pause(0.2)
            await pilot.click("#code-new-dir")
            await pilot.pause(0.2)
            assert isinstance(app.screen, tui.PromptScreen)
            app.screen.query_one("#prompt-in").value = "src/widgets"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert (project / "src/widgets").is_dir()
            ol = app.query_one("#code-files", tui.CodeFileList)
            assert ol.get_option_at_index(ol.highlighted).id == "d:src/widgets/"
            side = app.query_one("#code-side")
            app.code_ex("files 50")
            await pilot.pause(0.1)
            assert side.outer_size.width == 50 and load_state()["code_side_w"] == 50
            ol.focus()
            await pilot.press(">")
            await pilot.pause(0.1)
            assert side.outer_size.width == 54
            app.code_ex("files 999")  # giữ chỗ cho editor
            await pilot.pause(0.1)
            assert side.outer_size.width < app.query_one("#code").size.width - 20
            # kéo mép giữa cột file và editor
            split = app.query_one("#code-split")
            await pilot.mouse_down(split)
            x0 = side.region.x
            await pilot.hover("#code", offset=(x0 - app.query_one("#code").region.x + 40, 5))
            await pilot.mouse_up("#code", offset=(x0 - app.query_one("#code").region.x + 40, 5))
            await pilot.pause(0.1)
            assert side.outer_size.width == 40 and load_state()["code_side_w"] == 40
            app.code_ex("files =")
            await pilot.pause(0.1)
            assert side.outer_size.width == 34 and "code_side_w" not in load_state()
            await pilot.press("ctrl+q")
    asyncio.run(main())
