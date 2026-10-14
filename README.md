# AI Team (`ateam`)

**Trang docs và tải về:** https://ateam.khoaace.workers.dev

Công cụ terminal giúp **Claude Code, Codex, Antigravity và Grok (qua OpenCode)** làm việc như một đội:
một agent làm **trưởng nhóm** (mặc định Claude) lập kế hoạch và chia việc, các agent khác làm song song,
**giao việc cho nhau**, ghi chú chung, và trưởng nhóm **review** rồi giao thêm việc cho đến khi xong.
Bạn vẫn có thể giao tay bất cứ lúc nào.

```
 Bạn ──mục tiêu──▶ Trưởng nhóm (claude) ──kế hoạch──▶ Bảng việc (SQLite)
                                                        │
                ┌──────────────┬──────────────┬─────────┴────┐
              codex      antigravity (agy)   grok (opencode)  claude
                └── kết quả / ghi chú / <<<DELEGATE>>> ──▶ bảng việc ──▶ review ──▶ vòng tiếp
```

## Cài đặt

Một lệnh (macOS / Linux):

```bash
curl -fsSL https://raw.githubusercontent.com/khoaace/ateam/main/scripts/get.sh | bash
ateam doctor
```

Hoặc tải file `.zip` từ trang docs, rồi chạy `./install.sh` trong thư mục giải nén.

## Cài đặt từ mã nguồn (macOS)

```bash
cd ateam
./install.sh          # tạo venv ở ~/.ateam, lệnh `ateam` ở ~/.local/bin
ateam doctor          # kiểm tra claude / codex / agy / opencode đã có chưa
```

Yêu cầu: Python 3.9+ (`brew install python` nếu chưa có), git, và các CLI agent **đã đăng nhập sẵn**
(chạy thử `claude`, `codex`, `agy`, `opencode` một lần cho chắc).

## Dùng

```bash
cd ~/code/du-an-cua-ban
ateam
```

* **Gõ một câu bình thường** → giao mục tiêu cho trưởng nhóm. Kế hoạch hiện ra ở trạng thái *nháp*;
  xem, sửa (`/assign`, `/edit`, `/cancel`) rồi **Ctrl+G** hoặc `/go` để chạy.
* **Giao tay**: `/task codex viết unit test cho utils.py`
* **Nhắc file/thư mục bằng `@`**: gõ `@` trong ô nhập để hiện danh sách file và thư mục của dự án, gõ
  tiếp để lọc (khớp cả rải rác, vd `@atcfg` → `ateam/config.py`), ↑↓ chọn, Tab/Enter chèn, Esc đóng.
  Chọn thư mục thì danh sách đi vào trong thư mục đó. Khi chạy, ateam đổi `@đường/dẫn` sang đúng cú
  pháp của agent nhận việc (xem bảng dưới); `ateam add`/`ateam goal` ngoài dòng lệnh cũng hiểu `@`.
* Chọn task trong bảng (↑↓) để xem log trực tiếp của nó; **Ctrl+L** về log hệ thống.
* **Ctrl+R** chạy lại task đang chọn, **Ctrl+K** huỷ, `/note ...` ghi chú cho cả đội, `/help` xem tất cả lệnh.
* **Ctrl+T** mở tab **Đội** để xem cả 4 agent làm việc cùng lúc.

Không cần giao diện:

```bash
ateam goal "Thêm trang đăng nhập + viết test"          # hỏi duyệt kế hoạch rồi chạy
ateam goal -y "Sửa lỗi build"                           # chạy luôn
ateam add --to grok "Viết docstring cho src/api.py"     # thêm task
ateam run                                               # chạy hết task đang chờ
ateam list   /   ateam log 3   /   ateam log sys
```

### `@file` được truyền cho từng agent thế nào

| Agent (lệnh) | Trong prompt | Cờ thêm vào lệnh |
| --- | --- | --- |
| claude | `@src/app.py` (Claude Code tự đọc file) | — |
| antigravity (`agy`) | `@src/app.py` | — |
| codex | `src/app.py` (`codex exec` không có cú pháp `@`) | — |
| grok (`opencode run`) | `src/app.py` | `-f src/app.py` (đính kèm file) |
| CLI khác | `src/app.py` | — |

