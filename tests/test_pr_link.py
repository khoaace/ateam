"""Link tạo/xem Pull Request · Merge Request sau khi push (gitops, web, TUI)."""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from ateam import gitops


def git(path: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True).stdout


def test_remote_web_url():
    f = gitops.remote_web_url
    assert f("git@github.com:chu/repo.git") == "https://github.com/chu/repo"
    assert f("https://github.com/chu/repo.git") == "https://github.com/chu/repo"
    assert f("https://x-access-token:bimat@github.com/chu/repo") == "https://github.com/chu/repo"  # không lộ token
    assert f("ssh://git@gitlab.example.com:2222/nhom/con/repo.git") == "https://gitlab.example.com/nhom/con/repo"
    assert f("git@bitbucket.org:team/repo.git") == "https://bitbucket.org/team/repo"
    assert f("/tmp/remote.git") == "" and f("file:///tmp/r.git") == "" and f("../r.git") == "" and f("") == ""


def test_pr_link_from_server_output():
    gh = ("To github.com:chu/repo.git\nremote: \nremote: Create a pull request for 'tinh-nang' on GitHub by visiting:\n"
          "remote:      https://github.com/chu/repo/pull/new/tinh-nang\nremote: \n * [new branch]  tinh-nang -> tinh-nang\n")
    assert gitops.pr_link_from_output(gh) == {"url": "https://github.com/chu/repo/pull/new/tinh-nang",
                                              "kind": "PR", "view": False}
    gl_new = ("remote: To create a merge request for x, visit:\nremote:   "
              "https://gitlab.com/n/r/-/merge_requests/new?merge_request%5Bsource_branch%5D=x\n")
    link = gitops.pr_link_from_output(gl_new)
    assert link["kind"] == "MR" and not link["view"] and link["url"].endswith("source_branch%5D=x")
    gl_view = "remote: View merge request for x:\nremote:   https://gitlab.com/n/r/-/merge_requests/12\n"
    assert gitops.pr_link_from_output(gl_view) == {"url": "https://gitlab.com/n/r/-/merge_requests/12",
                                                   "kind": "MR", "view": True}
    assert gitops.pr_label(gitops.pr_link_from_output(gl_view)) == "Xem Merge Request"
    bb = "remote: Create pull request for x:\nremote:   https://bitbucket.org/t/r/pull-requests/new?source=x&t=1\n"
    assert gitops.pr_link_from_output(bb)["kind"] == "PR"
    # link khác (cảnh báo bảo mật…) hay output không có remote: → không có
    assert gitops.pr_link_from_output("remote: GitHub found 2 vulnerabilities: https://github.com/c/r/security\n") == {}
    assert gitops.pr_link_from_output("Everything up-to-date\n") == {}


def test_build_pr_link():
    assert gitops.build_pr_link("https://github.com/c/r", "feat/a b")["url"] == \
        "https://github.com/c/r/compare/feat/a%20b?expand=1"
    gl = gitops.build_pr_link("https://gitlab.com/n/r", "feat/x")
    assert gl["kind"] == "MR" and gl["url"].endswith("source_branch%5D=feat%2Fx")
    assert gitops.build_pr_link("https://bitbucket.org/t/r", "x")["url"] == \
        "https://bitbucket.org/t/r/pull-requests/new?source=x"
    assert gitops.build_pr_link("https://git.congty.vn/c/r", "x") == {}  # máy chủ lạ: không đoán
    assert gitops.pr_label({"kind": "PR"}) == "Tạo Pull Request"


