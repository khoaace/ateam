"""Kiểm tra lệnh thực tế, đính kèm OpenCode và output Grok; chỉ dùng CLI giả lập."""

from __future__ import annotations

import asyncio
import importlib

import pytest

from conftest import ateam, git_init, write_project_config
from ateam import mentions
from ateam.config import AgentConfig, agent_from_dict, help_command, parse_models, provider_template
from ateam.doctor import command_examples, inspect_commands
from ateam.opencode import ATTACHMENT_MAX


def test_opencode_directory_references_remain_in_prompt(tmp_path):
    folder = tmp_path / "my source"
    folder.mkdir()
    (folder / "main.py").write_text("x = 1\n")
    prompt, args = mentions.render('@"my source/" và @"my source/main.py"', "opencode", [tmp_path])
    assert prompt == "my source/ và my source/main.py"
    assert args == ["-f", "my source/main.py"]
    # File riêng trong thư mục gốc vẫn đọc được khi task chạy ở worktree.
    wt = tmp_path / "wt"
    wt.mkdir()
    prompt, args = mentions.render('@"my source/"', "/bin/opencode", [wt, tmp_path])
    assert prompt == str(folder) and args == []


def test_opencode_attachment_size_boundary_and_custom_flags(tmp_path):
    large = tmp_path / "large.png"
    with large.open("wb") as f:
        f.truncate(ATTACHMENT_MAX)
    _, args = mentions.render("@large.png", "opencode", [tmp_path], attachment_limit=ATTACHMENT_MAX)
    assert args == ["-f", "large.png"]
    with large.open("ab") as f:
        f.write(b"x")
    with pytest.raises(mentions.AttachmentError, match="10 MiB"):
        mentions.render("@large.png", "opencode", [tmp_path], attachment_limit=ATTACHMENT_MAX)
    assert mentions.render("@large.png", "codex", [tmp_path])[1] == ["--image=large.png"]
    assert mentions.render("@large.png", "opencode", [tmp_path], file_args=[])[1] == []
    assert mentions.render("@large.png", "opencode", [tmp_path], image_args=["--custom-image", "{path}"],
                           attachment_limit=ATTACHMENT_MAX)[1] == ["--custom-image", "large.png"]


