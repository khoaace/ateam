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
   `ateam set`, wizard `/setup`), `lead` (vai trò Trưởng nhóm ở `/setup`), `default_workflow` (chỉ còn đọc: lựa chọn
   chung của bản ≤ 0.52, dùng cho dự án chưa tự chọn — xem `.ateam/state.json` dưới), `lang` (`vi`/`en`, `/lang`, `ateam lang`), `theme` / `accent` (theme Textual và màu nhấn, `/theme`), `vim` (`false` = tắt phím vim ở tab 📝 Code, `/vim off`), `fmt_save` / `autosave` (tab Code của web: format khi lưu, tự lưu — `>Bật/tắt…` trong palette; vắng = tắt), `commit_agent` (agent viết commit message ở tab 🌿 Git, chọn cạnh nút ✨; vắng = trưởng nhóm), `git_tree` (`true` = tab 🌿 Git của TUI hiện file thay đổi theo cây thư mục, phím `t`; web nhớ riêng trong trình duyệt), `code_side_w` (độ rộng cột file tab 📝 Code của TUI do người dùng kéo / `:files N`; vắng = mặc định; web nhớ riêng trong trình duyệt), `notify` (`app` = chỉ toast/chuông trong app, `off` = tắt; vắng = cả thông báo hệ thống/trình duyệt — `/notify`), `approve_plan` / `auto_review` (kiểu làm việc ở `/setup`; chỉ ghi khi khác `true`), `onboarded` (đã qua
   wizard lần đầu; xoá khoá này để hiện lại), `models_found.<tên>` (model hỏi được từ CLI qua `models_command`),
   `recent_projects` (dự án mở gần đây, tối đa 20, cho `/open`; ghi mỗi lần mở TUI / `ateam web`), và
   `<dự án>/.ateam/state.json` → `default_workflow` (workflow chạy khi gõ mục tiêu ở dự án này — F4 / nút cạnh ô nhập, ★
   ở trang Workflows, popup Luồng mặc định, wizard đặt `tinh-nang` khi chọn kiểu "theo quy trình cố định"; `""` = trưởng
   nhóm lập kế hoạch; vắng = theo `default_workflow` chung cũ; workflow đã bị xoá thì bỏ qua), `verify_command` (đặt bằng `/verify` hoặc bước *Lệnh kiểm tra*), `isolation` /
   `merge` (bước *An toàn & duyệt code*, riêng từng dự án), `quality` (preset chất lượng chọn ở popup *Luồng mặc
   định* → ★ Trưởng nhóm lập kế hoạch; vắng = `auto`).
   Agent wizard tự tạo thêm (cùng CLI, model khác, vd `claude-review`) nằm trong `custom.toml` với `wizard = true`;
   chạy lại wizard thì các agent này được xoá và tạo lại.
6. Riêng từng task: cột `model`/`effort` (`/task agent:model@effort`, `/set`, kế hoạch của trưởng nhóm).

Tab ✅ To-do lưu ở `~/.config/ateam/todos/<tên thư mục>-<10 ký tự sha1 của đường dẫn>.json` (mảng
`{id, text, done, created, tags?, due?, priority?, desc?, updated?, done_at?}`, `ateam/todos.py`) — cố ý **ngoài** dự
án để không phải `.gitignore`; đổi tên/chuyển thư mục dự án thì danh sách cũ nằm lại ở file theo đường dẫn cũ.
`tags` là mảng id tag; `due` là `YYYY-MM-DD` hoặc `YYYY-MM-DDTHH:MM` (giờ máy); `priority` 0–3 (không · thấp · vừa · cao).
Tag dùng chung cho To-do và Ghi chú ở `~/.config/ateam/tags/<cùng tên file>.json` (mảng `{id, name, color}`, thứ tự
trong mảng = thứ tự hiển thị; xoá / gộp tag thì sửa luôn cả hai file). Ghi chú (tab 🗒 Ghi chú, `ateam/notes.py`) ở
`~/.config/ateam/notes/<cùng tên file>.json`: mảng `{id, title, body, tags, pinned, created, updated}`; lưu kèm
`updated` đã đọc nên hai nơi cùng sửa không đè mất nhau.

