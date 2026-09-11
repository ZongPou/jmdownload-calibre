"""给 calibredb 包一层，用来把书塞进 Calibre 书库。"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

_ADDED_IDS = re.compile(r"Added book ids:\s*(.+)")


class CalibreError(RuntimeError):
    pass


def find_calibredb() -> str | None:
    """在 PATH 里找 calibredb。"""
    return shutil.which("calibredb")


def _run(calibredb: str, args: list[str], library: Path | str | None = None) -> str:
    cmd = [calibredb, *args]
    if library:
        cmd += ["--library-path", str(library)]

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise CalibreError(detail or f"calibredb 失败了: {' '.join(cmd)}")
    return proc.stdout or ""


def add_book(calibredb: str, book: Path, library: Path | str | None = None,
             allow_duplicate: bool = False) -> list[str]:
    """添加一本书，返回 calibredb 报告的书 id 列表。"""
    args = ["add", str(book)]
    if allow_duplicate:
        args.append("--duplicates")

    output = _run(calibredb, args, library)
    match = _ADDED_IDS.search(output)
    if not match:
        return []
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


def set_metadata(calibredb: str, book_id: str, opf: Path, library: Path | str | None = None) -> None:
    """用 metadata.opf 覆盖某本书的元数据。"""
    _run(calibredb, ["set_metadata", str(book_id), str(opf)], library)


def list_ids(calibredb: str, library: Path | str | None = None) -> list[str]:
    """列出现有书 id，用来做重复检测。"""
    output = _run(calibredb, ["list", "--fields", "id", "--for-machine"], library)
    try:
        import json

        return [str(item["id"]) for item in json.loads(output)]
    except Exception:
        return [line.strip() for line in output.splitlines() if line.strip().isdigit()]
