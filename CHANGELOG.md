# Changelog

## Chưa phát hành

- **Sửa lỗi** `Lỗi: not enough values to unpack (expected at least 2, got 0)` khi gõ `/se` (hoặc `/set`)
  rồi Enter: danh sách gợi ý chèn `/set `, Enter lần nữa chạy `/set` không có tham số. Giờ gõ đủ tên một
  lệnh bắt buộc tham số rồi Enter chỉ chèn dấu cách chờ gõ tiếp; lệnh thiếu/sai tham số (`/set`, `/assign 3`,
  `/retry abc`, …) hiện cách dùng kèm gợi ý lệnh cùng tiền tố (`/set` → *hay ý bạn là /setup?*) thay vì lỗi.
- **`/compact [trọng tâm]`** (và `ateam compact`): trưởng nhóm tóm tắt ghi chú chung, mục tiêu gần đây và
  log hệ thống thành một ghi chú ngắn; prompt gửi agent về sau chỉ mang bản tóm tắt này cùng ghi chú mới
  hơn, thay vì cả chuỗi ghi chú cũ.

## 0.5.1 — 14/10/2026

- **Gõ `/` ở đầu ô nhập** hiện danh sách lệnh kèm tham số và mô tả, gõ tiếp để lọc; Tab chèn lệnh,
  Enter chạy luôn với lệnh không cần tham số. Gõ sai lệnh thì gợi ý lệnh gần nhất (`/stup` → `/setup`).
- **Trợ giúp trong bảng nổi** (`F1` hoặc `/help`): lệnh tô màu theo mục, đủ rộng để không bị gãy dòng
  như khi in vào cột log. Lần đầu mở app chỉ in phần *bắt đầu nhanh* thay vì toàn bộ trợ giúp.
- Bảng việc trống có hướng dẫn cách giao việc; mục tiêu chờ duyệt nhắc Ctrl+G; mục tiêu đang lập kế
  hoạch/review có spinner; cột trạng thái có biểu tượng (✓ ✗ ✎ ◆ …, spinner khi đang chạy).
- Thanh agent chỉ xuống dòng giữa các agent (không cắt đôi "(mặc định)"); terminal hẹp (< 140 cột) nới
  cột bảng việc để cột *Task* không bị đẩy mất; ô agent ở tab Đội gọn hơn (token ước tính xem ở `/usage`).
- Form workflow: tiêu đề cột thẳng hàng với ô nhập, ô chọn agent không còn bị gãy thành 2 dòng.

## 0.5.0 — 14/10/2026

- Thêm **agent và workflow tuỳ chỉnh**: `/custom` (hoặc nút *Agent & workflow tuỳ chỉnh…* ở màn hình
  thiết lập) mở màn hình quản lý cùng kiểu màn hình thiết lập. Form thêm agent có mẫu (claude, codex,
  agy, opencode, Gemini CLI, Aider, trống), các ô lệnh/vai trò/model/effort/cú pháp `@file`/dự phòng và
  dòng xem trước lệnh thật. Agent mới vào đội ngay, không cần mở lại app.
- Workflow = chuỗi bước dựng sẵn (agent, tiêu đề, prompt có `{goal}`, chạy sau bước nào, effort riêng),
  chạy bằng `/flow <tên> <mục tiêu>` hoặc `ateam flow <tên> <mục tiêu>` mà không cần trưởng nhóm lập kế
  hoạch; có mẫu tính năng mới, sửa lỗi, review code. `ateam flows` / `/flow` liệt kê.
- Lưu ở `~/.config/ateam/custom.toml` (khoá `[agents.*]`, `[workflows.*]` dùng được cả trong file cấu
  hình); file này không bị thay khi `config.toml` nâng cấp. DB thêm cột `goals.workflow`.

- Thêm màn hình **Thiết lập đội AI** khi mở app lần đầu (mở lại: `/setup` hoặc `ateam setup`): chọn
  agent nào tham gia, trưởng nhóm, model và effort từng agent trong một màn hình; Ctrl+S lưu, Esc bỏ
  qua. Trước khi hiện form, ateam hỏi **song song** các CLI có lệnh liệt kê model (`opencode models`,
  `agy models`, tối đa 20 giây) để bảng chọn có sẵn model thật; lỗi hoặc hết giờ thì dùng danh mục có sẵn.
- Lựa chọn lưu ở `state.json` (`agents.<tên>.enabled`, `lead`, `onboarded`); chỉ ghi giá trị khác file
  cấu hình, nên sửa file vẫn có tác dụng.
