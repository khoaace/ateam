"""Thông báo (ateam/notify.py): so trạng thái task/mục tiêu, thông báo hệ điều hành, /notify, TUI + web."""

from __future__ import annotations

import asyncio
import importlib
import os
import stat
from types import SimpleNamespace as NS

from ateam import notify


def T(tid, status, **kw):
    return NS(id=tid, status=status, title=kw.get("title", f"task {tid}"), agent=kw.get("agent", "codex"),
              error=kw.get("error"), goal_id=kw.get("goal_id", 1))


def G(gid, status):
    return NS(id=gid, status=status, text=f"mục tiêu {gid}")


def test_watcher_reports_only_new_transitions():
    w = notify.Watcher()
    # lần đầu chỉ ghi nhận: mở app không báo lại việc cũ
    assert w.diff([T(1, "failed"), T(2, "running")], [G(1, "awaiting")]) == []
    out = w.diff([T(1, "failed"), T(2, "failed", error="exit 1"), T(3, "review"), T(4, "conflict"), T(5, "done")],
                 [G(1, "awaiting"), G(2, "awaiting")])
    kinds = [(n.kind, n.task_id or n.goal_id) for n in out]
    assert kinds == [("plan", 2), ("failed", 2), ("review", 3), ("conflict", 4)]
    assert "exit 1" in out[1].body and out[1].level == "warn"
    assert w.diff([T(2, "failed"), T(3, "review")], [G(2, "awaiting")]) == []  # không báo lặp
    # task mới xuất hiện đã lỗi (vd giao tay rồi lỗi ngay giữa hai lượt đọc) vẫn được báo
    assert [n.kind for n in w.diff([T(6, "failed")], [])] == ["failed"]


def test_notify_command_and_desktop(env, monkeypatch, tmp_path):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import ateam.config
    importlib.reload(ateam.config)
    assert notify.mode() == "all"
    msg, test = notify.command("off")
    assert notify.mode() == "off" and not test and "tắt" in msg
    notify.command("app")
    assert notify.mode() == "app"
    notify.command("on")
    assert notify.mode() == "all" and "notify" not in ateam.config.load_state()
    assert notify.command("test")[1]
    try:
        notify.command("xyz")
        raise AssertionError("phải báo lỗi tham số")
    except ValueError:
        pass

    # thông báo macOS: gọi osascript (giả) với tiêu đề/nội dung đã escape
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "osa.log"
    fake = bin_dir / "osascript"
    fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{log}"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(notify.sys, "platform", "darwin")
    assert not asyncio.run(notify.desktop("x", "y"))  # ATEAM_DESKTOP_NOTIFY=0 trong test: tắt
    monkeypatch.setenv("ATEAM_DESKTOP_NOTIFY", "1")
    assert asyncio.run(notify.desktop('Task "lỗi"', "#3 sửa \\ bug"))
    sent = log.read_text()
    assert 'display notification "#3 sửa \\\\ bug" with title "Task \\"lỗi\\""' in sent


def test_tui_and_web_notify_on_failed_task(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import TeamApp
    from ateam.web import WebApp
    ensure_global_config()

    async def tui():
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        seen = []
        monkeypatch.setattr(app, "notify", lambda msg, **kw: seen.append((kw.get("title"), msg)))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.3)
            tid = app.db.add_task("codex", "Sửa lỗi đăng nhập", "x", status="draft")
            await pilot.pause(0.8)
            app.db.update_task(tid, status="failed", error="exit 2")
            for _ in range(40):
                if any(t == "✗ Task lỗi" for t, _m in seen):
                    break
                await pilot.pause(0.1)
            assert any(t == "✗ Task lỗi" and "Sửa lỗi đăng nhập" in m and "exit 2" in m for t, m in seen), seen
            seen.clear()
            app.run_command("/notify test")
            await pilot.pause(0.2)
            assert any(t == "🔔 ateam" for t, _m in seen)
            await pilot.press("ctrl+q")
    asyncio.run(tui())

    wa = WebApp(project, load_config(project), DB(project / ".ateam/team.db"), 0)
    sent = []
    monkeypatch.setattr(wa, "broadcast", sent.append)
    tasks, goals = wa.db.tasks(), wa.db.goals()
    wa.notices.diff(tasks, goals)
    tid = wa.db.add_task("codex", "Viết test", "x", status="draft")
    wa.db.update_task(tid, status="review")
    wa.push_notices(wa.notices.diff(wa.db.tasks(), wa.db.goals()))
    assert sent and sent[0]["t"] == "notice" and sent[0]["kind"] == "review" and sent[0]["task"] == tid
    assert sent[0]["desktop"] is True
    notify.set_mode("off")
    sent.clear()
    wa.db.update_task(tid, status="failed")
    wa.push_notices(wa.notices.diff(wa.db.tasks(), wa.db.goals()))
    assert sent == []
    r = asyncio.run(wa.command("/notify test"))
    assert sent and sent[0]["kind"] == "test" and r[2]["notify"] == "off"
    assert asyncio.run(wa.command("/notify sai"))[1] == "warn"
