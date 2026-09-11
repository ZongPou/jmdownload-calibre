"""metadata.opf 生成的测试。"""

import unittest

from jmcomic_calibre.convert import collect_images, convert
from jmcomic_calibre.metadata import DUBLIN_CORE_ELEMENTS, AlbumMeta, build_opf


class TestBuildOpf(unittest.TestCase):
    def test_escapes_special_characters(self):
        meta = AlbumMeta(album_id="1", title='A <b>&"B"', tags=["tag & more"])
        xml = build_opf(meta)
        self.assertIn("&lt;b&gt;", xml)
        self.assertIn("&amp;", xml)
        self.assertNotIn("<b>", xml)

    def test_each_tag_becomes_a_subject(self):
        meta = AlbumMeta(album_id="1", title="t", tags=["tag-a", "tag-b"])
        xml = build_opf(meta)
        self.assertEqual(2, xml.count("<dc:subject>"))
        self.assertIn("<dc:subject>tag-a</dc:subject>", xml)

    def test_default_author_and_identifier(self):
        xml = build_opf(AlbumMeta(album_id="42", title="无作者本子"))
        self.assertIn("jmcomic:42", xml)
        self.assertIn("JMComic", xml)

    def test_explicit_identifier_wins(self):
        meta = AlbumMeta(album_id="42", title="t", identifier="custom:1")
        self.assertIn("custom:1", build_opf(meta))

    def test_invalid_extra_key_is_ignored(self):
        meta = AlbumMeta(album_id="1", title="t", extra={"series index": "1", "language": "zh"})
        xml = build_opf(meta)
        self.assertNotIn("series index", xml)
        self.assertIn("<dc:language>zh</dc:language>", xml)

    def test_series_uses_calibre_meta_tags(self):
        meta = AlbumMeta(album_id="1", title="t", series="某系列", series_index="3")
        xml = build_opf(meta)
        self.assertIn('name="calibre:series"', xml)
        self.assertIn('name="calibre:series_index"', xml)

    def test_dublin_core_whitelist_size(self):
        self.assertEqual(15, len(DUBLIN_CORE_ELEMENTS))


class TestConvert(unittest.TestCase):
    def test_images_are_sorted_naturally(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("10.jpg", "2.jpg", "1.jpg"):
                (root / name).write_bytes(b"x")

            names = [p.name for p in collect_images(root)]

        self.assertEqual(["1.jpg", "2.jpg", "10.jpg"], names)

    def test_cbz_roundtrip(self):
        import tempfile
        import zipfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = []
            for name in ("1.jpg", "2.jpg"):
                path = root / name
                path.write_bytes(b"data")
                images.append(path)

            out = convert(images, root / "book.cbz")
            with zipfile.ZipFile(out) as archive:
                self.assertEqual(["1.jpg", "2.jpg"], archive.namelist())

    def test_unknown_format_is_rejected(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "1.jpg"
            image.write_bytes(b"x")
            with self.assertRaises(ValueError):
                convert([image], root / "book.txt")


if __name__ == "__main__":
    unittest.main()
