"""把本子信息写成 Calibre 能读的 metadata.opf。"""

from __future__ import annotations

from dataclasses import dataclass, field
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


def build_opf(meta: AlbumMeta) -> str:
    """生成一份 OPF 文本。XML 特殊字符在这里统一转义。"""
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
    add("identifier", meta.resolved_identifier(), ' opf:scheme="uuid"')

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

    lines.append("  </metadata>")
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
