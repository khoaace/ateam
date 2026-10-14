"""Test luồng đầu-cuối bằng agent giả lập (tests/fakebin). Mỗi test chạy `python -m ateam`."""

from __future__ import annotations

import subprocess

from conftest import ateam, git_init, tasks, write_project_config


def test_goal_plan_run_delegate_review(env, project):
    r = ateam(env, project, "goal", "-y", "-q", "Tạo các file a b c")
    assert "=== Mục tiêu #1: done ===" in r.stdout, r.stdout
    ts = {t.id: t for t in tasks(project)}
    # kế hoạch: codex (effort xhigh do trưởng nhóm đặt), grok, antigravity (effort sai bị bỏ)
    assert ts[1].agent == "codex" and ts[1].effort == "xhigh"
    assert ts[3].agent == "antigravity" and ts[3].effort is None and ts[3].depends_on == [1, 2]
    # codex giao README cho grok
    assert any(t.source == "delegate:codex" and t.agent == "grok" for t in ts.values())
    # review vòng 1 giao thêm c.txt cho claude
    assert any(t.agent == "claude" and t.source == "review" for t in ts.values())
    assert all(t.status == "done" for t in ts.values())
    for f in ("a.txt", "b.txt", "c.txt", "README.md"):
        assert (project / f).exists(), f
    # agy (chỉ in khi có tty) phải nhận được kết quả của task 1 và ghi chú chung
    log3 = (project / ".ateam/logs/t3.log").read_text()
    assert "thấy kết quả task 1" in log3 and "\x1b[" not in log3


def test_model_effort_flags_reach_cli(env, project, tmp_path):
    ateam(env, project, "set", "codex", "--model", "gpt-5.5", "--effort", "high")
    ateam(env, project, "add", "--to", "codex", "--effort", "xhigh", "tạo a")
    ateam(env, project, "run", "-q")
    args = (tmp_path / "args.log").read_text()
    # effort riêng của task (xhigh) thắng effort mặc định của agent (high)
    assert '-m gpt-5.5 -c model_reasoning_effort="xhigh"' in args, args


def test_missing_cli_and_empty_output_and_timeout(env, project):
    write_project_config(project, """
[agents.ghost]
command = ["khong-ton-tai", "{prompt}"]
[agents.mute]
command = ["agy", "-p", "{prompt}"]
pty = false
[agents.slow]
command = ["bash", "-c", "sleep 30", "_"]
timeout = 2
""")
    for a in ("ghost", "mute", "slow"):
        ateam(env, project, "add", "--to", a, f"việc của {a}")
    ateam(env, project, "add", "--to", "codex", "--title", "phụ thuộc", "x")
    from ateam.db import DB
    DB(project / ".ateam/team.db").update_task(4, depends_on=[3])
    ateam(env, project, "run", "-q")
    ts = {t.agent: t for t in tasks(project)}
    assert "Chưa cài" in ts["ghost"].error
    assert "không in ra gì" in ts["mute"].error  # agy không có pty -> im lặng
    assert "Quá thời gian" in ts["slow"].error
    assert ts["codex"].status == "blocked"


