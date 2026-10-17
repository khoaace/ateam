"""Giao diện web (`ateam web`): một tiến trình giữ *một* Orchestrator, các tab trình duyệt nói chuyện qua
WebSocket. Trang (HTML/CSS/JS thuần, không build, không CDN; editor CodeMirror đóng gói ở `webui/vendor/`) nằm
ở `ateam/webui/`. Tab Git: `web_git.py`; tab Code: `web_code.py`; /setup, /custom, tuỳ chọn: `web_setup.py`.

Giao thức (JSON):
- server → trình duyệt: {"t": "hello", …} (chữ giao diện, lệnh, dữ liệu gợi ý) khi kết nối và khi cấu hình đổi;
  {"t": "state", …ảnh chụp bảng việc} khi có thay đổi; {"t": "log", task, agent, line, raw}; {"t": "job", id, line};
  {"t": "prefs", …}; {"t": "toast", text, level, open?, …} trả lời thao tác.
- trình duyệt → server: {"op": "...", ...}, xem `WebApp.handle`. Lệnh /… cùng nghĩa với TUI (`WebApp.command`).
Chỉ nghe 127.0.0.1 và kiểm tra Host/Origin (chặn trang web lạ hoặc DNS rebinding điều khiển ateam).
"""

from __future__ import annotations

import asyncio
import json
import re
import shlex
from pathlib import Path

from aiohttp import WSMsgType, web

from . import __version__, mentions, notify, reports, shell, theme, update, wizard
from .config import Config, load_config, load_state, needs_setup, save_project_setting, save_state
from .db import ASKING, DB, GOAL_ENDED, Goal, Task
from .qr import QR
from .web_auth import Remote, auth_middleware, security_headers
from .i18n import LANG_NAMES, LANGS, get_lang, normalize, save_lang, set_lang, tr
from .orchestrator import SYSTEM, Orchestrator
from .web_code import CodeWeb
from .web_git import GitWeb
from .web_setup import SetupWeb

STATIC = Path(__file__).with_name("webui")
LOG_TAIL = 600       # số dòng cuối của log gửi khi mở 1 task
TASK_LIMIT = 400     # bảng việc gửi tối đa ngần này task gần nhất


