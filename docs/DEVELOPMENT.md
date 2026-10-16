# Phát triển ateam

## Môi trường

```bash
git clone https://github.com/khoaace/ateam && cd ateam
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
```

Yêu cầu Python ≥ 3.9 (macOS có sẵn 3.9.6; CI chạy 3.9 và 3.13 trên Ubuntu + macOS). Phụ thuộc duy nhất
khi chạy là `textual` (+ `tomli` cho Python < 3.11).

Chạy app từ mã nguồn mà không động vào cấu hình thật của máy:

```bash
export XDG_CONFIG_HOME=/tmp/ateam-xdg          # cấu hình + state.json riêng
export PATH=$PWD/tests/fakebin:$PATH           # dùng agent giả lập
mkdir -p /tmp/demo && python -m ateam -C /tmp/demo
```

Bỏ dòng `PATH=…fakebin` để chạy với CLI thật.

## Test

| File | Kiểm tra |
| --- | --- |
| `tests/test_units.py` | `AgentConfig.argv`, bóc JSON/DELEGATE/NOTE/SUMMARY, nhận diện hết hạn mức, nâng cấp config |
| `tests/test_flows.py` | Luồng đầu-cuối qua `python -m ateam`: kế hoạch → chạy → giao chéo → review; cờ model/effort; lỗi thiếu CLI / im lặng / timeout / bị chặn; worktree merge + xung đột; chế độ review (diff/merge/reject); verify sửa được / hết lượt / bỏ qua; hết hạn mức + dự phòng; `run` không treo |
| `tests/test_tui.py` | Mở TUI headless (`App.run_test`), giao task, đổi tab, Ctrl+D, Ctrl+Y, `/usage`; danh sách gợi ý `@file`; Ctrl+V dán ảnh và kéo-thả ảnh (`clipboard.grab_image` giả); wizard thiết lập (`TeamApp(..., setup=True)`) đi hết 7 bước, hỏi model từ CLI giả lập rồi lưu; Esc/✕ ở popup; bố cục hẹp + log vẽ lại khi đổi bề rộng |

Helper trong `tests/conftest.py`: fixture `env` (PATH có fakebin, XDG riêng, thư mục hạn mức,
file log đối số), `project`, hàm `ateam(env, cwd, *args)`, `git_init`, `write_project_config`, `tasks`.

Máy CI (Ubuntu) không có git identity. Chạy test giống CI để bắt lỗi kiểu này:

```bash
mkdir -p /tmp/cihome && HOME=/tmp/cihome GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 python -m pytest -q
```

### Agent giả lập (`tests/fakebin/`)

| Script | Hành vi |
| --- | --- |
| `claude` | Prompt có "Reply with ONLY a JSON array" → kế hoạch 3 task (codex effort xhigh, grok, antigravity phụ thuộc 1+2 với effort sai). "Review round 1" → chưa xong, giao `Tạo c.txt` cho claude. Vòng sau → xong. Còn lại: tạo `c.txt`. |
| `codex` | Tạo `a.txt`, giao README cho grok (nếu prompt cho phép DELEGATE), để NOTE. Prompt có "VERIFICATION COMMAND" → tạo `fixed.txt`. Làm trưởng nhóm thay khi prompt có "TEAM LEAD". |
| `opencode` | Tạo `b.txt`, hoặc `README.md` nếu prompt nhắc README. |
| `agy` | Không in gì nếu stdout không phải tty (như agy thật); in mã ANSI và `\r`. |
| `mycli` | CLI "tuỳ chỉnh" bất kỳ cho test `/custom` + workflow: ghi tiêu đề task vào `steps.txt` (kiểm tra thứ tự bước). |

Biến điều khiển (đọc trong `_common.sh`): `ATEAM_FAKE_SLOW` (giây giữa các dòng),
`ATEAM_FAKE_LIMIT_DIR` (có file `<tên>` trong đó → agent đó báo hết hạn mức),
`ATEAM_FAKE_ARGS_LOG` (ghi argv trừ prompt, để test cờ), `ATEAM_FAKE_FULL_LOG` (ghi cả prompt, để test
nội dung prompt, vd cú pháp `@file`). Lưu ý tên file hạn mức của OpenCode là
`grok` (tên agent trong ateam), không phải `opencode`.

Khi đổi prompt trong `prompts.py`, kiểm tra các chuỗi mà fakebin dò (`Reply with ONLY a JSON array`,
`Review round`, `TEAM LEAD`, `VERIFICATION COMMAND`, `DELEGATE`, `#1 by codex`).

