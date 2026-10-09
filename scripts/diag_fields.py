"""诊断脚本：打印 JmAlbumDetail 的公开属性（不下载图片），定位总页数字段。

用法：python scripts/diag_fields.py [album_id]
"""

import sys

ALBUM_ID = sys.argv[1] if len(sys.argv) > 1 else "350234"


def main():
    import jmcomic

    option = jmcomic.JmOption.default()
    client = option.new_jm_client()
    album = client.get_album_detail(ALBUM_ID)
    attrs = [a for a in dir(album) if not a.startswith("_")]
    print("ALBUM_ATTRS:", attrs)
    # 打印候选总页数字段的值
    for name in (
        "page_count", "total_page", "pages", "images_count",
        "length", "photo_count", "page_arr", "series",
    ):
        value = getattr(album, name, "<缺失>")
        if isinstance(value, (list, tuple)) and len(str(value)) > 80:
            value = f"<list len={len(value)}>"
        print(f"  {name} = {value!r}")


if __name__ == "__main__":
    main()
