# AGENTS.md

本项目由 AI 编码代理协作开发。本文件是跨会话/跨工具的上下文锚点，决策变更时须同步更新。

## 项目目标

把上游 CLI 工具（jmcomic-calibre，`jmcal` 命令）改造为 **Calibre GUI 插件**：
输入禁漫漫画 ID → 自动下载 → 打包 CBZ（内嵌 ComicInfo.xml）→ 带元数据直接入库 Calibre。

## 冻结的架构决策（勿推翻，变更需用户明确同意）

- **下载引擎**：插件通过**子进程桥**调用系统 Python 里 pip 安装的 jmcomic。
  原因：jmcomic 依赖 curl-cffi、pycryptodome（C 扩展二进制），无法打包进 Calibre 插件 zip。
- **入库**：插件进程内 `db.new_api.add_books([(mi, {'CBZ': stream})])` 直接写 Metadata 对象
  （含 title/authors/tags/pubdate/comments/identifiers/封面），不使用 calibredb 子进程。
- **判重**：入库前 `db.new_api.get_book_id_from_identifier('jmcomic:<id>')`。
  注意：add_books 自身只按 title/author 判重，**不认 identifiers**，判重必须自己做。
- **标识符**：双写 `jmcomic:<id>`（判重，域名无关）+ `url:https://18comic.vip/album/<id>/`
  （可点击跳转；域名做成可配置项，禁漫有多镜像）。
- **metadata.opf**：Calibre 入库后在书库书籍目录**自动生成**，插件不生成、不导入。
- **ComicInfo.xml**：打进 CBZ，但定位是"文件自描述 + 第三方阅读器兼容"（Kavita/Komga/YACReader/Mihon），
  **与 Calibre 元数据导入无关**。
- **复用边界**：`src/jmcomic_calibre/metadata.py`（AlbumMeta/export_opf，需扩展双标识符）、
  `convert.py`（自然排序 CBZ，需加 ComicInfo.xml 注入口）；`library.py`（calibredb）仅供 CLI 保留，插件不用。
- **Calibre 不读 CBZ 内嵌 ComicInfo.xml**（已源码核实：`comic_input.py` 不解析；
  `archive.py` 只读 ZIP 注释里的 ComicBookInfo JSON）。原生 Calibre 唯一会自动读的 CBZ 元数据是 ZIP 注释，
  本方案不采用，仅作技术备忘。

## 环境信息（用户机器：Windows / PowerShell）

- Calibre 9.15；插件 `minimum_calibre_version = (7, 0, 0)`
- Python 3.13.13 @ `C:\Program Files\Python313\python.exe`
- jmcomic 2.7.8（`pip install --user`，PATH 上的 python 直接可 import；插件 doctor 自动探测，
  `python_path` 配置项留空即用系统 Python，可填 venv 解释器路径切换）
- git remote：`origin` = ZongPou/jmcomic2calibre（用户 fork），`upstream` = yifenliwu/jmcomic-calibre（同步上游）
- 本地仓库根 = 工作区根 `c:/Users/zongp/Documents/ChatGPT/jmcomic2calibre`

## 分工边界（重要）

- 代理：写全部代码、离线单元测试（mock jmcomic，不碰网络）、构建 zip、git 提交
- 用户：真实站点联调（下载/CF 绕过/图片解密验证）、Calibre GUI 安装与验收、内容正确性 QC、
  代理环境配置、发布 Release
- 开局联调信息：Calibre 版本、jmcomic 版本、真实 album 元数据 JSON 结构（`meta_from_album` 映射已确认：
  name/authors/tags/description/pub_date）

## 阶段计划与进度

1. [x] 插件骨架：`calibre_plugin/`（plugin-import-name 标记、双层 `__init__.py`/`ui.py`）、
       ID 输入对话框、JSONConfig（python_path/域名/代理/格式）、doctor 环境探测、构建 zip 脚本
       （2026-10-10 完成；纯逻辑集中在 common.py 供离线单测；`python build_plugin.py` 出
       dist/jmcomic2calibre-v0.1.0.zip；`python -m unittest tests.test_plugin` 27 项全过）
2. [ ] 子进程下载桥：调用系统 Python 跑下载 + 元数据采集，stdout JSON-lines 事件协议（进度/结果/错误）
3. [ ] 入库：CBZ 打包（含 ComicInfo.xml）+ add_books（判重跳过/双标识符/封面）
4. [ ] 批量 ID、进度对话框、取消、错误处理、配置界面完善
5. [ ] 发布：构建产物 zip 不进 git，GitHub Release 由用户发布

## 协作约定

- 每轮任务完成后 git 暂存提交；提交信息按阶段浓缩关键词（如"阶段1: 插件骨架/doctor/构建脚本"）
- 不生成一次性总结报告文件；本文件是唯一的持久上下文
- 遇到需要推翻"冻结决策"的想法：先向用户陈述理由，获明确同意后修改本文件再动代码
