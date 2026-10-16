"""Quản lý git của dự án (tab 🌿 Git, lệnh /git): trạng thái, stage/unstage/bỏ thay đổi, commit, nhánh,
lịch sử, fetch/pull/push, stash. Không phụ thuộc Textual để test được riêng; mọi lệnh git chạy qua asyncio
(không treo vòng lặp sự kiện), không bao giờ hỏi mật khẩu trên terminal (GIT_TERMINAL_PROMPT=0).
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from .i18n import tr

NET_TIMEOUT = 120      # giây cho fetch/pull/push (mạng chậm, hỏi credential helper…)
LOCAL_TIMEOUT = 30
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # cây rỗng: "cha" của commit đầu tiên
BRANCH_RE = re.compile(r"^(?!/)(?!.*\.\.)(?!.*//)(?!.*@\{)[^\s~^:?*\[\\]+(?<!\.lock)(?<![/.])$")
LOG_SEP = "\x1f"


@dataclass
class FileChange:
    """Một file trong `git status`. index/work: mã trạng thái phía index (đã stage) và thư mục làm việc,
    '.' = không đổi, như porcelain v2 (M sửa, A thêm, D xoá, R đổi tên, C chép, T đổi kiểu)."""
    path: str
    index: str = "."
    work: str = "."
    orig: str = ""           # tên cũ khi đổi tên
    kind: str = "1"          # 1 thường · 2 đổi tên/chép · u xung đột · ? chưa theo dõi

    @property
    def untracked(self) -> bool:
        return self.kind == "?"

    @property
    def conflicted(self) -> bool:
        return self.kind == "u"

    @property
    def staged(self) -> bool:
        return self.kind in ("1", "2") and self.index != "."

    @property
    def unstaged(self) -> bool:
        return self.untracked or (self.kind in ("1", "2") and self.work != ".")


@dataclass
class RepoStatus:
    is_repo: bool = False
    branch: str = ""             # "" khi detached HEAD
    oid: str = ""                # commit HEAD ("" khi chưa có commit nào)
    upstream: str = ""
    ahead: int = 0
    behind: int = 0
    files: list[FileChange] = field(default_factory=list)
    stashes: int = 0
    state: str = ""              # merge · rebase · cherry-pick · revert · "" (bình thường)
    error: str = ""

    @property
    def detached(self) -> bool:
        return self.is_repo and not self.branch and bool(self.oid)

    @property
    def staged(self) -> list[FileChange]:
        return [f for f in self.files if f.staged]

    @property
    def unstaged(self) -> list[FileChange]:
        return [f for f in self.files if f.unstaged and not f.untracked]

    @property
    def untracked(self) -> list[FileChange]:
        return [f for f in self.files if f.untracked]

    @property
    def conflicts(self) -> list[FileChange]:
        return [f for f in self.files if f.conflicted]

    @property
    def clean(self) -> bool:
        return not self.files


@dataclass
class Branch:
    name: str
    current: bool = False
    remote: bool = False
    upstream: str = ""
    track: str = ""              # "[ahead 1, behind 2]" / "[gone]"
    subject: str = ""
    date: str = ""


@dataclass
class Commit:
    sha: str
    short: str
    author: str
    date: str                    # tương đối ("2 hours ago")
    subject: str
    refs: str = ""
    parents: list[str] = field(default_factory=list)


@dataclass
class Stash:
    ref: str                     # stash@{0}
    subject: str
    date: str = ""


def parse_status(text: str) -> RepoStatus:
    """Bóc `git status --porcelain=v2 --branch -z`."""
    st = RepoStatus(is_repo=True)
    parts = text.split("\0")
    i = 0
    while i < len(parts):
        rec = parts[i]
        i += 1
        if not rec:
            continue
        if rec.startswith("# "):
            key, _, val = rec[2:].partition(" ")
            if key == "branch.oid":
                st.oid = "" if val == "(initial)" else val
            elif key == "branch.head":
                st.branch = "" if val == "(detached)" else val
            elif key == "branch.upstream":
                st.upstream = val
            elif key == "branch.ab":
                m = re.match(r"\+(\d+) -(\d+)", val)
                if m:
                    st.ahead, st.behind = int(m.group(1)), int(m.group(2))
            elif key == "stash":
                st.stashes = int(val) if val.isdigit() else 0
            continue
        kind = rec[0]
        if kind == "1":
            f = rec.split(" ", 8)
            if len(f) == 9:
                st.files.append(FileChange(f[8], f[1][0], f[1][1], kind="1"))
        elif kind == "2":
            f = rec.split(" ", 9)
            orig = parts[i] if i < len(parts) else ""
            i += 1
            if len(f) == 10:
                st.files.append(FileChange(f[9], f[1][0], f[1][1], orig=orig, kind="2"))
        elif kind == "u":
            f = rec.split(" ", 10)
            if len(f) == 11:
                st.files.append(FileChange(f[10], f[1][0], f[1][1], kind="u"))
        elif kind == "?":
            st.files.append(FileChange(rec[2:], "?", "?", kind="?"))
    return st


def parse_log(text: str) -> list[Commit]:
    out = []
    for line in text.splitlines():
        p = line.split(LOG_SEP)
        if len(p) >= 7:
            out.append(Commit(sha=p[0], short=p[1], author=p[2], date=p[3], refs=p[4].strip(),
                              parents=p[5].split(), subject=LOG_SEP.join(p[6:])))
    return out


def parse_branches(text: str) -> list[Branch]:
    out = []
    for line in text.splitlines():
        p = line.split(LOG_SEP)
        if len(p) < 6:
            continue
        ref, head, upstream, track, date, subject = p[:6]
        if ref.startswith("refs/heads/"):
            out.append(Branch(ref[len("refs/heads/"):], current=head.strip() == "*", upstream=upstream,
                              track=track, subject=subject, date=date))
        elif ref.startswith("refs/remotes/") and not ref.endswith("/HEAD"):
            out.append(Branch(ref[len("refs/remotes/"):], remote=True, subject=subject, date=date))
    return out


def parse_stashes(text: str) -> list[Stash]:
    out = []
    for line in text.splitlines():
        p = line.split(LOG_SEP)
        if len(p) >= 3:
            out.append(Stash(p[0], p[2], p[1]))
    return out


def valid_branch_name(name: str) -> bool:
    return bool(name) and not name.startswith("-") and bool(BRANCH_RE.match(name))


def short_error(out: str, limit: int = 300) -> str:
    """Dòng có ích nhất của output lỗi git (bỏ dòng 'hint:')."""
    lines = [ln.strip() for ln in out.splitlines() if ln.strip() and not ln.startswith("hint:")]
    msg = " · ".join(lines[-3:]) if lines else tr("lỗi không rõ")
    return msg[:limit]


class GitRepo:
    """Thao tác git trên thư mục dự án. Các hàm thay đổi trạng thái trả về (thành công, lời nhắn)."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._ident: list[str] | None = None
        self._git_dir: Path | None = None
        self._lock: asyncio.Lock | None = None

    @property
    def lock(self) -> asyncio.Lock:
        """Không chạy hai lệnh thay đổi repo cùng lúc (bấm nút liên tục). Tạo khi dùng lần đầu, trong vòng
        lặp — Python 3.9 gắn Lock vào event loop lúc tạo."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def run(self, *args: str, timeout: float = LOCAL_TIMEOUT,
                  stdin: bytes | None = None) -> tuple[int, str]:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"     # không hỏi user/mật khẩu trong terminal của TUI (sẽ treo)
        env.setdefault("GIT_EDITOR", "true")  # merge/revert không mở trình soạn thảo
        env["LANGUAGE"] = "C"  # thông báo của git bằng tiếng Anh, ổn định để dò (CONFLICT, rejected…)
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "-c", "core.quotePath=false", *args, cwd=str(self.root),
                stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env)
        except FileNotFoundError:
            return 127, tr("Chưa cài git")
        try:
            out, _ = await asyncio.wait_for(proc.communicate(stdin), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return 124, tr("git {v} quá {v2} giây — đã dừng", v=args[0] if args else '', v2=int(timeout))
        return proc.returncode, out.decode("utf-8", "replace")

    async def ident(self) -> list[str]:
        """Như Orchestrator.git_ident: máy chưa cấu hình user.email vẫn commit được."""
        if self._ident is None:
            rc, email = await self.run("config", "user.email")
            self._ident = ([] if rc == 0 and email.strip() else
                           ["-c", "user.name=ateam", "-c", "user.email=ateam@localhost"])
        return self._ident

    async def _do(self, ok_msg: str, *args: str, timeout: float = LOCAL_TIMEOUT,
                  ident: bool = False) -> tuple[bool, str]:
        pre = await self.ident() if ident else []
        async with self.lock:
            rc, out = await self.run(*pre, *args, timeout=timeout)
        return (True, ok_msg) if rc == 0 else (False, short_error(out))

    # ------------------------------------------------------------------ đọc
    async def status(self) -> RepoStatus:
        rc, out = await self.run("status", "--porcelain=v2", "--branch", "--show-stash", "-z",
                                 "--untracked-files=all")
        if rc != 0:
            low = out.lower()
            if "not a git repository" in low or rc == 127:
                return RepoStatus(is_repo=False, error=short_error(out))
            # git cũ (< 2.35) chưa có --show-stash
            rc, out = await self.run("status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all")
            if rc != 0:
                return RepoStatus(is_repo=False, error=short_error(out))
        st = parse_status(out)
        if not st.stashes:
            rc, n = await self.run("rev-list", "--walk-reflogs", "--count", "refs/stash")
            st.stashes = int(n.strip()) if rc == 0 and n.strip().isdigit() else 0
        st.state = await self._op_state()
        return st

    async def _op_state(self) -> str:
        """merge/rebase/cherry-pick/revert đang dở, đọc từ file trạng thái trong thư mục .git."""
        if self._git_dir is None:
            rc, p = await self.run("rev-parse", "--absolute-git-dir")
            if rc != 0 or not p.strip():
                return ""
            self._git_dir = Path(p.strip())
        for name, label in (("MERGE_HEAD", "merge"), ("rebase-merge", "rebase"), ("rebase-apply", "rebase"),
                            ("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert")):
            if (self._git_dir / name).exists():
                return label
        return ""

    async def log(self, n: int = 50, ref: str = "", path: str = "") -> list[Commit]:
        fmt = LOG_SEP.join(["%H", "%h", "%an", "%ar", "%D", "%P", "%s"])
        args = ["log", f"-n{n}", f"--format={fmt}"]
        if ref:
            args.append(ref)
        if path:
            args += ["--", path]
        rc, out = await self.run(*args)
        return parse_log(out) if rc == 0 else []

    async def branches(self, remote: bool = True) -> list[Branch]:
        fmt = LOG_SEP.join(["%(refname)", "%(HEAD)", "%(upstream:short)", "%(upstream:track)",
                            "%(committerdate:relative)", "%(contents:subject)"])
        refs = ["refs/heads"] + (["refs/remotes"] if remote else [])
        rc, out = await self.run("for-each-ref", "--sort=-committerdate", f"--format={fmt}", *refs)
        return parse_branches(out) if rc == 0 else []

    async def stashes(self) -> list[Stash]:
        rc, out = await self.run("stash", "list", f"--format=%gd{LOG_SEP}%cr{LOG_SEP}%gs")
        return parse_stashes(out) if rc == 0 else []

    async def remotes(self) -> list[str]:
        rc, out = await self.run("remote")
        return out.split() if rc == 0 else []

    async def diff_text(self, *args: str) -> str:
        rc, out = await self.run("diff", "-M", "--no-color", *args)
        return out if rc == 0 else ""

    async def staged_diff(self, limit: int = 60_000) -> str:
        """Diff đã stage (cho trưởng nhóm viết commit message), cắt bớt nếu quá dài."""
        stat = await self.diff_text("--cached", "--stat")
        body = await self.diff_text("--cached")
        if len(body) > limit:
            body = body[:limit] + tr("\n… (diff đã được cắt bớt)")
        return (stat + "\n" + body).strip()

    # ------------------------------------------------------------------ diff cho màn hình xem diff
    async def changes_diffset(self, staged: bool, title: str = ""):
        """DiffSet cho DiffScreen: thay đổi đã stage (HEAD→index) hoặc chưa stage (index→thư mục, kèm
        file chưa theo dõi). base "" = index (git show :path), head None = file trong thư mục."""
        from .diffview import DiffSet, parse_unified
        if staged:
            files = parse_unified(await self.diff_text("--cached"))
            return DiffSet(0, title or tr("Thay đổi đã stage"), files, "HEAD", "")
        files = parse_unified(await self.diff_text())
        rc, others = await self.run("ls-files", "--others", "--exclude-standard", "-z")
        for path in [p for p in others.split("\0") if p] if rc == 0 else []:
            files.append(untracked_file(self.root, path))
        return DiffSet(0, title or tr("Thay đổi chưa stage"), files, "", None)

    async def commit_diffset(self, c: "Commit"):
        from .diffview import DiffSet, parse_unified
        parent = await self.commit_parent(c.sha)
        files = parse_unified(await self.diff_text(parent, c.sha))
        return DiffSet(0, f"Commit {c.short} · {c.subject}", files, parent, c.sha)

    # ------------------------------------------------------------------ thư mục làm việc
    async def init(self) -> tuple[bool, str]:
        self._git_dir = None
        return await self._do(tr("Đã tạo git repo"), "init")

    async def stage(self, paths: list[str]) -> tuple[bool, str]:
        if not paths:
            return False, tr("Không có file nào để stage")
        return await self._do(tr("Đã stage {v} file", v=len(paths)), "add", "-A", "--", *paths)

    async def stage_all(self) -> tuple[bool, str]:
        return await self._do(tr("Đã stage mọi thay đổi"), "add", "-A")

    async def unstage(self, paths: list[str] | None = None) -> tuple[bool, str]:
        st = await self.status()
        paths = paths or [f.path for f in st.staged]
        if not paths:
            return False, tr("Không có file nào đã stage")
        if not st.oid:  # chưa có commit: không có HEAD để reset về
            return await self._do(tr("Đã bỏ stage {v} file", v=len(paths)), "rm", "--cached", "-r", "-q", "--", *paths)
        extra = [f.orig for f in st.files if f.kind == "2" and f.path in paths and f.orig]
        return await self._do(tr("Đã bỏ stage {v} file", v=len(paths)), "reset", "-q", "HEAD", "--", *paths, *extra)

    async def discard(self, paths: list[str]) -> tuple[bool, str]:
        """Bỏ thay đổi CHƯA stage của file (file chưa theo dõi bị xoá). Không thể hoàn tác."""
        st = await self.status()
        by = {f.path: f for f in st.files}
        untracked = [p for p in paths if p in by and by[p].untracked]
        tracked = [p for p in paths if p in by and not by[p].untracked and by[p].work != "."]
        if not untracked and not tracked:
            return False, tr("Không có thay đổi chưa stage nào để bỏ")
        async with self.lock:
            if tracked:
                rc, out = await self.run("checkout", "--", *tracked)
                if rc != 0:
                    return False, short_error(out)
            if untracked:
                rc, out = await self.run("clean", "-f", "-q", "--", *untracked)
                if rc != 0:
                    return False, short_error(out)
        return True, tr("Đã bỏ thay đổi của {v} file", v=len(tracked) + len(untracked))

    async def commit(self, message: str, amend: bool = False, all_changes: bool = False,
                     no_verify: bool = False) -> tuple[bool, str]:
        """no_verify: `git commit --no-verify` — bỏ qua hook pre-commit/commit-msg (husky, lint-staged…)."""
        message = message.strip()
        if not message and not amend:
            return False, tr("Chưa có nội dung commit")
        st = await self.status()
        if st.conflicts:
            return False, tr("Còn {v} file xung đột — sửa xong rồi stage trước khi commit", v=len(st.conflicts))
        if all_changes and not st.staged:
            ok, msg = await self.stage_all()
            if not ok:
                return ok, msg
            st = await self.status()
        if not st.staged and not amend and st.state != "merge":
            return False, (tr("Chưa stage file nào — bấm Space ở file cần commit, hoặc 'a' để "
                              "stage tất cả")
                           if st.files else tr("Không có thay đổi nào để commit"))
        args = ["commit", "-q"]
        if no_verify:
            args.append("--no-verify")
        if amend:
            args.append("--amend")
            args += ["-m", message] if message else ["--no-edit"]
        else:
            args += ["-m", message]
        pre = await self.ident()
        async with self.lock:
            rc, out = await self.run(*pre, *args)
        if rc != 0:
            msg = short_error(out)
            if not no_verify and await self.has_commit_hooks():
                msg += tr(" — nếu do git hook chặn: tick 'Bỏ qua hook' hoặc /commit --no-verify "
                          "<message>")
            return False, msg
        _, sha = await self.run("rev-parse", "--short", "HEAD")
        skipped = tr(" (bỏ qua hook)") if no_verify else ""
        return True, (tr("Đã sửa commit trước ({v}){skipped}", v=sha.strip(), skipped=skipped) if amend
                      else tr("Đã commit {v}{skipped}", v=sha.strip(), skipped=skipped))

    async def has_commit_hooks(self) -> bool:
        """Repo có hook chạy khi commit (pre-commit, commit-msg…) — kể cả core.hooksPath của husky."""
        rc, p = await self.run("rev-parse", "--git-path", "hooks")
        dirs = [p.strip()] if rc == 0 and p.strip() else []
        rc, hp = await self.run("config", "core.hooksPath")
        if rc == 0 and hp.strip():
            dirs.insert(0, hp.strip())
        for d in dirs:
            path = Path(d) if Path(d).is_absolute() else self.root / d
            for name in ("pre-commit", "prepare-commit-msg", "commit-msg"):
                if (path / name).is_file():
                    return True
        return False

    async def last_message(self) -> str:
        rc, out = await self.run("log", "-1", "--format=%B")
        return out.strip() if rc == 0 else ""

    # ------------------------------------------------------------------ nhánh
    async def checkout(self, name: str) -> tuple[bool, str]:
        """Chuyển nhánh; nhánh remote (origin/x) thì tạo nhánh local theo dõi nó."""
        local = {b.name for b in await self.branches(remote=False)}
        if name not in local and "/" in name:
            remote_names = await self.remotes()
            rem, _, short = name.partition("/")
            if rem in remote_names and short:
                if short in local:
                    return await self._do(tr("Đã chuyển sang {short}", short=short), "checkout", "-q", short)
                return await self._do(tr("Đã tạo nhánh {short} theo dõi {name}", short=short, name=name), "checkout", "-q", "--track", name)
        return await self._do(tr("Đã chuyển sang {name}", name=name), "checkout", "-q", name)

    async def create_branch(self, name: str, start: str = "", switch: bool = True) -> tuple[bool, str]:
        name = name.strip()
        if not valid_branch_name(name):
            return False, tr("Tên nhánh không hợp lệ: '{name}'", name=name)
        if switch:
            return await self._do(tr("Đã tạo và chuyển sang nhánh {name}", name=name), "checkout", "-q", "-b", name,
                                  *([start] if start else []))
        return await self._do(tr("Đã tạo nhánh {name}", name=name), "branch", name, *([start] if start else []))

    async def rename_branch(self, old: str, new: str) -> tuple[bool, str]:
        if not valid_branch_name(new):
            return False, tr("Tên nhánh không hợp lệ: '{new}'", new=new)
        return await self._do(tr("Đã đổi tên {old} → {new}", old=old, new=new), "branch", "-m", old, new)

    async def delete_branch(self, name: str, force: bool = False) -> tuple[bool, str]:
        ok, msg = await self._do(tr("Đã xoá nhánh {name}", name=name), "branch", "-D" if force else "-d", name)
        if not ok and "not fully merged" in msg:
            return False, tr("Nhánh {name} còn commit chưa merge — xoá hẳn (mất các commit đó) "
                             "bằng nút 'Xoá hẳn'", name=name)
        return ok, msg

    async def merge(self, name: str) -> tuple[bool, str]:
        pre = await self.ident()
        async with self.lock:
            rc, out = await self.run(*pre, "merge", "--no-edit", name)
        if rc == 0:
            return True, (tr("Đã cập nhật, không có gì mới") if "Already up to date" in out
                          else tr("Đã merge {name} vào nhánh hiện tại", name=name))
        if "CONFLICT" in out:
            n = out.count("CONFLICT")
            return False, (tr("Merge {name} có {n} file xung đột — sửa file rồi stage và commit, "
                              "hoặc 'Huỷ merge'", name=name, n=n))
        return False, short_error(out)

    async def abort(self) -> tuple[bool, str]:
        """Huỷ merge/rebase/cherry-pick/revert đang dở."""
        state = await self._op_state()
        if not state:
            return False, tr("Không có merge/rebase nào đang dở")
        return await self._do(tr("Đã huỷ {state}", state=state), state, "--abort")

    # ------------------------------------------------------------------ remote
    async def fetch(self) -> tuple[bool, str]:
        if not await self.remotes():
            return False, tr("Repo chưa có remote nào (git remote add origin <url>)")
        return await self._do(tr("Đã fetch mọi remote"), "fetch", "--all", "--prune", timeout=NET_TIMEOUT)

    async def pull(self) -> tuple[bool, str]:
        st = await self.status()
        if not st.upstream:
            return False, (tr("Nhánh {v} chưa có upstream — Push trước để tạo nhánh trên remote", v=st.branch or '(detached)'))
        pre = await self.ident()
        async with self.lock:
            rc, out = await self.run(*pre, "pull", "--ff-only", timeout=NET_TIMEOUT)
            if rc != 0 and ("Not possible to fast-forward" in out or "diverg" in out):
                # hai bên cùng có commit mới: merge (không rebase — không viết lại lịch sử người dùng)
                rc, out = await self.run(*pre, "pull", "--no-rebase", "--no-edit", timeout=NET_TIMEOUT)
        if rc == 0:
            return True, tr("Đã cập nhật, không có gì mới") if "Already up to date" in out else tr("Đã pull")
        if "CONFLICT" in out:
            return False, tr("Pull bị xung đột — sửa file rồi stage và commit, hoặc 'Huỷ merge'")
        return False, short_error(out)

    async def push(self, force: bool = False) -> tuple[bool, str]:
        st = await self.status()
        if not st.branch:
            return False, tr("Đang ở detached HEAD — tạo nhánh trước khi push")
        args = ["push"]
        if force:
            args.append("--force-with-lease")
        if not st.upstream:
            remotes = await self.remotes()
            if not remotes:
                return False, tr("Repo chưa có remote nào (git remote add origin <url>)")
            remote = "origin" if "origin" in remotes else remotes[0]
            args += ["-u", remote, st.branch]
        async with self.lock:
            rc, out = await self.run(*args, timeout=NET_TIMEOUT)
        if rc == 0:
            return True, tr("Đã cập nhật, không có gì mới") if "Everything up-to-date" in out else tr("Đã push {branch}", branch=st.branch)
        if "rejected" in out and ("fetch first" in out or "non-fast-forward" in out):
            return False, tr("Remote có commit mới hơn — Pull trước rồi push lại")
        return False, short_error(out)

    # ------------------------------------------------------------------ stash
    async def stash_push(self, message: str = "", untracked: bool = True) -> tuple[bool, str]:
        st = await self.status()
        if st.clean:
            return False, tr("Không có thay đổi nào để stash")
        args = ["stash", "push"]
        if untracked:
            args.append("--include-untracked")
        if message:
            args += ["-m", message]
        return await self._do(tr("Đã cất thay đổi vào stash"), *args, ident=True)

    async def stash_apply(self, ref: str = "stash@{0}", pop: bool = True) -> tuple[bool, str]:
        pre = await self.ident()
        async with self.lock:
            rc, out = await self.run(*pre, "stash", "pop" if pop else "apply", ref)
        if rc == 0:
            return True, tr("Đã lấy lại {ref}", ref=ref) + ("" if pop else tr(" (vẫn giữ trong stash)"))
        if "CONFLICT" in out:
            return False, tr("Lấy {ref} bị xung đột — sửa file rồi stage; stash vẫn được giữ", ref=ref)
        return False, short_error(out)

    async def stash_drop(self, ref: str) -> tuple[bool, str]:
        return await self._do(tr("Đã xoá {ref}", ref=ref), "stash", "drop", ref)

    # ------------------------------------------------------------------ lịch sử
    async def revert(self, sha: str) -> tuple[bool, str]:
        pre = await self.ident()
        async with self.lock:
            rc, out = await self.run(*pre, "revert", "--no-edit", sha)
        if rc == 0:
            return True, tr("Đã tạo commit đảo ngược {v}", v=sha[:8])
        if "CONFLICT" in out:
            return False, tr("Revert bị xung đột — sửa file rồi stage và commit, hoặc 'Huỷ revert'")
        return False, short_error(out)

    async def reset_soft(self) -> tuple[bool, str]:
        """Bỏ commit cuối nhưng giữ thay đổi (đã stage) — "undo commit"."""
        st = await self.status()
        rc, _ = await self.run("rev-parse", "--verify", "-q", "HEAD~1")
        if rc != 0:
            return False, tr("Không có commit trước để quay về")
        if st.upstream and st.ahead == 0:
            return False, tr("Commit cuối đã push lên remote — dùng Revert thay vì bỏ commit")
        return await self._do(tr("Đã bỏ commit cuối, thay đổi vẫn giữ (đã stage)"), "reset", "--soft", "HEAD~1")

    async def commit_parent(self, sha: str) -> str:
        rc, out = await self.run("rev-parse", "--verify", "-q", f"{sha}^")
        return out.strip() if rc == 0 and out.strip() else EMPTY_TREE


def untracked_file(root: Path, path: str):
    """FileDiff "A" cho file chưa theo dõi (git diff không liệt kê)."""
    from .diffview import added_file
    try:
        f = root / path
        data = f.read_bytes() if f.stat().st_size <= 1_000_000 else None
    except OSError:
        data = None
    try:
        text = data.decode("utf-8") if data is not None and b"\0" not in data else None
    except UnicodeDecodeError:
        text = None
    return added_file(path, text)


def file_icon(f: FileChange, staged: bool) -> tuple[str, str]:
    """(chữ, màu) cho một dòng file trong danh sách."""
    if f.conflicted:
        return "!", "bold red"
    if f.untracked:
        return "U", "green"
    code = f.index if staged else f.work
    return code, {"M": "yellow", "A": "green", "D": "red", "R": "magenta", "C": "magenta",
                  "T": "yellow"}.get(code, "")


def summary_line(st: RepoStatus) -> str:
    """Một dòng tóm tắt trạng thái (cho thanh trạng thái / thông báo)."""
    if not st.is_repo:
        return tr("không phải git repo")
    head = st.branch or (f"detached @ {st.oid[:8]}" if st.oid else tr("(chưa có commit)"))
    parts = [f"⎇ {head}"]
    if st.upstream:
        sync = []
        if st.ahead:
            sync.append(f"↑{st.ahead}")
        if st.behind:
            sync.append(f"↓{st.behind}")
        parts.append(" ".join(sync) or tr("✓ đồng bộ"))
    if st.files:
        parts.append(tr("{v} đã stage · {v2} chưa stage", v=len(st.staged), v2=len(st.unstaged) + len(st.untracked)))
        if st.conflicts:
            parts.append(tr("{v} xung đột", v=len(st.conflicts)))
    else:
        parts.append(tr("sạch"))
    if st.state:
        parts.append(tr("đang {state}", state=st.state))
    return " · ".join(parts)

