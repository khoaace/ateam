"""agy (Antigravity) `--output-format stream-json`: mỗi dòng một sự kiện JSON → dòng log dễ đọc.

Ở chế độ chữ agy chỉ in câu trả lời cuối — ô agent trống suốt vài phút như treo, không biết id phiên, không có token
thật. stream-json báo id phiên (`init`), từng bước tool, chữ trả lời (`text_delta`) và token (`result.usage`).
`Run` tự dùng bộ đọc này khi lệnh là `agy … --output-format stream-json` (cờ do `AgentConfig.argv` thêm, xem
`SESSION_PRESETS`). Dòng không phải JSON (lỗi, cảnh báo) đi qua nguyên văn để nhận diện hết hạn mức như cũ."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .usage_logs import Usage

# agy --conversation <id không còn>: in cảnh báo rồi lặng lẽ mở phiên MỚI và vẫn thoát 0 (đã thử agy 1.4.4)
LOST_RE = re.compile(r'^warning: conversation "[^"]*" not found')
SESSION_LINE = "agy conversation {id}"
SESSION_RE = r"agy conversation ([0-9a-fA-F-]{36})"
# tham số đáng hiện của từng tool (thứ tự ưu tiên); không có thì lấy chuỗi đầu tiên
PARAM_KEYS = ("CommandLine", "Command", "Path", "AbsolutePath", "File", "TargetFile", "Query", "Url", "Pattern")

OUT, SHOW, META = "out", "show", "meta"  # vào output (bóc SUMMARY…) · chỉ hiện · hiện + bắt id phiên


def wants(argv: list[str]) -> bool:
    if not argv or Path(argv[0]).name != "agy":
        return False
    if "--output-format=stream-json" in argv:
        return True
    return any(a == "--output-format" and argv[i + 1:i + 2] == ["stream-json"] for i, a in enumerate(argv))


def tool_label(step: dict, cwd: str = "") -> str:
    name = step.get("tool_name") or (step.get("tool_info") or {}).get("name") or "tool"
    params = (step.get("tool_info") or {}).get("parameters") or {}
    val = next((params[k] for k in PARAM_KEYS if isinstance(params.get(k), str) and params[k]), None)
    if val is None:
        val = next((v for v in params.values() if isinstance(v, str) and v), "")
    val = " ".join(val.split())
    if cwd:  # đường dẫn trong dự án: bỏ phần thư mục dự án cho gọn
        val = val.replace(cwd.rstrip("/") + "/", "")
    return f"{name} {val[:160]}{'…' if len(val) > 160 else ''}".rstrip()


class AgyStream:
    """Bộ đọc của một lượt chạy: `feed(dòng)` trả [(dòng, OUT|SHOW|META)]."""

    def __init__(self):
        self.session: str | None = None
        self.cwd = ""
        self.usage: Usage | None = None
        self.lost = False       # --conversation không còn: agy đã mở phiên mới thiếu ngữ cảnh
        self.text = ""          # mọi chữ trả lời đã stream
        self._partial = ""

    def _flush(self) -> list[tuple[str, str]]:
        out = [(self._partial, OUT)] if self._partial else []
        self._partial = ""
        return out

    def _delta(self, delta: str, done: bool) -> list[tuple[str, str]]:
        self.text += delta
        *lines, self._partial = (self._partial + delta).split("\n")
        out = [(ln, OUT) for ln in lines]
        return out + self._flush() if done else out

    def feed(self, line: str) -> list[tuple[str, str]]:
        s = line.strip()
        if not s.startswith("{"):
            if self.session is None and LOST_RE.match(s):
                self.lost = True
            return [(line, OUT)]
        try:
            ev = json.loads(s)
        except ValueError:
            return [(line, OUT)]
        if not isinstance(ev, dict):
            return [(line, OUT)]
        kind = ev.get("event")
        if kind == "init":
            self.session = ev.get("conversation_id") or None
            self.cwd = str((ev.get("init") or {}).get("cwd") or "")
            return [(SESSION_LINE.format(id=self.session), META)] if self.session else []
        if kind == "step_update":
            st = ev.get("step_update") or {}
            typ, state = st.get("step_type"), st.get("state")
            if typ == "agent_response":
                return self._delta(st.get("text_delta") or "", state == "DONE")
            if typ == "tool" and state == "ACTIVE":
                return self._flush() + [("▸ " + tool_label(st, self.cwd), SHOW)]
            if typ == "tool" and state not in ("ACTIVE", "DONE"):
                return [(f"✗ {tool_label(st, self.cwd)} ({state})", SHOW)]
            return []
        if kind == "result":
            r = ev.get("result") or {}
            out = self._flush()
            resp = (r.get("response") or "").strip()
            if resp and resp not in self.text:  # chữ không stream qua text_delta: lấy câu trả lời cuối
                out += [(ln, OUT) for ln in resp.split("\n")]
            u = r.get("usage") or {}
            if u:
                self.usage = Usage(in_tok=int(u.get("input_tokens") or 0), out_tok=int(u.get("output_tokens") or 0),
                                   cache_read=int(u.get("cache_read_tokens") or 0))
            status = r.get("status")
            if status and status != "SUCCESS":
                err = r.get("error") or r.get("message") or ""
                out.append((f"✗ agy: {status} {err if isinstance(err, str) else json.dumps(err)}".rstrip(), OUT))
            return out
        return []
