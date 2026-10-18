"""Bảng việc chung (SQLite) — TUI, CLI và các agent cùng đọc/ghi."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planning',
    round INTEGER NOT NULL DEFAULT 1,
    summary TEXT,
    created REAL,
    workflow TEXT,
    followups TEXT,
    grill TEXT,
    lead_session TEXT,
    lead_session_agent TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER,
    parent_id INTEGER,
    agent TEXT NOT NULL,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    depends_on TEXT NOT NULL DEFAULT '[]',
    depth INTEGER NOT NULL DEFAULT 0,
    source TEXT,
    result TEXT,
    error TEXT,
    branch TEXT,
    created REAL,
    started REAL,
    finished REAL,
    model TEXT,
    effort TEXT,
    base TEXT,
    head TEXT,
    attempts INTEGER,
    session TEXT,
    session_agent TEXT,
    resume TEXT,
    ask TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    agent TEXT NOT NULL,
    kind TEXT NOT NULL,
    started REAL,
    finished REAL,
    rc INTEGER,
    status TEXT,
    prompt_chars INTEGER,
    output_chars INTEGER,
    goal_id INTEGER,
    model TEXT,
    cwd TEXT,
    in_tok INTEGER,
    out_tok INTEGER,
    cache_read INTEGER,
    cache_write INTEGER,
    cost REAL,
    tok_src TEXT
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author TEXT,
    text TEXT NOT NULL,
    created REAL
);
"""

# cột thêm sau vào bảng runs (DB cũ được ALTER TABLE khi mở)
RUN_USAGE_COLS = (("goal_id", "INTEGER"), ("model", "TEXT"), ("cwd", "TEXT"), ("in_tok", "INTEGER"),
                  ("out_tok", "INTEGER"), ("cache_read", "INTEGER"), ("cache_write", "INTEGER"),
                  ("cost", "REAL"), ("tok_src", "TEXT"))
# token của một lượt: số thật đọc từ log phiên của CLI, chưa có thì ước tính ~4 ký tự/token
TOKENS_SQL = ("COALESCE(in_tok + out_tok + COALESCE(cache_read, 0) + COALESCE(cache_write, 0),"
              " (COALESCE(prompt_chars, 0) + COALESCE(output_chars, 0)) / 4)")

# tác giả của ghi chú tóm tắt do /compact tạo
COMPACT_AUTHOR = "compact"

# trạng thái task
DRAFT, QUEUED, RUNNING, DONE, FAILED, CANCELLED, BLOCKED, CONFLICT, REVIEW = (
    "draft", "queued", "running", "done", "failed", "cancelled", "blocked", "conflict", "review",
)
ASKING = "asking"  # agent hỏi người dùng giữa task (<<<ASK>>>), chờ trả lời
ACTIVE = (DRAFT, QUEUED, RUNNING, REVIEW, ASKING)
FINISHED_BAD = (FAILED, CANCELLED, BLOCKED)
# trạng thái mục tiêu đã kết thúc (không còn lập kế hoạch / chạy / review nữa)
GOAL_ENDED = ("done", "incomplete", "failed", "cancelled")


@dataclass
class Task:
    id: int
    goal_id: int | None
    parent_id: int | None
    agent: str
    title: str
    prompt: str
    status: str
    depends_on: list[int]
    depth: int
    source: str | None
    result: str | None
    error: str | None
    branch: str | None
    created: float | None
    started: float | None
    finished: float | None
    model: str | None = None
    effort: str | None = None
    base: str | None = None
    head: str | None = None
    attempts: int | None = None
    session: str | None = None        # id phiên CLI của lượt gần nhất (để --resume)
    session_agent: str | None = None  # agent sở hữu phiên đó (đổi agent → không dùng lại)
    resume: str | None = None         # prompt ngắn gửi khi tiếp tục phiên (lý do chạy lại / câu trả lời)
    # <<<ASK>>>: {"qa": [{"q", "why", "options", "rec", "a"}]} — câu hỏi của agent và câu trả lời
    ask: dict | None = None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Task":
        d = dict(r)
        d["depends_on"] = json.loads(d.get("depends_on") or "[]")
        d["ask"] = json.loads(d["ask"]) if d.get("ask") else None
        return cls(**d)

    def question(self) -> dict | None:
        """Câu hỏi đang chờ trả lời (task ở trạng thái asking)."""
        qa = (self.ask or {}).get("qa") or []
        return qa[-1] if qa and qa[-1].get("a") is None else None


