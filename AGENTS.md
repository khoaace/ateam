# AGENTS.md — hướng dẫn cho AI agent làm việc trên repo này

Đọc file này trước khi sửa bất cứ thứ gì. Nó là điểm vào; chi tiết nằm trong `docs/`.

## ateam là gì

Công cụ terminal (Python + Textual) điều phối nhiều AI coding agent CLI — Claude Code, Codex,
Antigravity (`agy`), Grok Build (`grok`), OpenCode, hoặc bất kỳ CLI nào có chế độ headless — làm việc như
một đội trên cùng một repo của người dùng:

- **Trưởng nhóm** (mặc định `claude`) lập kế hoạch thành task JSON, review kết quả, giao thêm việc;
  `/grill` cho trưởng nhóm hỏi người dùng từng câu để chốt đặc tả trước khi lập kế hoạch; thành viên hỏi
  giữa task bằng `<<<ASK>>>` (trạng thái `asking`); `/retry`, vòng sửa, `/continue` tiếp tục đúng phiên CLI (`--resume`).
- **Bảng việc** SQLite (`.ateam/team.db`) là nguồn sự thật duy nhất; TUI, CLI và agent cùng đọc/ghi.
- **Bộ lập lịch** chạy task theo phụ thuộc và giới hạn song song; agent giao việc chéo bằng
  khối `<<<DELEGATE …>>>` trong output.
- Tự chạy lệnh kiểm tra sau task (fail thì giao sửa), worktree + duyệt diff trước khi merge,
  phát hiện hết hạn mức và chuyển sang agent dự phòng.
- Chat 💬 trực tiếp với từng agent (tab 🤖 Agents, `/chat`): mỗi tin một lượt `--resume` đúng phiên CLI; ⌨ / `/term` mở CLI thật.
- Tab 🌿 Git quản lý git của dự án (stage, commit — AI viết message (trưởng nhóm hoặc agent chọn), nhánh, pull/push, stash, lịch sử).

Người dùng là developer Việt Nam, dùng macOS. **Mọi chữ hiển thị cho người dùng viết bằng tiếng Việt.**

## Bản đồ repo

