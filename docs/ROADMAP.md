# Lộ trình và việc còn dở

Cập nhật: 14/10/2026, phiên bản 0.3.1.

## Trạng thái hiện tại

Đã có và có test: TUI hai tab, trưởng nhóm lập kế hoạch/review nhiều vòng, phụ thuộc, giao việc chéo,
ghi chú chung, model/effort theo agent và theo task, worktree + merge tự động/duyệt, verify + tự sửa,
nhận diện hết hạn mức + agent dự phòng + trưởng nhóm dự phòng, thống kê `/usage`, CLI headless đầy đủ,
trang docs + cài một lệnh, CI.

## Chưa kiểm chứng với CLI thật (ưu tiên cao)

Toàn bộ test dùng agent giả lập. Người dùng đã xác nhận `ateam doctor` thấy đủ 4 CLI
(claude 2.1.299, codex-cli 0.162.1, agy 1.3.4, opencode 2.0.27) và tên model `xai/grok-build-0.1`,
nhưng chưa có báo cáo chạy thật. Cần xác nhận:

- [ ] `claude --model X --effort Y -p … --permission-mode acceptEdits`: nhận cả hai cờ, sửa được file.
- [ ] `codex exec … -m X -c model_reasoning_effort="Y"`: giá trị TOML có ngoặc kép được chấp nhận.
- [ ] `agy --mode accept-edits --print-timeout 0 --effort Y -p …` qua pty: có output, sửa được file,
      không treo (từng có báo lỗi agy treo khi không có tty).
- [ ] `opencode run --model xai/grok-build-0.1 --variant Y …`: `--variant` có hiệu lực với model Grok
      không; nếu không, để `effort` trống cho grok.
- [ ] Thông báo hết hạn mức thật của từng CLI khớp `LIMIT_RE` và đọc được giờ hồi
      (khi gặp: lấy `ateam log <task>`, thêm mẫu + test).
- [ ] Cú pháp nhắc file (`mentions.SYNTAX`): Claude Code `-p` có đọc `@file` (và `@"có dấu cách"`)
      không; `agy` có hiểu `@file` như Gemini CLI không; `opencode run -f <path>` đính được cả thư mục
      không. Sai thì sửa `SYNTAX` hoặc đặt `file_ref`/`file_args` cho agent đó.
- [ ] Ảnh dán bằng Ctrl+V: `osascript` đọc được ảnh chụp màn hình trên macOS thật (và Ctrl+V tới được
      app trong Terminal/iTerm/Ghostty); `claude -p` có xem được ảnh qua `@ảnh` không; `codex exec
      --image=a.png "…"` không nuốt prompt; `agy` nhận `@ảnh`. Sai thì đặt `image_args`/`file_ref`.
- [ ] Danh mục model trong `CATALOG` (`config.py`) khớp tên CLI thật nhận (codex `gpt-5.5-codex`,
      alias của claude); định dạng output thật của `agy models` / `opencode models` bóc đúng bằng
      `parse_models` (agy cần đăng nhập, chạy qua pty).
- [ ] Mẫu agent Gemini CLI (`gemini --approval-mode auto_edit -p …`, `-m`) và Aider
      (`aider --yes-always --no-auto-commits --message …`, `--model`, `--file`) trong `/custom`
      (`EXTRA_AGENT_TEMPLATES` ở `config.py`) chưa chạy thử trên CLI thật.
- [ ] Kế hoạch JSON của Claude thật được bóc ổn định (`.ateam/logs/lead.log` khi lỗi).
- [ ] Giữ phiên: `claude -p --session-id <uuid>` rồi `--resume <uuid>` trong worktree tạo lại cùng đường dẫn;
      `codex exec resume --skip-git-repo-check -c sandbox_mode="workspace-write" <id> "…"` vẫn sửa được file
      (sandbox qua `-c`); thông báo "mất phiên" thật của codex/grok khớp `SESSION_LOST_RE`; `grok -p --session-id`.
- [ ] Chat (💬): `claude -p --resume`, `codex exec resume`, `grok --resume` nối đúng phiên qua nhiều lượt; "Mở trong
      terminal" (`INTERACTIVE_RESUME`): `claude --resume <id>`, `codex resume <id>`, `grok --resume <id>` mở đúng phiên
      vừa chat headless ở cùng thư mục; Ctrl+C / đổi cỡ cửa sổ trong xterm.js chạy đúng với TUI của từng CLI.
- [ ] Agent thật có tuân thủ `<<<ASK>>>` (chỉ hỏi khi thật mơ hồ, JSON đúng mẫu) không.
- [ ] `ateam web --tunnel` với cloudflared thật: dòng URL trong stderr khớp `TUNNEL_RE`; WebSocket qua tunnel;
      cookie `Secure` khi `X-Forwarded-Proto: https`; mã QR in ra terminal quét được bằng camera iPhone/Android.

## Backlog tính năng (đã đề xuất với người dùng, chưa làm)

Thứ tự là mức đáng làm ước tính; mỗi mục có gợi ý chỗ sửa.

