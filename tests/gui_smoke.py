"""离线真实 Qt 冒烟测试：calibre-debug -e tests/gui_smoke.py。

使用内存配置、模拟下载进程，不连接站点、不读写用户书库或配置。
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys
import types
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
package = types.ModuleType("calibre_plugins.jmcomic2calibre")
package.__path__ = [str(ROOT / "calibre_plugin")]
sys.modules[package.__name__] = package
from calibre_plugins.jmcomic2calibre.common import DEFAULTS
config = types.ModuleType(package.__name__ + ".config")
config.prefs = dict(DEFAULTS)
sys.modules[config.__name__] = config

from qt.core import QApplication, QDialog, QListWidgetItem, Qt
from calibre_plugins.jmcomic2calibre.dialogs import DownloadDialog, ChapterDialog
from calibre_plugins.jmcomic2calibre.worker import DownloadWorker, PrepareWorker
from calibre_plugins.jmcomic2calibre.config_widget import ConfigWidget
APP = QApplication.instance() or QApplication([])


def metadata(n):
    return {"title": "测试漫画", "album_id": "123", "chapters": [
        {"id": str(100 + i), "number": i, "title": "章节 %d" % i} for i in range(1, n + 1)]}


class GuiTests(unittest.TestCase):
    def setUp(self):
        config.prefs.update(DEFAULTS)
        self.patches = [patch.object(DownloadDialog, "start_probe"),
                        patch.object(DownloadDialog, "_start_prepare"),
                        patch.object(DownloadDialog, "_start_next")]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.dialog = DownloadDialog(None, types.SimpleNamespace(gui=Mock(), version=(0, 3, 0), show_config=Mock()))
        self.dialog._python_cmd = ["python"]

    def tearDown(self):
        self.dialog._closing = True

    def test_append_during_download_and_active_duplicate_filtered(self):
        self.dialog.set_downloading_ui(True)
        self.dialog.input_edit.setPlainText("123\n456")
        self.assertTrue(self.dialog.input_edit.isEnabled())
        self.assertTrue(self.dialog.download_button.isEnabled())
        self.dialog.on_download_clicked()
        self.dialog.input_edit.setPlainText("456\n789")
        self.dialog.on_download_clicked()
        self.assertEqual(["123", "456", "789"], [t["id"] for t in self.dialog._tasks])
        self.assertEqual("", self.dialog.input_edit.toPlainText())

    def task(self, n):
        item = QListWidgetItem()
        self.dialog.queue_list.addItem(item)
        t = {"id": "123", "state": "待选择章节", "meta": metadata(n), "item": item}
        self.dialog._tasks.append(t)
        return t

    def test_threshold_boundary_downloads_all_without_dialog(self):
        t = self.task(3)
        with patch.object(ChapterDialog, "exec") as execute:
            self.dialog._choose_next()
            execute.assert_not_called()
        self.assertEqual("等待中", t["state"])
        self.assertEqual(["101", "102", "103"], t["selected"])
        self.assertEqual("123", t["ingest_meta"]["selection_key"])

    def test_over_threshold_uses_dialog_and_range(self):
        t = self.task(12)
        def execute(d):
            d.range_edit.setText("1-10")
            d.apply_range()
            return QDialog.DialogCode.Accepted
        with patch.object(ChapterDialog, "exec", execute):
            self.dialog._choose_next()
        self.assertEqual(10, len(t["selected"]))
        self.assertEqual("第 1-10 集", t["label"])
        self.assertIn("第 1-10 集", t["ingest_meta"]["title"])

    def test_skip_does_not_download(self):
        t = self.task(4)
        with patch.object(ChapterDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.dialog._choose_next()
        self.assertEqual("已跳过", t["state"])

    def test_invalid_input_disables_submission(self):
        self.dialog.input_edit.setPlainText("123\ninvalid")
        self.assertFalse(self.dialog.download_button.isEnabled())
        self.dialog.on_download_clicked()
        self.assertEqual([], self.dialog._tasks)

    def test_config_threshold_saved_in_memory(self):
        widget = ConfigWidget()
        widget.auto_download_chapters.setValue(10)
        widget.save_settings()
        self.assertEqual(10, config.prefs["auto_download_chapters"])

    def test_zero_threshold_always_selects(self):
        config.prefs["auto_download_chapters"] = 0
        self.task(1)
        with patch.object(ChapterDialog, "exec", return_value=QDialog.DialogCode.Rejected) as execute:
            self.dialog._choose_next()
            execute.assert_called_once()

    def test_cover_event_uses_actual_qpixmap(self):
        from qt.core import QPixmap, QBuffer, QByteArray, QIODevice
        import base64
        t = self.task(3)
        t["state"] = "读取章节中"
        pixmap = QPixmap(20, 30)
        pixmap.fill(Qt.GlobalColor.blue)
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        self.dialog._on_prepared({"event": "prepared", "album_id": "123", "meta": metadata(3),
                                 "cover": base64.b64encode(bytes(data)).decode()})
        self.assertFalse(t["item"].icon().isNull())

    def test_cancel_only_current_and_waits_for_finished(self):
        self.dialog._worker = Mock()
        self.dialog.set_downloading_ui(True)
        self.dialog.cancel_current()
        self.dialog._worker.cancel.assert_called_once()
        self.assertTrue(self.dialog._downloading)
        self.assertFalse(self.dialog.cancel_button.isEnabled())

    def test_cancel_waiting_tasks_keeps_current_download_running(self):
        first = self.task(4)
        second = self.task(4)
        second["id"] = "456"
        first["state"] = "下载中"
        self.dialog._apply_selection(second, ["101"])
        self.dialog._active_task = first
        self.dialog._worker = Mock()
        self.dialog.set_downloading_ui(True)
        second["item"].setSelected(True)
        self.assertTrue(self.dialog.edit_task_button.isEnabled())
        self.dialog.cancel_selected_tasks()
        self.assertEqual("已取消", second["state"])
        self.assertEqual("下载中", first["state"])
        self.dialog._worker.cancel.assert_not_called()

    def test_cancel_preparing_ignores_late_result_even_after_same_id_readded(self):
        old = self.task(4)
        old["state"] = "读取章节中"
        self.dialog._preparing_task = old
        self.dialog._prepare_busy = True
        self.dialog._prepare = Mock()
        old["item"].setSelected(True)
        self.dialog.cancel_selected_tasks()
        self.dialog._prepare.cancel.assert_called_once()
        new = self.task(4)
        new["state"] = "读取章节中"
        self.dialog._on_prepared({"event": "prepared", "album_id": "123", "meta": metadata(4)})
        self.assertEqual("已取消", old["state"])
        self.assertEqual("读取章节中", new["state"])

    def test_edit_restores_selection_and_updates_range_without_auto_start(self):
        task = self.task(12)
        self.dialog._apply_selection(task, ["101", "102"])
        task["item"].setSelected(True)
        old_key = task["ingest_meta"]["selection_key"]
        def execute(d):
            self.assertEqual(["101", "102"], d.selected_ids())
            self.assertEqual("修改章节中", task["state"])
            d.range_edit.setText("3-5")
            d.apply_range()
            return QDialog.DialogCode.Accepted
        with patch.object(ChapterDialog, "exec", execute):
            self.dialog.edit_selected_task()
        self.assertEqual("等待中", task["state"])
        self.assertEqual(["103", "104", "105"], task["selected"])
        self.assertEqual("第 3-5 集", task["label"])
        self.assertNotEqual(old_key, task["ingest_meta"]["selection_key"])

    def test_dismiss_edit_keeps_old_chapters_and_active_cannot_edit(self):
        task = self.task(8)
        self.dialog._apply_selection(task, ["101"])
        task["item"].setSelected(True)
        with patch.object(ChapterDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.dialog.edit_selected_task()
        self.assertEqual(["101"], task["selected"])
        self.assertEqual("等待中", task["state"])
        task["state"] = "下载中"
        self.dialog._render_task(task)
        self.assertFalse(self.dialog.edit_task_button.isEnabled())
        with patch.object(ChapterDialog, "exec") as execute:
            self.dialog.edit_selected_task()
            execute.assert_not_called()

    def test_cancel_multiple_selected_tasks(self):
        for _ in range(3):
            t = self.task(4)
            t["state"] = "等待中"
            t["item"].setSelected(True)
        self.dialog.cancel_selected_tasks()
        self.assertEqual(["已取消"] * 3, [t["state"] for t in self.dialog._tasks])

    def test_progress_stays_busy_until_selected_total_is_known(self):
        self.dialog.on_worker_event({"event": "meta", "total_images": 0})
        self.dialog.on_worker_event({"event": "pages_known", "known_pages": 20,
                                    "chapters_ready": 1, "chapters_total": 2, "total": 0})
        self.assertEqual(0, self.dialog.progress_bar.maximum())
        self.dialog.on_worker_event({"event": "pages_known", "known_pages": 50,
                                    "chapters_ready": 2, "chapters_total": 2, "total": 50})
        self.dialog.on_worker_event({"event": "progress", "images": 25, "total": 50, "percent": 50})
        self.assertEqual(100, self.dialog.progress_bar.maximum())
        self.assertEqual(50, self.dialog.progress_bar.value())


class WorkerTests(unittest.TestCase):
    def test_cancel_removes_partial_folder_without_downloaded_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = DownloadWorker(["123"], ["python"], Mock())
            folder = Path(tmp) / "partial"
            folder.mkdir()
            (folder / "1.jpg").write_bytes(b"partial")
            proc = Mock(stdout=[], returncode=-15)
            proc.wait.side_effect = lambda: setattr(worker, "_cancelled", True)
            worker._work_dir = Mock(return_value=str(folder))
            with patch("calibre_plugins.jmcomic2calibre.worker.subprocess.Popen", return_value=proc):
                self.assertFalse(worker._run_one("123", "bridge.py"))
            self.assertFalse(folder.exists())
            self.assertEqual("已取消", worker.failed["123"])

    def test_prepare_failure_emits_failure_and_never_downloads(self):
        worker = PrepareWorker(["123"], ["python"], None)
        received = []
        worker.message_received.connect(received.append)
        proc = Mock(returncode=0)
        proc.communicate.return_value = ('{"event":"error","message":"模拟失败"}\n', None)
        with tempfile.TemporaryDirectory() as tmp:
            bridge = Path(tmp) / "bridge.py"
            bridge.touch()
            worker._extract_bridge = Mock(return_value=str(bridge))
            with patch("calibre_plugins.jmcomic2calibre.worker.subprocess.Popen", return_value=proc):
                worker.run()
        self.assertEqual("prepare_error", received[0]["event"])
        self.assertEqual("模拟失败", received[0]["message"])


class PipelineTests(unittest.TestCase):
    def test_real_threads_continue_queue_after_append(self):
        config.prefs.update(DEFAULTS)
        import threading
        import time
        started, release = threading.Event(), threading.Event()
        completed = []
        def run_one(worker, album_id, bridge_path):
            if album_id == "123":
                started.set()
                release.wait(3)
            worker.ok_ids.append(album_id)
            completed.append(album_id)
        with tempfile.TemporaryDirectory() as tmp:
            def bridge(worker):
                path = Path(tmp) / (worker.album_ids[0] + ".py")
                path.touch()
                return str(path)
            with patch.object(DownloadDialog, "start_probe"), patch.object(DownloadDialog, "_start_prepare"), patch.object(DownloadWorker, "_extract_bridge", bridge), patch.object(DownloadWorker, "_run_one", run_one):
                dialog = DownloadDialog(None, types.SimpleNamespace(gui=Mock(), version=(0, 3, 0), show_config=Mock()))
                dialog._python_cmd = ["python"]
                try:
                    for album_id in ("123", "456"):
                        dialog.input_edit.setPlainText(album_id)
                        dialog.on_download_clicked()
                        task = dialog._tasks[-1]
                        task["state"] = "读取章节中"
                        meta = metadata(2)
                        meta["album_id"] = album_id
                        dialog._on_prepared({"event": "prepared", "album_id": album_id, "meta": meta})
                        dialog._choose_next()
                        if album_id == "123":
                            self.assertTrue(started.wait(2))
                            self.assertTrue(dialog._downloading)
                    self.assertEqual("等待中", dialog._tasks[1]["state"])
                    release.set()
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline and (dialog._downloading or len(completed) < 2):
                        APP.processEvents()
                        time.sleep(0.005)
                    self.assertEqual(["123", "456"], completed)
                    self.assertEqual(["完成", "完成"], [t["state"] for t in dialog._tasks])
                finally:
                    release.set()
                    dialog._closing = True
                    if dialog._downloading:
                        dialog._worker.wait(3000)
                    APP.processEvents()


class IngestTests(unittest.TestCase):
    def test_partial_selection_does_not_block_other_selection_or_full_album(self):
        from calibre_plugins.jmcomic2calibre.ingest import create_book
        from calibre.ebooks.metadata.book.base import Metadata
        db = Mock()
        db.new_api.search.return_value = {1}
        old = Metadata("已下载选集")
        old.set_identifiers({"jmcomic": "123", "jmchapters": "123-sfirst"})
        db.new_api.get_metadata.return_value = old
        db.add_books.return_value = [2]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "1.jpg").write_bytes(b"image")
            result = create_book("123", tmp, {"title": "其他选集", "selection_key": "123-ssecond"}, db)
            self.assertEqual("ingested", result["status"])
            identifiers = db.add_books.call_args.args[2][0].get_identifiers()
            self.assertEqual("123", identifiers["jmcomic"])
            self.assertEqual("123-ssecond", identifiers["jmchapters"])
            self.assertTrue(identifiers["url"].endswith("/album/123/"))
            result = create_book("123", tmp, {"title": "全本"}, db)
            self.assertEqual("ingested", result["status"])
            self.assertNotIn("jmchapters", db.add_books.call_args.args[2][0].get_identifiers())
            result = create_book("123", tmp, {"selection_key": "123-sfirst"}, db)
            self.assertEqual("skipped", result["status"])
            old.set_identifiers({"jmcomic": "123"})
            result = create_book("123", tmp, {"selection_key": "123-ssecond"}, db)
            self.assertEqual("skipped", result["status"])


suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                           for cls in (GuiTests, WorkerTests, PipelineTests, IngestTests))
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
