# AI Team (`ateam`)

**Trang docs và tải về:** https://ateam.khoaace.workers.dev

Công cụ terminal giúp **Claude Code, Codex, Antigravity và Grok (qua OpenCode)** làm việc như một đội:
một agent làm **trưởng nhóm** (mặc định Claude) lập kế hoạch và chia việc, các agent khác làm song song,
**giao việc cho nhau**, ghi chú chung, và trưởng nhóm **review** rồi giao thêm việc cho đến khi xong.
Bạn vẫn có thể giao tay bất cứ lúc nào.

```
 Bạn ──mục tiêu──▶ Trưởng nhóm (claude) ──kế hoạch──▶ Bảng việc (SQLite)
                                                        │
                ┌──────────────┬──────────────┬─────────┴────┬──────────┐
              codex      antigravity (agy)   grok (Grok Build)  opencode  claude
                └── kết quả / ghi chú / <<<DELEGATE>>> ──▶ bảng việc ──▶ review ──▶ vòng tiếp
```

## Cài đặt

Một lệnh (macOS / Linux):

```bash
curl -fsSL https://raw.githubusercontent.com/khoaace/ateam/main/scripts/get.sh | bash
ateam doctor
```

Hoặc tải file `.zip` từ trang docs, rồi chạy `./install.sh` trong thư mục giải nén.

**Cập nhật**: gõ `/update` trong app (hoặc `ateam update`) — ateam so phiên bản với trang docs, có bản mới
thì chạy lại lệnh cài ở trên; xong thoát rồi mở lại app. Bản cài từ mã nguồn (`pip install -e`) thì cập
nhật bằng `git pull`.

## Cài đặt từ mã nguồn (macOS)

```bash
cd ateam
./install.sh          # tạo venv ở ~/.ateam, lệnh `ateam` ở ~/.local/bin
ateam doctor          # kiểm tra claude / codex / agy / grok / opencode đã có chưa, cờ trong lệnh còn hợp lệ không
```

Yêu cầu: Python 3.9+ (`brew install python` nếu chưa có), git, và các CLI agent **đã đăng nhập sẵn**
(chạy thử `claude`, `codex`, `agy`, `grok`, `opencode` một lần cho chắc).

## Dùng

```bash
cd ~/code/du-an-cua-ban
ateam
```

**Lần đầu mở app** sẽ hiện wizard *Thiết lập đội AI*, hỏi từng bước (Enter: chọn và sang bước tiếp, Esc: quay
lại bước trước, nút ✕ để đóng):

1. **CLI bạn đang dùng** — Claude Code, Codex, Antigravity, Grok Build, OpenCode (CLI chưa cài có lệnh cài).
2. **Kiểu làm việc** — trưởng nhóm lập kế hoạch rồi bạn duyệt / chạy luôn / theo quy trình cố định (thiết kế →
   code → test, gõ mục tiêu là chạy workflow `tinh-nang`) / chủ yếu tự giao việc bằng `/task`.
3. **Mức chi phí** — Tiết kiệm · Cân bằng · Tối đa: điền sẵn model và effort hợp lý cho từng vai trò.
4. **Vai trò → CLI · model · effort** — Trưởng nhóm, Code chính, Review code, Frontend/UI, Test & tài liệu,
   Nghiên cứu. Một CLI làm nhiều vai trò với model khác nhau thì ateam tự tạo thêm agent (vd `claude-review`).
5. **An toàn & duyệt code** — chỉ sửa file hay toàn quyền (chạy lệnh, mạng); sửa thẳng thư mục hay mỗi task một
   nhánh git (tự merge, hoặc xem diff rồi mới merge).
6. **Lệnh kiểm tra** — gợi ý từ `package.json` / `Makefile` (test, lint, build…) để tự chạy sau mỗi task.
7. **Xem lại & lưu** (Ctrl+S).

Danh sách model được hỏi thật từ các CLI (`codex debug models`, `agy models`, `grok models`, `opencode models`)
ngay khi wizard mở. Mở lại bất cứ lúc nào bằng `/setup` trong app hoặc `ateam setup` (wizard điền sẵn đội hiện
tại). Agent tuỳ chỉnh bạn tự thêm ở `/custom` được giữ nguyên. Chỉ muốn đổi CLI · model · effort của vai trò thì dùng
**`/roles`** (web: nút ⚡ ở tab Đội / Tuỳ chỉnh) — mở thẳng bảng vai trò, lưu là áp ngay, các thiết lập khác giữ nguyên.

* **Gõ một câu bình thường** → giao mục tiêu cho trưởng nhóm. Kế hoạch hiện ra ở trạng thái *nháp*
  trong khung **Duyệt kế hoạch** ngay trên ô nhập (thấy ở cả tab Bảng việc và Đội): danh sách task kèm
  agent và phụ thuộc, con trỏ đặt sẵn ở nút *Duyệt & chạy* nên chỉ cần **Enter** (hoặc **F2** / **Ctrl+G** /
  `/go`). ↑↓ trong danh sách để xem toàn bộ nội dung từng task ở ô chi tiết bên dưới; Enter trên một task
  để sửa nội dung, nút *Đổi agent*, *Bỏ kế hoạch* (`/drop`); Esc về ô nhập.
* **Giao tay**: `/task codex viết unit test cho utils.py` (gõ `/task ` để chọn agent từ danh sách); agent
  nhận đúng nguyên văn bạn gõ.
* **Tiếp tục mục tiêu / thread đã xong**: chọn một task trong bảng rồi **F6** (hoặc **Ctrl+O**), bấm nút
  **↪ Tiếp tục** cạnh mục tiêu đã xong, hoặc gõ `/continue ` để chọn từ danh sách — ô nhập điền sẵn
  `/continue m12 ` (mục tiêu) / `/continue t40 ` (task giao tay), dòng phía trên cho biết sẽ tiếp tục gì; gõ
  yêu cầu mới rồi Enter (Esc huỷ). Mục tiêu được mở lại: trưởng nhóm nhận kết quả các task cũ cùng yêu cầu mới
  và lập task bổ sung ngay trong mục tiêu đó. Task giao tay: cùng agent nhận các lượt trước kèm yêu cầu mới.
* **Dọn bảng việc**: nút **🗑 Dọn … task đã xong** phía trên bảng (hoặc `/clear`) xoá các task đã xong/lỗi/huỷ
  của mục tiêu đã kết thúc cùng log của chúng; task còn được task khác chờ thì giữ lại.
* **Nhắc file/thư mục bằng `@`**: gõ `@` trong ô nhập để hiện danh sách file và thư mục của dự án, gõ
  tiếp để lọc (khớp cả rải rác, vd `@atcfg` → `ateam/config.py`), ↑↓ chọn, Tab/Enter chèn, Esc đóng.
  Chọn thư mục thì danh sách đi vào trong thư mục đó. Khi chạy, ateam đổi `@đường/dẫn` sang đúng cú
  pháp của agent nhận việc (xem bảng dưới); `ateam add`/`ateam goal` ngoài dòng lệnh cũng hiểu `@`.
* **Popup**: mọi popup có nút **✕** ở góc phải; **Esc** chỉ đóng lớp trên cùng — đang mở danh sách chọn thì chỉ
  đóng danh sách, form đang sửa dở cần Esc hai lần (tránh mất phần đã nhập). Terminal hẹp (< 110 cột) thì bảng
  việc và log xếp dọc; kéo rộng cửa sổ thì log tự dàn lại.
