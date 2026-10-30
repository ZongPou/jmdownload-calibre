"""插件骨架离线单测：只测纯标准库逻辑（common.py / build_plugin.py）。

不 import calibre / Qt，系统 Python 直接可跑：
    python -m unittest tests.test_plugin -v
"""

import os
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

# ---- 离线 stub：无 calibre 的机器上，给 calibre_plugin 包一个可导入的基类 ----
# 产品代码保持官方插件结构；stub 只存在于测试进程。
try:
    import calibre  # noqa: F401
except ImportError:
    _fake_calibre = types.ModuleType("calibre")
    _fake_customize = types.ModuleType("calibre.customize")

    class _InterfaceActionBase:  # 占位基类
        pass

    _fake_customize.InterfaceActionBase = _InterfaceActionBase
    _fake_calibre.customize = _fake_customize
    sys.modules.setdefault("calibre", _fake_calibre)
    sys.modules.setdefault("calibre.customize", _fake_customize)

from build_plugin import build, collect_files, read_version
from calibre_plugin.bridge import parse_args
from calibre_plugin.common import (
    DEFAULTS,
    describe_probe,
    doctor,
    parse_album_ids,
    parse_event_line,
    parse_probe_output,
    probe_interpreter,
    python_candidates,
)
from calibre_plugin.packaging import (
    build_comicinfo_xml,
    build_web_url,
    collect_images,
    pack_cbz,
    parse_published,
    sanitize_filename,
)

ROOT = Path(__file__).resolve().parent.parent


class TestDownloadConcurrency(unittest.TestCase):
    def test_real_downloader_reuses_preloaded_details_offline(self):
        import jmcomic
        import json
        import contextlib
        import io
        from calibre_plugin.bridge import album_snapshot, fetch_meta_and_download
        album = jmcomic.JmAlbumDetail("123", "0", "测试", [("900", "1", "一"), ("300", "2", "二")],
            4, "", "", "0", "0", 0, [], [], [], [])
        option = jmcomic.JmOption.default()
        photo_calls = []
        def get_photo(photo_id, **kwargs):
            photo_calls.append((photo_id, kwargs))
            return jmcomic.JmPhotoDetail(photo_id, "章节", "123", "1" if photo_id == "900" else "2",
                scramble_id="0", page_arr=["00001.webp", "00002.webp"], data_original_domain="offline.invalid")
        client = types.SimpleNamespace(get_photo_detail=get_photo, get_album_detail=Mock(side_effect=AssertionError("不应请求漫画详情")))
        client.check_photo = lambda photo: jmcomic.JmApiClient.check_photo(client, photo)
        option.build_jm_client = Mock(return_value=client)
        def image_download(downloader, image):
            path = Path(downloader.option.decide_image_filepath(image))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"offline image")
            image.save_path = str(path)
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            cache = Path(tmp) / "album.json"
            cache.write_text(json.dumps(album_snapshot(album)), encoding="utf-8")
            with patch.object(jmcomic.JmOption, "default", return_value=option), patch.object(
                jmcomic.JmDownloader, "download_by_image_detail", image_download), patch("calibre_plugin.bridge.emit") as emit:
                fetch_meta_and_download("123", tmp, "", chapter_ids=["900", "300"], album_cache=str(cache))
            self.assertEqual(4, len(collect_images(tmp)))
            self.assertEqual([("900", {"fetch_album": False}), ("300", {"fetch_album": False})], photo_calls)
            self.assertEqual(4, emit.call_args_list[-1].args[0]["images"])

    def test_large_album_is_bounded_and_failure_never_reports_downloaded(self):
        from calibre_plugin.bridge import fetch_meta_and_download

        option = types.SimpleNamespace(
            dir_rule=types.SimpleNamespace(base_dir=""),
            download=types.SimpleNamespace(threading=types.SimpleNamespace(
                photo=32, image=30)),
            build_jm_client=Mock(return_value=types.SimpleNamespace(
                get_album_detail=Mock(return_value=types.SimpleNamespace(
                    page_count=5000)))),
        )

        def download(album_id, actual_option):
            self.assertEqual("364522", album_id)
            self.assertEqual(1, actual_option.download.threading.photo)
            self.assertEqual(16, actual_option.download.threading.image)
            raise RuntimeError("部分下载失败")

        fake = types.SimpleNamespace(
            JmOption=types.SimpleNamespace(default=lambda: option),
            download_album=download,
        )
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            sys.modules, {"jmcomic": fake}
        ), patch("calibre_plugin.bridge.emit") as emit:
            with self.assertRaisesRegex(RuntimeError, "部分下载失败"):
                fetch_meta_and_download("364522", tmp, "")
            self.assertFalse(any(
                call.args[0]["event"] == "downloaded"
                for call in emit.call_args_list
            ))


