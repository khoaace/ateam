"""/grill ("grill me"): trưởng nhóm phỏng vấn người dùng từng câu trước khi lập kế hoạch."""

from __future__ import annotations

import asyncio
import json
import sqlite3

from conftest import git_init, write_project_config


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

        async def wait(cond, n=200):  # CI chậm: chờ tới 30 giây, xong sớm thì thoát sớm
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
            assert await wait(lambda: app.db.goal(gid).status == "awaiting")
            g = app.db.goal(gid)
            assert g.spec.startswith("- Đăng nhập bằng email") and "Đã trả lời 2 câu" in g.spec
            assert [x["a"] for x in g.grill["qa"]] == ["Phương án B", "Chỉ đăng nhập bằng email"]
            assert await wait(lambda: not bar.display)  # DB đổi trước, thanh ẩn ở lượt vẽ sau (CI macOS chậm)
            assert "Trả lời câu hỏi" not in box.placeholder
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
            assert await wait(lambda: app.db.goal(gid2).status == "awaiting")
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
        assert o.grill_question(o.db.goal(gid))["q"] == "Câu hỏi số 2?"  # hỏi tiếp, chỉ điểm thiết yếu
        grills = [x for x in full.read_text().split("<<claude>>") if "you INTERVIEW the user" in x]
        assert "ESSENTIAL is still unclear" in grills[-1] and "at most 3 questions" in grills[-1]
        assert "Walk down each branch" not in grills[-1]
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


def _orch(env, project, monkeypatch, tmp_path):
    import importlib

    full = tmp_path / "full.log"
    for k, v in dict(env, ATEAM_FAKE_FULL_LOG=str(full)).items():
        monkeypatch.setenv(k, v)
    git_init(project)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    ensure_global_config()
    return Orchestrator(project, load_config(project), DB(project / ".ateam/team.db")), full


async def _idle(o):
    for _ in range(200):
        await asyncio.sleep(0.05)
        if not o.lead_busy:
            return


def test_grill_session_skip_digit_and_errors(env, project, monkeypatch, tmp_path):
    """Hỏi đáp tiếp đúng phiên trưởng nhóm; số = phương án; "tự quyết" theo khuyến nghị; lỗi hiện kèm ↻ Hỏi tiếp."""
    from ateam import mentions
    from ateam import prompts as P
    o, full = _orch(env, project, monkeypatch, tmp_path)

    async def main():
        await o.setup()
        gid = o.start_grill("Thêm trang đăng nhập")
        await _idle(o)
        g = o.db.goal(gid)
        sid = g.lead_session
        assert g.question()["q"] == "Câu hỏi số 1?" and sid
        assert "Walk down each branch" in full.read_text()  # /grill: phỏng vấn đầy đủ
        o.answer_grill(gid, "2")  # gõ số = chọn phương án
        await _idle(o)
        g = o.db.goal(gid)
        assert g.answered()[0]["a"] == "Phương án B" and g.question()["q"] == "Câu hỏi số 2?"
        assert g.lead_session == sid  # tiếp phiên cũ, không mở phiên mới mỗi câu
        assert not o.lead_runs

        # lỗi: không còn trưởng nhóm nào / JSON hỏng / ngoại lệ → ghi lỗi, không kẹt "đang nghĩ"
        real = o._call_lead

        async def none(*a, **k):
            return None
        monkeypatch.setattr(o, "_call_lead", none)
        o.answer_grill(gid, None)  # để trưởng nhóm tự quyết
        await _idle(o)
        g = o.db.goal(gid)
        assert g.answered()[1]["a"] == P.skip_answer("Phương án A") and "Phương án A" in g.answered()[1]["a"]
        assert "Không có trưởng nhóm nào" in g.grill["error"] and g.status == "grilling"

        async def garbage(*a, **k):
            return "không phải JSON"
        monkeypatch.setattr(o, "_call_lead", garbage)
        o.retry_grill(gid)
        await _idle(o)
        assert "không trả về câu hỏi" in o.db.goal(gid).grill["error"]

        def boom(*a, **k):
            raise mentions.AttachmentError("tệp quá lớn")
        orig = P.grill_prompt
        monkeypatch.setattr(P, "grill_prompt", boom)
        o.retry_grill(gid)
        await _idle(o)
        assert o.db.goal(gid).grill["error"] == "tệp quá lớn" and gid not in o.lead_busy
        monkeypatch.setattr(P, "grill_prompt", orig)
        monkeypatch.setattr(o, "_call_lead", real)
        o.retry_grill(gid)  # hỏi lại được: đủ 2 câu → chốt đặc tả → lập kế hoạch
        await _idle(o)
        g = o.db.goal(gid)
        assert g.spec and g.grill["closed"] and g.status in ("awaiting", "running") and not g.grill["error"]

    asyncio.run(main())


