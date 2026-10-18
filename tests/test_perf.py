"""Hiệu năng: đọc DB / file ít hơn, gom output, không giữ dòng trùng — kiểm hành vi, không đo giờ."""

from __future__ import annotations

import asyncio
import importlib

from ateam import config
from ateam.logtail import read_tail


def test_read_tail_reads_only_end(tmp_path):
    p = tmp_path / "a.log"
    p.write_text("".join(f"dòng {i}\n" for i in range(100_000)))
    assert read_tail(p, 3) == ["dòng 99997", "dòng 99998", "dòng 99999"]
    assert read_tail(tmp_path / "chua-co.log", 3) == []


def test_db_indexes_and_task_index(project):
    from ateam.db import DB
    db = DB(project / ".ateam/team.db")
    names = {r["name"] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"tasks_status", "tasks_goal", "runs_started", "notes_author"} <= names
    tid = db.add_task("codex", "x", "x", status="queued")
    assert db.task_index() == {tid: ("queued", "codex")}
    sig = db.change_sig()
    assert db.change_sig() == sig
    db.update_task(tid, status="done", finished=1.0)
    assert db.change_sig() != sig


def test_which_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(config.shutil, "which", lambda b: calls.append(b) or "/bin/" + b)
    config._WHICH.clear()
    assert config.which("zz") == config.which("zz") == "/bin/zz"
    assert calls == ["zz"]
    config._WHICH.clear()


def test_system_log_rotates(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam import orchestrator
    from ateam.config import load_config
    from ateam.db import DB
    monkeypatch.setattr(orchestrator, "SYSTEM_LOG_MAX", 2000)
    o = orchestrator.Orchestrator(project, load_config(project), DB(project / ".ateam/team.db"))
    for i in range(100):
        o.log(f"dòng số {i} " + "x" * 40)
    assert (o.logs / "system.log").stat().st_size <= 2100
    assert (o.logs / "system.log.1").exists()


def test_reflow_log_hidden_pane_keeps_lines_once():
    from textual.app import App
    from ateam.tui import ReflowLog

    class A(App):
        def compose(self):
            log = ReflowLog(id="log", max_lines=50)
            log.display = False  # như ô agent khi tab Đội chưa mở
            yield log

    async def main():
        app = A()
        async with app.run_test(size=(80, 20)) as pilot:
            log = app.query_one(ReflowLog)
            for i in range(120):
                log.write(f"dòng {i}")
            assert len(log._items) == 50 and not log._deferred_renders  # có giới hạn, không hàng đợi riêng
            log.display = True
            await pilot.pause()
            await pilot.pause()
            assert len(log._items) == 50  # trước đây phát lại qua write() → dòng đôi
            assert len(log.lines) == 50 and "dòng 119" in log.lines[-1].text
    asyncio.run(main())
