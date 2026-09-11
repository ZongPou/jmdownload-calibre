"""export_opf 的测试：锁定 jmcomic 插件迁移过来后 OPF 输出不变形。"""

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from jmcomic_calibre import DUBLIN_CORE_ELEMENTS, export_opf

NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": "http://www.idpf.org/2007/opf",
}


class FakeAlbum:
    """模仿 jmcomic 的 JmAlbumDetail：title 取 name，author 空时回落默认值。"""

    def __init__(self, **kw):
        self.id = kw.get("id", "123456")
        self.name = kw.get("name", "标题")
        self.authors = kw.get("authors", [])
        self.tags = kw.get("tags", [])
        self.description = kw.get("description", "")
        self.pub_date = kw.get("pub_date", "")

    @property
    def title(self):
        return self.name

    @property
    def author(self):
        return self.authors[0] if self.authors else "default_author"


def parse(path):
    return ET.parse(path).getroot()


class TestExportOpf(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_core_fields_and_escaping(self):
        album = FakeAlbum(
            name='测试<本子>名 & 特殊"字符"',
            authors=["作者甲"],
            tags=["tag1", "中文标签"],
            description="简介 <b>含XML特殊字符</b>",
        )
        opf = export_opf(album, self.root / "Bd" / "123456" / "metadata.opf")

        root = parse(opf)
        self.assertEqual(root.find(".//dc:title", NS).text, album.title)
        self.assertEqual(root.find(".//dc:creator", NS).text, "作者甲")
        self.assertEqual(
            [e.text for e in root.findall(".//dc:subject", NS)], ["tag1", "中文标签"]
        )
        self.assertEqual(root.find(".//dc:identifier", NS).text, "jmcomic:123456")
        self.assertEqual(
            root.find(".//dc:description", NS).text, "简介 <b>含XML特殊字符</b>"
        )

    def test_identifier_scheme_defaults_to_jmcomic(self):
        opf = export_opf(FakeAlbum(), self.root / "metadata.opf")
        identifier = parse(opf).find(".//dc:identifier", NS)
        self.assertEqual(identifier.get("{http://www.idpf.org/2007/opf}scheme"), "JMCOMIC")

    def test_fields_added_and_invalid_key_ignored(self):
        album = FakeAlbum()
        ignored = []
        export_opf(
            album,
            self.root / "metadata.opf",
            fields={"language": "zh", "series index": "1"},
            on_ignored=lambda key, allowed: ignored.append((key, allowed)),
        )

        root = parse(self.root / "metadata.opf")
        self.assertEqual(root.find(".//dc:language", NS).text, "zh")
        self.assertIsNone(root.find(".//{series index}"))
        self.assertEqual(len(ignored), 1)
        self.assertEqual(ignored[0][0], "series index")
        self.assertIn("language", ignored[0][1])

    def test_author_falls_back_to_album_author(self):
        album = FakeAlbum(id="654321", name="无作者本子", authors=[])
        export_opf(album, self.root / "metadata.opf")

        root = parse(self.root / "metadata.opf")
        # 与 jmcomic 的 JmModuleConfig.DEFAULT_AUTHOR 保持一致，而不是库自己的 JMComic
        self.assertEqual(root.find(".//dc:creator", NS).text, "default_author")

    def test_fields_can_override_title_and_author(self):
        album = FakeAlbum(authors=["原作者"])
        export_opf(
            album,
            self.root / "metadata.opf",
            fields={"title": "覆盖标题", "author": "覆盖作者"},
        )

        root = parse(self.root / "metadata.opf")
        self.assertEqual(root.find(".//dc:title", NS).text, "覆盖标题")
        self.assertEqual(root.find(".//dc:creator", NS).text, "覆盖作者")

    def test_include_cover_writes_manifest_and_calls_downloader(self):
        album = FakeAlbum()
        seen = []

        def download_cover(cover_path):
            seen.append(cover_path)
            Path(cover_path).write_bytes(b"jpeg")

        export_opf(
            album,
            self.root / "123456" / "metadata.opf",
            include_cover=True,
            download_cover=download_cover,
        )

        self.assertEqual(seen, [str(self.root / "123456" / "cover.jpg")])
        root = parse(self.root / "123456" / "metadata.opf")
        manifest = root.find(".//{*}manifest")
        self.assertIsNotNone(manifest)
        self.assertEqual(
            manifest.find("{*}item").get("href"), "cover.jpg"
        )

    def test_no_manifest_without_cover(self):
        export_opf(FakeAlbum(), self.root / "metadata.opf")
        root = parse(self.root / "metadata.opf")
        self.assertIsNone(root.find(".//{*}manifest"))
        self.assertIsNone(root.find('.//{*}meta[@name="cover"]'))

    def test_no_date_element_by_default(self):
        album = FakeAlbum(pub_date="2026-01-01")
        export_opf(album, self.root / "metadata.opf")
        # 插件的既有行为不写 dc:date，这里保持一致
        self.assertIsNone(parse(self.root / "metadata.opf").find(".//dc:date", NS))

    def test_creates_parent_dirs_and_returns_path(self):
        target = self.root / "a" / "b" / "metadata.opf"
        returned = export_opf(FakeAlbum(), target)
        self.assertEqual(returned, str(target))
        self.assertTrue(target.is_file())

    def test_dublin_core_whitelist_is_shared(self):
        self.assertEqual(15, len(DUBLIN_CORE_ELEMENTS))


if __name__ == "__main__":
    unittest.main()
