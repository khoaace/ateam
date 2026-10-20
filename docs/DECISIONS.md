# Các quyết định thiết kế

Mỗi mục: quyết định, lý do, và điều sẽ khiến nên xem lại. Đọc trước khi "dọn" code — nhiều chỗ trông
thừa là có chủ đích.

## 1. Gọi CLI headless, không gọi API mô hình

**Quyết định**: mỗi agent là một CLI có sẵn (`claude -p`, `codex exec`, `agy -p`, `opencode run`) chạy
như tiến trình con. **Lý do**: dùng gói đăng ký và cấu hình sẵn có của người dùng, không cần API key,
mỗi CLI tự lo đọc/sửa file và công cụ của nó; thêm agent mới chỉ là thêm vài dòng cấu hình.
**Đánh đổi**: không có số token chính xác, phụ thuộc định dạng output và cờ của từng CLI.

## 2. Giao thức bằng văn bản trong output, không bằng MCP

**Quyết định**: agent báo kết quả bằng dòng `SUMMARY:`, giao việc bằng khối `<<<DELEGATE …>>>`,
ghi chú bằng `<<<NOTE>>>`; trưởng nhóm trả JSON. **Lý do**: hoạt động với mọi CLI kể cả khi agent bị
sandbox chặn ghi ra ngoài thư mục làm việc (Codex `--sandbox workspace-write` không ghi được `.ateam/team.db` từ
worktree) hoặc không được chạy lệnh shell. Lệnh `ateam add/note` vẫn có cho agent chạy được shell.
**Xem lại nếu**: muốn agent giao việc *giữa chừng* và chờ kết quả — khi đó cần MCP server của ateam.

## 3. SQLite làm bảng việc

**Lý do**: nhiều tiến trình (TUI, `ateam add` do agent gọi, CLI khác) cùng ghi; WAL + `busy_timeout`
đủ cho vài chục task; không cần server. TUI đọc lại DB định kỳ thay vì nghe sự kiện nên thấy cả thay
đổi từ ngoài.

## 4. Một vòng lặp asyncio, không thread

**Lý do**: Textual đã chạy asyncio; tiến trình con và pty đọc qua `asyncio`/`add_reader`. Tránh khoá
và race giữa thread với DB/TUI. **Hệ quả**: không bao giờ gọi API chặn (`subprocess.run`,
`time.sleep`) trong orchestrator/TUI.

## 5. Chạy `agy` qua pty

**Lý do**: `agy -p` không in gì (thoát 0) hoặc treo khi stdout không phải terminal. Pty 220 cột cho
output đầy đủ; `clean_line` bỏ mã ANSI và `\r`. Task thoát 0 nhưng không in gì bị coi là lỗi để lộ
ra tình huống này.

## 6. Chèn cờ model/effort ngay trước prompt

**Lý do**: một số CLI viết bằng Go `flag` dừng đọc cờ ở đối số vị trí đầu tiên, và `-p` của vài CLI
nhận prompt làm giá trị; đặt cờ trước `-p`/prompt an toàn cho cả hai kiểu. Cờ nằm trong cấu hình
(`model_args`/`effort_args`) vì mỗi CLI gọi khác nhau (Codex dùng `-c model_reasoning_effort=…`,
OpenCode dùng `--variant`).

## 7. Kế hoạch ở trạng thái nháp mặc định

**Lý do**: nhìn kế hoạch vài giây rẻ hơn nhiều so với 4 agent chạy sai hướng hàng chục phút. Tắt bằng
`approve_plan = false`. Task bổ sung sau review cũng đi qua bước này.

## 8. Worktree theo task, merge `--no-ff`, xung đột thì dừng

**Lý do**: cho phép nhiều agent sửa code song song mà không ghi đè nhau; mỗi task là một commit merge
rõ ràng, dễ revert. ateam không tự giải xung đột (agent có thể giải sai một cách âm thầm) — task chuyển
`conflict`, nhánh được giữ. Task phụ thuộc chạy trên HEAD *sau khi* task trước đã merge.
**Hạn chế**: worktree yêu cầu chạy ở gốc repo đã có commit; ở chế độ shared không tách được diff theo task.

