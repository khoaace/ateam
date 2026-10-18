"""Rule của dự án (/rules): điều mọi agent phải tuân theo, như AGENTS.md của Codex hay .agents/rules của
Antigravity — nhưng ateam tự gửi kèm prompt nên agent nào (kể cả agent tuỳ chỉnh) cũng nhận. Lưu ngoài repo, riêng
máy này: ~/.config/ateam/rules/<tên>-<băm đường dẫn>.json (cùng tên file với to-do).

Mỗi rule: {id, title, text, enabled, targets, created}. targets rỗng = mọi agent; "agent:<tên>" / "role:<vai trò>"
(vai trò của agent ở /setup; role:lead = trưởng nhóm, gồm mọi lượt lập kế hoạch / review / viết commit message)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from . import config, todos
from .i18n import tr

MAX_TITLE = 120
MAX_TEXT = 8000
MAX_RULES = 50
_cache: dict = {}

# file rule CLI tự đọc trong repo (kiểm trên CLI thật 18/10/2026: claude 2.1.302, codex 0.162.1, agy 1.4.2,
# grok 1.0.62, opencode 1.19.3) — chỉ để xem / sửa ở popup /rules, ateam không gửi kèm
NATIVE: list[tuple[str, str]] = [
    ("AGENTS.md", "claude, codex, agy, grok, opencode"),
    ("AGENTS.override.md", "codex"),
    ("CLAUDE.md", "claude, grok, opencode"),
    ("CLAUDE.local.md", "claude"),
    ("GEMINI.md", "agy"),
    (".agents/rules/*.md", "agy"),
    (".claude/rules/*.md", "claude"),
    (".grok/rules/*", "grok"),
]


def path_for(root: Path) -> Path:
    return config.GLOBAL_DIR / "rules" / todos.path_for(root).name


def load(root: Path) -> list[dict]:
    p = path_for(root)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return []
    hit = _cache.get(p)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        items = [x for x in json.loads(p.read_text(encoding="utf-8"))
                 if isinstance(x, dict) and str(x.get("text") or "").strip()]
    except (OSError, ValueError, TypeError):
        items = []
    for x in items:
        x.setdefault("enabled", True)
        x["targets"] = [t for t in x.get("targets") or [] if isinstance(t, str)]
    _cache[p] = (mtime, items)
    return items


def save(root: Path, items: list[dict]) -> None:
    p = path_for(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def apply(root: Path, action: str, d: dict) -> str:
    """Thêm / sửa / bật-tắt / xoá / đổi thứ tự một rule. Trả "" hoặc lý do không làm được."""
    items = [dict(x) for x in load(root)]
    rid = int(d.get("id") or 0)
    i = next((k for k, x in enumerate(items) if x.get("id") == rid), None)
    if action in ("add", "update"):
        title = " ".join(str(d.get("title") or "").split())[:MAX_TITLE]
        text = str(d.get("text") or "").strip()
        if not text:
            return tr("Rule chưa có nội dung")
        if len(text) > MAX_TEXT:
            return tr("Rule dài quá {n} ký tự — tách thành nhiều rule", n=MAX_TEXT)
        targets = [t for t in d.get("targets") or [] if isinstance(t, str) and ":" in t]
        if action == "add":
            if len(items) >= MAX_RULES:
                return tr("Tối đa {n} rule", n=MAX_RULES)
            items.append({"id": max([x.get("id", 0) for x in items] + [0]) + 1, "title": title, "text": text,
                          "enabled": d.get("enabled", True) is not False, "targets": targets,
                          "created": int(time.time())})
        elif i is None:
            return tr("Không còn rule này")
        else:
            items[i].update(title=title, text=text, targets=targets)
            if "enabled" in d:
                items[i]["enabled"] = bool(d["enabled"])
    elif i is None:
        return tr("Không còn rule này")
    elif action == "toggle":
        items[i]["enabled"] = not items[i].get("enabled", True)
    elif action == "delete":
        items.pop(i)
    elif action == "move":
        j = max(0, min(len(items) - 1, i + int(d.get("by") or 0)))
        items.insert(j, items.pop(i))
    else:
        return tr("Không hiểu thao tác {v}", v=action)
    save(root, items)
    return ""


def name_of(rule: dict) -> str:
    return rule.get("title") or str(rule.get("text") or "").strip().splitlines()[0][:60]


def applies(rule: dict, agent: str, role: str, lead: bool) -> bool:
    """Rule có gửi cho lượt này không: agent tên `agent`, vai trò `role`; lead = lượt của trưởng nhóm."""
    if not rule.get("enabled", True):
        return False
    ts = rule.get("targets") or []
    return not ts or f"agent:{agent}" in ts or (role and f"role:{role}" in ts) or (lead and "role:lead" in ts)


def active_for(root: Path, agent: str, role: str = "", lead: bool = False) -> list[dict]:
    return [r for r in load(root) if applies(r, agent, role, lead)]


def block(items: list[dict], updated: bool = False) -> str:
    """Khối rule đặt trước prompt (tiếng Anh như mọi prompt; nội dung rule giữ nguyên chữ người dùng viết)."""
    if not items:
        return ""
    head = ("PROJECT RULES (updated by the user — these replace the earlier project rules):" if updated else
            "PROJECT RULES (set by the user for this project):")
    parts = [head, "Follow every rule below in everything you do for this request. They take priority over your "
                   "own habits and defaults, but do not change any output format this prompt asks for."]
    for n, r in enumerate(items, 1):
        parts.append(f"\n{n}. {r['title']}\n{r['text']}" if r.get("title") else f"\n{n}. {r['text']}")
    return "\n".join(parts) + "\n\n---\n\n"


def digest(items: list[dict]) -> str:
    return hashlib.sha1(json.dumps([[r.get("title"), r.get("text")] for r in items],
                                   ensure_ascii=False).encode()).hexdigest()[:12] if items else ""


def target_choices(cfg) -> list[tuple[str, str]]:
    """(giá trị, nhãn) cho ô "Áp dụng cho": vai trò rồi agent."""
    out = [(f"role:{k}", tr("Vai trò: {v}", v=label)) for k, label, _d in config.ROLES]
    out += [(f"agent:{n}", tr("Agent: {v}", v=n)) for n in cfg.agents]
    return out


def targets_label(rule: dict) -> str:
    ts = rule.get("targets") or []
    if not ts:
        return tr("mọi agent")
    roles = dict((k, label) for k, label, _d in config.ROLES)
    return ", ".join(roles.get(t[5:], t[5:]) if t.startswith("role:") else t.split(":", 1)[-1] for t in ts)


def native_files(root: Path) -> list[dict]:
    """File rule có sẵn trong repo mà CLI tự đọc: {path (tương đối), readers}."""
    root = Path(root)
    out = []
    for pattern, readers in NATIVE:
        for p in sorted(root.glob(pattern)) if "*" in pattern else [root / pattern]:
            if p.is_file():
                out.append({"path": p.relative_to(root).as_posix(), "readers": readers})
    return out
