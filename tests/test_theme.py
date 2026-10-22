"""Theme màu: bảng màu ngữ nghĩa cho mọi theme dựng sẵn, /theme <tên> <màu nhấn> đăng ký theme mới và lưu
vào state.json, ThemeScreen xem trước khi di chuyển / Esc trả theme cũ, thanh trạng thái hiện theme."""

from __future__ import annotations

import asyncio
import json

from textual.theme import BUILTIN_THEMES

from conftest import git_init


def test_palette_and_accents():
    from ateam import theme
    for name, t in BUILTIN_THEMES.items():
        pal = theme.palette(t)
        assert set(pal) == {"running", "ok", "warn", "err", "info"}, name
        assert all(pal.values()), name
    assert theme.normalize_accent("tím") == "purple"
    assert theme.normalize_accent("xanh lá") == "green"
    assert theme.normalize_accent("none") == ""
    assert theme.normalize_accent("???") is None
    t = theme.make_theme("nord", "purple")
    assert t.name == "nord+purple" and t.primary == theme.ACCENTS["purple"] and t.dark
    assert theme.make_theme("nord", "") is None
    names = theme.theme_names()
    assert names.index("textual-dark") < names.index("textual-light")  # tối trước, sáng sau


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
    cfg_mod = tui.load_state.__globals__
    ensure_global_config()
    return tui, tui.TeamApp(project, load_config(project), DB(project / ".ateam/team.db")), cfg_mod["STATE_FILE"]


def test_theme_command_and_screen(env, project, monkeypatch):
    tui, app, state_file = _app(env, project, monkeypatch)

    async def main():
        async def wait(cond, n=300):  # CI chạy song song có thể chậm: chờ tới ~30 giây, xong sớm thì thoát sớm
            for _ in range(n):
                await pilot.pause(0.1)
                if cond():
                    return True
            return False

        async with app.run_test(size=(150, 45)) as pilot:
            assert await wait(lambda: app._booted)
            assert app.theme == "textual-dark"
            bar = app.query_one("#statusbar", tui.StatusBar)
            assert "F1" in bar.build(app).plain  # phím tắt cố định ở bên phải thanh trạng thái

            app.run_command("/theme nord tím")
            await pilot.pause(0.2)
            assert app.theme == "nord+purple"
            assert tui.RUNNING.lower() == "#8b5cf6"  # màu "đang chạy" theo màu nhấn
            st = json.loads(state_file.read_text())
            assert st["theme"] == "nord" and st["accent"] == "purple"

            app.run_command("/theme khongco")
            await pilot.pause(0.1)
            assert app.theme == "nord+purple"

            # màn hình chọn: di chuyển = xem trước, Esc = trả lại theme cũ
            app.action_open_theme()
            assert await wait(lambda: isinstance(app.screen, tui.ThemeScreen) and app.screen.is_mounted)
            await pilot.pause(0.1)
            scr = app.screen
            tl = scr.query_one("#th-list")
            ids = [tl.get_option_at_index(i).id for i in range(tl.option_count)]
            tl.highlighted = ids.index("t:textual-light")
            assert await wait(lambda: app.theme == "textual-light+purple")
            assert not app.current_theme.dark
            await pilot.press("escape")
            assert await wait(lambda: app.theme == "nord+purple")
            assert not isinstance(app.screen, tui.ThemeScreen)

            # chọn rồi lưu
            app.action_open_theme()
            assert await wait(lambda: isinstance(app.screen, tui.ThemeScreen) and app.screen.is_mounted)
            await pilot.pause(0.1)
            scr = app.screen
            al = scr.query_one("#th-accent")
            al.highlighted = 0  # màu của theme
            tl = scr.query_one("#th-list")
            ids = [tl.get_option_at_index(i).id for i in range(tl.option_count)]
            tl.highlighted = ids.index("t:gruvbox")
            assert await wait(lambda: app.theme == "gruvbox")
            scr.query_one("#th-save").press()
            assert await wait(lambda: not isinstance(app.screen, tui.ThemeScreen))
            assert app.theme == "gruvbox"
            st = json.loads(state_file.read_text())
            assert st["theme"] == "gruvbox" and st["accent"] == ""

    asyncio.run(main())


def test_saved_theme_applied_on_start(env, project, monkeypatch, tmp_path):
    tui, app, state_file = _app(env, project, monkeypatch)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    st = json.loads(state_file.read_text()) if state_file.exists() else {}
    st.update(theme="catppuccin-latte", accent="orange")
    state_file.write_text(json.dumps(st))

    async def main():
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            assert app.theme == "catppuccin-latte+orange"
            assert not app.current_theme.dark
            from ateam import diffview
            assert diffview.SYNTAX_THEME == "friendly"  # diff trên nền sáng
            app.apply_theme("textual-dark")  # trả lại cho các test sau (biến module)

    asyncio.run(main())
