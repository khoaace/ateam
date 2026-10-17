"""Giữ phiên agent (--resume): /retry, vòng sửa verify, /continue mục tiêu dùng lại phiên CLI cũ."""

from __future__ import annotations

import asyncio
import importlib

from conftest import ateam, tasks

from ateam.config import AgentConfig


def test_argv_session_and_resume_flags():
    c = AgentConfig("claude", ["claude", "-p", "{prompt}", "--permission-mode", "acceptEdits"],
                    model_args=["--model", "{model}"])
    assert c.can_resume()
    assert c.argv("x", session="s1") == ["claude", "--session-id", "s1", "-p", "x", "--permission-mode",
                                         "acceptEdits"]
    assert c.argv("x", model="opus", session="s1", resume=True)[:5] == ["claude", "--model", "opus", "--resume", "s1"]
    k = AgentConfig("codex", ["codex", "exec", "--sandbox", "workspace-write", "--skip-git-repo-check", "{prompt}"])
    assert k.can_resume() and not k.session_flags(False)  # codex: id bắt từ header "session id:"
    assert k.argv("x", session="u1") == ["codex", "exec", "--sandbox", "workspace-write", "--skip-git-repo-check", "x"]
    assert k.argv("x", session="u1", resume=True) == [
        "codex", "exec", "resume", "--skip-git-repo-check", "-c", 'sandbox_mode="workspace-write"', "u1", "x"]
    # CLI không có preset, hoặc tắt bằng resume_args = []
    assert not AgentConfig("o", ["opencode", "run", "{prompt}"]).can_resume()
    assert not AgentConfig("c", ["claude", "-p", "{prompt}"], resume_args=[]).can_resume()


def _orch(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import load_config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    return Orchestrator(project, load_config(project), DB(project / ".ateam/team.db"))


def test_retry_and_verify_fix_resume_same_session(env, project, monkeypatch, tmp_path):
    ateam(env, project, "verify", 'test -f fixed.txt || { echo "FAIL: thiếu fixed.txt"; exit 1; }')
    o = _orch(env, project, monkeypatch)
    full = tmp_path / "full.log"
    monkeypatch.setenv("ATEAM_FAKE_FULL_LOG", str(full))

    async def main():
        await o.setup()
        tid = o.db.add_task("codex", "tạo a", "tạo a", status="queued")
        await o.run_until_idle()
        t = o.db.task(tid)
        assert t.status == "done" and t.attempts == 1 and t.session
        log = o.log_path(tid).read_text()
        # vòng sửa: cùng phiên, prompt chỉ có lỗi test (không nhắc lại đề bài)
        assert f"codex · fix" in log and f"tiếp tục phiên {t.session}" in log
        text = full.read_text()
        fix_call = text[text.index("exec resume"):]
        assert "ORIGINAL TASK" not in fix_call and "VERIFICATION COMMAND" in fix_call
        # /retry: cùng phiên, prompt ngắn nêu lý do chạy lại
        o.retry(tid)
        assert o.db.task(tid).resume
        await o.run_until_idle()
        assert f"tiếp tục phiên {t.session}" in o.log_path(tid).read_text()
        text = full.read_text()
        assert "asked you to run this same task again" in text[text.rindex("<<codex>>"):]
        assert o.db.task(tid).resume is None
        # đổi agent: phiên của codex không được dùng cho agent khác
        o.db.update_task(tid, agent="claude", status="failed")
        o.retry(tid)
        await o.run_until_idle()
        t2 = o.db.task(tid)
        assert t2.session_agent == "claude" and t2.session != t.session
        assert "tiếp tục phiên" not in o.log_path(tid).read_text()
    asyncio.run(main())


def test_continue_goal_resumes_lead_session(env, project, tmp_path):
    ateam(env, project, "goal", "-y", "-q", "Tạo các file a b c")
    from ateam.db import DB
    g = DB(project / ".ateam/team.db").goal(1)
    assert g.lead_session and g.lead_session_agent == "claude"
    env = dict(env, ATEAM_FAKE_ARGS_LOG=str(tmp_path / "args2.log"))
    ateam(env, project, "continue", "m1", "-y", "-q", "thêm file d")
    args = (tmp_path / "args2.log").read_text().splitlines()
    assert any(a.startswith("claude --resume " + g.lead_session) for a in args), args
    assert any(t.title == "Tạo d.txt" and t.status == "done" for t in tasks(project))
