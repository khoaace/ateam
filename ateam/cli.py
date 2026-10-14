"""Dòng lệnh `ateam`."""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, mentions
from .config import (DEFAULT_CONFIG, GLOBAL_CONFIG, ensure_global_config, load_config,
                     needs_setup, save_agent_setting)
from .db import DB, QUEUED
from .orchestrator import SYSTEM, Orchestrator


def find_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    env = os.environ.get("ATEAM_ROOT")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def open_db(root: Path) -> DB:
    env = os.environ.get("ATEAM_DB")
    return DB(Path(env) if env else root / ".ateam" / "team.db")


# ---------------------------------------------------------------------------- lệnh
def setup_config() -> None:
    for n in ensure_global_config():
        print("ℹ " + n)


def cmd_tui(args) -> int:
    root = find_root(args.dir)
    notes = ensure_global_config()
    cfg = load_config(root)
    cfg.notices = notes
    from .tui import TeamApp
    # Lần đầu mở app (hoặc `ateam setup`): màn hình chọn agent/model/effort, hỏi sẵn model của CLI
    TeamApp(root, cfg, open_db(root), setup=args.cmd == "setup" or needs_setup()).run()
    return 0


def cmd_init(args) -> int:
    setup_config()
    print(f"Cấu hình chung: {GLOBAL_CONFIG}")
    if args.project:
        p = find_root(args.dir) / ".ateam" / "config.toml"
        if p.exists():
            print(f"Đã có: {p}")
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(DEFAULT_CONFIG, encoding="utf-8")
            print(f"Đã tạo cấu hình dự án: {p}")
    return 0


def cmd_doctor(args) -> int:
    root = find_root(args.dir)
    setup_config()
    cfg = load_config(root)
    print(f"ateam {__version__}  ·  Python {sys.version.split()[0]}")
    print("Cấu hình:", ", ".join(map(str, cfg.sources)) or "(mặc định)")
    print(f"Trưởng nhóm: {cfg.lead}   ·   isolation: {cfg.isolation}"
          + (f" (merge: {cfg.merge})" if cfg.isolation == "worktree" else "")
          + f"   ·   song song: {cfg.max_parallel}")
    print(f"Kiểm tra sau task: {cfg.verify.command or '(tắt)'}   ·   "
          f"trưởng nhóm dự phòng: {', '.join(cfg.lead_fallback) or '(không)'}\n")
    ok = True
    for name, a in cfg.agents.items():
        path = shutil.which(a.binary) if a.binary else None
        flag = "✓" if path else "✗"
        ver = ""
        if path:
            try:
                r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15)
                ver = (r.stdout or r.stderr).strip().splitlines()[0][:60] if (r.stdout or r.stderr) else ""
            except Exception:
                ver = "(không lấy được version)"
        else:
            ok = ok and not a.enabled
        state = "" if a.enabled else " (đang tắt)"
        print(f" {flag} {name:12} {a.binary:10} {ver}{state}")
        if a.fallback:
            print(f"     dự phòng khi hết hạn mức: {', '.join(a.fallback)}")
        print(f"     model/effort: {a.label()}"
              + (f"   (effort hợp lệ: {', '.join(a.efforts)})" if a.efforts else ""))
        if a.models:
            print(f"     model gợi ý: {', '.join(a.models[:8])}" + (" …" if len(a.models) > 8 else ""))
        print(f"     {' '.join(a.argv('<prompt>'))}")
        print(f"     @file trong prompt → {mentions.describe(a.binary, a.file_ref, a.file_args, a.image_args)}")
    if cfg.lead not in cfg.agents:
        print(f"\n✗ Trưởng nhóm '{cfg.lead}' không có trong [agents].")
        ok = False
    if shutil.which("git") is None:
        print("\n⚠ Chưa có git — chế độ worktree sẽ không dùng được.")
    print("\nChọn agent, model, effort: ateam setup (hoặc /setup trong app).")
    print("\nMọi thứ sẵn sàng." if ok else "\nCài các CLI còn thiếu hoặc đặt enabled = false cho agent đó trong config.")
    return 0 if ok else 1


