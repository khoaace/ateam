"""Đa ngôn ngữ (vi/en) cho chữ hiển thị với người dùng.

Khoá là chính chuỗi tiếng Việt gốc: `tr("Đã merge #{tid}", tid=5)`. Ngôn ngữ `vi` (hoặc chuỗi chưa có bản
dịch) trả lại chuỗi Việt; `en` tra `locales/en.py`. Prompt gửi agent không đi qua đây (luôn tiếng Anh).

Ngôn ngữ chọn một lần lúc khởi động (`detect_lang`): đổi trong app (`/lang`) thì lưu rồi mở lại app, vì
nhiều chuỗi được tính sẵn lúc import (bảng lệnh, phím tắt, nhãn trạng thái).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

LANGS = ("vi", "en")
LANG_NAMES = {"vi": "Tiếng Việt", "en": "English"}

_lang = "vi"
_en: dict[str, str] | None = None


def _state_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ateam" / "state.json"


def _argv_lang(argv: list[str]) -> str | None:
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return None


def normalize(code: str | None) -> str | None:
    code = (code or "").strip().lower()
    if code.startswith("vi") or code in ("tieng-viet", "tiếng-việt"):
        return "vi"
    if code.startswith("en"):
        return "en"
    return None


def detect_lang(argv: list[str] | None = None) -> str:
    """--lang trên dòng lệnh > ATEAM_LANG > "lang" trong state.json > máy đã dùng ateam (vi) > LANG."""
    for code in (_argv_lang(sys.argv if argv is None else argv), os.environ.get("ATEAM_LANG")):
        if normalize(code):
            return normalize(code)
    sf = _state_file()
    try:
        state = json.loads(sf.read_text(encoding="utf-8"))
    except Exception:
        state = None
    if isinstance(state, dict) and normalize(state.get("lang")):
        return normalize(state.get("lang"))
    if state is not None:
        return "vi"  # người dùng cũ: giữ tiếng Việt như trước
    sys_lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    return "vi" if sys_lang.lower().startswith("vi") else "en"


def set_lang(code: str) -> None:
    global _lang
    _lang = normalize(code) or "vi"


def get_lang() -> str:
    return _lang


def save_lang(code: str) -> None:
    """Lưu ngôn ngữ vào state.json (dùng chung mọi dự án)."""
    sf = _state_file()
    try:
        state = json.loads(sf.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    except Exception:
        state = {}
    state["lang"] = normalize(code) or "vi"
    from .config import atomic_write  # config import i18n: nạp muộn để khỏi vòng import
    atomic_write(sf, json.dumps(state, ensure_ascii=False, indent=2))


def _catalog() -> dict[str, str]:
    global _en
    if _en is None:
        try:
            from .locales.en import EN
        except Exception:  # thiếu file dịch: vẫn chạy bằng tiếng Việt
            EN = {}
        _en = EN
    return _en


def tr(vi: str, **kw) -> str:
    """Chuỗi hiển thị theo ngôn ngữ hiện tại. kw điền vào {tên} (str.format)."""
    s = _catalog().get(vi, vi) if _lang == "en" else vi
    if kw:
        try:
            return s.format(**kw)
        except (KeyError, IndexError, ValueError):
            return vi.format(**kw)
    return s


set_lang(detect_lang())