* Chọn task trong bảng (↑↓) để xem log trực tiếp của nó; **Ctrl+L** về log hệ thống; nút **🗑 Xoá log** phía
  trên ô log ẩn phần log cũ (file `.ateam/logs/` giữ nguyên).
* **Agent & workflow riêng**: `/custom` (hoặc nút *Agent & workflow tuỳ chỉnh…* ở màn hình thiết lập) —
  xem mục dưới.
* **F5** (hoặc **Ctrl+R**) chạy lại task đang chọn, **Ctrl+K** huỷ, `/note ...` ghi chú cho cả đội. Ghi chú dài dần
  thì `/compact [trọng tâm]` (hoặc `ateam compact`): trưởng nhóm tóm tắt ghi chú, mục tiêu gần đây và log
  thành một ghi chú ngắn thay thế, prompt gửi agent sau đó gọn hơn. Gõ `/` ở đầu ô nhập để xem danh sách lệnh kèm mô tả; **F1** (hoặc `/help`) mở bảng trợ giúp đầy đủ.
* **Ctrl+T** mở tab **Đội** để xem cả 4 agent làm việc cùng lúc.

Không cần giao diện:

```bash
ateam goal "Thêm trang đăng nhập + viết test"          # hỏi duyệt kế hoạch rồi chạy
ateam goal -y "Sửa lỗi build"                           # chạy luôn
ateam add --to grok "Viết docstring cho src/api.py"     # thêm task
ateam run                                               # chạy hết task đang chờ
ateam continue m1 "Thêm nút quên mật khẩu"              # tiếp tục mục tiêu #1 (t5 = thread task #5)
ateam list   /   ateam log 3   /   ateam log sys
```

### `@file` được truyền cho từng agent thế nào

| Agent (lệnh) | Trong prompt | Cờ thêm vào lệnh |
| --- | --- | --- |
| claude | `@src/app.py` (Claude Code tự đọc file) | — |
| antigravity (`agy`) | `@src/app.py` | — |
| codex | `src/app.py` (`codex exec` không có cú pháp `@`) | — |
| grok (Grok Build) | `@src/app.py` | — |
| opencode (`opencode run`) | `src/app.py` | `-f src/app.py` (đính kèm file; ateam thêm `--` trước prompt) |
| CLI khác | `src/app.py` | — |

Chỉ đổi khi đường dẫn có thật trong dự án, nên `a@b.com`, `@property`, `codex@xhigh` giữ nguyên.
Đường dẫn có dấu cách viết `@"thư mục/file.md"`. Đổi cú pháp cho một agent bằng `file_ref` /
`file_args` trong config (xem `docs/CONFIG.md`); `ateam doctor` và `/agents` in cú pháp đang dùng.
Với OpenCode, `@thư_mục` chỉ đưa đường dẫn vào prompt; `-f` dành cho file. OpenCode 2 giới hạn mỗi tệp
đính kèm 10 MiB; ateam kiểm tra trước khi chạy và giới hạn ảnh tải lên web khi đội có OpenCode 2.

### Agent hỏi lại giữa task và nhớ phiên làm việc

- Gặp chỗ mơ hồ làm đổi kết quả, agent dừng và hỏi bạn (khối `<<<ASK>>>`): task chuyển sang **đang hỏi bạn**, câu hỏi
  hiện ở cùng khung với `/grill` (TUI lẫn web) kèm phương án gợi ý — bấm/gõ số hoặc gõ câu trả lời; "Để agent tự
  quyết", "Huỷ task". Có thông báo như task chờ duyệt. Tối đa 3 câu mỗi task; phần đang làm dở được giữ (worktree:
  trên nhánh của task). `ateam goal -y`/`ateam run` không có ai trả lời nên tự chọn phương án agent khuyên dùng.
- **Giữ phiên CLI**: `/retry`, từ chối kèm góp ý, vòng sửa khi kiểm tra fail, trả lời câu hỏi và `/continue` (thread
  `/task`) tiếp tục *đúng phiên* của agent (`claude --resume`, `codex exec resume`, `grok --resume`) thay vì gửi lại
  toàn bộ ngữ cảnh — đỡ token, sửa lỗi trúng hơn. `/continue m<id>`: trưởng nhóm tiếp tục phiên lập kế hoạch của mục
  tiêu đó. Phiên không còn (CLI đã xoá, khác thư mục) thì tự chạy lại với đầy đủ ngữ cảnh. agy/opencode chưa hỗ trợ.

### Để trưởng nhóm hỏi kỹ trước khi làm — `/grill`

Kể cả khi gõ mục tiêu bình thường (không `/grill`), lúc lập kế hoạch mà trưởng nhóm thấy có điểm **quan trọng chưa
rõ** (đổi hẳn cách làm, không tự tìm được trong code) thì nó **hỏi lại bạn trước** thay vì đoán — câu hỏi hiện ở
cùng khung Hỏi đáp dưới đây (kèm thông báo ❓), trả lời xong (hoặc **✓ Đủ rồi**) thì nó mới lập kế hoạch. Chi tiết
nhỏ thì nó tự chọn mặc định hợp lý và ghi rõ trong task. `ateam goal -y` (không ai trả lời) thì không hỏi.

Yêu cầu còn mơ hồ? `/grill Thêm trang đăng nhập` (kiểu "grill me"): thay vì lập kế hoạch ngay, trưởng nhóm
**hỏi bạn từng câu một** — phạm vi, luồng người dùng, dữ liệu, ca biên, giao diện, tiêu chí hoàn thành —
mỗi câu kèm 2–4 phương án và phương án nó khuyên dùng. Câu hỏi nào tự tìm được trong code thì nó tự đọc code
thay vì hỏi. Khung **Hỏi đáp** hiện phía trên ô nhập:

- gõ câu trả lời rồi Enter, hoặc gõ số / bấm vào phương án để chọn;
- **⏭ Để trưởng nhóm tự quyết** khi bạn không chắc;
- **✓ Đủ rồi** (`/grill xong`) để chốt luôn với những gì đã trả lời; **✗ Bỏ mục tiêu** (`/grill bỏ`).

Khi đủ rõ (tối đa 15 câu), trưởng nhóm viết **bản đặc tả** (phạm vi, quyết định đã chốt, ngoài phạm vi, tiêu
chí xong — hiện trong log hệ thống), rồi lập kế hoạch như thường. Bản đặc tả đi kèm mục tiêu trong mọi prompt
sau đó (lập kế hoạch, task, review). Chạy được với mọi CLI làm trưởng nhóm.

### Dán ảnh (Ctrl+V)

Chụp màn hình vào clipboard (vd **Cmd+Ctrl+Shift+4** trên macOS) rồi bấm **Ctrl+V** trong ô nhập: ảnh
được lưu ở `.ateam/images/` và ô nhập có thêm `@.ateam/images/paste-….png`. Kéo-thả file ảnh từ
Finder vào terminal cũng ra `@ảnh`. Khi chạy, ảnh đi như `@file` ở trên, riêng **codex** được thêm cờ
`--image=<ảnh>` để thấy ảnh thật (đổi bằng `image_args`). macOS dùng `osascript` có sẵn (hoặc
`pngpaste` nếu đã cài); Linux cần `wl-paste` hoặc `xclip`. Cmd+V vẫn dán chữ như thường.

