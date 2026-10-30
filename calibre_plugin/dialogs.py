"""下载对话框：ID/链接输入、实时解析预览、环境探测、下载进度与日志。

下载走 worker.DownloadWorker（子进程桥调用系统 Python 的 jmcomic），
本类只负责 UI 状态机、事件展示与会话日志（一键复制，供排障反馈）。
进度条双模式：拿到总页数（meta.total_images）后为百分比模式，否则 busy。

线程生命周期（防闪退）：worker 无 Qt parent；finished 同时连接
on_worker_finished（UI 复位）与 deleteLater（Qt 事件循环安全删除）；
结束后 Python 引用保留在 self._worker，直到下次下载覆盖。
"""

from datetime import datetime
import base64

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
    QListWidget, QListWidgetItem, QLineEdit, QMessageBox, Qt, QSize, QIcon, QPixmap,
)

from calibre_plugins.jmcomic2calibre.common import describe_probe, parse_album_ids
from calibre_plugins.jmcomic2calibre.config import prefs
from calibre_plugins.jmcomic2calibre.common import parse_chapter_range, chapter_label, selection_key

LOG_MAX_LINES = 3000  # 日志缓冲上限（超出丢弃最旧的）


class ChapterDialog(QDialog):
    def __init__(self, parent, meta):
        super().__init__(parent)
        self.setWindowTitle("选择下载章节")
        self.resize(500, 540)
        self.chapters = meta["chapters"]
        layout = QVBoxLayout(self)
        title = QLabel("%s\nID %s · 共 %d 集" % (meta["title"], meta["album_id"], len(self.chapters)))
        title.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(title)
        layout.addWidget(QLabel("批量选择章节（例如 1-10、12、15-18）"))
        row = QHBoxLayout()
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("输入章节范围，例如 1-10")
        row.addWidget(self.range_edit)
        apply_button = QPushButton("应用范围")
        apply_button.clicked.connect(self.apply_range)
        row.addWidget(apply_button)
        layout.addLayout(row)
        tools = QHBoxLayout()
        for label, checked in (("全选", True), ("清空", False)):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, value=checked: self.select_all(value))
            tools.addWidget(button)
        layout.addLayout(tools)
        self.list = QListWidget()
        for chapter in self.chapters:
            item = QListWidgetItem("第 %d 集　%s" % (chapter["number"], chapter["title"]))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)
        self.list.itemChanged.connect(self.update_count)
        layout.addWidget(self.list)
        self.count = QLabel()
        layout.addWidget(self.count)
        buttons = QHBoxLayout()
        skip = QPushButton("跳过此漫画")
        skip.clicked.connect(self.reject)
        buttons.addWidget(skip)
        self.confirm = QPushButton("确认并加入队列")
        self.confirm.clicked.connect(self.accept)
        buttons.addWidget(self.confirm)
        layout.addLayout(buttons)
        self.update_count()

    def selected_ids(self):
        return [c["id"] for i, c in enumerate(self.chapters)
                if self.list.item(i).checkState() == Qt.CheckState.Checked]

    def update_count(self, *_):
        n = len(self.selected_ids())
        self.count.setText("已选 %d / %d 集" % (n, len(self.chapters)))
        self.confirm.setEnabled(n > 0)

    def select_all(self, checked):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def apply_range(self):
        try:
            numbers = set(parse_chapter_range(self.range_edit.text(), len(self.chapters)))
        except ValueError as exc:
            QMessageBox.warning(self, "章节范围无效", str(exc))
            return
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.CheckState.Checked if i + 1 in numbers else Qt.CheckState.Unchecked)


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
        self._tasks = []
        self._prepare = None
        self._prepare_busy = False
        self._selection_open = False
        self._closing = False
        self._active_task = None

        self.setWindowTitle("JMdownload 下载")
        self.setMinimumWidth(660)

        layout = QVBoxLayout(self)

        self.status_label = QLabel("正在检测运行环境（Python / jmcomic）…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("每行一个漫画 ID 或网页链接："))
        self.input_edit = QPlainTextEdit()
        self.input_edit.setMaximumHeight(110)
        self.input_edit.setPlaceholderText(
            "例如：\n350234\nhttps://18comic.vip/album/350234/"
        )
        self.input_edit.textChanged.connect(self.update_preview)
        layout.addWidget(self.input_edit)

        self.preview_label = QLabel("")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)
        layout.addWidget(QLabel("下载队列（下载中可继续添加 ID）"))
        self.queue_list = QListWidget()
        self.queue_list.setIconSize(QSize(48, 68))
        self.queue_list.setMinimumHeight(220)
        layout.addWidget(self.queue_list)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 不确定进度（busy）
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        buttons = QHBoxLayout()
        self.reprobe_button = QPushButton("重新检测环境")
        self.reprobe_button.clicked.connect(self.start_probe)
        buttons.addWidget(self.reprobe_button)
        config_button = QPushButton("配置")
        config_button.clicked.connect(self.plugin.show_config)
        buttons.addWidget(config_button)
        self.copy_log_button = QPushButton("复制日志")
        self.copy_log_button.setToolTip(
            "复制本次会话的操作日志到剪贴板（报障时请粘贴给开发者）"
        )
        self.copy_log_button.clicked.connect(self.copy_log)
        buttons.addWidget(self.copy_log_button)
        buttons.addStretch(1)
        self.download_button = QPushButton("添加到队列")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.on_download_clicked)
        buttons.addWidget(self.download_button)
        self.cancel_button = QPushButton("取消当前任务")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_current)
        buttons.addWidget(self.cancel_button)
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
            "JMdownload 日志",
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
        self.update_preview()

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
        self.download_button.setEnabled(bool(ids) and bool(self._python_cmd) and not errors)

    # ---- 下载 ----

    def on_download_clicked(self):
        ids, _errors = parse_album_ids(self.input_edit.toPlainText())
        if not ids or _errors:
            return
        if not self._python_cmd:
            self.status_label.setText("环境未就绪，请先等待检测通过。")
            self.start_probe()
            return
        for album_id in ids:
            if any(t["id"] == album_id and t["state"] not in ("完成", "失败", "已取消", "已跳过") for t in self._tasks):
                self._log("队列中已存在，跳过重复添加：" + album_id)
                continue
            item = QListWidgetItem()
            item.setSizeHint(QSize(560, 82))
            self.queue_list.addItem(item)
            task = {"id": album_id, "state": "待读取章节", "item": item}
            self._tasks.append(task)
            self._render_task(task)
        self.input_edit.clear()
        self._start_prepare()

    def _render_task(self, task):
        task["item"].setText("%s\nID %s · %s\n%s" % (
            task.get("meta", {}).get("title", task["id"]), task["id"],
            task.get("label", "正在获取章节与封面"), task["state"]))
        task["item"].setToolTip(task.get("error", ""))

    def _start_prepare(self):
        if self._closing or self._prepare_busy:
            return
        task = next((t for t in self._tasks if t["state"] == "待读取章节"), None)
        if task is None:
            return
        from calibre_plugins.jmcomic2calibre.worker import PrepareWorker
        self._prepare_busy = True
        task["state"] = "读取章节中"
        self._render_task(task)
        self._prepare = PrepareWorker([task["id"]], self._python_cmd, None)
        self._prepare.message_received.connect(self._on_prepared)
        self._prepare.finished.connect(self._prepare_finished)
        self._prepare.finished.connect(self._prepare.deleteLater)
        self._prepare.start()

    def _prepare_finished(self):
        self._prepare_busy = False
        self._start_prepare()

    def _on_prepared(self, ev):
        if self._closing:
            return
        if ev["event"] == "log":
            self._log(ev.get("message", ""))
            return
        task = next(t for t in self._tasks if t["id"] == ev["album_id"] and t["state"] == "读取章节中")
        if ev["event"] == "prepare_error":
            task.update(state="失败", error=ev["message"], label="读取失败，可重新添加")
            self._log("读取章节失败 %s: %s" % (task["id"], ev["message"]))
        else:
            task.update(meta=ev["meta"], state="待选择章节")
            if ev.get("cover"):
                pixmap = QPixmap()
                pixmap.loadFromData(base64.b64decode(ev["cover"]))
                if not pixmap.isNull():
                    task["item"].setIcon(QIcon(pixmap))
        self._render_task(task)
        QTimer.singleShot(0, self._choose_next)
        self._start_next()

    def _choose_next(self):
        if self._closing or self._selection_open:
            return
        task = next((t for t in self._tasks if t["state"] == "待选择章节"), None)
        if not task:
            return
        self._selection_open = True
        chapters = task["meta"]["chapters"]
        if len(chapters) <= int(prefs["auto_download_chapters"]):
            selected = [c["id"] for c in chapters]
        else:
            dialog = ChapterDialog(self, task["meta"])
            selected = dialog.selected_ids() if dialog.exec() == QDialog.DialogCode.Accepted else []
        if selected:
            numbers = [c["number"] for c in chapters if c["id"] in selected]
            label = "全部 %d 集" % len(chapters) if len(selected) == len(chapters) else "第 %s 集" % chapter_label(numbers)
            ingest_meta = {"selection_key": selection_key(task["id"], chapters, selected)}
            if len(selected) != len(chapters):
                ingest_meta["title"] = task["meta"]["title"] + "（" + label + "）"
            task.update(state="等待中", selected=selected, label=label, ingest_meta=ingest_meta)
            self._log("加入队列：%s · %s" % (task["id"], label))
        else:
            task.update(state="已跳过", label="未选择章节")
        self._render_task(task)
        self._selection_open = False
        self._start_next()
        QTimer.singleShot(0, self._choose_next)

    def _start_next(self):
        if self._closing or self._downloading:
            return
        task = next((t for t in self._tasks if t["state"] not in ("完成", "失败", "已取消", "已跳过")), None)
        if not task or task["state"] != "等待中":
            return
        from calibre_plugins.jmcomic2calibre.worker import DownloadWorker
        ids = [task["id"]]
        self._active_task = task
        task["state"] = "下载中"
        self._render_task(task)

        # worker 不设 parent：QThread 带父对象时，若线程未结束就被级联
        # 销毁会硬崩（"Destroyed while thread is still running"）。
        # 生命周期：finished → on_worker_finished（UI 复位）+ deleteLater
        #（Qt 事件循环安全删除）；Python 引用保留到下次下载覆盖。
        self._worker = DownloadWorker(
            ids, self._python_cmd, self.gui.current_db, selection=task
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
        self.reprobe_button.setEnabled(not downloading)
        self.download_button.setText("添加到队列")
        self.cancel_button.setEnabled(downloading)

    def cancel_current(self):
        if self._downloading:
            self._worker.cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("正在取消当前任务…")
            self._log("用户请求取消当前任务，队列中的其他任务保留")

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
        task = self._active_task
        if task:
            error = failed.get(task["id"], "")
            task["state"] = ("完成" if ok else "已跳过" if skipped else
                             "已取消" if error == "已取消" else "失败")
            task["error"] = error
            self._render_task(task)
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
        if self._active_task and self._active_task["state"] == "下载中":
            self._active_task.update(state="失败", error="下载线程未返回结果，请复制日志排查")
            self._render_task(self._active_task)
        self._start_next()

    # ---- 生命周期 ----

    def closeEvent(self, event):
        event.ignore()
        self.reject()

    def reject(self):
        if not self._closing:
            self._closing = True
            self.setEnabled(False)
            self.status_label.setText("正在结束后台任务…")
            if self._downloading:
                self._worker.cancel()
            if self._prepare_busy:
                self._prepare.cancel()
        # 不销毁仍在运行的 QThread；finished 信号在事件循环中处理后再关窗。
        if self._downloading or self._prepare_busy or self._probe is not None:
            QTimer.singleShot(100, self.reject)
            return
        super().reject()
