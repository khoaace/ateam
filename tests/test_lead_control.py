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


def test_task_requeued_for_limits_at_most_max_times(env, project, monkeypatch):
    """Lỗi lặp lại mà khớp mẫu quá tải / hết hạn mức (quota hết hẳn, cấu hình sai trả 503…) không xếp task lại mãi."""
    from ateam.db import FAILED, QUEUED, RUNNING
    from ateam.orchestrator import MAX_REQUEUES
    o = _orch(env, project, monkeypatch)
    tid = o.db.add_task("codex", "t", "p", status=RUNNING)
    o.cfg.agents["codex"].fallback = []

    class FakeRun:
        output, cancelled, timed_out = "HTTP 503 Service Unavailable", False, False

    async def overloaded(t, a, prompt, workdir, log_file, **kw):
        return FakeRun(), 1, "overloaded"
    monkeypatch.setattr(o, "_run_agent", overloaded)
    monkeypatch.setattr(o, "_set_cooldown", lambda *a, **k: None)

    async def main():
        for i in range(MAX_REQUEUES + 1):
            o.db.update_task(tid, status=RUNNING)
            await o._run_task(tid)
            t = o.db.task(tid)
            assert t.status == (QUEUED if i < MAX_REQUEUES else FAILED), (i, t.status)
        assert "lặp lại" in o.db.task(tid).error
        o.retry(tid)  # người dùng /retry: đếm lại từ đầu
        assert tid not in o._requeues
    asyncio.run(main())


def test_goal_with_all_tasks_cancelled_skips_review(env, project, monkeypatch):
    """Người dùng huỷ hết task của mục tiêu: kết thúc luôn, không gọi trưởng nhóm review (tốn một lượt)."""
    from ateam.db import CANCELLED
    o = _orch(env, project, monkeypatch)
    gid = o.db.add_goal("G")
    o.db.update_goal(gid, status="running")
    o.db.add_task("codex", "t", "p", goal_id=gid, status=CANCELLED)
    assert o._check_goals()
    assert o.db.goal(gid).status == "cancelled" and gid not in o.lead_busy



def test_clear_finished_deletes_leftover_task_branches(env, project, monkeypatch):
    """Task lỗi ở chế độ worktree giữ nhánh ateam/tN để xem lại; dọn khỏi bảng việc thì xoá luôn nhánh đó."""
    import subprocess

    from ateam.db import FAILED
    o = _orch(env, project, monkeypatch)
    tid = o.db.add_task("codex", "t", "p", status=FAILED)
    subprocess.run(["git", "branch", f"ateam/t{tid}"], cwd=project, check=True)
    o.db.update_task(tid, branch=f"ateam/t{tid}")

    async def main():
        assert o.clear_finished() == (1, 0)
        await asyncio.gather(*list(o._bg))
    asyncio.run(main())
    out = subprocess.run(["git", "branch", "--list", "ateam/*"], cwd=project, capture_output=True, text=True).stdout
    assert not out.strip()


def test_delete_task_outside_plan(env, project, monkeypatch):
    """/delete: xoá hẳn task ngoài kế hoạch cùng log + nhánh; task trong kế hoạch / đang chạy / chờ duyệt / còn task
    khác chờ thì không."""
    import subprocess

    from ateam.db import DONE, FAILED, QUEUED, REVIEW, RUNNING
    o = _orch(env, project, monkeypatch)
    gid = o.db.add_goal("G")
    in_plan = o.db.add_task("codex", "trong ke hoach", "p", goal_id=gid, status=DONE)
    failed = o.db.add_task("codex", "loi", "p", status=FAILED)
    subprocess.run(["git", "branch", f"ateam/t{failed}"], cwd=project, check=True)
    o.db.update_task(failed, branch=f"ateam/t{failed}")
    o.log_path(failed).parent.mkdir(parents=True, exist_ok=True)
    o.log_path(failed).write_text("log")
    running = o.db.add_task("codex", "dang chay", "p", status=RUNNING)
    review = o.db.add_task("codex", "cho duyet", "p", status=REVIEW)
    base = o.db.add_task("codex", "nen", "p", status=DONE)
    o.db.add_task("claude", "phu thuoc", "p", status=QUEUED, depends_on=[base])

    async def main():
        assert "kế hoạch #" in o.delete_task(in_plan)
        assert "/cancel" in o.delete_task(running)
        assert "merge" in o.delete_task(review)
        assert "bị chặn" in o.delete_task(base)
        assert o.delete_task(failed) == f"Đã xoá task #{failed}"
        assert "Không có task" in o.delete_task(failed)
        await asyncio.gather(*list(o._bg))
    asyncio.run(main())
    left = {t.id for t in o.db.tasks()}
    assert failed not in left and {in_plan, running, review, base} <= left
    assert not o.log_path(failed).exists()
    out = subprocess.run(["git", "branch", "--list", "ateam/*"], cwd=project, capture_output=True, text=True).stdout
    assert not out.strip()


