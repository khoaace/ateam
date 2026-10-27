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
import base64
import json
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path

from aiohttp import WSMsgType, web

from . import (__version__, clipboard, gitops, lsp, mentions, notes, notify, palette, projects, quota, reports, rules,
               shell, theme, todos, update, wizard)
from .config import Config, found_models, load_config, load_state, needs_setup, save_project_setting, save_state
from .db import DB, GOAL_ENDED, Goal, Task
from .qr import QR
from .web_auth import Remote, auth_middleware, load_token, security_headers
from .i18n import LANG_NAMES, LANGS, get_lang, normalize, save_lang, set_lang, tr
from .orchestrator import SYSTEM, Orchestrator
from .opencode import ATTACHMENT_MAX
from .pty_session import PtySession
from .grid import SHELL, WHERE, GridHub, preset_names
from .logtail import read_tail
from .palette import safe_path
from .web_code import CodeWeb
from .web_git import GitWeb
from .web_setup import SetupWeb
from .web_skills import READONLY as SKILL_READONLY, OPS as SKILL_OPS, SLOW as SKILL_SLOW, SkillsOps

STATIC = Path(__file__).with_name("webui")
LOG_TAIL = 600       # số dòng cuối của log gửi khi mở 1 task
LOG_FLUSH = 0.1      # gom dòng log rồi gửi một lần (agent in hàng trăm dòng/giây)
IMAGE_MAX = 20 * 1024 ** 2  # ảnh dán vào ô nhập
TASK_LIMIT = 400     # bảng việc gửi tối đa ngần này task gần nhất
QUOTA_EVERY = 60     # giây giữa hai lần hỏi hạn mức 5h/tuần của các CLI (khi có trình duyệt đang mở)


def code_prefs(st: dict) -> dict:
    """Tuỳ chọn tab Code của web (state.json): format khi lưu, tự lưu — mặc định tắt."""
    return {"fmt_save": bool(st.get("fmt_save")), "autosave": bool(st.get("autosave"))}


