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
