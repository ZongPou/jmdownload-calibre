"""下载 → 转格式 → 写元数据 → 入库，串成一条流程。"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .convert import collect_images, convert
from .library import add_book, find_calibredb, set_metadata
from .metadata import AlbumMeta, build_opf, meta_from_album


def _option(option_path: str | None):
    import jmcomic

    if option_path:
        return jmcomic.create_option_by_file(option_path)
    return jmcomic.JmOption.default()


def fetch_meta(album_id: str, option_path: str | None = None) -> AlbumMeta:
    """查本子详情，转成 AlbumMeta。"""
    option = _option(option_path)
    detail = option.new_jm_client().get_album_detail(str(album_id))
    return meta_from_album(album_id, detail)


def download_album(album_id: str, target_dir: Path, option_path: str | None = None) -> Path:
    """用 jmcomic 下载本子，返回下载目录。"""
    import jmcomic

    option = _option(option_path)
    option.dir_rule.base_dir = str(target_dir)
    jmcomic.download_album(str(album_id), option)
    return target_dir


def import_album(
    album_id: str,
    *,
    library: str | None = None,
    fmt: str = "pdf",
    option_path: str | None = None,
    work_dir: str | None = None,
    calibredb: str | None = None,
    keep_workdir: bool = False,
    dry_run: bool = False,
) -> dict:
    """跑完整流程，返回一份执行摘要。"""
    fmt = fmt.lower().lstrip(".")
    if fmt not in ("pdf", "cbz"):
        raise ValueError("format 只支持 pdf 或 cbz")

    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix=f"jmcal_{album_id}_"))
    work.mkdir(parents=True, exist_ok=True)

    try:
        meta = fetch_meta(album_id, option_path)
        download_album(album_id, work / "src", option_path)

        images = collect_images(work / "src")
        if not images:
            raise RuntimeError(f"没找到图片，下载可能没成功：{work / 'src'}")

        book = convert(images, work / f"{meta.title}.{fmt}")
        opf = work / "metadata.opf"
        opf.write_text(build_opf(meta), encoding="utf-8")

        summary = {
            "album_id": str(album_id),
            "title": meta.title,
            "book": str(book),
            "opf": str(opf),
            "pages": len(images),
            "book_ids": [],
            "imported": False,
        }

        if dry_run:
            return summary

        calibredb = calibredb or find_calibredb()
        if not calibredb:
            raise RuntimeError("没找到 calibredb，先装 Calibre 并确保它在 PATH 里")

        book_ids = add_book(calibredb, book, library)
        for book_id in book_ids:
            set_metadata(calibredb, book_id, opf, library)

        summary["book_ids"] = book_ids
        summary["imported"] = True
        return summary
    finally:
        if not keep_workdir and work_dir is None:
            shutil.rmtree(work, ignore_errors=True)