def ui_strings() -> dict[str, str]:
    """Mọi chữ hiển thị trên trang web (JS chỉ dùng các khoá này — tests/test_web.py bắt chữ viết thẳng trong JS)."""
    return {
        "board": tr("Bảng việc"), "team": tr("Agents"), "terminal": tr("Terminal"), "git": tr("Git"),
        "code": tr("Code"), "syslog": tr("Log hệ thống"), "phone": tr("Điện thoại"),
        "phone_title": tr("Mở trên điện thoại"),
        "phone_hint": tr("Quét mã bằng camera điện thoại. URL chứa token toàn quyền — đừng gửi cho người khác."),
        "phone_ro": tr("Server đang ở chế độ chỉ xem (--readonly)."),
        "phone_local": tr("Server đang chỉ nghe trên máy này. Để mở từ điện thoại, chạy lại với:"),
        "phone_local_lan": tr("cùng Wi-Fi (http, token đi dạng rõ trong LAN)"),
        "phone_local_tunnel": tr("mọi nơi qua Cloudflare Tunnel (https, cần cài cloudflared)"),
        "phone_restart": tr("↻ Chạy lại"), "phone_restarting": tr("↻ Đang chạy lại server…"),
        "phone_restart_fail": tr("Server chưa chạy lại được — xem terminal đang chạy `ateam web`"),
        "phone_tunnel_wait": tr("⏳ Đang mở Cloudflare Tunnel…"),
        "phone_busy_q": tr("{n} lượt agent đang chạy sẽ bị dừng khi chạy lại server (task dở thành lỗi). Chạy lại?"),
        "phone_busy_yes": tr("Dừng & chạy lại"),
        "phone_copy": tr("Chép"), "copied": tr("Đã chép"),
        "readonly_banner": tr("👁 Chế độ chỉ xem — thao tác bị tắt"),
        "custom": tr("Workflows"), "dash": tr("Thống kê"), "dash_today": tr("Hôm nay"), "dash_week": tr("7 ngày"),
        "dash_month": tr("30 ngày"), "dash_runs": tr("{n} lượt"), "dash_failed": tr("{f} lỗi · {r} hết hạn mức"),
        "dash_chart": tr("Token theo ngày (14 ngày)"), "dash_by_agent": tr("Theo agent (30 ngày)"),
        "dash_by_model": tr("Theo model (30 ngày)"), "dash_history": tr("Lịch sử mục tiêu"),
        "dash_no_goals": tr("Chưa có mục tiêu nào. Gõ mục tiêu ở ô dưới để bắt đầu."),
        "handoff_btn": tr("Chuyển cuộc chat này cho agent khác (/handoff)"),
        "quota": tr("Hạn mức"), "quota_title": tr("Hạn mức 5 giờ / tuần"), "quota_refresh": tr("Hỏi lại hạn mức"),
        "quota_loading": tr("Đang hỏi hạn mức các CLI…"), "quota_none": tr("Chưa có CLI nào báo hạn mức (claude, codex, agy)"),
        "quota_used": tr("đã dùng {v}%"), "quota_reset_in": tr("hồi sau {v}"), "quota_reset_past": tr("đã tới giờ hồi"),
        "quota_at": tr("số liệu lúc {v}"),
        "dash_col_runs": tr("Lượt"), "dash_col_time": tr("Thời gian"), "dash_col_failed": tr("Lỗi"),
        "dash_col_real": tr("Số thật"), "dash_result": tr("Kết quả:"), "dash_continue": tr("Tiếp tục mục tiêu"),
        "dash_goal_stats": tr("{n} lượt chạy · {v} · {tok} token ({real}/{n} số thật) · {cost}"), "cu_default": tr("mặc định"), "ob_flow": tr("Cấu hình luồng cố định…"),
        "ob_flow_hint": tr("agent · model · effort cho từng bước của workflow '{name}'"),
        "df_title": tr("Luồng mặc định"), "df_step": tr("Bước"), "df_agent_default": tr("(mặc định của agent)"),
        "df_review": tr("Trưởng nhóm review khi xong"), "df_default": tr("Chạy khi gõ mục tiêu (luồng mặc định)"),
        "df_hint": tr("Gõ mục tiêu (không kèm /goal) là chạy workflow này: mỗi bước một task, bước sau chờ bước "
                      "trước. Chọn agent, model, effort cho từng bước — sửa tiêu đề/prompt hay thêm bước ở trang "
                      "Workflows."),
        "df_hint_lead": tr("Gõ mục tiêu (không kèm /goal) là trưởng nhóm lập kế hoạch và tự quyết viết test / review "
                           "code theo preset dưới đây (lưu riêng cho dự án này); ateam tự kiểm tra cuối khi có task "
                           "chạy song song."),
        "df_flow": tr("Luồng"), "df_quality": tr("Chất lượng"), "df_need_verify": tr(" · kiểm tra cuối cần lệnh /verify"),
        "cu_step_type": tr("Loại"),
        "cu_type_hint": tr("Loại bước: code = làm việc · review = agent khác xem thay đổi của các bước nó chờ, sửa lỗi "
                           "nhỏ · verify = ateam chạy lệnh kiểm tra (/verify) trên kết quả gộp, fail mới gọi agent của "
                           "bước sửa · ⏸ duyệt = dừng chờ bạn xem kết quả: Tiếp tục, Dừng, hoặc góp ý để bước trước "
                           "làm lại."),
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
        "bl_list": tr("Danh sách"), "bl_kanban": tr("Kanban"), "bl_jump": tr("Tới nhanh"),
        "bl_adhoc": tr("Ngoài kế hoạch"), "bl_adhoc_short": tr("ngoài KH"),
        "bl_adhoc_hint": tr("task giao tay cho từng agent, luôn ở trên cùng"),
        "bl_add_ph": tr("Giao task ngoài kế hoạch cho agent… (Enter)"), "bl_add": tr("Giao"),
        "bl_planning": tr("Trưởng nhóm đang lập kế hoạch…"), "bl_awaiting": tr("Kế hoạch chờ duyệt ở khung phía trên"),
        "bl_grilling": tr("Trưởng nhóm đang hỏi để chốt yêu cầu — trả lời ở khung phía trên"),
        "bl_no_tasks": tr("Chưa có task"), "bl_plans": tr("kế hoạch"), "bl_overview": tr("Tổng quan"),
        "bl_need": tr("Cần bạn"), "bl_need_none": tr("Không có việc nào chờ bạn"),
        "continue": tr("↪ Tiếp tục"), "followups": tr("{n} lần tiếp"),
        "cancel_plan": tr("Huỷ"), "cancel_plan_hint": tr("Dừng trưởng nhóm đang lập kế hoạch cho mục tiêu này"),
        "reassign": tr("Đổi agent"), "reassign_title": tr("Đổi agent cho task #{id}"),
        "reassign_hint": tr("Chọn agent khác — task chạy lại ngay với agent đó (prompt đầy đủ, phiên mới)"),
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
        "placeholder": tr("Nhập mục tiêu cho trưởng nhóm · / lệnh · ! lệnh terminal · @ nhắc file"),
        "placeholder_wf": tr("Nhập mục tiêu (chạy theo workflow '{wf}') · / lệnh · ! lệnh terminal · @ nhắc file"),
        "mode_lead": tr("★ Trưởng nhóm"), "mode_lead_full": tr("★ Trưởng nhóm lập kế hoạch"),
        "mode_lead_desc": tr("chia việc theo mục tiêu (mặc định)"),
        "mode_head": tr("Gõ mục tiêu sẽ chạy theo…"), "mode_no_flows": tr("chưa có workflow — tạo ở 🔀 Workflows"),
        "mode_pick_title": tr("Gõ mục tiêu → trưởng nhóm lập kế hoạch hay chạy một workflow (đổi luồng mặc định)"),
        "cu_make_default": tr("★ Đặt mặc định"), "cu_unset_default": tr("☆ Bỏ mặc định"),
        "placeholder_grill": tr("Trả lời câu hỏi của trưởng nhóm (Enter) · gõ số để chọn phương án"),
        "send_hint": tr("Enter gửi · Shift+Enter xuống dòng · ⌘V / kéo-thả để dán ảnh"),
        "update_now": tr("Cập nhật"), "upd_restarting": tr("↻ Đã cập nhật — đang khởi động lại server…"),
        "upd_busy": tr("Đã cập nhật ateam. {n} lượt agent đang chạy — khởi động lại sẽ dừng chúng (task dở thành lỗi, /retry sau)."),
        "upd_restart": tr("↻ Khởi động lại"), "retry": tr("Chạy lại"), "cancel": tr("Huỷ task"), "delete_task": tr("Xoá"),
        "delete_task_q": tr("Xoá task #{id}?"),
        "delete_task_text": tr("Xoá hẳn task khỏi bảng việc cùng file log và nhánh git của nó — không hoàn tác được."), "diff": tr("Xem diff"), "merge": tr("Merge"),
        "reject": tr("Từ chối"), "reject_ph": tr("Góp ý (để trống = chỉ từ chối, có góp ý = giao làm lại)"),
        "continue_task": tr("Hỏi tiếp"), "close": tr("Đóng"),
        "tab_log": tr("Log"), "tab_prompt": tr("Nội dung"), "tab_result": tr("Kết quả"),
        "chat_ph": tr("💬 Nhắn {agent}… (Enter gửi · /new: cuộc mới · /term: CLI thật)"),
        "chat_send": tr("Gửi"),
        "effort_none": tr("model này không chỉnh effort (CLI tự chọn)"),
        "open_term": tr("Mở CLI thật của agent (tiếp tục phiên chat) trong terminal"),
        "pty_exit": tr("CLI đã thoát (mã {rc}) — đóng cửa sổ này"),
        "grid": tr("Lưới"), "g_add": tr("＋ Thêm agent"), "g_layout": tr("Bố cục"), "g_to": tr("Gõ tới"),
        "g_one": tr("◉ Ô đang chọn"), "g_all": tr("⇉ Tất cả {n} ô"), "g_full": tr("⛶ Toàn màn hình"),
        "g_zoom": tr("Phóng to / thu lại ô"), "g_close": tr("Đóng terminal (dừng CLI)"),
        "g_restart": tr("Mở lại CLI (tiếp tục phiên)"), "g_more": tr("Thêm"),
        "g_empty_t": tr("Thêm agent vào ô này"),
        "g_empty_s": tr("Mỗi ô là CLI thật trong terminal · kéo tiêu đề ô để đổi chỗ, kéo khe để đổi kích thước"),
        "g_hint": tr("Kéo ⠿ tiêu đề ô để di chuyển · kéo khe giữa các ô để đổi kích thước · đúp-click khe: chia đều"),
        "g_drop_left": tr("Trái"), "g_drop_right": tr("Phải"), "g_drop_top": tr("Trên"), "g_drop_bottom": tr("Dưới"),
        "g_drop_center": tr("⇄ Đổi chỗ"),
        "g_run": tr("đang chạy"), "g_exit": tr("đã thoát ({rc})"), "g_off": tr("chưa mở"),
        "g_off_msg": tr("CLI chưa chạy — bấm để mở (tiếp tục phiên gần nhất)"),
        "g_exit_msg": tr("CLI đã thoát (mã {rc}) — bấm ⟲ để mở lại"),
        "g_add_title": tr("Thêm agent vào lưới · mở CLI thật trong một ô mới"),
        "g_cli": tr("CLI"), "g_model": tr("Model & effort"), "g_session": tr("Phiên"),
        "g_place": tr("Đặt ở đâu"), "g_new": tr("Phiên mới"), "g_resume": tr("Tiếp tục phiên gần nhất"),
        "g_resume_s": tr("--resume phiên chat/task gần nhất của agent"), "g_new_s": tr("CLI mở cuộc trò chuyện mới"),
        "g_place_auto": tr("Theo bố cục"), "g_place_right": tr("Chia ô chọn: phải"),
        "g_place_bottom": tr("Chia ô chọn: dưới"), "g_open": tr("▶ Mở terminal"),
        "g_shell": tr("⌨ Terminal trống"), "g_shell_s": tr("shell của bạn trong thư mục dự án, không mở agent"),
        "g_default": tr("mặc định"), "g_no_tty": tr("agent tuỳ chỉnh: không mở được ở chế độ tương tác"),
        "g_installed": tr("✓ đã cài"), "g_missing": tr("✗ chưa cài"), "g_bcast_in": tr("Nhận phím khi gửi tất cả"),
        "g_close_q": tr("Dừng CLI {agent} trong ô này và bỏ ô khỏi lưới?"), "g_close_yes": tr("Đóng"),
        "g_split_r": tr("◫ Chia dọc · thêm agent bên phải"), "g_split_b": tr("⊟ Chia ngang · thêm agent bên dưới"),
        "no_log": tr("Chưa có log."), "no_result": tr("Chưa có kết quả."), "error": tr("Lỗi"),
        "md_note": tr("Ghi chú"), "md_summary": tr("Tóm tắt"), "md_delegate": tr("Giao việc"), "md_ask": tr("Hỏi bạn"),
        "started": tr("Bắt đầu"), "duration": tr("Thời gian"),
        "deps": tr("Phụ thuộc"), "attempts": tr("Lần thử"), "branch": tr("Nhánh"),
        "lead": tr("trưởng nhóm"), "idle": tr("rảnh"), "not_installed": tr("chưa cài"),
        "cooldown": tr("nghỉ tới {v}"), "agent_running": tr("đang chạy {n} việc"),
        "jobs": tr("Lệnh terminal"), "no_jobs": tr("Chưa chạy lệnh nào"),
        "sh_title": tr("Shell"), "sh_new": tr("Mở shell mới ở thư mục dự án"), "sh_exited": tr("đã thoát"),
        "sh_reopen": tr("Mở lại"), "sh_exit_msg": tr("Shell đã thoát (mã {rc}) — ↻ Mở lại để chạy tiếp"), "sh_close": tr("Đóng"),
        "sh_close_hint": tr("Đóng shell (dừng mọi thứ đang chạy trong đó)"), "sh_run_in": tr("Chạy trong shell"),
        "sh_run_in_hint": tr("Chạy lệnh này trong một shell tương tác — cho lệnh cần gõ trả lời (npm init, ssh…)"),
        "sh_task": tr("Shell"),
        "sh_task_hint": tr("Mở shell trong worktree của task — sửa tay, chạy test; ✓ Merge sẽ gồm cả phần bạn sửa"),
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
        "git_filter_branch": tr("Lọc nhánh theo tên… (Enter: chuyển sang nhánh khớp đầu tiên)"),
        "git_no_match": tr("Không có nhánh nào khớp"), "git_local": tr("Nhánh local"), "git_remote": tr("Nhánh remote"),
        "git_continue": tr("Tiếp tục {v}"), "cf_resolve": tr("Giải quyết xung đột"),
        "cf_ai_all": tr("Nhờ agent giải quyết tất cả"), "cf_title": tr("Giải quyết xung đột"),
        "cf_block": tr("Xung đột {i}/{n} · dòng {line}"), "cf_current": tr("Hiện tại"), "cf_incoming": tr("Bên đến"),
        "cf_base": tr("Bản gốc"), "cf_keep_current": tr("Giữ hiện tại"), "cf_keep_incoming": tr("Lấy bên đến"),
        "cf_keep_both": tr("Giữ cả hai"), "cf_all_current": tr("Cả file: hiện tại"),
        "cf_all_incoming": tr("Cả file: bên đến"), "cf_ai": tr("Nhờ agent"), "cf_edit": tr("Sửa trong Code"),
        "cf_done": tr("Đánh dấu đã xong"), "cf_none": tr("Không còn dấu xung đột trong file — xem lại rồi Đánh dấu đã xong."),
        "cf_ours_deleted": tr("Phía hiện tại đã xoá file này, bên đến sửa nó."),
        "cf_theirs_deleted": tr("Bên đến đã xoá file này, phía hiện tại sửa nó."),
        "cf_binary": tr("File nhị phân hoặc không phải UTF-8 — chỉ chọn được nguyên bản một phía."),
        "cf_rebase": tr("Đang rebase: \"hiện tại\" là nhánh đích, \"bên đến\" là commit của bạn đang được áp lại."),
        "cf_resolved": tr("Đã giải quyết xong {path}"),
        "cf_empty": tr("(trống)"),
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
        "busy_cmd": tr("⏳ Đang chạy {v}…"),
        "busy_saving": tr("⏳ Đang lưu…"),
        "busy_loading": tr("⏳ Đang tải…"),
        "busy_replacing": tr("⏳ Đang thay thế…"),
        "busy_opening": tr("⏳ Đang mở {v}…"),
        "busy_opening_proj": tr("⏳ Đang mở dự án…"),
        "git_committing": tr("⏳ Đang commit… (hook có thể chạy lâu)"),
        "git_ai_resolving": tr("🤖 AI đang giải xung đột…"),
        "git_merging": tr("⏳ Đang merge…"),
        "git_checking_out": tr("⏳ Đang chuyển nhánh…"),
        "git_continuing": tr("⏳ Đang tiếp tục…"),
        "git_working": tr("⏳ Đang chạy git…"),
        "git_discard_title": tr("↺ Bỏ thay đổi"), "git_discard_yes": tr("Bỏ thay đổi"),
        "git_discard_q": tr("Bỏ mọi thay đổi chưa stage của {path}?"),
        "git_discard_dir": tr("Bỏ mọi thay đổi chưa stage (file chưa theo dõi bị XOÁ) của {n} file trong {path}?"),
        "git_tree": tr("📁 Thư mục"), "git_list": tr("≡ Danh sách"), "git_tree_hint": tr("Danh sách / cây thư mục (t)"),
        "git_discard_all": tr("↺ Bỏ tất cả"), "git_discard_all_title": tr("↺ Bỏ tất cả thay đổi"),
        "git_discard_all_yes": tr("Bỏ tất cả"),
        "git_discard_all_q": tr("Bỏ MỌI thay đổi ({s} file đã stage, {w} file chưa stage) và XOÁ {u} file chưa "
                                "theo dõi? Thư mục về đúng commit cuối — không thể hoàn tác."),
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
        "scm_tab": tr("Thay đổi"),
        "scm_title": tr("Source Control — file thay đổi, bấm để xem diff"),
        "scm_msg": tr("Commit message (⌘Enter) — chưa stage gì: commit tất cả"),
        "scm_commit": tr("Commit"),
        "scm_open_file": tr("Mở file"),
        "scm_stage": tr("Stage"),
        "scm_unstage": tr("Bỏ stage"),
        "scm_open_changes": tr("Xem thay đổi so với git (diff hai cột, sửa được)"),
        "scm_changes_btn": tr("Thay đổi"),
        "diff_revert_chunk": tr("Lấy lại đoạn cũ (bên trái) cho bên phải"),
        "diff_n_changes": tr("{n} đoạn thay đổi"),
        "diff_no_changes": tr("Không có thay đổi"),
        "diff_collapse": tr("Thu gọn các đoạn không đổi"),
        "diff_save": tr("Lưu"),
        "diff_save_first": tr("Lưu file trước khi stage"),
        "diff_l_head": tr("HEAD (commit cuối)"),
        "diff_l_index": tr("Index (đã stage / commit cuối)"),
        "diff_r_index": tr("Index (đã stage) — chỉ đọc"),
        "diff_r_work": tr("Thư mục làm việc — sửa được"),
        "diff_tab_index": tr("(Index)"),
        "diff_tab_work": tr("(Working Tree)"),
        "diff_ro_hint": tr("Bản đã stage — chỉ đọc · F7 / ⇧F7 đoạn sau / trước"),
        "diff_edit_hint": tr("Sửa bên phải rồi ⌘S lưu · → lấy lại đoạn cũ · F7 / ⇧F7 đoạn sau / trước"),
        "hunk_prev": tr("Đoạn trước"), "hunk_next": tr("Đoạn sau"), "split_view": tr("2 cột"),
        "open_in_code": tr("Mở trong Code"), "diff_binary": tr("File nhị phân — không hiện nội dung"),
        "diff_empty": tr("File rỗng"), "diff_renamed": tr("Chỉ đổi tên, nội dung giữ nguyên"),
        "diff_truncated": tr("File dài — chỉ hiện 4000 dòng đầu"),
        "diff_keys": tr("n/p: file · [ ]: đoạn đổi · s: 1 cột / 2 cột · e: mở trong Code · Esc: đóng"),
        # --- tab Code
        "code_filter": tr("Tìm file… (Enter mở · ⌘P)"), "code_nofile": tr("Không có file"),
        # command palette tab Code (palette.py; chữ dùng chung với TUI)
        "pal_ph": tr("Tên file… · > lệnh · @ symbol · # symbol dự án · :dòng · /tìm trong file"),
        "pal_foot": tr("↑↓ chọn · Enter mở · > lệnh · @ symbol · # cả dự án · : dòng · / tìm trong file · Esc đóng"),
        "pal_recent": tr("Mở gần đây"), "pal_hint": tr("Gõ tên file · > lệnh · @ symbol · # symbol dự án · :dòng · /tìm trong file"),
        "pal_nocmd": tr("Không có lệnh nào khớp"), "pal_nosym": tr("Không thấy symbol (hàm, class, heading) nào"),
        "pal_line": tr("Tới dòng {v}"), "pal_line_hint": tr("Gõ số dòng (1–{n})"),
        "pal_find_hint": tr("Gõ chữ cần tìm trong file"), "pal_nofind": tr("Không thấy \"{v}\" trong file"),
        "pal_nofile": tr("Không có file nào khớp — > để xem lệnh"),
        "pal_noopen": tr("Chưa mở file nào — gõ tên file để mở"),
        "proj_ph": tr("Tên dự án gần đây, hoặc đường dẫn: ~/code/app, ../app-khac"),
        "proj_foot": tr("↑↓ chọn · Tab đi vào thư mục · Enter mở · ⌘/Ctrl+Enter mở ở cửa sổ mới · Esc đóng"),
        "proj_recent": tr("Dự án gần đây"), "proj_current": tr("(đang mở)"),
        "proj_none": tr("Không có thư mục nào khớp"), "proj_hint": tr("Gõ đường dẫn thư mục, vd ~/code/app"),
        "proj_open": tr("Mở folder / dự án khác"),
        "proj_window": tr("Mở ở cửa sổ mới (dự án này vẫn mở)"),
        "proj_popup": tr("Trình duyệt chặn cửa sổ mới — bấm để mở"), "proj_popup_open": tr("Mở"),
        "proj_busy": tr("Đang có agent chạy"),
        "proj_busy_q": tr("{n} lượt agent đang chạy sẽ bị dừng (task dở thành lỗi — quay lại dự án này thì "
                          "/retry).\nMở {v}?"),
        "proj_busy_yes": tr("Dừng & mở"),
        "proj_switching": tr("↪ Đang mở dự án khác…"),
        "proj_switch_fail": tr("Không kết nối lại được — xem terminal đang chạy `ateam web` (có thể đã đổi cổng)"),
        "proj_unsaved_q": tr("Tab 📝 Code còn file chưa lưu: {v}\nBỏ các thay đổi và mở dự án khác?"),
        "proj_unsaved_yes": tr("Bỏ thay đổi & mở"),
        "skills": tr("Skills"), "sk_search": tr("Tìm skill…"), "sk_count": tr("{on}/{n} skill bật cho dự án"),
        "sk_hint": tr("Bật = trưởng nhóm thấy skill khi lập kế hoạch và tự gắn vào task. Gõ $tên-skill trong mục tiêu, "
                      "/task hay chat để dùng bất kỳ skill nào. Skill tạo mới lưu ở {v}."),
        "sk_empty": tr("Chưa có skill nào"),
        "sk_empty_hint": tr("Tạo skill, nhờ ✨ AI viết, hoặc cài từ GitHub (vd anthropics/skills)."),
        "sk_github": tr("Cài từ GitHub"), "sk_ai": tr("AI viết skill"), "sk_new": tr("Tạo skill"),
        "sk_toggle": tr("Bật cho dự án (trưởng nhóm thấy khi lập kế hoạch)"), "sk_no_desc": tr("(chưa có mô tả)"),
        "sk_others": tr("+{n} bản khác"), "sk_scripts": tr("có script"),
        "sk_scripts_hint": tr("Skill kèm script — agent có thể chạy chúng. Chỉ dùng skill từ nguồn bạn tin."),
        "sk_copy": tr("Chép $tên"), "sk_copied": tr("Đã chép {v} — dán vào mục tiêu, /task hay chat"),
        "sk_edit": tr("Sửa"), "sk_del": tr("Xoá skill"), "sk_del_q": tr("Chuyển skill \"{v}\" vào Thùng rác?"),
        "sk_import": tr("Chép vào thư viện ateam"),
        "sk_overwrite_q": tr("Thư viện đã có skill \"{v}\" — ghi đè?"), "sk_files": tr("File trong skill"),
        "sk_view": tr("Xem skill"), "sk_review": tr("Xem lại skill rồi lưu"),
        "sk_f_name": tr("Tên (a-z, 0-9, dấu gạch nối) — gõ $tên để dùng"),
        "sk_f_desc": tr("Mô tả: skill làm gì và khi nào dùng (trưởng nhóm dựa vào đây để chọn)"),
        "sk_f_desc_ph": tr("vd: Quy trình phát hành bản mới: tăng version, CHANGELOG, test, push. Dùng khi phát hành."),
        "sk_f_body": tr("Hướng dẫn cho agent (markdown)"),
        "sk_bad_name": tr("Tên chỉ gồm a-z, 0-9 và dấu gạch nối (không ở đầu/cuối, không hai gạch liền)"),
        "sk_exists": tr("Thư viện đã có skill \"{v}\" — lưu sẽ ghi đè"),
        "sk_ai_hint": tr("Mô tả skill bạn muốn — agent viết SKILL.md (tiếng Anh, cho agent đọc), bạn xem lại rồi lưu."),
        "sk_ai_ph": tr("Mô tả skill bạn muốn (vd: quy trình deploy lên Cloudflare Pages)"),
        "gate_title": tr("Chờ bạn duyệt"), "gate_head": tr("Bước duyệt #{id} của workflow"),
        "sk_from_goal": tr("Lưu thành skill"),
        "wf_from_goal": tr("Lưu thành workflow"),
        "wf_from_goal_hint": tr("Trưởng nhóm khái quát cách đội đã làm mục tiêu #{id} thành workflow dùng lại được "
                                "(thay chi tiết bằng {goal}) — bạn xem lại rồi lưu."),
        "wf_from_goal_wait": tr("🔀 {lead} đang khái quát mục tiêu thành workflow…"),
        "sk_from_goal_hint": tr("Agent rút cách đội đã làm mục tiêu #{id} thành skill dùng lại được — bạn xem lại rồi lưu."),
        "sk_focus_ph": tr("Trọng tâm (không bắt buộc), vd: chỉ phần build và deploy"),
        "sk_ai_agent": tr("Agent viết"), "sk_ai_go": tr("Viết"), "sk_ai_busy": tr("Agent đang viết skill…"),
        "sk_gh_hint": tr("Dán owner/repo hoặc link GitHub (cả …/tree/<nhánh>/<thư mục>); ateam tải repo rồi cho bạn chọn skill."),
        "sk_gh_fetch": tr("Tìm skill"), "sk_gh_install": tr("Cài skill đã chọn"),
        "sk_gh_busy": tr("Đang tải repo…"), "sk_n_files": tr("{n} file"), "sk_in_lib": tr("đã có trong thư viện"),
        "sk_gh_overwrite": tr("Ghi đè skill đã có trong thư viện"),
        "sk_gh_trust": tr("Skill được gửi kèm prompt cho agent và có thể kèm script — chỉ cài từ nguồn bạn tin."),
        "sk_gh_pick": tr("Chọn ít nhất một skill"),
        "rules_title": tr("📏 Rule của dự án"),
        "rules_hint": tr("Mọi agent phải tuân theo: ateam gửi kèm rule ở đầu mỗi prompt (task, chat, lập kế hoạch, "
                         "review, commit message). Lưu riêng máy này: {v}"),
        "rules_add": tr("+ Thêm rule"), "rules_empty": tr("Chưa có rule nào"),
        "rules_native": tr("File rule có sẵn trong repo — CLI tự đọc, ateam không gửi kèm"),
        "rules_reads": tr("{v} tự đọc"), "rules_all": tr("mọi agent"), "rules_open": tr("Mở"),
        "rules_edit": tr("✎ Sửa rule"), "rules_new": tr("+ Thêm rule"),
        "rules_f_title": tr("Tiêu đề (không bắt buộc)"), "rules_f_title_ph": tr("vd: Commit message tiếng Việt"),
        "rules_f_text": tr("Nội dung — agent nhận nguyên văn"),
        "rules_f_targets": tr("Áp dụng cho (không chọn gì = mọi agent)"), "rules_f_on": tr("Bật"),
        "rules_save": tr("Lưu"), "rules_del": tr("Xoá rule"), "rules_del_q": tr("Xoá rule \"{v}\"?"),
        "rules_up": tr("Lên"), "rules_down": tr("Xuống"), "rules_toggle": tr("Bật/tắt"),
        "pal_new": tr("📄 File mới"), "pal_path": tr("đường/dẫn/file.ext"),
        "pal_new_dir": tr("📁 Thư mục mới"), "pal_dir_path": tr("đường/dẫn/thư-mục"),
        "ctx_new_dir_here": tr("Thư mục mới ở đây…"),
        "code_side_resize": tr("Kéo để đổi độ rộng · bấm đúp: về mặc định"),
        "pal_rename": tr("✎ Đổi tên / chuyển {v}", v="{v}"), "pal_delete": tr("Xoá file"),
        "pal_delete_q": tr("Đưa {v} vào Thùng rác?", v="{v}"), "pal_delete_yes": tr("Xoá"),
        "pal_choose_agent": tr("Chọn agent"), "pal_ask": tr("Hỏi {agent} về {v}", agent="{agent}", v="{v}"),
        "pal_task": tr("Giao task cho {agent} về {v}", agent="{agent}", v="{v}"),
        "pal_ask_ph": tr("vd: giải thích đoạn này / viết test cho hàm này"),
        "pal_asked": tr("Đã hỏi {agent} — xem trả lời ở tab 🤖 Agents", agent="{agent}"),
        "pal_assigned": tr("Đã giao cho {agent}: {v}", agent="{agent}", v="{v}"),
        "pal_copied": tr("Đã chép {v}", v="{v}"), "pal_save_first": tr("Lưu file trước khi đổi tên"),
        "pal_line1": tr("(dòng {a})", a="{a}"), "pal_lines": tr("(dòng {a}–{b})", a="{a}", b="{b}"),
        "pal_wrap_on": tr("Xuống dòng mềm: bật"), "pal_wrap_off": tr("Xuống dòng mềm: tắt"),
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
        "code_md_edit": tr("Sửa"), "code_md_split": tr("Chia đôi"), "code_md_view": tr("Xem trước"),
        "code_md_title": tr("Xem trước markdown (Ctrl/⌘+Shift+V đổi chế độ)"),
        "code_load_fail": tr("Không nạp được editor (vendor/codemirror.js)"),
        "code_net_fail": tr("Mất kết nối tới ateam web — thử lại sau"), "code_refresh": tr("Làm mới danh sách file"),
        "code_changed_tab": tr("{path} vừa đổi trên đĩa (có thể do agent sửa) trong lúc bạn đang sửa dở", path="{path}"),
        "code_saved_all": tr("Đã lưu {n} file", n="{n}"),
        "code_saved_some": tr("Đã lưu {n} file · chưa lưu: {v}", n="{n}", v="{v}"),
        "ctx_open": tr("Mở"), "ctx_new_here": tr("File mới ở đây…"), "ctx_search_in": tr("Tìm trong thư mục này"),
        "ctx_rename": tr("Đổi tên / chuyển…"), "ctx_delete": tr("Xoá (vào Thùng rác)"),
        "ctx_copy_path": tr("Chép đường dẫn"), "ctx_git_diff": tr("Xem thay đổi git"),
        "git_st_M": tr("Đã sửa"), "git_st_U": tr("Mới, chưa theo dõi"), "git_st_A": tr("Đã stage (mới)"),
        "git_st_C": tr("Xung đột"), "git_st_D": tr("Đã xoá"), "git_st_R": tr("Đổi tên"), "git_st_T": tr("Đổi kiểu file"),
        "git_hunk_add": tr("Dòng mới so với HEAD"), "git_hunk_mod": tr("Đã sửa — nội dung ở HEAD:"),
        "git_hunk_del": tr("Đã xoá — nội dung ở HEAD:"), "git_hunk_revert": tr("Hoàn tác đoạn này"),
        "code_reloaded_by": tr("File đổi trên đĩa ({v} đang chạy task) — đã nạp lại", v="{v}"),
        "code_running": tr("{v} đang chạy", v="{v}"),
        "sr_outline": tr("Outline"), "outline_empty": tr("Không có symbol (hàm, class, heading) nào"),
        "pal_goto_symbol": tr("Tới symbol trong file (@)"), "code_empty_dir": tr("(thư mục trống)"),
        "pal_ws_hint": tr("Gõ tên hàm / class — tìm trong cả dự án"), "pal_ws_none": tr("Không thấy symbol nào khớp trong dự án"),
        "pal_ws_partial": tr("Dự án lớn — mới quét một phần, gõ lại sau vài giây để thấy thêm"),
        "pal_media": tr("Ảnh / PDF — không có dòng hay symbol"),
        "def_none": tr("Không thấy định nghĩa của {v}", v="{v}"), "def_noword": tr("Đặt con trỏ vào tên hàm / class cần tìm"),
        "lsp_busy": tr("Đang hỏi language server…"), "lsp_outside": tr("Nằm ngoài dự án: {v}", v="{v}"),
        "refs_title": tr("Chỗ dùng {v} ({n})", v="{v}", n="{n}"), "refs_none": tr("Không thấy chỗ nào dùng {v}", v="{v}"),
        "defs_title": tr("Định nghĩa của {v}", v="{v}"),
        "split_need": tr("Mở thêm một file để chia đôi"), "ctx_open_right": tr("Mở bên phải"),
        "mru_title": tr("File vừa dùng — giữ ⌥ và bấm Tab để đổi, thả ⌥ để mở"), "mru_none": tr("Chưa mở file nào khác"),
        "busy_formatting": tr("Đang format…"), "fmt_same": tr("{v}: file đã gọn, không có gì đổi", v="{v}"),
        "fmt_done": tr("Đã format bằng {v}", v="{v}"),
        "code_autosave_off": tr("Tạm tắt tự lưu {path}: file đã đổi trên đĩa — lưu tay (:w) để ghi đè", path="{path}"),
        "code_autosave_chip": tr("tự lưu"), "code_autosave_tip": tr("Tự lưu sau 1,5 giây ngừng gõ — ⌘⇧P › Bật/tắt tự lưu"),
        "ai_edit_title": tr("Sửa {v} bằng AI", v="{v}"),
        "ai_edit_ph": tr("Muốn sửa gì? vd: thêm xử lý lỗi, đổi sang async, viết docstring…"),
        "ai_hint": tr("Enter gửi · Shift+Enter xuống dòng · Esc huỷ"), "ai_go": tr("Sửa"),
        "ai_wait": tr("AI đang sửa đoạn trước — chờ xong đã"),
        "ai_busy_edit": tr("✨ {agent} đang sửa…", agent="{agent}"), "ai_busy_explain": tr("✨ {agent} đang đọc code…", agent="{agent}"),
        "ai_stale": tr("File đã đổi trong lúc chờ AI — bỏ kết quả, thử lại"),
        "ai_same": tr("{agent} không đổi gì đoạn này", agent="{agent}"),
        "ai_review": tr("{agent} đã sửa — duyệt từng đoạn hoặc:", agent="{agent}"),
        "ai_accept": tr("Chấp nhận"), "ai_reject": tr("Bỏ"), "ai_rejected": tr("Đã bỏ phần AI sửa"),
        "ai_explain_title": tr("{agent} giải thích {v}", agent="{agent}", v="{v}"), "ai_copy": tr("Chép câu trả lời"),
        "code_running_tip": tr("Agent đang chạy task ngay trong thư mục dự án (chế độ shared) — file đang mở có thể bị sửa"),
        # --- gợi ý ô nhập
        "cmds": tr("Lệnh"), "sg_agent": tr("Agent"), "sg_agent_task": tr("Agent · thêm :model hoặc @effort"),
        "sg_agent_focus": tr("Agent · phóng to để chat riêng"), "sg_agent_chat": tr("Agent · rồi gõ tin nhắn"),
        "sg_agent_grid": tr("Mở CLI thật trong một ô lưới"), "sg_shell": tr("Terminal — shell của bạn trong thư mục dự án"),
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
        "sound": tr("Âm thanh"), "sound_on": tr("Phát âm thanh khi có thông báo"), "sound_volume": tr("Âm lượng"),
        "sound_test": tr("Nghe thử"),
        "todo": tr("To-do"), "todo_ph": tr("Thêm việc…  #tag  !cao  @mai 17:00"),
        "todo_left": tr("{n} việc chưa xong"), "todo_clear": tr("Dọn việc đã xong"), "todo_empty": tr("Chưa có việc nào"),
        "todo_where": tr("Lưu riêng cho dự án này ở {path} — ngoài thư mục dự án, dùng chung tag với Ghi chú."),
        "todo_edit": tr("Bấm đúp để sửa"), "todo_del": tr("Xoá"), "todo_search": tr("Tìm việc…"),
        "todo_group": tr("Nhóm theo"), "grp_due": tr("Hạn"), "grp_tag": tr("Tag"), "grp_pri": tr("Ưu tiên"),
        "grp_manual": tr("Thủ công"), "f_due_all": tr("Hạn: tất cả"), "f_pri_all": tr("Ưu tiên: tất cả"),
        "pri_0": tr("Không"), "pri_1": tr("Thấp"), "pri_2": tr("Vừa"), "pri_3": tr("Cao"),
        "todo_hide_done": tr("Ẩn việc đã xong"), "todo_nomatch": tr("Không có việc nào khớp bộ lọc"),
        "todo_pop_open": tr("Mở tab To-do"), "todo_pop_none": tr("Không còn việc nào chưa xong 🎉"),
        "tag_all": tr("tất cả"), "tag_manage": tr("⚙ quản lý"), "tag_manage_btn": tr("⚙ Quản lý tag"),
        "b_over": tr("Quá hạn"), "b_today": tr("Hôm nay"), "b_week": tr("Tuần này"), "b_later": tr("Sau này"),
        "b_none": tr("Không có hạn"), "b_done": tr("Đã xong"), "b_untagged": tr("Không có tag"), "b_all": tr("Việc"),
        "due_over_days": tr("quá {n} ngày"), "due_today": tr("hôm nay"), "due_tomorrow": tr("mai"),
        "wd_short": tr("T2 T3 T4 T5 T6 T7 CN"),
        "st_overview": tr("Tổng quan"), "st_over": tr("quá hạn"), "st_today": tr("hôm nay"), "st_open": tr("chưa xong"),
        "st_week": tr("xong tuần này"),
        "dr_todo": tr("Việc #{id}"), "dr_nav": tr("việc khác"), "dr_close": tr("đóng"), "f_pri": tr("Ưu tiên"),
        "f_due": tr("Hạn"), "f_tags": tr("Tag"), "f_status": tr("Trạng thái"), "st_undone": tr("Chưa xong"),
        "st_done": tr("Đã xong"), "f_desc": tr("Mô tả (markdown)"), "md_edit": tr("Sửa"), "md_view": tr("Xem"),
        "md_split": tr("Chia đôi"), "desc_ph": tr("Chi tiết, checklist - [ ] …"), "no_due": tr("Chưa đặt hạn"),
        "q_today": tr("Hôm nay"), "q_tomorrow": tr("Ngày mai"), "q_nextweek": tr("Tuần sau"), "q_pick": tr("Chọn ngày…"),
        "add_tag": tr("＋ thêm tag"), "add_tag_ph": tr("tên tag rồi Enter"), "created_at": tr("tạo {t}"),
        "updated_at": tr("sửa {t}"), "to_lead": tr("▶ Giao cho trưởng nhóm"),
        "to_lead_tip": tr("Gửi tiêu đề + mô tả làm mục tiêu cho trưởng nhóm"), "del_todo_q": tr("Xoá việc “{v}”?"),
        "cal_time": tr("Giờ"), "cal_clear": tr("Bỏ hạn"), "cal_hint": tr("gõ được: mai, t6, 24/10 17h"),
        "qp_tags": tr("tag:"), "qp_due": tr("hạn:"), "qp_pri": tr("ưu tiên:"), "ac_new": tr("＋ Tạo tag mới “{v}”"),
        "ac_count": tr("{n} việc · {m} ghi chú"), "kb_pick": tr("chọn"), "kb_add": tr("thêm"),
        "m_open": tr("Mở chi tiết"), "m_due": tr("Đặt hạn…"),
        "tag_title": tr("Quản lý tag"), "tag_sub": tr("dùng chung cho To-do và Ghi chú của dự án này"),
        "tg_new_ph": tr("Tên tag mới, ví dụ: hotfix"), "tg_add": tr("＋ Thêm tag"),
        "tg_help": tr("Xoá tag chỉ gỡ tag khỏi việc và ghi chú, không xoá chúng · Gộp: chuyển mọi việc/ghi chú sang "
                      "tag khác rồi xoá tag này · Kéo ⋮⋮ để đổi thứ tự"),
        "th_todos": tr("Việc"), "th_notes": tr("Ghi chú"), "th_open": tr("Chưa xong"), "tg_rename": tr("Đổi tên"),
        "tg_merge": tr("Gộp vào…"), "tg_merge_go": tr("Gộp"), "tg_save": tr("Lưu"), "tg_hint": tr("Enter lưu · Esc huỷ"),
        "tg_color": tr("Màu"), "tg_del_q": tr("Xoá tag “{v}”? Việc và ghi chú vẫn còn, chỉ gỡ tag."),
        "tg_empty": tr("Chưa có tag nào — gõ #tag khi thêm việc, hoặc thêm ở đây"),
        "notes": tr("Ghi chú"), "n_search": tr("Tìm trong ghi chú…"), "n_new": tr("＋ Ghi chú"),
        "n_pinned": tr("Đã ghim"), "n_recent": tr("Gần đây"), "n_untitled": tr("Ghi chú không tên"),
        "n_title_ph": tr("Tiêu đề"), "n_body_ph": tr("Viết markdown… # tiêu đề, - danh sách, - [ ] việc, `code`"),
        "n_pin": tr("📌 Ghim"), "n_unpin": tr("📌 Bỏ ghim"), "n_del_q": tr("Xoá ghi chú “{v}”?"),
        "n_saved": tr("● Đã lưu {t}"), "n_saving": tr("Đang lưu…"), "n_unsaved": tr("● Chưa lưu"),
        "n_autosave": tr("tự lưu khi gõ"), "n_chars": tr("{n} ký tự"), "n_empty": tr("Chưa có ghi chú nào"),
        "n_none": tr("Chọn một ghi chú bên trái hoặc tạo ghi chú mới"), "n_nomatch": tr("Không có ghi chú khớp"),
        "n_conflict": tr("Ghi chú vừa được sửa ở nơi khác."), "n_reload": tr("Tải lại"), "n_overwrite": tr("Ghi đè"),
        "n_to_todo": tr("＋ Tạo to-do từ dòng đã chọn"), "n_tag_add": tr("＋ tag"),
        "goal_plan": tr("Kế hoạch"), "goal_plan_title": tr("Kế hoạch mục tiêu #{id}"),
        "src_plan": tr("Kế hoạch ban đầu"), "src_workflow": tr("Theo workflow"), "src_review": tr("Bổ sung khi review"),
        "src_followup": tr("Tiếp tục / làm thêm"), "src_delegate": tr("Giao việc chéo"), "src_user": tr("Thêm tay"),
        "plan_empty": tr("Mục tiêu này chưa có task nào"), "plan_summary": tr("Tổng kết của trưởng nhóm"),
        "plan_lead": tr("Kế hoạch của trưởng nhóm"), "plan_agents": tr("Kết quả từng agent"),
        "plan_show_prompt": tr("Xem prompt giao cho agent"),
        "roles_title": tr("Vai trò · model · effort"), "roles_full": tr("Thiết lập đầy đủ (/setup)…"),
        "roles_hint": tr("Đổi CLI · model · effort cho từng vai trò — lưu là có hiệu lực ngay. Kiểu làm việc, quyền, "
                         "lệnh kiểm tra giữ nguyên (đổi ở /setup)."),
        "image_pasted": tr("Đã dán ảnh {v}"),
        "sr_files": tr("File"), "sr_search": tr("Tìm"), "sr_replace_ph": tr("Thay bằng"),
        "sr_case": tr("Phân biệt hoa/thường"), "sr_word": tr("Khớp nguyên từ"), "sr_regex": tr("Dùng regex"),
        "sr_toggle_replace": tr("Hiện ô thay thế"), "sr_more": tr("Lọc file"),
        "sr_include": tr("File gồm — vd src, *.ts"), "sr_exclude": tr("File bỏ qua — vd *.test.ts, dist"),
        "sr_searching": tr("Đang tìm…"), "sr_none": tr("Không có kết quả"), "sr_summary": tr("{n} kết quả trong {f} file"),
        "sr_truncated": tr("quá nhiều, chỉ hiện phần đầu — thu hẹp tìm kiếm"),
        "sr_replace_all": tr("Thay tất cả"), "sr_replace_file": tr("Thay trong file này"),
        "sr_dismiss": tr("Bỏ khỏi kết quả"),
        "sr_confirm_q": tr("Thay {n} kết quả trong {f} file bằng \"{r}\"? App không hoàn tác được — xem lại bằng git diff."),
        "sr_dirty": tr("Bỏ qua file đang sửa dở (chưa lưu): {v}"),
        "lofi": tr("Nhạc lofi"), "lofi_play": tr("Phát"), "lofi_pause": tr("Tạm dừng"), "lofi_hide": tr("Thu gọn"),
        "lofi_close": tr("Tắt nhạc"), "lofi_custom": tr("Link của bạn"),
        "lofi_custom_ph": tr("Dán link YouTube hoặc stream mp3/aac rồi Enter…"),
        "lofi_bad_url": tr("Link không phát được — dùng link YouTube hoặc link stream http(s)"),
        "lofi_blocked": tr("Video này không cho phát nhúng ngoài YouTube — thử đài hoặc link khác"),
        "lofi_hint": tr("Radio online (cần mạng). Đài và âm lượng lưu riêng cho trình duyệt này."),
        "view_task": tr("Xem"),
        "side_collapse": tr("Thu gọn thanh bên"), "side_expand": tr("Mở rộng thanh bên"),
        "sound_local": tr("Mỗi loại có âm riêng: kế hoạch / diff chờ duyệt, agent hỏi, task lỗi, mục tiêu xong. Lưu riêng cho trình duyệt này."),
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
        "nav_g_work": tr("Điều phối"), "nav_g_dev": tr("Mã nguồn"), "nav_g_me": tr("Cá nhân"), "nav_g_stats": tr("Báo cáo"),
        "ag_hint": tr("Agent ngoài các vai trò ở trên. Bấm model · effort để đổi, 💬 để chat riêng với agent."),
        "ag_chat": tr("Chat"), "ag_custom": tr("tuỳ chỉnh"), "ag_off": tr("chưa bật"),
        "ag_off_hint": tr("Chưa tham gia đội — bật ở /setup."),
        "wf_hint": tr("Workflow chạy bằng /flow <tên> <mục tiêu>, hoặc ★ Đặt mặc định để gõ mục tiêu là chạy luôn. "
                      "Agent tuỳ chỉnh nằm ở trang Agents."),
        # --- /custom
        "cu_title": tr("Agent & workflow tuỳ chỉnh"),
        "cu_hint": tr("Agent mới tham gia đội như agent có sẵn (trưởng nhóm phân việc theo vai trò, bật/tắt ở "
                      "/setup). Workflow chạy bằng /flow <tên> <mục tiêu>, hoặc ★ Đặt mặc định để gõ mục tiêu là "
                      "chạy luôn."),
        "cu_agents": tr("Agent tuỳ chỉnh"), "cu_add_agent": tr("Thêm agent"), "cu_add_flow": tr("Thêm workflow"),
        "cu_run": tr("Chạy"), "cu_run_hint": tr("Điền /flow {name} vào ô nhập — gõ mục tiêu rồi Enter (chạy một lần, không đổi luồng mặc định)"),
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
        "cu_step_after": tr("Sau bước"), "cu_add_step": tr("Thêm bước"),
        "cu_project": tr("Chỉ dùng cho dự án này ({name})"), "cu_project_chip": tr("dự án"),
        "cu_step_up": tr("Chuyển lên"), "cu_step_down": tr("Chuyển xuống"), "cu_step_ins": tr("Chèn bước ngay dưới"),
        "cu_skill_hint": tr("Gõ $tên-skill trong prompt của bước để bước đó làm theo skill (xem trang 🧩 Skills)."),
        "cu_warn_verify": tr("Bước {i} (verify): chưa đặt lệnh kiểm tra (/verify) — bước sẽ xong ngay, không kiểm tra"),
        "cu_warn_agent": tr("Bước {i}: agent '{agent}' không có trong đội hoặc đang tắt — lúc chạy sẽ giao cho "
                            "trưởng nhóm"),
        "cu_warn_gate": tr("Bước {i} (duyệt) không chờ bước nào — không có gì để duyệt"),
        "kind_code": "code", "kind_review": "review", "kind_verify": "verify", "kind_gate": tr("⏸ duyệt"),
        "cu_ai": tr("✨ Gợi ý"), "cu_ai_btn": tr("Gợi ý"),
        "cu_ai_ph": tr("mô tả quy trình, vd: thiết kế → code → test → review"),
        "cu_ai_hint": tr("trưởng nhóm điền các bước"),
        "cu_ai_wait": tr("✨ {lead} đang thiết kế workflow…"), "cu_one_step": tr("Workflow cần ít nhất 1 bước"),
    }