| Đường dẫn | Nội dung |
| --- | --- |
| `ateam/cli.py` | Lệnh `ateam` (argparse): `tui` (mặc định, khoá 1 phiên/dự án), `web` (giao diện web; `--tui`: TUI qua textual-serve), `setup`, `goal`, `continue`, `add`, `run`, `diff`, `merge`, `reject`, `verify`, `usage`, `cooldown`, `set`, `doctor`, … |
| `ateam/tui.py` | Giao diện Textual: tab Bảng việc, tab 🤖 Agents (danh sách `AgentPane` — phóng to một ô để chat — + agent tuỳ chỉnh + Timeline), wizard thiết lập (`OnboardScreen`), popup chung (`BaseModal`, nút `Btn`), log co giãn (`ReflowLog`), xem lại kế hoạch (`PlanViewScreen`, `/plan`), tab ✅ To-do và 🗒 Ghi chú (`TodoPanel`, `NotesPanel`, `TagScreen` ở `tui_todo.py`, nạp muộn), agent/workflow tuỳ chỉnh (`CustomPanel(show=…)`: phần agent ở tab Agents, phần workflow ở tab 🔀 Workflows, cả hai ở popup `CustomScreen`; `AgentEditScreen`, `WorkflowEditScreen`, `DefaultFlowScreen`), tab 📊 Thống kê (`_refresh_dash`), thông báo (`show_notices`), lệnh `/…`, phím tắt |
| `ateam/web.py`, `web_git.py`, `web_code.py`, `web_setup.py`, `ateam/webui/` | `ateam web`: server aiohttp (một `Orchestrator` cho mọi tab, WebSocket đẩy ảnh chụp trạng thái, lệnh `/…` như TUI, `ui_strings()` cho chữ hiển thị) + trang HTML/CSS/JS thuần: `app.js` (Kanban, kế hoạch, /grill, trang Agents + popup chat, Terminal, gợi ý lệnh, thông báo), `git.js`, `dash.js` (Thống kê), `code.js` (CodeMirror + vim ở `webui/vendor/`, build bằng `scripts/editor/`; xterm.js cũng ở `vendor/`), `diff.js`, `setup.js` (/setup, trang Workflows, form agent tuỳ chỉnh, popup Luồng mặc định), `lofi.js` (nhạc lofi: radio YouTube/stream online), `todo.js` (tab To-do, Quản lý tag, popup lịch — `TD` dùng chung; nút nổi ✅ + popover việc chưa xong — `TodoPop`), `notes.js` (tab Ghi chú) |
| `ateam/web_auth.py`, `ateam/qr.py` | `ateam web` từ xa (`--host`, `--tunnel` Cloudflare, `--public-url`, `--readonly`): token `.ateam/web_token` → cookie, chặn Origin lạ, khoá khi sai nhiều, chạy cloudflared; mã QR thuần Python (terminal + SVG, nút 📱) |
| `ateam/wizard.py`, `ateam/reports.py` | Logic dùng chung TUI ↔ web: wizard /setup, form /custom, popup Luồng mặc định (`wizard`); /usage, dashboard + lịch sử mục tiêu, /agents, /flow, /models, gợi ý /continue (`reports`) |
| `ateam/orchestrator.py` | Lõi: lập kế hoạch, `tick()` lập lịch, `_run_task`, verify, worktree/merge, hạn mức, review |
| `ateam/runner.py` | `Run`: chạy 1 tiến trình (pipe hoặc pty), stream từng dòng, timeout, huỷ theo process group |
| `ateam/grid.py`, `ateam/vterm.py`, `ateam/tui_grid.py`, `ateam/webui/grid.js` | Tab 🔲 Lưới (`/grid`): mỗi ô là CLI tương tác thật của một agent trong pty. `grid.py`: bố cục cột/ô, preset, lưu `.ateam/grid.json`, `GridHub` giữ phiên pty + buffer cho cả TUI lẫn web; `vterm.py`: giả lập terminal VT100/xterm thuần Python cho TUI; `tui_grid.py`: `GridPanel`, `TermView`, `GridAddScreen`; `grid.js`: lưới xterm.js, kéo thả, kéo khe đổi kích thước |
| `ateam/pty_session.py`, `ateam/logtail.py` | `PtySession`: tiến trình tương tác trong pty nối hai chiều với xterm.js ("Mở trong terminal" ở web, chat 💬); `read_tail`/`read_log_tail`: đọc phần cuối file log |
| `ateam/config.py` | `DEFAULT_CONFIG` (TOML), dataclass `Config`/`AgentConfig`/`VerifyConfig`/`Workflow`, `AgentConfig.argv()`, state.json, custom.toml (agent/workflow tuỳ chỉnh, mẫu) |
| `ateam/db.py` | Schema SQLite + migration cột, `Task`/`Goal`, thống kê `runs` |
| `ateam/prompts.py` | Prompt gửi trưởng nhóm/thành viên (tiếng Anh) + bóc JSON, DELEGATE, NOTE, SUMMARY |
| `ateam/shell.py` | Lệnh terminal của người dùng (`!lệnh`, tab 💻 Terminal): `ShellManager` chạy qua `Run` (pty, huỷ process group), gợi ý script package.json/Makefile, bắt port |
| `ateam/gitops.py` | Tab 🌿 Git + `/git`, `/commit`, `/push`…: `GitRepo` (status porcelain v2, stage/unstage/bỏ thay đổi, commit/amend, nhánh, merge, fetch/pull/push, stash, revert, bỏ commit cuối) — async, không hỏi mật khẩu; màn hình ở `tui.py` (`GitFileList`, `GitLogList`, `GitBranchScreen`, `GitStashScreen`, `ConfirmScreen`) |
| `ateam/editor.py` | Tab 📝 Code: đọc/ghi file an toàn, tô màu pygments theo byte, `VimState` (phím vim → thao tác); widget `CodeEditor` ở `tui.py` |
| `ateam/todos.py`, `ateam/notes.py` | To-do (tag, hạn, ưu tiên, mô tả; bóc `#tag !cao @mai 17:00`), tag dùng chung, ghi chú markdown (xung đột theo `updated`) — JSON theo dự án ở `~/.config/ateam/`, ngoài repo |
| `ateam/rules.py` | `/rules`: rule của dự án mọi agent phải tuân theo — lưu ngoài repo, bật/tắt, chọn agent/vai trò; `Orchestrator.with_rules` gửi kèm mọi prompt |
| `ateam/overview.py` | `/init` (`ateam init --overview`): bản tổng quan dự án trưởng nhóm viết một lần vào `.ateam/project.md` (meta commit), gửi kèm prompt lập kế hoạch, `/grill`, kế hoạch tiếp và mỗi task |
| `ateam/projects.py` | `/open`: mở folder / dự án khác (dự án gần đây, gợi ý thư mục, kiểm tra đích); TUI/web chạy lại với `-C` |
| `ateam/palette.py` | Command palette tab Code (TUI + web): bảng lệnh, file gần đây, symbol (hàm/class/heading), lọc mờ, tạo/đổi tên/xoá file vào Thùng rác |
| `ateam/diffview.py` | Màn hình diff kiểu VS Code: bóc `git diff`, ghép dòng hai cột, tô cú pháp (pygments qua rich) và chữ đổi trong dòng; `DiffScreen` ở `tui.py` dùng |
| `ateam/mentions.py` | `@file`: gợi ý file/thư mục cho TUI, đổi `@đường/dẫn` sang cú pháp từng CLI (`SYNTAX`) |
| `ateam/clipboard.py` | Ctrl+V dán ảnh: đọc clipboard (osascript/pngpaste/wl-paste/xclip), lưu `.ateam/images/`, nhận ảnh kéo-thả |
| `ateam/limits.py` | Nhận diện thông báo hết hạn mức, đoán giờ hồi, lưu cooldown |
| `ateam/usage_logs.py` | Token & cost thật của một lượt: đọc file phiên Claude Code / Codex, bảng giá (`[prices]`) — dashboard, `/usage` |
| `ateam/notify.py` | Thông báo kế hoạch/diff chờ duyệt, task lỗi: `Watcher` so trạng thái, `desktop()` (osascript/notify-send), `/notify` |
| `tests/` | pytest; `tests/fakebin/` là các CLI giả lập `claude`, `codex`, `agy`, `grok` (Grok Build), `opencode`, `mycli` (agent tuỳ chỉnh), `code` (VS Code, cho phím `o` ở màn hình diff), `ruff` (format ở tab Code) |
| `site/`, `scripts/build_site.py`, `wrangler.jsonc` | Trang docs + gói zip, deploy Cloudflare Workers; `scripts/site_shots.py` chụp ảnh app cho `site/shots/` |
| `scripts/get.sh`, `install.sh` | Cài một lệnh từ GitHub; cài vào `~/.ateam/venv` + `~/.local/bin/ateam` |
| `docs/` | Tài liệu cho người phát triển (xem dưới) |

