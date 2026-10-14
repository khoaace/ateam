# AGENTS.md — hướng dẫn cho AI agent làm việc trên repo này

Đọc file này trước khi sửa bất cứ thứ gì. Nó là điểm vào; chi tiết nằm trong `docs/`.

## ateam là gì

Công cụ terminal (Python + Textual) điều phối nhiều AI coding agent CLI — Claude Code, Codex,
Antigravity (`agy`), Grok qua OpenCode, hoặc bất kỳ CLI nào có chế độ headless — làm việc như
một đội trên cùng một repo của người dùng:

- **Trưởng nhóm** (mặc định `claude`) lập kế hoạch thành task JSON, review kết quả, giao thêm việc.
- **Bảng việc** SQLite (`.ateam/team.db`) là nguồn sự thật duy nhất; TUI, CLI và agent cùng đọc/ghi.
- **Bộ lập lịch** chạy task theo phụ thuộc và giới hạn song song; agent giao việc chéo bằng
  khối `<<<DELEGATE …>>>` trong output.
- Tự chạy lệnh kiểm tra sau task (fail thì giao sửa), worktree + duyệt diff trước khi merge,
  phát hiện hết hạn mức và chuyển sang agent dự phòng.

Người dùng là developer Việt Nam, dùng macOS. **Mọi chữ hiển thị cho người dùng viết bằng tiếng Việt.**

## Bản đồ repo

| Đường dẫn | Nội dung |
| --- | --- |
| `ateam/cli.py` | Lệnh `ateam` (argparse): `tui` (mặc định), `goal`, `add`, `run`, `diff`, `merge`, `reject`, `verify`, `usage`, `cooldown`, `set`, `doctor`, … |
| `ateam/tui.py` | Giao diện Textual: tab Bảng việc, tab Đội (AgentPane + Timeline), lệnh `/…`, phím tắt |
| `ateam/orchestrator.py` | Lõi: lập kế hoạch, `tick()` lập lịch, `_run_task`, verify, worktree/merge, hạn mức, review |
| `ateam/runner.py` | `Run`: chạy 1 tiến trình (pipe hoặc pty), stream từng dòng, timeout, huỷ theo process group |
| `ateam/config.py` | `DEFAULT_CONFIG` (TOML), dataclass `Config`/`AgentConfig`/`VerifyConfig`, `AgentConfig.argv()`, state.json |
| `ateam/db.py` | Schema SQLite + migration cột, `Task`/`Goal`, thống kê `runs` |
| `ateam/prompts.py` | Prompt gửi trưởng nhóm/thành viên (tiếng Anh) + bóc JSON, DELEGATE, NOTE, SUMMARY |
| `ateam/limits.py` | Nhận diện thông báo hết hạn mức, đoán giờ hồi, lưu cooldown |
| `tests/` | pytest; `tests/fakebin/` là các CLI giả lập `claude`, `codex`, `agy`, `opencode` |
| `site/`, `scripts/build_site.py`, `wrangler.jsonc` | Trang docs + gói zip, deploy Cloudflare Workers |
| `scripts/get.sh`, `install.sh` | Cài một lệnh từ GitHub; cài vào `~/.ateam/venv` + `~/.local/bin/ateam` |
| `docs/` | Tài liệu cho người phát triển (xem dưới) |

## Lệnh hay dùng khi phát triển

```bash
pip install -e ".[dev]"          # cài từ mã nguồn + pytest
python -m pytest -q              # ~30s, 19 test, dùng agent giả lập — PHẢI xanh trước khi commit
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
5. **Chữ cho người dùng tiếng Việt; prompt gửi agent tiếng Anh** (agent tuân thủ tốt hơn), nhưng
   prompt luôn dặn agent viết theo ngôn ngữ của mục tiêu.
6. **Giữ nguyên giao thức output** mà `prompts.py` bóc: `SUMMARY:`, `<<<DELEGATE to="…" title="…">>> … <<<END>>>`,
   `<<<NOTE>>> … <<<END>>>`, kế hoạch là mảng JSON, review là object JSON. Đổi giao thức = đổi
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
