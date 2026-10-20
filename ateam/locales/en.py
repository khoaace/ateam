"""Bản dịch tiếng Anh: khoá = chuỗi tiếng Việt gốc trong tr(...). Thêm chuỗi mới: bọc tr("…") ở code
rồi thêm một dòng ở đây (tests/test_i18n.py báo chuỗi nào còn thiếu)."""

from __future__ import annotations

EN: dict[str, str] = {
    "Tệp {path} vượt giới hạn đính kèm {n} MiB của OpenCode. Hãy giảm dung lượng hoặc chia nhỏ tệp.":
        "File {path} exceeds OpenCode's {n} MiB attachment limit. Reduce its size or split the file.",
    "Grok chưa đăng nhập; danh sách có thể chỉ gồm model mặc định. Chạy `grok login`.":
        "Grok is not signed in; the list may only contain default models. Run `grok login`.",
    "chưa cài lệnh '{v}'":
        "command '{v}' is not installed",
    "trợ giúp thoát với mã {code}":
        "help exited with code {code}",
    "trợ giúp không có nội dung":
        "help returned no content",
    "hết thời gian đọc trợ giúp":
        "timed out reading help",
    "không chạy được lệnh trợ giúp":
        "could not run the help command",
    "     ✗ Không kiểm tra được `{cmd}`: {why}":
        "     ✗ Could not check `{cmd}`: {why}",
    "⚠ Không nhận diện được phiên bản OpenCode ({binary}); giữ cú pháp cấu hình hiện tại.":
        "⚠ Could not detect the OpenCode version ({binary}); keeping the configured syntax.",
    "⚠ OpenCode: đã lấy danh sách model nhưng thiếu metadata effort; tạm dùng effort mặc định của CLI.":
        "⚠ OpenCode: models loaded without effort metadata; using the CLI default effort for now.",
    "OpenCode: không lấy được catalog model ({why}); giữ danh sách đã lưu.":
        "OpenCode: could not load the model catalog ({why}); keeping the saved list.",
    "{agent}: không thấy model nào":
        "{agent}: no models found",
    "✓ Đã đổi ngôn ngữ sang {v}":
        "✓ Language changed to {v}",
    "Cấu hình chung: {GLOBAL_CONFIG}":
        "Global config: {GLOBAL_CONFIG}",
    "Cấu hình:":
        "Config:",
    "Kiểm tra sau task: {v}   ·   trưởng nhóm dự phòng: {v2}\n":
        "Check after each task: {v}   ·   backup leads: {v2}\n",
    "\nChọn agent, model, effort: ateam setup (hoặc /setup trong app).":
        "\nPick agents, models, effort: ateam setup (or /setup in the app).",
    "Thêm agent / workflow riêng: /custom trong app (hoặc nút ở màn hình thiết lập).":
        "Add your own agents / workflows: /custom in the app (or the button on the setup screen).",
    "\nChạy: ateam flow <tên> \"mục tiêu\"   ·   trong app: /flow <tên> <mục tiêu>":
        "\nRun: ateam flow <name> \"goal\"   ·   in the app: /flow <name> <goal>",
    "Đã thêm task #{tid} cho {to}. (Chạy khi `ateam` đang mở, hoặc `ateam run`)":
        "Added task #{tid} for {to}. (Runs while `ateam` is open, or with `ateam run`)",
    "Đã ghi chú.":
        "Note saved.",
    "Đặt: ateam set <agent> --model <tên> --effort <mức>":
        "Set: ateam set <agent> --model <name> --effort <level>",
    "Lệnh kiểm tra của dự án: {v}":
        "Project check command: {v}",
    "Ngôn ngữ hiện tại: {v} — đổi bằng `ateam lang en` hoặc `ateam lang vi`":
        "Current language: {v} — change with `ateam lang en` or `ateam lang vi`",
    "Không hỗ trợ '{code}' — chọn: {v}":
        "'{code}' is not supported — choose: {v}",
    "(mặc định)":
        "(default)",
    " (đang tắt)":
        " (disabled)",
    " (tuỳ chỉnh)":
        " (custom)",
    "\n✗ Trưởng nhóm '{lead}' không có trong [agents].":
        "\n✗ Lead '{lead}' is not in [agents].",
    "\n⚠ Chưa có git — chế độ worktree sẽ không dùng được.":
        "\n⚠ git is not installed — worktree mode won't work.",
    "\nWorkflow: {v}  (xem: ateam flows)":
        "\nWorkflows: {v}  (see: ateam flows)",
    "\nMọi thứ sẵn sàng.":
        "\nAll set.",
    "\nCài các CLI còn thiếu hoặc đặt enabled = false cho agent đó trong config.":
        "\nInstall the missing CLIs, or set enabled = false for that agent in the config.",
    "\n=== Mục tiêu #{gid}: {status} ===":
        "\n=== Goal #{gid}: {status} ===",
    "Chưa có workflow nào. Tạo trong app: /custom (hoặc nút ở màn hình `ateam setup`).":
        "No workflows yet. Create one in the app: /custom (or the button on the `ateam setup` screen).",
    "Không có agent '{to}'. Có: {v}":
        "No agent '{to}'. Available: {v}",
    "Đã chạm giới hạn số tầng giao việc.":
        "Delegation depth limit reached.",
    "Chưa có log.":
        "No log yet.",
    "Không có agent '{agent}'. Có: {v}":
        "No agent '{agent}'. Available: {v}",
    "⚠ '{effort}' không nằm trong {efforts} — vẫn lưu, nhưng CLI có thể báo lỗi.":
        "⚠ '{effort}' is not in {efforts} — saved anyway, but the CLI may reject it.",
    "Task đã xếp hàng lại — mở `ateam` hoặc chạy `ateam run` để làm lại.":
        "Task re-queued — open `ateam` or run `ateam run` to redo it.",
    "Lệnh kiểm tra: {v}":
        "Check command: {v}",
    "7 ngày":
        "7 days",
    "24 giờ":
        "24 hours",
    "Đang tạm nghỉ: ":
        "Cooling down: ",
    "{agent} hoạt động lại.":
        "{agent} is active again.",
    "{agent} tạm nghỉ {minutes} phút.":
        "{agent} is cooling down for {minutes} min.",
    "AI Team — điều phối nhiều AI agent CLI.":
        "AI Team — orchestrate several AI coding agent CLIs.",
    "thư mục dự án (mặc định: thư mục hiện tại)":
        "project directory (default: current directory)",
    "ngôn ngữ giao diện cho lần chạy này (vi | en)":
        "interface language for this run (vi | en)",
    "mở giao diện terminal (mặc định)":
        "open the terminal UI (default)",
    "mở giao diện trên trình duyệt (http://127.0.0.1:PORT, cần textual-serve)":
        "open the interface in a browser (http://127.0.0.1:PORT, needs textual-serve)",
    "Cần cài thêm textual-serve: {v}":
        "textual-serve is required: {v}",
    "Mở trên trình duyệt: {v}  (Ctrl+C để dừng)":
        "Open in your browser: {v}  (Ctrl+C to stop)",
    "Dự án này đang mở ở một phiên ateam khác (terminal hoặc tab web).\nĐóng phiên đó rồi mở lại.  ·  Ctrl+Q để thoát":
        "This project is already open in another ateam session (terminal or web tab).\nClose that one and try again.  ·  Ctrl+Q to quit",
    "xem / đổi ngôn ngữ giao diện (vi | en), lưu cho các lần sau":
        "show / change the interface language (vi | en), saved for next time",
    "mở giao diện ở màn hình thiết lập: agent, trưởng nhóm, model, effort":
        "open the UI on the setup screen: agents, lead, model, effort",
    "tạo file cấu hình":
        "create the config file",
    "tạo thêm .ateam/config.toml cho dự án":
        "also create .ateam/config.toml for the project",
    "kiểm tra các agent đã cài chưa":
        "check which agents are installed",
    "giao mục tiêu và chạy không cần giao diện":
        "give a goal and run it without the UI",
    "không hỏi duyệt kế hoạch":
        "don't ask to approve the plan",
    "không in log chi tiết của agent":
        "don't print detailed agent logs",
    "tiếp tục mục tiêu (m12) hoặc thread /task (t40) đã xong":
        "continue a finished goal (m12) or /task thread (t40)",
    "m<số> = mục tiêu, t<số> = task":
        "m<number> = goal, t<number> = task",
    "yêu cầu mới":
        "new request",
    "chạy mục tiêu theo workflow tuỳ chỉnh (không cần giao diện)":
        "run a goal with a custom workflow (no UI)",
    "tự duyệt các bước":
        "auto-approve the steps",
    "liệt kê workflow tuỳ chỉnh":
        "list custom workflows",
    "thêm 1 task vào bảng (agent cũng gọi được lệnh này)":
        "add a task to the board (agents can call this too)",
    "tên agent":
        "agent name",
    "model riêng cho task này":
        "model just for this task",
    "effort riêng cho task này":
        "effort just for this task",
    "đặt model / effort mặc định cho 1 agent":
        "set the default model / effort of an agent",
    "tên model, '-' để về mặc định":
        "model name, '-' to reset to default",
    "mức effort, '-' để về mặc định":
        "effort level, '-' to reset to default",
    "xem model / effort mỗi agent hỗ trợ":
        "show the models / effort levels each agent supports",
    "hỏi CLI danh sách model thật (opencode models, agy models)":
        "ask the CLI for its real model list (opencode models, agy models)",
    "ghi chú chung cho cả đội":
        "shared note for the whole team",
    "trưởng nhóm tóm tắt ghi chú & mục tiêu thành 1 ghi chú ngắn":
        "the lead summarizes notes & goals into one short note",
    "điều cần giữ trong bản tóm tắt (tuỳ chọn)":
        "what to keep in the summary (optional)",
    "liệt kê mục tiêu và task":
        "list goals and tasks",
    "in log của 1 task (hoặc 'sys')":
        "print a task's log (or 'sys')",
    "xem thay đổi của 1 task":
        "show a task's changes",
    "merge task đang chờ duyệt":
        "merge a task waiting for review",
    "từ chối task đang chờ duyệt (kèm góp ý = giao làm lại)":
        "reject a task waiting for review (with feedback = redo it)",
    "đặt lệnh kiểm tra sau mỗi task cho dự án (off = tắt)":
        "set the check command run after each task for this project (off = disable)",
    "thống kê lượt chạy và hạn mức theo agent (hỏi cả CLI của từng agent)":
        "run and usage-limit stats per agent (also asks each agent's CLI)",
    "chỉ thống kê của ateam, không hỏi các CLI":
        "only ateam's own stats, don't ask the CLIs",
    "cập nhật ateam lên bản mới nhất":
        "update ateam to the latest version",
    "cài lại kể cả khi đã là bản mới nhất":
        "reinstall even if already on the latest version",
    "cho agent tạm nghỉ N phút, hoặc 'off'":
        "let an agent cool down for N minutes, or 'off'",
    "chạy hết các task đang chờ rồi thoát":
        "run all queued tasks, then exit",
    "Đã có: {p}":
        "Already exists: {p}",
    "Đã tạo cấu hình dự án: {p}":
        "Created project config: {p}",
    "Trưởng nhóm: {lead}   ·   isolation: {isolation}":
        "Lead: {lead}   ·   isolation: {isolation}",
    "     dự phòng khi hết hạn mức: {v}":
        "     backup when out of quota: {v}",
    "  {name:12} {v:>4} lượt  {v2:>5} phút  ~{v3}k token  lỗi {v4}  hết hạn mức {v5}":
        "  {name:12} {v:>4} runs  {v2:>5} min  ~{v3}k tokens  failed {v4}  out of quota {v5}",
    "không":
        "no",
    "Đang dùng bản mới nhất ({version}).":
        "You are on the latest version ({version}).",
    "(tắt)":
        "(off)",
    "(không)":
        "(none)",
    "(không lấy được version)":
        "(could not get version)",
    "   (effort hợp lệ: {v})":
        "   (valid effort: {v})",
    "     model gợi ý: {v}":
        "     suggested models: {v}",
    "     ✗ cờ không thấy trong `{v}`: {v2} — CLI có thể đã đổi cờ; sửa command trong cấu hình":
        "     ✗ flags not found in `{v}`: {v2} — the CLI may have changed its flags; fix the command in the config",
    " (sau bước {v})":
        " (after step {v})",
    " (chạy ngay)":
        " (runs now)",
    "\nKế hoạch:":
        "\nPlan:",
    "{a} đến {v}":
        "{a} until {v}",
    "Chạy kế hoạch này? [Y/n] ":
        "Run this plan? [Y/n] ",
    "Đã dừng. Task vẫn ở trạng thái nháp — mở `ateam` để chỉnh và chạy.":
        "Stopped. Tasks stay as drafts — open `ateam` to edit and run them.",
    "clipboard không có ảnh":
        "clipboard has no image",
    "cần cài wl-paste (Wayland) hoặc xclip (X11) để dán ảnh":
        "install wl-paste (Wayland) or xclip (X11) to paste images",
    "không tìm thấy osascript để đọc clipboard":
        "osascript not found to read the clipboard",
    "# Agent và workflow tuỳ chỉnh của ateam. Sửa trong app: /custom (hoặc nút ở màn hình /setup).\n# File này được giữ nguyên khi config.toml nâng cấp lên bản mới.\n":
        "# ateam custom agents and workflows. Edit in the app: /custom (or the button on the /setup screen).\n# This file is kept when config.toml is upgraded to a new version.\n",
    "Agent \"grok\" giờ chạy Grok Build CLI (lệnh grok); lựa chọn cũ của nó (qua OpenCode) chuyển sang agent mới \"opencode\".":
        "Agent \"grok\" now runs the Grok Build CLI (command grok); its old choices (via OpenCode) moved to the new agent \"opencode\".",
    "cài Antigravity rồi bật lệnh agy":
        "install Antigravity, then enable the agy command",
    "★ Trưởng nhóm":
        "★ Lead",
    "Code chính":
        "Main coder",
    "Test & tài liệu":
        "Tests & docs",
    "Nghiên cứu":
        "Research",
    "Tiết kiệm":
        "Economy",
    "Cân bằng":
        "Balanced",
    "Tối đa":
        "Maximum",
    "mặc định":
        "default",
    "(chưa có bước)":
        "(no steps yet)",
    "{n}  ({binary})  đang dùng: {v}":
        "{n}  ({binary})  using: {v}",
    "Đã nâng cấp cấu hình lên bản {CONFIG_VERSION} (thêm tính năng mới). Bản cũ sao lưu ở {bak}":
        "Config upgraded to version {CONFIG_VERSION} (new features). The old one is backed up at {bak}",
    "  danh sách thật: {v}  (làm mới: /models {n} làm mới)":
        "  real list: {v}  (refresh: /models {n} refresh)",
    "(để CLI tự chọn)":
        "(let the CLI choose)",
    "(không có)":
        "(none)",
    "Bước {i}":
        "Step {i}",
    "  (file nhị phân — không hiện nội dung; nhấn o để mở bằng VS Code)":
        "  (binary file — content not shown; press o to open in VS Code)",
    "chỉ đổi tên, nội dung giữ nguyên":
        "renamed only, content unchanged",
    "file rỗng":
        "empty file",
    "file rỗng bị xoá":
        "empty file deleted",
    "  … còn nữa — file quá dài, nhấn o để xem đủ bằng VS Code":
        "  … more — file too long, press o to see it all in VS Code",
    "chỉ đổi quyền file":
        "file mode changed only",
    "File nhị phân — không mở trong editor":
        "Binary file — not opened in the editor",
    "file lớn — chỉ đọc":
        "large file — read-only",
    "văn bản":
        "plain text",
    "Không đọc được: {e}":
        "Cannot read: {e}",
    "không phải UTF-8 — chỉ đọc":
        "not UTF-8 — read-only",
    "Không lưu được: {e}":
        "Cannot save: {e}",
    "Không tìm thấy: {p}":
        "Pattern not found: {p}",
    "đã chép {n} dòng":
        "{n} lines yanked",
    "lỗi không rõ":
        "unknown error",
    "không phải git repo":
        "not a git repo",
    "Đã bỏ thay đổi của {v} file":
        "Discarded changes in {v} file(s)",
    " (bỏ qua hook)":
        " (hooks skipped)",
    "(chưa có commit)":
        "(no commits yet)",
    "{v} đã stage · {v2} chưa stage":
        "{v} staged · {v2} unstaged",
    "sạch":
        "clean",
    "đang {state}":
        "{state} in progress",
    "\n… (diff đã được cắt bớt)":
        "\n… (diff truncated)",
    "Thay đổi chưa stage":
        "Unstaged changes",
    "Đã tạo git repo":
        "Created a git repo",
    "Không có file nào để stage":
        "No files to stage",
    "Đã stage {v} file":
        "Staged {v} file(s)",
    "Đã stage mọi thay đổi":
        "Staged all changes",
    "Không có file nào đã stage":
        "No staged files",
    "Đã bỏ stage {v} file":
        "Unstaged {v} file(s)",
    "Không có thay đổi chưa stage nào để bỏ":
        "No unstaged changes to discard",
    "Chưa có nội dung commit":
        "Commit message is empty",
    "Còn {v} file xung đột — sửa xong rồi stage trước khi commit":
        "{v} file(s) still in conflict — fix them and stage before committing",
    " — nếu do git hook chặn: tick 'Bỏ qua hook' hoặc /commit --no-verify <message>":
        " — if a git hook blocked it: tick 'Skip hooks' or use /commit --no-verify <message>",
    "Đã sửa commit trước ({v}){skipped}":
        "Amended the last commit ({v}){skipped}",
    "Đã commit {v}{skipped}":
        "Committed {v}{skipped}",
    "Đã chuyển sang {name}":
        "Switched to {name}",
    "Tên nhánh không hợp lệ: '{name}'":
        "Invalid branch name: '{name}'",
    "Đã tạo nhánh {name}":
        "Created branch {name}",
    "Tên nhánh không hợp lệ: '{new}'":
        "Invalid branch name: '{new}'",
    "Đã đổi tên {old} → {new}":
        "Renamed {old} → {new}",
    "Đã xoá nhánh {name}":
        "Deleted branch {name}",
    "Nhánh {name} còn commit chưa merge — xoá hẳn (mất các commit đó) bằng nút 'Xoá hẳn'":
        "Branch {name} has unmerged commits — force delete (losing those commits) with the 'Force delete' button",
    "Merge {name} có {n} file xung đột — sửa file rồi stage và commit, hoặc 'Huỷ merge'":
        "Merging {name} left {n} conflicting file(s) — fix them, stage and commit, or 'Abort merge'",
    "Không có merge/rebase nào đang dở":
        "No merge/rebase in progress",
    "Đã huỷ {state}":
        "Aborted {state}",
    "Repo chưa có remote nào (git remote add origin <url>)":
        "This repo has no remote yet (git remote add origin <url>)",
    "Đã fetch mọi remote":
        "Fetched all remotes",
    "Nhánh {v} chưa có upstream — Push trước để tạo nhánh trên remote":
        "Branch {v} has no upstream — Push first to create it on the remote",
    "Pull bị xung đột — sửa file rồi stage và commit, hoặc 'Huỷ merge'":
        "Pull hit conflicts — fix the files, stage and commit, or 'Abort merge'",
    "Đang ở detached HEAD — tạo nhánh trước khi push":
        "Detached HEAD — create a branch before pushing",
    "Remote có commit mới hơn — Pull trước rồi push lại":
        "The remote has newer commits — Pull first, then push again",
    "Không có thay đổi nào để stash":
        "No changes to stash",
    "Đã cất thay đổi vào stash":
        "Stashed your changes",
    "Lấy {ref} bị xung đột — sửa file rồi stage; stash vẫn được giữ":
        "Applying {ref} hit conflicts — fix the files and stage; the stash is kept",
    "Đã xoá {ref}":
        "Dropped {ref}",
    "Đã tạo commit đảo ngược {v}":
        "Created a revert commit for {v}",
    "Revert bị xung đột — sửa file rồi stage và commit, hoặc 'Huỷ revert'":
        "Revert hit conflicts — fix the files, stage and commit, or 'Abort revert'",
    "Không có commit trước để quay về":
        "No earlier commit to go back to",
    "Commit cuối đã push lên remote — dùng Revert thay vì bỏ commit":
        "The last commit is already pushed — use Revert instead of undoing it",
    "Đã bỏ commit cuối, thay đổi vẫn giữ (đã stage)":
        "Undid the last commit; its changes are kept (staged)",
    "✓ đồng bộ":
        "✓ in sync",
    "{v} xung đột":
        "{v} conflicts",
    "Chưa cài git":
        "git is not installed",
    "git {v} quá {v2} giây — đã dừng":
        "git {v} took more than {v2} seconds — stopped",
    "Thay đổi đã stage":
        "Staged changes",
    "Chưa stage file nào — bấm Space ở file cần commit, hoặc 'a' để stage tất cả":
        "Nothing staged — press Space on a file to stage it, or 'a' to stage everything",
    "Không có thay đổi nào để commit":
        "No changes to commit",
    "Đã tạo và chuyển sang nhánh {name}":
        "Created and switched to branch {name}",
    "Đã cập nhật, không có gì mới":
        "Already up to date",
    "Đã merge {name} vào nhánh hiện tại":
        "Merged {name} into the current branch",
    "Đã pull":
        "Pulled",
    "Đã push {branch}":
        "Pushed {branch}",
    "Đã lấy lại {ref}":
        "Restored {ref}",
    "Đã tạo nhánh {short} theo dõi {name}":
        "Created branch {short} tracking {name}",
    " (vẫn giữ trong stash)":
        " (still kept in the stash)",
    "Đã chuyển sang {short}":
        "Switched to {short}",
    "{m} phút":
        "{m} min",
    "{v} ngày":
        "{v} days",
    "{v} giờ":
        "{v} hours",
    "{v} tuần":
        "{v} weeks",
    "tuần":
        "week",
    "Gói: {v}":
        "Plan: {v}",
    "Hạn mức chính":
        "Primary limit",
    "Hạn mức phụ":
        "Secondary limit",
    "{label} ({v}): đã dùng {used:g}%":
        "{label} ({v}): {used:g}% used",
    "⚠ Đang chạm hạn mức: {v}":
        "⚠ Hitting the limit: {v}",
    " · hồi lúc ":
        " · resets at ",
    "không giới hạn":
        "unlimited",
    " — lần chạy codex gần nhất)":
        " — from the latest codex run)",
    "(số liệu lúc ":
        "(data as of ",
    " · ảnh: ":
        " · images: ",
    "Đã trả lời — {lead} đang nghĩ câu tiếp theo…":
        "Answered — {lead} is thinking of the next question…",
    "{lead} đang chốt yêu cầu rồi lập kế hoạch cho mục tiêu #{id}…":
        "{lead} is finalizing the requirements, then planning goal #{id}…",
    "{lead} đang hỏi tiếp…":
        "{lead} is asking the next question…",
    "Đã bỏ mục tiêu #{id}":
        "Dropped goal #{id}",
    "{agent}: tìm thấy {v} model":
        "{agent}: found {v} models",
    "Đã sửa nội dung task #{tid}":
        "Updated the content of task #{tid}",
    "Đã xếp lại task #{tid}":
        "Re-queued task #{tid}",
    "Task #{tid} đã kết thúc ({status})":
        "Task #{tid} has already finished ({status})",
    "Trưởng nhóm đang review mục tiêu #{gid}…":
        "The lead is reviewing goal #{gid}…",
    "{agent} tạm nghỉ {minutes} phút":
        "{agent} cooling down for {minutes} min",
    "Đã merge #{tid}":
        "Merged #{tid}",
    "worktree (mỗi task 1 nhánh riêng)":
        "worktree (one branch per task)",
    "shared (chung thư mục)":
        "shared (same folder)",
    "Sẵn sàng. Trưởng nhóm: {lead}. Chế độ làm việc: {mode}.":
        "Ready. Lead: {lead}. Work mode: {mode}.",
    "🎯 Mục tiêu #{gid}: {text}":
        "🎯 Goal #{gid}: {text}",
    "✗ Không còn agent nào lập kế hoạch/review được ({label}).":
        "✗ No agent left that can plan/review ({label}).",
    "🔎 Mục tiêu #{gid} (hỏi đáp trước): {text}":
        "🔎 Goal #{gid} (Q&A first): {text}",
    "Không có mục tiêu nào đang hỏi đáp":
        "No goal is in a Q&A session",
    "Trưởng nhóm đang nghĩ câu hỏi — đợi chút":
        "The lead is thinking of a question — just a moment",
    "Chưa có câu hỏi nào để trả lời — bấm ↻ Hỏi tiếp":
        "No question to answer yet — press ↻ Ask again",
    "Câu trả lời trống":
        "The answer is empty",
    "Trưởng nhóm đang nghĩ — đợi chút rồi bấm lại":
        "The lead is thinking — wait a moment, then press again",
    "Trưởng nhóm đang nghĩ — đợi chút":
        "The lead is thinking — just a moment",
    "Đang chờ bạn trả lời câu hỏi":
        "Waiting for your answer",
    "✗ Bỏ mục tiêu #{id} (đang hỏi đáp)":
        "✗ Dropped goal #{id} (during Q&A)",
    "Không có workflow '{name}'. Có: {v}":
        "No workflow '{name}'. Available: {v}",
    "Workflow '{name}' chưa có bước nào":
        "Workflow '{name}' has no steps yet",
    "🎯 Mục tiêu #{gid} theo workflow '{name}': {text}":
        "🎯 Goal #{gid} with workflow '{name}': {text}",
    "Không có mục tiêu #{gid}":
        "No goal #{gid}",
    "Mục tiêu #{gid} chưa kết thúc — đợi xong (hoặc /review {gid}) rồi tiếp tục":
        "Goal #{gid} hasn't finished — wait for it (or /review {gid}), then continue",
    "Không có trưởng nhóm '{lead}' trong cấu hình":
        "No lead '{lead}' in the config",
    "Thiếu yêu cầu mới":
        "The new request is missing",
    "↪ Tiếp tục mục tiêu #{gid}: {text}":
        "↪ Continuing goal #{gid}: {text}",
    "Không hiểu '{ref}' — dùng m<số> cho mục tiêu, t<số> cho task":
        "Can't parse '{ref}' — use m<number> for a goal, t<number> for a task",
    "Không có task #{n}":
        "No task #{n}",
    "Không có task #{tid}":
        "No task #{tid}",
    "Agent '{agent}' không còn trong đội":
        "Agent '{agent}' is no longer on the team",
    "↪ Task #{nid} hỏi tiếp {agent} (sau #{tid}): {title}":
        "↪ Task #{nid} follows up with {agent} (after #{tid}): {title}",
    "✗ Đã bỏ kế hoạch #{gid} ({n} task nháp).":
        "✗ Dropped plan #{gid} ({n} draft tasks).",
    "🗑 Đã dọn {v} task, {v2} mục tiêu đã kết thúc khỏi bảng việc.":
        "🗑 Cleared {v} task(s) and {v2} finished goal(s) from the board.",
    "➕ Task #{tid} giao cho {agent}{extra}: {title}":
        "➕ Task #{tid} assigned to {agent}{extra}: {title}",
    "Không có agent '{agent}'":
        "No agent '{agent}'",
    "Task #{tid} đang chạy — /cancel trước rồi giao lại":
        "Task #{tid} is running — /cancel it first, then reassign",
    "Task #{tid} đang chạy — thay đổi sẽ áp dụng nếu /retry":
        "Task #{tid} is running — the change applies on /retry",
    "{agent}: CLI không có lệnh liệt kê model — dùng danh mục có sẵn":
        "{agent}: the CLI has no command to list models — using the built-in catalog",
    "{agent}: chưa cài lệnh '{v}'":
        "{agent}: command '{v}' is not installed",
    " ⚠ model đang chọn '{model}' không có trong danh sách — chọn lại: /model {agent}":
        " ⚠ the selected model '{model}' is not in the list — pick again: /model {agent}",
    "Task #{tid} đang chạy":
        "Task #{tid} is running",
    "Task #{tid} đang {status}":
        "Task #{tid} is {status}",
    "↻ Chạy lại task #{tid}":
        "↻ Re-running task #{tid}",
    "Đang dừng task #{tid}…":
        "Stopping task #{tid}…",
    "Đã huỷ task #{tid}":
        "Cancelled task #{tid}",
    "Đang huỷ task #{tid} và xoá nhánh của nó…":
        "Cancelling task #{tid} and deleting its branch…",
    "📝 Ghi chú ({author}): {text}":
        "📝 Note ({author}): {text}",
    "Trưởng nhóm đang xử lý mục tiêu này":
        "The lead is already working on this goal",
    "⏸ {agent} hết hạn mức — tạm nghỉ đến {v}.":
        "⏸ {agent} is out of quota — cooling down until {v}.",
    "{agent} hoạt động lại":
        "{agent} is active again",
    "⏸ {agent} tạm nghỉ đến {v} (đặt tay).":
        "⏸ {agent} cooling down until {v} (set manually).",
    "kiểm tra: {cmd}":
        "check: {cmd}",
    "\n$ [kiểm tra] {cmd}\n":
        "\n$ [check] {cmd}\n",
    "\n(Lệnh kiểm tra quá {timeout}s)":
        "\n(Check command exceeded {timeout}s)",
    "Task #{tid} không có nhánh chờ merge ({status})":
        "Task #{tid} has no branch waiting to merge ({status})",
    "Merge #{tid} thất bại — xem log hệ thống":
        "Merging #{tid} failed — see the system log",
    "✓ Đã merge #{tid} ({agent}): {title}":
        "✓ Merged #{tid} ({agent}): {title}",
    "Task #{tid} không ở trạng thái chờ duyệt ({status})":
        "Task #{tid} is not waiting for review ({status})",
    "Đã giao làm lại #{tid} kèm góp ý":
        "Sent #{tid} back for rework with your feedback",
    "Đã huỷ #{tid}":
        "Cancelled #{tid}",
    "Thư mục này không phải git repo (hoặc chưa có commit nào) — không xem được diff.":
        "This folder is not a git repo (or has no commits yet) — can't show a diff.",
    "Không có thay đổi nào chưa commit.":
        "No uncommitted changes.",
    "Thay đổi chưa commit của thư mục (chế độ shared, không tách theo task #{tid})":
        "Uncommitted changes in the folder (shared mode, not split per task #{tid})",
    "Thư mục này không phải git repo — không xem được diff.":
        "This folder is not a git repo — can't show a diff.",
    "(Chế độ shared không tách được diff theo từng task — đây là mọi thay đổi chưa commit của thư mục)\n":
        "(Shared mode can't split the diff per task — these are all uncommitted changes in the folder)\n",
    "🧠 {lead} đang lập kế hoạch cho mục tiêu #{gid}…":
        "🧠 {lead} is planning goal #{gid}…",
    "Trưởng nhóm không trả về câu hỏi hay đặc tả hợp lệ (xem .ateam/logs/lead.log) — bấm ↻ Hỏi tiếp để thử lại":
        "The lead returned neither a valid question nor a spec (see .ateam/logs/lead.log) — press ↻ Ask again to retry",
    "📝 Đã chốt yêu cầu cho mục tiêu #{gid} sau {v} câu hỏi:":
        "📝 Requirements for goal #{gid} agreed after {v} question(s):",
    "Đã bỏ khi đang hỏi đáp":
        "Dropped during Q&A",
    "📋 {v} bước ở trạng thái NHÁP — gõ /go {gid} để chạy.":
        "📋 {v} step(s) as DRAFT — type /go {gid} to run.",
    "📋 {v} bước — bắt đầu chạy.":
        "📋 {v} step(s) — starting.",
    "Không có mục tiêu #{n}":
        "No goal #{n}",
    "Task #{tid} đang chờ duyệt — merge (Ctrl+Y) hoặc /reject trước":
        "Task #{tid} is waiting for review — merge it (Ctrl+Y) or /reject it first",
    "Task #{tid} chưa xong — đợi chạy xong rồi tiếp tục":
        "Task #{tid} hasn't finished — wait for it, then continue",
    "▶ Đã duyệt {n} task.":
        "▶ Approved {n} task(s).",
    "Người dùng bỏ kế hoạch":
        "Plan dropped by the user",
    "{agent}: không chạy được {v}: {e}":
        "{agent}: could not run {v}: {e}",
    "hết thời gian":
        "timed out",
    "(hết {v} giây chờ)":
        "(timed out after {v} s)",
    "Đang thu gọn ngữ cảnh rồi, chờ chút…":
        "Already compacting the context, one moment…",
    "Chưa có ghi chú hay mục tiêu nào để thu gọn.":
        "No notes or goals to compact yet.",
    "🗜 {lead} đang thu gọn ngữ cảnh…":
        "🗜 {lead} is compacting the context…",
    "🗜 Đã thu gọn ngữ cảnh: ~{before} → {v} ký tự. Bản tóm tắt:":
        "🗜 Context compacted: ~{before} → {v} characters. Summary:",
    "Đã thu gọn ngữ cảnh (~{before} → {v} ký tự)":
        "Context compacted (~{before} → {v} characters)",
    "Không có thay đổi nào để viết commit message":
        "No changes to write a commit message for",
    "Viết commit message":
        "Write commit message",
    "▶ {agent} đã hồi hạn mức.":
        "▶ {agent}'s quota is back.",
    "▶ Bỏ tạm nghỉ cho {agent}.":
        "▶ Cooldown cleared for {agent}.",
    "⚠ #{id} muốn giao việc nhưng đã chạm giới hạn {max_delegation_depth} tầng.":
        "⚠ #{id} wants to delegate but hit the {max_delegation_depth}-level limit.",
    "🤝 {agent} giao task #{nid} cho {to}: {title}":
        "🤝 {agent} delegated task #{nid} to {to}: {title}",
    "🔍 {lead} đang review mục tiêu #{gid} (vòng {round})…":
        "🔍 {lead} is reviewing goal #{gid} (round {round})…",
    "git worktree add thất bại: {v}":
        "git worktree add failed: {v}",
    "👀 #{id} chờ duyệt merge — /diff {id} để xem, /merge {id} hoặc /reject {id}":
        "👀 #{id} awaits merge review — /diff {id} to view, /merge {id} or /reject {id}",
    "↩ Từ chối #{tid}, giao làm lại kèm góp ý: {feedback}":
        "↩ Rejected #{tid}, sent back for rework with feedback: {feedback}",
    "✗ Từ chối và huỷ #{tid}":
        "✗ Rejected and cancelled #{tid}",
    "Không lấy được diff của task #{tid}: {v}":
        "Could not get the diff of task #{tid}: {v}",
    "Task #{tid} không thay đổi file nào.":
        "Task #{tid} changed no files.",
    "Không có thay đổi nào.":
        "No changes.",
    "Phiên trước bị dừng giữa chừng — /retry để chạy lại":
        "The previous session stopped midway — /retry to run it again",
    "⚠ isolation=worktree cần chạy ở thư mục gốc của git repo đã có commit — chuyển sang chế độ shared.":
        "⚠ isolation=worktree must run at the root of a git repo with at least one commit — switching to shared mode.",
    "✗ Chưa cài '{binary}' ({name}).":
        "✗ '{binary}' is not installed ({name}).",
    "⏸ {name} đang hết hạn mức đến {v} — thử người khác.":
        "⏸ {name} is out of quota until {v} — trying someone else.",
    "↪ {name} làm thay trưởng nhóm cho: {label}":
        "↪ {name} stands in for the lead on: {label}",
    "✗ {label}: {name} thoát với mã {rc}.":
        "✗ {label}: {name} exited with code {rc}.",
    "Lập kế hoạch mục tiêu #{gid}":
        "Plan goal #{gid}",
    "✗ Không đọc được kế hoạch cho mục tiêu #{gid} (xem .ateam/logs/lead.log). Bạn vẫn có thể giao tay bằng /task.":
        "✗ Could not read the plan for goal #{gid} (see .ateam/logs/lead.log). You can still assign work by hand with /task.",
    "📋 Kế hoạch #{gid}: {v} task ở trạng thái NHÁP. Duyệt bằng /go {gid} (trong TUI: F2 hoặc Ctrl+G); sửa trước bằng /edit, /assign, /cancel.":
        "📋 Plan #{gid}: {v} task(s) as DRAFT. Approve with /go {gid} (in the TUI: F2 or Ctrl+G); edit first with /edit, /assign, /cancel.",
    "📋 Kế hoạch #{gid}: {v} task — bắt đầu chạy.":
        "📋 Plan #{gid}: {v} task(s) — starting.",
    "Hỏi đáp mục tiêu #{gid}":
        "Q&A for goal #{gid}",
    "❓ #{gid} câu {v}: {question}":
        "❓ #{gid} question {v}: {question}",
    "✗ Hỏi đáp #{gid}: {v}":
        "✗ Q&A #{gid}: {v}",
    "⚠ Agent '{agent}' không có trong đội — giao cho {lead}.":
        "⚠ Agent '{agent}' is not on the team — assigning to {lead}.",
    "theo agent":
        "per agent",
    "mã thoát {code}":
        "exit code {code}",
    "không thấy model nào":
        "no models found",
    "CLI này không có lệnh xem usage (đặt usage_command trong cấu hình nếu có)":
        "This CLI has no usage command (set usage_command in the config if it has one)",
    "Chưa cài lệnh '{v}'":
        "Command '{v}' is not installed",
    "… (còn {v} dòng — chạy `{cmd}` để xem đủ)":
        "… ({v} more lines — run `{cmd}` to see everything)",
    "(mã thoát {code})":
        "(exit code {code})",
    "(không in gì)":
        "(no output)",
    "Thu gọn ngữ cảnh":
        "Compact context",
    "✗ Không thu gọn được: trưởng nhóm không trả về dòng SUMMARY: (xem .ateam/logs/lead.log). Ghi chú cũ vẫn giữ nguyên.":
        "✗ Could not compact: the lead returned no SUMMARY: line (see .ateam/logs/lead.log). The old notes are kept.",
    "Không thu gọn được — ghi chú cũ vẫn giữ nguyên":
        "Could not compact — the old notes are kept",
    "⛔ Task #{id} bị chặn vì #{v} không xong.":
        "⛔ Task #{id} is blocked because #{v} did not finish.",
    "↪ #{id} chuyển từ {agent} sang {fb} vì {agent} hết hạn mức (đến {v}).":
        "↪ #{id} moved from {agent} to {fb} because {agent} is out of quota (until {v}).",
    "✗ Task #{id}: chưa cài '{binary}'.":
        "✗ Task #{id}: '{binary}' is not installed.",
    "🏁 Mục tiêu #{id} kết thúc ({v}).":
        "🏁 Goal #{id} ended ({v}).",
    "🔧 #{tid} test fail (mã {trc}) — {fixer} sửa lần {attempts}/{max_fix_attempts}":
        "🔧 #{tid} tests failed (code {trc}) — {fixer} fixing, attempt {attempts}/{max_fix_attempts}",
    "\n(Đã sửa để qua kiểm tra: {v})":
        "\n(Fixed to pass the check: {v})",
    "Lỗi nội bộ: {e!r}":
        "Internal error: {e!r}",
    "Bị huỷ":
        "Cancelled",
    "Quá thời gian ({timeout}s)":
        "Timed out ({timeout}s)",
    "Thoát với mã {rc}":
        "Exited with code {rc}",
    "{binary} không nhận một cờ trong lệnh (CLI có thể đã đổi phiên bản) — chạy `ateam doctor` rồi sửa command trong cấu hình":
        "{binary} rejected a flag in the command (the CLI may have changed version) — run `ateam doctor`, then fix the command in the config",
    "Agent không in ra gì (kiểm tra đăng nhập / quyền / pty)":
        "The agent printed nothing (check login / permissions / pty)",
    "{name} bị chặn chạy lệnh (thiếu quyền) — bật Toàn quyền cho agent này ở /setup (agent có sẵn) hoặc /custom (agent tuỳ chỉnh), rồi /retry":
        "{name} was blocked from running commands (missing permission) — enable Full access for this agent in /setup (built-in agent) or /custom (custom agent), then /retry",
    "{name} hết hạn mức":
        "{name} is out of quota",
    "⚠ #{id} giao việc cho '{to}' — không có trong đội, bỏ qua.":
        "⚠ #{id} delegated to '{to}' — not on the team, skipped.",
    "Review mục tiêu #{gid} vòng {round}":
        "Review goal #{gid} round {round}",
    "⚠ Không đọc được review của mục tiêu #{gid}.":
        "⚠ Could not read the review of goal #{gid}.",
    "🏁 Mục tiêu #{gid} {v}: {summary}":
        "🏁 Goal #{gid} {v}: {summary}",
    "⚠ Merge #{id} lỗi: {v}":
        "⚠ Merging #{id} failed: {v}",
    "Không merge được nhánh {branch} (xung đột hoặc thư mục chính đang có thay đổi) — tự merge tay, /merge {id} để thử lại, hoặc /retry":
        "Could not merge branch {branch} (conflicts, or the main folder has changes) — merge it by hand, /merge {id} to retry, or /retry",
    "Bị từ chối khi duyệt":
        "Rejected during review",
    "Bị dừng khi đang lập kế hoạch":
        "Stopped while planning",
    "✗ Không tìm thấy trưởng nhóm '{name}' trong cấu hình.":
        "✗ Lead '{name}' not found in the config.",
    "Trưởng nhóm không trả về kế hoạch JSON hợp lệ":
        "The lead did not return a valid JSON plan",
    "(chưa có)":
        "(none yet)",
    "mặc định của CLI":
        "CLI default",
    "Không chạy được: {e}":
        "Could not run: {e}",
    "Task phụ thuộc lỗi/huỷ: {v}":
        "Dependency failed/cancelled: {v}",
    "Chưa cài lệnh '{binary}' (kiểm tra bằng `ateam doctor`)":
        "Command '{binary}' is not installed (check with `ateam doctor`)",
    "Lỗi bộ lập lịch: {e!r}":
        "Scheduler error: {e!r}",
    " — xem log [test]":
        " — see the [test] log",
    "{fixer} hết hạn mức khi đang sửa lỗi test — /retry sau":
        "{fixer} ran out of quota while fixing the tests — /retry later",
    "↪ #{tid} xếp hàng lại":
        "↪ #{tid} re-queued",
    "Không đọc được kết quả review (xem .ateam/logs/lead.log)":
        "Could not read the review result (see .ateam/logs/lead.log)",
    "🏁 Mục tiêu #{gid} đã hết {max_rounds} vòng. Đánh giá: {summary}":
        "🏁 Goal #{gid} used up all {max_rounds} rounds. Assessment: {summary}",
    "Chưa có phiên codex nào ghi hạn mức — chạy 1 task codex trước.":
        "No codex session has recorded limits yet — run a codex task first.",
    "\n(không có thay đổi file nào — bỏ qua kiểm tra)\n":
        "\n(no files changed — skipping the check)\n",
    "✅ #{tid} qua kiểm tra `{command}`":
        "✅ #{tid} passed the check `{command}`",
    "Kiểm tra `{command}` vẫn fail (mã {trc})":
        "Check `{command}` still fails (code {trc})",
    "sửa lỗi test #{tid} ({attempts}/{max_fix_attempts})":
        "fix failing tests #{tid} ({attempts}/{max_fix_attempts})",
    ", chuyển sang {new_agent}":
        ", switching to {new_agent}",
    ", chờ {agent} hồi hạn mức":
        ", waiting for {agent}'s quota",
    "📋 {v} task bổ sung đang ở trạng thái NHÁP — /go {gid} để chạy.":
        "📋 {v} follow-up task(s) as DRAFT — /go {gid} to run.",
    "còn task lỗi":
        "some tasks failed",
    " sau {attempts} lần sửa":
        " after {attempts} fix attempt(s)",
    "HOÀN THÀNH":
        "DONE",
    "kết thúc":
        "ended",
    "Phiên trước dừng khi trưởng nhóm đang nghĩ câu hỏi — bấm ↻ Hỏi tiếp":
        "The previous session stopped while the lead was thinking of a question — press ↻ Ask again",
    "chạy gần đây":
        "recently run",
    "\n[thoát với mã {rc}]\n":
        "\n[exited with code {rc}]\n",
    "✗ Không chạy được: {e}":
        "✗ Could not run: {e}",
    "Màu của theme":
        "Theme color",
    "Xanh dương":
        "Blue",
    "Tím":
        "Purple",
    "Xanh lá":
        "Green",
    "Cam":
        "Orange",
    "Hồng":
        "Pink",
    "Vàng":
        "Yellow",
    "Xanh ngọc":
        "Cyan",
    "Đỏ":
        "Red",
    "Gõ một câu bình thường  → giao MỤC TIÊU cho trưởng nhóm lập kế hoạch & chia việc\n                          (hoặc chạy theo workflow mặc định: F4 / nút bên trái ô nhập để chọn).\n\nGiao việc:\n  /task <agent> <nội dung>          giao tay (vd: /task codex viết test cho utils.py)\n                                    agent nhận đúng nguyên văn bạn gõ (gõ /task rồi chọn agent)\n  /task <agent>@<effort> <nội dung> giao kèm effort riêng (vd: /task codex@xhigh tìm lỗi deadlock)\n  /task <agent>:<model>@<effort> …  giao kèm cả model riêng\n  /go [mục tiêu]                    duyệt kế hoạch nháp và chạy (F2 hoặc Ctrl+G, hoặc nút trong khung\n                                    \"Duyệt kế hoạch\" hiện phía trên ô nhập khi có kế hoạch chờ)\n  /drop [mục tiêu]                  bỏ kế hoạch nháp (huỷ mọi task nháp của nó)\n  /assign <task> <agent>            đổi người làm 1 task\n  /edit <task> <nội dung>           sửa nội dung task (khi chưa chạy)\n  /set <task> effort|model <giá trị>\n                                    đổi effort/model riêng cho 1 task ('-' = theo agent)\n  /retry <task>   /cancel <task>    chạy lại (F5 hoặc Ctrl+R) / huỷ (Ctrl+K) task\n  /review <mục tiêu>                bắt trưởng nhóm review ngay\n  /plan [mục tiêu]                  xem lại kế hoạch kể cả khi đã duyệt / xong (nút 📋 ở thẻ mục tiêu trên web)\n  /continue <m12|t40> <yêu cầu>     tiếp tục mục tiêu (m) hoặc thread /task (t) đã xong: trưởng nhóm\n                                    lập task bổ sung dựa trên việc đã làm / agent nhận kèm các lượt trước.\n                                    F6 (Ctrl+O) với task đang chọn, hoặc bấm \"↪ Tiếp tục\" ở khung mục tiêu\n  /note <nội dung>                  ghi chú chung cho cả đội\n  /chat <agent> [tin]               chat trực tiếp với 1 agent, giữ phiên CLI (ô 💬 ở tab Agents; /new: cuộc\n                                    mới · /term: mở CLI thật của agent tiếp tục phiên đó)\n  F7   /focus [agent]               phóng to 1 agent (chat riêng, cả màn hình); F7 / Esc thu lại\n\nLệnh, file, ảnh trong ô nhập:\n  gõ / ở đầu ô nhập                 hiện danh sách lệnh kèm mô tả, gõ tiếp để lọc\n  gõ @ trong ô nhập                 hiện danh sách file/thư mục của dự án, gõ tiếp để lọc\n                                    ↑↓ chọn · Tab/Enter chèn · Esc đóng (chọn thư mục để đi vào trong)\n                                    khi chạy, @đường-dẫn được đổi sang cú pháp của từng agent (xem /agents)\n  Ctrl+V trong ô nhập               dán ảnh từ clipboard (lưu vào .ateam/images, chèn @ảnh);\n                                    kéo-thả file ảnh vào terminal cũng thành @ảnh. Mỗi agent nhận ảnh\n                                    theo cách CLI đó hỗ trợ (codex: --image, opencode: -f)\n\nKiểm tra & duyệt code:\n  /verify <lệnh>                    lệnh kiểm tra sau mỗi task cho dự án này (vd: /verify npm test)\n  /verify off   /verify             tắt / xem lệnh đang dùng\n  /diff <task>                      xem thay đổi của task (Ctrl+D với task đang chọn)\n  /merge <task>                     duyệt và merge task đang chờ (Ctrl+Y)\n  /reject <task> [góp ý]            từ chối; có góp ý thì giao làm lại kèm góp ý đó\n\nHạn mức:\n  /usage                            thống kê lượt chạy, thời gian, token ước tính theo agent, rồi hỏi\n                                    hạn mức thật từ từng CLI (claude/agy: /usage, opencode stats, codex)\n  /update                           kiểm tra và cập nhật ateam lên bản mới nhất (mở lại app sau đó)\n  /cooldown <agent> <phút>          cho agent tạm nghỉ (vd khi bạn biết nó sắp hết hạn mức)\n  /cooldown <agent> off             cho agent làm việc lại ngay\n\nModel & effort của từng agent (được lưu lại cho lần sau):\n  /model <agent> <tên model>        vd: /model claude opus   ·   /model grok grok-4.7-build-fast\n  /effort <agent> <mức>             vd: /effort codex xhigh  ·   /effort claude high\n  /model <agent>   /effort <agent>  mở bảng chọn từ danh sách agent hỗ trợ (hoặc bấm vào ô agent ở tab Agents)\n  /model <agent> -                  quay về mặc định trong config (tương tự /effort <agent> -)\n  /models [agent]                   xem model & effort mỗi agent hỗ trợ\n  /models <agent> làm mới           hỏi CLI danh sách model thật (opencode models, agy models)\n  /agents                           xem model, effort, mức effort hợp lệ của từng agent\n  /setup                            mở lại màn hình thiết lập: bật/tắt agent, trưởng nhóm, model, effort\n  /roles                            sửa nhanh vai trò · CLI · model · effort (không đi lại cả /setup)\n  /theme [tên] [màu nhấn]           chọn theme màu (xem trước trực tiếp), vd /theme nord tím\n  /lang en|vi                       đổi ngôn ngữ giao diện (app tự mở lại)\n  /open [thư mục]                   mở folder / dự án khác: dự án gần đây, hoặc gõ đường dẫn (Tab gợi ý)\n  /rules [rule mới]                 rule của dự án mọi agent phải tuân theo (ateam gửi kèm mọi prompt): thêm,\n                                    sửa, bật/tắt, chỉ cho vài agent / vai trò; xem AGENTS.md, CLAUDE.md có sẵn\n\nAgent & workflow tuỳ chỉnh:\n  /custom                           thêm/sửa/xoá agent riêng (CLI bất kỳ) và workflow (chuỗi bước dựng sẵn)\n  /flow <tên> <mục tiêu>            chạy mục tiêu theo workflow — các bước thành task ngay, không cần lập kế hoạch\n  /flow                             xem các workflow đang có\n  /goal <mục tiêu>                  trưởng nhóm lập kế hoạch, kể cả khi đã đặt workflow mặc định\n  /grill <mục tiêu>                 \"grill me\": trưởng nhóm hỏi bạn từng câu (phạm vi, luồng, dữ liệu, ca\n                                    biên, tiêu chí xong…) kèm phương án gợi ý, tới khi đủ rõ thì chốt đặc tả\n                                    rồi lập kế hoạch. Trả lời ở ô nhập; gõ số / bấm để chọn phương án\n  /grill xong   /grill bỏ           chốt luôn với những gì đã trả lời / bỏ mục tiêu đang hỏi đáp\n\nKhác:\n  /pause  /resume                   tạm dừng / tiếp tục nhận task mới\n  /todo [việc cần làm]              tab ✅ To-do: việc riêng dự án, hiểu #tag !cao @mai 17:00 (lưu ngoài repo)\n  /notes [tiêu đề]   /tags          tab 🗒 Ghi chú (markdown, tự lưu) / quản lý tag dùng chung\n  /clear                            dọn task & mục tiêu đã kết thúc khỏi bảng (nút 🗑 trên bảng)\n  /compact [trọng tâm]              trưởng nhóm tóm tắt ghi chú, mục tiêu & log cho prompt sau gọn hơn\n  /log <task>   /log sys            xem log 1 task / log hệ thống (Ctrl+L)\n  /team  /board  /term  /git  /code chuyển tab Agents / Bảng việc / Terminal / Git / Code (Ctrl+T xoay vòng)\n  /grid [agent]                     tab 🔲 Lưới: mỗi ô là CLI thật của một agent (F10 sắp xếp, kéo tiêu đề đổi chỗ)\n  Alt+1 … Alt+9, Alt+0              tới thẳng tab theo thứ tự (Mac: bật \"Use Option as Meta\" trong terminal)\n\nLệnh terminal (tab 💻 Terminal):\n  !<lệnh>                           chạy lệnh trong thư mục dự án, vd !yarn dev, !make test\n  !                                 gợi ý script package.json, target Makefile, lệnh gần đây (Enter chạy)\n  /sh <lệnh>                        như !<lệnh>\n  /stop [số]                        dừng lệnh đang chọn (nút ■ Dừng / ↻ Chạy lại / ✗ Xoá trong tab)\n\nGit (tab 🌿 Git — Ctrl+T xoay tới, hoặc /git):\n  /git                              mở tab Git: file thay đổi, commit, nhánh, lịch sử, stash, pull/push\n                                    trong danh sách file: Space stage/bỏ stage · a stage tất cả · u bỏ stage\n                                    tất cả · x bỏ thay đổi · X bỏ tất cả · Enter/d xem diff · c tới ô commit\n                                    trong lịch sử: Enter/d xem commit · r revert\n  /git <lệnh>                       chạy git <lệnh> bất kỳ ở tab Terminal, vd /git tag v1.0,\n                                    /git cherry-pick abc123, /git remote add origin <url>\n  /commit <message>                 commit file đã stage (chưa stage gì thì commit mọi thay đổi)\n  /commit --no-verify <message>     commit bỏ qua git hook (pre-commit, commit-msg); /commit -n cũng được.\n                                    Trong tab Git: ô \"Bỏ qua hook (--no-verify)\" dưới nút Commit\n  /commit                           trưởng nhóm đọc diff và viết commit message (nút ✨ trong tab Git)\n  /push [-f]   /pull   /fetch       đồng bộ với remote (-f = --force-with-lease)\n  /branch [tên]   /checkout <nhánh> tạo & chuyển nhánh / chuyển nhánh (trống: mở danh sách nhánh)\n  /stash [message]   /stash pop     cất tạm / lấy lại thay đổi chưa commit (/stash list: danh sách)\n                                    đổi nhánh, pull, stash bị chặn khi agent đang chạy task\n\nXem & sửa code (tab 📝 Code — Ctrl+T xoay tới, hoặc /code):\n  Ctrl+P                            command palette: mở nhanh file (file gần đây trước); gõ > lệnh,\n                                    @ symbol (hàm, class, heading), :số tới dòng, /chữ tìm trong file.\n                                    F8 = lệnh, F9 = symbol (web: ⌘⇧P, ⌘⇧O). Lệnh: lưu tất cả, file mới,\n                                    đổi tên, xoá vào Thùng rác, xuống dòng mềm, xem diff git, mở VS Code,\n                                    hỏi / giao task cho agent về file hoặc đoạn đang chọn\n  /code [@file[:dòng]]              mở file trong editor (trống: mở tab, gõ để lọc file bên trái);\n                                    /edit @file cũng được\n                                    phím e ở tab Git (file đang chọn) / màn hình diff (đúng đoạn đang xem)\n  /search [từ khoá]   F3             tìm & thay trong toàn dự án như VS Code: Aa / nguyên từ / regex, lọc file,\n                                    xem trước chữ thay; Enter mở file đúng chỗ · r thay trong file · Ctrl+R thay tất cả\n  phím vim                          i a I A o O sửa · Esc về normal · h j k l w b e 0 ^ $ gg G Ctrl+D/U\n                                    x dd D dw cw cc yy p P J r u Ctrl+R · v V chọn · / ? n N * tìm\n                                    :w lưu · :q đóng · :wq · :q! bỏ thay đổi · :e! nạp lại · :<số> tới dòng\n                                    :bn :bp đổi file · :files ẩn/hiện danh sách · số đếm: 5j, 3dd, 2dw\n  /vim off   /vim on                tắt phím vim (sửa như editor thường, Ctrl+S lưu) / bật lại\n                                    file bị agent sửa trong lúc mở: tự nạp lại nếu bạn chưa sửa, không thì\n                                    báo để :e! hoặc :w! (ghi đè); file > 2 MB tắt tô màu, > 5 MB chỉ đọc\n\nTrợ giúp & thoát:\n  /help                             trợ giúp này (F1)\n  F2 = Ctrl+G, F5 = Ctrl+R, F6 = Ctrl+O   dùng F2/F5/F6 khi terminal chặn phím Ctrl (vd terminal trong VS Code/\n                                    Cursor trên Mac: Ctrl+G là Go to Line, Ctrl+R là Run Recent).\n                                    MacBook: giữ fn khi bấm F2/F5\n  /quit                             thoát (Ctrl+Q) — agent đang chạy sẽ bị dừng":
        "Type a plain sentence    → give the lead a GOAL to plan & split into tasks\n                          (or run the default workflow: F4 / the button left of the input picks it).\n\nAssigning work:\n  /task <agent> <content>           assign by hand (e.g. /task codex write tests for utils.py)\n                                    the agent gets exactly what you typed (type /task, then pick an agent)\n  /task <agent>@<effort> <content>  assign with its own effort (e.g. /task codex@xhigh find the deadlock)\n  /task <agent>:<model>@<effort> …  assign with its own model too\n  /go [goal]                        approve the draft plan and run it (F2 or Ctrl+G, or the button in\n                                    the \"Review plan\" box above the input when a plan is waiting)\n  /drop [goal]                      drop the draft plan (cancels all its draft tasks)\n  /assign <task> <agent>            change who does a task\n  /edit <task> <content>            edit a task's content (before it runs)\n  /set <task> effort|model <value>\n                                    set a task's own effort/model ('-' = follow the agent)\n  /retry <task>   /cancel <task>    re-run (F5 or Ctrl+R) / cancel (Ctrl+K) a task\n  /review <goal>                    make the lead review now\n  /plan [goal]                      review a goal's plan even after approval / completion (📋 on web goal cards)\n  /continue <m12|t40> <request>     continue a finished goal (m) or /task thread (t): the lead adds\n                                    tasks based on the work done / the agent gets the earlier turns.\n                                    F6 (Ctrl+O) on the selected task, or press \"↪ Continue\" in the goals box\n  /note <content>                   shared note for the whole team\n  /chat <agent> [message]           chat directly with one agent, keeping its CLI session (💬 box on the Agents\n                                    tab; /new: new chat · /term: open the agent's real CLI on that session)\n  F7   /focus [agent]               zoom one agent (private chat, full screen); F7 / Esc to restore\n\nCommands, files, images in the input:\n  type / at the start               show the command list with descriptions, keep typing to filter\n  type @ in the input               show the project's files/folders, keep typing to filter\n                                    ↑↓ select · Tab/Enter insert · Esc close (pick a folder to go inside)\n                                    when run, @path becomes each agent's own syntax (see /agents)\n  Ctrl+V in the input               paste an image from the clipboard (saved to .ateam/images, inserts @image);\n                                    dragging an image file into the terminal also becomes @image. Each agent\n                                    gets images the way its CLI supports (codex: --image, opencode: -f)\n\nChecking & reviewing code:\n  /verify <command>                 check command run after each task in this project (e.g. /verify npm test)\n  /verify off   /verify             disable / show the current command\n  /diff <task>                      show a task's changes (Ctrl+D on the selected task)\n  /merge <task>                     approve and merge a waiting task (Ctrl+Y)\n  /reject <task> [feedback]         reject; with feedback, the task is redone with it\n\nUsage limits:\n  /usage                            runs, time and estimated tokens per agent, then asks each CLI\n                                    for its real limits (claude/agy: /usage, opencode stats, codex)\n  /update                           check for and install the latest ateam (reopen the app afterwards)\n  /cooldown <agent> <minutes>       let an agent rest (e.g. when you know it's about to hit its limit)\n  /cooldown <agent> off             let the agent work again right away\n\nModel & effort per agent (remembered for next time):\n  /model <agent> <model name>       e.g. /model claude opus   ·   /model grok grok-4.7-build-fast\n  /effort <agent> <level>           e.g. /effort codex xhigh  ·   /effort claude high\n  /model <agent>   /effort <agent>  open a picker with what the agent supports (or click the agent row in Agents)\n  /model <agent> -                  back to the config default (same for /effort <agent> -)\n  /models [agent]                   show the models & effort levels each agent supports\n  /models <agent> refresh           ask the CLI for its real model list (opencode models, agy models)\n  /agents                           show each agent's model, effort and valid effort levels\n  /setup                            reopen the setup screen: enable/disable agents, lead, model, effort\n  /roles                            quickly edit roles · CLI · model · effort (without the whole /setup)\n  /theme [name] [accent]            pick a color theme (live preview), e.g. /theme nord purple\n  /lang en|vi                       change the interface language (the app reopens)\n  /open [folder]                    open another folder / project: recent projects, or type a path (Tab completes)\n  /rules [new rule]                 project rules every agent must follow (ateam sends them with every prompt):\n                                    add, edit, enable/disable, limit to some agents / roles; see existing AGENTS.md, CLAUDE.md\n\nCustom agents & workflows:\n  /custom                           add/edit/delete your own agents (any CLI) and workflows (step chains)\n  /flow <name> <goal>               run a goal with a workflow — steps become tasks right away, no planning\n  /flow                             list the available workflows\n  /goal <goal>                      the lead makes a plan, even when a default workflow is set\n  /grill <goal>                     \"grill me\": the lead asks you one question at a time (scope, flows, data,\n                                    edge cases, definition of done…) with suggested options, then writes a\n                                    spec and plans. Answer in the input; type a number / click to pick an option\n  /grill done   /grill drop         finalize with what you've answered so far / drop the goal in Q&A\n\nOther:\n  /pause  /resume                   pause / resume picking up new tasks\n  /todo [to-do]                     ✅ To-do tab: the project's to-dos, understands #tag !high @tomorrow 17:00 (outside the repo)\n  /notes [title]   /tags            🗒 Notes tab (markdown, autosaved) / manage the shared tags\n  /clear                            clear finished tasks & goals from the board (🗑 button on the board)\n  /compact [focus]                  the lead summarizes notes, goals & log so later prompts are shorter\n  /log <task>   /log sys            show a task's log / the system log (Ctrl+L)\n  /team  /board  /term  /git  /code switch to Agents / Board / Terminal / Git / Code (Ctrl+T cycles)\n  /grid [agent]                     🔲 Grid tab: each cell is an agent's real CLI (F10 arranges, drag a title to move)\n  Alt+1 … Alt+9, Alt+0              jump straight to a tab by position (Mac: enable \"Use Option as Meta\")\n\nTerminal commands (💻 Terminal tab):\n  !<command>                        run a command in the project folder, e.g. !yarn dev, !make test\n  !                                 suggest package.json scripts, Makefile targets, recent commands (Enter runs)\n  /sh <command>                     same as !<command>\n  /stop [number]                    stop the selected command (■ Stop / ↻ Restart / ✗ Remove buttons in the tab)\n\nGit (🌿 Git tab — Ctrl+T to reach it, or /git):\n  /git                              open the Git tab: changed files, commit, branches, history, stash, pull/push\n                                    in the file list: Space stage/unstage · a stage all · u unstage all\n                                    · x discard changes · X discard all · Enter/d view diff · c commit message\n                                    in the history: Enter/d view commit · r revert\n  /git <command>                    run any git <command> in the Terminal tab, e.g. /git tag v1.0,\n                                    /git cherry-pick abc123, /git remote add origin <url>\n  /commit <message>                 commit staged files (if nothing is staged, commit all changes)\n  /commit --no-verify <message>     commit skipping git hooks (pre-commit, commit-msg); /commit -n works too.\n                                    In the Git tab: the \"Skip hooks (--no-verify)\" box under Commit\n  /commit                           the lead reads the diff and writes the commit message (✨ in the Git tab)\n  /push [-f]   /pull   /fetch       sync with the remote (-f = --force-with-lease)\n  /branch [name]   /checkout <br>   create & switch branch / switch branch (empty: open the branch list)\n  /stash [message]   /stash pop     stash / restore uncommitted changes (/stash list: the list)\n                                    switching branches, pull and stash are blocked while agents run tasks\n\nCode view & edit (📝 Code tab — Ctrl+T cycles to it, or /code):\n  Ctrl+P                            command palette: quick open (recent files first); type > commands,\n                                    @ symbols (functions, classes, headings), :number go to line, /text find\n                                    in file. F8 = commands, F9 = symbols (web: ⌘⇧P, ⌘⇧O). Commands: save all,\n                                    new file, rename, delete to Trash, word wrap, git diff, open in VS Code,\n                                    ask / give a task to an agent about the file or selection\n  /code [@file[:line]]              open a file in the editor (empty: open the tab, type to filter files on the left);\n                                    /edit @file works too\n                                    key e in the Git tab (selected file) / diff screen (the hunk on screen)\n  /search [keyword]   F3             search & replace across the project like VS Code: Aa / whole word / regex,\n                                    file filters, replacement preview; Enter opens the file there · r replace in file\n  vim keys                          i a I A o O edit · Esc back to normal · h j k l w b e 0 ^ $ gg G Ctrl+D/U\n                                    x dd D dw cw cc yy p P J r u Ctrl+R · v V select · / ? n N * search\n                                    :w save · :q close · :wq · :q! discard changes · :e! reload · :<number> go to line\n                                    :bn :bp switch file · :files show/hide the file list · counts: 5j, 3dd, 2dw\n  /vim off   /vim on                turn vim keys off (edit like a normal editor, Ctrl+S saves) / back on\n                                    file changed by an agent while open: reloaded automatically if you have no\n                                    edits, otherwise you are told to :e! or :w! (overwrite); files > 2 MB are not\n                                    highlighted, > 5 MB open read-only\n\nHelp & quit:\n  /help                             this help (F1)\n  F2 = Ctrl+G, F5 = Ctrl+R, F6 = Ctrl+O   use F2/F5/F6 when the terminal grabs Ctrl keys (e.g. the VS Code/\n                                    Cursor terminal on Mac: Ctrl+G is Go to Line, Ctrl+R is Run Recent).\n                                    MacBook: hold fn when pressing F2/F5\n  /quit                             quit (Ctrl+Q) — running agents will be stopped",
    "👋 Chào mừng tới ateam — bắt đầu nhanh:\n  • Gõ một mục tiêu (vd: Thêm trang đăng nhập) → trưởng nhóm lập kế hoạch, Enter (hoặc F2) để duyệt & chạy\n  • /grill Thêm trang đăng nhập → trưởng nhóm hỏi kỹ từng câu cho rõ yêu cầu rồi mới lập kế hoạch\n  • /task codex viết test cho utils.py → giao tay cho 1 agent\n  • Gõ / để xem các lệnh · @ để nhắc file · Ctrl+V dán ảnh\n  • !yarn dev → chạy lệnh terminal (gõ ! để xem gợi ý) · tab 💻 Terminal\n  • /git → tab 🌿 Git: stage, commit (trưởng nhóm viết message), nhánh, pull/push, stash, lịch sử\n  • /code @file → tab 📝 Code: xem & sửa code với phím vim (:w lưu, /vim off để sửa kiểu thường)\n  • F1 hoặc /help: toàn bộ lệnh & phím tắt · Ctrl+T: đổi tab (Bảng việc / Agents / Workflows / Code / Git / …)":
        "👋 Welcome to ateam — quick start:\n  • Type a goal (e.g. Add a login page) → the lead plans it; press Enter (or F2) to approve & run\n  • /grill Add a login page → the lead asks you questions one by one to pin down the requirements, then plans\n  • /task codex write tests for utils.py → assign one agent by hand\n  • Type / to see commands · @ to mention files · Ctrl+V to paste images\n  • !yarn dev → run a terminal command (type ! for suggestions) · 💻 Terminal tab\n  • /git → 🌿 Git tab: stage, commit (the lead writes the message), branches, pull/push, stash, history\n  • /code @file → 📝 Code tab: view & edit code with vim keys (:w saves, /vim off for normal editing)\n  • F1 or /help: all commands & shortcuts · Ctrl+T: switch tabs (Board / Agents / Workflows / Code / Git / …)",
    "📋 Kế hoạch":
        "📋 Plan",
    "<agent> <nội dung>":
        "<agent> <content>",
    "giao tay cho 1 agent, gửi nguyên văn":
        "assign one agent by hand, sent verbatim",
    "[mục tiêu]":
        "[goal]",
    "duyệt kế hoạch nháp và chạy":
        "approve the draft plan and run it",
    "bỏ kế hoạch nháp (huỷ mọi task nháp của nó)":
        "drop the draft plan (cancels all its draft tasks)",
    "<mục tiêu>":
        "<goal>",
    "trưởng nhóm lập kế hoạch (bỏ qua workflow mặc định)":
        "the lead makes a plan (ignores the default workflow)",
    "<mục tiêu|xong|bỏ>":
        "<goal|done|drop>",
    "trưởng nhóm hỏi kỹ từng câu để làm rõ yêu cầu rồi mới lập kế hoạch":
        "the lead asks you questions one by one to clarify the requirements, then plans",
    "<lệnh>":
        "<command>",
    "chạy lệnh terminal (như !lệnh), vd /sh yarn dev":
        "run a terminal command (like !command), e.g. /sh yarn dev",
    "[số]":
        "[number]",
    "dừng lệnh terminal đang chọn (hoặc lệnh số đó)":
        "stop the selected terminal command (or that number)",
    "mở tab Terminal (lệnh đang chạy)":
        "open the Terminal tab (running commands)",
    "[tên] [màu nhấn]":
        "[name] [accent]",
    "chọn theme màu (xem trước trực tiếp)":
        "pick a color theme (live preview)",
    "đổi ngôn ngữ giao diện (app tự mở lại)":
        "change the interface language (the app reopens)",
    "[@file[:dòng]]":
        "[@file[:line]]",
    "mở tab 📝 Code: xem & sửa file với phím vim":
        "open the 📝 Code tab: view & edit files with vim keys",
    "<on|off|file>":
        "<on|off|file>",
    "bật/tắt phím vim trong tab 📝 Code":
        "turn vim keys on/off in the 📝 Code tab",
    "[lệnh git]":
        "[git command]",
    "mở tab Git; kèm lệnh thì chạy git <lệnh> ở tab Terminal":
        "open the Git tab; with a command, run git <command> in the Terminal tab",
    "commit (chưa stage gì thì commit tất cả); trống: trưởng nhóm viết message":
        "commit (nothing staged: commit everything); empty: the lead writes the message",
    "push nhánh hiện tại (lần đầu tự tạo nhánh trên remote)":
        "push the current branch (creates it on the remote the first time)",
    "pull nhánh hiện tại (fast-forward, không được thì merge)":
        "pull the current branch (fast-forward, else merge)",
    "fetch mọi remote":
        "fetch all remotes",
    "[tên]":
        "[name]",
    "tạo & chuyển sang nhánh mới; trống: danh sách nhánh":
        "create & switch to a new branch; empty: branch list",
    "<nhánh>":
        "<branch>",
    "chuyển sang nhánh (nhánh remote → tạo nhánh local)":
        "switch branch (remote branch → creates a local one)",
    "cất tạm / lấy lại thay đổi chưa commit":
        "stash / restore uncommitted changes",
    "<tên> <mục tiêu>":
        "<name> <goal>",
    "chạy mục tiêu theo workflow":
        "run a goal with a workflow",
    "đổi người làm 1 task":
        "change who does a task",
    "<task> <nội dung>":
        "<task> <content>",
    "sửa nội dung task chưa chạy":
        "edit a task that hasn't run",
    "<task> effort|model <giá trị>":
        "<task> effort|model <value>",
    "effort/model riêng cho 1 task":
        "a task's own effort/model",
    "chạy lại task":
        "re-run a task",
    "huỷ task":
        "cancel a task",
    "bắt trưởng nhóm review ngay":
        "make the lead review now",
    "<m12|t40> <yêu cầu>":
        "<m12|t40> <request>",
    "tiếp tục mục tiêu / thread đã xong (F6)":
        "continue a finished goal / thread (F6)",
    "<nội dung>":
        "<content>",
    "xem thay đổi của task":
        "show a task's changes",
    "duyệt và merge task đang chờ":
        "approve and merge a waiting task",
    "<task> [góp ý]":
        "<task> [feedback]",
    "từ chối, có góp ý thì giao làm lại":
        "reject; with feedback the task is redone",
    "[lệnh|off]":
        "[command|off]",
    "lệnh kiểm tra sau mỗi task":
        "check command after each task",
    "<agent> [tên|-]":
        "<agent> [name|-]",
    "đổi model của agent":
        "change an agent's model",
    "<agent> [mức|-]":
        "<agent> [level|-]",
    "đổi effort của agent":
        "change an agent's effort",
    "[agent] [làm mới]":
        "[agent] [refresh]",
    "xem model & effort hỗ trợ":
        "show supported models & effort",
    "cấu hình, lệnh chạy của từng agent":
        "each agent's config and run command",
    "màn hình thiết lập đội":
        "team setup screen",
    "agent & workflow tuỳ chỉnh":
        "custom agents & workflows",
    "thống kê lượt chạy + hạn mức còn lại báo bởi từng CLI":
        "run stats + remaining limits reported by each CLI",
    "<agent> <phút|off>":
        "<agent> <minutes|off>",
    "cho agent tạm nghỉ":
        "let an agent cool down",
    "[trọng tâm]":
        "[focus]",
    "tóm tắt ngữ cảnh chung cho prompt gọn lại":
        "summarize the shared context so prompts stay short",
    "dọn task & mục tiêu đã kết thúc khỏi bảng việc":
        "clear finished tasks & goals from the board",
    "tạm dừng nhận task mới":
        "pause picking up new tasks",
    "tiếp tục nhận task":
        "resume picking up tasks",
    "xem log 1 task / log hệ thống":
        "show a task's log / the system log",
    "chuyển sang tab Agents":
        "switch to the Agents tab",
    "chuyển sang tab Bảng việc":
        "switch to the Board tab",
    "toàn bộ lệnh & phím tắt":
        "all commands & shortcuts",
    "thoát":
        "quit",
    "Không hiểu lệnh /{cmd}":
        "Unknown command /{cmd}",
    "model nhỏ/nhanh, effort thấp — tốn ít hạn mức nhất":
        "small/fast models, low effort — uses the least quota",
    "model mạnh vừa, effort trung bình; trưởng nhóm và review cao hơn 1 bậc":
        "medium-strong models, medium effort; lead and review one step higher",
    "model mạnh nhất, effort cao — chất lượng tốt nhất, tốn hạn mức nhất":
        "strongest models, high effort — best quality, uses the most quota",
    "sửa file":
        "edit files",
    "toàn quyền":
        "full access",
    "Chỉ sửa file (an toàn)":
        "Edit files only (safe)",
    "Toàn quyền — chạy lệnh, mạng (build, git push…)":
        "Full access — run commands, network (build, git push…)",
    "@ file / thư mục":
        "@ file / folder",
    "↑↓ chọn · Tab/Enter chèn · Esc đóng":
        "↑↓ select · Tab/Enter insert · Esc close",
    "/ lệnh":
        "/ commands",
    "! lệnh terminal":
        "! terminal commands",
    "↑↓ chọn rồi Enter chạy · Tab chèn để sửa · Esc đóng":
        "↑↓ select, then Enter to run · Tab inserts to edit · Esc close",
    "/task — chọn agent":
        "/task — pick an agent",
    "/continue — chọn mục tiêu (m) hoặc thread /task (t) để tiếp tục":
        "/continue — pick a goal (m) or /task thread (t) to continue",
    "↑↓ chọn file · ] [ đoạn kế/trước · s hai cột/một cột · PgUp/PgDn cuộn":
        "↑↓ pick file · ] [ next/prev hunk · s split/unified · PgUp/PgDn scroll",
    "Đồng ý":
        "OK",
    "Đã lưu {path} · {n} dòng":
        "Saved {path} · {n} lines",
    "🔎 Trưởng nhóm hỏi để hiểu rõ yêu cầu":
        "🔎 The lead is asking to understand the requirements",
    "Duyệt kế hoạch":
        "Review plan",
    "Chọn {key} cho {agent}  (đang dùng: {v})":
        "Pick {key} for {agent}  (current: {v})",
    "Dùng: /{name} {args} — {desc}":
        "Usage: /{name} {args} — {desc}",
    "🔎 Review: ✓ hoàn thành":
        "🔎 Review: ✓ done",
    "🔎 Review: cần làm thêm":
        "🔎 Review: more work needed",
    "Đóng":
        "Close",
    "Lưu":
        "Save",
    "CLI bạn đang dùng":
        "CLIs you use",
    "Kiểu làm việc":
        "How you work",
    "Kiểu":
        "Style",
    "Mức chi phí":
        "Cost level",
    "Mức":
        "Level",
    "Vai trò · model · effort":
        "Roles · model · effort",
    "Vai trò":
        "Roles",
    "An toàn & duyệt code":
        "Safety & code review",
    "An toàn":
        "Safety",
    "Lệnh kiểm tra":
        "Check command",
    "Kiểm tra":
        "Check",
    "Xem lại & lưu":
        "Review & save",
    "Xem lại":
        "Review",
    "Trưởng nhóm lập kế hoạch, tôi duyệt rồi mới chạy":
        "The lead plans, I approve before it runs",
    "kế hoạch hiện ở khung Duyệt kế hoạch, Enter/F2 để chạy — an toàn, dễ kiểm soát":
        "the plan shows in the Review plan box, Enter/F2 to run — safe and easy to control",
    "Trưởng nhóm lập kế hoạch và chạy luôn":
        "The lead plans and runs right away",
    "nhanh nhất, không cần duyệt":
        "fastest, no approval",
    "Theo quy trình cố định: thiết kế → code → test":
        "Fixed process: design → code → test",
    "gõ mục tiêu là chạy workflow 'tinh-nang'; /goal vẫn để trưởng nhóm lập kế hoạch":
        "typing a goal runs the 'tinh-nang' workflow; /goal still lets the lead plan",
    "Chủ yếu tôi tự giao từng việc (/task)":
        "I mostly assign tasks myself (/task)",
    "tắt trưởng nhóm tự review và giao thêm việc":
        "turns off the lead's automatic review and follow-up tasks",
    "Sửa thẳng vào thư mục dự án":
        "Edit the project folder directly",
    "đơn giản; các agent làm chung một chỗ":
        "simple; agents work in the same place",
    "Mỗi task một nhánh git riêng, xong thì tự merge":
        "One git branch per task, merged automatically when done",
    "an toàn khi nhiều agent chạy song song":
        "safe when many agents run in parallel",
    "Mỗi task một nhánh git riêng, tôi xem diff rồi mới merge":
        "One git branch per task, I review the diff before merging",
    "Ctrl+D xem diff kiểu VS Code, Ctrl+Y merge":
        "Ctrl+D shows a VS Code-style diff, Ctrl+Y merges",
    "Lưu & bắt đầu (Ctrl+S)":
        "Save & start (Ctrl+S)",
    "Tiếp →":
        "Next →",
    "Đội\n":
        "Team\n",
    "\nCách làm việc\n":
        "\nHow you work\n",
    "Lệnh sẽ chạy: ":
        "Command to run: ",
    "Lệnh":
        "Command",
    "bắt buộc; {prompt} = nội dung task":
        "required; {prompt} = the task content",
    "trưởng nhóm phân việc dựa vào đây":
        "the lead assigns work based on this",
    "Model mặc định":
        "Default model",
    "trống = để CLI tự chọn":
        "empty = let the CLI choose",
    "Model gợi ý":
        "Suggested models",
    "cách nhau dấu phẩy":
        "comma-separated",
    "Cờ model":
        "Model flag",
    "Mức effort":
        "Effort levels",
    "vd: low, medium, high · '-' = không có":
        "e.g. low, medium, high · '-' = none",
    "Effort mặc định":
        "Default effort",
    "Cờ effort":
        "Effort flag",
    "Lệnh liệt kê model":
        "Model list command",
    "vd: mycli models (tuỳ chọn)":
        "e.g. mycli models (optional)",
    "Nhắc file @":
        "@file mention",
    "vd: @{path} hoặc {path} · trống = theo lệnh":
        "e.g. @{path} or {path} · empty = per command",
    "Cờ đính file":
        "File attach flag",
    "vd: -f {path} · trống = theo lệnh · '-' = tắt":
        "e.g. -f {path} · empty = per command · '-' = off",
    "Cờ đính ảnh":
        "Image attach flag",
    "vd: --image={path} · trống = theo lệnh · '-' = tắt":
        "e.g. --image={path} · empty = per command · '-' = off",
    "Dự phòng":
        "Fallback",
    "agent thay khi hết hạn mức, cách nhau dấu phẩy":
        "agents that take over when out of quota, comma-separated",
    "Timeout (giây)":
        "Timeout (seconds)",
    "mặc định 1800":
        "default 1800",
    "Số task cùng lúc":
        "Concurrent tasks",
    "mặc định 1":
        "default 1",
    "Đã lưu {v} '{name}'":
        "Saved {v} '{name}'",
    "   {v} → bây giờ ({v2})":
        "   {v} → now ({v2})",
    "Xem trước: ":
        "Preview: ",
    "Theme: ":
        "Theme: ",
    "   · đã trả lời {n_answered} câu":
        "   · answered {n_answered} question(s)",
    "📋 Kế hoạch chờ duyệt ":
        "📋 Plan awaiting review ",
    "File kế":
        "Next file",
    "File trước":
        "Previous file",
    "Đoạn kế":
        "Next hunk",
    "Đoạn trước":
        "Previous hunk",
    "Đổi kiểu":
        "Toggle view",
    "Sửa file":
        "Edit file",
    " · o mở VS Code":
        " · o open in VS Code",
    "\n{keys} · Esc đóng":
        "\n{keys} · Esc close",
    "Đang mở {path} trong VS Code…":
        "Opening {path} in VS Code…",
    "Stage/bỏ stage":
        "Stage/unstage",
    "Stage tất cả":
        "Stage all",
    "Bỏ stage tất cả":
        "Unstage all",
    "Bỏ thay đổi":
        "Discard changes",
    "Xem diff":
        "View diff",
    "Xem commit":
        "View commit",
    "Trợ giúp":
        "Help",
    "Thoát":
        "Quit",
    "Đổi tab":
        "Switch tab",
    "Duyệt & chạy":
        "Approve & run",
    "Chạy lại":
        "Re-run",
    "Huỷ task":
        "Cancel task",
    "Tiếp tục":
        "Continue",
    "Log hệ thống":
        "System log",
    "Trạng thái":
        "Status",
    "File mới — :w để tạo":
        "New file — :w to create it",
    "Chưa lưu — :w để lưu, :q! để bỏ thay đổi":
        "Unsaved — :w to save, :q! to discard changes",
    "Chưa mở file nào":
        "No file open",
    "Chỉ đọc ({v}) — :w! để vẫn ghi":
        "Read-only ({v}) — :w! to write anyway",
    "Đã nạp lại từ đĩa":
        "Reloaded from disk",
    "File vừa đổi trên đĩa — đã nạp lại":
        "File changed on disk — reloaded",
    "Xung đột — sửa xong thì stage":
        "Conflicts — stage once fixed",
    "Đã stage — sẽ vào commit":
        "Staged — goes into the commit",
    "Chưa stage":
        "Unstaged",
    "Message mới cho commit trước — Enter để sửa commit{skip}":
        "New message for the last commit — Enter to amend{skip}",
    "XOÁ file chưa theo dõi":
        "DELETE the untracked file",
    "bỏ mọi thay đổi chưa stage của":
        "discard all unstaged changes in",
    "✨ {lead} đang viết commit message…":
        "✨ {lead} is writing the commit message…",
    "🗑 Dọn {v} task đã xong":
        "🗑 Clear {v} finished task(s)",
    "📋 Kế hoạch #{goal_id} sẵn sàng — Enter hoặc F2 để duyệt & chạy":
        "📋 Plan #{goal_id} is ready — Enter or F2 to approve & run",
    "  (gõ yêu cầu mới rồi Enter, Esc huỷ)":
        "  (type the new request, then Enter; Esc to cancel)",
    "Trả lời câu hỏi của trưởng nhóm (Enter) · gõ số để chọn phương án · /grill xong để chốt":
        "Answer the lead's question (Enter) · type a number to pick an option · /grill done to finalize",
    "Nhập mục tiêu (chạy theo workflow '{wf}') · /goal: trưởng nhóm lập kế hoạch · /help · @ nhắc file":
        "Type a goal (runs workflow '{wf}') · /goal: the lead plans · /help · @ to mention files",
    "Nhập mục tiêu cho trưởng nhóm, /help, hoặc @ để nhắc file":
        "Type a goal for the lead, /help, or @ to mention files",
    "(~token = ước tính từ độ dài prompt và output, chưa gồm file agent tự đọc)":
        "(~token = estimated from prompt and output length; excludes files the agent reads itself)",
    "\nĐang hỏi hạn mức từ CLI của {v}…":
        "\nAsking {v}'s CLI for usage limits…",
    "Đang kiểm tra bản mới…":
        "Checking for a new version…",
    "\nChọn: /model <agent>, /effort <agent> hoặc bấm vào ô agent ở tab Agents. Model ngoài danh sách vẫn đặt được: /model <agent> <tên>.":
        "\nPick with /model <agent>, /effort <agent> or click an agent box in the Agents tab. Models not in the list can still be set: /model <agent> <name>.",
    " Gõ mục tiêu → workflow '{default_workflow}' (/goal: trưởng nhóm lập kế hoạch).":
        " Typing a goal → workflow '{default_workflow}' (/goal: the lead plans).",
    "⚙ Đã lưu thiết lập. Trưởng nhóm: {lead}. Đội: {v}.{flow} Đổi lại: /setup, /model, /effort.":
        "⚙ Settings saved. Lead: {lead}. Team: {v}.{flow} Change later: /setup, /model, /effort.",
    "Chưa có workflow nào. Tạo bằng /custom → '+ Thêm workflow' (có mẫu sẵn).":
        "No workflows yet. Create one with /custom → '+ Add workflow' (templates included).",
    "Chạy: /flow <tên> <mục tiêu>   ·   sửa: /custom":
        "Run: /flow <name> <goal>   ·   edit: /custom",
    "nháp":
        "draft",
    "chờ":
        "queued",
    "đang chạy":
        "running",
    "xong":
        "done",
    "lỗi":
        "failed",
    "đã huỷ":
        "cancelled",
    "bị chặn":
        "blocked",
    "xung đột":
        "conflict",
    "chờ duyệt":
        "in review",
    "đang lập kế hoạch":
        "planning",
    "chờ duyệt (F2)":
        "awaiting review (F2)",
    "đang hỏi bạn":
        "asking you",
    "đã bỏ":
        "dropped",
    "đang làm":
        "in progress",
    "đang review":
        "reviewing",
    "hoàn thành":
        "done",
    "chưa xong":
        "incomplete",
    " · hay ý bạn là ":
        " · did you mean ",
    "  ➕ Việc giao thêm":
        "  ➕ Extra tasks",
    "‹prompt ateam gửi agent — đã ẩn›":
        "‹ateam's prompt to the agent — hidden›",
    "✔ Tóm tắt:":
        "✔ Summary:",
    "📝 Ghi chú: ":
        "📝 Note: ",
    "↪ Giao cho {to}":
        "↪ Delegated to {to}",
    "Còn thay đổi chưa lưu — Esc lần nữa để bỏ, Ctrl+S để lưu":
        "Unsaved changes — press Esc again to discard, Ctrl+S to save",
    "Thiết lập đội AI · Bước {v}/{v2} — {title}":
        "AI team setup · Step {v}/{v2} — {title}",
    "Bạn đang dùng những CLI nào? Đội chỉ gồm các CLI được chọn.":
        "Which CLIs do you use? The team only includes the selected ones.",
    "Space: chọn/bỏ · Tab: sang nút Tiếp":
        "Space: select/unselect · Tab: go to Next",
    "Bạn muốn đội làm việc thế nào?":
        "How should the team work?",
    "↑↓ chọn · Enter: chọn và sang bước tiếp":
        "↑↓ select · Enter: choose and go to the next step",
    "Ưu tiên tiết kiệm hạn mức hay chất lượng?":
        "Save quota or maximize quality?",
    "Bước sau điền sẵn model & effort theo mức này — vẫn đổi được từng vai trò.":
        "The next step pre-fills models & effort for this level — you can still change each role.",
    "Giao từng vai trò cho CLI nào, dùng model và effort gì?":
        "Which CLI, model and effort for each role?",
    "agent không chạy lệnh shell / mạng":
        "agents don't run shell commands / network",
    "Toàn quyền — chạy lệnh, mạng (lint, build, git push…)":
        "Full access — run commands, network (lint, build, git push…)",
    "chỉ dùng cho repo bạn tin tưởng; agent tuỳ chỉnh đổi riêng ở /custom":
        "only for repos you trust; custom agents are set separately in /custom",
    "Agent được làm gì?":
        "What may the agents do?",
    "Thay đổi của agent áp vào code thế nào?":
        "How are the agents' changes applied to the code?",
    "chạy sau mỗi task có sửa code; lỗi thì giao agent sửa":
        "runs after each task that changes code; failures go back to an agent to fix",
    "Không chạy lệnh kiểm tra":
        "Don't run a check command",
    "bật sau bằng /verify <lệnh>":
        "enable later with /verify <command>",
    "Lệnh kiểm tra tự chạy sau mỗi task (test, lint, build)?":
        "Check command to run after each task (test, lint, build)?",
    "  Agent tuỳ chỉnh giữ nguyên: {v}\n":
        "  Custom agents kept as is: {v}\n",
    "Quyền":
        "Permissions",
    "Áp thay đổi":
        "Apply changes",
    "\n⚠ Chưa có trưởng nhóm — quay lại bước Vai trò.":
        "\n⚠ No lead yet — go back to the Roles step.",
    "Chọn ít nhất một CLI":
        "Pick at least one CLI",
    "Esc lần nữa để thoát thiết lập (giữ cấu hình hiện tại)":
        "Press Esc again to leave setup (keeps the current config)",
    "Chưa có trưởng nhóm — chọn CLI cho vai trò ★ Trưởng nhóm":
        "No lead yet — pick a CLI for the ★ Lead role",
    "✓ đã cài '{binary}'":
        "✓ '{binary}' installed",
    "✗ chưa cài '{binary}'":
        "✗ '{binary}' not installed",
    "   ⚠ toàn quyền: agent chạy được mọi lệnh trên máy, chỉ dùng với repo tin tưởng":
        "   ⚠ full access: the agent can run any command on your machine; only use with trusted repos",
    "Tên chỉ gồm chữ, số, - và _ (không dùng 'lead')":
        "Names may contain only letters, digits, - and _ (not 'lead')",
    "Đã có agent '{name}' — chọn tên khác":
        "Agent '{name}' already exists — pick another name",
    "Cần nhập lệnh chạy agent":
        "Enter the command that runs the agent",
    "Dự phòng không có trong đội: {v}":
        "Fallback agents not on the team: {v}",
    "Tên chỉ gồm chữ, số, - và _":
        "Names may contain only letters, digits, - and _",
    "Đã có workflow '{name}' — chọn tên khác":
        "Workflow '{name}' already exists — pick another name",
    "Workflow cần ít nhất 1 bước":
        "A workflow needs at least 1 step",
    "✗ chưa cài":
        "✗ not installed",
    "{v} bước: {v2}":
        "{v} steps: {v2}",
    "Đã dán ảnh {v}":
        "Pasted image {v}",
    "đang đọc danh sách file…":
        "reading the file list…",
    "không có file nào khớp":
        "no matching files",
    "  — chưa có hoạt động":
        "  — no activity yet",
    "█ đang chạy":
        "█ running",
    "█ xong":
        "█ done",
    "█ lỗi":
        "█ failed",
    "▒ trưởng nhóm lập kế hoạch/review":
        "▒ lead planning/reviewing",
    "○ rảnh":
        "○ idle",
    "⏸ tạm dừng":
        "⏸ paused",
    "⏸ nghỉ: {v}":
        "⏸ resting: {v}",
    " · còn {others} mục tiêu khác đang hỏi đáp (hiện sau khi xong mục tiêu này)":
        " · {others} more goal(s) in Q&A (shown after this one)",
    "{v} {lead} đang nghĩ câu hỏi tiếp theo…":
        "{v} {lead} is thinking of the next question…",
    "↑↓ xem từng task · Enter: sửa nội dung · Tab: chuyển nút · Esc: về ô nhập":
        "↑↓ browse tasks · Enter: edit content · Tab: move between buttons · Esc: back to the input",
    " · vòng {round}":
        " · round {round}",
    " · còn {v} kế hoạch khác sau":
        " · {v} more plan(s) after this",
    "  ⟵ chạy sau #{v}":
        "  ⟵ runs after #{v}",
    "File đã bị xoá — không có gì để sửa":
        "File was deleted — nothing to edit",
    "Không thấy lệnh 'code' — trong VS Code: Shell Command: Install 'code' command":
        "'code' command not found — in VS Code: Shell Command: Install 'code' command",
    "Gõ tên nhánh mới trước":
        "Type the new branch name first",
    "Chưa có nhánh nào":
        "No branches yet",
    "Không xoá nhánh remote từ đây (dùng /git push origin --delete <nhánh>)":
        "Remote branches can't be deleted here (use /git push origin --delete <branch>)",
    "{name} là nhánh hiện tại":
        "{name} is the current branch",
    "Không có thay đổi nào để cất":
        "No changes to stash",
    "Không có task nào đã kết thúc để dọn":
        "No finished tasks to clear",
    "🗑 Đã dọn {n_tasks} task":
        "🗑 Cleared {n_tasks} task(s)",
    "Gõ lệnh sau dấu !, vd !yarn dev (gõ ! để xem gợi ý)":
        "Type a command after !, e.g. !yarn dev (type ! for suggestions)",
    "Chưa chạy lệnh nào.\n\n":
        "No commands run yet.\n\n",
    "Gõ ":
        "Type ",
    "!lệnh":
        "!command",
    " ở ô nhập, vd ":
        " in the input, e.g. ",
    ".\nGõ ":
        ".\nType ",
    " để xem gợi ý script của dự án (package.json, Makefile, lệnh gần đây).\n\n":
        " to see the project's scripts (package.json, Makefile, recent commands).\n\n",
    "Lệnh chạy trong thư mục dự án, nhiều lệnh song song được; thoát app (Ctrl+Q) sẽ dừng mọi lệnh đang chạy.":
        "Commands run in the project folder, several can run in parallel; quitting the app (Ctrl+Q) stops all running commands.",
    "File đổi trên đĩa — :e! nạp lại (bỏ thay đổi của bạn) hoặc :w! ghi đè":
        "File changed on disk — :e! to reload (drops your changes) or :w! to overwrite",
    "📝 Chưa mở file":
        "📝 No file open",
    "Chọn file bên trái (gõ để lọc, Enter mở) · /code @đường/dẫn[:dòng] · phím e ở tab Git / màn hình diff":
        "Pick a file on the left (type to filter, Enter opens) · /code @path[:line] · key e in the Git tab / diff screen",
    "  ·  {lang}  ·  dòng {r}/{n}, cột {c}":
        "  ·  {lang}  ·  line {r}/{n}, col {c}",
    "Chọn 1 file trong danh sách trước":
        "Select a file in the list first",
    "   ⚠ đang {state} dở":
        "   ⚠ {state} in progress",
    "Commit message cho {n_staged} file đã stage — Enter để commit{skip}":
        "Commit message for {n_staged} staged file(s) — Enter to commit{skip}",
    "Commit message (chưa stage gì: commit mọi thay đổi) — Enter để commit{skip}":
        "Commit message (nothing staged: commits all changes) — Enter to commit{skip}",
    "Đang có {v} task chạy — đợi xong (hoặc Ctrl+K huỷ) rồi hẵng đổi nhánh/pull/stash":
        "{v} task(s) are running — wait for them (or cancel with Ctrl+K) before switching branches/pulling/stashing",
    "Chỉ bỏ được thay đổi chưa stage — bỏ stage file trước (Space)":
        "Only unstaged changes can be discarded — unstage the file first (Space)",
    "↺ Bỏ thay đổi":
        "↺ Discard changes",
    "{v} {path}?\nKhông thể hoàn tác.":
        "{v} {path}?\nThis cannot be undone.",
    "Xung đột · {path}":
        "Conflict · {path}",
    "Không có diff để xem":
        "No diff to show",
    "Commit {short} không đổi file nào (vd commit merge)":
        "Commit {short} changed no files (e.g. a merge commit)",
    "Tạo commit mới đảo ngược {short} · {subject}?":
        "Create a new commit reverting {short} · {subject}?",
    "Gõ commit message trước (hoặc bấm ✨ để trưởng nhóm viết)":
        "Type a commit message first (or press ✨ to let the lead write it)",
    "✨ Đã điền commit message — sửa nếu cần rồi Enter để commit":
        "✨ Commit message filled in — edit if needed, then Enter to commit",
    "Chưa có mục tiêu. Gõ yêu cầu ở ô dưới cùng.":
        "No goals yet. Type a request in the box at the bottom.",
    "Chưa có task nào.\n\n":
        "No tasks yet.\n\n",
    "chạy theo workflow '{default_workflow}' (/goal: trưởng nhóm)":
        "runs workflow '{default_workflow}' (/goal: the lead)",
    "trưởng nhóm lập kế hoạch & chia việc":
        "the lead plans & splits the work",
    "📜 Log hệ thống":
        "📜 System log",
    "  ·  chọn 1 task trong bảng để xem log riêng · Ctrl+T: tab Agents":
        "  ·  select a task in the board to see its log · Ctrl+T: Agents tab",
    "  (được {v} giao)":
        "  (assigned by {v})",
    "  · đã sửa lỗi test {attempts} lần":
        "  · fixed failing tests {attempts} time(s)",
    "\n👀 Chờ duyệt — Ctrl+D xem diff, Ctrl+Y merge, /reject <task> [góp ý]":
        "\n👀 Awaiting review — Ctrl+D view diff, Ctrl+Y merge, /reject <task> [feedback]",
    "❓ Trưởng nhóm hỏi — trả lời ở ô nhập (hoặc gõ số phương án)":
        "❓ The lead has a question — answer in the input (or type an option number)",
    "Kế hoạch không còn task nào":
        "The plan has no tasks left",
    "Không có task nháp nào cần duyệt":
        "No draft tasks to approve",
    "▶ Đã duyệt {n} task":
        "▶ Approved {n} task(s)",
    "Chọn 1 task trong bảng trước":
        "Select a task in the board first",
    "↪ Tiếp tục mục tiêu #{i} ":
        "↪ Continue goal #{i} ",
    " — trưởng nhóm lập task bổ sung dựa trên {n} task đã làm":
        " — the lead adds tasks based on the {n} task(s) already done",
    "↪ Hỏi tiếp {agent} ":
        "↪ Follow up with {agent} ",
    " — kèm {turns} lượt trước của thread":
        " — with the thread's {turns} earlier turn(s)",
    "Hôm nay":
        "Today",
    "mặc định trong config / CLI":
        "default from config / CLI",
    "ℹ Bỏ qua thiết lập. Mở lại bất cứ lúc nào bằng /setup (hoặc `ateam setup`).":
        "ℹ Setup skipped. Reopen it any time with /setup (or `ateam setup`).",
    "'{effort}' không có trong danh sách của {agent}: {v} — vẫn dùng, nhưng CLI có thể báo lỗi":
        "'{effort}' is not in {agent}'s list: {v} — used anyway, but the CLI may reject it",
    "▸ prompt gửi agent (ẩn)":
        "▸ prompt sent to the agent (hidden)",
    "✗ Lỗi: ":
        "✗ Error: ",
    "Trợ giúp ateam":
        "ateam help",
    "↑↓ / PgUp PgDn cuộn · Esc hoặc F1 đóng":
        "↑↓ / PgUp PgDn scroll · Esc or F1 to close",
    "Thiết lập đội AI":
        "AI team setup",
    "⚠ Không hỏi được danh sách model: {e}":
        "⚠ Could not get the model list: {e}",
    "  ✓ đã cài ({p})":
        "  ✓ installed ({p})",
    "  ✗ chưa cài — {v}":
        "  ✗ not installed — {v}",
    "(không dùng)":
        "(not used)",
    "Cùng một CLI làm nhiều vai trò với model/effort khác nhau → ateam tự tạo thêm agent (vd claude-review).":
        "One CLI in several roles with different models/effort → ateam creates extra agents (e.g. claude-review).",
    "đang dùng":
        "in use",
    "hoặc gõ lệnh khác, vd: npm run lint && npm test":
        "or type another command, e.g. npm run lint && npm test",
    "  (agent thêm)":
        "  (extra agent)",
    "chỉ sửa file":
        "edit files only",
    "Nhà cung cấp":
        "Provider",
    "CLI chạy agent này":
        "The CLI that runs this agent",
    "Tên":
        "Name",
    "chữ, số, - và _":
        "letters, digits, - and _",
    "(mặc định) = để CLI tự chọn":
        "(default) = let the CLI choose",
    "mức suy luận":
        "reasoning level",
    "toàn quyền khi agent cần chạy lệnh":
        "full access when the agent needs to run commands",
    "tuỳ chọn":
        "optional",
    "Nhập lệnh để xem trước.":
        "Enter a command to preview.",
    "★ trưởng nhóm ({lead})":
        "★ lead ({lead})",
    "{extra} (không có trong đội)":
        "{extra} (not on the team)",
    "tiêu đề":
        "title",
    "việc cần làm, có thể dùng {goal}":
        "what to do; may use {goal}",
    "trước":
        "previous",
    "Bước {i}: cần tiêu đề hoặc prompt":
        "Step {i}: needs a title or a prompt",
    "Agent & workflow tuỳ chỉnh":
        "Custom agents & workflows",
    "Chưa có. Bấm '+ Thêm agent' để thêm CLI bất kỳ (Gemini, Aider, script riêng…).":
        "None yet. Press '+ Add agent' to add any CLI (Gemini, Aider, your own script…).",
    "Chưa có. Bấm '+ Thêm workflow' (có mẫu: tính năng mới, sửa lỗi, review).":
        "None yet. Press '+ Add workflow' (templates: new feature, bug fix, review).",
    "Không dán được ảnh: {why}. Dán chữ bằng Cmd+V.":
        "Could not paste an image: {why}. Paste text with Cmd+V.",
    "Tối":
        "Dark",
    "🎨 Theme màu":
        "🎨 Color theme",
    "↑↓ xem trước · Tab sang cột màu nhấn · Enter lưu · Esc huỷ (trả theme cũ)":
        "↑↓ preview · Tab to accent colors · Enter save · Esc cancel (restore previous theme)",
    "✓ Đủ rồi — chốt & lập kế hoạch":
        "✓ Enough — finalize & plan",
    "⏭ Để trưởng nhóm tự quyết":
        "⏭ Let the lead decide",
    "↻ Hỏi tiếp":
        "↻ Ask again",
    "✗ Bỏ mục tiêu":
        "✗ Drop goal",
    "❓ Câu {v}: ":
        "❓ Question {v}: ",
    "▶ Duyệt & chạy  F2":
        "▶ Approve & run  F2",
    "✎ Sửa task":
        "✎ Edit task",
    "⇄ Đổi agent":
        "⇄ Change agent",
    "✗ Bỏ kế hoạch":
        "✗ Drop plan",
    "(kế hoạch không có task nào)":
        "(the plan has no tasks)",
    "✕ Đóng":
        "✕ Close",
    "hai cột":
        "split",
    "một cột":
        "unified",
    "  nhánh task của ateam":
        "  ateam task branch",
    "⎇ Nhánh — đang ở {v}":
        "⎇ Branches — on {v}",
    "Chỉ đổi tên được nhánh local":
        "Only local branches can be renamed",
    "📦 Stash — cất tạm thay đổi chưa commit":
        "📦 Stash — set aside uncommitted changes",
    "Chưa có stash nào.":
        "No stashes yet.",
    "Chỉ đọc: {v}":
        "Read-only: {v}",
    "📋 Bảng việc":
        "📋 Board",
    "🤖 Agents":
        "🤖 Agents",
    ", {n_goals} mục tiêu":
        ", {n_goals} goal(s)",
    "lỗi (mã {rc})":
        "failed (code {rc})",
    "đã dừng":
        "stopped",
    "File đã đổi trên đĩa":
        "File changed on disk",
    "{path} vừa bị sửa bên ngoài (có thể do agent) sau khi bạn mở.\nGhi đè bằng nội dung của bạn? (Huỷ rồi :e! để nạp bản trên đĩa)":
        "{path} was modified outside the editor (maybe by an agent) after you opened it.\nOverwrite it with your version? (Cancel, then :e! to load the version on disk)",
    "  ↑{ahead} chưa push":
        "  ↑{ahead} not pushed",
    "  ↓{behind} chưa pull":
        "  ↓{behind} not pulled",
    "  ✓ đồng bộ":
        "  ✓ in sync",
    "  chưa có trên remote (Push để tạo)":
        "  not on the remote yet (Push to create it)",
    "✓ Không có thay đổi nào chưa commit.":
        "✓ No uncommitted changes.",
    "📜 Lịch sử ({v} commit gần nhất)":
        "📜 History ({v} most recent commits)",
    "📜 Chưa có commit nào":
        "📜 No commits yet",
    " (kèm phần mô tả trưởng nhóm viết)":
        " (with the description the lead wrote)",
    "⇣ Đang fetch…":
        "⇣ Fetching…",
    "Dùng: /commit [--no-verify] <message>":
        "Usage: /commit [--no-verify] <message>",
    "  ⏸ TẠM DỪNG (/resume)":
        "  ⏸ PAUSED (/resume)",
    "🏁 Mục tiêu #{id} {v} — F6 hoặc bấm ↪ Tiếp tục để giao thêm việc":
        "🏁 Goal #{id} {v} — F6 or press ↪ Continue to add more work",
    " · vòng {round}]":
        " · round {round}]",
    "\n   ↪ lần tiếp {v}: {v2}":
        "\n   ↪ follow-up {v}: {v2}",
    " ↪ Tiếp tục ":
        " ↪ Continue ",
    "\n   ↳ xem khung Duyệt kế hoạch phía dưới · F2 duyệt & chạy":
        "\n   ↳ see the Review plan box below · F2 to approve & run",
    "\n   ↳ trả lời câu hỏi ở khung Hỏi đáp phía dưới":
        "\n   ↳ answer the question in the Q&A box below",
    "Gõ một mục tiêu":
        "Type a goal",
    "/grill <mục tiêu>":
        "/grill <goal>",
    "trưởng nhóm hỏi kỹ cho rõ rồi mới lập kế hoạch":
        "the lead asks questions until it's clear, then plans",
    "/task <agent> <nội dung>":
        "/task <agent> <content>",
    "giao tay cho 1 agent":
        "assign one agent by hand",
    "/flow <tên> <mục tiêu>":
        "/flow <name> <goal>",
    "chạy theo workflow dựng sẵn":
        "run a predefined workflow",
    "xem mọi lệnh & phím tắt":
        "see all commands & shortcuts",
    "mục tiêu #{id}":
        "goal #{id}",
    "hỏi tiếp {agent} trong thread này":
        "follow up with {agent} in this thread",
    "\n↪ F6: tiếp tục {what}":
        "\n↪ F6: continue {what}",
    "   hôm nay {v} lượt · {v2}":
        "   today {v} runs · {v2}",
    "\n✗ chưa cài lệnh '{binary}'":
        "\n✗ command '{binary}' is not installed",
    "Lệnh này đã dừng":
        "This command has already stopped",
    "(task chưa chạy — chưa có log)":
        "(task hasn't run — no log yet)",
    " của kế hoạch #{gid}":
        " of plan #{gid}",
    "Còn file chưa lưu":
        "Unsaved files",
    "Tab 📝 Code còn {n} file chưa lưu: {v}\nThoát và bỏ các thay đổi này?":
        "The 📝 Code tab has {n} unsaved file(s): {v}\nQuit and discard these changes?",
    "⚠ Mục tiêu #{i} chưa kết thúc — đợi xong rồi tiếp tục":
        "⚠ Goal #{i} hasn't finished — wait for it, then continue",
    "⚠ Task #{i} chưa xong (hoặc đang chờ duyệt) — đợi xong rồi tiếp tục":
        "⚠ Task #{i} hasn't finished (or is awaiting review) — wait for it, then continue",
    "Chưa có mục tiêu nào đã xong để tiếp tục — chọn 1 task trong bảng":
        "No finished goal to continue yet — select a task in the board",
    "Lỗi: {e}":
        "Error: {e}",
    "⚙ Đã cập nhật agent/workflow tuỳ chỉnh. Agent: {v}":
        "⚙ Custom agents/workflows updated. Agents: {v}",
    " (đã xoá: {v})":
        " (removed: {v})",
    "Enter: chọn · Esc: đóng · tên khác: /model <agent> <tên>":
        "Enter: pick · Esc: close · other name: /model <agent> <name>",
    "Agent & workflow tuỳ chỉnh…":
        "Custom agents & workflows…",
    "← Quay lại":
        "← Back",
    "  ⏳ đang hỏi danh sách model từ các CLI…":
        "  ⏳ asking the CLIs for their model lists…",
    " — cần thư mục là git repo có commit":
        " — needs a git repo with commits",
    "  (chưa cài)":
        "  (not installed)",
    "Thêm agent":
        "Add agent",
    "Chọn nhà cung cấp, model, effort và quyền — cờ CLI ateam tự điền. Ctrl+S lưu, Esc huỷ. CLI khác (Gemini, Aider, lệnh riêng): Nâng cao…":
        "Pick the provider, model, effort and permissions — ateam fills in the CLI flags. Ctrl+S saves, Esc cancels. Other CLIs (Gemini, Aider, your own command): Advanced…",
    "Nâng cao…":
        "Advanced…",
    "Huỷ":
        "Cancel",
    "Lưu (Ctrl+S)":
        "Save (Ctrl+S)",
    "Thêm agent tuỳ chỉnh":
        "Add custom agent",
    "Bất kỳ CLI nào có chế độ headless (nhận prompt, in kết quả rồi thoát). Chọn mẫu để điền sẵn, Ctrl+S lưu, Esc huỷ.":
        "Any CLI with a headless mode (takes a prompt, prints the result, exits). Pick a template to pre-fill, Ctrl+S saves, Esc cancels.",
    "Mẫu":
        "Template",
    "điền sẵn lệnh, cờ model/effort, cú pháp file":
        "pre-fills the command, model/effort flags, file syntax",
    "Tuỳ chọn":
        "Options",
    "pty cần cho CLI chỉ in khi có terminal (vd agy)":
        "pty is needed for CLIs that only print with a terminal (e.g. agy)",
    "\n⚠ lệnh không có {prompt}: prompt sẽ được thêm vào cuối":
        "\n⚠ the command has no {prompt}: the prompt will be appended at the end",
    "Thêm workflow":
        "Add workflow",
    "Chuỗi bước dựng sẵn, chạy bằng /flow <tên> <mục tiêu> — không cần trưởng nhóm lập kế hoạch. {goal} trong tiêu đề/prompt = mục tiêu bạn gõ. 'Sau bước': trống = sau bước liền trước, 0 = chạy ngay, 1,2 = sau bước 1 và 2.":
        "A predefined chain of steps, run with /flow <name> <goal> — no planning by the lead. {goal} in a title/prompt = the goal you type. 'After step': empty = after the previous step, 0 = run immediately, 1,2 = after steps 1 and 2.",
    "thay toàn bộ các bước":
        "replaces all the steps",
    "Mô tả":
        "Description",
    "hiện trong /flow":
        "shown in /flow",
    "review có thể giao thêm việc":
        "the review may add more work",
    "+ Thêm bước":
        "+ Add step",
    "Agent mới tham gia đội như agent có sẵn (trưởng nhóm phân việc theo vai trò, bật/tắt ở /setup). Workflow chạy bằng /flow <tên> <mục tiêu>, hoặc ★ Mặc định để gõ mục tiêu là chạy luôn. Lưu ở {CUSTOM_FILE}":
        "New agents join the team like built-in ones (the lead assigns work by role; enable/disable in /setup). Workflows run with /flow <name> <goal>, or press ★ Default so typing a goal runs it. Saved in {CUSTOM_FILE}",
    "Agent tuỳ chỉnh":
        "Custom agents",
    "+ Thêm agent":
        "+ Add agent",
    "+ Thêm workflow":
        "+ Add workflow",
    "Sửa":
        "Edit",
    "Xoá":
        "Delete",
    "'{name}' nằm trong file cấu hình — lưu sẽ tạo bản sao với tên mới.":
        "'{name}' is in the config file — saving creates a copy with a new name.",
    "Chắc chưa?":
        "Are you sure?",
    "Đã xoá '{name}'":
        "Deleted '{name}'",
    "✓ Lưu theme":
        "✓ Save theme",
    "\n   Gõ câu trả lời ở ô dưới rồi Enter · gõ số (1, 2…) hoặc bấm vào phương án để chọn":
        "\n   Type your answer below, then Enter · type a number (1, 2…) or click an option to pick it",
    "Huỷ (n)":
        "Cancel (n)",
    "Enter: chuyển sang nhánh đang chọn (nhánh remote → tạo nhánh local theo dõi nó) · Esc: đóng":
        "Enter: switch to the selected branch (remote branch → creates a local branch tracking it) · Esc: close",
    "⎇ Chuyển sang":
        "⎇ Switch to",
    "⤵ Merge vào nhánh hiện tại":
        "⤵ Merge into the current branch",
    "✗ Xoá":
        "✗ Delete",
    "✗ Xoá hẳn":
        "✗ Force delete",
    "Tên nhánh mới, vd feature/dang-nhap (Enter để tạo từ nhánh hiện tại)":
        "New branch name, e.g. feature/login (Enter to create from the current branch)",
    "＋ Tạo & chuyển sang":
        "＋ Create & switch",
    "✎ Đổi tên nhánh đang chọn":
        "✎ Rename the selected branch",
    "Gõ tên mới cho {name} vào ô bên dưới rồi bấm lại":
        "Type a new name for {name} in the box below, then press again",
    "⤴ Lấy lại (pop)":
        "⤴ Restore (pop)",
    "Áp dụng, giữ stash":
        "Apply, keep stash",
    "Ghi chú cho lần cất (không bắt buộc) — Enter để cất":
        "Note for this stash (optional) — Enter to stash",
    "📦 Cất mọi thay đổi (kể cả file mới)":
        "📦 Stash all changes (including new files)",
    "chưa có việc nào":
        "no work yet",
    "✗ Lệnh lỗi (mã {rc}): {cmd}":
        "✗ Command failed (code {rc}): {cmd}",
    "Đang mở":
        "Open",
    "File":
        "Files",
    "Ghi đè":
        "Overwrite",
    "tắt tô màu (file lớn)":
        "highlighting off (large file)",
    "Ctrl+S lưu · /vim on bật phím vim":
        "Ctrl+S saves · /vim on turns vim keys on",
    "⬇ Đang pull…":
        "⬇ Pulling…",
    "\n   📝 đã chốt yêu cầu sau {v} câu hỏi":
        "\n   📝 requirements agreed after {v} question(s)",
    "\n⏸ hết hạn mức — nghỉ đến {v}":
        "\n⏸ out of quota — resting until {v}",
    "Đã bỏ kế hoạch #{goal_id} ({n} task nháp)":
        "Dropped plan #{goal_id} ({n} draft task(s))",
    "🗑 Đã xoá log cũ — chỉ hiện dòng mới":
        "🗑 Old log cleared — only new lines are shown",
    "Thoát, bỏ thay đổi":
        "Quit, discard changes",
    "lượt":
        "runs",
    "thời gian":
        "time",
    "hết HM":
        "no quota",
    " (mới: {v})":
        " (new: {v})",
    "Dùng: /task <agent>[:model][@effort] <nội dung>  — agent: {v}":
        "Usage: /task <agent>[:model][@effort] <content>  — agents: {v}",
    "Sửa agent ":
        "Edit agent ",
    "trưởng nhóm chia việc dựa vào đây":
        "the lead assigns work based on this",
    "{label}: thiếu dấu nháy đóng":
        "{label}: missing closing quote",
    "Sửa workflow ":
        "Edit workflow ",
    "Trưởng nhóm review khi xong":
        "The lead reviews when done",
    "Bước {i}: 'Sau bước' phải là số bước đứng trước (1…{v})":
        "Step {i}: 'After step' must be earlier step numbers (1…{v})",
    "'{name}' đang là trưởng nhóm — đổi trưởng nhóm ở /setup trước.":
        "'{name}' is the lead — change the lead in /setup first.",
    "'{name}' nằm trong file cấu hình khác ({v}) — sửa file đó để xoá.":
        "'{name}' is in another config file ({v}) — edit that file to delete it.",
    "Sáng":
        "Light",
    "★ khuyên dùng: ":
        "★ recommended: ",
    "── {v} (mã {rc}) sau {v2} ──":
        "── {v} (code {rc}) after {v2} ──",
    "chỉ đọc":
        "read-only",
    "   i sửa · :w lưu · :q đóng · / tìm · u hoàn tác · /vim off tắt phím vim":
        "   i insert · :w save · :q close · / search · u undo · /vim off disables vim keys",
    "✗ Xoá stash":
        "✗ Drop stash",
    "Xoá {ref}? Thay đổi trong đó sẽ mất.":
        "Drop {ref}? The changes in it will be lost.",
    "⬆ Đang push…":
        "⬆ Pushing…",
    "  💻 {v} lệnh đang chạy":
        "  💻 {v} command(s) running",
    "  · task mới chuyển cho {fb}":
        "  · new tasks go to {fb}",
    "  · task của nó chờ hồi hạn mức":
        "  · its tasks wait for the quota",
    "\n○ rảnh":
        "\n○ idle",
    "Đang chạy — Dừng trước rồi mới xoá":
        "Running — stop it before removing",
    "Dùng: /{cmd} <agent> <giá trị|->  — agent: {v}":
        "Usage: /{cmd} <agent> <value|->  — agents: {v}",
    "(chọn để điền sẵn)":
        "(pick to pre-fill)",
    "Chạy trong terminal giả (pty)":
        "Run in a pseudo-terminal (pty)",
    "Chạy lệnh kiểm tra sau task":
        "Run the check command after tasks",
    "Toàn quyền":
        "Full access",
    "{label}: phải là số nguyên dương":
        "{label}: must be a positive integer",
    "vd: tinh-nang, sua-loi":
        "e.g. new-feature, bug-fix",
    "  ★ khuyên dùng":
        "  ★ recommended",
    "＋ Tạo git repo (git init)":
        "＋ Create a git repo (git init)",
    "  · {v} dòng":
        "  · {v} lines",
    "  · gần nhất #{id} ":
        "  · last #{id} ",
    "Dùng: /models [agent] [làm mới] — agent: {v}":
        "Usage: /models [agent] [refresh] — agents: {v}",
    "🗑 Dọn task đã xong":
        "🗑 Clear finished tasks",
    "🗑 Xoá log":
        "🗑 Clear log",
    "■ Dừng":
        "■ Stop",
    "↻ Chạy lại":
        "↻ Restart",
    "✗ Huỷ merge":
        "✗ Abort merge",
    "⎇ Nhánh":
        "⎇ Branches",
    "Tạo repo để theo dõi thay đổi, commit, và dùng chế độ worktree (mỗi task một nhánh riêng).\n":
        "Create a repo to track changes, commit, and use worktree mode (one branch per task).\n",
    "Tìm file… (Enter mở)":
        "Find file… (Enter opens)",
    "  · im lặng {v}":
        "  · silent {v}",
    "Đang hỏi {agent} danh sách model…":
        "Asking {agent} for its model list…",
    "Dùng: /set <task> model|effort <giá trị|->":
        "Usage: /set <task> model|effort <value|->",
    "+ Tất cả":
        "+ All",
    "Commit message — Enter để commit":
        "Commit message — Enter to commit",
    "✨ AI viết":
        "✨ AI write",
    "Sửa commit trước":
        "Amend last commit",
    "Bỏ qua hook (--no-verify)":
        "Skip hooks (--no-verify)",
    "Δ Xem commit":
        "Δ View commit",
    "⎌ Bỏ commit cuối":
        "⎌ Undo last commit",
    "Thư mục này chưa là git repo.\n\n":
        "This folder is not a git repo yet.\n\n",
    "✓ xong":
        "✓ done",
    "✗ Xoá hẳn nhánh":
        "✗ Force delete branch",
    "Xoá nhánh {name} kể cả commit chưa merge?\nCác commit đó sẽ mất.":
        "Delete branch {name} including unmerged commits?\nThose commits will be lost.",
    "Xoá hẳn":
        "Force delete",
    "Tiêu đề":
        "Title",
    "Sau bước":
        "After step",
    "■ đã dừng":
        "■ stopped",
    "✗ lỗi":
        "✗ failed",
    "⚙ Tắt kiểm tra sau mỗi task cho dự án này.":
        "⚙ Check after each task turned off for this project.",
    "⚙ Kiểm tra sau mỗi task: `{rest}` (sửa tối đa {max_fix_attempts} lần)":
        "⚙ Check after each task: `{rest}` (up to {max_fix_attempts} fix attempts)",
    "Lệnh không hỗ trợ: :{cmd}":
        "Not supported: :{cmd}",
    "Lệnh kiểm tra: {v} · sửa tối đa {max_fix_attempts} lần":
        "Check command: {v} · up to {max_fix_attempts} fix attempts",
    " · người sửa: {fix_agent}":
        " · fixer: {fix_agent}",
    "Dùng: /cooldown <agent> <phút|off>":
        "Usage: /cooldown <agent> <minutes|off>",
    "Đã duyệt {n} task":
        "Approved {n} task(s)",
    "Không có task nháp":
        "No draft tasks",
    "Đã bỏ kế hoạch #{gid} ({v} task nháp)":
        "Dropped plan #{gid} ({v} draft task(s))",
    "Không có kế hoạch nháp nào để bỏ":
        "No draft plan to drop",
    "Bỏ commit cuối cùng, giữ nguyên thay đổi của nó (ở trạng thái đã stage) để sửa rồi commit lại?":
        "Undo the last commit, keeping its changes (staged) so you can fix them and commit again?",
    "Bỏ commit":
        "Undo commit",
    "⏸ Tạm dừng: không bắt đầu task mới (task đang chạy vẫn tiếp tục).":
        "⏸ Paused: no new tasks will start (running tasks continue).",
    "▶ Tiếp tục.":
        "▶ Resumed.",
    " ★ trưởng nhóm":
        " ★ lead",
    " · tuỳ chỉnh (/custom)":
        " · custom (/custom)",
    "\n   vai trò: {role}":
        "\n   role: {role}",
    "\n   lệnh: {v}":
        "\n   command: {v}",
    "Theme: {v}":
        "Theme: {v}",
    "Không có theme {name} — có: {v}":
        "No theme named {name} — available: {v}",
    "Không có màu nhấn {name} — có: {v}":
        "No accent color named {name} — available: {v}",
    "Ngôn ngữ: {v} · đổi bằng /lang en hoặc /lang vi":
        "Language: {v} · change with /lang en or /lang vi",
    "Đang dùng {v} rồi":
        "Already using {v}",
    "Đã lưu {v} — áp dụng khi mở lại app (đang có agent chạy, không tự mở lại)":
        "Saved {v} — applies when you reopen the app (agents are running, so it won't reopen now)",
    "↪ Trưởng nhóm đang lập kế hoạch tiếp cho mục tiêu #{i}":
        "↪ The lead is planning the follow-up for goal #{i}",
    "↪ Task #{i}: hỏi tiếp {agent}":
        "↪ Task #{i}: following up with {agent}",
    "Không có lệnh nào đang chạy để dừng":
        "No running command to stop",
    "■ Đã dừng: {cmd}":
        "■ Stopped: {cmd}",
    "Phím vim trong tab 📝 Code: bật":
        "Vim keys in the 📝 Code tab: on",
    "Phím vim trong tab 📝 Code: tắt (Ctrl+S lưu)":
        "Vim keys in the 📝 Code tab: off (Ctrl+S saves)",
    "Phím vim: {v} · /vim on|off · /vim <file> mở file":
        "Vim keys: {v} · /vim on|off · /vim <file> opens a file",
    "Không có workflow '{name}'":
        "No workflow '{name}'",
    " · gõ / để xem danh sách, F1 trợ giúp":
        " · type / for the list, F1 for help",
    "bật":
        "on",
    "tắt":
        "off",
    " — có phải /{near}?":
        " — did you mean /{near}?",
    "→ Cập nhật ateam {version} → {latest}":
        "→ Updating ateam {version} → {latest}",
    "Đã cập nhật lên {latest}. Thoát (Ctrl+Q) rồi mở lại ateam để dùng bản mới.":
        "Updated to {latest}. Quit (Ctrl+Q) and reopen ateam to use the new version.",
    "Không kiểm tra được phiên bản mới (mất mạng?). Thử lại sau.":
        "Could not check for a new version (offline?). Try again later.",
    "Có bản {latest} (đang chạy {version}), nhưng ateam được cài từ mã nguồn ở {src}: cập nhật bằng `git -C {src} pull`, rồi mở lại app.":
        "Version {latest} is available (running {version}), but ateam was installed from source at {src}: update with `git -C {src} pull`, then reopen the app.",
    "Cập nhật thất bại (mã thoát {code}) — xem log ở trên, hoặc chạy tay: curl -fsSL {GET_SH} | bash":
        "Update failed (exit code {code}) — see the log above, or run by hand: curl -fsSL {GET_SH} | bash",
    # --- giao diện web (ateam/web.py)
    'Bảng việc':
        'Board',
    'Đội':
        'Team',
    'Terminal':
        'Terminal',
    'Git':
        'Git',
    'Code':
        'Code',
    'sắp có':
        'soon',
    'Đã kết nối':
        'Connected',
    'Mất kết nối — đang thử lại…':
        'Disconnected — retrying…',
    'Tạm dừng':
        'Pause',
    'Tiếp tục nhận task':
        'Resume',
    'Đang tạm dừng':
        'Paused',
    'Dọn việc đã xong':
        'Clear finished',
    'Đổi sáng / tối':
        'Toggle light / dark',
    'chờ chạy':
        'queued',
    'Nháp':
        'Draft',
    'Chờ chạy':
        'Queued',
    'Đang chạy':
        'Running',
    'Chờ duyệt':
        'In review',
    'Xong':
        'Done',
    'Lỗi / huỷ':
        'Failed / cancelled',
    'Trống':
        'Empty',
    'Chưa có mục tiêu nào':
        'No goals yet',
    'Gõ yêu cầu ở ô dưới cùng — trưởng nhóm sẽ lập kế hoạch, chia việc cho đội.':
        'Type a request in the box below — the lead will plan it and split the work across the team.',
    'Tất cả':
        'All',
    'vòng {n}':
        'round {n}',
    '↪ Tiếp tục':
        '↪ Continue',
    '{n} lần tiếp':
        '{n} follow-ups',
    'chờ duyệt kế hoạch':
        'plan awaiting review',
    'thất bại':
        'failed',
    'đang hỏi đáp':
        'in Q&A',
    'Kế hoạch #{id} chờ duyệt':
        'Plan #{id} awaiting review',
    '{n} task':
        '{n} tasks',
    'Bỏ kế hoạch':
        'Drop plan',
    'sau {v}':
        'after {v}',
    'Thôi':
        'Cancel',
    'Trưởng nhóm hỏi để hiểu rõ yêu cầu':
        'The lead is clarifying the requirements',
    'Câu {n}':
        'Question {n}',
    'đã trả lời {n} câu':
        '{n} answered',
    '{lead} đang nghĩ câu hỏi tiếp theo…':
        '{lead} is thinking of the next question…',
    'Bấm một phương án, hoặc gõ câu trả lời ở ô dưới rồi Enter':
        'Pick an option, or type an answer in the box below and press Enter',
    'khuyên dùng':
        'recommended',
    'Đủ rồi — chốt & lập kế hoạch':
        "That's enough — finalize & plan",
    'Để trưởng nhóm tự quyết':
        'Let the lead decide',
    'Hỏi tiếp':
        'Ask more',
    'Bỏ mục tiêu':
        'Drop goal',
    'Nhập mục tiêu cho trưởng nhóm · / lệnh · ! lệnh terminal · @ nhắc file':
        'Type a goal for the lead · / commands · ! terminal command · @ mention a file',
    "Nhập mục tiêu (chạy theo workflow '{wf}') · / lệnh · ! lệnh terminal · @ nhắc file":
        "Type a goal (runs workflow '{wf}') · / commands · ! terminal command · @ mention a file",
    'Trả lời câu hỏi của trưởng nhóm (Enter) · gõ số để chọn phương án':
        "Answer the lead's question (Enter) · type a number to pick an option",
    'Enter gửi · Shift+Enter xuống dòng · ⌘V / kéo-thả để dán ảnh':
        'Enter to send · Shift+Enter for a new line · ⌘V / drag-and-drop to attach an image',
    'Merge':
        'Merge',
    'Từ chối':
        'Reject',
    'Góp ý (để trống = chỉ từ chối, có góp ý = giao làm lại)':
        'Feedback (empty = just reject, with feedback = assign a redo)',
    'Log':
        'Log',
    'Nội dung':
        'Prompt',
    'Kết quả':
        'Result',
    'Chưa có kết quả.':
        'No result yet.',
    'Ghi chú':
        'Note',
    'Tóm tắt':
        'Summary',
    'Giao việc':
        'Delegate',
    'Lỗi':
        'Error',
    'Bắt đầu':
        'Started',
    'Thời gian':
        'Duration',
    'Phụ thuộc':
        'Depends on',
    'Lần thử':
        'Attempts',
    'Nhánh':
        'Branch',
    'trưởng nhóm':
        'lead',
    'rảnh':
        'idle',
    'chưa cài':
        'not installed',
    'nghỉ tới {v}':
        'resting until {v}',
    'đang chạy {n} việc':
        'running {n}',
    'Lệnh terminal':
        'Terminal commands',
    'Chưa chạy lệnh nào':
        'No commands run yet',
    'Gõ ! rồi lệnh ở ô dưới, vd !npm run dev — hoặc chọn một script gợi ý:':
        'Type ! and a command in the box below, e.g. !npm run dev — or pick a suggested script:',
    'Dừng':
        'Stop',
    'thoát với mã {rc}':
        'exited with code {rc}',
    'Script của dự án':
        'Project scripts',
    'Diff task #{id}':
        'Diff of task #{id}',
    'Đang tải…':
        'Loading…',
    'Lệnh có trên web':
        'Commands available on the web',
    'Ctrl+K: ô nhập · F2: duyệt kế hoạch · Esc: đóng':
        'Ctrl+K: input · F2: approve plan · Esc: close',
    'worktree':
        'worktree',
    'shared':
        'shared',
    'Không hiểu thao tác {op}':
        'Unknown action {op}',
    'Gõ / để xem các lệnh có trên web':
        'Type / to see the commands available on the web',
    'Đã thêm task #{tid} cho {to}':
        'Added task #{tid} for {to}',
    '/{cmd} chưa có trên giao diện web — dùng `ateam` trong terminal (hoặc `ateam web --tui`)':
        '/{cmd} is not available on the web UI yet — use `ateam` in a terminal (or `ateam web --tui`)',
    'Dùng: /goal <mục tiêu>':
        'Usage: /goal <goal>',
    'Dùng: /grill <mục tiêu>':
        'Usage: /grill <goal>',
    'Dùng: /flow <tên> <mục tiêu> — workflow: {v}':
        'Usage: /flow <name> <goal> — workflows: {v}',
    'Dùng: /continue <m12|t40> <yêu cầu>':
        'Usage: /continue <m12|t40> <request>',
    'Dùng: /note <nội dung>':
        'Usage: /note <text>',
    'Dự án này đang mở ở một phiên ateam khác — đóng phiên đó rồi chạy lại.':
        'This project is already open in another ateam session — close it and run again.',
    'mở giao diện web trên trình duyệt (http://127.0.0.1:PORT, cần aiohttp)':
        'open the web UI in a browser (http://127.0.0.1:PORT, needs aiohttp)',
    'tự mở trình duyệt':
        'open the browser automatically',
    'giao diện terminal trong trình duyệt (cần textual-serve)':
        'the terminal UI in a browser (needs textual-serve)',
    'Cần cài thêm aiohttp: {v}':
        'aiohttp is required: {v}',
    # --- giao diện web: Git, Code, diff, /setup, /custom, gợi ý lệnh
    'Xung đột':
        'Conflicts',
    'Đã stage':
        'Staged',
    'Thay đổi':
        'Changes',
    'Lịch sử':
        'History',
    'Huỷ thao tác':
        'Abort',
    'đang {v}':
        '{v} in progress',
    'đồng bộ':
        'in sync',
    'chưa có trên remote':
        'not on the remote yet',
    'Thư mục này chưa phải git repo':
        'This folder is not a git repo yet',
    'Tạo repo để theo dõi thay đổi, xem diff và dùng chế độ worktree.':
        'Create a repo to track changes, view diffs and use worktree mode.',
    'Commit message — chưa stage gì: commit tất cả thay đổi':
        'Commit message — nothing staged: commits all changes',
    'Commit message cho {n} file đã stage':
        'Commit message for {n} staged file(s)',
    'Message mới cho commit trước (trống = giữ nguyên)':
        'New message for the previous commit (empty = keep it)',
    'Sửa commit trước (amend)':
        'Amend previous commit',
    'AI viết':
        'AI write',
    'Agent viết commit message':
        'Agent that writes the commit message',
    'Trưởng nhóm ({lead})':
        'Team lead ({lead})',
    'Bỏ mọi thay đổi chưa stage của {path}?':
        'Discard all unstaged changes to {path}?',
    'XOÁ file mới {path}? (chưa từng commit — không lấy lại được)':
        'DELETE new file {path}? (never committed — cannot be recovered)',
    'Tạo commit đảo ngược {v}?':
        'Create a commit that reverts {v}?',
    'Chuyển sang':
        'Check out',
    'Đổi tên':
        'Rename',
    'Tên mới cho nhánh {name}:':
        'New name for branch {name}:',
    'Tên nhánh mới':
        'New branch name',
    'Tạo nhánh':
        'Create branch',
    'Merge {name} vào {cur}?':
        'Merge {name} into {cur}?',
    'Xoá hẳn nhánh':
        'Force delete branch',
    'Nhánh {name} chưa merge hết — xoá hẳn (mất các commit chưa merge)?':
        'Branch {name} is not fully merged — force delete it (losing the unmerged commits)?',
    'Ghi chú cho stash (tuỳ chọn)':
        'Stash message (optional)',
    'Cất thay đổi':
        'Stash changes',
    'Xoá {ref}? Không lấy lại được.':
        'Delete {ref}? This cannot be undone.',
    'Làm mới':
        'Refresh',
    'Đoạn sau':
        'Next hunk',
    '2 cột':
        'Split',
    'Mở trong Code':
        'Open in Code',
    'File nhị phân — không hiện nội dung':
        'Binary file — content not shown',
    'File rỗng':
        'Empty file',
    'Chỉ đổi tên, nội dung giữ nguyên':
        'Renamed only, content unchanged',
    'File dài — chỉ hiện 4000 dòng đầu':
        'Long file — only the first 4000 lines are shown',
    'n/p: file · [ ]: đoạn đổi · s: 1 cột / 2 cột · e: mở trong Code · Esc: đóng':
        'n/p: file · [ ]: hunk · s: unified / split · e: open in Code · Esc: close',
    'Tìm file… (Enter mở · ⌘P)':
        'Find file… (Enter opens · ⌘P)',
    'Không có file':
        'No files',
    'Chọn file ở cây bên trái, hoặc /code @file:dòng':
        'Pick a file in the tree on the left, or /code @file:line',
    'vim: i sửa · Esc · :w lưu · :q đóng · :bn/:bp đổi file · /vim off để tắt':
        'vim: i insert · Esc · :w save · :q close · :bn/:bp switch file · /vim off to disable',
    'Ctrl/⌘+S lưu · /vim on để bật phím vim':
        'Ctrl/⌘+S saves · /vim on enables vim keys',
    'Video này không cho phát nhúng ngoài YouTube — thử đài hoặc link khác':
        "This video can't be played outside YouTube — try another station or link",
    'Nhạc lofi':
        'Lofi music',
    'To-do':
        'To-do',
    'Prompt':
        'Prompt',
    'Tổng kết của trưởng nhóm':
        "Lead's summary",
    'Tìm':
        'Search',
    ' … (+{n} ký tự — dòng quá dài, mở file để xem đủ)':
        ' … (+{n} characters — line too long, open the file to see it all)',
    '[từ khoá]':
        '[keyword]',
    'tìm & thay trong toàn dự án (F3), như VS Code':
        'search & replace across the project (F3), like VS Code',
    'Thay trong file':
        'Replace in file',
    'Bỏ file':
        'Dismiss file',
    'Tìm trong dự án':
        'Search project',
    'Gõ chữ thay thế ở ô "Thay bằng" trước':
        'Type the replacement in the "Replace" box first',
    '🔍 Tìm & thay trong dự án':
        '🔍 Search & replace in the project',
    'Enter mở file · Tab sang kết quả · r thay trong file · x bỏ file · Ctrl+R thay tất cả · Esc đóng':
        'Enter opens the file · Tab to results · r replace in file · x dismiss file · Ctrl+R replace all · Esc closes',
    'Nguyên từ':
        'Whole word',
    'Tìm…':
        'Search…',
    'Thay bằng… (để trống: chỉ tìm)':
        'Replace with… (empty: search only)',
    'Thay bằng':
        'Replace',
    'Phân biệt hoa/thường':
        'Match case',
    'Khớp nguyên từ':
        'Match whole word',
    'Dùng regex':
        'Use regular expression',
    'Hiện ô thay thế':
        'Toggle replace',
    'Lọc file':
        'File filters',
    'File gồm — vd src, *.ts':
        'Files to include — e.g. src, *.ts',
    'File bỏ qua — vd *.test.ts, dist':
        'Files to exclude — e.g. *.test.ts, dist',
    'Đang tìm…':
        'Searching…',
    'Không có kết quả':
        'No results',
    '{n} kết quả trong {f} file':
        '{n} results in {f} files',
    'quá nhiều, chỉ hiện phần đầu — thu hẹp tìm kiếm':
        'too many, showing the first ones — narrow your search',
    'Thay tất cả':
        'Replace all',
    'Thay trong file này':
        'Replace in this file',
    'Bỏ khỏi kết quả':
        'Dismiss',
    'Thay {n} kết quả trong {f} file bằng "{r}"? App không hoàn tác được — xem lại bằng git diff.':
        'Replace {n} results in {f} files with "{r}"? This cannot be undone in the app — review with git diff.',
    'Bỏ qua file đang sửa dở (chưa lưu): {v}':
        'Skipped files with unsaved changes: {v}',
    '🔍 Thay "{q}" → "{r}": {n} chỗ trong {f} file':
        '🔍 Replaced "{q}" → "{r}": {n} matches in {f} files',
    'Đã thay {n} kết quả trong {f} file':
        'Replaced {n} results in {f} files',
    'Không có gì để thay':
        'Nothing to replace',
    'Regex không hợp lệ: {e}':
        'Invalid regex: {e}',
    'Không ghi được file: {e}':
        'Could not write the file: {e}',
    'Ảnh quá lớn (tối đa {n} MB)':
        'Image too large (max {n} MB)',
    'Dữ liệu dán vào không phải ảnh':
        'What you pasted is not an image',
    'sửa nhanh vai trò · CLI · model · effort của đội':
        "quickly edit the team's roles · CLI · model · effort",
    '⚡ Vai trò · model · effort':
        '⚡ Roles · model · effort',
    'Lưu là có hiệu lực ngay; kiểu làm việc, quyền, lệnh kiểm tra giữ nguyên (đổi ở /setup).':
        'Takes effect as soon as you save; work style, permissions and check command stay as they are (change them in /setup).',
    'Thiết lập đầy đủ (/setup)…':
        'Full setup (/setup)…',
    'Đổi CLI · model · effort cho từng vai trò — lưu là có hiệu lực ngay. Kiểu làm việc, quyền, lệnh kiểm tra giữ nguyên (đổi ở /setup).':
        'Change the CLI · model · effort for each role — takes effect as soon as you save. Work style, permissions and check command stay as they are (change them in /setup).',
    '⚡ Đã lưu vai trò. Trưởng nhóm: {lead}. Đội: {v}.':
        '⚡ Roles saved. Lead: {lead}. Team: {v}.',
    'Đã lưu vai trò':
        'Roles saved',
    'xem lại kế hoạch của mục tiêu, kể cả đã duyệt / đã xong':
        "review a goal's plan, even after approval / completion",
    '[việc cần làm]':
        '[to-do]',
    'mở tab To-do (lưu ngoài repo); kèm nội dung thì thêm việc':
        'open the To-do tab (stored outside the repo); with text, add it',
    'Sửa việc — Enter lưu, Esc huỷ':
        'Edit — Enter saves, Esc cancels',
    'Xong/chưa':
        'Done/undo',
    'Lên':
        'Up',
    'Xuống':
        'Down',
    'Space xong/chưa · e sửa · d xoá · Shift+↑↓ đổi thứ tự · c xoá việc đã xong':
        'Space done/undo · e edit · d delete · Shift+↑↓ reorder · c clear completed',
    '📋 Kế hoạch mục tiêu #{id}':
        '📋 Plan for goal #{id}',
    '↑↓ / PgUp PgDn cuộn · p hiện/ẩn prompt · Esc đóng':
        '↑↓ / PgUp PgDn scroll · p show/hide prompts · Esc closes',
    'Kế hoạch của trưởng nhóm':
        "Lead's plan",
    'Việc':
        'Task',
    'Chạy sau':
        'After',
    'Kết quả từng agent':
        "Each agent's result",
    'Xem prompt giao cho agent':
        'Show the prompt given to the agent',
    '✅ To-do':
        '✅ To-do',
    '✅ Đã thêm vào To-do':
        '✅ Added to To-do',
    'Thêm việc cần làm rồi Enter…':
        'Add a to-do, then Enter…',
    '{n} việc chưa xong':
        '{n} left to do',
    'Xoá việc đã xong':
        'Clear completed',
    'Chưa có việc nào':
        'Nothing to do yet',
    'Lưu riêng cho dự án này ở {path} — ngoài thư mục dự án, không cần .gitignore.':
        'Saved for this project only at {path} — outside the project folder, no .gitignore needed.',
    'Bấm đúp để sửa':
        'Double-click to edit',
    'Nhập nội dung việc cần làm':
        'Type what needs doing',
    'Kế hoạch':
        'Plan',
    'Kế hoạch mục tiêu #{id}':
        'Plan for goal #{id}',
    'Kế hoạch ban đầu':
        'Original plan',
    'Theo workflow':
        'From workflow',
    'Bổ sung khi review':
        'Added at review',
    'Tiếp tục / làm thêm':
        'Follow-ups',
    'Giao việc chéo':
        'Delegated',
    'Thêm tay':
        'Added by hand',
    'Mục tiêu này chưa có task nào':
        'This goal has no tasks yet',
    'Không thấy mục tiêu #{id}':
        'Goal #{id} not found',
    'Phát':
        'Play',
    'Thu gọn':
        'Collapse',
    'Mở rộng':
        'Expand',
    'Tắt nhạc':
        'Stop music',
    'Link của bạn':
        'Your link',
    'Dán link YouTube hoặc stream mp3/aac rồi Enter…':
        'Paste a YouTube or mp3/aac stream link, then Enter…',
    'Link không phát được — dùng link YouTube hoặc link stream http(s)':
        "Can't play this link — use a YouTube link or an http(s) stream link",
    'Radio online (cần mạng). Đài và âm lượng lưu riêng cho trình duyệt này.':
        'Online radio (needs internet). Station and volume are saved for this browser only.',
    'Chia đôi':
        'Split',
    'Xem trước':
        'Preview',
    'Xem trước markdown (Ctrl/⌘+Shift+V đổi chế độ)':
        'Markdown preview (Ctrl/⌘+Shift+V switches mode)',
    'dòng {r}/{n}, cột {c}':
        'line {r}/{n}, col {c}',
    'chỉ đọc: {v}':
        'read-only: {v}',
    'Chỉ đọc':
        'Read-only',
    'File đang ở chế độ chỉ đọc ({v}). Vẫn ghi?':
        'The file is read-only ({v}). Write anyway?',
    'Vẫn ghi':
        'Write anyway',
    '{path} đã bị sửa từ lúc bạn mở (có thể do agent). Ghi đè bằng nội dung của bạn?':
        '{path} changed since you opened it (maybe by an agent). Overwrite it with your version?',
    'Chưa lưu':
        'Unsaved',
    '{path} còn thay đổi chưa lưu. Đóng và bỏ thay đổi?':
        '{path} has unsaved changes. Close and discard them?',
    'File đổi trên đĩa — đã nạp lại':
        'File changed on disk — reloaded',
    'File vừa đổi trên đĩa (có thể do agent sửa) — :e! để nạp lại (bỏ phần đang sửa) hoặc :w! để ghi đè':
        'The file just changed on disk (maybe an agent edited it) — :e! to reload (dropping your edits) or :w! to overwrite',
    'Không nạp được editor (vendor/codemirror.js)':
        'Could not load the editor (vendor/codemirror.js)',
    'Agent':
        'Agent',
    'Agent · thêm :model hoặc @effort':
        'Agent · add :model or @effort',
    'Model của {v}':
        'Models of {v}',
    'Effort của {v}':
        'Efforts of {v}',
    'Task':
        'Task',
    'Task (hoặc @file để mở trong Code)':
        'Task (or @file to open in Code)',
    'Mục tiêu':
        'Goal',
    'Tiếp tục mục tiêu / thread':
        'Continue goal / thread',
    'Số phút':
        'Minutes',
    'hỏi lại danh sách model từ CLI':
        'ask the CLI for its model list again',
    'lấy lại và xoá stash':
        'restore and drop the stash',
    'lấy lại, giữ stash':
        'restore, keep the stash',
    'danh sách stash':
        'list stashes',
    'push đè (--force-with-lease)':
        'force push (--force-with-lease)',
    'bỏ qua hook':
        'skip hooks',
    'tắt kiểm tra':
        'turn checks off',
    'Chọn {key} cho {agent} (đang dùng: {v})':
        'Pick {key} for {agent} (current: {v})',
    'hoặc gõ tên khác rồi Enter':
        'or type another name and press Enter',
    'Bấm để đổi model / effort':
        'Click to change model / effort',
    'Giao diện':
        'Appearance',
    'Màu nhấn':
        'Accent color',
    'Mặc định (tím → ngọc)':
        'Default (violet → cyan)',
    'Theo hệ thống':
        'System',
    'Màu nhấn lưu chung với giao diện terminal; sáng/tối chỉ áp cho trình duyệt này.':
        'The accent color is shared with the terminal UI; light/dark applies to this browser only.',
    'Thiết lập đội AI · Bước {v}/{n} — {title}':
        'AI team setup · Step {v}/{n} — {title}',
    'Quay lại':
        'Back',
    'Tiếp':
        'Next',
    'Lưu & bắt đầu':
        'Save & start',
    'đã cài ({p})':
        'installed ({p})',
    'chưa cài — {v}':
        'not installed — {v}',
    'đang hỏi danh sách model từ các CLI…':
        'asking the CLIs for their model lists…',
    'agent thêm':
        'extra agent',
    'Agent tuỳ chỉnh giữ nguyên: {v}':
        'Custom agents kept: {v}',
    'Cách làm việc':
        'How the team works',
    'Chưa có trưởng nhóm — quay lại bước Vai trò.':
        'No lead yet — go back to the Roles step.',
    'Agent mới tham gia đội như agent có sẵn (trưởng nhóm phân việc theo vai trò, bật/tắt ở /setup). Workflow chạy bằng /flow <tên> <mục tiêu>, hoặc ★ Đặt mặc định để gõ mục tiêu là chạy luôn.':
        'New agents join the team like built-in ones (the lead assigns work by role; enable/disable in /setup). Run workflows with /flow <name> <goal>, or press ★ Make default so typing a goal runs it.',
    'Sửa agent {name}':
        'Edit agent {name}',
    'Sửa workflow {name}':
        'Edit workflow {name}',
    '{n} bước: {v}':
        '{n} steps: {v}',
    "Xoá '{name}'?":
        "Delete '{name}'?",
    'Chọn nhà cung cấp, model, effort và quyền — cờ CLI ateam tự điền. CLI khác (Gemini, Aider, lệnh riêng): Nâng cao…':
        'Pick a provider, model, effort and access — ateam fills in the CLI flags. Other CLIs (Gemini, Aider, your own command): Advanced…',
    'Bất kỳ CLI nào có chế độ headless (nhận prompt, in kết quả rồi thoát). Chọn mẫu để điền sẵn.':
        'Any CLI with a headless mode (takes a prompt, prints the result and exits). Pick a template to prefill.',
    'Lệnh sẽ chạy:':
        'Command to run:',
    "đã cài '{v}'":
        "'{v}' installed",
    "chưa cài '{v}'":
        "'{v}' not installed",
    'toàn quyền: agent chạy được mọi lệnh trên máy, chỉ dùng với repo tin tưởng':
        'full access: the agent can run any command on this machine — only for repos you trust',
    'lệnh không có {prompt}: prompt sẽ được thêm vào cuối':
        'the command has no {prompt}: the prompt will be appended at the end',
    'trưởng nhóm ({lead})':
        'lead ({lead})',
    '{v} (không có trong đội)':
        '{v} (not in the team)',
    'Thêm bước':
        'Add step',
    'Đóng tab trình duyệt là xong; dừng hẳn server: Ctrl+C ở terminal chạy `ateam web`':
        'Just close the browser tab; to stop the server: Ctrl+C in the terminal running `ateam web`',
    'Thống kê':
        'Usage',
    '✨ Đã điền commit message — sửa nếu cần rồi commit':
        '✨ Commit message filled in — edit it if needed, then commit',
    'Không thấy commit {v}':
        'Commit {v} not found',
    'Đường dẫn không hợp lệ (ngoài dự án): {path}':
        'Invalid path (outside the project): {path}',
    'Chỉ đọc ({note}) — :w! để vẫn ghi':
        'Read-only ({note}) — :w! to write anyway',
    'File đã đổi trên đĩa (có thể do agent sửa)':
        'The file changed on disk (maybe an agent edited it)',
    '{path} là thư mục':
        '{path} is a folder',
    'Đã lưu thiết lập':
        'Setup saved',
    'Màu nhấn: {v}':
        'Accent color: {v}',
    'Chọn nhà cung cấp':
        'Pick a provider',
    'Giao diện & màu nhấn':
        'Appearance & accent',
    '⚠ {agent} không nhận effort với model {model} — chạy lại không kèm effort':
        '⚠ {agent} does not accept an effort for model {model} — retrying without effort',
    '↻ chạy lại không kèm effort: {label}':
        '↻ retrying without effort: {label}',
    '{agent} không trả về commit message (xem .ateam/logs/lead.log)':
        '{agent} did not return a commit message (see .ateam/logs/lead.log)',
    "Không có agent '{name}'":
        "No agent '{name}'",
    'Thông báo thử — có kế hoạch/diff chờ duyệt hoặc task lỗi sẽ báo thế này.':
        'Test notification — plans/diffs awaiting approval and failed tasks will show up like this.',
    'Thông báo: {v} · /notify on|app|off|test':
        'Notifications: {v} · /notify on|app|off|test',
    'bật (trong app + thông báo hệ thống)':
        'on (in app + system notifications)',
    'chỉ trong app':
        'in app only',
    '🔔 Đã gửi thông báo thử':
        '🔔 Test notification sent',
    '📝 Kế hoạch chờ duyệt':
        '📝 Plan awaiting approval',
    'Mục tiêu #{gid}: {text}':
        'Goal #{gid}: {text}',
    'Âm thanh':
        'Sound',
    'Phát âm thanh khi có thông báo':
        'Play a sound on notifications',
    'Âm lượng':
        'Volume',
    'Nghe thử':
        'Preview',
    'Mỗi loại có âm riêng: kế hoạch / diff chờ duyệt, agent hỏi, task lỗi, mục tiêu xong. Lưu riêng cho trình duyệt này.':
        'Each kind has its own sound: plan / diff awaiting approval, agent question, failed task, goal done. Saved for this browser only.',
    '🏁 Mục tiêu hoàn thành':
        '🏁 Goal completed',
    'Mục tiêu kết thúc chưa xong':
        'Goal ended unfinished',
    '✗ Task lỗi':
        '✗ Task failed',
    '⚠ Task bị xung đột khi merge':
        '⚠ Task has a merge conflict',
    '👀 Task chờ duyệt diff':
        '👀 Task diff awaiting review',
    'thông báo khi có kế hoạch/diff chờ duyệt hoặc task lỗi':
        'notify when a plan/diff awaits approval or a task fails',
    'trong app + thông báo trình duyệt':
        'in app + browser notifications',
    'tắt thông báo':
        'turn notifications off',
    'gửi thử một thông báo':
        'send a test notification',
    'luồng mặc định: agent · model · effort từng bước':
        'default flow: agent · model · effort per step',
    '⚙ Cấu hình luồng cố định…':
        '⚙ Configure the fixed flow…',
    "  agent · model · effort cho từng bước của workflow '{name}'":
        "  agent · model · effort for each step of workflow '{name}'",
    "agent · model · effort cho từng bước của workflow '{name}'":
        "agent · model · effort for each step of workflow '{name}'",
    '⚙ Luồng mặc định':
        '⚙ Default flow',
    'Luồng mặc định':
        'Default flow',
    '(mặc định của agent)':
        '(agent default)',
    '★ mặc định · ':
        '★ default · ',
    '🔀 Workflows':
        '🔀 Workflows',
    'Tuỳ chỉnh':
        'Custom',
    'Gõ mục tiêu (không kèm /goal) là chạy workflow này: mỗi bước một task, bước sau chờ bước trước. Chọn agent, model, effort cho từng bước — sửa tiêu đề/prompt hay thêm bước ở tab 🔀 Workflows.':
        'Typing a goal (without /goal) runs this workflow: one task per step, each step waits for the previous one. Pick the agent, model and effort for each step — edit titles/prompts or add steps in the 🔀 Workflows tab.',
    'Gõ mục tiêu (không kèm /goal) là chạy workflow này: mỗi bước một task, bước sau chờ bước trước. Chọn agent, model, effort cho từng bước — sửa tiêu đề/prompt hay thêm bước ở trang Workflows.':
        'Typing a goal (without /goal) runs this workflow: one task per step, each step waits for the previous one. Pick the agent, model and effort for each step — edit titles/prompts or add steps under Workflows.',
    'Bước':
        'Step',
    'Chạy khi gõ mục tiêu (luồng mặc định)':
        'Run when I type a goal (default flow)',
    'Cấu hình luồng cố định…':
        'Configure the fixed flow…',
    "Đã lưu luồng '{name}': {v}":
        "Saved flow '{name}': {v}",
    '{k}  (mẫu, chưa tạo)':
        '{k}  (template, not created yet)',
    "Workflow '{name}' vừa đổi số bước — mở lại popup":
        "Workflow '{name}' just changed its number of steps — reopen the popup",
    '★ Trưởng nhóm ({lead})':
        '★ Team lead ({lead})',
    "Bước {i}: không có agent '{name}'":
        "Step {i}: no agent '{name}'",
    "Bước {i}: effort '{effort}' không hợp lệ cho {agent} ({v})":
        "Step {i}: effort '{effort}' is not valid for {agent} ({v})",
    '  ★ mặc định':
        '  ★ default',
    'token: Claude Code & Codex đọc từ log phiên của CLI; agent khác ước tính ~4 ký tự/token (dấu ~). cost: ước tính theo bảng giá công khai — sửa bằng [prices."<model>"] trong config.toml.':
        'token: Claude Code & Codex are read from the CLI\'s session logs; other agents are estimated at ~4 characters/token (marked ~). cost: estimated from public price lists — override with [prices."<model>"] in config.toml.',
    'Xem thêm: /dash (biểu đồ theo ngày, theo model, lịch sử mục tiêu)':
        'More: /dash (daily chart, per model, goal history)',
    'thống kê: token, cost, lịch sử mục tiêu':
        'stats: tokens, cost, goal history',
    ' Token 14 ngày (cao nhất {v}/ngày)\n ':
        ' Tokens, last 14 days (peak {v}/day)\n ',
    'Mục tiêu #{gid}':
        'Goal #{gid}',
    '{n} lượt chạy · {v} · {tok} token ({real}/{n} số thật) · {cost}':
        '{n} runs · {v} · {tok} tokens ({real}/{n} measured) · {cost}',
    '30 ngày':
        '30 days',
    '   {n} lượt · {v}':
        '   {n} runs · {v}',
    'Lượt':
        'Runs',
    'Số thật':
        'Measured',
    'Kết quả: ':
        'Result: ',
    'Kết quả:':
        'Result:',
    '📊 Thống kê':
        '📊 Stats',
    '  · {f} lỗi · {r} hết hạn mức':
        '  · {f} failed · {r} rate-limited',
    '{f} lỗi · {r} hết hạn mức':
        '{f} failed · {r} rate-limited',
    'Chưa có mục tiêu nào. Gõ mục tiêu ở ô dưới để bắt đầu.':
        'No goals yet. Type a goal in the box below to start.',
    'Theo agent · model (30 ngày)':
        'By agent · model (30 days)',
    'Lịch sử mục tiêu  ·  Enter: tiếp tục mục tiêu (/continue)':
        'Goal history  ·  Enter: continue the goal (/continue)',
    '{n} lượt':
        '{n} runs',
    'Token theo ngày (14 ngày)':
        'Tokens per day (14 days)',
    'Theo agent (30 ngày)':
        'By agent (30 days)',
    'Theo model (30 ngày)':
        'By model (30 days)',
    'Lịch sử mục tiêu':
        'Goal history',
    'Tiếp tục mục tiêu':
        'Continue goal',
    'Chưa cài cloudflared — cài bằng `brew install cloudflared` (macOS) rồi chạy lại.':
        'cloudflared is not installed — install it with `brew install cloudflared` (macOS) and run again.',
    '--public-url phải là địa chỉ đầy đủ, vd https://ateam.ten-mien.com':
        '--public-url must be a full address, e.g. https://ateam.your-domain.com',
    'địa chỉ nghe, vd 0.0.0.0 để mở từ điện thoại trong LAN (bật token)':
        'address to listen on, e.g. 0.0.0.0 to open from a phone on the LAN (enables the token)',
    'mở Cloudflare Tunnel (cloudflared, https, không cần tài khoản) + in mã QR':
        'open a Cloudflare Tunnel (cloudflared, https, no account needed) + print a QR code',
    'địa chỉ công khai khi bạn tự chạy named tunnel / domain riêng (bật token)':
        'public address when you run your own named tunnel / domain (enables the token)',
    'chỉ cho xem, không thao tác':
        'view only, no actions',
    'tạo token mới (thiết bị cũ phải quét lại)':
        'create a new token (old devices must scan again)',
    '--tui chỉ chạy trên máy này — bỏ --host/--tunnel/--public-url, hoặc dùng `ateam web` (giao diện web) để mở từ điện thoại.':
        '--tui only runs on this machine — drop --host/--tunnel/--public-url, or use `ateam web` (the web UI) to open it from a phone.',
    '🔒 Chế độ từ xa: cần token (lưu ở .ateam/web_token; --new-token để đổi)':
        '🔒 Remote mode: a token is required (stored in .ateam/web_token; --new-token to change it)',
    '⚠ Qua http trong LAN, token đi dạng rõ — ngoài mạng nhà nên dùng --tunnel (https).':
        '⚠ Over http on the LAN the token travels in clear text — outside your home network use --tunnel (https).',
    '⏳ Đang mở Cloudflare Tunnel… URL công khai + mã QR sẽ in ở dưới.':
        '⏳ Opening Cloudflare Tunnel… the public URL + QR code will be printed below.',
    ' · chỉ xem (--readonly)':
        ' · view only (--readonly)',
    ' · token có toàn quyền như trên máy này':
        ' · the token has full control, same as on this machine',
    '❓ Agent hỏi bạn':
        '❓ An agent asks you',
    'Đã trả lời — {agent} làm tiếp task #{tid}':
        'Answered — {agent} continues task #{tid}',
    'Task #{tid} không có câu hỏi nào đang chờ':
        'Task #{tid} has no pending question',
    '💬 #{tid} trả lời {agent}: {a}':
        '💬 #{tid} answer to {agent}: {a}',
    ' · tiếp tục phiên {s}':
        ' · resuming session {s}',
    '↻ không tiếp tục được phiên cũ — chạy lại với đầy đủ ngữ cảnh':
        '↻ could not resume the previous session — running again with full context',
    '❓ #{tid} {agent} hỏi: {q} — tự trả lời: {a}':
        '❓ #{tid} {agent} asks: {q} — auto-answered: {a}',
    '❓ #{tid} {agent} hỏi bạn: {q}':
        '❓ #{tid} {agent} asks you: {q}',
    '❓ {agent} hỏi · task #{tid} ':
        '❓ {agent} asks · task #{tid} ',
    '❓ Agent hỏi giữa task':
        '❓ Agent question during a task',
    ' · còn {others} task khác đang hỏi':
        ' · {others} more tasks are asking',
    '⏭ Để agent tự quyết':
        '⏭ Let the agent decide',
    '📜 Xem task':
        '📜 View task',
    '✗ Huỷ task':
        '✗ Cancel task',
    'Điện thoại':
        'Phone',
    'Mở trên điện thoại':
        'Open on your phone',
    'Quét mã bằng camera điện thoại. URL chứa token toàn quyền — đừng gửi cho người khác.':
        "Scan the code with your phone camera. The URL contains a full-access token — don't share it.",
    'Server đang ở chế độ chỉ xem (--readonly).':
        'The server is in view-only mode (--readonly).',
    'Server đang chỉ nghe trên máy này. Để mở từ điện thoại, chạy lại với:':
        'The server only listens on this machine. To open it from a phone, restart with:',
    'cùng Wi-Fi (http, token đi dạng rõ trong LAN)':
        'same Wi-Fi (http, the token travels in clear text on the LAN)',
    'mọi nơi qua Cloudflare Tunnel (https, cần cài cloudflared)':
        'from anywhere via Cloudflare Tunnel (https, needs cloudflared)',
    'Chép':
        'Copy',
    'Đã chép':
        'Copied',
    '👁 Chế độ chỉ xem — thao tác bị tắt':
        '👁 View-only mode — actions are disabled',
    'Agent hỏi giữa task':
        'Agent question during a task',
    '{agent} hỏi · task #{id}':
        '{agent} asks · task #{id}',
    'Để agent tự quyết':
        'Let the agent decide',
    'Xem task':
        'View task',
    'còn {n} task khác đang hỏi':
        '{n} more tasks are asking',
    'Trả lời câu hỏi của agent (Enter) · gõ số để chọn phương án':
        "Answer the agent's question (Enter) · type a number to pick an option",
    '🌐 Cloudflare Tunnel: {url}':
        '🌐 Cloudflare Tunnel: {url}',
    '✗ cloudflared đã dừng (mã {rc})':
        '✗ cloudflared stopped (code {rc})',
    'Chế độ chỉ xem (--readonly) — không làm được thao tác này':
        'View-only mode (--readonly) — this action is not allowed',
    '✗ Không chạy được cloudflared: {e}':
        '✗ Could not run cloudflared: {e}',
    'Máy này':
        'This machine',
    'Quét mã QR trong terminal đang chạy `ateam web`, hoặc dán token (file .ateam/web_token) vào đây.':
        'Scan the QR code in the terminal running `ateam web`, or paste the token (file .ateam/web_token) here.',
    'Vào':
        'Sign in',
    'Token không đúng':
        'Wrong token',
    'Cloudflare Tunnel':
        'Cloudflare Tunnel',
    'Địa chỉ công khai':
        'Public address',
    'Sai token quá nhiều lần — thử lại sau ít phút':
        'Too many wrong tokens — try again in a few minutes',
    'Mạng LAN':
        'LAN',
    'Trưởng nhóm không gợi ý được bước nào — thử mô tả rõ hơn':
        'The lead suggested no steps — try a clearer description',
    'Mô tả quy trình bạn muốn trước (vd: thiết kế → code → test → review)':
        'Describe the process you want first (e.g. design → code → test → review)',
    'Gợi ý workflow':
        'Suggest workflow',
    '{agent} không trả về workflow (xem .ateam/logs/lead.log)':
        '{agent} returned no workflow (see .ateam/logs/lead.log)',
    '✨ Gợi ý':
        '✨ Suggest',
    'Gợi ý':
        'Suggest',
    'mô tả quy trình, vd: thiết kế → code → test → review':
        'describe the process, e.g. design → code → test → review',
    'trưởng nhóm điền các bước':
        'the lead fills in the steps',
    '✨ {lead} đang thiết kế workflow…':
        '✨ {lead} is designing the workflow…',
    '✨ Đã điền {n} bước — xem lại rồi Ctrl+S để lưu':
        '✨ Filled {n} steps — review, then Ctrl+S to save',
    '✨ Đã điền {n} bước — xem lại rồi bấm Lưu':
        '✨ Filled {n} steps — review, then press Save',
    '⚠ Lỗi nội bộ: {e!r}':
        '⚠ Internal error: {e!r}',
    'Lỗi khi lập kế hoạch: {e!r}':
        'Error while planning: {e!r}',
    '✗ Lập kế hoạch mục tiêu #{gid} lỗi: {e!r}':
        '✗ Planning goal #{gid} failed: {e!r}',
    'Lỗi khi review: {e!r}':
        'Error during review: {e!r}',
    '✗ Review mục tiêu #{gid} lỗi: {e!r}':
        '✗ Review of goal #{gid} failed: {e!r}',
    'Không commit được thay đổi trong worktree {path} (giữ nguyên để bạn lấy lại): {v}':
        'Could not commit the changes in worktree {path} (kept as is so you can recover them): {v}',
    '⚠ #{id}: không mở lại được nhánh {branch} ({v}) — làm lại từ HEAD':
        '⚠ #{id}: could not reopen branch {branch} ({v}) — starting over from HEAD',
    'Thư mục chính đang merge dở — hoàn tất hoặc huỷ merge đó rồi /merge {id}':
        'The main folder has a merge in progress — finish or abort it, then /merge {id}',
    "Không có agent '{agent}' — agent: {v}":
        "No agent '{agent}' — agents: {v}",
    'Gõ nội dung tin nhắn cho {agent}':
        'Type a message for {agent}',
    '{agent} đang trả lời tin trước — đợi xong (hoặc /cancel {tid})':
        '{agent} is still answering the previous message — wait for it (or /cancel {tid})',
    '{agent} đang hết hạn mức (đến {v})':
        '{agent} is out of quota (until {v})',
    '<agent> [tin nhắn]':
        '<agent> [message]',
    'chat trực tiếp với 1 agent như trong terminal (giữ phiên, ô 💬 ở tab Agents)':
        'chat directly with one agent like in its terminal (keeps the session, 💬 box on the Agents tab)',
    'Không biết cách mở {agent} ở chế độ tương tác (agent tuỳ chỉnh) — tự mở trong terminal khác':
        "Don't know how to open {agent} interactively (custom agent) — open it in another terminal yourself",
    '💬 Nhắn {agent}… (Enter gửi · /new: cuộc mới · /term: mở CLI thật · Esc: về danh sách)':
        '💬 Message {agent}… (Enter sends · /new: new chat · /term: open the real CLI · Esc: back to the list)',
    '[agent]':
        '[agent]',
    'phóng to 1 agent cả màn hình để chat riêng (F7; gõ lại / Esc để thu)':
        'zoom one agent to full screen for a private chat (F7; again / Esc to restore)',
    'Phóng to agent':
        'Zoom agent',
    'Dùng: /focus [agent]  — agent: {v}':
        'Usage: /focus [agent]  — agents: {v}',
    '⛶ Phóng to / thu lại (Esc)':
        '⛶ Zoom / restore (Esc)',
    '\n── {agent}: {cmd} — thoát CLI để quay lại ateam ──\n':
        '\n── {agent}: {cmd} — exit the CLI to return to ateam ──\n',
    'Giao diện này không nhường terminal được — chạy trong terminal khác (đã chép): {cmd}':
        "This interface can't hand over the terminal — run it in another terminal (copied): {cmd}",
    'Không chạy được {cmd}: {e}':
        'Could not run {cmd}: {e}',
    '› bạn: {text}':
        '› you: {text}',
    '── cuộc trò chuyện mới ──':
        '── new conversation ──',
    'Dùng: /chat <agent> <tin nhắn>  — agent: {v}':
        'Usage: /chat <agent> <message>  — agents: {v}',
    'Gửi':
        'Send',
    '💬 Nhắn {agent}… (Enter gửi · /new: cuộc mới · /term: CLI thật · /focus: phóng to)':
        '💬 Message {agent}… (Enter sends · /new: new chat · /term: real CLI · /focus: zoom)',
    'Mở CLI thật của agent (tiếp tục phiên chat) trong terminal':
        "Open the agent's real CLI (continuing the chat session) in a terminal",
    'CLI đã thoát (mã {rc}) — đóng cửa sổ này':
        'CLI exited (code {rc}) — close this window',
    "⚙ {agent}: model {model} không có effort '{want}' → dùng {got}":
        "⚙ {agent}: model {model} has no '{want}' effort → using {got}",
    'model này không chỉnh effort (CLI tự chọn)':
        'this model has no effort setting (the CLI decides)',
    'Mở nhanh file…':
        'Quick open file…',
    'Tới symbol trong file… (@)':
        'Go to symbol in file… (@)',
    'Tới dòng… (:)':
        'Go to line… (:)',
    'Tìm trong file… (/)':
        'Find in file… (/)',
    'Tìm & thay trong dự án':
        'Find & replace in project',
    'Hỏi agent về file / đoạn đang chọn…':
        'Ask an agent about the file / selection…',
    'Giao task cho agent với file / đoạn đang chọn…':
        'Give an agent a task on the file / selection…',
    'Lưu file':
        'Save file',
    'Lưu tất cả':
        'Save all',
    'Đóng file':
        'Close file',
    'File kế tiếp':
        'Next file',
    'File mới…':
        'New file…',
    'Đổi tên / chuyển file…':
        'Rename / move file…',
    'Xoá file (vào Thùng rác)':
        'Delete file (to Trash)',
    'Chép đường dẫn (kèm dòng)':
        'Copy path (with line)',
    'Xem thay đổi git của file':
        "Show the file's git changes",
    'Mở trong VS Code':
        'Open in VS Code',
    'Bật/tắt xuống dòng mềm':
        'Toggle word wrap',
    'Bật/tắt số dòng':
        'Toggle line numbers',
    'Bật/tắt phím vim':
        'Toggle vim keys',
    'Ẩn/hiện danh sách file':
        'Show/hide file list',
    'Đường dẫn không hợp lệ: {v}':
        'Invalid path: {v}',
    'Đã có {v}':
        '{v} already exists',
    'Không còn file {v}':
        '{v} no longer exists',
    '{v} là thư mục — chỉ xoá file':
        '{v} is a folder — only files can be deleted',
    'Không đưa được vào Thùng rác: {e}':
        'Could not move to Trash: {e}',
    'Mở nhanh file':
        'Quick open',
    'Symbol':
        'Symbol',
    'Đã đổi {v} → {v2}':
        'Renamed {v} → {v2}',
    'Đã đưa {v} vào Thùng rác':
        'Moved {v} to Trash',
    '(dòng {a})':
        '(line {a})',
    '(dòng {a}–{b})':
        '(lines {a}–{b})',
    '{v}: không có thay đổi so với git':
        '{v}: no changes compared to git',
    'Lưu file trước khi đổi tên':
        'Save the file before renaming',
    'Giao task cho {agent} về {v}':
        'Task for {agent} on {v}',
    'Hỏi {agent} về {v}':
        'Ask {agent} about {v}',
    'Chọn agent':
        'Choose an agent',
    '↑↓ chọn · Enter mở · > lệnh · @ symbol · : dòng · / tìm trong file · Esc đóng':
        '↑↓ select · Enter open · > commands · @ symbol · : line · / find in file · Esc close',
    'Chưa mở file nào — gõ tên file để mở':
        'No file open — type a file name to open one',
    'Gõ số dòng (1–{n})':
        'Type a line number (1–{n})',
    'Gõ tên file · > lệnh · @ symbol · :dòng · /tìm trong file':
        'Type a file name · > commands · @ symbol · :line · /find in file',
    'Không có file nào khớp — > để xem lệnh':
        'No matching file — > for commands',
    'Enter xong · Esc huỷ':
        'Enter to confirm · Esc to cancel',
    'Tên file… · > lệnh · @ symbol · :dòng · /tìm trong file':
        'File name… · > commands · @ symbol · :line · /find in file',
    'Không có lệnh nào khớp':
        'No matching command',
    'Không thấy symbol (hàm, class, heading) nào':
        'No symbols (functions, classes, headings) found',
    'Gõ chữ cần tìm trong file':
        'Type text to find in the file',
    'Không thấy "{v}" trong file':
        '"{v}" not found in the file',
    'Mở gần đây':
        'Recently opened',
    'Đã giao cho {agent}: {v}':
        'Assigned to {agent}: {v}',
    'Đã hỏi {agent} — xem trả lời ở tab 🤖 Agents':
        'Asked {agent} — see the reply on the 🤖 Agents tab',
    'vd: giải thích đoạn này / viết test cho hàm này':
        'e.g. explain this part / write tests for this function',
    'Tới dòng {v}':
        'Go to line {v}',
    'Xuống dòng mềm: bật':
        'Word wrap: on',
    'Xuống dòng mềm: tắt':
        'Word wrap: off',
    'Đã chép {v}':
        'Copied {v}',
    '📄 File mới':
        '📄 New file',
    'đường/dẫn/file.ext':
        'path/to/file.ext',
    '✎ Đổi tên / chuyển {v}':
        '✎ Rename / move {v}',
    'Xoá file':
        'Delete file',
    'Đưa {v} vào Thùng rác?':
        'Move {v} to Trash?',
    'Chỉ mở VS Code được khi dùng ateam web trên chính máy này':
        'VS Code can only be opened when using ateam web on this same machine',
    '↪ Mở dự án {v}':
        '↪ Opening project {v}',
    'Mở folder / dự án khác…':
        'Open another folder / project…',
    'Gõ đường dẫn thư mục, vd ~/code/app':
        'Type a folder path, e.g. ~/code/app',
    'Không có thư mục {v}':
        'No such folder: {v}',
    '{v} không phải thư mục':
        '{v} is not a folder',
    'Đang mở dự án này rồi':
        'This project is already open',
    'Không ghi được vào {v} (ateam cần tạo .ateam/ ở đó)':
        "Can't write to {v} (ateam needs to create .ateam/ there)",
    'Dự án {v} đang mở ở một phiên ateam khác':
        'Project {v} is open in another ateam session',
    '[thư mục]':
        '[folder]',
    'mở folder / dự án khác (dự án gần đây, gõ đường dẫn — Tab gợi ý)':
        'open another folder / project (recent projects, type a path — Tab completes)',
    'Tên dự án gần đây, hoặc đường dẫn: ~/code/app, ../app-khac':
        "A recent project's name, or a path: ~/code/app, ../other-app",
    '↑↓ chọn · Tab đi vào thư mục · Enter mở · Esc đóng':
        '↑↓ select · Tab goes into the folder · Enter opens · Esc closes',
    'Dự án gần đây':
        'Recent projects',
    '(đang mở)':
        '(open now)',
    'Không có thư mục nào khớp':
        'No matching folder',
    'Trong trình duyệt (ateam web --tui) không đổi được dự án — chạy lại: ateam web --tui -C {v}':
        "Can't switch projects in the browser (ateam web --tui) — restart with: ateam web --tui -C {v}",
    'Đang có agent chạy':
        'Agents are running',
    '{n} lượt agent đang chạy sẽ bị dừng (task dở thành lỗi — quay lại dự án này thì /retry).\nMở {v}?':
        '{n} running agent turn(s) will be stopped (unfinished tasks become failed — /retry them when you come back to this project).\nOpen {v}?',
    'Dừng & mở':
        'Stop & open',
    'Mở folder / dự án khác':
        'Open another folder / project',
    'Tab 📝 Code còn file chưa lưu: {v}\nBỏ các thay đổi và mở dự án khác?':
        'The 📝 Code tab has unsaved files: {v}\nDiscard the changes and open another project?',
    'Bỏ thay đổi & mở':
        'Discard & open',
    '↪ Đang mở {v}…':
        '↪ Opening {v}…',
    'Đang mở web từ xa — chỉ đổi được dự án khi chạy trên máy này':
        'The web UI is open remotely — projects can only be switched when running on this machine',
    '📏 Đã thêm rule — mọi agent nhận từ lượt sau':
        '📏 Rule added — every agent gets it from the next turn',
    '📏 Rule của dự án':
        '📏 Project rules',
    '✎ Sửa rule':
        '✎ Edit rule',
    '[rule mới]':
        '[new rule]',
    '{v} tự đọc':
        'read by {v}',
    '+ Thêm rule (a)':
        '+ Add rule (a)',
    '+ Thêm rule':
        '+ Add rule',
    'a thêm · Enter sửa · Space bật/tắt · d xoá · Shift+↑↓ đổi thứ tự · Esc đóng':
        'a add · Enter edit · Space on/off · d delete · Shift+↑↓ reorder · Esc close',
    'Agent: {v}':
        'Agent: {v}',
    'Áp dụng cho (không chọn gì = mọi agent)':
        'Applies to (nothing selected = every agent)',
    'Bật':
        'On',
    'Bật/tắt':
        'On/off',
    'Chưa có rule nào — bấm a để thêm':
        'No rules yet — press a to add one',
    'Chưa có rule nào':
        'No rules yet',
    'File rule có sẵn trong repo — CLI tự đọc, ateam không gửi kèm (Enter mở ở tab Code)':
        "Rule files already in the repo — the CLIs read them themselves, ateam doesn't send them (Enter opens in the Code tab)",
    'File rule có sẵn trong repo — CLI tự đọc, ateam không gửi kèm':
        "Rule files already in the repo — the CLIs read them themselves, ateam doesn't send them",
    'Không còn rule này':
        'This rule no longer exists',
    'Không hiểu thao tác {v}':
        'Unknown action {v}',
    'Mở':
        'Open',
    'Mọi agent phải tuân theo: ateam gửi kèm rule ở đầu mỗi prompt (task, chat, lập kế hoạch, review, commit message). Lưu riêng máy này: {v}':
        'Every agent must follow these: ateam puts them at the top of every prompt (tasks, chat, planning, review, commit messages). Stored on this machine only: {v}',
    'mọi agent':
        'every agent',
    'Nội dung — agent nhận nguyên văn':
        'Content — agents get it verbatim',
    'Rule chưa có nội dung':
        'The rule has no content',
    'rule của dự án mà mọi agent phải tuân theo; kèm nội dung thì thêm luôn':
        'project rules every agent must follow; with text, adds it right away',
    'Rule dài quá {n} ký tự — tách thành nhiều rule':
        'Rule is longer than {n} characters — split it into several rules',
    'Thêm':
        'Add',
    'Tiêu đề (không bắt buộc)':
        'Title (optional)',
    'Tối đa {n} rule':
        'At most {n} rules',
    'Vai trò: {v}':
        'Role: {v}',
    'vd: Commit message tiếng Việt':
        'e.g. Commit messages in Vietnamese',
    'Xoá rule "{v}"?':
        'Delete rule "{v}"?',
    'Xoá rule':
        'Delete rule',
    'Lưu':
        'Save',
    '＋ File mới':
        '＋ New file',
    '❓ Trưởng nhóm hỏi bạn':
        '❓ The lead has a question',
    '❓ Trưởng nhóm cần làm rõ trước khi lập kế hoạch #{gid}: {question}':
        '❓ The lead needs a clarification before planning #{gid}: {question}',
    # giải quyết xung đột git
    'hiện tại':
        'current',
    'bên đến':
        'incoming',
    'Đã lấy bản {who} cho {v} file':
        'Took the {who} version for {v} file(s)',
    'Hết xung đột — bấm Tiếp tục {state} để hoàn tất':
        'No conflicts left — press Continue {state} to finish',
    'Không đọc được {path}':
        'Cannot read {path}',
    'Còn {v} khối xung đột trong {path}':
        '{v} conflict block(s) left in {path}',
    '{path} vẫn còn dấu xung đột <<<<<<< — sửa hết rồi đánh dấu xong':
        '{path} still has <<<<<<< conflict markers — fix them all, then mark as resolved',
    'Đã giải quyết {v} — còn {n} file xung đột':
        'Resolved {v} — {n} conflicted file(s) left',
    'Còn {v} file xung đột — giải quyết hết trước':
        '{v} conflicted file(s) left — resolve them first',
    'Đã hoàn tất {state}':
        'Finished the {state}',
    '{state} dừng ở commit tiếp theo: {n} file xung đột':
        '{state} stopped at the next commit: {n} conflicted file(s)',
    'File đã đổi — mở lại để xem các khối xung đột còn lại':
        'The file changed — reopen it to see the remaining conflict blocks',
    'Đã tiếp tục {state}':
        'Continued the {state}',
    '🤖 {agent} đang giải quyết xung đột {v} file — xem ở tab Agents; xong thì xem lại rồi Đánh dấu đã xong':
        '🤖 {agent} is resolving conflicts in {v} file(s) — follow it in the Agents tab; when done, review and Mark as resolved',
    'Không có file nào đang xung đột':
        'No conflicted files',
    '▶ Tiếp tục {state}':
        '▶ Continue {state}',
    'Giải quyết xung đột':
        'Resolve conflicts',
    'Nhờ agent giải quyết xung đột':
        'Ask an agent to resolve conflicts',
    'Giữ hiện tại':
        'Keep current',
    'Lấy bên đến':
        'Take incoming',
    'Giữ cả hai':
        'Keep both',
    'Cả file: hiện tại':
        'Whole file: current',
    'Cả file: bên đến':
        'Whole file: incoming',
    'Đánh dấu đã xong':
        'Mark as resolved',
    'Sửa trong Code':
        'Edit in Code',
    'Nhờ agent':
        'Ask agent',
    'Đã giải quyết xong {path}':
        'Resolved {path}',
    'Đang rebase: "hiện tại" là nhánh đích, "bên đến" là commit của bạn đang được áp lại.':
        'Rebasing: "current" is the target branch, "incoming" is your commit being replayed.',
    'Phía hiện tại đã xoá file này, bên đến sửa nó — O xoá, T giữ bản bên đến.':
        'The current side deleted this file and the incoming side changed it — O deletes, T keeps the incoming version.',
    '⇄ Giải quyết xung đột · {path}':
        '⇄ Resolve conflicts · {path}',
    'Bên đến đã xoá file này, phía hiện tại sửa nó — O giữ bản hiện tại, T xoá.':
        'The incoming side deleted this file and the current side changed it — O keeps the current version, T deletes.',
    'Xung đột {i}/{n} · dòng {line}':
        'Conflict {i}/{n} · line {line}',
    'Hiện tại':
        'Current',
    'Bản gốc':
        'Base',
    'Bên đến':
        'Incoming',
    'o giữ hiện tại · t lấy bên đến · b giữ cả hai (khối đang chọn) · O/T cả file · e sửa trong Code · g nhờ agent · m đánh dấu đã xong · Esc đóng':
        'o keep current · t take incoming · b keep both (selected block) · O/T whole file · e edit in Code · g ask agent · m mark as resolved · Esc close',
    'File nhị phân hoặc không phải UTF-8 — chỉ chọn được nguyên bản một phía (O/T).':
        'Binary or non-UTF-8 file — you can only take one side as a whole (O/T).',
    '(trống)':
        '(empty)',
    'Không còn dấu xung đột trong file — xem lại rồi m (đánh dấu đã xong).':
        'No conflict markers left in the file — review it, then m (mark as resolved).',
    '▶ Tiếp tục':
        '▶ Continue',
    '⇄ Giải quyết':
        '⇄ Resolve',
    '🤖 Nhờ agent':
        '🤖 Ask agent',
    'Tiếp tục {v}':
        'Continue {v}',
    'Nhờ agent giải quyết tất cả':
        'Ask an agent to resolve all',
    'Không còn dấu xung đột trong file — xem lại rồi Đánh dấu đã xong.':
        'No conflict markers left in the file — review it, then Mark as resolved.',
    'Phía hiện tại đã xoá file này, bên đến sửa nó.':
        'The current side deleted this file and the incoming side changed it.',
    'Bên đến đã xoá file này, phía hiện tại sửa nó.':
        'The incoming side deleted this file and the current side changed it.',
    'File nhị phân hoặc không phải UTF-8 — chỉ chọn được nguyên bản một phía.':
        'Binary or non-UTF-8 file — you can only take one side as a whole.',
    'Khối đang chọn: o giữ hiện tại · t lấy bên đến · b giữ cả hai  —  cả file: O hiện tại · T bên đến  —  e sửa · g nhờ agent · m đã xong · Esc đóng':
        'Selected block: o keep current · t take incoming · b keep both  —  whole file: O current · T incoming  —  e edit · g ask agent · m resolved · Esc close',
    '✎ Sửa trong Code':
        '✎ Edit in Code',
    '✓ Đánh dấu đã xong':
        '✓ Mark as resolved',
    'Lọc nhánh theo tên… (Enter: chuyển sang nhánh khớp đầu tiên)':
        'Filter branches by name… (Enter: switch to the first match)',
    'Không có nhánh nào khớp':
        'No matching branches',
    'Nhánh local':
        'Local branches',
    'Nhánh remote':
        'Remote branches',
    'Lọc nhánh theo tên… (Enter: chuyển sang nhánh khớp đầu tiên · ↓: xuống danh sách)':
        'Filter branches by name… (Enter: switch to the first match · ↓: go to the list)',
    'Đã bỏ mọi thay đổi ({v} file)':
        'Discarded all changes ({v} files)',
    'Đang {v} dở — dùng ✗ Huỷ merge (hoặc giải quyết xong) trước khi bỏ mọi thay đổi':
        'A {v} is in progress — use ✗ Abort merge (or finish resolving) before discarding all changes',
    'Chưa có commit nào — không có bản nào để quay về':
        'No commits yet — there is nothing to go back to',
    'Không có thay đổi nào để bỏ':
        'No changes to discard',
    'Bỏ tất cả thay đổi':
        'Discard all changes',
    'Luồng':
        'Flow',
    '  ⚙ Cấu hình luồng… (agent · model · effort từng bước, workflow mẫu)':
        '  ⚙ Configure flow… (agent · model · effort per step, workflow templates)',
    '☆ Bỏ mặc định':
        '☆ Unset default',
    '★ Mặc định':
        '★ Default',
    '↺ Bỏ tất cả thay đổi':
        '↺ Discard all changes',
    'Bỏ MỌI thay đổi ({s} file đã stage, {w} file chưa stage) và XOÁ {u} file chưa theo dõi? Thư mục về đúng commit cuối — không thể hoàn tác.':
        'Discard ALL changes ({s} staged files, {w} unstaged files) and DELETE {u} untracked files? The folder goes back to the last commit — this cannot be undone.',
    'Bỏ tất cả':
        'Discard all',
    'Gõ mục tiêu sẽ chạy theo…':
        'Typing a goal runs with…',
    'Enter: chọn · Esc: đóng · /goal luôn để trưởng nhóm lập kế hoạch · /flow <tên> chạy workflow khác một lần':
        'Enter: pick · Esc: close · /goal always has the lead plan · /flow <name> runs another workflow once',
    '↺ Bỏ tất cả':
        '↺ Discard all',
    '★ Trưởng nhóm lập kế hoạch':
        '★ Lead makes a plan',
    'chia việc theo mục tiêu (mặc định)':
        'splits the goal into tasks (default)',
    'chưa có workflow — tạo ở 🔀 Workflows':
        'no workflows yet — create one in 🔀 Workflows',
    'Gõ mục tiêu → trưởng nhóm lập kế hoạch hay chạy một workflow (đổi luồng mặc định)':
        'Typing a goal → the lead plans it, or a workflow runs it (change the default flow)',
    '★ Đặt mặc định':
        '★ Make default',
    "Gõ mục tiêu → chạy workflow '{name}' (/goal: trưởng nhóm lập kế hoạch)":
        "Typing a goal → runs workflow '{name}' (/goal: the lead plans)",
    'Gõ mục tiêu → trưởng nhóm lập kế hoạch':
        'Typing a goal → the lead plans it',
    "Xem":
        "View",
    "Thu gọn thanh bên":
        "Collapse sidebar",
    "Mở rộng thanh bên":
        "Expand sidebar",
    "Không có trưởng nhóm nào chạy được lúc này (hết hạn mức hoặc chưa cài — xem log hệ thống) — bấm ↻ Hỏi tiếp để thử lại":
        "No lead can run right now (rate-limited or not installed — see the system log) — press ↻ Ask again to retry",
    "Lỗi khi hỏi đáp: {e!r}":
        "Error during Q&A: {e!r}",
    # Lưới terminal (🔲 Lưới)
    'Một cột':
        'Single column',
    'Hai cột':
        'Two columns',
    'Lưới đều':
        'Even grid',
    'Lead + đội':
        'Lead + team',
    'Một hàng':
        'Single row',
    'Không có ô này':
        'No such cell',
    'mở tab 🔲 Lưới: mỗi ô là CLI thật của một agent; kèm agent thì thêm ô':
        "open the 🔲 Grid tab: each cell is an agent's real CLI; with an agent, add a cell",
    'Sắp xếp lưới':
        'Arrange grid',
    '🔲 Lưới':
        '🔲 Grid',
    'Sắp xếp: ←↑→↓ chọn ô · Shift+←↑→↓ đổi chỗ · +/- rộng · [/] cao · a thêm · x đóng · z phóng to · r mở lại · 1-5 bố cục · b gửi tất cả · Esc xong':
        'Arrange: ←↑→↓ select cell · Shift+←↑→↓ move · +/- width · [/] height · a add · x close · z zoom · r restart · 1-5 layout · b broadcast · Esc done',
    ' CLI đã thoát (mã {rc}) — Enter: mở lại ':
        ' CLI exited (code {rc}) — Enter: restart ',
    ' CLI chưa chạy — Enter: mở (tiếp tục phiên) ':
        ' CLI not running — Enter: open (resume session) ',
    'Thả lên ô khác: giữa = đổi chỗ, sát cạnh = đặt bên đó · thả tại chỗ = huỷ':
        'Drop on another cell: center = swap, edge = place on that side · drop in place = cancel',
    '  ⇉ gửi tất cả':
        '  ⇉ broadcast',
    '⇉ Gửi tất cả: bật':
        '⇉ Broadcast: on',
    '⇉ Gửi tất cả':
        '⇉ Broadcast',
    'CLI đang chạy — đóng nó (hoặc ✕) trước khi mở lại':
        'CLI is running — close it (or ✕) before restarting',
    ' ↑ lịch sử ({n} dòng) — gõ phím để về cuối ':
        ' ↑ history ({n} lines) — press a key to go to the bottom ',
    '● đang chạy':
        '● running',
    '■ đã thoát':
        '■ exited',
    '○ chưa mở':
        '○ not open',
    '＋ Thêm agent':
        '＋ Add agent',
    '⚙ Sắp xếp (F10)':
        '⚙ Arrange (F10)',
    'Chưa có agent nào trong lưới.\n\nBấm ＋ Thêm agent hoặc chọn nhanh một agent dưới đây — mỗi ô là CLI thật, gõ trực tiếp được.':
        'No agents in the grid yet.\n\nPress ＋ Add agent or pick one below — each cell is a real CLI you can type into directly.',
    'Đóng terminal':
        'Close terminal',
    'Dừng CLI {agent} trong ô này và bỏ ô khỏi lưới?':
        'Stop the {agent} CLI in this cell and remove the cell from the grid?',
    'Thêm agent vào lưới · mở CLI thật trong một ô mới':
        'Add agent to grid · open the real CLI in a new cell',
    'Tiếp tục phiên gần nhất của agent (--resume)':
        "Resume the agent's latest session (--resume)",
    'mặc định ({m})':
        'default ({m})',
    'Bấm vào ô để gõ thẳng vào CLI · phím Ctrl thuộc về CLI (Ctrl+Q vẫn thoát ateam) · F10: sắp xếp · kéo tiêu đề ô để đổi chỗ':
        'Click a cell to type straight into the CLI · Ctrl keys go to the CLI (Ctrl+Q still quits ateam) · F10: arrange · drag a cell title to move it',
    '▶ Mở terminal':
        '▶ Open terminal',
    '  ✗ chưa cài':
        '  ✗ not installed',
    'CLI tự chọn':
        'CLI decides',
    'Lưới':
        'Grid',
    'Bố cục':
        'Layout',
    'Gõ tới':
        'Type to',
    '◉ Ô đang chọn':
        '◉ Selected cell',
    '⇉ Tất cả {n} ô':
        '⇉ All {n} cells',
    '⛶ Toàn màn hình':
        '⛶ Full screen',
    'Phóng to / thu lại ô':
        'Zoom / unzoom cell',
    'Đóng terminal (dừng CLI)':
        'Close terminal (stop CLI)',
    'Mở lại CLI (tiếp tục phiên)':
        'Restart CLI (resume session)',
    'Thêm agent vào ô này':
        'Add agent next to this cell',
    'Mỗi ô là CLI thật trong terminal · kéo tiêu đề ô để đổi chỗ, kéo khe để đổi kích thước':
        'Each cell is a real CLI in a terminal · drag a cell title to move it, drag a gutter to resize',
    'Kéo ⠿ tiêu đề ô để di chuyển · kéo khe giữa các ô để đổi kích thước · đúp-click khe: chia đều':
        "Drag a cell's ⠿ title to move it · drag the gutter between cells to resize · double-click a gutter: equalize",
    'Trái':
        'Left',
    'Phải':
        'Right',
    'Trên':
        'Top',
    'Dưới':
        'Bottom',
    '⇄ Đổi chỗ':
        '⇄ Swap',
    'đã thoát ({rc})':
        'exited ({rc})',
    'chưa mở':
        'not open',
    'CLI chưa chạy — bấm để mở (tiếp tục phiên gần nhất)':
        'CLI not running — click to open (resume latest session)',
    'CLI đã thoát (mã {rc}) — bấm ⟲ để mở lại':
        'CLI exited (code {rc}) — press ⟲ to restart',
    'CLI':
        'CLI',
    'Model & effort':
        'Model & effort',
    'Phiên':
        'Session',
    'Đặt ở đâu':
        'Placement',
    'Phiên mới':
        'New session',
    'Tiếp tục phiên gần nhất':
        'Resume latest session',
    '--resume phiên chat/task gần nhất của agent':
        "--resume the agent's latest chat/task session",
    'CLI mở cuộc trò chuyện mới':
        'The CLI starts a new conversation',
    'Theo bố cục':
        'Follow layout',
    'Chia ô chọn: phải':
        'Split selected cell: right',
    'Chia ô chọn: dưới':
        'Split selected cell: below',
    'agent tuỳ chỉnh: không mở được ở chế độ tương tác':
        'custom agent: cannot be opened interactively',
    '✓ đã cài':
        '✓ installed',
    'Nhận phím khi gửi tất cả':
        'Receive keys when broadcasting',
    '◫ Chia dọc · thêm agent bên phải':
        '◫ Split vertically · add agent on the right',
    '⊟ Chia ngang · thêm agent bên dưới':
        '⊟ Split horizontally · add agent below',
    # To-do (tag, hạn, ưu tiên), Quản lý tag, Ghi chú
    'hôm nay':
        'today',
    'mai':
        'tomorrow',
    'quá {n} ngày':
        '{n}d overdue',
    'T2 T3 T4 T5 T6 T7 CN':
        'Mon Tue Wed Thu Fri Sat Sun',
    'mở tab To-do (lưu ngoài repo); kèm nội dung thì thêm việc · hiểu #tag !cao @mai':
        'open the To-do tab (stored outside the repo); with text, add a to-do · understands #tag !high @tomorrow',
    '[tiêu đề]':
        '[title]',
    'mở tab 🗒 Ghi chú (lưu ngoài repo); kèm tiêu đề thì tạo ghi chú mới':
        'open the 🗒 Notes tab (stored outside the repo); with a title, create a new note',
    'quản lý tag dùng chung cho To-do và Ghi chú':
        'manage the tags shared by To-do and Notes',
    '🗒 Ghi chú':
        '🗒 Notes',
    'Thêm việc…  #tag  !cao  @mai 17:00  — Enter':
        'Add a to-do…  #tag  !high  @tomorrow 17:00  — Enter',
    'Không':
        'None',
    'Thấp':
        'Low',
    'Vừa':
        'Medium',
    'Cao':
        'High',
    'Hạn':
        'Due',
    'Tag':
        'Tag',
    'Ưu tiên':
        'Priority',
    'Thủ công':
        'Manual',
    'Tuần này':
        'This week',
    'Sau này':
        'Later',
    'Không có hạn':
        'No due date',
    'Nhóm':
        'Group',
    'Lọc tag':
        'Filter tag',
    'Ẩn việc xong':
        'Hide done',
    'Quản lý tag':
        'Manage tags',
    'Nhóm theo: {g}':
        'Group by: {g}',
    'Enter chi tiết · Space xong · e sửa · t tag · u hạn · p ưu tiên · g nhóm · f lọc tag · h ẩn việc xong · T quản lý tag · d xoá · Shift+↑↓ đổi thứ tự · c dọn việc xong':
        'Enter details · Space done · e edit · t tags · u due · p priority · g group · f filter tag · h hide done · T manage tags · d delete · Shift+↑↓ reorder · c clear done',
    'Ghi chú mới':
        'New note',
    'Ghim':
        'Pin',
    'Tạo to-do từ dòng':
        'To-do from line',
    'n mới · p ghim · d xoá · Enter soạn · Ctrl+S lưu · Alt+T tạo to-do từ dòng đang chọn · tự lưu khi gõ':
        'n new · p pin · d delete · Enter edit · Ctrl+S save · Alt+T to-do from the current line · autosaves as you type',
    'Quá hạn':
        'Overdue',
    'Lưu riêng cho dự án này ở {path} — ngoài thư mục dự án, dùng chung tag với Ghi chú.':
        'Stored for this project only at {path} — outside the project folder, tags shared with Notes.',
    'Tag của việc':
        'To-do tags',
    'Hạn của việc':
        'To-do due date',
    'Chưa có tag nào — gõ #tag khi thêm việc':
        'No tags yet — type #tag when adding a to-do',
    'Lọc theo tag':
        'Filter by tag',
    'tất cả':
        'all',
    'Không hiểu hạn “{v}” — ví dụ: mai, t6, 24/10 17:00':
        'Could not understand the due date “{v}” — e.g. tomorrow, fri, 24/10 17:00',
    '{a} việc · {b} ghi chú · {c} chưa xong':
        '{a} to-dos · {b} notes · {c} open',
    'Thêm tag':
        'Add tag',
    'Gộp “{a}” vào':
        'Merge “{a}” into',
    '(huỷ)':
        '(cancel)',
    'Xoá ghi chú':
        'Delete note',
    'Xoá ghi chú “{v}”?':
        'Delete the note “{v}”?',
    '✅ Đã thêm {n} việc vào To-do':
        '✅ Added {n} to-dos',
    'Không có tag':
        'No tag',
    'Đã xong':
        'Done',
    'Ẩn việc đã xong':
        'Done hidden',
    '{n} việc quá hạn':
        '{n} overdue',
    'Cách nhau bằng dấu phẩy · tag chưa có thì tạo mới · trống = bỏ hết tag · có sẵn: {v}':
        'Comma separated · unknown tags are created · empty = remove all tags · existing: {v}',
    'mai 17:00':
        'tomorrow 17:00',
    'hôm nay · mai · t2…cn · tuần sau · 24/10 · 24/10 17:00 · 17h — trống = bỏ hạn':
        'today · tomorrow · mon…sun · next week · 24/10 · 24/10 17:00 · 17h — empty = no due date',
    'Việc #{id}':
        'To-do #{id}',
    'Mô tả (markdown)':
        'Description (markdown)',
    'Đổi tên tag':
        'Rename tag',
    'Xoá tag':
        'Delete tag',
    'Xoá tag “{v}”? Việc và ghi chú vẫn còn, chỉ gỡ tag.':
        'Delete the tag “{v}”? To-dos and notes stay; only the tag is removed.',
    '● Chưa lưu':
        '● Unsaved',
    '● Đã lưu {t}':
        '● Saved {t}',
    '{n} ký tự':
        '{n} chars',
    'Lọc tag:':
        'Tag filter:',
    '▶ Giao cho trưởng nhóm':
        '▶ Send to team lead',
    'Dùng chung cho To-do và Ghi chú của dự án này. Xoá tag chỉ gỡ tag khỏi việc và ghi chú, không xoá chúng.':
        "Shared by this project's To-do and Notes. Deleting a tag only removes it from to-dos and notes; they are kept.",
    'a thêm · r đổi tên · c đổi màu · m gộp vào tag khác · d xoá · Shift+↑↓ đổi thứ tự · Esc đóng':
        'a add · r rename · c recolor · m merge into another tag · d delete · Shift+↑↓ reorder · Esc close',
    'Chưa có tag nào — bấm a để thêm':
        'No tags yet — press a to add one',
    'Đã có tag “{name}”':
        'The tag “{name}” already exists',
    'Nhập tên tag':
        'Enter a tag name',
    'Tìm… (#tag để lọc)':
        'Search… (#tag to filter)',
    'Tag — cách nhau bằng dấu phẩy':
        'Tags — comma separated',
    'Ghi chú không tên':
        'Untitled note',
    'Ghi chú vừa được sửa ở nơi khác':
        'This note was just changed elsewhere',
    'Bản trên máy mới hơn bản đang sửa ở đây. Ghi đè bằng bản ở đây? (Huỷ = tải lại bản mới)':
        'The saved copy is newer than the one you are editing here. Overwrite it with this one? (Cancel = load the newer copy)',
    'Hạn — trống = không hạn':
        'Due — empty = none',
    'Không có việc nào khớp bộ lọc':
        'No to-dos match the filter',
    'Chưa có ghi chú nào — bấm n để tạo':
        'No notes yet — press n to create one',
    'Không có ghi chú khớp':
        'No matching notes',
    'Thêm việc…  #tag  !cao  @mai 17:00':
        'Add a to-do…  #tag  !high  @tomorrow 17:00',
    'Tìm việc…':
        'Search to-dos…',
    'Nhóm theo':
        'Group by',
    'Hạn: tất cả':
        'Due: all',
    'Ưu tiên: tất cả':
        'Priority: all',
    '⚙ quản lý':
        '⚙ manage',
    '⚙ Quản lý tag':
        '⚙ Manage tags',
    'Tổng quan':
        'Overview',
    'quá hạn':
        'overdue',
    'xong tuần này':
        'done this week',
    'việc khác':
        'other',
    'đóng':
        'close',
    'Chưa xong':
        'Open',
    'Chi tiết, checklist - [ ] …':
        'Details, checklist - [ ] …',
    'Chưa đặt hạn':
        'No due date',
    'Ngày mai':
        'Tomorrow',
    'Tuần sau':
        'Next week',
    'Chọn ngày…':
        'Pick a date…',
    '＋ thêm tag':
        '＋ add tag',
    'tên tag rồi Enter':
        'tag name, then Enter',
    'tạo {t}':
        'created {t}',
    'sửa {t}':
        'edited {t}',
    'Gửi tiêu đề + mô tả làm mục tiêu cho trưởng nhóm':
        'Send the title + description to the team lead as a goal',
    'Xoá việc “{v}”?':
        'Delete the to-do “{v}”?',
    'Giờ':
        'Time',
    'Bỏ hạn':
        'Clear',
    'gõ được: mai, t6, 24/10 17h':
        'you can type: tomorrow, fri, 24/10 17h',
    'tag:':
        'tag:',
    'hạn:':
        'due:',
    'ưu tiên:':
        'priority:',
    '＋ Tạo tag mới “{v}”':
        '＋ Create new tag “{v}”',
    '{n} việc · {m} ghi chú':
        '{n} to-dos · {m} notes',
    'chọn':
        'pick',
    'thêm':
        'add',
    'Mở chi tiết':
        'Open details',
    'Đặt hạn…':
        'Set due date…',
    'dùng chung cho To-do và Ghi chú của dự án này':
        "shared by this project's To-do and Notes",
    'Tên tag mới, ví dụ: hotfix':
        'New tag name, e.g. hotfix',
    '＋ Thêm tag':
        '＋ Add tag',
    'Xoá tag chỉ gỡ tag khỏi việc và ghi chú, không xoá chúng · Gộp: chuyển mọi việc/ghi chú sang tag khác rồi xoá tag này · Kéo ⋮⋮ để đổi thứ tự':
        'Deleting a tag only removes it from to-dos and notes; they are kept · Merge: move every to-do/note to another tag, then delete this one · Drag ⋮⋮ to reorder',
    'Gộp vào…':
        'Merge into…',
    'Gộp':
        'Merge',
    'Enter lưu · Esc huỷ':
        'Enter save · Esc cancel',
    'Màu':
        'Color',
    'Chưa có tag nào — gõ #tag khi thêm việc, hoặc thêm ở đây':
        'No tags yet — type #tag when adding a to-do, or add one here',
    'Tìm trong ghi chú…':
        'Search notes…',
    '＋ Ghi chú':
        '＋ Note',
    'Đã ghim':
        'Pinned',
    'Gần đây':
        'Recent',
    'Viết markdown… # tiêu đề, - danh sách, - [ ] việc, `code`':
        'Write markdown… # heading, - list, - [ ] task, `code`',
    '📌 Ghim':
        '📌 Pin',
    '📌 Bỏ ghim':
        '📌 Unpin',
    'Đang lưu…':
        'Saving…',
    'tự lưu khi gõ':
        'autosaves as you type',
    'Chưa có ghi chú nào':
        'No notes yet',
    'Chọn một ghi chú bên trái hoặc tạo ghi chú mới':
        'Pick a note on the left or create a new one',
    'Ghi chú vừa được sửa ở nơi khác.':
        'This note was just changed elsewhere.',
    'Tải lại':
        'Reload',
    '＋ Tạo to-do từ dòng đã chọn':
        '＋ To-do from selected lines',
    '＋ tag':
        '＋ tag',
    'Không thấy ghi chú #{id}':
        'Note #{id} not found',
    # --- trang Agents / Workflows
    "tab Workflows (agent tuỳ chỉnh ở tab Agents)":
        "Workflows tab (custom agents live in the Agents tab)",
    "Agent mới tham gia đội như agent có sẵn (trưởng nhóm phân việc theo vai trò, bật/tắt ở /setup). Lưu ở {CUSTOM_FILE}":
        "New agents join the team like built-in ones (the lead assigns work by role; enable/disable in /setup). Saved in {CUSTOM_FILE}",
    "Workflow chạy bằng /flow <tên> <mục tiêu>, hoặc ★ Mặc định để gõ mục tiêu là chạy luôn. Agent tuỳ chỉnh nằm ở tab 🤖 Agents. Lưu ở {CUSTOM_FILE}":
        "Workflows run with /flow <name> <goal>, or press ★ Default so typing a goal runs it. Custom agents live in the 🤖 Agents tab. Saved in {CUSTOM_FILE}",
    " [tuỳ chỉnh]":
        " [custom]",
    "Bấm vào một agent (hoặc F7) để chat riêng · bấm model/effort để đổi ngay · Esc về danh sách":
        "Click an agent (or F7) to chat with it · click a model/effort to switch right away · Esc back to the list",
    "Agents":
        "Agents",
    "Workflows":
        "Workflows",
    "💬 Nhắn {agent}… (Enter gửi · /new: cuộc mới · /term: CLI thật)":
        "💬 Message {agent}… (Enter sends · /new: new chat · /term: real CLI)",
    "Điều phối":
        "Orchestrate",
    "Mã nguồn":
        "Code",
    "Cá nhân":
        "Personal",
    "Báo cáo":
        "Reports",
    "Agent ngoài các vai trò ở trên. Bấm model · effort để đổi, 💬 để chat riêng với agent.":
        "Agents outside the roles above. Click model · effort to change it, 💬 to chat with an agent.",
    "Chat":
        "Chat",
    "tuỳ chỉnh":
        "custom",
    "chưa bật":
        "off",
    "⌨ Terminal trống":
        "⌨ Empty terminal",
    "shell của bạn trong thư mục dự án, không mở agent":
        "your shell in the project folder, no agent",
    "Chưa tham gia đội — bật ở /setup.":
        "Not on the team yet — turn them on in /setup.",
    "Workflow chạy bằng /flow <tên> <mục tiêu>, hoặc ★ Đặt mặc định để gõ mục tiêu là chạy luôn. Agent tuỳ chỉnh nằm ở trang Agents.":
        "Workflows run with /flow <name> <goal>, or ★ Make default so typing a goal runs it. Custom agents live on the Agents page.",
    'Đã huỷ lập kế hoạch mục tiêu #{gid}':
        'Cancelled planning for goal #{gid}',
    '✗ Huỷ lập kế hoạch mục tiêu #{gid}':
        '✗ Planning cancelled for goal #{gid}',
    'Dùng: /cancel <task> hoặc /cancel m<mục tiêu> (huỷ lập kế hoạch)':
        'Usage: /cancel <task> or /cancel m<goal> (cancel planning)',
    'Không có mục tiêu nào đang lập kế hoạch':
        'No goal is being planned',
    'Mục tiêu #{gid} không đang lập kế hoạch':
        'Goal #{gid} is not being planned',
    'Đã huỷ khi đang lập kế hoạch':
        'Cancelled while planning',
    '⇄ #{tid}: {old} → {agent}':
        '⇄ #{tid}: {old} → {agent}',
    '⏸ {agent} đang quá tải — tạm nghỉ đến {v} rồi thử lại.':
        '⏸ {agent} is overloaded — pausing until {v}, then retrying.',
    '⌛ {name} quá {v}s chưa xong ({label}) — thử agent dự phòng.':
        '⌛ {name} did not finish within {v}s ({label}) — trying a fallback agent.',
    '{name} đang quá tải (máy chủ bận) — thử lại sau ít phút':
        '{name} is overloaded (server busy) — try again in a few minutes',
    'Không có trưởng nhóm nào lập được kế hoạch (hết hạn mức, quá tải hoặc quá thời gian — xem log hệ thống)':
        'No team lead could make a plan (rate limited, overloaded or timed out — see the system log)',
    '{fixer} quá tải khi đang sửa lỗi test — /retry sau':
        '{fixer} was overloaded while fixing the tests — /retry later',
    ', chờ {agent} hết quá tải':
        ', waiting for {agent} to recover from overload',
    'đổi người làm 1 task (task lỗi/huỷ: chạy lại luôn); thiếu agent: bảng chọn':
        'reassign a task (failed/cancelled: rerun right away); no agent: pick from a list',
    '<task|m<mục tiêu>>':
        '<task|m<goal>>',
    'huỷ task; m<số>: huỷ lượt lập kế hoạch đang chạy':
        'cancel a task; m<id>: cancel the planning in progress',
    ' ⇄ Đổi agent ':
        ' ⇄ Change agent ',
    '  F5: chạy lại với {agent}':
        '  F5: rerun with {agent}',
    'Đổi agent cho task #{tid}':
        'Change agent for task #{tid}',
    'Thôi (giữ {agent})':
        'Never mind (keep {agent})',
    ' ✕ Huỷ lập kế hoạch ':
        ' ✕ Cancel planning ',
    'Dừng trưởng nhóm đang lập kế hoạch cho mục tiêu này':
        'Stop the team lead planning this goal',
    'Đổi agent':
        'Change agent',
    'Đổi agent cho task #{id}':
        'Change agent for task #{id}',
    'Chọn agent khác — task chạy lại ngay với agent đó (prompt đầy đủ, phiên mới)':
        'Pick another agent — the task reruns right away with it (full prompt, new session)',
    'Dùng: /assign <task> <agent> — hoặc mở task rồi bấm ⇄ Đổi agent':
        'Usage: /assign <task> <agent> — or open the task and click ⇄ Change agent',
    "⏳ Đang chạy {v}…":
        "⏳ Running {v}…",
    "⏳ Đang lưu…":
        "⏳ Saving…",
    "⏳ Đang tải…":
        "⏳ Loading…",
    "⏳ Đang thay thế…":
        "⏳ Replacing…",
    "⏳ Đang mở {v}…":
        "⏳ Opening {v}…",
    "⏳ Đang mở dự án…":
        "⏳ Opening project…",
    "⏳ Đang commit… (hook có thể chạy lâu)":
        "⏳ Committing… (hooks may take a while)",
    "🤖 AI đang giải xung đột…":
        "🤖 AI is resolving conflicts…",
    "⏳ Đang merge…":
        "⏳ Merging…",
    "⏳ Đang chuyển nhánh…":
        "⏳ Switching branch…",
    "⏳ Đang tiếp tục…":
        "⏳ Continuing…",
    "⏳ Đang chạy git…":
        "⏳ Running git…",
    "⏳ Đang viết…":
        "⏳ Writing…",
    "⏳ Đang thiết kế…":
        "⏳ Designing…",
}
