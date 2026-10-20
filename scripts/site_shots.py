#!/usr/bin/env python3
"""Chụp ảnh màn hình app thật cho trang docs (site/shots/*.svg).

Dựng một dự án demo nhỏ + các CLI agent giả lập có nội dung "thật" (thêm đăng nhập Google), mở TUI bằng
`App.run_test()` và `save_screenshot()` ở từng màn hình: bảng việc, tab Đội, hỏi đáp /grill, tab Code, tab
Git, màn hình diff, chọn theme. Không gọi CLI agent thật. Chạy lại khi giao diện đổi:

    python scripts/site_shots.py            # ghi đè site/shots/*.svg
    python scripts/site_shots.py --web      # ảnh giao diện web: site/shots/web-*.webp

`--web` chạy `ateam web` trên dự án demo và chụp bằng Chrome headless qua DevTools protocol (cần aiohttp và
Google Chrome/Chromium; đặt biến CHROME nếu Chrome nằm chỗ khác).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "shots"
SIZE = (150, 42)

# ------------------------------------------------------------------ CLI agent giả lập cho demo
AGENT = r'''#!/usr/bin/env bash
name="$(basename "$0")"
P="${@: -1}"
prev=""; for a in "$@"; do [ "$prev" = "-p" ] && P="$a"; prev="$a"; done  # claude/agy: prompt sau -p
case "$P" in --version) echo "$name 1.0.0"; exit 0 ;; --help) echo "Usage: $name"; exit 0 ;; esac
case "${1:-}" in
  models) case "$name" in
            opencode) printf 'xai/grok-build-0.1\nxai/grok-4.7\nanthropic/claude-sonnet-5-5\n' ;;
            agy) printf 'gemini-3-pro\ngemini-3-flash\n' ;;
            *) printf '  * grok-4.7 (default)\n  - grok-4.6\n' ;;
          esac; exit 0 ;;
  debug) echo '{"models":[{"slug":"gpt-6.1","visibility":"list"},{"slug":"gpt-6-mini","visibility":"list"}]}'; exit 0 ;;
esac
slow() { sleep "${DEMO_SLOW:-0.8}"; }
if [ -t 0 ] && [ -t 1 ]; then  # chạy tương tác trong pty (tab Lưới): màn hình CLI giả
  C=$'\e[36m'; G=$'\e[32m'; Y=$'\e[33m'; D=$'\e[2m'; B=$'\e[1m'; R=$'\e[0m'
  printf '%s%s ● %s%s  %sv1.0.0%s\n%s~/code/so-tay-nhom%s\n\n' "$B" "$C" "$name" "$R" "$D" "$R" "$D" "$R"
  case "$name" in
    claude) printf '%s>%s Tóm tắt các route đăng nhập\n\n%s●%s Đọc %sapp/auth/google.py%s\n%s●%s Có 2 route: %s/auth/google%s (chuyển sang Google) và\n  %s/auth/callback%s (nhận mã, tạo phiên).\n  Đang kiểm tra %sstate%s chống CSRF…\n' "$Y" "$R" "$G" "$R" "$C" "$R" "$G" "$R" "$C" "$R" "$C" "$R" "$C" "$R" ;;
    codex) printf '%s>%s Viết test cho /auth/callback\n\n%s•%s Tạo %stests/test_auth.py%s\n%s•%s Chạy %spytest -q%s\n  %s....  4 passed in 0.41s%s\n' "$Y" "$R" "$G" "$R" "$C" "$R" "$G" "$R" "$C" "$R" "$G" "$R" ;;
    agy) printf '%s>%s Dựng nút "Đăng nhập với Google"\n\n%s✓%s Cập nhật %sapp/templates/login.html%s\n%s✓%s Thêm style cho nút\n' "$Y" "$R" "$G" "$R" "$C" "$R" "$G" "$R" ;;
    grok) printf '%s>%s Cập nhật README\n\n%s•%s Thêm mục "Đăng nhập bằng Google"\n%s•%s Hướng dẫn đặt %sGOOGLE_CLIENT_ID%s\n' "$Y" "$R" "$G" "$R" "$G" "$R" "$C" "$R" ;;
    *) printf '%s>%s Sẵn sàng\n' "$Y" "$R" ;;
  esac
  printf '\n%s> %s' "$B" "$R"
  exec sleep 900
fi
if [[ "$P" == *"you INTERVIEW the user"* ]]; then
  n=$(printf '%s\n' "$P" | grep -cE '^A[0-9]+:' || true)
  if [ "$n" = 0 ]; then
    echo '{"question": "Người dùng đăng nhập bằng gì?", "why": "Quyết định có cần trang đăng ký và lưu mật khẩu hay không.", "options": ["Chỉ Google (OAuth)", "Google + email/mật khẩu", "Google, GitHub và email"], "recommended": "Chỉ Google (OAuth)"}'
  else
    echo '{"question": "Sau khi đăng nhập thì chuyển người dùng tới đâu?", "why": "Ảnh hưởng tới redirect URI và route cần bảo vệ.", "options": ["Trang trước đó", "Dashboard", "Trang hồ sơ"], "recommended": "Trang trước đó"}'
  fi
  exit 0
fi
if [[ "$P" == *"Reply with ONLY a JSON array"* ]]; then
  echo "Đang đọc cấu trúc dự án…"; slow
  cat <<'J'
[{"id":1,"agent":"codex","title":"API đăng nhập Google OAuth","prompt":"Thêm route /auth/google và /auth/callback dùng OAuth 2.0, lưu phiên đăng nhập.","depends_on":[],"effort":"high"},
 {"id":2,"agent":"antigravity","title":"Nút & trang đăng nhập","prompt":"Trang /login với nút Đăng nhập bằng Google, hiện avatar khi đã đăng nhập.","depends_on":[]},
 {"id":3,"agent":"grok","title":"Test luồng đăng nhập","prompt":"Viết test cho callback OAuth: thành công, sai state, hết hạn.","depends_on":[1]},
 {"id":4,"agent":"opencode","title":"Cập nhật README","prompt":"Thêm hướng dẫn cấu hình GOOGLE_CLIENT_ID vào README.","depends_on":[1,2]}]
J
  exit 0
fi
if [[ "$P" == *"Review round"* ]]; then echo '{"done": true, "summary": "Đủ: API, giao diện, test, tài liệu.", "new_tasks": []}'; exit 0; fi
if [[ "$P" == *"git COMMIT MESSAGE"* ]]; then printf 'SUMMARY:\nThêm đăng nhập bằng Google (OAuth 2.0)\n'; exit 0; fi
if [ "$name" = codex ]; then
  mkdir -p app/auth
  cat > app/auth/google.py <<'PY'
"""Đăng nhập bằng Google (OAuth 2.0, authorization code + PKCE)."""

from __future__ import annotations

import os
import secrets

from flask import Blueprint, abort, redirect, request, session, url_for

from app.auth.oauth import OAuthClient
from app.models import User, db

bp = Blueprint("google_auth", __name__, url_prefix="/auth")

google = OAuthClient(
    client_id=os.environ["GOOGLE_CLIENT_ID"],
    client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    scope="openid email profile",
)


@bp.get("/google")
def login():
    """Chuyển người dùng sang trang đồng ý của Google."""
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    session["next"] = request.args.get("next", url_for("home.index"))
    return redirect(google.authorize_redirect(url_for(".callback", _external=True), state=state))


@bp.get("/callback")
def callback():
    if request.args.get("state") != session.pop("oauth_state", None):
        abort(400, "state không khớp")
    token = google.fetch_token(code=request.args["code"])
    info = google.userinfo(token)
    user = User.query.filter_by(email=info["email"]).first()
    if user is None:
        user = User(email=info["email"], name=info.get("name", ""), avatar=info.get("picture"))
        db.session.add(user)
    db.session.commit()
    session["user_id"] = user.id
    return redirect(session.pop("next", "/"))
PY
  python3 - <<'PY'
import re
p = "app/__init__.py"
s = open(p).read()
if "google_bp" not in s:
    s = s.replace("from app.home import bp as home_bp\n", "from app.auth.google import bp as google_bp\nfrom app.home import bp as home_bp\n")
    s = s.replace("    app.register_blueprint(home_bp)\n", "    app.register_blueprint(home_bp)\n    app.register_blueprint(google_bp)\n")
open(p, "w").write(s)
PY
  cat <<'MD'
### Kế hoạch
1. Đọc `app/__init__.py`, `app/models.py`
2. Thêm `app/auth/google.py`: route **/auth/google**, **/auth/callback**
3. Đăng ký blueprint trong `create_app()`
MD
  slow
  cat <<'MD'

### Đã làm
- **OAuth 2.0 + PKCE**: kiểm tra `state` chống CSRF, lưu `next` để quay lại trang trước
- **Người dùng mới**: tạo `User` từ `email`, `name`, `picture`
  - Google trả về `error=access_denied` → `abort(400)`
MD
  slow
  cat <<'MD'

### Kiểm tra
```text
$ pytest -q tests/test_auth.py
....                                                         [100%]
4 passed in 0.41s
```

| Route | Việc |
|---|---|
| `/auth/google` | chuyển sang trang đồng ý của Google |
| `/auth/callback` | đổi `code` lấy token, lưu phiên |

<<<NOTE>>>[codex] Cần đặt `GOOGLE_CLIENT_ID` và `GOOGLE_CLIENT_SECRET` trong `.env`; redirect URI cho dev: http://localhost:5000/auth/callback<<<END>>>
MD
  echo "SUMMARY: Thêm OAuth Google: **/auth/google**, **/auth/callback**, lưu user + phiên"; exit 0
fi
if [ "$name" = agy ]; then
  mkdir -p app/templates
  cat > app/templates/login.html <<'H'
{% extends "base.html" %}
{% block content %}
<section class="login">
  <h1>Chào mừng trở lại</h1>
  <a class="btn-google" href="{{ url_for('google_auth.login', next=next) }}">
    <img src="/static/google.svg" alt=""> Đăng nhập bằng Google
  </a>
</section>
{% endblock %}
H
  for l in "Xem app/templates/base.html để dùng chung layout" "Tạo app/templates/login.html" \
           "Thêm nút Đăng nhập bằng Google theo hướng dẫn thương hiệu của Google" "Hiện avatar + tên ở header khi đã đăng nhập" \
           "Kiểm tra giao diện ở 375px và 1280px" "Thêm trạng thái hover/focus cho nút" \
           "Đổi màu nút theo theme tối" "Thêm aria-label cho nút đăng nhập" "Chụp lại giao diện để so sánh" \
           "Rút gọn CSS trùng lặp trong login.css"; do echo "$l"; slow; done
  echo "SUMMARY: Trang /login và nút Đăng nhập bằng Google"; exit 0
fi
if [ "$name" = grok ]; then
  for l in "Đọc app/auth/google.py" "Viết tests/test_auth.py: callback thành công, sai state, hết hạn" \
           "Giả lập Google bằng responses" "pytest -q: 6 passed"; do echo "$l"; slow; done
  echo "SUMMARY: 6 test cho luồng đăng nhập Google"; exit 0
fi
for l in "Đọc README.md" "Thêm mục Đăng nhập bằng Google: tạo OAuth client, GOOGLE_CLIENT_ID/SECRET" \
         "Thêm redirect URI cho môi trường dev"; do echo "$l"; slow; done
echo "SUMMARY: README: hướng dẫn cấu hình đăng nhập Google"
'''

PROJECT = {
    "app/__init__.py": '''from flask import Flask

from app.home import bp as home_bp
from app.models import db


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_prefixed_env()
    db.init_app(app)
    app.register_blueprint(home_bp)
    return app
''',
    "app/home.py": '''from flask import Blueprint, render_template

bp = Blueprint("home", __name__)


@bp.get("/")
def index():
    return render_template("index.html")
''',
    "app/models.py": '''from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(120), default="")
    avatar = db.Column(db.String(500))
''',
    "README.md": "# Sổ tay nhóm\n\nỨng dụng Flask nhỏ để ghi chú cho nhóm.\n",
    "requirements.txt": "flask>=3.0\nflask-sqlalchemy>=3.1\n",
}


def sh(cwd: Path, *args: str) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def make_project(base: Path) -> Path:
    proj = base / "so-tay-nhom"
    for rel, text in PROJECT.items():
        p = proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    sh(proj, "git", "init", "-q", "-b", "main")
    sh(proj, "git", "-c", "user.name=demo", "-c", "user.email=demo@example.com", "add", ".")
    sh(proj, "git", "-c", "user.name=demo", "-c", "user.email=demo@example.com", "commit", "-qm", "Khởi tạo dự án")
    return proj


CUSTOM = """[agents.gemini-cli]
command = ["gemini", "-p", "{prompt}"]
role = "Viết tài liệu, dịch thuật, tóm tắt"
efforts = ["low", "high"]

