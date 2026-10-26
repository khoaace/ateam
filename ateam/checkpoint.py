"""↩ Checkpoint theo mục tiêu và `/undo`: trước khi mục tiêu đầu tiên chạy, chụp lại HEAD + toàn bộ cây làm việc
(cả file chưa commit / chưa track, trừ file bị .gitignore) vào ref `refs/ateam/checkpoints/m<id>` (commit) và
`…/m<id>-tree` (tree). `/undo m<id>` đưa nhánh + thư mục dự án về đúng lúc đó; trước khi hoàn tác chụp thêm một bản
`redo` để `/undo redo` lấy lại. Không tạo commit nào, không cần git identity; chạy git qua asyncio (không treo app)."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

from .i18n import tr

PREFIX = "refs/ateam/checkpoints/"
META = "checkpoints.json"  # .ateam/checkpoints.json: {key: {"branch", "at"}} — ref chỉ giữ commit + tree
REDO = "redo"
TIMEOUT = 120.0


async def _git(root: Path, *args: str, index: str | None = None) -> tuple[int, str]:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", LANGUAGE="C")
    if index:
        env["GIT_INDEX_FILE"] = index
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-c", "core.quotePath=false", *args, cwd=str(root), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
    except FileNotFoundError:
        return 127, tr("Chưa cài git")
    try:
        out, err = await asyncio.wait_for(proc.communicate(), TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, tr("git {v} quá {v2} giây — đã dừng", v=args[0], v2=int(TIMEOUT))
    text = out.decode("utf-8", "replace")
    return proc.returncode, text if proc.returncode == 0 else (text + err.decode("utf-8", "replace")).strip()


async def _snapshot_tree(root: Path) -> str | None:
    """Tree của toàn bộ thư mục làm việc (file đã track + chưa track, bỏ file bị ignore) — index tạm, index thật giữ
    nguyên."""
    fd, tmp = tempfile.mkstemp(prefix="ateam-index-")
    os.close(fd)
    os.unlink(tmp)  # git tự tạo index mới
    try:
        if (await _git(root, "read-tree", "HEAD", index=tmp))[0] != 0:
            return None
        if (await _git(root, "add", "-A", "--", ".", ":(exclude).ateam", index=tmp))[0] != 0:
            return None
        rc, out = await _git(root, "write-tree", index=tmp)
        return out.strip() if rc == 0 else None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


async def _branch(root: Path) -> str:
    rc, out = await _git(root, "symbolic-ref", "-q", "--short", "HEAD")
    return out.strip() if rc == 0 else ""


async def exists(root: Path, key: str) -> bool:
    return (await _git(root, "rev-parse", "-q", "--verify", f"{PREFIX}{key}^{{commit}}"))[0] == 0


async def create(root: Path, key: str, overwrite: bool = False) -> str | None:
    """Chụp checkpoint `key` (vd "m12"). Trả lời nhắn lỗi, None = xong (hoặc đã có và không ghi đè)."""
    if not overwrite and await exists(root, key):
        return None
    rc, head = await _git(root, "rev-parse", "--verify", "HEAD")
    if rc != 0:
        return tr("chưa có commit nào — không tạo được điểm khôi phục")
    tree = await _snapshot_tree(root)
    if not tree:
        return tr("không chụp được thư mục làm việc")
    branch = await _branch(root)
    for ref, sha in ((f"{PREFIX}{key}", head.strip()), (f"{PREFIX}{key}-tree", tree)):
        rc, out = await _git(root, "update-ref", ref, sha)
        if rc != 0:
            return out.strip()[:200]
    meta = _meta(root)
    meta[key] = {"branch": branch, "at": time.time()}
    try:
        path = root / ".ateam" / META
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass
    return None


def _meta(root: Path) -> dict:
    try:
        data = json.loads((root / ".ateam" / META).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


async def info(root: Path, key: str) -> dict | None:
    """{"head", "tree", "branch", "at"} của checkpoint, None nếu không có."""
    rc, out = await _git(root, "for-each-ref", "--format=%(objectname) %(refname)", f"{PREFIX}{key}",
                         f"{PREFIX}{key}-tree")
    refs = {}
    for ln in out.splitlines() if rc == 0 else []:
        sha, _, ref = ln.partition(" ")
        refs[ref] = sha
    head, tree = refs.get(f"{PREFIX}{key}"), refs.get(f"{PREFIX}{key}-tree")
    if not head or not tree:
        return None
    meta = _meta(root).get(key) or {}
    return {"head": head, "tree": tree, "branch": str(meta.get("branch") or ""), "at": meta.get("at")}


async def changes(root: Path, key: str) -> list[str] | str:
    """File sẽ đổi nếu hoàn tác về checkpoint ("M\tđường/dẫn"…), hoặc chuỗi lỗi."""
    cp = await info(root, key)
    if not cp:
        return tr("Không có điểm khôi phục '{key}'", key=key)
    now = await _snapshot_tree(root)
    if not now:
        return tr("không chụp được thư mục làm việc")
    rc, out = await _git(root, "diff", "--no-renames", "--name-status", cp["tree"], now)
    return [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else out.strip()[:200]


async def restore(root: Path, key: str) -> tuple[bool, str]:
    """Đưa nhánh + thư mục làm việc về checkpoint `key`. Trước đó chụp bản `redo` (trừ khi đang khôi phục chính
    `redo`). File bị .gitignore (node_modules, .env…) không đụng tới."""
    cp = await info(root, key)
    if not cp:
        return False, tr("Không có điểm khôi phục '{key}'", key=key)
    git_dir = (await _git(root, "rev-parse", "--git-dir"))[1].strip()
    gd = Path(git_dir) if os.path.isabs(git_dir) else root / git_dir
    if any((gd / f).exists() for f in ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge",
                                       "rebase-apply")):
        return False, tr("Đang merge / rebase dở — xong hoặc huỷ ở tab Git trước")
    branch = await _branch(root)
    if cp["branch"] and branch != cp["branch"]:
        return False, tr("Điểm khôi phục ở nhánh {v}, bạn đang ở {v2} — chuyển về {v} trước", v=cp["branch"],
                         v2=branch or "(detached)")
    if key != REDO:
        err = await create(root, REDO, overwrite=True)
        if err:
            return False, tr("Không chụp được bản để lấy lại: {e}", e=err)
    steps = (("reset", "-q", "--soft", cp["head"]),           # nhánh về commit cũ, chưa đụng file
             ("read-tree", "-u", "--reset", cp["tree"]))       # index + file = ảnh chụp (xoá file track thêm sau)
    for args in steps:
        rc, out = await _git(root, *args)
        if rc != 0:
            return False, out.strip()[:300]
    # file mới (chưa từng track) tạo sau checkpoint: không có trong ảnh chụp → xoá
    rc, out = await _git(root, "ls-files", "-z", "--others", "--exclude-standard")
    removed = 0
    for rel in (out.split("\0") if rc == 0 else []):
        if not rel or rel.split("/", 1)[0] == ".ateam":  # bảng việc, log của ateam
            continue
        p = root / rel
        try:
            p.unlink()
            removed += 1
        except OSError:
            continue
        d = p.parent
        while d != root and d.is_dir() and not any(d.iterdir()):  # dọn thư mục rỗng
            d.rmdir()
            d = d.parent
    rc, out = await _git(root, "read-tree", cp["head"])  # index = HEAD: file chưa commit lúc đó lại là "chưa stage"
    if rc != 0:
        return False, out.strip()[:300]
    return True, tr("Đã đưa dự án về lúc {at} (xoá {n} file mới)",
                    at=time.strftime("%H:%M %d/%m", time.localtime(cp["at"])) if cp["at"] else key, n=removed)
