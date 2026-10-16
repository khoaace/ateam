"""Bộ điều phối: trưởng nhóm lập kế hoạch, lịch chạy theo phụ thuộc, giao việc chéo, review, worktree."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import time
from pathlib import Path
from typing import Callable

from . import limits
from . import mentions
from . import prompts as P
from .config import AgentConfig, Config
from .db import (ACTIVE, BLOCKED, CANCELLED, COMPACT_AUTHOR, CONFLICT, DB, DONE, DRAFT, FAILED,
                 FINISHED_BAD, GOAL_ENDED, QUEUED, REVIEW, RUNNING, Task)
from .runner import Run

SYSTEM = 0  # id "task" của log hệ thống
MAX_DELEGATIONS_PER_TASK = 5
# CLI báo không nhận cờ (clap, argparse, commander, yargs…) -> gợi ý chạy `ateam doctor`
BAD_FLAG_RE = re.compile(r"unexpected argument '-|unrecognized (?:argument|option)|unknown (?:option|flag|argument)"
                         r"|no such option", re.I)


# agent headless bị từ chối quyền chạy lệnh (agy thoát 0 sau khi in câu này -> trước đây task bị tính "xong")
DENIED_RE = re.compile(r"permission that headless mode cannot prompt for|auto-denied|auto-rejected"
                       r"|requested permissions? to use \w+, but you haven't granted it"
                       # Grok Build: lỗi có cấu trúc, hoặc model tự kể lại (tiếng Anh/Việt) khi --deny Bash chặn
                       r"|headless run cannot ask for approval"
                       r"|deny rule[^.\n]{0,20}\bbash\b|\bbash\b[^.\n]{0,20}deny rule"
                       r"|(?:blocked|denied|chặn|từ chối)[^.\n]{0,80}permission policy"
                       r"|permission policy[^.\n]{0,40}(?:blocked|denies|chặn|từ chối)", re.I)


class Orchestrator:
    def __init__(self, root: Path, cfg: Config, db: DB,
                 on_event: Callable[[str, dict], None] | None = None):
        self.root = Path(root).resolve()
        self.cfg, self.db = cfg, db
        self.on_event = on_event or (lambda kind, data: None)
        self.state = self.root / ".ateam"
        self.logs = self.state / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        gi = self.state / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n")
        self.runs: dict[int, Run] = {}
        self.lead_busy: set[int] = set()  # goal đang được lập kế hoạch / review
        self.compacting = False  # /compact đang chạy
        self.paused = False
        self.use_worktree = False
        self._git_ident: list[str] | None = None  # None = chưa kiểm tra
        self._merge_lock_obj: asyncio.Lock | None = None  # tạo khi dùng (xem _merge_lock)
        self._bg: set[asyncio.Task] = set()
        self._cancel_req: set[int] = set()
        self._wt_base: dict[int, str] = {}
        # hoạt động hiện tại của từng agent (cho tab Đội)
        self.activity: dict[str, dict] = {}
        # các lần trưởng nhóm lập kế hoạch / review: (bắt đầu, kết thúc|None, nhãn)
        self.lead_spans: list[list] = []
        # agent đang tạm nghỉ vì hết hạn mức: tên -> thời điểm hồi lại
        self.cooldown: dict[str, float] = limits.load_cooldowns()

    # ------------------------------------------------------------------ tiện ích
    def emit(self, kind: str, **data) -> None:
        try:
            self.on_event(kind, data)
        except Exception:
            pass

    def log(self, msg: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {msg}"
        with open(self.logs / "system.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        self.emit("log", task_id=SYSTEM, line=line)

    def log_path(self, tid: int) -> Path:
        return self.logs / f"t{tid}.log"

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.get_running_loop().create_task(coro)
        self._bg.add(t)
        t.add_done_callback(self._bg.discard)
        return t

    def argv_for(self, a: AgentConfig, prompt: str, workdir: Path, *, model: str | None = None,
                 effort: str | None = None, plan: bool = False) -> list[str]:
        """Lệnh chạy agent, đã đổi @đường-dẫn sang cú pháp của CLI đó (xem mentions.py)."""
        prompt, extra = mentions.render(prompt, a.binary, [Path(workdir), self.root],
                                        file_ref=a.file_ref, file_args=a.file_args,
                                        image_args=a.image_args)
        return mentions.insert_args(a.argv(prompt, model=model, effort=effort, plan=plan),
                                    prompt, extra)

    def env_for(self, task: Task | None = None) -> dict[str, str]:
        env = dict(os.environ)
        env["ATEAM_DB"] = str(self.db.path)
        env["ATEAM_ROOT"] = str(self.root)
        if task:
            env["ATEAM_TASK_ID"] = str(task.id)
            env["ATEAM_AGENT"] = task.agent
        return env

    def _begin_activity(self, agent: str, tid: int | None, title: str, label: str) -> dict:
        now = time.time()
        act = {"task_id": tid, "title": title, "label": label, "started": now,
               "lines": 0, "last_line": "", "last_at": now}
        self.activity.setdefault(agent, {})[id(act)] = act
        self.emit("activity", agent=agent, start=act)
        return act

    def _touch(self, act: dict, line: str) -> None:
        act["lines"] += 1
        act["last_at"] = time.time()
        if line.strip():
            act["last_line"] = line

    def _end_activity(self, agent: str, act: dict | None) -> None:
        if act is not None:
            self.activity.get(agent, {}).pop(id(act), None)
            self.emit("activity", agent=agent, end=act)

    def current_activities(self, agent: str) -> list[dict]:
        return list(self.activity.get(agent, {}).values())

    def notes_text(self) -> str:
        return "\n".join(f"- [{a}] {t}" for a, t in self.db.recent_notes())

    # ------------------------------------------------------------------ khởi động
    async def setup(self) -> None:
        # dọn trạng thái dở dang từ phiên trước
        for t in self.db.tasks(status=RUNNING):
            self.db.update_task(t.id, status=FAILED,
                                error="Phiên trước bị dừng giữa chừng — /retry để chạy lại")
        for g in self.db.goals():
            if g.status == "planning":
                self.db.update_goal(g.id, status="failed", summary="Bị dừng khi đang lập kế hoạch")
            elif g.status == "reviewing":
                self.db.update_goal(g.id, status="running")
        await self.apply_isolation()

    async def apply_isolation(self) -> None:
        """Chọn chế độ làm việc theo cfg.isolation (gọi lại được khi /setup đổi chế độ)."""
        self.use_worktree = False
        if self.cfg.isolation == "worktree":
            rc, top = await self._git("rev-parse", "--show-toplevel")
            rc2, _ = await self._git("rev-parse", "--verify", "HEAD")
            if rc == 0 and rc2 == 0 and Path(top.strip()).resolve() == self.root:
                self.use_worktree = True
            else:
                self.log("⚠ isolation=worktree cần chạy ở thư mục gốc của git repo đã có commit — "
                         "chuyển sang chế độ shared.")
        mode = "worktree (mỗi task 1 nhánh riêng)" if self.use_worktree else "shared (chung thư mục)"
        self.log(f"Sẵn sàng. Trưởng nhóm: {self.cfg.lead}. Chế độ làm việc: {mode}.")

    # ------------------------------------------------------------------ mục tiêu
    def new_goal(self, text: str) -> int:
        gid = self.db.add_goal(text)
        self.lead_busy.add(gid)
        self.log(f"🎯 Mục tiêu #{gid}: {text}")
        self._spawn(self._plan(gid))
        self.emit("changed")
        return gid

    async def _call_lead(self, prompt: str, label: str) -> str | None:
        """Gọi trưởng nhóm; nếu hết hạn mức thì lần lượt thử các agent trong lead_fallback."""
        names = [self.cfg.lead] + [n for n in self.cfg.lead_fallback if n != self.cfg.lead]
        for name in names:
            lead = self.cfg.agents.get(name)
            if not lead or not lead.enabled:
                if name == self.cfg.lead:
                    self.log(f"✗ Không tìm thấy trưởng nhóm '{name}' trong cấu hình.")
                continue
            if not lead.installed():
                self.log(f"✗ Chưa cài '{lead.binary}' ({name}).")
                continue
            if self.in_cooldown(name):
                self.log(f"⏸ {name} đang hết hạn mức đến {self.cooldown_label(name)} — thử người khác.")
                continue
            if name != self.cfg.lead:
                self.log(f"↪ {name} làm thay trưởng nhóm cho: {label}")
            out, rc, kind = await self._lead_once(lead, prompt, label)
            if kind == "ratelimit":
                self._set_cooldown(name, out)
                continue
            if rc != 0:
                self.log(f"✗ {label}: {name} thoát với mã {rc}.")
            return out
        self.log(f"✗ Không còn agent nào lập kế hoạch/review được ({label}).")
        return None

    async def _lead_once(self, lead: AgentConfig, prompt: str, label: str) -> tuple[str, int, str]:
        span = [time.time(), None, label]
        self.lead_spans.append(span)
        act = self._begin_activity(lead.name, None, label, lead.label())
        rid = self.db.add_run(None, lead.name, "lead", len(prompt))
        with open(self.logs / "lead.log", "a", encoding="utf-8") as f:
            f.write(f"\n===== {label} — {lead.name} — {time.ctime()} =====\n")

            def on_line(line: str) -> None:
                f.write(line + "\n")
                f.flush()
                self._touch(act, line)
                self.emit("log", task_id=SYSTEM, agent=lead.name, raw=line,
                          line=f"  [{lead.name}] {line}")

            run = Run(self.argv_for(lead, prompt, self.root, plan=True), str(self.root),
                      self.env_for(), use_pty=lead.pty, timeout=lead.timeout, on_line=on_line)
            rc = 1
            try:
                rc = await run.start()
            finally:
                span[1] = time.time()
                kind = self._classify(run, rc)
                self.db.finish_run(rid, rc, kind, len(run.output))
                act["status"] = DONE if kind == "ok" else FAILED
                self._end_activity(lead.name, act)
        return run.output, rc, kind

    async def _plan(self, gid: int, followup: tuple[str, str, str] | None = None) -> None:
        """followup: (yêu cầu mới, kết quả các task cũ, đánh giá cũ) khi tiếp tục mục tiêu đã xong."""
        try:
            goal = self.db.goal(gid)
            self.log(f"🧠 {self.cfg.lead} đang lập kế hoạch cho mục tiêu #{gid}…")
            if followup:
                prompt = P.followup_plan_prompt(self.cfg, goal.text, followup[1], followup[2],
                                                followup[0], str(self.root), self.notes_text(),
                                                earlier=(goal.followups or [])[:-1])
            else:
                prompt = P.plan_prompt(self.cfg, goal.text, str(self.root), self.notes_text())
            out = await self._call_lead(prompt, f"Lập kế hoạch mục tiêu #{gid}")
            plan = P.extract_json(out or "", list)
            if not plan:
                self.db.update_goal(gid, status="failed", summary="Trưởng nhóm không trả về kế hoạch JSON hợp lệ")
                self.log(f"✗ Không đọc được kế hoạch cho mục tiêu #{gid} (xem .ateam/logs/lead.log). "
                         f"Bạn vẫn có thể giao tay bằng /task.")
                return
            ids = self._insert_plan(gid, plan, source="followup" if followup else "plan")
            if self.cfg.approve_plan:
                self.db.update_goal(gid, status="awaiting")
                self.log(f"📋 Kế hoạch #{gid}: {len(ids)} task ở trạng thái NHÁP. "
                         f"Duyệt bằng /go {gid} (trong TUI: F2 hoặc Ctrl+G); sửa trước bằng /edit, /assign, /cancel.")
            else:
                self.db.update_goal(gid, status="running")
                self.log(f"📋 Kế hoạch #{gid}: {len(ids)} task — bắt đầu chạy.")
        finally:
            self.lead_busy.discard(gid)
            self.emit("changed")

    def run_workflow(self, name: str, text: str) -> int | str:
        """Tạo mục tiêu từ workflow dựng sẵn: các bước thành task ngay, không gọi trưởng nhóm.
        Trả về id mục tiêu, hoặc chuỗi lỗi."""
        wf = self.cfg.workflows.get(name)
        if not wf:
            return f"Không có workflow '{name}'. Có: {', '.join(self.cfg.workflows) or '(chưa có)'}"
        if not wf.steps:
            return f"Workflow '{name}' chưa có bước nào"
        gid = self.db.add_goal(text, workflow=name)
        self.log(f"🎯 Mục tiêu #{gid} theo workflow '{name}': {text}")
        ids = self._insert_plan(gid, wf.plan(text, self.cfg.lead), source="workflow", from_user=True)
        if self.cfg.approve_plan:
            self.db.update_goal(gid, status="awaiting")
            self.log(f"📋 {len(ids)} bước ở trạng thái NHÁP — gõ /go {gid} để chạy.")
        else:
            self.db.update_goal(gid, status="running")
            self.log(f"📋 {len(ids)} bước — bắt đầu chạy.")
        self.emit("changed")
        return gid

    def continue_goal(self, gid: int, text: str) -> int | str:
        """Mở lại mục tiêu đã kết thúc với yêu cầu mới: trưởng nhóm lập task bổ sung dựa trên việc
        đã làm. Trả về id mục tiêu, hoặc chuỗi lỗi."""
        g = self.db.goal(gid)
        if not g:
            return f"Không có mục tiêu #{gid}"
        if g.status not in GOAL_ENDED or gid in self.lead_busy:
            return f"Mục tiêu #{gid} chưa kết thúc — đợi xong (hoặc /review {gid}) rồi tiếp tục"
        if not self.cfg.agents.get(self.cfg.lead):
            return f"Không có trưởng nhóm '{self.cfg.lead}' trong cấu hình"
        text = text.strip()
        if not text:
            return "Thiếu yêu cầu mới"
        history, summary = self._results_text(gid), g.summary or ""
        self.db.add_followup(gid, text)
        self.db.update_goal(gid, status="planning", round=1, summary=None)  # max_rounds tính lại
        self.lead_busy.add(gid)
        self.log(f"↪ Tiếp tục mục tiêu #{gid}: {text}")
        self._spawn(self._plan(gid, followup=(text, history, summary)))
        self.emit("changed")
        return gid

    def continue_ref(self, ref: str) -> tuple[str, int] | str:
        """Bóc tham chiếu của /continue: "m12" = mục tiêu 12; "t40" hoặc "40" = task 40 (task thuộc
        mục tiêu thì là mục tiêu đó). Trả về ("goal"|"task", id) hoặc chuỗi lỗi."""
        m = re.fullmatch(r"#?([mMtT]?)(\d+)", ref.strip())
        if not m:
            return f"Không hiểu '{ref}' — dùng m<số> cho mục tiêu, t<số> cho task"
        n = int(m.group(2))
        if m.group(1).lower() == "m":
            return ("goal", n) if self.db.goal(n) else f"Không có mục tiêu #{n}"
        t = self.db.task(n)
        if not t:
            return f"Không có task #{n}"
        if t.goal_id is not None and self.db.goal(t.goal_id):
            return ("goal", t.goal_id)
        return ("task", n)

    def continue_any(self, ref: str, text: str) -> tuple[str, int] | str:
        """/continue <ref> <yêu cầu>: tiếp tục mục tiêu hoặc thread. Trả về ("goal", id mục tiêu) /
        ("task", id task mới), hoặc chuỗi lỗi."""
        r = self.continue_ref(ref)
        if isinstance(r, str):
            return r
        res = self.continue_goal(r[1], text) if r[0] == "goal" else self.continue_task(r[1], text)
        return res if isinstance(res, str) else (r[0], res)

    def continue_task(self, tid: int, text: str) -> int | str:
        """Hỏi tiếp trong thread /task: task mới cùng agent, prompt kèm các lượt trước.
        Trả về id task mới, hoặc chuỗi lỗi."""
        t = self.db.task(tid)
        if not t:
            return f"Không có task #{tid}"
        if t.status in ACTIVE:
            return (f"Task #{tid} đang chờ duyệt — merge (Ctrl+Y) hoặc /reject trước" if t.status == REVIEW
                    else f"Task #{tid} chưa xong — đợi chạy xong rồi tiếp tục")
        if t.agent not in self.cfg.active_agents():
            return f"Agent '{t.agent}' không còn trong đội"
        text = text.strip()
        if not text:
            return "Thiếu yêu cầu mới"
        title = text[:60] + ("…" if len(text) > 60 else "")
        nid = self.db.add_task(t.agent, title, text, status=QUEUED, source="followup",
                               parent_id=tid, model=t.model, effort=t.effort)
        self.log(f"↪ Task #{nid} hỏi tiếp {t.agent} (sau #{tid}): {title}")
        self.emit("changed")
        return nid

    def thread_of(self, t: Task, limit: int = 6) -> list[tuple[str, str]]:
        """Các lượt trước của thread /task (cũ → mới): (yêu cầu, kết quả)."""
        turns: list[tuple[str, str]] = []
        seen = {t.id}
        p = self.db.task(t.parent_id) if t.parent_id else None
        while p and p.id not in seen and len(turns) < limit:
            seen.add(p.id)
            turns.append((p.prompt, p.result or p.error or ""))
            p = self.db.task(p.parent_id) if p.source == "followup" and p.parent_id else None
        return turns[::-1]

    def _insert_plan(self, gid: int, plan: list[dict], source: str,
                     from_user: bool = False) -> list[int]:
        """from_user: kế hoạch do người dùng viết (workflow) — giữ effort/model của từng bước."""
        agents = self.cfg.active_agents()
        status = DRAFT if self.cfg.approve_plan else QUEUED
        id_map: dict = {}
        created: list[tuple[int, list]] = []
        for i, item in enumerate(plan, 1):
            agent = str(item.get("agent", "")).strip()
            if agent not in agents:
                self.log(f"⚠ Agent '{agent}' không có trong đội — giao cho {self.cfg.lead}.")
                agent = self.cfg.lead
            title = str(item.get("title") or f"Task {i}").strip()
            prompt = str(item.get("prompt") or title).strip()
            effort = str(item.get("effort") or "").strip().lower()
            if not from_user and (not self.cfg.lead_sets_effort or effort not in agents[agent].efforts):
                effort = ""
            model = str(item.get("model") or "").strip() if from_user else ""
            tid = self.db.add_task(agent, title, prompt, goal_id=gid, status=status, source=source,
                                   effort=effort or None, model=model or None)
            id_map[item.get("id", i)] = tid
            id_map[str(item.get("id", i))] = tid
            created.append((tid, item.get("depends_on") or []))
            self.log(f"   #{tid} → {agent}{(' @' + effort) if effort else ''}: {title}")
        for tid, deps in created:
            real = [id_map[d] for d in deps if d in id_map and id_map[d] != tid]
            if real:
                self.db.update_task(tid, depends_on=real)
        return [t for t, _ in created]

    def approve(self, gid: int | None = None) -> int:
        n = 0
        for t in self.db.tasks(goal_id=gid, status=DRAFT):
            self.db.update_task(t.id, status=QUEUED)
            n += 1
        for g in self.db.goals():
            if (gid is None or g.id == gid) and g.status == "awaiting":
                self.db.update_goal(g.id, status="running")
        if n:
            self.log(f"▶ Đã duyệt {n} task.")
        self.emit("changed")
        return n

    def discard_plan(self, gid: int) -> int:
        """Bỏ kế hoạch nháp của mục tiêu: huỷ mọi task nháp, mục tiêu thành "đã huỷ"."""
        g = self.db.goal(gid)
        if not g or g.status != "awaiting":
            return 0
        n = 0
        for t in self.db.tasks(goal_id=gid, status=DRAFT):
            self.db.update_task(t.id, status=CANCELLED, finished=time.time())
            n += 1
        self.db.update_goal(gid, status="cancelled", summary="Người dùng bỏ kế hoạch")
        self.log(f"✗ Đã bỏ kế hoạch #{gid} ({n} task nháp).")
        self.emit("changed")
        return n

    def finished_ids(self, tasks: list | None = None, goals: list | None = None) -> tuple[list[int], list[int]]:
        """Task và mục tiêu dọn được: task xong/lỗi/huỷ/bị chặn mà mục tiêu của nó đã kết thúc (hoặc
        không thuộc mục tiêu nào) và không còn task nào khác đang chờ nó; mục tiêu đã kết thúc mà dọn
        xong thì không còn task nào. tasks/goals: danh sách vừa đọc (TUI dùng lại, khỏi đọc DB lần nữa)."""
        goals = {g.id: g for g in (self.db.goals() if goals is None else goals)}
        ended = {gid for gid, g in goals.items() if g.status in GOAL_ENDED}
        tasks = self.db.tasks() if tasks is None else tasks
        drop = {t.id for t in tasks if t.status in (DONE,) + FINISHED_BAD
                and (t.goal_id is None or t.goal_id in ended)}
        needed = {d for t in tasks if t.id not in drop for d in t.depends_on}
        drop -= needed  # task còn lại phụ thuộc vào nó: xoá đi thì task đó thành "bị chặn"
        left = {t.goal_id for t in tasks if t.id not in drop}
        return sorted(drop), sorted(gid for gid in ended if gid not in left)

    def clear_finished(self) -> tuple[int, int]:
        """Dọn bảng việc: xoá task và mục tiêu đã kết thúc cùng file log của chúng."""
        tids, gids = self.finished_ids()
        if not tids and not gids:
            return 0, 0
        self.db.delete(tids, gids)
        for tid in tids:
            try:
                self.log_path(tid).unlink()
            except OSError:
                pass
        self.log(f"🗑 Đã dọn {len(tids)} task, {len(gids)} mục tiêu đã kết thúc khỏi bảng việc.")
        self.emit("changed")
        return len(tids), len(gids)

    # ------------------------------------------------------------------ giao tay / chỉnh sửa
    def add_task(self, agent: str, prompt: str, title: str | None = None, *,
                 model: str | None = None, effort: str | None = None) -> int:
        title = title or (prompt[:60] + ("…" if len(prompt) > 60 else ""))
        tid = self.db.add_task(agent, title, prompt, status=QUEUED, source="user",
                               model=model, effort=effort)
        extra = self.cfg.agents[agent].label(model, effort) if (model or effort) else ""
        self.log(f"➕ Task #{tid} giao cho {agent}{(' [' + extra + ']') if extra else ''}: {title}")
        self.emit("changed")
        return tid

    def assign(self, tid: int, agent: str) -> str:
        t = self.db.task(tid)
        if not t:
            return f"Không có task #{tid}"
        if agent not in self.cfg.active_agents():
            return f"Không có agent '{agent}'"
        if t.status == RUNNING:
            return f"Task #{tid} đang chạy — /cancel trước rồi giao lại"
        self.db.update_task(tid, agent=agent)
        self.emit("changed")
        return f"Task #{tid} → {agent}"

    def set_task_option(self, tid: int, key: str, value: str | None) -> str:
        t = self.db.task(tid)
        if not t:
            return f"Không có task #{tid}"
        if t.status == RUNNING:
            return f"Task #{tid} đang chạy — thay đổi sẽ áp dụng nếu /retry"
        self.db.update_task(tid, **{key: (None if value in (None, "", "-") else value)})
        self.emit("changed")
        return f"Task #{tid}: {key} = {value if value not in (None, '', '-') else 'theo agent'}"

    def set_agent_option(self, agent: str, key: str, value: str | None) -> str:
        from .config import save_agent_setting
        a = self.cfg.agents.get(agent)
        if not a:
            return f"Không có agent '{agent}'"
        reset = value in (None, "", "-")
        save_agent_setting(agent, key, None if reset else value)
        if reset:  # đọc lại giá trị gốc trong file cấu hình
            from .config import load_config
            fresh = load_config(self.root).agents.get(agent)
            value = getattr(fresh, key) if fresh else ""
        setattr(a, key, value or "")
        self.log(f"⚙ {agent}: {key} = {value or 'mặc định của CLI'}")
        self.emit("changed")
        return f"{agent}: {a.label()}"

    async def discover_models(self, agent: str, timeout: float = 30) -> str:
        """Chạy models_command của agent (vd `opencode models`) để lấy danh sách model thật."""
        from .config import parse_models, parse_models_json, save_found_models
        a = self.cfg.agents.get(agent)
        if not a:
            return f"Không có agent '{agent}'"
        if not a.models_command:
            return f"{agent}: CLI không có lệnh liệt kê model — dùng danh mục có sẵn"
        if not shutil.which(a.models_command[0]):
            return f"{agent}: chưa cài lệnh '{a.models_command[0]}'"
        run = Run(list(a.models_command), str(self.root), self.env_for(), use_pty=a.pty,
                  timeout=timeout, on_line=lambda _l: None)
        try:
            code = await run.start()
        except Exception as e:
            return f"{agent}: không chạy được {' '.join(a.models_command)}: {e}"
        found = parse_models(run.output, a.models_filter)
        # danh sách dạng chữ của opencode lẫn model mọi hãng -> giữ model mang tên agent (nếu có);
        # JSON (codex) đã chỉ gồm model dùng được, lọc theo tên sẽ chỉ còn "codex-auto-review"
        if (not a.models_filter and parse_models_json(run.output) is None
                and any(agent.lower() in m.lower() for m in found)):
            found = [m for m in found if agent.lower() in m.lower()]
        if code != 0 or not found:
            why = "hết thời gian" if run.timed_out else f"mã thoát {code}" if code else "không thấy model nào"
            return f"{agent}: {' '.join(a.models_command)} — {why}"
        save_found_models(agent, found)
        a.models = found + [m for m in a.models if m not in found]
        self.emit("changed")
        msg = f"{agent}: tìm thấy {len(found)} model"
        if a.model and a.model not in found:
            msg += f" ⚠ model đang chọn '{a.model}' không có trong danh sách — chọn lại: /model {agent}"
        return msg

    async def agent_usage(self, agent: str, timeout: float = 60) -> tuple[str, list[str]]:
        """Hạn mức / usage do chính CLI của agent báo: (lệnh đã dùng, các dòng kết quả)."""
        a = self.cfg.agents.get(agent)
        if not a:
            return "", [f"Không có agent '{agent}'"]
        if not a.usage_command:
            if Path(a.binary).name == "codex":
                lines = limits.codex_rate_limits()
                return "~/.codex/sessions", lines or ["Chưa có phiên codex nào ghi hạn mức — chạy 1 task codex trước."]
            return "", ["CLI này không có lệnh xem usage (đặt usage_command trong cấu hình nếu có)"]
        cmd = " ".join(a.usage_command)
        if not shutil.which(a.usage_command[0]):
            return cmd, [f"Chưa cài lệnh '{a.usage_command[0]}'"]
        run = Run(list(a.usage_command), str(self.root), self.env_for(), use_pty=a.pty,
                  timeout=timeout, on_line=lambda _l: None)
        try:
            code = await run.start()
        except Exception as e:
            return cmd, [f"Không chạy được: {e}"]
        lines = [ln for ln in run.lines if ln.strip()]
        if len(lines) > 20:  # opencode stats kèm bảng công cụ dài: giữ phần tổng quan / chi phí
            lines = lines[:20] + [f"… (còn {len(lines) - 20} dòng — chạy `{cmd}` để xem đủ)"]
        if run.timed_out:
            lines.append(f"(hết {int(timeout)} giây chờ)")
        elif code != 0:
            lines.append(f"(mã thoát {code})")
        return cmd, lines or ["(không in gì)"]

    async def usage_all(self, names: list[str] | None = None, on_done=None) -> dict[str, tuple[str, list[str]]]:
        """Hỏi song song hạn mức của các agent đang bật. on_done(agent, cmd, lines) gọi khi từng cái xong."""
        names = names if names is not None else list(self.cfg.active_agents())

        async def one(n: str):
            cmd, lines = await self.agent_usage(n)
            if on_done:
                on_done(n, cmd, lines)
            return n, (cmd, lines)
        return dict(await asyncio.gather(*(one(n) for n in names)))

    async def discover_all(self, names: list[str] | None = None, timeout: float = 20,
                           on_done=None) -> dict[str, str]:
        """Hỏi song song mọi agent đã cài có models_command. on_done(agent, msg) gọi khi từng cái xong."""
        names = [n for n in (names if names is not None else list(self.cfg.agents))
                 if n in self.cfg.agents and self.cfg.agents[n].models_command
                 and self.cfg.agents[n].installed()]

        async def one(n: str) -> tuple[str, str]:
            msg = await self.discover_models(n, timeout=timeout)
            if on_done:
                on_done(n, msg)
            return n, msg

        return dict(await asyncio.gather(*(one(n) for n in names)))

    def edit(self, tid: int, prompt: str) -> str:
        t = self.db.task(tid)
        if not t:
            return f"Không có task #{tid}"
        if t.status == RUNNING:
            return f"Task #{tid} đang chạy"
        self.db.update_task(tid, prompt=prompt)
        self.emit("changed")
        return f"Đã sửa nội dung task #{tid}"

    def retry(self, tid: int) -> str:
        t = self.db.task(tid)
        if not t:
            return f"Không có task #{tid}"
        if t.status in (RUNNING, QUEUED):
            return f"Task #{tid} đang {t.status}"
        self.db.update_task(tid, status=QUEUED, error=None, result=None, started=None, finished=None)
        for o in self.db.tasks(status=BLOCKED):
            if tid in o.depends_on:
                self.db.update_task(o.id, status=QUEUED, error=None)
        if t.goal_id:
            g = self.db.goal(t.goal_id)
            if g and g.status in ("done", "incomplete", "failed"):
                self.db.update_goal(g.id, status="running")
        self.log(f"↻ Chạy lại task #{tid}")
        self.emit("changed")
        return f"Đã xếp lại task #{tid}"

    def cancel(self, tid: int) -> str:
        t = self.db.task(tid)
        if not t:
            return f"Không có task #{tid}"
        if t.status == RUNNING and tid in self.runs:
            run = self.runs[tid]
            if run is not None:
                run.cancel()
            else:
                self._cancel_req.add(tid)
            return f"Đang dừng task #{tid}…"
        if t.status in (DRAFT, QUEUED):
            self.db.update_task(tid, status=CANCELLED, finished=time.time())
            self.emit("changed")
            return f"Đã huỷ task #{tid}"
        if t.status == REVIEW:
            self._spawn(self.reject(tid, None))
            return f"Đang huỷ task #{tid} và xoá nhánh của nó…"
        return f"Task #{tid} đã kết thúc ({t.status})"

    def note(self, text: str, author: str = "user") -> None:
        self.db.add_note(author, text)
        self.log(f"📝 Ghi chú ({author}): {text}")

    def compact_sources(self) -> tuple[str, str, str]:
        """Ghi chú, mục tiêu và log hệ thống kể từ lần /compact trước — thứ sẽ được tóm tắt."""
        since = self.db.last_compact()
        goals = "\n".join(f"#{g.id} [{g.status}] {g.full_text()}" + (f" — {g.summary}" if g.summary else "")
                          for g in self.db.goals()[-12:] if (g.created or 0) >= since)
        log = ""
        p = self.logs / "system.log"
        if p.exists():
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            log = "\n".join(lines[-60:])
        return self.notes_text(), goals, log

    async def compact(self, focus: str = "") -> tuple[bool, str]:
        """/compact: trưởng nhóm tóm tắt ghi chú + mục tiêu + log thành 1 ghi chú ngắn; prompt sau chỉ
        mang bản tóm tắt này (cùng ghi chú mới hơn) thay vì cả chuỗi ghi chú cũ. Trả về (thành công, lời nhắn)."""
        if self.compacting:
            return False, "Đang thu gọn ngữ cảnh rồi, chờ chút…"
        notes, goals, log = self.compact_sources()
        if not notes and not goals:
            return False, "Chưa có ghi chú hay mục tiêu nào để thu gọn."
        self.compacting = True
        try:
            self.log(f"🗜 {self.cfg.lead} đang thu gọn ngữ cảnh…")
            out = await self._call_lead(P.compact_prompt(notes=notes, goals=goals, log=log, focus=focus,
                                                         cwd=str(self.root)), "Thu gọn ngữ cảnh")
            summary = P.extract_summary(out) if out and "SUMMARY:" in out else ""
            if not summary:
                self.log("✗ Không thu gọn được: trưởng nhóm không trả về dòng SUMMARY: "
                         "(xem .ateam/logs/lead.log). Ghi chú cũ vẫn giữ nguyên.")
                return False, "Không thu gọn được — ghi chú cũ vẫn giữ nguyên"
            self.db.add_note(COMPACT_AUTHOR, summary)
            before = len(notes) + len(goals)
            self.log(f"🗜 Đã thu gọn ngữ cảnh: ~{before} → {len(summary)} ký tự. Bản tóm tắt:")
            for line in summary.splitlines():
                self.log("   " + line)
            return True, f"Đã thu gọn ngữ cảnh (~{before} → {len(summary)} ký tự)"
        finally:
            self.compacting = False
            self.emit("changed")

    async def commit_message(self) -> tuple[bool, str]:
        """Trưởng nhóm viết commit message cho thay đổi đã stage (chưa stage gì thì cho mọi thay đổi).
        Trả về (thành công, message hoặc lời nhắn lỗi)."""
        from .gitops import GitRepo
        repo = GitRepo(self.root)
        diff = await repo.staged_diff()
        if not diff:
            stat = await repo.diff_text("HEAD", "--stat")
            body = await repo.diff_text("HEAD")
            _, others = await repo.run("ls-files", "--others", "--exclude-standard")
            diff = (stat + "\n" + body[:60_000]).strip()
            if others.strip():
                diff += "\n\nNew untracked files:\n" + others.strip()
        if not diff.strip():
            return False, "Không có thay đổi nào để viết commit message"
        recent = "\n".join("- " + c.subject for c in await repo.log(8))
        out = await self._call_lead(P.commit_message_prompt(diff=diff, recent=recent, cwd=str(self.root)),
                                    "Viết commit message")
        msg = P.extract_commit_message(out or "")
        if not msg:
            return False, "Trưởng nhóm không trả về commit message (xem .ateam/logs/lead.log)"
        return True, msg

    def force_review(self, gid: int) -> str:
        g = self.db.goal(gid)
        if not g:
            return f"Không có mục tiêu #{gid}"
        if gid in self.lead_busy:
            return "Trưởng nhóm đang xử lý mục tiêu này"
        self.lead_busy.add(gid)
        self._spawn(self._review(gid))
        return f"Trưởng nhóm đang review mục tiêu #{gid}…"

    # ------------------------------------------------------------------ lịch chạy
    def running_count(self, agent: str | None = None) -> int:
        if agent is None:
            return len(self.runs)
        return sum(1 for tid in self.runs if (t := self.db.task(tid)) and t.agent == agent)

    def is_idle(self) -> bool:
        """Không còn việc gì chạy được (task chỉ chờ agent hồi hạn mức thì không tính)."""
        if self.runs or self.lead_busy:
            return False
        for t in self.db.tasks(status=QUEUED):
            if self.in_cooldown(t.agent) and not self.pick_fallback(t.agent):
                continue  # chờ hồi hạn mức
            deps = [self.db.task(d) for d in t.depends_on]
            if any(d and d.status in (REVIEW, DRAFT) for d in deps):
                continue  # chờ người duyệt
            return False
        return True

    def tick(self) -> None:
        agents = self.cfg.active_agents()
        changed = False
        for t in self.db.tasks(status=QUEUED):
            if t.id in self.runs:
                continue
            if t.agent not in agents:
                self.db.update_task(t.id, status=FAILED, error=f"Không có agent '{t.agent}'")
                changed = True
                continue
            dep_status = [(d, (self.db.task(d).status if self.db.task(d) else "missing"))
                          for d in t.depends_on]
            bad = [d for d, s in dep_status if s in FINISHED_BAD or s in (CONFLICT, "missing")]
            if bad:
                self.db.update_task(t.id, status=BLOCKED,
                                    error=f"Task phụ thuộc lỗi/huỷ: {', '.join('#'+str(b) for b in bad)}")
                self.log(f"⛔ Task #{t.id} bị chặn vì #{', #'.join(map(str, bad))} không xong.")
                changed = True
                continue
            if any(s != DONE for _, s in dep_status):
                continue
            if self.paused or len(self.runs) >= self.cfg.max_parallel:
                continue
            if self.in_cooldown(t.agent):
                fb = self.pick_fallback(t.agent)
                if not fb:
                    continue  # chờ hạn mức hồi lại
                self.db.update_task(t.id, agent=fb, model=None, effort=None)
                self.log(f"↪ #{t.id} chuyển từ {t.agent} sang {fb} vì {t.agent} hết hạn mức "
                         f"(đến {self.cooldown_label(t.agent)}).")
                t = self.db.task(t.id)
                changed = True
            a = agents[t.agent]
            if self.running_count(t.agent) >= a.max_concurrent:
                continue
            if not a.installed():
                self.db.update_task(t.id, status=FAILED,
                                    error=f"Chưa cài lệnh '{a.binary}' (kiểm tra bằng `ateam doctor`)")
                self.log(f"✗ Task #{t.id}: chưa cài '{a.binary}'.")
                changed = True
                continue
            # chiếm chỗ ngay để không chạy trùng
            self.db.update_task(t.id, status=RUNNING, started=time.time(), error=None)
            self.runs[t.id] = None  # type: ignore[assignment]
            self._spawn(self._run_task(t.id))
            changed = True
        if self._check_goals():
            changed = True
        if changed:
            self.emit("changed")

    def _check_goals(self) -> bool:
        changed = False
        for g in self.db.goals():
            if g.status != "running" or g.id in self.lead_busy:
                continue
            tasks = self.db.tasks(goal_id=g.id)
            if any(t.status in ACTIVE for t in tasks):
                continue
            if not tasks:
                continue
            wf = self.cfg.workflows.get(g.workflow or "")
            review = wf.review if wf and wf.review is not None else self.cfg.auto_review
            if review:
                self.lead_busy.add(g.id)
                self._spawn(self._review(g.id))
            else:
                ok = all(t.status == DONE for t in tasks)
                self.db.update_goal(g.id, status="done" if ok else "incomplete")
                self.log(f"🏁 Mục tiêu #{g.id} kết thúc ({'xong' if ok else 'còn task lỗi'}).")
            changed = True
        return changed

    async def run_forever(self, interval: float = 0.7) -> None:
        while True:
            try:
                self.tick()
            except Exception as e:  # không để vòng lặp chết
                self.log(f"Lỗi bộ lập lịch: {e!r}")
            await asyncio.sleep(interval)

    async def run_until_idle(self, interval: float = 0.5) -> None:
        while True:
            self.tick()
            await asyncio.sleep(interval)
            if self.is_idle():
                self.tick()
                await asyncio.sleep(interval)
                if self.is_idle():
                    return

    # ------------------------------------------------------------------ hạn mức
    def in_cooldown(self, agent: str) -> bool:
        until = self.cooldown.get(agent)
        if until and until > time.time():
            return True
        if until:
            self.cooldown.pop(agent, None)
            limits.save_cooldown(agent, None)
            self.log(f"▶ {agent} đã hồi hạn mức.")
        return False

    def cooldown_label(self, agent: str) -> str:
        until = self.cooldown.get(agent)
        return time.strftime("%H:%M %d/%m", time.localtime(until)) if until else "-"

    def _set_cooldown(self, agent: str, output: str) -> None:
        until = limits.reset_time(output, self.cfg.cooldown_minutes)
        self.cooldown[agent] = until
        limits.save_cooldown(agent, until)
        self.log(f"⏸ {agent} hết hạn mức — tạm nghỉ đến {self.cooldown_label(agent)}.")
        self.emit("changed")

    def set_cooldown_manual(self, agent: str, minutes: int | None) -> str:
        if agent not in self.cfg.agents:
            return f"Không có agent '{agent}'"
        if not minutes:
            self.cooldown.pop(agent, None)
            limits.save_cooldown(agent, None)
            self.log(f"▶ Bỏ tạm nghỉ cho {agent}.")
            self.emit("changed")
            return f"{agent} hoạt động lại"
        until = time.time() + minutes * 60
        self.cooldown[agent] = until
        limits.save_cooldown(agent, until)
        self.log(f"⏸ {agent} tạm nghỉ đến {self.cooldown_label(agent)} (đặt tay).")
        self.emit("changed")
        return f"{agent} tạm nghỉ {minutes} phút"

    def pick_fallback(self, agent: str, exclude: set[str] | None = None) -> str | None:
        a = self.cfg.agents.get(agent)
        for name in (a.fallback if a else []):
            fb = self.cfg.agents.get(name)
            if (fb and fb.enabled and name != agent and name not in (exclude or set())
                    and fb.installed() and not self.in_cooldown(name)):
                return name
        return None

    @staticmethod
    def _classify(run: Run, rc: int) -> str:
        if run.cancelled:
            return "cancelled"
        if run.timed_out:
            return "timeout"
        if limits.looks_rate_limited(run.output, rc):
            return "ratelimit"
        if rc != 0 and BAD_FLAG_RE.search(run.output):
            return "badflag"
        if DENIED_RE.search(run.output):
            return "denied"
        if rc != 0:
            return "failed"
        if not run.output.strip():
            return "empty"
        return "ok"

    # ------------------------------------------------------------------ chạy 1 task
    async def _run_agent(self, t: Task, a: AgentConfig, prompt: str, workdir: Path, log_file,
                         *, kind: str, title: str, model: str | None,
                         effort: str | None) -> tuple[Run, int, str]:
        """Chạy agent một lượt cho task t, ghi log, thống kê; trả (run, mã thoát, phân loại)."""
        label = a.label(model, effort)
        act = self._begin_activity(a.name, t.id, title, label)
        log_file.write(f"\n$ {a.name} · {kind} · {label} · {workdir}\n")
        rid = self.db.add_run(t.id, a.name, kind, len(prompt))

        def on_line(line: str) -> None:
            log_file.write(line + "\n")
            log_file.flush()
            self._touch(act, line)
            self.emit("log", task_id=t.id, agent=a.name, line=line)

        run = Run(self.argv_for(a, prompt, workdir, model=model, effort=effort), str(workdir),
                  self.env_for(t), use_pty=a.pty, timeout=a.timeout, on_line=on_line)
        self.runs[t.id] = run
        rc = 130
        try:
            if t.id in self._cancel_req:
                self._cancel_req.discard(t.id)
                run.cancelled = True
            else:
                rc = await run.start()
        finally:
            res = self._classify(run, rc)
            self.db.finish_run(rid, rc, res, len(run.output))
            act["status"] = {"ok": DONE, "cancelled": CANCELLED}.get(res, FAILED)
            self._end_activity(a.name, act)
        return run, rc, res

    async def _verify(self, t: Task, workdir: Path, log_file) -> tuple[bool, int, str]:
        cmd = self.cfg.verify.command
        act = self._begin_activity(t.agent, t.id, f"kiểm tra: {cmd}", "test")
        log_file.write(f"\n$ [kiểm tra] {cmd}\n")
        rid = self.db.add_run(t.id, t.agent, "test", len(cmd))

        def on_line(line: str) -> None:
            log_file.write("[test] " + line + "\n")
            log_file.flush()
            self._touch(act, line)
            self.emit("log", task_id=t.id, agent=t.agent, line="[test] " + line)

        run = Run(["/bin/sh", "-c", cmd], str(workdir), self.env_for(t), use_pty=False,
                  timeout=self.cfg.verify.timeout, on_line=on_line)
        self.runs[t.id] = run
        rc = await run.start()
        ok = rc == 0 and not run.cancelled
        self.db.finish_run(rid, rc, "ok" if ok else "failed", len(run.output))
        act["status"] = DONE if ok else FAILED
        self._end_activity(t.agent, act)
        tail = "\n".join(run.output.splitlines()[-120:])[-6000:]
        if run.timed_out:
            tail += f"\n(Lệnh kiểm tra quá {self.cfg.verify.timeout}s)"
        return ok, rc, tail

    async def _fingerprint(self, workdir: Path) -> str | None:
        """Dấu vân tay trạng thái code (git) để biết task có thay đổi gì không."""
        rc, head = await self._git("rev-parse", "HEAD", cwd=workdir)
        if rc != 0:
            return None
        _, diff = await self._git("diff", "HEAD", cwd=workdir)
        _, untracked = await self._git("ls-files", "--others", "--exclude-standard", cwd=workdir)
        h = hashlib.sha1((head + diff + untracked).encode())
        for name in untracked.splitlines():
            try:
                st = (workdir / name).stat()
                h.update(f"{name}{st.st_size}{st.st_mtime_ns}".encode())
            except OSError:
                pass
        return h.hexdigest()

    async def _run_task(self, tid: int) -> None:
        t = self.db.task(tid)
        agent = self.cfg.agents[t.agent]
        goal = self.db.goal(t.goal_id) if t.goal_id else None
        log_file = open(self.log_path(tid), "w", encoding="utf-8")
        status, error, summary = FAILED, None, None
        workdir = self.root
        outputs: list[str] = []
        new_agent: str | None = None
        v = self.cfg.verify
        try:
            if self.use_worktree:
                workdir = await self._wt_prepare(t)
            deps = []
            for d in t.depends_on:
                dt = self.db.task(d)
                if dt:
                    deps.append((dt.id, dt.agent, dt.title, dt.result or ""))
            if t.source == "user":  # /task: gửi nguyên văn người dùng gõ, không bọc vai trò/luật
                prompt = t.prompt
            elif t.source == "followup" and t.goal_id is None:  # hỏi tiếp thread /task
                prompt = P.thread_prompt(self.thread_of(t), t.prompt)
            else:
                prompt = P.task_prompt(
                    self.cfg, agent=t.agent, task_id=t.id, title=t.title, prompt=t.prompt,
                    goal=goal.full_text() if goal else None, deps=deps, notes=self.notes_text(),
                    cwd=str(workdir), can_delegate=t.depth < self.cfg.max_delegation_depth)
            gate = bool(v.command) and agent.verify
            before = await self._fingerprint(workdir) if gate and v.only_when_changed else None
            self.log(f"▶ #{tid} {t.agent}: {t.title}")

            run, rc, res = await self._run_agent(t, agent, prompt, workdir, log_file, kind="task",
                                                 title=t.title, model=t.model, effort=t.effort)
            outputs.append(run.output)
            status, error = self._status_of(res, rc, agent)
            if res == "ratelimit":
                self._set_cooldown(t.agent, run.output)
                new_agent = self.pick_fallback(t.agent)
                status, error = QUEUED, None

            # ---- cổng kiểm tra: chạy test, fail thì giao sửa
            attempts = 0
            while status == DONE and gate:
                if v.only_when_changed and before is not None:
                    if await self._fingerprint(workdir) == before:
                        log_file.write("\n(không có thay đổi file nào — bỏ qua kiểm tra)\n")
                        break
                ok, trc, tail = await self._verify(t, workdir, log_file)
                if ok:
                    self.log(f"✅ #{tid} qua kiểm tra `{v.command}`"
                             + (f" sau {attempts} lần sửa" if attempts else ""))
                    break
                if run.cancelled or tid in self._cancel_req:
                    status, error = CANCELLED, "Bị huỷ"
                    break
                if attempts >= v.max_fix_attempts:
                    status = FAILED
                    error = (f"Kiểm tra `{v.command}` vẫn fail (mã {trc})"
                             + (f" sau {attempts} lần sửa" if attempts else "") + " — xem log [test]")
                    break
                attempts += 1
                self.db.update_task(tid, attempts=attempts)
                fixer = v.fix_agent if v.fix_agent in self.cfg.active_agents() else t.agent
                if self.in_cooldown(fixer):
                    fixer = self.pick_fallback(fixer) or fixer
                fa = self.cfg.agents[fixer]
                self.log(f"🔧 #{tid} test fail (mã {trc}) — {fixer} sửa lần {attempts}/{v.max_fix_attempts}")
                fprompt = P.fix_prompt(agent=fixer, task_id=tid, title=t.title, prompt=t.prompt,
                                       command=v.command, rc=trc, output=tail, attempt=attempts,
                                       max_attempts=v.max_fix_attempts, cwd=str(workdir),
                                       original_agent=t.agent)
                same = fixer == t.agent
                run, rc, res = await self._run_agent(
                    t, fa, fprompt, workdir, log_file, kind="fix",
                    title=f"sửa lỗi test #{tid} ({attempts}/{v.max_fix_attempts})",
                    model=t.model if same else None, effort=t.effort if same else None)
                outputs.append(run.output)
                if res == "ratelimit":
                    self._set_cooldown(fixer, run.output)
                    status, error = FAILED, f"{fixer} hết hạn mức khi đang sửa lỗi test — /retry sau"
                    break
                status, error = self._status_of(res, rc, fa)

            summary = P.extract_summary(outputs[0]) if outputs else None
            if len(outputs) > 1 and status == DONE:
                summary = (summary or "") + f"\n(Đã sửa để qua kiểm tra: {P.extract_summary(outputs[-1])[:600]})"
            for out in outputs:
                for n in P.parse_notes(out):
                    self.db.add_note(t.agent, n)

            if self.use_worktree:
                status, error = await self._wt_finish(t, workdir, status, error)
            if status == DONE:
                self._delegations(t, "\n".join(outputs))
        except Exception as e:
            status, error = FAILED, f"Lỗi nội bộ: {e!r}"
        finally:
            log_file.close()
            self.runs.pop(tid, None)
            if status == QUEUED:  # hết hạn mức: xếp hàng lại, có thể đổi agent
                fields = {"status": QUEUED, "started": None, "error": None}
                if new_agent:
                    fields.update(agent=new_agent, model=None, effort=None)
                self.db.update_task(tid, **fields)
                self.log(f"↪ #{tid} xếp hàng lại" + (f", chuyển sang {new_agent}" if new_agent
                                                     else f", chờ {t.agent} hồi hạn mức"))
            else:
                self.db.update_task(tid, status=status, error=error, result=summary,
                                    finished=time.time())
                icon = {DONE: "✓", CANCELLED: "■", CONFLICT: "⚠", REVIEW: "👀"}.get(status, "✗")
                self.log(f"{icon} #{tid} {t.agent}: {status}" + (f" — {error}" if error else ""))
            self.emit("changed")

    def _status_of(self, res: str, rc: int, a: AgentConfig) -> tuple[str, str | None]:
        return {
            "ok": (DONE, None),
            "cancelled": (CANCELLED, "Bị huỷ"),
            "timeout": (FAILED, f"Quá thời gian ({a.timeout}s)"),
            "failed": (FAILED, f"Thoát với mã {rc}"),
            "badflag": (FAILED, f"{a.binary} không nhận một cờ trong lệnh (CLI có thể đã đổi phiên bản)"
                                " — chạy `ateam doctor` rồi sửa command trong cấu hình"),
            "empty": (FAILED, "Agent không in ra gì (kiểm tra đăng nhập / quyền / pty)"),
            "denied": (FAILED, f"{a.name} bị chặn chạy lệnh (thiếu quyền) — bật Toàn quyền cho agent này ở "
                               "/setup (agent có sẵn) hoặc /custom (agent tuỳ chỉnh), rồi /retry"),
            "ratelimit": (FAILED, f"{a.name} hết hạn mức"),
        }[res]

    def _delegations(self, t: Task, output: str) -> None:
        dels = P.parse_delegations(output)
        if not dels:
            return
        if t.depth >= self.cfg.max_delegation_depth:
            self.log(f"⚠ #{t.id} muốn giao việc nhưng đã chạm giới hạn {self.cfg.max_delegation_depth} tầng.")
            return
        agents = self.cfg.active_agents()
        for to, title, body in dels[:MAX_DELEGATIONS_PER_TASK]:
            if to not in agents:
                self.log(f"⚠ #{t.id} giao việc cho '{to}' — không có trong đội, bỏ qua.")
                continue
            nid = self.db.add_task(to, title or body[:60], body, goal_id=t.goal_id,
                                   parent_id=t.id, depth=t.depth + 1,
                                   status=QUEUED, source=f"delegate:{t.agent}")
            self.log(f"🤝 {t.agent} giao task #{nid} cho {to}: {title or body[:60]}")

    # ------------------------------------------------------------------ review
    async def _review(self, gid: int) -> None:
        try:
            g = self.db.goal(gid)
            self.db.update_goal(gid, status="reviewing")
            self.emit("changed")
            self.log(f"🔍 {self.cfg.lead} đang review mục tiêu #{gid} (vòng {g.round})…")
            out = await self._call_lead(
                P.review_prompt(self.cfg, g.full_text(), g.round, self._results_text(gid), str(self.root)),
                f"Review mục tiêu #{gid} vòng {g.round}")
            data = P.extract_json(out or "", dict)
            if not data:
                self.db.update_goal(gid, status="incomplete",
                                    summary="Không đọc được kết quả review (xem .ateam/logs/lead.log)")
                self.log(f"⚠ Không đọc được review của mục tiêu #{gid}.")
                return
            summary = str(data.get("summary", "")).strip()
            new = data.get("new_tasks") or []
            if data.get("done") or not new:
                self.db.update_goal(gid, status="done" if data.get("done") else "incomplete",
                                    summary=summary)
                self.log(f"🏁 Mục tiêu #{gid} {'HOÀN THÀNH' if data.get('done') else 'kết thúc'}: {summary}")
            elif g.round >= self.cfg.max_rounds:
                self.db.update_goal(gid, status="incomplete", summary=summary)
                self.log(f"🏁 Mục tiêu #{gid} đã hết {self.cfg.max_rounds} vòng. Đánh giá: {summary}")
            else:
                self.db.update_goal(gid, round=g.round + 1, summary=summary,
                                    status="awaiting" if self.cfg.approve_plan else "running")
                self.log(f"🔁 Review #{gid}: {summary}")
                ids = self._insert_plan(gid, new, source="review")
                if self.cfg.approve_plan:
                    self.log(f"📋 {len(ids)} task bổ sung đang ở trạng thái NHÁP — /go {gid} để chạy.")
        finally:
            self.lead_busy.discard(gid)
            self.emit("changed")

    def _results_text(self, gid: int) -> str:
        """Kết quả các task của mục tiêu, gửi trưởng nhóm khi review / lập kế hoạch tiếp."""
        lines = []
        for t in self.db.tasks(goal_id=gid):
            if t.status == CANCELLED:
                continue
            body = (t.result or t.error or "")[:1500]
            lines.append(f"#{t.id} [{t.agent}] {t.status}: {t.title}\n{body}\n")
        return "\n".join(lines)

    # ------------------------------------------------------------------ git worktree
    async def git_ident(self) -> list[str]:
        """Cờ `-c user.name/email` dự phòng khi máy chưa cấu hình git identity (vd máy CI).
        Kiểm tra lúc cần, vì lệnh CLI như `ateam merge` không chạy setup()."""
        if self._git_ident is None:
            rc, email = await self._git("config", "user.email")
            self._git_ident = ([] if rc == 0 and email.strip() else
                               ["-c", "user.name=ateam", "-c", "user.email=ateam@localhost"])
        return self._git_ident

    def _merge_lock(self) -> asyncio.Lock:
        # Python 3.9: asyncio.Lock() gắn vào event loop lúc tạo; tạo trong __init__ (ngoài vòng lặp, sau một
        # asyncio.run() trước đó) báo "There is no current event loop" -> tạo lần đầu dùng, trong vòng lặp
        if self._merge_lock_obj is None:
            self._merge_lock_obj = asyncio.Lock()
        return self._merge_lock_obj

    async def _git(self, *args: str, cwd: Path | None = None) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=str(cwd or self.root), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        return proc.returncode, out.decode("utf-8", "replace")

    async def _wt_prepare(self, t: Task) -> Path:
        path = self.state / "worktrees" / f"t{t.id}"
        branch = f"ateam/t{t.id}"
        if path.exists():
            await self._git("worktree", "remove", "--force", str(path))
        await self._git("worktree", "prune")
        _, base = await self._git("rev-parse", "HEAD")
        self._wt_base[t.id] = base.strip()
        rc, out = await self._git("worktree", "add", "-B", branch, str(path), "HEAD")
        if rc != 0:
            raise RuntimeError(f"git worktree add thất bại: {out.strip()}")
        self.db.update_task(t.id, branch=branch, base=base.strip(), head=None)
        return path

    async def _wt_finish(self, t: Task, path: Path, status: str,
                         error: str | None) -> tuple[str, str | None]:
        """Commit thay đổi của task; tự merge (merge=auto) hoặc để chờ duyệt (merge=review)."""
        branch = f"ateam/t{t.id}"
        await self._git("add", "-A", cwd=path)
        _, st = await self._git("status", "--porcelain", cwd=path)
        if st.strip():
            await self._git(*(await self.git_ident()), "commit", "-q", "-m",
                            f"ateam #{t.id} ({t.agent}): {t.title}", cwd=path)
        _, head = await self._git("rev-parse", "HEAD", cwd=path)
        await self._git("worktree", "remove", "--force", str(path))
        base = self._wt_base.pop(t.id, "") or (t.base or "")
        rc, cnt = await self._git("rev-list", "--count", f"{base}..{branch}") if base else (1, "")
        empty = rc == 0 and cnt.strip() == "0"
        self.db.update_task(t.id, head=head.strip() or None)
        if empty:  # task không đổi gì: không cần merge
            await self._git("branch", "-D", branch)
            self.db.update_task(t.id, branch=None)
            return status, error
        if status == QUEUED:  # hết hạn mức: bỏ phần dở dang, chạy lại từ đầu
            await self._git("branch", "-D", branch)
            return status, error
        if status != DONE:
            return status, error  # giữ nhánh để xem lại
        if self.cfg.merge == "review":
            self.log(f"👀 #{t.id} chờ duyệt merge — /diff {t.id} để xem, /merge {t.id} hoặc /reject {t.id}")
            return REVIEW, None
        ok, msg = await self._merge_branch(t)
        if ok:
            return DONE, None
        return CONFLICT, msg

    async def _merge_branch(self, t: Task) -> tuple[bool, str | None]:
        branch = f"ateam/t{t.id}"
        async with self._merge_lock():
            rc, out = await self._git(*(await self.git_ident()), "merge", "--no-ff", "--no-edit", "-m",
                                      f"ateam: merge #{t.id} ({t.agent}) {t.title}", branch)
            if rc != 0:
                await self._git("merge", "--abort")
                self.log(f"⚠ Merge #{t.id} lỗi: {out.strip()[:300]}")
                return False, (f"Không merge được nhánh {branch} (xung đột hoặc thư mục chính đang "
                               f"có thay đổi) — tự merge tay, /merge {t.id} để thử lại, hoặc /retry")
        await self._git("branch", "-D", branch)
        return True, None

    # ------------------------------------------------------------------ duyệt merge
    async def merge(self, tid: int) -> str:
        t = self.db.task(tid)
        if not t:
            return f"Không có task #{tid}"
        if t.status not in (REVIEW, CONFLICT) or not t.branch:
            return f"Task #{tid} không có nhánh chờ merge ({t.status})"
        ok, msg = await self._merge_branch(t)
        if not ok:
            self.db.update_task(tid, status=CONFLICT, error=msg)
            self.emit("changed")
            return f"Merge #{tid} thất bại — xem log hệ thống"
        self.db.update_task(tid, status=DONE, error=None, branch=None, finished=time.time())
        self.log(f"✓ Đã merge #{tid} ({t.agent}): {t.title}")
        try:
            self._delegations(t, self.log_path(tid).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
        self.emit("changed")
        return f"Đã merge #{tid}"

    async def reject(self, tid: int, feedback: str | None) -> str:
        t = self.db.task(tid)
        if not t:
            return f"Không có task #{tid}"
        if t.status not in (REVIEW, CONFLICT):
            return f"Task #{tid} không ở trạng thái chờ duyệt ({t.status})"
        if t.branch:
            await self._git("branch", "-D", t.branch)
        if feedback:
            prompt = (t.prompt + f"\n\nREVIEWER FEEDBACK (previous attempt was rejected — address this):"
                      f"\n{feedback}")
            self.db.update_task(tid, status=QUEUED, prompt=prompt, branch=None, head=None,
                                error=None, result=None, started=None, finished=None)
            self.log(f"↩ Từ chối #{tid}, giao làm lại kèm góp ý: {feedback}")
            msg = f"Đã giao làm lại #{tid} kèm góp ý"
        else:
            self.db.update_task(tid, status=CANCELLED, branch=None, error="Bị từ chối khi duyệt",
                                finished=time.time())
            self.log(f"✗ Từ chối và huỷ #{tid}")
            msg = f"Đã huỷ #{tid}"
        self.emit("changed")
        return msg

    async def _git_bytes(self, *args: str) -> tuple[int, bytes]:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=str(self.root), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await proc.communicate()
        return proc.returncode, out

    async def diff_files(self, tid: int) -> "DiffSet | str":
        """Diff có cấu trúc (từng file) cho màn hình xem diff; str = thông báo khi không xem được."""
        from .diffview import DiffSet, added_file, parse_unified
        t = self.db.task(tid)
        if not t:
            return f"Không có task #{tid}"
        git = ("-c", "core.quotePath=false", "diff", "-M", "--no-color")
        if t.base and (t.head or t.branch):
            head = t.head or t.branch
            rc, body = await self._git(*git, t.base, head)
            if rc != 0:
                return f"Không lấy được diff của task #{tid}: {body.strip()[:200]}"
            files = parse_unified(body)
            if not files:
                return f"Task #{tid} không thay đổi file nào."
            return DiffSet(tid, f"Diff #{tid} · {t.base[:8]}..{head[:12]}", files, t.base, head)
        rc, body = await self._git(*git, "HEAD")
        if rc != 0:
            return "Thư mục này không phải git repo (hoặc chưa có commit nào) — không xem được diff."
        files = parse_unified(body)
        _, others = await self._git("ls-files", "--others", "--exclude-standard", "-z")
        for path in [p for p in others.split("\0") if p and not p.startswith(".ateam/")]:
            f = self.root / path
            try:
                data = f.read_bytes() if f.stat().st_size <= 1_000_000 else None
            except OSError:
                continue
            try:
                text = data.decode("utf-8") if data is not None and b"\0" not in data else None
            except UnicodeDecodeError:
                text = None
            files.append(added_file(path, text))
        if not files:
            return "Không có thay đổi nào chưa commit."
        return DiffSet(tid, f"Thay đổi chưa commit của thư mục (chế độ shared, không tách theo task #{tid})",
                       files, "HEAD", None)

    async def diff_versions(self, ds, fd) -> tuple[Path, Path]:
        """Hai bản (cũ, mới) của một file trong diff, ghi ra .ateam/diff/ để mở bằng `code --diff`."""
        out = self.state / "diff" / f"t{ds.tid}"
        old = out / "old" / (fd.old_path or fd.path)
        new = out / "new" / fd.path
        old.parent.mkdir(parents=True, exist_ok=True)
        new.parent.mkdir(parents=True, exist_ok=True)
        data = b""
        if fd.status != "A":
            _, data = await self._git_bytes("show", f"{ds.base}:{fd.old_path or fd.path}")
        old.write_bytes(data)
        if ds.head is None and fd.status != "D":
            return old, self.root / fd.path  # chế độ shared: bản mới là file đang có trong thư mục
        data = b""
        if fd.status != "D":
            _, data = await self._git_bytes("show", f"{ds.head}:{fd.path}")
        new.write_bytes(data)
        return old, new

    async def diff(self, tid: int) -> str:
        """Diff của task (chế độ worktree), hoặc diff hiện tại của cả thư mục (shared)."""
        t = self.db.task(tid)
        if not t:
            return f"Không có task #{tid}"
        if t.base and (t.head or t.branch):
            head = t.head or t.branch
            _, stat = await self._git("diff", "--stat", t.base, head)
            _, body = await self._git("diff", t.base, head)
            if not body.strip():
                return f"Task #{tid} không thay đổi file nào."
            return f"Diff #{tid} ({t.base[:8]}..{head[:12]}):\n{stat}\n{body}"
        rc, stat = await self._git("diff", "HEAD", "--stat")
        if rc != 0:
            return "Thư mục này không phải git repo — không xem được diff."
        _, body = await self._git("diff", "HEAD")
        return ("(Chế độ shared không tách được diff theo từng task — đây là mọi thay đổi chưa commit "
                "của thư mục)\n" + (stat + "\n" + body if body.strip() else "Không có thay đổi nào."))