def _first_line(s: str | None, n: int = 160) -> str:
    return (s or "").strip().splitlines()[0][:n] if (s or "").strip() else ""


def task_json(t: Task, full: bool = True) -> dict:
    """full=False (ảnh chụp bảng việc gửi mỗi khi đổi): bỏ prompt/kết quả — có thể dài vài chục KB mỗi task;
    ngăn chi tiết lấy qua /api/task/{id}. Riêng task nháp giữ prompt (khung duyệt kế hoạch hiện nó)."""
    d = {"id": t.id, "goal": t.goal_id, "parent": t.parent_id, "agent": t.agent, "title": t.title,
         "prompt": t.prompt, "status": t.status, "deps": t.depends_on, "source": t.source,
         "result": t.result, "error": t.error, "branch": t.branch, "created": t.created,
         "started": t.started, "finished": t.finished, "model": t.model, "effort": t.effort,
         "attempts": t.attempts, "question": t.question(), "skills": t.skills or []}
    if not full:
        del d["result"]
        if t.status != "draft":
            del d["prompt"]
    return d


def goal_json(g: Goal, busy: bool) -> dict:
    qa = (g.grill or {}).get("qa") or []
    return {"id": g.id, "text": g.text, "title": _first_line(g.text, 200), "status": g.status, "round": g.round,
            "summary": g.summary, "workflow": g.workflow, "followups": g.followups or [],
            "busy": busy, "spec": bool(g.spec), "qa": sum(1 for x in qa if x.get("a") is not None),
            "created": g.created, "ended": g.status in GOAL_ENDED}


