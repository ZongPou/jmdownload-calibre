"""下载对话框：ID/链接输入、实时解析预览、环境探测、下载进度与日志。

下载走 worker.DownloadWorker（子进程桥调用系统 Python 的 jmcomic），
本类只负责 UI 状态机、事件展示与会话日志（一键复制，供排障反馈）。
进度条双模式：拿到总页数（meta.total_images）后为百分比模式，否则 busy。

线程生命周期（防闪退）：worker 无 Qt parent；finished 同时连接
on_worker_finished（UI 复位）与 deleteLater（Qt 事件循环安全删除）；
结束后 Python 引用保留在 self._worker，直到下次下载覆盖。
"""

from datetime import datetime

from qt.core import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTimer,
    QVBoxLayout,
    pyqtSignal,
    QThread,
)

from calibre_plugins.jmcomic2calibre.common import describe_probe, parse_album_ids
from calibre_plugins.jmcomic2calibre.config import prefs

LOG_MAX_LINES = 3000  # 日志缓冲上限（超出丢弃最旧的）


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
        self.gui = plugin.gui  # calibre 主窗口引用（书库刷新用）
        self._probe = None
        self._worker = None
        self._downloading = False
        self._python_cmd = None  # doctor 探测到的解释器命令
        self._album_start_text = ""
        self._total_images = 0  # 当前本的预期图片总数（meta 事件带来）
        self._log_lines = []  # 会话日志（带时间戳，供一键复制）

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

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 不确定进度（busy）
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        buttons = QHBoxLayout()
        self.reprobe_button = QPushButton("重新检测环境")
        self.reprobe_button.clicked.connect(self.start_probe)
        buttons.addWidget(self.reprobe_button)
        self.copy_log_button = QPushButton("复制日志")
        self.copy_log_button.setToolTip(
            "复制本次会话的操作日志到剪贴板（报障时请粘贴给开发者）"
        )
        self.copy_log_button.clicked.connect(self.copy_log)
        buttons.addWidget(self.copy_log_button)
        buttons.addStretch(1)
        self.download_button = QPushButton("开始下载")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.on_download_clicked)
        buttons.addWidget(self.download_button)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._log("对话框已打开（插件 v%s）" % self._version_text())
        self.start_probe()

    # ---- 日志 ----

    def _version_text(self) -> str:
        version = getattr(self.plugin, "version", None) or (0, 0, 0)
        return ".".join(str(x) for x in version)

    def _log(self, message: str) -> None:
        """追加一行会话日志（多行消息按行拆分），超出上限丢弃最旧的。"""
        stamp = datetime.now().strftime("%H:%M:%S")
        for line in str(message).splitlines() or [""]:
            self._log_lines.append("[%s] %s" % (stamp, line))
        if len(self._log_lines) > LOG_MAX_LINES:
            del self._log_lines[:-LOG_MAX_LINES]

    def copy_log(self):
        """把会话日志（含环境头信息）复制到剪贴板。"""
        try:
            from calibre.constants import __version__ as calibre_version
        except Exception:
            calibre_version = "未知"
        header = [
            "JMComic Downloader 日志",
            "插件版本: %s | calibre 版本: %s" % (self._version_text(), calibre_version),
            "系统: Windows | 导出时间: %s"
            % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "-" * 48,
        ]
        body = self._log_lines or ["（本次会话暂无日志）"]
        QApplication.clipboard().setText("\n".join(header + body))
        self._log("日志已复制到剪贴板（%d 行）" % len(body))
        self.copy_log_button.setText("已复制 ✓")
        QTimer.singleShot(1500, lambda: self.copy_log_button.setText("复制日志"))

    # ---- 环境探测 ----

    def start_probe(self):
        if self._probe is not None and self._probe.isRunning():
            return
        self.status_label.setText("正在检测运行环境（Python / jmcomic）…")
        self._probe = ProbeThread(self)
        self._probe.done.connect(self.on_probe_done)
        self._probe.start()

    def on_probe_done(self, result):
        text = describe_probe(result)
        self.status_label.setText(text)
        self._log(text)
        if result and result.get("ok") and result.get("cmd"):
            self._python_cmd = list(result["cmd"])
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
        if not self._downloading:
            self.download_button.setEnabled(bool(ids))

    # ---- 下载 ----

    def on_download_clicked(self):
        if self._downloading:
            self._worker.cancel()
            self.download_button.setEnabled(False)
            self.status_label.setText("正在取消…")
            self._log("用户请求取消下载")
            return
        ids, _errors = parse_album_ids(self.input_edit.toPlainText())
        if not ids:
            return
        if not self._python_cmd:
            self.status_label.setText("环境未就绪，请先等待检测通过。")
            self.start_probe()
            return
        from calibre_plugins.jmcomic2calibre.worker import DownloadWorker

        # worker 不设 parent：QThread 带父对象时，若线程未结束就被级联
        # 销毁会硬崩（"Destroyed while thread is still running"）。
        # 生命周期：finished → on_worker_finished（UI 复位）+ deleteLater
        #（Qt 事件循环安全删除）；Python 引用保留到下次下载覆盖。
        self._worker = DownloadWorker(
            ids, self._python_cmd, self.gui.current_db
        )
        self._worker.message_received.connect(self.on_worker_event)
        self._worker.finished.connect(self.on_worker_finished)
        self._worker.finished.connect(self._worker.deleteLater)
        self.set_downloading_ui(True)
        self.status_label.setText("正在启动下载引擎…")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self._log(
            "启动下载：%s（解释器: %s，临时目录: %s）"
            % (
                "、".join(ids),
                " ".join(self._python_cmd),
                prefs["work_dir"] or "系统默认",
            )
        )
        self._worker.start()

    def set_downloading_ui(self, downloading: bool):
        self._downloading = downloading
        self.input_edit.setEnabled(not downloading)
        self.reprobe_button.setEnabled(not downloading)
        self.download_button.setText("取消" if downloading else "开始下载")

    def on_worker_event(self, ev):
        kind = ev.get("event")
        if kind == "album_start":
            self._album_start_text = "正在下载 %s…" % ev.get("album_id")
            self._total_images = 0
            self.status_label.setText(self._album_start_text)
            self.progress_bar.setRange(0, 0)  # 元数据未到，先 busy
        elif kind == "meta":
            title = ev.get("title", "")
            authors = "、".join(ev.get("authors") or [])
            head = "《%s》" % title if title else ev.get("album_id", "")
            if authors:
                head += "（%s）" % authors
            self._album_start_text = "正在下载 %s …" % head
            self.status_label.setText(self._album_start_text)
            self._total_images = int(ev.get("total_images") or 0)
            self._log(
                "元数据：《%s》 作者: %s 标签: %s 总页数: %s"
                % (
                    title,
                    authors or "未知",
                    "、".join(ev.get("tags") or []) or "无",
                    self._total_images or "未知",
                )
            )
            if self._total_images > 0:
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(0)
            else:
                self.progress_bar.setRange(0, 0)
        elif kind == "progress":
            n = int(ev.get("images") or 0)
            total = int(ev.get("total") or self._total_images or 0)
            percent = ev.get("percent")
            if total > 0:
                self.status_label.setText(
                    "%s 已下载 %d/%d 张（%s%%）"
                    % (self._album_start_text, n, total, percent)
                )
                if percent is not None:
                    self.progress_bar.setValue(int(percent))
            else:
                self.status_label.setText(
                    "%s 已下载 %d 张图片" % (self._album_start_text, n)
                )
        elif kind == "log":
            # jmcomic 噪音输出 / worker 调试信息：记入日志（不进状态行）
            for line in str(ev.get("message", "")).splitlines():
                if line.strip():
                    self._log(line)
        elif kind == "downloaded":
            self.status_label.setText(
                "%s 下载完成：%s 张图片" % (self._album_start_text, ev.get("images", "?"))
            )
            self._log(
                "下载完成：%s 张图片（目录: %s）"
                % (ev.get("images", "?"), ev.get("dir", "?"))
            )
            if self._total_images > 0:
                self.progress_bar.setValue(100)
        elif kind == "album_ok":
            pass  # 汇总在 all_done
        elif kind == "ingesting":
            self._album_start_text = "正在打包入库《%s》…" % ev.get("title", "")
            self.status_label.setText(self._album_start_text)
            self._log("开始打包 CBZ 并入库…")
        elif kind == "ingested":
            self.status_label.setText(
                "已入库：《%s》→ 书号 %s（metadata.opf 已同步生成）"
                % (ev.get("title", ev.get("album_id")), ev.get("book_id"))
            )
            self._log(
                "已入库：《%s》→ 书号 %s"
                % (ev.get("title", ev.get("album_id")), ev.get("book_id"))
            )
        elif kind == "skipped":
            self.status_label.setText(
                "已在书库，跳过：%s（书号 %s）"
                % (ev.get("album_id"), ev.get("book_id"))
            )
            self._log(
                "判重命中，跳过：%s（书号 %s）"
                % (ev.get("album_id"), ev.get("book_id"))
            )
        elif kind == "error":
            message = ev.get("message", "")
            self.status_label.setText("错误：%s" % message)
            self._log("错误：%s" % message)
            tb = ev.get("traceback")
            if tb:
                self._log(tb)  # bridge 的完整堆栈（排障关键）
        elif kind == "all_done":
            self.report_all_done(ev)

    def report_all_done(self, ev):
        ok = ev.get("ok") or []
        skipped = ev.get("skipped") or []
        failed = ev.get("failed") or {}
        self.progress_bar.setVisible(False)
        self.set_downloading_ui(False)
        parts = []
        if ok:
            parts.append("入库 %d 本：%s" % (len(ok), "、".join(ok)))
        if skipped:
            parts.append("跳过（已在书库）：%s" % "、".join(skipped))
        if failed:
            detail = "；".join(
                "%s: %s" % (k, v) for k, v in sorted(failed.items())
            )
            parts.append("失败 %d 本：%s" % (len(failed), detail))
        summary = "；".join(parts) or "无任务"
        self.status_label.setText(summary)
        self._log("全部结束：%s" % summary)
        if ok:
            # legacy add_books 会同步 GUI 数据缓存，但视图仍需手动触发重载；
            # 各步骤独立容错，避免单点异常中断整条刷新链
            gui = self.gui

            def _step(func):
                try:
                    func()
                except Exception:
                    pass

            _step(lambda: gui.library_view.model().books_added(len(ok)))
            _step(lambda: gui.refresh_cover_browser())
            _step(lambda: gui.tags_view.recount())
        self.update_preview()

    def on_worker_finished(self):
        # UI 复位。注意：不置 self._worker = None——QThread 的 C++ 线程
        # 此刻可能尚未完全退出，解除 Python 引用会被 GC 触发析构导致闪退；
        # C++ 对象由 deleteLater 在事件循环中安全删除，Python 引用保留到
        # 下次下载覆盖。
        self.set_downloading_ui(False)

    # ---- 生命周期 ----

    def closeEvent(self, event):
        if self._probe is not None and self._probe.isRunning():
            self._probe.wait(3000)
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(5000)  # 超时也不销毁线程，由 deleteLater 兜底
        super().closeEvent(event)