Chỉ đổi khi đường dẫn có thật trong dự án, nên `a@b.com`, `@property`, `codex@xhigh` giữ nguyên.
Đường dẫn có dấu cách viết `@"thư mục/file.md"`. Đổi cú pháp cho một agent bằng `file_ref` /
`file_args` trong config (xem `docs/CONFIG.md`); `ateam doctor` và `/agents` in cú pháp đang dùng.

## Xem tiến trình từng agent — tab "Đội" (Ctrl+T)

Mỗi agent một ô: model · effort đang dùng, số task ✓ xong / ✗ lỗi / ⏳ chờ, task đang chạy kèm
thời gian chạy, số dòng output, dòng mới nhất, cảnh báo *im lặng* nếu quá 60 giây không có output,
và log trực tiếp (mỗi lần chạy có vạch ▶ bắt đầu / ■ kết thúc). Bên dưới là **timeline**: mỗi agent
một hàng, mỗi task một đoạn màu (tím = đang chạy, xanh = xong, đỏ = lỗi, vàng = trưởng nhóm đang lập
kế hoạch/review). Ctrl+T để quay lại Bảng việc.

## Model & effort từng agent

Trong app (được lưu lại cho lần sau, ở `~/.config/ateam/state.json`):

```
/model claude opus             /effort claude high
/model codex gpt-5.5           /effort codex xhigh
/model antigravity <tên>       /effort antigravity high      (xem tên: agy models)
/model grok xai/grok-4.7       /effort grok high             (OpenCode gọi là --variant)
/model codex -                 quay về mặc định
/agents                        xem tất cả + mức effort hợp lệ
```

Riêng cho 1 task: `/task codex@xhigh tìm lỗi deadlock`, `/task claude:opus@max thiết kế lại module auth`,
hoặc sửa task đang chờ: `/set 7 effort high`. Trưởng nhóm cũng tự chọn effort cho từng task khi lập kế
hoạch (tắt bằng `lead_sets_effort = false`). Ngoài app: `ateam set codex --model gpt-5.5 --effort high`.

Cách truyền cờ của từng CLI nằm trong `model_args` / `effort_args` ở file cấu hình — thêm agent mới chỉ cần
khai báo đúng cờ của nó.

## Tự kiểm tra sau mỗi task

```
/verify npm test          # hoặc: pytest -q, make check, cargo test …  (lưu riêng cho dự án này)
/verify off               # tắt
```

Sau mỗi task có thay đổi file, ateam chạy lệnh kiểm tra trong đúng thư mục của task. Fail thì giao sửa
kèm log lỗi (mặc định chính agent đó, tối đa 2 lần; đổi bằng `[verify] fix_agent`, `max_fix_attempts`).
Vẫn fail thì task báo lỗi. Agent chỉ đọc/nghiên cứu có thể đặt `verify = false`.

## Xem diff và duyệt merge (chế độ worktree)

Đặt `merge = "review"`: task xong (và qua kiểm tra) dừng ở trạng thái **chờ duyệt**.
**Ctrl+D** / `/diff 3` xem thay đổi, **Ctrl+Y** / `/merge 3` để merge,
`/reject 3 thiếu xử lý lỗi null` để giao làm lại kèm góp ý (`/reject 3` không góp ý = huỷ).
Task phụ thuộc chỉ chạy sau khi task trước được merge. Ngoài app: `ateam diff|merge|reject`.

## Hạn mức và agent dự phòng

Khi một agent báo hết hạn mức (rate limit / usage limit), ateam cho nó tạm nghỉ đến lúc hạn mức hồi
(đọc từ thông báo của CLI, không có thì 30 phút) và chuyển task sang agent trong `fallback` của nó.
Trưởng nhóm hết hạn mức thì `lead_fallback` lập kế hoạch/review thay. `/usage` (hoặc `ateam usage`) xem số
lượt, thời gian, token ước tính theo agent; `/cooldown codex 60` cho nghỉ tay, `/cooldown codex off` để bỏ.

## Các agent giao việc cho nhau thế nào?