class TestParseAlbumIds(unittest.TestCase):
    def test_bare_ids(self):
        ids, errors = parse_album_ids("350234\n123456")
        self.assertEqual(["350234", "123456"], ids)
        self.assertEqual([], errors)

    def test_ids_with_spaces(self):
        ids, errors = parse_album_ids("  350234  \n\t123\t")
        self.assertEqual(["350234", "123"], ids)
        self.assertEqual([], errors)

    def test_album_urls(self):
        line = "https://18comic.vip/album/350234/"
        ids, errors = parse_album_ids(line)
        self.assertEqual(["350234"], ids)
        self.assertEqual([], errors)

    def test_url_without_slashes(self):
        ids, _ = parse_album_ids("18comic.vip/album/999?id=1")
        self.assertEqual(["999"], ids)

    def test_mixed_and_comments_and_blank(self):
        text = "# 下载清单\n350234\n\nhttps://18comic.org/album/111/\n垃圾行"
        ids, errors = parse_album_ids(text)
        self.assertEqual(["350234", "111"], ids)
        self.assertEqual(["垃圾行"], errors)

    def test_dedup_keeps_order(self):
        ids, _ = parse_album_ids("350234\nhttps://x.com/album/350234/\n350235")
        self.assertEqual(["350234", "350235"], ids)

    def test_empty_input(self):
        self.assertEqual(([], []), parse_album_ids(""))
        self.assertEqual(([], []), parse_album_ids(None))

    def test_single_digit_is_error(self):
        ids, errors = parse_album_ids("7")
        self.assertEqual([], ids)
        self.assertEqual(["7"], errors)


