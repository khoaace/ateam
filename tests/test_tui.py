"""Smoke test giao diện: mở app headless, giao task, chuyển tab, xem diff, thoát."""

from __future__ import annotations

import asyncio
import os

from conftest import git_init, write_project_config


def test_tui_smoke(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    write_project_config(project, 'isolation = "worktree"\nmerge = "review"\n')

    import importlib

    import ateam.config
    importlib.reload(ateam.config)  # đọc XDG_CONFIG_HOME của test
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import AgentPane, TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            app.run_command("/effort claude high")
            app.run_command("/task grok tạo b")
            for _ in range(60):
                await pilot.pause(0.25)
                t = app.db.tasks()
                if t and t[0].status == "review":
                    break
            assert app.db.tasks()[0].status == "review"
            await pilot.press("ctrl+t")
            await pilot.pause(0.3)
            assert len(app.query(AgentPane)) == 4
            await pilot.press("ctrl+t")
            app.show_task(1)
            await pilot.press("ctrl+d")
            await pilot.pause(0.5)
            assert app.view_task == -1
            await pilot.press("ctrl+y")
            await pilot.pause(0.5)
            assert app.db.tasks()[0].status == "done"
            app.run_command("/usage")
            await pilot.press("ctrl+q")

    asyncio.run(main())
    assert (project / "b.txt").exists()
    assert os.environ.get("XDG_CONFIG_HOME") == env["XDG_CONFIG_HOME"]


def test_tui_file_mention_popup(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("")
    (project / "my docs").mkdir()
    (project / "my docs" / "plan.md").write_text("")

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import CommandInput, MentionList, TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.3)
            box = app.query_one("#cmd", CommandInput)
            popup = app.query_one("#mention", MentionList)
            await pilot.press(*"/task codex@high sửa @ap")
            await pilot.pause(0.5)
            assert popup.display
            await pilot.press("tab")
            await pilot.pause(0.2)
            assert box.value == "/task codex@high sửa @src/app.py "
            assert not popup.display
            await pilot.press(*"và @my")
            await pilot.pause(0.3)
            await pilot.press("enter")          # chọn thư mục: đi vào trong, danh sách vẫn mở
            await pilot.pause(0.2)
            assert box.value.endswith('@"my docs/') and popup.display
            await pilot.press("down", "up", "enter")
            await pilot.pause(0.2)
            assert box.value.endswith('và @"my docs/plan.md" ')
            await pilot.press(*"@")
            await pilot.pause(0.2)
            assert popup.display
            await pilot.press("escape")
            assert not popup.display
            await pilot.press("enter")          # danh sách đóng: Enter gửi lệnh như cũ
            await pilot.pause(0.3)
            assert box.value == ""
            t = app.db.tasks()[0]
            assert t.agent == "codex" and '@src/app.py và @"my docs/plan.md"' in t.prompt
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_model_effort_picker(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config, load_state
    from ateam.db import DB
    from ateam.tui import ChoiceScreen, TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.5)
            claude = app.cfg.agents["claude"]
            app.run_command("/model claude")
            await pilot.pause(0.2)
            assert isinstance(app.screen, ChoiceScreen)
            await pilot.press("home", "down", "enter")  # đầu danh sách là "opus", xuống 1 = "sonnet"
            await pilot.pause(0.2)
            assert claude.model == "sonnet"
            assert load_state()["agents"]["claude"]["model"] == "sonnet"
            app.run_command("/effort claude")
            await pilot.pause(0.2)
            await pilot.press("up", "enter")  # từ "mặc định" (cuối) lên 1 = "max"
            await pilot.pause(0.2)
            assert claude.effort == "max"
            argv = claude.argv("x")
            assert argv[argv.index("--model") + 1] == "sonnet" and "max" in argv
            app.run_command("/effort claude")
            await pilot.pause(0.2)
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert not isinstance(app.screen, ChoiceScreen) and claude.effort == "max"
            # tab Đội hiện danh sách model/effort, mục đang dùng nằm trong đó
            await pilot.press("ctrl+t")
            await pilot.pause(0.8)
            head = str(app.pane("claude").head.render())
            assert "effort:" in head and "sonnet" in head and "haiku" in head
            # lần đầu mở app tự hỏi opencode/agy danh sách model
            for _ in range(20):
                if "xai/grok-5-fast" in app.cfg.agents["grok"].models:
                    break
                await pilot.pause(0.25)
            assert "xai/grok-5-fast" in app.cfg.agents["grok"].models
            app.run_command("/models grok")
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_setup_screen(env, project, monkeypatch):
    """Màn hình thiết lập lần đầu: hỏi sẵn model từ CLI, chọn trưởng nhóm/model/effort, tắt agent."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from textual.widgets import Checkbox, Select

    from ateam.config import ensure_global_config, load_config, load_state, needs_setup
    from ateam.db import DB
    from ateam.tui import RESET, AgentPane, SetupScreen, TeamApp

    async def main():
        ensure_global_config()
        assert needs_setup()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"), setup=True)
        async with app.run_test(size=(160, 48)) as pilot:
            for _ in range(80):
                await pilot.pause(0.25)
                if isinstance(app.screen, SetupScreen) and app.screen.ready:
                    break
            scr = app.screen
            assert isinstance(scr, SetupScreen) and scr.ready
            await pilot.pause(0.3)
            # model hỏi được từ CLI giả lập đã có sẵn trong bảng chọn
            grok = scr.query_one("#setup-model-grok", Select)
            assert "xai/grok-5-fast" in [v for _, v in grok._options]
            agy = scr.query_one("#setup-model-antigravity", Select)
            assert "gemini-3-pro" in [v for _, v in agy._options]
            scr.query_one("#setup-lead", Select).value = "codex"
            scr.query_one("#setup-effort-claude", Select).value = "high"
            scr.query_one("#setup-model-codex", Select).value = "gpt-5.5"
            grok.value = "xai/grok-5-fast"
            scr.query_one("#setup-on-antigravity", Checkbox).value = False
            await pilot.press("ctrl+s")
            await pilot.pause(0.5)
            assert not isinstance(app.screen, SetupScreen)
            assert app.cfg.lead == "codex"
            assert app.cfg.agents["claude"].effort == "high"
            assert app.cfg.agents["grok"].model == "xai/grok-5-fast"
            assert not app.cfg.agents["antigravity"].enabled
            assert len(app.query(AgentPane)) == 3
            # mở lại bằng /setup, rồi Esc = giữ nguyên
            app.run_command("/setup")
            for _ in range(40):
                await pilot.pause(0.25)
                if isinstance(app.screen, SetupScreen) and app.screen.ready:
                    break
            assert app.screen.query_one("#setup-lead", Select).value == "codex"
            assert app.screen.query_one("#setup-model-claude", Select).value == RESET
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert app.cfg.lead == "codex"
            await pilot.press("ctrl+q")

    asyncio.run(main())
    st = load_state()
    assert st["onboarded"] and st["lead"] == "codex"
    assert st["agents"]["antigravity"] == {"enabled": False}
    assert st["agents"]["claude"] == {"effort": "high"}
    assert "grok" in st["models_found"] and "antigravity" in st["models_found"]
    cfg = load_config(project)
    assert cfg.lead == "codex" and not cfg.agents["antigravity"].enabled
    assert not needs_setup()
