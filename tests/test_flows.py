"""Test luồng đầu-cuối bằng agent giả lập (tests/fakebin). Mỗi test chạy `python -m ateam`."""

from __future__ import annotations

import subprocess
from pathlib import Path

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


def test_effort_rejected_by_model_retries_without_effort(env, project, tmp_path):
    """agy: "--effort is not supported for model claude-opus-4-6-thinking" -> chạy lại không có --effort."""
    ateam(env, project, "set", "antigravity", "--model", "claude-opus-4-6-thinking", "--effort", "high")
    ateam(env, project, "add", "--to", "antigravity", "--effort", "xhigh", "tạo a")
    ateam(env, project, "run", "-q")
    assert tasks(project)[-1].status == "done"
    calls = [ln for ln in (tmp_path / "args.log").read_text().splitlines() if ln.startswith("agy ")]
    assert "--effort xhigh" in calls[-2] and "--effort" not in calls[-1], calls
    log = (project / ".ateam" / "logs" / f"t{tasks(project)[-1].id}.log").read_text()
    assert "chạy lại không kèm effort" in log


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
    (project / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    ateam(env, project, "add", "--to", "codex", "làm giống @shot.png")
    ateam(env, project, "run", "-q")
    assert "--image=shot.png" in full.read_text() and "làm giống shot.png" in full.read_text()
    full.unlink()
    out = run_for("codex")
    assert "đọc src/app.py và my docs/plan.md, bỏ qua @nope" in out, out
    out = run_for("grok")  # Grok Build: @file ngay trong prompt
    assert '@src/app.py và @"my docs/plan.md", bỏ qua @nope' in out and "<<grok>>" in out, out
    out = run_for("opencode")
    assert "-f src/app.py -f my docs/plan.md --" in out and "đọc src/app.py và" in out, out
    assert "File not found" not in out  # -f không nuốt prompt (opencode thật báo lỗi này)
    assert "-f" in (tmp_path / "args.log").read_text()


def test_models_refresh_asks_cli(env, project):
    r = ateam(env, project, "models", "grok", "--refresh")  # grok models: "* grok-4.7 (default)"
    assert "grok: tìm thấy 3 model" in r.stdout and "Default" not in r.stdout, r.stdout
    assert "grok-4.7-build-fast" in r.stdout
    r = ateam(env, project, "models", "opencode", "--refresh")  # OpenCode --verbose: mọi nhà cung cấp, không lọc
    assert "tìm thấy 6 model" in r.stdout and "xai/grok-5-fast" in r.stdout, r.stdout
    # agy chỉ in khi có terminal -> phải hỏi qua pty
    r = ateam(env, project, "models", "antigravity", "--refresh")
    assert "gemini-3-pro" in r.stdout and "Available" not in r.stdout, r.stdout
    # lần sau đọc lại từ state.json, không cần hỏi lại
    r = ateam(env, project, "models")
    assert "xai/grok-5-fast" in r.stdout and "gemini-3-flash" in r.stdout
    assert "claude-opus-5-5" in r.stdout
    # codex: danh mục JSON (`codex debug models`), không lọc theo tên agent, model cũ bị báo
    ateam(env, project, "set", "codex", "--model", "gpt-5.5")
    r = ateam(env, project, "models", "codex", "--refresh")
    assert "tìm thấy 2 model" in r.stdout and "'gpt-5.5' không có trong danh sách" in r.stdout, r.stdout
    assert "gpt-6-luna" in r.stdout and "codex-auto-review" not in r.stdout
    # JSON một dòng ~150KB không bị cắt vụn; mức effort riêng từng model được lưu (codex, opencode --verbose)
    import json
    st = json.loads((Path(env["XDG_CONFIG_HOME"]) / "ateam/state.json").read_text())
    assert st["models_found"]["codex"] == ["gpt-6.1-sol", "gpt-6-luna"] and st["models_found_v"] == 2
    assert st["model_efforts"]["codex"]["gpt-6-luna"][-1] == "max"
    assert st["model_efforts"]["opencode"]["opencode/deepseek-v4.1-flash-free"] == ["low", "high", "max"]
    # danh sách lưu bởi bản cũ (có thể là rác "ta, g, he…") bị bỏ để hỏi lại CLI
    st["models_found_v"] = 1
    st["models_found"]["codex"] = ["ta", "g", "he"]
    (Path(env["XDG_CONFIG_HOME"]) / "ateam/state.json").write_text(json.dumps(st))
    r = ateam(env, project, "models", "codex")
    assert "gpt-6-luna" in r.stdout and " he " not in r.stdout and "·he" not in r.stdout, r.stdout


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


def test_doctor_flags_unknown_cli_flag_and_old_codex_config_still_runs(env, project):
    # cấu hình cũ còn --full-auto (codex mới báo "unexpected argument") phải được tự đổi cờ
    write_project_config(project, """
[agents.codex]
command = ["codex", "exec", "--full-auto", "--skip-git-repo-check", "{prompt}"]
[agents.badcodex]
command = ["codex", "exec", "--khong-co-co-nay", "{prompt}"]
enabled = true
""")
    r = ateam(env, project, "doctor", check=False)
    assert r.returncode == 1, r.stdout
    assert "codex exec --sandbox workspace-write --skip-git-repo-check <prompt>" in r.stdout
    assert "cờ không thấy trong `codex exec --help`: --khong-co-co-nay" in r.stdout
    assert "--full-auto" not in r.stdout
    ateam(env, project, "add", "--to", "codex", "tạo a")
    ateam(env, project, "run", "-q")
    assert (project / "a.txt").exists()
    assert tasks(project)[0].status == "done"


def test_compact_replaces_notes_with_lead_summary(env, project, tmp_path):
    r = ateam(env, project, "compact", check=False)
    assert r.returncode == 1 and "Chưa có ghi chú" in r.stdout
    for n in ("API chạy cổng 8080", "dùng pytest", "đừng sửa vendor/"):
        ateam(env, project, "note", n)
    env = dict(env, ATEAM_FAKE_FULL_LOG=str(tmp_path / "full.log"))
    r = ateam(env, project, "compact", "giữ", "cổng")
    assert "Đã thu gọn" in r.stdout and "- API chạy cổng 8080" in r.stdout, r.stdout
    prompt = (tmp_path / "full.log").read_text()
    assert "COMPACT it" in prompt and "đừng sửa vendor/" in prompt and "giữ cổng" in prompt
    from ateam.db import DB
    db = DB(project / ".ateam/team.db")
    notes = db.recent_notes()
    assert [a for a, _ in notes] == ["compact"] and notes[0][1].startswith("- API chạy cổng 8080")
    db.add_note("user", "ghi chú mới")
    assert [a for a, _ in db.recent_notes()] == ["compact", "user"]
    # prompt của task sau chỉ mang bản tóm tắt + ghi chú mới, không còn ghi chú cũ
    ateam(env, project, "add", "--to", "codex", "tạo a")
    ateam(env, project, "run", "-q")
    last = (tmp_path / "full.log").read_text().split("<<codex>>")[-1]
    assert "Mục tiêu đã xong" in last and "ghi chú mới" in last and "đừng sửa vendor/" not in last


def test_usage_asks_each_cli(env, project):
    """ateam usage: thống kê của ateam + hạn mức do CLI từng agent báo (claude/agy: -p /usage,
    opencode stats rút gọn, codex đọc rate_limits trong file phiên)."""
    r = ateam(env, project, "usage")
    out = r.stdout
    assert "📊 claude  (claude -p /usage)" in out and "Current session: 41% used" in out, out
    assert "📊 antigravity  (agy -p /usage)" in out and "Weekly Limit Remaining  29%" in out
    assert "📊 opencode  (opencode stats --days 7)" in out and "stat dòng 20" in out
    assert "stat dòng 21" not in out and "còn 10 dòng" in out
    assert "Chưa có phiên codex nào" in out
    sess = Path(env["CODEX_HOME"]) / "sessions" / "2026" / "10" / "15"
    sess.mkdir(parents=True)
    (sess / "rollout-x.jsonl").write_text(
        '{"timestamp":"2026-10-15T08:12:05Z","type":"event_msg","payload":{"type":"token_count",'
        '"rate_limits":{"plan_type":"plus","primary":{"used_percent":12.5,"window_minutes":300,'
        '"resets_at":1792651616},"secondary":{"used_percent":3,"window_minutes":10080,"resets_at":1792651616}}}}\n')
    out = ateam(env, project, "usage").stdout
    assert "Gói: plus" in out and "Hạn mức chính (5 giờ): đã dùng 12.5%" in out, out
    assert "Hạn mức phụ (tuần): đã dùng 3%" in out
    out = ateam(env, project, "usage", "--local").stdout
    assert "📊" not in out and "Đang tạm nghỉ" in out


def test_permission_denied_fails_with_hint(env, project):
    """agy bị từ chối quyền chạy lệnh vẫn thoát 0: task phải lỗi kèm cách bật Toàn quyền; bật rồi thì xong."""
    ateam(env, project, "add", "--to", "antigravity", "NEEDS_SHELL chạy lint rồi build")
    ateam(env, project, "run", "-q")
    t = tasks(project)[-1]
    assert t.status == "failed" and "Toàn quyền" in (t.error or ""), t
    write_project_config(project, "[agents.antigravity]\nfull_access = true\n")
    ateam(env, project, "add", "--to", "antigravity", "NEEDS_SHELL chạy lint rồi build")
    ateam(env, project, "run", "-q")
    assert tasks(project)[-1].status == "done"
    assert "--dangerously-skip-permissions" in (Path(env["ATEAM_FAKE_ARGS_LOG"])).read_text()
    # Grok Build: --deny Bash chặn lệnh, grok chỉ kể lại bằng lời rồi thoát 0 -> vẫn phải là lỗi
    ateam(env, project, "add", "--to", "grok", "NEEDS_SHELL chạy lint")
    ateam(env, project, "run", "-q")
    t = tasks(project)[-1]
    assert t.status == "failed" and "Toàn quyền" in (t.error or ""), t
    write_project_config(project, "[agents.antigravity]\nfull_access = true\n[agents.grok]\nfull_access = true\n")
    ateam(env, project, "add", "--to", "grok", "NEEDS_SHELL chạy lint")
    ateam(env, project, "run", "-q")
    assert tasks(project)[-1].status == "done"
    assert "grok --permission-mode bypassPermissions" in (Path(env["ATEAM_FAKE_ARGS_LOG"])).read_text()


def test_continue_goal_and_thread(env, project, tmp_path):
    env["ATEAM_FAKE_FULL_LOG"] = str(tmp_path / "full.log")
    ateam(env, project, "goal", "-y", "-q", "Tạo các file a b c")
    n_before = len(tasks(project))
    r = ateam(env, project, "continue", "m1", "-y", "-q", "thêm file d")
    assert "=== Mục tiêu #1: done ===" in r.stdout, r.stdout
    new = [t for t in tasks(project)][n_before:]
    assert new and new[0].source == "followup" and new[0].goal_id == 1 and new[0].title == "Tạo d.txt"
    full = (tmp_path / "full.log").read_text()
    plan = full[full.index("NEW FOLLOW-UP REQUEST") - 3000:full.index("NEW FOLLOW-UP REQUEST") + 200]
    assert "thêm file d" in plan and "tạo a.txt" in plan  # kết quả task cũ đi kèm
    # task thuộc mục tiêu -> tiếp tục cả mục tiêu; ref sai -> báo lỗi
    r = ateam(env, project, "continue", "zz", "x", check=False)
    assert r.returncode == 1 and "Không hiểu" in r.stderr

    # thread /task: hỏi tiếp cùng agent trong cùng phiên CLI (codex exec resume), chỉ gửi yêu cầu mới
    ateam(env, project, "add", "--to", "codex", "viết hàm cộng")
    ateam(env, project, "run", "-q")
    first = next(t for t in tasks(project) if t.title == "viết hàm cộng")
    tid = first.id
    assert first.session and first.session_agent == "codex"
    r = ateam(env, project, "continue", f"t{tid}", "-q", "thêm test cho hàm")
    t = next(t for t in tasks(project) if t.parent_id == tid and t.source == "followup")
    assert t.parent_id == tid and t.source == "followup" and t.goal_id is None and t.status == "done"
    assert f"tiếp tục phiên {first.session}" in (project / f".ateam/logs/t{t.id}.log").read_text()
    assert t.session == first.session
    # phiên không còn (CLI đã xoá) -> chạy lại không resume, prompt kèm lượt trước
    import shutil
    shutil.rmtree(env["CODEX_HOME"] + "/fake_sessions")
    ateam(env, project, "continue", f"t{t.id}", "-q", "thêm docstring")
    t2 = next(x for x in tasks(project) if x.parent_id == t.id)
    log = (project / f".ateam/logs/t{t2.id}.log").read_text()
    assert t2.status == "done" and "không tiếp tục được phiên cũ" in log and "nhớ lượt trước" in log
    assert t2.session and t2.session != first.session
