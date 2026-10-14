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
    workflow TEXT
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
    attempts INTEGER
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
    output_chars INTEGER
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author TEXT,
    text TEXT NOT NULL,
    created REAL
);
"""

# tác giả của ghi chú tóm tắt do /compact tạo
COMPACT_AUTHOR = "compact"

# trạng thái task
DRAFT, QUEUED, RUNNING, DONE, FAILED, CANCELLED, BLOCKED, CONFLICT, REVIEW = (
    "draft", "queued", "running", "done", "failed", "cancelled", "blocked", "conflict", "review",
)
ACTIVE = (DRAFT, QUEUED, RUNNING, REVIEW)
FINISHED_BAD = (FAILED, CANCELLED, BLOCKED)


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

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Task":
        d = dict(r)
        d["depends_on"] = json.loads(d.get("depends_on") or "[]")
        return cls(**d)


@dataclass
class Goal:
    id: int
    text: str
    status: str
    round: int
    summary: str | None
    created: float | None
    workflow: str | None = None


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
                         ("head", "TEXT"), ("attempts", "INTEGER")):
            if col not in cols:  # nâng cấp DB cũ
                self.conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {typ}")
        gcols = {r["name"] for r in self.conn.execute("PRAGMA table_info(goals)")}
        if "workflow" not in gcols:
            self.conn.execute("ALTER TABLE goals ADD COLUMN workflow TEXT")

    # ---------- goals ----------
    def add_goal(self, text: str, workflow: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO goals(text, status, round, created, workflow) VALUES (?, 'planning', 1, ?, ?)",
            (text, time.time(), workflow))
        return int(cur.lastrowid)

    def goal(self, gid: int) -> Goal | None:
        r = self.conn.execute("SELECT * FROM goals WHERE id=?", (gid,)).fetchone()
        return Goal(**dict(r)) if r else None

    def goals(self) -> list[Goal]:
        return [Goal(**dict(r)) for r in self.conn.execute("SELECT * FROM goals ORDER BY id")]

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
        keys = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE tasks SET {keys} WHERE id=?", (*fields.values(), tid))

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
    def add_run(self, task_id: int | None, agent: str, kind: str, prompt_chars: int) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs(task_id, agent, kind, started, prompt_chars) VALUES (?,?,?,?,?)",
            (task_id, agent, kind, time.time(), prompt_chars))
        return int(cur.lastrowid)

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