def _printer(prefix_task: bool = True):
    def on_event(kind: str, data: dict) -> None:
        if kind != "log":
            return
        tid = data["task_id"]
        line = data["line"]
        if tid == SYSTEM:
            print(line, flush=True)
        elif prefix_task:
            print(f"   │#{tid} {line}", flush=True)
    return on_event


def cmd_goal(args) -> int:
    root = find_root(args.dir)
    setup_config()
    cfg = load_config(root)
    db = open_db(root)

    async def main() -> int:
        orch = Orchestrator(root, cfg, db, on_event=_printer(not args.quiet))
        await orch.setup()
        gid = orch.new_goal(" ".join(args.text))
        while orch.lead_busy:
            await asyncio.sleep(0.3)
        g = db.goal(gid)
        if g.status == "failed":
            return 1
        while True:
            g = db.goal(gid)
            if g.status == "awaiting":
                drafts = db.tasks(goal_id=gid, status="draft")
                if not args.yes:
                    print("\nKế hoạch:")
                    for t in drafts:
                        dep = f" (sau #{', #'.join(map(str, t.depends_on))})" if t.depends_on else ""
                        print(f"  #{t.id} [{t.agent}] {t.title}{dep}")
                    ans = await asyncio.to_thread(input, "Chạy kế hoạch này? [Y/n] ")
                    if ans.strip().lower() in ("n", "no", "k", "không"):
                        print("Đã dừng. Task vẫn ở trạng thái nháp — mở `ateam` để chỉnh và chạy.")
                        return 0
                orch.approve(gid)
            await orch.run_until_idle()
            g = db.goal(gid)
            if g.status != "awaiting":
                break
        print(f"\n=== Mục tiêu #{gid}: {g.status} ===")
        if g.summary:
            print(g.summary)
        for t in db.tasks(goal_id=gid):
            print(f"  #{t.id} [{t.agent}] {t.status}: {t.title}" + (f" — {t.error}" if t.error else ""))
        return 0 if g.status == "done" else 2

    return asyncio.run(main())


def cmd_add(args) -> int:
    root = find_root(args.dir)
    cfg = load_config(root)
    db = open_db(root)
    if args.to not in cfg.active_agents():
        print(f"Không có agent '{args.to}'. Có: {', '.join(cfg.active_agents())}", file=sys.stderr)
        return 1
    parent = os.environ.get("ATEAM_TASK_ID")
    parent_task = db.task(int(parent)) if parent and parent.isdigit() else None
    depth = (parent_task.depth + 1) if parent_task else 0
    if parent_task and depth > cfg.max_delegation_depth:
        print("Đã chạm giới hạn số tầng giao việc.", file=sys.stderr)
        return 1
    prompt = " ".join(args.prompt)
    tid = db.add_task(args.to, args.title or prompt[:60], prompt, model=args.model, effort=args.effort,
                      goal_id=parent_task.goal_id if parent_task else None,
                      parent_id=parent_task.id if parent_task else None, depth=depth,
                      status=QUEUED,
                      source=f"delegate:{parent_task.agent}" if parent_task else "cli")
    print(f"Đã thêm task #{tid} cho {args.to}. (Chạy khi `ateam` đang mở, hoặc `ateam run`)")
    return 0


def cmd_note(args) -> int:
    db = open_db(find_root(args.dir))
    db.add_note(os.environ.get("ATEAM_AGENT", "user"), " ".join(args.text))
    print("Đã ghi chú.")
    return 0


def cmd_list(args) -> int:
    db = open_db(find_root(args.dir))
    for g in db.goals()[-10:]:
        print(f"🎯 #{g.id} [{g.status}] {g.text[:90]}")
    for t in db.tasks()[-40:]:
        dep = f" ⟵{','.join(map(str, t.depends_on))}" if t.depends_on else ""
        print(f"  #{t.id:<4} {t.agent:12} {t.status:10} {t.title[:70]}{dep}")
    return 0


def cmd_log(args) -> int:
    root = find_root(args.dir)
    p = root / ".ateam" / "logs" / ("system.log" if args.id in ("sys", "0") else f"t{args.id.lstrip('#')}.log")
    if not p.exists():
        print("Chưa có log.")
        return 1
    print(p.read_text(encoding="utf-8", errors="replace"))
    return 0


