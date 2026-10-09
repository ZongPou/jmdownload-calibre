"""下载对话框：ID/链接输入、实时解析预览、后台环境探测。

阶段 1 范围：界面 + 解析 + doctor。“开始下载”在阶段 2 接入子进程下载桥。
"""

from qt.core import (
    QThread,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    Qt,
    QVBoxLayout,
    pyqtSignal,
)

from calibre_plugins.jmcomic2calibre.common import describe_probe, parse_album_ids
from calibre_plugins.jmcomic2calibre.config import prefs


class ProbeThread(QThread):
    """后台跑环境探测，避免阻塞界面。"""

    done = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.custom_path = prefs["python_path"]

    def run(self):
        from calibre_plugins.jmcomic2calibre.common import doctor

        self.done.emit(doctor(self.custom_path))


class DownloadDialog(QDialog):

    def __init__(self, parent, plugin):
        QDialog.__init__(self, parent)
        self.plugin = plugin
        self._probe = None

        self.setWindowTitle("JMComic 下载")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)

        self.status_label = QLabel("正在检测运行环境（Python / jmcomic）…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("每行一个漫画 ID 或网页链接（# 开头为注释）："))
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText(
            "例如：\n350234\nhttps://18comic.vip/album/350234/"
        )
        self.input_edit.textChanged.connect(self.update_preview)
        layout.addWidget(self.input_edit)

        self.preview_label = QLabel("")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        buttons = QHBoxLayout()
        self.reprobe_button = QPushButton("重新检测环境")
        self.reprobe_button.clicked.connect(self.start_probe)
        buttons.addWidget(self.reprobe_button)
        buttons.addStretch(1)
        self.download_button = QPushButton("开始下载")
        self.download_button.setEnabled(False)
        self.download_button.setToolTip("下载引擎将在阶段 2 接入")
        self.download_button.clicked.connect(self.on_download)
        buttons.addWidget(self.download_button)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.start_probe()

    # ---- 环境探测 ----

    def start_probe(self):
        if self._probe is not None and self._probe.isRunning():
            return
        self.status_label.setText("正在检测运行环境（Python / jmcomic）…")
        self._probe = ProbeThread(self)
        self._probe.done.connect(self.on_probe_done)
        self._probe.start()

    def on_probe_done(self, result):
        self.status_label.setText(describe_probe(result))
        self._probe = None

    # ---- 输入解析预览 ----

    def update_preview(self):
        ids, errors = parse_album_ids(self.input_edit.toPlainText())
        parts = []
        if ids:
            parts.append("已识别 %d 个 ID：%s" % (len(ids), ", ".join(ids)))
        if errors:
            shown = "；".join(errors[:5])
            more = "（还有 %d 行）" % (len(errors) - 5) if len(errors) > 5 else ""
            parts.append("无法识别：%s%s" % (shown, more))
        self.preview_label.setText("\n".join(parts))
        self.download_button.setEnabled(bool(ids))

    def on_download(self):
        # 阶段 2 接入子进程下载桥；当前占位
        from calibre.gui2 import info_dialog

        info_dialog(
            self,
            "尚未实现",
            "下载引擎将在阶段 2 接入（子进程桥调用 jmcomic）。",
            show=True,
        )

    # ---- 生命周期 ----

    def closeEvent(self, event):
        if self._probe is not None and self._probe.isRunning():
            self._probe.wait(3000)
        super().closeEvent(event)
