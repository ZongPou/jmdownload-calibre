"""JMComic 下载桥：由系统 Python 执行（运行在 calibre 之外）。

由插件运行时从 zip 提取本文件，再用用户配置的解释器启动：
    python bridge.py --album-id 350234 --out-dir <目录> [--proxy http://...]
    python bridge.py --album-id 350234 --out-dir <目录> --meta-only   # 仅诊断

协议（stdout 逐行 JSON，接收方忽略无法解析的行）：
    {"event": "meta", "album_id": "...", "title": "...", "authors": [...],
     "tags": [...], "description": "...", "published": "...",
     "total_images": <总页数>}
    {"event": "progress", "images": <已下载图片数>, "total": <总页数>,
     "percent": <float|null>}
    {"event": "log", "message": "..."}
    {"event": "downloaded", "dir": "...", "images": <n>}
    {"event": "error", "message": "...", "traceback": "..."}
    {"event": "done"}

jmcomic / 第三方库的输出全部重定向到 stderr，保证 stdout 只有 JSON。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import traceback
import re


def _isolate_script_dir() -> None:
    """把脚本所在目录移出 sys.path。

    jmcomic 内部使用裸导入 `from common import time_stamp, ...`（依赖
    commonx 提供的顶层 common 模块）；本文件可能被提取到任意目录运行，
    若同目录恰好有名为 common.py 的模块（例如插件打包目录）就会劫持
    该导入导致 ImportError。与标准库无关，可安全隔离。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path[:] = [
        p for p in sys.path if p and os.path.abspath(p) != here
    ]


_isolate_script_dir()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
PROGRESS_INTERVAL = 1.5  # 秒
ALBUM_FIELDS = ("album_id", "scramble_id", "name", "episode_list", "page_count",
                "pub_date", "update_date", "likes", "views", "comment_count",
                "works", "actors", "authors", "tags", "description")


def album_snapshot(album):
    """跨预读/下载进程仅传 JSON 构造字段，避免重复请求整本详情。"""
    if not all(hasattr(album, name) for name in ALBUM_FIELDS):
        return None
    return {name: getattr(album, name) for name in ALBUM_FIELDS}


def emit(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="JMComic 下载桥")
    parser.add_argument("--album-id", required=True, help="漫画 ID")
    parser.add_argument("--out-dir", required=True, help="图片输出目录")
    parser.add_argument("--proxy", default="", help="代理地址（可选）")
    parser.add_argument("--chapters", default="", help="选中的章节 ID，以逗号分隔")
    parser.add_argument("--cover-path", default="", help="预览封面的独立存储路径")
    parser.add_argument("--album-cache", default="", help="预读漫画详情的 JSON 文件")
    parser.add_argument("--cover-only", action="store_true", help="仅获取队列封面，不请求章节")
    parser.add_argument(
        "--meta-only",
        action="store_true",
        help="只获取元数据用于诊断，不下载图片",
    )
    return parser.parse_args(argv)


def count_images(out_dir: str) -> int:
    total = 0
    for _root, _dirs, files in os.walk(out_dir):
        total += sum(
            1
            for f in files
            if os.path.splitext(f)[1].lower() in IMAGE_EXTS
        )
    return total


