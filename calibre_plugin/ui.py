"""真正的 GUI 插件（仅在 calibre GUI 启动时由 actual_plugin 加载）。

注意：get_icons / get_resources 是 calibre 插件系统注入到插件模块的
内置 builtins，直接调用即可，不要 import（新版 calibre.gui2 顶层没有它们）。
"""

from calibre.gui2.actions import InterfaceAction


class InterfacePlugin(InterfaceAction):

    name = "JMComic Downloader"
    action_spec = (
        "JMComic 下载",
        None,  # 图标在 genesis 里加载
        "输入禁漫漫画 ID，下载打包入库 Calibre",
        None,  # 快捷键
    )
    action_type = "current"

    def genesis(self):
        base = self.interface_action_base_plugin
        self.version = base.version

        icon = get_icons("images/icon.png", self.name)  # noqa: F821 由插件系统注入
        if icon is not None and not icon.isNull():
            self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.show_dialog)

    def show_dialog(self):
        from calibre_plugins.jmcomic2calibre.dialogs import DownloadDialog

        dialog = DownloadDialog(self.gui, self)
        dialog.exec()
