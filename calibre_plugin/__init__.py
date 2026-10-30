"""JMdownload —— Calibre InterfaceAction 插件入口。

本文件只做插件元数据包装，不 import 任何 GUI 库（Qt / calibre.gui2），
保证 calibre-customize / 命令行环境下也能安全加载。
真正的界面逻辑在 ui.py（由 actual_plugin 指向，仅 GUI 启动时加载）。
"""

from calibre.customize import InterfaceActionBase

__version__ = "0.3.0"



class Jmcomic2CalibrePlugin(InterfaceActionBase):
    name = "JMdownload"
    description = (
        "输入禁漫漫画 ID：自动下载、打包 CBZ（内嵌 ComicInfo.xml）"
        "并带元数据直接入库 Calibre"
    )
    supported_platforms = ["windows", "osx", "linux"]
    author = "ZongPou"
    version = (0, 3, 0)
    minimum_calibre_version = (7, 0, 0)
    actual_plugin = "calibre_plugins.jmcomic2calibre.ui:InterfacePlugin"

    # ---- 配置界面 ----
    # 首选项插件面板检查的是本包装类的 is_customizable，
    # 而非 actual plugin，因此两个类都要实现。
    # Qt 依赖延迟到方法调用时导入（首选项对话框本身就是 GUI 环境）。

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.jmcomic2calibre.config_widget import ConfigWidget

        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
