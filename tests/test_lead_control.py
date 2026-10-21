"""Điều khiển lượt trưởng nhóm: huỷ lập kế hoạch đang chạy, lead_timeout (CLI treo → agent dự phòng), máy chủ quá
tải (nghỉ ngắn + agent dự phòng); đổi agent cho task lỗi / bị huỷ rồi chạy lại."""

from __future__ import annotations

import asyncio
import importlib
import json
import time
from pathlib import Path

from conftest import ateam, git_init, tasks

from ateam import limits

AGY_503 = ("error: Our servers are experiencing high traffic right now, please try again in a minute. "
           "(UNAVAILABLE (code 503): No capacity available for model gemini-4-argon)")


def _orch(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    ensure_global_config()
    return Orchestrator(project, load_config(project), DB(project / ".ateam/team.db"))


async def _idle(o, secs: float = 15):
    for _ in range(int(secs / 0.05)):
        await asyncio.sleep(0.05)
        if not o.lead_busy:
            return


async def _until(cond, secs: float = 10):
    for _ in range(int(secs / 0.05)):
        if cond():
            return True
        await asyncio.sleep(0.05)
    return False


def test_overload_is_not_rate_limit():
    assert limits.looks_overloaded(AGY_503, 3) and not limits.looks_rate_limited(AGY_503, 3)
    assert limits.looks_overloaded('{"type":"error","error":{"type":"overloaded_error"}}', 1)
    # câu trả lời thành công dài có chữ "503": không phải lỗi
    assert not limits.looks_overloaded("Sửa lỗi 503 của API\nbước 1\nbước 2\nbước 3\nSUMMARY: xong", 0)


def test_overloaded_agent_falls_back_with_short_cooldown(env, project, tmp_path):
    (tmp_path / "limits" / "agy.overload").touch()
    ateam(env, project, "add", "--to", "antigravity", "việc 1")
    out = ateam(env, project, "run", "-q").stdout
    assert "antigravity đang quá tải" in out and "hết hạn mức" not in out
    t = tasks(project)[0]
    assert t.status == "done" and t.agent != "antigravity"  # agent dự phòng làm thay
    state = json.loads((Path(env["XDG_CONFIG_HOME"]) / "ateam" / "state.json").read_text())
    until = state["cooldown"]["antigravity"]
    assert time.time() < until <= time.time() + (limits.OVERLOAD_MINUTES + 1) * 60  # nghỉ vài phút, không 30 phút


def test_cancel_planning_stops_lead_without_fallback(env, project, monkeypatch):
    o = _orch(env, project, monkeypatch)

    async def main():
        await o.setup()
        gid = o.new_goal("TREO_LAP thêm trang")
        assert await _until(lambda: gid in o.lead_runs)
        t0 = time.time()
        assert "Đã huỷ" in o.cancel_planning(gid)
        await _idle(o)
        assert time.time() - t0 < 5  # dừng ngay, không chờ CLI chạy hết
        g = o.db.goal(gid)
        assert g.status == "cancelled" and not o.db.tasks(goal_id=gid) and not o.lead_busy
        lead_log = (project / ".ateam/logs/lead.log").read_text()
        assert "— codex —" not in lead_log  # huỷ thì không thử agent dự phòng
        assert "không đang lập kế hoạch" in o.cancel_planning(gid)
        assert "không đang lập kế hoạch" in o.cancel_command("m" + str(gid))
        assert "Dùng: /cancel" in o.cancel_command("abc")
    asyncio.run(main())


def test_lead_timeout_falls_back(env, project, monkeypatch):
    o = _orch(env, project, monkeypatch)
    o.cfg.lead_timeout = 1

    async def main():
        await o.setup()
        gid = o.new_goal("TREO_LAP thêm trang")
        await _idle(o)
        g = o.db.goal(gid)
        assert g.status in ("awaiting", "running"), (g.status, g.summary)
        assert [t.title for t in o.db.tasks(goal_id=gid)] == ["Kế hoạch do codex lập"]  # codex lập thay
        assert "claude quá 1s chưa xong" in (project / ".ateam/logs/system.log").read_text()
    asyncio.run(main())


def test_reassign_failed_task_and_rerun(env, project, monkeypatch):
    from ateam.db import CANCELLED, FAILED, QUEUED, RUNNING
    o = _orch(env, project, monkeypatch)
    tid = o.db.add_task("codex", "sửa X", "sửa X", model="gpt-6.1-sol", effort="xhigh")
    o.db.update_task(tid, status=FAILED, error="Thoát với mã 3", session="s1", session_agent="codex")
    msg = o.assign(tid, "grok", rerun=True)
    t = o.db.task(tid)
    assert "grok" in msg and t.status == QUEUED and t.agent == "grok" and t.error is None
    assert t.model is None and t.effort is None  # model/effort riêng là của codex
    # chạy lại bằng prompt đầy đủ: phiên cũ là của codex, không tiếp tục được với grok
    o.db.update_task(tid, status=CANCELLED)
    o.assign(tid, "claude")  # không rerun: chỉ đổi agent
    assert o.db.task(tid).status == CANCELLED and o.db.task(tid).agent == "claude"
    o.db.update_task(tid, status=RUNNING)
    assert "đang chạy" in o.assign(tid, "codex", rerun=True)


def test_web_ops_cancel_plan_and_reassign(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB, FAILED
    from ateam.web import WebApp
    ensure_global_config()
    wa = WebApp(project, load_config(project), DB(project / ".ateam/team.db"), 0)

    async def main():
        o = wa.orch
        tid = o.db.add_task("codex", "x", "x")
        o.db.update_task(tid, status=FAILED)
        msg, kind = (await wa.handle({"op": "assign", "task": tid, "agent": "grok", "rerun": True}))[:2]
        assert o.db.task(tid).agent == "grok" and o.db.task(tid).status == "queued"
        gid = o.db.add_goal("y")
        o.db.update_goal(gid, status="planning")  # kẹt "đang lập kế hoạch" (vd app tắt giữa chừng)
        msg = (await wa.handle({"op": "cancel_plan", "goal": gid}))[0]
        assert "Đã huỷ" in msg and o.db.goal(gid).status == "cancelled"
        assert "Dùng: /assign" in (await wa.handle({"op": "submit", "text": f"/assign {tid}"}))[0]
    asyncio.run(main())


def test_init_timeout_does_not_fall_back_and_quit_sees_lead_run(env, project, monkeypatch):
    """/init khám phá cả dự án: dùng timeout của agent (không phải lead_timeout) và hết giờ thì dừng — agent dự phòng
    cũng phải khám phá lại từ đầu. Trong lúc chạy, all_runs() có lượt trưởng nhóm để thoát app thì dừng nó."""
    o = _orch(env, project, monkeypatch)
    o.cfg.lead_timeout = 600
    o.cfg.agents["claude"].timeout = 1

    async def main():
        job = asyncio.ensure_future(o.init_overview("TREO_INIT"))
        await _until(lambda: o.lead_live)
        assert o.all_runs() and all(r.argv[0].endswith("claude") for r in o.all_runs())
        ok, msg = await job
        assert not ok and not o.lead_live
        log = (project / ".ateam/logs/system.log").read_text()
        assert "claude quá 1s chưa xong" in log and "codex làm thay" not in log
    asyncio.run(main())

