# Tham chiếu cấu hình

Nguồn cấu hình, ưu tiên tăng dần:

1. `DEFAULT_CONFIG` trong `ateam/config.py` (chỉ dùng khi chưa có file chung).
2. `~/.config/ateam/config.toml` — file chung. Nếu tồn tại, nó **thay hẳn** mặc định (để người dùng
   xoá được agent). Tạo tự động; khi `config_version` < `CONFIG_VERSION` thì sao lưu thành
   `config.v<N>.<epoch>.bak.toml` và ghi bản mặc định mới.
3. `<dự án>/.ateam/config.toml` — merge sâu lên trên (chỉ cần ghi khoá muốn đổi). Tạo bằng
   `ateam init --project`.
4. `~/.config/ateam/state.json` → `agents.<tên>.model|effort` (đặt bằng `/model`, `/effort`,
   `ateam set`), và `<dự án>/.ateam/state.json` → `verify_command` (đặt bằng `/verify`).
5. Riêng từng task: cột `model`/`effort` (`/task agent:model@effort`, `/set`, kế hoạch của trưởng nhóm).

`XDG_CONFIG_HOME` đổi được vị trí thư mục `~/.config`.

## Khoá cấp cao

| Khoá | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `config_version` | `3` | Phiên bản file; thấp hơn `CONFIG_VERSION` thì được nâng cấp |
| `lead` | `"claude"` | Agent làm trưởng nhóm |
| `max_parallel` | `3` | Tổng số task chạy cùng lúc |
| `approve_plan` | `true` | Kế hoạch (và task bổ sung sau review) ở `draft`, chờ `/go` |
| `auto_review` | `true` | Trưởng nhóm review khi mục tiêu chạy xong |
| `max_rounds` | `3` | Số vòng review tối đa |
| `max_delegation_depth` | `2` | Số tầng giao việc chéo tối đa |
| `lead_sets_effort` | `true` | Trưởng nhóm được gắn effort cho task (chỉ nhận mức trong `efforts`) |
| `isolation` | `"shared"` | `"shared"` (chung thư mục) hoặc `"worktree"` (mỗi task một git worktree; cần chạy ở gốc repo đã có commit, không thì tự về shared) |
| `merge` | `"auto"` | Chỉ với worktree: `"auto"` tự merge, `"review"` chờ `/merge` |

## `[verify]`

| Khoá | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `command` | `""` | Lệnh kiểm tra (chạy bằng `/bin/sh -c` trong thư mục task). Rỗng = tắt. `/verify` ghi đè theo dự án |
| `timeout` | `600` | Giây cho mỗi lần chạy lệnh kiểm tra |
| `max_fix_attempts` | `2` | Số lần giao sửa khi kiểm tra fail |
| `fix_agent` | `""` | Ai sửa; rỗng = agent làm task |
| `only_when_changed` | `true` | Bỏ qua kiểm tra nếu task không đổi file (cần git để biết; không có git thì luôn chạy) |

## `[limits]`

| Khoá | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `cooldown_minutes` | `30` | Thời gian nghỉ khi CLI không nói giờ hồi hạn mức |
| `lead_fallback` | `["codex"]` | Ai lập kế hoạch/review thay khi trưởng nhóm hết hạn mức |

## `[agents.<tên>]`

| Khoá | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `command` | — | argv chạy headless; `{prompt}` (bắt buộc nên có), có thể chứa `{model}`, `{effort}` |
| `role` | `""` | Thế mạnh; trưởng nhóm phân việc dựa vào đây |
| `model`, `effort` | `""` | Mặc định; rỗng = để CLI tự chọn |
| `model_args`, `effort_args` | `[]` | Cờ chèn trước prompt khi có model/effort (`{model}`, `{effort}` được thay) |
| `efforts` | `[]` | Mức effort hợp lệ (kiểm tra, gợi ý, giới hạn lựa chọn của trưởng nhóm) |
| `fallback` | `[]` | Agent thay thế khi agent này hết hạn mức (theo thứ tự) |
| `verify` | `true` | `false` = không chạy `[verify]` sau task của agent này |
| `timeout` | `1800` | Giây cho một lượt chạy |
| `max_concurrent` | `1` | Số task cùng lúc của agent này |
| `pty` | `false` | Chạy trong pseudo-terminal (cần cho `agy`) |
| `plan_command` | — | argv riêng khi agent lập kế hoạch/review (vd chế độ chỉ đọc) |
| `enabled` | `true` | `false` = tạm tắt |

## Mặc định của 4 agent (config_version 3)

| Agent | command | model_args / effort_args | efforts | fallback |
| --- | --- | --- | --- | --- |
| `claude` | `claude -p {prompt} --permission-mode acceptEdits` | `--model` / `--effort` | low, medium, high, max | codex |
| `codex` | `codex exec --full-auto --skip-git-repo-check {prompt}` | `-m` / `-c model_reasoning_effort="…"` | minimal…xhigh | claude |
| `antigravity` | `agy --mode accept-edits --print-timeout 0 -p {prompt}` (pty) | `--model` / `--effort` | low…max | claude, codex |
| `grok` | `opencode run {prompt}`, model `xai/grok-build-0.1` | `--model` / `--variant` | low, medium, high | codex |

Quyền mặc định là "được sửa file, không chạy lệnh shell tuỳ ý" ở những CLI phân biệt được hai việc
này. Muốn agent chạy cả test/build: claude `--permission-mode bypassPermissions`, agy
`--dangerously-skip-permissions`, opencode `--dangerously-skip-permissions`.

## Ví dụ cấu hình dự án

```toml
# .ateam/config.toml
isolation = "worktree"
merge = "review"
max_parallel = 4

[verify]
command = "npm test"
fix_agent = "codex"

[agents.codex]
model = "gpt-5.5"
max_concurrent = 2
```