def cmd_run(args) -> int:
    root = find_root(args.dir)
    cfg = load_config(root)
    db = open_db(root)

    async def main():
        orch = Orchestrator(root, cfg, db, on_event=_printer(not args.quiet))
        await orch.setup()
        await orch.run_until_idle()
    asyncio.run(main())
    return 0


def cmd_set(args) -> int:
    setup_config()
    cfg = load_config(find_root(args.dir))
    a = cfg.agents.get(args.agent)
    if not a:
        print(f"Không có agent '{args.agent}'. Có: {', '.join(cfg.agents)}", file=sys.stderr)
        return 1
    if args.model is None and args.effort is None:
        print(f"{a.name}: {a.label()}")
        return 0
    if args.effort not in (None, "-") and a.efforts and args.effort not in a.efforts:
        print(f"⚠ '{args.effort}' không nằm trong {a.efforts} — vẫn lưu, nhưng CLI có thể báo lỗi.")
    if args.model is not None:
        save_agent_setting(a.name, "model", args.model)
    if args.effort is not None:
        save_agent_setting(a.name, "effort", args.effort)
    a2 = load_config(find_root(args.dir)).agents[a.name]
    print(f"{a2.name}: {a2.label()}")
    print("   " + " ".join(a2.argv("<prompt>")))
    return 0


def cmd_models(args) -> int:
    from .config import describe_models
    setup_config()
    root = find_root(args.dir)
    cfg = load_config(root)
    if args.agent and args.agent not in cfg.agents:
        print(f"Không có agent '{args.agent}'. Có: {', '.join(cfg.agents)}", file=sys.stderr)
        return 1
    if args.refresh:
        orch = Orchestrator(root, cfg, open_db(root))
        names = [args.agent] if args.agent else None
        for n, msg in asyncio.run(orch.discover_all(names)).items():
            print(msg)
    print(describe_models(cfg, args.agent))
    print("Đặt: ateam set <agent> --model <tên> --effort <mức>")
    return 0


def _orch(args):
    root = find_root(args.dir)
    cfg = load_config(root)
    return Orchestrator(root, cfg, open_db(root))


def cmd_diff(args) -> int:
    print(asyncio.run(_orch(args).diff(int(args.id.lstrip("#")))))
    return 0


def cmd_merge(args) -> int:
    print(asyncio.run(_orch(args).merge(int(args.id.lstrip("#")))))
    return 0


def cmd_reject(args) -> int:
    fb = " ".join(args.feedback) or None
    print(asyncio.run(_orch(args).reject(int(args.id.lstrip("#")), fb)))
    if fb:
        print("Task đã xếp hàng lại — mở `ateam` hoặc chạy `ateam run` để làm lại.")
    return 0


def cmd_verify(args) -> int:
    from .config import save_project_setting
    root = find_root(args.dir)
    if not args.command:
        print(f"Lệnh kiểm tra: {load_config(root).verify.command or '(tắt)'}")
        return 0
    cmd = " ".join(args.command)
    save_project_setting(root, "verify_command", None if cmd in ("off", "-") else cmd)
    print(f"Lệnh kiểm tra của dự án: {load_config(root).verify.command or '(tắt)'}")
    return 0


def cmd_usage(args) -> int:
    import time as _t
    from .limits import load_cooldowns
    db = open_db(find_root(args.dir))
    for label, since in (("7 ngày", _t.time() - 7 * 86400), ("24 giờ", _t.time() - 86400)):
        print(f"{label}:")
        for name, r in db.usage(since).items():
            tok = (r["prompt_chars"] + r["output_chars"]) // 4
            print(f"  {name:12} {r['runs']:>4} lượt  {int(r['secs']) // 60:>5} phút  ~{tok // 1000}k token"
                  f"  lỗi {r['failed']}  hết hạn mức {r['ratelimits']}")
    cds = load_cooldowns()
    print("Đang tạm nghỉ: " + (", ".join(f"{a} đến {_t.strftime('%H:%M %d/%m', _t.localtime(t))}"
                                         for a, t in cds.items()) or "không"))
    return 0