def test_grill_finish_without_answers_plans_without_asking(env, project, monkeypatch, tmp_path):
    """Bấm "Đủ rồi" khi chưa trả lời câu nào, trưởng nhóm không viết đặc tả: lập kế hoạch luôn, không hỏi lại."""
    o, full = _orch(env, project, monkeypatch, tmp_path)

    async def main():
        await o.setup()
        gid = o.start_grill("CAN_HOI trang hồ sơ")
        await _idle(o)
        real = o._call_lead

        async def no_spec(prompt, *a, **k):
            return "{}" if "STOP the interview" in prompt else await real(prompt, *a, **k)
        monkeypatch.setattr(o, "_call_lead", no_spec)
        o.finish_grill(gid)
        await _idle(o)
        g = o.db.goal(gid)
        assert g.status in ("awaiting", "running") and g.grill["closed"] and not g.answered()
        plans = [x for x in full.read_text().split("<<claude>>") if "Reply with ONLY a JSON array" in x]
        assert plans and "To ask the user first" not in plans[-1]

    asyncio.run(main())


def test_waiting_view_stale_grill_does_not_hide_agent_question(env, project, monkeypatch, tmp_path):
    """/grill bị bỏ dở (lỗi) không che câu hỏi <<<ASK>>> của agent; câu /grill đang chờ thì ưu tiên trước."""
    from ateam.db import ASKING
    o, _ = _orch(env, project, monkeypatch, tmp_path)
    gid = o.db.add_goal("x")
    o.db.update_goal(gid, status="grilling")
    o.db.set_grill(gid, {"qa": [], "spec": "", "error": "hỏng"})
    assert o.waiting_view()["kind"] == "grill" and o.waiting_view()["error"] == "hỏng"
    tid = o.db.add_task("codex", "t", "t")
    o.db.update_task(tid, status=ASKING, ask={"qa": [{"q": "Màu gì?", "why": "", "options": ["Đỏ", "Xanh"],
                                                     "rec": "", "a": None}]})
    v = o.waiting_view()
    assert v["kind"] == "ask" and v["task"] == tid and v["question"]["q"] == "Màu gì?"
    assert "Đã trả lời" in o.answer_task(tid, "2") and o.db.task(tid).ask["qa"][0]["a"] == "Xanh"
    o.db.update_task(tid, status=ASKING, ask={"qa": [{"q": "Cỡ?", "why": "", "options": [], "rec": "", "a": None}]})
    o.db.set_grill(gid, {"qa": [{"q": "Ai dùng?", "why": "", "options": [], "rec": "", "a": None}], "spec": ""})
    assert o.waiting_view()["kind"] == "grill"  # câu /grill đang chờ trả lời: hiện trước
    assert o.grill_command("bỏ").startswith("Đã bỏ") and o.db.goal(gid).status == "cancelled"
    assert o.grill_command("Thêm trang") is None  # không phải lệnh con: mục tiêu mới


def test_cancel_grill_stops_lead_run(env, project, monkeypatch, tmp_path):
    """Bỏ mục tiêu khi trưởng nhóm đang nghĩ câu hỏi: dừng luôn tiến trình (khỏi tốn token)."""
    import time
    o, _ = _orch(env, project, monkeypatch, tmp_path)

    async def main():
        await o.setup()
        gid = o.start_grill("CHAM_HOI thêm trang")
        for _ in range(100):
            await asyncio.sleep(0.05)
            if gid in o.lead_runs:
                break
        assert gid in o.lead_runs
        t0 = time.time()
        assert "Đã bỏ" in o.cancel_grill(gid)
        await _idle(o)
        assert time.time() - t0 < 10 and not o.lead_busy and not o.lead_runs
        assert o.db.goal(gid).status == "cancelled"

    asyncio.run(main())


