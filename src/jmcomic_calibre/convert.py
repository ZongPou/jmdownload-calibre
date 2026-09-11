"""把下载好的图片目录转成 PDF / CBZ。"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def _natural_key(path: Path):
    """按数字顺序排页，避免 10.jpg 排在 2.jpg 前面。"""
    parts = re.split(r"(\d+)", str(path).lower())
    return [int(part) if part.isdigit() else part for part in parts]


def collect_images(folder: Path) -> list[Path]:
    """递归收集目录下的图片，按自然顺序返回。"""
    folder = Path(folder)
    files = [
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(files, key=_natural_key)


def images_to_pdf(images: list[Path], output: Path) -> Path:
    try:
        import img2pdf
    except ImportError as exc:  # pragma: no cover - 取决于环境
        raise RuntimeError("转 PDF 需要 img2pdf，先 pip install jmcomic-calibre[pdf]") from exc

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "wb") as handle:
        handle.write(img2pdf.convert([str(p) for p in images]))
    return output


def images_to_cbz(images: list[Path], output: Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for image in images:
            archive.write(image, arcname=image.name)
    return output


def convert(images: list[Path], output: Path) -> Path:
    """按输出后缀选格式。"""
    output = Path(output)
    suffix = output.suffix.lower()
    if not images:
        raise ValueError("没有可转换的图片")
    if suffix == ".pdf":
        return images_to_pdf(images, output)
    if suffix in (".cbz", ".zip"):
        return images_to_cbz(images, output)
    raise ValueError(f"不支持的输出格式: {output.suffix}（只支持 .pdf / .cbz / .zip）")