@dataclass
class Goal:
    id: int
    text: str
    status: str
    round: int
    summary: str | None
    created: float | None
    workflow: str | None = None
    followups: list[str] | None = None  # yêu cầu "tiếp tục" người dùng thêm sau khi mục tiêu kết thúc
    # /grill: trưởng nhóm phỏng vấn người dùng trước khi lập kế hoạch —
    # {"qa": [{"q", "why", "options", "rec", "a"}], "spec": "", "error": ""}
    grill: dict | None = None
    lead_session: str | None = None        # phiên trưởng nhóm lúc lập kế hoạch (/continue m<id> tiếp tục)
    lead_session_agent: str | None = None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Goal":
        d = dict(r)
        d["followups"] = json.loads(d.get("followups") or "[]")
        d["grill"] = json.loads(d["grill"]) if d.get("grill") else None
        return cls(**d)

    @property
    def spec(self) -> str:
        return str((self.grill or {}).get("spec") or "")

    def base_text(self) -> str:
        """Text gốc + bản đặc tả chốt sau khi hỏi đáp (/grill), nếu có."""
        if not self.spec:
            return self.text
        return (f"{self.text}\n\nCLARIFIED REQUIREMENTS (agreed with the user in a Q&A interview — "
                f"follow them):\n{self.spec}")

    def full_text(self) -> str:
        """Mục tiêu gửi agent: text gốc (+ đặc tả /grill) + các yêu cầu tiếp theo (tiếng Anh vì gửi agent)."""
        out = self.base_text()
        for i, f in enumerate(self.followups or [], 1):
            out += f"\n\nFOLLOW-UP {i}: {f}"
        return out


