"""把 calibre_plugin/ 打包成可安装的 Calibre 插件 zip。

纯标准库实现，任何 Python 3.9+ 均可运行，无需安装 Calibre：
    python build_plugin.py           # 输出 dist/jmdownload-calibre-v<version>.zip
    python build_plugin.py --outdir <目录>
安装：calibre → 首选项 → 插件 → 从文件加载插件，或命令行 calibre-customize -a <zip>
"""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLUGIN_DIR = ROOT / "calibre_plugin"
EXCLUDE_DIR_NAMES = {"__pycache__"}
EXCLUDE_SUFFIXES = {".pyc"}


def read_version(plugin_dir: Path = PLUGIN_DIR) -> str:
    """从 calibre_plugin/__init__.py 读取 version = (a, b, c) 并格式化为 a.b.c。"""
    text = (plugin_dir / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r"version\s*=\s*\(([^)]*)\)", text)
    if not match:
        raise SystemExit("错误：calibre_plugin/__init__.py 里找不到 version 元组")
    parts = [p.strip() for p in match.group(1).split(",") if p.strip()]
    if not parts:
        raise SystemExit("错误：version 元组为空")
    return ".".join(parts)


def collect_files(plugin_dir: Path = PLUGIN_DIR) -> list[Path]:
    """收集要打进 zip 的文件：顶层结构，排除缓存与构建产物。"""
    files = []
    for path in sorted(plugin_dir.rglob("*")):
        if not path.is_file():
            continue
        if EXCLUDE_DIR_NAMES & set(path.parts):
            continue
        if path.suffix.lower() in EXCLUDE_SUFFIXES:
            continue
        files.append(path)
    return files


def build(out_dir: str | Path | None = None, plugin_dir: Path = PLUGIN_DIR) -> Path:
    """打包并返回 zip 路径。__init__.py 必须位于 zip 顶层（calibre 硬性要求）。"""
    version = read_version(plugin_dir)
    dest = Path(out_dir) if out_dir else ROOT / "dist"
    dest.mkdir(parents=True, exist_ok=True)
    out_path = dest / f"jmdownload-calibre-v{version}.zip"

    files = collect_files(plugin_dir)
    top_names = {f.relative_to(plugin_dir).as_posix() for f in files}
    if "__init__.py" not in top_names:
        raise SystemExit("错误：__init__.py 不在插件目录顶层，插件将无法安装")

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in files:
            zf.write(file, file.relative_to(plugin_dir).as_posix())
    return out_path


def main():
    parser = argparse.ArgumentParser(description="打包 Calibre 插件 zip")
    parser.add_argument("--outdir", default=None, help="输出目录（默认 dist/）")
    args = parser.parse_args()
    out = build(args.outdir)
    size_kb = out.stat().st_size / 1024
    print(f"已打包 {out}（{size_kb:.1f} KB）")


if __name__ == "__main__":
    main()
