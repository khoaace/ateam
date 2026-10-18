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
            # bấm nút trực tiếp (Button.press) chứ không theo toạ độ: khung vừa vẽ lại, máy CI chậm thì
            # cú bấm chuột có thể rơi vào chỗ nút chưa kịp hiện
            app.query_one("#grill-cancel").press()
            assert await wait(lambda: app.db.goal(gid3).status == "cancelled")
            assert await wait(lambda: not bar.display)
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_grill_hanging_indent():
    from ateam.tui import hang
    out = hang("một hai ba bốn năm sáu bảy tám chín mười", 30, 6, first=6)
    lines = out.split("\n")
    assert len(lines) == 2 and lines[1].startswith(" " * 6) and not lines[0].startswith(" ")
    assert all(len(ln) <= 30 - (0 if i else 6) for i, ln in enumerate(lines))
    assert hang("ngắn", 80, 6) == "ngắn"


def test_plan_asks_user_when_unclear(env, project, monkeypatch, tmp_path):
    """Lập kế hoạch mà có điểm quan trọng chưa rõ: trưởng nhóm hỏi lại (như /grill) rồi mới lập kế hoạch."""
    import importlib

    full = tmp_path / "full.log"
    for k, v in dict(env, ATEAM_FAKE_FULL_LOG=str(full)).items():
        monkeypatch.setenv(k, v)
    git_init(project)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam import notify
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    ensure_global_config()
    o = Orchestrator(project, load_config(project), DB(project / ".ateam/team.db"))
    w = notify.Watcher()

    async def idle():
        for _ in range(200):
            await asyncio.sleep(0.05)
            if not o.lead_busy:
                return

    async def main():
        await o.setup()
        w.diff(o.db.tasks(), o.db.goals())
        gid = o.new_goal("CAN_HOI thêm đăng nhập")
        w.diff(o.db.tasks(), o.db.goals())  # đang lập kế hoạch
        await idle()
        g = o.db.goal(gid)
        assert g.status == "grilling" and o.grill_question(g)["q"] == "Đăng nhập bằng gì?"
        assert g.grill["from_plan"] and o.grill_question(g)["options"] == ["Email", "Google"]
        assert [n.kind for n in w.diff(o.db.tasks(), o.db.goals())] == ["ask"]  # báo người dùng
        assert "Đã trả lời" in o.answer_grill(gid, "Email")
        await idle()
        assert o.grill_question(o.db.goal(gid))["q"] == "Câu hỏi số 2?"  # hỏi tiếp như /grill
        o.answer_grill(gid, "B")
        await idle()
        g = o.db.goal(gid)
        assert g.spec and g.status in ("awaiting", "running") and o.db.tasks(goal_id=gid)
        # lập kế hoạch lần hai đã có đặc tả: không được hỏi lại nữa
        plans = [x for x in full.read_text().split("<<claude>>") if "Reply with ONLY a JSON array" in x]
        assert len(plans) == 2 and "To ask the user first" in plans[0] and "To ask the user first" not in plans[1]
        # chạy không tương tác (ateam goal -y): không hỏi, lập kế hoạch luôn
        o.auto_answer = True
        gid2 = o.new_goal("CAN_HOI việc khác")
        await idle()
        assert o.db.goal(gid2).status in ("awaiting", "running")
    asyncio.run(main())
