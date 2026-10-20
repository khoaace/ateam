"""To-do và tag theo dự án (tab ✅ To-do của TUI và web). Lưu ngoài repo — ~/.config/ateam/<loại>/<tên>-<băm đường
dẫn>.json — để không phải thêm gì vào .gitignore và không lẫn vào commit. Cùng tên file cho todos/, tags/, notes/
(notes.py), rules/ (rules.py).

Mỗi việc: {id, text, done, created} và các khoá tuỳ chọn (file cũ vẫn mở được): tags (id tag), due ("YYYY-MM-DD"
hoặc "YYYY-MM-DDTHH:MM", giờ máy), priority (0 không · 1 thấp · 2 vừa · 3 cao), desc (markdown), updated, done_at.
Mỗi tag: {id, name, color}; dùng chung cho to-do và ghi chú, thứ tự trong mảng là thứ tự hiện."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path

from . import config

MAX_TEXT = 500
MAX_DESC = 20000
MAX_TAG = 32
# bảng màu tag: đủ tương phản trên nền tối, theme sáng tự làm đậm chữ (CSS)
PALETTE = ["#f07178", "#f0a070", "#e6b84d", "#8fd16a", "#7dd3c0", "#22d3ee", "#8ec8ff", "#a78bfa", "#f0a0c8",
           "#c4b5fd", "#a3a094", "#e8e6dc"]
PRIORITIES = (0, 1, 2, 3)
DUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_cache: dict = {}  # đường dẫn file -> (mtime, danh sách): ảnh chụp web đọc mỗi 0,5 giây


def path_for(root: Path, kind: str = "todos") -> Path:
    root = Path(root).resolve()
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", root.name).strip("-") or "root"
    return config.GLOBAL_DIR / kind / f"{slug}-{hashlib.sha1(str(root).encode()).hexdigest()[:10]}.json"


def read_list(p: Path, keep) -> list:
    """Đọc mảng JSON (cache theo mtime), giữ phần tử dict mà keep(x) đúng."""
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return []
    hit = _cache.get(p)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        items = [x for x in json.loads(p.read_text(encoding="utf-8")) if isinstance(x, dict) and keep(x)]
    except (OSError, ValueError, TypeError):
        items = []
    _cache[p] = (mtime, items)
    return items


def write_list(p: Path, items: list) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    _cache.pop(p, None)


def next_id(items: list) -> int:
    return max([x.get("id", 0) for x in items] + [0]) + 1


def load(root: Path) -> list:
    return read_list(path_for(root), lambda x: x.get("text"))


def save(root: Path, items: list) -> None:
    write_list(path_for(root), items)


# ------------------------------------------------------------------ tag
def load_tags(root: Path) -> list:
    return read_list(path_for(root, "tags"), lambda x: x.get("name") and isinstance(x.get("id"), int))


def norm_tag(name) -> str:
    """'#Ý tưởng ' -> 'ý-tưởng': chữ thường, dấu cách thành '-', bỏ ký tự phân cách."""
    s = unicodedata.normalize("NFC", str(name or "")).strip().lstrip("#").lower()
    s = re.sub(r"[\s,;#]+", "-", s).strip("-")
    return s[:MAX_TAG]


def tag_map(root: Path) -> dict:
    return {t["id"]: t for t in load_tags(root)}


def tag_names(root: Path, ids) -> list:
    m = tag_map(root)
    return [m[i]["name"] for i in ids or [] if i in m]


def ensure_tags(root: Path, values) -> list:
    """Tên hoặc id tag -> danh sách id (giữ thứ tự, bỏ trùng); tên chưa có thì tạo tag mới, màu kế tiếp."""
    tags = [dict(t) for t in load_tags(root)]
    by_name = {t["name"]: t["id"] for t in tags}
    ids, created = [], False
    for v in values or []:
        if isinstance(v, int) or (isinstance(v, str) and v.isdigit() and int(v) in {t["id"] for t in tags}):
            i = int(v)
            if any(t["id"] == i for t in tags) and i not in ids:
                ids.append(i)
            continue
        n = norm_tag(v)
        if not n:
            continue
        if n not in by_name:
            t = {"id": next_id(tags), "name": n, "color": PALETTE[len(tags) % len(PALETTE)]}
            tags.append(t)
            by_name[n] = t["id"]
            created = True
        if by_name[n] not in ids:
            ids.append(by_name[n])
    if created:
        write_list(path_for(root, "tags"), tags)
    return ids


def _retag(root: Path, fn) -> None:
    """Sửa danh sách tag của mọi việc và ghi chú (gộp / xoá tag)."""
    from . import notes
    for p, items in ((path_for(root), load(root)), (notes.path_for(root), notes.load(root))):
        changed, out = False, []
        for x in items:
            old = list(x.get("tags") or [])
            new = fn(old)
            if new != old:
                x = dict(x, tags=new)
                changed = True
            out.append(x)
        if changed:
            write_list(p, out)


def apply_tag(root: Path, action: str, d: dict) -> list:
    """add (name, color) · rename (id, name) · recolor (id, color) · move (id, to) · merge (id, into: gắn tag đích
    cho mọi việc/ghi chú rồi xoá tag này) · delete (id: gỡ khỏi việc/ghi chú, không xoá chúng).
    ValueError("empty" | "exists") khi tên rỗng / trùng tag khác."""
    tags = [dict(t) for t in load_tags(root)]
    find = [t for t in tags if t["id"] == _int(d.get("id"))]
    name = norm_tag(d.get("name"))
    color = str(d.get("color") or "")
    if action in ("add", "rename"):
        if not name:
            raise ValueError("empty")
        if any(t["name"] == name and (not find or t["id"] != find[0]["id"]) for t in tags):
            raise ValueError("exists")
    if action == "add":
        tags.append({"id": next_id(tags), "name": name,
                     "color": color if COLOR_RE.match(color) else PALETTE[len(tags) % len(PALETTE)]})
    elif action == "rename" and find:
        find[0]["name"] = name
    elif action == "recolor" and find and COLOR_RE.match(color):
        find[0]["color"] = color.lower()
    elif action == "move" and find:
        tags.remove(find[0])
        tags.insert(max(0, min(_int(d.get("to")), len(tags))), find[0])
    elif action == "merge" and find:
        into = _int(d.get("into"))
        if into == find[0]["id"] or not any(t["id"] == into for t in tags):
            return tags
        src = find[0]["id"]
        _retag(root, lambda ids: list(dict.fromkeys(into if i == src else i for i in ids)))
        tags.remove(find[0])
    elif action == "delete" and find:
        src = find[0]["id"]
        _retag(root, lambda ids: [i for i in ids if i != src])
        tags.remove(find[0])
    else:
        return tags
    write_list(path_for(root, "tags"), tags)
    return tags


def tag_counts(root: Path) -> dict:
    """id tag -> {todos, notes, open}: số việc, số ghi chú, số việc chưa xong mang tag đó."""
    from . import notes
    out: dict = {t["id"]: {"todos": 0, "notes": 0, "open": 0} for t in load_tags(root)}
    for x in load(root):
        for i in set(x.get("tags") or []):
            if i in out:
                out[i]["todos"] += 1
                out[i]["open"] += 0 if x.get("done") else 1
    for x in notes.load(root):
        for i in set(x.get("tags") or []):
            if i in out:
                out[i]["notes"] += 1
    return out


# ------------------------------------------------------------------ hạn + cú pháp nhanh
def _int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower()).replace(chr(0x111), "d")  # đ không tách dấu khi NFD
    return "".join(c for c in s if not unicodedata.combining(c)).replace("-", "").replace("_", "")


TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2})|h(\d{2})?|(am|pm))$")
DATE_RE = re.compile(r"^(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?$")
ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
WEEKDAYS = {"t2": 0, "thu2": 0, "mon": 0, "t3": 1, "thu3": 1, "tue": 1, "t4": 2, "thu4": 2, "wed": 2,
            "t5": 3, "thu5": 3, "thu": 3, "t6": 4, "thu6": 4, "fri": 4, "t7": 5, "thu7": 5, "sat": 5,
            "cn": 6, "chunhat": 6, "sun": 6}


def parse_time(word: str):
    m = TIME_RE.match(word.strip().lower())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or m.group(3) or 0)
    if m.group(4) == "pm" and h < 12:
        h += 12
    if m.group(4) == "am" and h == 12:
        h = 0
    return (h, mi) if h < 24 and mi < 60 else None


def parse_date(word: str, today: dt.date):
    """'mai', 't6', 'tuần-sau', '24/10', '2026-10-24'… -> date (None nếu không hiểu)."""
    w = _ascii(word.strip())
    if w in ("homnay", "nay", "today"):
        return today
    if w in ("mai", "ngaymai", "tomorrow", "tmr"):
        return today + dt.timedelta(days=1)
    if w in ("mot", "ngaymot", "kia"):
        return today + dt.timedelta(days=2)
    if w in ("tuansau", "nextweek"):
        return today + dt.timedelta(days=7 - today.weekday())
    if w in ("cuoituan", "weekend"):
        return today + dt.timedelta(days=(5 - today.weekday()) % 7)
    if w in WEEKDAYS:
        return today + dt.timedelta(days=(WEEKDAYS[w] - today.weekday()) % 7)
    raw = word.strip().lower()
    m = ISO_RE.match(raw)
    try:
        if m:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = DATE_RE.match(raw)
        if m:
            y = int(m.group(3)) if m.group(3) else today.year
            d = dt.date(y + 2000 if y < 100 else y, int(m.group(2)), int(m.group(1)))
            if not m.group(3) and d < today - dt.timedelta(days=60):  # 5/1 gõ vào tháng 10: tháng 1 năm sau
                d = d.replace(year=d.year + 1)
            return d
    except ValueError:
        return None
    return None


def parse_due(text: str, now: dt.datetime | None = None) -> str | None:
    """'mai 17:00', 't6', '24/10 9h', '17h', '' -> chuỗi hạn ('' = bỏ hạn), None nếu không hiểu."""
    now = now or dt.datetime.now()
    words = str(text or "").strip().lstrip("@").split()
    if not words:
        return ""
    if DUE_RE.match(words[0]) and len(words) == 1:
        return words[0]
    day = parse_date(words[0], now.date())
    rest = words[1:] if day else words
    hm = parse_time(rest[0]) if rest else None
    if (rest and not hm) or len(rest) > 1:
        return None
    day = day or now.date()
    return day.isoformat() + (f"T{hm[0]:02d}:{hm[1]:02d}" if hm else "")


PRI_WORDS = {"thap": 1, "low": 1, "vua": 2, "med": 2, "medium": 2, "cao": 3, "high": 3, "1": 1, "2": 2, "3": 3}


def parse_quick(text: str, now: dt.datetime | None = None) -> dict:
    """'Sửa lỗi #bug !cao @t6 17:00' -> {text, tags (tên), due, priority}. Phần không hiểu giữ nguyên trong chữ;
    '#19' (chỉ có số) không phải tag."""
    now = now or dt.datetime.now()
    words, out, tags, due, pri = str(text or "").split(), [], [], None, None
    i = 0
    while i < len(words):
        w = words[i]
        if len(w) > 1 and w[0] == "#" and re.search(r"[^\W\d_]", w[1:]) and norm_tag(w):
            tags.append(norm_tag(w))
        elif re.fullmatch(r"!{1,3}", w):
            pri = len(w)
        elif w[0] == "!" and _ascii(w[1:]) in PRI_WORDS:
            pri = PRI_WORDS[_ascii(w[1:])]
        elif len(w) > 1 and w[0] == "@":
            nxt = words[i + 1] if i + 1 < len(words) else ""
            two = parse_due(w + " " + nxt, now) if nxt and parse_time(nxt) else None
            one = two or parse_due(w, now)
            if one:
                due = one
                i += 2 if two else 1
                continue
            out.append(w)
        else:
            out.append(w)
        i += 1
    return {"text": " ".join(out), "tags": list(dict.fromkeys(tags)), "due": due, "priority": pri}


def due_parts(due: str):
    """'2026-10-24T17:00' -> (date, (17, 0)) · '2026-10-24' -> (date, None) · sai -> (None, None)."""
    if not due or not DUE_RE.match(due):
        return None, None
    try:
        d = dt.date.fromisoformat(due[:10])
    except ValueError:
        return None, None
    return d, ((int(due[11:13]), int(due[14:16])) if len(due) > 10 else None)


BUCKETS = ("over", "today", "week", "later", "none", "done")


def bucket(x: dict, now: dt.datetime | None = None) -> str:
    """Nhóm theo hạn: over (quá hạn) · today · week (tới hết Chủ nhật) · later · none (không hạn) · done."""
    if x.get("done"):
        return "done"
    now = now or dt.datetime.now()
    d, hm = due_parts(x.get("due") or "")
    if not d:
        return "none"
    today = now.date()
    if d < today or (d == today and hm and (hm[0], hm[1]) < (now.hour, now.minute)):
        return "over"
    if d == today:
        return "today"
    if d <= today + dt.timedelta(days=6 - today.weekday()):
        return "week"
    return "later"


# ------------------------------------------------------------------ thao tác
def _clean_fields(root: Path, d: dict, item: dict) -> None:
    """Chép các khoá desc/due/priority/tags hợp lệ từ d sang item (khoá vắng: giữ nguyên)."""
    if "desc" in d:
        desc = str(d.get("desc") or "").rstrip()[:MAX_DESC]
        if desc:
            item["desc"] = desc
        else:
            item.pop("desc", None)
    if "due" in d:
        due = str(d.get("due") or "").strip()
        if due and not DUE_RE.match(due):
            due = parse_due(due) or ""  # TUI gõ "mai 17h"
        if due:
            item["due"] = due
        else:
            item.pop("due", None)
    if "priority" in d and d.get("priority") is not None:
        p = _int(d.get("priority"))
        item["priority"] = p if p in PRIORITIES else 0
    if "tags" in d and isinstance(d.get("tags"), list):
        item["tags"] = ensure_tags(root, d["tags"])


def apply(root: Path, action: str, d: dict) -> list:
    """add (text: hiểu cú pháp nhanh trừ khi plain; thêm desc/due/priority/tags) · edit (id + text/desc/due/priority/
    tags) · toggle (id) · delete (id) · clear (bỏ việc đã xong) · move (id, to). ValueError("empty") khi chữ rỗng."""
    items = [dict(x) for x in load(root)]
    text = str(d.get("text") or "").strip()
    find = [x for x in items if x.get("id") == d.get("id")]
    now = time.time()
    if action == "add":
        q = {"text": text, "tags": [], "due": None, "priority": None} if d.get("plain") else parse_quick(text)
        text = q["text"].strip()[:MAX_TEXT]
        if not text:
            raise ValueError("empty")
        item = {"id": next_id(items), "text": text, "done": False, "created": now}
        tags = list(d.get("tags") or []) + q["tags"] if isinstance(d.get("tags"), list) or q["tags"] else None
        extra = {k: v for k, v in (("due", q["due"]), ("priority", q["priority"])) if v is not None}
        _clean_fields(root, dict({k: d[k] for k in ("desc", "due", "priority") if k in d}, **extra,
                                 **({"tags": tags} if tags else {})), item)
        items.append(item)
    elif action == "toggle" and find:
        find[0]["done"] = not find[0].get("done")
        find[0]["done_at"] = now if find[0]["done"] else None
        find[0]["updated"] = now
    elif action == "edit" and find:
        if "text" in d and not text[:MAX_TEXT]:
            raise ValueError("empty")
        if text:
            find[0]["text"] = text[:MAX_TEXT]
        _clean_fields(root, d, find[0])
        find[0]["updated"] = now
    elif action == "delete" and find:
        items.remove(find[0])
    elif action == "clear":
        items = [x for x in items if not x.get("done")]
    elif action == "move" and find:
        items.remove(find[0])
        to = max(0, min(_int(d.get("to")), len(items)))
        items.insert(to, find[0])
    else:
        return items
    save(root, items)
    return items


def due_label(x: dict, now: dt.datetime | None = None) -> tuple:
    """Nhãn hạn ngắn cho danh sách (TUI): ('⏰ quá 2 ngày', 'over') · ('hôm nay 17:00', 'today') · ('T6 23/10', 'week')."""
    from .i18n import tr
    d, hm = due_parts(x.get("due") or "")
    if not d:
        return "", ""
    now = now or dt.datetime.now()
    b = "" if x.get("done") else bucket(x, now)
    days = (now.date() - d).days
    t = f" {hm[0]:02d}:{hm[1]:02d}" if hm else ""
    if days == 0:
        s = tr("hôm nay") + t
    elif days == -1:
        s = tr("mai") + t
    elif b == "over" and days <= 3:
        s = tr("quá {n} ngày", n=days)
    else:
        s = f"{tr('T2 T3 T4 T5 T6 T7 CN').split()[d.weekday()]} {d.day:02d}/{d.month:02d}" + t
    return ("⏰ " if b == "over" else "") + s, b