## Giao diện web (`ateam web`)

Giao diện web hiện đại, **đủ chức năng như terminal**: bảng Kanban (Nháp · Chờ chạy · Đang chạy · Chờ duyệt · Xong ·
Lỗi), thẻ mục tiêu có tiến độ, duyệt kế hoạch bằng nút (đổi agent, sửa nội dung task), `/grill` bấm chọn phương án,
ngăn chi tiết task (log trực tiếp, diff, merge/từ chối, chạy lại, hỏi tiếp), tab **Đội**, **Terminal**, **Git**
(stage, commit — AI viết message, amend, nhánh, stash, pull/push, lịch sử, revert), **Code** (cây thư mục,
editor CodeMirror có phím vim `:w :q :wq :e! :bn`, nhiều file, tự nạp lại khi agent sửa file, file `.md` có
Sửa / Chia đôi / Xem trước), diff kiểu VS Code
(2 cột, chữ đổi trong dòng, tô cú pháp), `/setup`, `/custom`, `/help`, `/usage`, `/models`… Sáng/tối, màu nhấn dùng
chung với terminal, dùng được trên điện thoại.

```bash
~/.ateam/venv/bin/python -m pip install aiohttp   # một lần (cài từ mã nguồn: pip install -e ".[web]")
ateam web --open           # mở http://127.0.0.1:8000  ·  đổi cổng: ateam web --port 9000
```

- Ô nhập dưới cùng dùng như trong terminal và gợi ý cả tham số: `/task ` → agent, `codex:` → model, `@` → effort;
  `/model <agent>`, `/assign`, `/retry <task>`, `/continue`, `/flow`, `/checkout <nhánh>`, `/code @file`… Ctrl+K về ô
  nhập, F2 duyệt kế hoạch, F6 tiếp tục, F1 trợ giúp, Esc đóng. Tab Git: phím `space a u x d c e` như TUI. Tab Code:
  ⌘P tìm file, ⌘S lưu, ⌘⇧V đổi chế độ xem trước markdown, **⌘⇧F tìm & thay trong toàn dự án** như VS Code (mục 🔍 Tìm ở
  sidebar: Aa / nguyên từ / regex, lọc file gồm · bỏ qua, xem trước chữ thay, thay từng file hoặc tất cả — `$1` trong
  chuỗi thay khi dùng regex; tôn trọng `.gitignore`, giữ CRLF/BOM; file đang sửa dở chưa lưu thì bỏ qua). TUI: **F3** hoặc
  `/search [từ khoá]` mở cùng chức năng (Enter mở file đúng chỗ · r thay trong file · x bỏ file · Ctrl+R thay tất cả).
- Dán ảnh (⌘V) hoặc kéo-thả file ảnh vào ô nhập: ảnh lưu vào `.ateam/images/` và chèn `@ảnh` vào prompt như Ctrl+V
  của TUI — ảnh đọc ngay trong trình duyệt nên dùng được cả khi mở từ điện thoại / qua tunnel.
- ✅ **To-do** (tab trên thanh bên, cả TUI: tab ✅ To-do hoặc `/todo [việc]`): quản lý việc riêng cho từng dự án —
  **tag** (màu, lọc, gộp, đổi tên ở popup **Quản lý tag** / `/tags`), **hạn** (nhóm Quá hạn · Hôm nay · Tuần này · Sau
  này, lịch chọn ngày), **ưu tiên** và **mô tả markdown** (checklist `- [ ]`). Ô thêm nhanh hiểu
  `Sửa login #bug !cao @mai 17:00` (`@hôm-nay` `@t6` `@tuần-sau` `@24/10` `@17h`; `!`/`!!`/`!!!`). Bấm một việc mở
  ngăn chi tiết, có nút giao việc đó cho trưởng nhóm. Nhóm theo hạn / tag / ưu tiên / thủ công (kéo để đổi thứ tự).
  TUI: Enter chi tiết · Space xong · t tag · u hạn · p ưu tiên · g nhóm · f lọc tag · h ẩn việc xong · T quản lý tag.
- 🗒 **Ghi chú** (`/notes [tiêu đề]`, TUI: tab 🗒 Ghi chú): ghi chú markdown theo dự án, dùng chung tag với To-do —
  ghim, tìm (`#tag` để lọc), soạn / xem trước / chia đôi, tự lưu khi gõ; hai nơi cùng sửa thì hỏi tải lại hay ghi đè.
  Chọn vài dòng → **＋ Tạo to-do** (TUI: Alt+T) hoặc gửi cho trưởng nhóm.
  To-do, tag và ghi chú lưu ở `~/.config/ateam/{todos,tags,notes}/`, **không** nằm trong thư mục dự án nên không cần
  `.gitignore`; TUI và web dùng chung.
- 📋 **Xem lại kế hoạch**: nút 📋 trên thẻ mục tiêu (TUI và ô nhập web: `/plan [mục tiêu]`) mở toàn bộ kế hoạch của
  trưởng nhóm kể cả khi đã duyệt / đã xong — task chia theo nguồn (kế hoạch ban đầu, bổ sung khi review, tiếp tục,
  giao việc chéo), trạng thái, chọn dòng xem prompt.
- 🎧 **Nhạc lofi** (nút ở thanh bên): phát radio lofi online trong khung nổi — chọn đài (Chillhop, Lofi Girl…) hoặc dán
  link YouTube / stream mp3 của bạn, chỉnh âm lượng, thu gọn để nghe nền. Cần mạng; lưu riêng cho từng trình duyệt.
- Một server giữ **một** bộ lập lịch: mở bao nhiêu tab trình duyệt cũng được, không chạy trùng task. Trong lúc
  đó `ateam` ở terminal sẽ báo dự án đang mở ở phiên khác.
- Mặc định chỉ nghe `127.0.0.1` và từ chối yêu cầu có Host/Origin lạ — trang web khác không điều khiển được ateam
  (giao diện chạy được lệnh shell). Tab Code không mở/ghi được file ngoài dự án hay trong `.git`.
- `ateam web --tui` (cần `textual-serve`): chính giao diện terminal vẽ trong trình duyệt; mỗi dự án chỉ 1 phiên.

### Theo dõi đội từ điện thoại

```bash
brew install cloudflared                        # một lần
ateam web --tunnel                              # https://<ngẫu nhiên>.trycloudflare.com — không cần tài khoản
ateam web --host 0.0.0.0                        # chỉ trong cùng Wi-Fi (http)
ateam web --public-url https://ateam.ten-mien.com   # bạn tự chạy named tunnel trỏ về http://127.0.0.1:8000
```

- Bật một trong các cờ trên là **chế độ từ xa**: mọi trang/API/WebSocket cần **token** (tạo một lần, lưu ở
  `.ateam/web_token`, quyền 600). Terminal in URL kèm token và **mã QR** — quét bằng camera điện thoại là vào; nút
  **📱 Điện thoại** ở sidebar cũng hiện mã QR. Trình duyệt nhận cookie HttpOnly (30 ngày) rồi xoá token khỏi thanh
  địa chỉ; không có cookie thì hiện trang dán token.
