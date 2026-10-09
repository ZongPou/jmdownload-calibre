"""打包辅助：图片自然排序 + ComicInfo.xml 生成 + CBZ 打包。

纯标准库实现（离线可测）。逻辑来源：上游 src/jmcomic_calibre/convert.py
（自然排序/CBZ），插件 zip 需自包含故携带于此。

ComicInfo.xml 遵循 Anansi/ComicRack 规范；定位是"文件自描述 +
Kavita/Komga 等第三方阅读器兼容"，Calibre 导入不读它（元数据由
ingest.py 经 Metadata 对象直接写库，见 AGENTS.md 冻结决策）。
"""

from __future__ import annotations

import os
import re
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
DEFAULT_WEB_DOMAIN = "https://18comic.vip"


def _natural_parts(text: str) -> list:
    """自然排序键：数字段按数值比较，字符串段按文本比较（可混合）。"""
    parts = re.split(r"(\d+)", text.lower())
    return [(0, int(p)) if p.isdigit() else (1, p) for p in parts]


def collect_images(folder: str) -> list[str]:
    """递归收集目录下的图片，按自然顺序返回完整路径列表。

    排序键用文件名（页码在文件名里，如 00001.jpg → 00027.jpg）；
    jmcomic 产物为平铺目录，忽略子目录层级即得到正确页序。
    """
    folder_abs = os.path.abspath(folder)
    images = [
        os.path.join(root, name)
        for root, _dirs, files in os.walk(folder_abs)
        for name in files
        if os.path.splitext(name)[1].lower() in IMAGE_EXTS
    ]
    return sorted(images, key=lambda p: _natural_parts(os.path.basename(p)))


def build_web_url(web_domain: str | None, album_id: str) -> str:
    domain = (web_domain or DEFAULT_WEB_DOMAIN).rstrip("/")
    return f"{domain}/album/{album_id}/"


_PUB_PATTERNS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y年%m月%d日",
)


def parse_published(text) -> datetime | None:
    """宽松解析发布日期，失败返回 None（不设 pubdate）。"""
    if not text:
        return None
    text = str(text).strip()
    for pattern in _PUB_PATTERNS:
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    match = re.search(r"(20\d{2})[-./年](\d{1,2})[-./月](\d{1,2})", text)
    if match:
        try:
            return datetime(*(int(g) for g in match.groups()))
        except ValueError:
            return None
    return None


def sanitize_filename(title: str, fallback: str) -> str:
    """去掉文件名非法字符，空标题回退到 album_id。"""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]', "_", (title or "").strip())
    return cleaned or fallback


def build_comicinfo_xml(
    meta: dict, web_url: str, page_count: int
) -> str:
    """从 meta（bridge 的 meta 事件字段）生成 ComicInfo.xml 文本。"""
    title = str(meta.get("title") or "")
    authors = [str(a) for a in (meta.get("authors") or []) if a]
    tags = [str(t) for t in (meta.get("tags") or []) if t]
    description = str(meta.get("description") or "")

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema">',
    ]

    def add(tag: str, value) -> None:
        if value in (None, ""):
            return
        lines.append(f"  <{tag}>{escape(str(value))}</{tag}>")

    add("Series", title)
    add("Title", title)
    add("Writer", ", ".join(authors))
    add("Summary", description)
    pub_date = parse_published(meta.get("published"))
    if pub_date is not None:
        add("Year", pub_date.year)
        add("Month", pub_date.month)
        add("Day", pub_date.day)
    if tags:
        add("Genre", ", ".join(tags))
        add("Tags", ", ".join(tags))
    add("LanguageISO", "zh")
    add("Manga", "Unknown")
    add("Web", web_url)
    if page_count:
        add("PageCount", page_count)
    lines.append("</ComicInfo>")
    return "\n".join(lines) + "\n"


def pack_cbz(
    images: list[str], comicinfo_xml: str, output: str
) -> str:
    """打 CBZ：ComicInfo.xml 放第一个条目，图片按自然顺序随后。"""
    if not images:
        raise ValueError("没有可打包的图片")
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ComicInfo.xml", comicinfo_xml.encode("utf-8"))
        for image in images:
            archive.write(image, arcname=os.path.basename(image))
    return output