def test_retry_unblocks_whole_chain(env, project, monkeypatch):
    """/retry bước đầu của chuỗi 1 → 2 → 3: mọi bước phía sau (không chỉ bước liền sau) được xếp lại."""
    from ateam.db import BLOCKED, FAILED, QUEUED
    o = _orch(env, project, monkeypatch)
    gid = o.db.add_goal("G")
    o.db.update_goal(gid, status="incomplete")
    a = o.db.add_task("codex", "a", "tạo a", goal_id=gid, status=FAILED)
    b = o.db.add_task("codex", "b", "tạo b", goal_id=gid, status=BLOCKED)
    c = o.db.add_task("codex", "c", "tạo c", goal_id=gid, status=BLOCKED)
    o.db.update_task(b, depends_on=[a])
    o.db.update_task(c, depends_on=[b])
    o.retry(a)
    assert [o.db.task(x).status for x in (a, b, c)] == [QUEUED] * 3
    assert o.db.goal(gid).status == "running"


def _gate_flow(o):
    from ateam.config import Workflow, WorkflowStep
    o.cfg.workflows["duyet"] = Workflow("duyet", review=False, steps=[
        WorkflowStep("codex", "Thiết kế", "viết thiết kế cho {goal}"),
        WorkflowStep("lead", "Duyệt thiết kế", kind="gate"),
        WorkflowStep("grok", "Làm", "làm {goal} theo thiết kế")])
    o.cfg.approve_plan = False
    return o.run_workflow("duyet", "trang đăng nhập")


def _steps(o, gid: int) -> list:
    """Các bước của workflow (bỏ task codex giả lập tự giao thêm qua <<<DELEGATE>>>)."""
    return [t for t in o.db.tasks(goal_id=gid) if not t.source.startswith("delegate")]


def _calls(log: Path) -> list[tuple[str, str]]:
    return [(c.partition(">> ")[0], c.partition(">> ")[2]) for c in log.read_text(encoding="utf-8").split("<<")[1:]]


def test_workflow_gate_continue_hands_off_previous_result(env, project, monkeypatch, tmp_path):
    """⏸ bước duyệt: không gọi agent, hỏi người dùng; Tiếp tục → bước sau chạy và nhận kết quả bước trước bước duyệt."""
    from ateam.db import ASKING, DONE
    env["ATEAM_FAKE_FULL_LOG"] = str(tmp_path / "full.log")
    o = _orch(env, project, monkeypatch)

    async def main():
        await o.setup()
        gid = _gate_flow(o)
        await o.run_until_idle(interval=0.01)
        design, gate, work = _steps(o, gid)
        assert design.status == DONE and gate.status == ASKING and work.status == "queued"
        v = o.waiting_view()
        assert v["gate"] and v["task"] == gate.id and v["question"]["options"] == ["Tiếp tục", "Dừng"]
        assert f"#{design.id} Thiết kế (codex)" in v["question"]["q"]
        assert "Đã duyệt" in o.answer_task(gate.id, "1")
        await o.run_until_idle(interval=0.01)
        return _steps(o, gid), o.db.goal(gid)
    ts, g = asyncio.run(main())
    assert [t.status for t in ts] == [DONE] * 3 and g.status == "done"
    calls = _calls(tmp_path / "full.log")
    assert all(n != o.cfg.lead for n, _ in calls)  # bước duyệt (agent = trưởng nhóm) không gọi agent nào
    work = next(c for n, c in calls if n == "grok" and f"YOUR TASK (#{ts[2].id})" in c)
    assert f"--- #{ts[0].id} by codex: Thiết kế ---" in work  # bàn giao xuyên qua bước duyệt


def test_workflow_gate_feedback_redoes_step_then_asks_again(env, project, monkeypatch, tmp_path):
    from ateam.db import ASKING
    env["ATEAM_FAKE_FULL_LOG"] = str(tmp_path / "full.log")
    o = _orch(env, project, monkeypatch)

    async def main():
        await o.setup()
        gid = _gate_flow(o)
        await o.run_until_idle(interval=0.01)
        gate = _steps(o, gid)[1]
        assert "làm lại" in o.answer_task(gate.id, "dùng OAuth thay vì mật khẩu")
        await o.run_until_idle(interval=0.01)
        return _steps(o, gid)
    design, gate, work = asyncio.run(main())
    assert gate.status == ASKING and len(gate.ask["qa"]) == 2 and work.status == "queued"
    codex = [c for n, c in _calls(tmp_path / "full.log") if n == "codex"]
    assert len(codex) == 2 and "dùng OAuth thay vì mật khẩu" in codex[1]


def test_workflow_gate_stop_ends_goal_without_review(env, project, monkeypatch):
    from ateam.db import CANCELLED, DONE
    o = _orch(env, project, monkeypatch)

    async def main():
        await o.setup()
        o.cfg.workflows.clear()
        gid = _gate_flow(o)
        o.cfg.workflows["duyet"].review = True  # dừng ở bước duyệt: không gọi trưởng nhóm review
        await o.run_until_idle(interval=0.01)
        gate = _steps(o, gid)[1]
        o.answer_task(gate.id, "2")
        await o.run_until_idle(interval=0.01)
        return _steps(o, gid), o.db.goal(gid)
    ts, g = asyncio.run(main())
    assert [t.status for t in ts] == [DONE, CANCELLED, CANCELLED]
    assert g.status == "incomplete" and "dừng ở bước duyệt" in g.summary


def test_workflow_gate_auto_approves_without_user(env, project, monkeypatch):
    o = _orch(env, project, monkeypatch)

    async def main():
        await o.setup()
        o.auto_answer = True
        gid = _gate_flow(o)
        await o.run_until_idle(interval=0.01)
        return _steps(o, gid)
    assert [t.status for t in asyncio.run(main())] == ["done"] * 3
