"""⏰ /schedule (hẹn giờ, hằng ngày, khi hồi hạn mức) và ↩ điểm khôi phục + /undo theo mục tiêu."""

from __future__ import annotations

import asyncio
import importlib
import subprocess
import time

from conftest import ateam, git_init, write_project_config


def _orch(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import load_config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    return Orchestrator(project, load_config(project), DB(project / ".ateam/team.db"))


def test_parse_schedule_specs():
    from ateam import schedule as S
    now = time.mktime((2026, 10, 26, 21, 0, 0, 0, 0, -1))
    r = S.parse("22:30 viết test", ["claude"], now)
    assert r["kind"] == "at" and r["text"] == "viết test" and r["at"] - now == 90 * 60
    assert S.parse("08:00 x", ["claude"], now)["at"] - now == 11 * 3600  # đã qua hôm nay → sáng mai
    assert S.parse("+1h30m x", ["claude"], now)["at"] - now == 5400
    r = S.parse("daily 07:15 /flow nhanh dọn test", ["claude"], now)
    assert (r["kind"], r["daily"], r["flow"], r["text"]) == ("daily", "07:15", "nhanh", "dọn test")
    assert S.parse("daily@7h x", ["claude"], now)["daily"] == "07:00"
    r = S.parse("quota claude sửa lỗi", ["claude", "codex"], now)
    assert (r["kind"], r["agent"], r["at"]) == ("quota", "claude", None)
    for bad in ("", "mai x", "25:00 x", "+0m x", "22:30", "quota grok x", "daily x"):
        assert isinstance(S.parse(bad, ["claude"], now), str), bad
    items = [{"cli": "claude", "windows": [{"kind": "5h", "used": 100, "resets_at": now + 60}]}]
    assert S.quota_blocked(items, "/usr/bin/claude", now) == now + 60
    assert S.quota_blocked(items, "codex", now) is None and S.quota_blocked(None, "claude", now) is None


def test_schedule_fires_once_daily_and_after_quota(env, project, monkeypatch):
    write_project_config(project, "approve_plan = true\n")
    o = _orch(env, project, monkeypatch)

    async def main():
        await o.setup()
        assert "Đã hẹn #1" in o.schedule_command("+5m Thêm file A")
        assert "Đã hẹn #2" in o.schedule_command("daily 06:00 Thêm file B")
        assert "Đã hẹn #3" in o.schedule_command("quota codex Thêm file C")
        assert "Không có workflow" in o.schedule_command("+5m /flow khong-co x")
        listing = o.schedule_command("")
        assert "#1" in listing and "hằng ngày 06:00" in listing and "khi codex còn hạn mức" in listing
        o.cooldown["codex"] = time.time() + 3600  # codex đang nghỉ: lịch #3 chờ
        assert not o.check_schedules(time.time())  # chưa tới giờ #1/#2
        assert [g.text for g in o.db.goals()] == []
        o.cooldown.pop("codex")
        o.quota_items = [{"cli": "codex", "windows": [{"kind": "5h", "used": 99, "resets_at": time.time() + 600}]}]
        o.check_schedules(time.time())
        assert o.db.goals() == []  # 5h còn cạn theo số liệu quota
        o.quota_items = None
        o.check_schedules(time.time() + 400)  # #1 tới giờ, #3 hết chờ
        assert sorted(g.text for g in o.db.goals()) == ["Thêm file A", "Thêm file C"]
        for _ in range(4):  # kế hoạch nháp (cả vòng review sau) của mục tiêu do lịch tạo: tự duyệt
            await o.run_until_idle()
            o.check_schedules()
        rows = {s["id"]: s for s in o.db.schedules()}
        assert rows[1]["status"] == "done" and rows[3]["status"] == "done" and rows[2]["status"] == "waiting"
        for gid in (rows[1]["goal_id"], rows[3]["goal_id"]):
            assert o.db.goal(gid).status == "done"
        # hằng ngày: chạy rồi dời sang ngày hôm sau, không chạy trùng
        at = rows[2]["at"]
        o.check_schedules(at + 1)
        o.check_schedules(at + 2)
        row = {s["id"]: s for s in o.db.schedules()}[2]
        assert [g.text for g in o.db.goals()].count("Thêm file B") == 1
        assert row["status"] == "waiting" and 86000 < row["at"] - at < 86800
        await o.run_until_idle()
        assert "Đã huỷ lịch #2" in o.schedule_command("rm 2")
        assert "Chưa có lịch" in o.schedule_command("list")
        await asyncio.gather(*list(o._bg), return_exceptions=True)
    asyncio.run(main())


def test_undo_restores_project_before_goal(env, project, monkeypatch):
    git_init(project)
    (project / "keep.txt").write_text("chưa commit\n")  # thay đổi dở của người dùng: giữ lại
    write_project_config(project, "auto_review = false\napprove_plan = false\n")
    o = _orch(env, project, monkeypatch)

    async def main():
        await o.setup()
        gid = o.new_goal("Thêm file A")
        assert gid in o._cp_pending  # task chờ chụp xong mới chạy
        await o.run_until_idle()
        assert o.db.goal(gid).status == "done"
        assert subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/ateam/checkpoints/m{gid}"],
                              cwd=project).returncode == 0
        made = [p.name for p in project.iterdir() if p.name not in (".git", ".ateam", "base.txt", "keep.txt")]
        assert made, "agent giả lập phải tạo file"
        (project / "base.txt").write_text("đã sửa\n")
        title, body = await o.undo_preview(f"m{gid}")
        assert f"#{gid}" in title and "base.txt" in body and "/undo redo" in body
        o.runs[999] = None  # đang có agent chạy: không cho hoàn tác
        assert not (await o.undo(f"m{gid}"))[0]
        o.runs.pop(999)
        ok, msg = await o.undo(f"m{gid}")
        assert ok, msg
        assert (project / "base.txt").read_text() == "base\n" and (project / "keep.txt").read_text() == "chưa commit\n"
        assert not any((project / n).exists() for n in made)
        assert (project / ".ateam/team.db").exists()  # bảng việc của ateam không bị xoá
        assert "hoàn tác" in o.db.goal(gid).summary
        ok, _ = await o.undo("redo")  # lấy lại
        assert ok and (project / "base.txt").read_text() == "đã sửa\n" and all((project / n).exists() for n in made)
        assert "Dùng: /undo" in await o.undo_preview("abc")
        await asyncio.gather(*list(o._bg), return_exceptions=True)
    asyncio.run(main())