def fetch_meta_and_download(
    album_id: str, out_dir: str, proxy: str, meta_only: bool = False,
    chapter_ids: list[str] | None = None, cover_path: str = "", album_cache: str = "",
    cover_only: bool = False,
) -> None:
    import jmcomic  # 系统环境里的 jmcomic

    os.makedirs(out_dir, exist_ok=True)
    option = jmcomic.JmOption.default()
    option.dir_rule.base_dir = out_dir
    # 上游默认每章 30 张图片、章节并发随 CPU 核心数增长。
    # 用户指定单章 16 张图片并发，章节仍顺序执行。
    option.download.threading.photo = 1
    option.download.threading.image = 16
    if proxy:
        os.environ.setdefault("HTTP_PROXY", proxy)
        os.environ.setdefault("HTTPS_PROXY", proxy)
        try:  # jmcomic 选项层面的代理（不同版本字段位置可能不同，失败不致命）
            option.client.proxies = {"http": proxy, "https": proxy}
        except Exception:
            pass

    # 与 JmDownloader 使用 option 缓存的同一个 client，复用连接及设置。
    client = option.build_jm_client()
    if cover_only:
        if not cover_path:
            raise ValueError("封面输出路径不能为空")
        client.download_album_cover(str(album_id), cover_path, size="_3x4")
        emit({"event": "cover", "path": cover_path})
        return
    album = None
    if album_cache:
        try:
            with open(album_cache, encoding="utf-8") as handle:
                snapshot = json.load(handle)
            if str(snapshot["album_id"]) != str(album_id):
                raise ValueError("漫画 ID 不匹配")
            album = jmcomic.JmAlbumDetail(**{k: snapshot[k] for k in ALBUM_FIELDS})
            emit({"event": "log", "message": "已复用预读漫画详情"})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            emit({"event": "log", "message": "预读详情不可用，重新获取: " + str(exc)})
    if album is None:
        album = client.get_album_detail(str(album_id))
    episodes = getattr(album, "episode_list", None) or [(str(album_id), "1", getattr(album, "name", str(album_id)))]
    chapters = [{"id": str(e[0]), "number": i, "title": str(e[2])}
                for i, e in enumerate(episodes, 1)]
    selected = set(chapter_ids or [])
    if selected and not selected.issubset({c["id"] for c in chapters}):
        raise ValueError("章节列表已变化，请重新添加漫画并选择章节")
    total_images = int(getattr(album, "page_count", 0) or 0)
    if selected and selected != {c["id"] for c in chapters}:
        # 选集总页数尚未知，先下载第一集，后续章节就绪时逐步统计。
        total_images = 0
    emit(
        {
            "event": "meta",
            "album_id": str(album_id),
            "title": getattr(album, "name", None) or str(album_id),
            "authors": [str(a) for a in (getattr(album, "authors", None) or [])],
            "tags": [str(t) for t in (getattr(album, "tags", None) or [])],
            "description": str(getattr(album, "description", "") or ""),
            "published": str(getattr(album, "pub_date", "") or ""),
            "total_images": total_images,
            "chapters": chapters,
            "album_snapshot": album_snapshot(album) if meta_only else None,
        }
    )

    if meta_only:
        if cover_path:
            try:
                client.download_album_cover(str(album_id), cover_path, size="_3x4")
                emit({"event": "cover", "path": cover_path})
            except Exception as exc:
                emit({"event": "log", "message": "封面预览获取失败（不影响下载）: " + str(exc)})
        emit({"event": "log", "message": "--meta-only 跳过下载"})
        emit({"event": "downloaded", "dir": out_dir, "images": 0})
        return

    emit({"event": "log", "message": "下载并发：1 章 / 16 张图片；逐章读取页数"})

    # 进度轮询线程：统计已落地的图片文件数（不依赖 jmcomic 内部回调 API）
    stop = threading.Event()

    def progress_loop():
        while not stop.wait(PROGRESS_INTERVAL):
            n = count_images(out_dir)
            percent = round(100.0 * n / total_images, 1) if total_images else None
            emit(
                {
                    "event": "progress",
                    "images": n,
                    "total": total_images,
                    "percent": percent,
                }
            )

    watcher = threading.Thread(target=progress_loop, daemon=True)
    watcher.start()
    try:
        if selected:
            # 顺序下载，固定序号目录保证 CBZ 章节次序；不能按 photo ID 排序。
            known_pages = 0
            selected_count = len(selected)
            chapters_ready = 0
            downloader = jmcomic.JmDownloader(option)
            for chapter in chapters:
                if chapter["id"] not in selected:
                    continue
                chapter_dir = os.path.join(out_dir, "%05d" % chapter["number"])
                os.makedirs(chapter_dir, exist_ok=True)
                option.dir_rule.base_dir = chapter_dir
                emit({"event": "log", "message": "读取第 %d 集详情（%d/%d）" % (
                    chapter["number"], chapters_ready + 1, selected_count)})
                photo = client.get_photo_detail(chapter["id"], fetch_album=False)
                photo.from_album = album
                known_pages += len(photo)
                chapters_ready += 1
                if chapters_ready == selected_count:
                    total_images = known_pages
                emit({"event": "pages_known", "known_pages": known_pages,
                      "chapters_ready": chapters_ready, "chapters_total": selected_count,
                      "total": total_images})
                downloader.begin_manifest(photo)
                try:
                    emit({"event": "log", "message": "开始下载第 %d 集，共 %d 页" % (
                        chapter["number"], len(photo))})
                    downloader.download_by_photo_detail(photo)
                    downloader.raise_if_has_exception()
                finally:
                    downloader.finish_manifest(photo)
                images = [os.path.join(root, name)
                          for root, _, files in os.walk(chapter_dir) for name in files
                          if os.path.splitext(name)[1].lower() in IMAGE_EXTS]
                images.sort(key=lambda path: [(0, int(p)) if p.isdigit() else (1, p)
                            for p in re.split(r"(\d+)", os.path.basename(path).lower())])
                if not images:
                    raise RuntimeError("章节 %s 没有下载到图片" % chapter["number"])
                for page, path in enumerate(images, 1):
                    os.replace(path, os.path.join(out_dir, "%05d_%05d%s" % (
                        chapter["number"], page, os.path.splitext(path)[1])))
        else:
            jmcomic.download_album(str(album_id), option)
    finally:
        stop.set()
        watcher.join(timeout=3)

    emit(
        {
            "event": "downloaded",
            "dir": out_dir,
            "images": count_images(out_dir),
        }
    )


def main(argv=None) -> None:
    args = parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK
    except Exception:
        pass
    try:
        fetch_meta_and_download(
            args.album_id, args.out_dir, args.proxy, args.meta_only,
            args.chapters.split(",") if args.chapters else None, args.cover_path,
            args.album_cache,
            args.cover_only,
        )
    except Exception as exc:
        emit(
            {
                "event": "error",
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    emit({"event": "done"})


if __name__ == "__main__":
    main()
