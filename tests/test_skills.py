"""🧩 Skills (ateam/skills.py): đọc SKILL.md, gom skill của mọi CLI + dự án + thư viện ateam, bật/tắt theo dự án,
`$tên`, khối gửi kèm prompt, thư viện (tạo / sửa / nhập / xoá), cài từ repo git."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from ateam import config, skills


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GLOBAL_DIR", tmp_path / "xdg" / "ateam")
    monkeypatch.setenv("ATEAM_SKILLS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ATEAM_TRASH_DIR", str(tmp_path / "trash"))
    return tmp_path


def mk(base: Path, name: str, desc: str = "Làm X. Dùng khi cần X.", body: str = "# Bước\n1. làm", meta: str = ""):
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n{meta}---\n\n{body}\n", encoding="utf-8")
    return d


def test_parse_frontmatter_variants():
    meta, body = skills.parse("﻿---\r\nname: \"pdf\"\r\ndescription: 'It''s ok' # c\r\n---\r\nThân\r\n")
    assert meta == {"name": "pdf", "description": "It's ok"} and body == "Thân\n"
    meta, _ = skills.parse("---\nname: a\ndescription: >\n  dòng một\n  dòng hai\n\n  đoạn mới\nlicense: MIT\n---\nx")
    assert meta["description"] == "dòng một dòng hai\nđoạn mới" and meta["license"] == "MIT"
    meta, _ = skills.parse("---\nname: a\ndescription: |\n  giữ\n  dòng\nmetadata:\n  author: k\n  version: \"1.0\"\n---\n")
    assert meta["description"] == "giữ\ndòng" and meta["metadata"] == {"author": "k", "version": "1.0"}
    meta, _ = skills.parse("---\nname: a\ndescription: chuỗi dài\n  viết tiếp\n---\n")
    assert meta["description"] == "chuỗi dài viết tiếp"
    assert skills.parse("# không có frontmatter") == ({}, "# không có frontmatter")
    meta, _ = skills.parse('---\ndescription: "có \\"nháy\\" và \\\\"\n---\n')
    assert meta["description"] == 'có "nháy" và \\'


def test_name_rules():
    assert not skills.name_problem("pdf-tools-2")
    for bad in ("", "PDF", "-a", "a-", "a--b", "a_b", "a" * 65, "tên"):
        assert skills.name_problem(bad), bad


def test_scan_sources_precedence_and_problems(lib, project):
    home = lib / "home"
    mk(home / ".claude/skills", "dup", desc="bản claude")
    mk(home / ".gemini/config/skills", "front", desc="UI")
    (home / ".gemini/antigravity").mkdir(parents=True)
    (home / ".gemini/antigravity/skills").symlink_to(home / ".gemini/config/skills")
    mk(home / ".claude/skills/synced/abc", "pdf", desc="PDF")  # claude.ai đồng bộ: lồng sâu hơn
    mk(home / ".codex/skills/.system", "hidden")  # skill hệ thống của codex: bỏ qua
    (home / ".claude/skills/brainstorm.md").write_text("---\nname: brainstorm\ndescription: nghĩ\n---\nx")
    (home / ".claude/skills/README.md").write_text("# chỉ là readme")
    mk(skills.library(), "dup", desc="bản thư viện")
    mk(project / ".agents/skills", "proj", desc="của dự án")
    mk(home / ".config/opencode/skills", "wrong-dir").joinpath("SKILL.md").write_text(
        "---\nname: other\n---\nx")
    items = {s.name: s for s in skills.scan(project)}
    assert set(items) == {"dup", "front", "pdf", "brainstorm", "proj", "other"}
    assert items["dup"].kind == "library" and items["dup"].others == ["~/.claude/skills/dup/SKILL.md"]
    assert items["front"].readers == "agy" or items["front"].source.endswith("antigravity/skills")
    assert items["proj"].kind == "project" and "codex" in items["proj"].readers
    assert items["brainstorm"].flat and items["brainstorm"].problems
    assert any("khác tên thư mục" in p for p in items["other"].problems)
    assert any("description" in p for p in items["other"].problems)
    assert items["pdf"].kind == "cli" and not items["pdf"].problems


def test_enabled_defaults_and_toggle(lib, project):
    home = lib / "home"
    mk(home / ".claude/skills", "cli-one")
    mk(skills.library(), "lib-one")
    mk(project / ".claude/skills", "proj-one")
    names = lambda: sorted(s.name for s in skills.enabled(project))  # noqa: E731
    assert names() == ["lib-one", "proj-one"]  # skill của CLI mặc định tắt
    skills.set_on(project, "cli-one", True)
    skills.set_on(project, "lib-one", False)
    assert names() == ["cli-one", "proj-one"]
    other = lib / "other"
    other.mkdir()
    assert sorted(s.name for s in skills.enabled(other)) == ["lib-one"]  # theo từng dự án


def test_mentions_and_blocks(lib, project):
    mk(skills.library(), "tdd", desc="Viết test trước. " * 40, body="Red, green, refactor.")
    mk(skills.library(), "release", body="x" * (skills.BODY_MAX + 50))
    items = skills.scan(project)
    got = skills.mentioned("dùng $tdd, $PATH, ${HOME}, a$tdd, \\$tdd, $release. và $tdd", items)
    assert [s.name for s in got] == ["tdd", "release"]
    assert skills.mentioned("$tdd-x $tdd_x", items) == []
    idx = skills.index_block(items)
    assert "- release:" in idx and "- tdd:" in idx and '"skills"' in idx and "…" in idx
    assert skills.index_block([]) == "" and skills.body_block([]) == ""
    block = skills.body_block(skills.resolve(["tdd", "$release", "nope"], items))
    assert "=== SKILL: tdd" in block and "Red, green, refactor." in block and "truncated" in block
    assert block.endswith("---\n\n")


def test_library_create_update_import_delete(lib, project):
    assert "a-z" in skills.create("Bad Name", "d", "b")
    assert "description" in skills.create("ok", " ", "b")
    assert not skills.create("ok", "Làm   việc\nX", "Thân")
    text = (skills.library() / "ok/SKILL.md").read_text()
    meta, body = skills.parse(text)
    assert meta == {"name": "ok", "description": "Làm việc X"} and body == "Thân\n"
    assert "Đã có" in skills.create("ok", "d", "b")
    assert "phải là 'ok'" in skills.update("ok", "---\nname: khac\ndescription: d\n---\nb")
    assert not skills.update("ok", "---\nname: ok\ndescription: mới\nlicense: MIT\n---\nthân mới")
    assert skills.find(skills.scan(project), "ok").description == "mới"
    home = lib / "home"
    (home / ".claude/skills").mkdir(parents=True)
    (home / ".claude/skills/brainstorm.md").write_text("---\nname: brainstorm\ndescription: nghĩ\n---\nx")
    d = mk(home / ".codex/skills", "play")
    (d / "scripts").mkdir()
    (d / "scripts/run.sh").write_text("echo")
    items = skills.scan(project)
    assert not skills.import_skill(skills.find(items, "brainstorm"))
    assert not skills.import_skill(skills.find(items, "play"))
    assert (skills.library() / "brainstorm/SKILL.md").is_file()
    lib_play = skills.find(skills.scan(project), "play")
    assert lib_play.kind == "library" and lib_play.has_scripts() and "scripts/run.sh" in lib_play.files()
    assert not asyncio.run(skills.delete("ok"))
    assert not (skills.library() / "ok").exists() and (lib / "trash/ok/SKILL.md").is_file()


def test_parse_source():
    gh = "https://github.com/anthropics/skills.git"
    assert skills.parse_source("anthropics/skills") == (gh, "", "")
    assert skills.parse_source("https://github.com/anthropics/skills") == (gh, "", "")
    assert skills.parse_source("https://github.com/anthropics/skills/tree/main/document-skills/pdf") == (
        gh, "main", "document-skills/pdf")
    assert skills.parse_source("git@host:x/y.git") == ("git@host:x/y.git", "", "")


def test_fetch_and_install_from_local_repo(lib):
    src = lib / "src"
    mk(src / "skills", "alpha", body="A")
    d = mk(src / "skills", "beta")
    (d / "scripts").mkdir()
    (d / "scripts/x.py").write_text("print(1)")
    mk(src, "Bad_Name")
    for a in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "s"]):
        subprocess.run(["git", *a], cwd=src, check=True, capture_output=True)
    mk(skills.library(), "alpha", body="cũ")

    async def main():
        tok, found, err = await skills.fetch(src.as_uri())
        assert not err, err
        by = {x["name"]: x for x in found}
        assert set(by) == {"alpha", "beta", "Bad_Name"}
        assert by["alpha"]["exists"] and by["beta"]["scripts"] and not by["Bad_Name"]["usable"]
        done, errs = await skills.install(tok, ["alpha", "beta", "Bad_Name"])
        assert done == ["beta"] and len(errs) == 2
        assert tok not in skills.PENDING
        tok2, _, _ = await skills.fetch(src.as_uri())
        done, errs = await skills.install(tok2, ["alpha"], overwrite=True)
        assert done == ["alpha"] and not errs
        assert (await skills.install(tok2, ["alpha"]))[1]  # phiên đã dùng xong
        _, found, err = await skills.fetch((lib / "nope").as_uri())
        assert err and not found
    asyncio.run(main())
    assert (skills.library() / "alpha/SKILL.md").read_text().endswith("A\n")
    assert (skills.library() / "beta/scripts/x.py").is_file()
    assert '"commit"' in (skills.library() / "beta/.ateam-source.json").read_text()


# ------------------------------------------------------------------ gắn skill vào task (orchestrator)
def _orch(env, project, monkeypatch):
    import importlib
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(config)
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    return Orchestrator(project, config.load_config(project), DB(project / ".ateam/team.db"))


def _calls(log: Path) -> list[tuple[str, str]]:
    """(agent, cả dòng lệnh kèm prompt) của mỗi lần gọi CLI giả lập (ATEAM_FAKE_FULL_LOG)."""
    out = []
    for chunk in log.read_text(encoding="utf-8").split("<<")[1:]:
        name, _, rest = chunk.partition(">> ")
        out.append((name, rest))
    return out


def test_lead_attaches_skills_and_members_receive_them(env, project, monkeypatch, tmp_path):
    env["ATEAM_FAKE_PLAN_SKILLS"] = "tdd"
    env["ATEAM_FAKE_FULL_LOG"] = str(tmp_path / "full.log")
    o = _orch(env, project, monkeypatch)
    mk(skills.library(), "tdd", desc="Viết test trước khi sửa code.", body="Red, green, refactor.")
    mk(Path(env["ATEAM_SKILLS_HOME"]) / ".claude/skills", "off-skill", desc="Không gửi trưởng nhóm")

    async def main():
        await o.setup()
        o.auto_answer = True
        o.cfg.approve_plan = False
        gid = o.new_goal("tạo a.txt")
        await o.run_until_idle(interval=0.01)
        return o.db.tasks(goal_id=gid)
    ts = asyncio.run(main())
    code = next(t for t in ts if t.agent == "codex")
    assert code.skills == ["tdd"]  # "khong-co" không có trong danh mục → bỏ
    assert all(not t.skills for t in ts if t is not code)
    calls = _calls(tmp_path / "full.log")
    plan = next(c for n, c in calls if n == "claude" and "AVAILABLE SKILLS" in c)
    assert "- tdd: Viết test trước" in plan and "off-skill" not in plan  # skill của CLI mặc định tắt
    member = next(c for n, c in calls if n == "codex")
    assert member.index("=== SKILL: tdd") < member.index("YOUR TASK") and "Red, green, refactor." in member
    assert "🧩 skills: tdd" in (project / f".ateam/logs/t{code.id}.log").read_text()


def test_dollar_skill_in_goal_task_and_chat(env, project, monkeypatch, tmp_path):
    env["ATEAM_FAKE_FULL_LOG"] = str(tmp_path / "full.log")
    o = _orch(env, project, monkeypatch)
    mk(Path(env["ATEAM_SKILLS_HOME"]) / ".codex/skills", "release", desc="Phát hành", body="Bump version rồi push.")

    async def main():
        await o.setup()
        o.auto_answer = True
        o.cfg.approve_plan = False
        gid = o.new_goal("$release bản mới, không đụng $PATH")
        await o.run_until_idle(interval=0.01)
        ts = o.db.tasks(goal_id=gid)
        tid = o.add_task("grok", "$release ngay")
        c1 = o.chat("claude", "xin chào")
        await o.run_until_idle(interval=0.01)
        c2 = o.chat("claude", "giờ dùng $release nhé")
        await o.run_until_idle(interval=0.01)
        return ts, o.db.task(tid), o.db.task(c2)
    ts, task, chat2 = asyncio.run(main())
    # $tên trong mục tiêu: gắn cố định mọi task code từ kế hoạch (cả task review thêm vào); việc agent tự giao chéo
    # (<<<DELEGATE>>>) là phần riêng — không tự nhận
    assert ts and all(t.skills == ["release"] for t in ts if not t.source.startswith("delegate"))
    assert any(t.source == "review" and t.skills == ["release"] for t in ts)
    assert task.status == "done" and chat2.status == "done"
    calls = _calls(tmp_path / "full.log")
    plan = next(c for n, c in calls if n == "claude" and "Reply with ONLY a JSON array" in c)
    assert "SKILLS THE USER ASKED FOR" in plan and "Bump version rồi push." in plan
    assert "AVAILABLE SKILLS" not in plan  # skill của CLI đang tắt: chỉ $tên mới dùng
    grok = [c for n, c in calls if n == "grok"]
    assert any("=== SKILL: release" in c and "$release ngay" in c for c in grok)
    chats = [c for n, c in calls if n == "claude" and ("xin chào" in c or "giờ dùng" in c)]
    assert "=== SKILL" not in chats[0] and "--resume" in chats[1] and "=== SKILL: release" in chats[1]


def test_old_db_gets_skills_column(tmp_path):
    import sqlite3

    from ateam.db import DB
    p = tmp_path / "team.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id INTEGER, parent_id INTEGER,"
                " agent TEXT NOT NULL, title TEXT NOT NULL, prompt TEXT NOT NULL, status TEXT NOT NULL DEFAULT"
                " 'queued', depends_on TEXT NOT NULL DEFAULT '[]', depth INTEGER NOT NULL DEFAULT 0, source TEXT,"
                " result TEXT, error TEXT, branch TEXT, created REAL, started REAL, finished REAL)")
    con.execute("INSERT INTO tasks(agent, title, prompt) VALUES ('codex', 'cũ', 'p')")
    con.commit()
    con.close()
    db = DB(p)
    assert db.task(1).skills is None
    tid = db.add_task("codex", "mới", "p", skills=["tdd"])
    db.update_task(1, skills=["a", "b"])
    assert db.task(tid).skills == ["tdd"] and db.task(1).skills == ["a", "b"]
    db.update_task(1, skills=None)
    assert db.task(1).skills is None


# ------------------------------------------------------------------ trang 🧩 Skills (web)
def test_web_skill_ops(env, project, monkeypatch, tmp_path):
    pytest.importorskip("aiohttp")
    from test_web import _web_app
    env["ATEAM_TRASH_DIR"] = str(tmp_path / "trash")
    env["ATEAM_FAKE_FULL_LOG"] = str(tmp_path / "full.log")
    wa = _web_app(env, project, monkeypatch)
    home = Path(env["ATEAM_SKILLS_HOME"])
    mk(home / ".claude/skills", "cli-one", desc="Của claude")

    async def main():
        st = (await wa.handle({"op": "skills_list"}))[2]
        one = next(s for s in st["skills"] if s["name"] == "cli-one")
        assert not one["on"] and one["kind"] == "cli" and "claude" in one["readers"]
        st = (await wa.handle({"op": "skills", "action": "toggle", "name": "cli-one", "on": True}))[2]
        assert next(s for s in st["skills"] if s["name"] == "cli-one")["on"]
        r = await wa.handle({"op": "skills", "action": "create", "name": "Sai Ten", "description": "d", "body": "b"})
        assert r[1] == "warn"
        r = await wa.handle({"op": "skills", "action": "create", "name": "ship", "description": "Phát hành",
                             "body": "1. push"})
        assert r[1] == "ok" and any(s["name"] == "ship" and s["kind"] == "library" and s["on"] for s in r[2]["skills"])
        v = (await wa.handle({"op": "skill_view", "name": "ship"}))[2]["skill_view"]
        assert "1. push" in v["text"] and v["files"] == ["SKILL.md"]
        assert (await wa.handle({"op": "skills", "action": "update", "name": "ship",
                                 "text": v["text"].replace("1. push", "1. git push")}))[1] == "ok"
        assert (await wa.handle({"op": "skills", "action": "import", "name": "cli-one"}))[1] == "ok"
        assert (skills.library() / "cli-one/SKILL.md").is_file()
        assert (await wa.handle({"op": "skills", "action": "delete", "name": "ship"}))[1] == "ok"
        assert not (skills.library() / "ship").exists()
        r = await wa.handle({"op": "skill_ai", "description": "quy trình phát hành"})
        assert r[2]["skill_draft"] == {"name": "phat-hanh", "description":
                                       "Release a new version. Use when the user asks to publish.",
                                       "body": "# Release\n1. Bump the version\n2. Push"}
        assert (await wa.handle({"op": "skill_ai", "description": "  "}))[1] == "warn"
        gid = wa.orch.db.add_goal("deploy prod")
        wa.orch.db.add_task("codex", "Deploy", "npm run deploy", goal_id=gid, status="done")
        r = await wa.handle({"op": "skill_ai", "goal": gid, "focus": "chỉ deploy"})
        assert r[2]["skill_draft"]["name"] == "tu-muc-tieu"
        assert (await wa.handle({"op": "submit", "text": "/skills"}))[2] == {"open": {"view": "skills"}}
        wa.remote.readonly = True
        assert (await wa.handle({"op": "skills_list"}))[2]["skills"]
        assert "readonly" in (await wa.handle({"op": "skills", "action": "toggle", "name": "x", "on": True}))[0]
    asyncio.run(main())
    lead = (tmp_path / "full.log").read_text()
    assert "TASKS (read a full log" in lead and "npm run deploy" in lead and "Focus from the user: chỉ deploy" in lead


def test_extract_skill():
    from ateam import prompts as P
    out = ("mẫu <<<SKILL>>>\n---\nname: ...\n<<<END>>>\nĐang viết\n<<<SKILL>>>\n```md\n---\nname: a\ndescription: d\n"
           "---\nNói <<<END>>> trong thân\n```\n<<<END>>>\n")
    assert P.extract_skill(out) == "---\nname: a\ndescription: d\n---\nNói <<<END>>> trong thân"
    assert P.extract_skill("không có") is None
    assert P.extract_skill("<<<SKILL>>>\n---\nname: ...\n---\n<<<END>>>") is None


def test_tui_skills_screen(env, project, monkeypatch):
    import importlib

    from conftest import wait_for
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(config)
    from ateam import tui
    from ateam.db import DB
    config.ensure_global_config()
    mk(Path(env["ATEAM_SKILLS_HOME"]) / ".claude/skills", "cli-one", desc="Của claude", body="# Hướng dẫn")
    app = tui.TeamApp(project, config.load_config(project), DB(project / ".ateam/team.db"))

    async def main():
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.pause(0.2)
            app.run_command("/skills")
            assert await wait_for(pilot, lambda: isinstance(app.screen, tui.SkillsScreen))
            opts = [str(o.prompt) for o in app.screen.query_one("#skills-list").options]
            assert any("~/.claude/skills" in x for x in opts) and any("cli-one" in x for x in opts)
            await pilot.press("space")
            assert [s.name for s in skills.enabled(project)] == ["cli-one"]
            await pilot.press("enter")
            assert await wait_for(pilot, lambda: isinstance(app.screen, tui.SkillViewScreen))
    asyncio.run(main())
