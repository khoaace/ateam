# Tham chiếu cấu hình

Nguồn cấu hình, ưu tiên tăng dần:

1. `DEFAULT_CONFIG` trong `ateam/config.py` (chỉ dùng khi chưa có file chung).
2. `~/.config/ateam/config.toml` — file chung. Nếu tồn tại, nó **thay hẳn** mặc định (để người dùng
   xoá được agent). Tạo tự động; khi `config_version` < `CONFIG_VERSION` thì sao lưu thành
   `config.v<N>.<epoch>.bak.toml` và ghi bản mặc định mới.
3. `~/.config/ateam/custom.toml` — agent (`[agents.<tên>]`) và workflow (`[workflows.<tên>]`) người dùng
   tự thêm qua `/custom`; merge sâu lên file chung. File riêng nên **không bị thay** khi file chung được
   nâng cấp. Lỗi cú pháp TOML = bỏ qua cả file.
4. `<dự án>/.ateam/config.toml` — merge sâu lên trên (chỉ cần ghi khoá muốn đổi). Tạo bằng
   `ateam init --project`.
5. `~/.config/ateam/state.json` → `agents.<tên>.model|effort|enabled|role|full_access` (đặt bằng `/model`, `/effort`,
   `ateam set`, wizard `/setup`), `lead` (vai trò Trưởng nhóm ở `/setup`), `default_workflow` (workflow chạy khi gõ
   mục tiêu trong TUI — wizard đặt `tinh-nang` khi chọn kiểu "theo quy trình cố định"; workflow đã bị xoá thì bỏ
   qua), `lang` (`vi`/`en`, `/lang`, `ateam lang`), `theme` / `accent` (theme Textual và màu nhấn, `/theme`), `approve_plan` / `auto_review` (kiểu làm việc ở `/setup`; chỉ ghi khi khác `true`), `onboarded` (đã qua
   wizard lần đầu; xoá khoá này để hiện lại), `models_found.<tên>` (model hỏi được từ CLI qua `models_command`), và
   `<dự án>/.ateam/state.json` → `verify_command` (đặt bằng `/verify` hoặc bước *Lệnh kiểm tra*), `isolation` /
   `merge` (bước *An toàn & duyệt code*, riêng từng dự án).
   Agent wizard tự tạo thêm (cùng CLI, model khác, vd `claude-review`) nằm trong `custom.toml` với `wizard = true`;
   chạy lại wizard thì các agent này được xoá và tạo lại.
6. Riêng từng task: cột `model`/`effort` (`/task agent:model@effort`, `/set`, kế hoạch của trưởng nhóm).

`XDG_CONFIG_HOME` đổi được vị trí thư mục `~/.config`.

## Khoá cấp cao

| Khoá | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `config_version` | `8` | Phiên bản file; thấp hơn `CONFIG_VERSION` thì được nâng cấp |
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
| `efforts` | danh mục | Mức effort hợp lệ (kiểm tra, gợi ý, bảng chọn, giới hạn lựa chọn của trưởng nhóm). Vắng = theo `CATALOG`; `[]` = không có |
| `models` | danh mục | Model gợi ý cho bảng chọn `/model`, tab Đội, `/models`. Vắng = `CATALOG` trong `config.py` theo tên lệnh (`claude`, `codex`, `agy`, `opencode`). Chỉ là gợi ý: tên ngoài danh sách vẫn đặt được |
| `full_access` | `false` | Toàn quyền: agent được chạy lệnh shell và dùng mạng (lint, build, `git push`). ateam đổi cờ lúc chạy: claude/grok `--permission-mode bypassPermissions`, codex `--sandbox danger-full-access`, agy `--dangerously-skip-permissions` (thay `--mode accept-edits`), opencode `--auto`; CLI khác không đổi. Đặt ở bước *An toàn* của `/setup` (cả đội, lưu `state.json`) hoặc form agent tuỳ chỉnh |
| `usage_command` | danh mục | argv in hạn mức/usage của CLI cho `/usage`: `claude -p /usage`, `agy -p /usage` (qua pty nếu `pty = true`), `opencode stats --days 7`; tối đa 20 dòng. Vắng với `codex` = đọc `rate_limits` trong file phiên mới nhất ở `$CODEX_HOME/sessions` (mặc định `~/.codex`) |
| `models_command` | danh mục | argv liệt kê model thật (`opencode models`, `agy models`, `codex debug models`; output dạng chữ mỗi dòng một model, hoặc JSON `{"models": [{"slug", "visibility"}]}` thì bỏ model `hide`); chạy song song ở màn hình thiết lập (`/setup`, lần đầu mở app), khi mở app mà chưa có kết quả, hoặc `/models <agent> làm mới`, kết quả lưu ở `state.json` và đứng trước `models` |
| `models_filter` | `""` | Chỉ giữ model chứa chữ này. Vắng: nếu có model chứa tên agent (vd `grok`) thì chỉ giữ các model đó |
| `fallback` | `[]` | Agent thay thế khi agent này hết hạn mức (theo thứ tự) |
| `verify` | `true` | `false` = không chạy `[verify]` sau task của agent này |
| `timeout` | `1800` | Giây cho một lượt chạy |
| `max_concurrent` | `1` | Số task cùng lúc của agent này |
| `pty` | `false` | Chạy trong pseudo-terminal (cần cho `agy`) |
| `plan_command` | — | argv riêng khi agent lập kế hoạch/review (vd chế độ chỉ đọc) |
| `enabled` | `true` | `false` = tạm tắt |
| `file_ref` | theo lệnh | Cách viết file được nhắc bằng `@` trong prompt; `{path}` được thay. Vắng = theo `mentions.SYNTAX`: `"@{path}"` cho `claude`/`agy`/`gemini`, `"{path}"` cho lệnh khác |
| `file_args` | theo lệnh | Cờ thêm vào lệnh cho mỗi file/thư mục được nhắc (chèn trước prompt). Vắng = `["-f", "{path}"]` cho `opencode`, `[]` cho lệnh khác; `[]` = tắt |
| `image_args` | theo lệnh | Như `file_args` nhưng cho file ảnh (`.png`, `.jpg`, `.webp`…, gồm ảnh dán bằng Ctrl+V). Vắng = `["--image={path}"]` cho `codex`, lệnh khác dùng `file_args`; `[]` = chỉ ghi đường dẫn trong prompt |