class TestChapterSelection(unittest.TestCase):
    def test_range_and_mixed_separators(self):
        from calibre_plugin.common import parse_chapter_range
        self.assertEqual([1, 2, 3, 5, 7, 8], parse_chapter_range("1-3、5，7-8,2", 8))

    def test_invalid_range_never_silently_downloads_all(self):
        from calibre_plugin.common import parse_chapter_range
        for text in ("", "0", "1-9", "5-2", "1-3,x", "-1", "1--2", "1.5"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_chapter_range(text, 8)

    def test_partial_identifier_stable_and_full_keeps_original(self):
        from calibre_plugin.common import selection_key, chapter_label
        chapters = [{"id": str(i)} for i in range(1, 5)]
        self.assertEqual("123", selection_key("123", chapters, ["4", "3", "2", "1"]))
        self.assertEqual(selection_key("123", chapters, ["1", "3"]), selection_key("123", chapters, ["3", "1"]))
        self.assertNotEqual(selection_key("123", chapters, ["1"]), selection_key("123", chapters, ["3"]))
        self.assertEqual("1-3、5、7-8", chapter_label([1, 2, 3, 5, 7, 8]))

    def _fake_jm(self):
        album = types.SimpleNamespace(name="多集漫画", page_count=6,
            episode_list=[("900", "1", "一"), ("100", "2", "二"), ("300", "3", "三")])
        class Photo:
            def __init__(self, photo_id):
                self.photo_id = photo_id
            def __len__(self):
                return 2
        client = types.SimpleNamespace(get_album_detail=Mock(return_value=album),
            get_photo_detail=Mock(side_effect=lambda photo_id, **kwargs: Photo(photo_id)), download_album_cover=Mock())
        option = types.SimpleNamespace(dir_rule=types.SimpleNamespace(base_dir=""),
            download=types.SimpleNamespace(threading=types.SimpleNamespace(photo=30, image=30)),
            build_jm_client=lambda: client)
        fake = types.SimpleNamespace(JmOption=types.SimpleNamespace(default=lambda: option),
                                     download_album=Mock())
        def download_photo(photo):
            photo_id = photo.photo_id
            self.assertEqual(1, option.download.threading.photo)
            self.assertEqual(16, option.download.threading.image)
            self.assertIsNotNone(photo.from_album)
            folder = Path(option.dir_rule.base_dir) / photo_id
            folder.mkdir()
            (folder / "1.jpg").write_bytes(photo_id.encode())
            (folder / "2.jpg").write_bytes(photo_id.encode())
        fake.download_photo = Mock()
        fake.downloader = types.SimpleNamespace(download_by_photo_detail=Mock(side_effect=download_photo),
            raise_if_has_exception=Mock(), begin_manifest=Mock(), finish_manifest=Mock())
        fake.JmDownloader = Mock(return_value=fake.downloader)
        return fake, client

    def test_selected_only_in_episode_order_unique_page_names_and_progress(self):
        from calibre_plugin.bridge import fetch_meta_and_download
        fake, _ = self._fake_jm()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"jmcomic": fake}), patch("calibre_plugin.bridge.emit") as emit:
            fetch_meta_and_download("123", tmp, "", chapter_ids=["300", "900"])
            self.assertEqual(["900", "300"], [c.args[0].photo_id for c in fake.downloader.download_by_photo_detail.call_args_list])
            fake.download_album.assert_not_called()
            images = collect_images(tmp)
            self.assertEqual([b"900", b"900", b"300", b"300"], [Path(p).read_bytes() for p in images])
            events = [c.args[0] for c in emit.call_args_list]
            self.assertEqual(0, next(e for e in events if e["event"] == "meta")["total_images"])
            page_events = [e for e in events if e["event"] == "pages_known"]
            self.assertEqual([0, 4], [e["total"] for e in page_events])
            self.assertEqual(4, next(e for e in events if e["event"] == "downloaded")["images"])
            archive = Path(tmp) / "test.cbz"
            pack_cbz(images, "<ComicInfo/>", str(archive))
            with zipfile.ZipFile(archive) as zf:
                self.assertEqual(len(zf.namelist()), len(set(zf.namelist())))

    def test_full_selection_still_sequential_and_original_page_count(self):
        from calibre_plugin.bridge import fetch_meta_and_download
        fake, _ = self._fake_jm()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"jmcomic": fake}), patch("calibre_plugin.bridge.emit") as emit:
            fetch_meta_and_download("123", tmp, "", chapter_ids=["900", "100", "300"])
            self.assertEqual(3, fake.downloader.download_by_photo_detail.call_count)
            self.assertEqual(6, emit.call_args_list[0].args[0]["total_images"])

    def test_changed_chapters_fail_before_download(self):
        from calibre_plugin.bridge import fetch_meta_and_download
        fake, _ = self._fake_jm()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"jmcomic": fake}):
            with self.assertRaisesRegex(ValueError, "章节列表已变化"):
                fetch_meta_and_download("123", tmp, "", chapter_ids=["999"])
            fake.download_photo.assert_not_called()

    def test_preview_cover_failure_does_not_block_chapter_selection(self):
        from calibre_plugin.bridge import fetch_meta_and_download
        fake, client = self._fake_jm()
        client.download_album_cover.side_effect = RuntimeError("离线封面失败")
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"jmcomic": fake}), patch("calibre_plugin.bridge.emit") as emit:
            fetch_meta_and_download("123", tmp, "", True, cover_path=os.path.join(tmp, "cover.jpg"))
            self.assertEqual(3, emit.call_args_list[0].args[0]["chapters"].__len__())
            fake.download_photo.assert_not_called()
            fake.download_album.assert_not_called()

    def test_first_chapter_downloads_before_second_detail_is_requested(self):
        from calibre_plugin.bridge import fetch_meta_and_download
        fake, client = self._fake_jm()
        order = []
        get_photo = client.get_photo_detail.side_effect
        download = fake.downloader.download_by_photo_detail.side_effect
        def get(photo_id, **kwargs):
            self.assertEqual({"fetch_album": False}, kwargs)
            order.append("get:" + photo_id)
            return get_photo(photo_id)
        def save(photo):
            order.append("download:" + photo.photo_id)
            download(photo)
        client.get_photo_detail.side_effect = get
        fake.downloader.download_by_photo_detail.side_effect = save
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"jmcomic": fake}), patch("calibre_plugin.bridge.emit"):
            fetch_meta_and_download("123", tmp, "", chapter_ids=["900", "300"])
        self.assertEqual(["get:900", "download:900", "get:300", "download:300"], order)
        client.get_album_detail.assert_called_once_with("123")
        fake.JmDownloader.assert_called_once()

    def test_reuses_preview_album_without_album_request(self):
        import json
        from calibre_plugin.bridge import fetch_meta_and_download, ALBUM_FIELDS
        fake, client = self._fake_jm()
        fields = {name: "" for name in ALBUM_FIELDS}
        fields.update(album_id="123", name="缓存漫画", page_count=6,
                      episode_list=[("900", "1", "一"), ("100", "2", "二"), ("300", "3", "三")])
        fake.JmAlbumDetail = lambda **kwargs: types.SimpleNamespace(**kwargs)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"jmcomic": fake}), patch("calibre_plugin.bridge.emit"):
            cache = Path(tmp) / "album.json"
            cache.write_text(json.dumps(fields), encoding="utf-8")
            fetch_meta_and_download("123", tmp, "", chapter_ids=["900"], album_cache=str(cache))
        client.get_album_detail.assert_not_called()
        self.assertEqual("缓存漫画", fake.downloader.download_by_photo_detail.call_args.args[0].from_album.name)

    def test_detail_download_failure_never_reports_success(self):
        from calibre_plugin.bridge import fetch_meta_and_download
        fake, _ = self._fake_jm()
        fake.downloader.raise_if_has_exception.side_effect = RuntimeError("图片失败")
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"jmcomic": fake}), patch("calibre_plugin.bridge.emit") as emit:
            with self.assertRaisesRegex(RuntimeError, "图片失败"):
                fetch_meta_and_download("123", tmp, "", chapter_ids=["900", "300"])
            self.assertFalse(any(c.args[0]["event"] == "downloaded" for c in emit.call_args_list))
            fake.downloader.finish_manifest.assert_called_once()