### Kiểm tra giao diện

Test chỉ bắt lỗi chức năng; bố cục cần nhìn. Chụp màn hình headless:

```python
import asyncio
from pathlib import Path
from ateam.config import ensure_global_config, load_config
from ateam.db import DB
from ateam.tui import TeamApp

async def shot(root: Path):
    ensure_global_config()
    app = TeamApp(root, load_config(root), DB(root / ".ateam/team.db"))
    async with app.run_test(size=(170, 50)) as pilot:
        app.run_command("/task codex tạo a")
        await pilot.pause(3)
        await pilot.press("ctrl+t")
        await pilot.pause(0.5)
        app.save_screenshot("team.svg")   # mở SVG, hoặc đổi sang PNG bằng cairosvg

asyncio.run(shot(Path("/tmp/demo")))
```

Trong ảnh SVG, ký tự vẽ khung và spinner có thể hiện thành ô vuông do font của trình render; trên
terminal thật vẫn đúng.

## Công thức cho thay đổi thường gặp

**Thêm agent mặc định**: thêm khối `[agents.<tên>]` trong `DEFAULT_CONFIG` (`config.py`) với
`command`, `model_args`, `effort_args`, `efforts`, `fallback`, `role`; tăng `CONFIG_VERSION`; thêm
script giả lập vào `tests/fakebin` nếu test cần; cập nhật `docs/CONFIG.md`, README, `site/index.html`.

**Thêm lệnh `/…` trong TUI**: thêm nhánh trong `TeamApp.run_command` (`tui.py`), dòng trong `HELP`,
và nếu là thao tác dữ liệu thì đặt logic trong `Orchestrator` (TUI chỉ gọi). Thao tác `async` chạy qua
`self.run_worker(coro, exclusive=False)`.

**Thêm lệnh dòng lệnh**: hàm `cmd_<tên>(args)` + `sub.add_parser` + mục trong `handlers` (`cli.py`).

**Thêm khoá cấu hình**: chú thích trong `DEFAULT_CONFIG`, trường dataclass, đọc trong `load_config`
(luôn có mặc định khi khoá vắng), `docs/CONFIG.md`. Chỉ tăng `CONFIG_VERSION` khi muốn người dùng cũ
nhận *mặc định mới* (file của họ bị thay, có sao lưu).

**Thêm cột DB**: `SCHEMA` + vòng migration trong `DB.__init__` + trường `Task`/`Goal` có giá trị mặc
định (thứ tự trường phải khớp `SELECT *` qua `dict(row)` — dùng tên, không dùng vị trí).

**Nhận diện thêm thông báo hết hạn mức**: thêm mẫu vào `LIMIT_RE` (và nếu có giờ hồi, vào
`IN_RE`/`AT_RE`/`EPOCH_RE`) trong `limits.py` + một assert trong `test_rate_limit_detection`.
Dùng nguyên văn thông báo người dùng gửi (`ateam log <task>`).

**Đổi trạng thái task**: hằng trong `db.py`, `ACTIVE`/`FINISHED_BAD` nếu cần, nhãn + màu trong
`STATUS`/`BAR_STYLE` (`tui.py`), máy trạng thái trong `docs/ARCHITECTURE.md`.

## Gỡ lỗi

- `ateam log sys` — log bộ điều phối; `ateam log <id>` — output đầy đủ của task (dòng đầu là agent,
  model · effort, thư mục); `.ateam/logs/lead.log` — kế hoạch/review thô của trưởng nhóm.
- `sqlite3 .ateam/team.db 'select id,agent,status,error from tasks'` — xem thẳng bảng việc.
- `ateam doctor` — in đúng argv sẽ chạy cho từng agent (đã chèn model/effort).
  Nó cũng so cờ trong `command` với `<lệnh> [lệnh con] --help` và báo cờ lạ. CLI đổi/bỏ cờ thì thêm
  vào `LEGACY_FLAGS` (`config.py`) để cấu hình cũ tự được đổi khi đọc; agent giả lập in cờ "biết" ở
  `--help` qua biến `fake_flags` (`tests/fakebin/_common.sh`).
- Lỗi khi vẽ TUI bị nuốt trong `refresh_view` (để app không treo) và ghi bằng `self.log.error`;
  muốn thấy thì `pip install textual-dev`, mở `textual console` ở một terminal, chạy app với
  `TEXTUAL=devtools python -m ateam` ở terminal khác.