Rule của dự án (`/rules`, `ateam/rules.py`) lưu cùng kiểu, ở `~/.config/ateam/rules/<cùng tên file>.json`: mảng
`{id, title, text, enabled, targets, created}`; `targets` rỗng = mọi agent, `"agent:<tên>"` / `"role:<vai trò>"`
(`role:lead` = trưởng nhóm, gồm mọi lượt lập kế hoạch / review / viết commit message của ai làm thay).

Skill (`/skills`, trang 🧩 Skills, `ateam/skills.py`): thư viện riêng của ateam ở `~/.config/ateam/skills/<tên>/SKILL.md`
(chuẩn Agent Skills: frontmatter `name` / `description` + markdown, có thể kèm `scripts/`, `references/`; skill cài từ
git có thêm `.ateam-source.json` ghi url / ref / commit). ateam còn đọc (không sửa) skill trong thư mục của từng CLI
(`~/.claude/skills`, `~/.codex/skills`, `~/.agents/skills`, `~/.gemini/antigravity/skills`, `~/.grok/skills`,
`~/.config/opencode/skill(s)`) và trong repo (`.agents/skills`, `.claude/skills`, `.opencode/skill(s)`, `.grok/skills`).
Bật/tắt theo dự án ở `~/.config/ateam/skill-sets/<cùng tên file>.json`: `{"on": [...], "off": [...]}` — mặc định bật
skill của dự án và thư viện, tắt skill trong thư mục CLI. `ATEAM_SKILLS_HOME` đổi thư mục nhà để tìm skill của CLI (test).

Workflow riêng của dự án (ô *Chỉ dùng cho dự án này* ở form workflow) ở `~/.config/ateam/workflows/<cùng tên file>.json`:
`{"<tên>": {thân như [workflows.<tên>] của custom.toml}}` — gộp sau `custom.toml`, trước `.ateam/config.toml`; trùng
tên thì thay hẳn bản chung (không gộp từng khoá).

Bản tổng quan dự án (`/init`, `ateam/overview.py`) ở `<dự án>/.ateam/project.md` (trong `.ateam/` nên git bỏ qua):
dòng đầu `<!-- ateam:init commit=<sha> date=<YYYY-MM-DD> -->`, còn lại là markdown — sửa tay được, `/init` lần sau
giữ phần người dùng sửa. Xoá file = thôi gửi kèm prompt.

Lịch `/schedule` nằm trong bảng `schedules` của `.ateam/team.db` (chỉ chạy khi một phiên ateam đang mở). Điểm khôi
phục `/undo` là ref git `refs/ateam/checkpoints/m<id>` (commit) + `…/m<id>-tree` (ảnh chụp thư mục làm việc) và
`refs/ateam/checkpoints/redo`; nhánh lúc chụp ghi ở `.ateam/checkpoints.json`. Xoá: `git update-ref -d <ref>`.

`XDG_CONFIG_HOME` đổi được vị trí thư mục `~/.config`.
`ATEAM_NO_UPDATE_CHECK=1` tắt việc hỏi trang docs có bản ateam mới mỗi lần mở TUI / `ateam web` (web hỏi lại mỗi 6
giờ); test đặt sẵn trong `tests/conftest.py`.

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
| `quality` | `"auto"` | Preset chất lượng khi trưởng nhóm lập kế hoạch: `"fast"` (test chỉ khi rủi ro, không task review, bỏ review cuối khi mọi task xong và qua kiểm tra), `"auto"` (trưởng nhóm tự quyết test / task review cho thay đổi rủi ro hoặc lớn), `"strict"` (test bắt buộc; thiếu task review thì ateam thêm). Không có trong file mặc định; `quality` trong `<dự án>/.ateam/state.json` (popup *Luồng mặc định*) thắng. Kiểm tra cuối giống nhau ở mọi preset: có lệnh verify và ≥2 task chạy song song thì ateam thêm task `verify` |

