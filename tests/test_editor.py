"""Tab 📝 Code: bộ phím vim (VimState), tô màu pygments theo byte, đọc/ghi file an toàn, và editor trong TUI
(mở bằng /edit, sửa + :w ghi đĩa, phím tắt app không cướp phím vim, file đổi trên đĩa tự nạp lại)."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from conftest import git_init

from ateam import editor
from ateam.editor import VimState, apply_ops


def run(keys, text, cursor=(0, 0), vim=None, height=20):
    """Gõ chuỗi phím vim lên text; trả (text, cursor, vim). Phím đặc biệt viết <esc>, <cr>, <c-r>…"""
    vim = vim or VimState()
    lines = text.split("\n")
    special = {"esc": ("escape", None), "cr": ("enter", None), "bs": ("backspace", None),
               "c-r": ("ctrl+r", None), "lt": ("<", "<"), "c-d": ("ctrl+d", None), "c-u": ("ctrl+u", None)}
    toks = []
    i = 0
    while i < len(keys):
        if keys[i] == "<":
            j = keys.index(">", i)
            toks.append(special[keys[i + 1:j]])
            i = j + 1
        else:
            toks.append((keys[i], keys[i]))
            i += 1
    undo: list = []
    for key, ch in toks:
        if vim.mode == "insert" and key != "escape":
            r, c = cursor
            if key == "enter":
                lines = lines[:r] + [lines[r][:c], lines[r][c:]] + lines[r + 1:]
                cursor = (r + 1, 0)
            elif key == "backspace":
                lines[r] = lines[r][:c - 1] + lines[r][c:]
                cursor = (r, c - 1)
            else:
                lines[r] = lines[r][:c] + ch + lines[r][c:]
                cursor = (r, c + 1)
            continue
        ops = vim.feed(key, ch, lines, cursor, height)
        if any(o[0] == "edit" for o in ops):
            undo.append(("\n".join(lines), cursor))
        if any(o[0] == "undo" for o in ops) and undo:
            t, cursor = undo.pop()
            lines = t.split("\n")
            continue
        lines, cursor = apply_ops(lines, cursor, ops)
    return "\n".join(lines), cursor, vim


def test_vim_motions():
    t = "def foo(a, b):\n    return a + b\n\nx = 1"
    assert run("j", t)[1] == (1, 0)
    assert run("3j", t)[1] == (3, 0)
    assert run("G", t)[1] == (3, 0)
    assert run("Ggg", t)[1] == (0, 0)
    assert run("2G", t)[1] == (1, 4)
    assert run("$", t)[1] == (0, 13)
    assert run("$0", t)[1] == (0, 0)
    assert run("j^", t)[1] == (1, 4)
    assert run("w", t)[1] == (0, 4)
    assert run("ww", t)[1] == (0, 7)  # foo -> ( -> a
    assert run("e", t)[1] == (0, 2)
    assert run("wb", t)[1] == (0, 0)
    assert run("4w", t)[1] == (0, 9)
    assert run(":2<cr>", t)[1] == (1, 4)
    assert run("/return<cr>", t)[1] == (1, 4)
    assert run("/a<cr>", t)[1] == (0, 8)
    assert run("/a<cr>n", t)[1] == (1, 11)
    assert run("/a<cr>nN", t)[1] == (0, 8)
    _, cur, v = run("/x<cr>", t)
    assert cur == (3, 0) and v.last_search == "x"


def test_vim_edits():
    t = "one\ntwo\nthree\nfour"
    assert run("dd", t)[0] == "two\nthree\nfour"
    assert run("2dd", t)[0] == "three\nfour"
    assert run("jddp", t)[0] == "one\nthree\ntwo\nfour"
    assert run("yyP", t)[0] == "one\none\ntwo\nthree\nfour"
    assert run("Gdd", t)[0] == "one\ntwo\nthree"
    assert run("dj", t)[0] == "three\nfour"
    assert run("x", t)[0] == "ne\ntwo\nthree\nfour"
    assert run("3x", t)[0] == "\ntwo\nthree\nfour"
    assert run("$x", t)[0] == "on\ntwo\nthree\nfour"
    assert run("D", t)[0] == "\ntwo\nthree\nfour"
    assert run("ihi <esc>", t)[0] == "hi one\ntwo\nthree\nfour"
    assert run("A!<esc>", t)[0] == "one!\ntwo\nthree\nfour"
    assert run("onew<esc>", t)[0] == "one\nnew\ntwo\nthree\nfour"
    assert run("Onew<esc>", t)[0] == "new\none\ntwo\nthree\nfour"
    assert run("J", t)[0] == "one two\nthree\nfour"
    assert run("rX", t)[0] == "Xne\ntwo\nthree\nfour"
    assert run("ccxx<esc>", t)[0] == "xx\ntwo\nthree\nfour"
    assert run(">>", t)[0] == "    one\ntwo\nthree\nfour"
    assert run(">><lt><lt>", t)[0] == t
    s = "foo bar baz"
    assert run("dw", s)[0] == "bar baz"
    assert run("2dw", s)[0] == "baz"
    assert run("cwqux<esc>", s)[0] == "qux bar baz"
    assert run("wcwX<esc>", s)[0] == "foo X baz"
    assert run("de", s)[0] == " bar baz"
    assert run("wd$", s)[0] == "foo "
    assert run("ywP", s)[0] == "foo foo bar baz"
    assert run("wdw", "a b\nc")[0] == "a \nc"  # dw ở cuối dòng không nuốt dòng sau
    # undo / redo
    assert run("ddu", t)[0] == t
    # visual
    assert run("vld", s)[0] == "o bar baz"
    assert run("Vjd", t)[0] == "three\nfour"
    assert run("vey$p", s)[0] == "foo bar bazfoo"
    assert run("veyw$vp", s)[0] == "foo bar bafoo"
    assert run("Vy", t)[2].reg_linewise


def test_vim_modes_and_ex():
    v = VimState()
    lines = ["abc"]
    assert v.feed("colon", ":", lines, (0, 0)) == [("mode", "command")]
    for ch in "wq":
        v.feed(ch, ch, lines, (0, 0))
    assert v.status == ":wq"
    assert v.feed("enter", None, lines, (0, 0))[-1] == ("ex", "wq")
    assert v.mode == "normal"
    v.feed("i", "i", lines, (0, 0))
    assert v.mode == "insert" and v.status == "-- INSERT --"
    assert v.feed("escape", None, lines, (0, 2))[-1] == ("move", (0, 1))
    v.feed("v", "v", lines, (0, 0))
    assert v.status == "-- VISUAL --"
    v.feed("escape", None, lines, (0, 0))
    v.feed("2", "2", lines, (0, 0))
    v.feed("d", "d", lines, (0, 0))
    assert v.status == "2d"
    v.feed("escape", None, lines, (0, 0))
    assert v.status == ""


def test_highlight_bytes():
    lx = editor.lexer_for(Path("a.py"))
    assert lx is not None
    text = 'x = "Tiếng Việt 🎉"  # chú thích\nreturn 1'
    hl = editor.highlight_lines(text, lx)
    line0 = text.split("\n")[0].encode("utf-8")
    spans = [(line0[s:e].decode("utf-8"), n) for s, e, n in hl[0]]
    assert any(n == "string" and "Việt 🎉" in txt for txt, n in spans)
    assert ("# chú thích", "comment") in spans
    assert any(n == "keyword" for _, _, n in hl[1])
    assert editor.highlight_lines(text, lx, end_line=1).keys() == {0}
    assert editor.lexer_for(Path("README.unknownext")) is None
    assert editor.highlight_lines("abc", None) == {}


def test_read_save_source(tmp_path):
    p = tmp_path / "win.txt"
    p.write_bytes(b"a\r\nb\r\n")
    sf = editor.read_source(p)
    assert sf.text == "a\nb\n" and sf.newline == "\r\n" and not sf.read_only
    assert editor.save_source(sf, "a\nB\n") == ""
    assert p.read_bytes() == b"a\r\nB\r\n"
    # agent sửa file sau khi mở -> xung đột, force thì ghi đè
    time.sleep(0.01)
    p.write_bytes(b"agent\n")
    os.utime(p, (time.time() + 5, time.time() + 5))
    assert editor.save_source(sf, "mine\n") == "conflict"
    assert editor.save_source(sf, "mine\n", force=True) == ""
    assert p.read_bytes() == b"mine\r\n"
    b = tmp_path / "x.bin"
    b.write_bytes(b"\x00\x01\x02")
    assert editor.read_source(b).error
    lat = tmp_path / "l.txt"
    lat.write_bytes("caf\xe9".encode("latin-1"))
    assert editor.read_source(lat).read_only
    new = editor.read_source(tmp_path / "sub" / "new.py")
    assert not new.error and new.text == ""
    assert editor.save_source(new, "x = 1\n") == ""
    assert (tmp_path / "sub" / "new.py").read_text() == "x = 1\n"


# ------------------------------------------------------------------------------------------- TUI
def _app(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    import importlib

    import ateam.config
    importlib.reload(ateam.config)  # đường dẫn ~/.config/ateam tính lúc import: trỏ về XDG của test
    from ateam import tui
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    ensure_global_config()
    return tui, tui.TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))


def test_code_tab_edit_and_save(env, project, monkeypatch):
    tui, app = _app(env, project, monkeypatch)
    src = project / "hello.py"
    src.write_text("def hi():\n    return 1\n")

    async def main():
        async def wait(cond, n=80):
            for _ in range(n):
                await pilot.pause(0.05)
                if cond():
                    return True
            return False

        async with app.run_test(size=(150, 45)) as pilot:
            assert await wait(lambda: app._booted)
            app.run_command("/edit @hello.py:2")
            ed = app.query_one("#code-editor", tui.CodeEditor)
            assert await wait(lambda: ed.buffer is not None and ed.buffer.path.name == "hello.py")
            assert app.query_one("#tabs").active == "tab-code"
            assert await wait(lambda: ed.has_focus)  # focus đặt sau khi nạp file: CI chậm có thể chưa kịp
            assert ed.cursor_location[0] == 1
            # Ctrl+D trong editor là phím vim (nửa trang), không mở màn hình diff của app
            before = ed.text
            await pilot.press("ctrl+d")
            assert not isinstance(app.screen, tui.DiffScreen)
            # phím xoá/sửa của TextArea không được chạy ở chế độ normal
            await pilot.press("ctrl+u", "backspace", "ctrl+k", "ctrl+w", "ctrl+x", "ctrl+v")
            assert ed.text == before and not ed.dirty
            # Ctrl+T của app vẫn đổi tab khi đang ở editor
            await pilot.press("ctrl+t")
            assert app.query_one("#tabs").active == "tab-git"  # tab sau 📝 Code
            app.open_code()
            await pilot.pause(0.1)
            ed.focus()
            await pilot.press("g", "g", "A")
            assert ed.vim.mode == "insert"
            await pilot.press(*"  # sửa", "escape")
            assert ed.vim.mode == "normal" and ed.dirty
            await pilot.press("colon", "q", "enter")  # :q khi chưa lưu -> bị chặn
            await pilot.pause(0.1)
            assert ed.buffer is not None and ed.buffer.path.name == "hello.py"
            await pilot.press("colon", "w", "enter")
            assert await wait(lambda: not ed.dirty)
            assert src.read_text() == "def hi():  # sửa\n    return 1\n"
            # agent sửa file -> buffer sạch tự nạp lại
            src.write_text("def hi():\n    return 2\n")
            os.utime(src, (time.time() + 5, time.time() + 5))
            app._code_check_at = 0
            app.refresh_view()
            assert await wait(lambda: "return 2" in ed.text)
            # dd + u
            await pilot.press("j", "d", "d")
            assert "return 2" not in ed.text
            await pilot.press("u")
            assert "return 2" in ed.text
            # tô màu chạy nền (debounce), có highlight cho từ khoá
            assert await wait(lambda: any(n == "keyword" for hs in ed._highlights.values() for _, _, n in hs))
            # /vim off: editor thường, Ctrl+S lưu
            app.run_command("/vim off")
            await pilot.pause(0.1)
            ed.focus()
            await pilot.press("end", *"!")
            assert ed.dirty
            await pilot.press("ctrl+s")
            assert await wait(lambda: not ed.dirty)
            assert src.read_text().endswith("!\n") or "!" in src.read_text()
            app.run_command("/vim on")

    asyncio.run(main())


def test_code_tab_big_file_fast(env, project, monkeypatch):
    tui, app = _app(env, project, monkeypatch)
    big = project / "big.py"
    big.write_text("".join(f"x_{i} = {i}  # dòng {i}\n" for i in range(60000)))

    async def main():
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(60):
                await pilot.pause(0.05)
                if app._booted:
                    break
            t0 = time.time()
            app.run_command("/edit @big.py")
            ed = app.query_one("#code-editor", tui.CodeEditor)
            for _ in range(100):
                await pilot.pause(0.05)
                if ed.buffer is not None:
                    break
            assert ed.buffer is not None and time.time() - t0 < 5
            assert not ed.highlight_on  # file quá lớn: tắt tô màu
            await pilot.press("G")
            assert ed.cursor_location[0] == ed.document.line_count - 1 == 60000
            # gõ liên tục không lexer lại từng phím
            small = project / "s.py"
            small.write_text("a = 1\n")
            app.run_command("/edit @s.py")
            for _ in range(60):
                await pilot.pause(0.05)
                if ed.buffer is not None and ed.buffer.path.name == "s.py":
                    break
            ed.hl_runs = 0
            await pilot.press("A")
            await pilot.press(*("+1" * 10))
            await pilot.press("escape")
            await pilot.pause(0.6)
            assert 1 <= ed.hl_runs <= 4

    asyncio.run(main())


def test_parse_target():
    from ateam.tui import parse_code_target
    assert parse_code_target("@src/a.py:12") == ("src/a.py", 12)
    assert parse_code_target('@"my file.py":3:4') == ("my file.py", 3)
    assert parse_code_target("README.md") == ("README.md", None)
    assert parse_code_target("C:/x.py") == ("C:/x.py", None)


def test_code_open_from_git_and_diff_and_quit_guard(env, project, monkeypatch):
    tui, app = _app(env, project, monkeypatch)
    (project / "base.txt").write_text("base\nline 2\nline 3\nchanged here\n")

    async def main():
        async def wait(cond, n=80):
            for _ in range(n):
                await pilot.pause(0.05)
                if cond():
                    return True
            return False

        async with app.run_test(size=(150, 45)) as pilot:
            assert await wait(lambda: app._booted)
            app.run_command("/git")
            assert await wait(lambda: app.git_status is not None and app.query_one("#git-files").option_count > 1)
            gl = app.query_one("#git-files")
            gl.focus()
            gl.highlighted = next(i for i in range(gl.option_count) if gl.get_option_at_index(i).id)
            await pilot.press("e")
            ed = app.query_one("#code-editor", tui.CodeEditor)
            assert await wait(lambda: ed.buffer is not None and ed.buffer.path.name == "base.txt")
            # màn hình diff: e mở đúng dòng của đoạn đổi
            app.run_command("/git")
            await pilot.pause(0.2)
            gl.focus()
            await app.action_git_diff()
            assert await wait(lambda: isinstance(app.screen, tui.DiffScreen))
            await pilot.pause(0.2)
            await pilot.press("e")
            assert await wait(lambda: app.query_one("#tabs").active == "tab-code"
                              and not isinstance(app.screen, tui.DiffScreen))
            assert ed.cursor_location[0] >= 1
            # còn file chưa lưu: thoát phải hỏi lại
            await pilot.press("o", *"new", "escape")
            assert ed.dirty
            await app.action_quit()
            assert await wait(lambda: isinstance(app.screen, tui.ConfirmScreen))
            await pilot.press("escape")
            assert await wait(lambda: not isinstance(app.screen, tui.ConfirmScreen))
            app.run_command("/code")
            ed.focus()
            await pilot.press("colon", "q", "exclamation_mark", "enter")
            assert await wait(lambda: ed.buffer is None)
            assert app.code_unsaved() == []

    asyncio.run(main())
