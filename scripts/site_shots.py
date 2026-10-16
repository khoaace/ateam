#!/usr/bin/env python3
"""Chụp ảnh màn hình app thật cho trang docs (site/shots/*.svg).

Dựng một dự án demo nhỏ + các CLI agent giả lập có nội dung "thật" (thêm đăng nhập Google), mở TUI bằng
`App.run_test()` và `save_screenshot()` ở từng màn hình: bảng việc, tab Đội, hỏi đáp /grill, tab Code, tab
Git, màn hình diff, chọn theme. Không gọi CLI agent thật. Chạy lại khi giao diện đổi:

    python scripts/site_shots.py            # ghi đè site/shots/*.svg
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
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
  for l in "Đọc app/__init__.py, app/models.py" "Thêm app/auth/google.py: route /auth/google, /auth/callback" \
           "Kiểm tra state chống CSRF, lưu next để quay lại trang trước" "Đăng ký blueprint trong create_app()" \
           "Chạy pytest -q tests/test_auth.py" "4 passed in 0.41s" "Rà lại xử lý lỗi khi Google trả về error=access_denied" \
           "Thêm abort(400) khi state không khớp"; do echo "$l"; slow; done
  echo "SUMMARY: Thêm OAuth Google: /auth/google, /auth/callback, lưu user + phiên"; exit 0
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


def make_bin(base: Path) -> Path:
    bindir = base / "bin"
    bindir.mkdir()
    for name in ("claude", "codex", "agy", "grok", "opencode"):
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
        save(app, "team")
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
        asyncio.run(shoot(base, proj))
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
