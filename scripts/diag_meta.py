"""诊断脚本：只查一次专辑元数据（不下载图片），打印真实异常。

用法：python scripts/diag_meta.py [album_id]
"""

import sys
import traceback

ALBUM_ID = sys.argv[1] if len(sys.argv) > 1 else "350234"


def main():
    try:
        import jmcomic

        print("jmcomic version:", jmcomic.__version__)
        option = jmcomic.JmOption.default()
        client = option.new_jm_client()
        album = client.get_album_detail(ALBUM_ID)
        print("META_OK, title length:", len(str(getattr(album, "name", ""))))
    except Exception as exc:
        print("META_FAILED:", repr(exc))
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
