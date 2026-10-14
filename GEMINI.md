# GEMINI.md

@./AGENTS.md

## Ghi chú riêng cho Gemini CLI / Antigravity

- Mọi quy tắc nằm trong `AGENTS.md` (đã import ở trên) và `docs/`. Nếu import không hoạt động, mở
  `AGENTS.md` đọc trước.
- Chạy `python -m pytest -q` trước và sau khi sửa; test dùng agent giả lập nên không tốn hạn mức.
- Khi được ateam giao task (prompt bắt đầu bằng `You are "…", a member of an AI agent team`),
  làm đúng phạm vi task và kết thúc bằng dòng `SUMMARY:`.
