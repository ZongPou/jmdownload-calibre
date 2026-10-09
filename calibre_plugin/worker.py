"""下载工作线程：提取 bridge.py → 子进程执行 → JSON 事件流转发到 UI。

由系统 Python（doctor 探测到的解释器）运行 bridge，本线程只做进程
管理与事件转发，不做下载。取消 = 终止当前子进程并停止后续队列。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from qt.core import QThread, pyqtSignal

from calibre_plugins.jmcomic2calibre.common import parse_event_line
from calibre_plugins.jmcomic2calibre.config import prefs

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class DownloadWorker(QThread):
    """album_ids 队列逐个下载；event 信号把事件 dict 发回 UI 线程。

    下载成功后在本线程内完成打包入库（ingest.create_book）。
    """

    event = pyqtSignal(object)

    def __init__(
        self, album_ids: list[str], python_cmd: list[str], db, parent=None
    ):
        super().__init__(parent)
        self.album_ids = list(album_ids)
        self.python_cmd = list(python_cmd)
        self.db = db
        self._proc: subprocess.Popen | None = None
        self._cancelled = False
        self._meta: dict[str, dict] = {}
        self.ok_ids: list[str] = []
        self.skipped_ids: list[str] = []
        self.failed: dict[str, str] = {}

    # ---- 对外：取消 ----

    def cancel(self):
        self._cancelled = True
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    # ---- 内部 ----

    def _extract_bridge(self) -> str:
        data = get_resources("bridge.py")  # noqa: F821 插件系统注入
        if not data:
            raise RuntimeError("插件包内找不到 bridge.py")
        fd, path = tempfile.mkstemp(prefix="jm2calibre_bridge_", suffix=".py")
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        return path

    def _work_dir(self, album_id: str) -> str:
        base = prefs["work_dir"] or os.path.join(
            tempfile.gettempdir(), "jmcomic2calibre"
        )
        return os.path.join(base, album_id)

    def _run_one(self, album_id: str, bridge_path: str) -> bool:
        out_dir = self._work_dir(album_id)
        keep = bool(prefs["keep_workdir"])
        cmd = list(self.python_cmd) + [
            bridge_path,
            "--album-id",
            album_id,
            "--out-dir",
            out_dir,
        ]
        proxy = prefs["proxy"]
        if proxy:
            cmd += ["--proxy", proxy]

        self.event.emit({"event": "album_start", "album_id": album_id})
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_CREATE_NO_WINDOW,
            )
        except OSError as exc:
            self.failed[album_id] = f"无法启动解释器: {exc}"
            return False

        downloaded_dir = None
        images = -1
        error_message = None
        log_tail: list[str] = []  # 失败诊断：保留 jmcomic 输出最后几行
        proc = self._proc
        for line in proc.stdout:  # type: ignore[union-attr]
            ev = parse_event_line(line)
            if ev is None:
                continue
            if ev["event"] == "meta":
                self._meta[album_id] = {
                    k: v for k, v in ev.items() if k not in ("event", "album_id")
                }
            elif ev["event"] == "downloaded":
                downloaded_dir, images = ev.get("dir"), ev.get("images", -1)
            elif ev["event"] == "error":
                error_message = ev.get("message", "未知错误")
            elif ev["event"] == "log":
                log_tail.append(ev.get("message", ""))
                if len(log_tail) > 30:
                    del log_tail[:-30]
            ev["album_id"] = album_id
            self.event.emit(ev)

        proc.wait()
        returncode = proc.returncode
        self._proc = None  # 进程已结束，取消不再需要引用；退出码已保存

        if self._cancelled:
            if not keep and downloaded_dir and os.path.isdir(downloaded_dir):
                shutil.rmtree(downloaded_dir, ignore_errors=True)
            self.failed[album_id] = "已取消"
            return False
        def fail_with_log(message: str) -> str:
            tail = [s for s in log_tail if s.strip()][-3:]
            return message + (
                "（日志尾部: " + " / ".join(tail) + "）" if tail else ""
            )

        if error_message is not None:
            self.failed[album_id] = fail_with_log(error_message)
            if not keep and os.path.isdir(out_dir):
                shutil.rmtree(out_dir, ignore_errors=True)
            return False
        if returncode != 0:
            self.failed[album_id] = fail_with_log(
                f"bridge 异常退出（码 {returncode}）"
            )
            return False

        # ---- 阶段 3：打包入库 ----
        meta = self._meta.get(album_id, {})
        self.event.emit(
            {
                "event": "ingesting",
                "album_id": album_id,
                "title": str(meta.get("title") or album_id),
            }
        )
        try:
            from calibre_plugins.jmcomic2calibre.ingest import create_book

            outcome = create_book(
                album_id,
                downloaded_dir or out_dir,
                meta,
                self.db,
                prefs["web_domain"],
            )
        except Exception as exc:
            self.failed[album_id] = f"入库失败: {exc}"
            return False

        if outcome["status"] == "skipped":
            self.skipped_ids.append(album_id)
            self.event.emit({"event": "skipped", "album_id": album_id, **outcome})
            if not keep and os.path.isdir(out_dir):
                shutil.rmtree(out_dir, ignore_errors=True)
            return True

        self.ok_ids.append(album_id)
        self.event.emit({"event": "ingested", "album_id": album_id, **outcome})
        if not keep and os.path.isdir(out_dir):
            shutil.rmtree(out_dir, ignore_errors=True)
        return True

    def run(self):
        bridge_path = None
        try:
            bridge_path = self._extract_bridge()
        except Exception as exc:
            self.event.emit({"event": "error", "message": str(exc)})
            self.event.emit({"event": "all_done"})
            return
        try:
            for album_id in self.album_ids:
                if self._cancelled:
                    break
                self._run_one(album_id, bridge_path)
        finally:
            if bridge_path:
                try:
                    os.unlink(bridge_path)
                except OSError:
                    pass
        self.event.emit(
            {
                "event": "all_done",
                "ok": self.ok_ids,
                "skipped": self.skipped_ids,
                "failed": dict(self.failed),
            }
        )
