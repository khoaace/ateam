"""/goal: kế hoạch chạy luôn, không chờ duyệt (kể cả task bổ sung sau review) dù approve_plan bật."""

from __future__ import annotations

import asyncio
import importlib
import sqlite3

from conftest import write_project_config


def _orch(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import load_config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    return Orchestrator(project, load_config(project), DB(project / ".ateam/team.db"))


def test_goal_auto_run_skips_plan_approval(env, project, monkeypatch):
    write_project_config(project, "approve_plan = true\n")
    o = _orch(env, project, monkeypatch)

    async def main():
        await o.setup()
        auto = o.new_goal("Thêm file A", auto_run=True)
        await o.run_until_idle()
        g = o.db.goal(auto)
        assert g.auto_run and g.status == "done"  # không dừng ở "awaiting", review xong cũng không chờ /go
        assert not o.needs_approval(auto)
        assert all(t.status != "draft" for t in o.db.tasks() if t.goal_id == auto)
        # gõ câu thường: vẫn chờ duyệt như cũ
        plain = o.new_goal("Thêm file B")
        await o.run_until_idle()
        g = o.db.goal(plain)
        assert not g.auto_run and g.status == "awaiting" and o.needs_approval(plain)
        assert {t.status for t in o.db.tasks() if t.goal_id == plain} == {"draft"}

    asyncio.run(main())


def test_goal_auto_run_column_migrates_old_db(tmp_path):
    path = tmp_path / "team.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
                 "status TEXT NOT NULL DEFAULT 'planning', round INTEGER NOT NULL DEFAULT 1, summary TEXT, created REAL)")
    conn.execute("INSERT INTO goals(text) VALUES ('cũ')")
    conn.commit()
    conn.close()
    from ateam.db import DB
    db = DB(path)
    assert db.goal(1).auto_run is None
    assert db.goal(db.add_goal("mới", auto_run=True)).auto_run == 1


def test_web_goal_command_sets_auto_run(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    from conftest import git_init
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    write_project_config(project, "approve_plan = true\n")
    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.web import WebApp, goal_json
    ensure_global_config()
    wa = WebApp(project, load_config(project), DB(project / ".ateam/team.db"), 0)

    async def main():
        await wa.orch.setup()
        await wa.submit("/goal Thêm file A")
        await wa.submit("Thêm file B")
        goals = wa.orch.db.goals()
        assert [bool(g.auto_run) for g in goals] == [True, False]
        assert goal_json(goals[0], False)["auto"] and not goal_json(goals[1], False)["auto"]
        await wa.orch.run_until_idle()

    asyncio.run(main())


def test_tui_goal_command_runs_without_approval(env, project, monkeypatch):
    from conftest import git_init
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    write_project_config(project, "approve_plan = true\n")
    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            app.run_command("/goal Thêm file A")
            for _ in range(80):
                await pilot.pause(0.25)
                g = app.db.goals()
                if g and g[0].status in ("done", "incomplete", "failed", "awaiting"):
                    break
            g = app.db.goals()[0]
            assert g.auto_run and g.status == "done"  # không dừng ở kế hoạch nháp
            app.exit()

    asyncio.run(main())