def ui_strings() -> dict[str, str]:
    """Mọi chữ hiển thị trên trang web (JS chỉ dùng các khoá này — tests/test_web.py bắt chữ viết thẳng trong JS)."""
    return {
        "board": tr("Bảng việc"), "team": tr("Đội"), "terminal": tr("Terminal"), "git": tr("Git"),
        "code": tr("Code"), "syslog": tr("Log hệ thống"), "phone": tr("Điện thoại"),
        "phone_title": tr("Mở trên điện thoại"),
        "phone_hint": tr("Quét mã bằng camera điện thoại. URL chứa token toàn quyền — đừng gửi cho người khác."),
        "phone_ro": tr("Server đang ở chế độ chỉ xem (--readonly)."),
        "phone_local": tr("Server đang chỉ nghe trên máy này. Để mở từ điện thoại, chạy lại với:"),
        "phone_local_lan": tr("cùng Wi-Fi (http, token đi dạng rõ trong LAN)"),
        "phone_local_tunnel": tr("mọi nơi qua Cloudflare Tunnel (https, cần cài cloudflared)"),
        "phone_copy": tr("Chép"), "copied": tr("Đã chép"),
        "readonly_banner": tr("👁 Chế độ chỉ xem — thao tác bị tắt"),
        "custom": tr("Tuỳ chỉnh"), "dash": tr("Thống kê"), "dash_today": tr("Hôm nay"), "dash_week": tr("7 ngày"),
        "dash_month": tr("30 ngày"), "dash_runs": tr("{n} lượt"), "dash_failed": tr("{f} lỗi · {r} hết hạn mức"),
        "dash_chart": tr("Token theo ngày (14 ngày)"), "dash_by_agent": tr("Theo agent (30 ngày)"),
        "dash_by_model": tr("Theo model (30 ngày)"), "dash_history": tr("Lịch sử mục tiêu"),
        "dash_no_goals": tr("Chưa có mục tiêu nào. Gõ mục tiêu ở ô dưới để bắt đầu."),
        "dash_col_runs": tr("Lượt"), "dash_col_time": tr("Thời gian"), "dash_col_failed": tr("Lỗi"),
        "dash_col_real": tr("Số thật"), "dash_result": tr("Kết quả:"), "dash_continue": tr("Tiếp tục mục tiêu"),
        "dash_goal_stats": tr("{n} lượt chạy · {v} · {tok} token ({real}/{n} số thật) · {cost}"), "cu_default": tr("mặc định"), "ob_flow": tr("Cấu hình luồng cố định…"),
        "ob_flow_hint": tr("agent · model · effort cho từng bước của workflow '{name}'"),
        "df_title": tr("Luồng mặc định"), "df_step": tr("Bước"), "df_agent_default": tr("(mặc định của agent)"),
        "df_review": tr("Trưởng nhóm review khi xong"), "df_default": tr("Chạy khi gõ mục tiêu (luồng mặc định)"),
        "df_hint": tr("Gõ mục tiêu (không kèm /goal) là chạy workflow này: mỗi bước một task, bước sau chờ bước "
                      "trước. Chọn agent, model, effort cho từng bước — sửa tiêu đề/prompt hay thêm bước ở mục "
                      "Tuỳ chỉnh."),
        "connected": tr("Đã kết nối"), "disconnected": tr("Mất kết nối — đang thử lại…"),
        "pause": tr("Tạm dừng"), "resume": tr("Tiếp tục nhận task"), "paused": tr("Đang tạm dừng"),
        "clear": tr("Dọn việc đã xong"), "theme": tr("Giao diện & màu nhấn"),
        "running": tr("đang chạy"), "queued": tr("chờ chạy"), "review": tr("chờ duyệt"),
        "failed": tr("lỗi"), "done": tr("xong"), "draft": tr("nháp"), "cancelled": tr("đã huỷ"),
        "blocked": tr("bị chặn"), "conflict": tr("xung đột"), "asking": tr("đang hỏi bạn"),
        "ask_title": tr("Agent hỏi giữa task"), "ask_head": tr("{agent} hỏi · task #{id}"),
        "ask_skip": tr("Để agent tự quyết"), "ask_view": tr("Xem task"), "ask_cancel": tr("Huỷ task"),
        "ask_more": tr("còn {n} task khác đang hỏi"),
        "placeholder_ask": tr("Trả lời câu hỏi của agent (Enter) · gõ số để chọn phương án"),
        "col_draft": tr("Nháp"), "col_queued": tr("Chờ chạy"), "col_running": tr("Đang chạy"),
        "col_review": tr("Chờ duyệt"), "col_done": tr("Xong"), "col_bad": tr("Lỗi / huỷ"),
        "empty_col": tr("Trống"), "no_goals": tr("Chưa có mục tiêu nào"),
        "no_goals_hint": tr("Gõ yêu cầu ở ô dưới cùng — trưởng nhóm sẽ lập kế hoạch, chia việc cho đội."),
        "all_goals": tr("Tất cả"), "round": tr("vòng {n}"),
        "continue": tr("↪ Tiếp tục"), "followups": tr("{n} lần tiếp"),
        "g_planning": tr("đang lập kế hoạch"), "g_awaiting": tr("chờ duyệt kế hoạch"),
        "g_running": tr("đang chạy"), "g_reviewing": tr("đang review"), "g_done": tr("hoàn thành"),
        "g_incomplete": tr("chưa xong"), "g_failed": tr("thất bại"), "g_cancelled": tr("đã huỷ"),
        "g_grilling": tr("đang hỏi đáp"),
        "plan_title": tr("Kế hoạch #{id} chờ duyệt"), "plan_count": tr("{n} task"),
        "approve": tr("Duyệt & chạy"), "drop_plan": tr("Bỏ kế hoạch"), "after": tr("sau {v}"),
        "edit": tr("Sửa"), "save": tr("Lưu"), "cancel_edit": tr("Thôi"),
        "grill_title": tr("Trưởng nhóm hỏi để hiểu rõ yêu cầu"), "grill_q": tr("Câu {n}"),
        "grill_answered": tr("đã trả lời {n} câu"), "grill_thinking": tr("{lead} đang nghĩ câu hỏi tiếp theo…"),
        "grill_hint": tr("Bấm một phương án, hoặc gõ câu trả lời ở ô dưới rồi Enter"),
        "recommended": tr("khuyên dùng"), "grill_done": tr("Đủ rồi — chốt & lập kế hoạch"),
        "grill_skip": tr("Để trưởng nhóm tự quyết"), "grill_retry": tr("Hỏi tiếp"),
        "grill_cancel": tr("Bỏ mục tiêu"),
        "grill_skip_answer": tr("(Tôi không chắc — bạn tự quyết)"),
        "grill_skip_rec": tr("(Tôi không chắc — bạn tự quyết, theo khuyến nghị: {v})"),
        "placeholder": tr("Nhập mục tiêu cho trưởng nhóm · / lệnh · ! lệnh terminal · @ nhắc file"),
        "placeholder_wf": tr("Nhập mục tiêu (chạy theo workflow '{wf}') · / lệnh · ! lệnh terminal · @ nhắc file"),
        "placeholder_grill": tr("Trả lời câu hỏi của trưởng nhóm (Enter) · gõ số để chọn phương án"),
        "send_hint": tr("Enter gửi · Shift+Enter xuống dòng"),
        "retry": tr("Chạy lại"), "cancel": tr("Huỷ task"), "diff": tr("Xem diff"), "merge": tr("Merge"),
        "reject": tr("Từ chối"), "reject_ph": tr("Góp ý (để trống = chỉ từ chối, có góp ý = giao làm lại)"),
        "continue_task": tr("Hỏi tiếp"), "close": tr("Đóng"),
        "tab_log": tr("Log"), "tab_prompt": tr("Nội dung"), "tab_result": tr("Kết quả"),
        "no_log": tr("Chưa có log."), "no_result": tr("Chưa có kết quả."), "error": tr("Lỗi"),
        "started": tr("Bắt đầu"), "duration": tr("Thời gian"),
        "deps": tr("Phụ thuộc"), "attempts": tr("Lần thử"), "branch": tr("Nhánh"),
        "lead": tr("trưởng nhóm"), "idle": tr("rảnh"), "not_installed": tr("chưa cài"),
        "cooldown": tr("nghỉ tới {v}"), "agent_running": tr("đang chạy {n} việc"),
        "jobs": tr("Lệnh terminal"), "no_jobs": tr("Chưa chạy lệnh nào"),
        "no_jobs_hint": tr("Gõ ! rồi lệnh ở ô dưới, vd !npm run dev — hoặc chọn một script gợi ý:"),
        "stop": tr("Dừng"), "restart": tr("Chạy lại"), "remove": tr("Xoá"),
        "j_running": tr("đang chạy"), "j_done": tr("xong"), "j_failed": tr("lỗi"), "j_stopped": tr("đã dừng"),
        "exit_code": tr("thoát với mã {rc}"), "files": tr("File"), "scripts": tr("Script của dự án"),
        "shortcuts": tr("Ctrl+K: ô nhập · F2: duyệt kế hoạch · Esc: đóng"),
        "worktree": tr("worktree"), "shared": tr("shared"),
        # --- tab Git
        "git_conflicts": tr("Xung đột"), "git_staged": tr("Đã stage"), "git_changes": tr("Thay đổi"),
        "git_stage_all": tr("Stage tất cả"), "git_unstage_all": tr("Bỏ stage tất cả"),
        "git_clean": tr("Không có thay đổi nào chưa commit."), "git_history": tr("Lịch sử"),
        "git_branches": tr("Nhánh"), "git_abort": tr("Huỷ thao tác"), "git_state": tr("đang {v}"),
        "git_synced": tr("đồng bộ"), "git_no_remote": tr("chưa có trên remote"), "git_no_commit": tr("(chưa có commit)"),
        "git_norepo": tr("Thư mục này chưa phải git repo"),
        "git_norepo_hint": tr("Tạo repo để theo dõi thay đổi, xem diff và dùng chế độ worktree."),
        "git_msg_all": tr("Commit message — chưa stage gì: commit tất cả thay đổi"),
        "git_msg_staged": tr("Commit message cho {n} file đã stage"),
        "git_msg_amend": tr("Message mới cho commit trước (trống = giữ nguyên)"),
        "git_amend": tr("Sửa commit trước (amend)"), "git_noverify": tr("Bỏ qua hook (--no-verify)"),
        "notify_on": tr("trong app + thông báo trình duyệt"), "notify_app": tr("chỉ trong app"),
        "notify_off": tr("tắt thông báo"), "notify_test": tr("gửi thử một thông báo"),
        "git_ai": tr("AI viết"), "git_ai_agent": tr("Agent viết commit message"),
        "git_ai_lead": tr("Trưởng nhóm ({lead})"), "git_ai_wait": tr("✨ {lead} đang viết commit message…"),
        "git_need_msg": tr("Gõ commit message trước (hoặc bấm ✨ để trưởng nhóm viết)"),
        "git_fetching": tr("⇣ Đang fetch…"), "git_pulling": tr("⬇ Đang pull…"), "git_pushing": tr("⬆ Đang push…"),
        "git_discard_title": tr("↺ Bỏ thay đổi"), "git_discard_yes": tr("Bỏ thay đổi"),
        "git_discard_q": tr("Bỏ mọi thay đổi chưa stage của {path}?"),
        "git_discard_new": tr("XOÁ file mới {path}? (chưa từng commit — không lấy lại được)"),
        "git_revert_q": tr("Tạo commit đảo ngược {v}?"), "git_undo": tr("⎌ Bỏ commit cuối"),
        "git_undo_q": tr("Bỏ commit cuối cùng, giữ nguyên thay đổi của nó (ở trạng thái đã stage) để sửa rồi "
                         "commit lại?"),
        "git_undo_yes": tr("Bỏ commit"), "git_checkout": tr("Chuyển sang"), "git_rename": tr("Đổi tên"),
        "git_rename_q": tr("Tên mới cho nhánh {name}:"), "git_new_branch": tr("Tên nhánh mới"),
        "git_create_branch": tr("Tạo nhánh"), "git_merge_q": tr("Merge {name} vào {cur}?"),
        "git_force_delete": tr("Xoá hẳn nhánh"),
        "git_force_delete_q": tr("Nhánh {name} chưa merge hết — xoá hẳn (mất các commit chưa merge)?"),
        "git_no_stash": tr("Chưa có stash nào."), "git_stash_msg": tr("Ghi chú cho stash (tuỳ chọn)"),
        "git_stash_push": tr("Cất thay đổi"), "git_stash_drop": tr("✗ Xoá stash"),
        "git_stash_drop_q": tr("Xoá {ref}? Không lấy lại được."), "refresh": tr("Làm mới"),
        # --- diff
        "hunk_prev": tr("Đoạn trước"), "hunk_next": tr("Đoạn sau"), "split_view": tr("2 cột"),
        "open_in_code": tr("Mở trong Code"), "diff_binary": tr("File nhị phân — không hiện nội dung"),
        "diff_empty": tr("File rỗng"), "diff_renamed": tr("Chỉ đổi tên, nội dung giữ nguyên"),
        "diff_truncated": tr("File dài — chỉ hiện 4000 dòng đầu"),
        "diff_keys": tr("n/p: file · [ ]: đoạn đổi · s: 1 cột / 2 cột · e: mở trong Code · Esc: đóng"),
        # --- tab Code
        "code_filter": tr("Tìm file… (Enter mở · ⌘P)"), "code_nofile": tr("Không có file"),
        "code_hint": tr("Chọn file ở cây bên trái, hoặc /code @file:dòng"),
        "code_vim_hint": tr("vim: i sửa · Esc · :w lưu · :q đóng · :bn/:bp đổi file · /vim off để tắt"),
        "code_novim_hint": tr("Ctrl/⌘+S lưu · /vim on để bật phím vim"), "code_plain": tr("văn bản"),
        "code_pos": tr("dòng {r}/{n}, cột {c}"), "code_readonly": tr("chỉ đọc: {v}"),
        "code_readonly_title": tr("Chỉ đọc"), "code_readonly_q": tr("File đang ở chế độ chỉ đọc ({v}). Vẫn ghi?"),
        "code_write_anyway": tr("Vẫn ghi"), "code_conflict": tr("File đã đổi trên đĩa"),
        "code_conflict_q": tr("{path} đã bị sửa từ lúc bạn mở (có thể do agent). Ghi đè bằng nội dung của bạn?"),
        "code_overwrite": tr("Ghi đè"), "code_unsaved": tr("Chưa lưu"),
        "code_unsaved_q": tr("{path} còn thay đổi chưa lưu. Đóng và bỏ thay đổi?"), "code_discard": tr("Bỏ thay đổi"),
        "code_reloaded": tr("Đã nạp lại từ đĩa"), "code_reloaded_disk": tr("File đổi trên đĩa — đã nạp lại"),
        "code_changed_dirty": tr("File vừa đổi trên đĩa (có thể do agent sửa) — :e! để nạp lại (bỏ phần đang sửa) "
                                 "hoặc :w! để ghi đè"),
        "code_new_file": tr("File mới — :w để tạo"),
        "code_load_fail": tr("Không nạp được editor (vendor/codemirror.js)"),
        # --- gợi ý ô nhập
        "cmds": tr("Lệnh"), "sg_agent": tr("Agent"), "sg_agent_task": tr("Agent · thêm :model hoặc @effort"),
        "sg_model": tr("Model của {v}"), "sg_effort": tr("Effort của {v}"), "sg_task": tr("Task"),
        "sg_task_or_file": tr("Task (hoặc @file để mở trong Code)"), "sg_goal": tr("Mục tiêu"),
        "sg_continue": tr("Tiếp tục mục tiêu / thread"), "sg_branch": tr("Nhánh"), "sg_minutes": tr("Số phút"),
        "sg_refresh": tr("hỏi lại danh sách model từ CLI"), "stash_pop": tr("lấy lại và xoá stash"),
        "stash_apply": tr("lấy lại, giữ stash"), "stash_list": tr("danh sách stash"),
        "force_push": tr("push đè (--force-with-lease)"), "no_verify": tr("bỏ qua hook"),
        "verify_off": tr("tắt kiểm tra"),
        # --- khung chung, theme, bảng chọn
        "help": tr("Trợ giúp"), "default_value": tr("(mặc định)"),
        "pick_title": tr("Chọn {key} cho {agent} (đang dùng: {v})"), "pick_custom": tr("hoặc gõ tên khác rồi Enter"),
        "pick_hint": tr("Bấm để đổi model / effort"), "appearance": tr("Giao diện"), "accent": tr("Màu nhấn"),
        "accent_default": tr("Mặc định (tím → ngọc)"), "mode_system": tr("Theo hệ thống"), "mode_light": tr("Sáng"),
        "mode_dark": tr("Tối"),
        "accent_shared": tr("Màu nhấn lưu chung với giao diện terminal; sáng/tối chỉ áp cho trình duyệt này."),
        # --- /setup
        "ob_title": tr("Thiết lập đội AI · Bước {v}/{n} — {title}"), "ob_back": tr("Quay lại"), "ob_next": tr("Tiếp"),
        "ob_save": tr("Lưu & bắt đầu"), "ob_custom": tr("Agent & workflow tuỳ chỉnh…"),
        "ob_q_cli": tr("Bạn đang dùng những CLI nào? Đội chỉ gồm các CLI được chọn."),
        "ob_installed": tr("đã cài ({p})"), "ob_not_installed": tr("chưa cài — {v}"),
        "ob_pick_cli": tr("Chọn ít nhất một CLI"), "ob_q_style": tr("Bạn muốn đội làm việc thế nào?"),
        "ob_q_tier": tr("Ưu tiên tiết kiệm hạn mức hay chất lượng?"),
        "ob_tier_hint": tr("Bước sau điền sẵn model & effort theo mức này — vẫn đổi được từng vai trò."),
        "ob_q_roles": tr("Giao từng vai trò cho CLI nào, dùng model và effort gì?"),
        "ob_roles_hint": tr("Cùng một CLI làm nhiều vai trò với model/effort khác nhau → ateam tự tạo thêm agent (vd "
                            "claude-review)."),
        "ob_discovering": tr("đang hỏi danh sách model từ các CLI…"), "ob_unused": tr("(không dùng)"),
        "ob_q_access": tr("Agent được làm gì?"), "ob_q_apply": tr("Thay đổi của agent áp vào code thế nào?"),
        "ob_need_git": tr(" — cần thư mục là git repo có commit"),
        "ob_q_verify": tr("Lệnh kiểm tra tự chạy sau mỗi task (test, lint, build)?"),
        "ob_verify_ph": tr("hoặc gõ lệnh khác, vd: npm run lint && npm test"), "ob_team": tr("Đội"),
        "ob_added": tr("agent thêm"), "ob_custom_kept": tr("Agent tuỳ chỉnh giữ nguyên: {v}"),
        "ob_how": tr("Cách làm việc"), "ob_style": tr("Kiểu"), "ob_tier": tr("Mức"), "ob_access": tr("Quyền"),
        "ob_apply": tr("Áp thay đổi"), "ob_verify": tr("Kiểm tra"), "ob_none": tr("không"),
        "ob_no_lead": tr("Chưa có trưởng nhóm — quay lại bước Vai trò."),
        # --- /custom
        "cu_title": tr("Agent & workflow tuỳ chỉnh"),
        "cu_hint": tr("Agent mới tham gia đội như agent có sẵn (trưởng nhóm phân việc theo vai trò, bật/tắt ở "
                      "/setup). Workflow chạy bằng /flow <tên> <mục tiêu>."),
        "cu_agents": tr("Agent tuỳ chỉnh"), "cu_add_agent": tr("Thêm agent"), "cu_add_flow": tr("Thêm workflow"),
        "cu_add_custom_agent": tr("Thêm agent tuỳ chỉnh"), "cu_edit_agent": tr("Sửa agent {name}"),
        "cu_edit_flow": tr("Sửa workflow {name}"),
        "cu_no_agents": tr("Chưa có. Bấm '+ Thêm agent' để thêm CLI bất kỳ (Gemini, Aider, script riêng…)."),
        "cu_no_flows": tr("Chưa có. Bấm '+ Thêm workflow' (có mẫu: tính năng mới, sửa lỗi, review)."),
        "cu_steps": tr("{n} bước: {v}"), "cu_del_q": tr("Xoá '{name}'?"),
        "cu_quick_hint": tr("Chọn nhà cung cấp, model, effort và quyền — cờ CLI ateam tự điền. CLI khác (Gemini, "
                            "Aider, lệnh riêng): Nâng cao…"),
        "cu_adv_hint": tr("Bất kỳ CLI nào có chế độ headless (nhận prompt, in kết quả rồi thoát). Chọn mẫu để "
                          "điền sẵn."),
        "cu_provider": tr("Nhà cung cấp"), "cu_name": tr("Tên"), "cu_access": tr("Quyền"),
        "cu_safe": tr("Chỉ sửa file (an toàn)"), "cu_full": tr("Toàn quyền"), "cu_role": tr("Vai trò"),
        "cu_role_ph": tr("trưởng nhóm chia việc dựa vào đây"), "cu_advanced": tr("Nâng cao…"),
        "cu_template": tr("Mẫu"), "cu_pick_template": tr("(chọn để điền sẵn)"),
        "cu_pty": tr("Chạy trong terminal giả (pty)"), "cu_verify": tr("Chạy lệnh kiểm tra sau task"),
        "cu_will_run": tr("Lệnh sẽ chạy:"), "cu_installed": tr("đã cài '{v}'"), "cu_missing": tr("chưa cài '{v}'"),
        "cu_full_warn": tr("toàn quyền: agent chạy được mọi lệnh trên máy, chỉ dùng với repo tin tưởng"),
        "cu_no_prompt": tr("lệnh không có {prompt}: prompt sẽ được thêm vào cuối"),
        "cu_type_cmd": tr("Nhập lệnh để xem trước."), "cu_desc": tr("Mô tả"),
        "cu_review": tr("Trưởng nhóm review khi xong"),
        "cu_flow_hint": tr("Chuỗi bước dựng sẵn, chạy bằng /flow <tên> <mục tiêu> — không cần trưởng nhóm lập kế "
                           "hoạch. {goal} trong tiêu đề/prompt = mục tiêu bạn gõ. 'Sau bước': trống = sau bước liền "
                           "trước, 0 = chạy ngay, 1,2 = sau bước 1 và 2."),
        "cu_flow_copy": tr("'{name}' nằm trong file cấu hình — lưu sẽ tạo bản sao với tên mới."),
        "cu_lead": tr("trưởng nhóm ({lead})"), "cu_not_in_team": tr("{v} (không có trong đội)"),
        "cu_step_title": tr("Tiêu đề"), "cu_step_prompt": tr("việc cần làm, có thể dùng {goal}"),
        "cu_step_after": tr("Sau bước"), "cu_add_step": tr("Thêm bước"), "cu_one_step": tr("Workflow cần ít nhất 1 bước"),
    }