def test_codex_lead_prompt_echo_and_truncated_plan(env, project, monkeypatch, tmp_path):
    """Codex làm trưởng nhóm: `codex exec` in lại prompt (có JSON câu hỏi mẫu) và model quên `]` cuối kế hoạch —
    trước đây thành câu hỏi "..." rồi "Trưởng nhóm không trả về kế hoạch JSON hợp lệ"."""
    write_project_config(project, 'lead = "codex"\n')
    o, _ = _orch(env, project, monkeypatch, tmp_path)

    async def main():
        await o.setup()
        gid = o.new_goal("THIEU_NGOAC hai cột cao bằng nhau")
        await _idle(o)
        g = o.db.goal(gid)
        assert g.status in ("awaiting", "running"), (g.status, g.summary, g.grill)
        assert [t.title for t in o.db.tasks(goal_id=gid)] == ["Kế hoạch do codex lập"]
    asyncio.run(main())


def test_prompt_echo_and_placeholder_question():
    from ateam import prompts as P
    prompt = "GOAL: @a.py\n\nAsk first.\nReply with ONLY JSON:\n" + P.QUESTION_SCHEMA
    # CLI nhận prompt đã kèm rule + đổi @file (khác `prompt` ở đầu) và giữ nguyên dòng trống
    out = (f"session id: x\nuser\nRULES\nGOAL: a.py\n\nAsk first.\n\nReply with ONLY JSON:\n{P.QUESTION_SCHEMA}\n"
           'codex\n{"question": "Màu gì?"}')
    assert P.strip_echo(out, prompt) == 'codex\n{"question": "Màu gì?"}'
    assert P.strip_echo(out, "lượt resume ngắn, khác hẳn", prompt) == 'codex\n{"question": "Màu gì?"}'
    assert P.strip_echo("không in lại prompt", prompt) == "không in lại prompt"
    assert P.strip_echo("a\nok\nb", "ok") == "a\nok\nb"  # quá ngắn: không cắt
    # câu trả lời trích một dòng của prompt: không cắt (phải khớp cả mấy dòng cuối liên tiếp)
    assert P.strip_echo(P.QUESTION_SCHEMA + "\nđáp", prompt) == P.QUESTION_SCHEMA + "\nđáp"
    assert P.question_from(json.loads(P.QUESTION_SCHEMA)) is None  # câu hỏi "..." của JSON mẫu
    assert P.question_from({"question": "Màu gì?"})["q"] == "Màu gì?"


def test_extract_json_closes_truncated_array():
    from ateam import prompts as P
    keys = ("prompt", "agent", "title")
    plan = '[{"id":1,"agent":"ui","title":"T","prompt":"p [x]","depends_on":[]}'
    want = [{"id": 1, "agent": "ui", "title": "T", "prompt": "p [x]", "depends_on": []}]
    assert P.extract_json(plan + "\ntokens used\n24,916\n" + plan, list, keys) == want
    assert P.extract_json("codex\n" + plan, list, keys) == want  # hết văn bản
    assert P.extract_json('[\n  {"agent": "ui", "prompt": "p"}\n\nxong', list, keys) == [{"agent": "ui", "prompt": "p"}]
    # JSON mẫu trong prompt hỏng giữa dòng (<ids>): không vá thành kế hoạch giả
    assert P.extract_json(P.TASK_SCHEMA, list, keys) is None
    assert P.extract_json('{"done": true, "spec": "a"\nok', dict, ("done",)) == {"done": True, "spec": "a"}
    assert P.extract_json('[{"agent": "ui", "prompt": "chưa đóng\nchuỗi', list, keys) is None


def test_task_output_prompt_echo_examples_ignored():
    """codex làm thành viên cũng in lại prompt: khối DELEGATE/NOTE/ASK/SUMMARY ví dụ không được coi là thật."""
    from ateam import prompts as P
    from ateam.config import AgentConfig, Config
    cfg = Config(agents={n: AgentConfig(n, [n, "{prompt}"]) for n in ("codex", "grok")})
    prompt = P.task_prompt(cfg, agent="codex", task_id=1, title="t", prompt="sửa X", goal=None, deps=[],
                           notes="", cwd="/p", can_delegate=True, can_ask=True)
    assert "MEMBER_NAME" in prompt and "<<<ASK>>>" in prompt
    out = "session id: x\nuser\n" + prompt + "\ncodex\nđã sửa X\n"
    assert P.parse_delegations(out) == []  # MEMBER_NAME của ví dụ
    answer = P.strip_echo(out, prompt)
    assert answer == "codex\nđã sửa X" and P.parse_ask(answer) is None and not P.parse_notes(answer)
    assert "SUMMARY" not in P.extract_summary(answer)  # thiếu SUMMARY: không lấy luật SUMMARY trong prompt
    assert P.extract_summary("xong\n**SUMMARY:**\nsửa a.py") == "sửa a.py"  # agy viết markdown