1. **Best-of-N cho task khó** — chạy cùng task trên 2–3 agent trong worktree riêng, trưởng nhóm chọn
   bản tốt nhất. Gợi ý: cột `variant_of` trong `tasks`; `_run_task` cho mỗi biến thể; một lượt
   `_call_lead` với diff của từng nhánh; merge nhánh thắng, xoá nhánh còn lại.
2. ~~**Giữ phiên làm việc của agent**~~ — đã làm (claude, codex, grok; `SESSION_PRESETS`). Còn: agy
   (`--conversation <id>`) và opencode (`--session <id>`) chưa có cách lấy id phiên chắc chắn.
3. **Token và chi phí thật** — đọc output JSON (`claude --output-format stream-json`,
   `codex exec --json`, `opencode run --format json`) thay vì ước tính theo ký tự. Cần bộ chuyển
   JSON → dòng chữ cho log/SUMMARY, và giữ đường văn bản hiện tại làm dự phòng. Lưu ý lỗi đã biết:
   `opencode run --format json` có phiên bản thoát trước khi in hết sự kiện.
4. **Nhận việc từ GitHub Issue / Linear** — `ateam issue 123` (dùng `gh issue view --json`) tạo mục
   tiêu; xong thì mở PR (`gh pr create`) với mô tả từ SUMMARY các task.
5. ~~**Playbook dựng sẵn**~~ — đã làm dưới tên *workflow* (`/custom`, `/flow`, `[workflows.*]`).
   Còn có thể: workflow riêng theo dự án sửa được trong app (hiện `/custom` chỉ ghi file chung).
6. **Thông báo** — macOS (`osascript -e 'display notification …'`), Telegram/Slack webhook khi mục
   tiêu xong hoặc task lỗi. Gợi ý: khối `[notify]`, gọi trong `_review` và nhánh `failed` của `_run_task`.
7. ~~**Agent hỏi lại người dùng**~~ — đã làm (`<<<ASK>>>`, trạng thái `asking`, khung /grill).
8. **Phân việc dựa trên lịch sử** — thống kê từ bảng `runs` (tỉ lệ thành công, thời gian theo agent),
   chèn vào `plan_prompt`.
9. **Checkpoint / `/undo`** — git tag trước mỗi mục tiêu; `/undo <mục tiêu>` reset về tag (cần xác
   nhận vì xoá thay đổi).
10. **Chuyển giao phiên giữa agent** — "nhờ codex review phiên chat với claude": tóm tắt thread chat (`thread_of`) thành
    prompt cho agent khác, mở chat mới với agent đó. Gợi ý: `/handoff <từ> <tới> [yêu cầu]`.
11. **Ngân sách chi phí theo mục tiêu** — `budget = 5.0` (USD) ở cấu hình hoặc `/goal --budget`; cộng `runs.cost` theo
    `goal_id`, vượt thì tạm dừng mục tiêu và hỏi người dùng.
12. **Bảng lệnh (Ctrl+P)** cho cả TUI và web — tìm mờ trên `COMMANDS` + thao tác của tab đang mở.

Ghi chú cho mục 3: khung chat (💬) hưởng lợi nhiều nhất — `claude -p` ở chế độ chữ chỉ in khi xong lượt, nên câu trả lời
chat chưa hiện dần.

## Hạn chế đã biết

- Chế độ shared: các task song song cùng sửa một thư mục; verify thấy cả thay đổi của task khác; không
  có diff theo task.
- Worktree cần chạy ở gốc repo đã có ít nhất 1 commit; thư mục chính có thay đổi chưa commit đụng file
  của task thì merge thất bại (`conflict`).
- Giao việc chéo chỉ xảy ra *sau khi* task giao xong (không chờ kết quả giữa chừng).
- `max_concurrent > 1` cho cùng agent ở chế độ shared dễ ghi đè lẫn nhau.
- Token ở `/usage` chỉ là ước tính từ độ dài prompt/output.
- Chưa có Windows (dùng `pty`, `fcntl`, `os.killpg`).
- Khoá 1 phiên (`.ateam/tui.lock`) chỉ áp cho giao diện (terminal, `ateam web`, `ateam web --tui`). `ateam goal`/`ateam run`
  chạy cùng lúc với giao diện không dọn task của giao diện và không chạy trùng task (`DB.claim_task`), nhưng hai bộ
  lập lịch cùng chạy nên `max_parallel` tính riêng mỗi bên; mở giao diện *sau khi* `ateam goal` đang chạy thì giao
  diện vẫn coi task RUNNING là dở dang.
- CI: job macOS + Python 3.13 từng hỏng ngẫu nhiên. Lần 14/10/2026 trên PR #2 bắt được nguyên nhân:
  `agy` giả lập in qua pty rồi thoát ngay, macOS bỏ phần output chưa đọc khi phía slave đóng hết
  → mất sạch output. `Run._run_pty` giờ giữ slave mở tới khi tiến trình thoát rồi đọc nốt. Nếu còn
  hỏng, annotation `pytest` của job sẽ nêu tên test (xem `docs/RELEASING.md`).
