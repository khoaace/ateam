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
tại). Agent tuỳ chỉnh bạn tự thêm ở `/custom` được giữ nguyên.

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

### Dán ảnh (Ctrl+V)

Chụp màn hình vào clipboard (vd **Cmd+Ctrl+Shift+4** trên macOS) rồi bấm **Ctrl+V** trong ô nhập: ảnh
được lưu ở `.ateam/images/` và ô nhập có thêm `@.ateam/images/paste-….png`. Kéo-thả file ảnh từ
Finder vào terminal cũng ra `@ảnh`. Khi chạy, ảnh đi như `@file` ở trên, riêng **codex** được thêm cờ
`--image=<ảnh>` để thấy ảnh thật (đổi bằng `image_args`). macOS dùng `osascript` có sẵn (hoặc
`pngpaste` nếu đã cài); Linux cần `wl-paste` hoặc `xclip`. Cmd+V vẫn dán chữ như thường.

## Xem tiến trình từng agent — tab "Đội" (Ctrl+T)

Mỗi agent một ô: model · effort đang dùng (và danh sách model/effort agent đó hỗ trợ), số task ✓ xong / ✗ lỗi / ⏳ chờ, task đang chạy kèm
thời gian chạy, số dòng output, dòng mới nhất, cảnh báo *im lặng* nếu quá 60 giây không có output,
và log trực tiếp (mỗi lần chạy có vạch ▶ bắt đầu / ■ kết thúc). Bên dưới là **timeline**: mỗi agent
một hàng, mỗi task một đoạn màu (tím = đang chạy, xanh = xong, đỏ = lỗi, vàng = trưởng nhóm đang lập
kế hoạch/review). Ctrl+T để quay lại Bảng việc.

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
```

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
  **⎇ Nhánh**, **📦 Stash**, **✗ Huỷ merge** khi đang xung đột.
- **File thay đổi** theo nhóm *Xung đột* / *Đã stage* / *Chưa stage*: **Space** stage/bỏ stage, **a** stage tất
  cả, **u** bỏ stage tất cả, **Enter**/**d** xem diff (màn hình diff hai cột như trên), **x** bỏ thay đổi (hỏi lại;
  file mới thì bị xoá), **c** tới ô commit.
- **Commit**: gõ message rồi Enter (chưa stage gì thì commit mọi thay đổi). **✨ Trưởng nhóm viết** (hoặc `/commit`
  không kèm message): trưởng nhóm đọc diff và viết message theo ngôn ngữ/kiểu các commit trước, bạn sửa rồi Enter.
  Ô **Sửa commit trước** = `--amend` (tự điền message cũ).
- **Lịch sử** 80 commit gần nhất: **Enter** xem diff của commit, **r** / **↶ Revert** tạo commit đảo ngược,
  **⎌ Bỏ commit cuối** (giữ thay đổi để sửa; chỉ khi chưa push).
- **Nhánh**: danh sách nhánh local + remote (mới nhất trước, `[ahead/behind]`), Enter chuyển sang (nhánh remote →
  tạo nhánh local theo dõi), tạo mới, đổi tên, merge vào nhánh hiện tại, xoá / xoá hẳn.
- **Stash**: cất mọi thay đổi (kể cả file mới) kèm ghi chú, lấy lại (pop), áp dụng mà giữ stash, xoá.

Lệnh tắt: `/commit <message>`, `/push [-f]` (`-f` = `--force-with-lease`), `/pull`, `/fetch`, `/branch [tên]`,
`/checkout <nhánh>`, `/stash [message]`, `/stash pop`. Việc khác (rebase, tag, cherry-pick, thêm remote):
`/git <lệnh>` chạy `git <lệnh>` ở tab Terminal. ateam không bao giờ hỏi mật khẩu trong app — push/pull cần
đăng nhập thì cấu hình SSH key hoặc credential helper trước. Đổi nhánh, pull, stash bị chặn khi agent đang chạy
task (chúng đang sửa thư mục hoặc sắp merge vào nhánh hiện tại).

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

Gõ `/custom` (hoặc bấm *Agent & workflow tuỳ chỉnh…* ở màn hình thiết lập) để mở màn hình quản lý,
cùng kiểu với màn hình thiết lập. Mọi thứ lưu ở `~/.config/ateam/custom.toml`, file này **không bị
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