def cmd_cooldown(args) -> int:
    from .limits import save_cooldown
    import time as _t
    if args.minutes in (None, "off", "0", "-"):
        save_cooldown(args.agent, None)
        print(f"{args.agent} hoạt động lại.")
    else:
        save_cooldown(args.agent, _t.time() + int(args.minutes) * 60)
        print(f"{args.agent} tạm nghỉ {args.minutes} phút.")
    return 0


# ---------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ateam", description="AI Team — điều phối nhiều AI agent CLI.")
    p.add_argument("--version", action="version", version=f"ateam {__version__}")
    p.add_argument("-C", "--dir", help="thư mục dự án (mặc định: thư mục hiện tại)")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("tui", help="mở giao diện terminal (mặc định)")
    sub.add_parser("setup", help="mở giao diện ở màn hình thiết lập: agent, trưởng nhóm, model, effort")
    s = sub.add_parser("init", help="tạo file cấu hình")
    s.add_argument("--project", action="store_true", help="tạo thêm .ateam/config.toml cho dự án")
    sub.add_parser("doctor", help="kiểm tra các agent đã cài chưa")
    s = sub.add_parser("goal", help="giao mục tiêu và chạy không cần giao diện")
    s.add_argument("text", nargs="+")
    s.add_argument("-y", "--yes", action="store_true", help="không hỏi duyệt kế hoạch")
    s.add_argument("-q", "--quiet", action="store_true", help="không in log chi tiết của agent")
    s = sub.add_parser("add", help="thêm 1 task vào bảng (agent cũng gọi được lệnh này)")
    s.add_argument("--to", required=True, help="tên agent")
    s.add_argument("--title")
    s.add_argument("--model", help="model riêng cho task này")
    s.add_argument("--effort", help="effort riêng cho task này")
    s.add_argument("prompt", nargs="+")
    s = sub.add_parser("set", help="đặt model / effort mặc định cho 1 agent")
    s.add_argument("agent")
    s.add_argument("--model", help="tên model, '-' để về mặc định")
    s.add_argument("--effort", help="mức effort, '-' để về mặc định")
    s = sub.add_parser("models", help="xem model / effort mỗi agent hỗ trợ")
    s.add_argument("agent", nargs="?")
    s.add_argument("--refresh", action="store_true",
                   help="hỏi CLI danh sách model thật (opencode models, agy models)")
    s = sub.add_parser("note", help="ghi chú chung cho cả đội")
    s.add_argument("text", nargs="+")
    sub.add_parser("list", help="liệt kê mục tiêu và task")
    s = sub.add_parser("log", help="in log của 1 task (hoặc 'sys')")
    s.add_argument("id")
    s = sub.add_parser("diff", help="xem thay đổi của 1 task")
    s.add_argument("id")
    s = sub.add_parser("merge", help="merge task đang chờ duyệt")
    s.add_argument("id")
    s = sub.add_parser("reject", help="từ chối task đang chờ duyệt (kèm góp ý = giao làm lại)")
    s.add_argument("id")
    s.add_argument("feedback", nargs="*")
    s = sub.add_parser("verify", help="đặt lệnh kiểm tra sau mỗi task cho dự án (off = tắt)")
    s.add_argument("command", nargs="*")
    sub.add_parser("usage", help="thống kê lượt chạy và hạn mức theo agent")
    s = sub.add_parser("cooldown", help="cho agent tạm nghỉ N phút, hoặc 'off'")
    s.add_argument("agent")
    s.add_argument("minutes", nargs="?")
    s = sub.add_parser("run", help="chạy hết các task đang chờ rồi thoát")
    s.add_argument("-q", "--quiet", action="store_true")

    args = p.parse_args(argv)
    handlers = {None: cmd_tui, "tui": cmd_tui, "setup": cmd_tui, "init": cmd_init, "doctor": cmd_doctor,
                "goal": cmd_goal, "add": cmd_add, "note": cmd_note, "list": cmd_list,
                "log": cmd_log, "run": cmd_run, "set": cmd_set, "models": cmd_models, "diff": cmd_diff,
                "merge": cmd_merge, "reject": cmd_reject, "verify": cmd_verify,
                "usage": cmd_usage, "cooldown": cmd_cooldown}
    try:
        return handlers[args.cmd](args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
