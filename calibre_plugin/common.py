"""插件通用逻辑：输入解析、环境探测、默认配置。

本模块只依赖 Python 标准库，不 import calibre / Qt，
保证在没有 Calibre 的环境里也能离线单元测试。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

# ---------- 默认配置（由 config.py 用 JSONConfig 包装） ----------

DEFAULTS = {
    "python_path": "",        # 自定义 Python 解释器路径；留空 = 自动探测
    "web_domain": "https://18comic.vip",   # 标识符 url: 用的域名（禁漫多镜像）
    "proxy": "",              # 代理地址如 http://127.0.0.1:7890；留空 = 直连
    "output_format": "CBZ",   # 下载后打包格式（当前仅 CBZ）
    "check_duplicates": True, # 入库前按 jmcomic:<id> 判重
    "keep_workdir": False,    # 保留下载临时目录（排障用）
    "work_dir": "",           # 下载临时目录；留空 = 系统临时目录
    "download_timeout": 1800, # 单本下载超时（秒）
    "auto_download_chapters": 3,
}


def parse_chapter_range(text: str, count: int) -> list[int]:
    """解析界面中的章节序号，返回按原书顺序排列的选择；非法输入整次拒绝。"""
    selected = set()
    for part in re.split(r"[,，、\s]+", text.strip()):
        if not part:
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not match:
            raise ValueError("请输入章节序号或范围，例如 1-10、12、15-18")
        start = int(match[1])
        end = int(match[2] or start)
        if not 1 <= start <= end <= count:
            raise ValueError("章节范围必须在 1 到 %d 之间，且起点不大于终点" % count)
        selected.update(range(start, end + 1))
    if not selected:
        raise ValueError("请至少选择一集")
    return sorted(selected)


def chapter_label(numbers: list[int]) -> str:
    groups = []
    for n in sorted(set(numbers)):
        if groups and n == groups[-1][-1] + 1:
            groups[-1].append(n)
        else:
            groups.append([n])
    return "、".join(str(g[0]) if len(g) == 1 else f"{g[0]}-{g[-1]}" for g in groups)


def download_title(title: str, numbers: list[int], fallback: str) -> str:
    """下载命名：漫画名 第1-10话；只清理标题开头的方括号附注。"""
    original = str(title or "").strip() or fallback
    name = re.sub(r"^(?:\s*(?:\[[^\[\]]*\]|【[^【】]*】))+\s*", "", original).strip()
    name = name or original  # 整个标题都在括号中时保留，避免丢失书名。
    return f"{name} 第{chapter_label(numbers)}话" if numbers else name


def selection_key(album_id: str, chapters: list[dict], selected: list[str]) -> str:
    """整本保留旧标识符；选集独立判重，避免挡住同一本的其他章节。"""
    import hashlib
    ids = [str(c["id"]) for c in chapters]
    if not selected or set(selected) == set(ids):
        return album_id
    digest = hashlib.sha256(",".join(i for i in ids if i in selected).encode()).hexdigest()[:16]
    return f"{album_id}-s{digest}"

# ---------- 输入解析 ----------

ALBUM_URL_RE = re.compile(r"/album/(\d+)", re.IGNORECASE)
BARE_ID_RE = re.compile(r"^(\d{2,})$")


def parse_album_ids(text: str) -> tuple[list[str], list[str]]:
    """把多行输入解析成漫画 ID 列表。

    每行支持：纯数字 ID（如 ``350234``）、含 ``/album/<id>`` 的网页链接、
    以 ``#`` 开头的注释行。返回 ``(ids, errors)``：ids 按出现顺序去重，
    errors 是无法识别的原始行。
    """
    ids: list[str] = []
    errors: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = BARE_ID_RE.match(line)
        if match:
            album_id = match.group(1)
        else:
            match = ALBUM_URL_RE.search(line)
            album_id = match.group(1) if match else None
        if album_id is None:
            errors.append(line)
        elif album_id not in ids:
            ids.append(album_id)
    return ids, errors


# ---------- 环境探测（doctor） ----------

# 在目标解释器里执行：一次性报告 Python 版本 + jmcomic 版本
PROBE_CODE = (
    "import sys, json\n"
    "info = {'python': '.'.join(map(str, sys.version_info[:3]))}\n"
    "try:\n"
    "    import jmcomic\n"
    "    info['jmcomic'] = str(getattr(jmcomic, '__version__', '?'))\n"
    "except Exception as exc:\n"
    "    info['error'] = repr(exc)\n"
    "print(json.dumps(info))\n"
)

_PROBE_TIMEOUT = 20  # 秒；Store 存根/损坏解释器要尽快放弃
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # 防止弹出控制台黑框


def python_candidates(
    custom_path: str = "", which=shutil.which
) -> list[list[str]]:
    """列出候选解释器的启动命令（按优先级）。

    自定义路径 > PATH 上的 python / python3 > py 启动器。
    Windows 商店的 python.exe 存根（执行不跑真 Python）会被过滤掉。
    """
    out: list[list[str]] = []
    seen: set[str] = set()

    def add(cmd: list[str]) -> None:
        key = " ".join(cmd).lower()
        if key not in seen:
            seen.add(key)
            out.append(cmd)

    if custom_path:
        add([custom_path])
    for name in ("python", "python3"):
        exe = which(name)
        if exe and "windowsapps" not in exe.lower():
            add([exe])
    if which("py"):
        add(["py", "-3"])
    return out


def parse_probe_output(stdout: str, returncode: int, cmd: list[str]) -> dict:
    """解析探测脚本输出。取 stdout 中最后一个可解析的 JSON 行。"""
    info = None
    for line in (stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                info = json.loads(line)
            except ValueError:
                continue
    if not isinstance(info, dict):
        return {
            "ok": False,
            "error": f"解释器无有效输出（退出码 {returncode}）",
            "cmd": cmd,
        }
    result = {"ok": "error" not in info, "cmd": cmd}
    result.update(info)
    return result


def probe_interpreter(
    cmd: list[str], timeout: int = _PROBE_TIMEOUT
) -> dict:
    """实际运行一次探测。cmd 形如 ['python'] 或 ['py', '-3']。"""
    try:
        proc = subprocess.run(
            list(cmd) + ["-c", PROBE_CODE],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "cmd": cmd}
    return parse_probe_output(proc.stdout, proc.returncode, cmd)


def doctor(
    custom_path: str = "", which=shutil.which, probe=probe_interpreter
) -> dict:
    """依次探测候选解释器，返回第一个可 import jmcomic 的结果。

    全部失败时返回最后一个探测结果；一个候选都没有时返回说明性错误。
    which / probe 可注入，便于离线测试。
    """
    last: dict | None = None
    for cmd in python_candidates(custom_path, which):
        last = probe(cmd)
        if last.get("ok"):
            return last
    if last is None:
        last = {"ok": False, "error": "未找到任何 Python 解释器", "cmd": None}
    return last


def describe_probe(result: dict) -> str:
    """把探测结果转成一行人类可读的状态文本。"""
    if not result:
        return "环境未检测"
    if result.get("ok"):
        py = result.get("python", "?")
        jm = result.get("jmcomic", "?")
        cmd = " ".join(result.get("cmd") or [])
        return f"环境 OK：Python {py} + jmcomic {jm}（{cmd}）"
    error = result.get("error", "未知原因")
    cmd = " ".join(result.get("cmd") or []) or "未找到解释器"
    return f"环境异常：{error}（{cmd}）"


# ---------- 桥接事件流解析 ----------


def parse_event_line(line: str) -> dict | None:
    """把 bridge 输出的一行文本解析成事件 dict。

    合法 JSON 行 → 事件（必须含字符串 event 字段，否则视为日志）；
    非 JSON 行（jmcomic/第三方库的杂音输出）→ {"event": "log", ...}；
    空行 → None。
    """
    text = (line or "").strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("event"), str):
            return data
    return {"event": "log", "message": text}