## 9. Verify chạy trong thư mục của task và giao sửa kèm log

**Lý do**: agent hay báo "xong" khi test còn đỏ. Chạy lệnh của người dùng là phán quyết khách quan; giao
lại kèm 120 dòng cuối output cho đúng agent (đã có ngữ cảnh) hoặc agent sửa lỗi chỉ định. `only_when_changed`
tránh chạy test cho task chỉ đọc/nghiên cứu. Ở chế độ shared, test thấy cả thay đổi của task khác
đang chạy song song — chấp nhận được; dùng worktree nếu cần tách bạch.

## 10. Nhận diện hết hạn mức bằng mẫu chữ, chỉ khi agent thất bại hoặc in ít

**Lý do**: không CLI nào có mã thoát riêng cho rate limit. Giới hạn ở "rc ≠ 0 hoặc ≤ 15 dòng" để không
nhầm task đang viết code về rate limiter. Cooldown lưu toàn cục vì hạn mức theo tài khoản, không theo
dự án. **Xem lại nếu**: thêm CLI có output JSON nêu rõ lỗi hạn mức — nên đọc trường đó thay vì regex.

## 11. UI tiếng Việt, prompt tiếng Anh

**Lý do**: người dùng là developer Việt Nam; mô hình tuân thủ định dạng (JSON, SUMMARY) ổn định hơn
với hướng dẫn tiếng Anh. Prompt dặn agent viết tiêu đề/nội dung theo ngôn ngữ của mục tiêu.

## 12. Trang docs trên Cloudflare Workers (static assets), build bằng Python

**Lý do**: tài khoản người dùng đã dùng nhiều Workers; Workers Builds nối với GitHub nên mỗi push lên
`main` tự deploy; `wrangler.jsonc` có `build.command` nên `npx wrangler deploy` tự dựng `dist/`.
Python có sẵn trong image build (không cần npm package để nén zip). Cài một lệnh (`scripts/get.sh`)
tải từ GitHub nên không phụ thuộc domain của trang docs.

## 13. Giao diện web riêng (aiohttp + JS thuần), một server một bộ lập lịch

