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
- [ ] Danh mục model trong `CATALOG` (`config.py`) khớp tên CLI thật nhận (codex `gpt-5.5-codex`,
      alias của claude); định dạng output thật của `agy models` / `opencode models` bóc đúng bằng
      `parse_models` (agy cần đăng nhập, chạy qua pty).
- [ ] Kế hoạch JSON của Claude thật được bóc ổn định (`.ateam/logs/lead.log` khi lỗi).

## Backlog tính năng (đã đề xuất với người dùng, chưa làm)

Thứ tự là mức đáng làm ước tính; mỗi mục có gợi ý chỗ sửa.

1. **Best-of-N cho task khó** — chạy cùng task trên 2–3 agent trong worktree riêng, trưởng nhóm chọn
   bản tốt nhất. Gợi ý: cột `variant_of` trong `tasks`; `_run_task` cho mỗi biến thể; một lượt
   `_call_lead` với diff của từng nhánh; merge nhánh thắng, xoá nhánh còn lại.
2. **Giữ phiên làm việc của agent** — dùng `--resume`/`--continue` của từng CLI khi `/retry` hoặc
   vòng sửa test, để agent nhớ ngữ cảnh. Gợi ý: khoá `resume_args` theo agent, lưu session id (đọc từ
   output JSON nếu CLI có) vào cột mới của `tasks`.
3. **Token và chi phí thật** — đọc output JSON (`claude --output-format stream-json`,
   `codex exec --json`, `opencode run --format json`) thay vì ước tính theo ký tự. Cần bộ chuyển
   JSON → dòng chữ cho log/SUMMARY, và giữ đường văn bản hiện tại làm dự phòng. Lưu ý lỗi đã biết:
   `opencode run --format json` có phiên bản thoát trước khi in hết sự kiện.
4. **Nhận việc từ GitHub Issue / Linear** — `ateam issue 123` (dùng `gh issue view --json`) tạo mục
   tiêu; xong thì mở PR (`gh pr create`) với mô tả từ SUMMARY các task.
5. **Playbook dựng sẵn** — mục tiêu theo mẫu (feature: thiết kế → code → test → review → docs;
   bugfix: tái hiện → sửa → test chống tái diễn). Gợi ý: thư mục `playbooks/*.toml`, lệnh
   `/play <tên> <mô tả>` sinh kế hoạch không cần gọi trưởng nhóm.
6. **Thông báo** — macOS (`osascript -e 'display notification …'`), Telegram/Slack webhook khi mục
   tiêu xong hoặc task lỗi. Gợi ý: khối `[notify]`, gọi trong `_review` và nhánh `failed` của `_run_task`.
7. **Agent hỏi lại người dùng** — khối `<<<ASK>>>câu hỏi<<<END>>>` → task chuyển trạng thái `waiting`,
   TUI hiện câu hỏi, câu trả lời được nối vào prompt và task chạy lại.
8. **Phân việc dựa trên lịch sử** — thống kê từ bảng `runs` (tỉ lệ thành công, thời gian theo agent),
   chèn vào `plan_prompt`.
9. **Checkpoint / `/undo`** — git tag trước mỗi mục tiêu; `/undo <mục tiêu>` reset về tag (cần xác
   nhận vì xoá thay đổi).

## Hạn chế đã biết

- Chế độ shared: các task song song cùng sửa một thư mục; verify thấy cả thay đổi của task khác; không
  có diff theo task.
- Worktree cần chạy ở gốc repo đã có ít nhất 1 commit; thư mục chính có thay đổi chưa commit đụng file
  của task thì merge thất bại (`conflict`).
- Giao việc chéo chỉ xảy ra *sau khi* task giao xong (không chờ kết quả giữa chừng).
- `max_concurrent > 1` cho cùng agent ở chế độ shared dễ ghi đè lẫn nhau.
- Token ở `/usage` chỉ là ước tính từ độ dài prompt/output.
- Chưa có Windows (dùng `pty`, `fcntl`, `os.killpg`).
- CI: job macOS + Python 3.13 từng hỏng ngẫu nhiên. Lần 14/10/2026 trên PR #2 bắt được nguyên nhân:
  `agy` giả lập in qua pty rồi thoát ngay, macOS bỏ phần output chưa đọc khi phía slave đóng hết
  → mất sạch output. `Run._run_pty` giờ giữ slave mở tới khi tiến trình thoát rồi đọc nốt. Nếu còn
  hỏng, annotation `pytest` của job sẽ nêu tên test (xem `docs/RELEASING.md`).