## `[prices."<model>"]` (tuỳ chọn)

Giá (USD / 1 triệu token) để dashboard tính cost, khớp khi tên model **chứa** chuỗi khoá; ghi đè bảng giá có sẵn
(`usage_logs.PRICES`, ước tính theo bảng giá công khai). `cache_read` mặc định 0,1 × `input`, `cache_write` 1,25 ×
`input`. Model không có giá thì cost hiện "—".

```toml
[prices."gpt-6.1"]
input = 1.5
output = 12
cache_read = 0.15
```

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
| `lead_fallback` | `["codex"]` | Ai lập kế hoạch/review thay khi trưởng nhóm hết hạn mức, quá tải hoặc quá `lead_timeout` |
| `lead_timeout` | `600` | Giây tối đa cho một lượt trưởng nhóm (lập kế hoạch, hỏi đáp, review) — quá thì dừng và thử `lead_fallback` (CLI treo không in gì, vd agy). Không vượt `timeout` của agent (nếu agent có đặt); `0` = chỉ theo `timeout` của agent. Không có trong file mặc định: tự thêm vào `[limits]` khi cần |

Máy chủ của nhà cung cấp **quá tải** (agy "high traffic… No capacity available", lỗi 503/529, `overloaded`) được xử lý
như hết hạn mức nhưng chỉ nghỉ `OVERLOAD_MINUTES` (3 phút, `limits.py`): task chuyển cho agent dự phòng hoặc tự chạy
lại khi hết nghỉ.

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
| `usage_command` | danh mục | argv in hạn mức/usage của CLI cho `/usage`: `claude -p /usage`, `agy -p /usage` (qua pty nếu `pty = true`), `opencode stats --days 7`; tối đa 20 dòng. Vắng với `codex` = đọc `rate_limits` trong file phiên mới nhất ở `$CODEX_HOME/sessions` (mặc định `~/.codex`); vắng với `grok` = `grok usage <phiên>` cho các phiên 7 ngày qua ở `$GROK_HOME/sessions` (mặc định `~/.grok`), cộng token & chi phí hôm nay / 7 ngày |
| `models_command` | danh mục | argv liệt kê model thật (`opencode models`, `agy models`, `codex debug models`; output dạng chữ mỗi dòng một model, hoặc JSON `{"models": [{"slug", "visibility"}]}` thì bỏ model `hide`); chạy song song ở màn hình thiết lập (`/setup`, lần đầu mở app), khi mở app mà chưa có kết quả, hoặc `/models <agent> làm mới`, kết quả lưu ở `state.json` và đứng trước `models` |
| `models_filter` | `""` | Chỉ giữ model chứa chữ này. Vắng: nếu có model chứa tên agent (vd `grok`) thì chỉ giữ các model đó |
| `fallback` | `[]` | Agent thay thế khi agent này hết hạn mức (theo thứ tự) |
| `verify` | `true` | `false` = không chạy `[verify]` sau task của agent này |
| `timeout` | `0` | Giây tối đa cho một lượt chạy task; `0` = không giới hạn (mặc định từ bản cấu hình 10 — agent làm lâu như agy vẫn đang chạy tốt thì không bị cắt; dừng tay bằng nút huỷ). Nâng cấp lên bản 10 bỏ `timeout = 1800` (mặc định cũ) khỏi agent tuỳ chỉnh trong `custom.toml` |
| `max_concurrent` | `1` | Số task cùng lúc của agent này |
| `pty` | `false` | Chạy trong pseudo-terminal (cần cho `agy`) |
| `plan_command` | — | argv riêng khi agent lập kế hoạch/review (vd chế độ chỉ đọc) |
| `enabled` | `true` | `false` = tạm tắt |
| `file_ref` | theo lệnh | Cách viết file được nhắc bằng `@` trong prompt; `{path}` được thay. Vắng = theo `mentions.SYNTAX`: `"@{path}"` cho `claude`/`agy`/`gemini`, `"{path}"` cho lệnh khác |
| `file_args` | theo lệnh | Cờ thêm vào lệnh cho mỗi file/thư mục được nhắc (chèn trước prompt). Vắng = `["-f", "{path}"]` cho `opencode`, `[]` cho lệnh khác; `[]` = tắt |
| `session_args` | theo lệnh | Cờ đặt id phiên cho lượt mới (`{session}` = uuid ateam sinh). Vắng = `SESSION_PRESETS` (`config.py`): claude/grok `["--session-id", "{session}"]`, codex/agy `[]` (id bắt từ output) |
| `resume_args` | theo lệnh | Cờ tiếp tục phiên `{session}` khi `/retry`, vòng sửa verify, trả lời `<<<ASK>>>`, `/continue`. Vắng = preset: claude/grok `["--resume", "{session}"]`, codex `["{session}"]` (ateam đổi lệnh sang `codex exec resume`), agy `["--conversation", "{session}"]`; `[]` = tắt (luôn gửi lại đủ ngữ cảnh) |
| `session_re` | theo lệnh | Regex (nhóm 1 = id) bắt id phiên trong output khi CLI không cho tự đặt id. Vắng = preset: codex `session id:\s*([0-9a-fA-F-]{36})`, agy `agy conversation ([0-9a-fA-F-]{36})` (dòng `agystream.py` in từ sự kiện `init`) |
| `stream_args` | theo lệnh | Cờ cho CLI in output dạng sự kiện, ateam đọc thành dòng log (chèn trước prompt nếu lệnh chưa tự đặt cờ đó). Vắng = preset: agy `["--output-format", "stream-json"]` — thấy từng bước tool lúc đang chạy, id phiên, token thật (`agystream.py`); `[]` = tắt (agy chỉ in câu trả lời cuối) |
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
| `prompt` | tiêu đề | Nội dung task; `{goal}` được thay (mục tiêu luôn có trong prompt dù không dùng `{goal}`); `$tên-skill` gắn skill cho bước |
| `after` | bước liền trước | Số thứ tự bước (từ 1) phải xong trước; `[]` = chạy ngay |
| `effort`, `model` | `""` | Riêng cho task của bước này (không bị lọc như effort trưởng nhóm đặt) |
| `type` | `"code"` | `"code"` làm việc; `"review"` agent xem diff của các bước nó chờ, tự sửa lỗi nhỏ, giao lỗi lớn cho tác giả; `"verify"` ateam chạy lệnh `[verify]` một lần trên kết quả gộp của các bước nó chờ, fail mới gọi `agent` của bước sửa (chưa đặt lệnh → bước xong ngay); `"gate"` ⏸ bước chờ người dùng duyệt (không gọi agent, `agent` bỏ qua): Tiếp tục / Dừng / góp ý để các bước nó chờ làm lại, `ateam flow -y` tự duyệt. Workflow không bị thêm/bớt bước theo `quality` |