[workflows.tinh-nang-moi]
description = "Tính năng mới: thiết kế → code → test → tài liệu"
review = true

[[workflows.tinh-nang-moi.steps]]
agent = "lead"
title = "Thiết kế {goal}"
prompt = "Thiết kế ngắn gọn: {goal}"

[[workflows.tinh-nang-moi.steps]]
agent = "codex"
title = "Viết code"
prompt = "Cài đặt theo thiết kế: {goal}"

[[workflows.tinh-nang-moi.steps]]
agent = "grok"
title = "Viết test"
prompt = "Viết test cho: {goal}"

[workflows.sua-loi]
description = "Sửa lỗi: tái hiện → sửa → test chống tái diễn"
review = false

[[workflows.sua-loi.steps]]
agent = "codex"
title = "Tái hiện lỗi"
prompt = "Tái hiện: {goal}"

[[workflows.sua-loi.steps]]
agent = "codex"
title = "Sửa và thêm test"
prompt = "Sửa lỗi và thêm test chống tái diễn: {goal}"
"""


def seed_demo(proj: Path) -> None:
    """Agent/workflow tuỳ chỉnh (trang Agents, Workflows) + to-do và ghi chú (tab To-do, Ghi chú)."""
    import datetime as dt

    from ateam import notes, todos
    from ateam.config import CUSTOM_FILE
    CUSTOM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CUSTOM_FILE.write_text(CUSTOM, encoding="utf-8")
    today = dt.date.today()

    def due(days: int, hm: str = "") -> str:
        return (today + dt.timedelta(days=days)).isoformat() + (("T" + hm) if hm else "")

    for text, extra in (
        ("Sửa lỗi đăng xuất không xoá cookie #bug !cao", {"due": due(-1, "17:00"), "desc": "Cookie `session` vẫn còn sau `/logout`.\n- Kiểm tra `Set-Cookie` max-age\n- Thêm test"}),
        ("Duyệt PR đăng nhập Google #review !cao", {"due": due(0, "15:00")}),
        ("Viết tài liệu cấu hình OAuth #docs", {"due": due(0, "17:30"), "priority": 2}),
        ("Thêm giới hạn tốc độ cho /auth/callback #bug", {"due": due(2), "priority": 2}),
        ("Chuyển CI sang chạy song song #hạ-tầng", {"due": due(4)}),
        ("Dọn các nhánh ateam/* cũ #hạ-tầng !thấp", {"due": due(9)}),
        ("Đặt tên lại bảng users → accounts #db", {}),
    ):
        todos.apply(proj, "add", dict({"text": text}, **extra))
    items = todos.load(proj)
    todos.apply(proj, "toggle", {"id": items[-1]["id"]}) if False else None
    todos.apply(proj, "add", {"text": "Thêm trang hồ sơ người dùng #feature"})
    todos.apply(proj, "toggle", {"id": todos.load(proj)[-1]["id"]})
    n = notes.apply(proj, "add", {"title": "Quyết định: đăng nhập chỉ bằng Google", "tags": ["docs"], "body":
        "# Quyết định đăng nhập\n\nChọn **chỉ Google (OAuth 2.0 + PKCE)** vì:\n\n- không phải lưu mật khẩu\n- ít bề mặt tấn công hơn\n- người dùng nội bộ đều có tài khoản Google\n\n## Việc còn lại\n\n- [ ] Trang lỗi khi `access_denied`\n- [ ] Ghi `GOOGLE_CLIENT_ID` vào README\n\n```python\nSCOPES = [\"openid\", \"email\", \"profile\"]\n```\n"})
    notes.apply(proj, "pin", {"id": n["id"], "on": True})
    notes.apply(proj, "add", {"title": "Câu hỏi cho buổi review", "tags": ["review"], "body":
        "- Có cần đăng xuất ở mọi thiết bị?\n- Thời hạn phiên: 7 ngày hay 30 ngày?\n"})
    notes.apply(proj, "add", {"title": "Ý tưởng: nhắc việc qua email", "tags": ["feature"], "body": "Gửi email tóm tắt việc quá hạn mỗi sáng."})


def make_bin(base: Path) -> Path:
    bindir = base / "bin"
    bindir.mkdir()
    for name in ("claude", "codex", "agy", "grok", "opencode", "gemini"):
        p = bindir / name
        p.write_text(AGENT, encoding="utf-8")
        p.chmod(0o755)
    return bindir


def clean_svg(path: Path, base: Path) -> None:
    """Bỏ khoảng trắng đầu dòng cho nhẹ; đường dẫn thư mục tạm -> ~/code."""
    text = path.read_text(encoding="utf-8").replace(str(base), "~/code")
    text = re.sub(r"\n\s+", "\n", text)
    path.write_text(text, encoding="utf-8")


async def shoot(base: Path, proj: Path) -> None:
    from ateam.config import ensure_global_config, load_config, mark_setup_done
    from ateam.db import DB
    from ateam.tui import TeamApp

    ensure_global_config()
    try:
        mark_setup_done()
    except Exception:
        pass
    seed_demo(proj)

    async def wait(pilot, cond, n=150):
        for _ in range(n):
            await pilot.pause(0.1)
            if cond():
                return True
        return False

    def save(app, name: str) -> None:
        app.save_screenshot(filename=f"{name}.svg", path=str(OUT))
        clean_svg(OUT / f"{name}.svg", base)
        print("  ✓", name)

    # 1) hỏi đáp /grill (dự án riêng để bảng việc chính gọn)
    gproj = make_project(base / "g")
    app = TeamApp(gproj, load_config(gproj), DB(gproj / ".ateam/team.db"))
    async with app.run_test(size=SIZE) as pilot:
        await wait(pilot, lambda: app._booted)
        app.sub_title = "~/code/so-tay-nhom"
        app.run_command("/grill Thêm đăng nhập bằng Google")
        await wait(pilot, lambda: app.query_one("#grill").question is not None)
        await pilot.pause(0.5)
        save(app, "grill")

    # 2) mục tiêu chạy thật: kế hoạch -> duyệt -> các agent làm song song
    app = TeamApp(proj, load_config(proj), DB(proj / ".ateam/team.db"))
    async with app.run_test(size=SIZE) as pilot:
        await wait(pilot, lambda: app._booted)
        app.sub_title = "~/code/so-tay-nhom"
        app.start_goal("Thêm đăng nhập bằng Google, có test và cập nhật README")
        await wait(pilot, lambda: any(t.status == "draft" for t in app.db.tasks()))
        await pilot.pause(0.6)
        save(app, "plan")
        app.action_approve()
        await wait(pilot, lambda: sum(t.status == "running" for t in app.db.tasks()) >= 2)
        await pilot.pause(4.5)
        tasks = app.db.tasks()
        first = next(t for t in tasks if t.status == "running")
        app.show_task(first.id)
        await pilot.pause(0.6)
        save(app, "board")
        app.action_toggle_tab()
        await pilot.pause(1.0)
        save(app, "agents")
        app.query_one("#tabs").active = "tab-custom"
        await pilot.pause(1.0)
        save(app, "workflows")
        app.query_one("#tabs").active = "tab-todo"
        await pilot.pause(1.0)
        save(app, "todo")
        app.query_one("#tabs").active = "tab-notes"
        await pilot.pause(1.0)
        save(app, "notes")
        app.run_command("/code @app/auth/google.py:35")
        await wait(pilot, lambda: app.code_editor().buffer is not None)
        await pilot.pause(0.8)
        await pilot.press("V", "j", "j")
        await pilot.pause(0.4)
        save(app, "code")
        await pilot.press("escape")
        app.run_command("/git")
        await wait(pilot, lambda: app.git_status is not None and app.git_status.files)
        await pilot.pause(0.8)
        save(app, "git")
        gl = app.query_one("#git-files")
        gl.focus()
        gl.highlighted = next(i for i in range(gl.option_count)
                              if (gl.get_option_at_index(i).id or "").endswith("app/__init__.py"))
        await app.action_git_diff()
        await pilot.pause(1.0)
        save(app, "diff")
        app.pop_screen()
        app.query_one("#tabs").active = "tab-board"
        await pilot.pause(0.5)
        app.apply_theme("tokyo-night", "purple")
        app.action_open_theme()
        await pilot.pause(0.8)
        save(app, "theme")
        app.screen.close()
        await app.action_quit()


# ------------------------------------------------------------------ giao diện web (ateam web + Chrome headless)
GOAL = "Thêm đăng nhập bằng Google, có test và cập nhật README"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_chrome() -> str:
    for c in (os.environ.get("CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")):
        if c and Path(c).exists():
            return c
    raise SystemExit("Không thấy Chrome/Chromium — đặt biến CHROME=<đường dẫn>")


# đường dẫn thư mục tạm trên trang -> ~/code (như clean_svg)
SCRUB = r"""(() => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n;
  while ((n = w.nextNode())) n.nodeValue = n.nodeValue.replace(/\/\S*?ateam-shots-[^\/\s]+/g, "~/code"); })()"""


class CDP:
    """Client DevTools protocol tối thiểu: gọi lệnh, đợi kết quả, bỏ qua sự kiện."""

    def __init__(self, ws):
        self.ws, self.seq = ws, 0

    async def call(self, method: str, **params):
        self.seq += 1
        await self.ws.send_json({"id": self.seq, "method": method, "params": params})
        while True:
            m = json.loads((await self.ws.receive()).data)
            if m.get("id") == self.seq:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})

    async def js(self, expr: str):
        r = await self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(f"{expr}: {r['exceptionDetails']}")
        return r.get("result", {}).get("value")

    async def until(self, expr: str, n: int = 200) -> None:
        for _ in range(n):
            if await self.js(f"!!({expr})"):
                return
            await asyncio.sleep(0.1)
        raise RuntimeError(f"hết giờ chờ: {expr}")

    async def shot(self, name: str) -> None:
        await self.js(SCRUB)
        r = await self.call("Page.captureScreenshot", format="webp", quality=86)
        (OUT / f"{name}.webp").write_bytes(base64.b64decode(r["data"]))
        print("  ✓", name)


async def shoot_web(base: Path, proj: Path) -> None:
    import aiohttp

    from ateam.config import ensure_global_config, mark_setup_done

    ensure_global_config()
    mark_setup_done()
    seed_demo(proj)
    port, dport = free_port(), free_port()
    server = subprocess.Popen([sys.executable, "-m", "ateam", "-C", str(proj), "web", "--port", str(port)],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    chrome = subprocess.Popen([find_chrome(), "--headless=new", f"--remote-debugging-port={dport}",
                               f"--user-data-dir={base / 'chrome'}", "--hide-scrollbars", "--no-first-run",
                               *(["--no-sandbox"] if os.geteuid() == 0 else []),
                               "--window-size=1440,900", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        async with aiohttp.ClientSession() as http:
            ws_url = None
            for _ in range(100):
                try:
                    async with http.get(f"http://127.0.0.1:{dport}/json/list") as r:
                        pages = [p for p in await r.json() if p["type"] == "page"]
                    if pages:
                        ws_url = pages[0]["webSocketDebuggerUrl"]
                        break
                except aiohttp.ClientError:
                    pass
                await asyncio.sleep(0.1)
            if not ws_url:
                raise RuntimeError("Chrome không mở cổng DevTools")
            async with http.ws_connect(ws_url, max_msg_size=0) as ws:
                c = CDP(ws)
                await c.call("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=2,
                             mobile=False)
                await c.call("Emulation.setEmulatedMedia",
                             features=[{"name": "prefers-color-scheme", "value": "dark"}])
                for _ in range(100):  # đợi server lên
                    try:
                        async with http.get(f"http://127.0.0.1:{port}/") as r:
                            if r.status == 200:
                                break
                    except aiohttp.ClientError:
                        pass
                    await asyncio.sleep(0.1)
                await c.call("Page.navigate", url=f"http://127.0.0.1:{port}/")
                await c.until("typeof S !== 'undefined' && S.meta && S.state")
                # mục tiêu chạy thật: kế hoạch -> duyệt -> các agent làm song song
                await c.js(f"send('submit', {{text: {json.dumps(GOAL)}}})")
                await c.until("S.state.tasks.some((t) => t.status === 'draft')")
                await c.js("send('approve', {goal: S.state.goals[0].id})")
                await c.until("S.state.tasks.filter((t) => t.status === 'running').length >= 2")
                # log markdown của codex (tiêu đề, danh sách, khối code, bảng, NOTE, SUMMARY) khi nó vừa xong
                codex = "S.state.tasks.find((t) => t.agent === 'codex')"
                await c.until(f"!['queued', 'running'].includes({codex}.status)")
                await c.js(f"openTask({codex}.id)")
                await asyncio.sleep(1.0)
                await c.js("document.querySelector('#toasts').replaceChildren()")  # toast đè lên ngăn log
                await c.shot("web-board")
                await c.js("closeDrawer(); setView('code'); CodeView.open('app/auth/google.py', 35)")
                await c.until("document.querySelector('#code .cm-editor')")
                await asyncio.sleep(1.2)
                await c.shot("web-code")
                await c.js("setView('git')")
                await c.until("document.querySelectorAll('#git .gfile').length")
                await asyncio.sleep(1.0)
                await c.shot("web-git")
                await c.js("setView('team')")
                await c.until("document.querySelectorAll('#view-team .ag-row').length >= 6")
                await asyncio.sleep(0.8)
                await c.shot("web-agents")
                await c.js("setView('custom')")
                await c.until("document.querySelectorAll('#custom .c-row').length >= 2")
                await asyncio.sleep(0.6)
                await c.shot("web-workflows")
                await c.js("setView('todo')")
                await asyncio.sleep(1.2)
                await c.shot("web-todo")
                await c.js("setView('notes')")
                await asyncio.sleep(1.2)
                await c.js("NotesView.openNote(1)")
                await asyncio.sleep(1.2)
                await c.shot("web-notes")
                await c.js("setView('grid')")
                await asyncio.sleep(0.5)
                await c.js("send('grid_preset', {preset: 'cols2'})")
                for agent in ("claude", "codex", "antigravity", "grok"):
                    await c.js(f"send('grid_add', {{agent: {json.dumps(agent)}, resume: false}})")
                    await asyncio.sleep(0.4)
                await asyncio.sleep(3.0)
                await c.js("document.querySelector('#toasts').replaceChildren()")
                await c.shot("web-grid")
    finally:
        chrome.terminate()
        server.terminate()
        server.wait(10)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="ateam-shots-"))
    try:
        bindir = make_bin(base)
        proj = make_project(base)
        os.environ["PATH"] = f"{bindir}{os.pathsep}{os.environ['PATH']}"
        os.environ["XDG_CONFIG_HOME"] = str(base / "xdg")
        os.environ["ATEAM_LANG"] = os.environ.get("ATEAM_LANG", "vi")
        os.environ["DEMO_SLOW"] = "0.8"
        os.environ["GIT_AUTHOR_NAME"] = os.environ["GIT_COMMITTER_NAME"] = "demo"
        os.environ["GIT_AUTHOR_EMAIL"] = os.environ["GIT_COMMITTER_EMAIL"] = "demo@example.com"
        sys.path.insert(0, str(ROOT))
        print(f"Chụp màn hình vào {OUT.relative_to(ROOT)}/")
        asyncio.run(shoot_web(base, proj) if "--web" in sys.argv else shoot(base, proj))
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
