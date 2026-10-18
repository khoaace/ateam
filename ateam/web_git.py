"""Tab Git và xem diff của giao diện web — bọc `gitops.GitRepo` và dữ liệu `diffview` thành JSON.

Diff gửi trình duyệt: mỗi dòng kèm token tô cú pháp (pygments) và đoạn chữ đổi trong dòng (`word_spans`);
`rows` ghép dòng cho kiểu hai cột (`split_rows`). Thao tác đổi nhánh/HEAD từ chối khi agent đang chạy (như TUI).
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import TYPE_CHECKING

from aiohttp import web

from . import diffview, gitops
from .config import save_commit_agent
from .i18n import tr

if TYPE_CHECKING:
    from .web import WebApp

MAX_DIFF_LINES = 4000   # mỗi file — như diffview.MAX_ROWS


# ---------------------------------------------------------------------------- diff → JSON
def _tok_class(ttype) -> str:
    """Lớp CSS ngắn cho một loại token pygments (tô màu ở app.css: .tk-k, .tk-s…)."""
    from pygments import token as T
    for kind, cls in ((T.Comment, "c"), (T.String, "s"), (T.Number, "n"), (T.Keyword, "k"),
                      (T.Name.Function, "f"), (T.Name.Class, "t"), (T.Name.Builtin, "b"),
                      (T.Name.Decorator, "d"), (T.Name.Tag, "k"), (T.Name.Attribute, "f"),
                      (T.Operator, "o"), (T.Generic.Heading, "k"), (T.Literal, "n")):
        if ttype in kind:
            return cls
    return ""


def highlight(lines: list[str], path: str) -> list[list[list[str]]]:
    """Token [[lớp, chữ], …] cho từng dòng — tô cả khối một lần để chuỗi/comment nhiều dòng vẫn đúng."""
    if not lines:
        return []
    code = "\n".join(lines)
    try:
        from pygments.lexers import get_lexer_for_filename
        from pygments.util import ClassNotFound
        try:
            lexer = get_lexer_for_filename(path, stripnl=False, ensurenl=False)
        except ClassNotFound:
            lexer = None
    except ImportError:  # pygments đi kèm rich/textual nên gần như luôn có
        lexer = None
    if lexer is None:
        return [[["", ln]] for ln in lines]
    out: list[list[list[str]]] = [[]]
    for ttype, value in lexer.get_tokens(code):
        cls = _tok_class(ttype)
        parts = value.split("\n")
        for i, part in enumerate(parts):
            if i:
                out.append([])
            if part:
                if out[-1] and out[-1][-1][0] == cls:
                    out[-1][-1][1] += part
                else:
                    out[-1].append([cls, part])
    out = out[:len(lines)]
    while len(out) < len(lines):
        out.append([])
    return out


def file_json(fd: diffview.FileDiff) -> dict:
    hunks, total = [], 0
    for h in fd.hunks:
        if total >= MAX_DIFF_LINES:
            break
        lines = h.lines[:MAX_DIFF_LINES - total]
        total += len(lines)
        h2 = diffview.Hunk(h.header, lines)
        texts = [ln.text.expandtabs(4) for ln in lines]
        old_idx = [i for i, ln in enumerate(lines) if ln.kind != "+"]
        new_idx = [i for i, ln in enumerate(lines) if ln.kind != "-"]
        toks: dict[int, list] = {}
        for i, t in zip(old_idx, highlight([texts[i] for i in old_idx], fd.path)):
            toks[i] = t
        for i, t in zip(new_idx, highlight([texts[i] for i in new_idx], fd.path)):
            if lines[i].kind == "+":
                toks[i] = t
        spans: dict[int, list] = {}
        for dels, adds in diffview._change_blocks(h2):
            for d, a in zip(dels, adds):
                spans[d], spans[a] = (list(map(list, s)) for s in diffview.word_spans(texts[d], texts[a]))
        hunks.append({
            "header": h.header,
            "lines": [{"k": ln.kind, "o": ln.old_no, "n": ln.new_no, "t": toks.get(i, [["", texts[i]]]),
                       "w": spans.get(i, [])} for i, ln in enumerate(lines)],
            "rows": [list(r) for r in diffview.split_rows(h2)],
        })
    return {"path": fd.path, "old_path": fd.old_path, "status": fd.status, "binary": fd.binary,
            "added": fd.added, "removed": fd.removed, "hunks": hunks,
            "truncated": sum(len(h.lines) for h in fd.hunks) > MAX_DIFF_LINES}


def diffset_json(ds: diffview.DiffSet, start: int = 0) -> dict:
    return {"tid": ds.tid, "title": ds.title, "base": ds.base, "head": ds.head, "start": start,
            "added": ds.added, "removed": ds.removed, "files": [file_json(f) for f in ds.files]}


# ---------------------------------------------------------------------------- trạng thái → JSON
def status_json(st: gitops.RepoStatus) -> dict:
    def row(f: gitops.FileChange, staged: bool) -> dict:
        icon, _ = gitops.file_icon(f, staged)
        return {"path": f.path, "orig": f.orig, "icon": icon}
    return {"is_repo": st.is_repo, "branch": st.branch, "oid": st.oid, "upstream": st.upstream,
            "ahead": st.ahead, "behind": st.behind, "stashes": st.stashes, "state": st.state, "error": st.error,
            "detached": st.detached, "clean": st.clean, "summary": gitops.summary_line(st),
            "groups": {"c": [row(f, False) for f in st.conflicts], "s": [row(f, True) for f in st.staged],
                       "w": [row(f, False) for f in st.unstaged + st.untracked]}}


class GitWeb:
    """Route /api/git/* và thao tác `{"op": "git", "action": …}` của WebApp."""

    def __init__(self, app: "WebApp"):
        self.app = app
        self.repo = gitops.GitRepo(app.root)

    def routes(self) -> list:
        return [web.get("/api/git/status", self.api_status), web.get("/api/git/log", self.api_log),
                web.get("/api/git/branches", self.api_branches), web.get("/api/git/stashes", self.api_stashes),
                web.get("/api/git/diff", self.api_diff), web.get("/api/diff/{tid}", self.api_task_diff)]

    async def api_status(self, _r: web.Request) -> web.Response:
        st = await self.repo.status()
        out = status_json(st)
        out["has_commits"] = bool(st.oid)
        out["busy"] = len(self.app.orch.runs)
        return web.json_response(out)

    async def api_log(self, r: web.Request) -> web.Response:
        # không cần `git status` trước (trình duyệt gọi cùng lúc với /api/git/status mỗi 3 giây):
        # chưa phải repo / chưa có commit thì `git log` lỗi và repo.log trả []
        return web.json_response([asdict(c) for c in await self.repo.log(int(r.query.get("n", 80)))])

    async def api_branches(self, _r: web.Request) -> web.Response:
        return web.json_response([asdict(b) for b in await self.repo.branches()])

    async def api_stashes(self, _r: web.Request) -> web.Response:
        return web.json_response([asdict(s) for s in await self.repo.stashes()])

    async def api_diff(self, r: web.Request) -> web.Response:
        """?kind=staged|unstaged|conflict|file&path=… hoặc ?commit=<sha>."""
        q = r.query
        if q.get("commit"):
            commits = [c for c in await self.repo.log(200) if c.sha.startswith(q["commit"])]
            if not commits:
                return web.json_response({"error": tr("Không thấy commit {v}", v=q["commit"])})
            ds = await self.repo.commit_diffset(commits[0])
            if not ds.files:
                return web.json_response({"error": tr("Commit {short} không đổi file nào (vd commit merge)",
                                                      short=commits[0].short)})
            return web.json_response(await asyncio.to_thread(diffset_json, ds))
        path, kind = q.get("path", ""), q.get("kind", "unstaged")
        if kind == "conflict":
            ds = diffview.DiffSet(0, tr("Xung đột · {path}", path=path),
                                  diffview.parse_unified(await self.repo.diff_text("HEAD", "--", path)), "HEAD", None)
        elif kind == "file":  # palette tab Code: thay đổi của đúng file này (chưa stage, không có thì đã stage)
            for staged in (False, True):
                ds = await self.repo.changes_diffset(staged=staged)
                if any(f.path == path for f in ds.files):
                    break
            else:
                return web.json_response({"error": tr("{v}: không có thay đổi so với git", v=path)})
        else:
            ds = await self.repo.changes_diffset(staged=kind == "staged")
        if not ds.files:
            return web.json_response({"error": tr("Không có diff để xem")})
        start = next((i for i, f in enumerate(ds.files) if f.path == path), 0)
        return web.json_response(await asyncio.to_thread(diffset_json, ds, start))

    async def api_task_diff(self, r: web.Request) -> web.Response:
        res = await self.app.orch.diff_files(int(r.match_info["tid"]))
        if isinstance(res, str):
            return web.json_response({"error": res})
        if not res.files:
            return web.json_response({"error": tr("Task #{tid} không thay đổi file nào.", tid=res.tid)})
        return web.json_response(await asyncio.to_thread(diffset_json, res))

    # ------------------------------------------------------------------ thao tác
    BUSY = {"pull", "checkout", "create_branch", "merge", "stash_push", "stash_apply", "stash_pop", "revert",
            "undo"}

    async def op(self, d: dict) -> tuple:
        """Một thao tác git. Trả (lời nhắn, mức[, thêm]) — mức ok/warn như TUI (git_do)."""
        g, act = self.repo, d.get("action")
        paths = [p for p in (d.get("paths") or ([d["path"]] if d.get("path") else [])) if p]
        runs = self.app.orch.runs
        if act in self.BUSY and runs:
            return tr("Đang có {v} task chạy — đợi xong (hoặc Ctrl+K huỷ) rồi hẵng đổi nhánh/pull/stash",
                      v=len(runs)), "warn"
        if act == "commit_agent":  # chọn agent viết commit message (dùng chung TUI, lưu state.json)
            name = str(d.get("name") or "")
            if name and name not in self.app.cfg.active_agents():
                return tr("Không có agent '{name}'", name=name), "warn"
            self.app.cfg.commit_agent = name
            save_commit_agent(name)
            return "", ""
        if act == "ai_message":
            ok, msg = await self.app.orch.commit_message()
            return (tr("✨ Đã điền commit message — sửa nếu cần rồi commit"), "ok", {"git_msg": msg}) if ok \
                else (msg, "warn")
        if act == "last_message":
            return "", "", {"git_msg": await g.last_message()}
        if act == "commit":
            st = await g.status()
            msg = str(d.get("message") or "").strip()
            amend = bool(d.get("amend"))
            if not msg and not amend:
                return tr("Gõ commit message trước (hoặc bấm ✨ để trưởng nhóm viết)"), "warn"
            ok, out = await g.commit(msg, amend=amend, all_changes=not st.staged, no_verify=bool(d.get("no_verify")))
            return out, "ok" if ok else "warn", {"committed": ok}
        calls = {
            "stage": lambda: g.stage(paths), "unstage": lambda: g.unstage(paths),
            "stage_all": g.stage_all, "unstage_all": lambda: g.unstage(), "discard": lambda: g.discard(paths),
            "fetch": g.fetch, "pull": g.pull, "push": lambda: g.push(force=bool(d.get("force"))),
            "abort": g.abort, "init": g.init,
            "checkout": lambda: g.checkout(d.get("name", "")),
            "create_branch": lambda: g.create_branch(d.get("name", "")),
            "rename_branch": lambda: g.rename_branch(d.get("name", ""), d.get("new", "")),
            "delete_branch": lambda: g.delete_branch(d.get("name", ""), force=bool(d.get("force"))),
            "merge": lambda: g.merge(d.get("name", "")),
            "stash_push": lambda: g.stash_push(str(d.get("message") or "")),
            "stash_apply": lambda: g.stash_apply(d.get("ref") or "stash@{0}", pop=False),
            "stash_pop": lambda: g.stash_apply(d.get("ref") or "stash@{0}", pop=True),
            "stash_drop": lambda: g.stash_drop(d.get("ref") or "stash@{0}"),
            "revert": lambda: g.revert(d.get("sha", "")), "undo": g.reset_soft,
        }
        if act not in calls:
            return tr("Không hiểu thao tác {op}", op=f"git {act}"), "warn"
        ok, msg = await calls[act]()
        return msg, "ok" if ok else "warn"

    async def command(self, cmd: str, rest: str) -> tuple | None:
        """/git, /commit, /push, /pull, /fetch, /branch, /checkout, /stash — cùng nghĩa TeamApp.git_command."""
        if cmd == "git":
            if not rest:
                return "", "", {"open": {"view": "git"}}
            return self.app.run_shell("git " + rest)  # lệnh git bất kỳ: chạy ở tab Terminal
        if cmd == "commit":
            if not rest:
                return "", "", {"open": {"view": "git", "git_ai": True}}
            words = rest.split()
            skip = words[0] in ("--no-verify", "-n")
            msg = " ".join(words[1:]) if skip else rest
            if not msg:
                return tr("Dùng: /commit [--no-verify] <message>"), "warn"
            return await self.op({"action": "commit", "message": msg, "no_verify": skip})
        if cmd == "push":
            return await self.op({"action": "push", "force": rest in ("-f", "--force", "force")})
        if cmd in ("pull", "fetch"):
            return await self.op({"action": cmd})
        if cmd == "branch":
            if not rest:
                return "", "", {"open": {"view": "git", "modal": "branches"}}
            return await self.op({"action": "create_branch", "name": rest})
        if cmd == "checkout":
            return await self.op({"action": "checkout", "name": rest})
        if cmd == "stash":
            if rest in ("pop", "apply"):
                return await self.op({"action": "stash_" + rest})
            if rest in ("list", "ls"):
                return "", "", {"open": {"view": "git", "modal": "stash"}}
            return await self.op({"action": "stash_push", "message": rest})
        return None