## `[workflows.<tên>]`

Chạy bằng `/flow <tên> <mục tiêu>` hoặc `ateam flow <tên> <mục tiêu>`: tạo mục tiêu (cột `goals.workflow`)
và chèn các bước thành task qua `_insert_plan` (nguồn `workflow`), không gọi trưởng nhóm lập kế hoạch.
Duyệt theo `approve_plan` như kế hoạch thường.

| Khoá | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `description` | `""` | Mô tả ngắn (hiện ở `/flow`, `/custom`) |
| `review` | theo `auto_review` | Trưởng nhóm review khi mọi bước xong (có thể giao thêm việc) |
| `[[…steps]]` | — | Danh sách bước theo thứ tự |

Mỗi bước:

| Khoá | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `agent` | `"lead"` | Tên agent; `"lead"` = trưởng nhóm lúc chạy. Agent không có/đang tắt → giao cho trưởng nhóm (như kế hoạch) |
| `title` | `"Bước N"` | Tiêu đề task; `{goal}` được thay |
| `prompt` | tiêu đề | Nội dung task; `{goal}` được thay (mục tiêu luôn có trong prompt dù không dùng `{goal}`) |
| `after` | bước liền trước | Số thứ tự bước (từ 1) phải xong trước; `[]` = chạy ngay |
| `effort`, `model` | `""` | Riêng cho task của bước này (không bị lọc như effort trưởng nhóm đặt) |

## Mặc định của 5 agent (config_version 8)

| Agent | command | model_args / effort_args | efforts | fallback |
| --- | --- | --- | --- | --- |
| `claude` | `claude -p {prompt} --permission-mode acceptEdits` | `--model` / `--effort` | low, medium, high, max | codex |
| `codex` | `codex exec --sandbox workspace-write --skip-git-repo-check {prompt}` | `-m` / `-c model_reasoning_effort="…"` | low…ultra | claude |
| `antigravity` | `agy --mode accept-edits --print-timeout 0 -p {prompt}` (pty) | `--model` / `--effort` | low…max | claude, codex |
| `grok` | `grok --permission-mode auto --deny Bash -p {prompt}` (Grok Build CLI; `acceptEdits` ở chế độ `-p` chặn cả sửa file) | `-m` / `--reasoning-effort` | low, medium, high, xhigh | codex |
| `opencode` | `opencode run {prompt}`, model `xai/grok-build-0.1` | `--model` / `--model {model}#{effort}` (variant ghi liền model) | low, medium, high | codex |

Bản 8: OpenCode bỏ `run --variant` ("Unrecognized flag: --variant"); variant giờ ghi liền model dạng
`provider/model#variant`. `effort_args` có `{model}` là dạng gộp: khi có effort và model, nó thay cho
`model_args`; không có model thì bỏ effort. Agent cũ (kể cả agent tuỳ chỉnh như `opencode-research`) còn
`effort_args = ["--variant", "{effort}"]` được đổi khi đọc (`LEGACY_EFFORT_ARGS` trong `config.py`).

Bản 6 đổi `grok` từ OpenCode sang Grok Build CLI. Khi nâng cấp, `ensure_global_config` chuyển các mục
`state.json` của `grok` cũ (`agents.grok`, `models_found.grok`, `lead`) sang `opencode` (sao lưu
`state.v5.<epoch>.bak.json`).

Quyền mặc định là "được sửa file, không chạy lệnh shell tuỳ ý" ở những CLI phân biệt được hai việc
này. Muốn agent chạy cả test/build: claude `--permission-mode bypassPermissions`, agy
`--dangerously-skip-permissions`, grok `--permission-mode bypassPermissions`, opencode `--auto` (khoá `full_access`).

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