## Mặc định của 5 agent (config_version 9)

| Agent | command | model_args / effort_args | efforts | fallback |
| --- | --- | --- | --- | --- |
| `claude` | `claude -p {prompt} --permission-mode acceptEdits` | `--model` / `--effort` | low, medium, high, xhigh, max | codex |
| `codex` | `codex exec --sandbox workspace-write --skip-git-repo-check {prompt}` | `-m` / `-c model_reasoning_effort="…"` | low…ultra | claude |
| `antigravity` | `agy --mode accept-edits --print-timeout 0 -p {prompt}` (pty) | `--model` / `--effort` | low…max | claude, codex |
| `grok` | `grok --permission-mode auto --deny Bash -p {prompt}` (Grok Build CLI; `acceptEdits` ở chế độ `-p` chặn cả sửa file) | `-m` / `--reasoning-effort` | low, medium, high, xhigh | codex |
| `opencode` | `opencode run {prompt}`, model `xai/grok-build-0.1` | `--model` / `--variant` (1.x), `--model provider/model#effort` (2.x) | theo catalog từng model | codex |

**OpenCode 1.x / 2.x.** ateam dò phiên bản bằng `opencode --version` một lần cho mỗi đường dẫn binary trong
phiên đang chạy, kể cả agent tuỳ chỉnh. Hai mẫu `effort_args = ["--variant", "{effort}"]` và
`["--model", "{model}#{effort}"]` được chọn lại theo phiên bản lúc dựng lệnh; file cấu hình giữ nguyên.
OpenCode 1.x dùng `models --verbose` và `run --variant`; OpenCode 2.x đã bỏ hai cờ này, dùng
`api model.list --param 'location[directory]=<gốc dự án>'` để lấy catalog và `run --model provider/model#effort`.
Hai mẫu `models_command` có sẵn (`opencode models`, `opencode models --verbose`) tự dùng API khi chạy 2.x;
lệnh liệt kê tuỳ chỉnh khác được giữ nguyên. Tham số `location[directory]` bảo đảm đọc catalog đúng dự án,
không lấy thư mục mặc định của server. Nếu không dò được phiên bản, ateam báo lỗi và giữ cú pháp cấu hình.