def _first_line(s: str | None, n: int = 160) -> str:
    return (s or "").strip().splitlines()[0][:n] if (s or "").strip() else ""


def task_json(t: Task) -> dict:
    return {"id": t.id, "goal": t.goal_id, "parent": t.parent_id, "agent": t.agent, "title": t.title,
            "prompt": t.prompt, "status": t.status, "deps": t.depends_on, "source": t.source,
            "result": t.result, "error": t.error, "branch": t.branch, "created": t.created,
            "started": t.started, "finished": t.finished, "model": t.model, "effort": t.effort,
            "attempts": t.attempts, "question": t.question()}


def goal_json(g: Goal, busy: bool) -> dict:
    qa = (g.grill or {}).get("qa") or []
    return {"id": g.id, "text": g.text, "title": _first_line(g.text, 200), "status": g.status, "round": g.round,
            "summary": g.summary, "workflow": g.workflow, "followups": g.followups or [],
            "busy": busy, "spec": bool(g.spec), "qa": sum(1 for x in qa if x.get("a") is not None),
            "created": g.created, "ended": g.status in GOAL_ENDED}


def tail_file(path: Path, n: int = LOG_TAIL) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()[-n:]


def guard_middleware(port: int):
    """Chỉ phục vụ khi Host là máy này (chặn DNS rebinding) và Origin (nếu có) cũng là máy này (chặn trang
    web lạ mở WebSocket tới ateam — giao diện chạy được lệnh shell). Từ xa: xem web_auth."""
    return auth_middleware(Remote(Path("."), port=port), port)