- Token có **toàn quyền** như trên máy (duyệt kế hoạch, trả lời agent, merge, `!lệnh`, sửa file, git push) — đừng
  gửi URL cho người khác. `--readonly`: chỉ xem. `--new-token`: đổi token, mọi thiết bị cũ phải quét lại. Sai token
  20 lần trong 10 phút thì khoá tạm.
- `--tunnel` dùng quick tunnel của Cloudflare (URL đổi mỗi lần chạy). Muốn URL cố định: tạo named tunnel
  (`cloudflared tunnel create ateam`, `cloudflared tunnel route dns ateam ateam.ten-mien.com`, chạy
  `cloudflared tunnel run --url http://127.0.0.1:8000 ateam`) rồi `ateam web --public-url https://ateam.ten-mien.com`.
  Có thể đặt thêm **Cloudflare Access** (Zero Trust) trước domain để bắt đăng nhập email/Google — token vẫn cần.
- `--host 0.0.0.0` đi qua http: token truyền dạng rõ trong LAN, ngoài mạng nhà nên dùng `--tunnel`.

## Theme màu và ngôn ngữ

- **`/theme`** mở màn hình chọn theme: 21 theme dựng sẵn (tối và sáng — nord, dracula, gruvbox, tokyo-night,
  catppuccin, solarized, rose-pine…) và màu nhấn tuỳ chọn (xanh dương, tím, xanh lá, cam, hồng, vàng, xanh ngọc,
  đỏ). Di chuyển là xem trước ngay; Enter lưu, Esc trả lại theme cũ. Lệnh nhanh: `/theme nord tím`,
  `/theme catppuccin-latte cam`. Màu trạng thái, viền popup, khung agent và diff đổi theo theme.
- **`/lang en`** / **`/lang vi`**: đổi ngôn ngữ giao diện (app tự mở lại). Ngoài app: `ateam lang en` (lưu),
  `ateam --lang en <lệnh>` hoặc `ATEAM_LANG=en` (một lần). Lần đầu dùng, ngôn ngữ theo `LANG` của máy.
- Thanh trạng thái phía trên phím tắt: nhánh git ↑↓, số task đang chạy / chờ / chờ duyệt / lỗi, agent đang
  nghỉ vì hết hạn mức, theme và ngôn ngữ (bấm vào để đổi).

Lựa chọn lưu ở `~/.config/ateam/state.json`, dùng chung mọi dự án.

## Xem tiến trình từng agent — tab "Đội" (Ctrl+T)

Mỗi agent một ô: model · effort đang dùng (và danh sách model/effort agent đó hỗ trợ), số task ✓ xong / ✗ lỗi / ⏳ chờ, task đang chạy kèm
thời gian chạy, số dòng output, dòng mới nhất, cảnh báo *im lặng* nếu quá 60 giây không có output,
và log trực tiếp (mỗi lần chạy có vạch ▶ bắt đầu / ■ kết thúc). Bên dưới là **timeline**: mỗi agent
một hàng, mỗi task một đoạn màu (tím = đang chạy, xanh = xong, đỏ = lỗi, vàng = trưởng nhóm đang lập
kế hoạch/review). Ctrl+T để quay lại Bảng việc.

### Chat trực tiếp với một agent (💬)

Mỗi ô agent có dòng **💬 Nhắn …** (web: ô chat dưới thẻ agent; hoặc `/chat <agent> [tin]` từ ô nhập chính). Mỗi tin
là một lượt chạy *tiếp đúng phiên CLI* của tin trước (`--resume` với claude/codex/grok; CLI không giữ phiên được thì
ateam gửi kèm các lượt trước) — như gõ trong terminal của CLI đó. Lượt chat chạy ở thư mục dự án, không chạy lệnh kiểm
tra, không worktree, không giao việc chéo và không hiện trên Bảng việc; trả lời hiện ngay trong ô agent.

- `/new` (trong ô chat): bắt đầu cuộc trò chuyện mới (phiên CLI mới).
- `/term` hoặc nút **⌨** (web): mở **CLI thật** của agent ở chế độ tương tác, tiếp tục phiên chat — TUI tạm nhường
  cả terminal (thoát CLI để quay lại ateam, các task khác vẫn chạy); web mở cửa sổ terminal (xterm.js) có hàng phím
  Esc · Tab · Ctrl+C · ↑↓ cho điện thoại. Ở đây dùng được mọi thứ của CLI (slash command, hỏi quyền…), nhưng ateam
  không đọc được kết quả của phần này.
- **F7**, `/focus [agent]`, `/focus` trong ô chat hoặc nút **⛶** (web): phóng to một agent cả tab Đội để chat riêng;
  F7 / Esc / gõ lại để thu về lưới.

## Lưới terminal — nhiều CLI thật cạnh nhau (tab 🔲 Lưới)

`/grid` (hoặc `/grid codex`) mở tab **🔲 Lưới**: mỗi ô là CLI tương tác thật của một agent (claude, codex, agy, grok,
opencode…) chạy trong thư mục dự án, gõ trực tiếp như terminal thường. **＋ Thêm agent** chọn CLI, model, effort, phiên
mới hay tiếp tục phiên gần nhất (`--resume`) và chỗ đặt ô.

- **Sắp xếp**: kéo tiêu đề ô thả lên ô khác (giữa = đổi chỗ, sát cạnh = đặt bên đó); bố cục nhanh: một cột, hai
  cột, lưới đều, lead + đội, một hàng. Web: kéo khe giữa các ô để đổi kích thước (đúp-click: chia đều), ⛶ toàn
  màn hình. TUI: **F10** vào chế độ sắp xếp bằng phím (←↑→↓ chọn, Shift+mũi tên đổi chỗ, `+/-` rộng, `[/]` cao).
- **⇉ Gửi tất cả**: phím gõ đi tới mọi ô đang bật "nhận phím khi gửi tất cả" — hỏi nhiều agent cùng một câu.
- Trong TUI, khi một ô đang được chọn thì phím Ctrl thuộc về CLI đó (Ctrl+Q vẫn thoát ateam).
- Bố cục lưu ở `.ateam/grid.json`; mở lại ateam thì ô hiện "chưa mở", bấm Enter / ⟲ để chạy lại CLI.

## Model & effort từng agent

Trong app (được lưu lại cho lần sau, ở `~/.config/ateam/state.json`):

```
/model claude opus             /effort claude high
/model codex gpt-5.5           /effort codex xhigh
/model antigravity <tên>       /effort antigravity high      (xem tên: agy models)
/model grok grok-4.7-build-fast   /effort grok high
/model opencode xai/grok-4.7   /effort opencode high         (OpenCode gọi là variant: chạy --model xai/grok-4.7#high)
/model codex -                 quay về mặc định
/model claude   /effort codex  mở bảng chọn từ danh sách agent đó hỗ trợ
/models                        xem model + effort mỗi agent hỗ trợ (● = đang dùng)
/models grok làm mới           hỏi CLI danh sách model thật (grok models, opencode models, agy models)
/agents                        xem tất cả + mức effort hợp lệ
/setup                         wizard thiết lập: CLI, kiểu làm việc, vai trò · model · effort, an toàn
/roles                         sửa nhanh bảng vai trò · CLI · model · effort (không đi lại cả wizard)
```

