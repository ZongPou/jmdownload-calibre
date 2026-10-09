# AGENTS.md

本项目由 AI 编码代理协作开发。本文件是跨会话/跨工具的上下文锚点，决策变更时须同步更新。

## 项目目标

把上游 CLI 工具（jmcomic-calibre，`jmcal` 命令）改造为 **Calibre GUI 插件**：
输入禁漫漫画 ID → 自动下载 → 打包 CBZ（内嵌 ComicInfo.xml）→ 带元数据直接入库 Calibre。

当前状态：**v0.2.2，核心链路（下载→打包→入库→视图刷新）已全部打通并通过用户验收**；
配置界面已就位；剩阶段 4 打磨项（精确进度条/批量体验/日志面板）与阶段 5（发布）。

## 冻结的架构决策（勿推翻，变更需用户明确同意）

- **下载引擎**：插件通过**子进程桥**调用系统 Python 里 pip 安装的 jmcomic。
  原因：jmcomic 依赖 curl-cffi、pycryptodome（C 扩展二进制），无法打包进 Calibre 插件 zip。
  ⚠️ jmcomic 内部有裸导入 `from common import ...`（依赖 commonx 的顶层 common 模块）——
  bridge.py 启动时必须把脚本所在目录移出 sys.path（已实现 _isolate_script_dir），否则被劫持。
- **入库**：走 **legacy 层** `gui.current_db.add_books([cbz_path], ['CBZ'], [mi], return_ids=True)`，
  mi 携带 title/authors/tags/pubdate/comments/identifiers/封面。**不能用 new_api.add_books 直写**——
  它不同步 GUI 数据缓存，入库后要重启 calibre 才能看到新书（2026-10-10 实测踩坑）。
  不使用 calibredb 子进程。
- **判重**：入库前 `db.new_api.search('identifiers:"=jmcomic:<id>"')`（Cache 没有
  get_book_id_from_identifier，那是旧 legacy API）。add_books 自身只按 title/author 判重，
  **不认 identifiers**，判重必须自己做。
- **标识符**：双写 `jmcomic:<id>`（判重，域名无关）+ `url:<域名>/album/<id>/`
  （可点击跳转；域名做成可配置项，禁漫有多镜像）。
- **metadata.opf**：Calibre 入库后在书库书籍目录**自动生成**，插件不生成、不导入。
- **ComicInfo.xml**：打进 CBZ，但定位是"文件自描述 + 第三方阅读器兼容"（Kavita/Komga/YACReader/Mihon），
  **与 Calibre 元数据导入无关**（已源码核实：Calibre 导入 CBZ 不读包内 ComicInfo.xml）。
- **配置界面**：is_customizable/config_widget/save_settings 必须在**包装类**（__init__.py 的
  InterfaceActionBase 子类）与 actual plugin **两边都实现**——首选项面板检查的是包装类。
  ConfigWidget 的 Qt 导入延迟到方法调用时（GUI 环境才有 Qt）。
- **防黑框**：所有 subprocess（worker 与 common.probe_interpreter）在 Windows 上必须带
  `creationflags=CREATE_NO_WINDOW`。
- **复用边界**：`src/jmcomic_calibre/metadata.py`（AlbumMeta/export_opf）仅供 CLI 共用；
  插件 zip 自包含，打包逻辑在 `calibre_plugin/packaging.py`（自然排序以文件名为键）；
  `library.py`（calibredb）仅供 CLI 保留，插件不用。
- **子进程环境**：bridge 由系统 Python 执行；stdout 仅 JSON 事件行（jmcomic 输出重定向 stderr），
  接收方把非 JSON 行视为日志；失败时 worker 附带日志尾部便于诊断。

## 环境信息（用户机器：Windows / PowerShell）

- Calibre 9.15（内嵌 Python 3.14；**新版 JSONConfig 不支持 defaults 参数**，用 setdefault 注入）；
  插件 `minimum_calibre_version = (7, 0, 0)`
- 系统 Python 3.13.13 @ `C:\Program Files\Python313\python.exe`
- jmcomic 2.7.8（`pip install --user`；插件 doctor 自动探测，`python_path` 留空即用系统 Python）
- git remote：`origin` = ZongPou/jmcomic2calibre（用户 fork），`upstream` = yifenliwu/jmcomic-calibre
- 本地仓库根 = 工作区根 `c:/Users/zongp/Documents/ChatGPT/jmcomic2calibre`
- 诊断工具：`scripts/diag_meta.py`（只查元数据不下载，定位网络/站点层问题）、
  bridge.py `--meta-only`

## 分工边界（重要）

- 代理：写全部代码、离线单元测试（mock jmcomic，不碰网络）、构建 zip、git 提交
- 用户：真实站点联调（下载/CF 绕过/图片解密验证）、Calibre GUI 安装与验收、内容正确性 QC、
  代理环境配置、GitHub Release 发布
- 测试命令：`python -m unittest tests.test_plugin`（45 项，全离线）

## 阶段计划与进度

1. [x] 插件骨架（对话框/JSONConfig/doctor/构建脚本）
2. [x] 子进程下载桥（JSON-lines 事件协议/进度轮询/取消）
3. [x] 入库：CBZ+ComicInfo.xml+legacy add_books（判重跳过/双标识符/封面/视图即时刷新）
4. [ ] 打磨：配置界面（已完成 v0.2.1）；剩：精确进度条、批量体验（"第 2/5 本"）、日志面板
5. [ ] 发布：README 起草（代理写）、GitHub Release 上传 zip（用户操作）

## 协作约定

- 每轮任务完成后 git 暂存提交；提交信息按阶段浓缩关键词（如"阶段1: 插件骨架/doctor/构建脚本"）
- 提交前必须先跑 `python -m unittest tests.test_plugin` 全过（踩过：串行命令里测试失败仍打包提交）
- 不生成一次性总结报告文件；本文件是唯一的持久上下文
- 遇到需要推翻"冻结决策"的想法：先向用户陈述理由，获明确同意后修改本文件再动代码
