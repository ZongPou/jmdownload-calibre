"""入库：CBZ 打包 + Metadata 构造 + 判重 + add_books 直接写库。

本模块在 GUI 进程的工作线程中调用（db.new_api 线程安全）。
calibre 依赖延迟导入，保证离线单测能导入本模块的纯逻辑部分。

判重：add_books 只按 title/author 判重，不认 identifiers，
所以必须先用 get_book_id_from_identifier('jmcomic:<id>') 自查。
"""

from __future__ import annotations

import os

from calibre_plugins.jmcomic2calibre.packaging import (
    build_comicinfo_xml,
    build_web_url,
    collect_images,
    pack_cbz,
    parse_published,
    sanitize_filename,
)


def _load_cover(images: list[str]):
    """取第一张图做封面字节。webp 转 JPEG（calibre 封面兼容性最好）。"""
    if not images:
        return None, None
    first = images[0]
    ext = os.path.splitext(first)[1].lower().lstrip(".")
    with open(first, "rb") as handle:
        data = handle.read()
    if ext in ("jpg", "jpeg", "png"):
        return ext, data
    try:  # webp/bmp/gif → JPEG
        from io import BytesIO

        from PIL import Image

        image = Image.open(first).convert("RGB")
        buffer = BytesIO()
        image.save(buffer, "JPEG", quality=90)
        return "jpg", buffer.getvalue()
    except Exception:
        return None, None


def create_book(
    album_id: str,
    out_dir: str,
    meta: dict,
    db,
    web_domain: str | None = None,
) -> dict:
    """下载目录 → CBZ（含 ComicInfo.xml）→ 入库。

    :param meta: bridge 的 meta 事件字段（title/authors/tags/description/published）
    :param db: gui.current_db（legacy LibraryDatabase）。入库必须走 legacy 层：
               new_api.add_books 直写不会同步 GUI 的数据缓存，导致要重启才能
               看到新书；legacy add_books 与"添加书籍"动作同路径，视图即时刷新。
    :returns: {'status': 'ingested'|'skipped'|'failed', 'book_id': int|None,
               'title': str, 'message': str}
    """
    from calibre.ebooks.metadata.book.base import Metadata

    title = str(meta.get("title") or album_id)
    result = {"status": "failed", "book_id": None, "title": title, "message": ""}

    # 1. 判重（jmcomic:<id>）——在打包前，省掉无用 IO。
    #    new_api(Cache) 没有 get_book_id_from_identifier（那是旧版 legacy API），
    #    用 identifiers 精确搜索（"=" 前缀）代替。
    identifier = str(meta.get("selection_key") or album_id)
    matches = db.new_api.search(f'identifiers:"=jmcomic:{album_id}"')
    # 始终保留 jmcomic:<原ID>。选集用附加标识符区分，全本也可覆盖选集判重。
    matches = {book_id for book_id in matches
               if not db.new_api.get_metadata(book_id).get_identifiers().get("jmchapters")
               or db.new_api.get_metadata(book_id).get_identifiers().get("jmchapters") == identifier}
    if matches:
        return {
            "status": "skipped",
            "book_id": sorted(matches)[0],
            "title": title,
            "message": "已存在于书库",
        }

    # 2. 图片 → ComicInfo.xml → CBZ
    images = collect_images(out_dir)
    if not images:
        result["message"] = "下载目录里没有图片"
        return result

    web_url = build_web_url(web_domain, album_id)
    comicinfo = build_comicinfo_xml(meta, web_url, len(images))
    cbz_path = os.path.join(
        out_dir, sanitize_filename(title, album_id) + ".cbz"
    )
    pack_cbz(images, comicinfo, cbz_path)

    # 3. Metadata 对象（元数据随对象直接入库，Calibre 会自动落盘 metadata.opf）
    authors = [str(a) for a in (meta.get("authors") or []) if a] or ["JMComic"]
    tags = [str(t) for t in (meta.get("tags") or []) if t]
    mi = Metadata(title, authors=authors)
    if tags:
        mi.tags = tags
    description = str(meta.get("description") or "").strip()
    if description:
        mi.comments = description
    pub_date = parse_published(meta.get("published"))
    if pub_date is not None:
        mi.pubdate = pub_date
    mi.language = "zh"
    mi.set_identifiers(
        {"jmcomic": str(album_id), "url": build_web_url(web_domain, album_id),
         **({"jmchapters": identifier} if identifier != str(album_id) else {})}
    )
    cover_ext, cover_data = _load_cover(images)
    if cover_data:
        mi.cover_data = (cover_ext, cover_data)

    # 4. 入库（legacy 层：同步 GUI 数据缓存，视图即时可见）
    ids = db.add_books([cbz_path], ["CBZ"], [mi], return_ids=True)
    if not ids:
        result["message"] = "add_books 未返回书 id"
        return result

    return {
        "status": "ingested",
        "book_id": ids[0],
        "title": title,
        "message": "",
    }
