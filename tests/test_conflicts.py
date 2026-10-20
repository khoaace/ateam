"""Giải quyết xung đột git (tab 🌿 Git): bóc khối <<<<<<<, chọn từng khối / cả file, đánh dấu xong, tiếp tục
merge/rebase — trên repo thật trong thư mục tạm; TUI và web."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from conftest import git_init

from ateam import gitops


def git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=path,
                          capture_output=True, text=True).stdout


def make_conflict(path: Path, files=("a.txt",), rebase: bool = False, init: bool = True) -> None:
    """Nhánh main và feature cùng sửa dòng 2 của mỗi file → merge (hoặc rebase) bị xung đột."""
    if init:
        git_init(path)
    git(path, "branch", "-M", "main")
    for f in files:
        (path / f).write_text("một\nhai\nba\n")
    git(path, "add", ".")
    git(path, "commit", "-qm", "gốc")
    git(path, "checkout", "-qb", "feature")
    for f in files:
        (path / f).write_text("một\nhai-feature\nba\n")
    git(path, "commit", "-qam", "feature")
    git(path, "checkout", "-q", "main")
    for f in files:
        (path / f).write_text("một\nhai-main\nba\n")
    git(path, "commit", "-qam", "main")
    if rebase:
        git(path, "checkout", "-q", "feature")
        git(path, "rebase", "main")
    else:
        git(path, "merge", "feature")


def test_parse_and_resolve_text():
    text = ("x\n<<<<<<< HEAD\nours1\nours2\n||||||| base\nold\n=======\ntheirs\n>>>>>>> feature\ny\n"
            "<<<<<<< HEAD\na\n=======\nb\n>>>>>>> feature\n")
    bs = gitops.parse_conflicts(text)
    assert len(bs) == 2 and bs[0].ours == ["ours1\n", "ours2\n"] and bs[0].base == ["old\n"]
    assert bs[0].theirs == ["theirs\n"] and (bs[0].ours_label, bs[0].theirs_label) == ("HEAD", "feature")
    assert gitops.resolve_conflict_text(text, 0, "theirs").startswith("x\ntheirs\ny\n<<<<<<<")
    assert gitops.resolve_conflict_text(text, 1, "both").endswith("y\na\nb\n")
    assert gitops.resolve_conflict_text(text, 1, "ours").count("<<<<<<<") == 1
    assert gitops.parse_conflicts("<<<<<<< không đóng\nx\n") == []


def test_resolve_blocks_and_continue_merge(tmp_path):
    make_conflict(tmp_path, ("a.txt", "b.txt"))
    g = gitops.GitRepo(tmp_path)

    async def main():
        st = await g.status()
        assert st.state == "merge" and {f.path for f in st.conflicts} == {"a.txt", "b.txt"}
        info = await g.conflict_info("a.txt")
        b = info["blocks"][0]
        assert (b["ours"], b["theirs"], b["before"], b["after"]) == ("hai-main\n", "hai-feature\n", ["một"], ["ba"])
        ok, msg = await g.continue_op()
        assert not ok and "xung đột" in msg
        ok, _ = await g.resolve_block("a.txt", 0, "both")  # hết khối → tự stage
        assert ok and (tmp_path / "a.txt").read_text() == "một\nhai-main\nhai-feature\nba\n"
        (tmp_path / "b.txt").write_text("<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> f\n")
        ok, msg = await g.mark_resolved(["b.txt"])
        assert not ok and "<<<<<<<" in msg
        ok, _ = await g.take_side(["b.txt"], "theirs")
        assert ok and (tmp_path / "b.txt").read_text() == "một\nhai-feature\nba\n"
        assert not (await g.status()).conflicts
        ok, msg = await g.continue_op()
        assert ok and (await g.status()).state == ""
    asyncio.run(main())
    assert "Merge branch 'feature'" in git(tmp_path, "log", "-1", "--format=%s")


def test_continue_rebase_and_deleted_side(tmp_path):
    make_conflict(tmp_path, rebase=True)
    g = gitops.GitRepo(tmp_path)

    async def main():
        assert (await g.status()).state == "rebase"
        ok, _ = await g.take_side(["a.txt"], "ours")  # khi rebase, "hiện tại" là nhánh đích (main)
        assert ok and (tmp_path / "a.txt").read_text() == "một\nhai-main\nba\n"
        ok, msg = await g.continue_op()
        assert ok and (await g.status()).state == "", msg
    asyncio.run(main())

    d = tmp_path / "del"
    d.mkdir()
    git_init(d)
    (d / "x.txt").write_text("1\n")
    git(d, "add", ".")
    git(d, "commit", "-qm", "x")
    git(d, "checkout", "-qb", "f")
    (d / "x.txt").unlink()
    git(d, "commit", "-qam", "xoá")
    git(d, "checkout", "-q", "-")
    (d / "x.txt").write_text("2\n")
    git(d, "commit", "-qam", "sửa")
    git(d, "merge", "f")
    g = gitops.GitRepo(d)

    async def deleted():
        info = await g.conflict_info("x.txt")
        assert info["theirs_deleted"] and not info["ours_deleted"] and not info["blocks"]
        ok, _ = await g.take_side(["x.txt"], "theirs")  # bên đến đã xoá file → xoá theo
        assert ok and not (d / "x.txt").exists() and not (await g.status()).conflicts
    asyncio.run(deleted())


def test_web_conflict_ops(env, project, monkeypatch, tmp_path):
    import pytest
    pytest.importorskip("aiohttp")
    from test_web import _web_app
    wa = _web_app(env, project, monkeypatch)
    make_conflict(project, ("a.txt", "b.txt"), init=False)
    full = tmp_path / "full.log"
    monkeypatch.setenv("ATEAM_FAKE_FULL_LOG", str(full))

    async def main():
        info = await wa.git.repo.conflict_info("a.txt")
        assert info["conflicted"] and len(info["blocks"]) == 1
        r = await wa.handle({"op": "git", "action": "resolve_block", "path": "a.txt", "index": 0, "choice": "ours"})
        assert r[1] == "ok" and [f.path for f in (await wa.git.repo.status()).conflicts] == ["b.txt"]
        r = await wa.handle({"op": "git", "action": "continue"})
        assert r[1] == "warn"  # còn b.txt
        r = await wa.handle({"op": "git", "action": "ai_resolve"})
        assert r[1] == "ok" and "1 file" in r[0]
        await wa.orch.run_until_idle()
        sent = full.read_text()
        assert "Resolve the git merge conflicts" in sent and "- b.txt" in sent and "- a.txt" not in sent
        r = await wa.handle({"op": "git", "action": "take_theirs", "path": "b.txt"})
        assert r[1] == "ok"
        r = await wa.handle({"op": "git", "action": "continue"})
        assert r[1] == "ok" and (await wa.git.repo.status()).state == ""
    asyncio.run(main())


def test_tui_conflict_screen(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    make_conflict(project, ("a.txt", "b.txt"))
    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import ConflictScreen, TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))

        async def wait(cond, n=40):
            for _ in range(n):
                await pilot.pause(0.15)
                if cond():
                    return True
            return False

        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            app.run_command("/git")
            assert await wait(lambda: app.git_status and len(app.git_status.conflicts) == 2)
            assert app.query_one("#git-cf-row").display and not app.query_one("#git-continue").display
            app.query_one("#git-files").focus()
            assert app.git_selected() == ("c", "a.txt")
            await pilot.press("enter")
            assert await wait(lambda: isinstance(app.screen, ConflictScreen) and app.screen.info.get("blocks"))
            await pilot.press("b")  # giữ cả hai → hết khối → tự stage, màn hình tự đóng
            assert await wait(lambda: not isinstance(app.screen, ConflictScreen))
            assert (project / "a.txt").read_text() == "một\nhai-main\nhai-feature\nba\n"
            await pilot.press("r")  # b.txt
            assert await wait(lambda: isinstance(app.screen, ConflictScreen) and app.screen.path == "b.txt")
            await pilot.press("T")
            assert await wait(lambda: not isinstance(app.screen, ConflictScreen))
            assert await wait(lambda: app.git_status and not app.git_status.conflicts
                              and app.query_one("#git-continue").display)
            app.query_one("#git-continue").press()
            assert await wait(lambda: app.git_status.state == "")
            await pilot.press("ctrl+q")
    asyncio.run(main())
