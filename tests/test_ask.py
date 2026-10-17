"""Agent hỏi người dùng giữa task (<<<ASK>>>): task chờ trả lời, khung hỏi đáp TUI/web, tiếp tục phiên."""

from __future__ import annotations

import asyncio
import importlib

from conftest import ateam, git_init, tasks, write_project_config

from ateam import prompts as P


def test_parse_ask():
    out = 'làm dở\n<<<ASK>>>{"question": "Màu gì?", "why": "UI", "options": ["xanh", "đỏ"], "recommended": "xanh"}<<<END>>>'
    assert P.parse_ask(out) == {"q": "Màu gì?", "why": "UI", "options": ["xanh", "đỏ"], "rec": "xanh"}
    assert P.parse_ask("<<<ASK>>>Dùng thư viện nào?<<<END>>>")["q"] == "Dùng thư viện nào?"
    assert P.parse_ask("không hỏi gì") is None
    assert P.parse_ask("\n".join(P.ASK_RULES)) is None  # ví dụ trong prompt (CLI in lại) không phải câu hỏi
    assert "<<<ASK>>>" not in P.extract_summary(out + "\nSUMMARY: x")


def test_headless_auto_answers(env, project, tmp_path):
    full = tmp_path / "full.log"
    env = dict(env, ATEAM_FAKE_FULL_LOG=str(full))
    ateam(env, project, "add", "--to", "claude", "ASKME lưu dữ liệu")
    ateam(env, project, "run", "-q")
    t = tasks(project)[0]
    assert t.status == "done" and t.ask["qa"][0]["a"] == "SQLite"  # theo phương án đề xuất
    assert "claude: câu trả lời SQLite" in (project / ".ateam/logs/t1.log").read_text()
    assert "--resume " + t.session in full.read_text()


def _orch(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import load_config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    return Orchestrator(project, load_config(project), DB(project / ".ateam/team.db"))


def test_ask_waits_for_answer_and_keeps_worktree(env, project, monkeypatch):
    git_init(project)
    write_project_config(project, 'isolation = "worktree"\n')
    o = _orch(env, project, monkeypatch)

    async def main():
        await o.setup()
        a = o.db.add_task("claude", "ASKME chọn DB", "ASKME chọn DB", status="queued")
        b = o.db.add_task("codex", "sau đó", "x", status="queued", depends_on=[a])
        await o.run_until_idle()  # dừng chờ người: task hỏi, task phụ thuộc chưa chạy
        t = o.db.task(a)
        assert t.status == "asking" and t.question()["q"] == "Dùng SQLite hay Postgres?"
        assert o.db.task(b).status == "queued" and o.ask_active().id == a
        assert not (project / "wip.txt").exists() and t.branch  # phần làm dở nằm trên nhánh của task
        assert "không có câu hỏi" in o.answer_task(b, "x")
        assert "làm tiếp" in o.answer_task(a, "Postgres")
        await o.run_until_idle()
        t = o.db.task(a)
        assert t.status == "done" and t.ask["qa"][0]["a"] == "Postgres"
        assert (project / "wip.txt").exists() and (project / "c.txt").exists()  # làm tiếp trên nhánh cũ
        assert o.db.task(b).status == "done"
        # hỏi lại rồi bị huỷ
        c = o.db.add_task("claude", "ASKME lần 2", "ASKME lần 2", status="queued")
        await o.run_until_idle()
        assert o.db.task(c).status == "asking"
        o.cancel(c)
        assert o.db.task(c).status == "cancelled" and o.ask_active() is None
        # huỷ sinh `git branch -D` chạy nền: chờ xong, kẻo asyncio.run() huỷ nó giữa lúc tạo tiến trình con -> treo
        await asyncio.gather(*list(o._bg), return_exceptions=True)
    asyncio.run(main())


def test_tui_and_web_show_agent_question(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    o = _orch(env, project, monkeypatch)
    from ateam.config import load_config
    from ateam.db import DB
    from ateam.tui import TeamApp
    from ateam.web import WebApp

    async def prep():
        await o.setup()
        o.db.add_task("claude", "ASKME chọn DB", "ASKME chọn DB", status="queued")
        o.db.add_task("claude", "ASKME khác", "ASKME khác", status="queued")
        await o.run_until_idle()
    asyncio.run(prep())

    async def tui():
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(150, 46)) as pilot:
            await pilot.pause(0.5)
            bar = app.query_one("#grill")
            assert bar.display and bar.task_id == 1
            assert "Dùng SQLite hay Postgres?" in str(app.query_one("#grill-q").render())
            assert app.query_one("#grill-askskip").display and not app.query_one("#grill-done").display
            app.query_one("#cmd").value = "2"  # gõ số = chọn phương án
            await pilot.press("enter")
            await pilot.pause(0.3)
            t = app.db.task(1)
            assert t.status in ("queued", "running", "done") and t.ask["qa"][0]["a"] == "Postgres"
            assert bar.task_id == 2  # câu hỏi tiếp theo
            await pilot.press("ctrl+q")
    asyncio.run(tui())

    wa = WebApp(project, load_config(project), DB(project / ".ateam/team.db"), 0)
    snap = wa.snapshot()
    assert snap["ask"]["task"] == 2 and snap["ask"]["question"]["options"] == ["SQLite", "Postgres"]
    assert next(x for x in snap["tasks"] if x["id"] == 2)["question"]["q"]
    r = asyncio.run(wa.submit("1"))
    assert "làm tiếp" in r[0] and wa.db.task(2).ask["qa"][0]["a"] == "SQLite"
    assert wa.snapshot()["ask"] is None


def test_watcher_notifies_question(tmp_path):
    from ateam.db import DB
    from ateam.notify import Watcher
    db = DB(tmp_path / "t.db")
    tid = db.add_task("claude", "chọn DB", "x", status="running")
    w = Watcher()
    w.diff(db.tasks(), db.goals())
    db.update_task(tid, status="asking", ask={"qa": [{"q": "SQLite hay Postgres?", "a": None}]})
    n = w.diff(db.tasks(), db.goals())
    assert [x.kind for x in n] == ["ask"] and "SQLite hay Postgres?" in n[0].body