class TestPythonCandidates(unittest.TestCase):
    def test_custom_path_first(self):
        def which(name):
            return "C:/Program Files/Python313/python.exe" if name == "python" else None

        result = python_candidates("D:/venv/python.exe", which=which)
        self.assertEqual(["D:/venv/python.exe"], result[0])
        self.assertEqual(
            ["C:/Program Files/Python313/python.exe"], result[1]
        )

    def test_windowsapps_stub_filtered(self):
        def which(name):
            if name == "python":
                return "C:/Users/x/AppData/Local/Microsoft/WindowsApps/python.exe"
            if name == "py":
                return "C:/Windows/py.exe"
            return None

        result = python_candidates(which=which)
        # 存根被过滤、py 启动器兜底
        self.assertEqual([["py", "-3"]], result)

    def test_no_python_at_all(self):
        result = python_candidates(which=lambda name: None)
        self.assertEqual([], result)

    def test_dedup(self):
        def which(name):
            return "C:/Python/python.exe" if name == "python" else None

        result = python_candidates(which=which)
        self.assertEqual(1, len(result))


class TestProbeParsing(unittest.TestCase):
    def test_ok_output(self):
        stdout = '某警告行\n{"python": "3.13.13", "jmcomic": "2.7.8"}\n'
        result = parse_probe_output(stdout, 0, ["python"])
        self.assertTrue(result["ok"])
        self.assertEqual("3.13.13", result["python"])
        self.assertEqual("2.7.8", result["jmcomic"])

    def test_import_failure(self):
        stdout = '{"python": "3.13.13", "error": "ModuleNotFoundError()"}'
        result = parse_probe_output(stdout, 0, ["python"])
        self.assertFalse(result["ok"])
        self.assertIn("ModuleNotFoundError", result["error"])

    def test_no_json(self):
        result = parse_probe_output("这不是 python 输出", 1, ["python"])
        self.assertFalse(result["ok"])
        self.assertIn("无有效输出", result["error"])

    def test_last_json_wins(self):
        stdout = '{"python": "3.0"}\n{"python": "3.13.13", "jmcomic": "2.7.8"}'
        result = parse_probe_output(stdout, 0, ["python"])
        self.assertEqual("3.13.13", result["python"])


