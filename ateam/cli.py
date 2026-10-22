"""Dòng lệnh `ateam`."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, mentions, reports
from .config import (DEFAULT_CONFIG, GLOBAL_CONFIG, ensure_global_config,
                     load_config, needs_setup, save_agent_setting)
from .db import DB, QUEUED
from .doctor import inspect_commands
from .orchestrator import SYSTEM, Orchestrator
from .opencode import major_version
from .i18n import LANG_NAMES, LANGS, get_lang, normalize, save_lang, set_lang, tr


def find_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    env = os.environ.get("ATEAM_ROOT")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def with_root(argv: list[str], root: Path) -> list[str]:
    """argv (bỏ tên chương trình) để mở lại ateam ở thư mục khác (/open): thay -C/--dir cũ."""
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
            continue
        if a in ("-C", "--dir"):
            skip = True
            continue
        if a.startswith("--dir=") or (a.startswith("-C") and len(a) > 2):
            continue
        out.append(a)
    return ["-C", str(root), *out]


def reexec(argv: list[str], root: Path | None = None) -> None:
    """Chạy lại ateam trong chính tiến trình này (execv). root: /open — chuyển hẳn sang dự án đó: execv giữ thư mục
    làm việc và biến môi trường, nên đổi luôn cwd, PWD và bỏ ATEAM_DB/ATEAM_ROOT của dự án cũ (không thì terminal,
    agent và chính ateam vẫn thấy đường dẫn cũ)."""
    if root is not None:
        argv = with_root(argv, root)
        os.chdir(root)
        os.environ["PWD"] = str(root)
        for k in ("ATEAM_DB", "ATEAM_ROOT"):
            os.environ.pop(k, None)
    os.execv(sys.executable, [sys.executable, "-m", "ateam", *argv])


def open_db(root: Path) -> DB:
    env = os.environ.get("ATEAM_DB")
    return DB(Path(env) if env else root / ".ateam" / "team.db")


# ---------------------------------------------------------------------------- lệnh
def setup_config() -> None:
    for n in ensure_global_config():
        print("ℹ " + n)


def acquire_session_lock(root: Path):
    """Khoá `.ateam/tui.lock` để chỉ 1 phiên giao diện (terminal hoặc tab web) chạy bộ lập lịch trên dự án —
    2 phiên cùng lúc có thể chạy trùng 1 task. Trả file đang giữ khoá (giữ nó sống suốt tiến trình; khoá tự nhả
    khi tiến trình thoát), hoặc None nếu phiên khác đang giữ."""
    try:
        import fcntl
    except ImportError:  # Windows: không có flock -> không khoá
        return True
    path = root / ".ateam" / "tui.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def free_port(host: str, start: int, tries: int = 20) -> int | None:
    """Cổng trống đầu tiên từ `start` (nhiều dự án chạy `ateam web` cùng lúc, như mở nhiều terminal TUI). Thử bind
    không đặt SO_REUSEADDR: trên macOS có cờ đó vẫn bind được cổng mà server khác đang nghe ở 0.0.0.0. bind() lỗi mà
    không ai nghe (chỉ còn kết nối TIME_WAIT — vd /open vừa tắt server cũ) thì vẫn là cổng trống: aiohttp bind với
    SO_REUSEADDR."""
    import socket
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    h = host.strip("[]")
    probe = {"": "127.0.0.1", "0.0.0.0": "127.0.0.1", "::": "::1"}.get(h, h)
    for port in range(start, min(start + tries, 65536)):
        try:
            with socket.socket(family) as s:
                s.bind((h, port))
        except OSError:
            try:
                with socket.socket(family) as s:
                    s.settimeout(0.3)
                    s.connect((probe, port))
            except ConnectionRefusedError:
                return port
            except OSError:
                pass
            continue
        return port
    return None


def pick_port(host: str, want: int) -> int | None:
    """Cổng cho `ateam web`: `want` bận thì lấy cổng kế tiếp còn trống (có báo); hết cổng thì báo lỗi, trả None."""
    port = free_port(host, want)
    if port is None:
        print(tr("Cổng {a}–{b} đều đang bận — chọn cổng khác bằng --port.", a=want, b=want + 19), file=sys.stderr)
    elif port != want:
        print(tr("⚠ Cổng {a} đang bận — dùng cổng {b}", a=want, b=port))
    return port


def ui_session_running(root: Path) -> bool:
    """Có phiên giao diện (TUI/web) đang giữ khoá dự án không — không giữ khoá lại, để vẫn mở được giao diện
    trong lúc `ateam goal`/`ateam run` chạy."""
    lock = acquire_session_lock(root)
    if lock is None:
        return True
    if lock is not True:
        lock.close()
    return False


def cmd_tui(args) -> int:
    root = find_root(args.dir)
    notes = ensure_global_config()
    cfg = load_config(root)
    cfg.notices = notes
    lock = acquire_session_lock(root)
    if lock is None:
        # không print: dưới `ateam web`, stdout là kênh giao thức của driver web
        from .tui import BusyApp
        BusyApp().run()
        return 1
    from .projects import touch_project
    from .tui import TeamApp
    touch_project(root)
    # Lần đầu mở app (hoặc `ateam setup`): màn hình chọn agent/model/effort, hỏi sẵn model của CLI
    app = TeamApp(root, cfg, open_db(root), setup=args.cmd == "setup" or needs_setup())
    app.run()
    # dưới `ateam web`, app thoát là trình duyệt báo "Session ended" -> không execv (tiến trình mới sẽ chạy mồ côi,
    # giữ khoá phiên); người dùng bấm Restart, textual-serve mở tiến trình mới với ngôn ngữ vừa lưu
    if getattr(app, "restart_requested", False) and "WebDriver" not in os.environ.get("TEXTUAL_DRIVER", ""):
        # /lang: nhiều chuỗi được tính lúc import -> mở lại cả tiến trình với ngôn ngữ mới
        argv, skip = [], False
        for a in sys.argv[1:]:  # bỏ --lang của lần chạy trước: dùng ngôn ngữ vừa lưu
            if skip or a.startswith("--lang="):
                skip = False
                continue
            if a == "--lang":
                skip = True
                continue
            argv.append(a)
        if args.cmd == "setup":
            argv = [a for a in argv if a != "setup"]
        reexec(argv, getattr(app, "restart_root", None))  # restart_root: /open mở dự án khác
    return 0


def cmd_web(args) -> int:
    remote_args = args.tunnel or args.public_url or args.host not in ("127.0.0.1", "localhost", "::1", "[::1]")
    if args.tui:
        if remote_args:
            print(tr("--tui chỉ chạy trên máy này — bỏ --host/--tunnel/--public-url, hoặc dùng `ateam web` "
                     "(giao diện web) để mở từ điện thoại."), file=sys.stderr)
            return 1
        return cmd_web_tui(args)
    try:
        from . import web
        from .web_auth import Remote, is_loopback
    except ImportError:
        print(tr("Cần cài thêm aiohttp: {v}", v=f"{shlex.quote(sys.executable)} -m pip install aiohttp"))
        return 1
    if args.tunnel and not shutil.which("cloudflared"):
        print(tr("Chưa cài cloudflared — cài bằng `brew install cloudflared` (macOS) rồi chạy lại."),
              file=sys.stderr)
        return 1
    if args.public_url and not re.match(r"https?://[^/\s]+", args.public_url):
        print(tr("--public-url phải là địa chỉ đầy đủ, vd https://ateam.ten-mien.com"), file=sys.stderr)
        return 1
    root = find_root(args.dir)
    notes = ensure_global_config()
    cfg = load_config(root)
    cfg.notices = notes
    # một server giữ một bộ lập lịch cho mọi tab trình duyệt; terminal mở `ateam` cùng lúc sẽ bị khoá
    lock = acquire_session_lock(root)
    if lock is None:
        print(tr("Dự án này đang mở ở một phiên ateam khác — đóng phiên đó rồi chạy lại."))
        return 1
    port = pick_port(args.host, args.port)  # dự án khác đang giữ cổng -> cổng kế tiếp
    if port is None:
        return 1
    remote = Remote(root / ".ateam", host=args.host, port=port, public_url=args.public_url or "",
                    tunnel=args.tunnel, readonly=args.readonly, new_token=args.new_token)
    url = f"http://127.0.0.1:{port}"
    if remote.enabled:
        url = remote.urls()[-1][1]  # máy này, kèm token
        print(tr("🔒 Chế độ từ xa: cần token (lưu ở .ateam/web_token; --new-token để đổi)")
              + (tr(" · chỉ xem (--readonly)") if args.readonly else tr(" · token có toàn quyền như trên máy này")))
        web.print_remote(remote)
        if not is_loopback(args.host):
            print(tr("⚠ Qua http trong LAN, token đi dạng rõ — ngoài mạng nhà nên dùng --tunnel (https)."))
        if args.tunnel:
            print(tr("⏳ Đang mở Cloudflare Tunnel… URL công khai + mã QR sẽ in ở dưới."))
    print(tr("Mở trên trình duyệt: {v}  (Ctrl+C để dừng)", v=url))
    if args.open:
        import webbrowser
        webbrowser.open(url)
    from .projects import touch_project
    touch_project(root)
    nxt = web.serve(root, cfg, open_db(root), port, remote)
    if nxt:  # /open trên web: server đã dừng (khoá phiên nhả khi execv) -> chạy lại ở dự án mới, cùng cổng
        # (cổng thật, kể cả khi đã đổi vì cổng muốn bận: trình duyệt đang mở cổng này)
        argv, skip = [], False
        for a in sys.argv[1:]:
            if skip:
                skip = False
                continue
            if a == "--port":
                skip = True
                continue
            if a in ("--open", "--new-token") or a.startswith("--port="):
                continue
            argv.append(a)
        print(tr("↪ Mở dự án {v}", v=nxt), flush=True)  # execv bỏ bộ đệm stdout chưa ghi
        reexec(argv + ["--port", str(port)], nxt)
    return 0


def cmd_web_tui(args) -> int:
    """`ateam web --tui`: chính giao diện terminal trong trình duyệt (textual-serve) — đủ mọi tab."""
    try:
        from textual_serve.server import Server

        from .web import guard_middleware
    except ImportError:
        print(tr("Cần cài thêm textual-serve: {v}", v=f"{shlex.quote(sys.executable)} -m pip install textual-serve"))
        return 1

    class GuardedServer(Server):
        """Như `ateam web`: chặn Host/Origin lạ — trang web khác không được mở WebSocket gõ phím vào ateam."""

        async def _make_app(self):
            app = await super()._make_app()
            app.middlewares.append(guard_middleware(self.port))
            return app

    root = find_root(args.dir)
    # mỗi tab trình duyệt chạy 1 tiến trình `ateam tui` riêng; chỉ nghe 127.0.0.1 vì giao diện chạy được lệnh shell.
    # --lang (chỉ cho lần chạy này) chuyển qua ATEAM_LANG; không có thì tiến trình con đọc ngôn ngữ đã lưu, nên
    # /lang + nút Restart đổi được ngôn ngữ (ATEAM_LANG thắng state.json: chọn --lang là ghim cho cả phiên web)
    if args.lang:
        os.environ["ATEAM_LANG"] = args.lang
    port = pick_port("127.0.0.1", args.port)
    if port is None:
        return 1
    argv = [sys.executable, "-m", "ateam", "-C", str(root), "tui"]
    print(tr("Mở trên trình duyệt: {v}  (Ctrl+C để dừng)", v=f"http://127.0.0.1:{port}"))
    GuardedServer(shlex.join(argv), host="127.0.0.1", port=port,
                  title=f"ateam — {root.name}").serve()
    return 0


def cmd_lang(args) -> int:
    if not args.code:
        print(tr("Ngôn ngữ hiện tại: {v} — đổi bằng `ateam lang en` hoặc `ateam lang vi`",
                 v=LANG_NAMES[get_lang()]))
        return 0
    code = normalize(args.code)
    if not code:
        print(tr("Không hỗ trợ '{code}' — chọn: {v}", code=args.code, v=", ".join(LANGS)))
        return 2
    save_lang(code)
    set_lang(code)
    print(tr("✓ Đã đổi ngôn ngữ sang {v}", v=LANG_NAMES[code]))
    return 0


def cmd_init(args) -> int:
    if args.focus and not args.overview:
        print(tr("Thêm --overview để trưởng nhóm viết bản tổng quan dự án: ateam init --overview {v}",
                 v=" ".join(args.focus)))
        return 2
    setup_config()
    print(tr("Cấu hình chung: {GLOBAL_CONFIG}", GLOBAL_CONFIG=GLOBAL_CONFIG))
    if args.project:
        p = find_root(args.dir) / ".ateam" / "config.toml"
        if p.exists():
            print(tr("Đã có: {p}", p=p))
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(DEFAULT_CONFIG, encoding="utf-8")
            print(tr("Đã tạo cấu hình dự án: {p}", p=p))
    if args.overview:
        o = _orch(args)
        ok, msg = asyncio.run(o.init_overview(" ".join(args.focus)))
        print(msg)
        return 0 if ok else 1
    return 0


def cmd_doctor(args) -> int:
    root = find_root(args.dir)
    setup_config()
    cfg = load_config(root)
    print(f"ateam {__version__}  ·  Python {sys.version.split()[0]}")
    print(tr("Cấu hình:"), ", ".join(map(str, cfg.sources)) or tr("(mặc định)"))
    print(tr("Trưởng nhóm: {lead}   ·   isolation: {isolation}", lead=cfg.lead, isolation=cfg.isolation)
          + (f" (merge: {cfg.merge})" if cfg.isolation == "worktree" else "")
          + f"   ·   song song: {cfg.max_parallel}")
    print(tr("Kiểm tra sau task: {v}   ·   trưởng nhóm dự phòng: {v2}\n", v=cfg.verify.command or tr("(tắt)"), v2=', '.join(cfg.lead_fallback) or tr("(không)")))
    ok = True
    help_cache = {}
    for name, a in cfg.agents.items():
        path = shutil.which(a.binary) if a.binary else None
        flag = "✓" if path else "✗"
        ver = ""
        if path:
            try:
                r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15)
                ver = (r.stdout or r.stderr).strip().splitlines()[0][:60] if (r.stdout or r.stderr) else ""
                if Path(a.binary).name == "opencode" and r.returncode == 0:
                    a.opencode_major = major_version(ver)
            except Exception:
                ver = tr("(không lấy được version)")
        else:
            ok = ok and not a.enabled
        state = "" if a.enabled else tr(" (đang tắt)")
        state += tr(" (tuỳ chỉnh)") if name in cfg.custom_agents else ""
        print(f" {flag} {name:12} {a.binary:10} {ver}{state}")
        if a.fallback:
            print(tr("     dự phòng khi hết hạn mức: {v}", v=', '.join(a.fallback)))
        print(f"     model/effort: {a.label()}"
              + (tr("   (effort hợp lệ: {v})", v=', '.join(a.efforts_for())) if a.efforts_for() else ""))
        if a.models:
            print(tr("     model gợi ý: {v}", v=', '.join(a.models[:8])) + (" …" if len(a.models) > 8 else ""))
        print(f"     {' '.join(a.argv('<prompt>'))}")
        if path:
            for issue in inspect_commands(a, root, help_cache):
                ok = ok and not a.enabled
                if issue.error:
                    print(tr("     ✗ Không kiểm tra được `{cmd}`: {why}", cmd=' '.join(issue.help_argv),
                             why=issue.error))
                else:
                    print(tr("     ✗ cờ không thấy trong `{v}`: {v2} — CLI có thể đã đổi cờ; sửa "
                             "command trong cấu hình", v=' '.join(issue.help_argv), v2=', '.join(issue.flags)))
        print(f"     @file trong prompt → {mentions.describe(a.binary, a.file_ref, a.file_args, a.image_args)}")
    if cfg.lead not in cfg.agents:
        print(tr("\n✗ Trưởng nhóm '{lead}' không có trong [agents].", lead=cfg.lead))
        ok = False
    if shutil.which("git") is None:
        print(tr("\n⚠ Chưa có git — chế độ worktree sẽ không dùng được."))
    if cfg.workflows:
        print(tr("\nWorkflow: {v}  (xem: ateam flows)", v=', '.join(cfg.workflows)))
    print(tr("\nChọn agent, model, effort: ateam setup (hoặc /setup trong app)."))
    print(tr("Thêm agent / workflow riêng: /custom trong app (hoặc nút ở màn hình thiết lập)."))
    print(tr("\nMọi thứ sẵn sàng.") if ok else tr("\n"
                                                     "Cài các CLI còn thiếu hoặc đặt enabled = "
                                                     "false cho agent đó trong config."))
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
        orch.auto_answer = True  # chạy không tương tác: agent hỏi (<<<ASK>>>) thì theo phương án đề xuất
        # giao diện đang mở: task RUNNING là của nó, không phải dở dang từ phiên trước
        await orch.setup(cleanup=not ui_session_running(root))
        if getattr(args, "ref", None):  # ateam continue <m12|t40> <yêu cầu>
            res = orch.continue_any(args.ref, " ".join(args.text))
            if isinstance(res, str):
                print("✗ " + res, file=sys.stderr)
                return 1
            if res[0] == "task":  # hỏi tiếp thread /task: chỉ cần chạy task mới
                await orch.run_until_idle()
                t = db.task(res[1])
                print(f"\n=== Task #{t.id} [{t.agent}]: {t.status} ===")
                print(t.error or t.result or "")
                return 0 if t.status == "done" else 2
            gid = res[1]
        elif getattr(args, "workflow", None):
            gid = orch.run_workflow(args.workflow, " ".join(args.text))
            if isinstance(gid, str):
                print("✗ " + gid, file=sys.stderr)
                return 1
        else:
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
                    print(tr("\nKế hoạch:"))
                    for t in drafts:
                        dep = f" (sau #{', #'.join(map(str, t.depends_on))})" if t.depends_on else ""
                        print(f"  #{t.id} [{t.agent}] {t.title}{dep}")
                    ans = await asyncio.to_thread(input, tr("Chạy kế hoạch này? [Y/n] "))
                    if ans.strip().lower() in ("n", "no", "k", "không"):
                        print(tr("Đã dừng. Task vẫn ở trạng thái nháp — mở `ateam` để chỉnh và "
                                 "chạy."))
                        return 0
                orch.approve(gid)
            await orch.run_until_idle()
            g = db.goal(gid)
            if g.status != "awaiting":
                break
        print(tr("\n=== Mục tiêu #{gid}: {status} ===", gid=gid, status=g.status))
        if g.summary:
            print(g.summary)
        for t in db.tasks(goal_id=gid):
            print(f"  #{t.id} [{t.agent}] {t.status}: {t.title}" + (f" — {t.error}" if t.error else ""))
        return 0 if g.status == "done" else 2

    return asyncio.run(main())


def cmd_flows(args) -> int:
    root = find_root(args.dir)
    setup_config()
    cfg = load_config(root)
    if not cfg.workflows:
        print(tr("Chưa có workflow nào. Tạo trong app: /custom (hoặc nút ở màn hình `ateam setup`)."))
        return 0
    for n, w in cfg.workflows.items():
        print(f"{n}  ({w.summary()})" + (f" — {w.description}" if w.description else ""))
        for i, st in enumerate(w.steps, 1):
            after = "" if st.after is None else (
                tr(" (sau bước {v})", v=', '.join(map(str, st.after))) if st.after else tr(" (chạy ngay)"))
            print(f"  {i}. [{st.agent}{('@' + st.effort) if st.effort else ''}] {st.title}{after}")
    print(tr("\nChạy: ateam flow <tên> \"mục tiêu\"   ·   trong app: /flow <tên> <mục tiêu>"))
    return 0


def cmd_add(args) -> int:
    root = find_root(args.dir)
    cfg = load_config(root)
    db = open_db(root)
    if args.to not in cfg.active_agents():
        print(tr("Không có agent '{to}'. Có: {v}", to=args.to, v=', '.join(cfg.active_agents())), file=sys.stderr)
        return 1
    parent = os.environ.get("ATEAM_TASK_ID")
    parent_task = db.task(int(parent)) if parent and parent.isdigit() else None
    depth = (parent_task.depth + 1) if parent_task else 0
    if parent_task and depth > cfg.max_delegation_depth:
        print(tr("Đã chạm giới hạn số tầng giao việc."), file=sys.stderr)
        return 1
    prompt = " ".join(args.prompt)
    tid = db.add_task(args.to, args.title or prompt[:60], prompt, model=args.model, effort=args.effort,
                      goal_id=parent_task.goal_id if parent_task else None,
                      parent_id=parent_task.id if parent_task else None, depth=depth,
                      status=QUEUED,
                      source=f"delegate:{parent_task.agent}" if parent_task else "cli")
    print(tr("Đã thêm task #{tid} cho {to}. (Chạy khi `ateam` đang mở, hoặc `ateam run`)", tid=tid, to=args.to))
    return 0


def cmd_note(args) -> int:
    db = open_db(find_root(args.dir))
    db.add_note(os.environ.get("ATEAM_AGENT", "user"), " ".join(args.text))
    print(tr("Đã ghi chú."))
    return 0


def cmd_compact(args) -> int:
    o = _orch(args)
    ok, msg = asyncio.run(o.compact(" ".join(args.focus)))
    print(msg)
    if ok:
        print(o.notes_text())
    return 0 if ok else 1


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
        print(tr("Chưa có log."))
        return 1
    print(p.read_text(encoding="utf-8", errors="replace"))
    return 0


def cmd_run(args) -> int:
    root = find_root(args.dir)
    cfg = load_config(root)
    db = open_db(root)

    async def main():
        orch = Orchestrator(root, cfg, db, on_event=_printer(not args.quiet))
        orch.auto_answer = True  # chạy không tương tác: agent hỏi (<<<ASK>>>) thì theo phương án đề xuất
        # giao diện đang mở: task RUNNING là của nó, không phải dở dang từ phiên trước
        await orch.setup(cleanup=not ui_session_running(root))
        await orch.run_until_idle()
    asyncio.run(main())
    return 0


def cmd_set(args) -> int:
    setup_config()
    cfg = load_config(find_root(args.dir))
    a = cfg.agents.get(args.agent)
    if not a:
        print(tr("Không có agent '{agent}'. Có: {v}", agent=args.agent, v=', '.join(cfg.agents)), file=sys.stderr)
        return 1
    if args.model is None and args.effort is None:
        print(f"{a.name}: {a.label()}")
        return 0
    if args.effort not in (None, "-") and a.efforts_for() and args.effort not in a.efforts_for():
        print(tr("⚠ '{effort}' không nằm trong {efforts} — vẫn lưu, nhưng CLI có thể báo lỗi.", effort=args.effort, efforts=a.efforts_for()))
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
        print(tr("Không có agent '{agent}'. Có: {v}", agent=args.agent, v=', '.join(cfg.agents)), file=sys.stderr)
        return 1
    if args.refresh:
        orch = Orchestrator(root, cfg, open_db(root))
        names = [args.agent] if args.agent else None
        for n, msg in asyncio.run(orch.discover_all(names)).items():
            print(msg)
    print(describe_models(cfg, args.agent))
    print(tr("Đặt: ateam set <agent> --model <tên> --effort <mức>"))
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
        print(tr("Task đã xếp hàng lại — mở `ateam` hoặc chạy `ateam run` để làm lại."))
    return 0


def cmd_verify(args) -> int:
    from .config import save_project_setting
    root = find_root(args.dir)
    if not args.command:
        print(tr("Lệnh kiểm tra: {v}", v=load_config(root).verify.command or tr("(tắt)")))
        return 0
    cmd = " ".join(args.command)
    save_project_setting(root, "verify_command", None if cmd in ("off", "-") else cmd)
    print(tr("Lệnh kiểm tra của dự án: {v}", v=load_config(root).verify.command or tr("(tắt)")))
    return 0


def cmd_usage(args) -> int:
    import time as _t
    from .limits import load_cooldowns
    db = open_db(find_root(args.dir))
    for label, since in ((tr("7 ngày"), _t.time() - 7 * 86400), (tr("24 giờ"), _t.time() - 86400)):
        print(f"{label}:")
        for name, r in db.usage(since).items():
            tok = (r["prompt_chars"] + r["output_chars"]) // 4
            print(tr("  {name:12} {v:>4} lượt  {v2:>5} phút  ~{v3}k token  lỗi {v4}  hết hạn mức "
                     "{v5}", name=name, v=r['runs'], v2=int(r['secs']) // 60, v3=tok // 1000, v4=r['failed'], v5=r['ratelimits']))
    cds = load_cooldowns()
    print(tr("Đang tạm nghỉ: ") + (", ".join(tr("{a} đến {v}", a=a, v=_t.strftime('%H:%M %d/%m', _t.localtime(t)))
                                         for a, t in cds.items()) or tr("không")))
    if args.local:
        return 0
    # hạn mức thật do CLI của từng agent báo (song song, in theo thứ tự xong trước)
    orch = _orch(args)

    def done(name: str, cmd: str, lines: list[str]) -> None:
        note = reports.agent_note(orch.cfg, name)
        print(f"\n📊 {name}" + (f"  ({cmd})" if cmd else "") + (f"  · {note}" if note else ""))
        for ln in lines:
            print("  " + ln)
    asyncio.run(orch.usage_all(on_done=done))
    return 0


def cmd_update(args) -> int:
    from .update import run_update
    ok, msg = asyncio.run(run_update(print, force=args.force))
    print(("✓ " if ok else "ℹ ") + msg)
    from . import __version__ as cur
    return 0 if ok or msg == tr("Đang dùng bản mới nhất ({version}).", version=cur) else 1


def cmd_cooldown(args) -> int:
    from .limits import save_cooldown
    import time as _t
    if args.minutes in (None, "off", "0", "-"):
        save_cooldown(args.agent, None)
        print(tr("{agent} hoạt động lại.", agent=args.agent))
    else:
        save_cooldown(args.agent, _t.time() + int(args.minutes) * 60)
        print(tr("{agent} tạm nghỉ {minutes} phút.", agent=args.agent, minutes=args.minutes))
    return 0


# ---------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ateam", description=tr("AI Team — điều phối nhiều AI agent CLI."))
    p.add_argument("--version", action="version", version=f"ateam {__version__}")
    p.add_argument("-C", "--dir", help=tr("thư mục dự án (mặc định: thư mục hiện tại)"))
    p.add_argument("--lang", choices=LANGS, help=tr("ngôn ngữ giao diện cho lần chạy này (vi | en)"))
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("tui", help=tr("mở giao diện terminal (mặc định)"))
    s = sub.add_parser("web", help=tr("mở giao diện web trên trình duyệt (http://127.0.0.1:PORT, cần aiohttp)"))
    s.add_argument("--port", type=int, default=8000,
                   help=tr("cổng (mặc định 8000; bận thì tự dùng cổng kế tiếp)"))
    s.add_argument("--open", action="store_true", help=tr("tự mở trình duyệt"))
    s.add_argument("--tui", action="store_true", help=tr("giao diện terminal trong trình duyệt (cần textual-serve)"))
    s.add_argument("--host", default="127.0.0.1",
                   help=tr("địa chỉ nghe, vd 0.0.0.0 để mở từ điện thoại trong LAN (bật token)"))
    s.add_argument("--tunnel", action="store_true",
                   help=tr("mở Cloudflare Tunnel (cloudflared, https, không cần tài khoản) + in mã QR"))
    s.add_argument("--public-url", default="",
                   help=tr("địa chỉ công khai khi bạn tự chạy named tunnel / domain riêng (bật token)"))
    s.add_argument("--readonly", action="store_true", help=tr("chỉ cho xem, không thao tác"))
    s.add_argument("--new-token", action="store_true", help=tr("tạo token mới (thiết bị cũ phải quét lại)"))
    s = sub.add_parser("lang", help=tr("xem / đổi ngôn ngữ giao diện (vi | en), lưu cho các lần sau"))
    s.add_argument("code", nargs="?")
    sub.add_parser("setup", help=tr("mở giao diện ở màn hình thiết lập: agent, trưởng nhóm, model, "
                                    "effort"))
    s = sub.add_parser("init", help=tr("tạo file cấu hình; --overview: trưởng nhóm viết bản tổng quan dự án"))
    s.add_argument("--project", action="store_true", help=tr("tạo thêm .ateam/config.toml cho dự án"))
    s.add_argument("--overview", action="store_true",
                   help=tr("trưởng nhóm tìm hiểu dự án, viết .ateam/project.md gửi kèm mọi kế hoạch & task "
                           "(như /init trong giao diện)"))
    s.add_argument("focus", nargs="*", help=tr("điều cần tìm hiểu kỹ (tuỳ chọn, cùng --overview)"))
    sub.add_parser("doctor", help=tr("kiểm tra các agent đã cài chưa"))
    s = sub.add_parser("goal", help=tr("giao mục tiêu và chạy không cần giao diện"))
    s.add_argument("text", nargs="+")
    s.add_argument("-y", "--yes", action="store_true", help=tr("không hỏi duyệt kế hoạch"))
    s.add_argument("-q", "--quiet", action="store_true", help=tr("không in log chi tiết của agent"))
    s = sub.add_parser("continue", help=tr("tiếp tục mục tiêu (m12) hoặc thread /task (t40) đã xong"))
    s.add_argument("ref", help=tr("m<số> = mục tiêu, t<số> = task"))
    s.add_argument("text", nargs="+", help=tr("yêu cầu mới"))
    s.add_argument("-y", "--yes", action="store_true", help=tr("không hỏi duyệt kế hoạch"))
    s.add_argument("-q", "--quiet", action="store_true")
    s = sub.add_parser("flow", help=tr("chạy mục tiêu theo workflow tuỳ chỉnh (không cần giao diện)"))
    s.add_argument("workflow")
    s.add_argument("text", nargs="+")
    s.add_argument("-y", "--yes", action="store_true", help=tr("tự duyệt các bước"))
    s.add_argument("-q", "--quiet", action="store_true")
    sub.add_parser("flows", help=tr("liệt kê workflow tuỳ chỉnh"))
    s = sub.add_parser("add", help=tr("thêm 1 task vào bảng (agent cũng gọi được lệnh này)"))
    s.add_argument("--to", required=True, help=tr("tên agent"))
    s.add_argument("--title")
    s.add_argument("--model", help=tr("model riêng cho task này"))
    s.add_argument("--effort", help=tr("effort riêng cho task này"))
    s.add_argument("prompt", nargs="+")
    s = sub.add_parser("set", help=tr("đặt model / effort mặc định cho 1 agent"))
    s.add_argument("agent")
    s.add_argument("--model", help=tr("tên model, '-' để về mặc định"))
    s.add_argument("--effort", help=tr("mức effort, '-' để về mặc định"))
    s = sub.add_parser("models", help=tr("xem model / effort mỗi agent hỗ trợ"))
    s.add_argument("agent", nargs="?")
    s.add_argument("--refresh", action="store_true",
                   help=tr("hỏi CLI danh sách model thật (opencode models, agy models)"))
    s = sub.add_parser("note", help=tr("ghi chú chung cho cả đội"))
    s.add_argument("text", nargs="+")
    s = sub.add_parser("compact", help=tr("trưởng nhóm tóm tắt ghi chú & mục tiêu thành 1 ghi chú "
                                          "ngắn"))
    s.add_argument("focus", nargs="*", help=tr("điều cần giữ trong bản tóm tắt (tuỳ chọn)"))
    sub.add_parser("list", help=tr("liệt kê mục tiêu và task"))
    s = sub.add_parser("log", help=tr("in log của 1 task (hoặc 'sys')"))
    s.add_argument("id")
    s = sub.add_parser("diff", help=tr("xem thay đổi của 1 task"))
    s.add_argument("id")
    s = sub.add_parser("merge", help=tr("merge task đang chờ duyệt"))
    s.add_argument("id")
    s = sub.add_parser("reject", help=tr("từ chối task đang chờ duyệt (kèm góp ý = giao làm lại)"))
    s.add_argument("id")
    s.add_argument("feedback", nargs="*")
    s = sub.add_parser("verify", help=tr("đặt lệnh kiểm tra sau mỗi task cho dự án (off = tắt)"))
    s.add_argument("command", nargs="*")
    s = sub.add_parser("usage", help=tr("thống kê lượt chạy và hạn mức theo agent (hỏi cả CLI của "
                                        "từng agent)"))
    s.add_argument("--local", action="store_true", help=tr("chỉ thống kê của ateam, không hỏi các CLI"))
    s = sub.add_parser("update", help=tr("cập nhật ateam lên bản mới nhất"))
    s.add_argument("--force", action="store_true", help=tr("cài lại kể cả khi đã là bản mới nhất"))
    s = sub.add_parser("cooldown", help=tr("cho agent tạm nghỉ N phút, hoặc 'off'"))
    s.add_argument("agent")
    s.add_argument("minutes", nargs="?")
    s = sub.add_parser("run", help=tr("chạy hết các task đang chờ rồi thoát"))
    s.add_argument("-q", "--quiet", action="store_true")

    args = p.parse_args(argv)
    if args.lang:
        set_lang(args.lang)
    handlers = {None: cmd_tui, "tui": cmd_tui, "web": cmd_web, "lang": cmd_lang, "setup": cmd_tui, "init": cmd_init, "doctor": cmd_doctor,
                "goal": cmd_goal, "flow": cmd_goal, "continue": cmd_goal, "flows": cmd_flows, "add": cmd_add, "note": cmd_note,
                "compact": cmd_compact, "list": cmd_list,
                "log": cmd_log, "run": cmd_run, "set": cmd_set, "models": cmd_models, "diff": cmd_diff,
                "merge": cmd_merge, "reject": cmd_reject, "verify": cmd_verify,
                "usage": cmd_usage, "update": cmd_update, "cooldown": cmd_cooldown}
    try:
        return handlers[args.cmd](args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
