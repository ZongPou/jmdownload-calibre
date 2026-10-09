"""真正的 GUI 插件（仅在 calibre GUI 启动时由 actual_plugin 加载）。"""

from calibre.gui2 import get_icons
from calibre.gui2.actions import InterfaceAction


class InterfacePlugin(InterfaceAction):

    name = "JMComic Downloader"
    action_spec = (
        "JMComic 下载",
        None,  # 图标在 genesis 里尝试加载
        "输入禁漫漫画 ID，下载打包入库 Calibre",
        None,  # 快捷键
    )
    action_type = "current"

    def genesis(self):
        base = self.interface_action_base_plugin
        self.version = base.version

        icon = get_icons("images/icon.png", self.name)
        if icon is not None and not icon.isNull():
            self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.show_dialog)

    def show_dialog(self):
        from calibre_plugins.jmcomic2calibre.dialogs import DownloadDialog

        dialog = DownloadDialog(self.gui, self)
        dialog.exec()