OpenCode được nhận diện tự động theo phiên bản: 1.x dùng `models --verbose` và `--variant`; 2.x dùng API
catalog theo thư mục dự án để lấy cả model/effort, rồi chạy với `--model provider/model#effort`. Cấu hình cũ và
agent tuỳ chỉnh dùng OpenCode vẫn được hỗ trợ. API catalog lỗi thì ateam thử `opencode models` và báo thiếu
metadata effort; gõ `/models opencode làm mới` để thử lại.

Tab Đội cũng hiện danh sách model/effort trong ô từng agent; bấm vào tiêu đề ô để chọn model rồi
effort. Ngoài app: `ateam models [agent] [--refresh]`.

Riêng cho 1 task: `/task codex@xhigh tìm lỗi deadlock`, `/task claude:opus@max thiết kế lại module auth`,
hoặc sửa task đang chờ: `/set 7 effort high`. Trưởng nhóm cũng tự chọn effort cho từng task khi lập kế
hoạch (tắt bằng `lead_sets_effort = false`). Ngoài app: `ateam set codex --model gpt-5.5 --effort high`.

Cách truyền cờ của từng CLI nằm trong `model_args` / `effort_args` ở file cấu hình — thêm agent mới chỉ cần
khai báo đúng cờ của nó.

## Tự kiểm tra sau mỗi task

```
/verify npm test          # hoặc: pytest -q, make check, cargo test …  (lưu riêng cho dự án này)
/verify off               # tắt
```

Sau mỗi task có thay đổi file, ateam chạy lệnh kiểm tra trong đúng thư mục của task. Fail thì giao sửa
kèm log lỗi (mặc định chính agent đó, tối đa 2 lần; đổi bằng `[verify] fix_agent`, `max_fix_attempts`).
Vẫn fail thì task báo lỗi. Agent chỉ đọc/nghiên cứu có thể đặt `verify = false`.

## Quyền của agent và agent tuỳ chỉnh

Mặc định agent **chỉ được sửa file**. Việc cần chạy lệnh (lint, build, `git commit/push`…) thì chọn **Toàn quyền**
ở bước *An toàn* của `/setup` (cả đội), hoặc cho riêng một agent tuỳ chỉnh trong form `/custom`: ateam tự đổi
đúng cờ cho từng CLI.
Agent bị chặn chạy lệnh thì task báo lỗi kèm hướng dẫn bật Toàn quyền (trước đây có CLI vẫn báo "xong").
Toàn quyền nghĩa là agent chạy được mọi lệnh trên máy — chỉ dùng với repo tin tưởng.

Thêm agent (`/custom` → *Thêm agent*): chọn **nhà cung cấp** (Claude Code, Codex, Antigravity, Grok Build, OpenCode),
**model**, **effort**, **quyền** và vai trò — mọi cờ CLI lấy từ mẫu. CLI khác (Gemini, Aider, lệnh riêng):
nút **Nâng cao…** mở form đầy đủ.

## Chạy lệnh terminal (dev server, test, build…)

Gõ `!` rồi lệnh ở ô nhập, ví dụ `!yarn dev`, `!make test` (hoặc `/sh yarn dev`). Lệnh chạy trong thư mục
dự án, output hiện trực tiếp ở tab **💻 Terminal** (Ctrl+T xoay vòng Bảng việc → Đội → Terminal → Git):
danh sách lệnh bên trái (đang chạy / ✓ xong / ✗ lỗi / ■ đã dừng, port phát hiện được như `:3000`),
output của lệnh đang chọn bên phải kèm link `http://localhost:<port>`, nút **■ Dừng**, **↻ Chạy lại**, **✗ Xoá**.
Nhiều lệnh chạy song song được; thanh agent ở tab Bảng việc nhắc khi còn lệnh đang chạy.

Gõ `!` để xem gợi ý: lệnh chạy gần đây, script trong `package.json` (tự dùng `pnpm`/`yarn`/`bun`/`npm` theo
lockfile), target trong `Makefile`. ↑↓ chọn rồi Enter chạy, Tab điền vào ô để sửa; Enter khi đã gõ lệnh thì
chạy đúng lệnh đã gõ. `/stop [số]` dừng lệnh. Thoát app (Ctrl+Q) sẽ dừng mọi lệnh đang chạy. Log đầy đủ ở
`.ateam/logs/sh<số>.log`.

## Quản lý git (tab 🌿 Git)

`/git` (hoặc Ctrl+T xoay tới tab **🌿 Git**) — làm mọi việc git hằng ngày mà không rời app:

- **Thanh trên**: nhánh hiện tại, upstream, `↑N` chưa push / `↓N` chưa pull, số stash, cảnh báo merge dở; nút
  **⇣ Fetch**, **⬇ Pull** (fast-forward, không được thì merge), **⬆ Push** (lần đầu tự tạo nhánh trên remote),
  **⎇ Nhánh**, **📦 Stash**, **✗ Huỷ merge** khi đang xung đột, **▶ Tiếp tục** (commit merge / `rebase --continue` /
  `cherry-pick --continue`) khi đã hết xung đột.
- **Giải quyết xung đột** (như VS Code): **Enter**/**r** trên file xung đột mở màn hình từng khối `<<<<<<<` — **o** giữ
  hiện tại, **t** lấy bên đến, **b** giữ cả hai; **O**/**T** lấy nguyên cả file một phía; **e** sửa tay ở tab Code;
  **m** đánh dấu đã xong. Hết khối thì file tự được stage. **g** / 🤖 *Nhờ agent* giao các file xung đột cho agent viết
  commit message (mặc định trưởng nhóm) sửa — xem tiến độ ở tab Đội, xong thì xem lại rồi đánh dấu đã xong.