def _orch(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from ateam import config
    importlib.reload(config)
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    return Orchestrator(project, config.load_config(project), DB(project / ".ateam/team.db"))


@pytest.mark.parametrize("worktree", [False, True])
def test_large_attachment_fails_cleanly_before_agent_starts(env, project, tmp_path, monkeypatch, worktree):
    env["ATEAM_FAKE_OPENCODE_VERSION"] = "2.0.32"
    env["ATEAM_FAKE_OPENCODE_LOG"] = str(tmp_path / "queries.log")
    if worktree:
        git_init(project)
        write_project_config(project, 'isolation = "worktree"\n')
    o = _orch(env, project, monkeypatch)
    images = project / ".ateam/images"
    images.mkdir(parents=True)
    with (images / "large.png").open("wb") as f:
        f.truncate(ATTACHMENT_MAX + 1)

    async def main():
        await o.setup()
        tid = o.add_task("opencode", "xem @.ateam/images/large.png")
        await o.run_until_idle(interval=0.01)
        task = o.db.task(tid)
        assert task.status == "failed" and "10 MiB" in task.error
        assert "Lỗi nội bộ" not in task.error
        assert not o.activity and not o.runs
        assert not [r for r in o.db.runs_since(0) if r["task_id"] == tid]
        if worktree:
            assert not (project / f".ateam/worktrees/t{tid}").exists()
        o.cfg.lead = "opencode"
        gid = o.new_goal("xem @.ateam/images/large.png")
        await o.run_until_idle(interval=0.01)
        goal = o.db.goal(gid)
        assert goal.status == "failed" and "10 MiB" in goal.summary
        assert not o.activity and not o.lead_busy
    asyncio.run(main())
    assert not any(line.startswith("run ") for line in (tmp_path / "queries.log").read_text().splitlines())


def test_grok_ignores_auth_text_and_cleans_saved_models(env, project, monkeypatch):
    output = "You are not authenticated.\n\nDefault model: grok-4.6\nAvailable models:\n * grok-4.6 (default)\n - grok-4.5\n"
    assert parse_models(output, binary="/bin/grok") == ["grok-4.6", "grok-4.5"]
    assert parse_models("You are not authenticated.", binary="grok") == []
    assert parse_models(output, "4.5", binary="grok") == ["grok-4.5"]
    env["ATEAM_FAKE_GROK_UNAUTHENTICATED"] = "1"
    o = _orch(env, project, monkeypatch)
    from ateam import config
    config.save_found_models("grok", ["You", "grok-4.6", "Please"])
    assert "You" not in config.load_config(project).agents["grok"].models

    async def main():
        msg = await o.discover_models("grok")
        assert "tìm thấy 3 model" in msg and "chưa đăng nhập" in msg
        state = config.load_state()
        assert "You" not in state["models_found"]["grok"]
        before = state["models_found"]["grok"]
        monkeypatch.setenv("ATEAM_FAKE_GROK_AUTH_ONLY", "1")
        msg = await o.discover_models("grok")
        assert "không thấy model nào" in msg
        assert config.load_state()["models_found"]["grok"] == before
    asyncio.run(main())


@pytest.mark.parametrize("version", ["1.19.3", "2.0.32"])
def test_doctor_checks_models_effort_resume_and_usage_without_tasks(env, project, tmp_path, version):
    env["ATEAM_FAKE_OPENCODE_VERSION"] = version
    log = tmp_path / "queries.log"
    env["ATEAM_FAKE_OPENCODE_LOG"] = str(log)
    r = ateam(env, project, "doctor", check=False)
    assert r.returncode == 0, r.stdout
    lines = log.read_text().splitlines()
    assert all(line == "--version" or line.endswith("--help") for line in lines)
    assert "stats --help" in lines and "run --help" in lines
    assert ("api model.list --help" if version.startswith("2") else "models --help") in lines


def test_doctor_reports_invalid_injected_and_auxiliary_flags(env, project):
    write_project_config(project, '''
[agents.bad]
command = ["codex", "exec", "{prompt}"]
model_args = ["--bad-model", "{model}"]
effort_args = ["--bad-effort", "{effort}"]
session_args = ["--bad-new-session", "{session}"]
resume_args = ["--bad-resume", "{session}"]
models_command = ["codex", "debug", "models", "--bad-models"]
usage_command = ["codex", "debug", "models", "--bad-usage"]
''')
    r = ateam(env, project, "doctor", check=False)
    assert r.returncode == 1
    for flag in ("--bad-model", "--bad-effort", "--bad-new-session", "--bad-resume", "--bad-models", "--bad-usage"):
        assert flag in r.stdout
    assert "codex exec resume --help" in r.stdout


def test_doctor_uses_resume_help_and_does_not_repeat_queries(env, project, monkeypatch):
    o = _orch(env, project, monkeypatch)
    import ateam.doctor as doctor
    original = doctor.subprocess.run
    calls = []

    def run(argv, **kwargs):
        calls.append(tuple(argv))
        return original(argv, **kwargs)

    monkeypatch.setattr(doctor.subprocess, "run", run)
    cache = {}
    assert inspect_commands(o.cfg.agents["codex"], project, cache) == []
    alias = agent_from_dict("second-codex", provider_template("codex"))
    assert inspect_commands(alias, project, cache) == []
    assert len(calls) == len(set(calls))
    assert ("codex", "exec", "resume", "--help") in calls


@pytest.mark.parametrize("failure", ["missing", "timeout", "nonzero", "empty"])
def test_doctor_reports_help_that_cannot_be_verified(tmp_path, monkeypatch, failure):
    import ateam.doctor as doctor
    from subprocess import CompletedProcess, TimeoutExpired
    a = AgentConfig("custom", ["mycli", "{prompt}"])
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None if failure == "missing" else "/bin/mycli")
    def run(argv, **kwargs):
        if failure == "timeout":
            raise TimeoutExpired(argv, 15)
        return CompletedProcess(argv, 7 if failure == "nonzero" else 0, "", "")
    monkeypatch.setattr(doctor.subprocess, "run", run)
    issues = inspect_commands(a, tmp_path)
    assert issues and all(issue.error for issue in issues)


def test_web_rejects_images_over_opencode_limit_before_saving(env, project, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer
    from ateam.cli import free_port
    from ateam.web import WebApp
    o = _orch(env, project, monkeypatch)
    app = WebApp(project, o.cfg, o.db, free_port("127.0.0.1", 18000, 1000))  # 8000 có thể đang chạy `ateam web`
    # Ảnh thử lớn hơn 10 MiB nhưng vẫn trong giới hạn chung 20 MiB.
    data = b"\x89PNG\r\n\x1a\n" + b"x" * ATTACHMENT_MAX

    async def main():
        async with TestClient(TestServer(app.make_app(), host="127.0.0.1", port=app.port)) as client:
            a = app.cfg.agents["opencode"]
            a.opencode_major = 2
            result = await (await client.post("/api/image", data=data)).json()
            assert "10 MB" in result["error"]
            assert not (project / ".ateam/images").exists()
            a.enabled = False  # đội không có OpenCode vẫn giữ giới hạn chung 20 MiB
            result = await (await client.post("/api/image", data=data)).json()
            assert "path" in result and (project / result["path"]).stat().st_size == len(data)
    asyncio.run(main())


def test_doctor_never_passes_prompt_to_help(tmp_path):
    a = AgentConfig("custom", ["mycli", "{prompt}"])
    assert all(help_command(cmd) == ["mycli", "--help"] for cmd in command_examples(a, tmp_path))