## Lệnh hay dùng khi phát triển

```bash
pip install -e ".[dev]"          # cài từ mã nguồn + pytest
python -m pytest -q              # ~3 phút, 100 test, dùng agent giả lập — PHẢI xanh trước khi commit
python -m ateam doctor           # xem lệnh thật sẽ chạy cho từng agent
python -m ateam -C /tmp/demo     # mở TUI trên một thư mục nháp
python scripts/build_site.py     # dựng trang docs vào dist/
```

Chạy thử với agent giả lập thay vì CLI thật:
`PATH=$PWD/tests/fakebin:$PATH XDG_CONFIG_HOME=/tmp/ateam-xdg python -m ateam goal -y "x"`.

## Quy tắc bắt buộc

1. **Chạy `python -m pytest -q` trước khi commit.** Thêm test cho mọi hành vi mới hoặc lỗi đã sửa.
2. **Không chạy CLI agent thật trong test.** Mở rộng `tests/fakebin/*` khi cần hành vi mới.
3. **Tương thích Python 3.9** (macOS có sẵn 3.9): luôn `from __future__ import annotations`,
   không dùng `match`, không dùng cú pháp `X | Y` ngoài annotation, không `tomllib` trực tiếp.
4. **Không thêm dependency** ngoài `textual` (và `tomli` cho 3.9/3.10) trừ khi thật cần.
5. **Chữ cho người dùng viết bằng `tr("tiếng Việt")` và có bản dịch trong `ateam/locales/en.py`**
   (`tests/test_i18n.py` bắt chuỗi thiếu bọc/thiếu dịch); **prompt gửi agent tiếng Anh** (agent tuân thủ tốt hơn), nhưng
   prompt luôn dặn agent viết theo ngôn ngữ của mục tiêu.
