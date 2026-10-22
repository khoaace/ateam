"""Hạn mức 5h/tuần dạng số cho giao diện web (ateam/quota.py): bóc output thật của claude/agy, file phiên codex."""

from __future__ import annotations

import datetime as dt
import json
import time

from ateam import quota

NOW = dt.datetime(2026, 10, 22, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=7))).timestamp()


def test_parse_claude_real_and_fake_output():
    lines = ["You are currently using your subscription to power your Claude Code usage", "",
             "Current session: 13% used · resets Oct 22 at 12:09pm (Asia/Saigon)",
             "Current week (all models): 3% used · resets Oct 27 at 5:59am (Asia/Saigon)",
             "Current week (Sonnet only): 7.5% used · resets Oct 27 at 5:59am (Asia/Saigon)",
             "  86%  Start fresh when you switch tasks · run /clear"]  # phần gợi ý phía dưới: không phải hạn mức
    s, w, sonnet = quota.parse_claude(lines, NOW)
    assert (s["kind"], s["used"], s["group"]) == ("5h", 13, "")
    assert s["resets_at"] == dt.datetime(2026, 10, 22, 12, 9, tzinfo=dt.timezone(dt.timedelta(hours=7))).timestamp()
    assert (w["kind"], w["used"], w["group"]) == ("week", 3, "")
    assert w["resets_at"] == dt.datetime(2026, 10, 27, 5, 59, tzinfo=dt.timezone(dt.timedelta(hours=7))).timestamp()
    assert (sonnet["used"], sonnet["group"]) == (7.5, "Sonnet only")
    # agent giả lập (không múi giờ, giờ tròn) và giờ hồi không kèm ngày
    fake = quota.parse_claude(["Current session: 41% used · resets Oct 15 at 7:40pm",
                               "Current week (all models): 26% used · resets 6am"], NOW)
    assert [x["used"] for x in fake] == [41, 26] and all(x["resets_at"] for x in fake)
    assert fake[1]["resets_at"] > NOW  # 6 giờ sáng đã qua → sáng mai
    assert fake[0]["resets_at"] < NOW  # ngày vừa qua giữ nguyên ("đã tới giờ hồi"), không đẩy sang năm sau
    # "Jan 2" in vào cuối năm → năm sau
    dec = dt.datetime(2026, 12, 30, 12).timestamp()
    jan = quota.parse_claude(["Current week (all models): 50% used · resets Jan 2 at 6am"], dec)[0]
    assert dt.datetime.fromtimestamp(jan["resets_at"]).year == 2027
    assert quota.parse_claude(["Chưa cài lệnh 'claude'"]) == []


def test_parse_agy_remaining_to_used():
    out = ("\x04\x08\x08Quota:\r\nGemini Models          Weekly Limit Remaining     11%   2026-10-24 09:03 +07\r\n"
           "Gemini Models          Five Hour Limit Remaining  100%  2026-10-22 12:37 +07\r\n"
           "Claude and GPT models  Weekly Limit Remaining     88%   2026-10-24 17:39 +07\r\n"
           "Claude and GPT models  Five Hour Limit Remaining  100%  2026-10-22 14:46 +07\r\n")
    ws = quota.parse_agy(out.split("\n"))
    assert [(w["group"], w["kind"], w["used"]) for w in ws] == [
        ("Gemini Models", "week", 89), ("Gemini Models", "5h", 0),
        ("Claude and GPT models", "week", 12), ("Claude and GPT models", "5h", 0)]
    assert ws[0]["resets_at"] == dt.datetime(2026, 10, 24, 9, 3, tzinfo=dt.timezone(dt.timedelta(hours=7))).timestamp()


def _codex_session(home, rate_limits: dict) -> None:
    d = home / "sessions" / "2026" / "10" / "22"
    d.mkdir(parents=True)
    ev = {"timestamp": "2026-10-22T02:00:00Z", "type": "event_msg",
          "payload": {"type": "token_count", "rate_limits": rate_limits}}
    (d / "rollout-x.jsonl").write_text(json.dumps(ev) + "\n")


def test_codex_quota_by_window_minutes(tmp_path):
    assert quota.codex_quota(tmp_path / "none") == ([], None)
    later = time.time() + 86400
    # gói Plus có khi chỉ có `primary` và đó là khung TUẦN: phân loại theo window_minutes, không theo tên khoá
    _codex_session(tmp_path / "a", {"plan_type": "plus", "secondary": None,
                                    "primary": {"used_percent": 9.0, "window_minutes": 10080, "resets_at": later}})
    ws, at = quota.codex_quota(tmp_path / "a")
    assert [(w["kind"], w["used"], w["resets_at"]) for w in ws] == [("week", 9, later)]
    assert at == dt.datetime(2026, 10, 22, 2, tzinfo=dt.timezone.utc).timestamp()
    # ảnh chụp cũ: khung đã qua giờ hồi coi như chưa dùng
    _codex_session(tmp_path / "b", {"primary": {"used_percent": 12.5, "window_minutes": 300, "resets_at": 1000},
                                    "secondary": {"used_percent": 3, "window_minutes": 10080, "resets_at": later}})
    ws, _ = quota.codex_quota(tmp_path / "b")
    assert [(w["kind"], w["used"]) for w in ws] == [("5h", 0), ("week", 3)]
