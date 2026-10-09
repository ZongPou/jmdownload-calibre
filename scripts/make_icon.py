"""将选定的第二套原始设计稿无损复制为插件图标。

依赖 Pillow（系统 Python 已装）。改图标时重跑：
python scripts/make_icon.py
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "design" / "icon-concepts" / "jmcomic-calibre-option-b-archive.png"
OUT = Path(__file__).resolve().parent.parent / "calibre_plugin" / "images" / "icon.png"


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # 保留原始 PNG 的分辨率与透明通道，交给 Calibre/Qt 在显示时缩放。
    OUT.write_bytes(SOURCE.read_bytes())
    print(f"已生成 {OUT}")


if __name__ == "__main__":
    main()
