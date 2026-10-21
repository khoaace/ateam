"""Lỗi tiềm ẩn đã sửa: nhận nhầm hết hạn mức, bóc JSON, chạy trùng task, mất việc khi commit worktree lỗi,
huỷ lúc verify, merge chồng lên merge dở của người dùng, runner (dòng dài, bộ nhớ, tiến trình con nền)."""

from __future__ import annotations

import asyncio
import importlib
import subprocess
import sys
import time
from pathlib import Path

from conftest import ateam, git_init, tasks, write_project_config

from ateam import limits
from ateam import prompts as P
from ateam.runner import Run


def _orch(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import load_config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    return Orchestrator(project, load_config(project), DB(project / ".ateam/team.db"))


def test_short_successful_answer_is_not_rate_limit():
    out = "I've reached the root cause of the bug.\nFixed parser.\nAdded tests.\nSUMMARY: add rate limiting to API"
    assert not limits.looks_rate_limited(out, 0)
    assert limits.looks_rate_limited("You've reached your usage limit. Try again in 5 minutes.", 1)
    assert limits.looks_rate_limited("Claude AI usage limit reached|%d" % (time.time() + 60), 0)


def test_extract_json_skips_empty_and_off_schema_values():
    out = 'files: []\nKế hoạch:\n[{"agent": "codex", "prompt": "x"}]'
    assert P.extract_json(out, list, keys=("prompt", "agent")) == [{"agent": "codex", "prompt": "x"}]
    out = '{"name": "pkg", "version": "1.0"}\n{"done": true, "summary": "ok"}'
    assert P.extract_json(out, dict, keys=("done", "summary")) == {"done": True, "summary": "ok"}
    assert P.extract_json("[] {}", list) is None and P.extract_json("[] {}", dict) is None
    t = time.time()
    assert P.extract_json("{" * 20000 + " không phải JSON", dict) is None
    assert time.time() - t < 2  # trước đây chép chuỗi ở mỗi dấu { (bậc hai)


def test_notes_skip_prompt_example():
    assert P.parse_notes("<<<NOTE>>>your note<<<END>>>\n<<<NOTE>>>cổng 8080<<<END>>>") == ["cổng 8080"]


def _run(argv, **kw) -> tuple[Run, int, list]:
    got: list[str] = []
    run = Run(argv, ".", {"PATH": "/usr/bin:/bin"}, timeout=kw.pop("timeout", 20), on_line=got.append, **kw)
    return run, asyncio.run(run.start()), got


def test_runner_long_line_without_newline_is_bounded():
    code = "import sys\nfor i in range(3000): sys.stdout.write('\\r' + 'x' * 4000)\nprint('\\nxong')"
    t = time.time()
    run, rc, got = _run([sys.executable, "-c", code], use_pty=False)
    assert rc == 0 and got[-1] == "xong" and time.time() - t < 10
    assert all(len(line) <= 70_000 for line in got)


def test_runner_keep_lines_limits_memory():
    run, rc, got = _run([sys.executable, "-c", "for i in range(100): print(i)"], use_pty=True, keep_lines=10)
    assert rc == 0 and len(got) == 100 and list(run.lines) == [str(i) for i in range(90, 100)]
    assert run.output.endswith("99")


def test_runner_pipe_does_not_wait_for_background_child():
    t = time.time()
    run, rc, got = _run(["/bin/sh", "-c", "sleep 30 & echo xong"], use_pty=False, timeout=25)
    try:
        assert rc == 0 and "xong" in got and time.time() - t < 10
    finally:
        run.kill_now()
        subprocess.run(["pkill", "-f", "sleep 30"], capture_output=True)


def test_child_pwd_follows_cwd(tmp_path):
    """$PWD của tiến trình con = thư mục chạy, không phải PWD kế thừa (dự án cũ sau /open, gốc khi ở worktree)."""
    from ateam.pty_session import PtySession
    for pty in (False, True):
        got: list[str] = []
        run = Run(["/bin/sh", "-c", "echo $PWD"], str(tmp_path), {"PATH": "/usr/bin:/bin", "PWD": "/du-an-cu"},
                  use_pty=pty, timeout=20, on_line=got.append)
        assert asyncio.run(run.start()) == 0 and got[-1].strip() == str(tmp_path)
    s = PtySession(["/bin/sh"], str(tmp_path), {"PWD": "/du-an-cu"}, on_data=lambda b: None, on_exit=lambda rc: None)
    assert s.env["PWD"] == str(tmp_path)


def test_claim_task_is_atomic_across_connections(project):
    from ateam.db import DB
    a, b = DB(project / ".ateam/team.db"), DB(project / ".ateam/team.db")
    tid = a.add_task("codex", "x", "x", status="queued")
    assert a.claim_task(tid) is True
    assert b.claim_task(tid) is False
    assert b.task(tid).status == "running"


def test_cli_run_keeps_tasks_of_open_ui_session(env, project, monkeypatch):
    from ateam.cli import acquire_session_lock
    from ateam.db import DB
    db = DB(project / ".ateam/team.db")
    tid = db.add_task("codex", "đang chạy ở TUI", "x", status="queued")
    assert db.claim_task(tid)
    lock = acquire_session_lock(project)  # giả làm phiên TUI đang mở
    try:
        ateam(env, project, "run", "-q")
        assert db.task(tid).status == "running"
    finally:
        lock.close()
    ateam(env, project, "run", "-q")  # không còn giao diện nào: đúng là dở dang từ phiên trước
    assert db.task(tid).status == "failed"


def test_worktree_commit_ignores_failing_pre_commit_hook(env, project):
    git_init(project)
    hook = project / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\necho hook chặn; exit 1\n")
    hook.chmod(0o755)
    write_project_config(project, 'isolation = "worktree"\nauto_review = false\n')
    r = ateam(env, project, "goal", "-y", "-q", "x")
    assert "done" in r.stdout
    log = subprocess.run(["git", "log", "--oneline"], cwd=project, capture_output=True, text=True).stdout
    assert "ateam: merge #1" in log


def test_auto_merge_does_not_abort_users_merge(env, project, monkeypatch):
    git_init(project)

    def g(*a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=project,
                              capture_output=True, text=True)
    g("checkout", "-qb", "ateam/t1")
    (project / "x.txt").write_text("task\n")
    g("add", ".")
    g("commit", "-qm", "task")
    g("checkout", "-q", "-")
    g("checkout", "-qb", "other")
    (project / "base.txt").write_text("other\n")
    g("commit", "-qam", "other")
    g("checkout", "-q", "-")
    (project / "base.txt").write_text("mine\n")
    g("commit", "-qam", "mine")
    assert g("merge", "other").returncode != 0  # người dùng đang giải xung đột
    o = _orch(env, project, monkeypatch)
    tid = o.db.add_task("codex", "t", "t", status="done")

    async def main():
        return await o._merge_branch(o.db.task(tid))
    ok, msg = asyncio.run(main())
    assert not ok and "merge dở" in msg
    assert g("rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0  # merge của người dùng còn nguyên


def test_cancel_during_verify_does_not_start_fix(env, project, monkeypatch):
    ateam(env, project, "verify", "sleep 20; exit 1")
    o = _orch(env, project, monkeypatch)

    async def main():
        await o.setup()
        tid = o.db.add_task("codex", "tạo a", "tạo a", status="queued")
        job = asyncio.ensure_future(o.run_until_idle())
        for _ in range(200):
            r = o.runs.get(tid)
            if r is not None and r.argv[:2] == ["/bin/sh", "-c"] and r.proc:
                break
            await asyncio.sleep(0.05)
        o.cancel(tid)
        await asyncio.wait_for(job, 30)
        return o.db.task(tid)
    t = asyncio.run(main())
    assert t.status == "cancelled" and not t.attempts


def test_plan_error_does_not_leave_goal_stuck(env, project, monkeypatch):
    o = _orch(env, project, monkeypatch)

    async def boom(*_a, **_k):
        raise OSError("E2BIG")
    monkeypatch.setattr(o, "_call_lead", boom)

    async def main():
        gid = o.db.add_goal("x")
        o.db.update_goal(gid, status="planning")
        await o._plan(gid)
        return o.db.goal(gid)
    g = asyncio.run(main())
    assert g.status == "failed" and "E2BIG" in g.summary


def test_safe_path_blocks_git_dir_any_case(tmp_path):
    from ateam.web_code import safe_path
    (tmp_path / ".git").mkdir()
    assert safe_path(tmp_path, ".GIT/config") is None and safe_path(tmp_path, ".git/config") is None
    assert safe_path(tmp_path, "src/a.py") == (tmp_path / "src/a.py").resolve()


def test_cancelled_run_stops_its_process():
    """Huỷ task đang chờ Run (thoát app, Ctrl+C): tiến trình ở session riêng phải bị dừng, không chạy mồ côi."""
    import os

    async def main():
        run = Run(["sleep", "30"], ".", dict(os.environ), use_pty=False, timeout=60, on_line=lambda _l: None)
        job = asyncio.ensure_future(run.start())
        for _ in range(100):
            await asyncio.sleep(0.02)
            if run.proc:
                break
        job.cancel()
        try:
            await job
        except asyncio.CancelledError:
            pass
        assert run.cancelled
        await asyncio.wait_for(run.proc.wait(), 5)
        return run.proc.returncode
    assert asyncio.run(main()) != 0

