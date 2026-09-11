"""jmcomic-calibre：把 JMComic 的本子整理进 Calibre 书库。

OPF 生成的对外接口是 :func:`jmcomic_calibre.export_opf`，
jmcomic 的 calibre_metadata 插件直接调它，两边共用同一份 XML 逻辑。
"""

from .metadata import (
    DEFAULT_AUTHOR,
    DUBLIN_CORE_ELEMENTS,
    AlbumMeta,
    build_opf,
    export_opf,
    meta_from_album,
)

__version__ = "0.2.0"

__all__ = [
    "DEFAULT_AUTHOR",
    "DUBLIN_CORE_ELEMENTS",
    "AlbumMeta",
    "build_opf",
    "export_opf",
    "meta_from_album",
    "__version__",
]