**Lý do**: người dùng muốn giao diện web hiện đại (Kanban, nút bấm) và đủ chức năng như terminal. Server aiohttp
giữ *một* `Orchestrator` cho mọi tab → mở nhiều tab không chạy trùng task (bảng việc chưa có bước "nhận task" nguyên
tử). Trang là HTML/CSS/JS thuần trong gói: không cần npm/build lúc chạy (CI và gói zip chỉ có Python), chạy offline.
aiohttp là extra không bắt buộc (`ateam[web]`). Đẩy *ảnh chụp* trạng thái thay vì diff sự kiện: đơn giản, đúng cả khi
CLI/agent khác ghi DB. Logic nằm trong màn hình Textual (wizard /setup, form /custom, báo cáo /usage…) được tách ra
`wizard.py`/`reports.py` để hai giao diện dùng chung; riêng bộ điều phối lệnh `/…` viết hai nơi (lệnh TUI gắn chặt
widget) — test đối chiếu `tui.COMMANDS` giữ chúng đồng bộ. Chỉ nghe `127.0.0.1` + kiểm Host/Origin vì giao diện chạy
được shell.
**Từ xa (`--tunnel`/`--host`/`--public-url`)**: token ngẫu nhiên 256 bit lưu `.ateam/web_token` thay vì mật khẩu —
không có gì để đoán, quét QR là vào. Token vào bằng `/?t=` một lần rồi đổi thành cookie HttpOnly + SameSite=Strict
(fetch/WebSocket tự gửi, không phải sửa ~30 chỗ gọi API, token không nằm lại trong lịch sử/Referer). Ở chế độ từ xa
*mọi* request cần token kể cả từ 127.0.0.1 (cloudflared nối vào từ localhost nên không phân biệt được) và bỏ danh sách
Host (tunnel/domain/IP LAN đều hợp lệ): DNS rebinding không mang được cookie của host thật; còn Origin phải trùng Host.
Chế độ cục bộ giữ như cũ (không token) để không làm phiền người chỉ dùng trên máy. QR tự viết (`qr.py`, ~250 dòng)
thay vì thêm dependency. Quick tunnel (`trycloudflare.com`) vì không cần tài khoản; named tunnel người dùng tự chạy.
**Giữ phiên (`--resume`) và `<<<ASK>>>`**: id phiên do ateam tự đặt khi CLI cho phép (`--session-id`, chắc chắn hơn
đoán file) hoặc bắt từ header (`codex: session id:`); preset theo tên binary trong code (`SESSION_PRESETS`) để không
phải tăng `CONFIG_VERSION`. Chỉ resume khi có *lý do* (cột `tasks.resume` = prompt ngắn) và cùng agent; mất phiên →
chạy lại với prompt đầy đủ, nên resume không bao giờ làm task hỏng hơn trước. Câu hỏi của agent dùng chung khung
/grill (đã quen tay) và trạng thái `asking` thuộc `ACTIVE` để mục tiêu không kết thúc khi còn câu hỏi.
**Editor**: CodeMirror 6 + `@replit/codemirror-vim` đóng gói một lần (`scripts/editor/`, esbuild) thành
`webui/vendor/codemirror.js` (~1,2 MB, ~400 KB nén) và commit vào repo — không CDN, không Node lúc chạy; chỉ gói
~25 ngôn ngữ phổ biến (gói `language-data` đầy đủ 1,7 MB). Vim thật (`:w`, chế độ, thanh ghi) thay vì port `VimState`
của TUI sang JS.
`ateam web --tui` giữ cách cũ (textual-serve chạy chính `ateam tui`, mỗi tab một tiến trình → khoá
`.ateam/tui.lock`, phiên thứ hai thấy `BusyApp`; `/lang` không `execv` vì tiến trình mới sẽ mồ côi, giữ khoá).
**Xem lại nếu**: cần truy cập từ máy khác (cần token + TLS); cần nhiều tiến trình cùng lập lịch (nhận task nguyên
tử trong SQLite); cần đổi theme Textual trên web (hiện web chỉ dùng chung màu nhấn).

## 14. Chat với agent = các lượt headless nối phiên; terminal thật chỉ là lối "tiếp quản"

**Lý do**: người dùng muốn nói chuyện với một agent như trong CLI của nó. Nhúng CLI tương tác làm kênh chính thì ateam
mất hết thứ nó dựa vào (SUMMARY, `<<<ASK>>>`, thống kê, phân loại lỗi/hết hạn mức) vì giao diện toàn màn hình không
bóc được. Nên chat chính là chuỗi task `source="chat"` chạy headless và `--resume` đúng phiên (hạ tầng của `/continue`),
còn nút ⌨ / `/term` mở CLI thật trên *cùng phiên* cho lúc cần slash command, hỏi quyền từng bước… — phần đó ateam
không theo dõi. Câu trả lời của claude `-p` chỉ hiện khi xong lượt (chưa stream, xem ROADMAP).
**Xem lại nếu**: đọc được output JSON stream của từng CLI (khi đó chat có thể hiện chữ dần và đếm token thật).

## 15. Rule của dự án gửi kèm prompt, không ghi vào AGENTS.md / CLAUDE.md