Mỗi agent nhận kèm hướng dẫn: nếu một phần việc hợp với thành viên khác hơn, nó in ra

```
<<<DELEGATE to="codex" title="Viết test">>>
nội dung yêu cầu...
<<<END>>>
```

`ateam` đọc output và tự tạo task mới cho agent đó (giới hạn bởi `max_delegation_depth`).
`<<<NOTE>>>...<<<END>>>` là ghi chú chung — mọi task sau đều thấy. Kết quả (dòng `SUMMARY:`) của task
được chuyển cho các task phụ thuộc vào nó. Agent nào chạy được lệnh shell cũng có thể gọi
`ateam add --to <agent> "..."` trực tiếp.

## Cấu hình

`~/.config/ateam/config.toml` (tạo tự động), ghi đè riêng cho từng dự án bằng `ateam init --project`
→ `.ateam/config.toml`. Có thể đổi trưởng nhóm, vai trò từng agent, lệnh chạy, timeout, số task song song.

Thêm agent mới chỉ cần một khối:

```toml
[agents.gemini]
command = ["gemini", "-p", "{prompt}", "--yolo"]
role = "Đọc codebase lớn, viết tài liệu."
```

**Chế độ làm việc** (`isolation`):

* `shared` (mặc định): mọi agent làm chung thư mục. Đơn giản; trưởng nhóm được dặn không cho 2 task song
  song sửa cùng file.
* `worktree`: mỗi task chạy trong một git worktree riêng (`ateam/t<id>`), xong thì tự commit và merge vào
  nhánh hiện tại. Nếu xung đột, task chuyển sang **xung đột** và nhánh được giữ lại để bạn merge tay.
  Cần chạy ở thư mục gốc của repo đã có ít nhất 1 commit.

## Lưu ý riêng từng CLI

* **Claude Code**: mặc định `--permission-mode acceptEdits` (được sửa file, không chạy lệnh shell).
  Muốn cho chạy test/build, đổi thành `bypassPermissions` — chỉ trong repo bạn tin tưởng.
* **Codex**: `codex exec --full-auto` — sửa file và chạy lệnh trong sandbox của Codex.
* **Antigravity (`agy`)**: chỉ in output khi có terminal thật, nên `ateam` chạy nó trong pseudo-terminal
  (`pty = true`), với `--mode accept-edits` (được sửa file) và `--print-timeout 0`. Muốn cho chạy cả lệnh
  shell: thay `--mode accept-edits` bằng `--dangerously-skip-permissions`.
* **Grok qua OpenCode**: `opencode run --model xai/grok-build-0.1 ...`; xem model bằng
  `opencode models | grep grok`. Nếu bị chặn quyền, thêm `--dangerously-skip-permissions`.

## Dữ liệu

Mọi thứ nằm trong `.ateam/` của dự án (đã tự gitignore): `team.db` (bảng việc), `logs/t<id>.log`,
`logs/lead.log` (output lập kế hoạch/review của trưởng nhóm), `logs/system.log`.

## Trang docs (Cloudflare Workers)

Trang giới thiệu và file tải nằm trong `site/`; `scripts/build_site.py` dựng chúng vào `dist/`
(điền phiên bản và đóng gói `ateam-<version>.zip`). `wrangler.jsonc` deploy `dist/` lên Cloudflare
Workers dưới dạng static assets, nên chỉ cần:

```bash
npx wrangler deploy        # tự chạy python3 scripts/build_site.py trước
```

Khi repo được nối với Workers Builds, mỗi lần push lên `main` sẽ tự build và deploy lại.

## Phát triển

Đọc `AGENTS.md` trước (điểm vào cho cả người lẫn AI agent), rồi `docs/`:
[kiến trúc](docs/ARCHITECTURE.md), [phát triển & test](docs/DEVELOPMENT.md),
[cấu hình](docs/CONFIG.md), [quyết định thiết kế](docs/DECISIONS.md), [lộ trình](docs/ROADMAP.md),
[phát hành](docs/RELEASING.md). Lịch sử thay đổi: [CHANGELOG.md](CHANGELOG.md).

```bash
pip install -e ".[dev]" && python -m pytest -q
```