def test_worktree_auto_merge(env, project):
    git_init(project)
    write_project_config(project, 'isolation = "worktree"\nauto_review = false\n')
    r = ateam(env, project, "goal", "-y", "-q", "x")
    assert "done" in r.stdout
    log = subprocess.run(["git", "log", "--oneline"], cwd=project, capture_output=True, text=True).stdout
    assert "ateam: merge #1" in log
    branches = subprocess.run(["git", "branch"], cwd=project, capture_output=True, text=True).stdout
    assert "ateam/" not in branches  # nhánh đã merge được dọn
    status = subprocess.run(["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True).stdout
    assert status.strip() == ""


def test_worktree_conflict(env, project):
    git_init(project)
    write_project_config(project, """isolation = "worktree"
max_parallel = 3
[agents.w1]
command = ["bash", "-c", "sleep 0.3; echo w1 > same.txt; echo SUMMARY: w1", "_"]
[agents.w2]
command = ["bash", "-c", "sleep 0.3; echo w2 > same.txt; echo SUMMARY: w2", "_"]
""")
    ateam(env, project, "add", "--to", "w1", "a")
    ateam(env, project, "add", "--to", "w2", "b")
    ateam(env, project, "run", "-q")
    st = sorted(t.status for t in tasks(project))
    assert st == ["conflict", "done"], st


def test_review_mode_diff_merge_reject(env, project):
    git_init(project)
    write_project_config(project, 'isolation = "worktree"\nmerge = "review"\n')
    ateam(env, project, "add", "--to", "grok", "tạo b")
    ateam(env, project, "add", "--to", "codex", "tạo a")
    ateam(env, project, "run", "-q")
    assert [t.status for t in tasks(project)] == ["review", "review"]
    assert not (project / "b.txt").exists()
    d = ateam(env, project, "diff", "1").stdout
    assert "+++ b/b.txt" in d
    assert "Đã merge #1" in ateam(env, project, "merge", "1").stdout
    assert (project / "b.txt").exists()
    ateam(env, project, "reject", "2", "đặt", "tên", "khác")
    t2 = tasks(project)[1]
    assert t2.status == "queued" and "REVIEWER FEEDBACK" in t2.prompt and "đặt tên khác" in t2.prompt


def test_verify_fix_loop(env, project):
    ateam(env, project, "verify", 'test -f fixed.txt || { echo "FAIL: thiếu fixed.txt"; exit 1; }')
    ateam(env, project, "add", "--to", "codex", "tạo a")
    ateam(env, project, "run", "-q")
    t = tasks(project)[0]
    assert t.status == "done" and t.attempts == 1
    assert "[test] FAIL" in (project / ".ateam/logs/t1.log").read_text()


def test_verify_gives_up_after_max_attempts(env, project):
    ateam(env, project, "verify", "echo boom; exit 3")
    ateam(env, project, "add", "--to", "grok", "tạo b")
    ateam(env, project, "run", "-q")
    t = tasks(project)[0]
    assert t.status == "failed" and t.attempts == 2 and "vẫn fail" in t.error


def test_verify_skipped_when_nothing_changed(env, project):
    git_init(project)
    write_project_config(project, '[agents.reader]\ncommand = ["bash", "-c", "echo SUMMARY: chỉ đọc", "_"]\n')
    ateam(env, project, "verify", "exit 1")
    ateam(env, project, "add", "--to", "reader", "đọc")
    ateam(env, project, "run", "-q")
    assert tasks(project)[0].status == "done"


def test_rate_limit_fallback_and_lead_fallback(env, project, tmp_path):
    limits_dir = tmp_path / "limits"
    (limits_dir / "grok").touch()
    ateam(env, project, "add", "--to", "grok", "việc 1")
    ateam(env, project, "add", "--to", "grok", "việc 2")
    out = ateam(env, project, "run", "-q").stdout
    assert "grok hết hạn mức" in out
    ts = tasks(project)
    assert [t.agent for t in ts[:2]] == ["codex", "codex"] and all(t.status == "done" for t in ts[:2])
    # trưởng nhóm hết hạn mức -> codex lập kế hoạch thay
    (limits_dir / "claude").touch()
    out = ateam(env, project, "goal", "-y", "-q", "x").stdout
    assert "codex làm thay trưởng nhóm" in out and "Kế hoạch do codex lập" in out
    usage = ateam(env, project, "usage").stdout
    assert "grok" in usage and "claude" in usage


def test_run_exits_when_only_cooldown_tasks_left(env, project, tmp_path):
    for a in ("grok", "codex", "claude"):
        (tmp_path / "limits" / a).touch()
    ateam(env, project, "add", "--to", "grok", "việc")
    r = ateam(env, project, "run", "-q", timeout=60)  # không được treo
    assert tasks(project)[0].status == "queued"
    assert "hết hạn mức" in r.stdout


def test_file_mentions_use_each_agent_syntax(env, project, tmp_path):
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("x = 1\n")
    (project / "my docs").mkdir()
    (project / "my docs" / "plan.md").write_text("plan\n")
    full = tmp_path / "full.log"
    env = dict(env, ATEAM_FAKE_FULL_LOG=str(full))

    def run_for(agent: str) -> str:
        if full.exists():
            full.unlink()
        ateam(env, project, "add", "--to", agent, 'đọc @src/app.py và @"my docs/plan.md", bỏ qua @nope')
        ateam(env, project, "run", "-q")
        return full.read_text()

    out = run_for("claude")
    assert '@src/app.py và @"my docs/plan.md", bỏ qua @nope' in out, out
    out = run_for("codex")
    assert "đọc src/app.py và my docs/plan.md, bỏ qua @nope" in out, out
    out = run_for("grok")
    assert "-f src/app.py -f my docs/plan.md" in out and "đọc src/app.py và" in out, out
    assert "-f" in (tmp_path / "args.log").read_text()


def test_models_refresh_asks_cli(env, project):
    r = ateam(env, project, "models", "grok", "--refresh")
    assert "tìm thấy 3 model" in r.stdout, r.stdout
    assert "xai/grok-5-fast" in r.stdout and "openai/gpt-5.5" not in r.stdout
    # agy chỉ in khi có terminal -> phải hỏi qua pty
    r = ateam(env, project, "models", "antigravity", "--refresh")
    assert "gemini-3-pro" in r.stdout and "Available" not in r.stdout, r.stdout
    # lần sau đọc lại từ state.json, không cần hỏi lại
    r = ateam(env, project, "models")
    assert "xai/grok-5-fast" in r.stdout and "gemini-3-flash" in r.stdout
    assert "claude-opus-5-5" in r.stdout


def test_custom_agent_and_workflow_cli(env, project, tmp_path):
    """Agent tuỳ chỉnh (CLI bất kỳ) + workflow: `ateam flow` tạo task theo bước, không gọi trưởng nhóm."""
    xdg = tmp_path / "xdg" / "ateam"
    xdg.mkdir(parents=True)
    (xdg / "custom.toml").write_text('''
[agents.mine]
command = ["mycli", "--headless", "{prompt}"]
role = "Việc vặt"
effort_args = ["--think", "{effort}"]
efforts = ["low", "high"]

[workflows.ship]
description = "hai bước"
review = false

[[workflows.ship.steps]]
agent = "mine"
title = "Viết {goal}"
prompt = "làm {goal}"

[[workflows.ship.steps]]
agent = "mine"
title = "Kiểm tra"
prompt = "kiểm tra lại"
effort = "high"
''', encoding="utf-8")
    r = ateam(env, project, "flows")
    assert "ship  (mine → mine)" in r.stdout, r.stdout
    r = ateam(env, project, "flow", "-y", "-q", "ship", "tính năng X")
    assert "=== Mục tiêu #1: done ===" in r.stdout, r.stdout
    ts = tasks(project)
    assert [(t.agent, t.title, t.source) for t in ts] == [
        ("mine", "Viết tính năng X", "workflow"), ("mine", "Kiểm tra", "workflow")]
    assert ts[1].depends_on == [ts[0].id] and ts[1].effort == "high"
    assert (project / "steps.txt").read_text().splitlines() == ["Viết tính năng X", "Kiểm tra"]
    assert "mycli --headless --think high" in (tmp_path / "args.log").read_text()
    assert not (project / ".ateam/logs/lead.log").exists()  # review = false, không gọi trưởng nhóm
    r = ateam(env, project, "flow", "-y", "nope", "x", check=False)
    assert r.returncode == 1 and "Không có workflow 'nope'" in r.stderr
