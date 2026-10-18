"""Đọc phần cuối file log mà không đọc cả file (log task / system.log có thể vài MB)."""

from __future__ import annotations

from pathlib import Path

LOG_TAIL_BYTES = 192 * 1024  # mở log 1 task: chỉ đọc chừng này byte cuối (file vài MB đọc + tô màu rất chậm)


def read_log_tail(path: Path, start: int = 0, limit: int = LOG_TAIL_BYTES) -> str:
    """Phần cuối file log từ byte `start` (bỏ dòng bị cắt dở ở đầu nếu phải bỏ bớt)."""
    with open(path, "rb") as f:
        size = f.seek(0, 2)
        if start > size:  # file bị ghi lại từ đầu (task chạy lại)
            start = 0
        begin = max(start, size - limit)
        f.seek(begin)
        data = f.read()
    if begin > start:
        nl = data.find(b"\n")
        data = data[nl + 1:] if nl >= 0 else b""
    return data.decode("utf-8", errors="replace")


def read_tail(path: Path, n: int, limit: int = LOG_TAIL_BYTES) -> list[str]:
    """n dòng cuối của file ([] nếu chưa có)."""
    try:
        return read_log_tail(path, limit=limit).splitlines()[-n:]
    except OSError:
        return []