**Lý do**: mỗi CLI tự đọc một kiểu file (claude `CLAUDE.md` + `AGENTS.md`, agy `GEMINI.md` + `.agents/rules`, grok
`.grok/rules`…), agent tuỳ chỉnh có thể không đọc file nào, và ghi vào file trong repo của người dùng thì đụng file họ
tự viết / lẫn vào commit. Gửi kèm prompt (ở `argv_for`) thì agent nào cũng nhận, chọn được người nhận theo agent/vai
trò, lưu ngoài repo. Đổi lại tốn thêm token mỗi lượt mới (lượt `--resume` không gửi lại) và rule chỉ có tác dụng khi
chạy qua ateam. Người dùng chọn cách này (18/10/2026).
**Xem lại nếu**: người dùng muốn rule có tác dụng cả khi mở CLI ngoài ateam (khi đó ghi một khối do ateam quản lý vào
`AGENTS.md`), hoặc muốn chia sẻ rule qua git.

## 16. Prompt gọn: ít task, phạm vi hẹp, review tiếp phiên lập kế hoạch

**Lý do**: agent tốn thời gian ở những việc không ai yêu cầu: trưởng nhóm đọc gần hết repo rồi chia nhiều task
(kể cả task "viết test"/"review" mà ateam đã tự làm qua `/verify` và review), thành viên refactor lan, chạy cả bộ test
nhiều lần, viết câu trả lời và `SUMMARY` dài (bị gửi tiếp cho task sau và lượt review). Prompt giờ dặn: khám phá vừa đủ,
ít task nhất (1 nếu một agent làm được), prompt task ngắn (làm gì / ở đâu / xong khi nào); thành viên làm thay đổi nhỏ
nhất, chỉ đọc file cần, biết các task song song (`siblings`) để không làm chồng, biết lệnh `/verify` ateam sẽ tự chạy
nên chỉ chạy test liên quan, `SUMMARY` ≤ ~5 dòng. Review tiếp tục phiên lập kế hoạch (`keep_session`) — trưởng nhóm
đã đọc code lúc đó, CLI dùng được prompt cache — và tin vào kết quả task + dòng "verification … passed" trong
`_results_text`; chỉ giao thêm việc cho lỗi thật / yêu cầu thiếu, vòng cuối không viết task (đằng nào cũng bị bỏ).
Người dùng chọn: vẫn review mọi mục tiêu, chia ít task, chỉ chạy test liên quan (20/10/2026).
**Xem lại nếu**: kế hoạch hay thiếu việc (prompt quá ngắn), hoặc review bỏ sót lỗi vì không tự kiểm.

## 17. Bóc output: bỏ phần CLI in lại prompt, vá JSON thiếu dấu đóng cuối

**Lý do**: `codex exec` in lại cả prompt (`user\n<prompt>`) trước câu trả lời, cả khi làm trưởng nhóm lẫn thành viên.
Các mẫu trong prompt (JSON câu hỏi `{"question": "..."}`, khối `<<<DELEGATE to="MEMBER_NAME">>>`, luật `SUMMARY:`) bị
bóc nhầm thành câu hỏi "...", việc giao cho `MEMBER_NAME`… Model còn có lúc quên `]` cuối mảng kế hoạch (gpt-6.1-sol,
20/10/2026) → "không trả về kế hoạch JSON hợp lệ". Giờ `strip_echo` cắt output tới hết 3 dòng cuối của prompt (khớp
liên tiếp — không so nguyên văn cả prompt vì CLI nhận bản đã kèm rule và đổi `@file`) trước khi bóc kế hoạch / review /
hỏi đáp / ASK / NOTE / SUMMARY; `extract_json` vá dấu `]`/`}` còn thiếu khi JSON hỏng đúng ở cuối dòng (không vá chỗ
hỏng giữa dòng như `[<ids>]` của mẫu); `question_from` bỏ câu hỏi không có chữ; `parse_delegations` bỏ `MEMBER_NAME`
(đọc lại từ file log khi merge). Agent giả lập `codex` in lại prompt như bản thật để test bắt được lỗi loại này.
**Xem lại nếu**: thêm CLI in lại prompt theo kiểu khác (cắt ngắn, đổi định dạng) — khi đó chỉ còn lớp lọc mẫu bảo vệ.
