"""TUI ↔ web đồng bộ: số file thay đổi trên tab Git, cây thư mục ở danh sách thay đổi, bấm file mở diff, script dự án
ở tab Terminal, ô terminal trống ở Lưới, gợi ý agent cho /focus /chat /grid, nền xám cho theme tối."""

from __future__ import annotations

import asyncio
import importlib
import json

from conftest import git_init

from ateam import gitops


def test_tree_rows_groups_and_compacts_folders():
    rows = gitops.tree_rows(["README.md", "src/app/a.py", "src/app/b.py", "src/lib/c.py", "docs/x/y/z.md"])
    assert rows == [
        (0, "docs/x/y/", "docs/x/y/", True),  # chuỗi thư mục chỉ có một con: gộp
        (1, "docs/x/y/z.md", "z.md", False),
        (0, "src/", "src/", True),
        (1, "src/app/", "app/", True),
        (2, "src/app/a.py", "a.py", False),
        (2, "src/app/b.py", "b.py", False),
        (1, "src/lib/", "lib/", True),
        (2, "src/lib/c.py", "c.py", False),
        (0, "README.md", "README.md", False),  # file sau thư mục cùng cấp
    ]
    assert gitops.tree_rows([]) == []


def test_dark_themes_get_gray_background():
    from textual.theme import BUILTIN_THEMES

    from ateam import theme
    for name in ("textual-dark", "dracula", "nord"):
        t = theme.grayed(BUILTIN_THEMES[name])
        assert (t.background, t.surface, t.panel) == ("#10110e", "#1c1d18", "#24261f"), name
        assert t.name == name and t.primary == BUILTIN_THEMES[name].primary  # giữ tên + màu nhấn
        assert t.variables["footer-background"] == "#161713"
    light = BUILTIN_THEMES["textual-light"]
    assert theme.grayed(light) is light
    # secondary navy của textual-dark (chữ "info") được làm sáng cho dễ đọc trên nền xám
    from textual.color import Color
    assert Color.parse(theme.grayed(BUILTIN_THEMES["textual-dark"]).secondary).brightness > \
        Color.parse(BUILTIN_THEMES["textual-dark"].secondary).brightness


def _app(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import TeamApp
    ensure_global_config()
    return TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))


def test_tui_git_badge_tree_and_click_diff(env, project, monkeypatch):
    git_init(project)
    (project / "src" / "app").mkdir(parents=True)
    (project / "src" / "app" / "a.py").write_text("a\n")
    (project / "src" / "app" / "b.py").write_text("b\n")
    (project / "top.txt").write_text("t\n")
    app = _app(env, project, monkeypatch)
    from ateam.tui import DiffScreen

    async def main():
        async def wait(cond, n=40):
            for _ in range(n):
                await pilot.pause(0.15)
                if cond():
                    return True
            return False

        async with app.run_test(size=(160, 48)) as pilot:
            assert await wait(lambda: app._booted)
            # nền xám đã áp cho theme tối mặc định
            assert app.current_theme.background == "#10110e"
            app.run_command("/git")
            assert await wait(lambda: app.git_status and len(app.git_status.files) == 3)
            tabs = app.query_one("#tabs")
            assert str(tabs.get_tab("tab-git").label) == "Git 3"
            files = app.query_one("#git-files")
            files.focus()
            # bấm (Enter) vào file = mở diff
            assert app.git_selected()[1].endswith(".py") or app.git_selected()[1] == "top.txt"
            await pilot.press("enter")
            assert await wait(lambda: isinstance(app.screen, DiffScreen))
            await pilot.press("q")
            assert await wait(lambda: not isinstance(app.screen, DiffScreen))
            # t: cây thư mục — hàng "src/app/" (gộp), Space stage cả thư mục
            files.focus()
            await pilot.press("t")
            await pilot.pause(0.2)
            ids = [files.get_option_at_index(i).id for i in range(files.option_count)]
            assert "w\0src/app/" in ids and "w\0src/app/a.py" in ids
            from ateam.config import load_state
            assert load_state().get("git_tree") is True
            files.highlighted = ids.index("w\0src/app/")
            await pilot.press("enter")  # thu gọn thư mục
            await pilot.pause(0.2)
            ids = [files.get_option_at_index(i).id for i in range(files.option_count)]
            assert "w\0src/app/" in ids and "w\0src/app/a.py" not in ids
            files.highlighted = ids.index("w\0src/app/")
            await pilot.press("space")
            assert await wait(lambda: {f.path for f in app.git_status.staged} == {"src/app/a.py", "src/app/b.py"})
            assert str(tabs.get_tab("tab-git").label) == "Git 3"
            await pilot.press("t")  # về danh sách phẳng
            await pilot.pause(0.2)
            ids = [files.get_option_at_index(i).id for i in range(files.option_count)]
            assert not any(i and i.endswith("/") for i in ids)
            await pilot.press("ctrl+q")
    asyncio.run(main())