class DB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=15, check_same_thread=False,
                                    isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=15000")
        self.conn.executescript(SCHEMA)
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(tasks)")}
        for col, typ in (("model", "TEXT"), ("effort", "TEXT"), ("base", "TEXT"),
                         ("head", "TEXT"), ("attempts", "INTEGER"), ("session", "TEXT"),
                         ("session_agent", "TEXT"), ("resume", "TEXT"), ("ask", "TEXT")):
            if col not in cols:  # nâng cấp DB cũ
                self.conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {typ}")
        rcols = {r["name"] for r in self.conn.execute("PRAGMA table_info(runs)")}
        for col, typ in RUN_USAGE_COLS:
            if col not in rcols:  # nâng cấp DB cũ: token/cost đọc từ log phiên của CLI (usage_logs.py)
                self.conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {typ}")
        gcols = {r["name"] for r in self.conn.execute("PRAGMA table_info(goals)")}
        for col in ("workflow", "followups", "grill", "lead_session", "lead_session_agent"):
            if col not in gcols:  # nâng cấp DB cũ
                self.conn.execute(f"ALTER TABLE goals ADD COLUMN {col} TEXT")

    # ---------- goals ----------
    def add_goal(self, text: str, workflow: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO goals(text, status, round, created, workflow) VALUES (?, 'planning', 1, ?, ?)",
            (text, time.time(), workflow))
        return int(cur.lastrowid)

    def goal(self, gid: int) -> Goal | None:
        r = self.conn.execute("SELECT * FROM goals WHERE id=?", (gid,)).fetchone()
        return Goal.from_row(r) if r else None

    def goals(self) -> list[Goal]:
        return [Goal.from_row(r) for r in self.conn.execute("SELECT * FROM goals ORDER BY id")]

    def add_followup(self, gid: int, text: str) -> None:
        g = self.goal(gid)
        if g:
            self.conn.execute("UPDATE goals SET followups=? WHERE id=?",
                              (json.dumps((g.followups or []) + [text], ensure_ascii=False), gid))

    def set_grill(self, gid: int, data: dict) -> None:
        self.conn.execute("UPDATE goals SET grill=? WHERE id=?", (json.dumps(data, ensure_ascii=False), gid))

    def update_goal(self, gid: int, **fields) -> None:
        if not fields:
            return
        keys = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE goals SET {keys} WHERE id=?", (*fields.values(), gid))

    # ---------- tasks ----------
    def add_task(self, agent: str, title: str, prompt: str, *, goal_id: int | None = None,
                 parent_id: int | None = None, depends_on: list[int] | None = None,
                 status: str = QUEUED, depth: int = 0, source: str = "user",
                 model: str | None = None, effort: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO tasks(goal_id, parent_id, agent, title, prompt, status, depends_on,"
            " depth, source, created, model, effort) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (goal_id, parent_id, agent, title, prompt, status,
             json.dumps(depends_on or []), depth, source, time.time(), model or None,
             effort or None))
        return int(cur.lastrowid)

    def task(self, tid: int) -> Task | None:
        r = self.conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        return Task.from_row(r) if r else None

    def tasks(self, goal_id: int | None = None, status: str | tuple | None = None) -> list[Task]:
        q, args = "SELECT * FROM tasks", []
        conds = []
        if goal_id is not None:
            conds.append("goal_id=?")
            args.append(goal_id)
        if status is not None:
            sts = (status,) if isinstance(status, str) else tuple(status)
            conds.append(f"status IN ({','.join('?' * len(sts))})")
            args.extend(sts)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY id"
        return [Task.from_row(r) for r in self.conn.execute(q, args)]

    def update_task(self, tid: int, **fields) -> None:
        if not fields:
            return
        if "depends_on" in fields:
            fields["depends_on"] = json.dumps(fields["depends_on"])
        if fields.get("ask") is not None:
            fields["ask"] = json.dumps(fields["ask"], ensure_ascii=False)
        keys = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE tasks SET {keys} WHERE id=?", (*fields.values(), tid))

    def claim_task(self, tid: int) -> bool:
        """QUEUED → RUNNING nguyên tử: chỉ một tiến trình (TUI, web, `ateam run`) chiếm được task."""
        cur = self.conn.execute("UPDATE tasks SET status=?, started=?, error=NULL WHERE id=? AND status=?",
                                (RUNNING, time.time(), tid, QUEUED))
        return cur.rowcount == 1

    def delete(self, task_ids: list[int], goal_ids: list[int]) -> None:
        """Xoá hẳn task / mục tiêu (dọn bảng việc). Bảng runs giữ nguyên để /usage vẫn đủ số liệu."""
        self.conn.executemany("DELETE FROM tasks WHERE id=?", [(i,) for i in task_ids])
        self.conn.executemany("DELETE FROM goals WHERE id=?", [(i,) for i in goal_ids])

    # ---------- notes ----------
    def add_note(self, author: str, text: str) -> None:
        self.conn.execute("INSERT INTO notes(author, text, created) VALUES (?,?,?)",
                          (author, text, time.time()))

    def recent_notes(self, limit: int = 15) -> list[tuple[str, str]]:
        """Ghi chú gần nhất, tính từ bản tóm tắt /compact mới nhất (ghi chú cũ hơn đã nằm trong nó)."""
        rows = self.conn.execute(
            "SELECT author, text FROM notes WHERE id >= (SELECT COALESCE(MAX(id), 0) FROM notes"
            " WHERE author = ?) ORDER BY id DESC LIMIT ?", (COMPACT_AUTHOR, limit)).fetchall()
        return [(r["author"], r["text"]) for r in reversed(rows)]

    def last_compact(self) -> float:
        """Thời điểm /compact gần nhất (0 nếu chưa từng)."""
        r = self.conn.execute("SELECT MAX(created) FROM notes WHERE author = ?",
                              (COMPACT_AUTHOR,)).fetchone()
        return float(r[0] or 0)

    # ---------- runs (thống kê lượt chạy) ----------
    def add_run(self, task_id: int | None, agent: str, kind: str, prompt_chars: int, *,
                goal_id: int | None = None, cwd: str | None = None, model: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs(task_id, agent, kind, started, prompt_chars, goal_id, cwd, model)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (task_id, agent, kind, time.time(), prompt_chars, goal_id, cwd, model or None))
        return int(cur.lastrowid)

    def run(self, rid: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        return dict(r) if r else None

    def set_run_usage(self, rid: int, *, model: str | None, in_tok: int, out_tok: int, cache_read: int,
                      cache_write: int, cost: float | None, src: str) -> None:
        self.conn.execute("UPDATE runs SET model=COALESCE(?, model), in_tok=?, out_tok=?, cache_read=?,"
                          " cache_write=?, cost=?, tok_src=? WHERE id=?",
                          (model or None, in_tok, out_tok, cache_read, cache_write, cost, src, rid))

    def runs_since(self, since: float) -> list[dict]:
        """Lượt chạy agent (không gồm lệnh kiểm tra) từ thời điểm since, kèm goal_id suy từ task."""
        return [dict(r) for r in self.conn.execute(
            "SELECT r.*, COALESCE(r.goal_id, t.goal_id) gid, " + TOKENS_SQL + " tokens FROM runs r LEFT JOIN tasks t ON t.id = r.task_id"
            " WHERE r.started >= ? AND r.kind != 'test' ORDER BY r.started", (since,))]

    def finish_run(self, rid: int, rc: int, status: str, output_chars: int) -> None:
        self.conn.execute("UPDATE runs SET finished=?, rc=?, status=?, output_chars=? WHERE id=?",
                          (time.time(), rc, status, output_chars, rid))

    def usage(self, since: float) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for r in self.conn.execute(
                "SELECT agent, COUNT(*) n, SUM(COALESCE(finished, started) - started) secs,"
                " SUM(prompt_chars) pc, SUM(COALESCE(output_chars, 0)) oc,"
                " SUM(status = 'ratelimit') rl, SUM(status IN ('failed', 'timeout')) bad"
                " FROM runs WHERE started >= ? AND kind != 'test' GROUP BY agent", (since,)):
            out[r["agent"]] = {"runs": r["n"], "secs": r["secs"] or 0, "prompt_chars": r["pc"] or 0,
                               "output_chars": r["oc"] or 0, "ratelimits": r["rl"] or 0,
                               "failed": r["bad"] or 0}
        return out