- `ateam models --refresh` và lần hỏi model khi mở app giờ chạy song song.
- **Dán ảnh** vào ô nhập bằng **Ctrl+V** (macOS: `osascript`/`pngpaste`; Linux: `wl-paste`/`xclip`):
  ảnh lưu ở `.ateam/images/` và được chèn dạng `@ảnh`; kéo-thả file ảnh vào terminal cũng thành `@ảnh`.
  Mỗi agent nhận ảnh theo CLI của nó: Codex thêm cờ `--image=…`, OpenCode `-f`, Claude/agy `@ảnh`.
  Khoá mới `image_args` theo agent. Ảnh trong `.ateam/` (không có ở worktree) được truyền bằng đường dẫn tuyệt đối.

## 0.4.0 — 14/10/2026

- Gõ `@` trong ô nhập để chọn file/thư mục của dự án (lọc khi gõ, ↑↓ chọn, Tab/Enter chèn, Esc đóng).
  Khi chạy, `@đường/dẫn` được đổi sang cú pháp của từng agent: `@path` cho Claude Code và agy, đường
  dẫn thường cho Codex, đường dẫn + `-f path` cho OpenCode. Khoá mới `file_ref`/`file_args` theo agent
  để tự chỉnh; `ateam doctor` và `/agents` in cú pháp đang dùng.
- Thêm: xem model và effort mỗi agent hỗ trợ. Tab Đội hiện danh sách ngay trong ô từng agent (mục đang
  dùng tô đậm); `/model <agent>` và `/effort <agent>` (không kèm giá trị) hoặc bấm vào tiêu đề ô agent
  mở bảng chọn; lựa chọn được lưu và đi thẳng vào cờ CLI như `/model <agent> <tên>`.
- Thêm `/models [agent]`, `ateam models [agent] [--refresh]`. Danh mục model/effort có sẵn cho
  claude, codex, agy, opencode; với `opencode models` / `agy models`, ateam hỏi CLI danh sách thật
  (lần đầu mở app, hoặc `/models <agent> làm mới`) và lưu vào `state.json`.
- Khoá cấu hình mới (không bắt buộc): `models`, `models_command`, `models_filter`.
- Trang docs: thêm khối `previews` vào `wrangler.jsonc` để Workers Builds dựng được bản xem trước cho
  nhánh PR.

## 0.3.1 — 14/10/2026

- Sửa: phím tắt Ctrl+D, Ctrl+K… không có tác dụng khi con trỏ đang ở ô nhập (mặc định khi mở app) —
  ô nhập của Textual nuốt phím. Các phím tắt của app giờ có `priority=True`.
- Sửa: `ateam merge` (dòng lệnh) thất bại trên máy chưa cấu hình git identity vì không chạy bước
  setup; identity dự phòng `ateam <ateam@localhost>` giờ được kiểm tra ngay trước mỗi commit/merge.
- Thêm bộ test tự động (19 test, agent giả lập trong `tests/fakebin`) và CI GitHub Actions
  (Ubuntu + macOS, Python 3.9 và 3.13).
- Thêm tài liệu cho người phát triển và AI agent: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `docs/`.
- Bỏ hàm thừa `runner.build_argv`.

## 0.3.0 — 14/10/2026

- Tự kiểm tra sau mỗi task: `[verify]`, `/verify <lệnh>`; test fail thì giao sửa kèm log (tối đa
  `max_fix_attempts`), bỏ qua khi task không đổi file.
- Chế độ worktree `merge = "review"`: task dừng ở "chờ duyệt"; `/diff` (Ctrl+D), `/merge` (Ctrl+Y),
  `/reject <task> [góp ý]`; CLI `ateam diff|merge|reject`.
- Hạn mức: nhận diện thông báo rate limit/usage limit, tạm nghỉ đến giờ hồi, chuyển task sang
  `fallback`, trưởng nhóm dự phòng `lead_fallback`; `/usage`, `/cooldown`, `ateam usage|cooldown`.
- Bảng `runs` thống kê lượt chạy; cột task `base`, `head`, `attempts`.
- Cấu hình lên `config_version = 3` (file cũ được sao lưu và thay).
- Trang docs + gói tải trên Cloudflare Workers; cài một lệnh qua `scripts/get.sh`.

## 0.2.0 — 14/10/2026

- Tab "Đội" (Ctrl+T): ô log trực tiếp cho từng agent, task đang chạy, thời gian, cảnh báo im lặng,
  timeline Gantt.
- Model và effort theo agent (`/model`, `/effort`, `ateam set`, lưu ở `state.json`) và theo task
  (`/task agent:model@effort`, `/set`); trưởng nhóm tự chọn effort (`lead_sets_effort`).
- Cấu hình `config_version = 2` với `model_args`/`effort_args`/`efforts`; agy chạy với
  `--mode accept-edits --print-timeout 0`; grok dùng `opencode run` + `model`.

## 0.1.0 — 14/10/2026

- Bản đầu: TUI Textual, bảng việc SQLite, trưởng nhóm lập kế hoạch/review, phụ thuộc, giao việc chéo
  (`<<<DELEGATE>>>`), ghi chú (`<<<NOTE>>>`), chế độ shared/worktree, CLI headless, `install.sh`.
