"""JMComic 下载桥：由系统 Python 执行（运行在 calibre 之外）。

由插件运行时从 zip 提取本文件，再用用户配置的解释器启动：
    python bridge.py --album-id 350234 --out-dir <目录> [--proxy http://...]

协议（stdout 逐行 JSON，接收方忽略无法解析的行）：
    {"event": "meta", "album_id": "...", "title": "...", "authors": [...],
     "tags": [...], "description": "...", "published": "..."}
    {"event": "progress", "images": <已下载图片数>, "percent": <float|null>}
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

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
PROGRESS_INTERVAL = 1.5  # 秒


def emit(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="JMComic 下载桥")
    parser.add_argument("--album-id", required=True, help="漫画 ID")
    parser.add_argument("--out-dir", required=True, help="图片输出目录")
    parser.add_argument("--proxy", default="", help="代理地址（可选）")
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


def fetch_meta_and_download(album_id: str, out_dir: str, proxy: str) -> None:
    import jmcomic  # 系统环境里的 jmcomic

    os.makedirs(out_dir, exist_ok=True)
    option = jmcomic.JmOption.default()
    option.dir_rule.base_dir = out_dir
    if proxy:
        os.environ.setdefault("HTTP_PROXY", proxy)
        os.environ.setdefault("HTTPS_PROXY", proxy)
        try:  # jmcomic 选项层面的代理（不同版本字段位置可能不同，失败不致命）
            option.client.proxies = {"http": proxy, "https": proxy}
        except Exception:
            pass

    client = option.new_jm_client()
    album = client.get_album_detail(str(album_id))
    emit(
        {
            "event": "meta",
            "album_id": str(album_id),
            "title": getattr(album, "name", None) or str(album_id),
            "authors": [str(a) for a in (getattr(album, "authors", None) or [])],
            "tags": [str(t) for t in (getattr(album, "tags", None) or [])],
            "description": str(getattr(album, "description", "") or ""),
            "published": str(getattr(album, "pub_date", "") or ""),
        }
    )

    # 进度轮询线程：统计已落地的图片文件数（不依赖 jmcomic 内部回调 API）
    stop = threading.Event()

    def progress_loop():
        while not stop.wait(PROGRESS_INTERVAL):
            n = count_images(out_dir)
            emit({"event": "progress", "images": n, "percent": None})

    watcher = threading.Thread(target=progress_loop, daemon=True)
    watcher.start()
    try:
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
        fetch_meta_and_download(args.album_id, args.out_dir, args.proxy)
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
