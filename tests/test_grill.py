"""/grill ("grill me"): trưởng nhóm phỏng vấn người dùng từng câu trước khi lập kế hoạch."""

from __future__ import annotations

import asyncio
import sqlite3

from conftest import git_init


def test_grill_prompt_goal_text_and_db_migration(tmp_path):
    from ateam.config import Config
    from ateam.db import DB
    from ateam import prompts as P

    # DB cũ chưa có cột grill vẫn mở được
    path = tmp_path / "old.db"
    c = sqlite3.connect(str(path))
    c.execute("CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL,"
              " status TEXT NOT NULL DEFAULT 'planning', round INTEGER NOT NULL DEFAULT 1,"
              " summary TEXT, created REAL, workflow TEXT, followups TEXT)")
    c.execute("INSERT INTO goals(text, status) VALUES ('làm A', 'done')")
    c.commit()
    c.close()
    db = DB(path)
    g = db.goal(1)
    assert g.grill is None and g.spec == "" and g.base_text() == "làm A"
    db.set_grill(1, {"qa": [{"q": "Ai dùng?", "a": "Khách"}], "spec": "- cho khách"})
    db.add_followup(1, "thêm B")
    g = db.goal(1)
    assert "CLARIFIED REQUIREMENTS" in g.base_text() and "- cho khách" in g.base_text()
    assert g.full_text().startswith(g.base_text()) and g.full_text().endswith("FOLLOW-UP 1: thêm B")

    prompt = P.grill_prompt(Config(), "Thêm đăng nhập", [{"q": "Ai dùng?", "a": "Khách"}], "/p", "",
                            finish=False, max_questions=15)
    assert "Q1: Ai dùng?\nA1: Khách" in prompt and "1 of at most 15" in prompt
    assert "Reply with ONLY a JSON array" not in prompt  # agent giả lập không nhầm sang lập kế hoạch
    assert "STOP the interview" in P.grill_prompt(Config(), "x", [], "/p", "", finish=True, max_questions=15)


def test_tui_grill_flow(env, project, monkeypatch, tmp_path):
    full = tmp_path / "full.log"
    env = dict(env, ATEAM_FAKE_FULL_LOG=str(full))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import GrillBar, TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))

        async def wait(cond, n=60):
            for _ in range(n):
                await pilot.pause(0.15)
                if cond():
                    return True
            return False

        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            bar = app.query_one("#grill", GrillBar)
            box = app.query_one("#cmd")
            app.run_command("/grill Thêm trang đăng nhập")
            assert await wait(lambda: bar.question is not None)
            gid = bar.goal_id
            assert bar.display and bar.question["q"] == "Câu hỏi số 1?"
            assert bar.question["options"] == ["Phương án A", "Phương án B"]
            assert "Trả lời câu hỏi" in box.placeholder
            assert app.db.goal(gid).status == "grilling"

            # gõ số = chọn phương án; câu gõ vào ô nhập là câu trả lời, không thành mục tiêu mới
            box.focus()
            box.value = "2"
            await pilot.press("enter")
            assert await wait(lambda: bar.question is not None and bar.question["q"] == "Câu hỏi số 2?")
            assert app.db.goal(gid).grill["qa"][0]["a"] == "Phương án B"
            assert len(app.db.goals()) == 1
            box.value = "Chỉ đăng nhập bằng email"
            await pilot.press("enter")
            # đủ 2 câu: claude giả lập chốt đặc tả -> lập kế hoạch -> chờ duyệt
            assert await wait(lambda: app.db.goal(gid).status == "awaiting", 80)
            g = app.db.goal(gid)
            assert g.spec.startswith("- Đăng nhập bằng email") and "Đã trả lời 2 câu" in g.spec
            assert [x["a"] for x in g.grill["qa"]] == ["Phương án B", "Chỉ đăng nhập bằng email"]
            assert not bar.display and "Trả lời câu hỏi" not in box.placeholder
            plan_prompts = [ln for ln in full.read_text().split("<<claude>>") if "JSON array" in ln]
            assert plan_prompts and "CLARIFIED REQUIREMENTS" in plan_prompts[-1]
            assert "Đã trả lời 2 câu" in plan_prompts[-1]
            app.run_command(f"/drop {gid}")

            # /grill xong sau 1 câu: chốt ngay với những gì đã có (bấm phương án = trả lời)
            app.run_command("/grill Thêm trang hồ sơ")
            assert await wait(lambda: bar.question is not None and bar.goal_id != gid)
            gid2 = bar.goal_id
            app.action_grill_pick(1)
            assert await wait(lambda: bar.question is not None and bar.question["q"] == "Câu hỏi số 2?")
            app.run_command("/grill xong")
            assert await wait(lambda: app.db.goal(gid2).status == "awaiting", 80)
            assert "Đã trả lời 1 câu" in app.db.goal(gid2).spec
            app.run_command(f"/drop {gid2}")

            # bỏ giữa chừng
            app.run_command("/grill Thêm trang cài đặt")
            assert await wait(lambda: bar.question is not None and bar.goal_id not in (gid, gid2))
            gid3 = bar.goal_id
            await pilot.click("#grill-cancel")
            assert await wait(lambda: app.db.goal(gid3).status == "cancelled")
            assert await wait(lambda: not bar.display)
            await pilot.press("ctrl+q")

    asyncio.run(main())
