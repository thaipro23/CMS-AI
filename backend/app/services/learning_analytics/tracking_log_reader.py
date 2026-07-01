from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(slots=True)
class TrackingReadResult:
    lines: list[str]
    start_offset: int
    end_offset: int
    file_exists: bool
    file_path: str
    file_inode: str | None
    file_size: int
    rotated: bool = False


class TrackingLogReader:
    """Streaming tracking.log reader with offset and rotate awareness."""

    def __init__(self, file_path: str, *, max_lines: int = 50000):
        self.file_path = str(file_path)
        self.max_lines = max(1, int(max_lines or 50000))

    def stat(self) -> tuple[bool, str | None, int]:
        path = Path(self.file_path)
        if not path.exists():
            return False, None, 0
        st = path.stat()
        return True, str(getattr(st, 'st_ino', '') or ''), int(st.st_size or 0)

    def read_from(self, *, last_offset: int = 0, last_inode: str | None = None) -> TrackingReadResult:
        exists, inode, size = self.stat()
        if not exists:
            return TrackingReadResult([], 0, 0, False, self.file_path, None, 0, False)
        rotated = False
        start_offset = max(0, int(last_offset or 0))
        if last_inode and inode and last_inode != inode:
            start_offset = 0
            rotated = True
        if start_offset > size:
            start_offset = 0
            rotated = True
        lines: list[str] = []
        end_offset = start_offset
        with open(self.file_path, 'rb') as handle:
            handle.seek(start_offset, os.SEEK_SET)
            for _ in range(self.max_lines):
                raw = handle.readline()
                if not raw:
                    break
                end_offset = handle.tell()
                lines.append(raw.decode('utf-8', errors='replace'))
        return TrackingReadResult(lines, start_offset, end_offset, True, self.file_path, inode, size, rotated)
