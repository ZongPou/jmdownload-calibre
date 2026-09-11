"""jmcal 命令行入口。"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .library import find_calibredb
from .pipeline import import_album


def cmd_doctor(args) -> int:
    """检查运行环境，缺什么直接说清楚。"""
    ok = True

    calibredb = find_calibredb()
    if calibredb:
        print(f"✅ calibredb: {calibredb}")
    else:
        print("❌ 没找到 calibredb —— 装好 Calibre 并把它加进 PATH")
        ok = False

    try:
        import img2pdf  # noqa: F401

        print("✅ img2pdf（PDF 转换可用）")
    except ImportError:
        print("⚠️ 没有 img2pdf —— 转 PDF 会失败，pip install jmcomic-calibre[pdf]")

    try:
        import jmcomic  # noqa: F401

        print("✅ jmcomic（下载可用）")
    except ImportError:
        print("❌ 没有 jmcomic —— 无法下载本子")
        ok = False

    print("\n一切正常。" if ok else "\n还有问题没解决，见上面 ❌ 的项。")
    return 0 if ok else 1


def cmd_add(args) -> int:
    summary = import_album(
        args.album_id,
        library=args.library,
        fmt=args.fmt,
        option_path=args.option_path,
        work_dir=args.work_dir,
        keep_workdir=args.keep_workdir,
        dry_run=args.dry_run,
    )

    print(f"📖 {summary['title']}（{summary['pages']} 页）")
    print(f"   文件: {summary['book']}")
    print(f"   元数据: {summary['opf']}")

    if args.dry_run:
        print("🧪 dry-run：没有写进书库")
    elif summary["book_ids"]:
        print(f"✅ 已导入 Calibre，book id: {', '.join(summary['book_ids'])}")
    else:
        print("⚠️ calibredb 没报告新增 id，可能被当成重复本子跳过了")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jmcal",
        description="把 JMComic 本子下载、转格式、写元数据并导入 Calibre 书库",
    )
    parser.add_argument("--version", action="version", version=f"jmcal {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="检查运行环境")
    doctor.set_defaults(func=cmd_doctor)

    add = sub.add_parser("add", help="下载一个本子并导入 Calibre")
    add.add_argument("album_id", help="本子 id")
    add.add_argument("--library", help="Calibre 书库路径，不填就用默认书库")
    add.add_argument("--format", dest="fmt", default="pdf", choices=["pdf", "cbz"],
                     help="导入格式，默认 pdf")
    add.add_argument("--option", dest="option_path", help="jmcomic 的 option.yml 路径")
    add.add_argument("--work-dir", help="临时工作目录")
    add.add_argument("--keep-workdir", action="store_true", help="保留临时文件，方便排查")
    add.add_argument("--dry-run", action="store_true", help="只下载和转换，不写进书库")
    add.set_defaults(func=cmd_add)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI 兜底，把错误讲清楚就够
        print(f"❌ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
