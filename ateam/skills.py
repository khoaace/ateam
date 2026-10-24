"""Skill (/skills, trang 🧩 Skills): hướng dẫn dùng lại được theo chuẩn Agent Skills (agentskills.io) — thư mục có
SKILL.md (frontmatter `name`, `description` + phần thân markdown, có thể kèm scripts/ references/ assets/).

Mỗi CLI tự đọc skill ở một thư mục riêng nên mỗi thành viên của đội thấy một bộ khác nhau; ateam gom mọi thư mục đó
thành một danh mục, trưởng nhóm gắn skill vào task (`"skills"` trong kế hoạch JSON) hoặc người dùng gõ `$tên`, và
ateam gửi kèm nội dung skill ở đầu prompt (như /rules) — agent nào cũng nhận cùng một bản.

Thư viện riêng của ateam: ~/.config/ateam/skills/<tên>/SKILL.md (không CLI nào tự đọc → không bị nạp trùng). Bật/tắt
theo dự án (chỉ ảnh hưởng danh sách gửi trưởng nhóm; `$tên` dùng được mọi skill): ~/.config/ateam/skill-sets/."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import config, todos
from .i18n import tr

NAME_MAX = 64
DESC_MAX = 1024
INDEX_DESC_MAX = 300  # mô tả trong danh sách gửi trưởng nhóm
BODY_MAX = 24_000  # ký tự phần thân gửi kèm prompt mỗi skill (đặc tả khuyên < ~5000 token)
SCAN_DEPTH = 3  # ~/.claude/skills/synced/<id>/<tên>/SKILL.md
FETCH_TIMEOUT = 120
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MENTION_RE = re.compile(r"(?<![\w$\\])\$([a-z0-9]+(?:-[a-z0-9]+)*)(?![\w-])")

# Thư mục CLI tự đọc skill (kiểm trên binary / log thật 24/10/2026: claude 2.1.310, codex 0.164.0, agy 1.4.7,
# grok 1.0.62, opencode 2.0.32). Thứ tự = ưu tiên khi trùng tên: dự án > thư viện ateam > thư mục CLI.
PROJECT_DIRS: list[tuple[str, str]] = [
    (".agents/skills", "codex, agy, grok"),
    (".claude/skills", "claude, grok, opencode"),
    (".opencode/skills", "opencode"),
    (".opencode/skill", "opencode"),
    (".grok/skills", "grok"),
]
HOME_DIRS: list[tuple[str, str]] = [
    (".claude/skills", "claude, grok, opencode"),
    (".codex/skills", "codex"),
    (".agents/skills", "codex"),
    (".gemini/antigravity/skills", "agy"),
    (".grok/skills", "grok"),
    (".config/opencode/skills", "opencode"),
    (".config/opencode/skill", "opencode"),
]


def library() -> Path:
    return config.GLOBAL_DIR / "skills"


def home_dir() -> Path:
    """Thư mục nhà để tìm skill của các CLI (ATEAM_SKILLS_HOME: test không đọc skill thật của máy)."""
    return Path(os.environ.get("ATEAM_SKILLS_HOME") or Path.home())


# ------------------------------------------------------------------ đọc SKILL.md
def _scalar(v: str) -> str:
    v = v.strip()
    m = re.match(r"^'((?:[^']|'')*)'\s*(?:#.*)?$", v)
    if m:
        return m.group(1).replace("''", "'")
    m = re.match(r'^"((?:[^"\\]|\\.)*)"\s*(?:#.*)?$', v)
    if m:
        return re.sub(r'\\(.)', lambda x: {"n": "\n", "t": "\t"}.get(x.group(1), x.group(1)), m.group(1))
    return re.sub(r"\s+#.*$", "", v)


def _indented(line: str) -> bool:
    return not line.strip() or line[:1] in " \t"


def _yaml(head: str) -> dict:
    """YAML tối giản đủ cho frontmatter của skill: `key: value`, chuỗi có nháy, khối `|` / `>`, map lồng một cấp."""
    out: dict = {}
    lines = head.split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z0-9_-]+):(?:[ \t]+(.*))?$", lines[i].rstrip())
        i += 1
        if not m:
            continue
        key, val = m.group(1), (m.group(2) or "").strip()
        if val[:1] in ("|", ">"):
            block = []
            while i < len(lines) and _indented(lines[i]):
                block.append(lines[i])
                i += 1
            ind = min((len(b) - len(b.lstrip()) for b in block if b.strip()), default=0)
            block = [b[ind:].rstrip() for b in block]
            if val[0] == "|":
                out[key] = "\n".join(block).strip()
            else:  # gấp dòng: dòng liền nhau nối bằng dấu cách, dòng trống = xuống dòng
                paras, cur = [], []
                for b in block + [""]:
                    if b.strip():
                        cur.append(b.strip())
                    elif cur:
                        paras.append(" ".join(cur))
                        cur = []
                out[key] = "\n".join(paras)
        elif not val:
            sub = {}
            while i < len(lines) and _indented(lines[i]):
                mm = re.match(r"^\s+([A-Za-z0-9_.-]+):\s*(.*)$", lines[i])
                i += 1
                if mm:
                    sub[mm.group(1)] = _scalar(mm.group(2))
            out[key] = sub
        else:
            while i < len(lines) and lines[i].strip() and lines[i][:1] in " \t":  # chuỗi thường viết nhiều dòng
                val += " " + lines[i].strip()
                i += 1
            out[key] = _scalar(val)
    return out


def parse(text: str) -> tuple[dict, str]:
    """(frontmatter, phần thân) của SKILL.md; không có frontmatter thì ({}, cả văn bản)."""
    text = text.lstrip("﻿").replace("\r\n", "\n")
    m = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", text, re.S)
    if not m:
        return {}, text
    return _yaml(m.group(1)), text[m.end():].lstrip("\n")


def name_problem(name: str) -> str:
    if not name:
        return tr("Thiếu tên skill")
    if len(name) > NAME_MAX:
        return tr("Tên skill dài quá {n} ký tự", n=NAME_MAX)
    if not NAME_RE.match(name):
        return tr("Tên skill chỉ gồm a-z, 0-9 và dấu gạch nối (không ở đầu/cuối, không hai gạch liền)")
    return ""


# ------------------------------------------------------------------ danh mục
@dataclass
class Skill:
    name: str
    description: str
    file: Path  # SKILL.md (hoặc file .md nằm phẳng)
    source: str  # thư mục nguồn để hiện (~/.claude/skills, thư viện ateam, .agents/skills…)
    kind: str  # "project" | "library" | "cli"
    readers: str = ""  # CLI tự đọc thư mục này
    flat: bool = False
    problems: list = field(default_factory=list)
    others: list = field(default_factory=list)  # bản cùng tên ở nguồn ưu tiên thấp hơn (không dùng)

    @property
    def dir(self) -> Path:
        return self.file.parent

    def body(self) -> str:
        try:
            return parse(self.file.read_text(encoding="utf-8", errors="replace"))[1].strip()
        except OSError:
            return ""

    def text(self) -> str:
        try:
            return self.file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def files(self) -> list[str]:
        if self.flat:
            return [self.file.name]
        out = []
        for p in sorted(self.dir.rglob("*")):
            if p.is_file() and ".git" not in p.parts and p.name != ".DS_Store":
                out.append(p.relative_to(self.dir).as_posix())
            if len(out) >= 200:
                break
        return out

    def has_scripts(self) -> bool:
        return not self.flat and (self.dir / "scripts").is_dir()

    def as_dict(self, on: bool) -> dict:
        return {"name": self.name, "description": self.description, "path": str(self.file),
                "dir": str(self.dir), "source": self.source, "kind": self.kind, "readers": self.readers,
                "flat": self.flat, "problems": list(self.problems), "others": list(self.others),
                "scripts": self.has_scripts(), "on": on, "usable": bool(NAME_RE.match(self.name))}


def _show(p: Path, home: Path) -> str:
    try:
        return "~/" + p.relative_to(home).as_posix()
    except ValueError:
        return str(p)


def _load(file: Path, source: str, kind: str, readers: str, flat: bool = False) -> Skill | None:
    try:
        meta, body = parse(file.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    if flat and not (meta.get("name") or meta.get("description")):
        return None  # README.md… nằm cạnh các skill
    dirname = file.stem if flat else file.parent.name
    name = str(meta.get("name") or "").strip() or dirname
    desc = " ".join(str(meta.get("description") or "").split())
    s = Skill(name=name, description=desc, file=file, source=source, kind=kind, readers="" if flat else readers,
              flat=flat)
    bad = name_problem(name)
    if bad:
        s.problems.append(bad)
    elif not flat and name != dirname:
        s.problems.append(tr("name '{n}' khác tên thư mục '{d}' — CLI có thể không nạp", n=name, d=dirname))
    if not desc:
        s.problems.append(tr("Thiếu description — trưởng nhóm không biết khi nào dùng"))
    elif len(desc) > DESC_MAX:
        s.problems.append(tr("description dài quá {n} ký tự", n=DESC_MAX))
    if flat:
        s.problems.append(tr("File .md nằm phẳng — CLI không nạp (cần <tên>/SKILL.md); nhập vào thư viện để sửa"))
    if len(body) > BODY_MAX:
        s.problems.append(tr("Phần thân dài quá {n} ký tự — chỉ gửi kèm phần đầu", n=BODY_MAX))
    return s


def _scan_dir(base: Path, source: str, kind: str, readers: str) -> list[Skill]:
    out: list[Skill] = []
    if not base.is_dir():
        return out
    try:
        children = sorted(base.iterdir())
    except OSError:
        return out
    for c in children:
        if c.name.startswith("."):  # .system (codex), .disabled, .git
            continue
        if c.is_file() and c.suffix.lower() == ".md":
            s = _load(c, source, kind, readers, flat=True) if c.name != "SKILL.md" else None
            if s:
                out.append(s)
        elif c.is_dir():
            stack = [(c, 1)]
            while stack:
                d, depth = stack.pop(0)
                f = d / "SKILL.md"
                if f.is_file():
                    s = _load(f, source, kind, readers)
                    if s:
                        out.append(s)
                    continue
                if depth < SCAN_DEPTH:
                    try:
                        stack += [(x, depth + 1) for x in sorted(d.iterdir()) if x.is_dir()
                                  and not x.name.startswith(".")]
                    except OSError:
                        pass
    return out


def scan(root: Path | None, home: Path | None = None) -> list[Skill]:
    """Mọi skill tìm được, mỗi tên một bản (bản ở nguồn ưu tiên cao nhất; các bản khác ghi ở `others`)."""
    home = home or home_dir()
    found: list[Skill] = []
    if root:
        for rel, readers in PROJECT_DIRS:
            found += _scan_dir(Path(root) / rel, rel, "project", readers)
    found += _scan_dir(library(), tr("thư viện ateam"), "library", "")
    for rel, readers in HOME_DIRS:
        found += _scan_dir(home / rel, "~/" + rel, "cli", readers)
    seen: dict[str, Skill] = {}
    real: set = set()
    for s in found:
        try:
            key = s.file.resolve()
        except OSError:
            key = s.file
        if key in real:  # cùng một file qua symlink (~/.gemini/antigravity/skills → ~/.gemini/config/skills)
            continue
        real.add(key)
        if s.name in seen:
            seen[s.name].others.append(_show(s.file, home))
        else:
            seen[s.name] = s
    return list(seen.values())


def find(items: list[Skill], name: str) -> Skill | None:
    return next((s for s in items if s.name == name), None)


# ------------------------------------------------------------------ bật / tắt theo dự án
def sets_path(root: Path) -> Path:
    return todos.path_for(root, "skill-sets")


def load_sets(root: Path) -> dict:
    try:
        d = json.loads(sets_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {"on": [x for x in d.get("on") or [] if isinstance(x, str)],
            "off": [x for x in d.get("off") or [] if isinstance(x, str)]}


def is_on(s: Skill, sets: dict) -> bool:
    """Mặc định bật skill của dự án và thư viện ateam; skill trong thư mục CLI tắt (danh sách gửi trưởng nhóm không
    phình) — người dùng bật từng cái."""
    if s.name in sets["on"]:
        return True
    return s.name not in sets["off"] and s.kind != "cli"


def set_on(root: Path, name: str, on: bool) -> None:
    sets = load_sets(root)
    sets["on"] = [x for x in sets["on"] if x != name] + ([name] if on else [])
    sets["off"] = [x for x in sets["off"] if x != name] + ([] if on else [name])
    p = sets_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(sets, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def enabled(root: Path, items: list[Skill] | None = None) -> list[Skill]:
    items = scan(root) if items is None else items
    sets = load_sets(root)
    return [s for s in items if is_on(s, sets) and NAME_RE.match(s.name) and s.description]


# ------------------------------------------------------------------ gửi kèm prompt
def mentioned(text: str, items: list[Skill]) -> list[Skill]:
    """Skill người dùng gọi bằng `$tên` (chỉ tên có trong danh mục — `$PATH`, `${x}` không tính)."""
    out: list[Skill] = []
    for m in MENTION_RE.finditer(text or ""):
        s = find(items, m.group(1))
        if s and s not in out:
            out.append(s)
    return out


def resolve(names, items: list[Skill]) -> list[Skill]:
    out: list[Skill] = []
    for n in names or []:
        s = find(items, str(n).strip().lstrip("$"))
        if s and s not in out:
            out.append(s)
    return out


def index_block(items: list[Skill]) -> str:
    """Danh sách skill đang bật cho trưởng nhóm lúc lập kế hoạch (tên + mô tả, không có phần thân)."""
    if not items:
        return ""
    lines = ["AVAILABLE SKILLS (reusable instructions installed by the user; a task receives a skill's full text"
             " only if you attach it):"]
    for s in sorted(items, key=lambda x: x.name):
        d = s.description if len(s.description) <= INDEX_DESC_MAX else s.description[:INDEX_DESC_MAX].rstrip() + "…"
        lines.append(f"- {s.name}: {d}")
    lines.append('To use skills, add "skills": ["<name>", ...] to a task — only when a skill\'s description clearly'
                 " matches that task, at most 2 per task. Do not copy skill text into task prompts.")
    return "\n".join(lines)


def body_block(items: list[Skill], head: str = "SKILLS FOR THIS TASK", sep: bool = True) -> str:
    """Nội dung các skill gắn với lượt này, đặt trước prompt (như khối rule); sep=False: không kèm dòng ngăn cuối
    (khối nằm giữa prompt lập kế hoạch)."""
    if not items:
        return ""
    parts = [f"{head} — follow these instructions while you work. Files a skill mentions are relative to its"
             " folder."]
    for s in items:
        body = s.body()
        if len(body) > BODY_MAX:
            body = body[:BODY_MAX].rstrip() + f"\n… (truncated — read the rest in {s.file})"
        parts.append(f"\n=== SKILL: {s.name} (folder: {s.dir}) ===\n{body}")
    return "\n".join(parts) + ("\n\n---\n\n" if sep else "")


# ------------------------------------------------------------------ thư viện ateam
def render(name: str, description: str, body: str) -> str:
    desc = json.dumps(" ".join(description.split()), ensure_ascii=False)
    return f"---\nname: {name}\ndescription: {desc}\n---\n\n{body.strip()}\n"


def check(name: str, description: str, body: str) -> str:
    bad = name_problem(name)
    if bad:
        return bad
    if not " ".join(description.split()):
        return tr("Thiếu mô tả (description): skill làm gì và khi nào dùng")
    if len(" ".join(description.split())) > DESC_MAX:
        return tr("description dài quá {n} ký tự", n=DESC_MAX)
    if not body.strip():
        return tr("Skill chưa có nội dung")
    return ""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def create(name: str, description: str, body: str, overwrite: bool = False) -> str:
    """Tạo skill trong thư viện ateam. Trả "" hoặc lý do không làm được."""
    name = name.strip()
    bad = check(name, description, body)
    if bad:
        return bad
    d = library() / name
    if d.exists() and not overwrite:
        return tr("Đã có skill '{n}' trong thư viện", n=name)
    _write(d / "SKILL.md", render(name, description, body))
    return ""


def update(name: str, text: str) -> str:
    """Ghi lại SKILL.md của skill trong thư viện (giữ mọi khoá frontmatter khác như license / metadata)."""
    f = library() / name / "SKILL.md"
    if not f.is_file():
        return tr("Không còn skill '{n}' trong thư viện", n=name)
    meta, body = parse(text)
    if str(meta.get("name") or "").strip() != name:
        return tr("name trong frontmatter phải là '{n}' (trùng tên thư mục)", n=name)
    bad = check(name, str(meta.get("description") or ""), body)
    if bad:
        return bad
    _write(f, text.replace("\r\n", "\n"))
    return ""


async def delete(name: str) -> str:
    from .palette import file_trash
    if not NAME_RE.match(name) or not (library() / name).is_dir():
        return tr("Không còn skill '{n}' trong thư viện", n=name)
    return await file_trash(library(), name, dirs=True)


def import_skill(s: Skill, overwrite: bool = False) -> str:
    """Chép skill (của CLI / dự án) vào thư viện ateam để sửa / dùng làm bản chính. File .md nằm phẳng thành
    <tên>/SKILL.md."""
    bad = name_problem(s.name)
    if bad:
        return bad
    dest = library() / s.name
    if s.kind == "library":
        return tr("Skill này đã ở trong thư viện")
    if dest.exists():
        if not overwrite:
            return tr("Đã có skill '{n}' trong thư viện", n=s.name)
        shutil.rmtree(dest)
    if s.flat:
        _write(dest / "SKILL.md", s.text())
    else:
        shutil.copytree(s.dir, dest, symlinks=False, ignore=shutil.ignore_patterns(".git", ".DS_Store"))
    return ""


# ------------------------------------------------------------------ cài từ GitHub / git
PENDING: dict[str, dict] = {}  # token → {"tmp", "at", "skills", "url", "commit"}
PENDING_TTL = 30 * 60


def parse_source(url: str) -> tuple[str, str, str]:
    """(URL để clone, nhánh/tag, thư mục con) từ `owner/repo`, link GitHub (kể cả …/tree/<nhánh>/<thư mục>) hoặc
    git URL bất kỳ."""
    url = url.strip()
    if re.match(r"^[\w.-]+/[\w.-]+$", url) and not url.startswith("."):
        return f"https://github.com/{re.sub(r'[.]git$', '', url)}.git", "", ""
    m = re.match(r"^https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/tree/([^/]+)(?:/(.+?))?)?/?$", url)
    if m:
        return f"https://github.com/{m.group(1)}/{m.group(2)}.git", m.group(3) or "", m.group(4) or ""
    return url, "", ""


def _cleanup() -> None:
    now = time.time()
    for tok, p in list(PENDING.items()):
        if now - p["at"] > PENDING_TTL:
            discard(tok)


def discard(token: str) -> None:
    p = PENDING.pop(token, None)
    if p:
        shutil.rmtree(p["tmp"], ignore_errors=True)


async def _run(*args: str, cwd: Path | None = None, timeout: float = FETCH_TIMEOUT) -> tuple[int, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"  # repo riêng tư: báo lỗi thay vì treo chờ mật khẩu
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    proc = await asyncio.create_subprocess_exec(*args, cwd=str(cwd) if cwd else None, env=env,
                                                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, tr("hết {n} giây", n=int(timeout))
    return proc.returncode or 0, out.decode("utf-8", "replace")


async def fetch(url: str) -> tuple[str, list[dict], str]:
    """Clone (depth 1) repo vào thư mục tạm, tìm các skill. Trả (token, skill tìm được, lỗi)."""
    _cleanup()
    if not url.strip():
        return "", [], tr("Dán link repo GitHub (vd anthropics/skills)")
    if not shutil.which("git"):
        return "", [], tr("Cần cài git để tải skill")
    src, ref, sub = parse_source(url)
    tmp = Path(tempfile.mkdtemp(prefix="ateam-skills-")).resolve()  # macOS: /var → /private/var
    repo = tmp / "repo"
    rc, out = await _run("git", "clone", "--depth", "1", "--quiet", *(["--branch", ref] if ref else []),
                         src, str(repo))
    if rc != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return "", [], tr("Không tải được {u}: {e}", u=src, e=out.strip()[-300:])
    _, commit = await _run("git", "rev-parse", "HEAD", cwd=repo, timeout=10)
    base = (repo / sub).resolve()
    if repo.resolve() not in [base, *base.parents] or not base.is_dir():
        shutil.rmtree(tmp, ignore_errors=True)
        return "", [], tr("Không có thư mục {p} trong repo", p=sub)
    found = []
    for f in sorted(base.rglob("SKILL.md")):
        if ".git" in f.relative_to(repo).parts or len(f.relative_to(base).parts) > 6:
            continue
        s = _load(f, src, "remote", "")
        if not s:
            continue
        found.append({"name": s.name, "description": s.description, "path": f.parent.relative_to(repo).as_posix(),
                      "files": len(s.files()), "scripts": s.has_scripts(), "problems": s.problems,
                      "exists": (library() / s.name).exists(), "usable": not name_problem(s.name)})
    if not found:
        shutil.rmtree(tmp, ignore_errors=True)
        return "", [], tr("Không tìm thấy SKILL.md nào trong {u}", u=url.strip())
    token = uuid.uuid4().hex
    PENDING[token] = {"tmp": tmp, "at": time.time(), "skills": found, "url": src, "ref": ref,
                      "commit": commit.strip()}
    return token, found, ""


async def install(token: str, names: list[str], overwrite: bool = False) -> tuple[list[str], list[str]]:
    """Chép các skill đã chọn từ lần fetch vào thư viện. Trả (đã cài, lỗi)."""
    p = PENDING.get(token)
    if not p:
        return [], [tr("Phiên tải đã hết hạn — tải lại")]
    done, errs = [], []
    repo = p["tmp"] / "repo"
    for item in p["skills"]:
        if item["name"] not in names:
            continue
        if not item["usable"]:
            errs.append(f"{item['name']}: {name_problem(item['name'])}")
            continue
        dest = library() / item["name"]
        if dest.exists() and not overwrite:
            errs.append(tr("Đã có skill '{n}' trong thư viện", n=item["name"]))
            continue

        def copy(src=repo / item["path"], dest=dest, item=item) -> None:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git", ".DS_Store"))
            (dest / ".ateam-source.json").write_text(json.dumps(
                {"url": p["url"], "ref": p["ref"], "path": item["path"], "commit": p["commit"],
                 "installed": int(time.time())}, indent=2), encoding="utf-8")
        try:
            await asyncio.to_thread(copy)
            done.append(item["name"])
        except OSError as e:
            errs.append(f"{item['name']}: {e}")
    discard(token)
    return done, errs