def test_tui_terminal_scripts_and_grid_shell(env, project, monkeypatch):
    git_init(project)
    (project / "package.json").write_text(json.dumps({"scripts": {"dev": "echo dev", "lint": "echo lint"}}))
    app = _app(env, project, monkeypatch)
    from ateam.grid import SHELL
    from ateam.tui_grid import GridAddScreen, GridCell

    async def main():
        async def wait(cond, n=40):
            for _ in range(n):
                await pilot.pause(0.15)
                if cond():
                    return True
            return False

        async with app.run_test(size=(160, 48)) as pilot:
            assert await wait(lambda: app._booted)
            ran = []
            monkeypatch.setattr(app, "run_shell", ran.append)
            app.query_one("#tabs").active = "tab-term"  # vào tab: script dự án hiện ngay, không cần gõ !
            ol = app.query_one("#term-scripts")
            assert await wait(lambda: ol.option_count >= 2)
            cmds = [ol.get_option_at_index(i).id for i in range(ol.option_count)]
            assert any(c.endswith("dev") for c in cmds) and any(c.endswith("lint") for c in cmds)
            ol.focus()
            ol.highlighted = 0
            await pilot.press("enter")
            assert ran == [cmds[0]]

            # Lưới: popup Thêm có mục ⌨ Terminal đầu tiên; nút ⌨ Terminal thêm ô shell
            app.query_one("#tabs").active = "tab-grid"
            await pilot.pause(0.3)
            app.query_one("#grid-add").press()
            assert await wait(lambda: isinstance(app.screen, GridAddScreen))
            scr = app.screen
            assert scr.names[0] == SHELL and scr.agent() != SHELL  # mặc định vẫn là agent đầu tiên
            scr.query_one("#ga-agents").highlighted = 0
            await pilot.pause(0.1)
            assert scr.result() == {"agent": SHELL, "model": "", "effort": "", "resume": False}
            assert scr.query_one("#ga-model").disabled and "$ " in str(scr.query_one("#ga-cmd").render())
            scr.close()
            await pilot.pause(0.2)
            app.query_one("#grid-shell").press()
            assert await wait(lambda: len(app.query(GridCell)) == 1)
            assert app.grid.layout.cols[0].cells[0].agent == SHELL
            await pilot.press("ctrl+q")
    asyncio.run(main())


def test_tui_agent_suggestions_for_focus_chat_grid(env, project, monkeypatch):
    git_init(project)
    app = _app(env, project, monkeypatch)
    from ateam.grid import SHELL
    from ateam.tui import CommandInput, MentionList

    async def main():
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.5)
            box = app.query_one("#cmd", CommandInput)
            popup = app.query_one("#mention", MentionList)

            def ids():
                return [popup.get_option_at_index(i).id for i in range(popup.option_count)]

            box.focus()
            for cmd in ("focus", "chat", "grid"):
                box.value = ""
                await pilot.press(*f"/{cmd} ")
                await pilot.pause(0.2)
                assert popup.display and popup.border_title.startswith(f"/{cmd}"), cmd
                assert "claude" in ids()
                assert (SHELL in ids()) == (cmd == "grid")
            box.value = ""
            await pilot.press(*"/chat cod")
            await pilot.pause(0.2)
            assert ids()[0] == "codex"
            await pilot.press("enter")
            assert box.value == "/chat codex " and not popup.display
            await pilot.press("ctrl+q")
    asyncio.run(main())


def test_web_git_tree_and_change_count(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    git_init(project)
    (project / "src").mkdir()
    (project / "src" / "x.py").write_text("x\n")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.web import WebApp, ui_strings
    from ateam.web_git import status_json
    ensure_global_config()
    wa = WebApp(project, load_config(project), DB(project / ".ateam/team.db"), 8131)

    async def main():
        st = await wa.git.repo.status()
        out = status_json(st)
        assert out["trees"]["w"] == [[0, "src/", "src/", True], [1, "src/x.py", "x.py", False]]
        assert out["trees"]["s"] == [] and out["trees"]["c"] == []
        wa.git.poll_changes(every=0)
        for _ in range(40):
            await asyncio.sleep(0.05)
            if wa.git.changes:
                break
        assert wa.git.changes == 1 and wa.snapshot()["git_changes"] == 1
    asyncio.run(main())
    s = ui_strings()
    assert {"git_tree", "git_list", "git_discard_dir", "sg_agent_focus", "sg_agent_chat", "sg_agent_grid"} <= set(s)


def test_tui_roles_table_edit_cancel_save(env, project, monkeypatch):
    git_init(project)
    app = _app(env, project, monkeypatch)
    from textual.widgets import Select

    from ateam.tui import RESET, RolesTable

    async def main():
        async def wait(cond, n=40):
            for _ in range(n):
                await pilot.pause(0.15)
                if cond():
                    return True
            return False

        async with app.run_test(size=(180, 50)) as pilot:
            assert await wait(lambda: app._booted)
            app.query_one("#tabs").active = "tab-team"
            table = app.query_one("#roles-table", RolesTable)
            assert await wait(lambda: table.base is not None)
            assert not table.query_one("#rt-save").display
            lead = app.cfg.lead
            eff = table.query_one("#rt-effort-lead", Select)
            choices = [v for _l, v in eff._options if v not in (RESET, eff.value)]
            assert choices
            eff.value = choices[0]
            assert await wait(lambda: table.dirty and table.query_one("#rt-save").display)
            table.query_one("#rt-cancel").press()
            assert await wait(lambda: not table.dirty and table.base is not None)
            eff = table.query_one("#rt-effort-lead", Select)
            eff.value = choices[0]
            assert await wait(lambda: table.dirty)
            table.query_one("#rt-save").press()
            assert await wait(lambda: not table.dirty and app.cfg.agents[app.cfg.lead].effort == choices[0])
            assert app.cfg.lead == lead
            await pilot.press("ctrl+q")
    asyncio.run(main())