# --readonly: thao tác không đổi gì vẫn cho phép
READONLY_OPS = ("custom_preview",)


def text_box(title: str, body: str) -> dict:
    """Mở một khung chữ (help, /usage, /agents…) ở trình duyệt."""
    return {"open": {"text": {"title": title, "body": body}}}


class WebApp:
    def __init__(self, root: Path, cfg: Config, db: DB, port: int = 8000, remote: Remote | None = None):
        self.root, self.cfg, self.db, self.port = root, cfg, db, port
        self.remote = remote or Remote(Path(root) / ".ateam", port=port)
        self.orch = Orchestrator(root, cfg, db, on_event=self.on_orch_event)
        self.shell = shell.ShellManager(root, on_event=self.on_shell_event)
        self.index = mentions.FileIndex(root)
        self.git = GitWeb(self)
        self.code = CodeWeb(self)
        self.setup = SetupWeb(self)
        self.clients: set[web.WebSocketResponse] = set()
        self.discovering = False  # đang hỏi danh sách model từ các CLI (wizard hiện "⏳")
        self._last_state = ""
        self.notices = notify.Watcher()  # báo trình duyệt khi task lỗi / chờ duyệt (như TUI)
        self._bg: set[asyncio.Task] = set()

    # ------------------------------------------------------------------ dựng app
    def make_app(self) -> web.Application:
        app = web.Application(middlewares=[auth_middleware(self.remote, self.port)],
                              client_max_size=32 * 1024 ** 2)
        app.on_response_prepare.append(security_headers)
        app.add_routes([
            web.get("/", self.page),
            web.get("/login", self.login_done),
            web.get("/api/remote", self.api_remote),
            web.get("/ws", self.ws),
            web.get("/api/log/{tid}", self.api_log),
            web.get("/api/agent/{name}", self.api_agent_tail),
            web.get("/api/job/{jid}", self.api_job),
            web.get("/api/scripts", self.api_scripts),
            web.get("/api/files", self.api_files),
            web.get("/api/continue", self.api_continue),
            web.get("/api/dashboard", self.api_dashboard),
            web.get("/api/goals", self.api_goals),
            web.static("/static", STATIC),
        ] + self.git.routes() + self.code.routes() + self.setup.routes())
        app.on_startup.append(self._startup)
        app.on_shutdown.append(self._shutdown)
        return app

    async def _startup(self, _app) -> None:
        await self.orch.setup()
        for n in self.cfg.notices:
            self.orch.log("ℹ " + n)
        self._spawn(self.orch.run_forever())
        self._spawn(self._push_loop())
        if self.remote.tunnel:
            self._spawn(self._tunnel())
        if not needs_setup():  # như TUI: hỏi model của CLI chưa từng hỏi (wizard tự hỏi khi mở)
            found = load_state().get("models_found", {})
            self._spawn(self.orch.discover_all([n for n in self.cfg.active_agents() if n not in found],
                                               on_done=lambda _n, msg: self.orch.log("⚙ " + msg)))

    async def _tunnel(self) -> None:
        def ready(url: str) -> None:
            print_remote(self.remote, only=url)
            self.orch.log(tr("🌐 Cloudflare Tunnel: {url}", url=url))
        try:
            await self.remote.start_tunnel(ready)
        except OSError as e:
            self.orch.log(tr("✗ Không chạy được cloudflared: {e}", e=e))
            return
        if self.remote.proc and self.remote.proc.returncode not in (None, 0):
            self.orch.log(tr("✗ cloudflared đã dừng (mã {rc})", rc=self.remote.proc.returncode))

    async def _shutdown(self, _app) -> None:
        await self.remote.stop_tunnel()
        self.shell.stop_all()  # không để lại dev server mồ côi
        for run in list(self.orch.runs.values()):
            if run is not None:
                run.cancel()
        for ws in list(self.clients):
            await ws.close()
        for t in list(self._bg):
            t.cancel()

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.get_running_loop().create_task(coro)
        self._bg.add(t)
        t.add_done_callback(self._bg.discard)
        return t

    async def reload_config(self, setup: bool = False) -> None:
        """Đọc lại cấu hình sau /setup hoặc /custom (như TeamApp._setup_done / reload_custom), báo mọi tab."""
        added, removed = wizard.reload_custom(self.cfg, load_config(self.root))
        if setup:
            if wizard.apply_live(self.cfg, load_config(self.root)):
                await self.orch.apply_isolation()
        else:
            self.orch.log(tr("⚙ Đã cập nhật agent/workflow tuỳ chỉnh. Agent: {v}", v=", ".join(self.cfg.agents))
                          + (tr(" (mới: {v})", v=", ".join(sorted(added))) if added else "")
                          + (tr(" (đã xoá: {v})", v=", ".join(sorted(removed))) if removed else "")
                          + f". Workflow: {', '.join(self.cfg.workflows) or tr('(chưa có)')}.")
        self.broadcast(self.hello())

    async def discover(self) -> None:
        """Hỏi danh sách model của mọi CLI (wizard /setup), báo trình duyệt khi xong."""
        if self.discovering:
            return
        self.discovering = True
        try:
            await self.orch.discover_all(timeout=20)
        except Exception as e:  # không bao giờ chặn wizard
            self.orch.log(tr("⚠ Không hỏi được danh sách model: {e}", e=e))
        finally:
            self.discovering = False
        self.broadcast({"t": "discovered"})
        self.broadcast(self.hello())

    # ------------------------------------------------------------------ sự kiện → trình duyệt
    def on_orch_event(self, kind: str, data: dict) -> None:
        if kind == "log":  # line: dòng cho log của task; raw: dòng gốc cho ô agent (tab Đội)
            line = data.get("line", "")
            self.broadcast({"t": "log", "task": data.get("task_id"), "agent": data.get("agent"),
                            "line": line, "raw": data.get("raw", line)})

    def on_shell_event(self, kind: str, job, line: str) -> None:
        if kind == "line":
            self.broadcast({"t": "job", "id": job.id, "line": line})

    def broadcast(self, msg: dict) -> None:
        if not self.clients:
            return
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.clients):
            if not ws.closed:
                self._spawn(self._send(ws, data))

    def push_notices(self, notes: list, force: bool = False) -> None:
        """Gửi thông báo cho trình duyệt (toast; `desktop` = được hiện thông báo của trình duyệt)."""
        m = notify.mode() if notes else "off"
        if force and notes and m == "off":
            m = "app"
        if m == "off":
            return
        for n in notes[:4]:
            self.broadcast(dict(n.to_json(), desktop=m == "all", force=force))

    def broadcast_prefs(self) -> None:
        st = load_state()
        self.broadcast({"t": "prefs", "vim": st.get("vim", True) is not False, "accent": st.get("accent") or "",
                        "accent_color": theme.ACCENTS.get(st.get("accent") or "", "")})

    @staticmethod
    async def _send(ws: web.WebSocketResponse, data: str) -> None:
        try:
            await ws.send_str(data)
        except (ConnectionError, RuntimeError):
            pass

    async def _push_loop(self) -> None:
        """Ảnh chụp bảng việc mỗi 0,5 giây — chỉ gửi khi khác lần trước (task/agent khác cũng ghi vào DB)."""
        while True:
            await asyncio.sleep(0.5)
            try:
                self.push_notices(self.notices.diff(self.db.tasks(), self.db.goals()))
            except Exception:
                pass
            if not self.clients:
                continue
            try:
                state = json.dumps(self.snapshot(), ensure_ascii=False)
            except Exception as e:  # DB đang bị ghi dở… — lần sau đọc lại
                self.orch.log(f"⚠ web: {e}")
                continue
            if state != self._last_state:
                self._last_state = state
                for ws in list(self.clients):
                    if not ws.closed:
                        await self._send(ws, state)

    # ------------------------------------------------------------------ ảnh chụp trạng thái
    def snapshot(self) -> dict:
        o, cfg = self.orch, self.cfg
        goals_all = self.db.goals()
        keep = {g.id for g in goals_all[-8:]} | {g.id for g in goals_all if g.status not in GOAL_ENDED}
        goals = [goal_json(g, g.status in ("planning", "reviewing") or g.id in o.lead_busy)
                 for g in goals_all if g.id in keep]
        tasks = self.db.tasks()[-TASK_LIMIT:]
        agents = []
        for name, a in cfg.active_agents().items():
            acts = [{k: act.get(k) for k in ("task_id", "title", "label", "started", "lines", "last_line")}
                    for act in o.current_activities(name)]
            agents.append({"name": name, "lead": name == cfg.lead, "installed": a.installed(),
                           "label": a.label(), "role": a.role, "model": a.model, "effort": a.effort,
                           "cooldown": o.cooldown_label(name) if o.in_cooldown(name) else "",
                           "activities": acts})
        grill = None
        g = o.grill_active()
        if g:
            busy = g.id in o.lead_busy
            q = None if busy else o.grill_question(g)
            qa = (g.grill or {}).get("qa") or []
            grill = {"goal": g.id, "text": _first_line(g.text, 300), "busy": busy, "question": q,
                     "n": len(qa), "answered": sum(1 for x in qa if x.get("a") is not None),
                     "error": "" if busy else str((g.grill or {}).get("error") or "")}
        ask = None
        at = o.ask_active() if not grill else None
        if at:
            ask = {"task": at.id, "agent": at.agent, "title": at.title, "question": at.question(),
                   "n": len((at.ask or {}).get("qa") or []), "more": len(self.db.tasks(status=ASKING)) - 1}
        jobs = [{"id": j.id, "cmd": j.cmd, "status": j.status, "started": j.started, "finished": j.finished,
                 "rc": j.rc, "ports": j.ports} for j in self.shell.jobs.values()]
        return {"t": "state", "goals": goals, "tasks": [task_json(t) for t in tasks], "agents": agents,
                "grill": grill, "ask": ask, "jobs": jobs, "paused": o.paused, "worktree": o.use_worktree,
                "lead": cfg.lead, "commit_agent": cfg.commit_agent, "workflow": cfg.default_workflow, "compacting": o.compacting,
                "continue": reports.continue_candidates(self.db), "busy": len(o.runs)}

    def hello(self) -> dict:
        from .tui import COMMANDS, HELP  # danh sách lệnh + trợ giúp dùng chung với TUI
        st = load_state()
        return {"t": "hello", "version": __version__, "project": self.root.name, "root": str(self.root),
                "remote": self.remote.enabled, "readonly": self.remote.readonly,
                "lang": get_lang(), "T": ui_strings(), "help": HELP,
                "commands": [{"name": n, "args": a, "desc": d} for n, a, d in COMMANDS],
                # dữ liệu gợi ý tham số lệnh (/task agent:model@effort, /model, /flow…)
                "agents": [{"name": n, "model": a.model, "effort": a.effort, "models": a.model_choices(),
                            "efforts": list(a.efforts), "role": a.role, "installed": a.installed(),
                            "lead": n == self.cfg.lead, "label": a.label()}
                           for n, a in self.cfg.active_agents().items()],
                "all_agents": list(self.cfg.agents),
                "workflows": [{"name": n, "summary": w.summary(), "description": w.description}
                              for n, w in self.cfg.workflows.items()],
                "accents": [{"key": k, "label": theme.accent_label(k), "color": c} for k, c in theme.ACCENTS.items()],
                "langs": [{"key": k, "label": LANG_NAMES[k]} for k in LANGS],
                "prefs": {"notify": notify.mode(), "vim": st.get("vim", True) is not False, "accent": st.get("accent") or "",
                          "accent_color": theme.ACCENTS.get(st.get("accent") or "", "")},
                "needs_setup": needs_setup()}

    # ------------------------------------------------------------------ HTTP
    async def login_done(self, _r: web.Request) -> web.Response:  # đã đăng nhập mà mở lại /login
        raise web.HTTPFound("/")

    async def api_remote(self, _r: web.Request) -> web.Response:
        """Mở trên điện thoại: các URL kèm token + mã QR (chỉ người đã đăng nhập mới gọi được)."""
        r = self.remote
        # máy này (127.0.0.1) không cần mã QR: điện thoại không mở được địa chỉ đó
        urls = [{"label": lb, "url": u, "svg": "" if "//127.0.0.1:" in u else QR(u).to_svg(5)}
                for lb, u in r.urls()] if r.enabled else []
        return web.json_response({"enabled": r.enabled, "readonly": r.readonly, "tunnel": r.tunnel,
                                  "urls": urls}, headers={"Cache-Control": "no-store"})

    async def page(self, _request: web.Request) -> web.StreamResponse:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        # ?v=: bản mới (hoặc file trang vừa sửa) không bị trình duyệt dùng lại JS/CSS cũ trong cache
        ver = f"{__version__}-{int(max(f.stat().st_mtime for f in STATIC.iterdir() if f.is_file()))}"
        html = html.replace("{{LANG}}", get_lang()).replace("{{TITLE}}", f"ateam · {self.root.name}") \
            .replace("{{V}}", ver)
        return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-store"})

    async def api_log(self, request: web.Request) -> web.Response:
        tid = int(request.match_info["tid"])
        path = self.orch.logs / "system.log" if tid == SYSTEM else self.orch.log_path(tid)
        return web.json_response({"task": tid, "lines": tail_file(path)})

    async def api_agent_tail(self, request: web.Request) -> web.Response:
        """Phần cuối log của task gần nhất của agent (ô agent ở tab Đội lúc mới mở trang)."""
        name = request.match_info["name"]
        last = [t for t in self.db.tasks() if t.agent == name and t.started]
        if not last:
            return web.json_response({"task": None, "lines": []})
        t = last[-1]
        return web.json_response({"task": t.id, "title": t.title, "status": t.status,
                                  "lines": tail_file(self.orch.log_path(t.id), 60)})

    async def api_job(self, request: web.Request) -> web.Response:
        job = self.shell.jobs.get(int(request.match_info["jid"]))
        return web.json_response({"id": job.id, "lines": job.lines[-3000:]} if job else {"lines": []})

    async def api_scripts(self, _request: web.Request) -> web.Response:
        return web.json_response([{"cmd": c, "desc": d} for c, d in shell.project_scripts(self.root)])

    async def api_files(self, request: web.Request) -> web.Response:
        if self.index.stale():
            await self.index.refresh()
        return web.json_response(mentions.search(self.index.entries, request.query.get("q", ""),
                                                 int(request.query.get("n", 12))))

    async def api_dashboard(self, _r: web.Request) -> web.Response:
        return web.json_response(reports.dashboard(self.db))  # cùng số liệu với tab 📊 Thống kê của TUI

    async def api_goals(self, r: web.Request) -> web.Response:
        return web.json_response(reports.goal_history(self.db, int(r.query.get("limit", "50") or 50)))

    async def api_continue(self, request: web.Request) -> web.Response:
        ok, text = reports.continue_hint(self.db, self.orch, request.query.get("ref", ""))
        return web.json_response({"ok": ok, "text": text})

    # ------------------------------------------------------------------ WebSocket
    async def ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=32 * 1024 ** 2)  # lưu file lớn qua WS
        await ws.prepare(request)
        self.clients.add(ws)
        try:
            await ws.send_str(json.dumps(self.hello(), ensure_ascii=False))
            await ws.send_str(json.dumps(self.snapshot(), ensure_ascii=False))
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                data: dict = {}
                try:
                    data = json.loads(msg.data)
                    reply = await self.handle(data)
                except Exception as e:  # thao tác lỗi không làm rớt kết nối
                    reply = (tr("Lỗi: {e}", e=e), "error")
                # (thông báo, mức) hoặc (thông báo, mức, {"open": …, …} cho trình duyệt mở khung/tab)
                out = {"t": "toast", "text": reply[0] if reply else "", "level": reply[1] if reply else "",
                       "ref": data.get("ref") if isinstance(data, dict) else None}
                if reply and len(reply) > 2:
                    out.update(reply[2])
                if reply or out["ref"] is not None:
                    await ws.send_str(json.dumps(out, ensure_ascii=False))
        finally:
            self.clients.discard(ws)
        return ws

    async def handle(self, d: dict) -> tuple | None:
        """Một thao tác từ trình duyệt. Trả (thông báo, mức: info|ok|warn|error[, thêm]) hoặc None."""
        o, op = self.orch, d.get("op")
        if self.remote.readonly and op not in READONLY_OPS:
            return tr("Chế độ chỉ xem (--readonly) — không làm được thao tác này"), "warn"
        if op == "submit":
            return await self.submit(str(d.get("text") or ""))
        if op == "approve":
            n = o.approve(d.get("goal"))
            return (tr("▶ Đã duyệt {n} task", n=n), "ok") if n else (tr("Không có task nháp nào cần duyệt"), "warn")
        if op == "drop":
            n = o.discard_plan(int(d["goal"]))
            return tr("Đã bỏ kế hoạch #{gid} ({v} task nháp)", gid=d["goal"], v=n), "info"
        if op == "grill":
            act, gid = d.get("action"), d.get("goal")
            if act == "answer":
                return o.answer_grill(gid, str(d.get("text") or "")), "info"
            if act == "done":
                return o.finish_grill(gid), "info"
            if act == "retry":
                return o.retry_grill(gid), "info"
            if act == "cancel":
                return o.cancel_grill(gid), "info"
        if op == "ask":
            act, tid = d.get("action"), int(d.get("task") or 0)
            if act == "answer":
                return o.answer_task(tid, str(d.get("text") or "")), "info"
            if act == "skip":
                return o.answer_task(tid, None), "info"
        if op == "retry":
            return o.retry(int(d["task"])), "info"
        if op == "cancel":
            return o.cancel(int(d["task"])), "info"
        if op == "merge":
            return await o.merge(int(d["task"])), "info"
        if op == "reject":
            return await o.reject(int(d["task"]), str(d.get("feedback") or "").strip() or None), "info"
        if op == "edit":
            return o.edit(int(d["task"]), str(d.get("prompt") or "").strip()), "info"
        if op == "assign":
            return o.assign(int(d["task"]), str(d.get("agent") or "")), "info"
        if op == "agent_option":  # bảng chọn model/effort (như open_picker của TUI)
            v = d.get("value")
            return o.set_agent_option(str(d["agent"]), str(d["key"]), None if v in (None, "") else str(v)), "ok"
        if op == "pause":
            o.paused = bool(d.get("on"))
            o.log(tr("⏸ Tạm dừng: không bắt đầu task mới (task đang chạy vẫn tiếp tục).") if o.paused
                  else tr("▶ Tiếp tục."))
            return None
        if op == "clear":
            n_tasks, n_goals = o.clear_finished()
            if not n_tasks and not n_goals:
                return tr("Không có task nào đã kết thúc để dọn"), "info"
            return (tr("🗑 Đã dọn {n_tasks} task", n_tasks=n_tasks)
                    + (tr(", {n_goals} mục tiêu", n_goals=n_goals) if n_goals else "")), "ok"
        if op == "job":
            job = self.shell.jobs.get(int(d["id"]))
            act = d.get("action")
            if not job:
                return None
            if act == "stop" and not self.shell.stop(job):
                return tr("Lệnh này đã dừng"), "info"
            if act == "restart":
                return "", "", {"open": {"job": self.shell.restart(job).id}}
            if act == "remove" and not self.shell.remove(job):
                return tr("Đang chạy — Dừng trước rồi mới xoá"), "warn"
            return None
        if op == "git":
            return await self.git.op(d)
        if op == "save":
            return self.code.save(d)
        if op == "setup_save":
            return await self.setup.save_setup(d)
        if op == "setup_skip":
            return self.setup.skip_setup()
        if op == "setup_discover":
            self._spawn(self.discover())
            return None
        if op == "custom_save":
            return await self.setup.save_custom(d)
        if op == "custom_delete":
            return await self.setup.delete_custom(d)
        if op == "default_flow_save":
            return await self.setup.save_default_flow(d)
        if op == "custom_preview":
            return self.setup.preview_agent(d)
        if op == "prefs":
            return self.setup.set_prefs(d)
        return tr("Không hiểu thao tác {op}", op=op), "warn"

    async def submit(self, text: str) -> tuple | None:
        """Ô nhập chính — cùng luật với TUI: !lệnh, trả lời /grill, mục tiêu mới, hoặc lệnh /…"""
        text = text.strip()
        if not text:
            return None
        if text.startswith("!"):
            return self.run_shell(text[1:])
        g = self.orch.grill_active()
        if not text.startswith("/") and g and self.orch.grill_question(g):
            q = self.orch.grill_question(g) or {}
            opts = q.get("options") or []
            if text.isdigit() and 1 <= int(text) <= len(opts):
                text = opts[int(text) - 1]  # gõ số = chọn phương án đó
            return self.orch.answer_grill(g.id, text), "info"
        at = self.orch.ask_active() if not g else None
        if not text.startswith("/") and at:
            opts = (at.question() or {}).get("options") or []
            if text.isdigit() and 1 <= int(text) <= len(opts):
                text = opts[int(text) - 1]
            return self.orch.answer_task(at.id, text), "info"
        if not text.startswith("/"):
            return self.start_goal(text, self.cfg.default_workflow)
        return await self.command(text)

    def run_shell(self, cmd: str) -> tuple:
        cmd = cmd.strip()
        if not cmd:
            return tr("Gõ lệnh sau dấu !, vd !yarn dev (gõ ! để xem gợi ý)"), "warn"
        job = self.shell.start(cmd)
        return "", "", {"open": {"job": job.id}}

    def start_goal(self, text: str, workflow: str = "") -> tuple[str, str] | None:
        if workflow:
            res = self.orch.run_workflow(workflow, text)
            return (res, "warn") if isinstance(res, str) else None
        if not self.cfg.agents.get(self.cfg.lead):
            return tr("Không có trưởng nhóm '{lead}' trong cấu hình", lead=self.cfg.lead), "error"
        self.orch.new_goal(text)
        return None

    async def _bg_log(self, coro, done_msg=None) -> None:
        """Chạy việc lâu (usage từ CLI, cập nhật) ở nền, kết quả ghi log hệ thống."""
        try:
            res = await coro
            if done_msg:
                self.orch.log(done_msg(res))
        except Exception as e:
            self.orch.log(tr("Lỗi: {e}", e=e))

    async def command(self, text: str) -> tuple | None:
        """Lệnh /… — cùng nghĩa với TeamApp.run_command (test kiểm mọi lệnh trong tui.COMMANDS)."""
        from .tui import COMMAND_ALIASES, COMMANDS, command_needs_args, command_usage, parse_code_target, \
            suggest_command
        cmd, _, rest = text[1:].partition(" ")
        cmd, rest = COMMAND_ALIASES.get(cmd.lower(), cmd.lower()), rest.strip()
        o, cfg, agents = self.orch, self.cfg, self.cfg.active_agents()

        def num(s: str) -> int:
            return int(s.strip().lstrip("#mt"))

        if cmd not in {c[0] for c in COMMANDS}:
            near = suggest_command(cmd)
            return (tr("Không hiểu lệnh /{cmd}", cmd=cmd) + (tr(" — có phải /{near}?", near=near) if near else "")
                    + tr(" · gõ / để xem danh sách, F1 trợ giúp")), "warn"
        if not rest and command_needs_args(cmd) and cmd not in ("flow", "model", "effort", "continue"):
            return command_usage(cmd), "warn"
        try:
            return await self._command(cmd, rest, o, cfg, agents, num, parse_code_target)
        except (ValueError, IndexError):  # thiếu/sai tham số -> chỉ cách dùng
            return command_usage(cmd), "warn"

    async def _command(self, cmd, rest, o, cfg, agents, num, parse_code_target) -> tuple | None:
        if cmd == "help":
            return "", "", {"open": {"modal": "help"}}
        if cmd == "task":
            spec, _, prompt = rest.partition(" ")
            m = re.fullmatch(r"([^:@]+)(?::([^@]+))?(?:@(.+))?", spec)
            if not m or m.group(1) not in agents or not prompt.strip():
                return tr("Dùng: /task <agent>[:model][@effort] <nội dung>  — agent: {v}",
                          v=", ".join(agents)), "warn"
            tid = o.add_task(m.group(1), prompt.strip(), model=m.group(2), effort=m.group(3))
            return tr("Đã thêm task #{tid} cho {to}", tid=tid, to=m.group(1)), "ok"
        if cmd == "goal":
            return self.start_goal(rest)
        if cmd == "go":
            n = o.approve(num(rest) if rest else None)
            return (tr("Đã duyệt {n} task", n=n), "ok") if n else (tr("Không có task nháp"), "warn")
        if cmd == "drop":
            g = o.db.goal(num(rest)) if rest else next((x for x in o.db.goals() if x.status == "awaiting"), None)
            if not g or g.status != "awaiting":
                return tr("Không có kế hoạch nháp nào để bỏ"), "warn"
            return tr("Đã bỏ kế hoạch #{gid} ({v} task nháp)", gid=g.id, v=o.discard_plan(g.id)), "info"
        if cmd == "grill":
            sub = rest.lower()
            if sub in ("xong", "done", "chot", "chốt"):
                return o.finish_grill(None), "info"
            if sub in ("bỏ", "bo", "huỷ", "huy", "cancel"):
                return o.cancel_grill(None), "info"
            if sub in ("tiếp", "tiep", "retry"):
                return o.retry_grill(None), "info"
            if not cfg.agents.get(cfg.lead):
                return tr("Không có trưởng nhóm '{lead}' trong cấu hình", lead=cfg.lead), "error"
            o.start_grill(rest)
            return None
        if cmd == "sh":
            return self.run_shell(rest)
        if cmd == "stop":
            jobs = [j for j in self.shell.jobs.values() if j.alive]
            job = self.shell.jobs.get(num(rest)) if rest else (jobs[-1] if jobs else None)
            if not job or not self.shell.stop(job):
                return tr("Không có lệnh nào đang chạy để dừng"), "warn"
            return tr("■ Đã dừng: {cmd}", cmd=job.cmd), "info"
        if cmd in ("term", "team", "board"):
            return "", "", {"open": {"view": cmd}}
        if cmd == "flow":
            name, _, goal = rest.partition(" ")
            if not name or not goal.strip():
                if name and name not in cfg.workflows:
                    return tr("Không có workflow '{name}'", name=name), "warn"
                return "", "", text_box("Workflow", reports.flows_text(cfg))
            res = o.run_workflow(name, goal.strip())
            return (res, "warn") if isinstance(res, str) else None
        if cmd == "assign":
            tid, agent = shlex.split(rest)[:2]
            return o.assign(num(tid), agent), "info"
        if cmd == "edit" and not re.match(r"^#?\d+(\s|$)", rest):  # /edit @file: mở file ở tab Code
            path, line = parse_code_target(rest)
            return "", "", {"open": {"code": {"path": path, "line": line}}}
        if cmd == "edit":
            tid, _, prompt = rest.partition(" ")
            return o.edit(num(tid), prompt.strip()), "info"
        if cmd == "set":
            tid, key, *val = rest.split(maxsplit=2)
            if key not in ("model", "effort"):
                return tr("Dùng: /set <task> model|effort <giá trị|->"), "warn"
            return o.set_task_option(num(tid), key, val[0] if val else None), "info"
        if cmd in ("model", "effort"):
            parts = rest.split(maxsplit=1)
            if not parts or parts[0] not in cfg.agents:
                return tr("Dùng: /{cmd} <agent> <giá trị|->  — agent: {v}", cmd=cmd, v=", ".join(cfg.agents)), "warn"
            a = cfg.agents[parts[0]]
            if len(parts) == 1:  # bảng chọn (như open_picker của TUI)
                items = a.model_choices() if cmd == "model" else list(a.efforts)
                return "", "", {"open": {"picker": {"agent": parts[0], "key": cmd, "items": items,
                                                    "current": a.model if cmd == "model" else a.effort}}}
            return o.set_agent_option(parts[0], cmd, parts[1].strip()), "info"
        if cmd == "models":
            parts = rest.split()
            if parts and parts[0] not in cfg.agents:
                return tr("Dùng: /models [agent] [làm mới] — agent: {v}", v=", ".join(cfg.agents)), "warn"
            if len(parts) > 1:
                msg = await o.discover_models(parts[0])
                o.log("⚙ " + msg)
                self.broadcast(self.hello())
            return "", "", text_box("Model & effort", reports.models_text(cfg, parts[0] if parts else None))
        if cmd == "agents":
            return "", "", text_box("Agent", reports.agents_text(cfg))
        if cmd == "usage":
            names = list(cfg.active_agents())
            o.log(tr("\nĐang hỏi hạn mức từ CLI của {v}…", v=", ".join(names)))

            def done(name: str, c: str, lines: list[str]) -> None:
                o.log(f"📊 {name}" + (f"  ({c})" if c else "") + "\n" + "\n".join("  " + ln for ln in lines))
            self._spawn(self._bg_log(o.usage_all(names, on_done=done)))
            return "", "", text_box(tr("Thống kê"), reports.usage_text(cfg, self.db, o))
        if cmd == "update":
            o.log(tr("Đang kiểm tra bản mới…"))
            self._spawn(self._bg_log(update.run_update(lambda line: o.log("  " + line)),
                                     lambda res: ("✓ " if res[0] else "ℹ ") + res[1]))
            return tr("Đang kiểm tra bản mới…"), "info", {"open": {"task": SYSTEM}}
        if cmd == "setup":
            return "", "", {"open": {"modal": "setup"}}
        if cmd == "custom":
            return "", "", {"open": {"view": "custom"}}  # mục 🧩 Tuỳ chỉnh ở sidebar (popup vẫn mở từ /setup)
        if cmd == "dash":
            return "", "", {"open": {"view": "dash"}}
        if cmd == "flow-setup":
            return "", "", {"open": {"modal": "flow"}}
        if cmd == "theme":
            arg = rest.lower()
            if not arg:
                return "", "", {"open": {"modal": "theme"}}
            if arg in ("light", "dark", "system", "sang", "sáng", "toi", "tối"):  # từ khoá: sáng/tối
                mode = "light" if arg in ("sang", "sáng") else "dark" if arg in ("toi", "tối") else arg
                return "", "", {"open": {"theme": mode}}
            words = arg.split()
            if words[0] in theme.theme_names():  # theme của terminal: lưu cho TUI, web dùng màu nhấn
                st = load_state()
                st["theme"] = words[0]
                save_state(st)
                words = words[1:]
                if not words:
                    return tr("Theme: {v}", v=arg), "ok"
            return self.setup.set_prefs({"accent": " ".join(words)})
        if cmd == "lang":
            code = normalize(rest)
            if not code:
                return tr("Ngôn ngữ: {v} · đổi bằng /lang en hoặc /lang vi", v=LANG_NAMES[get_lang()]), "warn"
            if code == get_lang():
                return tr("Đang dùng {v} rồi", v=LANG_NAMES[code]), "info"
            save_lang(code)
            set_lang(code)
            return tr("✓ Đã đổi ngôn ngữ sang {v}", v=LANG_NAMES[code]), "ok", {"reload": True}
        if cmd in ("code", "open", "vi"):
            path, line = parse_code_target(rest)
            return "", "", {"open": {"code": {"path": path, "line": line}}}
        if cmd == "notify":
            msg, test = notify.command(rest)  # tham số lạ: ValueError → cách dùng
            if test:
                self.push_notices([notify.test_notice()], force=True)
            return msg, "info", {"notify": notify.mode()}
        if cmd == "vim":
            arg = rest.lower()
            if arg in ("on", "off", "bật", "bat", "tắt", "tat"):
                return self.setup.set_prefs({"vim": arg in ("on", "bật", "bat")})
            if arg:
                path, line = parse_code_target(rest)
                return "", "", {"open": {"code": {"path": path, "line": line}}}
            return tr("Phím vim: {v} · /vim on|off · /vim <file> mở file",
                      v=tr("bật") if load_state().get("vim", True) is not False else tr("tắt")), "info"
        if cmd in ("git", "commit", "push", "pull", "fetch", "branch", "checkout", "stash"):
            return await self.git.command(cmd, rest)
        if cmd == "quit":
            return tr("Đóng tab trình duyệt là xong; dừng hẳn server: Ctrl+C ở terminal chạy `ateam web`"), "info"
        if cmd == "retry":
            return o.retry(num(rest)), "info"
        if cmd == "cancel":
            return o.cancel(num(rest)), "info"
        if cmd == "review":
            return o.force_review(num(rest)), "info"
        if cmd == "continue":
            ref, _, req = rest.partition(" ")
            if not req.strip():  # mới có ref: điền sẵn để gõ tiếp yêu cầu
                return "", "", {"open": {"prefill": f"/continue {ref} " if ref else "/continue "}}
            res = o.continue_any(ref, req)
            if isinstance(res, str):
                return res, "warn"
            kind, i = res
            if kind == "goal":
                return tr("↪ Trưởng nhóm đang lập kế hoạch tiếp cho mục tiêu #{i}", i=i), "ok"
            return tr("↪ Task #{i}: hỏi tiếp {agent}", i=i, agent=self.db.task(i).agent), "ok", {"open": {"task": i}}
        if cmd == "note":
            o.note(rest)
            return tr("Đã ghi chú."), "ok"
        if cmd == "diff":
            return "", "", {"open": {"diff": num(rest)}}
        if cmd == "merge":
            return await o.merge(num(rest)), "info"
        if cmd == "reject":
            tid, _, fb = rest.partition(" ")
            return await o.reject(num(tid), fb.strip() or None), "info"
        if cmd == "verify":
            v = cfg.verify
            if not rest:
                return (tr("Lệnh kiểm tra: {v} · sửa tối đa {max_fix_attempts} lần", v=v.command or tr("(tắt)"),
                           max_fix_attempts=v.max_fix_attempts)
                        + (tr(" · người sửa: {fix_agent}", fix_agent=v.fix_agent) if v.fix_agent else "")), "info"
            if rest.lower() in ("off", "-", "tắt"):
                save_project_setting(self.root, "verify_command", None)
                v.command = ""
                o.log(tr("⚙ Tắt kiểm tra sau mỗi task cho dự án này."))
            else:
                save_project_setting(self.root, "verify_command", rest)
                v.command = rest
                o.log(tr("⚙ Kiểm tra sau mỗi task: `{rest}` (sửa tối đa {max_fix_attempts} lần)", rest=rest,
                         max_fix_attempts=v.max_fix_attempts))
            return None
        if cmd == "cooldown":
            parts = rest.split()
            mins = None if len(parts) < 2 or parts[1].lower() in ("off", "0", "-") else int(parts[1])
            return o.set_cooldown_manual(parts[0], mins), "info"
        if cmd == "compact":
            ok, msg = await o.compact(rest)
            return msg, "ok" if ok else "warn"
        if cmd == "clear":
            return await self.handle({"op": "clear"})
        if cmd in ("pause", "resume"):
            return await self.handle({"op": "pause", "on": cmd == "pause"})
        if cmd == "log":
            return "", "", {"open": {"task": SYSTEM if rest in ("", "sys", "0") else num(rest)}}
        raise AssertionError(f"/{cmd}: not handled in WebApp.command")  # test_web bắt lệnh TUI chưa có ở web


def print_remote(remote: Remote, only: str = "") -> None:
    """In các URL kèm token + mã QR (quét bằng điện thoại) ra terminal chạy `ateam web`."""
    for label, url in remote.urls():
        if only and not url.startswith(only):
            continue
        print(f"\n📱 {label}: {url}")
        if only or url.startswith("https://") or "127.0.0.1" not in url:
            print(QR(url).to_text())


def serve(root: Path, cfg: Config, db: DB, port: int, remote: Remote | None = None) -> None:
    """Chạy server tới khi Ctrl+C."""
    wa = WebApp(root, cfg, db, port, remote)
    web.run_app(wa.make_app(), host=wa.remote.host, port=port, print=None, access_log=None)
