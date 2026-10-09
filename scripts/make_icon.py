"""生成插件占位图标：48x48，紫底白字 JM。

依赖 Pillow（系统 Python 已装）。一次性脚本，产物提交进仓库，
改图标时重跑：python scripts/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "calibre_plugin" / "images" / "icon.png"
BG = (91, 60, 196, 255)        # 深紫
FG = (255, 255, 255, 255)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 圆角底板
    draw.rounded_rectangle([1, 1, 46, 46], radius=10, fill=BG)
    # 字：优先系统 Arial，失败用 Pillow 默认字体
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    text = "JM"
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((48 - (right - left)) / 2 - left, (48 - (bottom - top)) / 2 - top),
              text, fill=FG, font=font)
    img.save(OUT)
    print(f"已生成 {OUT}")


if __name__ == "__main__":
    main()