def test_cli_schedule_and_undo(env, project):
    git_init(project)
    r = ateam(env, project, "schedule", "+30m", "viết", "README")
    assert "Đã hẹn #1" in r.stdout
    assert "viết README" in ateam(env, project, "schedule").stdout
    assert "Đã huỷ lịch #1" in ateam(env, project, "schedule", "rm", "1").stdout
    r = ateam(env, project, "undo", "m5", "-y", check=False)
    assert r.returncode == 1 and "Không có điểm khôi phục" in r.stdout


def test_web_schedule_and_undo_confirm(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    from test_web import _web_app
    wa = _web_app(env, project, monkeypatch)

    async def main():
        await wa.orch.setup()
        r = await wa.command("/schedule +10m viết README")
        assert r[1] == "ok" and "Đã hẹn #1" in r[0]
        r = await wa.command("/hen")  # bí danh, không tham số = khung danh sách lịch
        assert "viết README" in r[2]["open"]["text"]["body"]
        assert (await wa.command("/schedule mai x"))[1] == "warn"
        gid = wa.orch.new_goal("Thêm file A")
        await asyncio.gather(*list(wa.orch._bg), return_exceptions=True)  # chụp + lập kế hoạch xong
        (project / "base.txt").write_text("đổi\n")
        r = await wa.command(f"/undo m{gid}")  # hỏi lại trước: trình duyệt hiện hộp xác nhận rồi gửi lệnh --yes
        conf = r[2]["open"]["confirm"]
        assert conf["cmd"] == f"/undo m{gid} --yes" and "base.txt" in conf["text"]
        r = await wa.command(conf["cmd"])
        assert r[1] == "ok" and (project / "base.txt").read_text() == "base\n"
    asyncio.run(main())
