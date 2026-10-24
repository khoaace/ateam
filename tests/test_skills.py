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
