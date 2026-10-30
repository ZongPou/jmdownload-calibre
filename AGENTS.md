# AGENTS.md

本项目由 AI 编码代理协作开发。本文件是跨会话/跨工具的上下文锚点，决策变更时须同步更新。

## 项目目标与当前状态

把上游 CLI 工具（jmcomic-calibre，`jmcal` 命令）改造为 **Calibre GUI 插件**：
输入禁漫漫画 ID → 自动下载 → 打包 CBZ（内嵌 ComicInfo.xml）→ 带元数据直接入库 Calibre。

**当前状态：v0.2.8 本地修复候选版；v0.2.7 阶段 1-4 已验收，处于阶段 5（发布）**。
- 2026-10-31：日志中漫画 364522 有 314 张图片 SSL 中断/超时后失败。bridge 固定章节并发 1、图片并发 4，避免上游默认 30 × CPU 核心数放大连接；仍需用户真实站点验证，不能认定站点限流或网络问题已解决。
- 新构建：`dist/jmdownload-calibre-v0.2.8.zip`；离线测试 46 项（含大合集并发限制及失败不报下载完成）。旧发布简报只适用于 v0.2.7。
- 发布物：`dist/jmdownload-calibre-v0.2.7.zip`（构建产物）
- 本地 main 领先 origin/main **25 个提交**（未推送）
- 测试：`python -m unittest tests.test_plugin`，45 项全过（离线，不碰网络）
- 工作树 clean
- 发布交接简报：`reports/release/release-v0.2.7_review_brief.md`（发布操作按它执行）

## 功能清单（v0.2.7）

- 批量输入漫画 ID/网页链接（自动提取 ID、去重、注释行支持）
- 子进程桥调用系统 Python 的 jmcomic 下载（防黑框、可取消、取消清理半成品）
- 自然排序打包 CBZ（内嵌 ComicInfo.xml，Anansi 规范）
- 元数据随书入库（标题/作者/标签/简介/日期/封面，legacy add_books 路径，视图即时刷新）
- 双标识符：`jmcomic:<id>` 判重 + `url:` 可点击跳转（域名可配置）
- 判重跳过（identifiers 精确搜索）
- 精确进度条（page_count 百分比，n/total 显示；无总页数时回退 busy）
- 工具栏分体按钮 + 下拉菜单（下载/配置/环境检测）
- 配置面板（解释器/域名/代理/临时目录/判重开关/保留开关 + 环境测试按钮）
- 会话日志一键复制（状态变化全记录 + 失败堆栈 + jmcomic 日志尾部，环境头信息）

## 冻结的架构决策与踩坑清单（勿推翻；新代码必须遵守）

- **下载引擎**：子进程桥调用系统 Python 的 jmcomic（curl-cffi/pycryptodome 为二进制依赖，无法进插件 zip）。
- **bridge 必须 sys.path 隔离**：jmcomic 内部有裸导入 `from common import ...`，
  脚本目录若有 common.py 会劫持（已实现 `_isolate_script_dir`，勿删）。
- **入库走 legacy 层** `gui.current_db.add_books([cbz], ['CBZ'], [mi], return_ids=True)`。
  **严禁 new_api.add_books 直写**——不同步 GUI 数据缓存，需重启才可见（实测踩坑）。
- **判重**：`db.new_api.search('identifiers:"=jmcomic:<id>"')`（Cache 没有 get_book_id_from_identifier）。
- **worker 信号命名**：禁止叫 `event`（遮蔽 QObject.event → "native Qt signal is not callable" 闪退，
  已改名 message_received）。
- **QThread 生命周期**：无 Qt parent；`finished` → UI 复位 + `deleteLater`；结束后不解除
  Python 引用（提前置 None 会被 GC 析构致闪退，实测踩坑）。
- **防黑框**：所有 subprocess（worker/doctor）Windows 上必须 `creationflags=CREATE_NO_WINDOW`。
- **get_icons/get_resources** 是插件系统注入的 builtins，直接调用、**不要 import**
  （新版 calibre.gui2 顶层没有 get_icons，import 即炸）。
- **JSONConfig**（calibre 9.x）无 defaults 构造参数，用 setdefault 注入默认值。
- **books_added(num) 必须传数量**；入库后需手动触发视图刷新（books_added/refresh_cover_browser/
  tags_view.recount，各步骤独立容错）。
- **配置界面**：is_customizable/config_widget/save_settings 须在**包装类与 actual plugin 两边都实现**
  （首选项面板检查包装类）；ConfigWidget 的 Qt 导入延迟到方法调用。
- **identifier**：双写 `jmcomic:<id>`（判重）+ `url:<域名>/album/<id>/`（跳转，域名可配置）。
- **ComicInfo.xml** 定位是文件自描述与第三方阅读器兼容；**Calibre 导入 CBZ 不读它**（源码已核实）。
- **metadata.opf** 由 Calibre 入库后自动生成，插件不生成不导入。
- **测试纪律**：提交前必须 `python -m unittest tests.test_plugin` 全过——
  串行命令里测试失败后仍会继续打包提交（踩过），测试与提交分开跑。

## 环境信息（用户机器：Windows / PowerShell）

- Calibre 9.15（内嵌 Python 3.14；JSONConfig 无 defaults 参数，用 setdefault 注入默认值）
- 系统 Python 3.13.13 @ `C:\Program Files\Python313\python.exe`；jmcomic 2.7.8（--user 安装）
- 公开仓库目标：`ZongPou/jmdownload-calibre`；内部插件包名保持 `jmcomic2calibre`
- git remote：当前工作区仍指向旧远程，待用户在 GitHub 完成仓库改名后再更新 remote
- 本地仓库根 = 工作区根 `c:/Users/zongp/Documents/ChatGPT/jmcomic2calibre`
- 诊断脚本：`scripts/diag_meta.py`（查元数据定位网络问题）、`scripts/diag_fields.py`（字段探测）、
  bridge.py `--meta-only`

## 分工边界（重要）

- 代理：代码、离线单测（不碰网络）、构建 zip、git 提交
- 用户：真实站点联调、Calibre GUI 验收、内容 QC、GitHub push/Release（需用户凭证）
- 测试：`python -m unittest tests.test_plugin`（45 项，全离线）

## 阶段计划与进度

1. [x] 插件骨架（对话框/JSONConfig/doctor/构建脚本）
2. [x] 子进程下载桥（JSON-lines 事件协议/进度轮询/取消）
3. [x] 入库（CBZ+ComicInfo.xml+legacy add_books/判重/双标识符/封面/视图即时刷新）
4. [x] 打磨（4A 配置面板 / 4B 精确进度条 / 4C 下拉菜单 / 4D 日志一键复制 /
       取消闪退修复 / 中途取消清理半成品 / 防黑框全覆盖）
5. [ ] **发布（进行中，交接简报见 reports/release/）**：
   - push 25 个提交到 origin/main（需用户凭证）
   - 打 tag `v0.2.7` 并推送
   - 创建 GitHub Release：标题 `v0.2.7`，上传 `dist/jmdownload-calibre-v0.2.7.zip`，
     说明文案见交接简报第三节
   - README 增补插件安装/使用说明（仓库现有 README 是上游 CLI 的）

## 协作约定

- 每轮任务完成后 git 暂存提交；提交信息按阶段浓缩关键词
- 提交前必须先跑测试全过（测试与提交分开执行）
- 不生成一次性总结报告文件；AGENTS.md 是唯一持久上下文，
  交接/验收关口另出 reports/ 简报
- 遇到需要推翻"冻结决策/踩坑清单"的想法：先向用户陈述理由，获同意后改本文件再动代码
