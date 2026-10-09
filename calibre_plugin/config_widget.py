"""插件配置面板：首选项 → 插件 → JMComic Downloader → 自定义插件。

更改在保存后即时生效（prefs 每次下载时读取），无需重启 calibre。
"""

from qt.core import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calibre_plugins.jmcomic2calibre.common import DEFAULTS, describe_probe
from calibre_plugins.jmcomic2calibre.config import prefs
from calibre_plugins.jmcomic2calibre.dialogs import ProbeThread


class ConfigWidget(QWidget):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self._probe = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )

        # Python 解释器
        python_row = QHBoxLayout()
        self.python_path = QLineEdit(prefs["python_path"])
        self.python_path.setPlaceholderText("留空 = 自动探测 PATH 上的 python")
        python_row.addWidget(self.python_path)
        browse_python = QPushButton("浏览…")
        browse_python.clicked.connect(self.browse_python)
        python_row.addWidget(browse_python)
        form.addRow("Python 解释器", python_row)

        # 环境测试
        probe_row = QHBoxLayout()
        self.test_button = QPushButton("测试环境")
        self.test_button.clicked.connect(self.test_environment)
        probe_row.addWidget(self.test_button)
        self.probe_result = QLabel("")
        self.probe_result.setWordWrap(True)
        probe_row.addWidget(self.probe_result, 1)
        form.addRow("", probe_row)

        # 标识符域名
        self.web_domain = QLineEdit(prefs["web_domain"])
        self.web_domain.setPlaceholderText(DEFAULTS["web_domain"])
        form.addRow("标识符用域名", self.web_domain)

        # 代理
        self.proxy = QLineEdit(prefs["proxy"])
        self.proxy.setPlaceholderText("留空直连；例如 http://127.0.0.1:7890")
        form.addRow("代理", self.proxy)

        # 下载临时目录
        workdir_row = QHBoxLayout()
        self.work_dir = QLineEdit(prefs["work_dir"])
        self.work_dir.setPlaceholderText("留空 = 系统临时目录")
        workdir_row.addWidget(self.work_dir)
        browse_dir = QPushButton("浏览…")
        browse_dir.clicked.connect(self.browse_workdir)
        workdir_row.addWidget(browse_dir)
        form.addRow("下载临时目录", workdir_row)

        # 开关
        self.check_duplicates = QCheckBox("入库前按 jmcomic:<ID> 判重（推荐开启）")
        self.check_duplicates.setChecked(bool(prefs["check_duplicates"]))
        form.addRow("", self.check_duplicates)

        self.keep_workdir = QCheckBox("保留下载临时目录（排障用）")
        self.keep_workdir.setChecked(bool(prefs["keep_workdir"]))
        form.addRow("", self.keep_workdir)

        layout.addLayout(form)

        hint = QLabel("保存后即时生效，无需重启 calibre。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)

    # ---- 浏览 ----

    def browse_python(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Python 解释器",
            "",
            "可执行文件 (*.exe);;所有文件 (*)",
        )
        if path:
            self.python_path.setText(path)

    def browse_workdir(self):
        path = QFileDialog.getExistingDirectory(self, "选择下载临时目录")
        if path:
            self.work_dir.setText(path)

    # ---- 环境测试 ----

    def test_environment(self):
        if self._probe is not None and self._probe.isRunning():
            return
        prefs["python_path"] = self.python_path.text().strip()
        self.probe_result.setText("检测中…")
        self._probe = ProbeThread(self)
        self._probe.done.connect(self.on_probe_done)
        self._probe.start()

    def on_probe_done(self, result):
        self.probe_result.setText(describe_probe(result))
        self._probe = None

    # ---- 保存 ----

    def save_settings(self):
        prefs["python_path"] = self.python_path.text().strip()
        prefs["web_domain"] = (
            self.web_domain.text().strip() or DEFAULTS["web_domain"]
        )
        prefs["proxy"] = self.proxy.text().strip()
        prefs["work_dir"] = self.work_dir.text().strip()
        prefs["check_duplicates"] = self.check_duplicates.isChecked()
        prefs["keep_workdir"] = self.keep_workdir.isChecked()
