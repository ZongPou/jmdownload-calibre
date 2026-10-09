"""JMComic Downloader —— Calibre InterfaceAction 插件入口。

本文件只做插件元数据包装，不 import 任何 GUI 库（Qt / calibre.gui2），
保证 calibre-customize / 命令行环境下也能安全加载。
真正的界面逻辑在 ui.py（由 actual_plugin 指向，仅 GUI 启动时加载）。
"""

from calibre.customize import InterfaceActionBase

__version__ = "0.1.0"


class Jmcomic2CalibrePlugin(InterfaceActionBase):
    name = "JMComic Downloader"
    description = (
        "输入禁漫漫画 ID：自动下载、打包 CBZ（内嵌 ComicInfo.xml）"
        "并带元数据直接入库 Calibre"
    )
    supported_platforms = ["windows", "osx", "linux"]
    author = "ZongPou"
    version = (0, 1, 0)
    minimum_calibre_version = (7, 0, 0)
    actual_plugin = "calibre_plugins.jmcomic2calibre.ui:InterfacePlugin"
