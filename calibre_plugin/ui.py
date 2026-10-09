"""真正的 GUI 插件（仅在 calibre GUI 启动时由 actual_plugin 加载）。

注意：get_icons / get_resources 是 calibre 插件系统注入到插件模块的
内置 builtins，直接调用即可，不要 import（新版 calibre.gui2 顶层没有它们）。

工具栏按钮为分体按钮：点击主体 = 下载对话框；点箭头展开下拉菜单
（下载 / 配置 / 环境检测）。
"""

from qt.core import QDialog, QDialogButtonBox, QVBoxLayout

from calibre.gui2.actions import InterfaceAction


class InterfacePlugin(InterfaceAction):

    name = "JMdownload"
    action_spec = (
        "JMdownload",
        None,  # 图标在 genesis 里加载
        "输入禁漫漫画 ID，下载打包入库 Calibre",
        None,  # 快捷键
    )
    action_type = "current"
    # 按钮挂下拉菜单；"下载"克隆项由 calibre 自动加入菜单
    action_add_menu = True
    action_menu_clone_qaction = True

    def genesis(self):
        base = self.interface_action_base_plugin
        self.version = base.version

        icon = get_icons("images/icon.png", self.name)  # noqa: F821 由插件系统注入
        if icon is not None and not icon.isNull():
            self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.show_dialog)

        # 下拉菜单：calibre 已自动把"下载"克隆项加入，这里追加分隔线与入口
        menu = self.qaction.menu()
        if menu is not None:
            menu.addSeparator()
            config_action = menu.addAction("配置…")
            config_action.triggered.connect(self.show_config)
            env_action = menu.addAction("环境检测…")
            env_action.triggered.connect(self.show_environment)

    def show_dialog(self):
        from calibre_plugins.jmcomic2calibre.dialogs import DownloadDialog

        dialog = DownloadDialog(self.gui, self)
        dialog.exec()

    # ---- 下拉菜单入口 ----

    def show_config(self):
        """下拉菜单的"配置…"：以模态对话框打开配置面板，OK 时保存。"""
        from calibre_plugins.jmcomic2calibre.config_widget import ConfigWidget

        dialog = QDialog(self.gui)
        dialog.setWindowTitle("JMdownload 设置")
        layout = QVBoxLayout(dialog)
        widget = ConfigWidget()
        layout.addWidget(widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            widget.save_settings()

    def show_environment(self):
        """下拉菜单的"环境检测…"：后台探测后弹结果。"""
        from calibre.gui2 import info_dialog

        from calibre_plugins.jmcomic2calibre.common import describe_probe
        from calibre_plugins.jmcomic2calibre.dialogs import ProbeThread

        self._env_probe = ProbeThread(self.gui)

        def on_done(result):
            info_dialog(
                self.gui,
                "JMdownload 环境检测",
                describe_probe(result),
                show=True,
            )
            self._env_probe = None

        self._env_probe.done.connect(on_done)
        self._env_probe.start()

    # ---- 配置界面（首选项 → 插件 → 自定义插件） ----

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.jmcomic2calibre.config_widget import ConfigWidget

        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