6. **Giữ nguyên giao thức output** mà `prompts.py` bóc: `SUMMARY:`, `<<<DELEGATE to="…" title="…">>> … <<<END>>>`,
   `<<<NOTE>>> … <<<END>>>`, `<<<ASK>>>{json câu hỏi}<<<END>>>`, kế hoạch là mảng JSON, review là object JSON, câu hỏi `/grill` là object JSON
   (`question`/`options`/`recommended` hoặc `done`/`spec`), gợi ý workflow là object JSON (`name`/`description`/`review`/`steps`). Đổi giao thức = đổi
   cả prompt, parser, agent giả lập và test.
7. **Đổi mặc định trong `DEFAULT_CONFIG`** → tăng `CONFIG_VERSION` (file của người dùng sẽ được sao lưu
   và thay mới) và cập nhật `docs/CONFIG.md`. Thêm khoá mới mà không đổi mặc định cũ thì chỉ cần có
   giá trị mặc định trong code khi khoá vắng mặt.
8. **Thêm cột DB** → thêm vào `SCHEMA` *và* danh sách migration trong `DB.__init__` (DB cũ phải mở được).
9. **Phím tắt TUI dùng `priority=True`**, nếu không ô nhập của Textual nuốt mất Ctrl+D/Ctrl+K.
10. **Đừng giả định máy có git identity**: commit/merge luôn qua `await self.git_ident()`.
11. **Không làm treo vòng lặp asyncio**: mọi tiến trình con chạy qua `asyncio`/`Run`; không gọi
    `subprocess.run` trong orchestrator hoặc TUI.
12. **Phát hành**: tăng `__version__` (`ateam/__init__.py`) *và* `version` (`pyproject.toml`), ghi
    `CHANGELOG.md`, push lên `main` → CI chạy test, Cloudflare tự deploy trang docs + zip mới.

## Đọc tiếp

- `docs/ARCHITECTURE.md` — luồng dữ liệu, máy trạng thái task/mục tiêu, lập lịch, worktree, hạn mức, sự kiện TUI.
- `docs/DEVELOPMENT.md` — môi trường, test, agent giả lập, công thức cho các thay đổi thường gặp.
- `docs/CONFIG.md` — mọi khoá cấu hình và file trạng thái.
- `docs/DECISIONS.md` — vì sao thiết kế như hiện tại (đọc trước khi "sửa cho gọn").
- `docs/ROADMAP.md` — việc còn dở, điều chưa kiểm chứng trên CLI thật, backlog tính năng.
- `docs/RELEASING.md` — phát hành và deploy.
- `README.md` — tài liệu cho người dùng cuối. Trang docs: https://ateam.khoaace.workers.dev