class TestDoctor(unittest.TestCase):
    def test_returns_first_working(self):
        calls = []

        def probe(cmd, timeout=None):
            calls.append(cmd)
            if cmd == ["second"]:
                return {"ok": True, "cmd": cmd, "python": "3.13.13",
                        "jmcomic": "2.7.8"}
            return {"ok": False, "cmd": cmd, "error": "nope"}

        result = doctor(
            which=lambda name: {"python": "second", "py": "py"}.get(name),
            probe=probe,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(["second"], calls[0])

    def test_returns_last_failure_when_all_fail(self):
        def probe(cmd, timeout=None):
            return {"ok": False, "cmd": cmd, "error": "nope"}

        result = doctor(which=lambda name: "python" if name == "python" else None,
                        probe=probe)
        self.assertFalse(result["ok"])

    def test_no_interpreter_found(self):
        result = doctor(which=lambda name: None, probe=lambda cmd: {})
        self.assertFalse(result["ok"])
        self.assertIn("未找到", result["error"])


class TestDescribeProbe(unittest.TestCase):
    def test_ok_text(self):
        text = describe_probe(
            {"ok": True, "cmd": ["python"], "python": "3.13.13",
             "jmcomic": "2.7.8"}
        )
        self.assertIn("OK", text)
        self.assertIn("2.7.8", text)

    def test_fail_text(self):
        text = describe_probe({"ok": False, "error": "超时", "cmd": None})
        self.assertIn("异常", text)
        self.assertIn("超时", text)

    def test_empty(self):
        self.assertIn("未检测", describe_probe(None))


class TestRealProbe(unittest.TestCase):
    """冒烟测试：本机真实环境应能通过（需要系统 Python 装了 jmcomic）。"""

    def test_local_python_has_jmcomic(self):
        result = probe_interpreter(["python"])
        self.assertTrue(result.get("ok"), f"本机探测失败: {result}")
        self.assertTrue(result.get("jmcomic"))


class TestConfigDefaults(unittest.TestCase):
    def test_expected_keys_exist(self):
        for key in ("python_path", "web_domain", "proxy", "output_format",
                    "check_duplicates", "keep_workdir", "work_dir",
                    "download_timeout"):
            self.assertIn(key, DEFAULTS)


class TestBuildPlugin(unittest.TestCase):
    def test_read_version(self):
        self.assertEqual("0.3.1", read_version())

    def test_collect_files_excludes_cache(self):
        names = {f.name for f in collect_files()}
        self.assertIn("__init__.py", names)
        self.assertIn("plugin-import-name-jmcomic2calibre.txt", names)
        self.assertIn("bridge.py", names)
        self.assertIn("worker.py", names)
        self.assertNotIn("common.pyc", names)

    def test_build_zip_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = build(tmp)
            self.assertTrue(Path(out).exists())
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
            self.assertIn("__init__.py", names)
            self.assertIn("plugin-import-name-jmcomic2calibre.txt", names)
            self.assertIn("images/icon.png", names)
            self.assertIn("bridge.py", names)
            self.assertTrue(all(not n.startswith("__pycache__") for n in names))


class TestBridgeArgs(unittest.TestCase):
    def test_minimal(self):
        args = parse_args(["--album-id", "350234", "--out-dir", "D:/tmp/x"])
        self.assertEqual("350234", args.album_id)
        self.assertEqual("D:/tmp/x", args.out_dir)
        self.assertEqual("", args.proxy)

    def test_with_proxy(self):
        args = parse_args(
            ["--album-id", "1", "--out-dir", "x", "--proxy", "http://127.0.0.1:7890"]
        )
        self.assertEqual("http://127.0.0.1:7890", args.proxy)

    def test_missing_required(self):
        with self.assertRaises(SystemExit):
            parse_args(["--album-id", "1"])


class TestParseEventLine(unittest.TestCase):
    def test_valid_events(self):
        ev = parse_event_line('{"event": "progress", "images": 5}')
        self.assertEqual({"event": "progress", "images": 5}, ev)

    def test_meta_with_unicode(self):
        ev = parse_event_line('{"event": "meta", "title": "某本子"}')
        self.assertEqual("某本子", ev["title"])

    def test_noise_becomes_log(self):
        ev = parse_event_line("JMComic INFO: downloading page 3")
        self.assertEqual("log", ev["event"])
        self.assertIn("downloading", ev["message"])

    def test_blank_line(self):
        self.assertIsNone(parse_event_line("   "))

    def test_broken_json_becomes_log(self):
        ev = parse_event_line('{"event": "meta", "title": ')
        self.assertEqual("log", ev["event"])

    def test_json_without_event_becomes_log(self):
        ev = parse_event_line('{"foo": 1}')
        self.assertEqual("log", ev["event"])

    def test_non_dict_json_becomes_log(self):
        ev = parse_event_line("[1, 2, 3]")
        self.assertEqual("log", ev["event"])


class TestPackaging(unittest.TestCase):
    def test_build_web_url(self):
        self.assertEqual(
            "https://18comic.vip/album/350234/",
            build_web_url("https://18comic.vip/", "350234"),
        )
        self.assertEqual(
            "https://18comic.vip/album/1/",
            build_web_url(None, "1"),
        )

    def test_parse_published_formats(self):
        from datetime import datetime

        self.assertEqual(datetime(2024, 1, 15), parse_published("2024-01-15"))
        self.assertEqual(datetime(2024, 1, 15), parse_published("2024/1/15"))
        self.assertEqual(
            datetime(2024, 1, 15, 10, 30, 0),
            parse_published("2024-01-15 10:30:00"),
        )
        self.assertEqual(datetime(2024, 1, 5), parse_published("2024年1月5日"))
        self.assertIsNone(parse_published("未知格式"))
        self.assertIsNone(parse_published(""))
        self.assertIsNone(parse_published(None))

    def test_sanitize_filename(self):
        self.assertEqual("标题_A_B_", sanitize_filename("标题:A/B?", "1"))
        self.assertEqual("1", sanitize_filename("", "1"))
        self.assertEqual("1", sanitize_filename("  ", "1"))

    def test_comicinfo_fields(self):
        xml = build_comicinfo_xml(
            {
                "title": "测试本子 <I>",
                "authors": ["作者A", "作者B"],
                "tags": ["全彩", "中文"],
                "description": "简介 & 说明",
                "published": "2024-01-15",
            },
            "https://18comic.vip/album/350234/",
            200,
        )
        self.assertIn("<Series>测试本子 &lt;I&gt;</Series>", xml)
        self.assertIn("<Writer>作者A, 作者B</Writer>", xml)
        self.assertIn("<Summary>简介 &amp; 说明</Summary>", xml)
        self.assertIn("<Year>2024</Year>", xml)
        self.assertIn("<Month>1</Month>", xml)
        self.assertIn("<Day>15</Day>", xml)
        self.assertIn("<Genre>全彩, 中文</Genre>", xml)
        self.assertIn("<Tags>全彩, 中文</Tags>", xml)
        self.assertIn("<LanguageISO>zh</LanguageISO>", xml)
        self.assertIn("<Web>https://18comic.vip/album/350234/</Web>", xml)
        self.assertIn("<PageCount>200</PageCount>", xml)
        self.assertTrue(xml.startswith("<?xml"))

    def test_comicinfo_empty_meta(self):
        xml = build_comicinfo_xml({}, "https://x/album/1/", 0)
        self.assertNotIn("<Writer>", xml)
        self.assertNotIn("<Year>", xml)
        self.assertNotIn("<PageCount>", xml)

    def test_collect_images_natural_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("10.jpg", "2.jpg", "1.jpg", "note.txt"):
                open(os.path.join(tmp, name), "wb").close()
            subdir = os.path.join(tmp, "sub")
            os.mkdir(subdir)
            open(os.path.join(subdir, "3.png"), "wb").close()
            names = [os.path.basename(p) for p in collect_images(tmp)]
            self.assertEqual(["1.jpg", "2.jpg", "3.png", "10.jpg"], names)

    def test_pack_cbz_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("1.jpg", "2.jpg"):
                open(os.path.join(tmp, name), "wb").close()
            out = os.path.join(tmp, "out.cbz")
            pack_cbz(collect_images(tmp), "<ComicInfo/>", out)
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
            self.assertEqual("ComicInfo.xml", names[0])
            self.assertEqual(["ComicInfo.xml", "1.jpg", "2.jpg"], names)

    def test_pack_cbz_empty_raises(self):
        with self.assertRaises(ValueError):
            pack_cbz([], "<ComicInfo/>", os.path.join(tempfile.gettempdir(), "x.cbz"))


if __name__ == "__main__":
    unittest.main()