- **File thay đổi** theo nhóm *Xung đột* / *Đã stage* / *Chưa stage*: **Space** stage/bỏ stage, **a** stage tất
  cả, **u** bỏ stage tất cả, **Enter**/**d** xem diff (màn hình diff hai cột như trên), **x** bỏ thay đổi (hỏi lại;
  file mới thì bị xoá), **X** / nút **↺ Bỏ tất cả** bỏ mọi thay đổi — đã stage lẫn chưa, xoá file chưa theo dõi, thư
  mục về đúng commit cuối (hỏi lại, nêu số file; file trong `.gitignore` giữ nguyên), **c** tới ô commit.
- **Commit**: gõ message rồi Enter (chưa stage gì thì commit mọi thay đổi). **✨ AI viết** (hoặc `/commit`
  không kèm message): agent chọn ở ô bên cạnh (mặc định trưởng nhóm; lựa chọn dùng chung terminal và web) đọc diff
  và viết message theo ngôn ngữ/kiểu các commit trước, bạn sửa rồi Enter. Commit xong ô message được xoá.
  Ô **Sửa commit trước** = `--amend` (tự điền message cũ). Ô **Bỏ qua hook (--no-verify)** commit mà không
  chạy git hook (pre-commit, commit-msg — husky, lint-staged…); ô giữ nguyên tới khi bạn bỏ tick. Commit bị hook
  chặn thì thông báo lỗi nhắc ô này.
- **Lịch sử** 80 commit gần nhất: **Enter** xem diff của commit, **r** / **↶ Revert** tạo commit đảo ngược,
  **⎌ Bỏ commit cuối** (giữ thay đổi để sửa; chỉ khi chưa push).
- **Nhánh**: danh sách nhánh local + remote (mới nhất trước, `[ahead/behind]`), Enter chuyển sang (nhánh remote →
  tạo nhánh local theo dõi), tạo mới, đổi tên, merge vào nhánh hiện tại, xoá / xoá hẳn.
- **Stash**: cất mọi thay đổi (kể cả file mới) kèm ghi chú, lấy lại (pop), áp dụng mà giữ stash, xoá.

Lệnh tắt: `/commit <message>`, `/commit --no-verify <message>` (hoặc `-n`), `/push [-f]` (`-f` = `--force-with-lease`), `/pull`, `/fetch`, `/branch [tên]`,
`/checkout <nhánh>`, `/stash [message]`, `/stash pop`. Việc khác (rebase, tag, cherry-pick, thêm remote):
`/git <lệnh>` chạy `git <lệnh>` ở tab Terminal. ateam không bao giờ hỏi mật khẩu trong app — push/pull cần
đăng nhập thì cấu hình SSH key hoặc credential helper trước. Đổi nhánh, pull, stash bị chặn khi agent đang chạy
task (chúng đang sửa thư mục hoặc sắp merge vào nhánh hiện tại).

## Xem & sửa code (tab 📝 Code)

`/code @src/app.py:42` (hoặc `/edit @file`, Ctrl+T tới tab 📝 Code, phím `e` ở tab Git / màn hình diff) mở file
trong editor có tô màu cú pháp, số dòng, phím **vim**:

- `i a I A o O` vào chế độ sửa, `Esc` về normal; di chuyển `h j k l w b e 0 ^ $ gg G Ctrl+D/U`, có số đếm
  (`5j`, `3dd`, `2dw`);
- sửa: `x dd D dw cw cc yy p P J r`, hoàn tác `u` / `Ctrl+R`, chọn `v` / `V` rồi `d y c > <`;
- tìm `/ ? n N *`; `:w` lưu, `:q` đóng, `:wq`, `:q!` bỏ thay đổi, `:e!` nạp lại, `:42` tới dòng, `:bn` `:bp`
  đổi file, `:files` ẩn/hiện danh sách file.

Không quen vim: `/vim off` (sửa như editor thường, Ctrl+S lưu). Cột trái liệt kê file đang mở và file của dự án
(gõ để lọc). Agent sửa file bạn đang mở: chưa sửa gì thì tự nạp lại, đang sửa thì được báo — `:e!` lấy bản
trên đĩa, `:w!` ghi đè. Thoát app khi còn file chưa lưu sẽ được hỏi lại.

Editor chỉ vẽ các dòng đang hiện; tô màu chạy nền sau khi bạn ngừng gõ ~0,2 giây, nên file lớn vẫn mượt. File
trên 2 MB / 20 000 dòng không tô màu, trên 5 MB mở chỉ đọc, file nhị phân không mở.

**Command palette** như VS Code (TUI và web):

- **Ctrl+P** (web: ⌘P): mở nhanh file — gõ rải rác tên file (`apppy` → `src/app.py`), file mở gần đây đứng đầu
  (dùng chung TUI ↔ web).
- Gõ **`>`** (hoặc F8, web ⌘⇧P): lệnh — lưu tất cả, file mới, đổi tên / chuyển, xoá vào Thùng rác, xuống dòng mềm,
  số dòng, phím vim, chép đường dẫn, xem diff git của file, mở trong VS Code, tìm & thay trong dự án. Gõ từ khoá
  tiếng Anh như VS Code cũng được (`>wrap`, `>rename`).
- **`@`** (F9, web ⌘⇧O): tới hàm / class / heading trong file; thanh trên editor hiện `› tên hàm` đang đứng.
- **`:42`** tới dòng 42, **`/chữ`** liệt kê các dòng có chữ đó trong file.
- **＋ File mới**: nút ở cột danh sách file (hoặc `:new đường/dẫn` trên TUI, `>File mới` trong palette); gõ đường dẫn có
  thư mục thì thư mục được tạo luôn.
- **Hỏi agent về đoạn đang chọn** / **Giao task cho agent**: chọn agent, gõ câu hỏi — agent nhận `@file (dòng a–b)`
  kèm câu hỏi (hỏi = chat 💬 ở tab Đội; giao task = hiện trên Bảng việc).

## Rule của dự án

`/rules` (web: nút 📏 trên thanh trên) quản lý các rule mà **mọi agent phải tuân theo** trong dự án này — như
`AGENTS.md` của Codex hay `.agents/rules` của Antigravity, nhưng ateam tự gửi kèm ở đầu mỗi prompt (task, `/task`,
chat 💬, lập kế hoạch, review, `/grill`, viết commit message), nên agent nào cũng nhận, kể cả agent tuỳ chỉnh:

- Thêm / sửa / xoá, đổi thứ tự; **bật/tắt** từng rule mà không phải xoá. `/rules <nội dung>` thêm nhanh một rule.
- **Áp dụng cho**: để trống = mọi agent; hoặc chọn vài agent (vd chỉ `codex`) và/hoặc vai trò (vd *Trưởng nhóm* —
  gồm mọi lượt lập kế hoạch, review).
- Lưu **riêng máy này**, ngoài repo (`~/.config/ateam/rules/…`), không lẫn vào commit.
- Chat đang tiếp tục phiên CLI: ateam chỉ gửi lại rule khi bạn vừa đổi bộ rule.
- Popup liệt kê luôn các file rule **có sẵn trong repo** mà CLI tự đọc (`AGENTS.md` — claude, codex, agy, grok,
  opencode; `CLAUDE.md`; `GEMINI.md`; `.agents/rules/*.md`; `.claude/rules/*.md`; `.grok/rules/*`) — bấm để mở ở tab
  Code. ateam không gửi kèm các file này (CLI đã tự đọc).

## Mở folder / dự án khác

`/open` (hoặc bấm tên dự án góc trên bên trái ở web, hay `>Mở folder` trong palette tab Code) mở popup như
*File › Open Recent* của VS Code:

- Để trống: các dự án mở gần đây; gõ chữ để lọc theo tên thư mục.
- Gõ đường dẫn (`~/code/app`, `/Users/…`, `../app-khac` — tương đối là tính từ thư mục chứa dự án đang mở): hiện các
  thư mục con khớp; **Tab** đi vào thư mục đang chọn, **Enter** mở. `/open ~/code/app` mở thẳng.

ateam mở lại ở thư mục mới — bảng việc, cấu hình dự án, Git, Code, Terminal đều là của dự án đó (thư mục chưa
có `.ateam/` thì được tạo như lần đầu chạy `ateam` ở đó). Web giữ nguyên địa chỉ, trang tự nạp lại. Đang có agent
chạy thì được hỏi trước (task dở thành lỗi, quay lại thì `/retry`); tab Code còn file chưa lưu cũng được hỏi.
Không đổi được khi mở web từ xa (`--host`, `--tunnel`, `--public-url`: token chỉ cấp cho một dự án) và trong
`ateam web --tui`.

## Xem diff và duyệt merge (chế độ worktree)

Đặt `merge = "review"`: task xong (và qua kiểm tra) dừng ở trạng thái **chờ duyệt**.
**Ctrl+D** / `/diff 3` mở màn hình xem diff kiểu VS Code: danh sách file bên trái (M sửa · A thêm · D xoá ·
R đổi tên, kèm +/−), diff file đang chọn bên phải với số dòng, tô màu cú pháp và tô đậm từ bị đổi.
Mặc định **hai cột** (cũ | mới), `s` đổi sang một cột; ↑↓ chọn file, `]` `[` nhảy giữa các đoạn đổi,
`o` mở file đó trong VS Code (`code --diff`), Esc đóng. Ở chế độ shared màn hình này hiện mọi thay đổi
chưa commit của thư mục, gồm cả file mới chưa track.
**Ctrl+Y** / `/merge 3` để merge (từ màn hình diff cũng được),
`/reject 3 thiếu xử lý lỗi null` để giao làm lại kèm góp ý (`/reject 3` không góp ý = huỷ).
Task phụ thuộc chỉ chạy sau khi task trước được merge. Ngoài app: `ateam diff|merge|reject`.

## Hạn mức và agent dự phòng

Khi một agent báo hết hạn mức (rate limit / usage limit), ateam cho nó tạm nghỉ đến lúc hạn mức hồi
(đọc từ thông báo của CLI, không có thì 30 phút) và chuyển task sang agent trong `fallback` của nó.
Trưởng nhóm hết hạn mức thì `lead_fallback` lập kế hoạch/review thay. `/usage` (hoặc `ateam usage`) xem số
lượt, thời gian, token ước tính theo agent, rồi hỏi song song **hạn mức thật** từ CLI của từng agent:
Claude Code `claude -p /usage` (% phiên/tuần đã dùng, giờ hồi), Antigravity `agy -p /usage` (quota còn lại
theo nhóm model), OpenCode `opencode stats --days 7` (token, chi phí), Codex đọc ảnh chụp hạn mức trong file
phiên gần nhất (`~/.codex/sessions`; codex không có lệnh xem hạn mức mà không gọi model). `ateam usage --local`
bỏ phần hỏi CLI; `/cooldown codex 60` cho nghỉ tay, `/cooldown codex off` để bỏ.

## Thống kê: token, cost, lịch sử mục tiêu (`/dash`)

Tab **📊 Thống kê** (web: mục *Thống kê*): token (input · output · cache), cost, số lượt, thời gian chạy của hôm
nay / 7 / 30 ngày; biểu đồ token 14 ngày; bảng theo agent và theo model; **lịch sử mục tiêu** (đề bài, trạng
thái, task xong/lỗi, agent tham gia, token, cost, kết quả) — Enter (web: nút *Tiếp tục mục tiêu*) để giao thêm
việc bằng `/continue`.

Token của **Claude Code** và **Codex** là số thật, đọc từ file phiên mà CLI tự ghi (`~/.claude/projects`,
`~/.codex/sessions`) — ateam không đổi cách chạy CLI. Agent khác (agy, grok, opencode…) ước tính ~4 ký tự/token
(cột *Số thật* cho biết bao nhiêu lượt có số thật). Cost ước tính theo bảng giá công khai; model chưa có giá hiện
"—", thêm bằng `[prices."<model>"]` trong `config.toml` (xem `docs/CONFIG.md`).

## Thông báo

Khi có **kế hoạch chờ duyệt**, **task chờ duyệt diff**, **agent hỏi**, **task lỗi / xung đột merge**, hoặc **mục
tiêu kết thúc**, ateam báo: terminal hiện
toast + chuông + thông báo macOS (Notification Center); web hiện toast và thông báo của trình duyệt khi tab đang ẩn
(trình duyệt hỏi quyền ở lần bấm đầu tiên trên trang), tiêu đề tab hiện số việc chờ. `/notify app` chỉ báo trong
app, `/notify off` tắt, `/notify on` bật lại, `/notify test` gửi thử.

Web còn phát **âm thanh** riêng cho từng loại (kế hoạch, diff chờ duyệt, agent hỏi, lỗi, mục tiêu xong) — bật/tắt,
chỉnh âm lượng và nghe thử ở popup 🎨 Giao diện; lưu riêng cho từng trình duyệt (máy tính và điện thoại đặt khác nhau
được). Trình duyệt chỉ cho phát âm sau lần bấm đầu tiên trên trang.

## Các agent giao việc cho nhau thế nào?

Mỗi agent nhận kèm hướng dẫn: nếu một phần việc hợp với thành viên khác hơn, nó in ra

```
<<<DELEGATE to="codex" title="Viết test">>>
nội dung yêu cầu...
<<<END>>>
```

`ateam` đọc output và tự tạo task mới cho agent đó (giới hạn bởi `max_delegation_depth`).
`<<<NOTE>>>...<<<END>>>` là ghi chú chung — mọi task sau đều thấy. Kết quả (dòng `SUMMARY:`) của task
được chuyển cho các task phụ thuộc vào nó. Agent nào chạy được lệnh shell cũng có thể gọi
`ateam add --to <agent> "..."` trực tiếp.

## Agent và workflow tuỳ chỉnh

Gõ `/custom` để mở tab **🧩 Tuỳ chỉnh** (web: mục *Tuỳ chỉnh* ở sidebar; ở màn hình thiết lập vẫn có nút
*Agent & workflow tuỳ chỉnh…* mở cùng nội dung dạng popup).

**Gõ mục tiêu chạy workflow nào**: nút ngay bên trái ô nhập (TUI: bấm hoặc **F4**) cho chọn *★ Trưởng nhóm lập kế
hoạch* hay một workflow (kể cả workflow bạn tự tạo) — từ đó gõ prompt thẳng là chạy workflow đó, không cần
`/flow <tên>`; `/goal` vẫn luôn để trưởng nhóm lập kế hoạch. Mỗi workflow ở tab Tuỳ chỉnh cũng có nút **★ Đặt mặc
định** / **☆ Bỏ mặc định**. Lựa chọn dùng chung cho terminal và web.

**Luồng mặc định** (`/flow-setup`, nút *⚙ Luồng mặc định* ở tab Tuỳ chỉnh, hoặc *⚙ Cấu hình luồng cố định…* ở bước
*Kiểu làm việc* của `/setup`): chọn workflow chạy khi gõ mục tiêu và agent · model · effort cho từng bước (vd Thiết
kế = trưởng nhóm, Viết code = codex `high`, Viết test = antigravity), bật/tắt trưởng nhóm review cuối. Sửa tiêu
đề/prompt hay thêm bước thì dùng *Sửa* workflow ở tab Tuỳ chỉnh. Mọi thứ lưu ở `~/.config/ateam/custom.toml`, file này **không bị
thay** khi `config.toml` được nâng cấp lên bản mới.

**Thêm agent**: bất kỳ CLI nào có chế độ headless (nhận prompt, in kết quả rồi thoát). Chọn *Mẫu* để điền
sẵn (claude, codex, agy, opencode, Gemini CLI, Aider, hoặc trống), rồi sửa: lệnh (`{prompt}` = nội dung
task), vai trò (trưởng nhóm phân việc dựa vào đây), model mặc định + model gợi ý + cờ truyền model,
các mức effort + cờ truyền effort, lệnh liệt kê model, cách nhắc file `@` (`@{path}` hay `{path}`, cờ
đính file như `-f {path}`, cờ đính ảnh như `--image={path}`), agent dự phòng khi hết hạn mức, timeout, pty. Dòng *Lệnh sẽ chạy* ở cuối form
cho thấy lệnh thật và CLI đã cài chưa. Lưu xong, agent vào đội ngay (ô riêng ở tab Đội, bật/tắt và chọn
model/effort ở `/setup`, trưởng nhóm thấy nó khi lập kế hoạch).

**Thêm workflow**: chuỗi bước dựng sẵn, chạy không cần trưởng nhóm lập kế hoạch. Mỗi bước gồm agent (hoặc
*trưởng nhóm*), tiêu đề, prompt (`{goal}` = mục tiêu bạn gõ), *Sau bước* (trống = sau bước liền trước, `0`
= chạy ngay song song, `1,2` = sau bước 1 và 2) và effort riêng. Có mẫu *tính năng mới* (thiết kế → code →
test), *sửa lỗi* (tái hiện → sửa → test chống tái diễn), *review code*. Tick *Trưởng nhóm review khi
xong* để trưởng nhóm review và giao thêm việc như mục tiêu thường.

Không muốn tự điền từng bước? Gõ quy trình bạn muốn vào ô **✨ Gợi ý** (vd: *"thiết kế API, hai agent code
song song backend và frontend, rồi viết test e2e"*) rồi Enter / bấm *Gợi ý*: trưởng nhóm thiết kế các bước
theo đúng thành viên trong đội — agent, tiêu đề, prompt có `{goal}`, *Sau bước*, effort — và điền sẵn vào form
(chưa lưu). Sửa lại nếu cần rồi lưu. Agent không có trong đội thành trưởng nhóm, effort không hợp lệ bị bỏ.

```
/flow                                  xem các workflow
/flow tinh-nang thêm đăng nhập Google  tạo mục tiêu theo workflow (các bước ở trạng thái nháp → /go)
ateam flow -y tinh-nang "thêm đăng nhập Google"   chạy ngoài app
ateam flows                            liệt kê workflow
```

Sửa tay cũng được (`/custom` đọc lại file):

```toml
# ~/.config/ateam/custom.toml
[agents.aider]
command = ["aider", "--yes-always", "--no-auto-commits", "--message", "{prompt}"]
model_args = ["--model", "{model}"]
file_args = ["--file", "{path}"]
role = "Sửa code theo yêu cầu cụ thể."

[workflows.sua-loi]
description = "tái hiện → sửa → test"
review = true

[[workflows.sua-loi.steps]]
agent = "codex"
title = "Tái hiện lỗi"
prompt = "Tìm nguyên nhân và cách tái hiện lỗi: {goal}. Chưa sửa code."

[[workflows.sua-loi.steps]]
agent = "lead"                     # trưởng nhóm hiện tại
title = "Sửa lỗi"
prompt = "Sửa lỗi theo phân tích ở bước trước: {goal}"
effort = "high"
```

## Cấu hình

`~/.config/ateam/config.toml` (tạo tự động), ghi đè riêng cho từng dự án bằng `ateam init --project`
→ `.ateam/config.toml`. Có thể đổi trưởng nhóm, vai trò từng agent, lệnh chạy, timeout, số task song song.

Thêm agent mới: dùng `/custom` (mục trên), hoặc một khối trong file cấu hình:

```toml
[agents.gemini]
command = ["gemini", "-p", "{prompt}", "--yolo"]
role = "Đọc codebase lớn, viết tài liệu."
```

**Chế độ làm việc** (`isolation`):

* `shared` (mặc định): mọi agent làm chung thư mục. Đơn giản; trưởng nhóm được dặn không cho 2 task song
  song sửa cùng file.
* `worktree`: mỗi task chạy trong một git worktree riêng (`ateam/t<id>`), xong thì tự commit và merge vào
  nhánh hiện tại. Nếu xung đột, task chuyển sang **xung đột** và nhánh được giữ lại để bạn merge tay.
  Cần chạy ở thư mục gốc của repo đã có ít nhất 1 commit.

## Lưu ý riêng từng CLI

* **Claude Code**: mặc định `--permission-mode acceptEdits` (được sửa file, không chạy lệnh shell).
  Muốn cho chạy test/build, đổi thành `bypassPermissions` — chỉ trong repo bạn tin tưởng.
* **Codex**: `codex exec --sandbox workspace-write` — sửa file và chạy lệnh trong sandbox của Codex
  (Codex 0.152 trở đi đã bỏ `--full-auto`; cấu hình cũ còn cờ này được ateam tự đổi).
* **Antigravity (`agy`)**: chỉ in output khi có terminal thật, nên `ateam` chạy nó trong pseudo-terminal
  (`pty = true`), với `--mode accept-edits` (được sửa file) và `--print-timeout 0`. Muốn cho chạy cả lệnh
  shell: thay `--mode accept-edits` bằng `--dangerously-skip-permissions`.
* **Grok Build (`grok`)**: `grok --permission-mode auto --deny Bash -p "<prompt>"` — được sửa/tạo file, không
  chạy lệnh shell (`acceptEdits` của grok ở chế độ `-p` chặn cả sửa file nên ateam không dùng). Toàn quyền đổi thành
  `--permission-mode bypassPermissions` (chạy lệnh, mạng). Model bằng `-m` (`grok models`), effort
  `--reasoning-effort` (low, medium, high, xhigh). Cần `grok login` trước. Khi bị chặn lệnh, grok chỉ kể lại bằng
  lời rồi thoát 0 — ateam nhận ra câu đó và báo task lỗi kèm hướng dẫn bật Toàn quyền. Grok Build chưa có lệnh xem
  hạn mức chung nên `/usage` chỉ hiện thống kê của ateam.
* **OpenCode**: `opencode run --model xai/grok-build-0.1 ...` (chạy được nhiều nhà cung cấp; xem model bằng
  `opencode models`). Toàn quyền thêm `--auto`. Từ bản 0.6, agent `grok` cũ (chạy qua OpenCode) đổi tên thành
  `opencode`; lựa chọn model/effort đã lưu được chuyển theo.

## Dữ liệu

Mọi thứ nằm trong `.ateam/` của dự án (đã tự gitignore): `team.db` (bảng việc), `logs/t<id>.log`,
`logs/lead.log` (output lập kế hoạch/review của trưởng nhóm), `logs/system.log`.

## Trang docs (Cloudflare Workers)

Trang giới thiệu và file tải nằm trong `site/`; `scripts/build_site.py` dựng chúng vào `dist/`
(điền phiên bản và đóng gói `ateam-<version>.zip`). `wrangler.jsonc` deploy `dist/` lên Cloudflare
Workers dưới dạng static assets, nên chỉ cần:

```bash
npx wrangler deploy        # tự chạy python3 scripts/build_site.py trước
```

Khi repo được nối với Workers Builds, mỗi lần push lên `main` sẽ tự build và deploy lại.

## Phát triển

Đọc `AGENTS.md` trước (điểm vào cho cả người lẫn AI agent), rồi `docs/`:
[kiến trúc](docs/ARCHITECTURE.md), [phát triển & test](docs/DEVELOPMENT.md),
[cấu hình](docs/CONFIG.md), [quyết định thiết kế](docs/DECISIONS.md), [lộ trình](docs/ROADMAP.md),
[phát hành](docs/RELEASING.md). Lịch sử thay đổi: [CHANGELOG.md](CHANGELOG.md).

```bash
pip install -e ".[dev]" && python -m pytest -q
```