def tail_file(path: Path, n: int = LOG_TAIL) -> list[str]:
    return read_tail(path, n)


def guard_middleware(port: int):
    """Chỉ phục vụ khi Host là máy này (chặn DNS rebinding) và Origin (nếu có) cũng là máy này (chặn trang
    web lạ mở WebSocket tới ateam — giao diện chạy được lệnh shell). Từ xa: xem web_auth."""
    return auth_middleware(Remote(Path("."), port=port), port)


# --readonly: thao tác không đổi gì vẫn cho phép
READONLY_OPS = ("custom_preview", "goal_plan", "code_search", "rules_list", "grid_attach") + SKILL_READONLY


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
        self.lsp = lsp.Hub(root)  # đi tới định nghĩa / tìm chỗ dùng bằng language server (tab Code)
        self.setup = SetupWeb(self)
        self.skills = SkillsOps(self)
        self.clients: set[web.WebSocketResponse] = set()
        self.discovering = False  # đang hỏi danh sách model từ các CLI (wizard hiện "⏳")
        self._last_state = ""
        self._last_live = ""
        self._cache: dict[tuple, tuple] = {}
        self.ptys: dict[int, tuple[PtySession, web.WebSocketResponse]] = {}  # "Mở trong terminal" (xterm.js)
        self._pty_seq = 0
        # mục 🔲 Lưới: CLI thật của agent trong từng ô — thuộc về server (đóng tab không dừng CLI), tab mở sau
        # nhận lại output gần nhất (grid_attach)
        self.grid = GridHub(root, lambda: self.cfg, lambda a: self.orch.terminal_session(a))
        self.grid.listen(self._on_grid)
        self.orch.on_shell_release = self.grid.close_task_shells
        self.grid_ws: set[web.WebSocketResponse] = set()
        self._out: list[dict] = []    # dòng log / output lệnh chờ gửi (gom theo LOG_FLUSH)
        self._flushing = False
        self.notices = notify.Watcher()  # báo trình duyệt khi task lỗi / chờ duyệt (như TUI)
        self.latest: str | None = None  # bản ateam mới hơn bản đang chạy (_update_loop)
        self.windows: list = []  # `ateam web` của dự án mở ở cửa sổ mới (open_window) — dừng cùng server này
        self._bg: set[asyncio.Task] = set()
        self.quota: dict = {"t": "quota", "items": None, "at": 0}  # hạn mức 5h/tuần gần nhất (quota.collect)
        self._quota_lock: asyncio.Lock | None = None  # tạo trong vòng lặp asyncio (_startup)
        self.next_root: Path | None = None  # /open: serve() trả về để cli.cmd_web chạy lại ở dự án này
        self.next_args: list[str] = []  # 📱 chạy lại ở chế độ từ xa: đối số thêm cho lần chạy lại (remote_restart)

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
            web.get("/api/task/{tid}", self.api_task),
            web.get("/api/agent/{name}", self.api_agent_tail),
            web.get("/api/job/{jid}", self.api_job),
            web.get("/api/scripts", self.api_scripts),
            web.get("/api/files", self.api_files),
            web.post("/api/image", self.api_image),
            web.get("/api/continue", self.api_continue),
            web.get("/api/dashboard", self.api_dashboard),
            web.get("/api/goals", self.api_goals),
            web.get("/api/quota", self.api_quota),
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
        self._quota_lock = asyncio.Lock()
        self._spawn(self._quota_loop())
        self._spawn(self._update_loop())
        if self.remote.tunnel:
            self._spawn(self._tunnel())
        if not needs_setup():  # như TUI: hỏi model của CLI chưa từng hỏi (wizard tự hỏi khi mở)
            found = found_models(load_state())
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
        if not self.next_root:  # /open chạy lại server ở dự án khác: cửa sổ kia vẫn dùng tiếp
            for p in self.windows:
                if p.returncode is None:
                    p.terminate()
        for sess, _ws in list(self.ptys.values()):
            sess.kill_now()
        self.grid.shutdown()
        await self.lsp.close()
        runs = [j.run for j in self.shell.jobs.values() if j.run and j.alive]
        runs += self.orch.all_runs()
        self.shell.stop_all()  # không để lại dev server mồ côi
        for run in runs:
            run.cancel()
        procs = [r.proc for r in runs if r.proc and r.proc.returncode is None]
        if procs:  # chờ SIGTERM một chút, còn sống thì SIGKILL ngay (vòng lặp sắp dừng)
            try:
                await asyncio.wait_for(asyncio.gather(*(p.wait() for p in procs)), 3)
            except asyncio.TimeoutError:
                pass
            for run in runs:
                run.kill_now()
        for ws in list(self.clients):
            await ws.close()
        for t in list(self._bg):
            t.cancel()
        if self._bg:  # chờ task bị huỷ dọn tiến trình con (claude -p /usage của quota…) trước khi vòng lặp đóng
            await asyncio.wait(list(self._bg), timeout=2)

    # ------------------------------------------------------------------ mở folder / dự án khác (/open)
    def open_project(self, d: dict) -> tuple:
        """Dừng server rồi cli.cmd_web chạy lại với -C <thư mục>, cùng cổng; trình duyệt thấy dự án khác trong
        hello (root) thì tự nạp lại trang. Web từ xa không đổi được: token chỉ cấp quyền cho một dự án."""
        if self.remote.enabled:
            return tr("Đang mở web từ xa — chỉ đổi được dự án khi chạy trên máy này"), "warn"
        path, err = projects.check_target(str(d.get("path") or ""), self.root)
        if path is None:
            return err, "warn"
        busy = len(self.orch.runs) + len(self.orch.lead_busy)
        if busy and not d.get("force"):
            return "", "", {"busy": busy, "path": projects.shorten(path)}
        self.next_root = path
        asyncio.get_running_loop().call_later(0.3, self.stop_server)  # trả lời trình duyệt xong mới dừng
        return tr("↪ Đang mở {v}…", v=projects.shorten(path)), "info", {"switching": True}

    async def open_window(self, d: dict) -> tuple:
        """Mở dự án khác ở cửa sổ trình duyệt mới, dự án này vẫn mở: một `ateam web` riêng (cổng kế tiếp) chạy kèm
        server này — Ctrl+C ở terminal dừng cả hai. Dự án đó đang mở ở `ateam web` khác thì dùng lại server đó."""
        from .cli import free_port, web_port
        if self.remote.enabled:
            return tr("Đang mở web từ xa — chỉ đổi được dự án khác khi chạy trên máy này"), "warn"
        want = projects.expand(str(d.get("path") or ""), self.root)
        port = web_port(want.resolve()) if want.is_dir() else None
        if port:
            return (tr("⧉ {v} đã mở sẵn ở cổng {port}", v=projects.shorten(want.resolve()), port=port), "info",
                    {"url": f"http://127.0.0.1:{port}"})
        path, err = projects.check_target(str(d.get("path") or ""), self.root)
        if path is None:
            return err, "warn"
        port = free_port("127.0.0.1", self.port + 1)
        if port is None:
            return tr("Không còn cổng trống từ {v}", v=self.port + 1), "error"
        logf = path / ".ateam" / "web.log"
        logf.parent.mkdir(parents=True, exist_ok=True)
        with open(logf, "w", encoding="utf-8") as out:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "ateam", "-C", str(path), "web", "--port", str(port), cwd=str(path),
                stdin=asyncio.subprocess.DEVNULL, stdout=out, stderr=asyncio.subprocess.STDOUT)
        self.windows.append(proc)
        for _ in range(150):  # server mới nghe thì mới mở cửa sổ (tránh trang lỗi kết nối)
            await asyncio.sleep(0.1)
            if proc.returncode is not None:
                tail = [x for x in logf.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
                return tr("Không mở được {v}: {e}", v=projects.shorten(path), e=tail[-1] if tail else proc.returncode), "error"
            got = web_port(path)
            if got and await self._listening(got):
                self.orch.log(tr("⧉ Mở {v} ở cửa sổ mới: http://127.0.0.1:{port}", v=projects.shorten(path), port=got))
                return (tr("⧉ Đã mở {v} ở cửa sổ mới (cổng {port}) — Ctrl+C ở terminal dừng cả hai",
                           v=projects.shorten(path), port=got), "ok", {"url": f"http://127.0.0.1:{got}"})
        return tr("{v} chưa mở xong — xem {log}", v=projects.shorten(path), log=projects.shorten(logf)), "warn"

    def remote_restart(self, d: dict) -> tuple:
        """📱 Mở trên điện thoại: chạy lại server ở chế độ từ xa (như `ateam web --host 0.0.0.0` / `--tunnel`), cùng
        cổng. Trả token để trình duyệt này đăng nhập vào server mới (từ xa thì cả máy này cũng cần token)."""
        mode = d.get("mode")
        if self.remote.enabled:
            return tr("Server đã mở từ xa"), "warn"
        if mode not in ("lan", "tunnel"):
            return tr("Chế độ không hợp lệ: {v}", v=mode), "warn"
        if mode == "tunnel" and not shutil.which("cloudflared"):  # cmd_web sẽ thoát ngay → server chết
            return tr("Chưa cài cloudflared — cài bằng `brew install cloudflared` (macOS) rồi bấm lại."), "warn"
        busy = len(self.orch.runs) + len(self.orch.lead_busy)
        if busy and not d.get("force"):
            return "", "", {"busy": busy}
        self.next_root = self.root
        self.next_args = ["--tunnel"] if mode == "tunnel" else ["--host", "0.0.0.0"]
        asyncio.get_running_loop().call_later(0.3, self.stop_server)  # trả lời trình duyệt xong mới dừng
        return tr("↻ Đang chạy lại server…"), "info", {"restarting": True,
                                                       "token": load_token(self.root / ".ateam")}

    def busy_count(self) -> int:
        return len(self.orch.runs) + len(self.orch.lead_busy)

    async def _self_update(self) -> None:
        """/update, nút Cập nhật trên thông báo: cài xong thì chạy lại server bằng bản mới (cùng cổng) — trình duyệt
        nối lại thấy phiên bản khác thì tự tải lại trang. Agent đang chạy thì hỏi trước (tin "updated" kèm busy)."""
        try:
            ok, msg = await update.run_update(lambda line: self.orch.log("  " + line))
        except Exception as e:
            self.orch.log(tr("Lỗi: {e}", e=e))
            return
        if not ok:
            self.orch.log("ℹ " + msg)
            return
        self.latest = None
        self.orch.log("✓ " + msg)
        if self.remote.tunnel and not self.remote.public_url:  # tunnel nhanh: chạy lại là đổi URL, điện thoại mất kết nối
            msg = tr("Cloudflare Tunnel nhanh đổi URL mỗi lần chạy nên server không tự chạy lại — dừng (Ctrl+C) rồi "
                     "chạy lại `ateam web` để dùng bản mới.")
            self.orch.log("ℹ " + msg)
            self.broadcast({"t": "updated", "manual": True, "text": msg})
            return
        self.restart_for_update()

    def restart_for_update(self, force: bool = False) -> tuple:
        busy = self.busy_count()
        if busy and not force:
            self.broadcast({"t": "updated", "busy": busy})
            return "", "", {"busy": busy}
        self.orch.log(tr("↻ Khởi động lại server để dùng bản mới…"))
        self.next_root = self.root
        self.next_args = []
        self.broadcast({"t": "updated", "restarting": True})
        asyncio.get_running_loop().call_later(0.5, self.stop_server)  # gửi tin cho trình duyệt xong mới dừng
        return tr("↻ Đang khởi động lại server…"), "info", {"restarting": True}

    @staticmethod
    async def _listening(port: int) -> bool:
        try:
            _r, w = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            return False
        w.close()
        return True

    def rules_state(self) -> dict:
        return {"rules": rules.load(self.root), "native": rules.native_files(self.root),
                "targets": [{"v": v, "label": label} for v, label in rules.target_choices(self.cfg)],
                "file": projects.shorten(rules.path_for(self.root))}

    def stop_server(self) -> None:
        raise web.GracefulExit()  # như Ctrl+C: run_app chạy _shutdown (dừng agent, lệnh terminal) rồi trả về

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
        if kind == "log":  # line: dòng cho log của task; raw (nếu khác): dòng gốc cho ô agent (tab Agents)
            item = {"k": "log", "task": data.get("task_id"), "agent": data.get("agent"), "line": data.get("line", "")}
            if data.get("raw") not in (None, item["line"]):
                item["raw"] = data["raw"]
            self._queue(item)

    def on_shell_event(self, kind: str, job, line: str) -> None:
        if kind == "line":
            self._queue({"k": "job", "id": job.id, "line": line})

    def _queue(self, item: dict) -> None:
        """Gom dòng output, LOG_FLUSH giây gửi một tin {"t":"lines"} — thay vì một tin (và một tác vụ gửi cho
        mỗi trình duyệt) cho từng dòng."""
        if not self.clients:
            return
        self._out.append(item)
        if not self._flushing:
            self._flushing = True
            try:
                asyncio.get_running_loop().call_later(LOG_FLUSH, self._flush)
            except RuntimeError:  # không có vòng lặp (test gọi thẳng)
                self._flushing = False

    def _flush(self) -> None:
        self._flushing = False
        items, self._out = self._out, []
        if items:
            self.broadcast({"t": "lines", "items": items})

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
                        "accent_color": theme.ACCENTS.get(st.get("accent") or "", ""), **code_prefs(st)})

    @staticmethod
    async def _send(ws: web.WebSocketResponse, data: str) -> None:
        try:
            await ws.send_str(data)
        except (ConnectionError, RuntimeError):
            pass

    UPDATE_EVERY = 6 * 3600  # web hay để chạy nhiều ngày: hỏi lại bản mới định kỳ

    def update_info(self) -> dict:
        """Bản mới (nếu có) cho tin hello / update: chân thanh bên hiện ⬆, toast có nút Cập nhật."""
        if not self.latest:
            return {}
        return {"latest": self.latest, "update_text": update.new_version_text(self.latest),
                "update_src": update.editable_source() is not None}

    async def _update_loop(self) -> None:
        while True:
            latest = await update.check_new()
            if latest and latest != self.latest:
                self.latest = latest
                self.orch.log("ℹ " + update.new_version_text(latest))
                self.broadcast(dict(self.update_info(), t="update"))
            await asyncio.sleep(self.UPDATE_EVERY)

    async def _push_loop(self) -> None:
        """Ảnh chụp bảng việc mỗi 0,5 giây — chỉ gửi khi khác lần trước (task/agent khác cũng ghi vào DB).
        Dòng cuối của agent đang chạy đổi liên tục nên đi riêng trong tin "live" nhỏ, để ảnh chụp lớn chỉ gửi
        khi bảng việc thật sự đổi."""
        while True:
            await asyncio.sleep(0.5)
            try:
                tasks, goals = self.db.tasks(), self.db.goals()  # một lần đọc DB cho cả vòng
                self.push_notices(self.notices.diff(tasks, goals))
            except Exception:
                continue
            if not self.clients:
                continue
            self.git.poll_changes()
            try:
                state = json.dumps(self.snapshot(tasks, goals), ensure_ascii=False)
                live = json.dumps(self.live(), ensure_ascii=False)
            except Exception as e:  # DB đang bị ghi dở… — lần sau đọc lại
                self.orch.log(f"⚠ web: {e}")
                continue
            out = []
            if state != self._last_state:
                self._last_state = state
                out.append(state)
            if live != self._last_live:
                self._last_live = live
                out.append(live)
            for data in out:  # gửi song song: một trình duyệt chậm (điện thoại qua tunnel) không giữ chân cả nhóm
                await asyncio.gather(*(self._send(ws, data) for ws in list(self.clients) if not ws.closed))

    async def _quota_loop(self) -> None:
        while True:
            if self.clients:
                await self.refresh_quota()
            await asyncio.sleep(QUOTA_EVERY)

    async def refresh_quota(self) -> dict:
        """Hỏi lại hạn mức 5h/tuần của các CLI rồi gửi mọi tab. Đang có lượt hỏi thì chờ lượt đó, không hỏi chồng."""
        if self._quota_lock.locked():
            async with self._quota_lock:
                return self.quota
        async with self._quota_lock:
            try:
                items = await quota.collect(self.orch)
            except Exception as e:  # CLI in lạ, file phiên hỏng…: giữ số cũ, lần sau hỏi lại
                self.orch.log(f"⚠ quota: {e}")
                return self.quota
            self.quota = {"t": "quota", "items": items, "at": time.time()}
            self.orch.quota_items = items  # lịch "khi hồi hạn mức" (/schedule quota …)
        self.broadcast(self.quota)
        return self.quota

    def live(self) -> dict:
        """Dòng cuối của từng task đang chạy (thẻ Kanban)."""
        return {"t": "live", "last": {str(act["task_id"]): act.get("last_line") or ""
                                      for name in self.cfg.active_agents()
                                      for act in self.orch.current_activities(name) if act.get("task_id")}}

    # ------------------------------------------------------------------ ảnh chụp trạng thái
    def snapshot(self, tasks_all: list[Task] | None = None, goals_all: list[Goal] | None = None) -> dict:
        o, cfg = self.orch, self.cfg
        goals_all = self.db.goals() if goals_all is None else goals_all
        tasks_all = self.db.tasks() if tasks_all is None else tasks_all
        keep = {g.id for g in goals_all[-8:]} | {g.id for g in goals_all if g.status not in GOAL_ENDED}
        goals = [goal_json(g, g.status in ("planning", "reviewing") or g.id in o.lead_busy)
                 for g in goals_all if g.id in keep]
        tasks = tasks_all[-TASK_LIMIT:]
        agents = []
        for name, a in cfg.active_agents().items():
            acts = [{k: act.get(k) for k in ("task_id", "title", "label", "started")}
                    for act in o.current_activities(name)]
            agents.append({"name": name, "lead": name == cfg.lead, "installed": a.installed(),
                           "label": a.label(), "role": a.role, "model": a.model, "effort": a.current_effort(),
                           "models": a.model_choices()[:12], "efforts": a.efforts_for(),
                           "cooldown": o.cooldown_label(name) if o.in_cooldown(name) else "",
                           "activities": acts})
        # khung hỏi đáp: câu /grill chờ trả lời > câu <<<ASK>>> của agent > trạng thái /grill (đang nghĩ / lỗi)
        wv = o.waiting_view(goals_all, tasks_all)
        grill = ask = None
        if wv and wv["kind"] == "grill":
            grill = dict(wv, text=_first_line(wv["text"], 300))
        elif wv:
            ask = dict(wv, more=wv["others"])
        jobs = [{"id": j.id, "cmd": j.cmd, "status": j.status, "started": j.started, "finished": j.finished,
                 "rc": j.rc, "ports": j.ports} for j in self.shell.jobs.values()]
        return {"t": "state", "goals": goals, "tasks": [task_json(t, full=False) for t in tasks], "agents": agents,
                "grill": grill, "ask": ask, "jobs": jobs, "shells": self.grid.shells(), "paused": o.paused, "worktree": o.use_worktree,
                "lead": cfg.lead, "commit_agent": cfg.commit_agent, "workflow": cfg.default_workflow, "compacting": o.compacting,
                "continue": reports.continue_candidates(self.db, tasks_all, goals_all), "busy": len(o.runs), "todos": todos.load(self.root),
                "tags": todos.load_tags(self.root), "notes": notes.summaries(self.root), "git_changes": self.git.changes}

    def hello(self) -> dict:
        from .tui import COMMANDS, HELP  # danh sách lệnh + trợ giúp dùng chung với TUI
        st = load_state()
        return {"t": "hello", "version": __version__, **self.update_info(), "project": self.root.name, "root": str(self.root),
                "todo_file": str(todos.path_for(self.root)).replace(str(Path.home()), "~", 1),
                "notes_file": str(notes.path_for(self.root)).replace(str(Path.home()), "~", 1),
                "remote": self.remote.enabled, "readonly": self.remote.readonly,
                "lang": get_lang(), "T": ui_strings(), "help": HELP,
                "commands": [{"name": n, "args": a, "desc": d} for n, a, d in COMMANDS],
                # dữ liệu gợi ý tham số lệnh (/task agent:model@effort, /model, /flow…)
                "agents": [{"name": n, "model": a.model, "effort": a.effort, "models": a.model_choices(),
                            "efforts": list(a.efforts_for()), "role": a.role, "installed": a.installed(),
                            "lead": n == self.cfg.lead, "label": a.label(),
                            "tty": a.interactive_argv() is not None, "bin": a.binary}
                           for n, a in self.cfg.active_agents().items()],
                "all_agents": list(self.cfg.agents),
                "grid_presets": preset_names(),
                "code_commands": palette.commands_json(), "isolation": self.cfg.isolation,
                "workflows": [{"name": n, "summary": w.summary(), "description": w.description}
                              for n, w in self.cfg.workflows.items()],
                "accents": [{"key": k, "label": theme.accent_label(k), "color": c} for k, c in theme.ACCENTS.items()],
                "langs": [{"key": k, "label": LANG_NAMES[k]} for k in LANGS],
                "prefs": {"notify": notify.mode(), "vim": st.get("vim", True) is not False, "accent": st.get("accent") or "",
                          "accent_color": theme.ACCENTS.get(st.get("accent") or "", ""), **code_prefs(st)},
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
                                  "pending": r.tunnel and not r.tunnel_url, "urls": urls}, headers={"Cache-Control": "no-store"})

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

    async def api_task(self, request: web.Request) -> web.Response:
        """Prompt + kết quả đầy đủ của một task (ảnh chụp bảng việc không mang theo)."""
        t = self.db.task(int(request.match_info["tid"]))
        return web.json_response({"id": t.id, "prompt": t.prompt, "result": t.result, "error": t.error}
                                 if t else {"id": None})

    async def api_agent_tail(self, request: web.Request) -> web.Response:
        """Phần cuối log của task gần nhất của agent (ô agent ở tab Agents lúc mới mở trang)."""
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

    async def api_image(self, request: web.Request) -> web.Response:
        """Dán / kéo-thả ảnh vào ô nhập: thân request là byte ảnh → lưu `.ateam/images/`, trả `@đường/dẫn` để chèn."""
        if self.remote.readonly:
            return web.json_response({"error": tr("Chế độ chỉ xem (--readonly) — không làm được thao tác này")})
        data = await request.read()
        limit = min(IMAGE_MAX, ATTACHMENT_MAX) if any(
            (a.opencode_major or 0) >= 2 for a in self.cfg.active_agents().values()) else IMAGE_MAX
        if len(data) > limit:
            return web.json_response({"error": tr("Ảnh quá lớn (tối đa {n} MB)", n=limit // 1024 ** 2)})
        try:
            p = clipboard.save_image(data, self.root / ".ateam" / "images")
        except ValueError:
            return web.json_response({"error": tr("Dữ liệu dán vào không phải ảnh")})
        rel = clipboard.shorten(p, self.root)
        return web.json_response({"path": rel, "mention": mentions.quote(rel)})

    async def api_files(self, request: web.Request) -> web.Response:
        if self.index.stale():
            await self.index.refresh()
        return web.json_response(mentions.search(self.index.entries, request.query.get("q", ""),
                                                 int(request.query.get("n", 12))))

    def _cached(self, key: tuple, fn):
        """Kết quả tính từ cả lịch sử (dashboard, lịch sử mục tiêu — trình duyệt hỏi mỗi 5 giây): chỉ tính lại khi
        DB đổi hoặc sang phút mới."""
        sig = (key, self.db.change_sig(), int(time.time() // 60))
        hit = self._cache.get(key)
        if hit and hit[0] == sig:
            return hit[1]
        val = fn()
        self._cache[key] = (sig, val)
        return val

    async def api_dashboard(self, _r: web.Request) -> web.Response:
        # cùng số liệu với tab 📊 Thống kê của TUI
        return web.json_response(self._cached(("dash",), lambda: reports.dashboard(self.db)))

    async def api_quota(self, r: web.Request) -> web.Response:
        if r.query.get("refresh") or self.quota["items"] is None:
            await self.refresh_quota()
        return web.json_response(self.quota)

    async def api_goals(self, r: web.Request) -> web.Response:
        n = int(r.query.get("limit", "50") or 50)
        return web.json_response(self._cached(("goals", n), lambda: reports.goal_history(self.db, n)))

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
            if self.quota["items"] is not None:
                await ws.send_str(json.dumps(self.quota, ensure_ascii=False))
            elif self._quota_lock and not self._quota_lock.locked():  # tab đầu tiên: không chờ vòng 60 giây
                self._spawn(self.refresh_quota())
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                data: dict = {}
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue
                if self.slow_op(data):  # AI viết commit, push…: chạy riêng, tab vẫn gõ/bấm được trong lúc chờ
                    self._spawn(self._answer(ws, data))
                else:
                    await self._answer(ws, data)
        finally:
            self.clients.discard(ws)
            self.grid_ws.discard(ws)
            for pid, (sess, owner) in list(self.ptys.items()):  # tab đóng: đóng luôn terminal của nó
                if owner is ws:
                    sess.close()
                    self.ptys.pop(pid, None)
        return ws

    SLOW_GIT = ("ai_message", "ai_resolve", "commit", "push", "pull", "fetch")
    SLOW_CMDS = ("/commit ", "/push", "/pull", "/fetch", "/usage", "/init", "/compact", "/models ")

    def slow_op(self, d) -> bool:
        """Thao tác có thể chạy hàng chục giây (gọi AI, mạng, git hook). Còn lại chạy tuần tự để giữ thứ tự."""
        if not isinstance(d, dict):
            return False
        op = d.get("op")
        if op == "git":
            return d.get("action") in self.SLOW_GIT
        if op == "submit":
            return str(d.get("text") or "").strip().startswith(self.SLOW_CMDS)
        return op in ("workflow_suggest", "workflow_from_goal", "code_format", "code_ai", "code_lsp", "code_blame",
                      "open_window") + SKILL_SLOW

    async def _answer(self, ws: web.WebSocketResponse, data) -> None:
        """Chạy một thao tác rồi trả lời bằng toast (kèm ref nếu trình duyệt đang chờ)."""
        try:
            op = str(data.get("op") or "")
            reply = (await self.pty_op(ws, data) if op.startswith("pty_") else
                     await self.grid_op(ws, data) if op.startswith("grid_") else await self.handle(data))
        except Exception as e:  # thao tác lỗi không làm rớt kết nối
            reply = (tr("Lỗi: {e}", e=e), "error")
        # (thông báo, mức) hoặc (thông báo, mức, {"open": …, …} cho trình duyệt mở khung/tab)
        out = {"t": "toast", "text": reply[0] if reply else "", "level": reply[1] if reply else "",
               "ref": data.get("ref") if isinstance(data, dict) else None}
        if reply and len(reply) > 2:
            out.update(reply[2])
        if reply or out["ref"] is not None:
            await self._send(ws, json.dumps(out, ensure_ascii=False))

    async def pty_op(self, ws: web.WebSocketResponse, d: dict) -> tuple | None:
        """Terminal tương tác trong trình duyệt: pty_open {agent, rows, cols} → mở CLI thật của agent tiếp tục phiên
        chat; pty_in {id, data}; pty_resize {id, rows, cols}; pty_close {id}. Output: tin {"t":"pty", id, data(base64)}
        chỉ gửi cho tab đã mở."""
        if self.remote.readonly:
            return tr("Chế độ chỉ xem (--readonly) — không làm được thao tác này"), "warn"
        op = d.get("op")
        if op == "pty_open":
            agent = str(d.get("agent") or "")
            a = self.cfg.active_agents().get(agent)
            argv = a.interactive_argv(self.orch.terminal_session(agent)) if a else None
            if not argv:
                return tr("Không biết cách mở {agent} ở chế độ tương tác (agent tuỳ chỉnh) — tự mở trong terminal khác",
                          agent=agent), "warn"
            self._pty_seq += 1
            pid = self._pty_seq

            def on_data(b: bytes, pid=pid) -> None:
                self._spawn(self._send(ws, json.dumps({"t": "pty", "id": pid, "data": base64.b64encode(b).decode()})))

            def on_exit(rc: int, pid=pid) -> None:
                self.ptys.pop(pid, None)
                self._spawn(self._send(ws, json.dumps({"t": "pty_exit", "id": pid, "rc": rc})))

            sess = PtySession(argv, str(self.root), dict(os.environ), on_data=on_data, on_exit=on_exit,
                              rows=int(d.get("rows") or 30), cols=int(d.get("cols") or 100))
            try:
                await sess.start()
            except OSError as e:
                return tr("Không chạy được {cmd}: {e}", cmd=" ".join(argv), e=e), "error"
            self.ptys[pid] = (sess, ws)
            return "", "", {"open": {"pty": pid, "title": f"{agent} · {shlex.join(argv)}"}}
        entry = self.ptys.get(int(d.get("id") or 0))
        if not entry or entry[1] is not ws:
            return None
        sess = entry[0]
        if op == "pty_in":
            sess.write(str(d.get("data") or "").encode())
        elif op == "pty_resize":
            sess.resize(int(d.get("rows") or 30), int(d.get("cols") or 100))
        elif op == "pty_close":
            sess.close()
            self.ptys.pop(int(d["id"]), None)
        return None

    # ------------------------------------------------------------------ mục 🔲 Lưới
    def _on_grid(self, cid: str, kind: str, payload) -> None:
        if kind == "notice":  # ô cần người dùng: báo mọi tab, kể cả tab không ở mục Lưới
            agent = tr("Terminal") if payload["agent"] == SHELL else payload["agent"]
            wait = tr("Ô trong Lưới đang chờ bạn")
            if payload["kind"] == "done":
                n = notify.Notice("grid_done", tr("✅ {agent} đã xong lượt", agent=agent), wait, cell=cid)
            else:
                n = notify.Notice("grid_ask", tr("🔔 {agent} cần bạn", agent=agent), payload["text"] or wait,
                                  level="warn", cell=cid)
            self.push_notices([n])
            return
        if not self.grid_ws:
            return
        if kind == "data":
            msg = json.dumps({"t": "gpty", "id": cid, "data": base64.b64encode(payload).decode()})
        elif kind == "exit":
            msg = json.dumps({"t": "gpty_exit", "id": cid, "rc": payload})
        else:
            msg = json.dumps(dict(self.grid.state(), t="grid"), ensure_ascii=False)
        for ws in list(self.grid_ws):
            if not ws.closed:
                self._spawn(self._send(ws, msg))

    async def grid_op(self, ws: web.WebSocketResponse, d: dict) -> tuple | None:
        """grid_attach (mở mục Lưới: nhận bố cục + output gần nhất của từng ô, rồi output mới), grid_add {agent,
        model, effort, resume, near, where, rows, cols}, grid_start {id, rows, cols} (mở lại CLI), grid_in {id, data},
        grid_size {id, rows, cols}, grid_stop {id}, grid_close {id}, grid_move {src, dst, where}, grid_preset {preset},
        grid_sizes {widths, heights}, grid_bcast {on}, grid_cell {id, bcast}; grid_shell {task, cmd, rows, cols}: ⌨ shell
        rời ở tab Terminal (không vào bố cục), task = mở trong worktree của task đó."""
        op, g = d.get("op"), self.grid
        if op == "grid_attach":
            self.grid_ws.add(ws)
            await self._send(ws, json.dumps(dict(g.state(), t="grid"), ensure_ascii=False))
            for cid, t in list(g.terms.items()):
                if t.buf:
                    await self._send(ws, json.dumps({"t": "gpty", "id": cid, "replay": True,
                                                     "data": base64.b64encode(bytes(t.buf)).decode()}))
            return None
        if self.remote.readonly:
            return tr("Chế độ chỉ xem (--readonly) — không làm được thao tác này"), "warn"
        cid = str(d.get("id") or "")
        rows, cols = int(d.get("rows") or 24), int(d.get("cols") or 80)
        if op == "grid_in":
            g.write(cid, str(d.get("data") or "").encode())
            return None
        if op == "grid_size":
            g.resize(cid, rows, cols)
            return None
        if op == "grid_add":
            where = str(d.get("where") or "")
            new, err = await g.add(str(d.get("agent") or ""), model=str(d.get("model") or ""),
                                   effort=str(d.get("effort") or ""), resume=d.get("resume", True) is not False,
                                   near=str(d.get("near") or "") or None, where=where if where in WHERE else "",
                                   rows=rows, cols=cols)
            return (err, "warn" if not new else "error") if err else ("", "", {"grid_cell": new})
        if op == "grid_shell":
            return await self.open_shell(str(d.get("cmd") or ""), d.get("task"), rows, cols)
        if op == "grid_start":
            err = await g.start(cid, rows, cols)
            return (err, "error") if err else None
        if op == "grid_stop":  # dừng CLI/shell nhưng giữ ô (↻ Mở lại chạy tiếp)
            g.stop(cid)
        elif op == "grid_close":
            g.close(cid)
        elif op == "grid_move":
            if g.layout.move(str(d.get("src") or ""), str(d.get("dst") or ""), str(d.get("where") or "")):
                g.changed()
        elif op == "grid_preset":
            name = str(d.get("preset") or "")
            if name in preset_names():
                g.layout.apply(name)
                g.changed()
        elif op == "grid_sizes":
            g.layout.set_sizes(d.get("widths") if isinstance(d.get("widths"), list) else None,
                               d.get("heights") if isinstance(d.get("heights"), dict) else None)
            g.changed()
        elif op == "grid_bcast":
            g.bcast = bool(d.get("on"))
            g.changed(save=False)
        elif op == "grid_cell":
            g.update_cell(cid, **{k: d[k] for k in ("bcast", "resume", "model", "effort") if k in d})
        return None

    async def handle(self, d: dict) -> tuple | None:
        """Một thao tác từ trình duyệt. Trả (thông báo, mức: info|ok|warn|error[, thêm]) hoặc None."""
        o, op = self.orch, d.get("op")
        if self.remote.readonly and op not in READONLY_OPS and not (op == "note" and d.get("action") == "get"):
            return tr("Chế độ chỉ xem (--readonly) — không làm được thao tác này"), "warn"
        if op == "submit":
            return await self.submit(str(d.get("text") or ""))
        if op in SKILL_OPS:  # trang 🧩 Skills (web_skills.py)
            return await self.skills.handle(d)
        if op in ("rules", "rules_list"):  # popup 📏 Rule của dự án
            err = rules.apply(self.root, str(d.get("action") or ""), d) if op == "rules" else ""
            return err, "warn" if err else "", self.rules_state()
        if op == "projects":  # gợi ý cho popup Mở folder
            if self.remote.enabled:
                return "", "", {"items": []}
            return "", "", {"items": projects.candidates(str(d.get("q") or ""), self.root)}
        if op == "open_project":
            return self.open_project(d)
        if op == "open_window":
            return await self.open_window(d)
        if op == "remote_restart":
            return self.remote_restart(d)
        if op == "update_restart":  # đã cập nhật nhưng agent đang chạy: người dùng bấm "Khởi động lại"
            return self.restart_for_update(force=True)
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
            if act == "skip":  # để trưởng nhóm tự quyết (theo khuyến nghị)
                return o.answer_grill(gid, None), "info"
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
        if op == "chat":
            agent, text = str(d.get("agent") or ""), str(d.get("text") or "").strip()
            if text.startswith("/handoff "):  # trong ô 💬 của agent: /handoff <tới> [yêu cầu]
                return await self.command(f"/handoff {agent} {text[9:].strip()}")
            return self.chat(agent, text)
        if op == "retry":
            return o.retry(int(d["task"])), "info"
        if op == "cancel":
            return o.cancel(int(d["task"])), "info"
        if op == "delete_task":
            return o.delete_task(int(d["task"])), "info"
        if op == "merge":
            return await o.merge(int(d["task"])), "info"
        if op == "reject":
            return await o.reject(int(d["task"]), str(d.get("feedback") or "").strip() or None), "info"
        if op == "edit":
            return o.edit(int(d["task"]), str(d.get("prompt") or "").strip()), "info"
        if op == "assign":
            return o.assign(int(d["task"]), str(d.get("agent") or ""), rerun=bool(d.get("rerun"))), "info"
        if op == "cancel_plan":
            return o.cancel_planning(int(d["goal"])), "info"
        if op == "agent_option":  # bảng chọn model/effort (như open_picker của TUI)
            v, name = d.get("value"), str(d["agent"])
            msg = o.set_agent_option(name, str(d["key"]), None if v in (None, "") else str(v))
            a = self.cfg.agents.get(name)  # model mới có thể có mức effort khác: trình duyệt dùng ngay để hỏi tiếp
            return msg, "ok", ({"agent": {"name": name, "model": a.model, "effort": a.current_effort(),
                                          "efforts": a.efforts_for()}} if a else {})
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
        if op == "code_search":
            return await self.code.search(d)
        if op == "code_replace":
            return await self.code.replace(d)
        if op == "save":
            return self.code.save(d)
        if op == "code_format":
            return await self.code.format(d)
        if op == "code_lsp":  # F12 / Shift+F12: kết quả nằm trong payload (lỗi cũng vậy — không toast mỗi lần bấm)
            rel = str(d.get("path") or "")
            if safe_path(self.root, rel) is None:
                return "", "", {"lsp": {"error": tr("Đường dẫn không hợp lệ (ngoài dự án): {path}", path=rel)}}
            kind = "references" if d.get("kind") == "references" else "definition"
            return "", "", {"lsp": await self.lsp.query(kind, rel, str(d.get("text") or ""), int(d.get("line") or 1),
                                                        int(d.get("ch") or 0), utf16=True)}
        if op == "code_blame":  # blame dòng đang đứng (thanh trạng thái / palette)
            rel = str(d.get("path") or "")
            if safe_path(self.root, rel) is None:
                return "", "", {"blame": tr("Đường dẫn không hợp lệ (ngoài dự án): {path}", path=rel)}
            text = d.get("text")
            return "", "", {"blame": await gitops.blame_line(self.root, rel, int(d.get("line") or 1),
                                                             str(text) if text is not None else None)}
        if op == "code_ai":  # ⌘I sửa inline / giải thích đoạn chọn: agent chỉ trả lời, trang hiện diff để duyệt
            mode = "explain" if d.get("mode") == "explain" else "edit"
            ok, res = await self.orch.code_ai(mode, str(d.get("path") or ""), str(d.get("text") or ""),
                                              int(d.get("from") or 0), int(d.get("to") or 0),
                                              str(d.get("instruction") or ""), str(d.get("agent") or ""))
            if not ok:
                return res, "warn"
            return "", "", {"code": res} if mode == "edit" else {"answer": res}
        if op in ("file_new", "dir_new", "file_rename", "file_delete", "open_vscode"):
            return await self.code.file_op(op, d)
        if op == "setup_save":
            return await self.setup.save_setup(d)
        if op == "roles_save":
            return await self.setup.save_roles(d)
        if op == "setup_skip":
            return self.setup.skip_setup()
        if op == "setup_discover":
            self._spawn(self.discover())
            return None
        if op == "custom_save":
            return await self.setup.save_custom(d)
        if op == "custom_delete":
            return await self.setup.delete_custom(d)
        if op == "workflow_suggest":
            return await self.setup.suggest_workflow(d)
        if op == "workflow_from_goal":  # 🔀 Lưu mục tiêu thành workflow (khung 📋 kế hoạch của mục tiêu đã xong)
            ok, res = await self.orch.workflow_from_goal(int(d.get("goal") or 0))
            if not ok:
                return str(res), "warn"
            return tr("🔀 Đã khái quát {n} bước — xem lại rồi bấm Lưu", n=len(res["steps"])), "ok", {"wf_from_goal": res}
        if op == "default_flow_save":
            return await self.setup.save_default_flow(d)
        if op == "input_mode":  # ô chọn cạnh ô nhập / nút ★ ở mục Tuỳ chỉnh: gõ mục tiêu chạy workflow nào
            try:
                return wizard.set_input_mode(self.cfg, self.root, str(d.get("name") or "")), "ok", {"mode_saved": True}
            except ValueError as e:
                return str(e), "warn"
        if op == "custom_preview":
            return self.setup.preview_agent(d)
        if op == "prefs":
            return self.setup.set_prefs(d)
        if op == "todo":
            try:
                todos.apply(self.root, str(d.get("action") or ""), d)
            except ValueError:
                return tr("Nhập nội dung việc cần làm"), "warn"
            return None
        if op == "tag":
            try:
                todos.apply_tag(self.root, str(d.get("action") or ""), d)
            except ValueError as e:
                return (tr("Đã có tag “{name}”", name=todos.norm_tag(d.get("name"))) if str(e) == "exists"
                        else tr("Nhập tên tag")), "warn"
            return None
        if op == "note":
            return self.note_op(d)
        if op == "goal_plan":
            return self.goal_plan(d.get("goal"))
        return tr("Không hiểu thao tác {op}", op=op), "warn"

    def note_op(self, d: dict) -> tuple | None:
        """🗒 Ghi chú: get/add/save trả {"note": …} cho đúng tab hỏi (ref); save gặp bản mới hơn trả {"note_conflict": …}."""
        action = str(d.get("action") or "")
        try:
            n = notes.apply(self.root, action, d)
        except notes.Conflict as c:
            return "", "", {"note_conflict": c.note}
        if action == "to_todo":
            return tr("✅ Đã thêm vào To-do"), "ok"
        if action in ("get", "add", "save"):
            if n is None:
                return tr("Không thấy ghi chú #{id}", id=d.get("id")), "warn"
            return "", "", {"note": n}
        return None

    def goal_plan(self, gid) -> tuple:
        """📋 Kế hoạch của một mục tiêu (cả khi đã duyệt / xong): mọi task của nó, nhóm theo nguồn."""
        g = self.db.goal(int(gid)) if str(gid or "").isdigit() else None
        if not g:
            return tr("Không thấy mục tiêu #{id}", id=gid), "warn"
        tasks = [{k: v for k, v in task_json(t).items() if k in ("id", "agent", "title", "prompt", "status", "deps",
                                                                 "source", "model", "effort", "result", "error", "started", "finished",
                                                                 "skills")}
                 for t in self.db.tasks(goal_id=g.id)]
        return "", "", {"goal_plan": {"goal": goal_json(g, False), "tasks": tasks}}

    async def submit(self, text: str) -> tuple | None:
        """Ô nhập chính — cùng luật với TUI: !lệnh, trả lời /grill, mục tiêu mới, hoặc lệnh /…"""
        text = text.strip()
        if not text:
            return None
        if text.startswith("!"):
            return self.run_shell(text[1:])
        wv = self.orch.waiting_view()  # đang chờ người dùng trả lời: câu gõ vào là câu trả lời (số = phương án)
        if not text.startswith("/") and wv and wv["question"]:
            if wv["kind"] == "grill":
                return self.orch.answer_grill(wv["goal"], text), "info"
            return self.orch.answer_task(wv["task"], text), "info"
        if not text.startswith("/"):
            return self.start_goal(text, self.cfg.default_workflow)
        return await self.command(text)

    async def open_shell(self, cmd: str = "", task=None, rows: int = 24, cols: int = 80) -> tuple:
        """⌨ Mở shell tương tác ở tab Terminal (thư mục dự án, hoặc worktree của task); cmd gõ sẵn vào shell."""
        cwd = ""
        if task not in (None, ""):
            try:
                tid = int(task)
            except (TypeError, ValueError):
                return tr("Không có task #{tid}", tid=task), "warn"
            path, err = await self.orch.task_shell_dir(tid)
            if not path:
                return err, "warn"
            cwd, task = str(path), tid
        cid, err = await self.grid.add_shell(cwd, task if cwd else None, cmd.strip(), rows, cols)
        return (err, "error", {"open": {"term": cid}}) if err else ("", "", {"open": {"term": cid}})

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

    def chat(self, agent: str, text: str) -> tuple | None:
        """Tin nhắn ô 💬 (thẻ agent, tab Agents) hoặc /chat: như TeamApp.send_chat."""
        text = text.strip()
        new = text == "/new" or text.startswith("/new ")
        if new:
            text = text[4:].strip()
            if agent in self.cfg.active_agents():
                self._queue({"k": "log", "task": None, "agent": agent, "line": tr("── cuộc trò chuyện mới ──")})
            if not text:
                self.orch.chat_reset(agent)
                return None
        res = self.orch.chat(agent, text, new=new)
        if isinstance(res, str):
            return res, "warn"
        # mọi tab đang mở cùng thấy tin vừa gửi trong ô agent
        self._queue({"k": "log", "task": res, "agent": agent, "line": tr("› bạn: {text}", text=text)})
        return None

    async def _command(self, cmd, rest, o, cfg, agents, num, parse_code_target) -> tuple | None:
        if cmd == "help":
            return "", "", {"open": {"modal": "help"}}
        if cmd == "chat":
            agent, _, msg = rest.partition(" ")
            if agent not in agents:
                return tr("Dùng: /chat <agent> <tin nhắn>  — agent: {v}", v=", ".join(agents)), "warn"
            reply = self.chat(agent, msg) if msg.strip() else None
            return reply or ("", "", {"open": {"view": "team", "chat": agent}})
        if cmd == "handoff":
            parts = rest.split(maxsplit=2)
            if len(parts) < 2:
                return tr("Dùng: /handoff <từ> <tới> [yêu cầu]  — agent: {v}", v=", ".join(agents)), "warn"
            res = o.handoff(parts[0], parts[1], parts[2] if len(parts) > 2 else "")
            if isinstance(res, str):
                return res, "warn"
            self._queue({"k": "log", "task": None, "agent": parts[1], "line": tr("── cuộc trò chuyện mới ──")})
            self._queue({"k": "log", "task": res, "agent": parts[1],
                         "line": tr("› bạn: {text}", text=self.db.task(res).title)})
            return "", "", {"open": {"view": "team", "chat": parts[1]}}
        if cmd == "skills":
            return "", "", {"open": {"view": "skills"}}
        if cmd == "rules":
            err = rules.apply(self.root, "add", {"text": rest}) if rest else ""
            if err:
                return err, "warn"
            return (tr("📏 Đã thêm rule — mọi agent nhận từ lượt sau") if rest else ""), "ok", {"open": {"modal": "rules"}}
        if cmd == "open":
            if self.remote.enabled:
                return tr("Đang mở web từ xa — chỉ đổi được dự án khi chạy trên máy này"), "warn"
            return "", "", {"open": {"project": rest}}  # trình duyệt hỏi file chưa lưu / agent đang chạy
        if cmd == "focus":  # phóng to 1 thẻ agent: chỉ là cách xem, trình duyệt tự làm
            if rest and rest not in agents:
                return tr("Dùng: /focus [agent]  — agent: {v}", v=", ".join(agents)), "warn"
            return "", "", {"open": {"view": "team", "focus": rest}}
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
            msg = o.grill_command(rest)
            if msg is not None:
                return msg, "info"
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
        if cmd == "term":  # /term · /term <lệnh> · /term #12 (shell ở worktree của task #12)
            m = re.fullmatch(r"#?t?(\d+)", rest) if rest.startswith(("#", "t")) else None
            if m:
                return await self.open_shell(task=int(m.group(1)))
            return await self.open_shell(rest) if rest else ("", "", {"open": {"term": "focus"}})
        if cmd in ("team", "board"):
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
            tid, *agent = shlex.split(rest)[:2]
            if not agent:
                return tr("Dùng: /assign <task> <agent> — hoặc mở task rồi bấm ⇄ Đổi agent"), "warn"
            return o.assign(num(tid), agent[0], rerun=True), "info"
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
                items = a.model_choices() if cmd == "model" else list(a.efforts_for())
                return "", "", {"open": {"picker": {"agent": parts[0], "key": cmd, "items": items,
                                                    "current": a.model if cmd == "model" else a.current_effort()}}}
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
        if cmd == "undo":
            if rest.endswith(" --yes") or rest == "--yes":
                ok, msg = await o.undo(rest[:-5].strip())
                return msg, "ok" if ok else "error"
            res = await o.undo_preview(rest)
            if isinstance(res, str):
                return res, "warn"
            return "", "", {"open": {"confirm": {"title": res[0], "text": res[1], "yes": tr("Hoàn tác"),
                                                 "cmd": f"/undo {rest} --yes".replace("  ", " ")}}}
        if cmd == "schedule":
            msg = o.schedule_command(rest)
            if not rest or rest.split()[0].lower() in ("list", "ls"):
                return "", "", text_box(tr("⏰ Lịch hẹn"), msg)
            return msg, "ok" if msg.startswith("⏰") else "warn"
        if cmd == "usage":  # chờ hạn mức từ CLI (song song, toast "đang chạy…" ở trình duyệt) rồi mở một khung
            names = reports.usage_agents(cfg)
            o.log(tr("\nĐang hỏi hạn mức từ CLI của {v}…", v=", ".join(names)))

            def done(name: str, c: str, lines: list[str]) -> None:
                o.log(f"📊 {name}" + (f"  ({c})" if c else "") + "\n" + "\n".join("  " + ln for ln in lines))
            res = await o.usage_all(names, on_done=done)
            return "", "", text_box(tr("Thống kê"), reports.usage_text(cfg, self.db, o) + "\n\n"
                                    + reports.usage_quota_text(cfg, res))
        if cmd == "update":
            o.log(tr("Đang kiểm tra bản mới…"))
            self._spawn(self._self_update())
            return tr("Đang kiểm tra bản mới…"), "info", {"open": {"task_link": SYSTEM}}  # nút "Xem" trên toast, không tự mở ngăn log
        if cmd == "setup":
            return "", "", {"open": {"modal": "setup"}}
        if cmd == "roles":
            return "", "", {"open": {"modal": "roles"}}
        if cmd == "custom":
            return "", "", {"open": {"view": "custom"}}  # mục 🔀 Workflows ở sidebar (popup vẫn mở từ /setup)
        if cmd == "dash":
            return "", "", {"open": {"view": "dash"}}
        if cmd == "search":
            return "", "", {"open": {"search": rest}}
        if cmd == "plan":  # trống = mục tiêu mới nhất
            gid = int(rest.lstrip("#mM")) if rest.strip() else next((g.id for g in reversed(self.db.goals())), None)
            return ("", "", {"open": {"plan": gid}}) if gid else (tr("Chưa có mục tiêu nào"), "warn")
        if cmd == "todo":
            if rest.strip():
                try:
                    todos.apply(self.root, "add", {"text": rest})
                except ValueError:
                    return tr("Nhập nội dung việc cần làm"), "warn"
            return (tr("✅ Đã thêm vào To-do") if rest.strip() else ""), "ok", {"open": {"view": "todo"}}
        if cmd == "notes":
            n = notes.apply(self.root, "add", {"title": rest}) if rest.strip() else None
            return "", "", {"open": {"view": "notes", "note": n["id"] if n else None}}
        if cmd == "tags":
            return "", "", {"open": {"view": "todo", "modal": "tags"}}
        if cmd == "grid":
            if rest.strip():
                new, err = await self.grid.add(rest.strip())
                if not new:
                    return err, "warn"
            return "", "", {"open": {"view": "grid"}}
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
            return o.cancel_command(rest), "info"
        if cmd == "delete":
            return o.delete_task(num(rest)), "info"
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
            return (tr("↪ Task #{i}: hỏi tiếp {agent}", i=i, agent=self.db.task(i).agent), "ok",
                    {"open": {"task_link": i}})  # đang gõ thì đừng che bảng việc: toast có nút "Xem"
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
        if cmd == "init":
            ok, msg = await o.init_overview(rest)
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


def serve(root: Path, cfg: Config, db: DB, port: int, remote: Remote | None = None) -> tuple[Path | None, list[str]]:
    """Chạy server tới khi Ctrl+C (trả None) hoặc /open, 📱 chạy lại từ xa (trả thư mục dự án cần mở + đối số thêm)."""
    wa = WebApp(root, cfg, db, port, remote)
    web.run_app(wa.make_app(), host=wa.remote.host, port=port, print=None, access_log=None)
    return wa.next_root, wa.next_args
