"""Bố cục TUI: thanh bên thay thanh tab khi đủ rộng (bấm để chuyển màn hình / mở agent), Ctrl+B ẩn/hiện và nhớ
trong state.json, terminal hẹp tự trả lại thanh tab; nút dạng chip không còn "[ … ]"; thanh trạng thái có phím tắt."""

from __future__ import annotations

import asyncio
import json

from conftest import git_init


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
    app = tui.TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
    return tui, app, tui.load_state.__globals__["STATE_FILE"]


def test_sidebar_navigation_toggle_and_narrow(env, project, monkeypatch):
    tui, app, state_file = _app(env, project, monkeypatch)

    async def main():
        async def wait(cond, n=300):  # CI chạy song song có thể chậm: chờ tới ~30 giây, xong sớm thì thoát sớm
            for _ in range(n):
                await pilot.pause(0.1)
                if cond():
                    return True
            return False

        def side_lines() -> list[str]:
            return str(app.query_one("#side").render()).splitlines()

        def tab_bar():
            return app.query_one("#tabs").query_one("ContentTabs")

        async with app.run_test(size=(150, 45)) as pilot:
            assert await wait(lambda: app._booted)
            await pilot.pause(0.3)
            side = app.query_one("#side")
            assert app.sidebar_shown() and side.region.width == tui.SIDE_WIDTH and side.region.x == 0
            assert tab_bar().region.height == 0  # thanh tab ẩn, nội dung tab bắt đầu ngay dòng đầu
            lines = side_lines()
            assert project.name in lines[1] and any("Bảng việc" in ln for ln in lines)
            assert any("claude ★" in ln for ln in lines)  # trưởng nhóm trong khối Đội
            bar = app.query_one("#statusbar", tui.StatusBar).build(app).plain
            assert "F1" in bar and "^B" in bar and project.name not in bar  # tên dự án đã ở thanh bên

            # bấm "Git" ở thanh bên: sang tab Git, mục đó được tô
            y = next(i for i, ln in enumerate(side_lines()) if ln.strip().startswith("Git"))
            await pilot.click("#side", offset=(4, y + 1))  # +1: padding trên
            assert await wait(lambda: app.query_one("#tabs").active == "tab-git")
            # bấm tên agent: sang tab Agents, phóng to agent đó để chat
            y = next(i for i, ln in enumerate(side_lines()) if ln.strip().startswith("○ codex"))
            await pilot.click("#side", offset=(4, y + 1))  # +1: padding trên
            assert await wait(lambda: app.query_one("#tabs").active == "tab-team" and app.focus_agent == "codex")
            app.set_focus_agent(None)

            # nút dạng chip: nhãn không còn bọc "[ … ]"
            assert str(app.query_one("#git-push").label) == "⬆ Push"

            # Ctrl+B: ẩn thanh bên, hiện lại thanh tab, nhớ lựa chọn
            await pilot.press("ctrl+b")
            assert await wait(lambda: not app.sidebar_shown() and tab_bar().region.height > 0)
            assert app.query_one("#side").region.width == 0
            assert json.loads(state_file.read_text())["sidebar"] is False
            assert project.name in app.query_one("#statusbar", tui.StatusBar).build(app).plain
            await pilot.press("ctrl+b")
            assert await wait(lambda: app.sidebar_shown() and tab_bar().region.height == 0)
            assert json.loads(state_file.read_text())["sidebar"] is True

            # terminal hẹp: thanh bên tự ẩn (không đổi lựa chọn đã lưu), rộng lại thì hiện
            await pilot.resize_terminal(100, 40)
            assert await wait(lambda: not app.sidebar_shown() and tab_bar().region.height > 0)
            assert app.sidebar_on
            await pilot.resize_terminal(150, 45)
            assert await wait(lambda: app.sidebar_shown() and tab_bar().region.height == 0)
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_sidebar_off_is_remembered(env, project, monkeypatch):
    tui, app, state_file = _app(env, project, monkeypatch)
    st = json.loads(state_file.read_text()) if state_file.exists() else {}
    st["sidebar"] = False
    state_file.write_text(json.dumps(st))

    async def main():
        async with app.run_test(size=(150, 45)) as pilot:
            for _ in range(60):
                await pilot.pause(0.1)
                if app._booted:
                    break
            await pilot.pause(0.2)
            assert not app.sidebar_shown()
            assert app.query_one("#tabs").query_one("ContentTabs").region.height > 0
            labels = [str(t.label) for t in app.query("Tab")]
            assert labels[0] == "Bảng việc" and "Git" in labels  # nhãn tab không emoji
            await pilot.press("ctrl+q")

    asyncio.run(main())
