"""把本子信息写成 Calibre 能读的 metadata.opf。

这个模块是 OPF 生成的唯一实现：CLI（jmcal）和 jmcomic 的 calibre_metadata 插件
都走这里，避免两处各维护一份 XML 拼接逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from xml.sax.saxutils import escape, quoteattr

DEFAULT_AUTHOR = "JMComic"

# Dublin Core 的 15 个核心元素。
# 自定义 fields 里的键必须是这里面的名字（注意是 "series_index" 这种下划线写法，
# 写成 "series index" 之类的非法元素名会被直接忽略）。
DUBLIN_CORE_ELEMENTS = frozenset({
    "title", "creator", "subject", "description", "publisher",
    "contributor", "date", "type", "format", "identifier",
    "source", "language", "relation", "coverage", "rights",
})


@dataclass
class AlbumMeta:
    """准备写进 Calibre 的一本书的元数据。"""

    album_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str = ""
    published: str = ""
    publisher: str = ""
    language: str = ""
    series: str = ""
    series_index: str = ""
    identifier: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def resolved_authors(self) -> list[str]:
        return [a for a in self.authors if a] or [DEFAULT_AUTHOR]

    def resolved_identifier(self) -> str:
        # 用 jmcomic:<id> 而不是 uuid，重复导入时 Calibre 才好识别是同一本
        return self.identifier or f"jmcomic:{self.album_id}"


def build_opf(
    meta: AlbumMeta,
    *,
    identifier_scheme: str = "uuid",
    cover_filename: str | None = None,
) -> str:
    """生成一份 OPF 文本。XML 特殊字符在这里统一转义。

    :param identifier_scheme: dc:identifier 的 opf:scheme 属性
    :param cover_filename: 传了就写 <meta name="cover"> 和 <manifest>，指向该封面文件
    """
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uuid_id">',
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">',
    ]

    written: set[str] = set()

    def add(tag: str, text, attr: str = "") -> None:
        if text in (None, ""):
            return
        lines.append(f"    <dc:{tag}{attr}>{escape(str(text))}</dc:{tag}>")
        written.add(tag)

    add("title", meta.title)
    for author in meta.resolved_authors():
        add("creator", author, ' opf:role="aut"')
    for tag in meta.tags:
        add("subject", tag)
    add("description", meta.description)
    add("date", meta.published)
    add("publisher", meta.publisher)
    add("language", meta.language)
    add("identifier", meta.resolved_identifier(), f" opf:scheme={quoteattr(str(identifier_scheme))}")

    # extra 里只认合法的 Dublin Core 元素名；标准字段已经写过值的不再重复
    for key in sorted(meta.extra or {}):
        if key not in DUBLIN_CORE_ELEMENTS or key in written:
            continue
        add(key, meta.extra[key])

    if meta.series:
        lines.append(f'    <meta name="calibre:series" content={quoteattr(meta.series)}/>')
    if meta.series_index:
        lines.append(
            f'    <meta name="calibre:series_index" content={quoteattr(str(meta.series_index))}/>'
        )
    if cover_filename:
        lines.append('    <meta name="cover" content="cover-image"/>')

    lines.append("  </metadata>")

    if cover_filename:
        lines.append("  <manifest>")
        lines.append(
            f'    <item id="cover-image" href={quoteattr(cover_filename)} media-type="image/jpeg"/>'
        )
        lines.append("  </manifest>")

    lines.append("</package>")
    return "\n".join(lines) + "\n"


def meta_from_album(album_id: str, detail) -> AlbumMeta:
    """从 jmcomic 的 JmAlbumDetail 转成 AlbumMeta。"""
    authors = list(getattr(detail, "authors", None) or [])
    return AlbumMeta(
        album_id=str(album_id),
        title=getattr(detail, "name", "") or str(album_id),
        authors=authors,
        tags=list(getattr(detail, "tags", None) or []),
        description=getattr(detail, "description", "") or "",
        published=getattr(detail, "pub_date", "") or "",
    )


def _album_title(album) -> str:
    return (
        getattr(album, "title", None)
        or getattr(album, "name", None)
        or str(getattr(album, "id", ""))
    )


def _album_authors(album) -> list[str]:
    # 优先取 authors 列表（保留多位作者）；为空时回落到 author 属性，
    # 这样空作者的兜底逻辑和 jmcomic 的 JmModuleConfig.DEFAULT_AUTHOR 保持一致。
    authors = [str(a) for a in (getattr(album, "authors", None) or []) if a]
    if authors:
        return authors
    single = getattr(album, "author", None)
    return [str(single)] if single else []


def export_opf(
    album,
    opf_path: str | Path,
    *,
    fields: dict | None = None,
    include_cover: bool = False,
    download_cover: Callable[[str], None] | None = None,
    cover_filename: str = "cover.jpg",
    identifier_scheme: str = "JMCOMIC",
    series: str = "",
    series_index: str = "",
    on_ignored: Callable[[str, frozenset], None] | None = None,
) -> str:
    """从 jmcomic 的 album 对象生成 metadata.opf，返回写入的路径。

    :param album: JmAlbumDetail / JmPhotoDetail 之类的对象
    :param opf_path: 目标文件路径，父目录不存在会自动建
    :param fields: 追加的静态字段。title / author 会覆盖默认取值，
                   其余键必须是 Dublin Core 元素名，非法键会被忽略并回调 on_ignored
    :param include_cover: 是否下载封面到同目录的 cover_filename 并写进 manifest
    :param download_cover: 下载封面的回调，接收封面目标路径；include_cover=True 时必需
    :param on_ignored: 遇到非法 fields 键时的回调，参数为 (键名, 合法键集合)
    """
    fields = dict(fields or {})

    title = str(fields.pop("title", _album_title(album)))
    authors = _album_authors(album)
    if "author" in fields:
        authors = [str(fields.pop("author"))]

    meta = AlbumMeta(
        album_id=str(getattr(album, "id", "")),
        title=title,
        authors=authors,
        tags=list(getattr(album, "tags", None) or []),
        description=getattr(album, "description", "") or "",
        series=series,
        series_index=series_index,
    )

    for key, value in fields.items():
        key = str(key)
        if key not in DUBLIN_CORE_ELEMENTS:
            if on_ignored is not None:
                on_ignored(key, DUBLIN_CORE_ELEMENTS)
            continue
        meta.extra[key] = str(value)

    path = Path(opf_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    cover = None
    if include_cover:
        cover_path = path.parent / cover_filename
        if download_cover is not None:
            download_cover(str(cover_path))
        cover = cover_filename

    xml = build_opf(meta, identifier_scheme=identifier_scheme, cover_filename=cover)
    path.write_text(xml, encoding="utf-8")
    return str(path)