OpenCode 2.x đồng bộ catalog khi mở app dù đã có cache. API lỗi thì thử `opencode models`, báo thiếu metadata
và không gửi effort chưa xác định; cả hai lệnh lỗi thì giữ cache trước đó. Không chọn model cụ thể cũng không
gửi effort cho OpenCode 2. Không lưu/log `settings`, `headers` hoặc thông tin xác thực từ catalog.
Không cần sửa file cấu hình hoặc tăng `config_version` cho cơ chế nhận diện này.
Tham chiếu `@thư_mục` giữ đường dẫn trong prompt và bỏ cờ `-f` (CLI chỉ nhận file). Với OpenCode 2,
ateam chặn tệp đính kèm vượt 10 MiB trước khi chạy, cả khi lập kế hoạch hoặc thực hiện task. Web giới hạn
ảnh tải lên 10 MiB khi có agent OpenCode 2 đang bật; đội khác vẫn dùng giới hạn chung 20 MiB.

**Grok Build.** Danh sách dạng chữ chỉ đọc phần sau `Available models:` và nhận tên bắt đầu bằng `grok-`.
Thông báo chưa đăng nhập không được lưu thành tên model. Cache sai từ bản cũ được lọc khi nạp cấu hình;
lần làm mới lỗi giữ danh sách đã có.

**Effort theo từng model.** `efforts` là danh sách chung; mức riêng của từng model được hỏi từ CLI cùng lúc với
danh sách model (`/models <agent> làm mới`, tự hỏi khi mở app) và lưu ở `state.json` (`model_efforts`): codex
`codex debug models` (`supported_reasoning_levels`), OpenCode 1.x `opencode models --verbose` (`variants`),
OpenCode 2.x `api model.list` (`data[].variants[].id`; model không có variant = không gửi effort).
agy suy từ tên: `gemini-4-argon-low/-medium/-high` → effort đổi sang đúng
biến thể, model không có biến thể (claude-*) không nhận effort. Effort đang chọn không có ở model thì tự đổi sang
mức gần nhất (`nearest_effort`, hoà lấy mức cao hơn) và ghi một dòng log. `models_found_v` trong `state.json`:
danh sách model lưu bởi bản cũ hơn 2 bị bỏ (bản 0.19.2–0.20.2 bóc rác từ JSON một dòng của codex) và hỏi lại.

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
