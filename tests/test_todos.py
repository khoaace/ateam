"""To-do (tag, hạn, ưu tiên) và Ghi chú: phần lõi lưu file JSON ngoài repo, dùng chung cho TUI và web."""
from __future__ import annotations

import datetime as dt

import pytest

from ateam import config, notes, todos

NOW = dt.datetime(2026, 10, 20, 10, 0)  # thứ Ba


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GLOBAL_DIR", tmp_path / "cfg")
    p = tmp_path / "proj"
    p.mkdir()
    return p


def test_parse_due_words():
    assert todos.parse_due("mai 17:00", NOW) == "2026-10-21T17:00"
    assert todos.parse_due("@hôm-nay", NOW) == "2026-10-20"
    assert todos.parse_due("t6", NOW) == "2026-10-23"
    assert todos.parse_due("cn", NOW) == "2026-10-25"
    assert todos.parse_due("tuần-sau", NOW) == "2026-10-26"
    assert todos.parse_due("24/12 9h", NOW) == "2026-12-24T09:00"
    assert todos.parse_due("17h", NOW) == "2026-10-20T17:00"
    assert todos.parse_due("19/10", NOW) == "2026-10-19"     # vừa qua: vẫn năm nay (quá hạn), không nhảy năm sau
    assert todos.parse_due("5/1", NOW) == "2027-01-05"       # đã qua lâu: năm sau
    assert todos.parse_due("2026-11-02", NOW) == "2026-11-02"
    assert todos.parse_due("", NOW) == ""                    # trống = bỏ hạn
    assert todos.parse_due("abc", NOW) is None and todos.parse_due("mai xyz", NOW) is None


def test_parse_quick():
    q = todos.parse_quick("Sửa PR #19 #Bug #ui !cao @t6 17:00 nhé", NOW)
    assert q == {"text": "Sửa PR #19 nhé", "tags": ["bug", "ui"], "due": "2026-10-23T17:00", "priority": 3}
    assert todos.parse_quick("gọi @khoa !!", NOW) == {"text": "gọi @khoa", "tags": [], "due": None, "priority": 2}


def test_bucket_and_label():
    b = {d: todos.bucket({"due": d}, NOW) for d in ("2026-10-18", "2026-10-20T09:00", "2026-10-20", "2026-10-25",
                                                     "2026-10-26", "")}
    assert list(b.values()) == ["over", "over", "today", "week", "later", "none"]
    assert todos.bucket({"due": "2026-10-18", "done": True}, NOW) == "done"
    assert todos.due_label({"due": "2026-10-18"}, NOW) == ("⏰ quá 2 ngày", "over")
    assert todos.due_label({"due": "2026-10-20T17:00"}, NOW) == ("hôm nay 17:00", "today")
    assert todos.due_label({"due": "2026-10-23"}, NOW) == ("T6 23/10", "week")


def test_todo_quick_add_and_edit(root):
    todos.apply(root, "add", {"text": "Sửa login #bug !cao @mai"})
    x = todos.load(root)[0]
    assert x["text"] == "Sửa login" and x["priority"] == 3 and x["due"] and todos.tag_names(root, x["tags"]) == ["bug"]
    todos.apply(root, "add", {"text": "#ghi-chú thô", "plain": True})        # plain: không bóc cú pháp
    assert todos.load(root)[1]["text"] == "#ghi-chú thô" and not todos.load(root)[1].get("tags")
    todos.apply(root, "edit", {"id": x["id"], "due": "t6 9h", "tags": ["ui", "bug"], "priority": 0, "desc": "- a"})
    x = todos.load(root)[0]
    assert x["due"].endswith("T09:00") and x["desc"] == "- a" and not x.get("priority")
    assert todos.tag_names(root, x["tags"]) == ["ui", "bug"] and x.get("updated")
    todos.apply(root, "toggle", {"id": x["id"]})
    assert todos.load(root)[0]["done"] and todos.load(root)[0]["done_at"]
    with pytest.raises(ValueError):
        todos.apply(root, "add", {"text": "#chỉ-tag"})


def test_tags_shared_with_notes(root):
    todos.apply(root, "add", {"text": "a #bug #ui"})
    n = notes.apply(root, "add", {"title": "N", "tags": ["bug"]})
    tags = {t["name"]: t for t in todos.load_tags(root)}
    assert list(tags) == ["bug", "ui"] and tags["bug"]["color"] != tags["ui"]["color"]
    with pytest.raises(ValueError):
        todos.apply_tag(root, "rename", {"id": tags["ui"]["id"], "name": "Bug"})   # trùng tên
    todos.apply_tag(root, "rename", {"id": tags["ui"]["id"], "name": "Giao diện"})
    assert todos.tag_names(root, todos.load(root)[0]["tags"]) == ["bug", "giao-diện"]
    c = todos.tag_counts(root)[tags["bug"]["id"]]
    assert c == {"todos": 1, "notes": 1, "open": 1}
    todos.apply_tag(root, "merge", {"id": tags["bug"]["id"], "into": tags["ui"]["id"]})
    assert [t["name"] for t in todos.load_tags(root)] == ["giao-diện"]
    assert todos.load(root)[0]["tags"] == [tags["ui"]["id"]] and notes.get(root, n["id"])["tags"] == [tags["ui"]["id"]]
    todos.apply_tag(root, "delete", {"id": tags["ui"]["id"]})
    assert todos.load_tags(root) == [] and todos.load(root)[0]["tags"] == [] and notes.get(root, n["id"])["tags"] == []
    assert root not in todos.path_for(root, "tags").parents


def test_notes_conflict_and_summaries(root):
    a = notes.apply(root, "add", {"body": "# Họp sprint\n\n- [ ] gửi biên bản"})
    b = notes.apply(root, "add", {"title": "Lệnh debug", "body": "pytest -q"})
    s = notes.summaries(root)
    assert [x["title"] for x in s] == ["Lệnh debug", "Họp sprint"]          # sửa gần nhất trước
    assert s[1]["snip"] == "gửi biên bản"
    notes.apply(root, "pin", {"id": a["id"]})
    assert notes.summaries(root)[0]["id"] == a["id"]                         # ghim lên đầu
    saved = notes.apply(root, "save", {"id": b["id"], "body": "v2", "base": b["updated"]})
    with pytest.raises(notes.Conflict) as e:                                 # tab khác lưu bằng base cũ
        notes.apply(root, "save", {"id": b["id"], "body": "cũ", "base": b["updated"]})
    assert e.value.note["body"] == "v2"
    notes.apply(root, "save", {"id": b["id"], "body": "ghi đè", "base": b["updated"], "force": True})
    assert notes.get(root, b["id"])["body"] == "ghi đè" and saved["updated"] > b["updated"]
    notes.apply(root, "to_todo", {"id": a["id"], "text": "gửi biên bản"})
    assert todos.load(root)[-1]["text"] == "gửi biên bản"
    notes.apply(root, "delete", {"id": a["id"]})
    assert [n["id"] for n in notes.load(root)] == [b["id"]]
