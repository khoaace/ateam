"""Quản lý git (ateam/gitops.py, tab 🌿 Git): bóc output, thao tác trên repo thật trong thư mục tạm, TUI."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from conftest import git_init

from ateam import gitops
from ateam.prompts import extract_commit_message


def git(path: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True).stdout


def test_parse_status_porcelain_v2():
    text = "\0".join([
        "# branch.oid 1234567890abcdef",
        "# branch.head feature/x",
        "# branch.upstream origin/feature/x",
        "# branch.ab +2 -1",
        "# stash 3",
        "1 M. N... 100644 100644 100644 aaa bbb staged.py",
        "1 .M N... 100644 100644 100644 aaa bbb dir/có dấu cách.txt",
        "1 MM N... 100644 100644 100644 aaa bbb both.py",
        "2 R. N... 100644 100644 100644 aaa bbb R100 new name.py",
        "old name.py",
        "u UU N... 100644 100644 100644 100644 a b c conflict.txt",
        "? mới.txt",
        "",
    ])
    st = gitops.parse_status(text)
    assert (st.branch, st.oid[:4], st.upstream, st.ahead, st.behind, st.stashes) == \
        ("feature/x", "1234", "origin/feature/x", 2, 1, 3)
    assert [f.path for f in st.staged] == ["staged.py", "both.py", "new name.py"]
    assert [f.path for f in st.unstaged] == ["dir/có dấu cách.txt", "both.py"]
    assert [f.path for f in st.untracked] == ["mới.txt"]
    assert [f.path for f in st.conflicts] == ["conflict.txt"]
    ren = next(f for f in st.files if f.kind == "2")
    assert ren.orig == "old name.py"
    assert "↑2 ↓1" in gitops.summary_line(st) and "1 xung đột" in gitops.summary_line(st)

    fresh = gitops.parse_status("# branch.oid (initial)\0# branch.head main\0")
    assert fresh.oid == "" and fresh.branch == "main" and fresh.clean and not fresh.detached
    detached = gitops.parse_status("# branch.oid abc\0# branch.head (detached)\0")
    assert detached.detached


def test_branch_names_and_commit_message_parsing():
    for ok in ("main", "feature/dang-nhap", "fix-1.2", "khoa/tính-năng"):
        assert gitops.valid_branch_name(ok), ok
    for bad in ("", "-x", "a..b", "a b", "x.lock", "a/", "a~1", "a:b", "@{x}", "/a"):
        assert not gitops.valid_branch_name(bad), bad
    out = "Đang đọc diff\nSUMMARY:\n```\nThêm đăng nhập\n\nVì người dùng cần.\n```"
    assert extract_commit_message(out) == "Thêm đăng nhập\n\nVì người dùng cần."
    assert extract_commit_message('SUMMARY: "fix: sửa lỗi"') == "fix: sửa lỗi"
    assert extract_commit_message("không có gì") == ""


def test_gitrepo_operations(tmp_path, monkeypatch):
    # như máy CI: không có git identity — commit/merge/stash vẫn phải chạy (cờ -c user.* dự phòng)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repo = tmp_path / "r"
    repo.mkdir()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)

    async def main():
        g = gitops.GitRepo(repo)
        assert not (await g.status()).is_repo
        assert (await g.init())[0]
        st = await g.status()
        assert st.is_repo and st.oid == ""
        (repo / "a.txt").write_text("a\n")
        assert (await g.commit("x"))[1].startswith("Chưa stage")
        ok, msg = await g.commit("Khởi tạo", all_changes=True)  # /commit khi chưa stage gì
        assert ok, msg
        git(repo, "branch", "-M", "main")

        # stage / unstage / bỏ thay đổi
        (repo / "a.txt").write_text("a\nb\n")
        (repo / "mới.txt").write_text("x\n")
        assert (await g.stage(["a.txt"]))[0]
        st = await g.status()
        assert [f.path for f in st.staged] == ["a.txt"] and [f.path for f in st.untracked] == ["mới.txt"]
        ds = await g.changes_diffset(staged=True)
        assert [(f.status, f.path, f.added) for f in ds.files] == [("M", "a.txt", 1)]
        ds = await g.changes_diffset(staged=False)
        assert [(f.status, f.path) for f in ds.files] == [("A", "mới.txt")]
        assert (await g.unstage())[0]
        assert not (await g.status()).staged
        assert (await g.discard(["a.txt", "mới.txt"]))[0]
        assert (await g.status()).clean and not (repo / "mới.txt").exists()

        # push lần đầu tạo upstream; ahead/behind
        assert "chưa có remote" in (await g.push())[1]
        git(repo, "remote", "add", "origin", str(remote))
        ok, msg = await g.push()
        assert ok, msg
        st = await g.status()
        assert st.upstream == "origin/main" and st.ahead == 0
        (repo / "a.txt").write_text("a\nc\n")
        assert (await g.commit("Thêm c", all_changes=True))[0]
        assert (await g.status()).ahead == 1
        log = await g.log()
        assert [c.subject for c in log] == ["Thêm c", "Khởi tạo"]
        ds = await g.commit_diffset(log[-1])  # commit đầu tiên: so với cây rỗng
        assert [f.status for f in ds.files] == ["A"]

        # undo commit (chưa push) rồi commit lại; amend
        assert (await g.reset_soft())[0]
        assert [f.path for f in (await g.status()).staged] == ["a.txt"]
        assert (await g.commit("Thêm c (2)"))[0]
        assert (await g.commit("Thêm c — sửa", amend=True))[0]
        assert (await g.last_message()) == "Thêm c — sửa"
        assert (await g.push())[0]
        assert "đã push" in (await g.reset_soft())[1]

        # remote có commit mới: pull fast-forward
        other = tmp_path / "other"
        subprocess.run(["git", "clone", "-q", "-b", "main", str(remote), str(other)], check=True)
        (other / "o.txt").write_text("o\n")
        git(other, "add", ".")
        git(other, "-c", "user.name=o", "-c", "user.email=o@o", "commit", "-qm", "Từ máy khác")
        git(other, "push", "-q")
        assert (await g.fetch())[0]
        assert (await g.status()).behind == 1
        ok, msg = await g.pull()
        assert ok and (repo / "o.txt").exists(), msg

        # nhánh: tạo, đổi tên, merge, xoá; tên sai bị chặn
        assert not (await g.create_branch("a..b"))[0]
        assert (await g.create_branch("tinh-nang"))[0]
        (repo / "f.txt").write_text("f\n")
        assert (await g.commit("Tính năng", all_changes=True))[0]
        assert (await g.rename_branch("tinh-nang", "feature/x"))[0]
        assert (await g.checkout("main"))[0]
        assert "chưa merge" in (await g.delete_branch("feature/x"))[1]
        assert (await g.merge("feature/x"))[0]
        assert (await g.delete_branch("feature/x"))[0]
        names = [b.name for b in await g.branches()]
        assert "main" in names and "origin/main" in names and "feature/x" not in names

        # nhánh remote → tạo nhánh local theo dõi
        git(other, "checkout", "-qb", "remote-only")
        git(other, "push", "-q", "-u", "origin", "remote-only")
        await g.fetch()
        ok, msg = await g.checkout("origin/remote-only")
        assert ok and (await g.status()).branch == "remote-only", msg
        await g.checkout("main")

        # xung đột merge → trạng thái "merge", huỷ được
        assert (await g.create_branch("xd"))[0]
        (repo / "a.txt").write_text("nhánh xd\n")
        await g.commit("xd", all_changes=True)
        await g.checkout("main")
        (repo / "a.txt").write_text("nhánh main\n")
        await g.commit("main", all_changes=True)
        ok, msg = await g.merge("xd")
        st = await g.status()
        assert not ok and "xung đột" in msg and st.state == "merge" and [f.path for f in st.conflicts] == ["a.txt"]
        assert "xung đột" in (await g.commit("x"))[1]
        assert (await g.abort())[0]
        assert (await g.status()).state == ""

        # stash: cất (kể cả file mới), lấy lại, xoá
        (repo / "a.txt").write_text("đang sửa\n")
        (repo / "tmp.txt").write_text("t\n")
        assert (await g.stash_push("tạm"))[0]
        st = await g.status()
        assert st.clean and st.stashes == 1
        assert "tạm" in (await g.stashes())[0].subject
        assert (await g.stash_apply(pop=False))[0]
        assert (repo / "tmp.txt").exists() and (await g.status()).stashes == 1
        assert (await g.stash_drop("stash@{0}"))[0]
        assert (await g.status()).stashes == 0

        # revert
        await g.stage_all()
        await g.commit("Sẽ bị revert")
        head = (await g.log(1))[0]
        assert (await g.revert(head.sha))[0]
        assert (await g.log(1))[0].subject.startswith("Revert")

    asyncio.run(main())


def test_tui_git_tab(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    (project / "base.txt").write_text("base\nsửa\n")
    (project / "mới.txt").write_text("x\n")

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import ConfirmScreen, DiffScreen, GitBranchScreen, GitStashScreen, TeamApp

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
            assert await wait(lambda: app.git_status and len(app.git_status.files) == 2)
            assert app.query_one("#tabs").active == "tab-git"
            files = app.query_one("#git-files")
            files.focus()
            assert app.git_selected() == ("w", "base.txt")
            await pilot.press("space")  # stage base.txt
            assert await wait(lambda: [f.path for f in app.git_status.staged] == ["base.txt"])
            assert app.git_selected() == ("s", "base.txt")  # con trỏ đi theo file
            await pilot.press("enter")  # xem diff file đã stage
            assert await wait(lambda: isinstance(app.screen, DiffScreen))
            assert [f.path for f in app.screen.ds.files] == ["base.txt"]
            await pilot.press("escape")
            await pilot.pause(0.2)

            # x trên file chưa theo dõi: hỏi lại, n = giữ nguyên
            files.focus()
            await pilot.pause(0.1)
            await pilot.press("down")
            assert app.git_selected() == ("w", "mới.txt"), app.focused
            await pilot.press("x")
            assert await wait(lambda: isinstance(app.screen, ConfirmScreen))
            await pilot.press("n")
            await pilot.pause(0.2)
            assert (project / "mới.txt").exists()

            # ✨ trưởng nhóm (claude giả lập) viết message, Enter để commit — chỉ file đã stage
            app.run_command("/commit")
            box = app.query_one("#git-msg")
            assert await wait(lambda: box.value == "Thêm file mới cho bản demo", 80)
            assert "claude giả lập" in app._git_body
            box.focus()
            await pilot.press("enter")
            assert await wait(lambda: app.git_commits and app.git_commits[0].subject == "Thêm file mới cho bản demo")
            body = git(project, "log", "-1", "--format=%B")
            assert "claude giả lập" in body and box.value == ""
            assert [f.path for f in app.git_status.files] == ["mới.txt"]

            # nhánh: tạo bằng lệnh, chuyển lại bằng popup
            app.run_command("/branch feature/demo")
            assert await wait(lambda: app.git_status.branch == "feature/demo")
            app.git_button("git-branches")
            assert await wait(lambda: isinstance(app.screen, GitBranchScreen))
            names = [b.name for b in app.screen.branches]
            assert set(names) == {"feature/demo", "master"} or set(names) == {"feature/demo", "main"}
            ol = app.screen.query_one("#gb-list")
            ol.highlighted = next(i for i, b in enumerate(app.screen.branches) if not b.current)
            await pilot.press("enter")
            assert await wait(lambda: app.git_status.branch in ("master", "main"))

            # stash qua popup rồi /stash pop
            app.git_button("git-stash")
            assert await wait(lambda: isinstance(app.screen, GitStashScreen))
            await pilot.click("#gs-push")
            assert await wait(lambda: app.git_status.clean and app.git_status.stashes == 1)
            app.run_command("/stash pop")
            assert await wait(lambda: app.git_status.stashes == 0 and not app.git_status.clean)

            # đổi nhánh bị chặn khi agent đang chạy
            app.orch.runs[999] = None
            app.run_command("/checkout feature/demo")
            await pilot.pause(0.3)
            assert app.git_status.branch in ("master", "main")
            app.orch.runs.pop(999)

            # lịch sử: Enter xem diff commit
            log = app.query_one("#git-log")
            log.focus()
            log.highlighted = 0
            await pilot.press("enter")
            assert await wait(lambda: isinstance(app.screen, DiffScreen))
            assert app.screen.ds.head == app.git_commits[0].sha
            await pilot.press("escape")
            await pilot.press("ctrl+q")

    asyncio.run(main())
