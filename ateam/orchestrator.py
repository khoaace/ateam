"""Bộ điều phối: trưởng nhóm lập kế hoạch, lịch chạy theo phụ thuộc, giao việc chéo, review, worktree."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Callable

from . import checkpoint
from . import limits
from . import mentions
from . import usage_logs
from . import overview
from . import prompts as P
from . import rules
from . import schedule
from . import skills
from .config import (EFFORT_REJECTED_RE, KIND_CODE, KIND_GATE, KIND_REVIEW, KIND_VERIFY, LEAD_ALIAS, AgentConfig,
                     Config, task_kind)
from .db import (ACTIVE, ASKING, BLOCKED, CANCELLED, COMPACT_AUTHOR, CONFLICT, DB, DONE, DRAFT, FAILED,
                 FINISHED_BAD, GOAL_ENDED, QUEUED, REVIEW, RUNNING, Goal, Task)
from .logtail import read_tail
from .runner import Run
from .opencode import ATTACHMENT_MAX, Catalog, OpenCode, standard_models
from .i18n import tr

SYSTEM_LOG_MAX = 5 * 1024 ** 2

GRILL_MAX = 15  # /grill: số câu hỏi tối đa, tới đây trưởng nhóm phải chốt đặc tả
PLAN_ASK_MAX = 3  # hỏi lại khi lập kế hoạch (người dùng không gọi /grill): chỉ vài câu thiết yếu

SYSTEM = 0  # id "task" của log hệ thống
CHAT = "chat"  # nguồn task của lượt chat trực tiếp với agent (Orchestrator.chat): không hiện ở bảng việc
MAX_ASKS = 3  # số câu <<<ASK>>> tối đa một task được hỏi người dùng
NOTE_MAX = 500  # ký tự mỗi ghi chú của agent đưa vào prompt (notes_text)
MAX_REQUEUES = 5  # số lần một task được tự xếp lại vì hết hạn mức / quá tải trong một phiên, quá thì báo lỗi
QUICK_EFFORT = "low"  # lượt nhanh (viết commit message, giải thích code): không cần effort cao đặt cho lập kế hoạch
UNTRACKED_MAX = 100  # số file chưa track gửi kèm khi viết commit message
CHAT_REPLY_MAX = 12000  # độ dài câu trả lời chat giữ lại (thread / chuyển phiên)
HANDOFF_MAX = 4000  # SUMMARY giữ lại của task có task khác chờ (phân tích / thiết kế / review bàn giao dài hơn)
# --resume thất bại vì CLI không còn phiên đó (đã xoá, khác thư mục…) -> chạy lại với prompt đầy đủ
SESSION_LOST_RE = re.compile(r"no conversation found|session[^\n]{0,60}not (?:be )?found|no (?:saved )?session"
                             r"|could not find[^\n]{0,30}(?:session|conversation|rollout|thread)"
                             r"|(?:rollout|thread)[^\n]{0,60}not found", re.I)
MAX_DELEGATIONS_PER_TASK = 5


def pick_option(q: dict | None, text: str) -> str:
    """Câu trả lời người dùng gõ: số 1…n = chọn phương án đó (/grill, <<<ASK>>>), còn lại giữ nguyên."""
    text = text.strip()
    opts = (q or {}).get("options") or []
    return opts[int(text) - 1] if text.isdigit() and 1 <= int(text) <= len(opts) else text
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
# agent đã viết tới dòng SUMMARY: (agy viết "**SUMMARY:**") -> làm xong dù CLI thoát mã khác 0
# (opencode 2.0 thoát 1 sau câu trả lời đầy đủ khi một lần Web Search bị huỷ giữa phiên)
SUMMARY_LINE_RE = re.compile(r"^[*#\s]*SUMMARY:", re.M)


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
        self.lead_runs: dict[int, Run] = {}  # lượt trưởng nhóm đang chạy theo mục tiêu (huỷ khi bỏ /grill)
        self._lead_stop: set[int] = set()  # mục tiêu người dùng huỷ lúc đang lập kế hoạch: không thử agent dự phòng
        self.compacting = False  # /compact đang chạy
        self.initing = False  # /init đang chạy
        self._overview_hinted = False  # đã nhắc /init trong lần mở app này
        self._overview_sent: dict[str, str] = {}  # phiên trưởng nhóm -> digest khối bản tổng quan đã gửi trong phiên đó
        self.lead_live: set[Run] = set()  # lượt trưởng nhóm đang chạy (lập kế hoạch, review, /init…) — dừng khi thoát app
        self.paused = False
        self.auto_answer = False  # chạy không tương tác (ateam goal -y / run): tự trả lời <<<ASK>>>
        self.use_worktree = False
        self.on_shell_release: Callable[[int], None] | None = None  # đóng ⌨ shell của task (GridHub.close_task_shells)
        self._git_ident: list[str] | None = None  # None = chưa kiểm tra
        self._merge_lock_obj: asyncio.Lock | None = None  # tạo khi dùng (xem _merge_lock)
        self._bg: set[asyncio.Task] = set()
        self._usage_jobs: set[asyncio.Task] = set()  # đọc token sau mỗi lượt (run_until_idle chờ xong)
        self._cancel_req: set[int] = set()
        self._requeues: dict[int, int] = {}  # task -> số lần đã tự xếp lại vì hết hạn mức / quá tải (MAX_REQUEUES)
        # task kiểm tra cuối đang chạy lệnh kiểm tra (chưa gọi agent): không giữ suất của agent sửa
        self._checking: set[int] = set()
        self._rules_sent: dict[str, str] = {}  # phiên CLI -> digest bộ rule đã gửi trong phiên đó
        self._chat_new: set[str] = set()  # agent mà tin chat kế tiếp bắt đầu cuộc mới
        self._wt_base: dict[int, str] = {}
        # hoạt động hiện tại của từng agent (cho tab Agents)
        self.activity: dict[str, dict] = {}
        # các lần trưởng nhóm lập kế hoạch / review: (bắt đầu, kết thúc|None, nhãn)
        self.lead_spans: list[list] = []
        # agent đang tạm nghỉ vì hết hạn mức: tên -> thời điểm hồi lại
        self.cooldown: dict[str, float] = limits.load_cooldowns()
        # hạn mức 5h/tuần gần nhất giao diện hỏi được (quota.collect) — lịch "khi hồi hạn mức" dùng
        self.quota_items: list[dict] | None = None
        self._sched_at = 0.0  # lần cuối xem lịch hẹn (check_schedules)
        self._cp_pending: set[int] = set()  # mục tiêu đang chụp điểm khôi phục: task của nó chưa chạy (checkpoint.py)
        self.opencode = OpenCode(self.root, self.env_for, self.log)
        self._opencode_applied: dict[str, tuple[AgentConfig, str, Catalog]] = {}

    # ------------------------------------------------------------------ tiện ích
    def emit(self, kind: str, **data) -> None:
        try:
            self.on_event(kind, data)
        except Exception:
            pass

    def log(self, msg: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {msg}"
        path = self.logs / "system.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            if f.tell() > SYSTEM_LOG_MAX:  # không để system.log lớn mãi: giữ một bản cũ system.log.1
                os.replace(path, path.with_name("system.log.1"))
        self.emit("log", task_id=SYSTEM, line=line)

    def log_path(self, tid: int) -> Path:
        return self.logs / f"t{tid}.log"

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.get_running_loop().create_task(coro)
        self._bg.add(t)
        t.add_done_callback(self._bg_done)
        return t

    def _bg_done(self, t: asyncio.Task) -> None:
        self._bg.discard(t)
        if not t.cancelled() and t.exception() is not None:  # lỗi ngoài dự kiến: ghi lại thay vì im lặng
            self.log(tr("⚠ Lỗi nội bộ: {e!r}", e=t.exception()))

    def _usage_job(self, rid: int, a: AgentConfig, prompt: str, session: str | None = None,
                   usage: usage_logs.Usage | None = None) -> None:
        t = self._spawn(self._collect_usage(rid, a, prompt, session, usage))
        self._usage_jobs.add(t)
        t.add_done_callback(self._usage_jobs.discard)

    async def _collect_usage(self, rid: int, a: AgentConfig, prompt: str, session: str | None = None,
                             usage: usage_logs.Usage | None = None) -> None:
        """Token & cost của lượt vừa xong: CLI tự báo trong output (`usage`, agy stream-json) hoặc đọc file phiên
        của CLI (usage_logs), không có thì ước tính ~4 ký tự/token. Chạy nền trong thread (đọc file), không giữ
        chậm task."""
        r = self.db.run(rid)
        if not r:
            return
        u = usage
        if u is None:
            await asyncio.sleep(0.3)  # CLI ghi xong file phiên
            try:
                u = await asyncio.to_thread(usage_logs.collect, a.binary, r["cwd"] or str(self.root),
                                            r["started"], r["finished"] or time.time(), prompt, session)
            except Exception:
                u = None
        src = "cli" if u else "estimate"
        if not u:
            u = usage_logs.Usage(in_tok=(r["prompt_chars"] or 0) // 4, out_tok=(r["output_chars"] or 0) // 4,
                                 model=r["model"] or "")
        u.model = u.model or r["model"] or ""
        try:
            self.db.set_run_usage(rid, model=u.model, in_tok=u.in_tok, out_tok=u.out_tok, cache_read=u.cache_read,
                                  cache_write=u.cache_write, cost=usage_logs.cost_of(u, self.cfg.prices), src=src)
        except Exception:  # DB đang đóng (thoát app)
            return
        self.emit("changed")

    def argv_for(self, a: AgentConfig, prompt: str, workdir: Path, *, model: str | None = None,
                 effort: str | None = None, plan: bool = False, session: str | None = None,
                 resume: bool = False) -> list[str]:
        """Lệnh chạy agent, đã đổi @đường-dẫn sang cú pháp của CLI đó (xem mentions.py) và kèm rule của dự án."""
        prompt = self.with_rules(a, prompt, lead=plan, session=session, resume=resume)
        want = (effort or a.effort or "").strip()
        if (a.opencode_major or 0) >= 2:
            want = (effort or (model or a.model or "").partition("#")[2] or a.effort or "").strip()
        got = a.resolve_effort((model or a.model or ""), want)
        if want and got != want:
            self.log(tr("⚙ {agent}: model {model} không có effort '{want}' → dùng {got}", agent=a.name,
                        model=model or a.model or tr("mặc định"), want=want, got=got or tr("mặc định của CLI")))
        prompt, extra = mentions.render(prompt, a.binary, [Path(workdir), self.root],
                                        file_ref=a.file_ref, file_args=a.file_args,
                                        image_args=a.image_args,
                                        attachment_limit=ATTACHMENT_MAX if (a.opencode_major or 0) >= 2 else None)
        if prompt.startswith("-"):  # chat / `/task` gửi nguyên văn: "- sửa nút" bị clap/commander hiểu là cờ
            prompt = " " + prompt
        return mentions.insert_args(a.argv(prompt, model=model, effort=effort, plan=plan, session=session,
                                           resume=resume), prompt, extra)

    def with_rules(self, a: AgentConfig, prompt: str, *, lead: bool = False, session: str | None = None,
                   resume: bool = False) -> str:
        """Đặt rule của dự án (/rules, rules.py) trước prompt. Lượt tiếp tục phiên CLI (--resume) thì phiên đã có
        rule — chỉ gửi lại khi bộ rule đổi từ lần gửi trước trong phiên đó."""
        items = rules.active_for(self.root, a.name, a.role or "", lead or a.name == self.cfg.lead)
        d = rules.digest(items)
        if resume and session:
            sent = self._rules_sent.setdefault(session, d)  # phiên từ lần mở app trước: coi như đã có
            if sent == d:
                return prompt
            self._rules_sent[session] = d
            return (rules.block(items, updated=True) if items else
                    "PROJECT RULES: the user removed all project rules — ignore the earlier ones.\n\n---\n\n") + prompt
        if session:
            self._rules_sent[session] = d
        return rules.block(items) + prompt

    @staticmethod
    def new_session(a: AgentConfig) -> str | None:
        """Id phiên cho lượt mới: ateam tự đặt nếu CLI cho phép (--session-id), không thì bắt từ output."""
        return str(uuid.uuid4()) if a.can_resume() and a.session_flags(False) else None

    @staticmethod
    def session_of(a: AgentConfig, run: Run, session: str | None) -> str | None:
        pat = a.session_pattern()
        if pat and a.can_resume():
            m = None
            for m in re.finditer(pat, "\n".join([run.output, *run.meta])):
                pass
            if m:
                return m.group(1)
        return session

    def effort_rejected(self, a: AgentConfig, model: str | None, effort: str | None, run: Run,
                        rc: int) -> bool:
        """CLI từ chối cờ effort với model này (thoát lỗi ngay) -> ghi nhớ để lần sau không gửi; True = chạy lại."""
        m = (model if model else a.model) or ""
        if rc == 0 or run.cancelled or not a.effort_args or not a.split_effort(m, (effort or a.effort) or "")[1]:
            return False
        if not EFFORT_REJECTED_RE.search(run.output[-4000:]):
            return False
        a.no_effort.add(m)
        self.log(tr("⚠ {agent} không nhận effort với model {model} — chạy lại không kèm effort",
                    agent=a.name, model=m or tr("mặc định")))
        return True

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
        """Ghi chú gửi kèm prompt; ghi chú của agent cắt ở NOTE_MAX ký tự (một agent dán dài không làm phình mọi prompt
        sau) — ghi chú người dùng và bản /compact giữ nguyên."""
        def clip(author: str, text: str) -> str:
            if author in ("user", COMPACT_AUTHOR) or len(text) <= NOTE_MAX:
                return text
            return text[:NOTE_MAX].rstrip() + "…"
        return "\n".join(f"- [{a}] {clip(a, t)}" for a, t in self.db.recent_notes())

    async def overview_changes(self, commit: str) -> tuple[int | None, list[str]]:
        """(số commit, file đã đổi) kể từ commit lúc viết bản tổng quan; số commit None nếu không biết (không có git,
        commit không còn sau rebase…)."""
        if not commit:
            return None, []
        rc, n = await self._git("rev-list", "--count", f"{commit}..HEAD")
        if rc != 0 or not n.strip().isdigit():
            return None, []
        rc, names = await self._git("diff", "--name-only", commit, "HEAD")
        return int(n.strip()), names.split() if rc == 0 else []

    async def overview_block(self, hint: bool = False, session: str | None = None) -> str:
        """Khối PROJECT OVERVIEW (/init) gửi kèm prompt. hint: lượt lập kế hoạch — nhắc chạy /init (một lần mỗi
        lần mở app) khi chưa có bản tổng quan hoặc nó đã cũ. session: phiên trưởng nhóm sẽ được tiếp tục — đã nhận
        đúng khối này thì chỉ gửi một dòng nhắc (overview.SEEN) thay vì cả bản."""
        text, meta = overview.load(self.root)
        commits, changed = await self.overview_changes(meta.get("commit", "")) if text else (None, [])
        if hint and not self._overview_hinted:
            if not text:
                self._overview_hinted = True
                self.log(tr("💡 Chưa có bản tổng quan dự án — gõ /init để trưởng nhóm tìm hiểu dự án một lần, "
                            "các kế hoạch sau đỡ phải đọc lại code."))
            elif commits is not None and commits >= overview.STALE_COMMITS:
                self._overview_hinted = True
                self.log(tr("💡 Bản tổng quan dự án đã cũ ({n} commit từ lần /init) — gõ /init để cập nhật.",
                            n=commits))
        block = overview.block(text, meta, changed, commits)
        if block and session and self._overview_sent.get(session) == overview.digest(block):
            return overview.SEEN
        return block

    def _lead_session(self, g: Goal | None) -> str | None:
        """Phiên trưởng nhóm của mục tiêu mà lượt kế tiếp sẽ tiếp tục (như _call_lead chọn), hoặc None."""
        lead = self.cfg.agents.get(self.cfg.lead)
        if g and g.lead_session and lead and lead.can_resume() and g.lead_session_agent == lead.name:
            return g.lead_session
        return None

    def _overview_seen(self, gid: int, block: str) -> None:
        """Phiên trưởng nhóm của mục tiêu vừa nhận khối bản tổng quan này: lượt tiếp phiên sau không gửi lại."""
        g = self.db.goal(gid)
        if block and block != overview.SEEN and g and g.lead_session:
            self._overview_sent[g.lead_session] = overview.digest(block)

    def all_runs(self) -> list[Run]:
        """Mọi tiến trình agent đang chạy: task (kể cả lệnh kiểm tra) và lượt trưởng nhóm — để dừng hết khi thoát app."""
        return [r for r in self.runs.values() if r is not None] + list(self.lead_live)

    # ------------------------------------------------------------------ khởi động
    async def setup(self, cleanup: bool = True) -> None:
        """cleanup=False: phiên giao diện khác đang chạy trên dự án — task RUNNING/mục tiêu đang lập
        kế hoạch là của phiên đó, không phải dở dang."""
        await self.apply_isolation()
        await asyncio.gather(*(self.prepare_agent(a) for a in self.cfg.active_agents().values()))
        if not cleanup:
            return
        # dọn trạng thái dở dang từ phiên trước
        for t in self.db.tasks(status=RUNNING):
            self.db.update_task(t.id, status=FAILED,
                                error=tr("Phiên trước bị dừng giữa chừng — /retry để chạy lại"))
        for g in self.db.goals():
            if g.status == "planning":
                self.db.update_goal(g.id, status="failed", summary=tr("Bị dừng khi đang lập kế hoạch"))
            elif g.status == "reviewing":
                self.db.update_goal(g.id, status="running")
            elif g.status == "grilling" and not self.grill_question(g):
                # trưởng nhóm đang nghĩ câu hỏi thì app bị tắt: chờ người dùng bấm "Hỏi tiếp"
                self.db.set_grill(g.id, dict(g.grill or {}, error=tr("Phiên trước dừng khi trưởng "
                                                                     "nhóm đang nghĩ câu hỏi — bấm "
                                                                     "↻ Hỏi tiếp")))

    async def apply_isolation(self) -> None:
        """Chọn chế độ làm việc theo cfg.isolation (gọi lại được khi /setup đổi chế độ)."""
        self.use_worktree = False
        if self.cfg.isolation == "worktree":
            rc, top = await self._git("rev-parse", "--show-toplevel")
            rc2, _ = await self._git("rev-parse", "--verify", "HEAD")
            if rc == 0 and rc2 == 0 and Path(top.strip()).resolve() == self.root:
                self.use_worktree = True
            else:
                self.log(tr("⚠ isolation=worktree cần chạy ở thư mục gốc của git repo đã có commit "
                            "— chuyển sang chế độ shared."))
        mode = tr("worktree (mỗi task 1 nhánh riêng)") if self.use_worktree else tr("shared (chung thư mục)")
        self.log(tr("Sẵn sàng. Trưởng nhóm: {lead}. Chế độ làm việc: {mode}.", lead=self.cfg.lead, mode=mode))

    # ------------------------------------------------------------------ mục tiêu
    def new_goal(self, text: str) -> int:
        gid = self.db.add_goal(text)
        self._checkpoint_goal(gid)
        self.lead_busy.add(gid)
        self.log(tr("🎯 Mục tiêu #{gid}: {text}", gid=gid, text=text))
        self._spawn(self._plan(gid))
        self.emit("changed")
        return gid

    async def _call_lead(self, prompt: str, label: str, first: str = "", goal_id: int | None = None,
                         keep_session: bool = False, slow: bool = False, effort: str | None = None) -> str | None:
        """Gọi trưởng nhóm (hoặc `first` nếu có); nếu hết hạn mức thì lần lượt thử các agent trong lead_fallback.
        keep_session: lượt lập kế hoạch của mục tiêu goal_id — mở/tiếp tục phiên trưởng nhóm của mục tiêu đó
        (/continue m<id> nhờ vậy nhớ kế hoạch cũ). slow: lượt dài (/init khám phá cả dự án) — dùng timeout của agent
        thay lead_timeout, hết giờ thì dừng (agent khác cũng phải khám phá lại từ đầu). effort: mức riêng cho lượt này
        (lượt nhanh như viết commit message dùng "low" thay effort cao đặt cho lập kế hoạch)."""
        names = list(dict.fromkeys([first or self.cfg.lead, self.cfg.lead] + list(self.cfg.lead_fallback)))
        for name in names:
            if goal_id is not None and goal_id in self._lead_stop:
                return None
            lead = self.cfg.agents.get(name)
            if not lead or not lead.enabled:
                if name == self.cfg.lead:
                    self.log(tr("✗ Không tìm thấy trưởng nhóm '{name}' trong cấu hình.", name=name))
                continue
            if not lead.installed():
                self.log(tr("✗ Chưa cài '{binary}' ({name}).", binary=lead.binary, name=name))
                continue
            if self.in_cooldown(name):
                self.log(tr("⏸ {name} đang hết hạn mức đến {v} — thử người khác.", name=name, v=self.cooldown_label(name)))
                continue
            if name != names[0]:
                self.log(tr("↪ {name} làm thay trưởng nhóm cho: {label}", name=name, label=label))
            session = None
            if keep_session and goal_id is not None and lead.can_resume():
                g = self.db.goal(goal_id)
                session = g.lead_session if g and g.lead_session_agent == name else None
            out, rc, kind = await self._lead_once(lead, prompt, label, goal_id, session=session,
                                                  keep_session=keep_session and goal_id is not None, slow=slow,
                                                  effort=effort)
            if kind == "cancelled":
                return None
            if kind in ("ratelimit", "overloaded"):
                self._set_cooldown(name, out, overloaded=kind == "overloaded")
                continue
            if kind == "timeout" and slow:
                self.log(tr("⌛ {name} quá {v}s chưa xong ({label}).", name=name, v=lead.timeout, label=label))
                return None
            if kind == "timeout":  # CLI treo (vd agy không in gì): thử người khác thay vì chờ tiếp
                self.log(tr("⌛ {name} quá {v}s chưa xong ({label}) — thử agent dự phòng.", name=name,
                            v=self.lead_timeout(lead), label=label))
                continue
            if rc != 0:
                self.log(tr("✗ {label}: {name} thoát với mã {rc}.", label=label, name=name, rc=rc))
            return out
        self.log(tr("✗ Không còn agent nào lập kế hoạch/review được ({label}).", label=label))
        return None

    def lead_timeout(self, lead: AgentConfig) -> int:
        """Giây tối đa cho một lượt trưởng nhóm: lead_timeout (ngắn hơn timeout của task — lập kế hoạch/review
        thường xong trong vài phút), không vượt timeout của agent."""
        lt, own = self.cfg.lead_timeout, lead.timeout  # 0 = không giới hạn
        return min(own, lt) if lt > 0 and own > 0 else (lt or own)

    async def _lead_once(self, lead: AgentConfig, prompt: str, label: str,
                         goal_id: int | None = None, session: str | None = None,
                         keep_session: bool = False, slow: bool = False,
                         effort: str | None = None) -> tuple[str, int, str]:
        await self.prepare_agent(lead)
        if goal_id is not None and goal_id in self._lead_stop:  # huỷ trong lúc chuẩn bị: không chạy nữa
            return "", 1, "cancelled"
        resume = bool(session)
        if keep_session and not resume:
            session = self.new_session(lead)
        first_argv = self.argv_for(lead, prompt, self.root, plan=True, session=session, resume=resume,
                                   effort=effort)
        span = [time.time(), None, label]
        self.lead_spans.append(span)
        act = self._begin_activity(lead.name, None, label, lead.label())
        rid = self.db.add_run(None, lead.name, "lead", len(prompt), goal_id=goal_id, cwd=str(self.root),
                              model=lead.split_effort(lead.model or "", lead.effort or "")[0])
        with open(self.logs / "lead.log", "a", encoding="utf-8") as f:
            f.write(f"\n===== {label} — {lead.name} — {time.ctime()} =====\n")

            def on_line(line: str) -> None:
                f.write(line + "\n")
                f.flush()
                self._touch(act, line)
                self.emit("log", task_id=SYSTEM, agent=lead.name, raw=line,
                          line=f"  [{lead.name}] {line}")

            made: list[Run] = []

            def make(argv=None) -> Run:
                r = Run(argv if argv is not None else
                        self.argv_for(lead, prompt, self.root, plan=True, session=session, resume=resume,
                                      effort=effort),
                        str(self.root), self.env_for(), use_pty=lead.pty,
                        timeout=lead.timeout if slow else self.lead_timeout(lead), on_line=on_line)
                made.append(r)
                self.lead_live.add(r)
                return r
            run = make(first_argv)
            if goal_id is not None:
                self.lead_runs[goal_id] = run
            rc = 1
            try:
                rc = await run.start()
                if resume and not run.cancelled and (run.session_lost or (
                        rc != 0 and SESSION_LOST_RE.search(run.output[-3000:]))):
                    resume, session = False, self.new_session(lead)
                    run = make()
                    if goal_id is not None:
                        self.lead_runs[goal_id] = run
                    rc = await run.start()
                if self.effort_rejected(lead, None, effort, run, rc):
                    run = make()
                    if goal_id is not None:
                        self.lead_runs[goal_id] = run
                    rc = await run.start()
            finally:
                self.lead_live.difference_update(made)
                if goal_id is not None and self.lead_runs.get(goal_id) is run:
                    del self.lead_runs[goal_id]
                span[1] = time.time()
                kind = self._classify(run, rc)
                self.db.finish_run(rid, rc, kind, len(run.output))
                if keep_session:
                    session = self.session_of(lead, run, session)
                    if session and kind == "ok":
                        self.db.update_goal(goal_id, lead_session=session, lead_session_agent=lead.name)
                self._usage_job(rid, lead, prompt, session, run.usage)
                act["status"] = DONE if kind == "ok" else FAILED
                self._end_activity(lead.name, act)
        # CLI in lại prompt (codex exec) thì JSON mẫu trong prompt sẽ bị bóc nhầm thành kế hoạch/câu hỏi
        return P.strip_echo(run.output, prompt), rc, kind

    async def _plan(self, gid: int, followup: tuple[str, str, str] | None = None) -> None:
        """followup: (yêu cầu mới, kết quả các task cũ, đánh giá cũ) khi tiếp tục mục tiêu đã xong."""
        try:
            goal = self.db.goal(gid)
            self.log(tr("🧠 {lead} đang lập kế hoạch cho mục tiêu #{gid}…", lead=self.cfg.lead, gid=gid))
            # trưởng nhóm được hỏi lại khi có điểm quan trọng chưa rõ — trừ khi đã hỏi đáp (/grill, đã có đặc tả)
            # hoặc không ai trả lời (ateam goal -y)
            can_ask = not followup and not goal.spec and not (goal.grill or {}).get("closed") \
                and not self.auto_answer
            ov = await self.overview_block(hint=not followup, session=self._lead_session(goal))
            sk, asked = self._plan_skills(followup[0] if followup else goal.base_text())
            if followup:
                prompt = P.followup_plan_prompt(self.cfg, goal.base_text(), followup[1], followup[2],
                                                followup[0], str(self.root), self.notes_text(),
                                                earlier=(goal.followups or [])[:-1], overview=ov, skills=sk)
            else:
                prompt = P.plan_prompt(self.cfg, goal.base_text(), str(self.root), self.notes_text(),
                                       can_ask=can_ask, overview=ov, skills=sk)
            out = await self._call_lead(prompt, tr("Lập kế hoạch mục tiêu #{gid}", gid=gid), goal_id=gid,
                                        keep_session=True)
            if out is not None:
                self._overview_seen(gid, ov)
            if gid in self._lead_stop:  # người dùng đã huỷ (cancel_planning đã đổi trạng thái mục tiêu)
                return
            if out is None:
                self.db.update_goal(gid, status="failed", summary=tr(
                    "Không có trưởng nhóm nào lập được kế hoạch (hết hạn mức, quá tải hoặc quá thời gian — xem log "
                    "hệ thống)"))
                return
            plan = P.extract_json(out or "", list, keys=("prompt", "agent", "title"))
            q = P.question_from(P.extract_json(out or "", dict, keys=("question",)) or {}) \
                if can_ask and not plan else None
            if q:  # chuyển sang hỏi đáp (chỉ điểm thiết yếu, tối đa PLAN_ASK_MAX câu) rồi lập kế hoạch lại
                self.db.set_grill(gid, {"qa": [dict(q, a=None)], "spec": "", "error": "", "from_plan": True})
                self.db.update_goal(gid, status="grilling")
                self.log(tr("❓ Trưởng nhóm cần làm rõ trước khi lập kế hoạch #{gid}: {question}", gid=gid,
                            question=q["q"]))
                return
            if not plan:
                self.db.update_goal(gid, status="failed", summary=tr("Trưởng nhóm không trả về kế hoạch JSON hợp lệ"))
                self.log(tr("✗ Không đọc được kế hoạch cho mục tiêu #{gid} (xem "
                            ".ateam/logs/lead.log). Bạn vẫn có thể giao tay bằng /task.", gid=gid))
                return
            ids = self._insert_plan(gid, plan, source="followup" if followup else "plan", asked=asked)
            if self.cfg.approve_plan:
                self.db.update_goal(gid, status="awaiting")
                self.log(tr("📋 Kế hoạch #{gid}: {v} task ở trạng thái NHÁP. Duyệt bằng /go {gid} "
                            "(trong TUI: F2 hoặc Ctrl+G); sửa trước bằng /edit, /assign, /cancel.", gid=gid, v=len(ids)))
            else:
                self.db.update_goal(gid, status="running")
                self.log(tr("📋 Kế hoạch #{gid}: {v} task — bắt đầu chạy.", gid=gid, v=len(ids)))
        except mentions.AttachmentError as e:
            self.db.update_goal(gid, status="failed", summary=str(e))
            self.log(str(e))
        except Exception as e:  # không để mục tiêu kẹt ở "planning" tới lần mở app sau
            self.db.update_goal(gid, status="failed", summary=tr("Lỗi khi lập kế hoạch: {e!r}", e=e))
            self.log(tr("✗ Lập kế hoạch mục tiêu #{gid} lỗi: {e!r}", gid=gid, e=e))
        finally:
            self.lead_busy.discard(gid)
            self._lead_stop.discard(gid)
            self.emit("changed")

    def cancel_planning(self, gid: int | None) -> str:
        """Huỷ lượt lập kế hoạch đang chạy (dừng CLI của trưởng nhóm, không thử agent dự phòng). Mục tiêu mới thành
        "đã huỷ"; lập kế hoạch tiếp (/continue) thì quay về "chưa xong" — việc đã làm vẫn còn."""
        if gid is None:
            gid = next((g.id for g in reversed(self.db.goals()) if g.status == "planning"), None)
        g = self.db.goal(gid) if gid is not None else None
        if not g or g.status != "planning":
            return tr("Không có mục tiêu nào đang lập kế hoạch") if gid is None else \
                tr("Mục tiêu #{gid} không đang lập kế hoạch", gid=gid)
        if g.id in self.lead_busy:
            self._lead_stop.add(g.id)  # _plan tự bỏ khi lượt trưởng nhóm dừng
        followup = any(t.status != CANCELLED for t in self.db.tasks(goal_id=g.id))
        self.db.update_goal(g.id, status="incomplete" if followup else "cancelled",
                            summary=tr("Đã huỷ khi đang lập kế hoạch"))
        run = self.lead_runs.get(g.id)
        if run:
            run.cancel()
        self.log(tr("✗ Huỷ lập kế hoạch mục tiêu #{gid}", gid=g.id))
        self.emit("changed")
        return tr("Đã huỷ lập kế hoạch mục tiêu #{gid}", gid=g.id)

    # ------------------------------------------------------------------ /grill: hỏi đáp trước khi lập kế hoạch
    def start_grill(self, text: str) -> int:
        """Mục tiêu mới, nhưng trưởng nhóm phỏng vấn người dùng (từng câu một) trước khi lập kế hoạch."""
        gid = self.db.add_goal(text)
        self._checkpoint_goal(gid)
        self.db.update_goal(gid, status="grilling")
        self.db.set_grill(gid, {"qa": [], "spec": "", "error": ""})
        self.log(tr("🔎 Mục tiêu #{gid} (hỏi đáp trước): {text}", gid=gid, text=text))
        self._grill_spawn(gid)
        return gid

    @staticmethod
    def grill_question(g: Goal) -> dict | None:
        """Câu hỏi đang chờ người dùng trả lời (None nếu trưởng nhóm đang nghĩ / chưa hỏi)."""
        return g.question()

    def grill_active(self, goals: list[Goal] | None = None) -> Goal | None:
        """Mục tiêu đang hỏi đáp mới nhất (khung hỏi đáp ở TUI hiện mục tiêu này). goals: danh sách đã đọc sẵn."""
        goals = [g for g in (self.db.goals() if goals is None else goals) if g.status == "grilling"]
        return goals[-1] if goals else None

    def waiting_view(self, goals: list[Goal] | None = None, tasks: list[Task] | None = None) -> dict | None:
        """Khung hỏi đáp (TUI + web) hiện gì: câu /grill đang chờ trả lời > câu <<<ASK>>> của agent đang chờ >
        trạng thái /grill (trưởng nhóm đang nghĩ / lỗi). Một /grill bị bỏ dở (lỗi, đang nghĩ) không che câu hỏi
        của agent. goals/tasks: danh sách đã đọc sẵn."""
        goals = self.db.goals() if goals is None else goals
        g = self.grill_active(goals)
        gv = None
        if g:
            busy = g.id in self.lead_busy
            qa = (g.grill or {}).get("qa") or []
            gv = {"kind": "grill", "goal": g.id, "text": g.text, "busy": busy,
                  "question": None if busy else g.question(), "n": len(qa), "answered": len(g.answered()),
                  "error": "" if busy else str((g.grill or {}).get("error") or ""),
                  "others": sum(1 for x in goals if x.status == "grilling") - 1}
            if gv["question"]:
                return gv
        tasks = self.db.tasks(status=ASKING) if tasks is None else tasks
        t = self.ask_active(tasks)
        if t:
            return {"kind": "ask", "task": t.id, "agent": t.agent, "title": t.title, "question": t.question(),
                    "gate": t.kind == KIND_GATE, "deps": t.depends_on,
                    "n": len((t.ask or {}).get("qa") or []),
                    "others": sum(1 for x in tasks if x.status == ASKING) - 1}
        return gv

    def _grill_spawn(self, gid: int, finish: bool = False) -> None:
        self.lead_busy.add(gid)
        self.emit("changed")
        self._spawn(self._grill_step(gid, finish))

    def _grill_error(self, gid: int, data: dict, msg: str) -> None:
        """Lượt hỏi đáp không ra câu hỏi/đặc tả: ghi lỗi để khung hỏi đáp hiện kèm nút ↻ Hỏi tiếp."""
        g = self.db.goal(gid)
        if not g or g.status != "grilling":
            return
        self.db.set_grill(gid, dict(data, error=msg))
        self.log(tr("✗ Hỏi đáp #{gid}: {v}", gid=gid, v=msg))

    async def _grill_step(self, gid: int, finish: bool) -> None:
        to_plan = False
        data: dict = {}
        try:
            g = self.db.goal(gid)
            if not g or g.status != "grilling":
                return
            data = dict(g.grill or {}, error="")
            data.setdefault("qa", [])
            self.db.set_grill(gid, data)
            self.emit("changed")
            answered = g.answered()
            essential = bool(data.get("from_plan"))  # hỏi lại khi lập kế hoạch: chỉ điểm thiết yếu, ít câu
            limit = PLAN_ASK_MAX if essential else GRILL_MAX
            finish = finish or len(answered) >= limit
            # câu sau tiếp phiên trưởng nhóm đã nhận bản tổng quan: chỉ gửi một dòng nhắc
            ov = await self.overview_block(session=self._lead_session(g))
            prompt = P.grill_prompt(self.cfg, g.text, answered, str(self.root), self.notes_text(),
                                    finish=finish, max_questions=limit, essential_only=essential, overview=ov)
            # tiếp phiên trưởng nhóm của mục tiêu: không khám phá lại dự án mỗi câu, lượt lập kế hoạch sau đó
            # cũng nhớ những gì đã đọc. Lịch sử hỏi đáp vẫn nằm trong prompt (mất phiên / CLI không resume được).
            out = await self._call_lead(prompt, tr("Hỏi đáp mục tiêu #{gid}", gid=gid), goal_id=gid,
                                        keep_session=True)
            if out is not None:
                self._overview_seen(gid, ov)
            g = self.db.goal(gid)
            if not g or g.status != "grilling":  # người dùng huỷ trong lúc chờ
                return
            if out is None:
                self._grill_error(gid, data, tr("Không có trưởng nhóm nào chạy được lúc này (hết hạn mức hoặc "
                                                "chưa cài — xem log hệ thống) — bấm ↻ Hỏi tiếp để thử lại"))
                return
            res = P.extract_json(out, dict, keys=("question", "done", "spec")) or {}
            q = P.question_from(res)
            if q and not finish and not res.get("done"):
                data["qa"] = answered + [dict(q, a=None)]
                self.db.set_grill(gid, data)
                self.log(tr("❓ #{gid} câu {v}: {question}", gid=gid, v=len(data['qa']), question=q["q"]))
                return
            spec = str(res.get("spec") or "").strip()
            if not spec and (res.get("done") or finish) and answered:
                # trưởng nhóm không viết đặc tả: dùng chính các câu hỏi đáp
                spec = "\n".join(f"- {x['q']} → {x['a']}" for x in answered)
            if not spec and not finish:
                self._grill_error(gid, data, tr("Trưởng nhóm không trả về câu hỏi hay đặc tả hợp lệ (xem "
                                                ".ateam/logs/lead.log) — bấm ↻ Hỏi tiếp để thử lại"))
                return
            # người dùng chốt mà chưa có gì để viết đặc tả: lập kế hoạch luôn với mục tiêu gốc (không hỏi lại)
            data.update(spec=spec, closed=True, qa=answered)
            self.db.set_grill(gid, data)
            self.db.update_goal(gid, status="planning")
            self.log(tr("📝 Đã chốt yêu cầu cho mục tiêu #{gid} sau {v} câu hỏi:", gid=gid, v=len(answered)))
            for line in spec.splitlines():
                self.log("   " + line)
            to_plan = True
        except mentions.AttachmentError as e:
            self._grill_error(gid, data, str(e))
        except Exception as e:  # không để khung hỏi đáp trống trơn: hiện lỗi + nút ↻ Hỏi tiếp
            self._grill_error(gid, data, tr("Lỗi khi hỏi đáp: {e!r}", e=e))
        finally:
            if to_plan:
                self._spawn(self._plan(gid))  # lead_busy giữ nguyên, _plan tự bỏ khi xong
            else:
                self.lead_busy.discard(gid)
            self.emit("changed")

    def _grill_goal(self, gid: int | None) -> Goal | str:
        g = self.db.goal(gid) if gid is not None else self.grill_active()
        if not g or g.status != "grilling":
            return tr("Không có mục tiêu nào đang hỏi đáp")
        return g

    def grill_command(self, rest: str) -> str | None:
        """/grill xong|bỏ|tiếp (TUI và web dùng chung) -> lời nhắn; None: `rest` là mục tiêu mới (người gọi tự
        start_grill)."""
        sub = rest.strip().lower()
        if sub in ("xong", "done", "chot", "chốt"):
            return self.finish_grill(None)
        if sub in ("bỏ", "bo", "huỷ", "huy", "cancel"):
            return self.cancel_grill(None)
        if sub in ("tiếp", "tiep", "retry"):
            return self.retry_grill(None)
        return None

    def answer_grill(self, gid: int | None, answer: str | None) -> str:
        """answer: câu trả lời (số 1…n = chọn phương án); None = để trưởng nhóm tự quyết (theo khuyến nghị)."""
        g = self._grill_goal(gid)
        if isinstance(g, str):
            return g
        if g.id in self.lead_busy:
            return tr("Trưởng nhóm đang nghĩ câu hỏi — đợi chút")
        q = g.question()
        if not q:
            return tr("Chưa có câu hỏi nào để trả lời — bấm ↻ Hỏi tiếp")
        text = P.skip_answer(q.get("rec") or "") if answer is None else pick_option(q, answer)
        if not text:
            return tr("Câu trả lời trống")
        data = dict(g.grill or {})
        data["qa"] = list(data.get("qa") or [])
        data["qa"][-1] = dict(q, a=text)
        self.db.set_grill(g.id, data)
        self.log(f"💬 #{g.id}: {text}")
        self._grill_spawn(g.id)
        return tr("Đã trả lời — {lead} đang nghĩ câu tiếp theo…", lead=self.cfg.lead)

    def finish_grill(self, gid: int | None) -> str:
        """Người dùng thấy đủ rồi: trưởng nhóm viết đặc tả từ những gì đã hỏi rồi lập kế hoạch."""
        g = self._grill_goal(gid)
        if isinstance(g, str):
            return g
        if g.id in self.lead_busy:
            return tr("Trưởng nhóm đang nghĩ — đợi chút rồi bấm lại")
        self.db.set_grill(g.id, dict(g.grill or {}, qa=g.answered()))  # bỏ câu chưa trả lời
        self._grill_spawn(g.id, finish=True)
        return tr("{lead} đang chốt yêu cầu rồi lập kế hoạch cho mục tiêu #{id}…", lead=self.cfg.lead, id=g.id)

    def retry_grill(self, gid: int | None) -> str:
        g = self._grill_goal(gid)
        if isinstance(g, str):
            return g
        if g.id in self.lead_busy:
            return tr("Trưởng nhóm đang nghĩ — đợi chút")
        if g.question():
            return tr("Đang chờ bạn trả lời câu hỏi")
        self._grill_spawn(g.id)
        return tr("{lead} đang hỏi tiếp…", lead=self.cfg.lead)

    def cancel_grill(self, gid: int | None) -> str:
        g = self._grill_goal(gid)
        if isinstance(g, str):
            return g
        self.db.update_goal(g.id, status="cancelled", summary=tr("Đã bỏ khi đang hỏi đáp"))
        run = self.lead_runs.get(g.id)
        if run:  # trưởng nhóm đang nghĩ câu hỏi: dừng luôn, khỏi tốn token cho mục tiêu đã bỏ
            run.cancel()
        self.log(tr("✗ Bỏ mục tiêu #{id} (đang hỏi đáp)", id=g.id))
        self.emit("changed")
        return tr("Đã bỏ mục tiêu #{id}", id=g.id)

    def run_workflow(self, name: str, text: str) -> int | str:
        """Tạo mục tiêu từ workflow dựng sẵn: các bước thành task ngay, không gọi trưởng nhóm.
        Trả về id mục tiêu, hoặc chuỗi lỗi."""
        wf = self.cfg.workflows.get(name)
        if not wf:
            return tr("Không có workflow '{name}'. Có: {v}", name=name, v=', '.join(self.cfg.workflows) or tr("(chưa có)"))
        if not wf.steps:
            return tr("Workflow '{name}' chưa có bước nào", name=name)
        gid = self.db.add_goal(text, workflow=name)
        self._checkpoint_goal(gid)
        self.log(tr("🎯 Mục tiêu #{gid} theo workflow '{name}': {text}", gid=gid, name=name, text=text))
        from . import wizard
        for w in wizard.flow_warnings(self.cfg, wf):
            self.log("⚠ " + w)
        plan = wf.plan(text, self.cfg.lead)
        cat = skills.scan(self.root) if any("$" in x["prompt"] for x in plan) else []
        for item in plan:  # $tên trong prompt bước: gắn skill ngay để chip 🧩 hiện trên task nháp
            item["skills"] = [x.name for x in skills.mentioned(item["prompt"], cat)] if cat else []
        ids = self._insert_plan(gid, plan, source="workflow", from_user=True,
                                asked=[x.name for x in skills.mentioned(text, cat or skills.scan(self.root))]
                                if "$" in text else None)
        if self.cfg.approve_plan:
            self.db.update_goal(gid, status="awaiting")
            self.log(tr("📋 {v} bước ở trạng thái NHÁP — gõ /go {gid} để chạy.", v=len(ids), gid=gid))
        else:
            self.db.update_goal(gid, status="running")
            self.log(tr("📋 {v} bước — bắt đầu chạy.", v=len(ids)))
        self.emit("changed")
        return gid

    def continue_goal(self, gid: int, text: str) -> int | str:
        """Mở lại mục tiêu đã kết thúc với yêu cầu mới: trưởng nhóm lập task bổ sung dựa trên việc
        đã làm. Trả về id mục tiêu, hoặc chuỗi lỗi."""
        g = self.db.goal(gid)
        if not g:
            return tr("Không có mục tiêu #{gid}", gid=gid)
        if g.status not in GOAL_ENDED or gid in self.lead_busy:
            return tr("Mục tiêu #{gid} chưa kết thúc — đợi xong (hoặc /review {gid}) rồi tiếp tục", gid=gid)
        if not self.cfg.agents.get(self.cfg.lead):
            return tr("Không có trưởng nhóm '{lead}' trong cấu hình", lead=self.cfg.lead)
        text = text.strip()
        if not text:
            return tr("Thiếu yêu cầu mới")
        history, summary = self._results_text(gid), g.summary or ""
        self.db.add_followup(gid, text)
        self.db.update_goal(gid, status="planning", round=1, summary=None)  # max_rounds tính lại
        self.lead_busy.add(gid)
        self.log(tr("↪ Tiếp tục mục tiêu #{gid}: {text}", gid=gid, text=text))
        self._spawn(self._plan(gid, followup=(text, history, summary)))
        self.emit("changed")
        return gid

    def continue_ref(self, ref: str) -> tuple[str, int] | str:
        """Bóc tham chiếu của /continue: "m12" = mục tiêu 12; "t40" hoặc "40" = task 40 (task thuộc
        mục tiêu thì là mục tiêu đó). Trả về ("goal"|"task", id) hoặc chuỗi lỗi."""
        m = re.fullmatch(r"#?([mMtT]?)(\d+)", ref.strip())
        if not m:
            return tr("Không hiểu '{ref}' — dùng m<số> cho mục tiêu, t<số> cho task", ref=ref)
        n = int(m.group(2))
        if m.group(1).lower() == "m":
            return ("goal", n) if self.db.goal(n) else tr("Không có mục tiêu #{n}", n=n)
        t = self.db.task(n)
        if not t:
            return tr("Không có task #{n}", n=n)
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
            return tr("Không có task #{tid}", tid=tid)
        if t.status in ACTIVE:
            return (tr("Task #{tid} đang chờ duyệt — merge (Ctrl+Y) hoặc /reject trước", tid=tid) if t.status == REVIEW
                    else tr("Task #{tid} chưa xong — đợi chạy xong rồi tiếp tục", tid=tid))
        if t.agent not in self.cfg.active_agents():
            return tr("Agent '{agent}' không còn trong đội", agent=t.agent)
        text = text.strip()
        if not text:
            return tr("Thiếu yêu cầu mới")
        title = text[:60] + ("…" if len(text) > 60 else "")
        nid = self.db.add_task(t.agent, title, text, status=QUEUED, source="followup",
                               parent_id=tid, model=t.model, effort=t.effort)
        if t.session and t.session_agent == t.agent:  # tiếp tục phiên của lượt trước: chỉ gửi yêu cầu mới
            self.db.update_task(nid, session=t.session, session_agent=t.agent, resume=text)
        self.log(tr("↪ Task #{nid} hỏi tiếp {agent} (sau #{tid}): {title}", nid=nid, agent=t.agent, tid=tid, title=title))
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
            p = self.db.task(p.parent_id) if p.source in ("followup", CHAT) and p.parent_id else None
        return turns[::-1]

    def _plan_skills(self, text: str) -> tuple[str, list[str]]:
        """Khối skill cho prompt lập kế hoạch: danh sách skill đang bật (tên + mô tả) và nội dung đầy đủ của skill
        người dùng gọi bằng $tên trong mục tiêu (trưởng nhóm lập kế hoạch theo nó). Trả (khối, tên skill $tên)."""
        cat = skills.scan(self.root)
        asked = skills.mentioned(text, cat)
        parts = [skills.index_block(skills.enabled(self.root, cat))]
        if asked:
            parts.append(skills.body_block(asked, head="SKILLS THE USER ASKED FOR (ateam attaches them to every code"
                                                       " task of this plan; plan the work with them in mind)",
                                           sep=False))
        return "\n\n".join(p for p in parts if p), [x.name for x in asked]

    def _insert_plan(self, gid: int, plan: list[dict], source: str,
                     from_user: bool = False, asked: list[str] | None = None) -> list[int]:
        """from_user: kế hoạch do người dùng viết (workflow) — giữ effort/model của từng bước, không thêm/bớt bước.
        asked: skill người dùng gọi bằng $tên trong mục tiêu — gắn vào mọi task code (luật cố định, không để LLM chọn)."""
        if not from_user:
            plan = self._apply_checks(plan, source)
        cat = skills.scan(self.root) if asked or any(isinstance(x, dict) and x.get("skills") for x in plan) else []
        # trưởng nhóm chỉ được gắn skill người dùng đã bật cho dự án (hoặc gọi bằng $tên) — không phải skill nó tự biết
        # từ thư mục của CLI mình (claude đọc sẵn ~/.claude/skills)
        allowed = {x.name for x in skills.enabled(self.root, cat)} | set(asked or []) if cat else set()
        agents = self.cfg.active_agents()
        status = DRAFT if self.cfg.approve_plan else QUEUED
        id_map: dict = {}
        created: list[tuple[int, list]] = []
        for i, item in enumerate(plan, 1):
            kind = task_kind(item.get("type"))
            if kind == KIND_GATE and not from_user:  # bước ⏸ duyệt chỉ có trong workflow (kế hoạch thường: /go)
                kind = KIND_CODE
            agent = str(item.get("agent", "")).strip()
            if agent not in agents:
                self.log(tr("⚠ Agent '{agent}' không có trong đội — giao cho {lead}.", agent=agent, lead=self.cfg.lead))
                agent = self.cfg.lead
            title = str(item.get("title") or f"Task {i}").strip()
            prompt = str(item.get("prompt") or title).strip()
            effort = str(item.get("effort") or "").strip().lower()
            if not from_user and (not self.cfg.lead_sets_effort or effort not in agents[agent].efforts_for()):
                effort = ""
            model = str(item.get("model") or "").strip() if from_user else ""
            want = item.get("skills") or []
            if isinstance(want, str):  # "skills": "tdd, release"
                want = re.split(r"[,\s]+", want)
            picked = [x.name for x in skills.resolve(want if isinstance(want, list) else [], cat)]
            # kế hoạch người dùng viết (workflow: $tên trong prompt bước) thì giữ mọi skill, như $tên trong mục tiêu
            names = [n for n in picked if n in allowed or from_user]
            dropped = [n for n in picked if n not in names]
            if kind == KIND_CODE:
                names += [n for n in asked or [] if n not in names]
            tid = self.db.add_task(agent, title, prompt, goal_id=gid, status=status, source=source,
                                   effort=effort or None, model=model or None,
                                   kind=None if kind == KIND_CODE else kind, skills=names or None)
            id_map[item.get("id", i)] = tid
            id_map[str(item.get("id", i))] = tid
            created.append((tid, item.get("depends_on") or []))
            self.log(f"   #{tid} → {agent}{(' [' + kind + ']') if kind != KIND_CODE else ''}"
                     f"{(' @' + effort) if effort else ''}: {title}{(' 🧩 ' + ', '.join(names)) if names else ''}")
            if dropped:
                self.log(tr("⚠ #{tid}: bỏ skill {v} — chưa bật cho dự án (bật ở trang 🧩 Skills / /skills, hoặc gọi "
                            "bằng $tên trong mục tiêu)", tid=tid, v=", ".join(dropped)))
        graph: dict[int, list[int]] = {}
        for tid, deps in created:
            if not isinstance(deps, list):  # "depends_on": 1 hoặc "1"
                deps = [deps]
            graph[tid] = list(dict.fromkeys(id_map[d] for d in deps
                                            if isinstance(d, (int, str)) and d in id_map and id_map[d] != tid))
        for tid, real in self._drop_cycles(graph).items():
            if real:
                self.db.update_task(tid, depends_on=real)
        return [t for t, _ in created]

    def _apply_checks(self, plan: list[dict], source: str) -> list[dict]:
        """Luật chất lượng cho kế hoạch của trưởng nhóm (workflow không qua đây — người dùng tự chọn bước): preset
        Nhanh bỏ task review; Chặt chẽ thêm review khi kế hoạch mới / kế hoạch tiếp thiếu; có lệnh kiểm tra và ≥2 task
        chạy song song thì thêm một task kiểm tra cuối phụ thuộc mọi task khác — kiểm tra riêng từng task không thấy lỗi
        khi ghép (worktree) hoặc thấy thay đổi dở của task kia (shared). Chuỗi tuần tự thì không cần: task cuối đã được
        kiểm tra trên kết quả gộp. Mọi item được gán id rõ ràng để bỏ item không làm lệch depends_on."""
        items = [dict(x, id=x.get("id", i)) for i, x in enumerate(plan, 1) if isinstance(x, dict)]

        def kind(x: dict) -> str:
            return task_kind(x.get("type"))
        if self.cfg.quality == "fast":
            items = [x for x in items if kind(x) != KIND_REVIEW]
        code = [x for x in items if kind(x) == KIND_CODE]
        if (self.cfg.quality == "strict" and source in ("plan", "followup") and code
                and not any(kind(x) == KIND_REVIEW for x in items)):
            items.append({"id": "ateam-review", "type": KIND_REVIEW, "title": tr("Review code"),
                          "agent": self._reviewer({str(x.get("agent", "")) for x in code}),
                          "prompt": "Review the changes of the tasks you depend on against the goal.",
                          "depends_on": [x["id"] for x in code]})
        work = [x for x in items if kind(x) != KIND_VERIFY]
        if self.cfg.verify.command and len(work) == len(items) and self._has_parallel(work):
            items.append({"id": "ateam-verify", "type": KIND_VERIFY, "agent": self.cfg.lead,
                          "title": tr("Kiểm tra cuối"), "prompt": "", "depends_on": [x["id"] for x in work]})
        return items

    @staticmethod
    def _has_parallel(items: list[dict]) -> bool:
        """Có hai item không phụ thuộc (bắc cầu) vào nhau — chúng sẽ chạy song song."""
        def deps(x: dict) -> set[str]:
            d = x.get("depends_on") or []
            return {str(v) for v in (d if isinstance(d, list) else [d]) if isinstance(v, (int, str))}
        graph = {str(x["id"]): deps(x) for x in items}
        reach: dict[str, set[str]] = {}
        for n in graph:
            seen, stack = set(), list(graph[n])
            while stack:
                d = stack.pop()
                if d in graph and d not in seen:
                    seen.add(d)
                    stack.extend(graph[d])
            reach[n] = seen
        names = list(graph)
        return any(b not in reach[a] and a not in reach[b] for i, a in enumerate(names) for b in names[i + 1:])

    def _reviewer(self, authors: set[str]) -> str:
        """Agent review code khi preset Chặt chẽ tự thêm task review: agent giữ vai trò Review mà không phải tác giả;
        không có thì trưởng nhóm."""
        from .wizard import role_agents
        name = role_agents(self.cfg).get("review")
        return name if name and name not in authors else self.cfg.lead

    def _drop_cycles(self, graph: dict[int, list[int]]) -> dict[int, list[int]]:
        """Bỏ phụ thuộc tạo vòng (1 chờ 2, 2 chờ 1) — không thì cả hai chờ nhau mãi, mục tiêu treo ở "running"."""
        state: dict[int, int] = {}  # 1 = đang duyệt, 2 = xong

        def visit(n: int) -> None:
            state[n] = 1
            for d in list(graph.get(n, [])):
                if state.get(d) == 1:
                    graph[n].remove(d)
                    self.log(tr("⚠ Bỏ phụ thuộc vòng #{a} → #{b} trong kế hoạch.", a=n, b=d))
                elif d in graph and not state.get(d):
                    visit(d)
            state[n] = 2
        for n in graph:
            if not state.get(n):
                visit(n)
        return graph

    def approve(self, gid: int | None = None) -> int:
        n = 0
        for t in self.db.tasks(goal_id=gid, status=DRAFT):
            self.db.update_task(t.id, status=QUEUED)
            n += 1
        for g in self.db.goals():
            if (gid is None or g.id == gid) and g.status == "awaiting":
                self.db.update_goal(g.id, status="running")
        if n:
            self.log(tr("▶ Đã duyệt {n} task.", n=n))
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
        self.db.update_goal(gid, status="cancelled", summary=tr("Người dùng bỏ kế hoạch"))
        self.log(tr("✗ Đã bỏ kế hoạch #{gid} ({n} task nháp).", gid=gid, n=n))
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
                and (t.goal_id is None or t.goal_id in ended) and t.source != CHAT}  # chat không ở bảng việc
        needed = {d for t in tasks if t.id not in drop for d in t.depends_on}
        drop -= needed  # task còn lại phụ thuộc vào nó: xoá đi thì task đó thành "bị chặn"
        left = {t.goal_id for t in tasks if t.id not in drop}
        return sorted(drop), sorted(gid for gid in ended if gid not in left)

    def clear_finished(self) -> tuple[int, int]:
        """Dọn bảng việc: xoá task và mục tiêu đã kết thúc cùng file log của chúng."""
        tids, gids = self.finished_ids()
        if not tids and not gids:
            return 0, 0
        # task lỗi / huỷ ở chế độ worktree giữ nhánh để xem lại — dọn khỏi bảng thì xoá luôn, không để mồ côi trong repo
        for t in (self.db.task(i) for i in tids):
            if t and t.branch:
                self._spawn(self._drop_branch(t))
        self.db.delete(tids, gids)
        for tid in tids:
            try:
                self.log_path(tid).unlink()
            except OSError:
                pass
        self.log(tr("🗑 Đã dọn {v} task, {v2} mục tiêu đã kết thúc khỏi bảng việc.", v=len(tids), v2=len(gids)))
        self.emit("changed")
        return len(tids), len(gids)

    def delete_task(self, tid: int) -> str:
        """Xoá hẳn một task ngoài kế hoạch (giao tay, giao việc chéo) cùng file log và nhánh của nó. Task trong kế
        hoạch thuộc về mục tiêu (review, /continue) nên không xoá lẻ; đang chạy / chờ duyệt / xung đột còn việc dở
        trên nhánh → huỷ, merge hoặc bỏ trước."""
        t = self.db.task(tid)
        if not t:
            return tr("Không có task #{tid}", tid=tid)
        if t.goal_id is not None:
            return tr("Task #{tid} thuộc kế hoạch #{gid} — chỉ xoá được task ngoài kế hoạch", tid=tid, gid=t.goal_id)
        if t.status == RUNNING:
            return tr("Task #{tid} đang chạy — huỷ trước (/cancel {tid}) rồi xoá", tid=tid)
        if t.status in (REVIEW, CONFLICT):
            return tr("Task #{tid} đang chờ duyệt — merge hoặc bỏ trước rồi xoá", tid=tid)
        waiting = [x.id for x in self.db.tasks() if tid in x.depends_on and x.status not in (DONE,) + FINISHED_BAD]
        if waiting:
            return tr("Task {v} còn chờ task #{tid} — xoá thì chúng bị chặn", tid=tid,
                      v=", ".join(f"#{i}" for i in waiting))
        if t.branch:
            self._spawn(self._drop_branch(t))
        self.db.delete([tid], [])
        try:
            self.log_path(tid).unlink()
        except OSError:
            pass
        self.log(tr("🗑 Đã xoá task #{tid}: {title}", tid=tid, title=t.title))
        self.emit("changed")
        return tr("Đã xoá task #{tid}", tid=tid)

    # ------------------------------------------------------------------ giao tay / chỉnh sửa
    def add_task(self, agent: str, prompt: str, title: str | None = None, *,
                 model: str | None = None, effort: str | None = None) -> int:
        title = title or (prompt[:60] + ("…" if len(prompt) > 60 else ""))
        tid = self.db.add_task(agent, title, prompt, status=QUEUED, source="user",
                               model=model, effort=effort)
        extra = self.cfg.agents[agent].label(model, effort) if (model or effort) else ""
        self.log(tr("➕ Task #{tid} giao cho {agent}{extra}: {title}", tid=tid, agent=agent,
                    extra=(' [' + extra + ']') if extra else '', title=title))
        self.emit("changed")
        return tid

    def handoff(self, src: str, dst: str, request: str = "") -> int | str:
        """/handoff: kể lại cuộc chat với `src` cho `dst` (cuộc chat mới với dst) kèm yêu cầu — trống = nhờ dst review
        việc src đã làm. Trả id lượt chat mới của dst, hoặc chuỗi lỗi."""
        agents = self.cfg.active_agents()
        for a in (src, dst):
            if a not in agents:
                return tr("Không có agent '{agent}' — agent: {v}", agent=a, v=", ".join(agents))
        if src == dst:
            return tr("Chọn hai agent khác nhau")
        last = self.chat_last(src)
        if not last:
            return tr("Chưa chat với {agent} — /chat {agent} trước rồi mới chuyển", agent=src)
        if last.status in (QUEUED, RUNNING):
            return tr("{agent} đang trả lời tin trước — đợi xong rồi chuyển", agent=src)
        turns = self.thread_of(last, limit=20) + [(last.prompt, last.result or last.error or "")]
        prompt = P.handoff_prompt(src, turns, request, str(self.root))
        title = (tr("↪ từ {src}: {v}", src=src, v=request.strip()) if request.strip()
                 else tr("↪ review cuộc chat với {src}", src=src))
        tid = self.chat(dst, prompt, new=True, title=title)
        if isinstance(tid, int):
            self.log(tr("↪ Chuyển cuộc chat {src} → {dst} ({n} lượt): {title}", src=src, dst=dst, n=len(turns),
                        title=title))
        return tid

    def chat(self, agent: str, text: str, new: bool = False, title: str = "") -> int | str:
        """Nhắn thẳng cho một agent như dùng CLI của nó trong terminal: mỗi tin là một lượt chạy tiếp đúng phiên CLI
        của lượt chat trước (--resume), ở thư mục gốc, không verify/worktree/giao việc chéo. Trả id task của lượt,
        hoặc chuỗi lỗi."""
        a = self.cfg.active_agents().get(agent)
        if not a:
            return tr("Không có agent '{agent}' — agent: {v}", agent=agent, v=", ".join(self.cfg.active_agents()))
        text = text.strip()
        if not text:
            return tr("Gõ nội dung tin nhắn cho {agent}", agent=agent)
        last = self.chat_last(agent)
        if last and last.status in (QUEUED, RUNNING):
            return tr("{agent} đang trả lời tin trước — đợi xong (hoặc /cancel {tid})", agent=agent, tid=last.id)
        if new or agent in self._chat_new:  # /new: cuộc trò chuyện mới, phiên CLI mới
            self._chat_new.discard(agent)
            last = None
        title = title[:80] or text.splitlines()[0][:60] + ("…" if len(text) > 60 else "")
        tid = self.db.add_task(agent, title, text, status=QUEUED, source=CHAT,
                               parent_id=last.id if last else None)
        if last and last.session and last.session_agent == agent:  # tiếp tục phiên: chỉ gửi tin mới
            self.db.update_task(tid, session=last.session, session_agent=agent, resume=text)
        self.emit("changed")
        return tid

    async def resolve_conflicts(self, paths: list[str] | None = None) -> tuple[bool, str]:
        """Nhờ agent (agent viết commit ở tab Git, mặc định trưởng nhóm) sửa các file xung đột git — một lượt chat
        mới ở thư mục gốc (xem tiến độ ở tab Agents). paths None = mọi file đang xung đột."""
        from .gitops import GitRepo
        st = await GitRepo(self.root).status()
        files = [f.path for f in st.conflicts if paths is None or f.path in paths]
        if not files:
            return False, tr("Không có file nào đang xung đột")
        agent = self.commit_agent()
        res = self.chat(agent, P.conflict_prompt(files=files, state=st.state, cwd=str(self.root)), new=True)
        if isinstance(res, str):
            return False, res
        return True, tr("🤖 {agent} đang giải quyết xung đột {v} file — xem ở tab Agents; xong thì xem lại rồi "
                        "Đánh dấu đã xong", agent=agent, v=len(files))

    def chat_reset(self, agent: str) -> None:
        """Tin chat kế tiếp với agent bắt đầu cuộc mới (không nối phiên cũ)."""
        self._chat_new.add(agent)

    def terminal_session(self, agent: str) -> str | None:
        """Phiên CLI để "Mở trong terminal": của lượt chat gần nhất (chạy ở thư mục gốc — CLI tìm phiên theo thư mục),
        không có thì của task gần nhất chạy ở thư mục gốc (chế độ shared)."""
        tasks = [t for t in self.db.tasks() if t.agent == agent and t.session and t.session_agent == agent
                 and (t.source == CHAT or not t.branch)]
        chats = [t for t in tasks if t.source == CHAT]
        pick = (chats or tasks)[-1:] if (chats or tasks) else []
        return pick[0].session if pick else None

    def chat_last(self, agent: str) -> Task | None:
        """Lượt chat gần nhất với agent (để nối phiên)."""
        rows = [t for t in self.db.tasks() if t.source == CHAT and t.agent == agent]
        return rows[-1] if rows else None

    def assign(self, tid: int, agent: str, rerun: bool = False) -> str:
        """Đổi agent làm task (chưa chạy, lỗi, bị huỷ…). rerun: task lỗi/huỷ/bị chặn thì chạy lại luôn với agent mới
        (nút ⇄ Đổi agent) — phiên CLI cũ là của agent cũ nên chạy lại bằng prompt đầy đủ."""
        t = self.db.task(tid)
        if not t:
            return tr("Không có task #{tid}", tid=tid)
        if agent not in self.cfg.active_agents():
            return tr("Không có agent '{agent}'", agent=agent)
        if t.status == RUNNING:
            return tr("Task #{tid} đang chạy — /cancel trước rồi giao lại", tid=tid)
        if agent != t.agent:  # model/effort riêng của task là của agent cũ (như khi chuyển agent dự phòng)
            self.db.update_task(tid, agent=agent, model=None, effort=None)
            self.log(tr("⇄ #{tid}: {old} → {agent}", tid=tid, old=t.agent, agent=agent))
        if rerun and t.status in (FAILED, CANCELLED, BLOCKED):
            return f"Task #{tid} → {agent}. " + self.retry(tid)
        self.emit("changed")
        return f"Task #{tid} → {agent}"

    def set_task_option(self, tid: int, key: str, value: str | None) -> str:
        t = self.db.task(tid)
        if not t:
            return tr("Không có task #{tid}", tid=tid)
        if t.status == RUNNING:
            return tr("Task #{tid} đang chạy — thay đổi sẽ áp dụng nếu /retry", tid=tid)
        self.db.update_task(tid, **{key: (None if value in (None, "", "-") else value)})
        self.emit("changed")
        return f"Task #{tid}: {key} = {value if value not in (None, '', '-') else tr('theo agent')}"

    def set_agent_option(self, agent: str, key: str, value: str | None) -> str:
        from .config import save_agent_setting
        a = self.cfg.agents.get(agent)
        if not a:
            return tr("Không có agent '{agent}'", agent=agent)
        reset = value in (None, "", "-")
        save_agent_setting(agent, key, None if reset else value)
        if reset:  # đọc lại giá trị gốc trong file cấu hình
            from .config import load_config
            fresh = load_config(self.root).agents.get(agent)
            value = getattr(fresh, key) if fresh else ""
        setattr(a, key, value or "")
        if key == "effort" and value:
            # agy: effort nằm trong tên model -> đổi luôn sang biến thể (gemini-4-argon-medium -> -high) để model
            # hiện trên ô agent đúng cái thật sự chạy
            model, eff = a.split_effort(a.model, a.resolve_effort(a.model, value))
            if model != a.model and not eff:
                save_agent_setting(agent, "model", model)
                save_agent_setting(agent, "effort", None)
                a.model, a.effort = model, ""
        self.log(f"⚙ {agent}: {key} = {value or tr('mặc định của CLI')}")
        self.emit("changed")
        return f"{agent}: {a.label()}"

    def _apply_opencode_catalog(self, a: AgentConfig, catalog: Catalog) -> str:
        from .config import save_found_models
        if not catalog.models:
            return catalog.error
        found = [m for m in catalog.models if not a.models_filter or a.models_filter.lower() in m.lower()]
        if not found:
            return tr("{agent}: không thấy model nào", agent=a.name)
        efforts = {m: e for m, e in catalog.efforts.items() if m in found}
        save_found_models(a.name, found, efforts)
        a.models = found
        a.model_efforts = efforts
        self._opencode_applied[a.name] = (a, a.models_filter, catalog)
        self.emit("changed")
        msg = tr("{agent}: tìm thấy {v} model", agent=a.name, v=len(found))
        if catalog.warning:
            msg += "\n" + catalog.warning
        if a.model and a.model.partition("#")[0] not in found:
            msg += tr(" ⚠ model đang chọn '{model}' không có trong danh sách — chọn lại: /model "
                      "{agent}", model=a.model, agent=a.name)
        return msg

    async def prepare_agent(self, a: AgentConfig) -> None:
        """Dò cú pháp trước mọi lượt chạy; OpenCode 2 đồng bộ catalog một lần dù đã có cache trên đĩa."""
        await self.opencode.prepare(a)
        if (a.opencode_major or 0) >= 2 and standard_models(a):
            catalog = await self.opencode.catalog(a)
            previous = self._opencode_applied.get(a.name)
            if previous is None or previous[0] is not a or previous[1] != a.models_filter or previous[2] is not catalog:
                msg = self._apply_opencode_catalog(a, catalog)
                if msg:
                    self.log(msg)
                # Ghi nhận cả lỗi để không lặp thông báo mỗi task; /models làm mới vẫn thử lại được.
                self._opencode_applied[a.name] = (a, a.models_filter, catalog)

    async def discover_models(self, agent: str, timeout: float = 30) -> str:
        """Chạy models_command của agent (vd `opencode models`) để lấy danh sách model thật."""
        from .config import parse_model_efforts, parse_models, parse_models_json, parse_models_verbose, \
            save_found_models
        a = self.cfg.agents.get(agent)
        if not a:
            return tr("Không có agent '{agent}'", agent=agent)
        if not a.models_command:
            return tr("{agent}: CLI không có lệnh liệt kê model — dùng danh mục có sẵn", agent=agent)
        if not shutil.which(a.models_command[0]):
            return tr("{agent}: chưa cài lệnh '{v}'", agent=agent, v=a.models_command[0])
        await self.opencode.prepare(a, timeout=timeout)
        if (a.opencode_major or 0) >= 2 and standard_models(a):
            return self._apply_opencode_catalog(a, await self.opencode.catalog(a, timeout, refresh=True))
        # max_partial=None: `codex debug models` in JSON ~500KB trên MỘT dòng — cắt ra là bóc thành rác
        run = Run(list(a.models_command), str(self.root), self.env_for(), use_pty=a.pty,
                  timeout=timeout, on_line=lambda _l: None, max_partial=None)
        try:
            code = await run.start()
        except Exception as e:
            return tr("{agent}: không chạy được {v}: {e}", agent=agent, v=' '.join(a.models_command), e=e)
        found = parse_models(run.output, a.models_filter, binary=a.binary)
        # danh sách dạng chữ của opencode lẫn model mọi hãng -> agent đặt tên theo hãng (vd "grok" chạy qua
        # opencode) chỉ giữ model mang tên đó; JSON (codex) đã chỉ gồm model dùng được, lọc theo tên sẽ chỉ còn
        # "codex-auto-review"; agent trùng tên CLI ("opencode") thì giữ hết, không thì chỉ còn model opencode/*
        structured = parse_models_json(run.output) is not None or parse_models_verbose(run.output) is not None
        if (not a.models_filter and not structured and agent.lower() != Path(a.binary).name.lower()
                and any(agent.lower() in m.lower() for m in found)):
            found = [m for m in found if agent.lower() in m.lower()]
        if code != 0 or not found:
            why = tr("hết thời gian") if run.timed_out else tr("mã thoát {code}", code=code) if code else tr("không thấy model nào")
            return f"{agent}: {' '.join(a.models_command)} — {why}"
        efforts = {m: e for m, e in parse_model_efforts(run.output).items() if m in found}
        save_found_models(agent, found, efforts)
        a.models = found + [m for m in a.models if m not in found]
        a.model_efforts = efforts
        self.emit("changed")
        msg = tr("{agent}: tìm thấy {v} model", agent=agent, v=len(found))
        if Path(a.binary).name == "grok" and re.search(r"not authenticated|not logged in", run.output, re.I):
            msg += "\n" + tr("Grok chưa đăng nhập; danh sách có thể chỉ gồm model mặc định. Chạy `grok login`.")
        if a.model and a.model not in found:
            msg += tr(" ⚠ model đang chọn '{model}' không có trong danh sách — chọn lại: /model "
                      "{agent}", model=a.model, agent=agent)
        return msg

    async def agent_usage(self, agent: str, timeout: float = 60) -> tuple[str, list[str]]:
        """Hạn mức / usage do chính CLI của agent báo: (lệnh đã dùng, các dòng kết quả)."""
        a = self.cfg.agents.get(agent)
        if not a:
            return "", [tr("Không có agent '{agent}'", agent=agent)]
        if not a.installed():  # agent đang tắt vẫn được hỏi (/usage hiện đủ các CLI), nhưng chưa cài thì thôi
            return "", [tr("Chưa cài lệnh '{v}'", v=a.binary)]
        if not a.usage_command:
            if Path(a.binary).name == "grok":
                return "grok usage", limits.grok_usage_lines(await self._grok_reports(a))
            if Path(a.binary).name == "codex":
                lines = limits.codex_rate_limits()
                return "~/.codex/sessions", lines or [tr("Chưa có phiên codex nào ghi hạn mức — "
                                                         "chạy 1 task codex trước.")]
            return "", [tr("CLI này không có lệnh xem usage (đặt usage_command trong cấu hình nếu "
                           "có)")]
        cmd = " ".join(a.usage_command)
        if not shutil.which(a.usage_command[0]):
            return cmd, [tr("Chưa cài lệnh '{v}'", v=a.usage_command[0])]
        run = Run(list(a.usage_command), str(self.root), self.env_for(), use_pty=a.pty,
                  timeout=timeout, on_line=lambda _l: None)
        try:
            code = await run.start()
        except Exception as e:
            return cmd, [tr("Không chạy được: {e}", e=e)]
        lines = [ln for ln in run.lines if ln.strip()]
        if len(lines) > 20:  # opencode stats kèm bảng công cụ dài: giữ phần tổng quan / chi phí
            lines = lines[:20] + [tr("… (còn {v} dòng — chạy `{cmd}` để xem đủ)", v=len(lines) - 20, cmd=cmd)]
        if run.timed_out:
            lines.append(tr("(hết {v} giây chờ)", v=int(timeout)))
        elif code != 0:
            lines.append(tr("(mã thoát {code})", code=code))
        return cmd, lines or [tr("(không in gì)")]

    async def _grok_reports(self, a: AgentConfig, timeout: float = 20) -> list[dict]:
        """JSON của `grok usage <phiên>` cho các phiên grok gần đây (lệnh chính thức, thay cho đọc file phiên)."""
        import json

        async def one(sid: str) -> dict | None:
            try:
                proc = await asyncio.create_subprocess_exec(
                    a.binary, "usage", sid, cwd=str(self.root), env=self.env_for(), stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            except OSError:
                return None
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return None
            try:
                rep = json.loads(out.decode("utf-8", "replace"))
            except ValueError:
                return None
            return rep if isinstance(rep, dict) else None
        reps = await asyncio.gather(*(one(s) for s in limits.grok_recent_sessions()))
        return [r for r in reps if r]

    async def usage_all(self, names: list[str] | None = None, on_done=None) -> dict[str, tuple[str, list[str]]]:
        """Hỏi song song hạn mức của các agent (mặc định: reports.usage_agents — đủ claude, codex, agy, grok).
        on_done(tên, cmd, lines) gọi khi từng cái xong.
        Hạn mức là của tài khoản CLI, không phải của agent: nhiều agent cùng một CLI (antigravity, antigravity-ui…)
        chỉ hỏi một lần, kết quả đứng tên "antigravity, antigravity-ui"."""
        if names is None:
            from .reports import usage_agents
            names = usage_agents(self.cfg)
        groups: dict[tuple, list[str]] = {}
        for n in names:
            a = self.cfg.agents.get(n)
            key = (tuple(a.usage_command) if a.usage_command else ("bin", Path(a.binary).name)) if a else ("?", n)
            groups.setdefault(key, []).append(n)

        async def one(group: list[str]):
            agents = [self.cfg.agents[n] for n in group if n in self.cfg.agents]
            first = next((a.name for a in agents if a.enabled), group[0])  # agent đang bật đại diện cho CLI
            cmd, lines = await self.agent_usage(first)
            label = ", ".join(group)
            if on_done:
                on_done(label, cmd, lines)
            return label, (cmd, lines)
        return dict(await asyncio.gather(*(one(g) for g in groups.values())))

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
            return tr("Không có task #{tid}", tid=tid)
        if t.status == RUNNING:
            return tr("Task #{tid} đang chạy", tid=tid)
        self.db.update_task(tid, prompt=prompt)
        self.emit("changed")
        return tr("Đã sửa nội dung task #{tid}", tid=tid)

    def retry(self, tid: int) -> str:
        t = self.db.task(tid)
        if not t:
            return tr("Không có task #{tid}", tid=tid)
        if t.status in (RUNNING, QUEUED, ASKING):
            return tr("Task #{tid} đang {status}", tid=tid, status=t.status)
        # cùng phiên: agent nhớ đề bài và lần làm trước, chỉ cần biết lý do chạy lại
        resume = P.retry_prompt(t.error or t.result or "", self.use_worktree) if t.session else None
        ask = dict(t.ask, parked=False) if t.ask else None
        self._requeues.pop(tid, None)
        self.db.update_task(tid, status=QUEUED, error=None, result=None, started=None, finished=None,
                            resume=resume, ask=ask)
        # mở chặn lan truyền: chuỗi 1 → 2 → 3 mà 1 lỗi thì cả 2 lẫn 3 đều bị chặn, không chỉ task phụ thuộc trực tiếp
        requeued, more = {tid}, True
        while more:
            more = False
            for o in self.db.tasks(status=BLOCKED):
                if o.id not in requeued and requeued & set(o.depends_on):
                    self.db.update_task(o.id, status=QUEUED, error=None)
                    requeued.add(o.id)
                    more = True
        if t.goal_id:
            g = self.db.goal(t.goal_id)
            if g and g.status in ("done", "incomplete", "failed"):
                self.db.update_goal(g.id, status="running")
        self.log(tr("↻ Chạy lại task #{tid}", tid=tid))
        self.emit("changed")
        return tr("Đã xếp lại task #{tid}", tid=tid)

    # ------------------------------------------------------------------ <<<ASK>>>: agent hỏi người dùng
    def ask_active(self, tasks: list[Task] | None = None) -> Task | None:
        """Task đang chờ người dùng trả lời câu hỏi (cũ nhất trước) — hiện ở khung hỏi đáp như /grill.
        tasks: danh sách đã đọc sẵn."""
        src = self.db.tasks(status=ASKING) if tasks is None else [t for t in tasks if t.status == ASKING]
        asking = [t for t in src if t.question()]
        return min(asking, key=lambda t: t.id) if asking else None

    # ------------------------------------------------------------------ ⏸ bước duyệt của workflow
    def _gate_ask(self, t: Task) -> None:
        """Mọi bước bước duyệt chờ đã xong: hỏi người dùng (khung hỏi đáp như <<<ASK>>>) — Tiếp tục / Dừng / góp ý.
        Không ai trả lời được (ateam flow -y) thì tự Tiếp tục."""
        deps = self._through_gates(t.depends_on)
        see = "\n".join(f"#{d.id} {d.title} ({d.agent})" for d in deps)
        text = t.prompt if t.prompt and t.prompt != t.title else tr("Duyệt kết quả của các bước trước")
        q = {"q": f"⏸ {t.title}: {text}" + ("\n" + tr("Kết quả cần xem:") + "\n" + see if see else ""),
             "why": tr("Tiếp tục: chạy bước sau · Dừng: kết thúc mục tiêu · gõ góp ý: các bước trên làm lại theo góp ý"),
             "options": [tr("Tiếp tục"), tr("Dừng")], "rec": tr("Tiếp tục"), "gate": True, "a": None}
        qa = list((t.ask or {}).get("qa") or [])
        if self.auto_answer:
            qa.append(dict(q, a=q["rec"]))
            self.db.update_task(t.id, status=DONE, ask={"qa": qa}, result=tr("Đã duyệt (tự động)"),
                                started=time.time(), finished=time.time())
            self.log(tr("⏸ #{tid} {title}: tự duyệt (không có ai trả lời)", tid=t.id, title=t.title))
            return
        self.db.update_task(t.id, status=ASKING, ask={"qa": qa + [q]}, error=None, result=None)
        self.log(tr("⏸ #{tid} chờ bạn duyệt: {title}", tid=t.id, title=t.title))

    def _gate_answer(self, t: Task, q: dict, answer: str | None) -> str:
        go, stop = q["options"][:2]
        a = pick_option(q, answer or "") or go  # ⏭ (không quyết) = Tiếp tục
        q["a"] = a
        if a == go:
            self.db.update_task(t.id, status=DONE, ask=t.ask, result=tr("Đã duyệt"), finished=time.time())
            self.log(tr("✓ #{tid} đã duyệt: {title}", tid=t.id, title=t.title))
            msg = tr("Đã duyệt — chạy bước tiếp theo")
        elif a == stop:
            self.db.update_task(t.id, status=CANCELLED, ask=t.ask, error=tr("Bạn dừng ở bước duyệt"),
                                finished=time.time())
            dead, more = {t.id}, True  # huỷ lan truyền các bước phía sau
            while more:
                more = False
                for o in self.db.tasks(goal_id=t.goal_id, status=(DRAFT, QUEUED)):
                    if o.id not in dead and dead & set(o.depends_on):
                        self.db.update_task(o.id, status=CANCELLED, finished=time.time())
                        dead.add(o.id)
                        more = True
            if t.goal_id is not None:  # người dùng tự dừng: kết thúc luôn, không gọi trưởng nhóm review
                self.db.update_goal(t.goal_id, status="incomplete",
                                    summary=tr("Bạn dừng ở bước duyệt #{tid}", tid=t.id))
            self.log(tr("■ #{tid} dừng ở bước duyệt: {title}", tid=t.id, title=t.title))
            msg = tr("Đã dừng mục tiêu ở bước duyệt #{tid}", tid=t.id)
        else:  # góp ý: các bước bước duyệt chờ làm lại theo góp ý, xong thì hỏi lại
            redo = []
            for d in self._through_gates(t.depends_on):
                if d.session and d.session_agent == d.agent:  # tiếp phiên: agent nhớ đề bài và lần làm trước
                    self.db.update_task(d.id, status=QUEUED, result=None, error=None, started=None, finished=None,
                                        resume=P.user_feedback_prompt(a))
                else:
                    self.db.update_task(d.id, status=QUEUED, result=None, error=None, started=None, finished=None,
                                        prompt=d.prompt + "\n\nUSER FEEDBACK (after reviewing your previous result — "
                                                          "address this):\n" + a)
                redo.append(d.id)
            self.db.update_task(t.id, status=QUEUED, ask=t.ask, error=None)
            self.log(tr("↩ #{tid} góp ý: {a} — làm lại {v}", tid=t.id, a=a[:200],
                        v=", ".join(f"#{x}" for x in redo)))
            msg = tr("Đã gửi góp ý — {v} làm lại, xong sẽ hỏi bạn duyệt lại", v=", ".join(f"#{x}" for x in redo))
        self.emit("changed")
        return msg

    def _through_gates(self, ids: list[int]) -> list[Task]:
        """Task theo id, thay bước ⏸ duyệt bằng các bước nó chờ (đệ quy, không trùng)."""
        out: list[Task] = []
        seen: set[int] = set()
        todo = list(ids)
        while todo:
            d = self.db.task(todo.pop(0))
            if not d or d.id in seen:
                continue
            seen.add(d.id)
            if d.kind == KIND_GATE:
                todo[:0] = d.depends_on
            else:
                out.append(d)
        return out

    def answer_task(self, tid: int, answer: str | None) -> str:
        """Trả lời câu hỏi của agent (None = để agent tự quyết) rồi xếp task chạy tiếp."""
        t = self.db.task(tid)
        q = t.question() if t else None
        if not t or t.status != ASKING or not q:
            return tr("Task #{tid} không có câu hỏi nào đang chờ", tid=tid)
        if t.kind == KIND_GATE:
            return self._gate_answer(t, q, answer)
        q["a"] = pick_option(q, answer or "") or P.SKIP_ANSWER
        qa = t.ask["qa"]
        self.db.update_task(tid, status=QUEUED, ask=t.ask, started=None, error=None,
                            resume=P.answer_prompt(q["q"], q["a"], len(qa) < MAX_ASKS))
        self.log(tr("💬 #{tid} trả lời {agent}: {a}", tid=tid, agent=t.agent, a=q["a"][:200]))
        self.emit("changed")
        return tr("Đã trả lời — {agent} làm tiếp task #{tid}", agent=t.agent, tid=tid)

    def cancel_command(self, ref: str) -> str:
        """/cancel <task> | m<mục tiêu> (huỷ lượt lập kế hoạch đang chạy) — TUI và web dùng chung."""
        m = re.fullmatch(r"#?([mM]?)(\d+)", ref.strip())
        if not m:
            return tr("Dùng: /cancel <task> hoặc /cancel m<mục tiêu> (huỷ lập kế hoạch)")
        return self.cancel_planning(int(m.group(2))) if m.group(1) else self.cancel(int(m.group(2)))

    def cancel(self, tid: int) -> str:
        t = self.db.task(tid)
        if not t:
            return tr("Không có task #{tid}", tid=tid)
        if t.status == RUNNING and tid in self.runs:
            run = self.runs[tid]
            self._cancel_req.add(tid)  # cả khi đang chạy lệnh kiểm tra: không giao sửa lỗi nữa
            if run is not None:
                run.cancel()
            return tr("Đang dừng task #{tid}…", tid=tid)
        if t.status in (DRAFT, QUEUED, ASKING):
            if t.status == ASKING and t.branch and (t.ask or {}).get("parked"):
                self._spawn(self._drop_branch(t))  # phần làm dở trước khi hỏi
            self.db.update_task(tid, status=CANCELLED, finished=time.time())
            self.emit("changed")
            return tr("Đã huỷ task #{tid}", tid=tid)
        if t.status == REVIEW:
            self._spawn(self.reject(tid, None))
            return tr("Đang huỷ task #{tid} và xoá nhánh của nó…", tid=tid)
        return tr("Task #{tid} đã kết thúc ({status})", tid=tid, status=t.status)

    def note(self, text: str, author: str = "user") -> None:
        self.db.add_note(author, text)
        self.log(tr("📝 Ghi chú ({author}): {text}", author=author, text=text))

    def compact_sources(self) -> tuple[str, str, str]:
        """Ghi chú, mục tiêu và log hệ thống kể từ lần /compact trước — thứ sẽ được tóm tắt."""
        since = self.db.last_compact()
        goals = "\n".join(f"#{g.id} [{g.status}] {g.full_text()}" + (f" — {g.summary}" if g.summary else "")
                          for g in self.db.goals()[-12:] if (g.created or 0) >= since)
        log = "\n".join(read_tail(self.logs / "system.log", 60))
        return self.notes_text(), goals, log

    async def compact(self, focus: str = "") -> tuple[bool, str]:
        """/compact: trưởng nhóm tóm tắt ghi chú + mục tiêu + log thành 1 ghi chú ngắn; prompt sau chỉ
        mang bản tóm tắt này (cùng ghi chú mới hơn) thay vì cả chuỗi ghi chú cũ. Trả về (thành công, lời nhắn)."""
        if self.compacting:
            return False, tr("Đang thu gọn ngữ cảnh rồi, chờ chút…")
        notes, goals, log = self.compact_sources()
        if not notes and not goals:
            return False, tr("Chưa có ghi chú hay mục tiêu nào để thu gọn.")
        self.compacting = True
        try:
            self.log(tr("🗜 {lead} đang thu gọn ngữ cảnh…", lead=self.cfg.lead))
            out = await self._call_lead(P.compact_prompt(notes=notes, goals=goals, log=log, focus=focus,
                                                         cwd=str(self.root)), tr("Thu gọn ngữ cảnh"))
            # ~25 gạch đầu dòng có thể quá 2500 ký tự mặc định: cắt thì mất dòng cuối (việc còn dở)
            summary = P.extract_summary(out, 5000) if out and "SUMMARY:" in out else ""
            if not summary:
                self.log(tr("✗ Không thu gọn được: trưởng nhóm không trả về dòng SUMMARY: (xem "
                            ".ateam/logs/lead.log). Ghi chú cũ vẫn giữ nguyên."))
                return False, tr("Không thu gọn được — ghi chú cũ vẫn giữ nguyên")
            self.db.add_note(COMPACT_AUTHOR, summary)
            before = len(notes) + len(goals)
            self.log(tr("🗜 Đã thu gọn ngữ cảnh: ~{before} → {v} ký tự. Bản tóm tắt:", before=before, v=len(summary)))
            for line in summary.splitlines():
                self.log("   " + line)
            return True, tr("Đã thu gọn ngữ cảnh (~{before} → {v} ký tự)", before=before, v=len(summary))
        finally:
            self.compacting = False
            self.emit("changed")

    async def init_overview(self, focus: str = "") -> tuple[bool, str]:
        """/init: trưởng nhóm tìm hiểu dự án và viết .ateam/project.md (đã có thì cập nhật theo các thay đổi kể từ
        lần trước — rẻ hơn viết lại). Trả về (thành công, lời nhắn)."""
        if self.initing:
            return False, tr("Trưởng nhóm đang tìm hiểu dự án rồi, chờ chút…")
        self.initing = True
        try:
            current, meta = overview.load(self.root)
            changes = ""
            if current:
                commits, changed = await self.overview_changes(meta.get("commit", ""))
                rc, status = await self._git("status", "--short")
                status = status.strip() if rc == 0 else ""
                if commits == 0 and not changed and not status and not focus.strip():  # không gọi agent vô ích
                    return True, tr("Bản tổng quan dự án vẫn mới — không có thay đổi nào từ lần /init trước (gõ "
                                    "/init <trọng tâm> để buộc cập nhật, xoá .ateam/project.md để viết lại)")
                changes = overview.changes_text(commits, changed, status)
            self.log(tr("🔎 {lead} đang tìm hiểu dự án (/init)…", lead=self.cfg.lead))
            native = [x["path"] for x in rules.native_files(self.root)]
            out = await self._call_lead(P.init_prompt(cwd=str(self.root), current=current, changes=changes,
                                                      focus=focus, native=native),
                                        tr("Tìm hiểu dự án (/init)"), slow=True)
            text = P.extract_overview(out or "")
            if not text:
                self.log(tr("✗ /init: trưởng nhóm không trả về bản tổng quan (xem .ateam/logs/lead.log)."))
                return False, tr("Trưởng nhóm không trả về bản tổng quan (xem .ateam/logs/lead.log)")
            rc, head = await self._git("rev-parse", "HEAD")
            overview.save(self.root, text, head.strip() if rc == 0 else "")
            self._overview_hinted = False
            self.log(tr("🔎 Đã viết bản tổng quan dự án .ateam/project.md (~{n} ký tự) — mọi kế hoạch & task sau "
                        "sẽ dùng nó.", n=len(text)))
            return True, tr("Đã viết bản tổng quan dự án .ateam/project.md (~{n} ký tự)", n=len(text))
        finally:
            self.initing = False
            self.emit("changed")

    def commit_agent(self) -> str:
        """Agent viết commit message: chọn ở tab Git (cfg.commit_agent), mặc định trưởng nhóm."""
        a = self.cfg.agents.get(self.cfg.commit_agent)
        return self.cfg.commit_agent if a and a.enabled else self.cfg.lead

    async def commit_message(self) -> tuple[bool, str]:
        """Agent viết commit (commit_agent) viết message cho thay đổi đã stage (chưa stage gì thì cho
        mọi thay đổi). Trả về (thành công, message hoặc lời nhắn lỗi)."""
        from .gitops import GitRepo
        repo = GitRepo(self.root)
        diff = await repo.staged_diff()
        if not diff:
            stat = await repo.diff_text("HEAD", "--stat")
            body = await repo.diff_text("HEAD")
            _, others = await repo.run("ls-files", "--others", "--exclude-standard")
            diff = (stat + "\n" + body[:60_000]).strip()
            new = others.strip().splitlines()
            if new:  # thư mục build / node_modules chưa ignore: hàng nghìn file — prompt đi qua argv
                more = [f"… (+{len(new) - UNTRACKED_MAX} more)"] if len(new) > UNTRACKED_MAX else []
                diff += "\n\nNew untracked files:\n" + "\n".join(new[:UNTRACKED_MAX] + more)
        if not diff.strip():
            return False, tr("Không có thay đổi nào để viết commit message")
        recent = "\n".join("- " + c.subject for c in await repo.log(8))
        writer = self.commit_agent()
        out = await self._call_lead(P.commit_message_prompt(diff=diff, recent=recent, cwd=str(self.root)),
                                    tr("Viết commit message"), first=writer, effort=QUICK_EFFORT)
        msg = P.extract_commit_message(out or "")
        if not msg:
            return False, tr("{agent} không trả về commit message (xem .ateam/logs/lead.log)", agent=writer)
        return True, msg

    CODE_AI_CONTEXT = 200  # số dòng trước / sau đoạn chọn gửi kèm cho agent

    async def code_ai(self, mode: str, path: str, text: str, start: int, end: int, instruction: str = "",
                      agent: str = "") -> tuple[bool, str]:
        """Tab Code (web): agent viết lại đoạn text[start:end] của file (mode "edit" → đoạn code mới, ⌘I) hoặc giải
        thích nó ("explain" → Markdown). Agent chỉ trả lời, không sửa file. (thành công, kết quả hoặc lời báo lỗi)."""
        from . import editor
        from .i18n import get_lang
        start, end = sorted((max(0, min(start, len(text))), max(0, min(end, len(text)))))
        before = "".join(text[:start].splitlines(keepends=True)[-self.CODE_AI_CONTEXT:])
        after = "".join(text[end:].splitlines(keepends=True)[:self.CODE_AI_CONTEXT])
        lang = editor.language_name(Path(path))
        who = agent if agent in self.cfg.active_agents() else self.commit_agent()
        if mode == "edit":
            if not instruction.strip():
                return False, tr("Gõ yêu cầu sửa trước (vd: thêm xử lý lỗi)")
            prompt = P.code_edit_prompt(path=path, language=lang, before=before, selection=text[start:end], after=after,
                                        instruction=instruction.strip(), cwd=str(self.root))
            out = await self._call_lead(prompt, tr("Sửa code inline: {path}", path=path), first=who)
            code = P.extract_code_block(P.strip_echo(out or "", prompt))
            if code is None:
                return False, tr("{agent} không trả về đoạn code (xem .ateam/logs/lead.log)", agent=who)
            return True, code
        prompt = P.code_explain_prompt(path=path, language=lang, before=before, selection=text[start:end], after=after,
                                       question=instruction.strip(), cwd=str(self.root), lang=get_lang())
        out = await self._call_lead(prompt, tr("Giải thích code: {path}", path=path), first=who,
                                    effort=QUICK_EFFORT)
        answer = P.extract_answer(P.strip_echo(out or "", prompt))
        if not answer:
            return False, tr("{agent} không trả lời (xem .ateam/logs/lead.log)", agent=who)
        return True, answer

    async def write_skill(self, description: str = "", gid: int | None = None, agent: str = "",
                          focus: str = "") -> tuple[bool, "dict | str"]:
        """✨ Trang 🧩 Skills: agent (mặc định trưởng nhóm) viết SKILL.md theo mô tả, hoặc rút quy trình của mục tiêu
        gid đã làm xong (💾 Lưu thành skill). Không lưu: trả (thành công, {name, description, body} để điền form — hoặc
        lời nhắn lỗi)."""
        who = agent if agent in self.cfg.active_agents() else self.cfg.lead
        names = [x.name for x in skills.scan(self.root)]
        if gid is not None:
            g = self.db.goal(gid)
            if not g:
                return False, tr("Không còn mục tiêu #{gid}", gid=gid)
            rows = [(t.id, t.agent, t.title, t.prompt[:2000], (t.result or t.error or "")[:2000], self.log_path(t.id))
                    for t in self.db.tasks(goal_id=gid) if t.status != CANCELLED and t.kind != KIND_VERIFY]
            prompt = P.skill_from_goal_prompt(goal=g.full_text(), summary=g.summary or "", tasks=rows,
                                              existing=names, cwd=str(self.root), focus=focus.strip())
            label = tr("Lưu mục tiêu #{gid} thành skill", gid=gid)
        else:
            if not description.strip():
                return False, tr("Mô tả skill bạn muốn trước (vd: quy trình phát hành bản mới)")
            prompt = P.skill_write_prompt(description=description.strip(), existing=names, cwd=str(self.root))
            label = tr("Viết skill")
        out = await self._call_lead(prompt, label, first=who)
        text = P.extract_skill(P.strip_echo(out or "", prompt))
        if not text:
            return False, tr("{agent} không trả về SKILL.md (xem .ateam/logs/lead.log)", agent=who)
        meta, body = skills.parse(text)
        return True, {"name": str(meta.get("name") or "").strip(),
                      "description": " ".join(str(meta.get("description") or "").split()), "body": body.strip()}

    async def suggest_workflow(self, description: str) -> tuple[bool, "dict | str"]:
        """Trưởng nhóm thiết kế workflow tuỳ chỉnh theo mô tả của người dùng (form /custom → ✨ Gợi ý).
        Trả về (thành công, dữ liệu điền form — xem wizard.suggestion_form — hoặc lời nhắn lỗi)."""
        if not description.strip():
            return False, tr("Mô tả quy trình bạn muốn trước (vd: thiết kế → code → test → review)")
        on = skills.enabled(self.root, skills.scan(self.root))
        out = await self._call_lead(P.workflow_suggest_prompt(self.cfg, description.strip(), str(self.root),
                                                              skills.index_block(on)), tr("Gợi ý workflow"))
        return self._workflow_form(out, on)

    async def workflow_from_goal(self, gid: int) -> tuple[bool, "dict | str"]:
        """🔀 Lưu mục tiêu đã xong thành workflow: trưởng nhóm khái quát các task (giữ cấu trúc, thay chi tiết bằng
        {goal}) → dữ liệu điền form workflow, chưa lưu; "project" tick sẵn (thường mang lệnh / đường dẫn của dự án)."""
        g = self.db.goal(gid)
        if not g or g.status != "done":
            return False, tr("Chỉ lưu được mục tiêu đã xong thành workflow")
        tasks = [t for t in self.db.tasks(goal_id=gid) if t.status != CANCELLED]
        if not tasks:
            return False, tr("Mục tiêu #{gid} không có task nào", gid=gid)
        num = {t.id: i for i, t in enumerate(tasks, 1)}
        lines = []
        for i, t in enumerate(tasks, 1):
            deps = ", ".join(str(num[d]) for d in t.depends_on if d in num) or "none"
            agent = LEAD_ALIAS if t.agent == self.cfg.lead else t.agent
            prompt = t.prompt if len(t.prompt) <= 600 else t.prompt[:600] + "…"
            lines.append(f"{i}. [{agent}, {t.kind or KIND_CODE}] {t.title} — waits for: {deps} — {t.status}\n"
                         f"   Prompt: {prompt}")
        on = skills.enabled(self.root, skills.scan(self.root))
        out = await self._call_lead(P.workflow_from_goal_prompt(self.cfg, g.full_text(), "\n".join(lines),
                                                                str(self.root), skills.index_block(on)),
                                    tr("Lưu mục tiêu #{gid} thành workflow", gid=gid))
        ok, form = self._workflow_form(out, on)
        if ok:
            form["project"] = True
        return ok, form

    def _workflow_form(self, out: str | None, on: list) -> tuple[bool, "dict | str"]:
        """JSON workflow trưởng nhóm trả về → dữ liệu điền form (skill của bước thành $tên trong prompt)."""
        from . import wizard
        raw = P.extract_json(out or "", dict, keys=("steps", "name"))
        if not raw:
            return False, tr("{agent} không trả về workflow (xem .ateam/logs/lead.log)", agent=self.cfg.lead)
        try:
            return True, wizard.suggestion_form(self.cfg, raw, {x.name for x in on})
        except ValueError as e:
            return False, str(e)

    def force_review(self, gid: int) -> str:
        g = self.db.goal(gid)
        if not g:
            return tr("Không có mục tiêu #{gid}", gid=gid)
        if gid in self.lead_busy:
            return tr("Trưởng nhóm đang xử lý mục tiêu này")
        self.lead_busy.add(gid)
        self._spawn(self._review(gid))
        return tr("Trưởng nhóm đang review mục tiêu #{gid}…", gid=gid)

    # ------------------------------------------------------------------ lịch chạy
    def running_count(self, agent: str | None = None, index: dict | None = None) -> int:
        """index: DB.task_index() đã đọc sẵn trong lượt tick. Task kiểm tra cuối đang chạy lệnh kiểm tra (_checking)
        không tính vào suất của agent: nó chưa gọi agent."""
        if agent is None:
            return len(self.runs)
        tids = [tid for tid in self.runs if tid not in self._checking]
        if index is not None:
            return sum(1 for tid in tids if tid in index and index[tid][1] == agent)
        return sum(1 for tid in tids if (t := self.db.task(tid)) and t.agent == agent)

    async def _wait_agent_free(self, agent: str, tid: int) -> None:
        """Task kiểm tra cuối phải gọi agent sửa: chờ tới khi agent còn suất (max_concurrent) hoặc task bị huỷ."""
        a = self.cfg.agents.get(agent)
        waiting = False
        while a and tid not in self._cancel_req and self.running_count(agent) >= a.max_concurrent:
            if not waiting:
                waiting = True
                self.log(tr("⏳ #{tid} chờ {agent} rảnh để sửa lỗi kiểm tra cuối", tid=tid, agent=agent))
            await asyncio.sleep(0.5)

    def is_idle(self) -> bool:
        """Không còn việc gì chạy được (task chỉ chờ agent hồi hạn mức thì không tính)."""
        if self.runs or self.lead_busy:
            return False
        for t in self.db.tasks(status=QUEUED):
            if self.in_cooldown(t.agent) and not self.pick_fallback(t.agent):
                continue  # chờ hồi hạn mức
            deps = [self.db.task(d) for d in t.depends_on]
            if any(d and d.status in (REVIEW, DRAFT, ASKING) for d in deps):
                continue  # chờ người duyệt
            return False
        return True

    def tick(self) -> None:
        agents = self.cfg.active_agents()
        changed = False
        queued = self.db.tasks(status=QUEUED)
        index = self.db.task_index() if queued else {}  # trạng thái mọi task, một truy vấn cho cả lượt
        for t in queued:
            if t.id in self.runs or t.goal_id in self._cp_pending:
                continue
            if t.agent not in agents:
                self.db.update_task(t.id, status=FAILED, error=tr("Không có agent '{agent}'", agent=t.agent))
                changed = True
                continue
            dep_status = [(d, index[d][0] if d in index else "missing") for d in t.depends_on]
            bad = [d for d, s in dep_status if s in FINISHED_BAD or s in (CONFLICT, "missing")]
            if bad:
                self.db.update_task(t.id, status=BLOCKED,
                                    error=tr("Task phụ thuộc lỗi/huỷ: {v}", v=', '.join('#' + str(b) for b in bad)))
                self.log(tr("⛔ Task #{id} bị chặn vì #{v} không xong.", id=t.id, v=', #'.join(map(str, bad))))
                changed = True
                continue
            if any(s != DONE for _, s in dep_status):
                continue
            if t.kind == KIND_GATE:  # ⏸ bước duyệt: không gọi agent, hỏi người dùng
                self._gate_ask(t)
                changed = True
                continue
            chat = t.source == CHAT  # người dùng đang chờ trả lời: không xếp sau hàng đợi chung, không đổi agent
            # kiểm tra cuối: bước đầu chỉ chạy lệnh kiểm tra như ngay trong suất của task ở bản cũ — không chờ suất song
            # song, agent hết hạn mức hay agent bận; fail mới cần agent sửa (_run_task tự chờ agent đó rảnh)
            check = t.kind == KIND_VERIFY
            if not chat and (self.paused or (not check and len(self.runs) >= self.cfg.max_parallel)):
                continue
            if chat and self.in_cooldown(t.agent):
                self.db.update_task(t.id, status=FAILED, finished=time.time(),
                                    error=tr("{agent} đang hết hạn mức (đến {v})", agent=t.agent,
                                             v=self.cooldown_label(t.agent)))
                changed = True
                continue
            if self.in_cooldown(t.agent) and not check:
                fb = self.pick_fallback(t.agent)
                if not fb:
                    continue  # chờ hạn mức hồi lại
                self.db.update_task(t.id, agent=fb, model=None, effort=None)
                self.log(tr("↪ #{id} chuyển từ {agent} sang {fb} vì {agent} hết hạn mức (đến {v}).", id=t.id, agent=t.agent, fb=fb, v=self.cooldown_label(t.agent)))
                t = self.db.task(t.id)
                changed = True
            a = agents[t.agent]
            if not chat and not check and self.running_count(t.agent, index) >= a.max_concurrent:
                continue
            if not a.installed():
                self.db.update_task(t.id, status=FAILED,
                                    error=tr("Chưa cài lệnh '{binary}' (kiểm tra bằng `ateam doctor`)", binary=a.binary))
                self.log(tr("✗ Task #{id}: chưa cài '{binary}'.", id=t.id, binary=a.binary))
                changed = True
                continue
            # chiếm chỗ ngay để không chạy trùng (tiến trình khác cùng DB có thể vừa chiếm)
            if not self.db.claim_task(t.id):
                changed = True
                continue
            index[t.id] = (RUNNING, t.agent)
            self.runs[t.id] = None  # type: ignore[assignment]
            if check:
                self._checking.add(t.id)
            self._spawn(self._run_task(t.id))
            changed = True
        if self._check_goals():
            changed = True
        if time.time() - self._sched_at >= schedule.CHECK_EVERY:
            self._sched_at = time.time()
            if self.check_schedules():
                changed = True
        if changed:
            self.emit("changed")

    # ------------------------------------------------------------------ ↩ điểm khôi phục, /undo (checkpoint.py)
    def _checkpoint_goal(self, gid: int) -> None:
        """Chụp HEAD + thư mục làm việc trước mục tiêu (nền); task của mục tiêu chờ chụp xong mới chạy."""
        if not (self.root / ".git").exists():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:  # gọi ngoài vòng lặp (test, CLI đồng bộ): bỏ qua
            return
        self._cp_pending.add(gid)

        async def run() -> None:
            try:
                err = await checkpoint.create(self.root, f"m{gid}")
                if err:
                    self.log(tr("⚠ Không tạo được điểm khôi phục cho mục tiêu #{gid}: {e}", gid=gid, e=err))
            finally:
                self._cp_pending.discard(gid)
        self._spawn(run())

    def undo_ref(self, ref: str) -> str:
        """"" = mục tiêu mới nhất; "m12" / "12" / "#12" = mục tiêu 12; "redo" = bản chụp ngay trước lần /undo cuối.
        Trả khoá checkpoint ("m12", "redo") hoặc "" nếu không hiểu."""
        ref = ref.strip().lower()
        if ref in (checkpoint.REDO, "lai", "back"):
            return checkpoint.REDO
        if not ref:
            goals = self.db.goals()
            return f"m{goals[-1].id}" if goals else ""
        m = re.fullmatch(r"#?m?(\d+)", ref)
        return f"m{m.group(1)}" if m else ""

    async def undo_preview(self, ref: str) -> tuple[str, str] | str:
        """(tiêu đề, nội dung hỏi lại) trước khi /undo, hoặc chuỗi lỗi."""
        key = self.undo_ref(ref)
        if not key:
            return tr("Dùng: /undo [m<số mục tiêu>|redo]")
        files = await checkpoint.changes(self.root, key)
        if isinstance(files, str):
            return files
        if not files:
            return tr("Thư mục dự án đã giống lúc {key} — không có gì để hoàn tác", key=key)
        names = [ln.split("\t", 1)[-1] for ln in files]
        new = sum(1 for ln in files if ln.startswith("A"))
        body = tr("Đưa nhánh và mọi file của dự án về lúc trước mục tiêu #{gid}: {n} file đổi lại, {new} file tạo "
                  "sau đó bị xoá.", gid=key[1:], n=len(files), new=new) if key != checkpoint.REDO else \
            tr("Lấy lại trạng thái ngay trước lần /undo gần nhất: {n} file đổi lại.", n=len(files))
        if key != checkpoint.REDO:
            later = [g for g in self.db.goals() if g.id > int(key[1:]) and g.status != "cancelled"]
            if later:
                body += "\n" + tr("⚠ Thay đổi của mục tiêu sau đó cũng mất: {v}", v=", ".join(f"#{g.id}" for g in later))
            body += "\n" + tr("Lấy lại được bằng /undo redo. File bị .gitignore (node_modules, .env…) giữ nguyên.")
        body += "\n\n" + "\n".join("  " + x for x in names[:12]) + (f"\n  … +{len(names) - 12}" if len(names) > 12 else "")
        return tr("↩ Hoàn tác về trước mục tiêu #{gid}?", gid=key[1:]) if key != checkpoint.REDO else \
            tr("↩ Lấy lại thay đổi trước /undo?"), body

    async def undo(self, ref: str) -> tuple[bool, str]:
        """Hoàn tác về điểm khôi phục: huỷ việc còn dở của mục tiêu đó và các mục tiêu sau, rồi khôi phục file."""
        key = self.undo_ref(ref)
        if not key:
            return False, tr("Dùng: /undo [m<số mục tiêu>|redo]")
        if self.runs or self.lead_busy or self._cp_pending:
            return False, tr("Đang có agent chạy — đợi xong hoặc huỷ (/cancel) rồi /undo")
        ok, msg = await checkpoint.restore(self.root, key)
        if not ok:
            self.log(tr("✗ /undo: {e}", e=msg))
            return False, msg
        if key != checkpoint.REDO:
            gid = int(key[1:])
            for g in self.db.goals():
                if g.id < gid:
                    continue
                for t in self.db.tasks(goal_id=g.id, status=ACTIVE):
                    self.db.update_task(t.id, status=CANCELLED, finished=time.time(), error=tr("Hoàn tác bằng /undo"))
                if g.status not in GOAL_ENDED:
                    self.db.update_goal(g.id, status="cancelled", summary=tr("Hoàn tác bằng /undo"))
                elif g.id == gid:
                    self.db.update_goal(g.id, summary=((g.summary or "") + "\n" + tr("↩ Đã hoàn tác bằng /undo")).strip())
        self.log("↩ " + msg)
        self.emit("changed")
        return True, "↩ " + msg

    # ------------------------------------------------------------------ ⏰ lịch hẹn (schedule.py)
    def schedule_command(self, rest: str) -> str:
        """/schedule, `ateam schedule`: không tham số = xem lịch; rm <số> = huỷ; <khi> <mục tiêu> = hẹn mới."""
        words = rest.split()
        if not words or words[0].lower() in ("list", "ls"):
            return schedule.list_text(self.db.schedules())
        if words[0].lower() in schedule.REMOVE_WORDS:
            ids = [int(w.lstrip("#")) for w in words[1:] if w.lstrip("#").isdigit()]
            if not ids:
                return tr("Dùng: /schedule rm <số>")
            have = {s["id"] for s in self.db.schedules("waiting")}
            for sid in ids:
                if sid in have:
                    self.db.update_schedule(sid, status="cancelled")
            gone = [f"#{i}" for i in ids if i in have]
            self.emit("changed")
            return (tr("⏰ Đã huỷ lịch {v}", v=", ".join(gone)) if gone
                    else tr("Không có lịch đang chờ nào số {v}", v=", ".join(map(str, ids))))
        res = schedule.parse(rest, list(self.cfg.active_agents()))
        if isinstance(res, str):
            return res
        if res["flow"] and res["flow"] not in self.cfg.workflows:
            return tr("Không có workflow '{name}'", name=res["flow"])
        sid = self.db.add_schedule(res["text"], res["kind"], at=res["at"], daily=res["daily"], agent=res["agent"],
                                   flow=res["flow"])
        label = schedule.when_label(res)
        self.log(tr("⏰ Hẹn #{sid} ({when}): {text}", sid=sid, when=label, text=res["text"]))
        self.emit("changed")
        return tr("⏰ Đã hẹn #{sid} — {when}: {text} (ateam cần đang mở lúc đó; kế hoạch tự duyệt)", sid=sid,
                  when=label, text=res["text"])

    def check_schedules(self, now: float | None = None) -> bool:
        """Chạy các lịch hẹn tới giờ; mục tiêu do lịch tạo thì tự duyệt kế hoạch (người dùng không ngồi đó)."""
        now = time.time() if now is None else now
        changed = False
        rows = self.db.schedules()
        for gid in {r["goal_id"] for r in rows if r.get("goal_id") and (r.get("fired") or 0) > now - 86400}:
            g = self.db.goal(gid)
            if g and g.status == "awaiting":  # kế hoạch nháp (cả vòng sau) của mục tiêu do lịch tạo
                self.approve(gid)
                changed = True
        for s in rows:
            if s["status"] != "waiting":
                continue
            if s["kind"] == schedule.QUOTA:
                a = self.cfg.agents.get(s["agent"] or "")
                if not a or self.in_cooldown(s["agent"]) or schedule.quota_blocked(self.quota_items, a.binary, now):
                    continue
            elif not s.get("at") or s["at"] > now:
                continue
            nxt = schedule.next_hhmm(s["daily"], now) if s["kind"] == schedule.DAILY else None
            if not self.db.claim_schedule(s["id"], s.get("at"), nxt):
                continue
            changed = True
            self.log(tr("⏰ Tới lịch #{sid}: {text}", sid=s["id"], text=s["text"]))
            flow = s.get("flow") or self.cfg.default_workflow
            if flow and flow in self.cfg.workflows:
                res = self.run_workflow(flow, s["text"])
            elif self.cfg.agents.get(self.cfg.lead):
                res = self.new_goal(s["text"])
            else:
                res = tr("Không có trưởng nhóm '{lead}' trong cấu hình", lead=self.cfg.lead)
            if isinstance(res, str):
                self.log(tr("✗ Lịch #{sid} không chạy được: {e}", sid=s["id"], e=res))
                continue
            self.db.update_schedule(s["id"], goal_id=res)
            g = self.db.goal(res)
            if g and g.status == "awaiting":  # workflow: bước nháp có ngay
                self.approve(res)
        return changed

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
            if all(t.status == CANCELLED for t in tasks):  # người dùng huỷ hết: khỏi tốn một lượt review
                self.db.update_goal(g.id, status="cancelled", summary=tr("Mọi task đã bị huỷ"))
                self.log(tr("🏁 Mục tiêu #{id} kết thúc: mọi task đã bị huỷ.", id=g.id))
                changed = True
                continue
            wf = self.cfg.workflows.get(g.workflow or "")
            review = wf.review if wf and wf.review is not None else self.cfg.auto_review
            if review and not g.workflow and self.cfg.quality == "fast" and self._clean(tasks):
                self.db.update_goal(g.id, status="done", summary=tr("Mọi task xong và qua kiểm tra — bỏ review cuối "
                                                                   "(preset Nhanh)"))
                self.log(tr("🏁 Mục tiêu #{id} xong: mọi task qua kiểm tra, bỏ review cuối (preset Nhanh).", id=g.id))
            elif review:
                self.lead_busy.add(g.id)
                self._spawn(self._review(g.id))
            else:
                ok = all(t.status == DONE for t in tasks)
                self.db.update_goal(g.id, status="done" if ok else "incomplete")
                self.log(tr("🏁 Mục tiêu #{id} kết thúc ({v}).", id=g.id, v='xong' if ok else tr("còn task lỗi")))
            changed = True
        return changed

    async def run_forever(self, interval: float = 0.7) -> None:
        while True:
            try:
                self.tick()
            except Exception as e:  # không để vòng lặp chết
                self.log(tr("Lỗi bộ lập lịch: {e!r}", e=e))
            await asyncio.sleep(interval)

    async def run_until_idle(self, interval: float = 0.5) -> None:
        while True:
            self.tick()
            await asyncio.sleep(interval)
            if self.is_idle():
                self.tick()
                await asyncio.sleep(interval)
                if self.is_idle():
                    if self._usage_jobs:  # lệnh `ateam goal`… thoát ngay sau đó: ghi xong token/cost đã
                        await asyncio.gather(*list(self._usage_jobs), return_exceptions=True)
                    return

    # ------------------------------------------------------------------ hạn mức
    def in_cooldown(self, agent: str) -> bool:
        until = self.cooldown.get(agent)
        if until and until > time.time():
            return True
        if until:
            self.cooldown.pop(agent, None)
            limits.save_cooldown(agent, None)
            self.log(tr("▶ {agent} đã hồi hạn mức.", agent=agent))
        return False

    def cooldown_label(self, agent: str) -> str:
        until = self.cooldown.get(agent)
        return time.strftime("%H:%M %d/%m", time.localtime(until)) if until else "-"

    def _set_cooldown(self, agent: str, output: str, overloaded: bool = False) -> None:
        """overloaded: máy chủ quá tải (lỗi tạm thời) — nghỉ vài phút thay vì cooldown_minutes."""
        until = limits.reset_time(output, limits.OVERLOAD_MINUTES if overloaded else self.cfg.cooldown_minutes)
        self.cooldown[agent] = until
        limits.save_cooldown(agent, until)
        self.log(tr("⏸ {agent} đang quá tải — tạm nghỉ đến {v} rồi thử lại.", agent=agent, v=self.cooldown_label(agent))
                 if overloaded else
                 tr("⏸ {agent} hết hạn mức — tạm nghỉ đến {v}.", agent=agent, v=self.cooldown_label(agent)))
        self.emit("changed")

    def set_cooldown_manual(self, agent: str, minutes: int | None) -> str:
        if agent not in self.cfg.agents:
            return tr("Không có agent '{agent}'", agent=agent)
        if not minutes:
            self.cooldown.pop(agent, None)
            limits.save_cooldown(agent, None)
            self.log(tr("▶ Bỏ tạm nghỉ cho {agent}.", agent=agent))
            self.emit("changed")
            return tr("{agent} hoạt động lại", agent=agent)
        until = time.time() + minutes * 60
        self.cooldown[agent] = until
        limits.save_cooldown(agent, until)
        self.log(tr("⏸ {agent} tạm nghỉ đến {v} (đặt tay).", agent=agent, v=self.cooldown_label(agent)))
        self.emit("changed")
        return tr("{agent} tạm nghỉ {minutes} phút", agent=agent, minutes=minutes)

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
        if limits.looks_overloaded(run.output, rc):
            return "overloaded"
        if rc != 0 and BAD_FLAG_RE.search(run.output):
            return "badflag"
        if DENIED_RE.search(run.output):
            return "denied"
        if rc != 0 and not SUMMARY_LINE_RE.search(run.output[-6000:]):
            return "failed"
        if not run.output.strip():
            return "empty"
        return "ok"

    # ------------------------------------------------------------------ chạy 1 task
    async def _run_agent(self, t: Task, a: AgentConfig, prompt: str, workdir: Path, log_file,
                         *, kind: str, title: str, model: str | None,
                         effort: str | None, session: str | None = None,
                         full_prompt: str | None = None) -> tuple[Run, int, str]:
        """Chạy agent một lượt cho task t, ghi log, thống kê; trả (run, mã thoát, phân loại).
        session: tiếp tục phiên CLI này (prompt là bản ngắn); CLI báo mất phiên thì chạy lại với
        full_prompt trong phiên mới. Phiên của lượt (agent của task) được lưu vào task để lần sau dùng lại."""
        await self.prepare_agent(a)
        label = a.label(model, effort)
        own = a.name == t.agent and a.can_resume()
        resume = bool(session and own)
        if not resume:
            session = self.new_session(a) if own else None
        first_argv = self.argv_for(a, prompt, workdir, model=model, effort=effort, session=session, resume=resume)
        act = self._begin_activity(a.name, t.id, title, label)
        log_file.write(f"\n$ {a.name} · {kind} · {label} · {workdir}"
                       + (tr(" · tiếp tục phiên {s}", s=session[:8]) if resume else "") + "\n")
        rid = self.db.add_run(t.id, a.name, kind, len(prompt), goal_id=t.goal_id, cwd=str(workdir),
                              model=a.split_effort((model or a.model) or "", (effort or a.effort) or "")[0])

        def on_line(line: str) -> None:
            log_file.write(line + "\n")
            log_file.flush()
            self._touch(act, line)
            self.emit("log", task_id=t.id, agent=a.name, line=line)

        def make(argv=None) -> Run:
            r = Run(argv if argv is not None else
                    self.argv_for(a, prompt, workdir, model=model, effort=effort, session=session,
                                  resume=resume), str(workdir),
                    self.env_for(t), use_pty=a.pty, timeout=a.timeout, on_line=on_line)
            self.runs[t.id] = r
            return r
        run = make(first_argv)
        rc = 130
        try:
            if t.id in self._cancel_req:
                self._cancel_req.discard(t.id)
                run.cancelled = True
            else:
                rc = await run.start()
                if resume and not run.cancelled and full_prompt and (run.session_lost or (
                        rc != 0 and SESSION_LOST_RE.search(run.output[-3000:]))):
                    on_line(tr("↻ không tiếp tục được phiên cũ — chạy lại với đầy đủ ngữ cảnh"))
                    prompt, resume, session = full_prompt, False, self.new_session(a)
                    run = make()
                    rc = await run.start()
                if self.effort_rejected(a, model, effort, run, rc):
                    on_line(tr("↻ chạy lại không kèm effort: {label}", label=a.label(model, effort)))
                    run = make()
                    rc = await run.start()
        finally:
            res = self._classify(run, rc)
            self.db.finish_run(rid, rc, res, len(run.output))
            if own:
                session = self.session_of(a, run, session)
                self.db.update_task(t.id, session=session, session_agent=a.name if session else None)
            self._usage_job(rid, a, prompt, session, run.usage)
            act["status"] = {"ok": DONE, "cancelled": CANCELLED}.get(res, FAILED)
            self._end_activity(a.name, act)
        return run, rc, res

    async def _verify(self, t: Task, workdir: Path, log_file) -> tuple[bool, int, str]:
        cmd = self.cfg.verify.command
        act = self._begin_activity(t.agent, t.id, tr("kiểm tra: {cmd}", cmd=cmd), "test")
        log_file.write(tr("\n$ [kiểm tra] {cmd}\n", cmd=cmd))
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
            tail += tr("\n(Lệnh kiểm tra quá {timeout}s)", timeout=self.cfg.verify.timeout)
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

    @staticmethod
    def _check_for(t: Task, tasks: list[Task], pending: bool = False) -> Task | None:
        """Task kiểm tra cuối (cùng mục tiêu) phụ thuộc bắc cầu vào t — pending: chỉ task chưa chạy (draft/queued),
        không thì mọi task chưa bị huỷ. tasks: các task của mục tiêu."""
        by_id = {o.id: o for o in tasks}
        for c in tasks:
            if c.kind != KIND_VERIFY or c.id == t.id or c.status == CANCELLED \
                    or (pending and c.status not in (DRAFT, QUEUED)):
                continue
            seen, stack = set(), list(c.depends_on)
            while stack:
                d = stack.pop()
                if d == t.id:
                    return c
                if d not in seen and d in by_id:
                    seen.add(d)
                    stack.extend(by_id[d].depends_on)
        return None

    @staticmethod
    def _diff_hint(deps: list[Task]) -> str:
        """Cách xem thay đổi của các task được review: worktree → base..head của từng task (đã merge vào HEAD nên
        `git diff HEAD` không còn thấy); shared → thay đổi chưa commit của thư mục."""
        ranges = [f"`git diff {d.base[:12]} {d.head[:12]}` for #{d.id}" for d in deps
                  if d.base and d.head and d.base != d.head]
        return ", ".join(ranges) if ranges else "`git diff HEAD`; new files: `git status`"

    async def _run_task(self, tid: int) -> None:
        t = self.db.task(tid)
        if not t:  # bị xoá giữa lúc chiếm chỗ và chạy
            self.runs.pop(tid, None)
            return
        log_file = None
        status, error, summary = FAILED, None, None
        workdir = self.root
        outputs: list[str] = []
        new_agent: str | None = None
        v = self.cfg.verify
        qa = list((t.ask or {}).get("qa") or [])
        can_ask = len(qa) < MAX_ASKS
        asked: dict | None = None  # câu <<<ASK>>> của lượt này
        parked = False
        # tiếp tục phiên CLI cũ (cùng agent) khi có lý do chạy lại: /retry, góp ý, trả lời câu hỏi, /continue
        sess = t.session if t.resume and t.session and t.session_agent == t.agent else None
        try:
            agent = self.cfg.agents[t.agent]
            goal = self.db.goal(t.goal_id) if t.goal_id else None
            log_file = open(self.log_path(tid), "w", encoding="utf-8")
            if t.resume:
                self.db.update_task(tid, resume=None)
            chat = t.source == CHAT
            check = t.kind == KIND_VERIFY  # kiểm tra cuối: ateam chạy lệnh kiểm tra trước, fail mới gọi agent sửa
            if chat:
                can_ask = False  # như gõ trong CLI: agent hỏi lại thì người dùng nhắn tiếp
            elif self.use_worktree:
                workdir = await self._wt_prepare(t)
            # bước ⏸ duyệt không có kết quả để bàn giao: bước sau nhận kết quả của các bước mà bước duyệt chờ
            dep_tasks = self._through_gates(t.depends_on)
            deps = [(dt.id, dt.agent, dt.title, dt.result or "") for dt in dep_tasks]
            goal_tasks = self.db.tasks(goal_id=t.goal_id) if t.goal_id else []
            handoff = any(t.id in o.depends_on for o in goal_tasks)  # có task chờ kết quả của task này
            if check:
                full = ""
            elif t.source == "user" or (chat and not t.parent_id):  # /task, chat: gửi nguyên văn, không bọc vai trò/luật
                full = t.prompt + P.qa_text(qa)
            elif (t.source == "followup" and t.goal_id is None) or chat:  # hỏi tiếp thread /task hoặc chat
                full = P.thread_prompt(self.thread_of(t), t.prompt) + P.qa_text(qa)
            else:
                full = P.task_prompt(
                    self.cfg, agent=t.agent, task_id=t.id, title=t.title, prompt=t.prompt,
                    goal=goal.full_text() if goal else None, deps=deps, notes=self.notes_text(),
                    cwd=str(workdir), can_delegate=t.depth < self.cfg.max_delegation_depth,
                    qa=qa, can_ask=can_ask,
                    siblings=[(o.id, o.agent, o.title) for o in goal_tasks
                              if o.id != t.id and o.status != CANCELLED] if t.goal_id else None,
                    verify_cmd=v.command if v.command and agent.verify else "",
                    # chỉ trưởng nhóm đọc bản tổng quan; thành viên nhận phần cần thiết qua prompt của task (đỡ ~3K
                    # token mỗi task) — bước workflow do trưởng nhóm làm (thiết kế) bàn giao lại qua SUMMARY
                    overview=await self.overview_block() if t.agent == self.cfg.lead else "", kind=t.kind or KIND_CODE,
                    diff=self._diff_hint(dep_tasks) if t.kind == KIND_REVIEW else "", handoff=handoff)
            prompt = t.resume if sess else full
            if full or sess:  # skill gắn với task (trưởng nhóm / $tên trong mục tiêu) + $tên trong prompt / tin nhắn
                cat = skills.scan(self.root) if t.skills or "$" in t.prompt + (t.resume or "") else []
                use = skills.resolve(t.skills, cat)
                use += [s for s in skills.mentioned(t.prompt, cat) if s not in use]
                if full and use:
                    full = skills.body_block(use) + full
                    log_file.write("🧩 skills: " + ", ".join(s.name for s in use) + "\n")
                # tiếp phiên (/retry, sửa lỗi, chat): phiên đã có skill của prompt đầy đủ — chỉ thêm $tên của lượt này
                again = skills.mentioned(t.resume or "", cat) if sess else []
                if again:
                    log_file.write("🧩 skills: " + ", ".join(s.name for s in again) + "\n")
                prompt = (skills.body_block(again) + t.resume) if sess else full
            gate = bool(v.command) and (agent.verify or check) and not chat
            # có kiểm tra cuối phía sau: nó chạy một lần trên kết quả gộp thay cho kiểm tra riêng — shared thì task song
            # song đang sửa dở cùng thư mục làm lệnh fail giả; cả hai chế độ đỡ N lần chạy test (tốc độ như bản cũ)
            cover = self._check_for(t, goal_tasks, pending=True) if gate and not check else None
            if cover:
                gate = False
            before = await self._fingerprint(workdir) if gate and v.only_when_changed and not check else None
            run = None
            if check:
                self.log(tr("▶ #{tid} kiểm tra cuối: {cmd}", tid=tid, cmd=v.command or "—"))
                status, error = DONE, None
            else:
                self.log(f"▶ #{tid} {t.agent}: {t.title}")
                run, rc, res = await self._run_agent(t, agent, prompt, workdir, log_file, kind="task",
                                                     title=t.title, model=t.model, effort=t.effort,
                                                     session=sess, full_prompt=full)
                outputs.append(P.strip_echo(run.output, prompt, full))  # codex in lại prompt: bỏ khối mẫu trong đó
                status, error = self._status_of(res, rc, agent)
                if res in ("ratelimit", "overloaded"):  # quá tải: nghỉ vài phút rồi tự chạy lại (hoặc agent dự phòng)
                    self._set_cooldown(t.agent, run.output, overloaded=res == "overloaded")
                    if chat:  # chat là với đúng agent này: báo lỗi, không lặng lẽ chuyển người khác
                        status, error = self._status_of(res, rc, agent)
                    else:
                        new_agent = self.pick_fallback(t.agent)
                        status, error = QUEUED, None
            asked = P.parse_ask(outputs[-1]) if outputs and status == DONE and can_ask else None
            if cover and status == DONE and not asked:
                log_file.write(tr("\n(bỏ kiểm tra riêng — kiểm tra cuối #{id} chạy trên kết quả gộp)\n", id=cover.id))

            # ---- cổng kiểm tra: chạy test, fail thì giao sửa
            attempts = 0
            while status == DONE and gate and not asked:
                if v.only_when_changed and before is not None:
                    if await self._fingerprint(workdir) == before:
                        log_file.write(tr("\n(không có thay đổi file nào — bỏ qua kiểm tra)\n"))
                        break
                ok, trc, tail = await self._verify(t, workdir, log_file)
                if ok:
                    self.log(tr("✅ #{tid} qua kiểm tra `{command}`", tid=tid, command=v.command)
                             + (tr(" sau {attempts} lần sửa", attempts=attempts) if attempts else ""))
                    break
                if (run is not None and run.cancelled) or tid in self._cancel_req:
                    status, error = CANCELLED, tr("Bị huỷ")
                    break
                if attempts >= v.max_fix_attempts:
                    status = FAILED
                    error = (tr("Kiểm tra `{command}` vẫn fail (mã {trc})", command=v.command, trc=trc)
                             + (tr(" sau {attempts} lần sửa", attempts=attempts) if attempts else "") + tr(" — xem log [test]"))
                    break
                attempts += 1
                self.db.update_task(tid, attempts=attempts)
                fixer = v.fix_agent if v.fix_agent in self.cfg.active_agents() else t.agent
                if self.in_cooldown(fixer):
                    fixer = self.pick_fallback(fixer) or fixer
                fa = self.cfg.agents[fixer]
                self.log(tr("🔧 #{tid} test fail (mã {trc}) — {fixer} sửa lần "
                            "{attempts}/{max_fix_attempts}", tid=tid, trc=trc, fixer=fixer, attempts=attempts, max_fix_attempts=v.max_fix_attempts))
                if check:
                    fprompt = P.check_fix_prompt(
                        agent=fixer, task_id=tid, goal=goal.full_text() if goal else None,
                        note=t.prompt if t.prompt != t.title else "",
                        tasks=[(d.id, d.agent, d.title) for d in dep_tasks], command=v.command, rc=trc,
                        output=tail, attempt=attempts, max_attempts=v.max_fix_attempts, cwd=str(workdir))
                else:
                    fprompt = P.fix_prompt(agent=fixer, task_id=tid, title=t.title, prompt=t.prompt,
                                           command=v.command, rc=trc, output=tail, attempt=attempts,
                                           max_attempts=v.max_fix_attempts, cwd=str(workdir),
                                           original_agent=t.agent)
                same = fixer == t.agent
                fsess = None
                if same:  # agent của task tự sửa: tiếp tục phiên vừa làm, chỉ gửi lỗi
                    cur = self.db.task(tid)
                    fsess = cur.session if cur and cur.session_agent == fixer else None
                sent = P.fix_resume_prompt(command=v.command, rc=trc, output=tail, attempt=attempts,
                                           max_attempts=v.max_fix_attempts) if fsess else fprompt
                if check:  # lệnh kiểm tra chạy không cần agent; sửa thì phải chờ agent sửa rảnh (max_concurrent)
                    await self._wait_agent_free(fixer, tid)
                    self._checking.discard(tid)
                run, rc, res = await self._run_agent(
                    t, fa, sent, workdir, log_file, kind="fix",
                    title=tr("sửa lỗi test #{tid} ({attempts}/{max_fix_attempts})", tid=tid, attempts=attempts, max_fix_attempts=v.max_fix_attempts),
                    model=t.model if same else None, effort=t.effort if same else None,
                    session=fsess, full_prompt=fprompt)
                if check:
                    self._checking.add(tid)
                outputs.append(P.strip_echo(run.output, sent, fprompt))
                if res in ("ratelimit", "overloaded"):
                    self._set_cooldown(fixer, run.output, overloaded=res == "overloaded")
                    status, error = FAILED, (tr("{fixer} quá tải khi đang sửa lỗi test — /retry sau", fixer=fixer)
                                             if res == "overloaded" else
                                             tr("{fixer} hết hạn mức khi đang sửa lỗi test — /retry sau", fixer=fixer))
                    break
                status, error = self._status_of(res, rc, fa)

            if check:
                summary = (tr("Chưa đặt lệnh kiểm tra (/verify) — bỏ qua kiểm tra cuối") if not v.command else
                           (tr("✅ `{cmd}` qua trên kết quả gộp", cmd=v.command)
                            + (tr(" sau {n} lần sửa: {v}", n=len(outputs), v=P.extract_summary(outputs[-1])[:600])
                               if outputs else "")) if status == DONE else None)
            else:
                summary = (P.extract_summary(outputs[0], CHAT_REPLY_MAX if chat else
                                             HANDOFF_MAX if handoff else 2500)) if outputs else None
                if len(outputs) > 1 and status == DONE:
                    summary = (summary or "") + tr("\n(Đã sửa để qua kiểm tra: {v})",
                                                   v=P.extract_summary(outputs[-1])[:600])
            for out in outputs:
                for n in P.parse_notes(out):
                    self.db.add_note(t.agent, n)

            if asked:  # agent hỏi người dùng: giữ phần đã làm (nhánh worktree), chờ trả lời
                if self.use_worktree:
                    await self._wt_park(t, workdir)
                    parked = True
            elif self.use_worktree and not chat:
                status, error = await self._wt_finish(t, workdir, status, error)
            if status == DONE and not asked and not chat and not check:
                self._delegations(t, "\n".join(outputs))
        except mentions.AttachmentError as e:
            status, error = FAILED, str(e)
            if self.use_worktree and workdir != self.root:
                status, error = await self._wt_finish(t, workdir, status, error)
        except Exception as e:
            status, error = FAILED, tr("Lỗi nội bộ: {e!r}", e=e)
        finally:
            if log_file:
                log_file.close()
            self.runs.pop(tid, None)
            self._cancel_req.discard(tid)  # yêu cầu huỷ của lượt này không được ảnh hưởng lượt /retry sau
            self._checking.discard(tid)
            if asked and status == DONE:
                qa.append(dict(asked, a=None))
                if self.auto_answer:  # không ai trả lời (ateam goal -y / run): theo đề xuất của agent
                    qa[-1]["a"] = asked["rec"] or P.SKIP_ANSWER
                    self.db.update_task(tid, status=QUEUED, ask={"qa": qa, "parked": parked}, started=None,
                                        error=None, resume=P.answer_prompt(asked["q"], qa[-1]["a"],
                                                                            len(qa) < MAX_ASKS))
                    self.log(tr("❓ #{tid} {agent} hỏi: {q} — tự trả lời: {a}", tid=tid, agent=t.agent,
                                q=asked["q"], a=qa[-1]["a"]))
                else:
                    self.db.update_task(tid, status=ASKING, ask={"qa": qa, "parked": parked}, error=None,
                                        result=None)
                    self.log(tr("❓ #{tid} {agent} hỏi bạn: {q}", tid=tid, agent=t.agent, q=asked["q"]))
            elif status == QUEUED and self._requeues.get(tid, 0) >= MAX_REQUEUES:
                # lỗi lặp lại mà khớp mẫu hết hạn mức / quá tải (quota tài khoản hết hẳn, cấu hình sai trả 503…):
                # không xếp lại mãi — mỗi lượt vẫn tốn thời gian (và token)
                self._requeues.pop(tid, None)
                error = tr("{agent} hết hạn mức / quá tải lặp lại {n} lần liên tiếp — /retry sau", agent=t.agent,
                           n=MAX_REQUEUES + 1)
                self.db.update_task(tid, status=FAILED, error=error, finished=time.time())
                self.log(f"✗ #{tid} {t.agent}: {FAILED} — {error}")
            elif status == QUEUED:  # hết hạn mức: xếp hàng lại, có thể đổi agent
                self._requeues[tid] = self._requeues.get(tid, 0) + 1
                fields = {"status": QUEUED, "started": None, "error": None}
                if new_agent:
                    fields.update(agent=new_agent, model=None, effort=None)
                self.db.update_task(tid, **fields)
                self.log(tr("↪ #{tid} xếp hàng lại", tid=tid) + (tr(", chuyển sang {new_agent}", new_agent=new_agent) if new_agent
                                                     else tr(", chờ {agent} hết quá tải", agent=t.agent) if res == "overloaded"
                                                     else tr(", chờ {agent} hồi hạn mức", agent=t.agent)))
            else:
                self._requeues.pop(tid, None)
                self.db.update_task(tid, status=status, error=error, result=summary,
                                    finished=time.time())
                icon = {DONE: "✓", CANCELLED: "■", CONFLICT: "⚠", REVIEW: "👀"}.get(status, "✗")
                self.log(f"{icon} #{tid} {t.agent}: {status}" + (f" — {error}" if error else ""))
            self.emit("changed")

    def _status_of(self, res: str, rc: int, a: AgentConfig) -> tuple[str, str | None]:
        return {
            "ok": (DONE, None),
            "cancelled": (CANCELLED, tr("Bị huỷ")),
            "timeout": (FAILED, tr("Quá thời gian ({timeout}s)", timeout=a.timeout)),
            "failed": (FAILED, tr("Thoát với mã {rc}", rc=rc)),
            "badflag": (FAILED, tr("{binary} không nhận một cờ trong lệnh (CLI có thể đã đổi phiên "
                                   "bản) — chạy `ateam doctor` rồi sửa command trong cấu hình", binary=a.binary)),
            "empty": (FAILED, tr("Agent không in ra gì (kiểm tra đăng nhập / quyền / pty)")),
            "denied": (FAILED, tr("{name} bị chặn chạy lệnh (thiếu quyền) — bật Toàn quyền cho "
                                  "agent này ở /setup (agent có sẵn) hoặc /custom (agent tuỳ "
                                  "chỉnh), rồi /retry", name=a.name)),
            "ratelimit": (FAILED, tr("{name} hết hạn mức", name=a.name)),
            "overloaded": (FAILED, tr("{name} đang quá tải (máy chủ bận) — thử lại sau ít phút", name=a.name)),
        }[res]

    def _delegations(self, t: Task, output: str) -> None:
        dels = P.parse_delegations(output)
        if not dels:
            return
        if t.depth >= self.cfg.max_delegation_depth:
            self.log(tr("⚠ #{id} muốn giao việc nhưng đã chạm giới hạn {max_delegation_depth} tầng.", id=t.id, max_delegation_depth=self.cfg.max_delegation_depth))
            return
        agents = self.cfg.active_agents()
        made = []
        for to, title, body in dels[:MAX_DELEGATIONS_PER_TASK]:
            if to not in agents:
                self.log(tr("⚠ #{id} giao việc cho '{to}' — không có trong đội, bỏ qua.", id=t.id, to=to))
                continue
            nid = self.db.add_task(to, title or body[:60], body, goal_id=t.goal_id,
                                   parent_id=t.id, depth=t.depth + 1,
                                   status=QUEUED, source=f"delegate:{t.agent}")
            made.append(nid)
            self.log(tr("🤝 {agent} giao task #{nid} cho {to}: {title}", agent=t.agent, nid=nid, to=to,
                        title=title or body[:60]))
        if made and t.goal_id:  # kiểm tra cuối chưa chạy chờ cả việc vừa giao (vd reviewer giao sửa cho tác giả)
            for c in self.db.tasks(goal_id=t.goal_id, status=(DRAFT, QUEUED)):
                if c.kind == KIND_VERIFY and t.id in c.depends_on:
                    self.db.update_task(c.id, depends_on=c.depends_on + made)

    # ------------------------------------------------------------------ review
    async def _review(self, gid: int) -> None:
        try:
            g = self.db.goal(gid)
            self.db.update_goal(gid, status="reviewing")
            self.emit("changed")
            self.log(tr("🔍 {lead} đang review mục tiêu #{gid} (vòng {round})…", lead=self.cfg.lead, gid=gid, round=g.round))
            # tiếp tục phiên lập kế hoạch: trưởng nhóm đã đọc code lúc đó, không phải khám phá lại dự án; mục tiêu
            # không có phiên đó (chạy theo workflow) thì gửi kèm bản tổng quan dự án
            ov = "" if self._lead_session(g) else await self.overview_block()
            out = await self._call_lead(
                P.review_prompt(self.cfg, g.full_text(), g.round, self._results_text(gid), str(self.root),
                                final=g.round >= self.cfg.max_rounds, overview=ov),
                tr("Review mục tiêu #{gid} vòng {round}", gid=gid, round=g.round), goal_id=gid,
                keep_session=True)
            if out is not None:
                self._overview_seen(gid, ov)
            data = P.extract_json(out or "", dict, keys=("done", "summary", "new_tasks"))
            if not data:
                self.db.update_goal(gid, status="incomplete",
                                    summary=tr("Không đọc được kết quả review (xem .ateam/logs/lead.log)"))
                self.log(tr("⚠ Không đọc được review của mục tiêu #{gid}.", gid=gid))
                return
            summary = str(data.get("summary", "")).strip()
            new = data.get("new_tasks") or []
            if data.get("done") or not new:
                self.db.update_goal(gid, status="done" if data.get("done") else "incomplete",
                                    summary=summary)
                self.log(tr("🏁 Mục tiêu #{gid} {v}: {summary}", gid=gid, v=tr("HOÀN THÀNH") if data.get('done') else tr("kết thúc"), summary=summary))
            elif g.round >= self.cfg.max_rounds:
                self.db.update_goal(gid, status="incomplete", summary=summary)
                self.log(tr("🏁 Mục tiêu #{gid} đã hết {max_rounds} vòng. Đánh giá: {summary}", gid=gid, max_rounds=self.cfg.max_rounds, summary=summary))
            else:
                self.db.update_goal(gid, round=g.round + 1, summary=summary,
                                    status="awaiting" if self.cfg.approve_plan else "running")
                self.log(f"🔁 Review #{gid}: {summary}")
                text = g.full_text()  # $tên trong mục tiêu: task review thêm vào cũng nhận skill đó
                ids = self._insert_plan(gid, new, source="review", asked=[
                    x.name for x in skills.mentioned(text, skills.scan(self.root))] if "$" in text else None)
                if self.cfg.approve_plan:
                    self.log(tr("📋 {v} task bổ sung đang ở trạng thái NHÁP — /go {gid} để chạy.", v=len(ids), gid=gid))
        except Exception as e:  # không để mục tiêu kẹt ở "reviewing"
            self.db.update_goal(gid, status="incomplete", summary=tr("Lỗi khi review: {e!r}", e=e))
            self.log(tr("✗ Review mục tiêu #{gid} lỗi: {e!r}", gid=gid, e=e))
        finally:
            self.lead_busy.discard(gid)
            self.emit("changed")

    def _results_text(self, gid: int) -> str:
        """Kết quả các task của mục tiêu, gửi trưởng nhóm khi review / lập kế hoạch tiếp."""
        lines = []
        cmd = self.cfg.verify.command
        tasks = self.db.tasks(goal_id=gid)
        for t in tasks:
            if t.status == CANCELLED:
                continue
            body = (t.result or t.error or "")[:1500]
            a = self.cfg.agents.get(t.agent)
            chk = self._check_for(t, tasks) if t.kind != KIND_VERIFY else None
            if chk:  # task được kiểm tra cuối bao không chạy kiểm tra riêng: chỉ kết quả kiểm tra cuối là đúng
                body += f"\n(checked by final verify #{chk.id}: {chk.status})"
            elif cmd and t.status == DONE and a and a.verify and t.kind != KIND_VERIFY:  # trưởng nhóm khỏi chạy lại
                body += f"\n(verification `{cmd}`: passed, or no file changes)"
            lines.append(f"#{t.id} [{t.agent}]{(' ' + t.kind) if t.kind else ''} {t.status}: {t.title}\n{body}\n")
        return "\n".join(lines)

    def _clean(self, tasks: list[Task]) -> bool:
        """Mục tiêu xong gọn — preset Nhanh bỏ review cuối: mọi task xong, có lệnh kiểm tra, mỗi task đã qua kiểm tra
        riêng hoặc được kiểm tra cuối bao, không có task review (kết quả review cần trưởng nhóm đọc)."""
        if not self.cfg.verify.command:
            return False
        for t in tasks:
            if t.status != DONE or t.kind == KIND_REVIEW:
                return False
            a = self.cfg.agents.get(t.agent)
            if t.kind != KIND_VERIFY and not (a and a.verify) and not self._check_for(t, tasks):
                return False
        return True

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

    # ---- ⌨ shell ở worktree của task (tab Terminal)
    async def task_shell_dir(self, tid: int) -> tuple[Path | None, str]:
        """Thư mục cho shell của task: worktree đang chạy, hoặc worktree riêng `sh-t{id}` mở trên nhánh của task
        (chờ duyệt / xung đột / lỗi) — phần sửa tay được commit vào nhánh trước khi merge."""
        t = self.db.task(tid)
        if not t:
            return None, tr("Không có task #{tid}", tid=tid)
        run_wt = self.state / "worktrees" / f"t{t.id}"
        if t.status == RUNNING and run_wt.is_dir():
            return run_wt, ""
        if not t.branch:
            return None, tr("Task #{tid} không có worktree hay nhánh riêng — mở shell thường ở thư mục dự án", tid=tid)
        path = self.shell_wt(tid)
        if path.is_dir():
            return path, ""
        await self._git("worktree", "prune")
        rc, out = await self._git("worktree", "add", str(path), t.branch)
        if rc != 0:
            return None, tr("git worktree add thất bại: {v}", v=out.strip()[:300])
        return path, ""

    def shell_wt(self, tid: int) -> Path:
        return self.state / "worktrees" / f"sh-t{tid}"

    async def _shell_wt_release(self, t: Task, keep: bool) -> str | None:
        """Đóng shell của task và gỡ worktree `sh-t{id}` (git không cho xoá / checkout lại nhánh đang mở ở worktree
        khác). keep: commit phần người dùng sửa tay vào nhánh trước; commit lỗi thì giữ worktree, trả lỗi."""
        if self.on_shell_release:
            self.on_shell_release(t.id)
        path = self.shell_wt(t.id)
        if not path.is_dir():
            return None
        if keep:
            err = await self._wt_commit(path, f"ateam #{t.id}: manual edits (shell)")
            if err:
                return err
        await self._git("worktree", "remove", "--force", str(path))
        return None

    async def _drop_branch(self, t: Task) -> None:
        await self._shell_wt_release(t, keep=False)
        await self._git("branch", "-D", t.branch)

    async def _wt_prepare(self, t: Task) -> Path:
        await self._shell_wt_release(t, keep=True)  # nhánh làm tiếp (trả lời câu hỏi) có cả phần sửa tay
        path = self.state / "worktrees" / f"t{t.id}"
        branch = f"ateam/t{t.id}"
        if path.exists():
            await self._git("worktree", "remove", "--force", str(path))
        await self._git("worktree", "prune")
        if (t.ask or {}).get("parked") and t.branch and t.base:
            # vừa trả lời câu hỏi <<<ASK>>>: làm tiếp trên nhánh đang dở, không tạo lại từ HEAD
            self.db.update_task(t.id, ask=dict(t.ask, parked=False))
            rc, out = await self._git("worktree", "add", str(path), t.branch)
            if rc == 0:
                self._wt_base[t.id] = t.base
                return path
            self.log(tr("⚠ #{id}: không mở lại được nhánh {branch} ({v}) — làm lại từ HEAD", id=t.id,
                        branch=t.branch, v=out.strip()[:200]))
        _, base = await self._git("rev-parse", "HEAD")
        self._wt_base[t.id] = base.strip()
        rc, out = await self._git("worktree", "add", "-B", branch, str(path), "HEAD")
        if rc != 0:
            raise RuntimeError(tr("git worktree add thất bại: {v}", v=out.strip()))
        self.db.update_task(t.id, branch=branch, base=base.strip(), head=None)
        return path

    async def _wt_commit(self, path: Path, msg: str) -> str | None:
        """Commit mọi thay đổi trong worktree. Bỏ hook (pre-commit/husky) và ký GPG: đây là commit nội bộ
        của nhánh task, không được để chúng chặn rồi mất việc. Trả lỗi (chuỗi) nếu commit không được."""
        await self._git("add", "-A", cwd=path)
        _, st = await self._git("status", "--porcelain", cwd=path)
        if not st.strip():
            return None
        rc, out = await self._git(*(await self.git_ident()), "-c", "commit.gpgsign=false", "commit", "-q",
                                  "--no-verify", "-m", msg, cwd=path)
        if rc != 0:
            return tr("Không commit được thay đổi trong worktree {path} (giữ nguyên để bạn lấy lại): {v}",
                      path=path, v=out.strip()[:300])
        return None

    async def _wt_park(self, t: Task, path: Path) -> None:
        """Task dừng giữa chừng (agent hỏi người dùng): commit phần đã làm vào nhánh, gỡ worktree."""
        err = await self._wt_commit(path, f"ateam #{t.id} ({t.agent}): {t.title} (WIP)")
        if err:
            raise RuntimeError(err)
        await self._git("worktree", "remove", "--force", str(path))
        self._wt_base.pop(t.id, None)

    async def _wt_finish(self, t: Task, path: Path, status: str,
                         error: str | None) -> tuple[str, str | None]:
        """Commit thay đổi của task; tự merge (merge=auto) hoặc để chờ duyệt (merge=review)."""
        branch = f"ateam/t{t.id}"
        err = await self._wt_commit(path, f"ateam #{t.id} ({t.agent}): {t.title}")
        if err:
            self.log("⚠ " + err)
            return FAILED, err
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
            self.log(tr("👀 #{id} chờ duyệt merge — /diff {id} để xem, /merge {id} hoặc /reject {id}", id=t.id))
            return REVIEW, None
        ok, msg = await self._merge_branch(t)
        if ok:
            return DONE, None
        return CONFLICT, msg

    async def _merge_branch(self, t: Task) -> tuple[bool, str | None]:
        branch = f"ateam/t{t.id}"
        err = await self._shell_wt_release(t, keep=True)  # phần bạn sửa tay trong ⌨ shell của task vào cùng merge
        if err:
            return False, err
        async with self._merge_lock():
            if (await self._git("rev-parse", "-q", "--verify", "MERGE_HEAD"))[0] == 0:
                # người dùng đang merge dở (tab Git): không merge chồng, càng không được --abort phần của họ
                return False, tr("Thư mục chính đang merge dở — hoàn tất hoặc huỷ merge đó rồi /merge {id}",
                                 id=t.id)
            rc, out = await self._git(*(await self.git_ident()), "merge", "--no-ff", "--no-edit", "-m",
                                      f"ateam: merge #{t.id} ({t.agent}) {t.title}", branch)
            if rc != 0:
                await self._git("merge", "--abort")
                self.log(tr("⚠ Merge #{id} lỗi: {v}", id=t.id, v=out.strip()[:300]))
                return False, (tr("Không merge được nhánh {branch} (xung đột hoặc thư mục chính "
                                  "đang có thay đổi) — tự merge tay, /merge {id} để thử lại, hoặc "
                                  "/retry", branch=branch, id=t.id))
        await self._git("branch", "-D", branch)
        return True, None

    # ------------------------------------------------------------------ duyệt merge
    async def merge(self, tid: int) -> str:
        t = self.db.task(tid)
        if not t:
            return tr("Không có task #{tid}", tid=tid)
        if t.status not in (REVIEW, CONFLICT) or not t.branch:
            return tr("Task #{tid} không có nhánh chờ merge ({status})", tid=tid, status=t.status)
        ok, msg = await self._merge_branch(t)
        if not ok:
            self.db.update_task(tid, status=CONFLICT, error=msg)
            self.emit("changed")
            return tr("Merge #{tid} thất bại — xem log hệ thống", tid=tid)
        self.db.update_task(tid, status=DONE, error=None, branch=None, finished=time.time())
        self.log(tr("✓ Đã merge #{tid} ({agent}): {title}", tid=tid, agent=t.agent, title=t.title))
        try:
            self._delegations(t, self.log_path(tid).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
        self.emit("changed")
        return tr("Đã merge #{tid}", tid=tid)

    async def reject(self, tid: int, feedback: str | None) -> str:
        t = self.db.task(tid)
        if not t:
            return tr("Không có task #{tid}", tid=tid)
        if t.status not in (REVIEW, CONFLICT):
            return tr("Task #{tid} không ở trạng thái chờ duyệt ({status})", tid=tid, status=t.status)
        if t.branch:
            await self._drop_branch(t)
        if feedback:
            prompt = (t.prompt + f"\n\nREVIEWER FEEDBACK (previous attempt was rejected — address this):"
                      f"\n{feedback}")
            self.db.update_task(tid, status=QUEUED, prompt=prompt, branch=None, head=None,
                                error=None, result=None, started=None, finished=None,
                                resume=P.feedback_prompt(feedback, self.use_worktree) if t.session else None)
            self.log(tr("↩ Từ chối #{tid}, giao làm lại kèm góp ý: {feedback}", tid=tid, feedback=feedback))
            msg = tr("Đã giao làm lại #{tid} kèm góp ý", tid=tid)
        else:
            self.db.update_task(tid, status=CANCELLED, branch=None, error=tr("Bị từ chối khi duyệt"),
                                finished=time.time())
            self.log(tr("✗ Từ chối và huỷ #{tid}", tid=tid))
            msg = tr("Đã huỷ #{tid}", tid=tid)
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
            return tr("Không có task #{tid}", tid=tid)
        git = ("-c", "core.quotePath=false", "diff", "-M", "--no-color")
        if t.base and (t.head or t.branch):
            head = t.head or t.branch
            rc, body = await self._git(*git, t.base, head)
            if rc != 0:
                return tr("Không lấy được diff của task #{tid}: {v}", tid=tid, v=body.strip()[:200])
            files = parse_unified(body)
            if not files:
                return tr("Task #{tid} không thay đổi file nào.", tid=tid)
            return DiffSet(tid, f"Diff #{tid} · {t.base[:8]}..{head[:12]}", files, t.base, head)
        rc, body = await self._git(*git, "HEAD")
        if rc != 0:
            return tr("Thư mục này không phải git repo (hoặc chưa có commit nào) — không xem được "
                      "diff.")
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
            return tr("Không có thay đổi nào chưa commit.")
        return DiffSet(tid, tr("Thay đổi chưa commit của thư mục (chế độ shared, không tách theo "
                               "task #{tid})", tid=tid),
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
            return tr("Không có task #{tid}", tid=tid)
        if t.base and (t.head or t.branch):
            head = t.head or t.branch
            _, stat = await self._git("diff", "--stat", t.base, head)
            _, body = await self._git("diff", t.base, head)
            if not body.strip():
                return tr("Task #{tid} không thay đổi file nào.", tid=tid)
            return f"Diff #{tid} ({t.base[:8]}..{head[:12]}):\n{stat}\n{body}"
        rc, stat = await self._git("diff", "HEAD", "--stat")
        if rc != 0:
            return tr("Thư mục này không phải git repo — không xem được diff.")
        _, body = await self._git("diff", "HEAD")
        return (tr("(Chế độ shared không tách được diff theo từng task — đây là mọi thay đổi chưa "
                   "commit của thư mục)\n") + (stat + "\n" + body if body.strip() else tr("Không có thay đổi nào.")))
