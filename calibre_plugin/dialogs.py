"""下载对话框：ID/链接输入、实时解析预览、环境探测、下载进度。

下载走 worker.DownloadWorker（子进程桥调用系统 Python 的 jmcomic），
本类只负责 UI 状态机与事件展示。
进度条双模式：拿到总页数（meta.total_images）后为百分比模式，否则 busy。

线程生命周期（防闪退）：worker 无 Qt parent；finished 同时连接
on_worker_finished（UI 复位）与 deleteLater（Qt 事件循环安全删除）；
结束后 Python 引用保留在 self._worker，直到下次下载覆盖。
"""

from qt.core import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    pyqtSignal,
    QThread,
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
        self.gui = plugin.gui  # calibre 主窗口引用（书库刷新用）
        self._probe = None
        self._worker = None
        self._downloading = False
        self._python_cmd = None  # doctor 探测到的解释器命令
        self._album_start_text = ""
        self._total_images = 0  # 当前本的预期图片总数（meta 事件带来）

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
        buttons.addStretch(1)
        self.download_button = QPushButton("开始下载")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.on_download_clicked)
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
        self._worker.event.connect(self.on_worker_event)
        self._worker.finished.connect(self.on_worker_finished)
        self._worker.finished.connect(self._worker.deleteLater)
        self.set_downloading_ui(True)
        self.status_label.setText("正在启动下载引擎…")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
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
            pass  # 噪音输出，忽略
        elif kind == "downloaded":
            self.status_label.setText(
                "%s 下载完成：%s 张图片" % (self._album_start_text, ev.get("images", "?"))
            )
            if self._total_images > 0:
                self.progress_bar.setValue(100)
        elif kind == "album_ok":
            pass  # 汇总在 all_done
        elif kind == "ingesting":
            self._album_start_text = "正在打包入库《%s》…" % ev.get("title", "")
            self.status_label.setText(self._album_start_text)
        elif kind == "ingested":
            self.status_label.setText(
                "已入库：《%s》→ 书号 %s（metadata.opf 已同步生成）"
                % (ev.get("title", ev.get("album_id")), ev.get("book_id"))
            )
        elif kind == "skipped":
            self.status_label.setText(
                "已在书库，跳过：%s（书号 %s）"
                % (ev.get("album_id"), ev.get("book_id"))
            )
        elif kind == "error":
            self.status_label.setText("错误：%s" % ev.get("message", ""))
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
        self.status_label.setText("；".join(parts) or "无任务")
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