def _setup(tmp_path, monkeypatch) -> tuple[Path, Path]:
    """Repo có remote `origin` mang URL GitHub, nhưng push thật vào repo bare trên máy (pushInsteadOf)."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "-c", "user.name=a", "-c", "user.email=a@b", "commit", "-q", "--allow-empty", "-m", "init")
    git(repo, "remote", "add", "origin", "git@github.com:chu/repo.git")
    git(repo, "config", f"url.{remote}.pushInsteadOf", "git@github.com:chu/repo.git")
    return repo, remote


def test_push_sets_pr_link(tmp_path, monkeypatch):
    repo, remote = _setup(tmp_path, monkeypatch)

    async def main():
        g = gitops.GitRepo(repo)
        ok, msg = await g.push()  # nhánh mặc định: không có link
        assert ok, msg
        assert g.last_pr == {} and g.pr_for("main") == {}
        git(repo, "checkout", "-q", "-b", "tinh-nang")
        ok, msg = await g.push()  # máy chủ không in gì: dựng từ URL remote
        assert ok, msg
        assert g.last_pr == {"url": "https://github.com/chu/repo/compare/tinh-nang?expand=1", "kind": "PR",
                             "view": False, "branch": "tinh-nang"}
        assert g.pr_for("tinh-nang") and g.pr_for("main") == {}  # đổi nhánh thì thôi hiện
        # máy chủ in link (như GitHub/GitLab): dùng đúng link đó
        hook = remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\ncat >/dev/null\necho 'To create a merge request for x, visit:'\n"
                        "echo '  https://gitlab.com/n/r/-/merge_requests/new?x=1'\n")
        hook.chmod(0o755)
        git(repo, "checkout", "-q", "-b", "nhanh-2")
        ok, msg = await g.push()
        assert ok, msg
        assert g.last_pr["url"] == "https://gitlab.com/n/r/-/merge_requests/new?x=1" and g.last_pr["kind"] == "MR"
        # push lỗi: giữ link của lần thành công gần nhất (vẫn đúng nhánh)
        git(repo, "remote", "set-url", "origin", str(tmp_path / "khong-co.git"))
        git(repo, "config", "--unset", f"url.{remote}.pushInsteadOf")
        assert not (await g.push())[0]
        assert g.pr_for("nhanh-2")

    asyncio.run(main())


def test_web_push_returns_pr(env, project, monkeypatch, tmp_path):
    import pytest
    pytest.importorskip("aiohttp")
    from test_web import _web_app
    wa = _web_app(env, project, monkeypatch)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(project, "remote", "add", "origin", "https://gitlab.com/nhom/repo.git")
    git(project, "config", f"url.{remote}.pushInsteadOf", "https://gitlab.com/nhom/repo.git")
    git(project, "checkout", "-q", "-b", "sua-loi")

    async def main():
        assert (await wa.handle({"op": "submit", "text": "/pr"}))[1] == "warn"
        r = await wa.handle({"op": "git", "action": "push"})
        assert r[1] == "ok", r
        assert r[2]["pr"] == {"url": "https://gitlab.com/nhom/repo/-/merge_requests/new?merge_request%5Bsource_branch"
                                     "%5D=sua-loi", "kind": "MR", "label": "Tạo Merge Request"}
        r = await wa.handle({"op": "submit", "text": "/pr"})
        assert r[1] == "ok" and r[2]["pr"]["kind"] == "MR"
        wa.git._remember(await wa.git.repo.status())
        assert wa.git.info["pr"]["label"] == "Tạo Merge Request"

    asyncio.run(main())


def test_tui_push_shows_pr_button(env, project, monkeypatch, tmp_path):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from conftest import git_init
    git_init(project)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(project, "remote", "add", "origin", "git@github.com:chu/repo.git")
    git(project, "config", f"url.{remote}.pushInsteadOf", "git@github.com:chu/repo.git")
    git(project, "checkout", "-q", "-b", "tinh-nang")

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        opened: list[str] = []
        app.open_url = lambda url, **_kw: opened.append(url)

        async def wait(cond, n=200):
            for _ in range(n):
                await pilot.pause(0.15)
                if cond():
                    return True
            return False

        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            app.run_command("/git")
            btn = app.query_one("#git-pr")
            assert await wait(lambda: app.git_status is not None)
            assert not btn.display
            app.run_command("/pr")  # chưa push: báo, không mở gì
            await pilot.pause(0.2)
            assert not opened
            app.run_command("/push")
            assert await wait(lambda: btn.display)
            assert str(btn.label) == "🔗 PR"
            msgs = [n.message for n in app._notifications]
            assert any("Tạo Pull Request: https://github.com/chu/repo/compare/tinh-nang?expand=1" in m for m in msgs)
            btn.press()
            await pilot.pause(0.2)
            app.run_command("/pr")
            await pilot.pause(0.2)
            assert opened == ["https://github.com/chu/repo/compare/tinh-nang?expand=1"] * 2

    asyncio.run(main())
